# grpc_data_manager.py - 통합된 실시간 데이터 관리 및 gRPC 스트림 처리
import time
import threading
import json
import os
import pandas as pd
import queue
from datetime import datetime
from collections import deque
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

@dataclass
class StreamSample:
    """스트림 샘플 데이터 클래스"""
    timestamp: float
    angles: List[float]
    sequence: int = 0
    session_id: str = ""
    capture_time_ns: int = 0
    send_time_ns: int = 0

class GRPCDataManager:
    """통합된 gRPC 데이터 관리 클래스"""
    
    def __init__(self, max_samples: int = 10000):
        self.max_samples = max_samples
        self.lock = threading.Lock()
        
        # 실시간 데이터 저장소
        self.encoder_data = deque(maxlen=max_samples)
        self.streaming_data = deque(maxlen=max_samples)
        self.save_stream_data = deque(maxlen=max_samples)  # Save Stream 전용
        self.pose_data = []
        self.grpc_logs = deque(maxlen=1000)
        self.recorded_samples = []
        
        # 스트림 처리
        self.stream_queue = queue.Queue(maxsize=1000)
        self.stream_callbacks = []
        self.stream_worker_thread = None
        self.stream_worker_running = False
        
        # 상태 관리
        self.is_streaming = False
        self.is_recording = False
        self.is_save_streaming = False  # Save Stream 상태
        self.robot_connected = False
        
        # 로봇 상태
        self.robot_state = {
            "connected": False,
            "gravity": {"left": {"active": False}, "right": {"active": False}},
            "position": {"left": {"active": True}, "right": {"active": True}},
            "hardware_buttons": {
                "r_push_1": {"state": 1}, 
                "l_push_1": {"state": 1}, 
                "l_push_2": {"state": 1}
            },
            "communication": {"fps": 0.0, "interval": 0.0},
            "recording": {"active": False}
        }
        
        # 게인 값
        self.gain_values = {"shoulder_gain": 0.6, "joint_gain": 0.7}
        
        # 스트림 워커 시작
        self._start_stream_worker()
        
        print("[DATA_MANAGER] 통합 gRPC 데이터 매니저 초기화 완료")
    
    def _start_stream_worker(self):
        """스트림 워커 스레드 시작"""
        self.stream_worker_running = True
        self.stream_worker_thread = threading.Thread(target=self._stream_worker_loop, daemon=True)
        self.stream_worker_thread.start()
    
    def _stream_worker_loop(self):
        """스트림 워커 메인 루프"""
        print("[STREAM_WORKER] 스트림 워커 시작됨")
        
        while self.stream_worker_running:
            try:
                # 타임아웃으로 큐에서 데이터 가져오기
                sample = self.stream_queue.get(timeout=0.1)
                
                if sample is None:  # 종료 신호
                    break
                
                # 콜백 실행
                self._process_stream_sample(sample)
                self.stream_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[STREAM_WORKER] 처리 오류: {e}")
        
        print("[STREAM_WORKER] 스트림 워커 종료됨")
    
    def _process_stream_sample(self, sample: StreamSample):
        """스트림 샘플 처리"""
        with self.lock:
            callbacks_copy = self.stream_callbacks[:]
        
        for callback in callbacks_copy:
            try:
                callback(sample)
            except Exception as e:
                print(f"[STREAM_WORKER] 콜백 실행 오류: {e}")
    
    def add_stream_callback(self, callback: Callable[[StreamSample], None]):
        """스트림 콜백 추가"""
        with self.lock:
            self.stream_callbacks.append(callback)
    
    def add_stream_sample(self, angles: List[float], sequence: int = 0, 
                         session_id: str = "", capture_time_ns: int = 0, 
                         send_time_ns: int = 0) -> bool:
        """스트림 샘플 추가"""
        try:
            timestamp = time.time()
            sample = StreamSample(
                timestamp=timestamp,
                angles=angles[:],
                sequence=sequence,
                session_id=session_id,
                capture_time_ns=capture_time_ns or int(timestamp * 1_000_000_000),
                send_time_ns=send_time_ns or int(timestamp * 1_000_000_000)
            )
            
            self.stream_queue.put_nowait(sample)
            return True
            
        except queue.Full:
            return False
        except Exception as e:
            print(f"[DATA_MANAGER] 스트림 샘플 추가 오류: {e}")
            return False
    
    # ===============================
    # Save Stream 관련 메서드들
    # ===============================
    
    def start_save_streaming(self):
        """Save 스트리밍 시작"""
        with self.lock:
            self.is_save_streaming = True
            self.save_stream_data.clear()
            print("[DATA_MANAGER] Save 스트리밍 시작")
    
    def stop_save_streaming(self):
        """Save 스트리밍 중지"""
        with self.lock:
            self.is_save_streaming = False
            sample_count = len(self.save_stream_data)
            print(f"[DATA_MANAGER] Save 스트리밍 중지 - {sample_count}개 샘플 수집됨")
    
    def add_save_stream_sample(self, angles: List[float], timestamp: float = None):
        """Save Stream 샘플 추가"""
        if not self.is_save_streaming:
            return
            
        if timestamp is None:
            timestamp = time.time()
            
        with self.lock:
            sample = {
                "timestamp": timestamp,
                "angles": angles[:],
                "formatted": self._format_angles(angles),
                "datetime": datetime.fromtimestamp(timestamp).strftime("%H:%M:%S.%f")[:-3]
            }
            self.save_stream_data.append(sample)
    
    def get_save_stream_data(self, limit: int = 50) -> List[Dict]:
        """Save Stream 데이터 조회"""
        with self.lock:
            data_list = list(self.save_stream_data)
            return data_list[-limit:] if limit > 0 else data_list
    
    def get_save_stream_status(self) -> Dict[str, Any]:
        """Save Stream 상태 조회"""
        with self.lock:
            return {
                "active": self.is_save_streaming,
                "sample_count": len(self.save_stream_data),
                "last_update": self.save_stream_data[-1]["timestamp"] if self.save_stream_data else None
            }
    
    # ===============================
    # 기존 호환성 메서드들
    # ===============================
    
    def start_streaming(self):
        """일반 스트리밍 시작"""
        with self.lock:
            self.is_streaming = True
            self.streaming_data.clear()
            print("[DATA_MANAGER] 일반 스트리밍 시작")
    
    def stop_streaming(self):
        """일반 스트리밍 중지"""
        with self.lock:
            self.is_streaming = False
            print(f"[DATA_MANAGER] 일반 스트리밍 중지 - 총 {len(self.streaming_data)}개 샘플")
    
    def add_streaming_sample(self, angles: List[float], timestamp: float = None):
        """일반 스트리밍 샘플 추가"""
        if timestamp is None:
            timestamp = time.time()
            
        with self.lock:
            sample = {
                "timestamp": timestamp,
                "angles": angles[:],
                "formatted": self._format_angles(angles)
            }
            
            if self.is_streaming:
                self.streaming_data.append(sample)
            
            # Save Stream이 활성화되어 있으면 해당 데이터에도 추가
            if self.is_save_streaming:
                self.save_stream_data.append(sample)
    
    def get_streaming_data(self, limit: int = 50) -> List[Dict]:
        """일반 스트리밍 데이터 조회"""
        with self.lock:
            data_list = list(self.streaming_data)
            return data_list[-limit:] if limit > 0 else data_list
    
    def update_encoder_data(self, angles: List[float], timestamp: float = None):
        """엔코더 데이터 업데이트"""
        if timestamp is None:
            timestamp = time.time()
            
        with self.lock:
            sample = {
                "timestamp": timestamp,
                "angles": angles[:],
                "formatted": self._format_angles(angles)
            }
            self.encoder_data.append(sample)
            
            # 활성화된 스트리밍에 데이터 추가
            if self.is_streaming:
                self.streaming_data.append(sample)
            
            if self.is_save_streaming:
                self.save_stream_data.append(sample)
    
    def get_encoder_entries(self, limit: int = 10) -> List[Dict]:
        """엔코더 데이터 조회"""
        with self.lock:
            data_list = list(self.encoder_data)
            return data_list[-limit:] if limit > 0 else data_list
    
    def get_current_encoder_data(self) -> Dict:
        """현재 엔코더 데이터 조회"""
        with self.lock:
            if self.encoder_data:
                return dict(self.encoder_data[-1])
            else:
                return {
                    "angles": [0.0] * 14, 
                    "formatted": "No data", 
                    "timestamp": time.time()
                }
    
    # ===============================
    # 포즈 관리 메서드들
    # ===============================
    
    def save_encoder_pose(self, angles: List[float], name: str = None) -> str:
        """엔코더 포즈 저장"""
        if name is None:
            timestamp = datetime.now().strftime("%H%M%S")
            name = f"Pose_{timestamp}"
            
        with self.lock:
            pose = {
                "name": name,
                "timestamp": time.time(),
                "angles": angles[:],
                "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.pose_data.append(pose)
            
        print(f"[DATA_MANAGER] 포즈 저장: {name}")
        return name
    
    def get_saved_poses(self) -> List[Dict]:
        """저장된 포즈 조회"""
        with self.lock:
            return self.pose_data[:]
    
    def clear_poses(self):
        """저장된 포즈 클리어"""
        with self.lock:
            count = len(self.pose_data)
            self.pose_data.clear()
            print(f"[DATA_MANAGER] {count}개 포즈 클리어됨")
    
    def save_pose(self, angles: List[float], name: str = None) -> str:
        """포즈 저장 (호환성)"""
        return self.save_encoder_pose(angles, name)
    
    # ===============================
    # 게인 관리 메서드들
    # ===============================
    
    def update_gain_values(self, shoulder_gain: float, joint_gain: float):
        """게인 값 업데이트"""
        with self.lock:
            self.gain_values["shoulder_gain"] = float(shoulder_gain)
            self.gain_values["joint_gain"] = float(joint_gain)
            print(f"[DATA_MANAGER] 게인 업데이트: S={shoulder_gain:.2f}, J={joint_gain:.2f}")
    
    def get_current_gain_values(self) -> Dict[str, float]:
        """현재 게인 값 조회"""
        with self.lock:
            return self.gain_values.copy()
    
    def reset_gain_to_default(self):
        """게인 값을 기본값으로 리셋"""
        with self.lock:
            self.gain_values = {"shoulder_gain": 0.6, "joint_gain": 0.7}
            print("[DATA_MANAGER] 게인 값 기본값으로 리셋")
    
    # ===============================
    # 로봇 상태 관리 메서드들
    # ===============================
    
    def connect_client(self, command: str = "CONNECT"):
        """클라이언트 연결"""
        with self.lock:
            self.robot_state["connected"] = True
            self.add_grpc_entry("CONNECT", f"클라이언트 연결: {command}")
    
    def disconnect_client(self):
        """클라이언트 연결 해제"""
        with self.lock:
            self.robot_state["connected"] = False
            self.add_grpc_entry("DISCONNECT", "클라이언트 연결 해제")
    
    def update_robot_state(self, **kwargs):
        """로봇 상태 업데이트"""
        with self.lock:
            for key, value in kwargs.items():
                if key in self.robot_state:
                    if isinstance(self.robot_state[key], dict) and isinstance(value, dict):
                        self.robot_state[key].update(value)
                    else:
                        self.robot_state[key] = value
    
    def set_gravity_mode(self, command):
        """중력 모드 설정 - 왼팔/오른팔 독립적"""
        if not hasattr(self, 'robot_state'):
            self.robot_state = {
                "gravity": {"left_active": False, "right_active": False},
                "position": {"left_active": True, "right_active": True}
            }
        
        if command == "LEFT_ON":
            self.robot_state["gravity"]["left_active"] = True
            self.robot_state["position"]["left_active"] = False
            print("[DATA_MANAGER] 왼팔 Gravity 모드 ON")
            
        elif command == "LEFT_OFF":
            self.robot_state["gravity"]["left_active"] = False
            self.robot_state["position"]["left_active"] = True
            print("[DATA_MANAGER] 왼팔 Gravity 모드 OFF")
            
        elif command == "RIGHT_ON":
            self.robot_state["gravity"]["right_active"] = True
            self.robot_state["position"]["right_active"] = False
            print("[DATA_MANAGER] 오른팔 Gravity 모드 ON")
            
        elif command == "RIGHT_OFF":
            self.robot_state["gravity"]["right_active"] = False
            self.robot_state["position"]["right_active"] = True
            print("[DATA_MANAGER] 오른팔 Gravity 모드 OFF")

    def set_position_mode(self, command):
        """포지션 모드 설정 - 왼팔/오른팔 독립적"""
        if not hasattr(self, 'robot_state'):
            self.robot_state = {
                "gravity": {"left_active": False, "right_active": False},
                "position": {"left_active": True, "right_active": True}
            }
        
        if command == "LEFT_ON":
            self.robot_state["position"]["left_active"] = True
            self.robot_state["gravity"]["left_active"] = False
            print("[DATA_MANAGER] 왼팔 Position 모드 ON")
            
        elif command == "LEFT_OFF":
            self.robot_state["position"]["left_active"] = False
            print("[DATA_MANAGER] 왼팔 Position 모드 OFF")
            
        elif command == "RIGHT_ON":
            self.robot_state["position"]["right_active"] = True
            self.robot_state["gravity"]["right_active"] = False
            print("[DATA_MANAGER] 오른팔 Position 모드 ON")
            
        elif command == "RIGHT_OFF":
            self.robot_state["position"]["right_active"] = False
            print("[DATA_MANAGER] 오른팔 Position 모드 OFF")

    def get_robot_state(self):
        """현재 로봇 상태 반환"""
        if not hasattr(self, 'robot_state'):
            self.robot_state = {
                "connected": True,
                "gravity": {"left_active": False, "right_active": False},
                "position": {"left_active": True, "right_active": True},
                "communication": {"fps": 0.0, "interval": 0.0},
                "recording": {"active": False}
            }
        
        return self.robot_state.copy()
    
    def update_communication_stats(self, fps: float, interval: float):
        """통신 통계 업데이트"""
        with self.lock:
            self.robot_state["communication"]["fps"] = fps
            self.robot_state["communication"]["interval"] = interval
    
    def update_activity(self):
        """활동 업데이트 (마지막 활동 시간 갱신)"""
        with self.lock:
            self.robot_state["last_activity"] = time.time()
    
    # ===============================
    # 녹화 관리 메서드들
    # ===============================
    
    def start_recording(self):
        """녹화 시작"""
        with self.lock:
            self.is_recording = True
            self.robot_state["recording"]["active"] = True
            self.robot_state["recording"]["start_time"] = time.time()
            print("[DATA_MANAGER] 녹화 시작")
    
    def stop_recording(self) -> Optional[str]:
        """녹화 중지"""
        with self.lock:
            if not self.is_recording:
                return None
            
            self.is_recording = False
            self.robot_state["recording"]["active"] = False
            
            # 현재 엔코더 데이터를 포즈로 저장
            if self.encoder_data:
                latest_data = self.encoder_data[-1]
                pose_name = self.save_encoder_pose(latest_data["angles"])
                print(f"[DATA_MANAGER] 녹화 중지 - 포즈 저장: {pose_name}")
                return pose_name
            
            return None
    
    def get_recorded_samples(self) -> List[Dict]:
        """녹화된 샘플 조회"""
        with self.lock:
            return self.recorded_samples[:]
    
    def delete_recorded_data(self):
        """녹화된 데이터 삭제"""
        with self.lock:
            count = len(self.recorded_samples)
            self.recorded_samples.clear()
            print(f"[DATA_MANAGER] {count}개 녹화 샘플 삭제됨")
    
    # ===============================
    # 로깅 메서드들
    # ===============================
    
    def add_grpc_entry(self, entry_type: str, message: str):
        """gRPC 로그 엔트리 추가"""
        with self.lock:
            entry = {
                "timestamp": time.time(),
                "type": entry_type,
                "message": message,
                "datetime": datetime.now().strftime("%H:%M:%S.%f")[:-3]
            }
            self.grpc_logs.append(entry)
    
    def get_grpc_entries(self, limit: int = 100) -> List[Dict]:
        """gRPC 로그 엔트리 조회"""
        with self.lock:
            data_list = list(self.grpc_logs)
            return data_list[-limit:] if limit > 0 else data_list
    
    def get_recorded_log(self, limit: int = 100) -> List[Dict]:
        """녹화 로그 조회 (호환성)"""
        return self.get_grpc_entries(limit)
    
    # ===============================
    # 데이터 정리 메서드들
    # ===============================
    
    def reset_all_data(self):
        """모든 데이터 리셋"""
        with self.lock:
            self.encoder_data.clear()
            self.streaming_data.clear()
            self.save_stream_data.clear()
            self.pose_data.clear()
            self.grpc_logs.clear()
            self.recorded_samples.clear()
            print("[DATA_MANAGER] 모든 데이터 리셋됨")
    
    def cleanup(self):
        """정리 작업"""
        print("[DATA_MANAGER] 정리 작업 시작")
        
        # 스트림 워커 중지
        self.stream_worker_running = False
        try:
            self.stream_queue.put(None, timeout=1.0)
        except queue.Full:
            pass
        
        if self.stream_worker_thread and self.stream_worker_thread.is_alive():
            self.stream_worker_thread.join(timeout=2.0)
        
        print("[DATA_MANAGER] 정리 작업 완료")
    
    # ===============================
    # CSV 저장 메서드들
    # ===============================
    
    def save_to_csv(self, data_type: str = "streaming", filename: str = None) -> Optional[str]:
        """데이터를 CSV로 저장"""
        try:
            # log 폴더 생성
            log_folder = "log"
            if not os.path.exists(log_folder):
                os.makedirs(log_folder)
            
            # 파일명 생성
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"robot_{data_type}_{timestamp}.csv"
            
            # 확장자 확인
            if not filename.endswith('.csv'):
                filename += '.csv'
            
            filepath = os.path.join(log_folder, filename)
            
            # 데이터 선택
            with self.lock:
                if data_type == "save_stream":
                    data_to_save = list(self.save_stream_data)
                elif data_type == "streaming":
                    data_to_save = list(self.streaming_data)
                elif data_type == "encoder":
                    data_to_save = list(self.encoder_data)
                elif data_type == "poses":
                    data_to_save = self.pose_data[:]
                elif data_type == "logs":
                    data_to_save = list(self.grpc_logs)
                else:
                    raise ValueError(f"Unknown data type: {data_type}")
            
            if not data_to_save:
                print(f"[DATA_MANAGER] 저장할 {data_type} 데이터가 없습니다.")
                return None
            
            # DataFrame 생성
            if data_type == "poses":
                df = pd.DataFrame(data_to_save)
            elif data_type == "logs":
                df = pd.DataFrame(data_to_save)
            else:
                # 엔코더/스트리밍/Save Stream 데이터
                records = []
                for sample in data_to_save:
                    record = {
                        "timestamp": sample["timestamp"],
                        "datetime": datetime.fromtimestamp(sample["timestamp"]).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    }
                    
                    angles = sample.get("angles", [])
                    for i, angle in enumerate(angles):
                        record[f"joint_{i+1}_rad"] = angle
                        record[f"joint_{i+1}_deg"] = angle * 180 / 3.14159
                    
                    record["formatted"] = sample.get("formatted", "")
                    records.append(record)
                
                df = pd.DataFrame(records)
            
            # CSV 저장
            df.to_csv(filepath, index=False)
            file_size = os.path.getsize(filepath)
            print(f"[DATA_MANAGER] {data_type} 데이터 저장 완료: {filepath}")
            print(f"[DATA_MANAGER] 파일 크기: {file_size/1024:.1f}KB, 샘플 수: {len(data_to_save)}")
            
            return filepath
            
        except Exception as e:
            print(f"[DATA_MANAGER] CSV 저장 실패: {e}")
            return None
    
    def save_save_stream_to_csv(self, filename: str = None) -> Optional[str]:
        """Save Stream 데이터를 CSV로 저장"""
        return self.save_to_csv("save_stream", filename)
    
    def save_all_data_to_csv(self, base_filename: str = None) -> Dict[str, Optional[str]]:
        """모든 데이터를 개별 CSV 파일로 저장"""
        if base_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"robot_export_{timestamp}"
        
        results = {}
        data_types = ["save_stream", "streaming", "encoder", "poses", "logs"]
        
        for data_type in data_types:
            filename = f"{base_filename}_{data_type}.csv"
            filepath = self.save_to_csv(data_type, filename)
            results[data_type] = filepath
        
        return results
    
    # ===============================
    # 통계 및 유틸리티 메서드들
    # ===============================
    
    def get_statistics(self) -> Dict[str, Any]:
        """전체 통계 조회"""
        with self.lock:
            stats = {
                "encoder_samples": len(self.encoder_data),
                "streaming_samples": len(self.streaming_data),
                "save_stream_samples": len(self.save_stream_data),
                "saved_poses": len(self.pose_data),
                "grpc_logs": len(self.grpc_logs),
                "recorded_samples": len(self.recorded_samples),
                "current_fps": self.robot_state["communication"]["fps"],
                "recording_active": self.is_recording,
                "streaming_active": self.is_streaming,
                "save_streaming_active": self.is_save_streaming,
                "current_gains": self.gain_values.copy(),
                "robot_connected": self.robot_state["connected"]
            }
        
        return stats
    
    def _format_angles(self, angles: List[float]) -> str:
        """각도를 포맷팅하여 문자열로 변환"""
        if not angles:
            return "No angles"
        
        # 라디안을 도로 변환하여 표시 (처음 8개만)
        display_count = min(8, len(angles))
        display_angles = [angles[i] * 180 / 3.14159 for i in range(display_count)]
        formatted = [f"{angle:+6.1f}°" for angle in display_angles]
        
        result = ", ".join(formatted)
        if len(angles) > 8:
            result += f" ... (+{len(angles)-8}개)"
        
        return result
    
    def print_status(self):
        """현재 상태 출력"""
        stats = self.get_statistics()
        print("\n=== gRPC Data Manager 상태 ===")
        print(f"연결 상태: {'연결됨' if stats['robot_connected'] else '연결 안됨'}")
        print(f"스트리밍: {'활성' if stats['streaming_active'] else '비활성'}")
        print(f"Save 스트리밍: {'활성' if stats['save_streaming_active'] else '비활성'}")
        print(f"녹화: {'활성' if stats['recording_active'] else '비활성'}")
        print(f"현재 FPS: {stats['current_fps']:.1f}")
        print(f"데이터 현황:")
        print(f"  - 엔코더 샘플: {stats['encoder_samples']}개")
        print(f"  - 스트리밍 샘플: {stats['streaming_samples']}개")
        print(f"  - Save Stream 샘플: {stats['save_stream_samples']}개")
        print(f"  - 저장된 포즈: {stats['saved_poses']}개")
        print(f"  - gRPC 로그: {stats['grpc_logs']}개")
        print(f"게인 값: Shoulder={stats['current_gains']['shoulder_gain']:.2f}, Joint={stats['current_gains']['joint_gain']:.2f}")
        print("============================\n")

# ===============================
# 전역 인스턴스 및 호환성 함수들
# ===============================

# 전역 데이터 매니저 인스턴스
grpc_data_manager = GRPCDataManager()

# 모듈 종료 시 정리 작업을 위한 등록
import atexit
atexit.register(grpc_data_manager.cleanup)

# ===============================
# 편의 함수들 (호환성 유지)
# ===============================

def start_streaming():
    """스트리밍 시작"""
    grpc_data_manager.start_streaming()

def stop_streaming():
    """스트리밍 중지"""
    grpc_data_manager.stop_streaming()

def start_save_streaming():
    """Save 스트리밍 시작"""
    grpc_data_manager.start_save_streaming()

def stop_save_streaming():
    """Save 스트리밍 중지"""
    grpc_data_manager.stop_save_streaming()

def add_streaming_sample(angles: List[float], timestamp: float = None):
    """스트리밍 샘플 추가"""
    grpc_data_manager.add_streaming_sample(angles, timestamp)

def add_save_stream_sample(angles: List[float], timestamp: float = None):
    """Save Stream 샘플 추가"""
    grpc_data_manager.add_save_stream_sample(angles, timestamp)

def save_save_stream_to_csv(filename: str = None) -> Optional[str]:
    """Save Stream 데이터를 CSV로 저장"""
    return grpc_data_manager.save_save_stream_to_csv(filename)

def get_save_stream_data(limit: int = 50) -> List[Dict]:
    """Save Stream 데이터 조회"""
    return grpc_data_manager.get_save_stream_data(limit)

def get_save_stream_status() -> Dict[str, Any]:
    """Save Stream 상태 조회"""
    return grpc_data_manager.get_save_stream_status()

# 전체 상태 출력 함수
def print_manager_status():
    """매니저 상태 출력"""
    grpc_data_manager.print_status()

if __name__ == "__main__":
    # 테스트 코드
    print("=== gRPC Data Manager 테스트 ===")
    
    # 테스트 데이터 추가
    test_angles = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    
    grpc_data_manager.update_encoder_data(test_angles)
    grpc_data_manager.start_save_streaming()
    grpc_data_manager.add_save_stream_sample(test_angles)
    
    time.sleep(0.1)
    
    grpc_data_manager.stop_save_streaming()
    
    # 상태 출력
    grpc_data_manager.print_status()
    
    # CSV 저장 테스트
    filepath = grpc_data_manager.save_save_stream_to_csv("test_save_stream")
    if filepath:
        print(f"테스트 파일 저장 완료: {filepath}")
    
    # 정리
    grpc_data_manager.cleanup()