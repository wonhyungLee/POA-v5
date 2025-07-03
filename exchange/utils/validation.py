"""
POA 시스템 환경 변수 검증 유틸리티
"""
import os
import json
import ipaddress
import logging
from typing import List, Dict, Any
from exchange.utility.LogMaker import logger

def validate_environment() -> tuple[bool, List[str]]:
    """환경 변수 유효성 검사
    
    Returns:
        tuple: (검증 성공 여부, 오류 메시지 목록)
    """
    errors = []
    
    # 필수 환경 변수 체크
    required_vars = ["PASSWORD", "DB_ID", "DB_PASSWORD"]
    for var in required_vars:
        if not os.getenv(var):
            errors.append(f"필수 환경 변수 {var}가 설정되지 않음")
    
    # KIS 계정 완성도 체크
    kis_validation_errors = validate_kis_accounts()
    errors.extend(kis_validation_errors)
    
    # 화이트리스트 IP 형식 체크
    whitelist_errors = validate_whitelist()
    errors.extend(whitelist_errors)
    
    # 포트 번호 체크
    port_errors = validate_port()
    errors.extend(port_errors)
    
    # 거래소 API 키 체크
    exchange_errors = validate_exchange_keys()
    errors.extend(exchange_errors)
    
    if errors:
        for error in errors:
            logger.error(f"환경 변수 검증 오류: {error}")
        return False, errors
    
    logger.info("환경 변수 검증 성공")
    return True, []

def validate_kis_accounts() -> List[str]:
    """KIS 계정 설정 검증"""
    errors = []
    kis_accounts = {}
    
    # 환경 변수에서 KIS 계정 정보 수집
    for key, value in os.environ.items():
        if key.startswith("KIS") and key.endswith(("_KEY", "_SECRET", "_ACCOUNT_NUMBER", "_ACCOUNT_CODE")):
            kis_num = key.split("_")[0]
            if kis_num not in kis_accounts:
                kis_accounts[kis_num] = {}
            kis_accounts[kis_num][key.split("_", 1)[1]] = value
    
    # 불완전한 KIS 계정 체크
    for kis_num, config in kis_accounts.items():
        required_keys = ["KEY", "SECRET", "ACCOUNT_NUMBER", "ACCOUNT_CODE"]
        missing_keys = [key for key in required_keys if key not in config or not config[key]]
        if missing_keys:
            errors.append(f"{kis_num} 계정의 누락된 설정: {missing_keys}")
        
        # KIS 번호 범위 체크
        try:
            num = int(kis_num.replace("KIS", ""))
            if not 1 <= num <= 50:
                errors.append(f"{kis_num} 번호가 유효 범위(1-50)를 벗어남")
        except ValueError:
            errors.append(f"{kis_num} 번호 형식이 잘못됨")
    
    if kis_accounts:
        logger.info(f"KIS 계정 {len(kis_accounts)}개 발견")
    
    return errors

def validate_whitelist() -> List[str]:
    """화이트리스트 IP 주소 검증"""
    errors = []
    whitelist = os.getenv("WHITELIST", "[]")
    
    try:
        if isinstance(whitelist, str):
            try:
                ip_list = json.loads(whitelist)
            except json.JSONDecodeError:
                # JSON이 아닌 경우 콤마로 분할
                ip_list = [ip.strip() for ip in whitelist.split(',')]
        else:
            ip_list = whitelist
        
        if not isinstance(ip_list, list):
            errors.append("화이트리스트 형식이 잘못됨 (배열이어야 함)")
            return errors
        
        for ip in ip_list:
            if ip and ip.strip():
                ip = ip.strip()
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    errors.append(f"잘못된 IP 주소: {ip}")
                    
    except Exception as e:
        errors.append(f"화이트리스트 검증 중 오류: {str(e)}")
    
    return errors

def validate_port() -> List[str]:
    """포트 번호 검증"""
    errors = []
    port = os.getenv("PORT")
    
    if port:
        try:
            port_num = int(port)
            if not 1 <= port_num <= 65535:
                errors.append(f"포트 번호가 유효 범위(1-65535)를 벗어남: {port_num}")
        except ValueError:
            errors.append(f"포트 번호 형식이 잘못됨: {port}")
    
    return errors

