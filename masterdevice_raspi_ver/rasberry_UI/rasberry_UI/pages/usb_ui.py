# pages/usb_ui.py - 선택적 오버레이 적용 (Device ON/OFF 버튼과 Encoder List는 제외)
from dash import html, dcc, Input, Output, State, callback, ctx
import dash_bootstrap_components as dbc
import threading
import serial
import time
import os
import json
import struct
import csv
from datetime import datetime
import grpc
from concurrent import futures
from collections import deque

# 키보드 입력을 위한 라이브러리
try:
    from pynput import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

# master_ui.py의 설정들
FRAME_HEADER1 = 0xAA
FRAME_HEADER2 = 0xBB
NUM_JOINTS = 7
ENC_DATA_SIZE = NUM_JOINTS * 2 * 4
FRAME_SIZE = 2 + 1 + ENC_DATA_SIZE + 2

SAVE_DIR = r"C:\Users\wntlr\Desktop\UI_test\log"
os.makedirs(SAVE_DIR, exist_ok=True)

# 전역 변수들
shared_ser = None  # 단일 시리얼 연결
BAUDRATE = 4_000_000
current_usb_port = None  # 추가: 현재 USB 포트 저장
device_active = True  # 🆕 Device ON/OFF 상태 관리

# 빠른 UI 표시용 최근 프레임 버퍼(문자열) + 통계
recent_frames = deque(maxlen=60)  # 약 1~1.2초치
stats_lock = threading.Lock()
stats = {
    'last_ts': 0.0,
    'ema_interval_ms': None,  # 지수이동평균 인터벌(ms)
    'fps': 0.0
}

# COMPLETE 메시지 저장용 전역 변수 (추가)
complete_messages = []
complete_messages_lock = threading.Lock()

# 키보드 상태 변수 (완전한 토글 방식) - 키 매핑 변경: 1번 키 → 오른팔, 4번 키 → 왼팔
keyboard_state = {
    '1': False,  # 오른팔 토글 (변경됨)
    '2': False,  # 레코딩 토글
    '3': False,  # 왼팔 푸시2
    '4': False,  # 왼팔 토글 (변경됨)
    '5': False,  # 오른팔 푸시1 -> 클리어
    '6': False   # 오른팔 푸시2
}

# 이전 키보드 상태 (토글 감지용)
prev_keyboard_state = {
    '1': False, '2': False, '3': False,
    '4': False, '5': False, '6': False
}

# 키 물리적 상태 추적 (키 반복 방지)
key_physically_pressed = {
    '1': False, '2': False, '3': False,
    '4': False, '5': False, '6': False
}

# 기존 변수들
switch_state = {
    'R_toggle': '1', 'R_push_1': '1', 'R_push_2': '1',
    'L_toggle': '1', 'L_push_1': '1', 'L_push_2': '1'
}
prev_switch_state = {
    'R_toggle': '1', 'R_push_1': '1', 'R_push_2': '1',
    'L_toggle': '1', 'L_push_1': '1', 'L_push_2': '1'
}
latest_enc_R = [0] * NUM_JOINTS  # 오른팔 엔코더
latest_enc_L = [0] * NUM_JOINTS  # 왼팔 엔코더
recorded_encoders = []
recording_active = False  # 확실히 False로 시작
keyboard_active = False
serial_thread_active = False
last_frame_time = 0
frame_intervals = []
latest_param = []
new_grpc_data = False
lock = threading.Lock()

# 명령 이력 추적 (추가)
command_history = []

# ===== Device ON/OFF 상태 관리 함수들 =====
def set_device_active(active):
    """Device 활성화 상태 설정"""
    global device_active
    device_active = active
    print(f"[DEBUG] Device active state changed to: {active}")

def get_device_active():
    """Device 활성화 상태 반환"""
    global device_active
    return device_active

# ===== 키보드 입력 처리 함수들 =====
def send_keyboard_state():
    """현재 키보드 상태를 OpenCR에 전송"""
    global shared_ser, device_active
    
    # 🆕 Device가 비활성화된 경우 키보드 명령 차단
    if not device_active:
        print("[DEBUG] Device is inactive - keyboard commands blocked")
        return
        
    if shared_ser and shared_ser.is_open:
        try:
            # "KEY:123456" 형식으로 전송
            state_str = "KEY:"
            for key in ['1', '2', '3', '4', '5', '6']:
                state_str += '1' if keyboard_state[key] else '0'
            state_str += '\n'
            
            shared_ser.write(state_str.encode())
            
            # 명령 이력 기록
            log_command(state_str.strip(), True, "키보드 상태 전송")
            
        except Exception as e:
            log_command("KEY_STATE", False, str(e))

def handle_special_key_functions(key_char, is_press=True):
    """특수 키 기능 처리 (레코딩, 클리어 등)"""
    global recording_active, recorded_encoders, device_active
    
    # 🆕 Device가 비활성화된 경우 특수 기능 차단
    if not device_active:
        return
    
    if key_char == '2' and is_press:  # 2번 키: 레코딩 토글 (키를 누를 때만)
        # 키 상태에 따라 레코딩 상태 설정
        recording_active = keyboard_state['2']
    
    elif key_char == '5' and is_press:  # 5번 키: 클리어 (키를 누를 때만)
        count = len(recorded_encoders)
        with lock:
            recorded_encoders.clear()

def on_key_press(key):
    """키보드 눌림 이벤트 (키별 다른 동작 방식)"""
    global keyboard_state, prev_keyboard_state, key_physically_pressed, device_active
    
    # 🆕 Device가 비활성화된 경우 키보드 입력 무시
    if not device_active:
        return
    
    try:
        # 숫자 키 1-6만 처리
        if hasattr(key, 'char') and key.char in ['1', '2', '3', '4', '5', '6']:
            # 이미 물리적으로 눌린 상태면 무시 (키 반복 방지)
            if key_physically_pressed[key.char]:
                return
            
            # 물리적 키 상태 업데이트
            key_physically_pressed[key.char] = True
            
            # 이전 상태 저장
            prev_keyboard_state[key.char] = keyboard_state[key.char]
            
            # 키별 다른 동작 방식 (1번 키 → 오른팔, 4번 키 → 왼팔)
            if key.char in ['1', '2', '4']:  # 토글 키들 (1: 오른팔, 2: 레코딩, 4: 왼팔)
                # 토글: 상태 반전
                keyboard_state[key.char] = not keyboard_state[key.char]
                
                # 특수 기능 처리 (토글 변화 시)
                if key.char == '2':
                    handle_special_key_functions(key.char, is_press=True)
                    
            elif key.char in ['3', '5', '6']:  # 푸시 키들
                # 푸시: 누르는 동안 ON
                keyboard_state[key.char] = True
                
                # 특수 기능 처리 (푸시 시)
                if key.char == '5':
                    handle_special_key_functions(key.char, is_press=True)
            
            # OpenCR에 상태 전송
            send_keyboard_state()
                
    except Exception as e:
        pass

def on_key_release(key):
    """키보드 릴리즈 이벤트"""
    global key_physically_pressed, keyboard_state, device_active
    
    # 🆕 Device가 비활성화된 경우 키보드 입력 무시
    if not device_active:
        return
    
    try:
        # 숫자 키 1-6만 처리
        if hasattr(key, 'char') and key.char in ['1', '2', '3', '4', '5', '6']:
            # 물리적 키 상태 업데이트
            key_physically_pressed[key.char] = False
            
            # 푸시 키들은 키를 떼면 OFF
            if key.char in ['3', '5', '6']:
                if keyboard_state[key.char]:  # 현재 ON 상태라면
                    keyboard_state[key.char] = False
                    # OpenCR에 상태 전송
                    send_keyboard_state()
                
    except Exception as e:
        pass

# ===== 엔코더 리더 함수들 =====
def find_frame_start(ser):
    """프레임 시작점 찾기"""
    for _ in range(500):
        byte1 = ser.read(1)
        if byte1 and byte1[0] == FRAME_HEADER1:
            byte2 = ser.read(1)
            if byte2 and byte2[0] == FRAME_HEADER2:
                return True
    return False

def read_encoder_frame(ser):
    """엔코더 프레임 읽기"""
    try:
        if not find_frame_start(ser):
            return None
        
        # 나머지 59바이트 읽기 (스위치1 + 데이터56 + CRC2)
        data = ser.read(FRAME_SIZE - 2)
        if len(data) != FRAME_SIZE - 2:
            return None
        
        # 스위치 상태 (앞 1바이트)
        switch_state = data[0]
        
        # 엔코더 데이터 (다음 56바이트)
        encoder_data = data[1:1+ENC_DATA_SIZE]
        
        # CRC (마지막 2바이트)
        crc_received = struct.unpack('<H', data[1+ENC_DATA_SIZE:1+ENC_DATA_SIZE+2])[0]
        crc_calc = sum(data[0:1+ENC_DATA_SIZE]) & 0xFFFF
        if crc_received != crc_calc:
            return None
        
        # 14개 uint32 해석 - 순서 변경: 처음 7개가 왼팔, 다음 7개가 오른팔
        values = struct.unpack('<14I', encoder_data)
        left_arm = list(values[:7])   # 처음 7개 → 왼팔 (변경됨)
        right_arm = list(values[7:])  # 다음 7개 → 오른팔 (변경됨)
        
        return {
            'timestamp': time.time(),
            'switch': switch_state,
            'right_arm': right_arm,
            'left_arm': left_arm
        }
    except Exception as e:
        return None

