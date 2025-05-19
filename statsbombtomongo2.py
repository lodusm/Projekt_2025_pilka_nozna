#dodatkowy skrypt aby dodać kolekcję lineups zawierającą dane składów na każdy z meczów
import time
import pandas as pd
from pymongo import MongoClient
from statsbombpy import sb

client = MongoClient("mongodb://localhost:27017")
db = client["football_data"]
matches_collection = db["matches"]
lineups_collection = db["lineups"]


lineups_collection.delete_many({})
match_ids = matches_collection.distinct("match_id")

for idx, match_id in enumerate(match_ids, 1):
    print(f"[{idx}/{len(match_ids)}] Match ID {match_id} — downloading lineups...")

    try:
        lineups_data = sb.lineups(match_id)
        lineup_docs = []

        for team_name, df in lineups_data.items():

            for _, row in df.iterrows():
                player_doc = row.to_dict()
                player_doc["team"] = team_name
                player_doc["match_id"] = match_id
                lineup_docs.append(player_doc)

        if lineup_docs:
            lineups_collection.insert_many(lineup_docs)
            print(f"Saved {match_id}")

    except Exception as e:
        print(f"Error {match_id}: {e}")

    time.sleep(0.3)
