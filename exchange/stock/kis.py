from datetime import datetime
import json
import httpx
import time
from exchange.stock.error import TokenExpired
from exchange.stock.schemas import *
from exchange.database import db
from pydantic import validate_arguments
import traceback
import copy
from exchange.model import MarketOrder
from devtools import debug
import logging

# 로깅 설정
logger = logging.getLogger(__name__)


class KoreaInvestment:
    def __init__(
        self,
        key: str,
        secret: str,
        account_number: str,
        account_code: str,
        kis_number: int,
    ):
        self.key = key
        self.secret = secret
        self.kis_number = kis_number
        self.base_url = BaseUrls.base_url.value  # 모든 kis 번호에 대해 실전투자 사용
        self.is_auth = False
        self.account_number = account_number
        self.base_headers = {}
        self.session = httpx.Client()
        self.async_session = httpx.AsyncClient()
        self.auth()

        self.base_body = {}
        self.base_order_body = AccountInfo(
            CANO=account_number, ACNT_PRDT_CD=account_code
        )
        self.order_exchange_code = {
            "NASDAQ": ExchangeCode.NASDAQ,
            "NYSE": ExchangeCode.NYSE,
            "AMEX": ExchangeCode.AMEX,
        }
        self.query_exchange_code = {
            "NASDAQ": QueryExchangeCode.NASDAQ,
            "NYSE": QueryExchangeCode.NYSE,
            "AMEX": QueryExchangeCode.AMEX,
        }

    def init_info(self, order_info: MarketOrder):
        self.order_info = order_info

    def close_session(self):
        self.session.close()

    def get(self, endpoint: str, params: dict = None, headers: dict = None):
        url = f"{self.base_url}{endpoint}"
        # headers |= self.base_headers
        return self.session.get(url, params=params, headers=headers).json()

    def post_with_error_handling(
        self, endpoint: str, data: dict = None, headers: dict = None
    ):
        url = f"{self.base_url}{endpoint}"
        response = self.session.post(url, json=data, headers=headers).json()
        if "access_token" in response.keys() or response["rt_cd"] == "0":
            return response
        else:
            raise Exception(response)

    def post(self, endpoint: str, data: dict = None, headers: dict = None):
        return self.post_with_error_handling(endpoint, data, headers)

    def get_hashkey(self, data) -> str:
        headers = {"appKey": self.key, "appSecret": self.secret}
        endpoint = "/uapi/hashkey"
        url = f"{self.base_url}{endpoint}"
        return self.session.post(url, json=data, headers=headers).json()["HASH"]

    def open_auth(self):
        return self.open_json("auth.json")

    def write_auth(self, auth):
        self.write_json("auth.json", auth)

    def check_auth(self, auth, key, secret, kis_number):
        """인증 토큰 유효성 검사"""
        if auth is None:
            logger.debug(f"KIS{kis_number}: 인증 정보가 없음")
            return False
        
        try:
            access_token, access_token_token_expired = auth
            
            if access_token == "nothing":
                logger.debug(f"KIS{kis_number}: 토큰이 'nothing'으로 설정됨")
                return False
            
            # 토큰 유효성 API 호출 테스트
            if not self.is_auth:
                try:
                    response = self.session.get(
                        "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-ccnl",
                        headers={
                            "authorization": f"BEARER {access_token}",
                            "appkey": key,
                            "appsecret": secret,
                            "custtype": "P",
                            "tr_id": "FHKST01010300",
                        },
                        params={
                            "FID_COND_MRKT_DIV_CODE": "J",
                            "FID_INPUT_ISCD": "005930",
                        },
                        timeout=10  # 타임아웃 추가
                    )
                    
                    if response.status_code != 200:
                        logger.warning(f"KIS{kis_number}: API 호출 실패 - HTTP {response.status_code}")
                        return False
                    
                    response_data = response.json()
                    if response_data.get("msg_cd") == "EGW00123":
                        logger.debug(f"KIS{kis_number}: 토큰이 만료됨")
                        return False
                        
                except httpx.TimeoutException:
                    logger.warning(f"KIS{kis_number}: API 호출 타임아웃")
                    return False
                except httpx.HTTPStatusError as e:
                    logger.warning(f"KIS{kis_number}: API 호출 HTTP 오류 - {e.response.status_code}")
                    return False
                except Exception as e:
                    logger.warning(f"KIS{kis_number}: API 호출 중 오류 - {str(e)}")
                    return False
            
            # 토큰 만료 시간 체크
            try:
                access_token_token_expired = datetime.strptime(
                    access_token_token_expired, "%Y-%m-%d %H:%M:%S"
                )
                diff = access_token_token_expired - datetime.now()
                total_seconds = diff.total_seconds()
                
                # 1시간 이상 남아있어야 유효
                if total_seconds < 3600:
                    logger.debug(f"KIS{kis_number}: 토큰 만료 시간 임박 - {total_seconds/60:.1f}분 남음")
                    return False
                
                logger.debug(f"KIS{kis_number}: 토큰 유효 - {total_seconds/3600:.1f}시간 남음")
                return True
                
            except (ValueError, TypeError) as e:
                logger.error(f"KIS{kis_number}: 토큰 만료 시간 파싱 오류 - {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"KIS{kis_number}: 인증 체크 중 오류 - {traceback.format_exc()}")
            return False

    def create_auth(self, key: str, secret: str):
        """새로운 인증 토큰 생성"""
        data = {"grant_type": "client_credentials", "appkey": key, "appsecret": secret}
        base_url = BaseUrls.base_url.value
        endpoint = "/oauth2/tokenP"
        url = f"{base_url}{endpoint}"
        
        max_retries = 3
        base_delay = 1
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"KIS{self.kis_number}: 토큰 생성 시도 {attempt + 1}/{max_retries}")
                
                response = self.session.post(url, json=data, timeout=30)
                
                if response.status_code != 200:
                    raise httpx.HTTPStatusError(f"HTTP {response.status_code}", request=None, response=response)
                
                response_data = response.json()
                
                if "access_token" in response_data.keys() or response_data.get("rt_cd") == "0":
                    logger.info(f"KIS{self.kis_number}: 토큰 생성 성공")
                    return response_data["access_token"], response_data["access_token_token_expired"]
                else:
                    error_msg = response_data.get("msg1", "알 수 없는 오류")
                    raise Exception(f"토큰 생성 실패: {error_msg}")
                    
            except httpx.TimeoutException:
                logger.warning(f"KIS{self.kis_number}: 토큰 생성 타임아웃 (시도 {attempt + 1})")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                raise Exception("토큰 생성 타임아웃")
                
            except httpx.HTTPStatusError as e:
                logger.warning(f"KIS{self.kis_number}: 토큰 생성 HTTP 오류 - {e.response.status_code}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                raise Exception(f"토큰 생성 HTTP 오류: {e.response.status_code}")
                
            except Exception as e:
                logger.error(f"KIS{self.kis_number}: 토큰 생성 중 오류 - {str(e)}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                raise e
        
        raise Exception("토큰 생성 최대 재시도 횟수 초과")

    def auth(self):
        auth_id = f"KIS{self.kis_number}"
        auth = db.get_auth(auth_id)
        if not self.check_auth(auth, self.key, self.secret, self.kis_number):
            auth = self.create_auth(self.key, self.secret)
            db.set_auth(auth_id, auth[0], auth[1])
        else:
            self.is_auth = True
        access_token = auth[0]
        self.base_headers = BaseHeaders(
            authorization=f"Bearer {access_token}",
            appkey=self.key,
            appsecret=self.secret,
            custtype="P",
        ).dict()
        return auth

    def create_order(
        self,
        exchange: Literal["KRX", "NASDAQ", "NYSE", "AMEX"],
        ticker: str,
        order_type: Literal["limit", "market"],
        side: Literal["buy", "sell"],
        amount: int,
        price: int = 0,
        mintick=0.01,
    ):
        """개선된 주문 생성 메서드 (재시도 로직 강화)"""
        max_retries = 5
        base_delay = 1
        last_exception = None
        
        logger.info(f"KIS{self.kis_number}: {exchange} {ticker} {side} {amount} 주문 시도")
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"KIS{self.kis_number}: 주문 시도 {attempt + 1}/{max_retries}")
                
                endpoint = (
                    Endpoints.korea_order.value
                    if exchange == "KRX"
                    else Endpoints.usa_order.value
                )
                body = self.base_order_body.dict()
                headers = copy.deepcopy(self.base_headers)
                price = str(price)

                amount = str(int(amount))

                if exchange == "KRX":
                    if self.base_url == BaseUrls.base_url:
                        headers |= (
                            KoreaBuyOrderHeaders(**headers)
                            if side == "buy"
                            else KoreaSellOrderHeaders(**headers)
                        )
                    elif self.base_url == BaseUrls.paper_base_url:
                        headers |= (
                            KoreaPaperBuyOrderHeaders(**headers)
                            if side == "buy"
                            else KoreaPaperSellOrderHeaders(**headers)
                        )

                    if order_type == "market":
                        body |= KoreaMarketOrderBody(**body, PDNO=ticker, ORD_QTY=amount)
                    elif order_type == "limit":
                        body |= KoreaOrderBody(
                            **body,
                            PDNO=ticker,
                            ORD_DVSN=KoreaOrderType.limit,
                            ORD_QTY=amount,
                            ORD_UNPR=price,
                        )
                elif exchange in ("NASDAQ", "NYSE", "AMEX"):
                    exchange_code = self.order_exchange_code.get(exchange)
                    current_price = self.fetch_current_price(exchange, ticker)
                    price = (
                        current_price + mintick * 50
                        if side == "buy"
                        else current_price - mintick * 50
                    )
                    if price < 1:
                        price = 1.0
                    price = float("{:.2f}".format(price))
                    if self.base_url == BaseUrls.base_url:
                        headers |= (
                            UsaBuyOrderHeaders(**headers)
                            if side == "buy"
                            else UsaSellOrderHeaders(**headers)
                        )
                    elif self.base_url == BaseUrls.paper_base_url:
                        headers |= (
                            UsaPaperBuyOrderHeaders(**headers)
                            if side == "buy"
                            else UsaPaperSellOrderHeaders(**headers)
                        )

                    if order_type == "market":
                        body |= UsaOrderBody(
                            **body,
                            PDNO=ticker,
                            ORD_DVSN=UsaOrderType.limit.value,
                            ORD_QTY=amount,
                            OVRS_ORD_UNPR=price,
                            OVRS_EXCG_CD=exchange_code,
                        )
                    elif order_type == "limit":
                        body |= UsaOrderBody(
                            **body,
                            PDNO=ticker,
                            ORD_DVSN=UsaOrderType.limit.value,
                            ORD_QTY=amount,
                            OVRS_ORD_UNPR=price,
                            OVRS_EXCG_CD=exchange_code,
                        )
                        
                result = self.post(endpoint, body, headers)
                
                # 성공 응답 체크
                if result.get("rt_cd") == "0":
                    logger.info(f"KIS{self.kis_number}: 주문 성공 - {result.get('msg1', '')}")
                    return result
                else:
                    # API 오류 응답 처리
                    error_msg = result.get("msg1", "알 수 없는 오류")
                    raise Exception(f"주문 실패: {error_msg}")
                    
            except httpx.TimeoutException:
                logger.warning(f"KIS{self.kis_number}: 주문 타임아웃 (시도 {attempt + 1})")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                raise Exception("네트워크 타임아웃")
                
            except httpx.HTTPStatusError as e:
                logger.warning(f"KIS{self.kis_number}: 주문 HTTP 오류 - {e.response.status_code}")
                if e.response.status_code == 429:  # Rate limit
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                        continue
                raise Exception(f"HTTP 오류: {e.response.status_code}")
                
            except Exception as e:
                last_exception = e
                error_msg = str(e)
                
                # 특정 오류에 대한 재시도 로직
                if any(keyword in error_msg.lower() for keyword in ["internal error", "overloaded", "server error"]):
                    logger.warning(f"KIS{self.kis_number}: 서버 오류로 재시도 (시도 {attempt + 1}) - {error_msg}")
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                        continue
                
                # 재시도 불가능한 오류들
                if any(keyword in error_msg.lower() for keyword in 
                       ["invalid", "unauthorized", "forbidden", "not found", "비밀번호"]):
                    logger.error(f"KIS{self.kis_number}: 재시도 불가 오류 - {error_msg}")
                    raise last_exception
                
                logger.warning(f"KIS{self.kis_number}: 주문 오류 (시도 {attempt + 1}) - {error_msg}")
                if attempt == max_retries - 1:
                    raise last_exception
                    
        raise Exception("최대 재시도 횟수 초과") 

    def create_market_buy_order(
        self,
        exchange: Literal["KRX", "NASDAQ", "NYSE", "AMEX"],
        ticker: str,
        amount: int,
        price: int = 0,
    ):
        if exchange == "KRX":
            return self.create_order(exchange, ticker, "market", "buy", amount)
        elif exchange == "usa":
            return self.create_order(exchange, ticker, "market", "buy", amount, price)

    def create_market_sell_order(
        self,
        exchange: Literal["KRX", "NASDAQ", "NYSE", "AMEX"],
        ticker: str,
        amount: int,
        price: int = 0,
    ):
        if exchange == "KRX":
            return self.create_order(exchange, ticker, "market", "sell", amount)
        elif exchange == "usa":
            return self.create_order(exchange, ticker, "market", "buy", amount, price)

    def create_korea_market_buy_order(self, ticker: str, amount: int):
        return self.create_market_buy_order("KRX", ticker, amount)

    def create_korea_market_sell_order(self, ticker: str, amount: int):
        return self.create_market_sell_order("KRX", ticker, amount)

    def create_usa_market_buy_order(self, ticker: str, amount: int, price: int):
        return self.create_market_buy_order("usa", ticker, amount, price)

    def fetch_ticker(
        self, exchange: Literal["KRX", "NASDAQ", "NYSE", "AMEX"], ticker: str
    ):
        if exchange == "KRX":
            endpoint = Endpoints.korea_ticker.value
            headers = KoreaTickerHeaders(**self.base_headers).dict()
            query = KoreaTickerQuery(FID_INPUT_ISCD=ticker).dict()
        elif exchange in ("NASDAQ", "NYSE", "AMEX"):
            exchange_code = self.query_exchange_code.get(exchange)
            endpoint = Endpoints.usa_ticker.value
            headers = UsaTickerHeaders(**self.base_headers).dict()
            query = UsaTickerQuery(EXCD=exchange_code, SYMB=ticker).dict()
        ticker = self.get(endpoint, query, headers)
        return ticker.get("output")

    def fetch_current_price(self, exchange, ticker: str):
        try:
            if exchange == "KRX":
                return float(self.fetch_ticker(exchange, ticker)["stck_prpr"])
            elif exchange in ("NASDAQ", "NYSE", "AMEX"):
                return float(self.fetch_ticker(exchange, ticker)["last"])

        except KeyError:
            print(traceback.format_exc())
            return None

    def open_json(self, path):
        with open(path, "r") as f:
            return json.load(f)

    def write_json(self, path, data):
        with open(path, "w") as f:
            json.dump(data, f)


if __name__ == "__main__":
    pass
