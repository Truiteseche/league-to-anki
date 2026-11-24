from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from utils import load_config, get_patch_id, get_champs_list, get_champs_details, build_champ_card
from items import get_items_list, build_item_card, ensure_icons
from tooltips import load_strings, render_champion_tooltips
import genanki
import argparse

champCardModel = genanki.Model(
    2076546967,
    "League of Legends champion card model",
    fields=[{"name": "Question"}, {"name": "Answer"}],
    templates=[{"name": "Champion card", "qfmt": "{{Question}}", "afmt": "{{Answer}}"}]
)

itemCardModel = genanki.Model(
    2076546966,
    "League of Legends item card model",
    fields=[{"name": "Question"}, {"name": "Answer"}],
    templates=[{"name": "Item card", "qfmt": "{{Question}}", "afmt": "{{Answer}}"}]
)


def _as_list(value):
    """Config/CLI filters must be lists of strings; anything else (e.g. the legacy `"items": true`) is ignored."""
    if isinstance(value, list):
        return [str(v).lower() for v in value]
    return None


def build_champions_deck(PATCH_ID, lang, deck_name, whitelist, exclude, workers):
    deck = genanki.Deck(2076546968, f"{deck_name}::Champions")
    champs = get_champs_list(PATCH_ID, lang)

    if whitelist:
        champs = [c for c in champs if c["id"].lower() in whitelist or c["name"].lower() in whitelist]
    if exclude:
        champs = [c for c in champs if c["id"].lower() not in exclude and c["name"].lower() not in exclude]

    if load_strings(PATCH_ID, lang) is None:
        print(f"Warning: no CommunityDragon tooltip data for {lang}, keeping Data Dragon ability descriptions")

    def fetch(champ_id):
        champ = get_champs_details(PATCH_ID, lang, champ_id)
        # The game's own ability tooltips: values per rank, AD/AP scalings...
        champ["_tooltips"] = render_champion_tooltips(PATCH_ID, lang, champ)
        return champ

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch, champ["id"]): champ for champ in champs}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Fetching champions"):
            champ = futures[future]
            try:
                detailedChamp = future.result()
            except Exception:
                tqdm.write(f"Failed: {champ['id']}")
                continue

            tags = [t.replace(" ", "_") for t in champ.get("tags", []) if t]
            if champ.get("partype"):
                tags.append(champ["partype"].replace(" ", "_"))

            deck.add_note(genanki.Note(
                model=champCardModel,
                fields=[
                    build_champ_card(PATCH_ID, detailedChamp, False),
                    build_champ_card(PATCH_ID, detailedChamp, True),
                ],
                tags=tags,
                guid=genanki.guid_for("lol-champion", champ["id"]),
            ))
    return deck


def _item_keys(item):
    return {item["_id"].lower(), item["name"].lower(), item.get("_en_name", "").lower()}


def build_items_deck(PATCH_ID, lang, deck_name, whitelist, exclude, english_names):
    deck = genanki.Deck(2076546965, f"{deck_name}::Items")
    items, all_items = get_items_list(PATCH_ID, lang)

    if whitelist:
        items = [i for i in items if _item_keys(i) & set(whitelist)]
    if exclude:
        items = [i for i in items if not _item_keys(i) & set(exclude)]

    for item in tqdm(items, desc="Building item cards"):
        deck.add_note(genanki.Note(
            model=itemCardModel,
            fields=[
                build_item_card(PATCH_ID, item, all_items, False, english_names),
                build_item_card(PATCH_ID, item, all_items, True, english_names),
            ],
            guid=genanki.guid_for("lol-item", item["_id"]),
        ))
    return deck


def main():
    parser = argparse.ArgumentParser(description="Generate League of Legends Anki decks")
    parser.add_argument("--lang", "-l", help="Language locale (e.g. en_US, ko_KR)")
    parser.add_argument("--output", "-o", help="Base output name: writes <name>_champions.apkg and <name>_items.apkg")
    parser.add_argument("--champions", nargs="+", help="Only include specific champions")
    parser.add_argument("--excludeChampions", nargs="+", help="Exclude specific champions")
    parser.add_argument("--onlyChampions", action="store_true", help="Skip item deck")
    parser.add_argument("--items", nargs="+", help="Only include specific items (id or name)")
    parser.add_argument("--excludeItems", nargs="+", help="Exclude specific items (id or name)")
    parser.add_argument("--onlyItems", action="store_true", help="Skip champions deck")
    parser.add_argument("--englishNames", action="store_true", help="Show the English item name in parentheses")
    parser.add_argument("--workers", type=int, default=20, help="Parallel workers (default: 20)")
    args = parser.parse_args()

    PATCH_ID = get_patch_id()
    cfg = load_config()

    lang = args.lang or cfg.get("language", "en_US")
    base = args.output or cfg.get("output") or f"LoL_{PATCH_ID}_{lang}"
    if base.lower().endswith(".apkg"):
        base = base[:-len(".apkg")]

    onlyChamps = args.onlyChampions or cfg.get("only_champions", False)
    onlyItems = args.onlyItems or cfg.get("only_items", False)
    if onlyChamps and onlyItems:
        parser.error("--onlyChampions and --onlyItems are mutually exclusive")

    english_names = (args.englishNames or cfg.get("english_names", False)) and not lang.startswith("en_")
    deck_name = cfg.get("deck_name") or "League of Legends"

    print(f"Patch: {PATCH_ID} | Lang: {lang}")

    if not onlyItems:
        deck = build_champions_deck(
            PATCH_ID, lang, deck_name,
            _as_list(args.champions or cfg.get("champions")),
            _as_list(args.excludeChampions or cfg.get("champions_exclude")),
            args.workers,
        )
        out = f"{base}_champions.apkg"
        package = genanki.Package(deck)
        package.media_files = ensure_icons()  # stat icons used in ability tooltips
        package.write_to_file(out)
        print(f"Wrote {len(deck.notes)} champion cards to {out}")

    if not onlyChamps:
        deck = build_items_deck(
            PATCH_ID, lang, deck_name,
            _as_list(args.items or cfg.get("items")),
            _as_list(args.excludeItems or cfg.get("items_exclude")),
            english_names,
        )
        out = f"{base}_items.apkg"
        package = genanki.Package(deck)
        package.media_files = ensure_icons()
        package.write_to_file(out)
        print(f"Wrote {len(deck.notes)} item cards to {out}")

    print("Done")


if __name__ == "__main__":
    main()
