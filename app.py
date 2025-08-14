from dash import Dash, dcc, html, Input, Output, State, dash
import dash_bootstrap_components as dbc
import serial.tools.list_ports
import serial
import sys
import os

# 페이지 레이아웃 가져오기
from pages import wifi_ui_1 as wifi_ui
from pages import usb, usb_ui, local, local_ui, wifi

# UI_TEST를 경로에 추가
sys.path.append(os.path.dirname(__file__))

from GRPC.stubs import client

# ── 1) 앱 초기화 ─────────────────────────────────────
app = Dash(__name__,
           external_stylesheets=[dbc.themes.BOOTSTRAP],
           suppress_callback_exceptions=True)

# ── 2) 공통 헤더 컴포넌트 ─────────────────────────────
header = html.Div(
    style={
        "backgroundColor": "#5A6D8C",
        "padding": "10px 20px",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "space-between",
        "boxShadow": "0 2px 10px rgba(0,0,0,0.1)"
    },
    children=[
        html.Div([
            html.H1("Master Device",
                    style={
                        "margin": "0",
                        "color": "white",
                        "fontSize": "2.5rem",
                        "fontWeight": "bold",
                        "textShadow": "2px 2px 4px rgba(0,0,0,0.3)"
                    }),
            html.Small("smart teach device",
                       style={"color": "#E8F4FD", "fontSize": "1rem"}),
        ]),
        html.Img(src="/assets/Neuro_Meka.png", style={"height": "50px"}),
    ],
)

# ── 3) dcc.Location + dcc.Store ────────────────────────
app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    dcc.Store(id="usb-port-store"),     
    dcc.Store(id="wifi-conn-store"), 
    dcc.Store(id="teleop-state", data={"running": False}),
    html.Div(id="page-content")
])

