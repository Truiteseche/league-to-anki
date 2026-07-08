from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from utils import load_config, get_language, get_patch_id, get_champs_list, get_champs_details, build_champ_card
from items import get_items_list, build_item_card
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate League of Legends Anki decks")
    parser.add_argument("--lang", "-l", help="Language locale (e.g. en_US, ko_KR)")
    parser.add_argument("--output", "-o", help="Output .apkg filename")
    parser.add_argument("--champions", nargs="+", help="Only include specific champions")
    parser.add_argument("--exclude", nargs="+", help="Exclude specific champions")
    parser.add_argument("--no-items", action="store_true", help="Skip item deck")
    parser.add_argument("--workers", type=int, default=20, help="Parallel workers (default: 20)")
    args = parser.parse_args()

    cfg = load_config()
    lang = args.lang or get_language()

    PATCH_ID = get_patch_id()

    output = args.output or cfg.get("output") or f"LoL_{PATCH_ID}_{lang}.apkg"
    champions_only = args.champions or cfg.get("champions_only")
    champions_exclude = args.exclude or cfg.get("champions_exclude")
    skip_items = args.no_items or not cfg.get("items", True)

    print(f"Patch: {PATCH_ID} | Lang: {lang} | Output: {output}")

    parent_deck = cfg.get("deck_name") or "League of Legends"
    champsDeck = genanki.Deck(2076546968, f"{parent_deck}::Champions")
    champs = get_champs_list(PATCH_ID, lang)

    if champions_only:
        champs = [c for c in champs if c["id"] in champions_only]
    if champions_exclude:
        champs = [c for c in champs if c["id"] not in champions_exclude]

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(get_champs_details, PATCH_ID, lang, champ["id"]): champ
            for champ in champs
        }
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

            champCard = genanki.Note(
                model=champCardModel,
                fields=[build_champ_card(PATCH_ID, detailedChamp, False), build_champ_card(PATCH_ID, detailedChamp, True)],
                tags=tags
            )
            champsDeck.add_note(champCard)

    decks = [champsDeck]
    if not skip_items:
        itemsDeck = genanki.Deck(2076546965, f"{parent_deck}::Items")
        items, all_items = get_items_list(PATCH_ID, lang)
        for item in tqdm(items, desc="Building item cards"):
            itemCard = genanki.Note(
                model=itemCardModel,
                fields=[build_item_card(PATCH_ID, item, all_items, False), build_item_card(PATCH_ID, item, all_items, True)]
            )
            itemsDeck.add_note(itemCard)
        decks.append(itemsDeck)

    genanki.Package(decks).write_to_file(output)
    print("Done")
