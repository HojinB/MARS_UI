# app.py - 수정된 메인 앱 (server.py 모듈 import 방식)
import dash
import os
import sys
import time
import threading
import grpc
from concurrent import futures
import signal
import atexit
from dash import html, dcc, Input, Output, State, callback, no_update
import dash_bootstrap_components as dbc

# ===============================
# 전역 설정
# ===============================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GRPC_AVAILABLE = False

def load_grpc_modules():
    """gRPC 모듈들을 동적으로 로드"""
    global GRPC_AVAILABLE
    global masterdevice_pb2_grpc, masterdevice_pb2
    
    try:
        # GRPC/stubs 디렉토리를 sys.path에 추가
        stubs_path = os.path.join(SCRIPT_DIR, 'GRPC', 'stubs')
        if stubs_path not in sys.path:
            sys.path.insert(0, stubs_path)
        
        # protobuf 모듈들 import
        import masterdevice_pb2
        import masterdevice_pb2_grpc
        
        GRPC_AVAILABLE = True
        print("[INFO] gRPC 모듈 로드 성공")
        return True
        
    except Exception as e:
        print(f"[ERROR] gRPC 모듈 로드 실패: {e}")
        GRPC_AVAILABLE = False
        return False

# gRPC 모듈 로드 시도
load_grpc_modules()

# gRPC 서버 모듈 import
GRPC_SERVER_AVAILABLE = False
try:
    from GRPC.stubs.server import create_grpc_server, PCGRPCServiceImpl
    GRPC_SERVER_AVAILABLE = True
    print("[INFO] ✅ gRPC 서버 모듈 로드 성공")
except ImportError as e:
    print(f"[ERROR] gRPC 서버 모듈 로드 실패: {e}")
    GRPC_SERVER_AVAILABLE = False

# 데이터 매니저 모듈들 import
try:
    from grpc_data_manager import real_time_data_manager
    from grpc_stream_handler import grpc_stream_handler, save_stream_manager
    print("[INFO] 데이터 관리 모듈 로드 성공")
except ImportError as e:
    print(f"[WARNING] 데이터 관리 모듈 로드 실패: {e}")
    real_time_data_manager = None
    save_stream_manager = None

# 기존 grpc_data_manager 호환성 유지
try:
    from grpc_data_manager import grpc_data_manager
    print("[INFO] 기존 grpc_data_manager 로드 성공")
except ImportError:
    # 데이터 매니저를 grpc_data_manager로 매핑
    if real_time_data_manager:
        grpc_data_manager = real_time_data_manager
        print("[INFO] real_time_data_manager를 grpc_data_manager로 매핑")
    else:
        # 더미 매니저 생성
        class DummyDataManager:
            def get_robot_state(self): return {"connected": False}
            def get_current_gain_values(self): return {"shoulder_gain": 0.6, "joint_gain": 0.7}
            def get_encoder_entries(self, limit): return []
            def get_current_encoder_data(self): return {"angles": [0.0]*14, "formatted": "No data"}
            def update_gain_values(self, s, j): pass
            def save_encoder_pose(self, angles, name=None): return name or "Dummy"
            def start_streaming(self): pass
            def stop_streaming(self): pass
            def get_streaming_data(self, limit=50): return []
            def clear_poses(self): pass
            def reset_all_data(self): pass
            def delete_recorded_data(self): pass
            def reset_gain_to_default(self): pass
        
        grpc_data_manager = DummyDataManager()
        print("[WARNING] 더미 데이터 매니저 사용")

# GRPC 클라이언트 모듈 import
if GRPC_AVAILABLE:
    try:
        stubs_path = os.path.join(SCRIPT_DIR, 'GRPC', 'stubs')
        if stubs_path not in sys.path:
            sys.path.insert(0, stubs_path)
        from GRPC.stubs import client
        print("[INFO] client 모듈 로드 성공")
    except Exception as e:
        print(f"[WARNING] client 모듈 로드 실패: {e}")

# 페이지 레이아웃 가져오기
try:
    from pages import wifi_ui_1 as wifi_ui
    from pages import wifi, local, local_ui
    print("[INFO] 페이지 모듈들 로드 성공")
except ImportError as e:
    print(f"[ERROR] 페이지 모듈 로드 실패: {e}")
    # 최소한의 더미 레이아웃
    class DummyLayout:
        layout = html.Div("페이지 로드 실패")
    wifi_ui = wifi = local = local_ui = DummyLayout()

# ===============================
# 네트워크 설정
# ===============================
LOCAL_IP = "192.168.0.4"     # PC IP 고정
WEB_SERVER_PORT = 8050       # 웹서버 포트 (Dash)
GRPC_SERVER_PORT = 50052     # gRPC 서버 포트

