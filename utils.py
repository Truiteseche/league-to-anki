import re
import requests
import hashlib
import time
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_TTL = 3600

def _cache_get(url, ttl=CACHE_TTL):
    key = hashlib.md5(url.encode()).hexdigest()
    path = CACHE_DIR / key
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < ttl:
            with path.open("r") as f:
                return json.load(f)
    return None

def _cache_set(url, data):
    key = hashlib.md5(url.encode()).hexdigest()
    path = CACHE_DIR / key
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f)

def http_get_json(url, retries=3, timeout=15, cache_ttl=CACHE_TTL):
    cached = _cache_get(url, cache_ttl)
    if cached is not None:
        return cached

    for attempt in range(retries):
        try:
            res = requests.get(url, timeout=timeout)
            res.raise_for_status()
            data = res.json()
            _cache_set(url, data)
            return data
        except requests.exceptions.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)

def http_get_file(url, dest, retries=3, timeout=15):
    """Download a binary file to `dest` unless it already exists. Returns the path."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(retries):
        try:
            res = requests.get(url, timeout=timeout)
            res.raise_for_status()
            dest.write_bytes(res.content)
            return dest
        except requests.exceptions.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)

_CONFIG_CACHE = None

def load_config():
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    cfg_path = Path(__file__).resolve().parent / "config.json"
    if not cfg_path.exists():
        _CONFIG_CACHE = {}
        return _CONFIG_CACHE
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            _CONFIG_CACHE = json.load(f)
            return _CONFIG_CACHE
    except json.JSONDecodeError:
        _CONFIG_CACHE = {}
        return _CONFIG_CACHE

def get_patch_id():
    data = http_get_json("https://ddragon.leagueoflegends.com/api/versions.json")
    return data[0]

def get_champs_list(PATCH_ID, lang):
    url = f"https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/data/{lang}/champion.json"
    data = http_get_json(url)
    return list(data["data"].values())

def get_champs_details(PATCH_ID, lang, champId):
    url = f"https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/data/{lang}/champion/{champId}.json"
    data = http_get_json(url)
    return data["data"][champId]

# Riot's tooltip markup -> inline styles. Standard HTML tags are kept; any other tag is
# dropped while its text is kept.
TAG_STYLES = {
    "magicdamage": "color: #00BFFF",
    "physicaldamage": "color: #FF4500",
    "truedamage": "color: #FFFFFF; font-weight: bold",
    "healing": "color: #32CD32",
    "shield": "color: #C0C0C0",
    "scaleap": "color: #BA55D3",
    "scalead": "color: #FF8C00",
    "scalemana": "color: #6495ED",
    "scalehealth": "color: #32CD32",
    "scalearmor": "color: #E0B050",
    "scalemr": "color: #7986CB",
    "scalelevel": "color: #c4c4a5",
    "status": "color: #FFA500",
    "speed": "color: #00CED1",
    "attackspeed": "color: #F9A825",
    "lifesteal": "color: #E57373",
    "onhit": "color: #F06292",
    "keyword": "font-weight: bold",
    "attention": "font-weight: bold",
    "keywordmajor": "color: #F0C75E; font-weight: bold",
    "keywordstealth": "color: #B39DDB",
    "spellname": "color: #FFD58A; font-weight: bold",
    "spellpassive": "color: #d39542; font-weight: bold",
    "spellactive": "color: #d39542; font-weight: bold",
    "recast": "color: #FFD700",
    "raritylegendary": "color: #FF9800",
    "rules": "color: #9E9E9E; font-style: italic; font-size: 0.9em",
}
KEPT_TAGS = {"br", "li", "ul", "ol", "b", "i", "strong", "em", "span", "div", "p"}


def colorize_riot_tags(html):
    def repl(m):
        closing, tag = m.group(1), m.group(2).lower()
        if tag in TAG_STYLES:
            return "</span>" if closing else f'<span style="{TAG_STYLES[tag]}">'
        return m.group(0) if tag in KEPT_TAGS else ""
    return re.sub(r"<(/?)([A-Za-z][A-Za-z0-9]*)\s*/?>", repl, html)


def sanitizeBurn(cdBurn, columns=None):
    """Render "8/7/6" as table cells; a shorter row's last cell spans the remaining columns."""
    values = cdBurn.split("/")
    cells = [f"<td>{v}</td>" for v in values]
    if columns and len(values) < columns:
        cells[-1] = f'<td colspan="{columns - len(values) + 1}">{values[-1]}</td>'
    return "".join(cells)


