# wifi_ui_1.py - 스레드 분리 버전 (UI 완전 비블로킹)
import dash
from dash import dcc, html, Input, Output, State, callback, no_update
import dash_bootstrap_components as dbc
import time
import threading
import json
import os
import pandas as pd
from datetime import datetime
import queue
import traceback
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum

# gRPC 클라이언트 모듈 import
GRPC_CLIENT_AVAILABLE = True
try:
    from GRPC.stubs import client
    print("[INFO] gRPC client 모듈 로드 성공")
except ImportError as e:
    print(f"[WARNING] gRPC client 모듈 로드 실패: {e}")
    GRPC_CLIENT_AVAILABLE = False

# 통합된 grpc_data_manager import
try:
    from grpc_data_manager import grpc_data_manager
    print("[INFO] 통합 grpc_data_manager 모듈 로드 성공")
except ImportError as e:
    print(f"[WARNING] grpc_data_manager 모듈 로드 실패: {e}")
    # 더미 매니저 생성
    class DummyGRPCDataManager:
        def save_pose(self, angles):
            return "Dummy_Pose"
        def get_saved_poses(self):
            return []
        def clear_poses(self):
            pass
        def delete_recorded_data(self):
            pass
        def get_recorded_log(self, limit):
            return []
        def get_robot_state(self):
            return {"connected": False, "hardware_buttons": {}, "communication": {}, "recording": {}, "gravity": {}, "position": {}}
        def get_grpc_entries(self, limit):
            return []
        def get_encoder_entries(self, limit):
            return []
        def get_current_gain_values(self):
            return {"shoulder_gain": 0.6, "joint_gain": 0.7}
        def update_gain_values(self, shoulder_gain, joint_gain):
            pass
        def get_current_encoder_data(self):
            return {"angles": [0.0] * 14, "formatted": "0.0°" * 14}
        def save_encoder_pose(self, angles, name=None):
            return name or f"Pose_{int(time.time())}"
        def reset_all_data(self):
            pass
        def start_streaming(self):
            pass
        def stop_streaming(self):
            pass
        def reset_gain_to_default(self):
            pass
        def get_recorded_samples(self):
            return []
    
    grpc_data_manager = DummyGRPCDataManager()

# 설정 및 상수
DEFAULT_RASPBERRY_IP = "192.168.0.43"
DEFAULT_RASPBERRY_PORT = 50051

# ===============================
# 백그라운드 작업 관리 시스템
# ===============================

class TaskType(Enum):
    APPLY_GAINS = "apply_gains"
    SEND_SAVE = "send_save"
    SEND_CLEAR = "send_clear"
    SEND_HOMING = "send_homing"
    SEND_TELEOP = "send_teleop"
    SEND_DELETE = "send_delete"
    SEND_POWER_OFF = "send_power_off"

@dataclass
class BackgroundTask:
    task_id: str
    task_type: TaskType
    params: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

@dataclass
class TaskResult:
    task_id: str
    success: bool
    result: Any = None
    error: str = ""
    timestamp: float = field(default_factory=time.time)

