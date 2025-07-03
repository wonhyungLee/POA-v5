"""
KIS 동적 설정 지원을 위한 헬퍼 모듈
"""
from typing import Any

class DynamicKISSettings:
    """KIS1~KIS50까지 동적으로 처리하는 헬퍼 클래스"""
    
    def __init__(self, settings_dict: dict):
        self._settings = settings_dict
    
    def get_kis_settings(self, kis_number: int) -> tuple[str, str, str, str] | None:
        """
        지정된 KIS 번호의 설정을 반환
        
        Args:
            kis_number: KIS 번호 (1-50)
            
        Returns:
            (key, secret, account_number, account_code) 또는 None
        """
        if not 1 <= kis_number <= 50:
            return None
            
        prefix = f"KIS{kis_number}"
        
        key = self._settings.get(f"{prefix}_KEY")
        secret = self._settings.get(f"{prefix}_SECRET")
        account_number = self._settings.get(f"{prefix}_ACCOUNT_NUMBER")
        account_code = self._settings.get(f"{prefix}_ACCOUNT_CODE")
        
        if all([key, secret, account_number, account_code]):
            return key, secret, account_number, account_code
        
        return None
    
    def has_kis_settings(self, kis_number: int) -> bool:
        """지정된 KIS 번호의 설정이 있는지 확인"""
        return self.get_kis_settings(kis_number) is not None
