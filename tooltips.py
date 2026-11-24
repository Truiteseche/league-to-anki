"""Rebuild item and champion ability tooltips from the game's own data.

Data Dragon cannot evaluate the values the game computes when it shows a tooltip
(level ranges, stat scalings, melee/ranged splits, item cooldowns), so it prints
them as 0 (or as nothing in English), and its champion ability descriptions are
short summaries without any number. CommunityDragon exposes the raw game data for
every patch: item and champion definitions (data values per rank and calculations)
and the localized string table holding the tooltip templates. This module renders
those templates the way the game does, with the same stat icons.

Anything it does not understand raises `Unresolved`, and the caller keeps the
Data Dragon text, so a card is never worse than before.
"""
import re
import threading

from utils import http_get_json

CDRAGON = "https://raw.communitydragon.org"
CDRAGON_TEXTICONS = f"{CDRAGON}/latest/plugins/rcp-be-lol-game-data/global/default/assets/ux/fonts/texticons/lol"
VERSIONED_TTL = 30 * 24 * 3600  # versioned CommunityDragon files never change

# Text icons the game puts in tooltips (%i:name%), by directory. Inactive melee/ranged
# icons are the dimmed variants of the active ones: both values matter on a flashcard.
TEXT_ICON_FILES = {
    "statsicon": ["scaleap", "scalead", "scalearmor", "scalemr", "scalehealth", "scalemana", "scaleapen",
                  "scaleas", "scalems", "scalecrit", "scalecritmult", "scalelevel", "scalehealshield", "scalerange",
                  "onhit"],
    "gameplay": ["cooldown", "meleeactive", "rangedactive"],
}
TEXT_ICON_ALIASES = {"meleeinactive": "meleeactive", "rangedinactive": "rangedactive"}
DROPPED_TEXT_ICONS = {"activeeffect"}  # would sit before <active> and break the section layout

# mStat values seen in calculations, checked against the tooltips' own wording.
STAT_ICON = {0: "scaleap", 1: "scalearmor", 2: "scalead", 4: "scaleas", 6: "scalemr", 7: "scalems",
             8: "scalecrit", 9: "scalecritmult", 12: "scalehealth", 29: "scaleapen", 34: "scalehealshield"}
MANA = "scalemana"
# Stats that are themselves ratios (bonus attack speed, crit chance and damage, heal and shield
# power): "100% of crit damage" stays 100% even inside a value displayed as a percentage.
RATIO_STAT_ICONS = {"scaleas", "scalecrit", "scalecritmult", "scalehealshield"}
STAT_FORMULA_TOTAL, STAT_FORMULA_BASE, STAT_FORMULA_BONUS = 0, 1, 2


class Unresolved(Exception):
    pass


def text_icon_media_name(icon):
    folder = next(d for d, names in TEXT_ICON_FILES.items() if icon in names)
    return f"lol_stat_{icon}.png" if folder == "statsicon" else f"lol_ui_{icon}.png"


def text_icon_sources():
    """(media filename, url) for every icon this module can emit."""
    return [
        (text_icon_media_name(icon), f"{CDRAGON_TEXTICONS}/{folder}/{icon}.png")
        for folder, names in TEXT_ICON_FILES.items() for icon in names
    ]


def _icon(name, size=14):
    key = TEXT_ICON_ALIASES.get(name.lower(), name.lower())
    if key in DROPPED_TEXT_ICONS or not any(key in n for n in TEXT_ICON_FILES.values()):
        return ""
    return (f'<img src="{text_icon_media_name(key)}" '
            f'style="height: {size}px; width: {size}px; vertical-align: middle">')


def fnv1a(name):
    """CommunityDragon stores unknown names as the FNV-1a hash of their lowercase form."""
    h = 0x811C9DC5
    for c in name.lower().encode():
        h = ((h ^ c) * 0x01000193) & 0xFFFFFFFF
    return f"{{{h:08x}}}"


