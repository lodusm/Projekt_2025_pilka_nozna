import dash
from dash import Input, Output, callback, html, dash_table, dcc
from pymongo import MongoClient
import pandas as pd
import json
import plotly.graph_objects as go
from plotly_football_pitch import make_pitch_figure, PitchDimensions, SingleColourBackground
import utils

dash.register_page(__name__, path_template="/match/<match_id>")

client = MongoClient("mongodb://localhost:27017/")
db = client["football_data"]

matches_df = pd.DataFrame(list(db.matches.find()))
lineups = pd.DataFrame(list(db.lineups.find()))
lineups = utils.apply_nicknames(lineups=lineups)
players_df = sorted(lineups["player_name"].dropna().unique())


def get_match_data(match_id):
    match_id = int(match_id)
    events = pd.DataFrame(list(db.events.find({'match_id': match_id})))
    lineups = pd.DataFrame(list(db.lineups.find({'match_id': match_id})))
    return events, lineups


def generate_timeline(match_id):
    icons = {
        "Yellow Card": "🟨",
        "Second Yellow": "🟨🟥",
        "Red Card": "🟥",
        "Halftime": "✅",
        "Goal": "⚽",
        "Own Goal": "⚽",
        "Goal (Pen)": "⚽",
        "Half End": "✅",
        "Own goal": "❌",
        "Added time": "🕑",
        "Substitution": "🔁"
    }

    events, lineups = get_match_data(match_id)
    events, lineups = utils.apply_nicknames(events, lineups)
    events['minute'] += 1

    timeline = []

    #gole, asysty
    normal_goals = events[(events['type'] == 'Shot')
                          & (events['shot_outcome'] == 'Goal')].copy()
    own_goals = events[events['type'] == 'Own Goal For'].copy()
    goals = pd.concat([normal_goals, own_goals], ignore_index=True)

    passes = events[events['type'] == 'Pass'][['id', 'player']]
    assist_map = dict(zip(passes['id'], passes['player']))

    for _, row in goals.iterrows():
        minute = row['minute']
        team = row.get('team')
        player = row.get('player')

        if row['type'] == 'Shot':
            assist_id = row.get('shot_key_pass_id')
            assistant = assist_map.get(assist_id)
            player_str = f"{player} (a. {assistant})" if assistant else player
            event_type = 'Goal (Pen)' if row.get(
                'shot_type') == 'Penalty' else 'Goal'
        else:
            player_str = player
            event_type = 'Own Goal'

        timeline.append({
            'icon': icons.get(event_type),
            'minute': minute,
            'team': team,
            'player': player_str,
            'type': event_type
        })

    #kartki
    lineups['cards'] = lineups['cards'].apply(
        lambda x: json.loads(x.replace("'", '"'))
        if isinstance(x, str) and x.startswith("[") else x)

    for team_name in lineups['team'].unique():
        team_players = lineups[lineups['team'] == team_name]
        for _, player in team_players.iterrows():
            for card in player.get("cards", []):
                card_type = card.get("card_type")
                time_str = card.get("time", "0:0")
                try:
                    minute, _ = map(int, time_str.split(":"))
                except:
                    minute = 0

                timeline.append({
                    'icon':
                    icons.get(card_type),
                    'minute':
                    minute + 1,
                    'team':
                    team_name,
                    'player':
                    player.get("player_name", "Brak danych"),
                    'type':
                    card_type
                })

    #zmiany
    subs = events[events['type'] == 'Substitution'].copy()
    for _, row in subs.iterrows():
        timeline.append({
            'icon': icons['Substitution'],
            'minute': row['minute'],
            'team': row.get('team'),
            'player':
            f"⬇️ {row.get('player')} ⬆️ {row.get('substitution_replacement')}",
            'type': 'Substitution'
        })

    #połowy i doliczony czas
    half_ends = (events[events['type'] == 'Half End'].sort_values(
        ['period', 'minute', 'second']).drop_duplicates(subset='period',
                                                        keep='last'))

    for _, row in half_ends.iterrows():
        period = row.get("period")
        minute = row.get("minute", 0)

        if period == 1:
            if minute > 45:
                timeline.append({
                    'icon': icons['Added time'],
                    'minute': 45,
                    'team': '',
                    'player': '',
                    'type': f'1st Half +{minute - 45} min'
                })
            timeline.append({
                'icon': icons['Half End'],
                'minute': minute,
                'team': '',
                'player': '',
                'type': 'Halftime'
            })

        elif period == 2:
            if minute > 90:
                timeline.append({
                    'icon': icons['Added time'],
                    'minute': 90,
                    'team': '',
                    'player': '',
                    'type': f'2nd Half +{minute - 90} min'
                })
            timeline.append({
                'icon': icons['Half End'],
                'minute': minute,
                'team': '',
                'player': '',
                'type': 'Fulltime'
            })

    timeline_df = pd.DataFrame(timeline)
    timeline_df = timeline_df.sort_values(by='minute').reset_index(drop=True)
    return timeline_df[['icon', 'minute', 'type', 'team', 'player']]