# ── 4) 라우터 콜백 ────────────────────────────────────
@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname")
)
def display_page(pathname):
    print(f"[DEBUG] Current pathname: {pathname}")
    if pathname == "/usb":
        return usb.layout
    elif pathname == "/usb-ui":
        return usb_ui.layout
    elif pathname == "/wifi":
        return wifi.layout
    elif pathname == "/wifi-ui":
        print("[DEBUG] Loading wifi-ui page")
        return wifi_ui.layout
    elif pathname == "/local":
        return local.layout
    elif pathname == "/local-ui":
        return local_ui.layout
    else:
        # 🎨 개선된 메인 메뉴
        return html.Div([
            header,
            
            # 메인 컨테이너
            dbc.Container([
                # 타이틀 섹션
                html.Div([
                    html.H1("Connection Mode 선택",
                            style={
                                'textAlign': 'center',
                                'marginTop': '40px',
                                'marginBottom': '20px',
                                'color': '#2C3E50',
                                'fontWeight': 'bold',
                                'fontSize': '2.5rem'
                            }),
                    html.P("원하는 연결 방식을 선택해주세요",
                           style={
                               'textAlign': 'center',
                               'color': '#7F8C8D',
                               'fontSize': '1.2rem',
                               'marginBottom': '50px'
                           })
                ]),
                
                # 연결 모드 카드들
                dbc.Row([
                    # Local Connect
                    dbc.Col([
                        html.Div([
                            dcc.Link([
                                html.Div([
                                    # 아이콘
                                    html.Div("🖥️", 
                                            style={
                                                'fontSize': '4rem',
                                                'marginBottom': '20px',
                                                'textAlign': 'center'
                                            }),
                                    # 제목
                                    html.H3("Local Connect",
                                            style={
                                                'color': 'white',
                                                'fontWeight': 'bold',
                                                'marginBottom': '15px',
                                                'textAlign': 'center'
                                            }),
                                    # 설명
                                    html.P("로컬 네트워크로 직접 연결",
                                           style={
                                               'color': 'rgba(255,255,255,0.9)',
                                               'textAlign': 'center',
                                               'fontSize': '1rem',
                                               'margin': '0'
                                           })
                                ])
                            ], href="/local", style={'textDecoration': 'none'})
                        ], 
                        style={
                            'background': 'linear-gradient(135deg, #27AE60, #2ECC71)',
                            'borderRadius': '20px',
                            'padding': '40px 20px',
                            'textAlign': 'center',
                            'boxShadow': '0 10px 30px rgba(39, 174, 96, 0.3)',
                            'transition': 'all 0.3s ease',
                            'cursor': 'pointer',
                            'height': '280px',
                            'display': 'flex',
                            'alignItems': 'center',
                            'justifyContent': 'center'
                        },
                        className="connection-card",
                        id="local-card")
                    ], width=4),
                    
                    # Wi-Fi Connect
                    dbc.Col([
                        html.Div([
                            dcc.Link([
                                html.Div([
                                    # 아이콘
                                    html.Div("📶", 
                                            style={
                                                'fontSize': '4rem',
                                                'marginBottom': '20px',
                                                'textAlign': 'center'
                                            }),
                                    # 제목
                                    html.H3("Wi-Fi Connect",
                                            style={
                                                'color': 'white',
                                                'fontWeight': 'bold',
                                                'marginBottom': '15px',
                                                'textAlign': 'center'
                                            }),
                                    # 설명
                                    html.P("무선 네트워크를 통한 연결",
                                           style={
                                               'color': 'rgba(255,255,255,0.9)',
                                               'textAlign': 'center',
                                               'fontSize': '1rem',
                                               'margin': '0'
                                           })
                                ])
                            ], href="/wifi", style={'textDecoration': 'none'})
                        ], 
                        style={
                            'background': 'linear-gradient(135deg, #3498DB, #5DADE2)',
                            'borderRadius': '20px',
                            'padding': '40px 20px',
                            'textAlign': 'center',
                            'boxShadow': '0 10px 30px rgba(52, 152, 219, 0.3)',
                            'transition': 'all 0.3s ease',
                            'cursor': 'pointer',
                            'height': '280px',
                            'display': 'flex',
                            'alignItems': 'center',
                            'justifyContent': 'center'
                        },
                        className="connection-card",
                        id="wifi-card")
                    ], width=4),
                    
                    # USB Connect
                    dbc.Col([
                        html.Div([
                            dcc.Link([
                                html.Div([
                                    # 아이콘
                                    html.Div("🔌", 
                                            style={
                                                'fontSize': '4rem',
                                                'marginBottom': '20px',
                                                'textAlign': 'center'
                                            }),
                                    # 제목
                                    html.H3("USB Connect",
                                            style={
                                                'color': 'white',
                                                'fontWeight': 'bold',
                                                'marginBottom': '15px',
                                                'textAlign': 'center'
                                            }),
                                    # 설명
                                    html.P("USB 시리얼 포트로 직접 연결",
                                           style={
                                               'color': 'rgba(255,255,255,0.9)',
                                               'textAlign': 'center',
                                               'fontSize': '1rem',
                                               'margin': '0'
                                           })
                                ])
                            ], href="/usb", style={'textDecoration': 'none'})
                        ], 
                        style={
                            'background': 'linear-gradient(135deg, #E67E22, #F39C12)',
                            'borderRadius': '20px',
                            'padding': '40px 20px',
                            'textAlign': 'center',
                            'boxShadow': '0 10px 30px rgba(230, 126, 34, 0.3)',
                            'transition': 'all 0.3s ease',
                            'cursor': 'pointer',
                            'height': '280px',
                            'display': 'flex',
                            'alignItems': 'center',
                            'justifyContent': 'center'
                        },
                        className="connection-card",
                        id="usb-card")
                    ], width=4),
                ], className="g-4", style={'marginBottom': '50px'}),
                
                # 하단 정보
                html.Div([
                    html.P("💡 각 연결 모드를 클릭하여 마스터 디바이스에 연결하세요",
                           style={
                               'textAlign': 'center',
                               'color': '#95A5A6',
                               'fontSize': '1rem',
                               'marginTop': '30px'
                           })
                ])
                
            ], fluid=True, style={'minHeight': '80vh'}),
        ])