# ---------------------------------------------------------------------------
# Values. A number is a tuple: one value, or one value per spell rank.
# A Value is that number, or a level range, plus stat scalings; a Split holds the
# melee and ranged versions of a value.
# ---------------------------------------------------------------------------

def _vec(x):
    return tuple(float(v) for v in x) if isinstance(x, (list, tuple)) else (float(x),)


def _broadcast(a, b, op):
    if len(a) == 1 or len(b) == 1 or len(a) == len(b):
        n = max(len(a), len(b))
        return tuple(op(a[i % len(a)], b[i % len(b)]) for i in range(n))
    raise Unresolved("rank counts differ")


def _add(a, b):
    return _broadcast(a, b, lambda x, y: x + y)


def _mul(a, b):
    return _broadcast(a, b, lambda x, y: x * y)


class Value:
    def __init__(self, base=0.0, level=None, scalings=None):
        self.base = _vec(base)
        self.level = level  # (lo, hi): value at champion level 1 and 18
        self.scalings = scalings or []  # (coefficient tuple, icon, formula)
        if self.level is not None and any(self.base) and len(self.base) == 1:
            lo, hi = self.level
            self.level, self.base = (lo + self.base[0], hi + self.base[0]), (0.0,)

    @property
    def is_const(self):
        return self.level is None and not self.scalings

    def __add__(self, other):
        if self.level and other.level:
            level = (self.level[0] + other.level[0], self.level[1] + other.level[1])
        else:
            level = self.level or other.level
        return Value(_add(self.base, other.base), level, self.scalings + other.scalings)

    def scale(self, k):
        k = _vec(k)
        level = self.level
        if level is not None:
            if len(k) > 1:
                raise Unresolved("level range times rank values")
            level = (level[0] * k[0], level[1] * k[0])
        return Value(_mul(self.base, k), level, [(_mul(c, k), i, f) for c, i, f in self.scalings])


class Split:
    def __init__(self, melee, ranged):
        self.melee, self.ranged = melee, ranged

    def scale(self, k):
        return Split(self.melee.scale(k), self.ranged.scale(k))


def _num(x, precision=None):
    # One decimal by default: enough for every value in the game data, and it hides float
    # noise such as 30% x 0.667 = 20.01%.
    precision = 1 if precision is None else precision
    x = round(x, precision)
    if x == int(x):
        return str(int(x))
    return f"{x:.{precision}f}".rstrip("0").rstrip(".")


def nums(values, k=1.0, precision=None, suffix=""):
    """Per-rank values as "60/85/110", or a single number when every rank is the same."""
    shown = [f"{_num(v * k, precision)}{suffix}" for v in values]
    return shown[0] if len(set(shown)) == 1 else "/".join(shown)