# Responsive layout. The sections keep their inline styles; these rules override them
# (hence !important). The card is always fluid, up to 700px wide, and on narrow screens
# (phones, a small Anki window) it also gets a compact layout so nothing scrolls sideways.
CARD_CSS = """
<style>
.lol-card { width: auto !important; max-width: 700px; box-sizing: border-box; overflow-wrap: anywhere; }
.lol-card * { box-sizing: border-box; }
.lol-card img { max-width: 100%; }
.lol-card table { max-width: 100%; }
@media (max-width: 720px) {
    .lol-card { margin: 0 auto !important; padding: 6px !important; font-size: 15px; }
    .lol-card h2 { font-size: 1.3em !important; }
    .lol-card h3 { font-size: 1.05em !important; }
    .lol-card .lol-section { padding: 6px 2px !important; }
    .lol-card .lol-champ-header { gap: 12px !important; }
    .lol-card .lol-champ-portrait { width: 72px !important; height: 72px !important; flex-shrink: 0; }
    .lol-card .lol-tags span { display: inline-block; font-size: 13px !important; padding: 2px 8px !important; margin: 2px 4px 2px 0; }
    .lol-card .lol-ability-head { flex-wrap: wrap !important; gap: 8px 12px !important; align-items: center !important; }
    .lol-card .lol-ability-head h3 { flex: 1 1 calc(100% - 52px) !important; min-width: 0; margin: 0; }
    .lol-card .lol-ability-icon { width: 40px !important; height: 40px !important; flex-shrink: 0; }
    .lol-card .lol-cd { flex: 0 1 auto; font-size: 13px; }
    .lol-card .lol-cd td { padding-inline: 4px !important; }
    .lol-card .lol-item-icon { width: 48px !important; height: 48px !important; }
    .lol-card .lol-tree-row { flex-wrap: wrap !important; gap: 2px 6px !important; }
    .lol-card .lol-tree-row img { width: 20px !important; height: 20px !important; }
    .lol-card .lol-tree-children { padding-left: 10px !important; }
}
</style>"""


def wrap_card(parts):
    """Wrap rendered sections in the card container shared by champion and item cards."""
    return f"""
<div class="lol-card" style="text-align: left; background-color: #221f40; padding: 10px; border-radius: 8px; width: 700px; margin: 25px auto; border: 1px solid #c4c4a5">
    {"".join(parts)}
</div>{CARD_CSS}"""


DEFAULT_CHAMPION_FRONT = ["header"]
DEFAULT_CHAMPION_BACK = ["header", "abilities"]
CHAMPION_SECTIONS = {}


def _champ_header(PATCH_ID, champ):
    tags_html = '</span><span style="color:#c4c4a5; border: 1px solid #c4c4a5; border-radius: 50px; padding: 5px 10px; margin-right: 5px; font-size: 16px;">'.join(champ["tags"])
    return f"""
<div class="lol-champ-header" style="display: flex; flex-flow: row nowrap; align-items: center; gap: 20px;">
    <img class="lol-champ-portrait" src="https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img/champion/{champ["image"]["full"]}" style="border-radius: 6px;">
    <div style="display: flex; flex-flow: column nowrap; gap: 5px; min-width: 0">
        <h2 style="color:#d39542; margin-block: 0px; padding-block: 0px">{champ["id"]}</h2>
        <div style="color:#fff4bf">{champ["title"][0].upper() + champ["title"][1:]}</div>
        <div class="lol-tags" style="padding-block: 6px; opacity: 0.8">
            <span style="color:#c4c4a5; border: 1px solid #c4c4a5; border-radius: 50px; padding: 5px 10px; margin-right: 5px; font-size: 16px;">{tags_html}</span>
        </div>
    </div>
</div>"""


