# GRPC/stubs/client.py - 완전한 gRPC 클라이언트 (모든 RPC 지원)
import grpc
import sys
import os
import time
import threading

# protobuf 모듈 import
try:
    import masterdevice_pb2
    import masterdevice_pb2_grpc
    GRPC_AVAILABLE = True
except ImportError as e:
    print(f"[CLIENT ERROR] protobuf 모듈 import 실패: {e}")
    GRPC_AVAILABLE = False

def create_grpc_channel(ip: str, port: int, timeout: int = 5):
    """gRPC 채널 생성 및 연결 확인"""
    if not GRPC_AVAILABLE:
        return None, "gRPC 모듈이 로드되지 않음"
    
    try:
        server_address = f"{ip}:{port}"
        print(f"[CLIENT] gRPC 연결 시도: {server_address}")
        
        # 채널 생성
        channel = grpc.insecure_channel(server_address)
        
        # 연결 상태 확인 (타임아웃 포함)
        try:
            grpc.channel_ready_future(channel).result(timeout=timeout)
            print(f"[CLIENT] ✅ gRPC 서버 연결 성공: {server_address}")
            return channel, "연결 성공"
        except grpc.FutureTimeoutError:
            print(f"[CLIENT] ⚠️ gRPC 서버 연결 타임아웃 (서버 확인 필요): {server_address}")
            return channel, "연결 타임아웃 (비동기 시도)"
        
    except Exception as e:
        print(f"[CLIENT] ❌ gRPC 채널 생성 실패: {e}")
        return None, f"채널 생성 실패: {str(e)}"

def test_connection(ip: str, port: int) -> tuple:
    """연결 테스트"""
    channel, status = create_grpc_channel(ip, port, timeout=3)
    if channel:
        try:
            # 실제 Connect RPC 호출해서 테스트
            stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
            request = masterdevice_pb2.ConnectCommand(command="TEST_CONNECTION")
            response = stub.Connect(request, timeout=3.0)
            channel.close()
            return True, f"연결 성공: {response.message}"
        except Exception as e:
            channel.close()
            return False, f"연결 실패: {str(e)}"
    else:
        return False, status

# ============= 모든 RPC 서비스 함수들 =============

def send_connect_command(ip: str, port: int, command: str = "CONNECT"):
    """Connect 명령 전송"""
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        request = masterdevice_pb2.ConnectCommand(command=command)
        
        print(f"[CLIENT] Connect 전송: {command}")
        response = stub.Connect(request, timeout=3.0)
        
        result = f"Connect 성공: {response.message}"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"Connect RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"Connect 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    finally:
        channel.close()

def send_gravity_comp_gain(ip: str, port: int, shoulder_gain: float, joint_gain: float):
    """GravityCompGain 명령 전송"""
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        # 값 범위 검증
        shoulder_gain = max(0.2, min(1.0, float(shoulder_gain)))
        joint_gain = max(0.2, min(1.0, float(joint_gain)))
        
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        request = masterdevice_pb2.GravityCompGainRequest(
            shoulder_gain=shoulder_gain,
            joint_gain=joint_gain
        )
        
        print(f"[CLIENT] GravityCompGain 전송: shoulder={shoulder_gain:.2f}, joint={joint_gain:.2f}")
        response = stub.GravityCompGain(request, timeout=3.0)
        
        result = f"토크 게인 설정 성공: {response.message}"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"GravityCompGain RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"토크 게인 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    finally:
        channel.close()

def send_gravity_mode_command(ip: str, port: int, command: str):
    """GravityMode 명령 전송"""
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        request = masterdevice_pb2.GravityState(command=command)
        
        print(f"[CLIENT] GravityMode 전송: {command}")
        response = stub.GravityMode(request, timeout=3.0)
        
        result = f"GravityMode 성공: {command}"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"GravityMode RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"GravityMode 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    finally:
        channel.close()

def send_position_mode_command(ip: str, port: int, command: str):
    """PositionMode 명령 전송"""
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        request = masterdevice_pb2.PositionState(command=command)
        
        print(f"[CLIENT] PositionMode 전송: {command}")
        response = stub.PositionMode(request, timeout=3.0)
        
        result = f"PositionMode 성공: {command}"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"PositionMode RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"PositionMode 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    finally:
        channel.close()
