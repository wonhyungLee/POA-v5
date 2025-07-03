"""
POA 시스템 데이터베이스 연결 관리 개선 버전
"""
import sqlite3
import traceback
import os
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from exchange.utils.logging_config import log_error_message, log_system_message

current_file_directory = os.path.dirname(os.path.realpath(__file__))
parent_directory = Path(current_file_directory).parent

class ImprovedDatabase:
    """개선된 데이터베이스 클래스"""
    
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, database_url: str = f"{parent_directory}/store.db"):
        cls = type(self)
        if not hasattr(cls, "_init"):
            self.database_url = database_url
            self.connection = None
            self.cursor = None
            self.max_retries = 3
            self.retry_delay = 1
            self.connection_lock = threading.Lock()
            self.last_health_check = None
            self.health_check_interval = 300  # 5분마다 헬스체크
            
            # 연결 초기화
            self._connect()
            self._init_tables()
            
            cls._init = True

    def _connect(self):
        """데이터베이스 연결 설정"""
        for attempt in range(self.max_retries):
            try:
                if self.connection:
                    try:
                        self.connection.close()
                    except:
                        pass
                
                # 데이터베이스 디렉토리 생성
                db_dir = os.path.dirname(self.database_url)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir)
                
                self.connection = sqlite3.connect(
                    self.database_url,
                    timeout=30,
                    check_same_thread=False,
                    isolation_level=None  # 자동 커밋 모드
                )
                
                # 연결 최적화 설정
                self.connection.execute("PRAGMA foreign_keys = ON")
                self.connection.execute("PRAGMA journal_mode = WAL")
                self.connection.execute("PRAGMA synchronous = NORMAL")
                self.connection.execute("PRAGMA cache_size = 10000")
                self.connection.execute("PRAGMA temp_store = MEMORY")
                
                self.connection.row_factory = sqlite3.Row
                self.cursor = self.connection.cursor()
                
                log_system_message(f"데이터베이스 연결 성공: {self.database_url}")
                return
                
            except Exception as e:
                log_error_message(f"데이터베이스 연결 실패 (시도 {attempt + 1}/{self.max_retries}): {str(e)}", "DATABASE")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise e

    def _ensure_connection(self):
        """연결 상태 확인 및 재연결"""
        with self.connection_lock:
            # 헬스체크 주기 확인
            now = datetime.now()
            if (self.last_health_check is None or 
                (now - self.last_health_check).total_seconds() > self.health_check_interval):
                self._health_check()
                self.last_health_check = now
            
            if self.connection is None:
                self._connect()
                return
            
            try:
                # 연결 테스트
                self.connection.execute("SELECT 1")
            except sqlite3.Error:
                log_system_message("데이터베이스 연결 끊김. 재연결 시도...")
                self._connect()

    def _health_check(self):
        """데이터베이스 헬스체크"""
        try:
            if self.connection:
                self.connection.execute("SELECT 1")
                # 간단한 성능 테스트
                start_time = time.time()
                self.connection.execute("SELECT COUNT(*) FROM sqlite_master")
                query_time = time.time() - start_time
                
                if query_time > 5:  # 5초 이상 걸리면 경고
                    log_system_message(f"데이터베이스 응답 시간 느림: {query_time:.2f}초", "WARNING")
                
        except Exception as e:
            log_error_message(f"데이터베이스 헬스체크 실패: {str(e)}", "DATABASE")

    def _init_tables(self):
        """테이블 초기화"""
        try:
            # 인증 테이블 생성
            auth_query = """
            CREATE TABLE IF NOT EXISTS auth (
                exchange TEXT PRIMARY KEY,
                access_token TEXT,
                access_token_token_expired TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
            self.execute(auth_query)
            
            # 업데이트 트리거 생성
            trigger_query = """
            CREATE TRIGGER IF NOT EXISTS update_auth_timestamp 
            AFTER UPDATE ON auth
            BEGIN
                UPDATE auth SET updated_at = CURRENT_TIMESTAMP WHERE exchange = NEW.exchange;
            END;
            """
            self.execute(trigger_query)
            
            # 로그 테이블 생성 (선택사항)
            log_query = """
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
            self.execute(log_query)
            
            log_system_message("데이터베이스 테이블 초기화 완료")
            
        except Exception as e:
            log_error_message(f"테이블 초기화 실패: {str(e)}", "DATABASE")
            raise

    def execute(self, query: str, params: Union[Dict, tuple, None] = None) -> sqlite3.Cursor:
        """안전한 쿼리 실행"""
        self._ensure_connection()
        
        try:
            if params is None:
                cursor = self.connection.execute(query)
            else:
                cursor = self.connection.execute(query, params)
            return cursor
            
        except sqlite3.Error as e:
            log_error_message(f"쿼리 실행 실패: {str(e)}\nQuery: {query}", "DATABASE")
            raise e

    def execute_many(self, query: str, params_list: List[Union[Dict, tuple]]) -> None:
        """여러 레코드 일괄 실행"""
        self._ensure_connection()
        
        try:
            self.connection.executemany(query, params_list)
            
        except sqlite3.Error as e:
            log_error_message(f"일괄 실행 실패: {str(e)}\nQuery: {query}", "DATABASE")
            raise e

    def fetch_one(self, query: str, params: Union[Dict, tuple, None] = None) -> Optional[sqlite3.Row]:
        """단일 레코드 조회"""
        cursor = self.execute(query, params)
        return cursor.fetchone()

    def fetch_all(self, query: str, params: Union[Dict, tuple, None] = None) -> List[sqlite3.Row]:
        """모든 레코드 조회"""
        cursor = self.execute(query, params)
        return cursor.fetchall()

    def transaction(self):
        """트랜잭션 컨텍스트 매니저"""
        return DatabaseTransaction(self)

    def set_auth(self, exchange: str, access_token: str, access_token_token_expired: str) -> None:
        """인증 정보 설정"""
        query = """
        INSERT INTO auth (exchange, access_token, access_token_token_expired)
        VALUES (?, ?, ?)
        ON CONFLICT(exchange) DO UPDATE SET
        access_token=excluded.access_token,
        access_token_token_expired=excluded.access_token_token_expired,
        updated_at=CURRENT_TIMESTAMP;
        """
        self.execute(query, (exchange, access_token, access_token_token_expired))

    def get_auth(self, exchange: str) -> Optional[tuple]:
        """인증 정보 조회"""
        query = """
        SELECT access_token, access_token_token_expired FROM auth 
        WHERE exchange = ?;
        """
        result = self.fetch_one(query, (exchange,))
        return (result['access_token'], result['access_token_token_expired']) if result else None

    def clear_auth(self, exchange: str = None) -> None:
        """인증 정보 초기화"""
        if exchange:
            # 특정 거래소 인증 정보 초기화
            self.set_auth(exchange, "nothing", "nothing")
        else:
            # 모든 KIS 인증 정보 초기화
            for i in range(1, 51):
                self.set_auth(f"KIS{i}", "nothing", "nothing")

    def get_all_auth(self) -> List[Dict[str, Any]]:
        """모든 인증 정보 조회"""
        query = """
        SELECT exchange, access_token, access_token_token_expired, updated_at
        FROM auth
        ORDER BY exchange;
        """
        results = self.fetch_all(query)
        return [dict(row) for row in results] if results else []

    def cleanup_old_auth(self, days: int = 30) -> int:
        """오래된 인증 정보 정리"""
        query = """
        DELETE FROM auth 
        WHERE access_token = 'nothing' 
        AND datetime(updated_at) < datetime('now', '-' || ? || ' days');
        """
        cursor = self.execute(query, (days,))
        deleted_count = cursor.rowcount
        
        if deleted_count > 0:
            log_system_message(f"오래된 인증 정보 {deleted_count}개 정리 완료")
        
        return deleted_count

    def get_database_info(self) -> Dict[str, Any]:
        """데이터베이스 정보 조회"""
        try:
            # 기본 정보
            info = {
                "database_path": self.database_url,
                "connection_status": "connected" if self.connection else "disconnected",
                "tables": []
            }
            
            # 테이블 정보
            tables_query = """
            SELECT name, sql FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
            """
            tables = self.fetch_all(tables_query)
            
            for table in tables:
                table_name = table['name']
                count_query = f"SELECT COUNT(*) as count FROM {table_name}"
                count_result = self.fetch_one(count_query)
                
                info["tables"].append({
                    "name": table_name,
                    "row_count": count_result['count'] if count_result else 0
                })
            
            # 파일 크기
            if os.path.exists(self.database_url):
                file_size = os.path.getsize(self.database_url)
                info["file_size_mb"] = round(file_size / 1024 / 1024, 2)
            
            return info
            
        except Exception as e:
            log_error_message(f"데이터베이스 정보 조회 실패: {str(e)}", "DATABASE")
            return {"error": str(e)}

    def vacuum(self) -> None:
        """데이터베이스 최적화"""
        try:
            log_system_message("데이터베이스 최적화 시작")
            self.execute("VACUUM")
            log_system_message("데이터베이스 최적화 완료")
        except Exception as e:
            log_error_message(f"데이터베이스 최적화 실패: {str(e)}", "DATABASE")
            raise

    def backup(self, backup_path: str) -> bool:
        """데이터베이스 백업"""
        try:
            # 백업 디렉토리 생성
            backup_dir = os.path.dirname(backup_path)
            if backup_dir and not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            # 백업 실행
            with sqlite3.connect(backup_path) as backup_conn:
                self.connection.backup(backup_conn)
            
            log_system_message(f"데이터베이스 백업 완료: {backup_path}")
            return True
            
        except Exception as e:
            log_error_message(f"데이터베이스 백업 실패: {str(e)}", "DATABASE")
            return False

    def close(self) -> None:
        """연결 종료"""
        try:
            if self.connection:
                self.connection.close()
                self.connection = None
                self.cursor = None
                log_system_message("데이터베이스 연결 종료")
        except Exception as e:
            log_error_message(f"데이터베이스 연결 종료 중 오류: {str(e)}", "DATABASE")

    def __del__(self):
        """소멸자"""
        self.close()