print(f"[INFO] PC IP: {LOCAL_IP}")
print(f"[INFO] 웹서버 포트: {WEB_SERVER_PORT}")
print(f"[INFO] gRPC 서버 포트: {GRPC_SERVER_PORT}")

# 전역 gRPC 서버 인스턴스
_grpc_server = None
_grpc_service_impl = None

# ===============================
# gRPC 서버 관리 함수들
# ===============================
def cleanup_grpc_server():
    """gRPC 서버 정리"""
    global _grpc_server
    if _grpc_server:
        print("🛑 gRPC 서버 종료 중...")
        _grpc_server.stop(grace=2.0)
        _grpc_server = None
        print("✅ gRPC 서버 종료 완료")

# 프로그램 종료 시 정리
atexit.register(cleanup_grpc_server)

def start_pc_grpc_server():
    """PC에서 실행되는 gRPC 서버 시작 (모듈화된 버전)"""
    global _grpc_server, _grpc_service_impl

    try:
        if not GRPC_SERVER_AVAILABLE:
            print("❌ gRPC 서버 모듈이 없어 서버를 시작할 수 없습니다.")
            return
            
        # gRPC 서버 생성 (server.py 모듈 사용)
        _grpc_server, _grpc_service_impl = create_grpc_server(
            host=LOCAL_IP, 
            port=GRPC_SERVER_PORT, 
            max_workers=10
        )

        print(f"🚀 gRPC 서버 시작: {LOCAL_IP}:{GRPC_SERVER_PORT}")
        _grpc_server.start()
        _grpc_server.wait_for_termination()  # 종료될 때까지 대기
        
    except Exception as e:
        print(f"❌ gRPC 서버 시작 실패: {e}")

def signal_handler(signum, frame):
    """시그널 핸들러"""
    print(f"\n🛑 종료 신호 수신 ({signum})")
    cleanup_grpc_server()
    sys.exit(0)

# 시그널 핸들러 등록
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ===============================
# Dash 앱 초기화
# ===============================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Master Device Control"

# CSS 스타일 추가
app.index_string = '''
<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <style>
        .status-card {
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            border: none;
        }
        .fps-indicator {
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 4px;
        }
        .connection-good { background-color: #d4edda; color: #155724; }
        .connection-bad { background-color: #f8d7da; color: #721c24; }
        .led-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-left: 5px;
        }
        .led-green { background-color: #28a745; box-shadow: 0 0 5px #28a745; }
        .led-red { background-color: #dc3545; box-shadow: 0 0 5px #dc3545; }
        .led-off { background-color: #6c757d; }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
</body>
</html>
'''

# ── 헤더 ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
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

# ── 앱 레이아웃 ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    dcc.Store(id="wifi-conn-store"),
    dcc.Store(id="teleop-state", data={"running": False}),
    dcc.Store(id="save-stream-state", data={"active": False, "data": []}),  # Save Stream 상태 저장소
    html.Div(id="page-content")
])

# ===============================
# 콜백 함수들
# ===============================

# Wi-Fi 연결하기 → 바로 /wifi-ui로 이동
@app.callback(
    [Output("wifi-conn-store", "data"),
     Output("url", "pathname")],
    Input("btn-wifi-connect", "n_clicks"),
    [State("wifi-ip", "value"),
     State("slave-port", "value"),
     State("master-ip", "value"),
     State("master-port", "value")],
    prevent_initial_call=True
)
def handle_wifi_connect(n_clicks, robot_ip, robot_port, master_ip, master_port):
    """Wi-Fi 연결 정보 저장 후 바로 제어 화면으로 이동"""
    if not n_clicks:
        return no_update, no_update

    # 입력 검증
    if not robot_ip or not robot_port:
        print("Wi-Fi 연결: Robot IP/Port가 비어 있습니다.")
        return no_update, no_update

    try:
        port_int = int(robot_port)
    except Exception:
        print("Wi-Fi 연결: Port가 숫자가 아닙니다.")
        return no_update, no_update

    data = {
        "raspberry_ip": str(robot_ip).strip(),
        "raspberry_port": port_int,
        "master_ip": (str(master_ip).strip() if master_ip else ""),
        "master_port": (int(master_port) if master_port else None),
    }
    print(f"Wi-Fi 연결 정보 저장: {data}")
    
    # 바로 /wifi-ui로 이동
    return data, "/wifi-ui"