def send_homing_command(ip: str, port: int, command: str) -> str:
    """
    Homing 명령 전송 - 기존 Homing RPC 직접 사용
    """
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        
        # ⭐ 수정: 기존 Homing RPC 사용
        request = masterdevice_pb2.HomingCommand()
        request.command = command  # "GO_HOME"
        
        print(f"[CLIENT] Homing 명령 전송: {command} → {ip}:{port}")
        
        # 기존 Homing RPC 호출
        response = stub.Homing(request, timeout=10.0)
        
        result = f"Homing 성공: {response.message if hasattr(response, 'message') else 'OK'}"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"Homing RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"Homing 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    finally:
        channel.close()


def send_master_teleop_command(ip: str, port: int, command: str):
    """Teleoperation1 명령 전송"""
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        request = masterdevice_pb2.TeleoperationCommand1(command=command)
        
        print(f"[CLIENT] Teleoperation1 전송: {command}")
        response = stub.Teleoperation1(request, timeout=5.0)
        
        result = f"Teleoperation1 성공: {response.message}"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"Teleoperation1 RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"Teleoperation1 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    finally:
        channel.close()

def send_delete_command(ip: str, port: int, command: str):
    """Delete 명령 전송"""
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        request = masterdevice_pb2.DeleteCommand(command=command)
        
        print(f"[CLIENT] Delete 전송: {command}")
        response = stub.Delete(request, timeout=5.0)
        
        result = f"Delete 성공: {command}"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"Delete RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"Delete 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    finally:
        channel.close()

def send_power_off_command(ip: str, port: int, command: str = "POWER_OFF"):
    """PowerOff 명령 전송"""
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        request = masterdevice_pb2.PowerOffStart(command=command)
        
        print(f"[CLIENT] PowerOff 전송: {command}")
        response = stub.PowerOff(request, timeout=5.0)
        
        result = f"PowerOff 성공: {response.message}"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"PowerOff RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"PowerOff 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    finally:
        channel.close()

# ============= Save 관련 함수들 =============

def send_save_command(ip: str, port: int, command: str = "SAVE", angles: list = None):
    """Save 명령 전송 (단일 포즈 저장)"""
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        
        def generate_save_requests():
            """SaveCommand 스트림 생성"""
            # 시작 명령
            if command == "SAVE":
                start_request = masterdevice_pb2.SaveCommand(command="SAVE_START")
                yield start_request
            
            # 각도 데이터 (있는 경우)
            if angles and len(angles) > 0:
                angles_request = masterdevice_pb2.SaveCommand()
                angles_request.angle.extend([float(a) for a in angles])
                yield angles_request
            
            # 종료 명령
            if command == "SAVE":
                end_request = masterdevice_pb2.SaveCommand(command="SAVE_STOP")
                yield end_request
        
        print(f"[CLIENT] Save 스트림 전송: command='{command}', angles={len(angles) if angles else 0}개")
        response = stub.Save(generate_save_requests(), timeout=10.0)
        
        result = f"Save 성공: 저장 완료"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"Save RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"Save 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    finally:
        channel.close()

def start_save_streaming(ip: str, port: int, on_data_callback=None, duration: int = 10):
    """Save 스트리밍 시작 - 단순화된 구현으로 UNIMPLEMENTED 오류 해결"""
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        
        def generate_simple_save_requests():
            """단순한 Save 요청 생성 (STREAM 명령 제거)"""
            # 기본 Save 시작
            start_request = masterdevice_pb2.SaveCommand(command="SAVE_START")
            yield start_request
            
            # 지속적인 데이터 수집 (duration 동안)
            start_time = time.time()
            sample_count = 0
            
            while (time.time() - start_time) < duration:
                sample_count += 1
                # 빈 각도 데이터로 샘플링 트리거
                data_request = masterdevice_pb2.SaveCommand(command="SAVE_SAMPLE")
                yield data_request
                time.sleep(0.1)  # 10Hz 샘플링
            
            # Save 종료
            end_request = masterdevice_pb2.SaveCommand(command="SAVE_STOP")
            yield end_request
        
        print(f"[CLIENT] Save 스트리밍 시작: {duration}초 동안 (단순화된 방식)")
        response = stub.Save(generate_simple_save_requests(), timeout=float(duration + 5))
        
        # 콜백이 있으면 데이터 전달
        if on_data_callback and callable(on_data_callback):
            on_data_callback({"status": "completed", "message": "스트리밍 완료"})
        
        result = f"Save 스트리밍 완료: {duration}초"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"Save 스트리밍 RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        if on_data_callback:
            on_data_callback({"status": "error", "message": error_msg})
        return error_msg
    except Exception as e:
        error_msg = f"Save 스트리밍 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        if on_data_callback:
            on_data_callback({"status": "error", "message": error_msg})
        return error_msg
    finally:
        channel.close()

# ============= Teleoperation2 스트리밍 지원 =============