CHAMPION_SECTIONS["header"] = _champ_header


def _spell_rows(spell, resource):
    """(label, "a/b/c") rows for the cooldown, cost and range of a spell, skipping empty ones."""
    from tooltips import _icon  # tooltips imports this module
    rows = [(_icon("cooldown", 16) or "CD", spell.get("cooldownBurn", ""))]
    cost = spell.get("costBurn", "")
    if cost and any(float(v or 0) for v in cost.split("/") if v.replace(".", "", 1).isdigit()):
        rows.append((resource or "COST", cost))
    spell_range = spell.get("rangeBurn", "")
    if spell_range and spell_range not in ("0", "25000"):  # 25000 = self-cast / global
        rows.append((_icon("scaleRange", 16) or "RANGE", spell_range))
    return [(label, values) for label, values in rows if values]


def _ability_block(img_url, label, name, description, spell=None, resource=None):
    table = ""
    if spell is not None:
        rows = _spell_rows(spell, resource)
        cols = max(len(values.split("/")) for _, values in rows)
        table = f"""
            <table class="lol-cd" style="color:#fff4bf; text-align: center; border-collapse: collapse">
                {"".join(f'<tr><th style="text-align: left; padding-right: 10px">{lbl}</th>{sanitizeBurn(values, cols)}</tr>' for lbl, values in rows)}
            </table>"""
    align = " align-items: center;" if spell is not None else ""
    return f"""
    <div class="lol-section" style="padding: 10px">
        <div class="lol-ability-head" style="display: flex; flex-flow: row nowrap; gap: 20px;{align}">
            <img class="lol-ability-icon" src="{img_url}" style="border-radius: 6px;">
            <h3 style="flex: 1">({label}) {name}</h3>{table}
        </div>
        <div style="margin-top: 10px; line-height: 1.5">{colorize_riot_tags(description)}</div>
    </div>"""


def _champ_abilities(PATCH_ID, champ):
    cdn = f"https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img"
    passive = champ["passive"]
    # Game tooltips (values per rank, scalings) when they could be rendered, else Data Dragon's summary.
    tooltips = champ.get("_tooltips", {})
    blocks = [_ability_block(f"{cdn}/passive/{passive['image']['full']}", "P", passive["name"],
                             tooltips.get("P") or passive["description"])]
    for label, spell in zip("QWER", champ["spells"]):
        blocks.append(_ability_block(f"{cdn}/spell/{spell['image']['full']}", label, spell["name"],
                                     tooltips.get(label) or spell["description"], spell, champ.get("partype")))
    hr = '\n    <hr style="border: 1px solid #c4c4a5; border-radius: 50px">'
    return f"""
<div style="color:#fff4bf">{hr.join(blocks)}
</div>
<style>
.lol-cd td {{
    padding-inline: 10px;
}}
.lol-cd td:not(:last-child) {{
    border-right: 1px solid #c4c4a5;
}}
</style>"""


CHAMPION_SECTIONS["abilities"] = _champ_abilities


def _champ_lore(PATCH_ID, champ):
    lore = champ.get("lore", "").strip()
    if not lore:
        return ""
    return f"""
<div class="lol-section" style="padding: 10px">
    <h3 style="color: #d39542; margin-block: 5px">Lore</h3>
    <div style="color: #fff4bf; line-height: 1.5">{lore}</div>
</div>"""


CHAMPION_SECTIONS["lore"] = _champ_lore


