#Skrypt do ściągnia bazy danych z API StatsBomb i zapisywania jej w MongoDB lokalnie. Do uruchomienia jeden raz.


import json
import time
import pandas as pd
from statsbombpy import sb
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "football_data"
MATCHES_COLLECTION = "matches"
EVENTS_COLLECTION = "events"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

COMPETITION_ID = 11
SEASON_ID = 27

matches = sb.matches(competition_id=COMPETITION_ID, season_id=SEASON_ID)
match_data = matches.to_dict(orient="records")

db[MATCHES_COLLECTION].delete_many({})
db[MATCHES_COLLECTION].insert_many(match_data)

for i, match_id in enumerate(matches["match_id"]):
    try:
        print(f"Processing match {i+1}/{len(matches)}")
        events = sb.events(match_id)
        events["match_id"] = match_id
        event_data = events.to_dict(orient="records")
        db[EVENTS_COLLECTION].insert_many(event_data)
    
    except Exception as e:
        print(e)
    time.sleep(1)

print("Done")