class Tooltip:
    """Renders a tooltip template from named values and game calculations."""

    def __init__(self, values, calcs, strings):
        self.strings = strings
        self.values = {}
        for name, value in values.items():
            self._index(self.values, name, _vec(value))
        self.calcs = {}
        for name, calc in (calcs or {}).items():
            self._index(self.calcs, name, calc)
        self.percent = False
        self.precision = None

    @staticmethod
    def _index(table, name, value):
        table[name.lower()] = value
        if not name.startswith("{"):
            table[fnv1a(name)] = value

    def _get(self, table, name):
        key = name.lower()
        if key in table:
            return table[key]
        return table.get(fnv1a(name)) if not name.startswith("{") else None

    # -- calculations -------------------------------------------------------

    def const(self, part):
        v = self.part(part)
        if not isinstance(v, Value) or not v.is_const:
            raise Unresolved(f"non-constant multiplier {part.get('__type')}")
        return v.base

    def data_value(self, name):
        v = self._get(self.values, name)
        if v is None:
            raise Unresolved(f"data value {name}")
        return v

    def scalar(self, name):
        """A data value that must be the same at every rank (0 when absent or empty)."""
        if not name:
            return 0.0
        v = self._get(self.values, name)
        if v is None:
            raise Unresolved(f"data value {name}")
        if len(set(v)) > 1:
            raise Unresolved(f"rank-dependent value {name}")
        return v[0]

    @staticmethod
    def stat_scaling(stat, formula, coef):
        if stat not in STAT_ICON:
            raise Unresolved(f"stat {stat}")
        return Value(scalings=[(_vec(coef), STAT_ICON[stat], formula)])

    def part(self, p):
        t = p.get("__type")
        formula = p.get("mStatFormula", STAT_FORMULA_TOTAL)
        if t == "NumberCalculationPart":
            return Value(p.get("mNumber", 0.0))
        if t == "NamedDataValueCalculationPart":
            return Value(self.data_value(p["mDataValue"]))
        if t == "ByCharLevelInterpolationCalculationPart":
            return Value(level=(p.get("mStartValue", 0.0), p.get("mEndValue", 0.0)))
        if t == "ByCharLevelBreakpointsCalculationPart":
            return Value(level=self._breakpoints(p))
        if t == "ByCharLevelFormulaCalculationPart":  # one value per champion level, index = level
            values = p.get("values") or []
            if len(values) < 19:
                raise Unresolved("short level formula")
            return Value(level=(values[1], values[18]))
        if t == "{ee18a47b}":  # interpolation between two data values
            return Value(level=(self.scalar(p["StartDataValue"]), self.scalar(p["EndDataValue"])))
        if t == "{b22609db}":  # base + bonus per level after the first
            base, per_level = self.scalar(p["{91d404a5}"]), self.scalar(p["{b2cd0eb0}"])
            return Value(level=(base, base + per_level * 17))
        if t == "{4ce08984}":  # breakpoints whose amounts are data values
            return Value(level=self._breakpoints({
                "mLevel1Value": self.scalar(p.get("{91d404a5}")),
                "mInitialBonusPerLevel": self.scalar(p.get("{bbd778a2}")),
                "mBreakpoints": [
                    {"mLevel": bp.get("level", 0),
                     "mAdditionalBonusAtThisLevel": self.scalar(bp.get("{ae9b464d}")),
                     **({"mBonusPerLevelAtAndAfter": self.scalar(bp["{b0d8b2ac}"])} if "{b0d8b2ac}" in bp else {})}
                    for bp in p.get("{9823b29a}", [])
                ],
            }))
        if t == "StatByCoefficientCalculationPart":
            return self.stat_scaling(p.get("mStat", 0), formula, p.get("mCoefficient", 0.0))
        if t == "StatByNamedDataValueCalculationPart":
            return self.stat_scaling(p.get("mStat", 0), formula, self.data_value(p["mDataValue"]))
        if t == "StatBySubPartCalculationPart":
            return self.stat_scaling(p.get("mStat", 0), formula, self.const(p["mSubpart"]))
        if t == "AbilityResourceByCoefficientCalculationPart":
            return Value(scalings=[(_vec(p.get("mCoefficient", 0.0)), MANA, formula)])
        if t == "SumOfSubPartsCalculationPart":
            total = Value()
            for sub in p.get("mSubparts", []):
                total = total + self.part(sub)
            return total
        if t == "ProductOfSubPartsCalculationPart":
            a, b = self.part(p["mPart1"]), self.part(p["mPart2"])
            if a.is_const:
                return b.scale(a.base)
            if b.is_const:
                return a.scale(b.base)
            raise Unresolved("product of non-constant parts")
        if "mSpellCalculationKey" in p:  # a calculation reusing another one
            v = self.calc(p["mSpellCalculationKey"])
            if not isinstance(v, Value):
                raise Unresolved(f"calc reference {p['mSpellCalculationKey']}")
            return v
        raise Unresolved(f"part {t}")

    @staticmethod
    def _breakpoints(p):
        """Value at level 1 and level 18."""
        value = p.get("mLevel1Value", 0.0)
        rate = p.get("mInitialBonusPerLevel", 0.0)
        bps = {bp.get("mLevel", 0): bp for bp in p.get("mBreakpoints", [])}
        for level in range(2, 19):
            bp = bps.get(level)
            if bp:
                value += bp.get("mAdditionalBonusAtThisLevel", 0.0)
                if "mBonusPerLevelAtAndAfter" in bp:
                    rate = bp["mBonusPerLevelAtAndAfter"]
            value += rate
        return p.get("mLevel1Value", 0.0), value

    def calc(self, name):
        c = self._get(self.calcs, name)
        if c is None:
            return None
        t = c.get("__type")
        if t == "GameCalculationModified":
            base = self.calc(c["mModifiedGameCalculation"])
            if base is None:
                raise Unresolved(f"modified calc {name}")
            result = base.scale(self.const(c["mMultiplier"])) if "mMultiplier" in c else base
        elif "mFormulaParts" in c:
            result = Value()
            for p in c["mFormulaParts"]:
                result = result + self.part(p)
            if "mMultiplier" in c:
                result = result.scale(self.const(c["mMultiplier"]))
            if "mRangedMultiplier" in c:
                result = Split(result, result.scale(self.const(c["mRangedMultiplier"])))
        else:
            raise Unresolved(f"calc {t}")
        if c.get("mDisplayAsPercent"):
            self.percent = True
        precision = c.get("mPrecision")
        self.precision = precision if precision is not None and precision >= 0 else None  # -1 = default
        return result

    def lookup_single(self, name):
        v = self.calc(name)
        if v is not None:
            return v
        v = self._get(self.values, name)
        if v is not None:
            return Value(v)
        return None

    def lookup(self, name):
        self.percent, self.precision = False, None
        v = self.lookup_single(name)
        if v is not None:
            return v
        # Values that differ for melee and ranged champions are stored as two entries.
        split_suffix = "MeleeRangedSplit"
        base = name[:-len(split_suffix)] if name.endswith(split_suffix) else name
        pairs = [(base + "Melee", base + "Ranged"), (base, base + "Range"), (base, base + "Ranged")]
        if name.endswith(split_suffix):
            pairs.append(("MeleeItemCalcValue", "RangedItemCalcValue"))
        for melee_name, ranged_name in pairs:
            melee, ranged = self.lookup_single(melee_name), self.lookup_single(ranged_name)
            if isinstance(melee, Value) and isinstance(ranged, Value):
                return Split(melee, ranged)
        raise Unresolved(f"placeholder {name}")

    # -- formatting ---------------------------------------------------------

    def fmt_value(self, v, factor=1.0, percent_suffix=None):
        """`factor` comes from the template (@Name*100@); `percent_suffix` is the "%" the template
        writes right after the value, which is then already a percentage: it is moved onto the
        numbers so that the scalings come after it ("8% (+4% / 100 AP)")."""
        if isinstance(v, Split):
            nowrap = '<span style="white-space: nowrap">'
            return (f"({nowrap}{_icon('meleeActive')}{self.fmt_value(v.melee, factor, percent_suffix)}</span> | "
                    f"{nowrap}{_icon('rangedActive')}{self.fmt_value(v.ranged, factor, percent_suffix)}</span>)")
        pct = "%" if self.percent else (percent_suffix or "")
        k = factor * (100 if self.percent else 1)
        is_percentage = self.percent or percent_suffix is not None
        base = ""
        if v.level is not None:
            lo, hi = v.level
            base = (f"{_num(lo * k, self.precision)}{pct}&nbsp;-&nbsp;"
                    f"{_num(hi * k, self.precision)}{pct}{_icon('scaleLevel')}")
            if any(v.base):  # per-rank values plus a level-based bonus
                base = f"{nums(v.base, k, self.precision, pct)} (+{base})"
        elif any(v.base) or not v.scalings:
            base = nums(v.base, k, self.precision, pct)
        scalings = []
        for coef, icon, formula in v.scalings:
            modifier = ""
            if formula == STAT_FORMULA_BONUS:
                modifier = self.strings.get("tooltip_statsuidata_bonusiconmodifier", "")
            elif formula == STAT_FORMULA_BASE:
                modifier = self.strings.get("tooltip_statsuidata_baseiconmodifier", "")
            # Stats are counted in points (AP, AD, health...) or are ratios (crit, bonus attack
            # speed...), and the value is a number of points or a percentage: word each case so that
            # "X%" always reads as "X% of the stat".
            ratio_stat = icon in RATIO_STAT_ICONS
            if is_percentage and ratio_stat:
                shown = f"{nums(coef, k, 3, '%')}{_icon(icon)}"  # "100% crit damage"
            elif is_percentage:
                # gain per 100 points of the stat, as the game words it: "+4% / 100 AP"
                shown = f"{nums(coef, k * 100, 3, '%')}&nbsp;/&nbsp;100{_icon(icon)}"
            elif ratio_stat:
                # gain per 1% of the stat: "+0.5 / 1% crit chance", not "5000% crit chance"
                shown = f"{nums(coef, k * 0.01, 3)}&nbsp;/&nbsp;1%{_icon(icon)}"
            else:
                shown = f"{nums(coef, k * 100, 3, '%')}{_icon(icon)}"  # "+50% AP"
            scalings.append(shown + modifier)
        if not base:
            # Pure scaling (e.g. "2% of bonus mana"): the template already writes any leading "+".
            return " + ".join(scalings)
        return " ".join([base] + [f"(+{s})" for s in scalings])

    # -- templates ----------------------------------------------------------

    def render(self, text, depth=0):
        if depth > 8:
            raise Unresolved("template recursion")

        def include(m):
            key = m.group(1).strip()
            key = key.replace("@GameModeInteger@", "1")  # 1 = Summoner's Rift
            if "@ChampRange@" in key:
                # Show both values, "(melee | ranged)", instead of the in-game per-champion one.
                key = key.replace("@ChampRange@", "1").replace("_Dynamic", "")
            s = self.strings.get(key.lower())
            if s is None and re.search(r"@(?!f\d+@)[^@]+@", key):
                # Keys picked by a runtime state (e.g. _@IsEmpowered@): use the default variant.
                for state in ("0", "1"):
                    s = self.strings.get(re.sub(r"@(?!f\d+@)[^@]+@", state, key).lower())
                    if s is not None:
                        break
            if s is None:
                raise Unresolved(f"string {key}")
            return self.render(s, depth + 1)

        text = re.sub(r"\{\{\s*([^}]+?)\s*\}\}", include, text)
        # Values only known in a live game (@f1@, @f2@...): drop the "(...)" holding them.
        text = re.sub(r"\s*\((?:<[^>()]+>)*@f\d+@(?:</[^>()]+>)*\)", "", text)

        def placeholder(m):
            # @Name@, @Name*100@, @Name.1*100@ (".1": decimals shown), and @spell.Other:Name@
            # for a value of another spell of the same champion.
            other, name = m.group(1), m.group(2)
            digits, factor = m.group(3), float(m.group(4)) if m.group(4) else 1.0
            if re.fullmatch(r"f\d+", name):
                raise Unresolved(f"runtime value {name}")
            tip = self.other_spell(other) if other else self
            value = tip.lookup(name)
            if digits is not None:
                tip.precision = int(digits)
            return tip.fmt_value(value, factor, m.group(5))

        text = re.sub(r"@(?:[Ss]pell\.([A-Za-z0-9_]+):)?([A-Za-z0-9_{}]+)(?:\.(\d+))?(?:\*(-?[\d.]+))?@"
                      r"((?:&nbsp;|\s)?%)?", placeholder, text)
        text = re.sub(r"%i:([A-Za-z]+)%", lambda m: _icon(m.group(1)), text)
        return re.sub(r"</?if0is0>", "", text)

    def other_spell(self, name):
        raise Unresolved(f"spell reference {name}")


