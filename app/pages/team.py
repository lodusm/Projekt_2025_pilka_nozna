from dash import html, dcc, dash_table, callback, Output, Input, register_page
import dash
from pymongo import MongoClient
import pandas as pd
from utils import internal_team_id, apply_nicknames
import numpy as np
import plotly.graph_objects as go
from plotly_football_pitch import make_pitch_figure, PitchDimensions, SingleColourBackground
import plotly.express as px
from dash import html, dcc

register_page(__name__, path_template="/team/<team_id>")

client = MongoClient("mongodb://localhost:27017/")
db = client["football_data"]
lineups = pd.DataFrame(list(db.lineups.find()))
lineups = apply_nicknames(lineups=lineups)
matches = pd.DataFrame(list(db.matches.find()))


def get_match_result_stats(events, matches_df, team_name):
    team_matches = matches_df[(matches_df['home_team'] == team_name) |
                              (matches_df['away_team'] == team_name)].copy()

    played = len(team_matches)

    def is_win(row):
        return row['home_score'] > row['away_score'] if row[
            'home_team'] == team_name else row['away_score'] > row['home_score']

    def is_draw(row):
        return row['home_score'] == row['away_score']

    wins = team_matches.apply(is_win, axis=1).sum()
    draws = team_matches.apply(is_draw, axis=1).sum()
    losses = played - wins - draws
    win_pct = f"{(wins / played) * 100:.1f}%" if played else "0.0%"
    points = wins * 3 + draws
    ppm = f"{points / played:.2f}" if played else "0.00"

    return pd.DataFrame([{
        "Matches Played": played,
        "Points": points,
        "Wins": wins,
        "Draws": draws,
        "Losses": losses,
        "Win %": win_pct,
        "Points per Match": ppm
    }])


def get_scoring_offensive_stats(events, matches_df, team_name):
    team_matches = matches_df[(matches_df['home_team'] == team_name) |
                              (matches_df['away_team'] == team_name)].copy()

    goals_scored = sum(row['home_score'] if row['home_team'] ==
                       team_name else row['away_score']
                       for _, row in team_matches.iterrows())
    goals_conceded = sum(row['away_score'] if row['home_team'] ==
                         team_name else row['home_score']
                         for _, row in team_matches.iterrows())
    goal_diff = goals_scored - goals_conceded
    clean_sheets = sum((row['away_score'] == 0 if row['home_team'] ==
                        team_name else row['home_score'] == 0)
                       for _, row in team_matches.iterrows())
    failed_to_score = sum((row['home_score'] == 0 if row['home_team'] ==
                           team_name else row['away_score'] == 0)
                          for _, row in team_matches.iterrows())

    team_events = events[events['team'] == team_name]
    shots = team_events[team_events['type'] == 'Shot']
    on_target = shots[shots['shot_outcome'].isin(['Goal', 'Saved'])]
    xg = shots['shot_statsbomb_xg'].sum()
    accuracy = f"{(len(on_target) / len(shots)) * 100:.1f}%" if len(
        shots) > 0 else "0.0%"

    team_passes = events[(events['team'] == team_name)
                         & (events['type'] == 'Pass')]
    completed = team_passes[team_passes['pass_outcome'].isna()]
    total_passes = len(team_passes)
    pass_acc = f"{(len(completed) / total_passes) * 100:.1f}%" if total_passes > 0 else "0.0%"

    possession_acts = events[events['type'].isin(
        ['Pass', 'Carry', 'Ball Receipt'])]
    total_acts = len(possession_acts)
    team_pos = possession_acts[possession_acts['team'] == team_name]
    avg_pos = f"{(len(team_pos) / total_acts) * 100:.1f}%" if total_acts > 0 else "0.0%"

    return pd.DataFrame({
        "Stat": [
            "Goals Scored", "Goals Conceded", "Goal Difference",
            "Clean Sheets", "Failed to Score", "Total Shots",
            "Shots on Target", "Shot Accuracy", "Expected Goals (xG)",
            "Passes Attempted", "Passes Completed", "Pass Accuracy",
            "Average Possession"
        ],
        "Value": [
            goals_scored, goals_conceded, goal_diff, clean_sheets,
            failed_to_score,
            len(shots),
            len(on_target), accuracy,
            round(xg, 2), total_passes,
            len(completed), pass_acc, avg_pos
        ]
    })


