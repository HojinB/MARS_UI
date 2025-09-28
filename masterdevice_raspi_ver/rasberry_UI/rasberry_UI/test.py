# test.py
"""
Master Device gRPC 서버 테스트 스크립트
PC에서 gRPC 서버를 단독으로 실행하여 라즈베리파이 연결 테스트
"""

import threading
import time
import sys
import signal
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

# gRPC 서버 및 데이터 매니저 import
try:
    from GRPC.stubs.server import serve_async, MasterDeviceServer
    from grpc_data_manager import grpc_data_manager
    GRPC_AVAILABLE = True
    print("✅ gRPC 모듈 로드 성공")
except ImportError as e:
    GRPC_AVAILABLE = False
    print(f"❌ gRPC 모듈 로드 실패: {e}")
    sys.exit(1)

# 설정
TEST_HOST = "0.0.0.0"
TEST_PORT = 50052
MONITOR_INTERVAL = 3  # 모니터링 간격 (초)

class TestMonitor:
    """테스트 모니터링 클래스"""
    
    def __init__(self):
        self.running = True
        self.start_time = time.time()
        self.last_stats = None
    
    def stop(self):
        """모니터링 중지"""
        self.running = False
    
    def print_header(self):
        """헤더 출력"""
        print("\n" + "=" * 80)
        print("🚀 Master Device gRPC 서버 테스트 모드")
        print("=" * 80)
        print(f"📍 서버 주소: {TEST_HOST}:{TEST_PORT}")
        print(f"📊 모니터링 간격: {MONITOR_INTERVAL}초")
        print(f"🔗 라즈베리파이 연결 주소: 192.168.0.4:{TEST_PORT}")
        print("=" * 80)
        print("💡 라즈베리파이에서 테스트:")
        print(f"   ./robot_client 192.168.0.4:{TEST_PORT}")
        print("=" * 80)
    
    def print_system_status(self):
        """시스템 상태 출력"""
        uptime = time.time() - self.start_time
        uptime_str = f"{int(uptime//3600):02d}:{int((uptime%3600)//60):02d}:{int(uptime%60):02d}"
        
        print(f"\n⏰ 가동 시간: {uptime_str}")
        
        # 데이터 매니저 상태
        try:
            robot_state = grpc_data_manager.get_robot_state()
            statistics = grpc_data_manager.get_statistics()
            
            print(f"🔗 연결 상태: {'✅ 연결됨' if robot_state['connected'] else '❌ 연결 끊김'}")
            print(f"📊 통신 FPS: {statistics['current_fps']}")
            print(f"📦 총 샘플: {statistics['total_samples']}")
            print(f"💾 저장된 포즈: {statistics['saved_poses']}개")
            print(f"📝 gRPC 로그: {statistics['grpc_logs']}개")
            print(f"🎬 녹화 상태: {'🔴 녹화 중' if statistics['recording_active'] else '⏹️ 중지'}")
            
            if statistics['recording_active']:
                print(f"📹 녹화 샘플: {statistics['recording_samples']}개")
        
        except Exception as e:
            print(f"❌ 상태 조회 오류: {e}")
    
    def print_recent_activity(self):
        """최근 활동 출력"""
        try:
            # 최근 gRPC 로그
            grpc_logs = grpc_data_manager.get_grpc_entries(5)
            if grpc_logs:
                print("\n📡 최근 gRPC 활동:")
                for log in grpc_logs[:3]:  # 최신 3개만
                    level_icon = {"INFO": "ℹ️", "ERROR": "❌", "WARNING": "⚠️"}.get(log["level"], "📝")
                    print(f"   {level_icon} [{log['timestamp']}] {log['topic']}: {log['message']}")
            
            # 현재 엔코더 데이터
            current_encoder = grpc_data_manager.get_current_encoder_data()
            if current_encoder:
                angles_str = ", ".join([f"{a:.1f}°" for a in current_encoder["angles"][:4]])  # 첫 4개만
                print(f"\n🎮 현재 엔코더: [{angles_str}...] (#{current_encoder['sample_id']})")
        
        except Exception as e:
            print(f"❌ 활동 조회 오류: {e}")
    
    def monitor_loop(self):
        """모니터링 루프"""
        self.print_header()
        
        while self.running:
            try:
                self.print_system_status()
                self.print_recent_activity()
                print("-" * 80)
                
                # 다음 출력까지 대기
                for i in range(MONITOR_INTERVAL):
                    if not self.running:
                        break
                    time.sleep(1)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ 모니터링 오류: {e}")
                time.sleep(1)
        
        print("\n🛑 모니터링 중지")

def run_grpc_server():
    """gRPC 서버 실행"""
    try:
        print(f"🚀 gRPC 서버 시작: {TEST_HOST}:{TEST_PORT}")
        from GRPC.stubs.server import serve
        serve(host=TEST_HOST, port=TEST_PORT)
    except Exception as e:
        print(f"❌ gRPC 서버 오류: {e}")

def signal_handler(signum, frame):
    """시그널 핸들러"""
    print(f"\n🛑 종료 신호 수신 ({signum})")
    global monitor
    if 'monitor' in globals():
        monitor.stop()
    sys.exit(0)

