import re
from utils import http_get_json, load_config

TAG_COLORS = {
    "Damage": "#C62828",
    "SpellDamage": "#1565C0",
    "Health": "#2E7D32",
    "Armor": "#78909C",
    "SpellBlock": "#5C6BC0",
    "AttackSpeed": "#F9A825",
    "CriticalStrike": "#E65100",
    "LifeSteal": "#AD1457",
    "Mana": "#0D47A1",
    "ManaRegen": "#42A5F5",
    "HealthRegen": "#66BB6A",
    "CooldownReduction": "#7B1FA2",
    "AbilityHaste": "#7B1FA2",
    "Active": "#FF6F00",
    "NonbootsMovement": "#00ACC1",
    "ArmorPenetration": "#BF360C",
    "MagicPenetration": "#6A1B9A",
    "OnHit": "#E91E63",
    "Aura": "#00897B",
    "Tenacity": "#FF8F00",
    "Slow": "#37474F",
    "SpellVamp": "#C2185B",
    "Boots": "#4E342E",
}


def get_items_list(PATCH_ID, lang):
    url = f"https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/data/{lang}/item.json"
    raw = http_get_json(url)["data"]

    items = []
    for item_id, item in raw.items():
        if not item["gold"]["purchasable"]:
            continue
        if not item["maps"].get("11", False):
            continue
        if item.get("into"):
            continue
        if item["gold"]["total"] < 1400:
            continue
        item["_id"] = item_id
        items.append(item)

    return items, raw


def parse_stats_from_description(description):
    """Extract stat name/value pairs from Riot's description HTML."""
    match = re.search(r'<stats>(.*?)</stats>', description)
    if not match:
        return []

    stats_block = match.group(1)
    parts = stats_block.split('<br>')

    stats = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r'<attention>(.*?)</attention>\s*(.*)', part)
        if m:
            value = m.group(1).strip()
            name = m.group(2).strip()
            stats.append((name, value))

    return stats


DEFAULT_ITEM_FRONT = ["header"]
DEFAULT_ITEM_BACK = ["header", "stats", "description", "build_path", "gold"]
ITEM_SECTIONS = {}


def convert_riot_html(description):
    desc = re.sub(r'<stats>.*?</stats>', '', description)
    desc = re.sub(r'</?mainText>', '', desc)
    desc = desc.strip()
    desc = re.sub(r'^(<br>\s*)+', '', desc)
    desc = re.sub(r'(\s*<br>)+$', '', desc)

    if not desc:
        return ""

    # Mark ALL passive/active tags with null-byte-delimited tokens
    def mark_tag(match):
        tag = match.group(1)
        name = match.group(2)
        return f'\0{tag.upper()}:{name}\0'

    desc = re.sub(r'<(passive)>(.*?)</\1>', mark_tag, desc)
    desc = re.sub(r'<(active)>(.*?)</\1>', mark_tag, desc)

    # Split on <br> to separate sections
    sections = re.split(r'(?:<br>\s*)+', desc)

    # Build the HTML by distinguishing definition markers from inline references
    parts_html = []
    section_open = False

    for section in sections:
        section = section.strip()
        if not section:
            continue

        marker_match = re.match(r'\0(PASSIVE|ACTIVE):(.+?)\0\s*(.*)', section)
        if marker_match:
            if section_open:
                parts_html.append('</div>')
            tag_type = marker_match.group(1)
            ability_name = marker_match.group(2)
            rest = marker_match.group(3)
            color = '#FFD700' if tag_type == 'PASSIVE' else '#FF6347'
            bg = 'rgba(255, 215, 0, 0.08)' if tag_type == 'PASSIVE' else 'rgba(255, 99, 71, 0.08)'
            parts_html.append(
                f'<div style="background: {bg}; border-left: 3px solid {color}; '
                f'padding: 8px; margin: 8px 0; border-radius: 4px">'
                f'<strong style="color: {color}; font-size: 15px">{ability_name}</strong><br>'
                f'{rest}'
            )
            section_open = True
        else:
            # Continuation text: convert any inline markers back to plain names
            section = re.sub(r'\0(PASSIVE|ACTIVE):(.+?)\0', r'\2', section)
            parts_html.append(f'<br>{section}')

    if section_open:
        parts_html.append('</div>')

    desc = ''.join(parts_html)

    # Apply color conversions for damage types etc.
    conversions = [
        (r'<magicDamage>', '<span style="color: #00BFFF">'),
        (r'</magicDamage>', '</span>'),
        (r'<physicalDamage>', '<span style="color: #FF4500">'),
        (r'</physicalDamage>', '</span>'),
        (r'<healing>', '<span style="color: #32CD32">'),
        (r'</healing>', '</span>'),
        (r'<shield>', '<span style="color: #C0C0C0">'),
        (r'</shield>', '</span>'),
        (r'<scaleAP>', '<span style="color: #BA55D3">'),
        (r'</scaleAP>', '</span>'),
        (r'<scaleMana>', '<span style="color: #6495ED">'),
        (r'</scaleMana>', '</span>'),
        (r'<status>', '<span style="color: #FFA500">'),
        (r'</status>', '</span>'),
        (r'<speed>', '<span style="color: #00CED1">'),
        (r'</speed>', '</span>'),
        (r'<keyword>', '<strong>'),
        (r'</keyword>', '</strong>'),
        (r'<attention>', '<strong>'),
        (r'</attention>', '</strong>'),
    ]

    for pattern, replacement in conversions:
        desc = re.sub(pattern, replacement, desc)

    desc = re.sub(r'</?[A-Z][a-zA-Z0-9]*>', '', desc)

    return desc