def validate_exchange_keys() -> List[str]:
    """거래소 API 키 검증"""
    errors = []
    exchanges = ["BINANCE", "UPBIT", "BYBIT", "BITGET", "OKX"]
    
    for exchange in exchanges:
        key = os.getenv(f"{exchange}_KEY")
        secret = os.getenv(f"{exchange}_SECRET")
        
        # 키와 시크릿이 모두 있거나 모두 없어야 함
        if (key and not secret) or (not key and secret):
            errors.append(f"{exchange} 거래소의 키 설정이 불완전함 (KEY, SECRET 모두 필요)")
        
        # 패스프레이즈가 필요한 거래소 체크
        if exchange in ["BITGET", "OKX"]:
            passphrase = os.getenv(f"{exchange}_PASSPHRASE")
            if key and secret and not passphrase:
                errors.append(f"{exchange} 거래소의 패스프레이즈가 설정되지 않음")
    
    return errors

def get_kis_account_summary() -> Dict[str, Any]:
    """KIS 계정 요약 정보 반환"""
    kis_accounts = {}
    
    for key, value in os.environ.items():
        if key.startswith("KIS") and key.endswith(("_KEY", "_SECRET", "_ACCOUNT_NUMBER", "_ACCOUNT_CODE")):
            kis_num = key.split("_")[0]
            if kis_num not in kis_accounts:
                kis_accounts[kis_num] = {}
            kis_accounts[kis_num][key.split("_", 1)[1]] = bool(value)
    
    summary = {
        "total_accounts": len(kis_accounts),
        "complete_accounts": 0,
        "incomplete_accounts": 0,
        "accounts": {}
    }
    
    for kis_num, config in kis_accounts.items():
        required_keys = ["KEY", "SECRET", "ACCOUNT_NUMBER", "ACCOUNT_CODE"]
        has_all_keys = all(key in config and config[key] for key in required_keys)
        
        if has_all_keys:
            summary["complete_accounts"] += 1
        else:
            summary["incomplete_accounts"] += 1
        
        summary["accounts"][kis_num] = {
            "complete": has_all_keys,
            "missing_keys": [key for key in required_keys if key not in config or not config[key]]
        }
    
    return summary

def print_environment_summary():
    """환경 변수 설정 요약 출력"""
    logger.info("=== POA 환경 변수 요약 ===")
    
    # 기본 설정
    logger.info(f"PASSWORD: {'✓' if os.getenv('PASSWORD') else '✗'}")
    logger.info(f"PORT: {os.getenv('PORT', 'Not set')}")
    logger.info(f"DISCORD_WEBHOOK: {'✓' if os.getenv('DISCORD_WEBHOOK_URL') else '✗'}")
    
    # KIS 계정 요약
    kis_summary = get_kis_account_summary()
    logger.info(f"KIS 계정: {kis_summary['complete_accounts']}개 완료, {kis_summary['incomplete_accounts']}개 불완전")
    
    # 거래소 요약
    exchanges = ["BINANCE", "UPBIT", "BYBIT", "BITGET", "OKX"]
    active_exchanges = []
    for exchange in exchanges:
        if os.getenv(f"{exchange}_KEY") and os.getenv(f"{exchange}_SECRET"):
            active_exchanges.append(exchange)
    
    logger.info(f"활성 거래소: {', '.join(active_exchanges) if active_exchanges else 'None'}")
    
    # 화이트리스트
    whitelist = os.getenv("WHITELIST", "[]")
    try:
        ip_list = json.loads(whitelist) if isinstance(whitelist, str) else whitelist
        logger.info(f"화이트리스트 IP: {len(ip_list)}개")
    except:
        logger.info("화이트리스트: 형식 오류")
    
    logger.info("========================")

if __name__ == "__main__":
    # 테스트 실행
    is_valid, errors = validate_environment()
    if not is_valid:
        print("환경 변수 검증 실패:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("환경 변수 검증 성공")
    
    print_environment_summary()
