from pydantic import BaseModel, BaseSettings, validator, root_validator
from typing import Literal, Dict, Any
import os
import json
import ipaddress
from pathlib import Path
from enum import Enum
from devtools import debug

CRYPTO_LITERAL = Literal["BINANCE", "UPBIT", "BYBIT", "BITGET", "OKX"]


STOCK_LITERAL = Literal[
    "KRX",
    "NASDAQ",
    "NYSE",
    "AMEX",
]


EXCHANGE_LITERAL = Literal[
    "BINANCE",
    "UPBIT",
    "BYBIT",
    "BITGET",
    "OKX",
    "KRX",
    "NASDAQ",
    "NYSE",
    "AMEX",
]

QUOTE_LITERAL = Literal[
    "USDT", "USDT.P", "USDTPERP", "BUSD", "BUSD.P", "BUSDPERP", "KRW", "USD", "USD.P"
]

SIDE_LITERAL = Literal[
    "buy", "sell", "entry/buy", "entry/sell", "close/buy", "close/sell"
]


def find_env_file():
    current_path = os.path.abspath(__file__)
    while True:
        parent_path = os.path.dirname(current_path)
        env_path = os.path.join(parent_path, ".env")
        dev_env_path = os.path.join(parent_path, ".env.dev")
        if os.path.isfile(dev_env_path):
            return dev_env_path
        elif os.path.isfile(env_path):
            return env_path
        if parent_path == current_path:
            break
        current_path = parent_path
    return None


env_path = find_env_file()


CRYPTO_EXCHANGES = ("BINANCE", "UPBIT", "BYBIT", "BITGET", "OKX")

STOCK_EXCHANGES = (
    "KRX",
    "NASDAQ",
    "NYSE",
    "AMEX",
)

COST_BASED_ORDER_EXCHANGES = ("UPBIT", "BYBIT", "BITGET")

NO_ORDER_AMOUNT_OUTPUT_EXCHANGES = (
    "BITGET",
    "KRX",
    "NASDAQ",
    "NYSE",
    "AMEX",
)

# "BITGET", "KRX", "NASDAQ", "AMEX", "NYSE")


crypto_futures_code = ("PERP", ".P")

# Literal[
#     "KRW", "USDT", "USDTPERP", "BUSD", "BUSDPERP", "USDT.P", "USD", "BUSD.P"
# ]


class Settings(BaseSettings):
    PASSWORD: str
    WHITELIST: list[str] | None = None
    PORT: int | None = None
    DISCORD_WEBHOOK_URL: str | None = None
    
    # 거래소 API 키들
    UPBIT_KEY: str | None = None
    UPBIT_SECRET: str | None = None
    BINANCE_KEY: str | None = None
    BINANCE_SECRET: str | None = None
    BYBIT_KEY: str | None = None
    BYBIT_SECRET: str | None = None
    BITGET_KEY: str | None = None
    BITGET_SECRET: str | None = None
    BITGET_PASSPHRASE: str | None = None
    OKX_KEY: str | None = None
    OKX_SECRET: str | None = None
    OKX_PASSPHRASE: str | None = None
    
    # 데이터베이스 설정
    DB_ID: str = "poa@admin.com"
    DB_PASSWORD: str = "poabot!@#$"

    class Config:
        env_file = env_path
        env_file_encoding = "utf-8"
        # 추가 환경 변수 허용 (KIS1~KIS50 동적 처리)
        extra = "allow"
    
    def __getattr__(self, name: str) -> Any:
        """동적 KIS 설정 접근을 위한 메서드"""
        if name.startswith("KIS") and name.endswith(("_KEY", "_SECRET", "_ACCOUNT_NUMBER", "_ACCOUNT_CODE")):
            # 환경 변수에서 직접 읽기
            value = os.getenv(name)
            return value
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'") 
    
    def get_kis_settings(self, kis_number: int) -> tuple[str, str, str, str] | None:
        """지정된 KIS 번호의 설정을 반환"""
        if not 1 <= kis_number <= 50:
            return None
            
        prefix = f"KIS{kis_number}"
        
        key = os.getenv(f"{prefix}_KEY")
        secret = os.getenv(f"{prefix}_SECRET")
        account_number = os.getenv(f"{prefix}_ACCOUNT_NUMBER")
        account_code = os.getenv(f"{prefix}_ACCOUNT_CODE")
        
        if all([key, secret, account_number, account_code]):
            return key, secret, account_number, account_code
        
        return None
    
    def has_kis_settings(self, kis_number: int) -> bool:
        """지정된 KIS 번호의 설정이 있는지 확인"""
        return self.get_kis_settings(kis_number) is not None
    
    def get_available_kis_numbers(self) -> list[int]:
        """사용 가능한 KIS 번호 목록 반환"""
        available = []
        for i in range(1, 51):
            if self.has_kis_settings(i):
                available.append(i)
        return available
    
    @validator("WHITELIST", pre=True, always=True)
    def validate_whitelist(cls, v):
        """화이트리스트 IP 주소 유효성 검사"""
        if v is None:
            return []
        
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                # 문자열이 JSON이 아닌 경우 콤마로 분할
                v = [ip.strip() for ip in v.split(',')]
        
        if not isinstance(v, list):
            return []
        
        validated_ips = []
        for ip in v:
            if ip and ip.strip():
                ip = ip.strip()
                try:
                    # IP 주소 유효성 검사
                    ipaddress.ip_address(ip)
                    validated_ips.append(ip)
                except ValueError:
                    # 유효하지 않은 IP는 무시
                    continue
        
        return validated_ips


