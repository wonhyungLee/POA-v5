"""
POA 웹 기반 설정 관리 인터페이스
"""
import os
import json
import shutil
import subprocess
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import HTTPException
from pydantic import BaseModel, validator
from exchange.utility import log_message
from exchange.utils.validation import validate_environment, get_kis_account_summary

class KISAccountConfig(BaseModel):
    """KIS 계정 설정"""
    kis_number: int
    key: str
    secret: str
    account_number: str
    account_code: str
    
    @validator('kis_number')
    def validate_kis_number(cls, v):
        if not 1 <= v <= 50:
            raise ValueError('KIS 번호는 1-50 범위여야 합니다')
        return v

class EnvVarConfig(BaseModel):
    """환경 변수 설정"""
    name: str
    value: str
    
    @validator('name')
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('환경 변수 이름을 입력해야 합니다')
        return v.strip()

class ExchangeConfig(BaseModel):
    """거래소 설정"""
    exchange: str
    key: str
    secret: str
    passphrase: Optional[str] = None
    
    @validator('exchange')
    def validate_exchange(cls, v):
        valid_exchanges = ['BINANCE', 'UPBIT', 'BYBIT', 'BITGET', 'OKX']
        if v.upper() not in valid_exchanges:
            raise ValueError(f'지원되지 않는 거래소입니다. 지원 거래소: {valid_exchanges}')
        return v.upper()

