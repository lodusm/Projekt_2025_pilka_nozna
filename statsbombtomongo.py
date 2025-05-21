import json
import time
import pandas as pd
from statsbombpy import sb
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "football_data"
MATCHES_COLLECTION = "matches"
EVENTS_COLLECTION = "events"
LINEUPS_COLLECTION = "lineups"

COMPETITION_ID = 11
SEASON_ID = 27

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

matches_col = db[MATCHES_COLLECTION]
events_col = db[EVENTS_COLLECTION]
lineups_col = db[LINEUPS_COLLECTION]

    
def drop_nan_fields(records):
    cleaned = []
    for record in records:
        cleaned_doc = {}
        for key, val in record.items():
            try:
                if pd.notnull(val): 
                    cleaned_doc[key] = val
            except:
                cleaned_doc[key] = val  
        cleaned.append(cleaned_doc)
    return cleaned

print("Pobieranie meczów")
matches = sb.matches(competition_id=COMPETITION_ID, season_id=SEASON_ID)
match_data = matches.to_dict(orient='records')

matches_col.delete_many({})
matches_col.insert_many(match_data)

events_col.delete_many({})
lineups_col.delete_many({})

match_ids = matches["match_id"].tolist()

for i, match_id in enumerate(match_ids, 1):
    print(f"{i}/{len(match_ids)}")

    try:
        print("Pobieranie zdarzeń")
        events = sb.events(match_id)
        events["match_id"] = match_id
        event_data = events.to_dict(orient='records')
        event_data = events.to_dict(orient='records')
        events_col.insert_many(drop_nan_fields(event_data))
    except Exception as e:
        print(e)

    try:
        print("Pobieranie składów")
        lineups_data = sb.lineups(match_id)
        lineup_docs = []

        for team_name, df in lineups_data.items():
            for _, row in df.iterrows():
                player_doc = row.to_dict()
                player_doc['team'] = team_name
                player_doc['match_id'] = match_id
                lineup_docs.append(player_doc)

        if lineup_docs:
            lineups_col.insert_many(lineup_docs)

    except Exception as e:
        print(e)

    time.sleep(1)
db.events.create_index([("type", 1), ("id", 1)])

print("Pobrano wszystkie dane.")