def send_teleoperation2_stream(ip: str, port: int, angles_stream: list, on_progress_callback=None):
    """Teleoperation2 스트리밍"""
    channel, status = create_grpc_channel(ip, port)
    if not channel:
        return f"연결 실패: {status}"
    
    try:
        stub = masterdevice_pb2_grpc.masterdeviceStub(channel)
        
        def generate_teleop_requests():
            """TeleoperationCommand2 스트림 생성"""
            for i, angles in enumerate(angles_stream):
                request = masterdevice_pb2.TeleoperationCommand2()
                request.angle.extend([float(a) for a in angles])
                request.seq = i + 1
                request.t_capture_ns = int(time.time() * 1_000_000_000)
                request.t_send_ns = int(time.time() * 1_000_000_000)
                
                if on_progress_callback:
                    on_progress_callback({"sample": i+1, "total": len(angles_stream), "angles": angles})
                
                yield request
                time.sleep(0.01)  # 100Hz
        
        print(f"[CLIENT] Teleoperation2 스트림 시작: {len(angles_stream)}개 샘플")
        response = stub.Teleoperation2(generate_teleop_requests(), timeout=30.0)
        
        result = f"Teleoperation2 스트리밍 성공: {response.message}"
        print(f"[CLIENT] ✅ {result}")
        return result
        
    except grpc.RpcError as e:
        error_msg = f"Teleoperation2 RPC 실패: {e.code()} - {e.details()}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"Teleoperation2 요청 오류: {str(e)}"
        print(f"[CLIENT] ❌ {error_msg}")
        return error_msg
    finally:
        channel.close()

# ============= 상태 조회 기능 (Homing RPC 확장 사용) =============

def get_robot_status(ip: str, port: int):
    """로봇 상태 조회"""
    return send_homing_command(ip, port, "GET_STATUS", timeout=5)

def get_saved_poses(ip: str, port: int):
    """저장된 포즈 조회"""
    return send_homing_command(ip, port, "GET_POSES", timeout=5)

# ============= 실시간 모니터링 함수들 =============

def start_realtime_monitoring(ip: str, port: int, duration: int = 60, callback=None):
    """실시간 모니터링 시작 (별도 스레드에서 실행)"""
    def monitoring_thread():
        """모니터링 스레드 함수"""
        start_time = time.time()
        sample_count = 0
        
        try:
            while (time.time() - start_time) < duration:
                sample_count += 1
                
                # 연결 확인
                is_connected, status = test_connection(ip, port)
                
                if callback:
                    callback({
                        "type": "monitoring",
                        "sample": sample_count,
                        "connected": is_connected,
                        "status": status,
                        "timestamp": time.time()
                    })
                
                time.sleep(1.0)  # 1초마다 체크
                
        except Exception as e:
            if callback:
                callback({"type": "error", "message": str(e)})
    
    # 별도 스레드에서 모니터링 실행
    thread = threading.Thread(target=monitoring_thread, daemon=True)
    thread.start()
    return thread

# ============= 유틸리티 함수들 =============

def validate_gain_values(shoulder_gain: float, joint_gain: float) -> tuple:
    """게인 값 검증 및 정규화"""
    try:
        shoulder = max(0.2, min(1.0, float(shoulder_gain)))
        joint = max(0.2, min(1.0, float(joint_gain)))
        
        is_valid = (0.2 <= shoulder <= 1.0) and (0.2 <= joint <= 1.0)
        message = "Valid" if is_valid else "Values clamped to valid range"
        
        return shoulder, joint, is_valid, message
        
    except (ValueError, TypeError) as e:
        return 0.6, 0.7, False, f"Invalid input: {str(e)}"

def format_joint_angles(angles: list, precision: int = 1) -> str:
    """관절 각도를 포맷팅하여 문자열로 반환"""
    if not angles:
        return "No angles"
    
    # 라디안을 도(degree)로 변환하여 표시
    display_angles = [round(angle * 180 / 3.14159, precision) for angle in angles]
    formatted = [f"{angle:+{precision+4}.{precision}f}°" for angle in display_angles]
    return ", ".join(formatted)

def log_grpc_call(method_name: str, ip: str, port: int, params: dict = None):
    """gRPC 호출 로깅"""
    timestamp = time.strftime("[%H:%M:%S]")
    param_str = f", params={params}" if params else ""
    print(f"{timestamp} [gRPC CALL] {method_name} → {ip}:{port}{param_str}")

# ============= 배치 명령 처리 =============

