# from dotenv import load_dotenv
# import os
from utils import *

# load_dotenv()
# RIOT_API_KEY = os.getenv("RIOT_API_KEY")
# print("api key", RIOT_API_KEY)

# first retrieve the current game version so we get the data from the good patch note
PATCH_ID = get_patch_id()
print("PATCH_ID:", PATCH_ID)
lang = get_language()
print("language:", lang)

champs = get_champs_list(PATCH_ID, lang)

for i in range(len(champs)):
    print(i, champs[i]["id"])

detailedChamp = get_champs_details(PATCH_ID, lang, champs[25]["id"])
print(build_champ_card(PATCH_ID, detailedChamp, True))