def _champ_tips(PATCH_ID, champ):
    ally = champ.get("allytips", [])
    enemy = champ.get("enemytips", [])
    if not ally and not enemy:
        return ""
    parts = []
    if ally:
        parts.append(f'<h4 style="color: #32CD32; margin-block: 5px">As {champ["id"]}</h4>'
                      f'<ul style="color: #fff4bf; margin: 4px 0; padding-left: 20px">'
                      f'{"".join(f"<li>{t}</li>" for t in ally)}</ul>')
    if enemy:
        parts.append(f'<h4 style="color: #FF6347; margin-block: 5px">Vs {champ["id"]}</h4>'
                      f'<ul style="color: #fff4bf; margin: 4px 0; padding-left: 20px">'
                      f'{"".join(f"<li>{t}</li>" for t in enemy)}</ul>')
    return f"""
<div class="lol-section" style="padding: 10px">
    <h3 style="color: #d39542; margin-block: 5px">Tips</h3>
    {"".join(parts)}
</div>"""


CHAMPION_SECTIONS["tips"] = _champ_tips


def _champ_stats(PATCH_ID, champ):
    stats = champ.get("stats", {})
    if not stats:
        return ""
    labels = {
        "hp": "HP", "hpperlevel": "HP/lvl",
        "mp": "MP", "mpperlevel": "MP/lvl",
        "movespeed": "Move Speed",
        "armor": "Armor", "armorperlevel": "Armor/lvl",
        "spellblock": "MR", "spellblockperlevel": "MR/lvl",
        "attackdamage": "AD", "attackdamageperlevel": "AD/lvl",
        "attackspeed": "AS", "attackspeedperlevel": "AS/lvl",
        "attackrange": "Range",
        "hpregeneration": "HP Regen", "hpregenerationperlevel": "HP Regen/lvl",
        "mpregen": "MP Regen", "mpregenperlevel": "MP Regen/lvl",
        "critperlevel": "Crit/lvl",
    }
    rows = []
    for key, label in labels.items():
        val = stats.get(key)
        if val is not None:
            rows.append(f"<tr><td style='padding-right: 15px; color: #87CEEB'>{label}</td><td style='color: #fff4bf'>{val}</td></tr>")
    if not rows:
        return ""
    return f"""
<div class="lol-section" style="padding: 10px">
    <h3 style="color: #d39542; margin-block: 5px">Base Stats</h3>
    <table style="color: #fff4bf; border-collapse: collapse">{"".join(rows)}</table>
</div>"""


CHAMPION_SECTIONS["stats"] = _champ_stats


def _champ_info(PATCH_ID, champ):
    info = champ.get("info", {})
    if not info:
        return ""
    bars = []
    for label in ["attack", "defense", "magic", "difficulty"]:
        val = info.get(label)
        if val is not None:
            pct = val * 10
            bars.append(f"""
    <div style="margin: 4px 0">
        <div style="color: #87CEEB; font-size: 13px">{label.title()}</div>
        <div style="background: #3a3a5c; border-radius: 4px; height: 10px; width: 200px">
            <div style="background: #d39542; border-radius: 4px; height: 10px; width: {pct}%"></div>
        </div>
    </div>""")
    return f"""
<div class="lol-section" style="padding: 10px">
    <h3 style="color: #d39542; margin-block: 5px">Info</h3>
    {"".join(bars)}
</div>"""


CHAMPION_SECTIONS["info"] = _champ_info


def build_champ_card(PATCH_ID, champ, verso=False):
    cfg = load_config().get("champion_card", {})
    section_order = cfg.get("back" if verso else "front", DEFAULT_CHAMPION_BACK if verso else DEFAULT_CHAMPION_FRONT)

    parts = []
    for i, name in enumerate(section_order):
        if name in CHAMPION_SECTIONS:
            html = CHAMPION_SECTIONS[name](PATCH_ID, champ)
            if html:
                if i > 0:
                    parts.append('<hr style="border: 1px solid #c4c4a5; border-radius: 50px">')
                parts.append(html)

    return wrap_card(parts)