# wifi_ui에 실제 연결 정보 주입
@app.callback(
    Output("wifi-raspberry-connection", "data"),
    Input("wifi-conn-store", "data"),
    State("url", "pathname"),
    prevent_initial_call=True
)
def pass_wifi_store_to_wifi_ui(conn_store, pathname):
    if pathname != "/wifi-ui" or not conn_store:
        return no_update
    ip = conn_store.get("raspberry_ip") or conn_store.get("ip")
    port = conn_store.get("raspberry_port") or conn_store.get("port")
    if not ip or not port:
        return no_update
    data = {"ip": ip, "port": int(port)}
    print(f"wifi-raspberry-connection 업데이트: {data}")
    return data

# 라우터 콜백
@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname")
)
def display_page(pathname):
    print(f"[DEBUG] Current pathname: {pathname}")
    if pathname == "/wifi":
        return wifi.layout
    elif pathname == "/wifi-ui":
        print("[DEBUG] Loading wifi-ui page")
        return wifi_ui.layout
    elif pathname == "/local":
        return local.layout
    elif pathname == "/local-ui":
        return local_ui.layout
    else:
        # 메인 메뉴
        return html.Div([
            header,

            # 메인 컨테이너
            dbc.Container([
                # 타이틀 섹션
                html.Div([
                    html.H1("라즈베리파이 연결",
                            style={
                                'textAlign': 'center',
                                'marginTop': '40px',
                                'marginBottom': '20px',
                                'fontWeight': 'bold',
                                'fontSize': '2.5rem',
                                'color': '#2C3E50'
                            }),
                    html.P("라즈베리파이와 Wi-Fi로 연결하여 마스터 디바이스를 제어하세요",
                           style={
                               'textAlign': 'center', 
                               'fontSize': '1.2rem', 
                               'color': '#7F8C8D', 
                               'marginBottom': '50px'
                           })
                ], className="text-center"),

                # 연결 모드 카드
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            dcc.Link([
                                html.Div([
                                    html.Div("🍓",
                                            style={'fontSize': '5rem', 'marginBottom': '30px', 'textAlign': 'center'}),
                                    html.H3("라즈베리파이",
                                            style={'color': 'white', 'fontWeight': 'bold', 'marginBottom': '20px', 'textAlign': 'center'}),
                                    html.P("무선 네트워크를 통한 연결",
                                           style={'color': 'rgba(255,255,255,0.9)', 'textAlign': 'center', 'fontSize': '1.1rem', 'margin': '0'})
                                ])
                            ], href="/wifi", style={'textDecoration': 'none'})
                        ],
                        style={
                            'background': 'linear-gradient(135deg, #E74C3C, #C0392B)',
                            'borderRadius': '25px', 'padding': '50px 30px', 'textAlign': 'center',
                            'boxShadow': '0 15px 35px rgba(231, 76, 60, 0.3)',
                            'transition': 'all 0.3s ease', 'cursor': 'pointer', 'height': '320px',
                            'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                            'border': '2px solid transparent'
                        })
                    ], width=6, style={'margin': '0 auto'}),
                ], justify="center", className="g-4"),

                # 시스템 상태 표시
                html.Div([
                    dbc.Alert([
                        html.Div([
                            html.Span("💡 ", style={'fontSize': '1.2rem'}),
                            html.Strong("시스템 상태: "),
                            f"gRPC {'활성화' if GRPC_AVAILABLE else '비활성화'} | ",
                            f"gRPC 서버 {'사용 가능' if GRPC_SERVER_AVAILABLE else '사용 불가'} | ",
                            f"데이터 매니저 {'연결됨' if real_time_data_manager else '연결 안됨'}"
                        ])
                    ], color="info" if (GRPC_AVAILABLE and GRPC_SERVER_AVAILABLE) else "warning", className="mt-4"),
                    
                    # 기능 안내
                    dbc.Alert([
                        html.Div([
                            html.H6("🚀 주요 기능", style={'fontWeight': 'bold', 'marginBottom': '10px'}),
                            html.Ul([
                                html.Li("실시간 로봇 제어 및 모니터링"),
                                html.Li("Save Stream: 실시간 데이터 수집 및 CSV 저장"),
                                html.Li("토크 게인 조절 및 프리셋 설정"),
                                html.Li("Gravity/Position 모드 전환"),
                                html.Li("텔레오퍼레이션 제어")
                            ], style={'marginBottom': '0'})
                        ])
                    ], color="light", className="mt-3")
                ])

            ], fluid=True, style={'maxWidth': '900px', 'margin': '0 auto', 'padding': '20px'})
        ])

# ===============================
# Save Stream 전용 콜백들 (추가)
# ===============================

