import dash
from dash import html, dash_table, dcc, callback, Output, Input
from pymongo import MongoClient
import pandas as pd
from utils import internal_team_id
import plotly.graph_objs as go

dash.register_page(__name__, path="/")

# === MongoDB Setup ===
client = MongoClient("mongodb://localhost:27017/")
db = client["football_data"]
matches = pd.DataFrame(list(db.matches.find()))

# Wyszukaniwanie w bazie danych wszystkich goli
normal_goals_query = {
    "type": "Shot",
    "shot_outcome": "Goal"
}
normal_goals = pd.DataFrame(list(db.events.find(normal_goals_query)))

# Dołączenie goli samobójczych, nie są one traktowane jak strzały
own_goals_query = {
    "type": "Own Goal For"
}
own_goals = pd.DataFrame(list(db.events.find(own_goals_query)))

goals = pd.concat([normal_goals, own_goals], ignore_index=True)

def generate_league_table(matches):
    # Goals
    home_goals_scored = matches.groupby('home_team')['home_score'].sum().rename('home_goals')
    away_goals_scored = matches.groupby('away_team')['away_score'].sum().rename('away_goals')
    home_goals_conceded = matches.groupby('home_team')['away_score'].sum().rename('home_goals_conceded')
    away_goals_conceded = matches.groupby('away_team')['home_score'].sum().rename('away_goals_conceded')

    goal_stats = pd.concat([
        home_goals_scored,
        away_goals_scored,
        home_goals_conceded,
        away_goals_conceded
    ], axis=1)

    goal_stats['goals_scored'] = goal_stats['home_goals'] + goal_stats['away_goals']
    goal_stats['goals_conceded'] = goal_stats['home_goals_conceded'] + goal_stats['away_goals_conceded']
    goal_stats['goal_difference'] = goal_stats['goals_scored'] - goal_stats['goals_conceded']

    # Results
    home = matches[['home_team', 'home_score', 'away_score']].copy()
    home.columns = ['team', 'goals_for', 'goals_against']
    away = matches[['away_team', 'away_score', 'home_score']].copy()
    away.columns = ['team', 'goals_for', 'goals_against']

    results = pd.concat([home, away], ignore_index=True)
    results['win'] = results['goals_for'] > results['goals_against']
    results['draw'] = results['goals_for'] == results['goals_against']
    results['loss'] = results['goals_for'] < results['goals_against']
    results['points'] = results['win'] * 3 + results['draw']

    league_stats = results.groupby('team').agg(
        matches_played=('team', 'count'),
        wins=('win', 'sum'),
        draws=('draw', 'sum'),
        losses=('loss', 'sum'),
        points=('points', 'sum')
    )

    # Merge & Order
    final_table = league_stats.join(goal_stats)
    final_table = final_table.sort_values(by=['points', 'goal_difference', 'goals_scored'], ascending=False)

    col_order = [
        'points', 'goal_difference', 'wins', 'draws', 'losses',
        'goals_scored', 'goals_conceded', 'home_goals', 'away_goals',
        'home_goals_conceded', 'away_goals_conceded'
    ]
    final_table = final_table[col_order].reset_index()
    final_table.index += 1
    final_table.reset_index(inplace=True)  # add position

    final_table.rename(columns={
        'index': '#',
        'team': 'Team',
        'points': 'PTS',
        'goal_difference': 'DIFF',
        'wins': 'W',
        'draws': 'D',
        'losses': 'L',
        'goals_scored': 'G',
        'goals_conceded': 'GC',
        'home_goals': 'Home G',
        'away_goals': 'Away G',
        'home_goals_conceded': 'H. GC',
        'away_goals_conceded': 'A. GC'
    }, inplace=True)

    final_table['team_id'] = final_table['Team']
    return final_table

