# # pages/wifi_ui_2.py
# import dash
# from dash import html, dcc, Input, Output, State, callback, ctx
# import dash_bootstrap_components as dbc
# import threading
# import serial
# import time
# import os
# import json
# import struct
# import grpc
# from concurrent import futures

# # master_ui.py의 설정들
# FRAME_HEADER1 = 0xAA
# FRAME_HEADER2 = 0xBB
# NUM_JOINTS = 6
# ENC_DATA_SIZE = NUM_JOINTS * 2 * 4  # 48 bytes
# FRAME_SIZE = 2 + 1 + ENC_DATA_SIZE + 2  # 53 bytes

# SAVE_DIR = r"C:\Users\wntlr\Desktop\jungyoonho\0708_jungyoonho_master_ui (1)\0707\0707\UI_project\UI_test\log"
# if not os.path.exists(SAVE_DIR):
#     try:
#         os.makedirs(SAVE_DIR, exist_ok=True)
#     except:
#         SAVE_DIR = "./log"
#         os.makedirs(SAVE_DIR, exist_ok=True)

# # 전역 변수들
# shared_ser = None
# BAUDRATE = 4_000_000

# switch_state = {
#     'R_toggle': '1', 'R_push_1': '1', 'R_push_2': '1',
#     'L_toggle': '1', 'L_push_1': '1', 'L_push_2': '1'
# }
# prev_switch_state = {
#     'R_toggle': '1', 'R_push_1': '1', 'R_push_2': '1',
#     'L_toggle': '1', 'L_push_1': '1', 'L_push_2': '1'
# }
# latest_enc_R = [0] * NUM_JOINTS
# latest_enc_L = [0] * NUM_JOINTS
# recorded_encoders = []
# recording_active = False
# last_frame_time = 0
# frame_intervals = []
# latest_param = []
# new_grpc_data = False
# lock = threading.Lock()

# # Wi-Fi 연결 성공 화면
# wifi_success_layout = dbc.Container([
#     html.Div([
#         html.H2("✅ Wi-Fi 연결 완료!", 
#                 style={'textAlign': 'center', 'color': '#28a745', 'marginTop': '100px'}),
#         html.P("마스터 디바이스 제어 화면으로 자동 이동합니다...", 
#                style={'textAlign': 'center', 'fontSize': '18px', 'marginTop': '20px'}),
        
#         # 카운트다운 표시
#         html.Div([
#             html.Span("자동 이동까지: "),
#             html.Span(id="wifi-countdown-display", children="5", 
#                      style={'fontWeight': 'bold', 'fontSize': '24px', 'color': '#007bff'}),
#             html.Span("초")
#         ], style={'textAlign': 'center', 'marginTop': '30px', 'fontSize': '16px'}),
        
#         # 수동 이동 버튼
#         html.Div([
#             dbc.Button("지금 바로 이동", id="wifi-manual-redirect-btn", color="primary", 
#                       style={'marginTop': '40px'})
#         ], style={'textAlign': 'center'}),
        
#         # Wi-Fi 정보 표시
#         html.Div(id="wifi-info-display", style={'textAlign': 'center', 'marginTop': '30px'}),
#     ]),
    
#     # 자동 전환을 위한 타이머 (1초마다 업데이트)
#     dcc.Interval(id="wifi-redirect-interval", interval=1000, n_intervals=0, max_intervals=6),
#     dcc.Store(id="wifi-page-state", data={"current_page": "wifi_success"}),
    
#     # JavaScript로 확실한 자동 전환 보장
#     html.Script("""
#     setTimeout(function() {
#         window.location.pathname = '/wifi-ui';
#         setTimeout(function() {
#             // 페이지 새로고침으로 메인 화면 강제 로드
#             window.location.reload();
#         }, 100);
#     }, 5000);
#     """)
# ], fluid=True)

# # 메인 마스터 디바이스 제어 화면
# main_control_layout = html.Div([
#     # 헤더
#     html.Div([
#         html.Img(src="/assets/Neuro_Meka.png", style={'height': '60px'}),
#         html.H2("Neuro Meka Master device (Wi-Fi Connected)",
#                 style={'color': '#7c8bc7', 'fontWeight': 'bold', 'marginLeft': '20px'})
#     ], style={'display': 'flex', 'alignItems': 'center',
#               'borderBottom': '2px solid #ccc', 'paddingBottom': '10px'}),

