#!/usr/bin/env python3
"""
POA 시스템 기능 검증 스크립트
모든 주요 기능이 버그 없이 동작하는지 확인합니다.
"""

import os
import sys
import json
import yaml
import subprocess
import time
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class POASystemTester:
    def __init__(self):
        self.test_results = []
        self.passed = 0
        self.failed = 0
        
    def test(self, name: str, condition: bool, error_msg: str = ""):
        """테스트 결과 기록"""
        if condition:
            self.passed += 1
            logger.info(f"✓ {name}")
            self.test_results.append((name, "PASS", ""))
        else:
            self.failed += 1
            logger.error(f"✗ {name}: {error_msg}")
            self.test_results.append((name, "FAIL", error_msg))
            
    def run_all_tests(self):
        """모든 테스트 실행"""
        logger.info("=== POA 시스템 기능 검증 시작 ===")
        
        # 1. 환경 검증
        self.test_environment()
        
        # 2. KIS 번호 범위 테스트
        self.test_kis_number_range()
        
        # 3. 동적 설정 관리 테스트
        self.test_dynamic_config()
        
        # 4. 서비스 관리 테스트
        self.test_service_management()
        
        # 5. 보안 설정 테스트
        self.test_security_settings()
        
        # 6. 백업/복원 테스트
        self.test_backup_restore()
        
        # 결과 요약
        self.print_summary()
        
    def test_environment(self):
        """환경 설정 테스트"""
        logger.info("\n[1/6] 환경 설정 테스트")
        
        # Python 버전 확인
        python_version = sys.version_info
        self.test(
            "Python 3.10 이상",
            python_version.major == 3 and python_version.minor >= 10,
            f"현재 버전: {python_version.major}.{python_version.minor}"
        )
        
        # 필수 디렉토리 확인
        required_dirs = [
            "/root/POA",
            "/root/POA/scripts",
            "/root/POA/exchange",
            "/root/POA/exchange/stock",
            "/root/POA/config",
            "/root/POA/templates"
        ]
        
        for dir_path in required_dirs:
            # Windows 경로로 변환
            win_path = dir_path.replace("/root", "C:\\Temp")
            self.test(
                f"디렉토리 존재: {dir_path}",
                Path(win_path).exists(),
                f"경로를 찾을 수 없음: {win_path}"
            )
            
        # 필수 파일 확인
        required_files = [
            "/root/POA/exchange/stock/kis.py",
            "/root/POA/exchange/utils/validation.py",
            "/root/POA/scripts/config_manager.py",
            "/root/POA/scripts/env_manager.sh",
            "/root/POA/config/poa_config.yaml"
        ]
        
        for file_path in required_files:
            win_path = file_path.replace("/root", "C:\\Temp")
            self.test(
                f"파일 존재: {file_path}",
                Path(win_path).exists(),
                f"파일을 찾을 수 없음: {win_path}"
            )
            
    def test_kis_number_range(self):
        """KIS 번호 범위 테스트 (1-50)"""
        logger.info("\n[2/6] KIS 번호 범위 테스트")
        
        # validation.py에서 KIS 번호 범위 확인
        validation_path = Path("C:\\Temp\\POA\\exchange\\utils\\validation.py")
        if validation_path.exists():
            content = validation_path.read_text()
            self.test(
                "validation.py에 1-50 범위 체크 포함",
                "1 <= num <= 50" in content,
                "KIS 번호 범위 체크 코드를 찾을 수 없음"
            )
            
        # env_manager.sh에서 KIS 번호 범위 확인
        env_manager_path = Path("C:\\Temp\\POA\\scripts\\env_manager.sh")
        if env_manager_path.exists():
            content = env_manager_path.read_text()
            self.test(
                "env_manager.sh에 1-50 범위 체크 포함",
                '[ "$kis_num" -lt 1 ] || [ "$kis_num" -gt 50 ]' in content,
                "KIS 번호 범위 체크 스크립트를 찾을 수 없음"
            )
            
        # config_manager.py에서 KIS 번호 범위 확인
        config_manager_path = Path("C:\\Temp\\POA\\scripts\\config_manager.py")
        if config_manager_path.exists():
            content = config_manager_path.read_text()
            self.test(
                "config_manager.py에 1-50 범위 체크 포함",
                "1 <= num <= 50" in content,
                "KIS 번호 범위 체크 코드를 찾을 수 없음"
            )
            
    def test_dynamic_config(self):
        """동적 설정 관리 테스트"""
        logger.info("\n[3/6] 동적 설정 관리 테스트")
        
        # YAML 설정 파일 파싱 테스트
        config_path = Path("C:\\Temp\\POA\\config\\poa_config.yaml")
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                self.test("YAML 설정 파일 파싱", True, "")
                
                # 필수 섹션 확인
                required_sections = ['system', 'database', 'security', 'exchanges', 'kis_accounts']
                for section in required_sections:
                    self.test(
                        f"설정 섹션 존재: {section}",
                        section in config,
                        f"필수 섹션 누락: {section}"
                    )
                    
            except Exception as e:
                self.test("YAML 설정 파일 파싱", False, str(e))
                
        # config_manager.py 실행 가능 테스트
        config_manager = Path("C:\\Temp\\POA\\scripts\\config_manager.py")
        if config_manager.exists():
            try:
                # Python 구문 확인
                compile(config_manager.read_text(), str(config_manager), 'exec')
                self.test("config_manager.py 구문 검증", True, "")
            except SyntaxError as e:
                self.test("config_manager.py 구문 검증", False, str(e))
                
    def test_service_management(self):
        """서비스 관리 기능 테스트"""
        logger.info("\n[4/6] 서비스 관리 기능 테스트")
        
        # service_manager.sh 확인
        service_manager = Path("C:\\Temp\\POA\\scripts\\service_manager.sh")
        if service_manager.exists():
            content = service_manager.read_text()
            
            # 필수 명령어 확인
            commands = ['status', 'restart', 'stop', 'logs', 'health']
            for cmd in commands:
                self.test(
                    f"service_manager.sh에 '{cmd}' 명령 포함",
                    f'"{cmd}")' in content or f"'{cmd}')" in content,
                    f"'{cmd}' 명령을 찾을 수 없음"
                )
                
        # cloud-init 서비스 정의 확인
        cloud_init = Path("C:\\Temp\\POA\\templates\\cloud-init-dynamic.yaml")
        if cloud_init.exists():
            content = cloud_init.read_text()
            
            services = ['pm2-root.service', 'pocketbase.service', 'ntpd-sync.service']
            for service in services:
                self.test(
                    f"cloud-init에 {service} 정의",
                    service in content,
                    f"{service} 정의를 찾을 수 없음"
                )
                
    def test_security_settings(self):
        """보안 설정 테스트"""
        logger.info("\n[5/6] 보안 설정 테스트")
        
        # 화이트리스트 IP 검증
        config_path = Path("C:\\Temp\\POA\\config\\poa_config.yaml")
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    
                whitelist = config.get('security', {}).get('whitelist', [])
                self.test(
                    "화이트리스트 IP 설정",
                    len(whitelist) > 0,
                    "화이트리스트가 비어있음"
                )
                
                # Uptime Robot IP 확인
                uptime_ips = ["52.89.214.238", "34.212.75.30", "54.218.53.128", "52.32.178.7"]
                for ip in uptime_ips:
                    self.test(
                        f"Uptime Robot IP 포함: {ip}",
                        ip in whitelist,
                        "모니터링 IP 누락"
                    )
                    
            except Exception as e:
                self.test("보안 설정 확인", False, str(e))
                
        # 비밀번호 설정 확인
        validation_path = Path("C:\\Temp\\POA\\exchange\\utils\\validation.py")
        if validation_path.exists():
            content = validation_path.read_text()
            self.test(
                "비밀번호 필수 검증 포함",
                '"PASSWORD"' in content,
                "비밀번호 검증 코드를 찾을 수 없음"
            )
            
    def test_backup_restore(self):
        """백업/복원 기능 테스트"""
        logger.info("\n[6/6] 백업/복원 기능 테스트")
        
        # 백업 함수 확인
        bash_functions = Path("C:\\Temp\\POA\\templates\\cloud-init-dynamic.yaml")
        if bash_functions.exists():
            content = bash_functions.read_text()
            
            backup_commands = ['poa_backup', 'create', 'list', 'restore']
            for cmd in backup_commands:
                self.test(
                    f"백업 명령 '{cmd}' 정의",
                    cmd in content,
                    f"백업 명령 '{cmd}'를 찾을 수 없음"
                )
                
        # 로그 로테이션 설정 확인
        self.test(
            "로그 로테이션 설정",
            'logrotate.d/poa' in content if bash_functions.exists() and content else False,
            "로그 로테이션 설정을 찾을 수 없음"
        )
        
    def print_summary(self):
        """테스트 결과 요약"""
        total = self.passed + self.failed
        logger.info("\n" + "="*50)
        logger.info("테스트 결과 요약")
        logger.info("="*50)
        logger.info(f"총 테스트: {total}")
        logger.info(f"성공: {self.passed} ({self.passed/total*100:.1f}%)")
        logger.info(f"실패: {self.failed} ({self.failed/total*100:.1f}%)")
        
        if self.failed > 0:
            logger.info("\n실패한 테스트:")
            for name, status, error in self.test_results:
                if status == "FAIL":
                    logger.info(f"  - {name}: {error}")
                    
        logger.info("\n" + "="*50)
        
        # 권장사항
        if self.failed > 0:
            logger.info("\n권장사항:")
            logger.info("1. 실패한 테스트 항목을 확인하고 수정하세요.")
            logger.info("2. 모든 파일이 올바른 경로에 있는지 확인하세요.")
            logger.info("3. 파일 권한과 소유권을 확인하세요.")
        else:
            logger.info("\n✅ 모든 테스트를 통과했습니다!")
            logger.info("POA 시스템이 정상적으로 작동할 준비가 되었습니다.")

def main():
    """메인 함수"""
    tester = POASystemTester()
    tester.run_all_tests()
    
    # 테스트 실패 시 비정상 종료
    if tester.failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
