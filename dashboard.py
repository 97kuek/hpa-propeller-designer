import dash
from dash import dcc, html, Input, Output
import pandas as pd
import plotly.express as px
import os

app = dash.Dash(__name__, title="Propeller Design Dashboard")

import glob

# Find latest output dir (for simplicity, just take the first one or a default)
out_dirs = glob.glob("output/*/")
prop_dir = out_dirs[0] if out_dirs else ""

STRUCT_FILE = os.path.join(prop_dir, "structural_properties.csv")
HTML_FILE = os.path.join(prop_dir, "propeller_3d.html")

def load_data():
    if os.path.exists(STRUCT_FILE):
        return pd.read_csv(STRUCT_FILE)
    return pd.DataFrame()

app.layout = html.Div([
    html.H1("Propeller Design & Airfoil Metrics Dashboard", style={'textAlign': 'center'}),
    
    html.Div([
        html.H3("Structural Properties over Radius"),
        dcc.Dropdown(
            id='metric-dropdown',
            options=[
                {'label': 'Area', 'value': 'Area'},
                {'label': 'Ixx (Bending)', 'value': 'Ixx'},
                {'label': 'Iyy (Bending)', 'value': 'Iyy'},
                {'label': 'X Centroid', 'value': 'X_c'},
                {'label': 'Y Centroid', 'value': 'Y_c'}
            ],
            value='Area',
            clearable=False,
            style={'width': '50%'}
        ),
        dcc.Graph(id='metric-graph')
    ], style={'padding': '20px'}),
    
    html.Div([
        html.H3("Interactive 3D Geometry"),
        html.Iframe(srcDoc=open(HTML_FILE, "r", encoding="utf-8").read() if os.path.exists(HTML_FILE) else f"<h3>No 3D Model Found in {HTML_FILE}. Run main workflow first.</h3>", 
                    width="100%", height="600px", style={"border": "none"})
    ], style={'padding': '20px'})
])

@app.callback(
    Output('metric-graph', 'figure'),
    [Input('metric-dropdown', 'value')]
)
def update_graph(selected_metric):
    df = load_data()
    if df.empty:
        return px.line(title="No data found. Run the main workflow to generate structural_properties.csv.")
        
    fig = px.line(df, x='r/R', y=selected_metric, markers=True, 
                  title=f'{selected_metric} Distribution along Blade Radius')
    fig.update_layout(xaxis_title="r/R (Non-dimensional Radius)")
    return fig

if __name__ == '__main__':
    print("Starting Interactive Dashboard at http://127.0.0.1:8050/")
    app.run(debug=True)
