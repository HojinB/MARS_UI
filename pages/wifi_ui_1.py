# pages/wifi_ui_1.py
import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

# 간단한 Wi-Fi 성공 화면
wifi_success_screen = dbc.Container([
    html.Div([
        html.H2("✅ Wi-Fi 연결 완료!", 
                style={'textAlign': 'center', 'color': '#28a745', 'marginTop': '100px'}),
        html.P("마스터 디바이스 제어 화면으로 자동 이동합니다...", 
               style={'textAlign': 'center', 'fontSize': '18px', 'marginTop': '20px'}),
        
        # 카운트다운 표시
        html.Div([
            html.Span("자동 이동까지: "),
            html.Span(id="countdown-number", children="5", 
                     style={'fontWeight': 'bold', 'fontSize': '24px', 'color': '#007bff'}),
            html.Span("초")
        ], style={'textAlign': 'center', 'marginTop': '30px', 'fontSize': '16px'}),
        
        # Wi-Fi 연결 정보
        html.Div(id="show-wifi-info", style={'textAlign': 'center', 'marginTop': '20px', 'fontWeight': 'bold'}),
        
        # 수동 이동 버튼
        html.Div([
            dbc.Button("지금 바로 이동", id="manual-go-btn", color="primary", 
                      style={'marginTop': '20px', 'marginRight': '10px'}),
            html.Br(),
            dcc.Link("← Wi-Fi 메뉴로 돌아가기", href="/wifi", 
                    className="btn btn-link", style={'marginTop': '10px'})
        ], style={'textAlign': 'center'}),
    ])
], fluid=True)