def main():
    """메인 실행 함수"""
    global monitor
    
    if not GRPC_AVAILABLE:
        print("❌ gRPC 모듈이 없어 테스트를 실행할 수 없습니다.")
        return
    
    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("🧪 Master Device gRPC 서버 테스트 시작")
    
    # 데이터 매니저 초기화
    grpc_data_manager.reset_all_data()
    grpc_data_manager.add_grpc_entry("SYSTEM", "테스트 모드 시작")
    
    # gRPC 서버 스레드 시작
    print("🚀 gRPC 서버를 백그라운드에서 시작...")
    grpc_thread = threading.Thread(target=run_grpc_server, daemon=True)
    grpc_thread.start()
    
    # 서버 시작 대기
    time.sleep(2)
    
    # 모니터 시작
    monitor = TestMonitor()
    
    try:
        monitor.monitor_loop()
    except KeyboardInterrupt:
        print("\n🛑 사용자 중단 요청")
    except Exception as e:
        print(f"\n❌ 테스트 실행 오류: {e}")
    finally:
        monitor.stop()
        print("\n🏁 테스트 완료")

def demo_data_generation():
    """데모 데이터 생성 (테스트용)"""
    print("\n🎭 데모 데이터 생성 중...")
    
    # 샘플 엔코더 데이터 생성
    import random
    for i in range(10):
        angles = [random.uniform(-180, 180) for _ in range(6)]
        grpc_data_manager.update_encoder_data(angles)
        time.sleep(0.1)
    
    # 샘플 포즈 저장
    for i in range(3):
        angles = [random.uniform(-90, 90) for _ in range(6)]
        pose_name = grpc_data_manager.save_encoder_pose(angles, f"DemoPose_{i+1}")
        print(f"   💾 데모 포즈 저장: {pose_name}")
    
    # 샘플 로그 생성
    grpc_data_manager.add_grpc_entry("DEMO", "데모 연결 시뮬레이션")
    grpc_data_manager.set_gravity_mode("GRAVITY_ON_ALL")
    grpc_data_manager.set_position_mode("POSITION_ON_LEFT")
    
    print("✅ 데모 데이터 생성 완료")

def interactive_commands():
    """대화형 명령 처리"""
    print("\n💬 대화형 모드 시작 (종료하려면 'quit' 입력)")
    print("사용 가능한 명령:")
    print("  stats     - 통계 표시")
    print("  logs      - 최근 로그 표시")
    print("  demo      - 데모 데이터 생성")
    print("  clear     - 데이터 클리어")
    print("  poses     - 저장된 포즈 표시")
    print("  quit/exit - 종료")
    
    while True:
        try:
            cmd = input("\n> ").strip().lower()
            
            if cmd in ['quit', 'exit', 'q']:
                break
            elif cmd == 'stats':
                stats = grpc_data_manager.get_statistics()
                print(f"📊 통계: {stats}")
            elif cmd == 'logs':
                logs = grpc_data_manager.get_grpc_entries(10)
                print("📝 최근 로그:")
                for log in logs:
                    print(f"  [{log['timestamp']}] {log['topic']}: {log['message']}")
            elif cmd == 'demo':
                demo_data_generation()
            elif cmd == 'clear':
                grpc_data_manager.reset_all_data()
                print("🗑️ 모든 데이터 클리어됨")
            elif cmd == 'poses':
                poses = grpc_data_manager.get_saved_poses()
                print(f"💾 저장된 포즈 ({len(poses)}개):")
                for pose in poses:
                    angles_str = ", ".join([f"{a:.1f}°" for a in pose["angles"]])
                    print(f"  {pose['name']}: [{angles_str}]")
            elif cmd == 'help':
                print("💡 도움말: 위의 명령 목록을 참조하세요")
            elif cmd == '':
                continue
            else:
                print(f"❌ 알 수 없는 명령: {cmd}")
        
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ 명령 실행 오류: {e}")
    
    print("👋 대화형 모드 종료")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Master Device gRPC 서버 테스트")
    parser.add_argument("--port", type=int, default=50052, help="gRPC 서버 포트 (기본값: 50052)")
    parser.add_argument("--host", default="0.0.0.0", help="바인딩 호스트 (기본값: 0.0.0.0)")
    parser.add_argument("--monitor-interval", type=int, default=3, help="모니터링 간격 (초, 기본값: 3)")
    parser.add_argument("--demo", action="store_true", help="시작 시 데모 데이터 생성")
    parser.add_argument("--interactive", action="store_true", help="대화형 모드 활성화")
    
    args = parser.parse_args()
    
    # 설정 적용
    TEST_HOST = args.host
    TEST_PORT = args.port
    MONITOR_INTERVAL = args.monitor_interval
    
    # 데모 데이터 생성
    if args.demo:
        demo_data_generation()
    
    # 대화형 모드
    if args.interactive:
        # gRPC 서버를 백그라운드에서 시작
        grpc_thread = threading.Thread(target=run_grpc_server, daemon=True)
        grpc_thread.start()
        time.sleep(1)
        
        interactive_commands()
    else:
        # 일반 모니터링 모드
        main()