def serial_communication_thread(port):
    """단일 리더: 바이너리 프레임(AA BB … 61B) 우선 파싱 + 텍스트 상태 메시지 병행 - 왼팔↔오른팔 수정"""
    global shared_ser, serial_thread_active, recorded_encoders, latest_enc_R, latest_enc_L
    global complete_messages, recording_active

    try:
        shared_ser = serial.Serial(port, BAUDRATE, timeout=0.01)  # 기존 BAUDRATE 그대로
        serial_thread_active = True

        buf = bytearray()
        FRAME_HDR = b'\xAA\xBB'
        FRAME_LEN = FRAME_SIZE  # 61 = 2 + 1 + 56 + 2

        while serial_thread_active:
            try:
                n = shared_ser.in_waiting
                if n:
                    chunk = shared_ser.read(n)
                    if not chunk:
                        time.sleep(0.001)
                        continue
                    buf.extend(chunk)

                    # 1) 바이너리 프레임 우선 파싱
                    while True:
                        i = buf.find(FRAME_HDR)
                        if i < 0:
                            break
                        if len(buf) - i < FRAME_LEN:
                            break  # 프레임 미완성 → 다음 루프

                        frame = bytes(buf[i:i+FRAME_LEN])
                        del buf[:i+FRAME_LEN]  # 소비

                        # frame = [AA,BB, sw(1), enc(56), crc(2)]
                        sw = frame[2]
                        enc = frame[3:3+ENC_DATA_SIZE]  # 56B
                        crc_rx = int.from_bytes(frame[-2:], 'little')
                        crc_calc = sum(frame[2:2+1+ENC_DATA_SIZE]) & 0xFFFF
                        if crc_rx != crc_calc:
                            # CRC 불일치 → 폐기
                            continue

                        try:
                            values = struct.unpack('<14I', enc)
                        except struct.error:
                            continue

                        # 엔코더 데이터 순서 변경: 처음 7개가 왼팔, 다음 7개가 오른팔
                        left_arm = list(values[:7])   # 처음 7개 → 왼팔 (변경됨)
                        right_arm = list(values[7:])  # 다음 7개 → 오른팔 (변경됨)
                        ts = time.time()

                        with lock:
                            # 최신값은 항상 갱신 (UI 실시간 표시용)
                            latest_enc_L = left_arm   # 왼팔 (변경됨)
                            latest_enc_R = right_arm  # 오른팔 (변경됨)
                            # 레코딩 중일 때만 적재
                            if recording_active:
                                recorded_encoders.append({
                                    'timestamp': ts,
                                    'left_arm': left_arm,   # 왼팔 (변경됨)
                                    'right_arm': right_arm  # 오른팔 (변경됨)
                                })

                        # 통신 상태는 항상 업데이트
                        with stats_lock:
                            if stats['last_ts'] != 0.0:
                                dt = (ts - stats['last_ts']) * 1000.0  # ms
                                if stats['ema_interval_ms'] is None:
                                    stats['ema_interval_ms'] = dt
                                else:
                                    alpha = 0.2
                                    stats['ema_interval_ms'] = (1 - alpha) * stats['ema_interval_ms'] + alpha * dt
                                if stats['ema_interval_ms'] > 0:
                                    stats['fps'] = 1000.0 / stats['ema_interval_ms']
                            stats['last_ts'] = ts

                        # 엔코더 값은 항상 UI에 표시 - 표시 순서 변경 (Right가 먼저)
                        ts_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S.%f')[:-3]
                        right_str = ', '.join(f'{x:4d}' for x in right_arm)  # 오른팔이 위로 (변경됨)
                        left_str  = ', '.join(f'{x:4d}' for x in left_arm)   # 왼팔이 아래로 (변경됨)
                        line = f'[{ts_str}]\nRight : [{right_str}]\nLeft  : [{left_str}]\n'

                        with stats_lock:
                            recent_frames.append(line)

                    # 2) 남은 버퍼에서 텍스트 라인('\n') 파싱
                    while True:
                        nl = buf.find(b'\n')
                        if nl < 0:
                            break
                        line = buf[:nl+1].decode('utf-8', errors='ignore').strip()
                        del buf[:nl+1]
                        if not line:
                            continue

                        # COMPLETE/상태 메시지만 저장
                        if any(k in line for k in ['COMPLETE','START','MOVING','REACHED','ERROR','TIMEOUT','BLOCKED']):
                            with complete_messages_lock:
                                complete_messages.append({'message': line, 'timestamp': time.time()})
                                if len(complete_messages) > 30:
                                    complete_messages[:] = complete_messages[-30:]
                            log_command("RECEIVED", True, line)

                time.sleep(0.001)

            except Exception as e:
                # 과도한 로그 방지
                time.sleep(0.01)

        if shared_ser and shared_ser.is_open:
            shared_ser.close()

    except Exception as e:
        serial_thread_active = False

# ===== 기타 함수들 (생략 - 기존과 동일) =====
def get_recent_complete_messages():
    """최근 COMPLETE 메시지들을 반환"""
    with complete_messages_lock:
        current_time = time.time()
        # 30초 이내의 메시지만 반환
        recent = [msg for msg in complete_messages 
                 if current_time - msg['timestamp'] < 30]
        return recent.copy()

def start_keyboard_listener(port):
    """키보드 리스너 및 시리얼 통신 시작"""
    global keyboard_active
    
    if not KEYBOARD_AVAILABLE:
        return
    
    try:
        # 시리얼 통신 스레드 시작
        serial_thread = threading.Thread(target=serial_communication_thread, args=(port,), daemon=True)
        serial_thread.start()
        
        # 시리얼 연결 대기
        time.sleep(1)
        
        keyboard_active = True
    
        
        # 키보드 리스너 생성 및 시작
        listener = keyboard.Listener(
            on_press=on_key_press,
            on_release=on_key_release
        )
        listener.start()
        
        # 리스너가 활성 상태로 유지
        while keyboard_active:
            time.sleep(0.1)
            
        listener.stop()
        
    except Exception as e:
        keyboard_active = False

def stop_keyboard_listener():
    """키보드 리스너 및 시리얼 통신 중지"""
    global keyboard_active, serial_thread_active
    keyboard_active = False
    serial_thread_active = False

# UI 버튼용 엔코더 녹화 (기존 방식 유지)
def encoder_recording_thread_ui(port):
    """단일 리더 사용: 포트 재오픈 금지. 녹화 플래그 유지용 루프만."""
    global recording_active
    while recording_active:
        time.sleep(0.05)

# ===== app.py용 상태 접근 함수들 =====
def get_keyboard_state():
    """키보드 상태 반환 (app.py에서 사용)"""
    global keyboard_state
    return keyboard_state.copy()  # 복사본 반환으로 안전성 확보

def get_serial_connection():
    """시리얼 연결 객체 반환 (app.py에서 사용)"""
    global shared_ser
    return shared_ser

def get_current_port():
    """현재 USB 포트 반환 (app.py에서 사용)"""
    global current_usb_port
    return current_usb_port

def get_baudrate():
    """보드레이트 반환"""
    return BAUDRATE

def get_serial_status():
    """시리얼 연결 상태 상세 정보 반환"""
    global shared_ser, serial_thread_active, keyboard_active
    
    status = {
        'connected': shared_ser is not None and shared_ser.is_open if shared_ser else False,
        'port': current_usb_port,
        'thread_active': serial_thread_active,
        'keyboard_active': keyboard_active,
        'baudrate': BAUDRATE if shared_ser else None
    }
    
    return status

def send_command_safely(command):
    """안전한 명령 전송 함수 (app.py에서 사용 가능)"""
    global shared_ser
    
    if not shared_ser or not shared_ser.is_open:
        return False, "시리얼 연결이 없습니다"
    
    try:
        if not command.endswith('\n'):
            command += '\n'
        
        bytes_written = shared_ser.write(command.encode())
        shared_ser.flush()
        
        log_command(command.strip(), True, f"{bytes_written} bytes 전송")
        return True, f"명령 전송 성공: {bytes_written} bytes"
    except Exception as e:
        log_command(command.strip(), False, str(e))
        return False, f"명령 전송 실패: {e}"

def log_command(command, success, response=""):
    """명령 실행 이력 로깅"""
    global command_history
    
    entry = {
        'timestamp': datetime.now(),
        'command': command,
        'success': success,
        'response': response
    }
    
    command_history.append(entry)
    
    # 최근 100개만 유지
    if len(command_history) > 100:
        command_history = command_history[-100:]

