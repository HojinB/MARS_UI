# GRPC/stubs/server.py - 모듈화된 gRPC 서버
import time
from concurrent import futures
import grpc
import threading
import sys
from pathlib import Path
import json
import random
import math

# 패키지/상대 임포트로 고정 (둘 다 지원)
try:
    # 패키지로 실행: python -m GRPC.stubs.server 또는 다른 파일에서 import
    from . import masterdevice_pb2 as pb2
    from . import masterdevice_pb2_grpc as pb2_grpc
except ImportError:
    # 파일 단독 실행: python GRPC/stubs/server.py
    sys.path.append(str(Path(__file__).resolve().parent))
    import masterdevice_pb2 as pb2
    import masterdevice_pb2_grpc as pb2_grpc

# grpc_data_manager import 시도
try:
    # 상위 디렉토리에서 import
    sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
    from grpc_data_manager import grpc_data_manager
    DATA_MANAGER_AVAILABLE = True
except ImportError as e:
    print(f"[WARNING] grpc_data_manager import 실패: {e}")
    DATA_MANAGER_AVAILABLE = False
    grpc_data_manager = None


class PCGRPCServiceImpl(pb2_grpc.masterdeviceServicer):
    """PC에서 실행되는 gRPC 서비스 - 라즈베리파이로부터 상태/데이터 수신"""

    def __init__(self):
        self.request_count = 0
        self.enable_data_manager = DATA_MANAGER_AVAILABLE
        self.server_start_time = time.time()
        self.client_connections = {}
        print("🤖 PC gRPC 서비스 초기화 완료")
        if self.enable_data_manager:
            print("✅ Data Manager 연동 활성화")
        else:
            print("⚠️ Data Manager 연동 비활성화")

    def _log_request(self, method_name, request_data, client_addr=None):
        """요청 로깅 및 데이터 매니저에 기록"""
        self.request_count += 1
        timestamp = time.strftime("[%H:%M:%S]")

        # 클라이언트 IP 추출
        client_ip = "unknown"
        if client_addr:
            try:
                parts = client_addr.split(':')
                if len(parts) >= 2:
                    client_ip = parts[1] if parts[0] == "ipv4" else parts[-1]
            except:
                client_ip = str(client_addr)

        print(f"{timestamp} 🔥 요청 #{self.request_count} - {method_name}: {request_data}")
        print(f"    👤 클라이언트: {client_ip}")
        
        if self.enable_data_manager:
            grpc_data_manager.add_grpc_entry("RECEIVED", f"[{method_name}] {request_data} (from {client_ip})")

        # 클라이언트 연결 추적
        self.client_connections[client_ip] = {
            "last_seen": time.time(),
            "request_count": self.client_connections.get(client_ip, {}).get("request_count", 0) + 1,
            "last_rpc": method_name
        }

    def Connect(self, request, context):
        """최소한의 Connect 구현 - 디버깅용"""
        print(f"[SERVER] Connect 요청 수신: {request.command}")
        
        try:
            # 최소한의 로깅
            self.request_count += 1
            print(f"[SERVER] 요청 번호: {self.request_count}")
            
            # 즉시 응답 반환
            response_msg = "SUCCESS"
            response = pb2.ConnectMessage(message=response_msg)
            
            print(f"[SERVER] ✅ 응답 반환: {response_msg}")
            return response
            
        except Exception as e:
            print(f"[SERVER] ❌ Connect 오류: {e}")
            return pb2.ConnectMessage(message=f"ERROR: {str(e)}")

    def GravityMode(self, request, context):
        print(f"[SERVER] GravityMode 요청: {request.command}")
        try:
            self.request_count += 1
            command = request.command
            
            # Data Manager 업데이트 추가
            if self.enable_data_manager:
                try:
                    grpc_data_manager.set_gravity_mode(command)
                    # 상호 배타적 모드 처리
                    if "ON" in command.upper():
                        grpc_data_manager.set_position_mode("ALL_OFF")
                        print(f"[SERVER] Gravity {command} → Position 모드 자동 OFF")
                except Exception as dm_error:
                    print(f"[SERVER] Data Manager 업데이트 오류: {dm_error}")
            
            print(f"[SERVER] ✅ Gravity 모드 설정: {command}")
            return pb2.GravityReply()
        except Exception as e:
            return pb2.GravityReply()

    def PositionMode(self, request, context):
        print(f"[SERVER] PositionMode 요청: {request.command}")
        try:
            self.request_count += 1
            command = request.command
            
            # Data Manager 업데이트 추가
            if self.enable_data_manager:
                try:
                    grpc_data_manager.set_position_mode(command)
                    # 상호 배타적 모드 처리
                    if "ON" in command.upper():
                        grpc_data_manager.set_gravity_mode("ALL_OFF")
                        print(f"[SERVER] Position {command} → Gravity 모드 자동 OFF")
                except Exception as dm_error:
                    print(f"[SERVER] Data Manager 업데이트 오류: {dm_error}")
            
            print(f"[SERVER] ✅ Position 모드 설정: {command}")
            return pb2.PositionReply()
        except Exception as e:
            return pb2.PositionReply()

    def GravityCompGain(self, request, context):
        """토크 게인 설정 RPC 핸들러"""
        payload = f"shoulder={request.shoulder_gain:.2f}, joint={request.joint_gain:.2f}"
        self._log_request("GravityCompGain", payload, context.peer())
        
        try:
            shoulder_gain = request.shoulder_gain
            joint_gain = request.joint_gain
            
            # 값 범위 검증
            if not (0.2 <= shoulder_gain <= 1.0) or not (0.2 <= joint_gain <= 1.0):
                error_msg = f"게인 값 범위 오류: shoulder={shoulder_gain}, joint={joint_gain} (허용범위: 0.2-1.0)"
                print(f"    {error_msg}")
                if self.enable_data_manager:
                    grpc_data_manager.add_grpc_entry("GAIN_ERROR", error_msg)
                return pb2.GravityCompGainReply(message=error_msg)
            
            # grpc_data_manager에 게인 값 업데이트
            if self.enable_data_manager:
                grpc_data_manager.update_gain_values(shoulder_gain, joint_gain)
            
            response_msg = "Gain defined."
            print(f"    토크 게인 설정 완료: shoulder={shoulder_gain:.2f}, joint={joint_gain:.2f}")
            return pb2.GravityCompGainReply(message=response_msg)
            
        except Exception as e:
            error_msg = f"토크 게인 처리 오류: {str(e)}"
            print(f"    {error_msg}")
            if self.enable_data_manager:
                grpc_data_manager.add_grpc_entry("ERROR", error_msg)
            return pb2.GravityCompGainReply(message=error_msg)

    def Save(self, request_iterator, context):
        """Save 스트림 처리 - 안정화 버전"""
        print(f"[SERVER] Save 스트림 시작")
        
        total_msgs = 0
        last_action = "NONE"
        
        try:
            for req in request_iterator:
                total_msgs += 1
                
                try:
                    cmd = getattr(req, "command", "") or ""
                    angles = list(getattr(req, "angle", []))
                    
                    if cmd == "SAVE_START":
                        if self.enable_data_manager:
                            try:
                                grpc_data_manager.start_recording()
                            except Exception as dm_error:
                                print(f"    ⚠️ Data Manager 녹화 시작 오류: {dm_error}")
                        last_action = "SAVE_START"
                        print(f"    📹 SAVE_START")
                        
                    elif cmd == "SAVE_STOP":
                        pose_name = None
                        if self.enable_data_manager:
                            try:
                                pose_name = grpc_data_manager.stop_recording()
                            except Exception as dm_error:
                                print(f"    ⚠️ Data Manager 녹화 중지 오류: {dm_error}")
                        last_action = f"SAVE_STOP:{pose_name}"
                        print(f"    💾 SAVE_STOP -> {pose_name}")
                        
                    elif len(angles) > 0:
                        pose_name = None
                        if self.enable_data_manager:
                            try:
                                pose_name = grpc_data_manager.save_encoder_pose(angles)
                            except Exception as dm_error:
                                print(f"    ⚠️ Data Manager 포즈 저장 오류: {dm_error}")
                                pose_name = f"pose_{total_msgs}"
                        last_action = f"SAVE_ANGLES:{pose_name}"
                        print(f"    💾 각도 저장: {pose_name} ({len(angles)}개)")
                    
                    # 주기적 상태 출력
                    if total_msgs % 50 == 0:
                        print(f"    📊 Save 스트림: {total_msgs}개 처리됨")
                        
                except Exception as msg_error:
                    print(f"    ⚠️ 메시지 처리 오류: {msg_error}")
                    continue

            print(f"[SERVER] ✅ Save 스트림 완료: {total_msgs}개, 마지막={last_action}")
            return pb2.SaveReply()
            
        except Exception as e:
            print(f"[SERVER] ❌ Save 스트림 처리 오류: {e}")
            return pb2.SaveReply()

            print(f"    ✅ Save stream end, total msgs={total_msgs}, last={last_action}")
            return pb2.SaveReply()
        except Exception as e:
            print(f"    ❌ Save 스트림 처리 오류: {e}")
            if self.enable_data_manager:
                grpc_data_manager.add_grpc_entry("ERROR", f"Save 스트림 오류: {str(e)}")
            return pb2.SaveReply()

    def Homing(self, request, context):
        self._log_request("Homing", request.command, context.peer())
        try:
            if request.command == "GO_HOME":
                message = "홈 위치 도달 완료"
                print("    🏠 홈 위치로 이동 시작")
                if self.enable_data_manager:
                    grpc_data_manager.add_grpc_entry("HOMING", "GO_HOME 명령 수신")
            else:
                message = f"홈 이동 처리 완료: {request.command}"
                if self.enable_data_manager:
                    grpc_data_manager.add_grpc_entry("HOMING", f"홈 명령: {request.command}")
            print(f"    ✅ {message}")
            return pb2.HomingReply(message=message)
        except Exception as e:
            print(f"    ❌ 홈 이동 오류: {e}")
            if self.enable_data_manager:
                grpc_data_manager.add_grpc_entry("ERROR", f"홈 이동 오류: {str(e)}")
            return pb2.HomingReply(message=f"홈 이동 실패: {str(e)}")

    def Teleoperation1(self, request, context):
        self._log_request("Teleoperation1", request.command, context.peer())
        try:
            if request.command == "START":
                message = "텔레오퍼레이션 시작됨"
                print("    🎮 텔레오퍼레이션 시작")
                if self.enable_data_manager:
                    grpc_data_manager.add_grpc_entry("TELEOP", "텔레오퍼레이션 START")
            elif request.command == "STOP":
                message = "텔레오퍼레이션 중지됨"
                print("    ⛔ 텔레오퍼레이션 중지")
                if self.enable_data_manager:
                    grpc_data_manager.add_grpc_entry("TELEOP", "텔레오퍼레이션 STOP")
            else:
                message = f"텔레오퍼레이션 처리됨: {request.command}"
                if self.enable_data_manager:
                    grpc_data_manager.add_grpc_entry("TELEOP", f"텔레오퍼레이션 명령: {request.command}")
            return pb2.TeleoperationMessage1(message=message)
        except Exception as e:
            print(f"    ❌ 텔레오퍼레이션 오류: {e}")
            if self.enable_data_manager:
                grpc_data_manager.add_grpc_entry("ERROR", f"텔레오퍼레이션 오류: {str(e)}")
            return pb2.TeleoperationMessage1(message=f"텔레오퍼레이션 오류: {str(e)}")

    def Teleoperation2(self, request_iterator, context):
        self._log_request("Teleoperation2", "스트림 시작", context.peer())
        try:
            count = 0
            start_time = time.time()
            for request in request_iterator:
                count += 1
                angles = list(request.angle)
                if self.enable_data_manager:
                    grpc_data_manager.update_encoder_data(angles)
                if count % 20 == 0:
                    elapsed = time.time() - start_time
                    fps = count / elapsed if elapsed > 0 else 0.0
                    print(f"    🎮 스트림 데이터 {count}: {len(angles)}개 관절, {fps:.1f} FPS")

            duration = time.time() - start_time
            fps = count / duration if duration > 0 else 0.0
            message = f"스트림 처리 완료: {count}개 데이터, {fps:.1f} FPS, {duration:.1f}초"
            print(f"    ✅ {message}")
            if self.enable_data_manager:
                grpc_data_manager.add_grpc_entry("TELEOP_STREAM", message)
            return pb2.TeleoperationMessage2(message=message)
        except Exception as e:
            error_msg = f"스트림 처리 오류: {str(e)}"
            print(f"    ❌ {error_msg}")
            if self.enable_data_manager:
                grpc_data_manager.add_grpc_entry("ERROR", error_msg)
            return pb2.TeleoperationMessage2(message=error_msg)

    def Delete(self, request, context):
        """삭제 명령 처리 - 안정화 버전"""
        print(f"[SERVER] Delete 요청: {request.command}")
        
        try:
            self.request_count += 1
            command = request.command.upper()
            message = "삭제 처리 완료"
            
            if self.enable_data_manager:
                try:
                    if "POSE" in command or "POSES" in command:
                        pose_count = len(grpc_data_manager.get_saved_poses())
                        grpc_data_manager.clear_poses()
                        message = f"포즈 데이터 삭제: {pose_count}개"
                        print(f"    🗑️ 포즈 삭제: {pose_count}개")
                        
                    elif "RECORDED" in command or "LOG" in command:
                        grpc_data_manager.delete_recorded_data()
                        message = "녹화 데이터 삭제 완료"
                        print(f"    🗑️ 녹화 데이터 삭제")
                        
                    elif "ALL" in command:
                        grpc_data_manager.reset_all_data()
                        message = "모든 데이터 삭제 완료"
                        print(f"    🗑️ 전체 데이터 삭제")
                        
                    else:
                        message = f"삭제 명령 처리됨: {command}"
                        print(f"    🗑️ 기타 삭제: {command}")
                        
                except Exception as dm_error:
                    print(f"    ⚠️ Data Manager 삭제 오류: {dm_error}")
                    message = f"삭제 처리됨 (일부 오류 발생)"
            else:
                message = f"삭제 신호 수신: {command}"
                print(f"    🗑️ 삭제 신호: {command}")
            
            print(f"[SERVER] ✅ {message}")
            return pb2.DeleteReply()
            
        except Exception as e:
            error_msg = f"삭제 처리 오류: {str(e)}"
            print(f"[SERVER] ❌ {error_msg}")
            return pb2.DeleteReply()

    def PowerOff(self, request, context):
        self._log_request("PowerOff", request.command, context.peer())
        try:
            message = f"전원 관리 처리됨: {request.command}"
            if request.command == "POWER_OFF":
                message = "시스템 종료 신호 처리됨"
                if self.enable_data_manager:
                    grpc_data_manager.disconnect_client()
                print(f"    🔌 시스템 전원 종료 신호")
            
            if self.enable_data_manager:
                grpc_data_manager.add_grpc_entry("POWER", message)
            return pb2.PowerOffReply(message=message)
        except Exception as e:
            print(f"    ❌ 전원 관리 오류: {e}")
            if self.enable_data_manager:
                grpc_data_manager.add_grpc_entry("ERROR", f"전원 관리 오류: {str(e)}")
            return pb2.PowerOffReply(message=f"전원 관리 실패: {str(e)}")

    def get_stats(self):
        """서버 통계 정보 반환"""
        uptime = time.time() - self.server_start_time
        active_clients = len([c for c in self.client_connections.values() 
                            if (time.time() - c["last_seen"]) < 30])
        
        return {
            "total_requests": self.request_count,
            "uptime_seconds": uptime,
            "active_clients": active_clients,
            "total_clients": len(self.client_connections),
            "data_manager_enabled": self.enable_data_manager
        }