# ── 5) 🔄 Wi-Fi UI 자동 전환 콜백 (가장 중요!) ─────────────
@app.callback(
    [Output("main-content", "children"),
     Output("countdown-number", "children"),
     Output("page-state", "data")],
    [Input("auto-timer", "n_intervals"),
     Input("manual-go-btn", "n_clicks")],
    State("page-state", "data"),
    prevent_initial_call=False
)
def handle_wifi_auto_redirect(timer_count, manual_click, current_state):
    from pages.wifi_ui_1 import wifi_success_screen, main_control_screen
    
    print(f"[DEBUG] Auto redirect - timer: {timer_count}, manual: {manual_click}, state: {current_state}")
    
    # 현재 상태 확인
    if current_state is None:
        current_state = {"current_view": "wifi_success"}
    
    current_view = current_state.get("current_view", "wifi_success")
    
    # 이미 메인 화면이면 그대로 유지
    if current_view == "main_control":
        return main_control_screen, "0", {"current_view": "main_control"}
    
    # 수동 버튼 클릭 또는 5초 경과 시 메인 화면으로 전환
    if manual_click or (timer_count is not None and timer_count >= 5):
        print("[DEBUG] ✅ Switching to main control screen")
        return main_control_screen, "0", {"current_view": "main_control"}
    
    # 카운트다운 계산 및 표시
    countdown = max(0, 5 - (timer_count or 0))
    print(f"[DEBUG] ⏰ Countdown: {countdown}")
    
    return wifi_success_screen, str(countdown), {"current_view": "wifi_success"}

# ── 6) USB 관련 콜백 ─────────────────────────────────
@app.callback(
    Output("url", "pathname", allow_duplicate=True),
    Output("usb-port-store", "data"),
    Input("btn-usb-connect", "n_clicks"),
    State("usb-port-dropdown", "value"),
    prevent_initial_call=True
)
def connect_usb(n_clicks, port):
    if not port:
        return dash.no_update, dash.no_update
    try:
        ser = serial.Serial(port, baudrate=4_000_000, timeout=0.1)
        ser.close()
        return "/usb-ui", port
    except Exception as e:
        return dash.no_update, dash.no_update

# ── 7) USB_UI 페이지: 모터 이동 콜백 ─────────────────────
@app.callback(
    Output("move-status", "children"),
    Input("btn-move", "n_clicks"),
    State("usb-port-store", "data"),
    State("motor-id", "value"),
    State("target-pos", "value"),
    prevent_initial_call=True
)
def move_motor(n, port, motor_id, pos):
    try:
        from dynamixel_sdk import PortHandler, PacketHandler
    except ImportError:
        return dbc.Alert("Dynamixel SDK가 설치되지 않았습니다.", color="warning")
    
    if not port:
        return dbc.Alert("먼저 USB 페이지에서 포트를 선택하고 연결하세요.", color="warning")
    if motor_id is None or pos is None:
        return dbc.Alert("모터 ID와 목표 위치를 입력해주세요.", color="warning")
    try:
        ph = PortHandler(port)
        ph.openPort()
        ph.setBaudRate(4_000_000)
        pk = PacketHandler(2.0)
        pk.write4ByteTxRx(ph, motor_id, 116, pos)
        ph.closePort()
        return dbc.Alert(f"모터 {motor_id} → 위치 {pos} 이동 명령 전송 완료", color="success")
    except Exception as e:
        return dbc.Alert(f"이동 실패: {e}", color="danger")