def get_command_history():
    """명령 이력 반환"""
    return command_history.copy()

def get_recent_serial_messages():
    """최근 시리얼 메시지들을 반환"""
    # 여기서는 실제 시리얼 통신을 모니터링하는 대신
    # command_history에서 최근 응답을 확인합니다
    recent_messages = []
    
    current_time = time.time()
    for entry in command_history[-10:]:  # 최근 10개 명령만 확인
        if current_time - entry['timestamp'].timestamp() < 30:  # 30초 이내
            if entry['success'] and 'response' in entry:
                recent_messages.append({
                    'command': entry['command'],
                    'response': entry['response'],
                    'timestamp': entry['timestamp'].timestamp()
                })
    
    return recent_messages

def check_for_complete_messages():
    """COMPLETE 메시지 확인"""
    # 실제 구현에서는 시리얼 포트에서 직접 읽어야 하지만,
    # 여기서는 시뮬레이션으로 처리
    global shared_ser
    
    complete_messages = []
    if shared_ser and shared_ser.is_open:
        try:
            # 시리얼 버퍼에서 데이터 읽기 시도
            if shared_ser.in_waiting > 0:
                data = shared_ser.read(shared_ser.in_waiting).decode('utf-8', errors='ignore')
                lines = data.split('\n')
                for line in lines:
                    line = line.strip()
                    if 'COMPLETE' in line:
                        complete_messages.append(line)
        except Exception as e:
            pass
    
def get_system_summary():
    """전체 시스템 상태 요약"""
    keyboard_status = get_keyboard_state()
    serial_status = get_serial_status()
    
    summary = {
        'overall_status': 'OK' if serial_status['connected'] else 'ERROR',
        'serial': serial_status,
        'keyboard': keyboard_status,
        'gravity_mode': {
            'right_arm': keyboard_status.get('1', False),  # 1번 키 → 오른팔 (변경됨)
            'left_arm': keyboard_status.get('4', False)    # 4번 키 → 왼팔 (변경됨)
        },
        'recording_active': recording_active,
        'command_count': len(command_history)
    }
    
    return summary

# 🆕 수정된 레이아웃 - Device ON/OFF 버튼과 Encoder List는 항상 활성화
layout = html.Div([
    # 🟢 헤더 - 항상 활성화 (Device ON/OFF 버튼들)
    html.Div([
        # 좌측: 로고 및 제목
        html.Div([
            html.Img(src="/assets/Neuro_Meka.png", style={'height': '60px'}),
            html.H2("Neuro Meka Master device",
                    style={'color': '#7c8bc7', 'fontWeight': 'bold', 'marginLeft': '20px'})
        ], style={'display': 'flex', 'alignItems': 'center'}),
        
        # 우측: Device ON/OFF 버튼들 - 항상 활성화
        html.Div([
            dbc.Button([
                html.I(className="fas fa-play", style={'marginRight': '8px'}),
                "Device ON"
            ], 
            id="device-on-btn", 
            color="success", 
            size="lg",
            className="me-3",
            style={
                'fontWeight': 'bold',
                'borderRadius': '10px',
                'padding': '10px 20px',
                'boxShadow': '0 4px 8px rgba(0,0,0,0.2)',
                'transition': 'all 0.3s ease'
            }),
            dbc.Button([
                html.I(className="fas fa-power-off", style={'marginRight': '8px'}),
                "Device OFF"
            ], 
            id="device-off-btn", 
            color="warning", 
            size="lg",
            style={
                'fontWeight': 'bold',
                'borderRadius': '10px',
                'padding': '10px 20px',
                'boxShadow': '0 4px 8px rgba(0,0,0,0.2)',
                'transition': 'all 0.3s ease'
            })
        ], style={'display': 'flex', 'alignItems': 'center'})
        
    ], style={
        'display': 'flex', 
        'alignItems': 'center',
        'justifyContent': 'space-between',
        'borderBottom': '2px solid #ccc', 
        'paddingBottom': '10px',
        'marginBottom': '20px'
    }),

    # 🔴 제어 가능한 섹션들 (Device OFF 시 오버레이가 적용될 영역)
    html.Div(id="controllable-sections", 
        style={'position': 'relative'},  # 상대적 위치 설정으로 오버레이 적용 준비
        children=[
            # 실시간 키보드 상태 패널
            dbc.Card([
                dbc.CardHeader(html.H5("🎹 실시간 버튼 상태", className="mb-0")),
                dbc.CardBody([
                    html.Div([
                        html.Div(id="keyboard-status-display", 
                                style={'fontFamily': 'monospace', 'fontSize': '1.1em', 'padding': '15px',
                                       'backgroundColor': '#f8f9fa', 'borderRadius': '8px'})
                    ])
                ])
            ], className="mt-4"),

            # 팔 상태 표시
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("오른팔 상태"),  # 변경됨: 왼팔 → 오른팔
                        dbc.CardBody([
                            html.Div([
                                html.Span(id="led-right-pos", style={'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#888'}, className="me-2"),
                                html.Span("Position Control", id="pos-right", style={'color': '#6c757d', 'fontSize': '1.4em'})
                            ], className="d-flex align-items-center mb-2"),
                            html.Div([
                                html.Span(id="led-right-grav", style={'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#888'}, className="me-2"),
                                html.Span("Gravity Control", id="grav-right", style={'color': '#6c757d', 'fontSize': '1.4em'})
                            ], className="d-flex align-items-center")
                        ])
                    ], className="h-100"),
                    xs=12, md=6
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("왼팔 상태"),  # 변경됨: 오른팔 → 왼팔
                        dbc.CardBody([
                            html.Div([
                                html.Span(id="led-left-pos", style={'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#888'}, className="me-2"),
                                html.Span("Position Control", id="pos-left", style={'color': '#6c757d', 'fontSize': '1.4em'})
                            ], className="d-flex align-items-center mb-2"),
                            html.Div([
                                html.Span(id="led-left-grav", style={'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#888'}, className="me-2"),
                                html.Span("Gravity Control", id="grav-left", style={'color': '#6c757d', 'fontSize': '1.4em'})
                            ], className="d-flex align-items-center")
                        ])
                    ], className="h-100"),
                    xs=12, md=6
                ),
            ], className="g-3 mt-3"),

            # 중력보상 체크 알림 영역
            html.Div([
                html.Div(id="gravity-check-alert", style={'marginTop': '15px'})
            ]),

            # 홈 제어 및 페어링
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("Home Control"),
                        dbc.CardBody(
                            html.Div([
                                dbc.Button("Go to Home", id="go-home-btn", color="info", size="lg", style={'fontSize': '1.4em'})
                            ], className="d-flex align-items-center")
                        )
                    ], className="h-100"),
                    xs=12, md=6
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader("Master Device Pairing"),
                        dbc.CardBody([
                            html.Span(id="pairing-indicator", style={'display':'inline-block','width':'12px','height':'12px','borderRadius':'50%','backgroundColor':'#888'}, className="me-2"),
                            dbc.Button("Pair", id="pairing-btn", color="secondary", style={'fontSize': '1.4em'}),
                            html.Div(id="grpc-enc-display", className="ms-4", style={'fontFamily':'monospace','whiteSpace':'pre'})
                        ])
                    ], className="h-100"),
                    xs=12, md=6
                ),
            ], className="g-3 mt-3"),

            # 🆕 선택적 오버레이 (controllable-sections 내부에 위치)
            html.Div(id="selective-overlay", 
                children=[
                    html.Div([
                        html.H2("🔌 DEVICE OFF", style={'color': 'white', 'textAlign': 'center', 'marginBottom': '20px'}),
                        html.P("Device ON 버튼을 눌러 활성화하세요", style={'color': 'white', 'textAlign': 'center', 'fontSize': '1.2em'}),
                        html.P("키보드 제어 및 로봇 제어가 비활성화되었습니다", style={'color': '#ccc', 'textAlign': 'center', 'fontSize': '1em'})
                    ], style={
                        'position': 'absolute',
                        'top': '50%',
                        'left': '50%',
                        'transform': 'translate(-50%, -50%)',
                        'textAlign': 'center',
                        'zIndex': '1001'
                    })
                ],
                style={
                    'display': 'none',  # 기본적으로 숨김
                    'position': 'absolute',
                    'top': '0',
                    'left': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0, 0, 0, 0.75)',
                    'zIndex': '1000',
                    'borderRadius': '10px'
                }
            ),
        ]
    ),

    # 🟢 Encoder List - 항상 활성화된 영역 (오버레이 영향 없음)
    dbc.Card([
        dbc.CardHeader(html.H5("Encoder List", className="mb-0")),
        dbc.CardBody([
            html.Div([
                html.Span("🎮 Hardware Controls", style={'fontWeight': 'bold'}),
            ], style={'marginBottom': '10px', 'padding': '5px', 'backgroundColor': '#f8f9fa', 'borderRadius': '3px'}),
            
            html.Div([
                html.Div([
                    dbc.Button("Recording", id="save-btn", color="primary", className="me-2"),
                    dbc.Button("Clear", id="clear-btn", color="danger", className="me-2"),
                    dbc.Button("Save As", id="save-as-btn", color="secondary", className="me-2"),
                ], style={'display': 'flex', 'alignItems': 'center'}),
                
                html.Div([
                    html.Span(id="total-data-count", 
                             style={
                                 'fontSize': '1.2em', 
                                 'fontWeight': 'bold', 
                                 'color': '#007bff',
                                 'backgroundColor': '#e3f2fd',
                                 'padding': '8px 16px',
                                 'borderRadius': '20px',
                                 'border': '2px solid #2196f3'
                             })
                ], style={'display': 'flex', 'alignItems': 'center'})
            ], style={
                'display': 'flex', 
                'justifyContent': 'space-between', 
                'alignItems': 'center',
                'marginBottom': '15px'
            }),
            
            html.Div(id="action-status-display", style={'marginTop': '10px', 'marginBottom': '10px'}),
            html.Hr(),
            
            html.Div([
                html.Span("📊 Communication: ", style={'fontWeight': 'bold'}),
                html.Span(id="comm-fps", children="0 FPS", style={'color': 'green', 'fontWeight': 'bold'}),
                html.Span(" | Interval: "),
                html.Span(id="comm-interval", children="0ms", style={'color': 'blue'}),
                html.Span(" | Recording: "),
                html.Span(id="recording-status", children="STOPPED", style={'color': 'red', 'fontWeight': 'bold'}),
                html.Span(" | Serial: "),
                html.Span(id="serial-status", children="DISCONNECTED", style={'color': 'gray', 'fontWeight': 'bold'}),
            ], style={'marginBottom': '15px', 'fontSize': '0.9em', 'color': '#666'}),
            
            html.Div(id="encoder-list-display", 
                    style={
                        'height': '280px', 
                        'overflowY': 'auto',
                        'fontFamily': 'monospace', 
                        'fontSize': '1.1em',
                        'lineHeight': '1.4',
                        'backgroundColor': '#f8f9fa',
                        'padding': '15px',
                        'borderRadius': '8px',
                        'border': '1px solid #dee2e6'
                    })
        ])
    ], className="mt-4"),

    # Store들
    dcc.Store(id="device-on-status", data={'blinking': False, 'timestamp': 0}),
    dcc.Store(id="device-off-status", data={'blinking': False, 'timestamp': 0}),
    dcc.Store(id="go-home-status", data={'blinking': False, 'timestamp': 0}),
    dcc.Store(id="status-messages", data={'clear': [], 'save': []}),
    dcc.Store(id="device-state", data={'active': True}),  # 🆕 Device 상태 Store

    # 기타 요소들
    dcc.Store(id="grpc-entries", data=[]),
    dcc.Interval(id="interval", interval=100, n_intervals=0),  # 20ms → 100ms로 변경
    html.Div(id="connection-health-monitor", style={'display': 'none'}),
    html.Div(id="debug-info-display", style={'display': 'none'}),
    
    html.Br(),
    dcc.Link("← USB 메뉴로 돌아가기", href="/usb", className="btn btn-link")
], style={'padding': '20px'})