def create_grpc_server(host: str = "0.0.0.0", port: int = 50052, max_workers: int = 10):
    """gRPC 서버 생성 및 반환"""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    service_impl = PCGRPCServiceImpl()
    pb2_grpc.add_masterdeviceServicer_to_server(service_impl, server)
    
    bind_addr = f"{host}:{port}"
    server.add_insecure_port(bind_addr)
    
    print(f"🚀 gRPC 서버 생성 완료: {bind_addr}")
    return server, service_impl


def serve_standalone(host: str = "0.0.0.0", port: int = 50055, max_workers: int = 10):
    """독립 실행용 서버 (테스트용)"""
    server, service_impl = create_grpc_server(host, port, max_workers)
    
    print("=" * 70)
    print("PC gRPC 서버 (독립 실행 모드)")
    print("=" * 70)
    print(f"바인딩: {host}:{port}")
    print(f"최대 워커: {max_workers}")
    print(f"데이터 매니저: {'활성화' if DATA_MANAGER_AVAILABLE else '비활성화'}")
    print("=" * 70)

    server.start()
    print("서버 시작 완료. 요청 대기 중...")
    
    try:
        while True:
            time.sleep(10)
            stats = service_impl.get_stats()
            print(f"[통계] 요청: {stats['total_requests']}, 활성 클라이언트: {stats['active_clients']}")
    except KeyboardInterrupt:
        print("\n종료 신호 수신. 서버 정리 중...")
        server.stop(grace=3.0)
        print("서버 종료 완료.")


if __name__ == "__main__":
    # 독립 실행 시에만 서버 시작
    serve_standalone()