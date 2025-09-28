# core/config.py
"""
Master Device 전역 설정 관리
"""
import os
import socket

# =================================
# 네트워크 설정
# =================================
def get_local_ip():
    """로컬 IP 주소 자동 감지"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

# IP 및 포트 설정
LOCAL_IP = get_local_ip()
WEB_SERVER_PORT = 8050
GRPC_SERVER_PORT = 50051

# 라즈베리파이 기본 설정
DEFAULT_RASPBERRY_IP = "192.168.0.100"
DEFAULT_RASPBERRY_PORT = 50052

# =================================
# gRPC 설정
# =================================
GRPC_CONNECTION_TIMEOUT = 5  # 초
GRPC_REQUEST_TIMEOUT = 10    # 초
GRPC_RETRY_COUNT = 3

# =================================
# 데이터 수집 설정
# =================================
DATA_COLLECTION_INTERVAL = 50  # ms (20Hz)
SAVE_STREAM_INTERVAL = 100     # ms (10Hz)
MAX_STREAM_SAMPLES = 1000      # 최대 저장 샘플 수

# 모터 관련 설정
MOTOR_COUNT = 14
DEFAULT_ANGLES = [0.0] * MOTOR_COUNT

# =================================
# 파일 경로 설정
# =================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
GRPC_STUBS_DIR = os.path.join(PROJECT_ROOT, "grpc_modules", "stubs")

# 디렉토리 생성
for dir_path in [LOGS_DIR, ASSETS_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        print(f"📁 디렉토리 생성: {dir_path}")

# =================================
# UI 설정
# =================================
APP_TITLE = "Master Device Control"
APP_DESCRIPTION = "Smart Teach Device Interface"

# 색상 테마
COLORS = {
    'primary': '#5A6D8C',
    'success': '#28a745', 
    'danger': '#dc3545',
    'warning': '#ffc107',
    'info': '#17a2b8',
    'light': '#f8f9fa',
    'dark': '#343a40'
}

# =================================
# 로깅 설정
# =================================
LOG_FORMAT = "[%(asctime)s] %(levelname)s - %(message)s"
LOG_LEVEL = "INFO"

# =================================
# 환경 변수 오버라이드
# =================================
def load_env_overrides():
    """환경 변수로 설정값 오버라이드"""
    global DEFAULT_RASPBERRY_IP, DEFAULT_RASPBERRY_PORT, WEB_SERVER_PORT
    
    if os.getenv("RASPBERRY_PI_IP"):
        DEFAULT_RASPBERRY_IP = os.getenv("RASPBERRY_PI_IP")
    
    if os.getenv("RASPBERRY_PI_PORT"):
        DEFAULT_RASPBERRY_PORT = int(os.getenv("RASPBERRY_PI_PORT"))
    
    if os.getenv("WEB_PORT"):
        WEB_SERVER_PORT = int(os.getenv("WEB_PORT"))

# 환경 변수 적용
load_env_overrides()

# =================================
# 설정 검증
# =================================
def validate_config():
    """설정값 유효성 검증"""
    errors = []
    
    # 포트 범위 검증
    if not (1024 <= WEB_SERVER_PORT <= 65535):
        errors.append(f"웹 서버 포트가 유효하지 않음: {WEB_SERVER_PORT}")
    
    if not (1024 <= DEFAULT_RASPBERRY_PORT <= 65535):
        errors.append(f"라즈베리파이 포트가 유효하지 않음: {DEFAULT_RASPBERRY_PORT}")
    
    # IP 형식 검증 (간단한 검증)
    ip_parts = DEFAULT_RASPBERRY_IP.split('.')
    if len(ip_parts) != 4 or not all(part.isdigit() and 0 <= int(part) <= 255 for part in ip_parts):
        errors.append(f"라즈베리파이 IP가 유효하지 않음: {DEFAULT_RASPBERRY_IP}")
    
    if errors:
        raise ValueError("설정 오류:\n" + "\n".join(errors))

# 설정 검증 실행
try:
    validate_config()
    print(f"✅ 설정 검증 완료 - 웹서버: {LOCAL_IP}:{WEB_SERVER_PORT}, 라즈베리파이: {DEFAULT_RASPBERRY_IP}:{DEFAULT_RASPBERRY_PORT}")
except ValueError as e:
    print(f"❌ {e}")
    exit(1)