# ── 8) Wi-Fi 연결 콜백 ─────────────────────────────────
@app.callback(
    [Output("url", "pathname", allow_duplicate=True),
     Output("wifi-conn-store", "data"),
     Output("show-wifi-info", "children")],
    Input("btn-wifi-connect", "n_clicks"),
    [State("master-ip", "value"),
     State("master-port", "value")],
    prevent_initial_call=True
)
def handle_wifi_connection(n_clicks, ip, port):
    print(f"[DEBUG] WiFi connect called with IP: {ip}, Port: {port}")
    
    if not ip or not port:
        return dash.no_update, dash.no_update, dbc.Alert("Master IP와 Port를 모두 입력하세요.", color="danger")

    try:
        command = "CONNECT_FROM_UI"
        response = client.send_connect_command(ip, port, command)
        
        print(f"[DEBUG] Raw response: '{response}'")
        cleaned_response = response.strip().lower() if response else ""
        print(f"[DEBUG] Cleaned response: '{cleaned_response}'")
        
        if cleaned_response == "success":
            print("[DEBUG] Success condition met, redirecting to /wifi-ui")
            wifi_info = html.Div([
                html.P(f"🌐 Master IP: {ip}"),
                html.P(f"🔌 Port: {port}"),
                html.P("✅ gRPC 연결 상태: 성공")
            ])
            return "/wifi-ui", {"status": "success", "ip": ip, "port": port}, wifi_info
        else:
            print(f"[DEBUG] Success condition not met. Expected 'success', got '{cleaned_response}'")
            return dash.no_update, {"status": "fail"}, dbc.Alert(f"⚠️ 응답: {response}", color="warning")
    except Exception as e:
        print(f"[DEBUG] Exception occurred: {e}")
        return dash.no_update, {"status": "fail"}, dbc.Alert(f"❌ gRPC 전송 실패: {e}", color="danger")

# ── 9) 🏠 Go to Home 버튼 콜백 ─────────────────────────
@app.callback(
    Output("go-home-status", "children"),
    Input("go-home-btn", "n_clicks"),
    State("wifi-conn-store", "data"),
    prevent_initial_call=True
)
def handle_go_home(n_clicks, wifi_data):
    print(f"[DEBUG] Go Home button clicked")
    
    if not wifi_data or not isinstance(wifi_data, dict) or wifi_data.get("status") != "success":
        return dbc.Alert("❌ Wi-Fi가 연결되지 않았습니다.", color="danger")
    
    ip = wifi_data.get("ip")
    port = wifi_data.get("port")
    
    if not ip or not port:
        return dbc.Alert("❌ 연결 정보가 없습니다.", color="danger")
    
    try:
        command = "GO_HOME"
        response = client.send_homing_command(ip, port, command)
        print(f"[DEBUG] Homing response: '{response}'")
        
        if response and "success" in response.lower():
            return dbc.Alert(f"✅ 홈 위치로 이동 완료! 응답: {response}", color="success")
        else:
            return dbc.Alert(f"⚠️ 홈 이동 응답: {response}", color="warning")
    except Exception as e:
        print(f"[DEBUG] Homing command failed: {e}")
        return dbc.Alert(f"❌ 홈 이동 실패: {e}", color="danger")