class ItemTooltip(Tooltip):
    def __init__(self, bin_item, strings):
        values = {dv["mName"]: dv.get("mValue", 0.0) or 0.0 for dv in bin_item.get("mDataValues", [])}
        super().__init__(values, bin_item.get("mItemCalculations"), strings)
        self.item = bin_item

    def lookup_single(self, name):
        v = super().lookup_single(name)
        if v is not None:
            return v
        v = self.item.get("m" + name)
        if isinstance(v, (int, float)):
            return Value(v)
        effect = re.fullmatch(r"Effect(\d+)Amount", name)
        amounts = self.item.get("mEffectAmount") or []
        if effect and 0 < int(effect.group(1)) <= len(amounts):
            return Value(amounts[int(effect.group(1)) - 1])
        return None


class SpellTooltip(Tooltip):
    """A champion spell. Rank arrays hold rank 0 at index 0, so ranks 1..N are values[1:N+1]."""

    def __init__(self, spell, strings, ranks, champion_spells=None):
        self.spell = spell
        self.ranks = ranks
        # {lowercase spell name: (mSpell, ranks)} for @spell.Name:Value@ references
        self.champion_spells = champion_spells or {}
        values = {dv["name"]: self._ranked(dv.get("values")) for dv in spell.get("DataValues") or [] if "name" in dv}
        super().__init__(values, spell.get("mSpellCalculations"), strings)

    def _ranked(self, values):
        if not values:
            return (0.0,)
        if self.ranks <= 1 or len(values) <= 1:
            return _vec(values[1] if len(values) > 1 else values[0])
        return _vec(values[1:self.ranks + 1])

    def other_spell(self, name):
        entry = self.champion_spells.get(name.lower())
        if not entry:
            raise Unresolved(f"spell reference {name}")
        spell, ranks = entry
        return SpellTooltip(spell, self.strings, ranks, self.champion_spells)

    def _effect_amount(self, index):
        amounts = self.spell.get("mEffectAmount") or []
        if 0 < index <= len(amounts):
            return self._ranked(amounts[index - 1].get("value"))
        raise Unresolved(f"effect amount {index}")

    def part(self, p):
        if p.get("__type") == "EffectValueCalculationPart":
            return Value(self._effect_amount(p.get("mEffectIndex", 0)))
        return super().part(p)

    def lookup_single(self, name):
        v = super().lookup_single(name)
        if v is not None:
            return v
        if name.lower() == "cooldown" and self.spell.get("cooldownTime"):
            return Value(self._ranked(self.spell["cooldownTime"]))
        if name.lower() == "cost":
            # Unlike the other rank arrays, costs start at rank 1.
            costs = (self.spell.get("manaValues") or {}).get("values") or self.spell.get("mana")
            if costs:
                return Value(_vec(costs[:self.ranks]))
        effect = re.fullmatch(r"Effect(\d+)Amount", name)
        if effect:
            return Value(self._effect_amount(int(effect.group(1))))
        for field in ("m" + name, name[:1].lower() + name[1:]):  # e.g. @MaxAmmo@ -> mMaxAmmo
            v = self.spell.get(field)
            if isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v):
                return Value(self._ranked(v))
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return Value(v)
        return None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _cdragon_json(path, PATCH_ID, timeout=120):
    """A CommunityDragon file for this patch, falling back to the latest version."""
    version = ".".join(PATCH_ID.split(".")[:2])
    try:
        return http_get_json(f"{CDRAGON}/{version}/{path}", timeout=timeout, cache_ttl=VERSIONED_TTL)
    except Exception:
        return http_get_json(f"{CDRAGON}/latest/{path}", timeout=timeout)