def generate_top_scorers(goals_df):
    non_own_goals = goals_df[goals_df['type'] == 'Shot'].copy()

    top_scorers = (
        non_own_goals
        .groupby(['player', 'team'])
        .size()
        .reset_index(name='goals')
        .sort_values(by='goals', ascending=False)
    )

    penalty_goals = (
        non_own_goals[non_own_goals['shot_type'] == 'Penalty']
        .groupby(['player', 'team'])
        .size()
        .reset_index(name='penalties')
    )

    free_kick_goals = (
        non_own_goals[non_own_goals['shot_type'] == 'Free Kick']
        .groupby(['player', 'team'])
        .size()
        .reset_index(name='free_kicks')
    )

    top_scorers = top_scorers.merge(penalty_goals, on=['player', 'team'], how='left')
    top_scorers = top_scorers.merge(free_kick_goals, on=['player', 'team'], how='left')
    top_scorers['penalties'] = top_scorers['penalties'].fillna(0).astype(int)
    top_scorers['free_kicks'] = top_scorers['free_kicks'].fillna(0).astype(int)
    top_scorers['open_play'] = top_scorers['goals'] - top_scorers['penalties'] - top_scorers['free_kicks']
    top_scorers = top_scorers.reset_index(drop=True)
    top_scorers.index += 1
    top_scorers.columns = ['Player', 'Team', 'Goals', 'Pen.', 'FK', 'Open Play']

    return top_scorers

def generate_top_assistants(goals_df, db):
    non_own_goals = goals_df[goals_df['type'] == 'Shot'].copy()
    assist_ids = non_own_goals['shot_key_pass_id'].dropna().reset_index(drop=True)
    assist_rows = []

    for id in assist_ids:
        result = db.events.find_one({'type': 'Pass', 'id': id}, {"player": 1, "team": 1, "_id": 0})
        if result:
            assist_rows.append(result)

    assists_df = pd.DataFrame(assist_rows)
    top_assistants = assists_df.groupby(['player', 'team']).size().reset_index(name='Assists')
    top_assistants = top_assistants.sort_values('Assists', ascending=False).reset_index(drop=True)
    top_assistants.columns = ['Player', 'Team', 'Assists']
    top_assistants.index += 1

    return top_assistants

def geenrate_title_race(matches_df):
    # Prepare data for home and away games
    home = matches_df[['match_id', 'match_week', 'home_team', 'home_score', 'away_score']].copy()
    home['team'] = home['home_team']
    home['goals_for'] = home['home_score']
    home['goals_against'] = home['away_score']

    away = matches_df[['match_id', 'match_week', 'away_team', 'away_score', 'home_score']].copy()
    away['team'] = away['away_team']
    away['goals_for'] = away['away_score']
    away['goals_against'] = away['home_score']

    results = pd.concat([home, away], ignore_index=True)

    # Assign points
    results['points'] = results.apply(
        lambda row: 3 if row['goals_for'] > row['goals_against'] else 1 if row['goals_for'] == row['goals_against'] else 0,
        axis=1
    )
    results = results.sort_values(by=['team', 'match_week'])
    results['cumulative_points'] = results.groupby('team')['points'].cumsum()

    # Order teams for consistent legend
    final_points = results[results['match_week'] == results['match_week'].max()]
    ordered_teams = final_points.sort_values(by='cumulative_points', ascending=False)['team']

    # Plotly Figure
    fig = go.Figure()
    for team in ordered_teams:
        team_data = results[results['team'] == team]
        fig.add_trace(go.Scatter(
            x=team_data['match_week'],
            y=team_data['cumulative_points'],
            mode='lines+markers',
            name=team,
            hovertemplate=f"<b>{team}</b><br>Week: %{{x}}<br>Points: %{{y}}<extra></extra>"
        ))

    fig.update_layout(
        xaxis_title="Matchweek",
        yaxis_title="Points",
        template="plotly_dark",
        height=600,
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
        xaxis=dict(dtick=1),
        yaxis=dict(dtick=10),
        legend=dict(orientation="v", x=1.02, y=1, bgcolor='#324863'),
        legend_title_text="Team",
        plot_bgcolor="#1c273a",  
        paper_bgcolor="#1c273a"   
    )

    return fig


final_table = generate_league_table(matches)
top_scorers = generate_top_scorers(goals)
top_assistants = generate_top_assistants(goals, db)