# ===== 콜백들 =====

# 🆕 Device ON/OFF 상태에 따른 선택적 오버레이 제어 (중력보상 체크 추가)
@callback(
    [Output("selective-overlay", "style"),
     Output("device-state", "data")],
    [Input("device-on-btn", "n_clicks"),
     Input("device-off-btn", "n_clicks")],
    [State("device-state", "data")],
    prevent_initial_call=True
)
def handle_selective_overlay_control(on_clicks, off_clicks, current_state):
    """Device ON/OFF 버튼에 따른 선택적 오버레이 제어 - 중력보상 모드 체크 추가"""
    if not ctx.triggered:
        return {'display': 'none'}, {'active': True}
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == "device-on-btn" and on_clicks:
        # Device ON: 오버레이 숨김, UI 활성화
        set_device_active(True)
        overlay_style = {'display': 'none'}
        print("[DEBUG] Device ON - Overlay hidden, UI activated")
        return overlay_style, {'active': True}
    
    elif trigger_id == "device-off-btn" and off_clicks:
        # 🆕 중력보상 모드 체크 (app.py와 동일한 로직)
        global keyboard_state
        
        right_arm_gravity = keyboard_state.get('1', False)  # 1번 키 → 오른팔
        left_arm_gravity = keyboard_state.get('4', False)   # 4번 키 → 왼팔
        
        print(f"[DEBUG] Overlay control - Gravity check - Right: {right_arm_gravity}, Left: {left_arm_gravity}")
        
        # 🚫 중력보상 모드가 활성화되어 있으면 오버레이 활성화 차단
        if right_arm_gravity or left_arm_gravity:
            gravity_arms = []
            if right_arm_gravity:
                gravity_arms.append("오른팔")
            if left_arm_gravity:
                gravity_arms.append("왼팔")
            
            arms_text = ", ".join(gravity_arms)
            print(f"[DEBUG] Device OFF overlay blocked - {arms_text} in gravity mode")
            
            # 오버레이 활성화하지 않고 현재 상태 유지
            return {'display': 'none'}, current_state or {'active': True}
        
        # ✅ 양쪽 팔이 모두 Position Control 모드일 때만 오버레이 활성화
        set_device_active(False)
        overlay_style = {
            'display': 'block',
            'position': 'absolute',
            'top': '0',
            'left': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0, 0, 0, 0.75)',
            'zIndex': '1000',
            'borderRadius': '10px'
        }
        print("[DEBUG] Device OFF - Selective overlay shown, controls disabled (both arms in position control)")
        return overlay_style, {'active': False}
    
    # 기본값
    return {'display': 'none'}, current_state or {'active': True}

# 자동 키보드 제어 및 상태 업데이트 - Device 상태 반영
@callback(
    Output("keyboard-status-display", "children"),
    Input("interval", "n_intervals"),
    [State("usb-port-store", "data"),
     State("device-state", "data")],
    prevent_initial_call=True
)
def auto_start_keyboard_and_update_status(n_intervals, port_data, device_state):
    """자동으로 키보드 제어를 시작하고 실시간 상태를 업데이트 - Device 상태 반영"""
    try:
        global keyboard_state, keyboard_active, current_usb_port, device_active
        
        # Device 상태 동기화
        if device_state and 'active' in device_state:
            device_active = device_state['active']
            
        # 포트 정보 업데이트
        if port_data and current_usb_port != port_data:
            current_usb_port = port_data
        
        # 첫 3번 실행 시에만 키보드 제어 자동 시작 체크 (50ms * 3 = 150ms)
        if n_intervals <= 3 and port_data and not keyboard_active and KEYBOARD_AVAILABLE:
            try:
                thread = threading.Thread(target=start_keyboard_listener, args=(port_data,), daemon=True)
                thread.start()
            except:
                pass
        
        # 🆕 Device가 비활성화된 경우
        if not device_active:
            return html.Div([
                html.Div("🔌 DEVICE OFF - 키보드 제어 비활성화됨", 
                        style={'color': 'red', 'textAlign': 'center', 'fontWeight': 'bold', 'fontSize': '1.2em'}),
                html.Div("Device ON 버튼을 눌러 활성화하세요", 
                        style={'color': 'gray', 'textAlign': 'center', 'fontSize': '1em', 'marginTop': '5px'})
            ])
        
        # 키보드 상태가 활성화되지 않은 경우
        if not keyboard_active:
            if not KEYBOARD_AVAILABLE:
                return html.Div([
                    html.Div("❌ pynput 라이브러리가 설치되지 않았습니다.", 
                            style={'color': 'red', 'textAlign': 'center', 'fontWeight': 'bold'}),
                    html.Div("'pip install pynput'를 실행해주세요.", 
                            style={'color': 'red', 'textAlign': 'center', 'fontSize': '0.9em'})
                ])
            elif not port_data:
                return html.Div("⚠️ USB 포트가 연결되지 않았습니다.", 
                               style={'color': 'orange', 'textAlign': 'center', 'fontWeight': 'bold'})
            else:
                return html.Div("🔄 키보드 제어 초기화 중...", 
                               style={'color': 'blue', 'textAlign': 'center'})
        
        # 키 상태 표시 (성능 최적화) - 텍스트 수정 (1번 키 → 오른팔, 4번 키 → 왼팔)
        status_elements = [
            html.Div([
                html.Span("🤲 오른팔: ", style={'fontWeight': 'bold', 'marginRight': '15px'}),  # 변경: 왼팔 → 오른팔
                html.Span("🟢 ON" if keyboard_state.get('1', False) else "🔴 OFF", 
                         style={'color': 'green' if keyboard_state.get('1', False) else 'red', 'marginRight': '15px', 'fontWeight': 'bold'}),
                html.Span("🔴 REC" if keyboard_state.get('2', False) else "⏸️ STOP", 
                         style={'color': 'red' if keyboard_state.get('2', False) else 'gray', 'marginRight': '15px', 'fontWeight': 'bold'}),
                html.Span("🟡 PUSH" if keyboard_state.get('3', False) else "⭕ OFF", 
                         style={'color': 'orange' if keyboard_state.get('3', False) else 'gray', 'fontWeight': 'bold'})
            ], style={'marginBottom': '10px'}),
            
            html.Div([
                html.Span("🤲 왼팔: ", style={'fontWeight': 'bold', 'marginRight': '15px'}),  # 변경: 오른팔 → 왼팔
                html.Span("🟢 ON" if keyboard_state.get('4', False) else "🔴 OFF", 
                         style={'color': 'green' if keyboard_state.get('4', False) else 'red', 'marginRight': '15px', 'fontWeight': 'bold'}),
                html.Span("🟡 PUSH" if keyboard_state.get('5', False) else "⭕ OFF", 
                         style={'color': 'orange' if keyboard_state.get('5', False) else 'gray', 'marginRight': '15px', 'fontWeight': 'bold'}),
                html.Span("🟡 PUSH" if keyboard_state.get('6', False) else "⭕ OFF", 
                         style={'color': 'orange' if keyboard_state.get('6', False) else 'gray', 'fontWeight': 'bold'})
            ])
        ]
        
        return html.Div(status_elements)
        
    except Exception:
        return html.Div("⚠️ 상태 업데이트 중...", style={'textAlign': 'center', 'color': 'gray'})