def get_passing_possession_stats(events, team_name):
    team_passes = events[(events['team'] == team_name)
                         & (events['type'] == 'Pass')]
    completed = team_passes[team_passes['pass_outcome'].isna()]
    total_passes = len(team_passes)
    pass_acc = f"{(len(completed) / total_passes) * 100:.1f}%" if total_passes > 0 else "0.0%"

    possession_acts = events[events['type'].isin(
        ['Pass', 'Carry', 'Ball Receipt'])]
    total_acts = len(possession_acts)
    team_pos = possession_acts[possession_acts['team'] == team_name]
    avg_pos = f"{(len(team_pos) / total_acts) * 100:.1f}%" if total_acts > 0 else "0.0%"

    return pd.DataFrame({
        "Stat": [
            "Passes Attempted", "Passes Completed", "Pass Accuracy",
            "Average Possession"
        ],
        "Value": [total_passes,
                  len(completed), pass_acc, avg_pos]
    })


def draw_team_shot_map(events, team_name):
    pitch_length, pitch_width = 120, 80

    shots = events[(events['type'] == 'Shot') & (events['team'] == team_name) &
                   (events['location'].notnull())].copy()

    if shots.empty:
        return go.Figure()

    shots['x'] = shots['location'].apply(lambda loc: loc[0])
    shots['y'] = shots['location'].apply(lambda loc: 80 - loc[1])
    shots['x'] = pitch_length - shots['x']
    shots['y'] = pitch_width - shots['y']

    goals = shots[shots['shot_outcome'] == 'Goal']
    on_target = shots[shots['shot_outcome'] == 'Saved']
    off_target = shots[~shots['shot_outcome'].isin(['Goal', 'Saved'])]

    fig = make_pitch_figure(
        PitchDimensions(pitch_width, pitch_length),
        pitch_background=SingleColourBackground("darkslategrey"))

    def scatter(df, color, size, symbol, label):
        fig.add_trace(
            go.Scatter(x=df['x'],
                       y=df['y'],
                       mode='markers',
                       marker=dict(size=size,
                                   color=color,
                                   symbol=symbol,
                                   line=dict(color='white', width=1.2)),
                       name=label,
                       hovertext=df['player'],
                       hoverinfo='text',
                       showlegend=True))

    scatter(off_target, "grey", 8, "circle", "Off Target")
    scatter(on_target, "dodgerblue", 10, "diamond", "On Target")
    scatter(goals, "crimson", 14, "star", "Goal")

    fig.update_layout(paper_bgcolor='#0a1128',
                      height=480,
                      width=800,
                      margin=dict(l=20, r=20, t=40, b=20),
                      title_font_color='white',
                      font_color='white',
                      showlegend=True)

    return fig


def get_team_result(row, team_name):
    is_home = row['home_team'] == team_name
    team_score = row['home_score'] if is_home else row['away_score']
    opp_score = row['away_score'] if is_home else row['home_score']

    if team_score > opp_score:
        return '🟩'
    elif team_score == opp_score:
        return '🟨'
    else:
        return '🟥'


def get_team_name(team_id):
    id_to_name = {v: k for k, v in internal_team_id().items()}
    return id_to_name.get(int(team_id), "Unknown Team")


def get_team_players(team_name):
    players = (lineups[lineups["team"] == team_name][[
        "jersey_number", "player_name", "player_id"
    ]].drop_duplicates("player_id").sort_values("jersey_number").rename(
        columns={
            "jersey_number": "Jersey",
            "player_name": "Name"
        }))
    return players.to_dict("records")


