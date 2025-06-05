import dash
from dash import html, dcc, dash_table
import pandas as pd
import plotly.graph_objs as go
from pymongo import MongoClient
import utils
from plotly_football_pitch import make_pitch_figure, PitchDimensions, SingleColourBackground, add_heatmap
import numpy as np
from scipy.ndimage import gaussian_filter

dash.register_page(__name__, path_template="/player/<player_id>")

client = MongoClient("mongodb://localhost:27017/")
db = client["football_data"]


def get_player_info(player_id):
    lineups = pd.DataFrame(list(db.lineups.find()))
    player_row = lineups[lineups['player_id'] == player_id]
    if player_row.empty:
        return None, None
    return player_row.iloc[0].to_dict(), lineups[lineups['player_id'] ==
                                                 player_id]


def get_related_data(player_id, team):
    query = {
        '$or': [
            {
                'player_id': player_id
            },
            {
                'pass_recipient_id': player_id
            },
            {
                'substitution_replacement_id': player_id
            },
        ]
    }
    events = pd.DataFrame(list(db.events.find(query)))
    matches = pd.DataFrame(list(db.matches.find({'team': team})))
    starting_events = pd.DataFrame(
        list(db.events.find({
            'type': 'Starting XI',
            'team': team
        })))
    return events, matches, starting_events


def extract_player_events(events, player_id):
    player_events = events[(events['player_id'] == player_id)
                           & events['location'].notna()].copy()
    player_events['x'] = player_events['location'].apply(lambda loc: loc[0])
    player_events['y'] = player_events['location'].apply(lambda loc: loc[1])
    return player_events


def get_position_counts(starting_events, player_id):
    position_counts = {}
    for _, row in starting_events.iterrows():
        lineup = row.get('tactics', {}).get('lineup', [])
        for p in lineup:
            if p['player']['id'] == player_id:
                pos = p['position']['name']
                position_counts[pos] = position_counts.get(pos, 0) + 1
    return position_counts


def calculate_appearances(events, starting_events, player_id, position_counts):
    starting_appearances = sum(position_counts.values())
    sub_appearances = len(
        events[(events['type'] == 'Substitution')
               & (events.get('substitution_replacement_id') == player_id)]
    ) if 'substitution_replacement_id' in events.columns else 0
    return starting_appearances, sub_appearances


def generate_stats_table(player_events, events, minutes_played, player_id):

    def count_event(df, event_type, condition=None):
        if 'type' not in df.columns:
            return 0
        filtered = df[df['type'] == event_type]
        if condition:
            try:
                filtered = filtered[condition(filtered)]
            except KeyError:
                return 0
        return filtered.shape[0]

    def safe_per_90(value):
        return round(value * 90 /
                     minutes_played, 2) if minutes_played > 0 else 0.0

    total_passes = count_event(player_events, 'Pass')
    completed_passes = count_event(player_events, 'Pass',
                                   lambda df: df['pass_outcome'].isna())
    dribbles = count_event(player_events, 'Dribble')
    successful_dribbles = count_event(
        player_events, 'Dribble',
        lambda df: df['dribble_outcome'] == 'Complete')
    total_shots = count_event(player_events, 'Shot')
    goals = count_event(player_events, 'Shot',
                        lambda df: df['shot_outcome'] == 'Goal')
    fouls_committed = count_event(player_events, 'Foul Committed')
    fouls_won = count_event(player_events, 'Foul Won')
    carries = count_event(player_events, 'Carry')

    touches = 0
    if 'type' in events.columns and 'player_id' in events.columns:
        touches = events[(events['player_id'] == player_id)
                         & (events['type'].isin([
                             'Pass', 'Carry', 'Dribble', 'Shot',
                             'Interception', 'Clearance', 'Block', 'Foul Won'
                         ]))].shape[0]

    df_stats = pd.DataFrame({
        'Stat': [
            'Passes', 'Pass accuracy', 'Dribbles', 'Shots', 'Goals',
            'Fouls committed', 'Fouls received', 'Ball touches', 'Carries'
        ],
        'Total': [
            total_passes, f"{round(100 * completed_passes / total_passes, 2)}%"
            if total_passes > 0 else "0%", f"{successful_dribbles}/{dribbles}",
            total_shots, goals, fouls_committed, fouls_won, touches, carries
        ],
        'Per 90': [
            safe_per_90(total_passes), '',
            f"{safe_per_90(successful_dribbles)}/{safe_per_90(dribbles)}",
            safe_per_90(total_shots),
            safe_per_90(goals),
            safe_per_90(fouls_committed),
            safe_per_90(fouls_won),
            safe_per_90(touches),
            safe_per_90(carries)
        ]
    })

    return df_stats


