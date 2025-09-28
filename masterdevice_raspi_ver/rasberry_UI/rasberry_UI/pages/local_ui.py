# pages/local_ui.py
import dash
from dash import html
import dash_bootstrap_components as dbc
from dash import html, dcc
import dash_bootstrap_components as dbc



layout = dbc.Container([
    html.H3("✅ Local 연결 완료!", className="mt-4"),
    html.P("로컬 연결이 성공적으로 완료되었습니다."),
    html.Br(),
    dcc.Link("← Local 메뉴로 돌아가기", href="/local", className="btn btn-link")
], fluid=True)