# 통합된 버튼 이벤트 처리 콜백 + Device 상태 반영
@callback(
    [Output("save-btn", "children"),
     Output("save-btn", "color"),
     Output("recording-status", "children"),
     Output("recording-status", "style"),
     Output("action-status-display", "children"),
     Output("status-messages", "data")],
    [Input("save-btn", "n_clicks"),
     Input("clear-btn", "n_clicks"),
     Input("save-as-btn", "n_clicks")],
    [State("usb-port-store", "data"),
     State("save-btn", "children"),
     State("status-messages", "data"),
     State("device-state", "data")],  # 🆕 Device 상태 추가
    prevent_initial_call=True
)
def handle_all_buttons(save_clicks, clear_clicks, save_as_clicks, port_data, current_text, status_data, device_state):
    """모든 버튼 이벤트를 통합 처리 + Device 상태 반영"""
    global recording_active, recorded_encoders, device_active
    
    # Device 상태 동기화
    if device_state and 'active' in device_state:
        device_active = device_state['active']
    
    if not ctx.triggered:
        return ("Recording", "primary", "STOPPED", 
                {'color': 'red', 'fontWeight': 'bold'}, 
                "", status_data if status_data else {'clear': [], 'save': []})
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    btn_text = current_text if current_text else "Recording"
    btn_color = "primary"
    recording_status_text = "STOPPED"
    recording_style = {'color': 'red', 'fontWeight': 'bold'}
    status_display = ""
    new_status_data = status_data if status_data else {'clear': [], 'save': []}
    
    # 🆕 Device가 비활성화된 경우 일부 버튼 동작 허용 (Recording, Clear, Save As는 계속 작동)
    # Device OFF 상태에서도 엔코더 리스트 관련 기능은 사용 가능하도록 수정
    
    if trigger_id == "save-btn":
        if not port_data:
            status_display = dbc.Alert("❌ USB 포트가 연결되지 않았습니다.", color="danger")
        elif current_text == "Recording":
            recording_active = True
           
            
            btn_text = "Stop"
            btn_color = "danger"
            recording_status_text = "RECORDING"
            recording_style = {'color': 'red', 'fontWeight': 'bold'}
            
            if not device_active:
                status_display = dbc.Alert("🔴 녹화 시작됨 (Device OFF 모드)", color="warning")
            else:
                status_display = dbc.Alert("🔴 녹화 시작됨", color="success")
        else:
            recording_active = False
            btn_text = "Recording"
            btn_color = "primary"
            recording_status_text = "STOPPED"
            recording_style = {'color': 'red', 'fontWeight': 'bold'}
            status_display = dbc.Alert("⏹️ 녹화 중지됨", color="info")
    
    elif trigger_id == "clear-btn":
        count = len(recorded_encoders)
        with lock:
            recorded_encoders.clear()
        status_display = dbc.Alert(f"🗑️ 데이터 초기화 완료 ({count}개 항목 삭제)", color="warning")
        if recording_active:
            recording_status_text = "RECORDING"
            recording_style = {'color': 'red', 'fontWeight': 'bold'}
        
    elif trigger_id == "save-as-btn":
        if not recorded_encoders:
            status_display = dbc.Alert("💾 저장할 데이터가 없습니다.", color="warning")
        else:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"encoder_data_{timestamp}.csv"
                filepath = os.path.join(SAVE_DIR, filename)
                
                with lock:
                    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                        # CSV 필드명 순서 변경: 오른팔이 먼저, 왼팔이 나중
                        fieldnames = ['timestamp', 'datetime']
                        
                        for i in range(NUM_JOINTS):
                            fieldnames.append(f'right_joint_{i+1}')  # 오른팔이 먼저 (변경됨)
                        
                        for i in range(NUM_JOINTS):
                            fieldnames.append(f'left_joint_{i+1}')   # 왼팔이 나중 (변경됨)
                        
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()
                        
                        for entry in recorded_encoders:
                            row = {
                                'timestamp': entry['timestamp'],
                                'datetime': datetime.fromtimestamp(entry['timestamp']).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                            }
                            
                            # 오른팔 데이터 먼저 (변경됨)
                            for i in range(NUM_JOINTS):
                                row[f'right_joint_{i+1}'] = entry['right_arm'][i]
                            
                            # 왼팔 데이터 나중 (변경됨)
                            for i in range(NUM_JOINTS):
                                row[f'left_joint_{i+1}'] = entry['left_arm'][i]
                            
                            writer.writerow(row)
                    
                    data_count = len(recorded_encoders)
                    if data_count > 1:
                        duration = recorded_encoders[-1]['timestamp'] - recorded_encoders[0]['timestamp']
                        avg_fps = data_count / duration if duration > 0 else 0
                    else:
                        duration = 0
                        avg_fps = 0
                
                status_display = dbc.Alert([
                    html.P(f"✅ 저장 완료: {filename}"),
                    html.P(f"📊 데이터 수: {data_count}개, 시간: {duration:.2f}초, 평균 FPS: {avg_fps:.1f}"),
                    html.P(f"📁 저장 위치: {filepath}")
                ], color="success")
                
            except Exception as e:
                status_display = dbc.Alert(f"❌ 저장 실패: {e}", color="danger")
        
        if recording_active:
            recording_status_text = "RECORDING"
            recording_style = {'color': 'red', 'fontWeight': 'bold'}
    
    return (btn_text, btn_color, recording_status_text, recording_style, 
            status_display, new_status_data)