def calculate_minutes(events_df, starting_df, player_id):
    minutes = 0
    if events_df.empty or 'match_id' not in events_df.columns:
        return 0
    for match_id in events_df['match_id'].unique():
        match_events = events_df[events_df['match_id'] == match_id]
        match_start = starting_df[starting_df['match_id'] == match_id]
        started = False

        if not match_start.empty:
            lineup = match_start.iloc[0].get('tactics', {}).get('lineup', [])
            if any(p['player']['id'] == player_id for p in lineup):
                started = True

        sub_out = match_events[(match_events['type'] == 'Substitution') & (
            match_events.get('player_id') == player_id if 'player_id' in
            match_events.columns else False)]

        sub_in = match_events[(match_events['type'] == 'Substitution') & (
            match_events.get('substitution_replacement_id') == player_id
            if 'substitution_replacement_id' in match_events.columns else False
        )] if 'substitution_replacement_id' in match_events.columns else pd.DataFrame(
        )

        if started:
            if not sub_out.empty:
                minutes += sub_out.iloc[0]['minute']
            else:
                minutes += 90
        elif not started and not sub_in.empty:
            minutes += (90 - sub_in.iloc[0]['minute'])

    return minutes


def draw_map(player_events, shots, position_counts):
    import pandas as pd
    from scipy.ndimage import gaussian_filter

    pitch_width, pitch_length = 80, 120
    coords = utils.get_coordinates()

    #heatmap
    width_bins, length_bins = 40, 60
    heatmap = np.zeros((width_bins, length_bins))
    bin_width = pitch_width / width_bins
    bin_length = pitch_length / length_bins

    for _, row in player_events.iterrows():
        x, y = row['x'], 80 - row['y']
        col = int(x / bin_length)
        row_ = int(y / bin_width)
        if 0 <= row_ < width_bins and 0 <= col < length_bins:
            heatmap[row_, col] += 1

    if heatmap.max() > 0:
        heatmap = heatmap / heatmap.max()
    smoothed = gaussian_filter(heatmap, sigma=1.2)

    fig = make_pitch_figure(PitchDimensions(pitch_width, pitch_length),
                            pitch_background=SingleColourBackground("#2F4F4F"))

    fig = add_heatmap(fig,
                      smoothed,
                      colorscale='YlOrRd',
                      opacity=0.9,
                      showscale=False,
                      showlegend=True,
                      name='Activity',
                      hoverinfo="skip")

    #strzały
    if not shots.empty:

        def classify(outcome):
            if outcome == 'Goal':
                return 'Goal'
            elif outcome in ['Saved', 'Saved to Post', 'Saved Off Target']:
                return 'On Target'
            return 'Off Target'

        shots = shots.copy()
        shots['category'] = shots['shot_outcome'].apply(classify)
        shots['x'] = shots['location'].apply(lambda loc: loc[0])
        shots['y'] = shots['location'].apply(lambda loc: 80 - loc[1])

        symbol_map = {
            'Goal': 'star',
            'On Target': 'diamond',
            'Off Target': 'circle'
        }
        color_map = {'Goal': 'red', 'On Target': 'blue', 'Off Target': 'gray'}

        for cat in shots['category'].unique():
            cat_data = shots[shots['category'] == cat]
            fig.add_trace(
                go.Scatter(x=cat_data['x'],
                           y=cat_data['y'],
                           mode='markers',
                           name=cat,
                           marker=dict(symbol=symbol_map[cat],
                                       size=12,
                                       color=color_map[cat],
                                       line=dict(color='white', width=1)),
                           text=cat_data['shot_outcome'],
                           hoverinfo='text'))

    #pozycje
    if position_counts:
        data = []
        for pos, count in position_counts.items():
            x, y = coords[pos]
            data.append({
                "Position": pos,
                "Count": count,
                "x": 2 * x,
                "y": 80 - y
            })

        df = pd.DataFrame(data)

        fig.add_trace(
            go.Scatter(x=df["x"],
                       y=df["y"],
                       mode="markers",
                       name="Starting Positions",
                       text=[
                           f"{pos}<br>{count}"
                           for pos, count in zip(df["Position"], df["Count"])
                       ],
                       textposition="top center",
                       marker=dict(size=20,
                                   color="purple",
                                   line=dict(color="white", width=2)),
                       hoverinfo="text",
                       showlegend=True))

    fig.update_layout(paper_bgcolor="#0a1128",
                      plot_bgcolor="#0a1128",
                      height=600,
                      width=1000,
                      font_color='white',
                      margin=dict(l=20, r=20, t=40, b=20))

    return fig


