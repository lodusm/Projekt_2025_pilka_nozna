import pandas as pd

#Funkcja do zmieniania pełnych nazwisk na ksywki (Lionel Andreas Messi Cuccitini > Lionel Messi)
def apply_nicknames(events=None, lineups=None, starting_events=None):

    if lineups is None:
        raise ValueError("Musisz podać DataFrame `lineups`.")

    nickname_dict = {
        row['player_id']: row['player_nickname']
        for _, row in lineups.iterrows()
        if pd.notnull(row['player_nickname'])
    }

    full_name_dict = {
        row['player_name']: row['player_nickname']
        for _, row in lineups.iterrows()
        if pd.notnull(row['player_nickname'])
    }

    lineups['player_name'] = lineups.apply(
        lambda row: row['player_nickname'] if pd.notnull(row['player_nickname']) else row['player_name'],
        axis=1
    )

    if events is not None:
        if starting_events is None:
            starting_events = events[events['type'] == 'Starting XI'].copy()

        if 'player' in events.columns:
            events['player'] = events.apply(
                lambda row: nickname_dict.get(row.get('player_id'), row.get('player'))
                if pd.notnull(row.get('player_id')) else row.get('player'),
                axis=1
            )

        for idx in events[events['type'] == 'Substitution'].index:
            player_id = events.at[idx, 'player_id']
            sub_name = events.at[idx, 'substitution_replacement']

            if player_id in nickname_dict:
                events.at[idx, 'player'] = nickname_dict[player_id]

            if pd.notnull(sub_name) and sub_name in full_name_dict:
                events.at[idx, 'substitution_replacement'] = full_name_dict[sub_name]

    if starting_events is not None and 'tactics' in starting_events.columns:
        for idx in starting_events[starting_events['tactics'].notnull()].index:
            lineup = starting_events.at[idx, 'tactics'].get('lineup', [])
            for player in lineup:
                pid = player['player']['id']
                nickname = nickname_dict.get(pid)
                if nickname:
                    player['player']['name'] = nickname

    for idx, row in lineups.iterrows():
        player_id = row['player_id']
        nickname = nickname_dict.get(player_id)
        if nickname and isinstance(row.get('cards'), list):
            for card in row['cards']:
                card['player_name'] = nickname

    return (events, lineups) if events is not None else lineups



def get_coordinates():
    return {
        # Goalkeeper
        'Goalkeeper': (8, 40),

        # Defense
        'Left Back': (20, 20),
        'Left Center Back': (20, 30),
        'Center Back': (20, 40),
        'Right Center Back': (20, 50),
        'Right Back': (20, 60),

        # Defensive Midfield
        'Left Defensive Midfield': (30, 27),
        'Center Defensive Midfield': (30, 40),
        'Right Defensive Midfield': (30, 53),

        # Central Midfield
        'Left Center Midfield': (38, 27),
        'Center Midfield': (38, 40),
        'Right Center Midfield': (38, 53),

        # Attacking Midfield
        'Left Attacking Midfield': (46, 27),
        'Center Attacking Midfield': (46, 40),
        'Right Attacking Midfield': (46, 53),

        # Wingers
        'Left Wing': (50, 15),
        'Right Wing': (50, 65),

        # Forwards
        'Center Forward': (53, 40),
        'Striker': (55, 40),
        'Second Striker': (49, 40),

        # Additional Specific Roles
        'Right Midfield': (42, 60),
        'Left Midfield': (42, 20),
        'Right Center Forward': (52, 50),
        'Left Center Forward': (52, 30)
    }