# ── 10) 🚀 Teleop Start 버튼 콜백 (자동 실행 방지) ─────────────────────────
@app.callback(
    [Output("teleop-status", "children"),
     Output("teleop-state", "data", allow_duplicate=True)],
    Input("teleop-start-btn", "n_clicks"),
    [State("wifi-conn-store", "data"),
     State("teleop-state", "data")],
    prevent_initial_call=True  # 중요: 페이지 로드 시 자동 실행 방지
)
def handle_teleop_start(n_clicks, wifi_data, teleop_state):
    # n_clicks가 None이거나 0이면 실행하지 않음
    if not n_clicks or n_clicks == 0:
        print("[DEBUG] 🚀 Teleop Start - no clicks detected, skipping")
        return dash.no_update, dash.no_update
    
    print(f"[DEBUG] 🚀 Teleop Start button clicked - n_clicks: {n_clicks}")
    
    if not wifi_data or not isinstance(wifi_data, dict) or wifi_data.get("status") != "success":
        return dbc.Alert("❌ Wi-Fi가 연결되지 않았습니다.", color="danger"), dash.no_update
    
    if teleop_state and teleop_state.get("running", False):
        return dbc.Alert("⚠️ Teleop이 이미 실행 중입니다.", color="warning"), dash.no_update
    
    ip = wifi_data.get("ip")
    port = wifi_data.get("port")
    
    if not ip or not port:
        return dbc.Alert("❌ 연결 정보가 없습니다.", color="danger"), dash.no_update
    
    try:
        print(f"[DEBUG] 🚀 Sending START command to {ip}:{port}")
        command = "START"
        response = client.send_master_teleop_command(ip, port, command)
        print(f"[DEBUG] 🚀 Teleop Start response: '{response}'")
        
        if response and ("success" in response.lower() or "ok" in response.lower()):
            return dbc.Alert(f"✅ Teleop 시작됨! 응답: {response}", color="success"), {"running": True}
        else:
            return dbc.Alert(f"⚠️ Teleop 시작 응답: {response}", color="warning"), {"running": False}
    except Exception as e:
        print(f"[DEBUG] 🚀 Teleop Start command failed: {e}")
        return dbc.Alert(f"❌ Teleop 시작 실패: {e}", color="danger"), {"running": False}

# ── 11) ⏹️ Teleop Stop 버튼 콜백 (자동 실행 방지) ─────────────────────────
@app.callback(
    [Output("teleop-status", "children", allow_duplicate=True),
     Output("teleop-state", "data", allow_duplicate=True)],
    Input("teleop-stop-btn", "n_clicks"),
    [State("wifi-conn-store", "data"),
     State("teleop-state", "data")],
    prevent_initial_call=True  # 중요: 페이지 로드 시 자동 실행 방지
)
def handle_teleop_stop(n_clicks, wifi_data, teleop_state):
    # n_clicks가 None이거나 0이면 실행하지 않음
    if not n_clicks or n_clicks == 0:
        print("[DEBUG] 🛑 Teleop Stop - no clicks detected, skipping")
        return dash.no_update, dash.no_update
    
    print(f"[DEBUG] 🛑 Teleop Stop button clicked - n_clicks: {n_clicks}")
    
    if not wifi_data or not isinstance(wifi_data, dict) or wifi_data.get("status") != "success":
        return dbc.Alert("❌ Wi-Fi가 연결되지 않았습니다.", color="danger"), dash.no_update
    
    ip = wifi_data.get("ip")
    port = wifi_data.get("port")
    
    if not ip or not port:
        return dbc.Alert("❌ 연결 정보가 없습니다.", color="danger"), dash.no_update
    
    try:
        print(f"[DEBUG] 🛑 Sending STOP command to {ip}:{port}")
        command = "STOP"
        response = client.send_master_teleop_command(ip, port, command)
        print(f"[DEBUG] 🛑 Teleop Stop response: '{response}'")
        
        if response and ("success" in response.lower() or "ok" in response.lower()):
            return dbc.Alert(f"⏹️ Teleop 중지됨! 응답: {response}", color="secondary"), {"running": False}
        else:
            return dbc.Alert(f"⚠️ Teleop 중지 응답: {response}", color="warning"), {"running": False}
    except Exception as e:
        print(f"[DEBUG] 🛑 Teleop Stop command failed: {e}")
        return dbc.Alert(f"❌ Teleop 중지 실패: {e}", color="danger"), {"running": False}

# ── 12) 서버 실행 ─────────────────────────────────────

server = app.server
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8050))
    app.run(
        host='0.0.0.0',  # 외부 접속 허용
        port=port,
        debug=False      # 프로덕션에서는 debug=False
    )