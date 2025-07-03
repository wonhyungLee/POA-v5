"""
POA 시스템 로깅 설정 및 관리
"""
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
import traceback

class POALogger:
    """POA 전용 로거 클래스"""
    
    def __init__(self, log_dir="/root/logs", max_file_size=10*1024*1024, backup_count=5):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        
        # 로거 설정
        self.setup_loggers()
    
    def setup_loggers(self):
        """로거들 설정"""
        # 기본 포맷터
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # 메인 애플리케이션 로거
        self.main_logger = self._create_logger(
            'poa.main', 
            'poa_main.log', 
            detailed_formatter,
            level=logging.INFO
        )
        
        # 주문 로거
        self.order_logger = self._create_logger(
            'poa.order', 
            'poa_orders.log', 
            detailed_formatter,
            level=logging.INFO
        )
        
        # 오류 로거
        self.error_logger = self._create_logger(
            'poa.error', 
            'poa_errors.log', 
            detailed_formatter,
            level=logging.ERROR
        )
        
        # KIS 로거
        self.kis_logger = self._create_logger(
            'poa.kis', 
            'poa_kis.log', 
            detailed_formatter,
            level=logging.DEBUG
        )
        
        # 시스템 로거
        self.system_logger = self._create_logger(
            'poa.system', 
            'poa_system.log', 
            simple_formatter,
            level=logging.INFO
        )
        
        # 설정 변경 로거
        self.config_logger = self._create_logger(
            'poa.config', 
            'poa_config.log', 
            detailed_formatter,
            level=logging.INFO
        )
    
    def _create_logger(self, name, filename, formatter, level=logging.INFO):
        """개별 로거 생성"""
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # 기존 핸들러 제거
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # 파일 핸들러 (로테이션)
        file_handler = RotatingFileHandler(
            self.log_dir / filename,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
        
        # 오류 레벨은 별도 콘솔 출력
        if level == logging.ERROR:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.ERROR)
            logger.addHandler(console_handler)
        
        # 프로파게이션 방지
        logger.propagate = False
        
        return logger
    
    def log_main(self, message, level=logging.INFO):
        """메인 로그"""
        self.main_logger.log(level, message)
    
    def log_order(self, exchange, result, order_info, success=True):
        """주문 로그"""
        level = logging.INFO if success else logging.ERROR
        message = f"[{exchange}] {order_info.get('side', 'Unknown')} {order_info.get('base', 'Unknown')} {order_info.get('amount', 0)} - {'성공' if success else '실패'}"
        if not success:
            message += f" - {result}"
        self.order_logger.log(level, message)
    
    def log_error(self, message, category="General", exception=None):
        """오류 로그"""
        if exception:
            message += f" - Exception: {str(exception)}"
            message += f" - Traceback: {traceback.format_exc()}"
        
        self.error_logger.error(f"[{category}] {message}")
    
    def log_kis(self, kis_number, message, level=logging.INFO):
        """KIS 관련 로그"""
        formatted_message = f"[KIS{kis_number}] {message}"
        self.kis_logger.log(level, formatted_message)
    
    def log_system(self, message, level=logging.INFO):
        """시스템 로그"""
        self.system_logger.log(level, message)
    
    def log_config(self, action, message, level=logging.INFO):
        """설정 변경 로그"""
        formatted_message = f"[{action}] {message}"
        self.config_logger.log(level, formatted_message)
    
    def get_log_files_info(self):
        """로그 파일 정보 조회"""
        log_files = []
        
        for log_file in self.log_dir.glob("*.log"):
            try:
                stat = log_file.stat()
                log_files.append({
                    "filename": log_file.name,
                    "size": stat.st_size,
                    "size_mb": round(stat.st_size / 1024 / 1024, 2),
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "path": str(log_file)
                })
            except Exception as e:
                continue
        
        return sorted(log_files, key=lambda x: x['modified'], reverse=True)
    
    def cleanup_old_logs(self, days_to_keep=30):
        """오래된 로그 파일 정리"""
        cutoff_time = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
        cleaned_files = []
        
        for log_file in self.log_dir.glob("*.log*"):
            try:
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    cleaned_files.append(str(log_file))
            except Exception as e:
                continue
        
        if cleaned_files:
            self.log_system(f"오래된 로그 파일 {len(cleaned_files)}개 정리 완료")
        
        return cleaned_files
    
    def get_recent_logs(self, log_type="main", lines=100):
        """최근 로그 조회"""
        log_files = {
            "main": "poa_main.log",
            "order": "poa_orders.log",
            "error": "poa_errors.log",
            "kis": "poa_kis.log",
            "system": "poa_system.log",
            "config": "poa_config.log"
        }
        
        if log_type not in log_files:
            return []
        
        log_file = self.log_dir / log_files[log_type]
        
        if not log_file.exists():
            return []
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                return [line.strip() for line in all_lines[-lines:]]
        except Exception as e:
            return [f"로그 읽기 오류: {str(e)}"]

# 전역 로거 인스턴스
poa_logger = POALogger()

def setup_logging(log_level="INFO"):
    """로깅 시스템 초기화"""
    global poa_logger
    
    # 로그 레벨 설정
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # 루트 로거 설정
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 외부 라이브러리 로거 레벨 조정
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    
    poa_logger.log_system("POA 로깅 시스템 초기화 완료")
    return poa_logger

# 편의 함수들
def log_message(message, level="INFO"):
    """일반 메시지 로그"""
    poa_logger.log_main(message, getattr(logging, level.upper(), logging.INFO))

def log_order_message(exchange, result, order_info):
    """주문 메시지 로그"""
    poa_logger.log_order(exchange, result, order_info, success=True)

def log_order_error_message(error_message, order_info):
    """주문 오류 메시지 로그"""
    poa_logger.log_order("ERROR", error_message, order_info, success=False)

def log_error_message(error_message, category="General"):
    """오류 메시지 로그"""
    poa_logger.log_error(error_message, category)

def log_kis_message(kis_number, message, level="INFO"):
    """KIS 메시지 로그"""
    poa_logger.log_kis(kis_number, message, getattr(logging, level.upper(), logging.INFO))

def log_system_message(message, level="INFO"):
    """시스템 메시지 로그"""
    poa_logger.log_system(message, getattr(logging, level.upper(), logging.INFO))

def log_config_message(action, message, level="INFO"):
    """설정 변경 메시지 로그"""
    poa_logger.log_config(action, message, getattr(logging, level.upper(), logging.INFO))

if __name__ == "__main__":
    # 테스트
    logger = setup_logging()
    
    log_message("테스트 메시지")
    log_order_message("BINANCE", {"status": "success"}, {"side": "buy", "base": "BTC", "amount": 1})
    log_error_message("테스트 오류", "TEST")
    log_kis_message(1, "토큰 생성 성공")
    log_system_message("시스템 상태 정상")
    log_config_message("ADD_KIS", "KIS5 계정 추가")
    
    print("로그 파일 정보:")
    for file_info in logger.get_log_files_info():
        print(f"  {file_info['filename']}: {file_info['size_mb']}MB")