layout = html.Div([
    html.H2("League Table", style={"textAlign": "center"}),

    dcc.Store(id="league-data", data=final_table.to_dict("records")),

    dash_table.DataTable(
        id="league-table",
        columns=[{"name": col, "id": col} for col in final_table.columns if col != 'team_id'],
        data=final_table.to_dict("records"),
        style_as_list_view=True,
        style_cell={
            'backgroundColor': '#1c273a',
            'color': '#f0f0f0',
            'border': '1px solid #2f3e54',
            'padding': '8px',
            'textAlign': 'center',
            'fontSize': '15px',
            'fontFamily': 'Segoe UI, sans-serif',
            'cursor': 'pointer'
        },
        style_header={
            'backgroundColor': '#324863',
            'color': '#ffffff',
            'fontWeight': 'bold',
            'fontSize': '15px',
            'borderBottom': '2px solid #50657a'
        },
        style_data_conditional=[
            {'if': {'row_index': 'odd'}, 'backgroundColor': '#1e2a3e'},
            {'if': {'state': 'active'}, 'backgroundColor': '#2a3b50'}
        ],
        style_table={
            'width': '100%',
            'maxWidth': '100%',
            'overflowX': 'visible',
            'overflowY': 'auto',
            'border': 'none',
            'marginBottom': '2rem'
        }
    ),


    html.Div([
        html.Div([
            html.H3("Top Scorers", style={"textAlign": "center"}),
            dash_table.DataTable(
                columns=[{"name": col, "id": col} for col in top_scorers.columns],
                data=top_scorers.head(20).to_dict("records"),
                style_as_list_view=True,
                style_table={"width": "100%", "overflowX": "auto"},
                style_cell={
                    "backgroundColor": "#1c273a",
                    "color": "#f0f0f0",
                    "fontFamily": "Segoe UI, sans-serif",
                    "border": "1px solid #2f3e54",
                    "padding": "6px",
                    "textAlign": "center",
                    "fontSize": "14px"
                },
                style_header={
                    "backgroundColor": "#324863",
                    "color": "white",
                    "fontWeight": "bold"
                }
            )
        ], style={"width": "49%", "display": "inline-block", "verticalAlign": "top"}),

        html.Div([
            html.H3("Top Assistants", style={"textAlign": "center"}),
            dash_table.DataTable(
                columns=[{"name": col, "id": col} for col in top_assistants.columns],
                data=top_assistants.head(20).to_dict("records"),
                style_as_list_view=True,
                style_table={"width": "100%", "overflowX": "auto"},
                style_cell={
                    "backgroundColor": "#1c273a",
                    "color": "#f0f0f0",
                    "fontFamily": "Segoe UI, sans-serif",
                    "border": "1px solid #2f3e54",
                    "padding": "6px",
                    "textAlign": "center",
                    "fontSize": "14px"
                },
                style_header={
                    "backgroundColor": "#324863",
                    "color": "white",
                    "fontWeight": "bold"
                }
            )
        ], style={"width": "49%", "display": "inline-block", "marginLeft": "2%", "verticalAlign": "top"})
    ], style={"textAlign": "center", 'marginBottom': '2rem'}),
    
    html.Div([
        html.H3("Title Race", style={"textAlign": "center", "marginTop": "2rem"}),
        dcc.Graph(
            figure=geenrate_title_race(matches),
            config={"displayModeBar": False},
            style={"width": "100%", "maxWidth": "1200px", "margin": "0 auto"}
        )
    ], style={"marginBottom": "2rem"}),

    dcc.Location(id='league-url', refresh=True)
], className="container")


@callback(
    Output("league-url", "pathname"),
    Input("league-table", "active_cell"),
    Input("league-data", "data")
)
def navigate_to_team(active_cell, table_data):
    if active_cell and table_data:
        row = active_cell['row']
        team_name = table_data[row]['Team']
        team_id = internal_team_id().get(team_name)
        if team_id:
            return f"/team/{team_id}"
    return dash.no_update