def draw_lineup_plot(match_id):
    events, lineups = get_match_data(match_id)
    starting_events = events[events['type'] == 'Starting XI'].copy()
    events, lineups = utils.apply_nicknames(events, lineups, starting_events)

    match = matches_df[matches_df["match_id"] == match_id].iloc[0]
    home_team = match['home_team']
    away_team = match['away_team']
    position_coordinates = utils.get_coordinates()

    pitch_length, pitch_width = 120, 80
    players = []

    for _, row in starting_events.iterrows():
        team = row['team']
        for player in row['tactics']['lineup']:
            name = player['player']['name']
            number = player['jersey_number']
            position = player['position']['name']
            x, y = position_coordinates.get(position, (10, 10))
            if team == away_team:
                x, y = pitch_length - x, pitch_width - y
            players.append({
                'x': x,
                'y': 80 - y,
                'team': team,
                'name': name,
                'number': number
            })

    df = pd.DataFrame(players)
    fig = make_pitch_figure(PitchDimensions(pitch_width, pitch_length),
                            pitch_background=SingleColourBackground("#2F4F4F"))

    for team, color in [(home_team, "blue"), (away_team, "red")]:
        team_df = df[df['team'] == team]
        fig.add_trace(
            go.Scatter(x=team_df['x'],
                       y=team_df['y'],
                       mode="markers+text",
                       text=team_df['number'].astype(str),
                       textposition="middle center",
                       marker=dict(size=40,
                                   color=color,
                                   line=dict(color="white", width=3)),
                       textfont=dict(color="white", size=20),
                       hovertext=f"{team_df['name']}",
                       hoverinfo="text",
                       showlegend=False))

    fig.update_layout(
        paper_bgcolor='#0a1128',
        autosize=True,
        margin=dict(l=20, r=20, t=40, b=20),
    )

    return fig