# 통합된 엔코더 디스플레이 업데이트 + Device 상태 반영
@callback(
    [Output("encoder-list-display", "children"),
     Output("total-data-count", "children"),
     Output("comm-fps", "children"),
     Output("comm-interval", "children"),
     Output("serial-status", "children"),
     Output("serial-status", "style")],
    Input("interval", "n_intervals"),
    State("device-state", "data"),  # 🆕 Device 상태 추가
    prevent_initial_call=True
)
def update_encoder_display_with_live_data(n_intervals, device_state):
    """통합된 엔코더 디스플레이 업데이트 (레코딩 상태에 따른 표시) + Device 상태 반영"""
    global recorded_encoders, serial_thread_active, keyboard_state, recording_active, device_active

    # Device 상태 동기화
    if device_state and 'active' in device_state:
        device_active = device_state['active']

    try:
        # 통신 상태는 항상 업데이트
        with stats_lock:
            lines = list(recent_frames)
            fps = stats['fps']
            interval_ms = stats['ema_interval_ms'] if stats['ema_interval_ms'] is not None else 0.0

        # 🆕 Device가 비활성화된 경우에도 엔코더 데이터는 표시 (단, Device OFF 표시 추가)
        device_status_prefix = ""
        if not device_active:
            device_status_prefix = "🔌 [DEVICE OFF] "
        
        # 레코딩 중이면 실시간 데이터 표시, 일시중지면 레코딩된 데이터 표시
        if recording_active:
            # 레코딩 중: 실시간 엔코더 값 표시
            if lines:
                # Device OFF 상태 표시 추가
                if not device_active:
                    header_text = f"{device_status_prefix}실시간 엔코더 (키보드 제어 비활성화)\n" + "="*50 + "\n"
                    text = header_text + ''.join(lines[-10:])  # 화면 공간 확보를 위해 10개로 줄임
                else:
                    text = ''.join(lines[-12:])
                live_display = html.Pre(text, style={'margin': 0, 'fontSize': '1.3em', 'lineHeight': '1.5'})
            else:
                status_text = f"{device_status_prefix}프레임 수신 대기중..."
                live_display = html.Div(
                    status_text,
                    style={'textAlign': 'center','color':'#6c757d','padding':'20px','fontStyle':'italic', 'fontSize': '1.2em'}
                )
        else:
            # 레코딩 일시중지: 지금까지 레코딩된 데이터 표시
            if recorded_encoders:
                # 최근 12개의 레코딩된 데이터 표시
                recent_recorded = recorded_encoders[-10:]  # 화면 공간 확보
                text_lines = []
                
                # Device OFF 상태 헤더 추가
                if not device_active:
                    text_lines.append(f"{device_status_prefix}녹화된 데이터 (키보드 제어 비활성화)\n" + "="*50 + "\n")
                
                for entry in recent_recorded:
                    ts_str = datetime.fromtimestamp(entry['timestamp']).strftime('%H:%M:%S.%f')[:-3]
                    # 표시 순서: 오른팔이 위, 왼팔이 아래 (변경됨)
                    right_str = ', '.join(f'{x:4d}' for x in entry['right_arm'])
                    left_str = ', '.join(f'{x:4d}' for x in entry['left_arm'])
                    text_lines.append(f'[{ts_str}]\nRight : [{right_str}]\nLeft  : [{left_str}]\n')
                
                text = ''.join(text_lines)
                live_display = html.Pre(text, style={'margin': 0, 'fontSize': '1.3em', 'lineHeight': '1.5'})
            else:
                pause_text = f"{device_status_prefix}⏸️ 레코딩 일시중지"
                instruction_text = "2번 키를 눌러 레코딩을 시작하세요" if device_active else "Device ON 후 2번 키로 레코딩 가능"
                live_display = html.Div([
                    html.Div(pause_text, 
                            style={'textAlign': 'center', 'color': '#6c757d', 'fontSize': '1.2em', 'fontWeight': 'bold'}),
                    html.Div(instruction_text, 
                            style={'textAlign': 'center', 'color': '#999', 'fontSize': '0.9em', 'marginTop': '10px'})
                ], style={'padding': '40px'})

        # 녹화용 누적 카운트는 기존대로
        total_count = len(recorded_encoders)
        count_display = f"📊 총 녹화된 데이터: {total_count}개"

        # 통신 상태 및 수치 + Device 상태 반영
        if not device_active:
            serial_status = "DEVICE OFF"
            serial_style = {'color': 'orange', 'fontWeight': 'bold'}
        elif serial_thread_active:
            serial_status = "CONNECTED"
            serial_style = {'color': 'green', 'fontWeight': 'bold'}
        else:
            serial_status = "DISCONNECTED"
            serial_style = {'color': 'red', 'fontWeight': 'bold'}

        fps_text = f"{fps:0.1f} FPS" if fps > 0 and device_active else "0 FPS"
        interval_text = f"{interval_ms:0.1f} ms" if interval_ms and device_active else "—"

        return live_display, count_display, fps_text, interval_text, serial_status, serial_style
        
    except Exception as e:
        # 오류 발생 시 안전한 기본값 반환
        return (
            html.Div("⚠️ 데이터 로딩 중...", style={'textAlign': 'center', 'padding': '20px'}),
            "📊 총 녹화된 데이터: 0개",
            "0 FPS",
            "0ms",
            "ERROR",
            {'color': 'red', 'fontWeight': 'bold'}
        )

# 팔 상태 표시 업데이트 - 키 매핑 수정 (1번 키 → 오른팔, 4번 키 → 왼팔) + Device 상태 반영
@callback(
    [Output("led-left-pos", "style"),
     Output("led-left-grav", "style"),
     Output("pos-left", "style"),
     Output("grav-left", "style"),
     Output("led-right-pos", "style"),
     Output("led-right-grav", "style"),
     Output("pos-right", "style"),
     Output("grav-right", "style")],
    Input("interval", "n_intervals"),
    State("device-state", "data"),  # 🆕 Device 상태 추가
    prevent_initial_call=True
)
def update_arm_status_display(n_intervals, device_state):
    """팔 상태 표시 업데이트 (50ms 인터벌 최적화) - 키 매핑 수정 + Device 상태 반영"""
    try:
        global keyboard_state, device_active
        
        # Device 상태 동기화
        if device_state and 'active' in device_state:
            device_active = device_state['active']
        
        # 깜박임 효과 계산 (50ms 기준으로 조정)
        blink_factor = 0.7 + 0.3 * abs(((n_intervals * 5) % 200) - 100) / 100
        
        # 공통 스타일 정의
        led_off = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#6c757d'}
        led_green = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#28a745'}
        led_red = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#dc3545'}
        led_gray = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#999'}  # 🆕 비활성화 상태
        
        text_normal = {'color': '#6c757d', 'fontWeight': 'normal', 'fontSize': '1.4em'}
        text_inactive = {'color': '#999', 'fontWeight': 'normal', 'fontSize': '1.4em'}  # 🆕 비활성화 상태
        
        # 🆕 Device가 비활성화된 경우 - 현재 상태는 유지하되 회색으로 표시
        if not device_active:
            # 현재 키보드 상태를 반영하되 회색으로 표시
            left_gravity = keyboard_state.get('4', False)  # 4번 키 → 왼팔
            right_gravity = keyboard_state.get('1', False)  # 1번 키 → 오른팔
            
            # 왼팔 상태 (회색으로 표시)
            if left_gravity:
                left_pos_led = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#aaa'}
                left_grav_led = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#cc6666'}
            else:
                left_pos_led = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#66aa66'}
                left_grav_led = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#aaa'}
            
            # 오른팔 상태 (회색으로 표시)
            if right_gravity:
                right_pos_led = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#aaa'}
                right_grav_led = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#cc6666'}
            else:
                right_pos_led = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#66aa66'}
                right_grav_led = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#aaa'}
            
            return (left_pos_led, left_grav_led, text_inactive, text_inactive,
                    right_pos_led, right_grav_led, text_inactive, text_inactive)
        
        # 왼팔 상태 - 4번 키로 변경 (변경됨)
        left_gravity = keyboard_state.get('4', False)  # 4번 키 → 왼팔
        if left_gravity:
            left_pos_led = led_off
            left_grav_led = led_red
            left_pos_style = text_normal
            left_grav_style = {
                'color': '#dc3545', 'fontWeight': 'bold',
                'backgroundColor': f'rgba(220, 53, 69, {blink_factor * 0.2})',
                'padding': '4px 8px', 'borderRadius': '4px', 'transition': 'all 0.3s ease', 'fontSize': '1.4em'
            }
        else:
            left_pos_led = led_green
            left_grav_led = led_off
            left_pos_style = {
                'color': '#28a745', 'fontWeight': 'bold',
                'backgroundColor': f'rgba(40, 167, 69, {blink_factor * 0.2})',
                'padding': '4px 8px', 'borderRadius': '4px', 'transition': 'all 0.3s ease', 'fontSize': '1.4em'
            }
            left_grav_style = text_normal
        
        # 오른팔 상태 - 1번 키로 변경 (변경됨)
        right_gravity = keyboard_state.get('1', False)  # 1번 키 → 오른팔
        if right_gravity:
            right_pos_led = led_off
            right_grav_led = led_red
            right_pos_style = text_normal
            right_grav_style = {
                'color': '#dc3545', 'fontWeight': 'bold',
                'backgroundColor': f'rgba(220, 53, 69, {blink_factor * 0.2})',
                'padding': '4px 8px', 'borderRadius': '4px', 'transition': 'all 0.3s ease', 'fontSize': '1.4em'
            }
        else:
            right_pos_led = led_green
            right_grav_led = led_off
            right_pos_style = {
                'color': '#28a745', 'fontWeight': 'bold',
                'backgroundColor': f'rgba(40, 167, 69, {blink_factor * 0.2})',
                'padding': '4px 8px', 'borderRadius': '4px', 'transition': 'all 0.3s ease', 'fontSize': '1.4em'
            }
            right_grav_style = text_normal
        
        return (left_pos_led, left_grav_led, left_pos_style, left_grav_style,
                right_pos_led, right_grav_led, right_pos_style, right_grav_style)
                
    except Exception:
        # 오류 시 기본 상태 반환
        default_led = {'display':'inline-block','width':'10px','height':'10px','borderRadius':'50%','backgroundColor':'#888'}
        default_style = {'color': '#6c757d', 'fontSize': '1.4em'}
        return (default_led, default_led, default_style, default_style,
                default_led, default_led, default_style, default_style)

# 연결 상태 건강성 모니터링 콜백
@callback(
    Output("connection-health-monitor", "children"),
    Input("interval", "n_intervals"),
    prevent_initial_call=True
)
def monitor_connection_health(n_intervals):
    """연결 상태 건강성 모니터링 (비활성화)"""
    return ""