def layout(player_id=None):
    player_id = int(player_id)
    player_info, lineups = get_player_info(player_id)
    if not player_info:
        return html.Div(f"No player found with ID {player_id}")

    full_name = player_info['player_name']
    team = player_info['team']
    nickname = player_info.get('player_nickname') or full_name
    country = player_info.get('country', 'N/A')
    jersey = player_info.get('jersey_number', 'N/A')

    events, matches, starting_events = get_related_data(player_id, team)
    minutes_played = calculate_minutes(events, starting_events, player_id)
    if events.empty or minutes_played == 0:
        return html.Div([
            html.H2(f"{nickname}",
                    style={
                        "textAlign": "center",
                        "marginBottom": "1rem"
                    }),
            html.P(f"Nationality: {country} | Jersey: {jersey} | Team: {team}",
                   style={"textAlign": "center"}),
            html.H4("No Data",
                    style={
                        "textAlign": "center",
                        "marginTop": "2rem"
                    }),
            html.P(f"{nickname} has not played his season.",
                   style={
                       "textAlign": "center",
                       "color": "#bbbbbb"
                   })
        ],
                        style={"padding": "2rem"})
    events, lineups = utils.apply_nicknames(events,
                                            lineups,
                                            starting_events=starting_events)

    position_counts = get_position_counts(starting_events, player_id)
    starting_appearances, sub_appearances = calculate_appearances(
        events, starting_events, player_id, position_counts)

    player_events = extract_player_events(events, player_id)
    shots = player_events[player_events['type'] == 'Shot'].copy()
    stats_table = generate_stats_table(player_events, events, minutes_played,
                                       player_id)
    appearance_data = pd.DataFrame([{
        "Minutes Played": minutes_played,
        "Appearances": starting_appearances + sub_appearances,
        "Starts": starting_appearances,
        "Sub-ins": sub_appearances
    }])

    common_header_style = {
        'backgroundColor': '#324863',
        'color': '#ffffff',
        'fontWeight': 'bold',
        'fontSize': '15px',
        'borderBottom': '2px solid #50657a'
    }
    return html.Div(
        [
            html.H1(f"{nickname}",
                    style={
                        "textAlign": "center",
                        "marginBottom": "1rem"
                    }),
            html.
            P(f"  👕Team: {team}       📍Nationality: {country}       #️Jersey: {jersey}",
              style={
                  "textAlign": "center",
                  "fontSize": "20px"
              }),
            html.Div([
                #występy
                dash_table.DataTable(columns=[{
                    "name": col,
                    "id": col
                } for col in appearance_data.columns],
                                     data=[appearance_data.iloc[0].to_dict()],
                                     style_table={
                                         "margin": "1rem auto",
                                         "maxWidth": "650px",
                                         "overflowX": "auto",
                                         "borderRadius": "8px",
                                         "width": "100%"
                                     },
                                     style_cell={
                                         'backgroundColor': '#1c273a',
                                         'color': '#f0f0f0',
                                         'border': '1px solid #2f3e54',
                                         'padding': '8px',
                                         'textAlign': 'center',
                                         'fontSize': '15px',
                                         'fontFamily': 'Segoe UI, sans-serif',
                                         'cursor': 'pointer',
                                         'minWidth': '100px',
                                         'width': '100px',
                                         'maxWidth': '100px'
                                     },
                                     style_header={
                                         'backgroundColor': '#324863',
                                         'color': '#ffffff',
                                         'fontWeight': 'bold',
                                         'fontSize': '15px',
                                         'borderBottom': '2px solid #50657a',
                                         'textAlign': 'center'
                                     })
            ]),
            html.Div(
                [
                    #tabelka
                    html.Div(
                        [
                            html.H4("Season Stats",
                                    style={
                                        "textAlign": "center",
                                        "marginBottom": "40px"
                                    }),
                            dash_table.DataTable(
                                columns=[{
                                    "name": col,
                                    "id": col
                                } for col in stats_table.columns],
                                data=stats_table.to_dict("records"),
                                style_table={
                                    "width": "100%",
                                    "overflowX": "auto"
                                },
                                style_cell={
                                    'backgroundColor': '#1c273a',
                                    'color': '#f0f0f0',
                                    'border': '1px solid #2f3e54',
                                    'padding': '8px',
                                    'textAlign': 'center',
                                    'fontSize': '15px',
                                    'fontFamily': 'Segoe UI, sans-serif',
                                    'cursor': 'pointer',
                                    'whiteSpace': 'normal'
                                },
                                style_header=common_header_style)
                        ],
                        style={
                            "width": "30%",
                            "display": "inline-block",
                            "marginLeft": "2%",
                            "verticalAlign": "top"
                        }),

                    #mapa
                    html.Div(
                        [
                            html.H4("Mega Map", style={"textAlign": "center"}),
                            dcc.Graph(figure=draw_map(player_events, shots,
                                                      position_counts),
                                      config={"displayModeBar": False},
                                      style={
                                          "width": "100%",
                                          "maxWidth": "800px",
                                          "margin": "0 auto"
                                      })
                        ],
                        style={
                            "flex": "0 0 700px",
                            "display": "flex",
                            "flexDirection": "column",
                            "alignItems": "center"
                        })
                ],
                style={
                    "display": "flex",
                    "justifyContent": "center",
                    "gap": "2rem",
                    "marginTop": "2rem",
                    "flexWrap": "wrap"
                }),
        ],
        style={"padding": "2rem"})