#     # Encoder List
#     dcc.Store(id="saved-entries", data=[]),
#     dbc.Card([
#         dbc.CardHeader(html.H5("Encoder List", className="mb-0")),
#         dbc.CardBody([
#             # 하드웨어 버튼 상태 표시
#             html.Div([
#                 html.Span("🎮 Hardware Controls: ", style={'fontWeight': 'bold'}),
#                 html.Span("R_push_1: ", style={'fontSize': '0.9em'}),
#                 html.Span(id="r-push1-status", children="1", style={'fontWeight': 'bold', 'color': 'blue'}),
#                 html.Span(" | L_push_1: ", style={'fontSize': '0.9em', 'marginLeft': '10px'}),
#                 html.Span(id="l-push1-status", children="1", style={'fontWeight': 'bold', 'color': 'blue'}),
#                 html.Span(" | L_push_2: ", style={'fontSize': '0.9em', 'marginLeft': '10px'}),
#                 html.Span(id="l-push2-status", children="1", style={'fontWeight': 'bold', 'color': 'blue'}),
#             ], style={'marginBottom': '10px', 'padding': '5px', 'backgroundColor': '#f8f9fa', 'borderRadius': '3px'}),
            
#             # 버튼들
#             dbc.Button("Save", id="save-btn", color="primary", className="me-2"),
#             dbc.Button("Clear", id="clear-btn", color="danger", className="me-2"),
#             dbc.Button("Save As", id="save-as-btn", color="secondary", className="me-2"),
#             dbc.Button("Import Recorded", id="import-recorded-btn", color="success", className="me-2"),
#             dbc.Button("Clear Recorded", id="clear-recorded-btn", color="warning"),
            
#             html.Div(id="save-as-status", style={'marginTop': '10px'}),
#             html.Div(id="import-status", style={'marginTop': '5px'}),
#             html.Hr(),
            
#             # 통신 속도 및 녹화 상태 표시
#             html.Div([
#                 html.Span("📊 Communication: ", style={'fontWeight': 'bold'}),
#                 html.Span(id="comm-fps", children="0 FPS", style={'color': 'green', 'fontWeight': 'bold'}),
#                 html.Span(" | Interval: "),
#                 html.Span(id="comm-interval", children="0ms", style={'color': 'blue'}),
#                 html.Span(" | Recording: "),
#                 html.Span(id="recording-status", children="STOPPED", style={'color': 'red', 'fontWeight': 'bold'}),
#             ], style={'marginBottom': '10px', 'fontSize': '0.9em', 'color': '#666'}),
            
#             html.Div(id="encoder-list-display", style={'height': '200px', 'overflowY': 'auto'})
#         ])
#     ], className="mt-4"),

#     # 실시간 기록된 엔코더 로그
#     dbc.Card([
#         dbc.CardHeader(html.H5("Live Encoder Log", className="mb-0")),
#         dbc.CardBody(
#             html.Div(id="recorded-list-display",
#                     style={'height': '200px', 'overflowY': 'auto',
#                             'fontFamily':'monospace', 'fontSize':'0.8em'})
#         )
#     ], className="mt-4"),

#     dbc.Row([
#         dbc.Col(
#             dbc.Card([
#                 dbc.CardHeader("왼팔 상태"),
#                 dbc.CardBody(
#                     html.Div([
#                         html.Div([
#                             html.Span(
#                                 id="led-left-pos",
#                                 style={
#                                     'display':'inline-block','width':'10px','height':'10px',
#                                     'borderRadius':'50%','backgroundColor':'#888'
#                                 },
#                                 className="me-2"
#                             ),
#                             html.Span("Position Control", id="pos-left", className="control-inactive")
#                         ], className="d-flex align-items-center mb-2"),

#                         html.Div([
#                             html.Span(
#                                 id="led-left-grav",
#                                 style={
#                                     'display':'inline-block','width':'10px','height':'10px',
#                                     'borderRadius':'50%','backgroundColor':'#888'
#                                 },
#                                 className="me-2"
#                             ),
#                             html.Span("Gravity Control", id="grav-left", className="control-inactive")
#                         ], className="d-flex align-items-center")
#                     ], className="d-flex flex-column")
#                 )
#             ], className="h-100"),
#             xs=12, md=6
#         ),

