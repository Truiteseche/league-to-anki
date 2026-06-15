import requests
from pathlib import Path
import json

def load_config():
    cfg_path = Path(__file__).resolve().parent / "config.json"
    if not cfg_path.exists():
        return {}
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def get_language(default: str = "en_US"):
    cfg = load_config()
    return cfg.get("language", default)

def get_patch_id():
    url = "https://ddragon.leagueoflegends.com/api/versions.json"
    res = requests.get(url)
    res.raise_for_status()
    data = res.json()
    return data[0]

def get_champs_list(PATCH_ID, lang):
    url = f"https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/data/{lang}/champion.json"
    res = requests.get(url)
    res.raise_for_status()
    data = res.json()
    return [data["data"][list(data["data"].keys())[i]] for i in range(len(data["data"]))]

def build_champ_card(PATCH_ID, champ):
    # return the html of a champ's card
    return f"""
<div style="background-color: #221f40; padding: 10px; border-radius: 8px; width: max-content; min-width: 500px; margin: 25px auto; border: 1px solid #c4c4a5">
    <div style="display: flex; flex-flow: row nowrap; align-items: center; gap: 20px">
        <img src="https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img/champion/{champ["image"]["full"]}" style="border-radius: 6px;">
        <div style="display: flex; flex-flow: column nowrap; gap: 5px">
            <h2 style="color:#d39542; margin-block: 10px; margin-block: 0px; padding-block: 0px">{champ["id"]}</h2>
            <div style="color:#fff4bf">{champ["title"][0].upper() + champ["title"][1:]}</div>
            <div style="padding-block: 6px; opacity: 0.8">
                <span style="color:#c4c4a5; border: 1px solid #c4c4a5; border-radius: 50px; padding: 5px 10px; margin-right: 5px; font-size: 16px;">{
                    '</span><span style="color:#c4c4a5; border: 1px solid #c4c4a5; border-radius: 50px; padding: 5px 10px; margin-right: 5px; font-size: 16px;">'.join(champ["tags"])
                }</span>
            </div>
        </div>
    </div>
</div>
"""