def get_team_matches(team_name):
    team_matches = matches[(matches['home_team'] == team_name) |
                           (matches['away_team'] == team_name)].copy()

    team_matches["Score"] = team_matches.apply(
        lambda row: f"{row['home_score']} : {row['away_score']}", axis=1)
    team_matches["Result"] = team_matches.apply(
        lambda row: get_team_result(row, team_name), axis=1)

    table_data = team_matches[[
        "match_id", "match_week", "Result", "home_team", "Score", "away_team"
    ]].rename(columns={
        "match_week": "Week",
        "home_team": "Home",
        "away_team": "Away"
    })

    return table_data.sort_values("Week").to_dict("records")


def get_top_scorers(events, team_name=None):
    goals = events[(events['type'] == 'Shot')
                   & (events['shot_outcome'] == 'Goal')].copy()

    if team_name:
        goals = goals[goals['team'] == team_name]

    penalty_goals = goals[goals['shot_type'] == 'Penalty']
    free_kick_goals = goals[goals['shot_type'] == 'Free Kick']

    df = (goals.groupby(['player']).size().reset_index(name='Goals').merge(
        penalty_goals.groupby('player').size().reset_index(name='Penalties'),
        on='player',
        how='left').merge(free_kick_goals.groupby('player').size().reset_index(
            name='Free Kicks'),
                          on='player',
                          how='left').fillna(0))

    df['Penalties'] = df['Penalties'].astype(int)
    df['Free Kicks'] = df['Free Kicks'].astype(int)
    df['Open Play'] = df['Goals'] - df['Penalties'] - df['Free Kicks']

    df = df.sort_values('Goals', ascending=False).reset_index(drop=True)
    df.index += 1
    return df.rename(columns={'player': 'Player'})[[
        'Player', 'Goals', 'Penalties', 'Free Kicks', 'Open Play'
    ]]


def get_top_assistants(events, team_name=None):
    goal_events = events[(events['type'] == 'Shot')
                         & (events['shot_outcome'] == 'Goal')]
    assist_ids = goal_events['shot_key_pass_id'].dropna()

    assist_passes = events[events['id'].isin(assist_ids)]

    if team_name:
        assist_passes = assist_passes[assist_passes['team'] == team_name]

    df = assist_passes.groupby('player').size().reset_index(name='Assists')
    df = df.sort_values('Assists', ascending=False).reset_index(drop=True)
    df.index += 1
    return df.rename(columns={'player': 'Player'})[['Player', 'Assists']]


import plotly.express as px
from dash import html, dcc


def draw_goals_treemap(events, team_name=None):
    df = get_top_scorers(events, team_name)

    fig = px.treemap(df,
                     path=['Player'],
                     values='Goals',
                     color='Goals',
                     color_continuous_scale='reds')

    fig.update_layout(
        paper_bgcolor='#1c273a',
        plot_bgcolor='#1c273a',
        font=dict(color='white', family='Segoe UI, sans-serif'),
        margin=dict(t=40, l=10, r=10, b=10),
        title_x=0.5,
    )

    return html.Div([
        dcc.Graph(figure=fig,
                  config={"displayModeBar": False},
                  style={
                      "height": "770px",
                      "width": "770px",
                      "margin": "0 auto"
                  })
    ],
                    style={
                        "maxWidth": "600px",
                        "maxHeight": "600px"
                    })