def generate_match_stats(events, lineups, match, home_team, away_team):

    def count_shots(df):
        return len(df[df['type'] == 'Shot'])

    def count_shots_on_target(df):
        return len(df[(df['type'] == 'Shot')
                      & (df['shot_outcome'].isin(['Goal', 'Saved']))])

    def sum_xg(df):
        return df[df['type'] == 'Shot']['shot_statsbomb_xg'].sum()

    def count_passes(df):
        return df[df['type'] == 'Pass']

    def count_accurate_passes(df):
        passes = count_passes(df)
        return len(passes[passes['pass_outcome'].isnull()])

    def pass_accuracy_pct(df):
        passes = count_passes(df)
        total = len(passes)
        accurate = count_accurate_passes(df)
        return f"{(accurate / total) * 100:.1f}%" if total > 0 else "0.0%"

    def count_corners(df):
        return len(df[df['pass_type'] == 'Corner'])

    def count_penalties(df):
        return len(df[df['shot_type'] == 'Penalty'])

    def count_free_kicks(df):
        return len(df[df['pass_type'] == 'Free Kick'])

    lineups_dict = {
        team: group.to_dict(orient="records")
        for team, group in lineups.groupby("team")
    }

    def count_yellow_cards(team):
        return sum(1 for p in lineups_dict.get(team, [])
                   for c in p.get("cards", [])
                   if c.get("card_type") in ["Yellow Card", "Second Yellow"])

    def count_red_cards(team):
        return sum(1 for p in lineups_dict.get(team, [])
                   for c in p.get("cards", [])
                   if c.get("card_type") in ["Red Card", "Second Yellow"])

    home_events = events[events['team'] == home_team]
    away_events = events[events['team'] == away_team]

    controlled_events = events[events['type'].isin(
        ['Pass', 'Ball Receipt', 'Carry'])]
    total_controlled = len(controlled_events)
    home_possession = f"{(len(controlled_events[controlled_events['team'] == home_team]) / total_controlled) * 100:.1f}%" if total_controlled else "0.0%"
    away_possession = f"{(len(controlled_events[controlled_events['team'] == away_team]) / total_controlled) * 100:.1f}%" if total_controlled else "0.0%"

    stats = {
        'Goals': [match['home_score'], match['away_score']],
        'Shots': [count_shots(home_events),
                  count_shots(away_events)],
        'Shots on Target': [
            count_shots_on_target(home_events),
            count_shots_on_target(away_events)
        ],
        'xG': [round(sum_xg(home_events), 2),
               round(sum_xg(away_events), 2)],
        'Possession': [home_possession, away_possession],
        'Accurate Passes': [
            count_accurate_passes(home_events),
            count_accurate_passes(away_events)
        ],
        'Pass Accuracy':
        [pass_accuracy_pct(home_events),
         pass_accuracy_pct(away_events)],
        'Corners': [count_corners(home_events),
                    count_corners(away_events)],
        'Penalties':
        [count_penalties(home_events),
         count_penalties(away_events)],
        'Free Kicks':
        [count_free_kicks(home_events),
         count_free_kicks(away_events)],
        'Yellow Cards':
        [count_yellow_cards(home_team),
         count_yellow_cards(away_team)],
        'Red Cards': [count_red_cards(home_team),
                      count_red_cards(away_team)],
    }

    df = pd.DataFrame.from_dict(
        stats, orient='index',
        columns=[home_team, away_team
                 ]).reset_index().rename(columns={'index': 'Statistic'})
    df = df[[home_team, 'Statistic', away_team]]
    return df


def get_lineup_tables(events, lineups, home_team, away_team):
    starting_11 = events[events['type'] == 'Starting XI']
    starting_ids = {
        player['player']['id']
        for _, row in starting_11.iterrows()
        for player in row['tactics']['lineup']
    }

    def parse_players(team, is_sub=False):
        players = []
        df = lineups[(lineups['team'] == team)]
        if is_sub:
            df = df[~df['player_id'].isin(starting_ids)]
        else:
            df = df[df['player_id'].isin(starting_ids)]

        for _, row in df.iterrows():
            players.append({
                'Jersey':
                row['jersey_number'],
                'Name':
                row.get('player_name',
                        row.get('player', {}).get('name')),
            })
        return pd.DataFrame(players)

    return (
        parse_players(home_team),
        parse_players(away_team),
        parse_players(home_team, is_sub=True),
        parse_players(away_team, is_sub=True),
    )


def draw_shot_map(events, home_team, away_team):
    pitch_length, pitch_width = 120, 80

    shots = events[(events['type'] == 'Shot')
                   & (events['location'].notnull())].copy()
    shots['x'] = shots['location'].apply(lambda loc: loc[0])
    shots['y'] = shots['location'].apply(lambda loc: 80 - loc[1])

    shots.loc[shots['team'] == home_team, 'x'] = pitch_length - shots['x']
    shots.loc[shots['team'] == home_team, 'y'] = pitch_width - shots['y']

    home_shots = shots[shots['team'] == home_team]
    away_shots = shots[shots['team'] == away_team]

    home_goals = home_shots[home_shots['shot_outcome'] == 'Goal']
    home_others = home_shots[home_shots['shot_outcome'] != 'Goal']
    away_goals = away_shots[away_shots['shot_outcome'] == 'Goal']
    away_others = away_shots[away_shots['shot_outcome'] != 'Goal']

    fig = make_pitch_figure(
        PitchDimensions(pitch_width, pitch_length),
        pitch_background=SingleColourBackground("darkslategrey"))

    def scatter_shots(df, color, size, marker, label):
        fig.add_trace(
            go.Scatter(x=df['x'],
                       y=df['y'],
                       mode='markers',
                       marker=dict(size=size,
                                   color=color,
                                   symbol=marker,
                                   line=dict(color='white', width=1.5)),
                       name=label,
                       hovertext=df['player'],
                       hoverinfo='text',
                       showlegend=False))

    scatter_shots(home_others, "blue", 10, "circle", f"{home_team} - shots")
    scatter_shots(home_goals, "blue", 18, "star", f"{home_team} - goals")
    scatter_shots(away_others, "red", 10, "circle", f"{away_team} - shots")
    scatter_shots(away_goals, "red", 18, "star", f"{away_team} - goals")

    fig.update_layout(paper_bgcolor='#0a1128',
                      height=500,
                      width=700,
                      margin=dict(l=20, r=20, t=40, b=20),
                      showlegend=False)

    return fig