def send_multiple_commands(ip: str, port: int, commands: list):
    """여러 명령을 순차적으로 전송"""
    results = []
    
    for cmd_info in commands:
        cmd_type = cmd_info.get("type")
        cmd_params = cmd_info.get("params", {})
        
        try:
            if cmd_type == "connect":
                result = send_connect_command(ip, port, cmd_params.get("command", "CONNECT"))
            elif cmd_type == "gain":
                result = send_gravity_comp_gain(ip, port, cmd_params.get("shoulder", 0.6), cmd_params.get("joint", 0.7))
            elif cmd_type == "gravity":
                result = send_gravity_mode_command(ip, port, cmd_params.get("command", "RESET"))
            elif cmd_type == "position":
                result = send_position_mode_command(ip, port, cmd_params.get("command", "RESET"))
            elif cmd_type == "homing":
                result = send_homing_command(ip, port, cmd_params.get("command", "GO_HOME"))
            elif cmd_type == "teleop":
                result = send_master_teleop_command(ip, port, cmd_params.get("command", "START"))
            elif cmd_type == "save":
                result = send_save_command(ip, port, cmd_params.get("command", "SAVE"), cmd_params.get("angles"))
            elif cmd_type == "delete":
                result = send_delete_command(ip, port, cmd_params.get("command", "CLEAR"))
            elif cmd_type == "power":
                result = send_power_off_command(ip, port, cmd_params.get("command", "POWER_OFF"))
            else:
                result = f"Unknown command type: {cmd_type}"
            
            results.append({"command": cmd_info, "result": result, "success": "성공" in result})
            
            # 명령 간 간격
            time.sleep(0.1)
            
        except Exception as e:
            results.append({"command": cmd_info, "result": f"실행 오류: {str(e)}", "success": False})
    
    return results

# ============= 연결 상태 모니터링 =============

class ConnectionMonitor:
    """gRPC 연결 상태 지속 모니터링"""
    
    def __init__(self, ip: str, port: int, check_interval: float = 2.0):
        self.ip = ip
        self.port = port
        self.check_interval = check_interval
        self.is_running = False
        self.thread = None
        self.callbacks = []
    
    def add_callback(self, callback):
        """상태 변경 콜백 추가"""
        if callable(callback):
            self.callbacks.append(callback)
    
    def start_monitoring(self):
        """모니터링 시작"""
        if self.is_running:
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print(f"[CONNECTION_MONITOR] 모니터링 시작: {self.ip}:{self.port}")
    
    def stop_monitoring(self):
        """모니터링 중지"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        print(f"[CONNECTION_MONITOR] 모니터링 중지")
    
    def _monitor_loop(self):
        """모니터링 루프"""
        last_status = None
        
        while self.is_running:
            try:
                is_connected, message = test_connection(self.ip, self.port)
                
                # 상태 변경 시에만 콜백 호출
                if is_connected != last_status:
                    status_data = {
                        "connected": is_connected,
                        "message": message,
                        "timestamp": time.time(),
                        "ip": self.ip,
                        "port": self.port
                    }
                    
                    for callback in self.callbacks:
                        try:
                            callback(status_data)
                        except Exception as e:
                            print(f"[CONNECTION_MONITOR] 콜백 오류: {e}")
                    
                    last_status = is_connected
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"[CONNECTION_MONITOR] 모니터링 오류: {e}")
                time.sleep(self.check_interval)

if __name__ == "__main__":
    # 클라이언트 테스트 코드
    print("=== 완전한 gRPC Client 테스트 ===")
    print(f"gRPC 사용 가능: {GRPC_AVAILABLE}")
    
    if GRPC_AVAILABLE and len(sys.argv) >= 3:
        test_ip = sys.argv[1]
        test_port = int(sys.argv[2])
        
        print(f"\n연결 테스트: {test_ip}:{test_port}")
        is_connected, message = test_connection(test_ip, test_port)
        print(f"결과: {message}")
        
        if is_connected:
            # 모든 RPC 함수 테스트
            print(f"\n=== 전체 RPC 테스트 ===")
            
            # 1. Connect 테스트
            result = send_connect_command(test_ip, test_port, "TEST_CONNECT")
            print(f"Connect: {result}")
            
            # 2. 토크 게인 테스트
            result = send_gravity_comp_gain(test_ip, test_port, 0.6, 0.7)
            print(f"Gain: {result}")
            
            # 3. 상태 조회 테스트
            result = get_robot_status(test_ip, test_port)
            print(f"Status: {result}")
            
            # 4. 포즈 조회 테스트
            result = get_saved_poses(test_ip, test_port)
            print(f"Poses: {result}")
            
            print(f"\n✅ 모든 테스트 완료")
            
    else:
        print("사용법: python client.py <IP> <PORT>")