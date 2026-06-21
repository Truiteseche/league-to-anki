# from dotenv import load_dotenv
# import os
from utils import *
import genanki

# define an anki model and deck
champCardModel = genanki.Model(
    2076546967,
    "League of Legends champion card model",
    fields=[
        {"name": "Question"},
        {"name": "Answer"}
    ],
    templates=[
        {
            "name": "Champion card",
            "qfmt": "{{Question}}",
            "afmt": "{{Answer}}",
        }
    ]
)

champsDeck = genanki.Deck(
    2076546968,
    "Champions League of Legends"
)


# load_dotenv()
# RIOT_API_KEY = os.getenv("RIOT_API_KEY")
# print("api key", RIOT_API_KEY)


# first retrieve the current game version so we get the data from the good patch note
PATCH_ID = get_patch_id()
print("PATCH_ID:", PATCH_ID)
lang = get_language()
print("language:", lang)

champs = get_champs_list(PATCH_ID, lang)

# champsDeck.add_model(champCardModel)
for i in range(len(champs)):
    print(i, champs[i]["id"])
    detailedChamp = get_champs_details(PATCH_ID, lang, champs[i]["id"])
    champCard = genanki.Note(
        model=champCardModel,
        fields=[build_champ_card(PATCH_ID, detailedChamp, False), build_champ_card(PATCH_ID, detailedChamp, True)]
    )
    champsDeck.add_note(champCard)

genanki.Package(champsDeck).write_to_file('LoLChampionsDeck.apkg')