def draw_pass_network(events, team_name):
    from collections import defaultdict
    import numpy as np

    pitch_length, pitch_width = 120, 80

    passes = events[(events['type'] == 'Pass')
                    & (events['pass_outcome'].isnull()) &
                    (events['location'].notnull()) &
                    (events['pass_end_location'].notnull()) &
                    (events['player'].notnull()) &
                    (events['team'] == team_name)].copy()

    if passes.empty:
        return html.Div(f"No pass data available for {team_name}")

    #średnie pozycje
    player_locs = defaultdict(lambda: [[], []])
    for _, row in passes.iterrows():
        player = row['player']
        x, y = row['location']
        player_locs[player][0].append(x)
        player_locs[player][1].append(80 - y)

    avg_pos = {
        p: (np.mean(xs), np.mean(ys))
        for p, (xs, ys) in player_locs.items()
    }

    #pary zawodników
    ocmbinations = passes.groupby(['player', 'pass_recipient'
                                   ]).size().reset_index(name='count')

    fig = make_pitch_figure(
        PitchDimensions(pitch_width, pitch_length),
        pitch_background=SingleColourBackground("darkslategrey"))

    #linie
    for _, row in ocmbinations.iterrows():
        p1, p2, count = row['player'], row['pass_recipient'], row['count']
        if p1 in avg_pos and p2 in avg_pos:
            x0, y0 = avg_pos[p1]
            x1, y1 = avg_pos[p2]
            fig.add_shape(type="line",
                          x0=x0,
                          y0=y0,
                          x1=x1,
                          y1=y1,
                          line=dict(width=min(count, 6), color="skyblue"),
                          opacity=0.5)

    #zawodnicy
    for player, (x, y) in avg_pos.items():
        fig.add_trace(
            go.Scatter(x=[x],
                       y=[y],
                       mode="markers+text",
                       text=[player.split()[-1]],
                       textposition="top center",
                       marker=dict(size=14,
                                   color="blue",
                                   line=dict(color="white", width=2)),
                       textfont=dict(color="white", size=10),
                       hoverinfo="text",
                       hovertext=[player],
                       showlegend=False))

    fig.update_layout(paper_bgcolor='#0a1128',
                      height=500,
                      width=750,
                      margin=dict(l=20, r=20, t=40, b=20))

    return html.Div(dcc.Graph(figure=fig, config={"displayModeBar": False}),
                    style={"textAlign": "center"})