_STRINGS = {}
_STRINGS_LOCK = threading.Lock()


def load_strings(PATCH_ID, lang):
    """The localized string table (about 36 MB), loaded once per run."""
    key = (PATCH_ID, lang)
    with _STRINGS_LOCK:
        if key not in _STRINGS:
            try:
                path = f"game/{lang.lower()}/data/menu/en_us/lol.stringtable.json"
                _STRINGS[key] = _cdragon_json(path, PATCH_ID)["entries"]
            except Exception:
                _STRINGS[key] = None
        return _STRINGS[key]


def load_game_data(PATCH_ID, lang):
    """Item definitions and the localized string table, or None if CommunityDragon lacks them."""
    strings = load_strings(PATCH_ID, lang)
    if strings is None:
        return None
    try:
        bin_items = _cdragon_json("game/items.cdtb.bin.json", PATCH_ID)
    except Exception:
        return None
    by_id = {str(v["itemID"]): v for v in bin_items.values() if isinstance(v, dict) and "itemID" in v}
    return by_id, strings


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

def render_item_description(game_data, item_id, ddragon_description):
    """Data Dragon description with its text rebuilt from the game template, or None to keep it as is.

    The stats block stays the Data Dragon one: the card's stat table and icons rely on it.
    """
    by_id, strings = game_data
    bin_item = by_id.get(item_id)
    template = strings.get(f"generatedtip_item_{item_id}_description")
    stats = re.search(r"<stats>.*?</stats>", ddragon_description)
    if not bin_item or not template or not stats:
        return None

    sections = re.findall(r"<section>(.*?)</section>", template, re.S)
    body = []
    for section in sections:
        section = section.strip()
        if not section or "<flavorText>" in section:
            continue
        if not body and re.search(r"<attention>%i:scale", section):
            continue  # the stats block
        body.append(section)
    if not body:
        return None

    try:
        text = ItemTooltip(bin_item, strings).render("<br><br>".join(body))
    except Unresolved:
        return None
    return f"<mainText>{stats.group(0)}<br><br>{text}</mainText>"


