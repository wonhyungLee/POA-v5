#!/usr/bin/env python3
"""
POA 동적 설정 관리 스크립트
YAML 설정 파일을 읽어서 환경 변수로 변환하고 서비스를 재시작합니다.
"""

import os
import sys
import yaml
import json
import logging
from typing import Dict, Any, List
from pathlib import Path
import subprocess
import shutil
from datetime import datetime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/root/logs/config_manager.log')
    ]
)
logger = logging.getLogger(__name__)

class POAConfigManager:
    def __init__(self, config_file: str = "/root/config/poa_config.yaml"):
        self.config_file = Path(config_file)
        self.env_file = Path("/root/.env")
        self.backup_dir = Path("/root/backups")
        self.backup_dir.mkdir(exist_ok=True)
        
    def load_config(self) -> Dict[str, Any]:
        """YAML 설정 파일 로드"""
        if not self.config_file.exists():
            logger.error(f"설정 파일이 존재하지 않습니다: {self.config_file}")
            sys.exit(1)
            
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info("설정 파일을 성공적으로 로드했습니다.")
            return config
        except Exception as e:
            logger.error(f"설정 파일 로드 중 오류: {e}")
            sys.exit(1)
            
    def backup_env_file(self):
        """현재 환경 변수 파일 백업"""
        if self.env_file.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f".env.{timestamp}"
            shutil.copy2(self.env_file, backup_path)
            logger.info(f"환경 변수 파일 백업 완료: {backup_path}")
            
    def convert_to_env_vars(self, config: Dict[str, Any]) -> Dict[str, str]:
        """YAML 설정을 환경 변수로 변환"""
        env_vars = {}
        
        # 시스템 설정
        if 'system' in config:
            env_vars['APP_NAME'] = config['system'].get('app_name', 'POA')
            env_vars['PORT'] = str(config['system'].get('port', 80))
            env_vars['LOG_LEVEL'] = config['system'].get('log_level', 'INFO')
            
        # 데이터베이스 설정
        if 'database' in config:
            env_vars['DB_ID'] = config['database'].get('id', '')
            env_vars['DB_PASSWORD'] = config['database'].get('password', '')
            
        # 보안 설정
        if 'security' in config:
            env_vars['PASSWORD'] = config['security'].get('password', '')
            whitelist = config['security'].get('whitelist', [])
            env_vars['WHITELIST'] = json.dumps(whitelist)
            
        # Discord 설정
        if 'discord' in config:
            env_vars['DISCORD_WEBHOOK_URL'] = config['discord'].get('webhook_url', '')
            
        # 거래소 설정
        if 'exchanges' in config:
            for exchange, settings in config['exchanges'].items():
                if settings.get('enabled', False):
                    prefix = exchange.upper()
                    env_vars[f'{prefix}_KEY'] = settings.get('key', '')
                    env_vars[f'{prefix}_SECRET'] = settings.get('secret', '')
                    if 'passphrase' in settings:
                        env_vars[f'{prefix}_PASSPHRASE'] = settings.get('passphrase', '')
                        
        # KIS 계정 설정
        if 'kis_accounts' in config and config['kis_accounts']:
            for account in config['kis_accounts']:
                if isinstance(account, dict) and 'number' in account:
                    num = account['number']
                    if 1 <= num <= 50:
                        env_vars[f'KIS{num}_KEY'] = account.get('key', '')
                        env_vars[f'KIS{num}_SECRET'] = account.get('secret', '')
                        env_vars[f'KIS{num}_ACCOUNT_NUMBER'] = account.get('account_number', '')
                        env_vars[f'KIS{num}_ACCOUNT_CODE'] = account.get('account_code', '')
                    else:
                        logger.warning(f"KIS 번호가 유효 범위(1-50)를 벗어남: {num}")
                        
        # 도메인 설정
        if 'services' in config and 'caddy' in config['services']:
            domain = config['services']['caddy'].get('domain', '')
            if domain:
                env_vars['DOMAIN'] = domain
                
        return env_vars
        
    def write_env_file(self, env_vars: Dict[str, str]):
        """환경 변수 파일 작성"""
        self.backup_env_file()
        
        try:
            with open(self.env_file, 'w', encoding='utf-8') as f:
                for key, value in sorted(env_vars.items()):
                    # 빈 값은 제외
                    if value:
                        # 값에 따옴표가 포함되어 있으면 이스케이프
                        if '"' in value:
                            value = value.replace('"', '\\"')
                        f.write(f'{key}="{value}"\n')
                        
            logger.info(f"환경 변수 파일 작성 완료: {self.env_file}")
        except Exception as e:
            logger.error(f"환경 변수 파일 작성 중 오류: {e}")
            sys.exit(1)
            
    def validate_config(self) -> List[str]:
        """설정 검증"""
        errors = []
        config = self.load_config()
        
        # 필수 설정 확인
        if not config.get('security', {}).get('password'):
            errors.append("보안 비밀번호가 설정되지 않았습니다.")
            
        if not config.get('database', {}).get('id'):
            errors.append("데이터베이스 ID가 설정되지 않았습니다.")
            
        if not config.get('database', {}).get('password'):
            errors.append("데이터베이스 비밀번호가 설정되지 않았습니다.")
            
        # KIS 계정 검증
        kis_accounts = config.get('kis_accounts', [])
        if kis_accounts:
            for account in kis_accounts:
                if isinstance(account, dict):
                    num = account.get('number')
                    if not num:
                        errors.append("KIS 계정 번호가 누락되었습니다.")
                    elif num < 1 or num > 50:
                        errors.append(f"KIS{num} 번호가 유효 범위(1-50)를 벗어났습니다.")
                    
                    required_fields = ['key', 'secret', 'account_number', 'account_code']
                    missing = [f for f in required_fields if not account.get(f)]
                    if missing:
                        errors.append(f"KIS{num} 계정의 필수 필드가 누락되었습니다: {missing}")
                        
        return errors
        
    def restart_services(self):
        """서비스 재시작"""
        logger.info("서비스 재시작 시작...")
        
        # PM2 재시작
        try:
            subprocess.run(['pm2', 'restart', 'POA'], check=True)
            logger.info("PM2 서비스 재시작 완료")
        except subprocess.CalledProcessError as e:
            logger.error(f"PM2 재시작 실패: {e}")
        except FileNotFoundError:
            logger.warning("PM2가 설치되어 있지 않습니다.")
            
        # PocketBase 재시작
        try:
            subprocess.run(['systemctl', 'restart', 'pocketbase'], check=True)
            logger.info("PocketBase 서비스 재시작 완료")
        except subprocess.CalledProcessError as e:
            logger.error(f"PocketBase 재시작 실패: {e}")
            
    def apply_config(self):
        """설정 적용"""
        logger.info("POA 설정 적용 시작...")
        
        # 설정 검증
        errors = self.validate_config()
        if errors:
            logger.error("설정 검증 실패:")
            for error in errors:
                logger.error(f"  - {error}")
            sys.exit(1)
            
        # 설정 로드 및 변환
        config = self.load_config()
        env_vars = self.convert_to_env_vars(config)
        
        # 환경 변수 파일 작성
        self.write_env_file(env_vars)
        
        # 서비스 재시작
        self.restart_services()
        
        logger.info("설정 적용 완료!")
        
    def show_status(self):
        """현재 설정 상태 표시"""
        config = self.load_config()
        
        print("=== POA 시스템 설정 상태 ===")
        print(f"설정 파일: {self.config_file}")
        print(f"환경 변수 파일: {self.env_file}")
        print()
        
        # 시스템 설정
        print("[시스템 설정]")
        system = config.get('system', {})
        print(f"  앱 이름: {system.get('app_name', 'POA')}")
        print(f"  포트: {system.get('port', 80)}")
        print(f"  로그 레벨: {system.get('log_level', 'INFO')}")
        print()
        
        # 거래소 설정
        print("[거래소 설정]")
        exchanges = config.get('exchanges', {})
        active_exchanges = [name for name, settings in exchanges.items() 
                          if settings.get('enabled', False)]
        print(f"  활성 거래소: {', '.join(active_exchanges) if active_exchanges else '없음'}")
        print()
        
        # KIS 계정
        print("[KIS 계정]")
        kis_accounts = config.get('kis_accounts', [])
        if kis_accounts:
            for account in kis_accounts:
                if isinstance(account, dict) and 'number' in account:
                    num = account['number']
                    print(f"  KIS{num}: {'설정됨' if account.get('key') else '미설정'}")
        else:
            print("  설정된 계정 없음")
        print()
        
        # 보안 설정
        print("[보안 설정]")
        security = config.get('security', {})
        print(f"  비밀번호: {'설정됨' if security.get('password') else '미설정'}")
        whitelist = security.get('whitelist', [])
        print(f"  화이트리스트 IP: {len(whitelist)}개")
        print()

def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='POA 동적 설정 관리')
    parser.add_argument('command', choices=['apply', 'validate', 'status', 'help'],
                       help='실행할 명령')
    parser.add_argument('--config', default='/root/config/poa_config.yaml',
                       help='설정 파일 경로')
    
    args = parser.parse_args()
    
    manager = POAConfigManager(args.config)
    
    if args.command == 'apply':
        manager.apply_config()
    elif args.command == 'validate':
        errors = manager.validate_config()
        if errors:
            print("설정 검증 실패:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
        else:
            print("설정 검증 성공!")
    elif args.command == 'status':
        manager.show_status()
    elif args.command == 'help':
        parser.print_help()
        print("\n사용 예시:")
        print("  python3 config_manager.py status     # 현재 설정 상태 확인")
        print("  python3 config_manager.py validate   # 설정 검증")
        print("  python3 config_manager.py apply      # 설정 적용 및 서비스 재시작")

if __name__ == "__main__":
    main()