# Device ON 버튼 처리 (중력보상 체크 추가) - 키 매핑 수정
@callback(
    Output("device-on-status", "data"),
    Input("device-on-btn", "n_clicks"),
    prevent_initial_call=True
)
def handle_device_on_button(n_clicks):
    """Device ON 버튼 처리 - 중력보상 모드 체크 및 점멸 효과 - 키 매핑 수정"""
    if n_clicks:
        # 키보드 상태 확인
        global keyboard_state, shared_ser
        
        # 시리얼 연결 확인
        if not shared_ser or not shared_ser.is_open:
            return {
                'blinking': False, 
                'timestamp': time.time(),
                'success': False,
                'message': "시리얼 연결이 활성화되지 않았습니다."
            }
        
        # 중력보상 모드 확인 - 키 매핑 수정 (1번 키 → 오른팔, 4번 키 → 왼팔)
        right_arm_gravity = keyboard_state.get('1', False)  # 1번 키 → 오른팔
        left_arm_gravity = keyboard_state.get('4', False)   # 4번 키 → 왼팔
        
        if right_arm_gravity or left_arm_gravity:
            # 중력보상 모드인 팔들 확인
            gravity_arms = []
            key_instructions = []
            
            if right_arm_gravity:
                gravity_arms.append("오른팔")
                key_instructions.append("1번 키(오른팔)")
            if left_arm_gravity:
                gravity_arms.append("왼팔")
                key_instructions.append("4번 키(왼팔)")
            
            arms_text = ", ".join(gravity_arms)
            keys_text = " 또는 ".join(key_instructions)
            
            return {
                'blinking': False, 
                'timestamp': time.time(),
                'success': False,
                'message': f"🚫 Device ON 실행 불가: {arms_text}이 중력보상 모드입니다. {keys_text}를 눌러 Position Control 모드로 변경해주세요."
            }
        
        # 정상적으로 명령 전송
        success, message = send_command_safely("DEVICE_ON")
        return {
            'blinking': True, 
            'timestamp': time.time(),
            'success': success,
            'message': message
        }
    return {'blinking': False, 'timestamp': 0}

# Device OFF 버튼 처리 (중력보상 체크 추가) - 키 매핑 수정
@callback(
    Output("device-off-status", "data"),
    Input("device-off-btn", "n_clicks"),
    prevent_initial_call=True
)
def handle_device_off_button(n_clicks):
    """Device OFF 버튼 처리 - 중력보상 모드 체크 및 점멸 효과 - 키 매핑 수정"""
    if n_clicks:
        # 키보드 상태 확인
        global keyboard_state, shared_ser
        
        # 시리얼 연결 확인
        if not shared_ser or not shared_ser.is_open:
            return {
                'blinking': False, 
                'timestamp': time.time(),
                'success': False,
                'message': "시리얼 연결이 활성화되지 않았습니다."
            }
        
        # 중력보상 모드 확인 - 키 매핑 수정 (1번 키 → 오른팔, 4번 키 → 왼팔)
        right_arm_gravity = keyboard_state.get('1', False)  # 1번 키 → 오른팔
        left_arm_gravity = keyboard_state.get('4', False)   # 4번 키 → 왼팔
        
        if right_arm_gravity or left_arm_gravity:
            # 중력보상 모드인 팔들 확인
            gravity_arms = []
            key_instructions = []
            
            if right_arm_gravity:
                gravity_arms.append("오른팔")
                key_instructions.append("1번 키(오른팔)")
            if left_arm_gravity:
                gravity_arms.append("왼팔")
                key_instructions.append("4번 키(왼팔)")
            
            arms_text = ", ".join(gravity_arms)
            keys_text = " 또는 ".join(key_instructions)
            
            return {
                'blinking': False, 
                'timestamp': time.time(),
                'success': False,
                'message': f"🚫 Device OFF 실행 불가: {arms_text}이 중력보상 모드입니다. {keys_text}를 눌러 Position Control 모드로 변경해주세요."
            }
        
        # 정상적으로 명령 전송
        success, message = send_command_safely("DEVICE_OFF")
        return {
            'blinking': True, 
            'timestamp': time.time(),
            'success': success,
            'message': message
        }
    return {'blinking': False, 'timestamp': 0}

# Go to Home 버튼 처리 (중력보상 체크 추가) - 키 매핑 수정
@callback(
    Output("go-home-status", "data"),
    Input("go-home-btn", "n_clicks"),
    [State("device-state", "data")],  # 🆕 Device 상태 추가
    prevent_initial_call=True
)
def handle_go_home_button(n_clicks, device_state):
    """Go to Home 버튼 처리 - 중력보상 모드 체크 및 점멸 효과 - 키 매핑 수정 + Device 상태 확인"""
    if n_clicks:
        # 키보드 상태 확인
        global keyboard_state, shared_ser, device_active
        
        # Device 상태 동기화 및 확인
        if device_state and 'active' in device_state:
            device_active = device_state['active']
        
        if not device_active:
            return {
                'blinking': False, 
                'timestamp': time.time(),
                'success': False,
                'message': "🔌 Device가 OFF 상태입니다. Device ON을 먼저 실행해주세요."
            }
        
        # 시리얼 연결 확인
        if not shared_ser or not shared_ser.is_open:
            return {
                'blinking': False, 
                'timestamp': time.time(),
                'success': False,
                'message': "시리얼 연결이 활성화되지 않았습니다."
            }
        
        # 중력보상 모드 확인 - 키 매핑 수정 (1번 키 → 오른팔, 4번 키 → 왼팔)
        right_arm_gravity = keyboard_state.get('1', False)  # 1번 키 → 오른팔
        left_arm_gravity = keyboard_state.get('4', False)   # 4번 키 → 왼팔
        
        if right_arm_gravity or left_arm_gravity:
            # 중력보상 모드인 팔들 확인
            gravity_arms = []
            key_instructions = []
            
            if right_arm_gravity:
                gravity_arms.append("오른팔")
                key_instructions.append("1번 키(오른팔)")
            if left_arm_gravity:
                gravity_arms.append("왼팔")
                key_instructions.append("4번 키(왼팔)")
            
            arms_text = ", ".join(gravity_arms)
            keys_text = " 또는 ".join(key_instructions)
            
            return {
                'blinking': False, 
                'timestamp': time.time(),
                'success': False,
                'message': f"🚫 Go to Home 실행 불가: {arms_text}이 중력보상 모드입니다. {keys_text}를 눌러 Position Control 모드로 변경해주세요."
            }
        
        # 정상적으로 명령 전송
        success, message = send_command_safely("HOME")
        return {
            'blinking': True, 
            'timestamp': time.time(),
            'success': success,
            'message': message
        }
    return {'blinking': False, 'timestamp': 0}