def draw_xg_timeline(events, home_team, away_team):

    shots = events[(events['type'] == 'Shot')
                   & (events['shot_statsbomb_xg'].notnull()) &
                   (events['team'].notnull())].copy()

    home_xg = shots[shots['team'] == home_team].copy()
    away_xg = shots[shots['team'] == away_team].copy()

    home_xg['cumulative_xg'] = home_xg['shot_statsbomb_xg'].cumsum()
    away_xg['cumulative_xg'] = away_xg['shot_statsbomb_xg'].cumsum()

    home_xg = pd.concat(
        [pd.DataFrame([{
            'minute': 0,
            'cumulative_xg': 0
        }]), home_xg],
        ignore_index=True)
    away_xg = pd.concat(
        [pd.DataFrame([{
            'minute': 0,
            'cumulative_xg': 0
        }]), away_xg],
        ignore_index=True)

    home_goals = home_xg[home_xg.get('shot_outcome') == 'Goal']
    away_goals = away_xg[away_xg.get('shot_outcome') == 'Goal']

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=home_xg['minute'],
                   y=home_xg['cumulative_xg'],
                   mode='lines',
                   line=dict(shape='hv', color='blue'),
                   name=home_team))
    fig.add_trace(
        go.Scatter(x=away_xg['minute'],
                   y=away_xg['cumulative_xg'],
                   mode='lines',
                   line=dict(shape='hv', color='red'),
                   name=away_team))

    fig.add_trace(
        go.Scatter(x=home_goals['minute'],
                   y=home_goals['cumulative_xg'],
                   mode='markers',
                   marker=dict(symbol='star',
                               size=12,
                               color='blue',
                               line=dict(color='white', width=1)),
                   name=f"Goals - {home_team}"))
    fig.add_trace(
        go.Scatter(x=away_goals['minute'],
                   y=away_goals['cumulative_xg'],
                   mode='markers',
                   marker=dict(symbol='star',
                               size=12,
                               color='red',
                               line=dict(color='white', width=1)),
                   name=f"Goals - {away_team}"))

    fig.update_layout(xaxis_title="Minute",
                      yaxis_title="Cumulative xG",
                      template="plotly_dark",
                      plot_bgcolor="#1c273a",
                      paper_bgcolor="#1c273a",
                      legend=dict(orientation="v", x=1.02, y=1),
                      margin=dict(l=40, r=40, t=60, b=40),
                      height=500)

    return fig


def link_team(team_name):
    ids = utils.internal_team_id()
    return dcc.Link(team_name, href=f"/team/{ids[team_name]}")


