import dash
from dash import html, dash_table, dcc, callback, Output, Input
import pandas as pd
from pymongo import MongoClient
from utils import internal_team_id

dash.register_page(__name__, path="/matches", name="Matches")

client = MongoClient("mongodb://localhost:27017/")
db = client["football_data"]
matches = pd.DataFrame(list(db.matches.find()))

matches["Score"] = matches.apply(lambda row: f"{row['home_score']} : {row['away_score']}", axis=1)

table_data_full = matches[["match_id", "match_week", "home_team", "Score", "away_team"]].rename(columns={
    "home_team": "Home",
    "away_team": "Away"
})

layout = html.Div([
    html.H2("📅 Match List", style={"textAlign": "center"}),

    html.Div([
        dcc.Dropdown(
            id="matchweek-dropdown",
            className="dark-dropdown",
            options=[{"label": f"Week {i}", "value": i} for i in sorted(matches["match_week"].dropna().unique())],
            placeholder="Select Matchweek",
            value=1,
            style={"width": "250px", "margin": "1rem auto"},
            clearable=False
        )
    ], style={"textAlign": "center"}),

    dcc.Store(id='match-data'),

    html.Div([
        dash_table.DataTable(
            id='matches-table',
            columns=[
                {'name': 'Home', 'id': 'Home'},
                {'name': 'Score', 'id': 'Score'},
                {'name': 'Away', 'id': 'Away'},
                {'name': 'Match ID', 'id': 'match_id'},
            ],
            page_action='none',
            style_as_list_view=True,

            style_cell={
                'backgroundColor': '#1c273a',
                'color': '#f0f0f0',
                'border': '1px solid #2f3e54',
                'padding': '8px',
                'fontSize': '15px',
                'fontFamily': 'Segoe UI, sans-serif',
                'cursor': 'pointer',
                'whiteSpace': 'normal',
                'height': 'auto',
            },

            style_cell_conditional=[
                {'if': {'column_id': 'Home'}, 'width': '240px', 'textAlign': 'left'},
                {'if': {'column_id': 'Away'}, 'width': '240px', 'textAlign': 'right'},
                {'if': {'column_id': 'Score'}, 'width': '80px', 'textAlign': 'center'},
                {'if': {'column_id': 'match_id'}, 'display': 'none'},
            ],

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
                'maxWidth': '700px',
                'margin': '0 auto',
                'border': 'none',
                'overflowX': 'auto'
            }
        )
    ]),

    dcc.Location(id='matches-url', refresh=True)
], className='container')

#do aktualizacji po rundzie
@callback(
    Output('matches-table', 'data'),
    Output('match-data', 'data'),
    Input('matchweek-dropdown', 'value')
)
def update_table(matchweek):
    if matchweek is None:
        return [], []
    filtered = table_data_full[table_data_full["match_week"] == matchweek]
    data = filtered.to_dict("records")
    return data, data

#idź do meczu albo drużyny
@callback(
    Output('matches-url', 'pathname'),
    Input('matches-table', 'active_cell'),
    Input('match-data', 'data')
)
def row_click_navigation(active_cell, data):
    ids = internal_team_id()
    if active_cell and data:
        row_idx = active_cell['row']
        col_id = active_cell['column_id']
        row = data[row_idx]

        if col_id == "Score":
            return f"/match/{row['match_id']}"
        elif col_id == "Home":
            return f"/team/{ids[row['Home']]}"
        elif col_id == "Away":
            return f"/team/{ids[row['Away']]}"
    return dash.no_update