# 메인 제어 화면
main_control_screen = html.Div([
    # 헤더
    html.Div([
        html.Img(src="/assets/Neuro_Meka.png", style={'height': '60px'}),
        html.H2("Neuro Meka Master device (Wi-Fi Connected)",
                style={'color': '#7c8bc7', 'fontWeight': 'bold', 'marginLeft': '20px'})
    ], style={'display': 'flex', 'alignItems': 'center',
              'borderBottom': '2px solid #ccc', 'paddingBottom': '10px'}),

    # Encoder List
    dcc.Store(id="saved-entries", data=[]),
    dbc.Card([
        dbc.CardHeader(html.H5("Encoder List", className="mb-0")),
        dbc.CardBody([
            # 하드웨어 버튼 상태 표시
            html.Div([
                html.Span("🎮 Hardware Controls: ", style={'fontWeight': 'bold'}),
                html.Span("R_push_1: ", style={'fontSize': '0.9em'}),
                html.Span(id="r-push1-status", children="1", style={'fontWeight': 'bold', 'color': 'blue'}),
                html.Span(" | L_push_1: ", style={'fontSize': '0.9em', 'marginLeft': '10px'}),
                html.Span(id="l-push1-status", children="1", style={'fontWeight': 'bold', 'color': 'blue'}),
                html.Span(" | L_push_2: ", style={'fontSize': '0.9em', 'marginLeft': '10px'}),
                html.Span(id="l-push2-status", children="1", style={'fontWeight': 'bold', 'color': 'blue'}),
            ], style={'marginBottom': '10px', 'padding': '5px', 'backgroundColor': '#f8f9fa', 'borderRadius': '3px'}),
            
            # 버튼들
            dbc.Button("Save", id="save-btn", color="primary", className="me-2"),
            dbc.Button("Clear", id="clear-btn", color="danger", className="me-2"),
            dbc.Button("Save As", id="save-as-btn", color="secondary", className="me-2"),
            dbc.Button("Import Recorded", id="import-recorded-btn", color="success", className="me-2"),
            dbc.Button("Clear Recorded", id="clear-recorded-btn", color="warning"),
            
            html.Div(id="save-as-status", style={'marginTop': '10px'}),
            html.Div(id="import-status", style={'marginTop': '5px'}),
            html.Hr(),
            
            # 통신 속도 및 녹화 상태 표시
            html.Div([
                html.Span("📊 Communication: ", style={'fontWeight': 'bold'}),
                html.Span(id="comm-fps", children="0 FPS", style={'color': 'green', 'fontWeight': 'bold'}),
                html.Span(" | Interval: "),
                html.Span(id="comm-interval", children="0ms", style={'color': 'blue'}),
                html.Span(" | Recording: "),
                html.Span(id="recording-status", children="STOPPED", style={'color': 'red', 'fontWeight': 'bold'}),
            ], style={'marginBottom': '10px', 'fontSize': '0.9em', 'color': '#666'}),
            
            html.Div(id="encoder-list-display", style={'height': '200px', 'overflowY': 'auto'})
        ])
    ], className="mt-4"),

    # 실시간 기록된 엔코더 로그
    dbc.Card([
        dbc.CardHeader(html.H5("Live Encoder Log", className="mb-0")),
        dbc.CardBody(
            html.Div(id="recorded-list-display",
                    style={'height': '200px', 'overflowY': 'auto',
                            'fontFamily':'monospace', 'fontSize':'0.8em'})
        )
    ], className="mt-4"),

    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader("왼팔 상태"),
                dbc.CardBody(
                    html.Div([
                        html.Div([
                            html.Span(
                                id="led-left-pos",
                                style={
                                    'display':'inline-block','width':'10px','height':'10px',
                                    'borderRadius':'50%','backgroundColor':'#888'
                                },
                                className="me-2"
                            ),
                            html.Span("Position Control", id="pos-left", className="control-inactive")
                        ], className="d-flex align-items-center mb-2"),

                        html.Div([
                            html.Span(
                                id="led-left-grav",
                                style={
                                    'display':'inline-block','width':'10px','height':'10px',
                                    'borderRadius':'50%','backgroundColor':'#888'
                                },
                                className="me-2"
                            ),
                            html.Span("Gravity Control", id="grav-left", className="control-inactive")
                        ], className="d-flex align-items-center")
                    ], className="d-flex flex-column")
                )
            ], className="h-100"),
            xs=12, md=6
        ),

        dbc.Col(
            dbc.Card([
                dbc.CardHeader("오른팔 상태"),
                dbc.CardBody(
                    html.Div([
                        html.Div([
                            html.Span(
                                id="led-right-pos",
                                style={
                                    'display':'inline-block','width':'10px','height':'10px',
                                    'borderRadius':'50%','backgroundColor':'#888'
                                },
                                className="me-2"
                            ),
                            html.Span("Position Control", id="pos-right", className="control-inactive")
                        ], className="d-flex align-items-center mb-2"),

                        html.Div([
                            html.Span(
                                id="led-right-grav",
                                style={
                                    'display':'inline-block','width':'10px','height':'10px',
                                    'borderRadius':'50%','backgroundColor':'#888'
                                },
                                className="me-2"
                            ),
                            html.Span("Gravity Control", id="grav-right", className="control-inactive")
                        ], className="d-flex align-items-center")
                    ], className="d-flex flex-column")
                )
            ], className="h-100"),
            xs=12, md=6
        ),
    ], className="g-3 mt-3"),

    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader("Home Control"),
                dbc.CardBody(
                    html.Div([
                        dbc.Button("Go to Home", id="go-home-btn", color="info", className="me-3"),
                        html.Div(id="go-home-status")
                    ], className="d-flex align-items-center")
                )
            ], className="h-100"),
            xs=12, md=6
        ),
        dbc.Col(
            dbc.Card([
                dbc.CardHeader("Teleop Control"),
                dbc.CardBody(
                    html.Div([
                        dbc.Button("Teleop Start", id="teleop-start-btn", color="success", className="me-2"),
                        dbc.Button("Teleop Stop", id="teleop-stop-btn", color="danger", className="me-3"),
                        html.Div(id="teleop-status")
                    ], className="d-flex align-items-center")
                )
            ], className="h-100"),
            xs=12, md=6
        ),
    ], className="g-3 mt-3"),

    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader("Master Device Pairing (Wi-Fi)"),
                dbc.CardBody(
                    html.Div([
                        html.Span(
                            id="pairing-indicator",
                            style={
                                'display':'inline-block','width':'12px','height':'12px',
                                'borderRadius':'50%','backgroundColor':'#28a745'
                            },
                            className="me-2"
                        ),
                        dbc.Button("Connected", id="pairing-btn", color="success", disabled=True),
                        html.Div(
                            id="grpc-enc-display",
                            className="ms-4",
                            style={'fontFamily':'monospace','whiteSpace':'pre'}
                        )
                    ], className="d-flex align-items-center")
                )
            ], className="h-100"),
            xs=12, md=12
        ),
    ], className="g-3 mt-3"),

    # Live gRPC Encoder List
    dcc.Store(id="grpc-entries", data=[]),
    dbc.Card([
        dbc.CardHeader(html.H5("Live gRPC Encoder List")),
        dbc.CardBody([
            html.Div(
                id="grpc-list-display",
                style={
                    'height':'150px',
                    'overflowY':'auto',
                    'fontFamily':'monospace',
                    'whiteSpace':'pre-wrap'
                }
            )
        ])
    ], className="mt-4"),

    # 주기적 업데이트 트리거
    dcc.Interval(id="interval", interval=50, n_intervals=0),
    
    html.Br(),
    dcc.Link("← Wi-Fi 메뉴로 돌아가기", href="/wifi", className="btn btn-link")
], style={'padding': '20px'})

# 메인 레이아웃
layout = html.Div([
    # 페이지 상태 저장
    dcc.Store(id="page-state", data={"current_view": "wifi_success"}),
    
    # 메인 콘텐츠
    html.Div(id="main-content", children=wifi_success_screen),
    
    # 타이머 (1초마다 실행, 최대 6초)
    dcc.Interval(id="auto-timer", interval=1000, n_intervals=0, max_intervals=6)
])