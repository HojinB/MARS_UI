from dash import html, dcc
import dash_bootstrap_components as dbc

layout = dbc.Container([
    html.H3("🌐 Local 연결", className="mt-4"),
    html.P("Local 모드 기능은 여기 구현"),
    dcc.Link("← 메인으로 돌아가기", href="/", className="btn btn-link")
], fluid=True)