class BackgroundWorker:
    """백그라운드에서 gRPC 호출을 처리하는 워커"""
    
    def __init__(self):
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.worker_thread = None
        self.running = False
        self.connection_data = {
            "ip": DEFAULT_RASPBERRY_IP,
            "port": DEFAULT_RASPBERRY_PORT
        }
        
        print("[WORKER] BackgroundWorker 초기화")
    
    def start(self):
        """워커 스레드 시작"""
        if self.running:
            return
        
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        print("[WORKER] 백그라운드 워커 스레드 시작")
    
    def stop(self):
        """워커 스레드 중지"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
        print("[WORKER] 백그라운드 워커 스레드 중지")
    
    def update_connection(self, ip: str, port: int):
        """연결 정보 업데이트"""
        self.connection_data = {"ip": ip, "port": port}
        print(f"[WORKER] 연결 정보 업데이트: {ip}:{port}")
    
    def submit_task(self, task_type: TaskType, **params) -> str:
        """작업 제출"""
        task_id = f"{task_type.value}_{int(time.time() * 1000)}"
        task = BackgroundTask(
            task_id=task_id,
            task_type=task_type,
            params=params
        )
        
        try:
            self.task_queue.put_nowait(task)
            print(f"[WORKER] 작업 제출: {task_id} ({task_type.value})")
            return task_id
        except queue.Full:
            print(f"[WORKER] 작업 큐 가득참: {task_id}")
            return ""
    
    def get_result(self) -> Optional[TaskResult]:
        """결과 가져오기 (논블로킹)"""
        try:
            return self.result_queue.get_nowait()
        except queue.Empty:
            return None
    
    def get_all_results(self) -> List[TaskResult]:
        """모든 결과 가져오기"""
        results = []
        while True:
            result = self.get_result()
            if result is None:
                break
            results.append(result)
        return results
    
    def _worker_loop(self):
        """워커 메인 루프"""
        print("[WORKER] 워커 루프 시작")
        
        while self.running:
            try:
                # 작업 가져오기 (타임아웃 0.5초)
                task = self.task_queue.get(timeout=0.5)
                
                print(f"[WORKER] 작업 처리 시작: {task.task_id}")
                
                # 작업 실행
                result = self._execute_task(task)
                
                # 결과 저장
                self.result_queue.put(result)
                
                print(f"[WORKER] 작업 처리 완료: {task.task_id} (성공: {result.success})")
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[WORKER] 워커 루프 오류: {e}")
                traceback.print_exc()
        
        print("[WORKER] 워커 루프 종료")
    
    def _execute_task(self, task: BackgroundTask) -> TaskResult:
        """작업 실행"""
        if not GRPC_CLIENT_AVAILABLE:
            return TaskResult(
                task_id=task.task_id,
                success=False,
                error="gRPC 클라이언트 모듈 없음"
            )
        
        try:
            ip = self.connection_data["ip"]
            port = self.connection_data["port"]
            
            if task.task_type == TaskType.APPLY_GAINS:
                result = client.send_gravity_comp_gain(
                    ip, port,
                    task.params["shoulder_gain"],
                    task.params["joint_gain"]
                )
                # 로컬 데이터 매니저에도 업데이트
                grpc_data_manager.update_gain_values(
                    task.params["shoulder_gain"],
                    task.params["joint_gain"]
                )
                
            elif task.task_type == TaskType.SEND_SAVE:
                result = client.send_save_command(
                    ip, port, "SAVE",
                    task.params.get("angles", [])
                )
                
            elif task.task_type == TaskType.SEND_CLEAR:
                result = client.send_delete_command(ip, port, "CLEAR_POSES")
                grpc_data_manager.clear_poses()
                
            elif task.task_type == TaskType.SEND_HOMING:
                result = client.send_homing_command(ip, port, "GO_HOME")
                
            elif task.task_type == TaskType.SEND_TELEOP:
                command = task.params.get("command", "START")
                result = client.send_master_teleop_command(ip, port, command)
                
            elif task.task_type == TaskType.SEND_DELETE:
                command = task.params.get("command", "DELETE_ALL")
                result = client.send_delete_command(ip, port, command)
                if command == "DELETE_ALL":
                    grpc_data_manager.reset_all_data()
                    
            elif task.task_type == TaskType.SEND_POWER_OFF:
                result = client.send_power_off_command(ip, port, "POWER_OFF")
                
            else:
                raise ValueError(f"알 수 없는 작업 타입: {task.task_type}")
            
            return TaskResult(
                task_id=task.task_id,
                success=True,
                result=result
            )
            
        except Exception as e:
            print(f"[WORKER] 작업 실행 오류: {task.task_id} - {e}")
            return TaskResult(
                task_id=task.task_id,
                success=False,
                error=str(e)
            )

# 전역 백그라운드 워커 인스턴스
background_worker = BackgroundWorker()

# 실시간 데이터 스트림 관리자
class RealTimeDataStream:
    """실시간 엔코더 데이터 스트림 관리"""
    
    def __init__(self):
        self.latest_data = {
            "encoder_data": {"angles": [], "timestamp": 0},
            "robot_state": {"connected": False},
            "gain_values": {"shoulder_gain": 0.6, "joint_gain": 0.7},
            "encoder_entries": [],
            "last_update": 0,
            "error_count": 0
        }
        self.data_lock = threading.Lock()
        self.stream_thread = None
        self.running = False
        
    def start(self):
        """데이터 스트림 시작"""
        if self.running:
            return
        
        self.running = True
        self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.stream_thread.start()
        print("[STREAM] 실시간 데이터 스트림 시작")
    
    def stop(self):
        """데이터 스트림 중지"""
        self.running = False
        if self.stream_thread:
            self.stream_thread.join(timeout=1.0)
        print("[STREAM] 실시간 데이터 스트림 중지")
    
    def get_latest_data(self):
        """최신 데이터 가져오기"""
        with self.data_lock:
            return self.latest_data.copy()
    
    def _stream_loop(self):
        """데이터 스트림 루프"""
        print("[STREAM] 데이터 스트림 루프 시작")
        
        while self.running:
            try:
                # 데이터 매니저에서 데이터 가져오기
                current_time = time.time()
                
                encoder_data = grpc_data_manager.get_current_encoder_data()
                robot_state = grpc_data_manager.get_robot_state()
                gain_values = grpc_data_manager.get_current_gain_values()
                encoder_entries = grpc_data_manager.get_encoder_entries(3)
                
                # 안전하게 데이터 업데이트
                with self.data_lock:
                    self.latest_data.update({
                        "encoder_data": encoder_data or {"angles": [], "timestamp": current_time},
                        "robot_state": robot_state or {"connected": False},
                        "gain_values": gain_values or {"shoulder_gain": 0.6, "joint_gain": 0.7},
                        "encoder_entries": encoder_entries or [],
                        "last_update": current_time
                    })
                
                # 200ms 간격으로 업데이트 (5Hz)
                time.sleep(0.2)
                
            except Exception as e:
                print(f"[STREAM] 데이터 스트림 오류: {e}")
                with self.data_lock:
                    self.latest_data["error_count"] += 1
                time.sleep(0.5)  # 오류 시 더 긴 대기
        
        print("[STREAM] 데이터 스트림 루프 종료")

# 전역 실시간 데이터 스트림 인스턴스
real_time_stream = RealTimeDataStream()

# 앱 시작 시 백그라운드 서비스 시작
background_worker.start()
real_time_stream.start()

# CSS 스타일 및 클래스 정의
def get_led_style(is_active: bool, color: str = "green") -> dict:
    return {
        'display': 'inline-block',
        'width': '12px',
        'height': '12px',
        'borderRadius': '50%',
        'backgroundColor': color if is_active else '#888',
        'boxShadow': f'0 0 6px {color}' if is_active else 'none',
        'transition': 'all 0.3s ease'
    }

def format_motor_angles(angles):
    """모터 각도를 포맷팅하여 표시용 문자열로 변환"""
    if not angles or len(angles) == 0:
        return "엔코더 데이터 없음"
    
    # 14개 모터 각도를 2줄로 나누어 표시
    line1_motors = []  # 모터 1-7 (왼팔)
    line2_motors = []  # 모터 8-14 (오른팔)
    
    for i, angle in enumerate(angles[:14]):  # 최대 14개만 처리
        try:
            # 라디안을 도로 변환 (이미 도 단위라면 그대로 사용)
            if abs(angle) > 10:  # 10도보다 크면 이미 도 단위로 가정
                angle_deg = float(angle)
            else:  # 라디안 단위로 가정
                angle_deg = float(angle) * 180.0 / 3.14159
                
            formatted_angle = f"M{i+1:02d}: {angle_deg:+6.1f}°"
            
            if i < 7:
                line1_motors.append(formatted_angle)
            else:
                line2_motors.append(formatted_angle)
        except (ValueError, TypeError):
            formatted_angle = f"M{i+1:02d}: ERROR"
            if i < 7:
                line1_motors.append(formatted_angle)
            else:
                line2_motors.append(formatted_angle)
    
    # 두 줄로 구성
    result = "왼팔:  " + "  ".join(line1_motors) + "\n"
    result += "오른팔: " + "  ".join(line2_motors)
    
    return result

# ===============================
# 레이아웃 컴포넌트들
# ===============================

# 메인 제어 화면
main_control_screen = html.Div([

    # 헤더
    html.Div([
        html.Img(src="/assets/Neuro_Meka.png", style={'height': '60px'}),
        html.H2("Neuro Meka Master device (Wi-Fi Connected)",
                style={'color': '#7c8bc7', 'fontWeight': 'bold', 'marginLeft': '20px'})
    ], style={'display': 'flex', 'alignItems': 'center',
              'borderBottom': '2px solid #ccc', 'paddingBottom': '10px'}),

    # 연결 상태 표시
    dbc.Alert(id="wifi-connection-status", color="success", className="mt-3"),

    # ============= 백그라운드 작업 상태 표시 =============
    html.Div([
        html.Span("🔄 Background Tasks: ", style={'fontWeight': 'bold'}),
        html.Span(id="wifi-bg-task-status", children="Ready", 
                  style={'color': '#28a745', 'fontWeight': 'bold'}),
        html.Span(" | Stream: ", style={'fontSize': '0.9em', 'marginLeft': '15px'}),
        html.Span(id="wifi-stream-status", children="Active",
                  style={'color': '#007bff', 'fontWeight': 'bold'}),
    ], style={'marginBottom': '10px', 'padding': '8px',
              'backgroundColor': '#f0f8ff', 'borderRadius': '5px'}),

    # ============= 토크 게인 조절 카드 =============
    dbc.Card([
        dbc.CardHeader([
            html.H5("⚙️ Torque Gain Control", className="mb-0", style={'display': 'inline-block'}),
            html.Div(id="wifi-gain-status-indicator", 
                     style={'float': 'right', 'fontSize': '0.9em', 'color': '#6c757d'})
        ]),
        dbc.CardBody([
            # 현재 게인 값 표시
            html.Div([
                html.Span("📊 Current Gains: ", style={'fontWeight': 'bold', 'marginRight': '10px'}),
                html.Span("Shoulder: ", style={'fontSize': '0.9em'}),
                html.Span(id="wifi-current-shoulder-gain", children="0.60", 
                          style={'fontWeight': 'bold', 'color': '#007bff', 'marginRight': '15px'}),
                html.Span("Joint: ", style={'fontSize': '0.9em'}),
                html.Span(id="wifi-current-joint-gain", children="0.70",
                          style={'fontWeight': 'bold', 'color': '#28a745'}),
            ], style={'marginBottom': '15px', 'padding': '8px', 
                      'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),

            # 게인 조절 입력
            dbc.Row([
                dbc.Col([
                    dbc.Label("Shoulder Gain:", style={'fontWeight': 'bold'}),
                    dbc.InputGroup([
                        dbc.Input(
                            id="wifi-shoulder-gain-input",
                            type="number",
                            min=0.2,
                            max=1.0,
                            step=0.05,
                            value=0.6,
                            placeholder="0.2 - 1.0"
                        ),
                        dbc.InputGroupText("(0.2-1.0)")
                    ], className="mb-2")
                ], width=6),
                dbc.Col([
                    dbc.Label("Joint Gain:", style={'fontWeight': 'bold'}),
                    dbc.InputGroup([
                        dbc.Input(
                            id="wifi-joint-gain-input",
                            type="number",
                            min=0.2,
                            max=1.0,
                            step=0.05,
                            value=0.7,
                            placeholder="0.2 - 1.0"
                        ),
                        dbc.InputGroupText("(0.2-1.0)")
                    ], className="mb-2")
                ], width=6),
            ]),

            # 게인 조절 버튼들
            html.Div([
                dbc.Button("Apply Gains", id="wifi-apply-gains-btn", color="primary", className="me-2"),
                dbc.Button("Reset to Default", id="wifi-reset-gains-btn", color="secondary", className="me-2"),
                dbc.Button("Fine Tune +", id="wifi-fine-tune-up-btn", color="success", size="sm", className="me-1"),
                dbc.Button("Fine Tune -", id="wifi-fine-tune-down-btn", color="warning", size="sm"),
            ], className="mb-2"),

            html.Div(id="wifi-gain-status", style={'marginTop': '10px'}),

            # 프리셋 게인 값들
            html.Div([
                html.Small("Quick Presets: ", style={'fontWeight': 'bold', 'marginRight': '10px'}),
                dbc.ButtonGroup([
                    dbc.Button("Conservative", id="wifi-preset-conservative", color="info", size="sm"),
                    dbc.Button("Balanced", id="wifi-preset-balanced", color="primary", size="sm"),
                    dbc.Button("Aggressive", id="wifi-preset-aggressive", color="warning", size="sm"),
                ], size="sm")
            ], style={'marginTop': '10px'})
        ])
    ], className="mt-4 status-card"),

    # ============= 팔 상태 모니터링 카드 =============
    dbc.Card([
        dbc.CardHeader([
            html.H5("🤖 Arm Status Monitor", className="mb-0", style={'display': 'inline-block'}),
            html.Div(id="wifi-arm-mode-status", children="Position Mode",
                     style={'float': 'right', 'fontSize': '0.9em', 'color': '#28a745'})
        ]),
        dbc.CardBody([
            # 현재 팔 상태 표시
            html.Div([
                html.Span("🦾 Current Arm Status: ", style={'fontWeight': 'bold', 'marginBottom': '10px', 'display': 'block'}),
                
                # 왼팔 상태
                html.Div([
                    html.Span("Left Arm: ", style={'fontSize': '1em', 'fontWeight': 'bold'}),
                    html.Span(id="wifi-left-arm-status", children="Position", 
                            style={'fontWeight': 'bold', 'fontSize': '1.1em'}),  # 색상은 콜백에서 동적 설정
                    html.Span(id="wifi-left-arm-indicator", className="ms-2")
                ], style={'marginBottom': '8px'}),

                # 오른팔 상태
                html.Div([
                    html.Span("Right Arm: ", style={'fontSize': '1em', 'fontWeight': 'bold'}),
                    html.Span(id="wifi-right-arm-status", children="Position",
                            style={'fontWeight': 'bold', 'fontSize': '1.1em'}),
                    html.Span(id="wifi-right-arm-indicator", className="ms-2")
                ], style={'marginBottom': '10px'}),
                
            ], style={'padding': '10px', 'backgroundColor': '#f8f9fa', 'borderRadius': '5px'}),

            # 상태 정보 설명
            html.Div([
                html.Small("💡 ", style={'fontSize': '1em'}),
                html.Small("Position Mode: 위치 제어 활성 | Gravity Mode: 중력 보상 활성", 
                          style={'fontSize': '0.9em', 'color': '#6c757d'})
            ], style={'marginTop': '10px', 'fontStyle': 'italic'})
        ])
    ], className="mt-4 status-card"),

    # ============= 실시간 엔코더 데이터 표시 카드 (스레드 기반) =============
    dcc.Store(id="wifi-saved-entries", data=[]),
    dcc.Store(id="wifi-task-results", data=[]),  # 백그라운드 작업 결과 저장
    dbc.Card([
        dbc.CardHeader([
            html.H5("📊 Real-time Encoder Data", className="mb-0", style={'display': 'inline-block'}),
            html.Div(id="wifi-encoder-status-indicator", 
                    children=[html.Span("🟢 Streaming", style={'color': 'green'})],
                    style={'float': 'right'})
        ]),
        dbc.CardBody([
            # 하드웨어 버튼 상태 표시
            html.Div([
                html.Span("🎮 Hardware Controls: ", style={'fontWeight': 'bold'}),
                html.Span("R_push_1: ", style={'fontSize': '0.9em'}),
                html.Span(id="wifi-r-push1-status", children="1",
                          style={'fontWeight': 'bold', 'color': 'blue'}),
                html.Span(" | L_push_1: ", style={'fontSize': '0.9em', 'marginLeft': '10px'}),
                html.Span(id="wifi-l-push1-status", children="1",
                          style={'fontWeight': 'bold', 'color': 'blue'}),
                html.Span(" | L_push_2: ", style={'fontSize': '0.9em', 'marginLeft': '10px'}),
                html.Span(id="wifi-l-push2-status", children="1",
                          style={'fontWeight': 'bold', 'color': 'blue'}),
            ], style={'marginBottom': '10px', 'padding': '5px',
                      'backgroundColor': '#f8f9fa', 'borderRadius': '3px'}),

            # 컨트롤 버튼들
            html.Div([
                dbc.Button("Save", id="wifi-save-btn", color="primary", className="me-2"),
                dbc.Button("Clear", id="wifi-clear-btn", color="danger", className="me-2"),
                dbc.Button("Save As", id="wifi-save-as-btn", color="secondary", className="me-2"),
                dbc.Button("Import Recorded", id="wifi-import-recorded-btn", color="success", className="me-2"),
                dbc.Button("Clear Recorded", id="wifi-clear-recorded-btn", color="warning", className="me-2"),
                dbc.Button("Export CSV", id="wifi-export-csv-btn", color="info", className="me-2"),
            ], className="mb-2"),

            # 추가 제어 버튼들
            html.Div([
                dbc.Button("Go Home", id="wifi-go-home-btn", color="info", className="me-2"),
                dbc.Button("Start Teleop", id="wifi-start-teleop-btn", color="success", className="me-2"),
                dbc.Button("Stop Teleop", id="wifi-stop-teleop-btn", color="danger", className="me-2"),
                dbc.Button("Delete All", id="wifi-delete-all-btn", color="warning", className="me-2"),
                dbc.Button("Power Off", id="wifi-power-off-btn", color="dark", className="me-2"),
            ], className="mb-3"),

            # 상태 표시 영역들
            html.Div(id="wifi-save-as-status", style={'marginTop': '10px'}),
            html.Div(id="wifi-import-status", style={'marginTop': '5px'}),
            html.Div(id="wifi-control-status", style={'marginTop': '5px'}),
            html.Div(id="wifi-save-status", style={'marginTop': '5px'}),
            html.Div(id="wifi-clear-status", style={'marginTop': '5px'}),
            html.Hr(),

            # 통신 속도 및 녹화 상태 표시
            html.Div([
                html.Span("📊 Communication: ", style={'fontWeight': 'bold'}),
                html.Span(id="wifi-comm-fps", children="0 FPS"),
                html.Span(" | Interval: ", style={'fontSize': '0.9em', 'marginLeft': '10px'}),
                html.Span(id="wifi-comm-interval", children="0ms",
                          style={'fontWeight': 'bold', 'color': '#28a745', 'marginRight': '15px'}),
                html.Span(" | Recording: ", style={'fontSize': '0.9em'}),
                html.Span(id="wifi-recording-status", children="STOPPED", className="text-muted"),
            ], style={'marginBottom': '10px', 'padding': '5px',
                      'backgroundColor': '#f1f3f4', 'borderRadius': '3px'}),

            # 실시간 엔코더 데이터 표시 영역
            html.Div([
                html.H6("🔢 Live Motor Encoder Data (14-DOF)", 
                       style={'fontWeight': 'bold', 'marginBottom': '10px'}),
                html.Div([
                    html.Span("📊 실시간 수신: ", style={'fontWeight': 'bold'}),
                    html.Span(id="wifi-encoder-update-count", children="0 samples", 
                              style={'fontWeight': 'bold', 'color': '#007bff', 'marginRight': '15px'}),
                    html.Span(" | 마지막 업데이트: ", style={'fontSize': '1.2em'}),
                    html.Span(id="wifi-encoder-last-update", children="--:--:--",
                              style={'fontWeight': 'bold', 'color': '#28a745'}),
                ], style={'marginBottom': '10px', 'padding': '8px',
                          'backgroundColor': '#e9ecef', 'borderRadius': '5px'}),
            ], className="mb-3"),

            # 실시간 엔코더 데이터 표시 (스레드 기반)
            html.Div(
                id="wifi-encoder-list-display",
                children="📡 실시간 엔코더 데이터 스트림 시작 중...",
                style={
                    'height': '200px',
                    'overflowY': 'auto',
                    'fontFamily': 'Consolas, "Courier New", monospace',
                    'whiteSpace': 'pre-wrap',
                    'fontSize': '1.3em',
                    'border': '2px solid #dee2e6',
                    'color': '#212529',
                    'borderRadius': '8px',
                    'padding': '8px',
                    'lineHeight': '1.4',
                    'backgroundColor': "#ffffff"
                }
            ),
            html.Hr(),
            html.Div([
                html.H6([
                    html.Span("💾 ", style={'fontSize': '1.2em'}),
                    "저장된 포즈 리스트"
                ], style={'fontWeight': 'bold', 'marginBottom': '10px'}),
                
                html.Div([
                    html.Span("이 포즈 수: ", style={'fontWeight': 'bold'}),
                    html.Span(id="wifi-total-poses-count", children="0", 
                              style={'fontWeight': 'bold', 'color': '#007bff', 'marginRight': '15px'}),
                    html.Span(" | 마지막 저장: ", style={'fontSize': '1.3em'}),
                    html.Span(id="wifi-last-pose-time", children="--:--:--",
                              style={'fontWeight': 'bold', 'color': "#2bd653"}),
                ], style={'marginBottom': '10px', 'padding': '12px',
                          'backgroundColor': "#271E1E", 'borderRadius': '8px'}),
                
                # 저장된 포즈 리스트 
                html.Div(
                    id="wifi-saved-poses-list",
                    children="저장된 포즈가 없습니다.",
                    style={
                        'maxHeight': '300px',
                        'overflowY': 'auto',
                        'fontFamily': 'Consolas, "Courier New", monospace',
                        'fontSize': '1.3em',
                        'border': '2px solid #dee2e6',
                        'color': "#000000",
                        'borderRadius': '5px',
                        'padding': '10px',
                        'backgroundColor': "#e0e0e0",
                        'whiteSpace': 'pre-line'
                    }
                )
            ], className="mb-3"),
        ])
    ], className="mt-4 status-card"),

    # 빠른 UI 업데이트 간격 (200ms)
    dcc.Interval(id="wifi-interval", interval=200, n_intervals=0),
    # 백그라운드 작업 결과 체크 (더 빠른 간격 - 100ms)
    dcc.Interval(id="wifi-bg-result-interval", interval=100, n_intervals=0),

    html.Br(),
    dcc.Link("← Wi-Fi 메뉴로 돌아가기", href="/wifi", className="btn btn-link")
], style={'padding': '20px'})

# 페이지 레이아웃
layout = html.Div([
    dcc.Store(id="wifi-raspberry-connection", data={
        "ip": DEFAULT_RASPBERRY_IP,
        "port": DEFAULT_RASPBERRY_PORT
    }),
    dcc.Store(id="wifi-auto-connect-attempted", data=False),
    main_control_screen
])

# ===============================
# 백그라운드 작업 결과 처리 콜백
# ===============================

@callback(
    [Output("wifi-task-results", "data"),
     Output("wifi-bg-task-status", "children"),
     Output("wifi-gain-status", "children"),
     Output("wifi-save-status", "children"), 
     Output("wifi-clear-status", "children"),
     Output("wifi-control-status", "children")],
    Input("wifi-bg-result-interval", "n_intervals"),
    State("wifi-task-results", "data"),
    prevent_initial_call=True
)
def check_background_results(n_intervals, current_results):
    """백그라운드 작업 결과 확인 및 처리"""
    # 새 결과들 가져오기
    new_results = background_worker.get_all_results()
    
    if not new_results:
        return no_update, no_update, no_update, no_update, no_update, no_update
    
    # 결과 처리
    gain_status = no_update
    save_status = no_update
    clear_status = no_update
    control_status = no_update
    
    for result in new_results:
        print(f"[UI] 백그라운드 작업 결과: {result.task_id} - 성공: {result.success}")
        
        if result.task_id.startswith("apply_gains"):
            if result.success:
                gain_status = dbc.Alert("✅ 토크 게인 적용 완료", color="success", duration=3000)
            else:
                gain_status = dbc.Alert(f"⚠️ 토크 게인 적용 실패: {result.error}", color="danger", duration=3000)
                
        elif result.task_id.startswith("send_save"):
            if result.success:
                save_status = dbc.Alert(f"💾 Save 완료: {result.result}", color="success", duration=3000)
            else:
                save_status = dbc.Alert(f"⚠️ Save 실패: {result.error}", color="danger", duration=3000)
                
        elif result.task_id.startswith("send_clear"):
            if result.success:
                clear_status = dbc.Alert(f"🗑️ Clear 완료: {result.result}", color="warning", duration=3000)
            else:
                clear_status = dbc.Alert(f"⚠️ Clear 실패: {result.error}", color="danger", duration=3000)
                
        elif result.task_id.startswith(("send_homing", "send_teleop", "send_delete", "send_power_off")):
            if result.success:
                task_name = result.task_id.split('_')[1]
                icons = {
                    "homing": "🏠", "teleop": "🎮", "delete": "🗑️", "power": "⚡"
                }
                icon = icons.get(task_name, "✅")
                color = "danger" if task_name == "delete" else "success" if task_name != "teleop" else "primary"
                control_status = dbc.Alert(f"{icon} {task_name.title()} 완료: {result.result}", 
                                         color=color, duration=3000)
            else:
                control_status = dbc.Alert(f"⚠️ 작업 실패: {result.error}", color="danger", duration=3000)
    
    # 전체 결과 저장 (최대 100개까지)
    all_results = (current_results or []) + [
        {"task_id": r.task_id, "success": r.success, "timestamp": r.timestamp}
        for r in new_results
    ]
    if len(all_results) > 100:
        all_results = all_results[-100:]
    
    # 백그라운드 작업 상태 업데이트
    bg_status = f"Processed {len(new_results)} tasks"
    
    return all_results, bg_status, gain_status, save_status, clear_status, control_status

# ===============================
# 실시간 데이터 업데이트 콜백 (스레드 기반)
# ===============================

@callback(
    [Output("wifi-connection-status", "children"),
     Output("wifi-current-shoulder-gain", "children"),
     Output("wifi-current-joint-gain", "children"),
     Output("wifi-encoder-list-display", "children"),
     Output("wifi-encoder-update-count", "children"),
     Output("wifi-encoder-last-update", "children"),
     Output("wifi-stream-status", "children"),
     Output("wifi-comm-fps", "children"),
     Output("wifi-comm-interval", "children"),
     Output("wifi-recording-status", "children"),
     Output("wifi-left-arm-status", "children"),
     Output("wifi-right-arm-status", "children"),
     Output("wifi-arm-mode-status", "children"),
     Output("wifi-left-arm-status", "style"),  # 추가
     Output("wifi-right-arm-status", "style"),
     Output("wifi-saved-poses-list", "children"),  # 추가
     Output("wifi-total-poses-count", "children"),  # 추가
     Output("wifi-last-pose-time", "children")],  # 추가],  # 추가
    Input("wifi-interval", "n_intervals"),
    State("wifi-raspberry-connection", "data"),
    prevent_initial_call=True
)
def update_realtime_status_threaded(n_intervals, connection_data):
    """스레드 기반 실시간 상태 업데이트 (완전 비블로킹)"""
    try:
        # 실시간 데이터 스트림에서 최신 데이터 가져오기 (논블로킹)
        latest_data = real_time_stream.get_latest_data()
        
        ip = connection_data.get("ip", DEFAULT_RASPBERRY_IP)
        port = connection_data.get("port", DEFAULT_RASPBERRY_PORT)
        
        # 연결 정보를 백그라운드 워커에 업데이트
        background_worker.update_connection(ip, port)
        
        # ===== 연결 상태 =====
        robot_state = latest_data["robot_state"]
        is_connected = True
        connection_status = f"✅ 연결됨: {ip}:{port}" if is_connected else f"❌ 연결 끊김: {ip}:{port}"
        
        # ===== 게인 값 =====
        gain_values = latest_data["gain_values"]
        
        # ===== 엔코더 데이터 =====
        encoder_data = latest_data["encoder_data"]
        encoder_entries = latest_data["encoder_entries"]

        encoder_display = "엔코더 데이터 스트림 대기 중..."
        encoder_count = "0"
        last_update = "--:--:--"

        if encoder_data and encoder_data.get("angles"):
            angles = encoder_data.get("angles", [])
            timestamp = encoder_data.get("timestamp", time.time())
            
            # 엔코더 데이터 포맷팅
            encoder_display = format_motor_angles(angles)
            
            # 통계 정보
            encoder_count = f"{len(encoder_entries)} samples"
            last_update = time.strftime("%H:%M:%S", time.localtime(timestamp))
        else:
            # 실시간 데이터가 없을 때는 기본 메시지만 표시
            encoder_display = "실시간 엔코더 데이터 대기 중..."
            encoder_count = "0 samples"
            last_update = "--:--:--"

        # ===== 저장된 포즈 리스트 ===== (엔코더 데이터와 독립적으로 처리)
        saved_poses_display = "저장된 포즈가 없습니다."
        total_poses = "0"
        last_pose_time = "--:--:--"
        
        try:
            saved_poses = grpc_data_manager.get_saved_poses()
            total_poses = str(len(saved_poses))
            
            if saved_poses:
                # 최근 10개 포즈만 표시
                recent_poses = saved_poses[-10:]
                pose_lines = []
                
                for i, pose in enumerate(recent_poses):
                    pose_name = pose.get("name", f"Pose_{i+1}")
                    pose_time = pose.get("datetime", "Unknown")
                    angles = pose.get("angles", [])
                    
                    # 처음 4개 각도만 간단히 표시
                    if angles and len(angles) >= 4:
                        angle_preview = [f"{float(angles[j])*180/3.14159:+5.1f}°" for j in range(min(4, len(angles)))]
                        angle_str = ", ".join(angle_preview) + "..."
                    else:
                        angle_str = "No angles"
                    
                    pose_lines.append(f"[{len(saved_poses)-len(recent_poses)+i+1:2d}] {pose_name} ({pose_time}) - {angle_str}")
                
                saved_poses_display = "\n".join(pose_lines)
                
                # 마지막 포즈 시간
                last_pose = saved_poses[-1]
                last_pose_timestamp = last_pose.get("timestamp", time.time())
                last_pose_time = time.strftime("%H:%M:%S", time.localtime(last_pose_timestamp))
                
        except Exception as e:
            print(f"[UI] 저장된 포즈 표시 오류: {e}")
            saved_poses_display = f"포즈 리스트 로드 오류: {e}"
        # ===== 통신 상태 =====
        comm = robot_state.get("communication", {})
        fps = comm.get("fps", 0.0)
        interval = comm.get("interval", 0.0)
        
        # ===== 팔 모드 상태 =====
        # 수정된 코드 - grpc_data_manager에서 직접 가져오기
        try:
            # grpc_data_manager에서 실제 로봇 상태 가져오기
            current_robot_state = grpc_data_manager.get_robot_state()
            
            # 중력/포지션 모드 상태
            gravity_modes = current_robot_state.get("gravity", {})
            position_modes = current_robot_state.get("position", {})
            
            # 각 팔 상태 확인 (독립적)
            left_gravity = gravity_modes.get("left_active", False)
            right_gravity = gravity_modes.get("right_active", False)
            
            # 상태 표시 (Gravity 우선, 없으면 Position)
            left_arm_status = "Gravity" if left_gravity else "Position"
            right_arm_status = "Gravity" if right_gravity else "Position"
            
            # 전체 모드 (하나라도 Gravity면 Gravity Mode)
            overall_arm_status = "Gravity Mode" if (left_gravity or right_gravity) else "Position Mode"
            
        except Exception as e:
            print(f"[UI] 팔 상태 가져오기 오류: {e}")
            # 기본값으로 fallback
            left_arm_status = "Position"
            right_arm_status = "Position" 
            overall_arm_status = "Position Mode"
        
        
        # ===== 스트림 상태 =====
        last_stream_update = latest_data.get("last_update", 0)
        current_time = time.time()
        stream_age = current_time - last_stream_update
        
        if stream_age < 1.0:
            stream_status = "Active"
        elif stream_age < 5.0:
            stream_status = "Slow"
        else:
            stream_status = "Stale"

        left_style = {
            'fontWeight': 'bold', 
            'fontSize': '1.3em',
            'color': '#dc3545' if left_gravity else '#007bff'  # 빨강(Gravity) vs 파랑(Position)
        }
        right_style = {
            'fontWeight': 'bold', 
            'fontSize': '1.3em', 
            'color': '#dc3545' if right_gravity else '#007bff'
        }
            
        return (
            dbc.Alert(connection_status, color="success" if is_connected else "danger"),
            f"{gain_values.get('shoulder_gain', 0.6):.2f}",
            f"{gain_values.get('joint_gain', 0.7):.2f}",
            encoder_display,
            encoder_count,
            last_update,
            stream_status,
            f"{fps:.1f} FPS",
            f"{interval:.1f}ms",
            "RECORDING" if robot_state.get("recording", {}).get("active", False) else "STOPPED",
            left_arm_status,
            right_arm_status,
            overall_arm_status,
            left_style,   # 추가
            right_style,   # 추가
            saved_poses_display,  # 추가
            total_poses,  # 추가
            last_pose_time  # 추가
        )
        
    except Exception as e:
        print(f"[ERROR] 실시간 상태 업데이트 오류: {e}")
        return (
            dbc.Alert("❌ 실시간 업데이트 오류", color="danger"),
            no_update, no_update, f"업데이트 오류: {str(e)}", 
            "오류", "--:--:--", "Error", "0 FPS", "0ms", "ERROR",
            "?", "?", "?"
        )

# ===============================
# 버튼 콜백들 (백그라운드 작업 제출)
# ===============================

# Apply Gains 버튼 (백그라운드 작업 제출)
@callback(
    [Output("wifi-current-shoulder-gain", "children", allow_duplicate=True),
     Output("wifi-current-joint-gain", "children", allow_duplicate=True)],
    Input("wifi-apply-gains-btn", "n_clicks"),
    [State("wifi-shoulder-gain-input", "value"),
     State("wifi-joint-gain-input", "value")],
    prevent_initial_call=True
)
def apply_gains_threaded(n_clicks, shoulder_gain, joint_gain):
    """토크 게인 적용 (백그라운드 작업 제출)"""
    if not n_clicks:
        return no_update, no_update
    
    # 게인 값 검증
    shoulder_gain = max(0.2, min(1.0, float(shoulder_gain or 0.6)))
    joint_gain = max(0.2, min(1.0, float(joint_gain or 0.7)))
    
    # 백그라운드 작업 제출
    task_id = background_worker.submit_task(
        TaskType.APPLY_GAINS,
        shoulder_gain=shoulder_gain,
        joint_gain=joint_gain
    )
    
    print(f"[UI] Apply Gains 작업 제출: {task_id}")
    
    # UI는 즉시 값 업데이트
    return f"{shoulder_gain:.2f}", f"{joint_gain:.2f}"

# Save 버튼 (백그라운드 작업)
@callback(
    Output("wifi-save-as-status", "children"),
    Input("wifi-save-btn", "n_clicks"),
    prevent_initial_call=True
)
def handle_save_threaded(n_clicks):
    """Save 버튼 처리 (백그라운드 작업)"""
    if not n_clicks:
        return no_update
    
    # 현재 엔코더 데이터 가져오기
    latest_data = real_time_stream.get_latest_data()
    encoder_data = latest_data["encoder_data"]
    angles = encoder_data.get("angles", [0.0] * 14) if encoder_data else [0.0] * 14
    
    # 백그라운드 작업 제출
    task_id = background_worker.submit_task(TaskType.SEND_SAVE, angles=angles)
    
    print(f"[UI] Save 작업 제출: {task_id}")
    
    return dbc.Alert("📤 Save 작업 제출됨 (백그라운드 처리 중)", color="info", duration=2000)

# Clear 버튼
@callback(
    Output("wifi-save-as-status", "children", allow_duplicate=True),
    Input("wifi-clear-btn", "n_clicks"),
    prevent_initial_call=True
)
def handle_clear_threaded(n_clicks):
    """Clear 버튼 처리 (백그라운드 작업)"""
    if not n_clicks:
        return no_update
    
    task_id = background_worker.submit_task(TaskType.SEND_CLEAR)
    print(f"[UI] Clear 작업 제출: {task_id}")
    
    return dbc.Alert("📤 Clear 작업 제출됨 (백그라운드 처리 중)", color="info", duration=2000)

# 제어 버튼들 (백그라운드 작업)
@callback(
    Output("wifi-save-as-status", "children", allow_duplicate=True),
    [Input("wifi-go-home-btn", "n_clicks"),
     Input("wifi-start-teleop-btn", "n_clicks"),
     Input("wifi-stop-teleop-btn", "n_clicks"),
     Input("wifi-delete-all-btn", "n_clicks"),
     Input("wifi-power-off-btn", "n_clicks")],
    prevent_initial_call=True
)
def handle_control_buttons_threaded(home_clicks, start_teleop_clicks, stop_teleop_clicks, 
                                   delete_all_clicks, power_off_clicks):
    """제어 버튼들 처리 (백그라운드 작업)"""
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    task_id = ""
    action_name = ""
    
    if trigger_id == "wifi-go-home-btn":
        task_id = background_worker.submit_task(TaskType.SEND_HOMING)
        action_name = "Home 이동"
    elif trigger_id == "wifi-start-teleop-btn":
        task_id = background_worker.submit_task(TaskType.SEND_TELEOP, command="START")
        action_name = "Teleop 시작"
    elif trigger_id == "wifi-stop-teleop-btn":
        task_id = background_worker.submit_task(TaskType.SEND_TELEOP, command="STOP")
        action_name = "Teleop 중지"
    elif trigger_id == "wifi-delete-all-btn":
        task_id = background_worker.submit_task(TaskType.SEND_DELETE, command="DELETE_ALL")
        action_name = "전체 삭제"
    elif trigger_id == "wifi-power-off-btn":
        task_id = background_worker.submit_task(TaskType.SEND_POWER_OFF)
        action_name = "전원 종료"
    
    if task_id:
        print(f"[UI] 제어 작업 제출: {action_name} - {task_id}")
        return dbc.Alert(f"📤 {action_name} 작업 제출됨 (백그라운드 처리 중)", color="info", duration=2000)
    
    return no_update

# 나머지 간단한 콜백들 (로컬 작업)
@callback(
    [Output("wifi-shoulder-gain-input", "value"),
     Output("wifi-joint-gain-input", "value"),
     Output("wifi-gain-status", "children", allow_duplicate=True)],
    Input("wifi-reset-gains-btn", "n_clicks"),
    prevent_initial_call=True
)
def reset_gains_to_default(n_clicks):
    if not n_clicks:
        return no_update, no_update, no_update
    grpc_data_manager.reset_gain_to_default()
    return 0.6, 0.7, dbc.Alert("🔄 게인 값이 기본값으로 리셋되었습니다.", color="info", duration=3000)

@callback(
    [Output("wifi-shoulder-gain-input", "value", allow_duplicate=True),
     Output("wifi-joint-gain-input", "value", allow_duplicate=True),
     Output("wifi-gain-status", "children", allow_duplicate=True)],
    [Input("wifi-fine-tune-up-btn", "n_clicks"),
     Input("wifi-fine-tune-down-btn", "n_clicks")],
    [State("wifi-shoulder-gain-input", "value"),
     State("wifi-joint-gain-input", "value")],
    prevent_initial_call=True
)
def fine_tune_gains(up_clicks, down_clicks, current_shoulder, current_joint):
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    shoulder = float(current_shoulder or 0.6)
    joint = float(current_joint or 0.7)
    
    if trigger_id == "wifi-fine-tune-up-btn":
        shoulder = min(1.0, shoulder + 0.05)
        joint = min(1.0, joint + 0.05)
        message = "📈 게인 값 증가"
    elif trigger_id == "wifi-fine-tune-down-btn":
        shoulder = max(0.2, shoulder - 0.05)
        joint = max(0.2, joint - 0.05)
        message = "📉 게인 값 감소"
    else:
        return no_update, no_update, no_update
    
    return round(shoulder, 2), round(joint, 2), dbc.Alert(f"{message}: S={shoulder:.2f}, J={joint:.2f}", color="info", duration=2000)

@callback(
    [Output("wifi-shoulder-gain-input", "value", allow_duplicate=True),
     Output("wifi-joint-gain-input", "value", allow_duplicate=True),
     Output("wifi-gain-status", "children", allow_duplicate=True)],
    [Input("wifi-preset-conservative", "n_clicks"),
     Input("wifi-preset-balanced", "n_clicks"),
     Input("wifi-preset-aggressive", "n_clicks")],
    prevent_initial_call=True
)
def apply_gain_presets(conservative_clicks, balanced_clicks, aggressive_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == "wifi-preset-conservative":
        return 0.3, 0.4, dbc.Alert("🛡️ Conservative 프리셋 적용", color="info", duration=2000)
    elif trigger_id == "wifi-preset-balanced":
        return 0.6, 0.7, dbc.Alert("⚖️ Balanced 프리셋 적용", color="primary", duration=2000)
    elif trigger_id == "wifi-preset-aggressive":
        return 0.8, 0.9, dbc.Alert("🚀 Aggressive 프리셋 적용", color="warning", duration=2000)
    
    return no_update, no_update, no_update

# 로컬 작업들
@callback(
    Output("wifi-save-as-status", "children", allow_duplicate=True),
    Input("wifi-save-as-btn", "n_clicks"),
    prevent_initial_call=True
)
def handle_save_as_local(n_clicks):
    if not n_clicks:
        return no_update
    
    custom_name = f"Custom_{time.strftime('%H%M%S')}"
    latest_data = real_time_stream.get_latest_data()
    encoder_data = latest_data["encoder_data"]
    angles = encoder_data.get("angles", [0.0] * 8) if encoder_data else [0.0] * 8
    
    pose_name = grpc_data_manager.save_encoder_pose(angles, custom_name)
    return dbc.Alert(f"💾 커스텀 포즈 저장: {pose_name}", color="info", duration=3000)

@callback(
    Output("wifi-import-status", "children"),
    Input("wifi-import-recorded-btn", "n_clicks"),
    prevent_initial_call=True
)
def import_recorded_data(n_clicks):
    if not n_clicks:
        return no_update
    
    recorded_samples = grpc_data_manager.get_recorded_samples()
    imported_count = 0
    
    for sample in recorded_samples:
        angles = sample.get("values", [])
        if angles:
            pose_name = f"Recorded_{imported_count+1:03d}"
            grpc_data_manager.save_encoder_pose(angles, pose_name)
            imported_count += 1
    
    if imported_count > 0:
        return dbc.Alert(f"📥 녹화 데이터 가져오기 완료: {imported_count}개 포즈", color="success", duration=3000)
    else:
        return dbc.Alert("⚠️ 가져올 녹화 데이터가 없습니다.", color="warning", duration=3000)

@callback(
    Output("wifi-import-status", "children", allow_duplicate=True),
    Input("wifi-clear-recorded-btn", "n_clicks"),
    prevent_initial_call=True
)
def clear_recorded_data(n_clicks):
    if not n_clicks:
        return no_update
    
    grpc_data_manager.delete_recorded_data()
    return dbc.Alert("🗑️ 녹화 데이터 삭제 완료", color="warning", duration=3000)

# CSV 내보내기 콜백 추가
@callback(
    Output("wifi-save-as-status", "children", allow_duplicate=True),
    Input("wifi-export-csv-btn", "n_clicks"),
    prevent_initial_call=True
)
def export_poses_to_csv(n_clicks):
    """저장된 포즈들을 CSV로 내보내기"""
    if not n_clicks:
        return no_update
    
    try:
        # 저장된 포즈 데이터 가져오기
        saved_poses = grpc_data_manager.get_saved_poses()
        
        if not saved_poses:
            return dbc.Alert("⚠️ 내보낼 포즈 데이터가 없습니다.", color="warning", duration=3000)
        
        # CSV 파일로 저장
        filename = f"saved_poses_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        
        # pandas DataFrame 생성
        records = []
        for pose in saved_poses:
            record = {
                "pose_name": pose.get("name", "Unknown"),
                "timestamp": pose.get("timestamp", 0),
                "datetime": pose.get("datetime", "Unknown")
            }
            
            # 각도 데이터 추가 (14개 모터)
            angles = pose.get("angles", [])
            for i in range(14):
                if i < len(angles):
                    record[f"joint_{i+1}_rad"] = angles[i]
                    record[f"joint_{i+1}_deg"] = angles[i] * 180 / 3.14159
                else:
                    record[f"joint_{i+1}_rad"] = 0.0
                    record[f"joint_{i+1}_deg"] = 0.0
            
            records.append(record)
        
        df = pd.DataFrame(records)
        
        # log 폴더 생성 확인
        log_folder = "log"
        if not os.path.exists(log_folder):
            os.makedirs(log_folder)
        
        filepath = os.path.join(log_folder, filename)
        df.to_csv(filepath, index=False)
        
        file_size = os.path.getsize(filepath)
        
        return dbc.Alert(
            f"📊 CSV 내보내기 완료: {filename} ({len(saved_poses)}개 포즈, {file_size/1024:.1f}KB)", 
            color="success", 
            duration=5000
        )
        
    except Exception as e:
        print(f"[ERROR] CSV 내보내기 실패: {e}")
        return dbc.Alert(f"❌ CSV 내보내기 실패: {str(e)}", color="danger", duration=3000)