def layout(match_id=None):

    common_cell_style = {
        'backgroundColor': '#1c273a',
        'color': '#f0f0f0',
        'border': '1px solid #2f3e54',
        'padding': '8px',
        'fontSize': '15px',
        'fontFamily': 'Segoe UI, sans-serif',
        'cursor': 'pointer',
        'whiteSpace': 'normal',
        'textAlign': 'center'
    }

    common_header_style = {
        'backgroundColor': '#324863',
        'color': '#ffffff',
        'fontWeight': 'bold',
        'fontSize': '14px',
        'borderBottom': '2px solid #50657a',
        'textAlign': 'center'
    }

    match_id = int(match_id)
    match = matches_df[matches_df["match_id"] == match_id]
    row = match.iloc[0]
    events, lineups = get_match_data(match_id)
    events, lineups = utils.apply_nicknames(events, lineups)
    home_team, away_team = row['home_team'], row['away_team']
    timeline_df = generate_timeline(match_id)
    stats_df = generate_match_stats(events, lineups, row, home_team, away_team)
    home_df, away_df, subs_home, subs_away = get_lineup_tables(
        events, lineups, home_team, away_team)

    return html.Div(
        [
            html.Div(
                [
                    html.Div(link_team(home_team),
                             style={
                                 "flex": "1",
                                 "textAlign": "right",
                                 "paddingRight": "1rem",
                                 "fontSize": "4rem",
                                 "fontWeight": "bold"
                             }),
                    html.Div(f"{row['home_score']} - {row['away_score']}",
                             style={
                                 "flex": "0",
                                 "textAlign": "center",
                                 "fontWeight": "bold",
                                 "fontSize": "4rem",
                                 "minWidth": "150px"
                             }),
                    html.Div(link_team(away_team),
                             style={
                                 "flex": "1",
                                 "textAlign": "left",
                                 "paddingLeft": "1rem",
                                 "fontSize": "4rem",
                                 "fontWeight": "bold"
                             })
                ],
                style={
                    "display": "flex",
                    "justifyContent": "center",
                    "alignItems": "center",
                    "margin": "1rem auto",
                    "maxWidth": "100%",
                    "gap": "1rem",
                    'fontFamily': 'Segoe UI, sans-serif'
                }),
            html.
            P(f"📅 {row.get('match_date', 'Unknown')} 🏟️  {row.get('stadium', 'Unknown')} ✏️ {row.get('referee', 'Unknown')}",
              style={
                  "textAlign": "center",
                  "fontSize": "1rem"
              }),

            #składy
            html.Div(
                [
                    html.H4("Lineups", style={"textAlign": "center"}),
                    html.Div(
                        [
                            #gospodarze
                            html.Div(
                                [
                                    html.H5("Starting XI",
                                            style={"textAlign": "center"}),
                                    html.Div(dash_table.DataTable(
                                        columns=[{
                                            "name": col,
                                            "id": col
                                        } for col in home_df.columns],
                                        data=home_df.to_dict('records'),
                                        style_cell=common_cell_style,
                                        style_header=common_header_style,
                                        page_action="none"),
                                             style={
                                                 'maxWidth': '300px',
                                                 'overflowY': 'auto',
                                                 'margin': '0.5rem auto',
                                                 'overflowX': 'auto'
                                             }),
                                    html.H5("Bench",
                                            style={
                                                "marginTop": "1rem",
                                                "textAlign": "center"
                                            }),
                                    html.Div(dash_table.DataTable(
                                        columns=[{
                                            "name": col,
                                            "id": col
                                        } for col in subs_home.columns],
                                        data=subs_home.to_dict('records'),
                                        style_cell=common_cell_style,
                                        style_header=common_header_style,
                                        page_action="none"),
                                             style={
                                                 'maxWidth': '300px',
                                                 'overflowY': 'auto',
                                                 'margin': '0.5rem auto',
                                                 'overflowX': 'auto'
                                             }),
                                ],
                                style={
                                    "flex": "0 0 250px",
                                    "display": "flex",
                                    "flexDirection": "column",
                                    "justifyContent": "center",
                                    "alignItems": "center",
                                    "paddingTop": "1rem"
                                }),

                            #mapka
                            html.Div(
                                [
                                    dcc.Graph(
                                        figure=draw_lineup_plot(match_id),
                                        config={"displayModeBar": False},
                                        style={
                                            "width": "100%",
                                            "height": "auto"
                                        })
                                ],
                                style={
                                    "flex": "1",
                                    "display": "flex",
                                    "justifyContent": "center",
                                    "alignItems": "flex-start",
                                    "paddingTop": "1rem"
                                }),

                            #goście
                            html.Div(
                                [
                                    html.H5("Starting XI",
                                            style={"textAlign": "center"}),
                                    html.Div(dash_table.DataTable(
                                        columns=[{
                                            "name": col,
                                            "id": col
                                        } for col in away_df.columns],
                                        data=away_df.to_dict('records'),
                                        style_cell=common_cell_style,
                                        style_header=common_header_style,
                                        page_action="none"),
                                             style={
                                                 'maxWidth': '300px',
                                                 'overflowY': 'auto',
                                                 'margin': '0.5rem auto',
                                                 'overflowX': 'auto'
                                             }),
                                    html.H5("Bench",
                                            style={
                                                "marginTop": "1rem",
                                                "textAlign": "center"
                                            }),
                                    html.Div(dash_table.DataTable(
                                        columns=[{
                                            "name": col,
                                            "id": col
                                        } for col in subs_away.columns],
                                        data=subs_away.to_dict('records'),
                                        style_cell=common_cell_style,
                                        style_header=common_header_style,
                                        page_action="none"),
                                             style={
                                                 'maxWidth': '300px',
                                                 'overflowY': 'auto',
                                                 'margin': '0.5rem auto',
                                                 'overflowX': 'auto'
                                             }),
                                ],
                                style={
                                    "flex": "0 0 250px",
                                    "display": "flex",
                                    "flexDirection": "column",
                                    "justifyContent": "center",
                                    "alignItems": "center",
                                    "paddingTop": "1rem"
                                }),
                        ],
                        style={
                            "display": "flex",
                            "justifyContent": "center",
                            "gap": "4rem",
                            "marginTop": "1rem"
                        }),
                ],
                style={
                    "maxWidth": "1300px",
                    "margin": "0 auto",
                    "padding": "1rem",
                    "boxSizing": "border-box"
                }),

            #timeline+strzały
            html.Div(
                [
                    #timeline
                    html.Div(
                        [
                            html.H4("Timeline", style={"textAlign": "center"}),
                            dash_table.DataTable(
                                columns=[{
                                    "name": col.capitalize(),
                                    "id": col
                                } for col in timeline_df.columns],
                                data=timeline_df.to_dict('records'),
                                style_cell=common_cell_style,
                                style_header={"fontWeight": "bold"},
                                page_action="none",
                                style_table={
                                    "marginTop": "1rem",
                                    "marginBottom": "1rem",
                                    "overflowX": "auto"
                                })
                        ],
                        style={
                            "flex": "1",
                            "display": "flex",
                            "flexDirection": "column",
                            "alignItems": "center",
                            "minWidth": "360px"
                        }),

                    #mapa strzałów
                    html.Div(
                        [
                            html.H4("Shots Map", style={"textAlign": "center"
                                                        }),
                            dcc.Graph(figure=draw_shot_map(
                                events, home_team, away_team),
                                      config={"displayModeBar": False},
                                      style={
                                          "width": "100%",
                                          "maxWidth": "680px",
                                          "margin": "0 auto"
                                      })
                        ],
                        style={
                            "flex": "1",
                            "display": "flex",
                            "flexDirection": "column",
                            "alignItems": "center",
                            "minWidth": "360px"
                        })
                ],
                style={
                    "display": "flex",
                    "justifyContent": "center",
                    "alignItems": "flex-start",
                    "gap": "1rem",
                    "marginTop": "2rem",
                    "padding": "0 1rem",
                    "flexWrap": "wrap",
                    "width": "100%"
                }),
            #tableka statystyk
            html.Div([
                html.H4("Statistics", style={"textAlign": "center"}),
                html.Div(
                    [
                        dash_table.DataTable(columns=[{
                            "name": col,
                            "id": col
                        } for col in stats_df.columns],
                                             data=stats_df.to_dict('records'),
                                             style_cell=common_cell_style,
                                             style_cell_conditional=[
                                                 {
                                                     'if': {
                                                         'column_id':
                                                         stats_df.columns[0]
                                                     },
                                                     'width': '33.33%'
                                                 },
                                                 {
                                                     'if': {
                                                         'column_id':
                                                         stats_df.columns[1]
                                                     },
                                                     'width': '33.33%'
                                                 },
                                                 {
                                                     'if': {
                                                         'column_id':
                                                         stats_df.columns[2]
                                                     },
                                                     'width': '33.33%'
                                                 },
                                             ],
                                             style_header=common_header_style,
                                             style_table={"width": "100%"})
                    ],
                    style={
                        "width": "50%",
                        "margin": "0 auto",
                        "marginTop": "2rem",
                        "marginBottom": "2rem"
                    })
            ]),
            #siatki podań
            html.H4("Passing networks", style={"textAlign": "center"}),
            html.Div(
                [
                    html.Div(draw_pass_network(events, home_team),
                             style={
                                 "flex": "0 1 45%",
                                 "textAlign": "center",
                                 "display": "flex",
                                 "justifyContent": "center"
                             }),
                    html.Div(draw_pass_network(events, away_team),
                             style={
                                 "flex": "0 1 45%",
                                 "textAlign": "center",
                                 "display": "flex",
                                 "justifyContent": "center"
                             })
                ],
                style={
                    "display": "flex",
                    "justifyContent": "center",
                    "alignItems": "flex-start",
                    "gap": "3rem",
                    "marginTop": "1rem",
                    "flexWrap": "wrap",
                    "padding": "0 1rem",
                    "width": "100%",
                    "boxSizing": "border-box"
                }),
            html.Div([
                html.H3("Match momentum",
                        style={
                            "textAlign": "center",
                            "marginTop": "2rem"
                        }),
                dcc.Graph(figure=draw_xg_timeline(events, home_team,
                                                  away_team),
                          config={"displayModeBar": False},
                          style={
                              "width": "100%",
                              "maxWidth": "1200px",
                              "margin": "0 auto"
                          })
            ],
                     style={"marginBottom": "2rem"})
        ],
        style={"overflowX": "hidden"})