class DatabaseTransaction:
    """트랜잭션 컨텍스트 매니저"""
    
    def __init__(self, database: ImprovedDatabase):
        self.database = database
        self.connection = database.connection

    def __enter__(self):
        self.connection.execute("BEGIN")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.connection.execute("COMMIT")
        else:
            self.connection.execute("ROLLBACK")
            log_error_message(f"트랜잭션 롤백: {exc_val}", "DATABASE")


# 전역 데이터베이스 인스턴스
improved_db = ImprovedDatabase()

# 기존 코드와의 호환성을 위한 래퍼 클래스
class Database:
    """기존 코드와 호환성을 위한 래퍼 클래스"""
    
    def __init__(self, database_url: str = None):
        self.db = improved_db
        
    def close(self):
        return self.db.close()
    
    def excute(self, query: str, value: Union[dict, tuple]):
        """기존 오타 메서드 호환성 유지"""
        return self.execute(query, value)
    
    def execute(self, query: str, value: Union[dict, tuple]):
        return self.db.execute(query, value)
    
    def excute_many(self, query: str, values: List[Union[dict, tuple]]):
        """기존 오타 메서드 호환성 유지"""
        return self.execute_many(query, values)
    
    def execute_many(self, query: str, values: List[Union[dict, tuple]]):
        return self.db.execute_many(query, values)
    
    def fetch_one(self, query: str, value: Union[dict, tuple]):
        return self.db.fetch_one(query, value)
    
    def fetch_all(self, query: str, value: Union[dict, tuple]):
        return self.db.fetch_all(query, value)
    
    def set_auth(self, exchange, access_token, access_token_token_expired):
        return self.db.set_auth(exchange, access_token, access_token_token_expired)
    
    def get_auth(self, exchange):
        return self.db.get_auth(exchange)
    
    def clear_auth(self):
        return self.db.clear_auth()
    
    def init_db(self):
        # 이미 초기화됨
        pass


# 기존 코드와의 호환성을 위한 인스턴스
db = Database()

# 개선된 데이터베이스 인스턴스도 제공
enhanced_db = improved_db

if __name__ == "__main__":
    # 테스트
    try:
        print("데이터베이스 정보:")
        info = enhanced_db.get_database_info()
        for key, value in info.items():
            print(f"  {key}: {value}")
        
        print("\n인증 정보 테스트:")
        enhanced_db.set_auth("TEST", "test_token", "2024-01-01 00:00:00")
        auth = enhanced_db.get_auth("TEST")
        print(f"  설정된 인증 정보: {auth}")
        
        print("\n트랜잭션 테스트:")
        with enhanced_db.transaction():
            enhanced_db.set_auth("TEST2", "test_token2", "2024-01-01 00:00:00")
        
        print("데이터베이스 테스트 완료")
        
    except Exception as e:
        print(f"데이터베이스 테스트 실패: {e}")
        traceback.print_exc()