#         dbc.Col(
#             dbc.Card([
#                 dbc.CardHeader("오른팔 상태"),
#                 dbc.CardBody(
#                     html.Div([
#                         html.Div([
#                             html.Span(
#                                 id="led-right-pos",
#                                 style={
#                                     'display':'inline-block','width':'10px','height':'10px',
#                                     'borderRadius':'50%','backgroundColor':'#888'
#                                 },
#                                 className="me-2"
#                             ),
#                             html.Span("Position Control", id="pos-right", className="control-inactive")
#                         ], className="d-flex align-items-center mb-2"),

#                         html.Div([
#                             html.Span(
#                                 id="led-right-grav",
#                                 style={
#                                     'display':'inline-block','width':'10px','height':'10px',
#                                     'borderRadius':'50%','backgroundColor':'#888'
#                                 },
#                                 className="me-2"
#                             ),
#                             html.Span("Gravity Control", id="grav-right", className="control-inactive")
#                         ], className="d-flex align-items-center")
#                     ], className="d-flex flex-column")
#                 )
#             ], className="h-100"),
#             xs=12, md=6
#         ),
#     ], className="g-3 mt-3"),

#     dbc.Row([
#         dbc.Col(
#             dbc.Card([
#                 dbc.CardHeader("Home Control"),
#                 dbc.CardBody(
#                     html.Div([
#                         dbc.Button("Go to Home", id="go-home-btn", color="info", className="me-3"),
#                         html.Div(id="go-home-status")
#                     ], className="d-flex align-items-center")
#                 )
#             ], className="h-100"),
#             xs=12, md=6
#         ),
#         dbc.Col(
#             dbc.Card([
#                 dbc.CardHeader("Master Device Pairing (Wi-Fi)"),
#                 dbc.CardBody(
#                     html.Div([
#                         html.Span(
#                             id="pairing-indicator",
#                             style={
#                                 'display':'inline-block','width':'12px','height':'12px',
#                                 'borderRadius':'50%','backgroundColor':'#28a745'  # Wi-Fi 연결 시 초록색
#                             },
#                             className="me-2"
#                         ),
#                         dbc.Button("Connected", id="pairing-btn", color="success", disabled=True),
#                         html.Div(
#                             id="grpc-enc-display",
#                             className="ms-4",
#                             style={'fontFamily':'monospace','whiteSpace':'pre'}
#                         )
#                     ], className="d-flex align-items-center")
#                 )
#             ], className="h-100"),
#             xs=12, md=6
#         ),
#     ], className="g-3 mt-3"),

#     # Live gRPC Encoder List
#     dcc.Store(id="grpc-entries", data=[]),
#     dbc.Card([
#         dbc.CardHeader(html.H5("Live gRPC Encoder List")),
#         dbc.CardBody([
#             html.Div(
#                 id="grpc-list-display",
#                 style={
#                     'height':'150px',
#                     'overflowY':'auto',
#                     'fontFamily':'monospace',
#                     'whiteSpace':'pre-wrap'
#                 }
#             )
#         ])
#     ], className="mt-4"),

#     # 주기적 업데이트 트리거
#     dcc.Interval(id="interval", interval=50, n_intervals=0),  # 20Hz 업데이트
    
#     html.Br(),
#     dcc.Link("← Wi-Fi 메뉴로 돌아가기", href="/wifi", className="btn btn-link")
# ], style={'padding': '20px'})

# # 메인 레이아웃 - 조건부 표시 (초기에는 Wi-Fi 성공 화면)
# layout = html.Div([
#     html.Div(id="wifi-main-content", children=wifi_success_layout)
# ])

# # ⚠️ 콜백들은 app.py에서 처리하므로 여기서는 제거
# # 필요한 경우 app.py에서 다음 콜백들을 추가:
# # - wifi-countdown-display 업데이트
# # - wifi-manual-redirect-btn 클릭 처리  
# # - wifi-redirect-interval로 자동 전환
# # - wifi-main-content 업데이트

# # CSS 스타일
# def get_css_styles():
#     return """
#     .led-on {
#         color: #28a745 !important;
#     }
#     .led-off {
#         color: #6c757d !important;
#     }
#     .led-pos-on {
#         color: #007bff !important;
#     }
#     .control-active {
#         color: #28a745;
#         font-weight: bold;
#     }
#     .control-inactive {
#         color: #6c757d;
#     }
#     """