def layout(team_id=None):
    common_cell_style = {
        'backgroundColor': '#1c273a',
        'color': '#f0f0f0',
        'border': '1px solid #2f3e54',
        'padding': '8px',
        'textAlign': 'center',
        'fontSize': '15px',
        'fontFamily': 'Segoe UI, sans-serif',
        'cursor': 'pointer'
    }

    common_header_style = {
        'backgroundColor': '#324863',
        'color': '#ffffff',
        'fontWeight': 'bold',
        'fontSize': '15px',
        'borderBottom': '2px solid #50657a'
    }

    common_table_style = {
        'maxWidth': '600px',
        'maxHeight': '600px',
        'overflowY': 'auto',
        'margin': '1rem auto',
        'overflowX': 'auto'
    }

    team_name = get_team_name(team_id)
    player_data = get_team_players(team_name)
    match_data = get_team_matches(team_name)
    team_matches = matches[(matches['home_team'] == team_name) |
                           (matches['away_team'] == team_name)]
    match_ids = team_matches['match_id'].tolist()
    events = pd.DataFrame(
        list(db.events.find({"match_id": {
            "$in": match_ids
        }})))
    events, _ = apply_nicknames(events=events, lineups=lineups)

    scorers_df = get_top_scorers(events, team_name)
    assists_df = get_top_assistants(events, team_name)

    match_result_stats = get_match_result_stats(events, matches, team_name)
    scoring_offensive_stats = get_scoring_offensive_stats(
        events, matches, team_name)

    passing_possession_stats = get_passing_possession_stats(events, team_name)

    return html.Div([
        html.H1(f"👕 {team_name}", style={"textAlign": "center"}),
        dcc.Store(id='team-player-data', data=player_data),
        dcc.Store(id='team-match-data', data=match_data),

        #pasek
        dash_table.DataTable(columns=[{
            "name": col,
            "id": col
        } for col in match_result_stats.columns],
                             data=[match_result_stats.iloc[0].to_dict()],
                             style_table={
                                 "margin": "1rem auto",
                                 "maxWidth": "1400px",
                                 "overflowX": "auto",
                                 "borderRadius": "8px",
                                 "boxShadow": "0 0 8px rgba(0,0,0,0.3)"
                             },
                             style_cell={
                                 **common_cell_style, 'minWidth': '100px',
                                 'width': '100px',
                                 'maxWidth': '100px'
                             },
                             style_header=common_header_style),

        #mecze i składy
        html.Div(
            [
                html.Div([
                    html.H4("Matches", style={"textAlign": "center"}),
                    dash_table.DataTable(
                        id='team-matches-table',
                        columns=[{
                            "name": "Week",
                            "id": "Week"
                        }, {
                            "name": "Result",
                            "id": "Result"
                        }, {
                            "name": "Home",
                            "id": "Home"
                        }, {
                            "name": "Score",
                            "id": "Score"
                        }, {
                            "name": "Away",
                            "id": "Away"
                        }, {
                            "name": "Match ID",
                            "id": "match_id"
                        }],
                        data=match_data,
                        style_as_list_view=True,
                        style_cell=common_cell_style,
                        style_header=common_header_style,
                        style_data_conditional=[{
                            'if': {
                                'row_index': 'odd'
                            },
                            'backgroundColor': '#1e2a3e'
                        }, {
                            'if': {
                                'state': 'active'
                            },
                            'backgroundColor': '#2a3b50'
                        }, {
                            'if': {
                                'column_id': 'match_id'
                            },
                            'display': 'none'
                        }],
                        style_header_conditional=[{
                            'if': {
                                'column_id': 'match_id'
                            },
                            'display': 'none'
                        }],
                        style_table=common_table_style)
                ],
                         style={
                             "width": "50%",
                             "margin": "0",
                             "padding": "0"
                         }),
                html.Div([
                    html.H4("Squad", style={"textAlign": "center"}),
                    dash_table.DataTable(
                        id='team-players-table',
                        columns=[
                            {
                                "name": "Jersey",
                                "id": "Jersey"
                            },
                            {
                                "name": "Name",
                                "id": "Name"
                            },
                            {
                                "name": "player_id",
                                "id": "player_id"
                            },
                        ],
                        data=player_data,
                        style_as_list_view=True,
                        style_cell=common_cell_style,
                        style_header=common_header_style,
                        style_data_conditional=[{
                            'if': {
                                'row_index': 'odd'
                            },
                            'backgroundColor': '#1e2a3e'
                        }, {
                            'if': {
                                'state': 'active'
                            },
                            'backgroundColor': '#2a3b50'
                        }, {
                            'if': {
                                'column_id': 'player_id'
                            },
                            'display': 'none'
                        }],
                        style_header_conditional=[{
                            'if': {
                                'column_id': 'player_id'
                            },
                            'display': 'none'
                        }],
                        style_table=common_table_style)
                ],
                         style={
                             "width": "50%",
                             "margin": "0",
                             "padding": "0"
                         })
            ],
            style={
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "flex-start",
                "margin": "1rem auto",
                "padding": "0",
                "gap": "4rem",
                "maxWidth": "1400px",
                "width": "100%"
            }),

        #strzelcy, asystenci
        html.Div(
            [
                html.Div([
                    html.H4("Top Scorers", style={"textAlign": "center"}),
                    dash_table.DataTable(columns=[{
                        "name": col,
                        "id": col
                    } for col in scorers_df.columns],
                                         data=scorers_df.to_dict("records"),
                                         style_table={
                                             'maxWidth': '600px',
                                             'maxHeight': '375px',
                                             'overflowY': 'scroll',
                                             'margin': '1rem auto',
                                             'overflowX': 'auto'
                                         },
                                         style_cell=common_cell_style,
                                         style_header=common_header_style),
                    html.H4("Top Assistants",
                            style={
                                "textAlign": "center",
                                "marginTop": "2rem"
                            }),
                    dash_table.DataTable(columns=[{
                        "name": col,
                        "id": col
                    } for col in assists_df.columns],
                                         data=assists_df.to_dict("records"),
                                         style_table={
                                             'maxWidth': '600px',
                                             'maxHeight': '375px',
                                             'overflowY': 'scroll',
                                             'margin': '1rem auto',
                                             'overflowX': 'auto'
                                         },
                                         style_cell=common_cell_style,
                                         style_header=common_header_style)
                ],
                         style={
                             "width": "50%",
                             "margin": "0",
                             "padding": "0"
                         }),
                html.Div([
                    html.H4("Goals by player",
                            style={
                                "textAlign": "center",
                                "marginTop": "2rem"
                            }),
                    draw_goals_treemap(events, team_name)
                ],
                         style={"flex": 1})
            ],
            style={
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "flex-start",
                "margin": "1rem auto",
                "padding": "0",
                "gap": "4rem",
                "maxWidth": "1400px",
                "width": "100%"
            }),

        #atak i mapa strzałów
        html.Div(
            [
                html.Div([
                    html.H4("Scoring Stats", style={"textAlign": "center"}),
                    dash_table.DataTable(
                        columns=[{
                            "name": col,
                            "id": col
                        } for col in scoring_offensive_stats.columns],
                        data=scoring_offensive_stats.to_dict("records"),
                        style_table=common_table_style,
                        style_cell=common_cell_style,
                        style_header=common_header_style)
                ],
                         style={
                             "flex": 1,
                             "marginRight": "-200px"
                         }),
                html.Div([
                    html.H4("Shots Map",
                            style={
                                "textAlign": "center",
                                "marginLeft": "-300px"
                            }),
                    dcc.Graph(figure=draw_team_shot_map(events, team_name),
                              config={"displayModeBar": False},
                              style={
                                  "width": "100%",
                                  "height": "100%",
                                  "maxWidth": "800px"
                              })
                ],
                         style={
                             "flex": 1,
                             "alignItems": "flex-start"
                         })
            ],
            style={
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "flex-center",
                "margin": "1rem auto",
                "padding": "0",
                "gap": "4rem",
                "width": "100%",
                "marginRight": "-120px"
            }),
        dcc.Location(id='team-url')
    ])


@callback(Output('team-url', 'pathname'),
          Input('team-players-table', 'active_cell'),
          Input('team-player-data', 'data'))
def go_to_player(active_cell, data):
    if active_cell and data:
        row = active_cell['row']
        player_id = data[row]['player_id']
        return f"/player/{player_id}"
    return dash.no_update


@callback(Output('team-url', 'pathname', allow_duplicate=True),
          Input('team-matches-table', 'active_cell'),
          Input('team-match-data', 'data'),
          prevent_initial_call=True)
def go_to_match(active_cell, data):
    if active_cell and data:
        row = active_cell['row']
        match_id = data[row]['match_id']
        return f"/match/{match_id}"
    return dash.no_update
