# core/grpc_manager.py
"""
gRPC 연결 및 상태 관리
"""
import sys
import time
import threading
from typing import Optional, Tuple
from .config import GRPC_STUBS_DIR, GRPC_CONNECTION_TIMEOUT

class GrpcManager:
    """gRPC 연결 및 모듈 관리 클래스"""
    
    def __init__(self):
        self.grpc_available = False
        self.masterdevice_pb2 = None
        self.masterdevice_pb2_grpc = None
        self._connection_status = {}
        self._lock = threading.Lock()
        
        # gRPC 모듈 로드 시도
        self._load_grpc_modules()
    
    def _load_grpc_modules(self) -> bool:
        """gRPC protobuf 모듈들을 동적으로 로드"""
        try:
            # GRPC/stubs 디렉토리를 sys.path에 추가
            if GRPC_STUBS_DIR not in sys.path:
                sys.path.insert(0, GRPC_STUBS_DIR)
            
            # protobuf 모듈들 import
            import masterdevice_pb2
            import masterdevice_pb2_grpc
            
            self.masterdevice_pb2 = masterdevice_pb2
            self.masterdevice_pb2_grpc = masterdevice_pb2_grpc
            self.grpc_available = True
            
            print("[INFO] ✅ gRPC 모듈 로드 성공")
            return True
            
        except Exception as e:
            print(f"[ERROR] ❌ gRPC 모듈 로드 실패: {e}")
            self.grpc_available = False
            return False
    
    def is_available(self) -> bool:
        """gRPC 모듈 사용 가능 여부 반환"""
        return self.grpc_available
    
    def create_channel(self, ip: str, port: int) -> Tuple[Optional[object], str]:
        """
        gRPC 채널 생성
        
        Args:
            ip: 서버 IP 주소
            port: 서버 포트
            
        Returns:
            Tuple[채널 객체 또는 None, 상태 메시지]
        """
        if not self.grpc_available:
            return None, "gRPC 모듈이 로드되지 않았습니다"
        
        try:
            import grpc
            
            server_address = f"{ip}:{port}"
            
            # 채널 옵션 설정
            options = [
                ('grpc.keepalive_time_ms', 30000),
                ('grpc.keepalive_timeout_ms', 5000),
                ('grpc.keepalive_permit_without_calls', True),
                ('grpc.http2.max_pings_without_data', 0),
                ('grpc.http2.min_time_between_pings_ms', 10000),
                ('grpc.http2.min_ping_interval_without_data_ms', 300000)
            ]
            
            # 채널 생성
            channel = grpc.insecure_channel(server_address, options=options)
            
            # 연결 테스트
            try:
                grpc.channel_ready_future(channel).result(timeout=GRPC_CONNECTION_TIMEOUT)
                status = f"연결 성공: {server_address}"
                
                # 연결 상태 저장
                with self._lock:
                    self._connection_status[server_address] = {
                        'connected': True,
                        'last_check': time.time(),
                        'channel': channel
                    }
                    
            except grpc.FutureTimeoutError:
                status = f"연결 타임아웃: {server_address}"
                channel = None
            except Exception as e:
                status = f"연결 실패: {server_address} - {str(e)}"
                channel = None
                
            return channel, status
            
        except Exception as e:
            return None, f"채널 생성 오류: {str(e)}"
    
    def create_stub(self, channel, service_type: str = "masterdevice"):
        """
        gRPC 스텁 생성
        
        Args:
            channel: gRPC 채널
            service_type: 서비스 타입 (기본: "masterdevice")
            
        Returns:
            gRPC 스텁 객체 또는 None
        """
        if not self.grpc_available or not channel:
            return None
        
        try:
            if service_type == "masterdevice":
                return self.masterdevice_pb2_grpc.masterdeviceStub(channel)
            else:
                raise ValueError(f"지원하지 않는 서비스 타입: {service_type}")
                
        except Exception as e:
            print(f"[ERROR] 스텁 생성 실패: {e}")
            return None
    
    def check_connection_status(self, ip: str, port: int) -> dict:
        """
        연결 상태 확인
        
        Args:
            ip: 서버 IP
            port: 서버 포트
            
        Returns:
            연결 상태 정보 딕셔너리
        """
        server_address = f"{ip}:{port}"
        
        with self._lock:
            status = self._connection_status.get(server_address, {
                'connected': False,
                'last_check': 0,
                'channel': None
            })
        
        # 연결 상태가 오래되었으면 다시 확인
        current_time = time.time()
        if current_time - status.get('last_check', 0) > 30:  # 30초마다 확인
            channel, message = self.create_channel(ip, port)
            if channel:
                status.update({
                    'connected': True,
                    'last_check': current_time,
                    'message': message,
                    'channel': channel
                })
            else:
                status.update({
                    'connected': False,
                    'last_check': current_time,
                    'message': message,
                    'channel': None
                })
        
        return status
    
    def get_connection_info(self) -> dict:
        """모든 연결 정보 반환"""
        with self._lock:
            return self._connection_status.copy()
    
    def close_channel(self, ip: str, port: int):
        """채널 연결 종료"""
        server_address = f"{ip}:{port}"
        
        with self._lock:
            if server_address in self._connection_status:
                status = self._connection_status[server_address]
                channel = status.get('channel')
                
                if channel:
                    try:
                        channel.close()
                    except Exception as e:
                        print(f"[WARNING] 채널 종료 오류: {e}")
                
                # 상태 업데이트
                status.update({
                    'connected': False,
                    'channel': None,
                    'last_check': time.time()
                })
    
    def cleanup(self):
        """모든 연결 정리"""
        print("[INFO] gRPC 연결 정리 중...")
        
        with self._lock:
            for server_address, status in self._connection_status.items():
                channel = status.get('channel')
                if channel:
                    try:
                        channel.close()
                    except Exception as e:
                        print(f"[WARNING] 채널 정리 오류 ({server_address}): {e}")
            
            self._connection_status.clear()
        
        print("[INFO] gRPC 연결 정리 완료")

# 전역 gRPC 매니저 인스턴스
grpc_manager = GrpcManager()