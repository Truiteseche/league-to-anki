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

def get_language(default: str = "en_US"):
    cfg = load_config()
    return cfg.get("language", default)

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

def sanitizeBurn(cdBurn):
    return cdBurn.replace("/", "</td><td>")


DEFAULT_CHAMPION_FRONT = ["header"]
DEFAULT_CHAMPION_BACK = ["header", "abilities"]
CHAMPION_SECTIONS = {}


def _champ_header(PATCH_ID, champ):
    tags_html = '</span><span style="color:#c4c4a5; border: 1px solid #c4c4a5; border-radius: 50px; padding: 5px 10px; margin-right: 5px; font-size: 16px;">'.join(champ["tags"])
    return f"""
<div style="display: flex; flex-flow: row nowrap; align-items: center; gap: 20px;">
    <img src="https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img/champion/{champ["image"]["full"]}" style="border-radius: 6px;">
    <div style="display: flex; flex-flow: column nowrap; gap: 5px">
        <h2 style="color:#d39542; margin-block: 0px; padding-block: 0px">{champ["id"]}</h2>
        <div style="color:#fff4bf">{champ["title"][0].upper() + champ["title"][1:]}</div>
        <div style="padding-block: 6px; opacity: 0.8">
            <span style="color:#c4c4a5; border: 1px solid #c4c4a5; border-radius: 50px; padding: 5px 10px; margin-right: 5px; font-size: 16px;">{tags_html}</span>
        </div>
    </div>
</div>"""


CHAMPION_SECTIONS["header"] = _champ_header


def _champ_abilities(PATCH_ID, champ):
    return f"""
<div style="color:#fff4bf">
    <div style="padding: 10px">
        <div style="display: flex; flex-flow: row nowrap; gap: 20px">
            <img src="https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img/passive/{champ["passive"]["image"]["full"]}" style="border-radius: 6px;">
            <h3 style="flex: 1">(P) {champ["passive"]["name"]}</h3>
        </div>
        <div style="margin-top: 10px;">{champ["passive"]["description"]}</div>
    </div>
    <hr style="border: 1px solid #c4c4a5; border-radius: 50px">
    <div style="padding: 10px">
        <div style="display: flex; flex-flow: row nowrap; gap: 20px; align-items: center;">
            <img src="https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img/spell/{champ["spells"][0]["image"]["full"]}" style="border-radius: 6px;">
            <h3 style="flex: 1">(Q) {champ["spells"][0]["name"]}</h3>
            <table style="color:#fff4bf; text-align: center; border-collapse: collapse">
                <tr><th style="text-align: left;">CD</th><td>{sanitizeBurn(champ["spells"][0]["cooldownBurn"])}</td></tr>
                <tr><th style="text-align: left; padding-right: 10px">COST</th><td>{sanitizeBurn(champ["spells"][0]["costBurn"])}</td></tr>
            </table>
        </div>
        <div style="margin-top: 10px;">{champ["spells"][0]["description"]}</div>
    </div>
    <hr style="border: 1px solid #c4c4a5; border-radius: 50px">
    <div style="padding: 10px">
        <div style="display: flex; flex-flow: row nowrap; gap: 20px; align-items: center;">
            <img src="https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img/spell/{champ["spells"][1]["image"]["full"]}" style="border-radius: 6px;">
            <h3 style="flex: 1">(W) {champ["spells"][1]["name"]}</h3>
            <table style="color:#fff4bf; text-align: center; border-collapse: collapse">
                <tr><th style="text-align: left;">CD</th><td>{sanitizeBurn(champ["spells"][1]["cooldownBurn"])}</td></tr>
                <tr><th style="text-align: left; padding-right: 10px">COST</th><td>{sanitizeBurn(champ["spells"][1]["costBurn"])}</td></tr>
            </table>
        </div>
        <div style="margin-top: 10px;">{champ["spells"][1]["description"]}</div>
    </div>
    <hr style="border: 1px solid #c4c4a5; border-radius: 50px">
    <div style="padding: 10px">
        <div style="display: flex; flex-flow: row nowrap; gap: 20px; align-items: center;">
            <img src="https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img/spell/{champ["spells"][2]["image"]["full"]}" style="border-radius: 6px;">
            <h3 style="flex: 1">(E) {champ["spells"][2]["name"]}</h3>
            <table style="color:#fff4bf; text-align: center; border-collapse: collapse">
                <tr><th style="text-align: left;">CD</th><td>{sanitizeBurn(champ["spells"][2]["cooldownBurn"])}</td></tr>
                <tr><th style="text-align: left; padding-right: 10px">COST</th><td>{sanitizeBurn(champ["spells"][2]["costBurn"])}</td></tr>
            </table>
        </div>
        <div style="margin-top: 10px;">{champ["spells"][2]["description"]}</div>
    </div>
    <hr style="border: 1px solid #c4c4a5; border-radius: 50px">
    <div style="padding: 10px">
        <div style="display: flex; flex-flow: row nowrap; gap: 20px; align-items: center;">
            <img src="https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img/spell/{champ["spells"][3]["image"]["full"]}" style="border-radius: 6px;">
            <h3 style="flex: 1">(R) {champ["spells"][3]["name"]}</h3>
            <table style="color:#fff4bf; text-align: center; border-collapse: collapse">
                <tr><th style="text-align: left;">CD</th><td>{sanitizeBurn(champ["spells"][3]["cooldownBurn"])}</td></tr>
                <tr><th style="text-align: left; padding-right: 10px">COST</th><td>{sanitizeBurn(champ["spells"][3]["costBurn"])}</td></tr>
            </table>
        </div>
        <div style="margin-top: 10px;">{champ["spells"][3]["description"]}</div>
    </div>
</div>
<style>
td {{
    padding-inline: 10px;
}}
td:not(:last-child) {{
    border-right: 1px solid #c4c4a5;
}}
</style>"""


CHAMPION_SECTIONS["abilities"] = _champ_abilities


def _champ_lore(PATCH_ID, champ):
    lore = champ.get("lore", "").strip()
    if not lore:
        return ""
    return f"""
<div style="padding: 10px">
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
<div style="padding: 10px">
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
<div style="padding: 10px">
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
<div style="padding: 10px">
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

    return f"""
<div style="text-align: left; background-color: #221f40; padding: 10px; border-radius: 8px; width: 700px; margin: 25px auto; border: 1px solid #c4c4a5">
    {"".join(parts)}
</div>"""
