"""
POA 시스템 메모리 및 성능 모니터링
"""
import psutil
import gc
import threading
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from exchange.utils.logging_config import log_system_message, log_error_message

@dataclass
class SystemMetrics:
    """시스템 메트릭 데이터 클래스"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_free_gb: float
    network_sent_mb: float
    network_recv_mb: float
    process_count: int
    thread_count: int

class MemoryMonitor:
    """메모리 및 시스템 리소스 모니터링 클래스"""
    
    def __init__(self, threshold_memory=80, threshold_cpu=80, threshold_disk=80):
        self.threshold_memory = threshold_memory
        self.threshold_cpu = threshold_cpu
        self.threshold_disk = threshold_disk
        
        self.monitoring = False
        self.monitor_thread = None
        self.metrics_history = []
        self.max_history_size = 1440  # 24시간 (1분마다 수집)
        
        self.initial_network_stats = None
        self.last_network_stats = None
        
        # 알림 쿨다운 (같은 문제에 대해 연속 알림 방지)
        self.last_alerts = {
            'memory': None,
            'cpu': None,
            'disk': None
        }
        self.alert_cooldown = timedelta(minutes=10)
    
    def start_monitoring(self, interval=60):
        """모니터링 시작"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop, 
                args=(interval,),
                daemon=True
            )
            self.monitor_thread.start()
            log_system_message("시스템 모니터링 시작")
    
    def stop_monitoring(self):
        """모니터링 중지"""
        if self.monitoring:
            self.monitoring = False
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=5)
            log_system_message("시스템 모니터링 중지")
    
    def _monitor_loop(self, interval):
        """모니터링 루프"""
        while self.monitoring:
            try:
                # 메트릭 수집
                metrics = self._collect_metrics()
                
                # 히스토리에 추가
                self.metrics_history.append(metrics)
                
                # 히스토리 크기 제한
                if len(self.metrics_history) > self.max_history_size:
                    self.metrics_history.pop(0)
                
                # 임계값 체크 및 알림
                self._check_thresholds(metrics)
                
                # 메모리 정리 (필요시)
                self._cleanup_memory_if_needed(metrics)
                
                time.sleep(interval)
                
            except Exception as e:
                log_error_message(f"모니터링 루프 오류: {str(e)}", "MONITOR")
                time.sleep(interval)
    
    def _collect_metrics(self) -> SystemMetrics:
        """시스템 메트릭 수집"""
        # CPU 사용률
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # 메모리 정보
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_mb = memory.used / 1024 / 1024
        memory_available_mb = memory.available / 1024 / 1024
        
        # 디스크 정보
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_used_gb = disk.used / 1024 / 1024 / 1024
        disk_free_gb = disk.free / 1024 / 1024 / 1024
        
        # 네트워크 정보
        network_stats = psutil.net_io_counters()
        if self.initial_network_stats is None:
            self.initial_network_stats = network_stats
            self.last_network_stats = network_stats
        
        network_sent_mb = (network_stats.bytes_sent - self.initial_network_stats.bytes_sent) / 1024 / 1024
        network_recv_mb = (network_stats.bytes_recv - self.initial_network_stats.bytes_recv) / 1024 / 1024
        
        # 프로세스 정보
        process_count = len(psutil.pids())\n        \n        # 현재 프로세스의 스레드 수\n        current_process = psutil.Process(os.getpid())\n        thread_count = current_process.num_threads()\n        \n        return SystemMetrics(\n            timestamp=datetime.now(),\n            cpu_percent=cpu_percent,\n            memory_percent=memory_percent,\n            memory_used_mb=memory_used_mb,\n            memory_available_mb=memory_available_mb,\n            disk_percent=disk_percent,\n            disk_used_gb=disk_used_gb,\n            disk_free_gb=disk_free_gb,\n            network_sent_mb=network_sent_mb,\n            network_recv_mb=network_recv_mb,\n            process_count=process_count,\n            thread_count=thread_count\n        )\n    \n    def _check_thresholds(self, metrics: SystemMetrics):\n        \"\"\"임계값 체크 및 알림\"\"\"\n        now = datetime.now()\n        \n        # 메모리 임계값 체크\n        if metrics.memory_percent > self.threshold_memory:\n            if (self.last_alerts['memory'] is None or \n                now - self.last_alerts['memory'] > self.alert_cooldown):\n                log_system_message(\n                    f\"메모리 사용량 경고: {metrics.memory_percent:.1f}% \"\n                    f\"({metrics.memory_used_mb:.1f}MB 사용)\", \n                    \"WARNING\"\n                )\n                self.last_alerts['memory'] = now\n        \n        # CPU 임계값 체크\n        if metrics.cpu_percent > self.threshold_cpu:\n            if (self.last_alerts['cpu'] is None or \n                now - self.last_alerts['cpu'] > self.alert_cooldown):\n                log_system_message(\n                    f\"CPU 사용량 경고: {metrics.cpu_percent:.1f}%\", \n                    \"WARNING\"\n                )\n                self.last_alerts['cpu'] = now\n        \n        # 디스크 임계값 체크\n        if metrics.disk_percent > self.threshold_disk:\n            if (self.last_alerts['disk'] is None or \n                now - self.last_alerts['disk'] > self.alert_cooldown):\n                log_system_message(\n                    f\"디스크 사용량 경고: {metrics.disk_percent:.1f}% \"\n                    f\"({metrics.disk_used_gb:.1f}GB 사용)\", \n                    \"WARNING\"\n                )\n                self.last_alerts['disk'] = now\n    \n    def _cleanup_memory_if_needed(self, metrics: SystemMetrics):\n        \"\"\"메모리 정리 (필요시)\"\"\"\n        if metrics.memory_percent > 85:  # 85% 이상일 때 강제 정리\n            log_system_message(\"메모리 사용량 높음. 가비지 컬렉션 실행\")\n            \n            # 가비지 컬렉션 실행\n            collected = gc.collect()\n            \n            # 재측정\n            new_memory = psutil.virtual_memory()\n            log_system_message(\n                f\"가비지 컬렉션 완료: {collected}개 객체 정리, \"\n                f\"메모리 사용량: {new_memory.percent:.1f}%\"\n            )\n    \n    def get_current_metrics(self) -> Dict:\n        \"\"\"현재 시스템 메트릭 조회\"\"\"\n        try:\n            metrics = self._collect_metrics()\n            return {\n                \"timestamp\": metrics.timestamp.isoformat(),\n                \"cpu_percent\": metrics.cpu_percent,\n                \"memory_percent\": metrics.memory_percent,\n                \"memory_used_mb\": round(metrics.memory_used_mb, 1),\n                \"memory_available_mb\": round(metrics.memory_available_mb, 1),\n                \"disk_percent\": metrics.disk_percent,\n                \"disk_used_gb\": round(metrics.disk_used_gb, 1),\n                \"disk_free_gb\": round(metrics.disk_free_gb, 1),\n                \"network_sent_mb\": round(metrics.network_sent_mb, 1),\n                \"network_recv_mb\": round(metrics.network_recv_mb, 1),\n                \"process_count\": metrics.process_count,\n                \"thread_count\": metrics.thread_count\n            }\n        except Exception as e:\n            log_error_message(f\"메트릭 수집 오류: {str(e)}\", \"MONITOR\")\n            return {}\n    \n    def get_metrics_history(self, hours: int = 24) -> List[Dict]:\n        \"\"\"메트릭 히스토리 조회\"\"\"\n        if not self.metrics_history:\n            return []\n        \n        # 지정된 시간 범위의 데이터만 반환\n        cutoff_time = datetime.now() - timedelta(hours=hours)\n        filtered_metrics = [\n            {\n                \"timestamp\": m.timestamp.isoformat(),\n                \"cpu_percent\": m.cpu_percent,\n                \"memory_percent\": m.memory_percent,\n                \"disk_percent\": m.disk_percent,\n                \"memory_used_mb\": round(m.memory_used_mb, 1),\n                \"network_sent_mb\": round(m.network_sent_mb, 1),\n                \"network_recv_mb\": round(m.network_recv_mb, 1)\n            }\n            for m in self.metrics_history\n            if m.timestamp >= cutoff_time\n        ]\n        \n        return filtered_metrics\n    \n    def get_summary_stats(self) -> Dict:\n        \"\"\"요약 통계 조회\"\"\"\n        if not self.metrics_history:\n            return {}\n        \n        # 최근 24시간 데이터\n        recent_metrics = [m for m in self.metrics_history \n                         if m.timestamp >= datetime.now() - timedelta(hours=24)]\n        \n        if not recent_metrics:\n            return {}\n        \n        cpu_values = [m.cpu_percent for m in recent_metrics]\n        memory_values = [m.memory_percent for m in recent_metrics]\n        disk_values = [m.disk_percent for m in recent_metrics]\n        \n        return {\n            \"period\": \"24시간\",\n            \"data_points\": len(recent_metrics),\n            \"cpu\": {\n                \"avg\": round(sum(cpu_values) / len(cpu_values), 1),\n                \"max\": round(max(cpu_values), 1),\n                \"min\": round(min(cpu_values), 1)\n            },\n            \"memory\": {\n                \"avg\": round(sum(memory_values) / len(memory_values), 1),\n                \"max\": round(max(memory_values), 1),\n                \"min\": round(min(memory_values), 1)\n            },\n            \"disk\": {\n                \"avg\": round(sum(disk_values) / len(disk_values), 1),\n                \"max\": round(max(disk_values), 1),\n                \"min\": round(min(disk_values), 1)\n            }\n        }\n    \n    def force_garbage_collection(self) -> Dict:\n        \"\"\"강제 가비지 컬렉션\"\"\"\n        try:\n            # 실행 전 메모리 상태\n            before_memory = psutil.virtual_memory()\n            \n            # 가비지 컬렉션 실행\n            collected = gc.collect()\n            \n            # 실행 후 메모리 상태\n            after_memory = psutil.virtual_memory()\n            \n            result = {\n                \"collected_objects\": collected,\n                \"memory_before_percent\": before_memory.percent,\n                \"memory_after_percent\": after_memory.percent,\n                \"memory_freed_mb\": round(\n                    (before_memory.used - after_memory.used) / 1024 / 1024, 1\n                )\n            }\n            \n            log_system_message(\n                f\"강제 가비지 컬렉션 완료: {collected}개 객체 정리, \"\n                f\"{result['memory_freed_mb']}MB 메모리 해제\"\n            )\n            \n            return result\n            \n        except Exception as e:\n            log_error_message(f\"가비지 컬렉션 오류: {str(e)}\", \"MONITOR\")\n            return {\"error\": str(e)}\n\n# 전역 모니터 인스턴스\nmemory_monitor = MemoryMonitor()\n\ndef start_system_monitoring():\n    \"\"\"시스템 모니터링 시작\"\"\"\n    global memory_monitor\n    memory_monitor.start_monitoring()\n    return memory_monitor\n\ndef stop_system_monitoring():\n    \"\"\"시스템 모니터링 중지\"\"\"\n    global memory_monitor\n    memory_monitor.stop_monitoring()\n\ndef get_system_status():\n    \"\"\"시스템 상태 조회\"\"\"\n    return memory_monitor.get_current_metrics()\n\ndef get_system_history(hours=24):\n    \"\"\"시스템 히스토리 조회\"\"\"\n    return memory_monitor.get_metrics_history(hours)\n\ndef get_system_summary():\n    \"\"\"시스템 요약 통계\"\"\"\n    return memory_monitor.get_summary_stats()\n\ndef force_gc():\n    \"\"\"강제 가비지 컬렉션\"\"\"\n    return memory_monitor.force_garbage_collection()\n\nif __name__ == \"__main__\":\n    # 테스트\n    monitor = MemoryMonitor()\n    print(\"현재 시스템 메트릭:\")\n    print(monitor.get_current_metrics())\n    \n    print(\"\\n가비지 컬렉션 테스트:\")\n    print(monitor.force_garbage_collection())\n