def build_item_tree(item_id, all_items, memo=None):
    if memo is None:
        memo = {}
    if item_id in memo:
        return memo[item_id]

    item = all_items.get(item_id)
    if not item:
        return None

    node = {
        "id": item_id,
        "name": item["name"],
        "total": item["gold"]["total"],
        "combine": item["gold"]["base"],
        "image": item["image"]["full"],
        "children": []
    }

    for child_id in item.get("from", []):
        child = build_item_tree(child_id, all_items, memo)
        if child:
            node["children"].append(child)

    memo[item_id] = node
    return node


def render_tree_html(node, PATCH_ID, depth=0):
    if not node:
        return ""

    img = f"https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img/item/{node['image']}"
    has_children = bool(node["children"])
    combine_str = f" <span style='color: #666; font-size: 13px'>({node['combine']}g)</span>" if has_children else ""

    children_html = ""
    if has_children:
        children_parts = []
        for child in node["children"]:
            children_parts.append(render_tree_html(child, PATCH_ID, depth + 1))
        children_html = f'<div style="padding-left: 24px; border-left: 1px solid #3a3a5c;">{"".join(children_parts)}</div>'

    return f"""
    <div style="margin: 1px 0">
        <div style="display: flex; align-items: center; gap: 8px; padding: 3px 0">
            <img src="{img}" style="width: 24px; height: 24px; border-radius: 3px">
            <span style="color: #e8e0d0; font-size: 14px">{node['name']}</span>
            <span style="color: #FFD700; font-size: 14px">{node['total']}g</span>
            {combine_str}
        </div>
        {children_html}
    </div>"""


def _item_stats(item):
    stats = parse_stats_from_description(item.get("description", ""))
    if not stats:
        return ""
    rows = []
    for name, value in stats:
        rows.append(
            f"<tr><td style='padding-right: 15px; color: #87CEEB'>{name}</td>"
            f"<td style='color: #fff4bf'>{value}</td></tr>"
        )
    return f"""
<div style="padding: 10px">
    <h3 style="color: #d39542; margin-block: 5px">Stats</h3>
    <table style="color: #fff4bf; border-collapse: collapse">{"".join(rows)}</table>
</div>"""


ITEM_SECTIONS["stats"] = lambda PATCH_ID, item, all_items: _item_stats(item)


def _item_header(PATCH_ID, item, all_items):
    img = f"https://ddragon.leagueoflegends.com/cdn/{PATCH_ID}/img/item/{item['image']['full']}"
    return f"""
<div style="text-align: center">
    <img src="{img}" style="border-radius: 6px; width: 64px; height: 64px">
    <h2 style="color: #d39542; margin-block: 10px">{item['name']}</h2>
    <div style="color: #FFD700; font-size: 20px">{item['gold']['total']}g</div>
</div>"""


ITEM_SECTIONS["header"] = _item_header


def _item_description(PATCH_ID, item, all_items):
    description_html = convert_riot_html(item.get("description", ""))
    if not description_html:
        return ""
    return f"""
<div style="padding: 10px">
    <h3 style="color: #d39542; margin-block: 5px">Description</h3>
    <div style="color: #fff4bf; line-height: 1.5">{description_html}</div>
</div>"""


ITEM_SECTIONS["description"] = _item_description


def _item_build_path(PATCH_ID, item, all_items):
    from_ids = item.get("from", [])
    if not from_ids:
        return ""
    tree = build_item_tree(item["_id"], all_items)
    tree_html = render_tree_html(tree, PATCH_ID)
    return f"""
<div style="padding: 10px">
    <h3 style="color: #d39542; margin-block: 5px">Build Path</h3>
    <div style="padding: 4px 0">{tree_html}</div>
</div>"""


ITEM_SECTIONS["build_path"] = _item_build_path


def _item_gold(PATCH_ID, item, all_items):
    gold = item["gold"]
    total = gold["total"]
    base = gold["base"]
    components_cost = total - base
    return f"""
<div style="padding: 10px">
    <h3 style="color: #d39542; margin-block: 5px">Gold</h3>
    <table style="color: #fff4bf; border-collapse: collapse">
        <tr><td style="padding-right: 15px">Total</td><td style="color: #FFD700">{total}g</td></tr>
        <tr><td style="padding-right: 15px">Components</td><td style="color: #888">{components_cost}g</td></tr>
        <tr><td style="padding-right: 15px">Combine Cost</td><td style="color: #87CEEB">{base}g</td></tr>
        <tr><td style="padding-right: 15px">Sell Value</td><td style="color: #888">{gold['sell']}g</td></tr>
    </table>
</div>"""


ITEM_SECTIONS["gold"] = _item_gold


def build_item_card(PATCH_ID, item, all_items, verso=False):
    cfg = load_config().get("item_card", {})
    section_order = cfg.get("back" if verso else "front", DEFAULT_ITEM_BACK if verso else DEFAULT_ITEM_FRONT)

    parts = []
    for i, name in enumerate(section_order):
        if name in ITEM_SECTIONS:
            html = ITEM_SECTIONS[name](PATCH_ID, item, all_items)
            if html:
                if i > 0:
                    parts.append('<hr style="border: 1px solid #c4c4a5; border-radius: 50px">')
                parts.append(html)

    return f"""
<div style="text-align: left; background-color: #221f40; padding: 10px; border-radius: 8px; width: 700px; margin: 25px auto; border: 1px solid #c4c4a5">
    {"".join(parts)}
</div>"""
