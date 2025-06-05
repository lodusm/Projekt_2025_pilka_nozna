import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import pandas as pd
from pymongo import MongoClient
from utils import apply_nicknames, internal_team_id

client = MongoClient("mongodb://localhost:27017/")
db = client["football_data"]
lineups = pd.DataFrame(list(db.lineups.find()))
lineups = apply_nicknames(lineups=lineups)

teams = sorted(lineups["team"].dropna().unique())
players = sorted(lineups["player_name"].dropna().unique())

app = dash.Dash(__name__,
                use_pages=True,
                external_stylesheets=[dbc.themes.FLATLY],
                suppress_callback_exceptions=True)
app.title = "LaLiga Dashboard"
server = app.server

navbar = dbc.Navbar(dbc.Container([
    dbc.Row([
        dbc.Col(dbc.NavbarBrand(
            "⚽ LaLiga 2015/16", href="/", className="brand-title"),
                width="auto"),
        dbc.Col(dbc.Nav([
            dbc.NavItem(
                dbc.NavLink("Matches", href="/matches", className="nav-link")),
        ]),
                width="auto",
                className="align-self-center"),
        dbc.Col(dcc.Dropdown(id='team-dropdown',
                             options=[{
                                 'label': t,
                                 'value': t
                             } for t in teams],
                             placeholder="Select team",
                             className="dark-dropdown",
                             style={"width": "200px"}),
                width="auto",
                className="align-self-center"),
        dbc.Col(dcc.Dropdown(id='player-dropdown',
                             options=[{
                                 'label': p,
                                 'value': p
                             } for p in players],
                             placeholder="Select player",
                             className="dark-dropdown",
                             style={"width": "200px"}),
                width="auto",
                className="align-self-center"),
    ],
            className="g-2 align-items-center flex-nowrap",
            justify="start")
],
                                  fluid=True),
                    color="dark",
                    dark=True,
                    className="custom-navbar",
                    style={"padding": "0.5rem 1rem"})

app.layout = html.Div([
    navbar,
    dcc.Location(id='url-dropdown', refresh=True), dash.page_container
],
                      className="app-body")


@app.callback(Output('player-dropdown', 'options'),
              Input('team-dropdown', 'value'))
def update_player_dropdown(selected_team):
    if selected_team:
        filtered = lineups[lineups['team'] ==
                           selected_team]['player_name'].dropna().unique()
        return [{'label': name, 'value': name} for name in sorted(filtered)]
    return [{'label': name, 'value': name} for name in players]


@app.callback(
    Output('url-dropdown', 'pathname'),
    [Input('team-dropdown', 'value'),
     Input('player-dropdown', 'value')])
def dropdown_navigation(team_value, player_value):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id == 'team-dropdown' and team_value:
        team_id = internal_team_id().get(team_value)
        if team_id:
            return f"/team/{team_id}"

    if trigger_id == 'player-dropdown' and player_value:
        filtered = lineups[lineups['player_name'] == player_value]
        if not filtered.empty:
            player_id = filtered.iloc[0]['player_id']
            return f"/player/{player_id}"


if __name__ == "__main__":
    app.run(debug=True)