# Save Stream 데이터 자동 수집 콜백
@app.callback(
    Output("save-stream-state", "data"),
    Input("wifi-save-stream-interval", "n_intervals"),
    State("save-stream-state", "data"),
    prevent_initial_call=True
)
def update_save_stream_data(n_intervals, current_state):
    """Save Stream 데이터 자동 수집"""
    if not current_state.get("active", False):
        return no_update
    
    try:
        # 현재 엔코더 데이터 가져오기
        if grpc_data_manager:
            current_data = grpc_data_manager.get_current_encoder_data()
            
            if current_data and current_data.get("angles"):
                # 새 샘플 추가
                timestamp = time.time()
                new_sample = {
                    "timestamp": timestamp,
                    "angles": current_data.get("angles", []),
                    "formatted": current_data.get("formatted", "")
                }
                
                # 현재 상태에 데이터 추가
                stream_data = current_state.get("data", [])
                stream_data.append(new_sample)
                
                # 최대 1000개 샘플만 유지
                if len(stream_data) > 1000:
                    stream_data = stream_data[-1000:]
                
                # 실시간 데이터 매니저에도 추가
                if real_time_data_manager:
                    real_time_data_manager.add_streaming_sample(current_data.get("angles", []), timestamp)
                
                return {
                    "active": True,
                    "data": stream_data
                }
    
    except Exception as e:
        print(f"[ERROR] Save stream 데이터 수집 오류: {e}")
    
    return no_update

# ===============================
# 앱 실행 및 초기화
# ===============================

def initialize_app():
    """앱 초기화"""
    print("\n" + "="*60)
    print("🚀 Master Device 웹 인터페이스 초기화 (모듈화 버전)")
    print("="*60)
    
    # log 폴더 생성
    log_folder = "log"
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)
        print(f"📁 log 폴더 생성: {log_folder}")
    
    # assets 폴더 확인
    assets_folder = "assets"
    if not os.path.exists(assets_folder):
        os.makedirs(assets_folder)
        print(f"📁 assets 폴더 생성: {assets_folder}")
    
    # 스트림 핸들러 시작
    if 'grpc_stream_handler' in globals():
        try:
            grpc_stream_handler.start()
            print("📡 gRPC 스트림 핸들러 시작됨")
        except Exception as e:
            print(f"⚠️ 스트림 핸들러 시작 실패: {e}")
    
    print(f"📊 gRPC 모듈: {'✅ 사용 가능' if GRPC_AVAILABLE else '❌ 사용 불가'}")
    print(f"🚀 gRPC 서버: {'✅ 사용 가능' if GRPC_SERVER_AVAILABLE else '❌ 사용 불가'}")
    print("="*60 + "\n")

def cleanup_app():
    """앱 정리"""
    print("\n[INFO] 앱 정리 중...")
    
    # 스트림 핸들러 중지
    if 'grpc_stream_handler' in globals():
        try:
            grpc_stream_handler.stop()
            print("[INFO] gRPC 스트림 핸들러 중지됨")
        except Exception as e:
            print(f"[WARNING] 스트림 핸들러 중지 오류: {e}")
    
    # gRPC 서버 중지
    cleanup_grpc_server()

if __name__ == "__main__":
    # 앱 초기화
    initialize_app()
    
    # PC gRPC 서버 시작 (별도 스레드)
    if GRPC_SERVER_AVAILABLE:
        print("🤖 PC gRPC 서버를 백그라운드에서 시작합니다...")
        grpc_thread = threading.Thread(target=start_pc_grpc_server, daemon=True)
        grpc_thread.start()
        time.sleep(1)  # 서버 시작 대기
    else:
        print("⚠️ gRPC 서버 모듈이 없어 gRPC 서버를 시작할 수 없습니다.")
    
    print("=" * 80)
    print("🎉 PC UI 서버 시작 완료! (모듈화 버전)")
    print(f"🔡 로컬 주소: http://{LOCAL_IP}:{WEB_SERVER_PORT}")
    print(f"🌍 외부 접속: http://0.0.0.0:{WEB_SERVER_PORT}")
    print(f"🤖 gRPC 서버: {LOCAL_IP}:{GRPC_SERVER_PORT} (라즈베리파이용)")
    print(f"🔧 gRPC 사용 가능: {GRPC_AVAILABLE}")
    print(f"🚀 gRPC 서버 사용 가능: {GRPC_SERVER_AVAILABLE}")
    print("=" * 80)
    print("\n🔗 라즈베리파이에서 실행:")
    print(f"   ./robot_client {LOCAL_IP}:{GRPC_SERVER_PORT}")
    print("=" * 80 + "\n")
    
    try:
        app.run(
            host="0.0.0.0",
            port=WEB_SERVER_PORT,
            debug=False,
            dev_tools_hot_reload=False
        )
    except KeyboardInterrupt:
        print("\n🛑 사용자 중단 요청")
    except Exception as e:
        print(f"\n❌ 서버 실행 오류: {e}")
    finally:
        cleanup_grpc_server()
        cleanup_app()
        print("👋 프로그램 종료 완료")