import pandas as pd

#Funkcja do zmieniania pełnych nazwisk na ksywki (Lionel Andreas Messi Cuccitini > Lionel Messi)
def apply_nicknames(events, lineups):

    #Słownik id : nickname
    nickname_dict = {
        row['player_id']: row['player_nickname']
        for _, row in lineups.iterrows()
        if pd.notnull(row['player_nickname'])
    }

    #Słownik player_name : nickname
    full_name_dict = {
        row['player_name']: row['player_nickname']
        for _, row in lineups.iterrows()
        if pd.notnull(row['player_nickname'])
    }

    #Zamiana w składach
    lineups['player_name'] = lineups.apply(
        lambda row: row['player_nickname'] if pd.notnull(row['player_nickname']) else row['player_name'],
        axis=1
    )

    #Zamiana w eventach
    if 'player' in events.columns:
        events['player'] = events.apply(
            lambda row: nickname_dict.get(row.get('player_id'), row.get('player'))
            if pd.notnull(row.get('player_id')) else row.get('player'),
            axis=1
        )

    #Zamiana w wyjściowych 11stkach
    for idx in events[(events['type'] == 'Starting XI') & (events['tactics'].notnull())].index:
        lineup = events.at[idx, 'tactics'].get('lineup', [])
        for player in lineup:
            player_id = player['player']['id']
            nickname = nickname_dict.get(player_id)
            if nickname:
                player['player']['name'] = nickname

    #Zamiana w kartkach
    for idx, row in lineups.iterrows():
        player_id = row['player_id']
        nickname = nickname_dict.get(player_id)
        if nickname and isinstance(row.get('cards'), list):
            for card in row['cards']:
                card['player_name'] = nickname

    #Zamiana w zmianach
    for idx in events[events['type'] == 'Substitution'].index:
        player_id = events.at[idx, 'player_id']
        sub_name = events.at[idx, 'substitution_replacement']

        if player_id in nickname_dict:
            events.at[idx, 'player'] = nickname_dict[player_id]

        if pd.notnull(sub_name) and sub_name in full_name_dict:
            events.at[idx, 'substitution_replacement'] = full_name_dict[sub_name]

    return events, lineups

def get_coordinates():
    return {
        'Goalkeeper': (8, 40),
        'Left Back': (20, 20),
        'Left Center Back': (20, 30),
        'Center Back': (20, 40),
        'Right Center Back': (20, 50),
        'Right Back': (20, 60),

        'Left Defensive Midfield': (30, 27),
        'Center Defensive Midfield': (30, 40),
        'Right Defensive Midfield': (30, 53),

        'Left Center Midfield': (38, 27),
        'Center Midfield': (38, 40),
        'Right Center Midfield': (38, 53),

        'Left Attacking Midfield': (46, 27),
        'Center Attacking Midfield': (46, 40),
        'Right Attacking Midfield': (46, 53),

        'Left Wing': (50, 15),
        'Right Wing': (50, 65),
        'Center Forward': (53, 40),
        'Striker': (55, 40),
        'Second Striker': (49, 40),
    }