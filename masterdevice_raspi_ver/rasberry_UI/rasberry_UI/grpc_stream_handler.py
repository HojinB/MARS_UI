# grpc_stream_handler.py - gRPC 스트림 데이터 실시간 처리
import time
import threading
import queue
import json
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class StreamSample:
    """스트림 샘플 데이터 클래스"""
    timestamp: float
    angles: List[float]
    sequence: int
    session_id: str
    capture_time_ns: int
    send_time_ns: int

class GRPCStreamHandler:
    """gRPC 스트림 데이터 실시간 처리 클래스"""
    
    def __init__(self, max_queue_size: int = 1000):
        self.max_queue_size = max_queue_size
        self.data_queue = queue.Queue(maxsize=max_queue_size)
        self.callbacks = []
        self.is_running = False
        self.worker_thread = None
        self.lock = threading.Lock()
        
        # 통계
        self.stats = {
            "total_samples": 0,
            "processed_samples": 0,
            "dropped_samples": 0,
            "last_fps": 0.0,
            "start_time": None
        }
        
        print("[STREAM_HANDLER] gRPC 스트림 핸들러 초기화 완료")
    
    def add_callback(self, callback: Callable[[StreamSample], None]):
        """데이터 처리 콜백 추가"""
        with self.lock:
            self.callbacks.append(callback)
            print(f"[STREAM_HANDLER] 콜백 추가됨 - 총 {len(self.callbacks)}개")
    
    def remove_callback(self, callback: Callable[[StreamSample], None]):
        """데이터 처리 콜백 제거"""
        with self.lock:
            if callback in self.callbacks:
                self.callbacks.remove(callback)
                print(f"[STREAM_HANDLER] 콜백 제거됨 - 총 {len(self.callbacks)}개")
    
    def start(self):
        """스트림 핸들러 시작"""
        if self.is_running:
            return
        
        self.is_running = True
        self.stats["start_time"] = time.time()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        print("[STREAM_HANDLER] 스트림 처리 시작")
    
    def stop(self):
        """스트림 핸들러 중지"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 큐에 종료 신호 추가
        try:
            self.data_queue.put(None, timeout=1.0)
        except queue.Full:
            pass
        
        # 워커 스레드 종료 대기
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)
        
        print(f"[STREAM_HANDLER] 스트림 처리 중지 - 총 {self.stats['processed_samples']}개 샘플 처리됨")
    
    def add_sample(self, angles: List[float], sequence: int = 0, session_id: str = "", 
                  capture_time_ns: int = 0, send_time_ns: int = 0) -> bool:
        """새로운 샘플 추가"""
        if not self.is_running:
            return False
        
        try:
            timestamp = time.time()
            sample = StreamSample(
                timestamp=timestamp,
                angles=angles[:],  # 복사본 생성
                sequence=sequence,
                session_id=session_id,
                capture_time_ns=capture_time_ns or int(timestamp * 1_000_000_000),
                send_time_ns=send_time_ns or int(timestamp * 1_000_000_000)
            )
            
            # 논블로킹으로 큐에 추가
            self.data_queue.put_nowait(sample)
            self.stats["total_samples"] += 1
            return True
            
        except queue.Full:
            # 큐가 가득 찬 경우 드롭
            self.stats["dropped_samples"] += 1
            print(f"[STREAM_HANDLER] 큐 가득참 - 샘플 드롭됨 (총 {self.stats['dropped_samples']}개)")
            return False
        except Exception as e:
            print(f"[STREAM_HANDLER] 샘플 추가 오류: {e}")
            return False
    
    def _worker_loop(self):
        """워커 스레드 메인 루프"""
        last_stats_time = time.time()
        samples_since_last_stats = 0
        
        print("[STREAM_HANDLER] 워커 스레드 시작됨")
        
        while self.is_running:
            try:
                # 타임아웃으로 큐에서 데이터 가져오기
                sample = self.data_queue.get(timeout=0.1)
                
                # 종료 신호 확인
                if sample is None:
                    break
                
                # 콜백 실행
                self._process_sample(sample)
                self.stats["processed_samples"] += 1
                samples_since_last_stats += 1
                
                # FPS 계산 (5초마다)
                current_time = time.time()
                if (current_time - last_stats_time) >= 5.0:
                    self.stats["last_fps"] = samples_since_last_stats / (current_time - last_stats_time)
                    last_stats_time = current_time
                    samples_since_last_stats = 0
                
                self.data_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[STREAM_HANDLER] 워커 루프 오류: {e}")
                time.sleep(0.1)
        
        print("[STREAM_HANDLER] 워커 스레드 종료됨")
    
    def _process_sample(self, sample: StreamSample):
        """샘플 처리 - 모든 콜백 실행"""
        with self.lock:
            callbacks_copy = self.callbacks[:]
        
        for callback in callbacks_copy:
            try:
                callback(sample)
            except Exception as e:
                print(f"[STREAM_HANDLER] 콜백 실행 오류: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """처리 통계 조회"""
        with self.lock:
            stats_copy = self.stats.copy()
            
        if stats_copy["start_time"]:
            uptime = time.time() - stats_copy["start_time"]
            stats_copy["uptime_seconds"] = uptime
            stats_copy["average_fps"] = stats_copy["processed_samples"] / uptime if uptime > 0 else 0.0
        
        return stats_copy

class SaveStreamManager:
    """Save Stream 전용 관리 클래스"""
    
    def __init__(self, data_manager, stream_handler: GRPCStreamHandler):
        self.data_manager = data_manager
        self.stream_handler = stream_handler
        self.is_active = False
        
        # 스트림 핸들러에 콜백 등록
        self.stream_handler.add_callback(self._on_stream_sample)
        
        print("[SAVE_STREAM] Save Stream Manager 초기화 완료")
    
    def start_save_stream(self):
        """Save 스트림 시작"""
        if self.is_active:
            return False
        
        self.is_active = True
        self.data_manager.start_streaming()
        print("[SAVE_STREAM] Save 스트림 시작됨")
        return True
    
    def stop_save_stream(self):
        """Save 스트림 중지"""
        if not self.is_active:
            return False
        
        self.is_active = False
        self.data_manager.stop_streaming()
        print("[SAVE_STREAM] Save 스트림 중지됨")
        return True
    
    def _on_stream_sample(self, sample: StreamSample):
        """스트림 샘플 처리 콜백"""
        if not self.is_active:
            return
        
        # 데이터 매니저에 샘플 추가
        self.data_manager.add_streaming_sample(sample.angles, sample.timestamp)
    
    def save_current_stream_to_csv(self, filename: str = None) -> Optional[str]:
        """현재 스트림 데이터를 CSV로 저장"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"save_stream_{timestamp}.csv"
        
        return self.data_manager.save_to_csv("streaming", filename)
    
    def get_stream_stats(self) -> Dict[str, Any]:
        """스트림 통계 조회"""
        stream_data = self.data_manager.get_streaming_data()
        
        stats = {
            "is_active": self.is_active,
            "sample_count": len(stream_data),
            "start_time": stream_data[0]["timestamp"] if stream_data else None,
            "end_time": stream_data[-1]["timestamp"] if stream_data else None,
            "duration_seconds": 0.0
        }
        
        if stats["start_time"] and stats["end_time"]:
            stats["duration_seconds"] = stats["end_time"] - stats["start_time"]
        
        return stats

# 전역 인스턴스들
grpc_stream_handler = GRPCStreamHandler()

# 데이터 매니저 import 및 연결
try:
    from data_manager import real_time_data_manager
    save_stream_manager = SaveStreamManager(real_time_data_manager, grpc_stream_handler)
    print("[STREAM_HANDLER] 데이터 매니저 연결 성공")
except ImportError:
    print("[STREAM_HANDLER] 데이터 매니저 연결 실패 - 더미 매니저 사용")
    save_stream_manager = None

# 모듈 시작
def start_stream_handling():
    """스트림 핸들링 시작"""
    grpc_stream_handler.start()

def stop_stream_handling():
    """스트림 핸들링 중지"""
    grpc_stream_handler.stop()

# 모듈 로드 시 자동 시작
start_stream_handling()