# 상태 메시지 표시를 위한 새로운 콜백 추가 - 텍스트 수정 (1번 키 → 오른팔, 4번 키 → 왼팔)
@callback(
    Output("gravity-check-alert", "children"),
    Input("device-on-status", "data"),
    Input("device-off-status", "data"),
    Input("go-home-status", "data"),
    prevent_initial_call=True
)
def display_gravity_check_messages(on_status, off_status, home_status):
    """중력보상 체크 결과 메시지 표시 - 텍스트 수정"""
    
    # 최근 실행된 버튼의 상태 확인
    latest_status = None
    latest_time = 0
    button_name = ""
    
    if on_status and on_status.get('timestamp', 0) > latest_time:
        latest_status = on_status
        latest_time = on_status.get('timestamp', 0)
        button_name = "Device ON"
    
    if off_status and off_status.get('timestamp', 0) > latest_time:
        latest_status = off_status
        latest_time = off_status.get('timestamp', 0)
        button_name = "Device OFF"
    
    if home_status and home_status.get('timestamp', 0) > latest_time:
        latest_status = home_status
        latest_time = home_status.get('timestamp', 0)
        button_name = "Go to Home"
    
    # 최근 5초 이내의 메시지만 표시
    if latest_status and time.time() - latest_time < 5:
        success = latest_status.get('success', True)
        message = latest_status.get('message', "")
        
        if not success and "실행 불가" in message:
            # 중력보상 모드 경고 메시지 (상세 버전)
            parts = message.split(":")
            if len(parts) >= 2:
                arms_info = parts[1].split("이 중력보상 모드입니다.")[0].strip()
                key_info = parts[1].split("모드입니다. ")[1] if "모드입니다. " in parts[1] else ""
                
                return dbc.Alert([
                    html.Div([
                        html.Span("🚫 ", style={'fontSize': '1.2rem'}),
                        html.Strong(f"{button_name} 실행 불가")
                    ]),
                    html.Div([
                        html.Span(f"{arms_info}이 현재 ", style={'fontWeight': 'normal'}),
                        html.Span("중력보상 모드", style={'fontWeight': 'bold', 'color': '#dc3545'}),
                        html.Span("입니다.", style={'fontWeight': 'normal'})
                    ], style={'marginTop': '8px', 'fontSize': '1.05em'}),
                    html.Hr(style={'margin': '10px 0'}),
                    html.Div([
                        html.Span("📍 ", style={'fontSize': '1rem'}),
                        html.Strong("Position Control 모드로 먼저 변경해주세요:")
                    ], style={'marginTop': '8px'}),
                    html.Div([
                        html.Span("• "),
                        html.Span(key_info if key_info else "키보드 1번 키(오른팔) 또는 4번 키(왼팔)를 눌러 Position Control 모드로 변경", 
                                style={'fontWeight': 'normal'}),
                    ], style={'marginTop': '5px', 'paddingLeft': '10px'}),
                    html.Div([
                        html.Span("• 팔 상태 패널에서 "),
                        html.Span("Position Control", style={'fontWeight': 'bold', 'color': '#28a745'}),
                        html.Span(" 활성화 확인 후 다시 시도")
                    ], style={'marginTop': '3px', 'paddingLeft': '10px'}),
                    html.Div([
                        html.Span(f"⚠️ 안전을 위해 중력보상 모드에서는 {button_name}이 제한됩니다.", 
                                style={'fontStyle': 'italic', 'color': '#856404'})
                    ], style={'marginTop': '10px', 'padding': '8px', 'backgroundColor': '#fff3cd', 'borderRadius': '4px'})
                ], color="warning", dismissable=True, duration=8000)
        
        elif not success and "시리얼 연결" in message:
            # 시리얼 연결 문제
            return dbc.Alert([
                html.Div([
                    html.Span("⚠️ ", style={'fontSize': '1.2rem'}),
                    html.Strong(f"{button_name} 실행 불가")
                ]),
                html.Div("USB 시리얼 연결이 활성화되지 않았습니다.", style={'marginTop': '5px'}),
                html.Div("페이지를 새로고침하거나 USB를 다시 연결해주세요.", 
                        style={'marginTop': '3px', 'fontSize': '0.9em', 'color': '#666'})
            ], color="warning", dismissable=True, duration=5000)
        
        elif not success and "Device가 OFF" in message:
            # 🆕 Device OFF 상태 경고
            return dbc.Alert([
                html.Div([
                    html.Span("🔌 ", style={'fontSize': '1.2rem'}),
                    html.Strong(f"{button_name} 실행 불가")
                ]),
                html.Div("Device가 OFF 상태입니다.", style={'marginTop': '5px'}),
                html.Div("Device ON 버튼을 먼저 실행해주세요.", 
                        style={'marginTop': '3px', 'fontSize': '0.9em', 'color': '#666'})
            ], color="warning", dismissable=True, duration=5000)
        
        elif success:
            # 성공 메시지
            return dbc.Alert([
                html.Div([
                    html.Span("✅ ", style={'fontSize': '1.2rem'}),
                    html.Strong(f"{button_name} 명령 전송 성공!")
                ]),
                html.Div(message, style={'marginTop': '5px'})
            ], color="success", dismissable=True, duration=3000)
    
    return ""

# 모든 버튼 스타일 업데이트 (Device ON/OFF + Go to Home)
@callback(
    [Output("device-on-btn", "style"),
     Output("device-off-btn", "style"),
     Output("go-home-btn", "style")],
    Input("interval", "n_intervals"),
    [State("device-on-status", "data"),
     State("device-off-status", "data"),
     State("go-home-status", "data")],
    prevent_initial_call=True
)
def update_all_button_styles_with_complete_detection(n_intervals, on_status, off_status, home_status):
    """모든 버튼의 깜박임 효과 (극도로 가시성 높은 버전)"""
    # 기본 버튼 스타일
    base_style = {
        'fontWeight': 'bold',
        'borderRadius': '10px',
        'padding': '10px 20px',
        'boxShadow': '0 4px 8px rgba(0,0,0,0.2)',
        'transition': 'all 0.1s ease'  # 더 빠른 전환
    }
    
    # 1초마다 한 번만 체크 (100ms * 10 = 1초)
    if n_intervals % 10 == 0:
        try:
            current_time = time.time()
            
            # COMPLETE 메시지 확인
            recent_messages = get_recent_complete_messages()
            device_on_complete = any('DEVICE_ON_COMPLETE' in msg.get('message', '') for msg in recent_messages)
            device_off_complete = any('DEVICE_OFF_COMPLETE' in msg.get('message', '') for msg in recent_messages)
            home_complete = any('HOME_COMPLETE' in msg.get('message', '') for msg in recent_messages)
            
            # 깜박임이 필요한지만 체크
            need_blink_on = (on_status and on_status.get('blinking', False) and 
                           not device_on_complete and 
                           (current_time - on_status.get('timestamp', 0) <= 30.0))
            
            need_blink_off = (off_status and off_status.get('blinking', False) and 
                            not device_off_complete and 
                            (current_time - off_status.get('timestamp', 0) <= 30.0))
            
            need_blink_home = (home_status and home_status.get('blinking', False) and 
                             not home_complete and 
                             (current_time - home_status.get('timestamp', 0) <= 30.0))
            
            # 극도로 강한 깜박임 효과 계산 (매우 눈에 띄게)
            if need_blink_on or need_blink_off or need_blink_home:
                blink_phase = ((n_intervals * 5) % 15) / 15  # 훨씬 더 빠른 깜박임
                intensity = 0.1 + 0.9 * abs(blink_phase - 0.5) * 2  # 극도로 강한 변화 (0.1 ~ 1.0)
                scale = 0.9 + 0.2 * intensity  # 더 큰 크기 변화 (0.9 ~ 1.1)
            else:
                intensity = 1.0
                scale = 1.0
            
            # Device ON 버튼 스타일 (초록색 강조)
            on_btn_style = base_style.copy()
            if need_blink_on:
                on_btn_style.update({
                    'backgroundColor': f'rgba(40,167,69,{0.3 + 0.7 * intensity})',  # 더 강한 색상 변화
                    'borderColor': f'rgba(255,255,255,{intensity})',  # 흰색 테두리
                    'border': f'4px solid rgba(255,255,255,{intensity})',  # 더 두꺼운 테두리
                    'transform': f'scale({scale})',  # 더 큰 크기 변화
                    'boxShadow': f'0 12px 35px rgba(40,167,69,{intensity}), 0 0 30px rgba(255,255,255,{intensity * 0.8}), inset 0 0 20px rgba(255,255,255,{intensity * 0.3})',  # 삼중 그림자 + 내부 그림자
                    'color': f'rgba(255,255,255,{0.7 + 0.3 * intensity})',  # 더 강한 글자색 변화
                    'textShadow': f'0 0 10px rgba(255,255,255,{intensity * 0.8})'  # 글자 그림자 추가
                })
            
            # Device OFF 버튼 스타일 (노란색 강조)
            off_btn_style = base_style.copy()
            if need_blink_off:
                off_btn_style.update({
                    'backgroundColor': f'rgba(255,193,7,{0.3 + 0.7 * intensity})',  # 더 강한 색상 변화
                    'borderColor': f'rgba(255,255,255,{intensity})',  # 흰색 테두리
                    'border': f'4px solid rgba(255,255,255,{intensity})',  # 더 두꺼운 테두리
                    'transform': f'scale({scale})',  # 더 큰 크기 변화
                    'boxShadow': f'0 12px 35px rgba(255,193,7,{intensity}), 0 0 30px rgba(255,255,255,{intensity * 0.8}), inset 0 0 20px rgba(255,255,255,{intensity * 0.3})',  # 삼중 그림자 + 내부 그림자
                    'color': f'rgba(0,0,0,{0.6 + 0.4 * intensity})',  # 더 강한 글자색 변화
                    'textShadow': f'0 0 8px rgba(255,255,255,{intensity * 0.6})'  # 글자 그림자 추가
                })
            
            # Go to Home 버튼 스타일 (파란색 강조)
            home_btn_style = base_style.copy()
            home_btn_style.update({'fontSize': '1.4em'})
            if need_blink_home:
                home_btn_style.update({
                    'backgroundColor': f'rgba(23,162,184,{0.3 + 0.7 * intensity})',  # 더 강한 색상 변화
                    'borderColor': f'rgba(255,255,255,{intensity})',  # 흰색 테두리
                    'border': f'4px solid rgba(255,255,255,{intensity})',  # 더 두꺼운 테두리
                    'transform': f'scale({scale})',  # 더 큰 크기 변화
                    'boxShadow': f'0 12px 35px rgba(23,162,184,{intensity}), 0 0 30px rgba(255,255,255,{intensity * 0.8}), inset 0 0 20px rgba(255,255,255,{intensity * 0.3})',  # 삼중 그림자 + 내부 그림자
                    'color': f'rgba(255,255,255,{0.7 + 0.3 * intensity})',  # 더 강한 글자색 변화
                    'fontSize': '1.4em',
                    'textShadow': f'0 0 10px rgba(255,255,255,{intensity * 0.8})'  # 글자 그림자 추가
                })
            
            return on_btn_style, off_btn_style, home_btn_style
            
        except:
            pass
    
    # 기본 스타일 반환
    home_style = base_style.copy()
    home_style['fontSize'] = '1.4em'
    return base_style, base_style, home_style