class ConfigManager:
    """설정 관리자 클래스"""
    
    def __init__(self):
        self.env_file = "/root/.env"
        self.backup_dir = "/root/backups"
        self.log_dir = "/root/logs"
        
        # 디렉토리 생성
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
    
    def backup_env_file(self) -> str:
        """환경 변수 파일 백업"""
        if not os.path.exists(self.env_file):
            raise FileNotFoundError("환경 변수 파일이 존재하지 않습니다")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.backup_dir}/.env.{timestamp}"
        
        shutil.copy(self.env_file, backup_path)
        log_message(f"환경 변수 백업 완료: {backup_path}")
        return backup_path
    
    def update_env_file(self, env_vars: Dict[str, str]) -> None:
        """환경 변수 파일 업데이트"""
        if not os.path.exists(self.env_file):
            # 파일이 없으면 새로 생성
            with open(self.env_file, 'w') as f:
                for key, value in env_vars.items():
                    f.write(f'{key}="{value}"\n')
            log_message("새 환경 변수 파일 생성 완료")
            return
        
        # 기존 내용 읽기
        with open(self.env_file, 'r') as f:
            lines = f.readlines()
        
        # 새 내용 준비
        new_lines = []
        updated_vars = set()
        
        for line in lines:
            if '=' in line and not line.strip().startswith('#'):
                var_name = line.split('=')[0].strip()
                if var_name in env_vars:
                    new_lines.append(f'{var_name}="{env_vars[var_name]}"\n')
                    updated_vars.add(var_name)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        # 새 변수 추가
        for var_name, var_value in env_vars.items():
            if var_name not in updated_vars:
                new_lines.append(f'{var_name}="{var_value}"\n')
        
        # 파일 쓰기
        with open(self.env_file, 'w') as f:
            f.writelines(new_lines)
        
        log_message(f"환경 변수 업데이트 완료: {list(env_vars.keys())}")
    
    def remove_env_vars(self, var_names: List[str]) -> None:
        """환경 변수 제거"""
        if not os.path.exists(self.env_file):
            raise FileNotFoundError("환경 변수 파일이 존재하지 않습니다")
        
        with open(self.env_file, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        removed_vars = []
        
        for line in lines:
            if '=' in line and not line.strip().startswith('#'):
                var_name = line.split('=')[0].strip()
                if var_name not in var_names:
                    new_lines.append(line)
                else:
                    removed_vars.append(var_name)
            else:
                new_lines.append(line)
        
        with open(self.env_file, 'w') as f:
            f.writelines(new_lines)
        
        if removed_vars:
            log_message(f"환경 변수 제거 완료: {removed_vars}")
    
    def restart_services(self) -> bool:
        """서비스 재시작"""
        try:
            # PM2 재시작
            result = subprocess.run(["pm2", "restart", "POA"], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                log_message(f"PM2 재시작 실패: {result.stderr}")
                return False
            
            # PocketBase 재시작
            result = subprocess.run(["systemctl", "restart", "pocketbase"], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                log_message(f"PocketBase 재시작 실패: {result.stderr}")
                return False
            
            log_message("서비스 재시작 완료")
            return True
            
        except Exception as e:
            log_message(f"서비스 재시작 중 오류: {str(e)}")
            return False
    
    def get_current_config(self) -> Dict[str, Any]:
        """현재 설정 조회"""
        if not os.path.exists(self.env_file):
            return {}
        
        config = {}
        with open(self.env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # 따옴표 제거
                    value = value.strip('"').strip("'")
                    config[key] = value
        
        return config
    
    def add_kis_account(self, config: KISAccountConfig) -> Dict[str, Any]:
        """KIS 계정 추가"""
        try:
            # 백업
            backup_path = self.backup_env_file()
            
            # 환경 변수 추가
            env_vars = {
                f"KIS{config.kis_number}_KEY": config.key,
                f"KIS{config.kis_number}_SECRET": config.secret,
                f"KIS{config.kis_number}_ACCOUNT_NUMBER": config.account_number,
                f"KIS{config.kis_number}_ACCOUNT_CODE": config.account_code
            }
            
            self.update_env_file(env_vars)
            
            # 검증
            is_valid, errors = validate_environment()
            if not is_valid:
                # 백업에서 복구
                shutil.copy(backup_path, self.env_file)
                raise HTTPException(
                    status_code=400, 
                    detail=f"환경 변수 검증 실패: {errors}"
                )
            
            # 서비스 재시작
            if not self.restart_services():
                raise HTTPException(
                    status_code=500, 
                    detail="서비스 재시작 실패"
                )
            
            return {
                "status": "success", 
                "message": f"KIS{config.kis_number} 계정 추가 완료",
                "backup_path": backup_path
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"KIS 계정 추가 중 오류: {str(e)}"
            )
    
    def remove_kis_account(self, kis_number: int) -> Dict[str, Any]:
        """KIS 계정 제거"""
        try:
            if not 1 <= kis_number <= 50:
                raise ValueError("KIS 번호는 1-50 범위여야 합니다")
            
            # 백업
            backup_path = self.backup_env_file()
            
            # 환경 변수 제거
            var_names = [
                f"KIS{kis_number}_KEY",
                f"KIS{kis_number}_SECRET",
                f"KIS{kis_number}_ACCOUNT_NUMBER",
                f"KIS{kis_number}_ACCOUNT_CODE"
            ]
            
            self.remove_env_vars(var_names)
            
            # 서비스 재시작
            if not self.restart_services():
                raise HTTPException(
                    status_code=500, 
                    detail="서비스 재시작 실패"
                )
            
            return {
                "status": "success", 
                "message": f"KIS{kis_number} 계정 제거 완료",
                "backup_path": backup_path
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"KIS 계정 제거 중 오류: {str(e)}"
            )
    
    def update_exchange_config(self, config: ExchangeConfig) -> Dict[str, Any]:
        """거래소 설정 업데이트"""
        try:
            # 백업
            backup_path = self.backup_env_file()
            
            # 환경 변수 준비
            env_vars = {
                f"{config.exchange}_KEY": config.key,
                f"{config.exchange}_SECRET": config.secret
            }
            
            # 패스프레이즈가 필요한 거래소
            if config.exchange in ['BITGET', 'OKX'] and config.passphrase:
                env_vars[f"{config.exchange}_PASSPHRASE"] = config.passphrase
            
            self.update_env_file(env_vars)
            
            # 검증
            is_valid, errors = validate_environment()
            if not is_valid:
                # 백업에서 복구
                shutil.copy(backup_path, self.env_file)
                raise HTTPException(
                    status_code=400, 
                    detail=f"환경 변수 검증 실패: {errors}"
                )
            
            # 서비스 재시작
            if not self.restart_services():
                raise HTTPException(
                    status_code=500, 
                    detail="서비스 재시작 실패"
                )
            
            return {
                "status": "success", 
                "message": f"{config.exchange} 거래소 설정 업데이트 완료",
                "backup_path": backup_path
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"거래소 설정 업데이트 중 오류: {str(e)}"
            )
    
    def update_env_var(self, config: EnvVarConfig) -> Dict[str, Any]:
        """환경 변수 업데이트"""
        try:
            # 백업
            backup_path = self.backup_env_file()
            
            # 환경 변수 업데이트
            env_vars = {config.name: config.value}
            self.update_env_file(env_vars)
            
            # 검증
            is_valid, errors = validate_environment()
            if not is_valid:
                # 백업에서 복구
                shutil.copy(backup_path, self.env_file)
                raise HTTPException(
                    status_code=400, 
                    detail=f"환경 변수 검증 실패: {errors}"
                )
            
            # 서비스 재시작
            if not self.restart_services():
                raise HTTPException(
                    status_code=500, 
                    detail="서비스 재시작 실패"
                )
            
            return {
                "status": "success", 
                "message": f"{config.name} 환경 변수 업데이트 완료",
                "backup_path": backup_path
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"환경 변수 업데이트 중 오류: {str(e)}"
            )
    
    def get_system_status(self) -> Dict[str, Any]:
        """시스템 상태 조회"""
        try:
            # 환경 변수 검증
            is_valid, errors = validate_environment()
            
            # KIS 계정 요약
            kis_summary = get_kis_account_summary()
            
            # 서비스 상태
            service_status = {}
            
            # PM2 상태
            try:
                result = subprocess.run(["pm2", "describe", "POA"], 
                                      capture_output=True, text=True)
                service_status["pm2"] = result.returncode == 0
            except:
                service_status["pm2"] = False
            
            # PocketBase 상태
            try:
                result = subprocess.run(["systemctl", "is-active", "pocketbase"], 
                                      capture_output=True, text=True)
                service_status["pocketbase"] = result.stdout.strip() == "active"
            except:
                service_status["pocketbase"] = False
            
            return {
                "environment_valid": is_valid,
                "environment_errors": errors,
                "kis_accounts": kis_summary,
                "service_status": service_status,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "error": f"시스템 상태 조회 중 오류: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }

# 전역 설정 관리자 인스턴스
config_manager = ConfigManager()