def get_extra_order_info(order_info):
    extra_order_info = {
        "is_futures": None,
        "is_crypto": None,
        "is_stock": None,
        "is_spot": None,
        "is_entry": None,
        "is_close": None,
        "is_buy": None,
        "is_sell": None,
    }
    if order_info["exchange"] in CRYPTO_EXCHANGES:
        extra_order_info["is_crypto"] = True
        if any([order_info["quote"].endswith(code) for code in crypto_futures_code]):
            extra_order_info["is_futures"] = True
        else:
            extra_order_info["is_spot"] = True

    elif order_info["exchange"] in STOCK_EXCHANGES:
        extra_order_info["is_stock"] = True

    if order_info["side"] in ("entry/buy", "entry/sell"):
        extra_order_info["is_entry"] = True
        _side = order_info["side"].split("/")[-1]
        if _side == "buy":
            extra_order_info["is_buy"] = True
        elif _side == "sell":
            extra_order_info["is_sell"] = True
    elif order_info["side"] in ("close/buy", "close/sell"):
        extra_order_info["is_close"] = True
        _side = order_info["side"].split("/")[-1]
        if _side == "buy":
            extra_order_info["is_buy"] = True
        elif _side == "sell":
            extra_order_info["is_sell"] = True
    elif order_info["side"] == "buy":
        extra_order_info["is_buy"] = True
    elif order_info["side"] == "sell":
        extra_order_info["is_sell"] = True

    return extra_order_info


def parse_side(side: str):
    if side.startswith("entry/") or side.startswith("close/"):
        return side.split("/")[-1]
    else:
        return side


def parse_quote(quote: str):
    if quote.endswith(".P"):
        return quote.replace(".P", "")
    else:
        return quote


class OrderRequest(BaseModel):
    exchange: EXCHANGE_LITERAL
    base: str
    quote: QUOTE_LITERAL
    # QUOTE
    type: Literal["market", "limit"] = "market"
    side: SIDE_LITERAL
    amount: float | None = None
    price: float | None = None
    cost: float | None = None
    percent: float | None = None
    amount_by_percent: float | None = None
    leverage: int | None = None
    stop_price: float | None = None
    profit_price: float | None = None
    order_name: str = "주문"
    kis_number: int | None = 1  # 1-50 범위 지원
    hedge: str | None = None
    unified_symbol: str | None = None
    is_crypto: bool | None = None
    is_stock: bool | None = None
    is_spot: bool | None = None
    is_futures: bool | None = None
    is_coinm: bool | None = None
    is_entry: bool | None = None
    is_close: bool | None = None
    is_buy: bool | None = None
    is_sell: bool | None = None
    is_total: bool | None = None
    is_contract: bool | None = None
    contract_size: float | None = None
    margin_mode: str | None = None

    class Config:
        use_enum_values = True

    @root_validator(pre=True)
    def root_validate(cls, values):
        # "NaN" to None
        for key, value in values.items():
            if isinstance(value, str):
                values[key] = value.replace(',', '')
            if values[key] in ("NaN", ""):
                values[key] = None
            

        values |= get_extra_order_info(values)

        values["side"] = parse_side(values["side"])
        values["quote"] = parse_quote(values["quote"])
        base = values["base"]
        quote = values["quote"]
        unified_symbol = f"{base}/{quote}"
        exchange = values["exchange"]
        if values["is_futures"]:
            if quote == "USD":
                unified_symbol = f"{base}/{quote}:{base}"
                values["is_coinm"] = True
            else:
                unified_symbol = f"{base}/{quote}:{quote}"

        if not values["is_stock"]:
            values["unified_symbol"] = unified_symbol

        if values["exchange"] in STOCK_EXCHANGES:
            values["is_stock"] = True
        return values


class OrderBase(OrderRequest):
    password: str

    @validator("password")
    def password_validate(cls, v):
        try:
            setting = Settings()
            if v != setting.PASSWORD:
                raise ValueError("비밀번호가 틀렸습니다")
            return v
        except Exception as e:
            raise ValueError(f"비밀번호 검증 중 오류: {str(e)}")


class MarketOrder(OrderBase):
    price: float | None = None
    type: Literal["market"] = "market"


class PriceRequest(BaseModel):
    exchange: EXCHANGE_LITERAL
    base: str
    quote: QUOTE_LITERAL
    is_crypto: bool | None = None
    is_stock: bool | None = None
    is_futures: bool | None = None

    @root_validator(pre=True)
    def root_validate(cls, values):
        # "NaN" to None
        for key, value in values.items():
            if isinstance(value, str):
                values[key] = value.replace(',', '')
            if values[key] in ("NaN", ""):
                values[key] = None

        values |= get_extra_order_info(values)

        return values


# class PositionRequest(BaseModel):
#     exchange: EXCHANGE_LITERAL
#     base: str
#     quote: QUOTE_LITERAL


class Position(BaseModel):
    exchange: EXCHANGE_LITERAL
    base: str
    quote: QUOTE_LITERAL
    side: Literal["long", "short"]
    amount: float
    entry_price: float
    roe: float


class HedgeData(BaseModel):
    password: str
    exchange: Literal["BINANCE"]
    base: str
    quote: QUOTE_LITERAL = "USDT.P"
    amount: float | None = None
    leverage: int | None = None
    hedge: str

    @validator("password")
    def password_validate(cls, v):
        try:
            setting = Settings()
            if v != setting.PASSWORD:
                raise ValueError("비밀번호가 틀렸습니다")
            return v
        except Exception as e:
            raise ValueError(f"비밀번호 검증 중 오류: {str(e)}")

    @root_validator(pre=True)
    def root_validate(cls, values):
        for key, value in values.items():
            if key in ("exchange", "base", "quote", "hedge"):
                values[key] = value.upper()
        return values