# ---------------------------------------------------------------------------
# Champions
# ---------------------------------------------------------------------------

def _spell_tooltip(spell, strings, ranks, champion_spells=None):
    keys = (spell.get("mClientData") or {}).get("mTooltipData", {}).get("mLocKeys", {})
    template = strings.get(keys.get("keyTooltip", "").lower())
    if not template:
        raise Unresolved("no tooltip template")
    return SpellTooltip(spell, strings, ranks, champion_spells).render(template)


def _champion_spells(data, abilities):
    """Every spell of a champion by name, with the rank count of the ability slot it belongs to."""
    slot_ranks = {path: ranks for _, path, ranks in abilities if path}
    spells = {}
    for path, obj in data.items():
        if isinstance(obj, dict) and obj.get("__type") == "SpellObject" and obj.get("mSpell"):
            name = path.rsplit("/", 1)[-1].lower()
            # Spells outside the five slots (transformations, sub-casts) usually follow a basic ability.
            spells[name] = (obj["mSpell"], slot_ranks.get(path, 5))
    return spells


def render_champion_tooltips(PATCH_ID, lang, champ):
    """{"P"|"Q"|"W"|"E"|"R": tooltip html} for the abilities whose game tooltip could be rendered."""
    strings = load_strings(PATCH_ID, lang)
    if strings is None:
        return {}
    cid = champ["id"].lower()
    try:
        data = _cdragon_json(f"game/data/characters/{cid}/{cid}.bin.json", PATCH_ID)
    except Exception:
        return {}
    record = next((v for v in data.values() if isinstance(v, dict) and v.get("__type") == "CharacterRecord"), None)
    if not record:
        return {}

    abilities = [("P", record.get("mCharacterPassiveSpell"), 1)]
    for label, path, ddragon_spell in zip("QWER", record.get("spells", []), champ.get("spells", [])):
        abilities.append((label, path, ddragon_spell.get("maxrank", 5)))

    champion_spells = _champion_spells(data, abilities)
    tooltips = {}
    for label, path, ranks in abilities:
        spell = (data.get(path) or {}).get("mSpell")
        if not spell:
            continue
        try:
            tooltips[label] = _spell_tooltip(spell, strings, ranks, champion_spells)
        except Unresolved:
            pass
    return tooltips
