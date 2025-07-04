from fastapi.exception_handlers import (
    request_validation_exception_handler,
)
from pprint import pprint
from fastapi import FastAPI, Request, status, BackgroundTasks
from fastapi.responses import ORJSONResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
import httpx
from datetime import datetime
from exchange.stock.kis import KoreaInvestment
from exchange.model import MarketOrder, PriceRequest, HedgeData, OrderRequest
from exchange.utils.logging_config import (
    setup_logging,
    log_message,
    log_order_message,
    log_order_error_message,
    log_error_message,
    log_system_message,
    log_config_message,
    poa_logger
)
import traceback
from exchange import get_exchange, db, settings, get_bot, pocket
from exchange.utility import log_alert_message, print_alert_message, log_hedge_message, log_validation_error_message
from exchange.utils.validation import validate_environment, print_environment_summary
from exchange.utils.config_manager import config_manager, KISAccountConfig, EnvVarConfig, ExchangeConfig
from exchange.utils.memory_monitor import start_system_monitoring, stop_system_monitoring, get_system_status, get_system_history, get_system_summary, force_gc
import ipaddress
import os
import sys
from devtools import debug

VERSION = "0.1.8"
app = FastAPI(default_response_class=ORJSONResponse)


def get_error(e):
    tb = traceback.extract_tb(e.__traceback__)
    target_folder = os.path.abspath(os.path.dirname(tb[0].filename))
    error_msg = []

    for tb_info in tb:
        # if target_folder in tb_info.filename:
        error_msg.append(
            f"File {tb_info.filename}, line {tb_info.lineno}, in {tb_info.name}"
        )
        error_msg.append(f"  {tb_info.line}")

    error_msg.append(str(e))

    return error_msg


@app.on_event("startup")
async def startup():
    # 로깅 시스템 초기화
    setup_logging()
    log_system_message("POA 시스템 시작")
    
    # 시스템 모니터링 시작
    start_system_monitoring()
    
    # 환경 변수 검증
    is_valid, errors = validate_environment()
    if not is_valid:
        log_error_message("환경 변수 검증 실패. 서버를 종료합니다.", "STARTUP")
        for error in errors:
            log_error_message(f"  - {error}", "STARTUP")
        sys.exit(1)
    
    # 환경 변수 요약 출력
    print_environment_summary()
    
    log_system_message(f"POABOT 실행 완료! - 버전:{VERSION}")


@app.on_event("shutdown")
async def shutdown():
    log_system_message("POA 시스템 종료")
    
    # 시스템 모니터링 중지
    stop_system_monitoring()
    
    # 데이터베이스 연결 종료
    db.close()


whitelist = [
    "52.89.214.238",
    "34.212.75.30",
    "54.218.53.128",
    "52.32.178.7",
    "127.0.0.1",
]
whitelist = whitelist + settings.WHITELIST


# @app.middleware("http")
# async def add_process_time_header(request: Request, call_next):
#     start_time = time.perf_counter()
#     response = await call_next(request)
#     process_time = time.perf_counter() - start_time
#     response.headers["X-Process-Time"] = str(process_time)
#     return response


@app.middleware("http")
async def whitelist_middleware(request: Request, call_next):
    try:
        if (
            request.client.host not in whitelist
            and not ipaddress.ip_address(request.client.host).is_private
        ):
            msg = f"{request.client.host}는 안됩니다"
            print(msg)
            return ORJSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=f"{request.client.host}는 허용되지 않습니다",
            )
    except:
        log_error_message(traceback.format_exc(), "미들웨어 에러")
    else:
        response = await call_next(request)
        return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    msgs = [
        f"[에러{index+1}] " + f"{error.get('msg')} \n{error.get('loc')}"
        for index, error in enumerate(exc.errors())
    ]
    message = "[Error]\n"
    for msg in msgs:
        message = message + msg + "\n"

    log_validation_error_message(f"{message}\n {exc.body}")
    return await request_validation_exception_handler(request, exc)


@app.get("/ip")
async def get_ip():
    data = httpx.get("https://ipv4.jsonip.com").json()["ip"]
    log_message(data)


@app.get("/hi")
async def welcome():
    return "hi!!"


@app.post("/price")
async def price(price_req: PriceRequest, background_tasks: BackgroundTasks):
    exchange = get_exchange(price_req.exchange)
    price = exchange.dict()[price_req.exchange].fetch_price(
        price_req.base, price_req.quote
    )
    return price


def log(exchange_name, result, order_info):
    log_order_message(exchange_name, result, order_info)
    print_alert_message(order_info)


def log_error(error_message, order_info):
    log_order_error_message(error_message, order_info)
    log_alert_message(order_info, "실패")


@app.post("/order")
@app.post("/")
async def order(request: Request, background_tasks: BackgroundTasks):
    order_data = await request.json()
    
    # Manually fix the price if it's a TradingView placeholder
    price = order_data.get("price")
    if isinstance(price, str) and price.startswith('{') and price.endswith('}'):
        order_data["price"] = None

    try:
        order_info = MarketOrder(**order_data)
    except Exception as e:
        log_validation_error_message(f"[Validation Error] {e}\n {order_data}")
        # Re-raise the exception to be handled by FastAPI's error handling
        raise

    order_result = None
    try:
        exchange_name = order_info.exchange
        bot = get_bot(exchange_name, order_info.kis_number)
        bot.init_info(order_info)

        if bot.order_info.is_crypto:
            if bot.order_info.is_entry:
                order_result = bot.market_entry(bot.order_info)
            elif bot.order_info.is_close:
                order_result = bot.market_close(bot.order_info)
            elif bot.order_info.is_buy:
                order_result = bot.market_buy(bot.order_info)
            elif bot.order_info.is_sell:
                order_result = bot.market_sell(bot.order_info)
            background_tasks.add_task(log, exchange_name, order_result, order_info)
        elif bot.order_info.is_stock:
            order_result = bot.create_order(
                bot.order_info.exchange,
                bot.order_info.base,
                order_info.type.lower(),
                order_info.side.lower(),
                order_info.amount,
            )
            background_tasks.add_task(log, exchange_name, order_result, order_info)

    except TypeError as e:
        error_msg = get_error(e)
        background_tasks.add_task(
            log_order_error_message, "\n".join(error_msg), order_info
        )

    except Exception as e:
        error_msg = get_error(e)
        background_tasks.add_task(log_error, "\n".join(error_msg), order_info)

    else:
        return {"result": "success"}

    finally:
        pass



def get_hedge_records(base):
    records = pocket.get_full_list("kimp", query_params={"filter": f'base = "{base}"'})
    binance_amount = 0.0
    binance_records_id = []
    upbit_amount = 0.0
    upbit_records_id = []
    for record in records:
        if record.exchange == "BINANCE":
            binance_amount += record.amount
            binance_records_id.append(record.id)
        elif record.exchange == "UPBIT":
            upbit_amount += record.amount
            upbit_records_id.append(record.id)

    return {
        "BINANCE": {"amount": binance_amount, "records_id": binance_records_id},
        "UPBIT": {"amount": upbit_amount, "records_id": upbit_records_id},
    }


@app.post("/hedge")
async def hedge(hedge_data: HedgeData, background_tasks: BackgroundTasks):
    exchange_name = hedge_data.exchange.upper()
    bot = get_bot(exchange_name)
    upbit = get_bot("UPBIT")

    base = hedge_data.base
    quote = hedge_data.quote
    amount = hedge_data.amount
    leverage = hedge_data.leverage
    hedge = hedge_data.hedge

    foreign_order_info = OrderRequest(
        exchange=exchange_name,
        base=base,
        quote=quote,
        side="entry/sell",
        type="market",
        amount=amount,
        leverage=leverage,
    )
    bot.init_info(foreign_order_info)
    if hedge == "ON":
        try:
            if amount is None:
                raise Exception("헷지할 수량을 요청하세요")
            binance_order_result = bot.market_entry(foreign_order_info)
            binance_order_amount = binance_order_result["amount"]
            pocket.create(
                "kimp",
                {
                    "exchange": "BINANCE",
                    "base": base,
                    "quote": quote,
                    "amount": binance_order_amount,
                },
            )
            if leverage is None:
                leverage = 1
            try:
                korea_order_info = OrderRequest(
                    exchange="UPBIT",
                    base=base,
                    quote="KRW",
                    side="buy",
                    type="market",
                    amount=binance_order_amount,
                )
                upbit.init_info(korea_order_info)
                upbit_order_result = upbit.market_buy(korea_order_info)
            except Exception as e:
                hedge_records = get_hedge_records(base)
                binance_records_id = hedge_records["BINANCE"]["records_id"]
                binance_amount = hedge_records["BINANCE"]["amount"]
                binance_order_result = bot.market_close(
                    OrderRequest(
                        exchange=exchange_name,
                        base=base,
                        quote=quote,
                        side="close/buy",
                        amount=binance_amount,
                    )
                )
                for binance_record_id in binance_records_id:
                    pocket.delete("kimp", binance_record_id)
                log_message(
                    "[헷지 실패] 업비트에서 에러가 발생하여 바이낸스 포지션을 종료합니다"
                )
            else:
                upbit_order_info = upbit.get_order(upbit_order_result["id"])
                upbit_order_amount = upbit_order_info["filled"]
                pocket.create(
                    "kimp",
                    {
                        "exchange": "UPBIT",
                        "base": base,
                        "quote": "KRW",
                        "amount": upbit_order_amount,
                    },
                )
                log_hedge_message(
                    exchange_name,
                    base,
                    quote,
                    binance_order_amount,
                    upbit_order_amount,
                    hedge,
                )

        except Exception as e:
            # log_message(f"{e}")
            background_tasks.add_task(
                log_error_message, traceback.format_exc(), "헷지 에러"
            )
            return {"result": "error"}
        else:
            return {"result": "success"}


# =============================================================================
# 설정 관리 API 엔드포인트
# =============================================================================

@app.get("/config/status")
async def get_system_status():
    """시스템 상태 조회"""
    try:
        status = config_manager.get_system_status()
        return status
    except Exception as e:
        return {"error": f"시스템 상태 조회 중 오류: {str(e)}"}


@app.get("/config/env")
async def get_current_config():
    """현재 환경 변수 설정 조회 (민감한 정보 마스킹)"""
    try:
        config = config_manager.get_current_config()
        
        # 민감한 정보 마스킹
        masked_config = {}
        for key, value in config.items():
            if any(keyword in key.upper() for keyword in ['KEY', 'SECRET', 'PASSWORD', 'PASSPHRASE']):
                masked_config[key] = '*' * 8 if value else ''
            else:
                masked_config[key] = value
        
        return {
            "status": "success",
            "config": masked_config,
            "total_variables": len(config)
        }
    except Exception as e:
        return {"error": f"설정 조회 중 오류: {str(e)}"}


@app.post("/config/kis/add")
async def add_kis_account(config: KISAccountConfig, background_tasks: BackgroundTasks):
    """KIS 계정 추가"""
    try:
        result = config_manager.add_kis_account(config)
        background_tasks.add_task(
            log_message, f"KIS{config.kis_number} 계정 추가 완료"
        )
        return result
    except Exception as e:
        background_tasks.add_task(
            log_error_message, traceback.format_exc(), "KIS 계정 추가 오류"
        )
        raise e


@app.delete("/config/kis/{kis_number}")
async def remove_kis_account(kis_number: int, background_tasks: BackgroundTasks):
    """KIS 계정 제거"""
    try:
        result = config_manager.remove_kis_account(kis_number)
        background_tasks.add_task(
            log_message, f"KIS{kis_number} 계정 제거 완료"
        )
        return result
    except Exception as e:
        background_tasks.add_task(
            log_error_message, traceback.format_exc(), "KIS 계정 제거 오류"
        )
        raise e


@app.post("/config/exchange")
async def update_exchange_config(config: ExchangeConfig, background_tasks: BackgroundTasks):
    """거래소 설정 업데이트"""
    try:
        result = config_manager.update_exchange_config(config)
        background_tasks.add_task(
            log_message, f"{config.exchange} 거래소 설정 업데이트 완료"
        )
        return result
    except Exception as e:
        background_tasks.add_task(
            log_error_message, traceback.format_exc(), "거래소 설정 업데이트 오류"
        )
        raise e


@app.post("/config/env")
async def update_env_var(config: EnvVarConfig, background_tasks: BackgroundTasks):
    """환경 변수 업데이트"""
    try:
        result = config_manager.update_env_var(config)
        background_tasks.add_task(
            log_message, f"{config.name} 환경 변수 업데이트 완료"
        )
        return result
    except Exception as e:
        background_tasks.add_task(
            log_error_message, traceback.format_exc(), "환경 변수 업데이트 오류"
        )
        raise e


@app.post("/config/restart")
async def restart_services(background_tasks: BackgroundTasks):
    """서비스 재시작"""
    try:
        success = config_manager.restart_services()
        if success:
            background_tasks.add_task(log_message, "서비스 재시작 완료")
            return {"status": "success", "message": "서비스 재시작 완료"}
        else:
            background_tasks.add_task(log_error_message, "서비스 재시작 실패", "서비스 관리")
            return {"status": "error", "message": "서비스 재시작 실패"}
    except Exception as e:
        background_tasks.add_task(
            log_error_message, traceback.format_exc(), "서비스 재시작 오류"
        )
        return {"status": "error", "message": f"서비스 재시작 중 오류: {str(e)}"}


@app.get("/config/validate")
async def validate_configuration():
    """환경 변수 검증"""
    try:
        from exchange.utils.validation import validate_environment, get_kis_account_summary
        
        is_valid, errors = validate_environment()
        kis_summary = get_kis_account_summary()
        
        return {
            "status": "success",
            "valid": is_valid,
            "errors": errors,
            "kis_accounts": kis_summary
        }
    except Exception as e:
        return {"status": "error", "message": f"검증 중 오류: {str(e)}"}


@app.get("/config/backups")
async def list_backups():
    """백업 파일 목록 조회"""
    try:
        backup_dir = "/root/backups"
        if not os.path.exists(backup_dir):
            return {"status": "success", "backups": []}
        
        backups = []
        for filename in os.listdir(backup_dir):
            if filename.startswith('.env.'):
                filepath = os.path.join(backup_dir, filename)
                stat = os.stat(filepath)
                backups.append({
                    "filename": filename,
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        
        # 최신 순으로 정렬
        backups.sort(key=lambda x: x['created'], reverse=True)
        
        return {
            "status": "success",
            "backups": backups,
            "total": len(backups)
        }
    except Exception as e:
        return {"status": "error", "message": f"백업 목록 조회 중 오류: {str(e)}"}


@app.get("/logs/{log_type}")
async def get_logs(log_type: str, lines: int = 100):
    """로그 조회"""
    try:
        valid_types = ["main", "order", "error", "kis", "system", "config"]
        if log_type not in valid_types:
            return {"status": "error", "message": f"유효하지 않은 로그 타입. 사용 가능: {valid_types}"}
        
        recent_logs = poa_logger.get_recent_logs(log_type, lines)
        
        return {
            "status": "success",
            "log_type": log_type,
            "lines": len(recent_logs),
            "logs": recent_logs
        }
    except Exception as e:
        return {"status": "error", "message": f"로그 조회 중 오류: {str(e)}"}


@app.get("/logs/files")
async def get_log_files():
    """로그 파일 목록 조회"""
    try:
        log_files = poa_logger.get_log_files_info()
        return {
            "status": "success",
            "log_files": log_files,
            "total_files": len(log_files)
        }
    except Exception as e:
        return {"status": "error", "message": f"로그 파일 조회 중 오류: {str(e)}"}


@app.post("/logs/cleanup")
async def cleanup_logs(days_to_keep: int = 30, background_tasks: BackgroundTasks = None):
    """오래된 로그 정리"""
    try:
        if days_to_keep < 1:
            return {"status": "error", "message": "보관 기간은 최소 1일 이상이어야 합니다"}
        
        cleaned_files = poa_logger.cleanup_old_logs(days_to_keep)
        
        if background_tasks:
            background_tasks.add_task(
                log_system_message, f"로그 정리 완료: {len(cleaned_files)}개 파일 삭제"
            )
        
        return {
            "status": "success",
            "message": f"{len(cleaned_files)}개 파일 정리 완료",
            "cleaned_files": cleaned_files
        }
    except Exception as e:
        return {"status": "error", "message": f"로그 정리 중 오류: {str(e)}"}


# =============================================================================
# 시스템 모니터링 API 엔드포인트
# =============================================================================

@app.get("/monitor/status")
async def get_system_metrics():
    """현재 시스템 메트릭 조회"""
    try:
        metrics = get_system_status()
        return {
            "status": "success",
            "metrics": metrics
        }
    except Exception as e:
        return {"status": "error", "message": f"메트릭 수집 오류: {str(e)}"}


@app.get("/monitor/history")
async def get_system_metrics_history(hours: int = 24):
    """시스템 메트릭 히스토리 조회"""
    try:
        if hours < 1 or hours > 168:  # 최대 7일
            return {"status": "error", "message": "시간 범위는 1-168시간 사이여야 합니다"}
        
        history = get_system_history(hours)
        return {
            "status": "success",
            "hours": hours,
            "data_points": len(history),
            "history": history
        }
    except Exception as e:
        return {"status": "error", "message": f"히스토리 조회 오류: {str(e)}"}


@app.get("/monitor/summary")
async def get_system_summary_stats():
    """시스템 요약 통계 조회"""
    try:
        summary = get_system_summary()
        return {
            "status": "success",
            "summary": summary
        }
    except Exception as e:
        return {"status": "error", "message": f"요약 통계 조회 오류: {str(e)}"}


@app.post("/monitor/gc")
async def force_garbage_collection(background_tasks: BackgroundTasks):
    """강제 가비지 컴렉션"""
    try:
        result = force_gc()
        
        background_tasks.add_task(
            log_system_message, 
            f"강제 GC 실행: {result.get('collected_objects', 0)}개 객체 정리"
        )
        
        return {
            "status": "success",
            "message": "가비지 컴렉션 완료",
            "result": result
        }
    except Exception as e:
        background_tasks.add_task(
            log_error_message, f"가비지 컴렉션 오류: {str(e)}", "MONITOR"
        )
        return {"status": "error", "message": f"가비지 컴렉션 오류: {str(e)}"}


@app.get("/monitor/health")
async def system_health_check():
    """시스템 헬스체크"""
    try:
        metrics = get_system_status()
        
        # 헬스 상태 판단
        health_status = "healthy"
        issues = []
        
        if metrics.get("memory_percent", 0) > 85:
            health_status = "warning"
            issues.append(f"메모리 사용량 높음: {metrics.get('memory_percent', 0):.1f}%")
        
        if metrics.get("cpu_percent", 0) > 80:
            health_status = "warning"
            issues.append(f"CPU 사용량 높음: {metrics.get('cpu_percent', 0):.1f}%")
        
        if metrics.get("disk_percent", 0) > 85:
            health_status = "warning"
            issues.append(f"디스크 사용량 높음: {metrics.get('disk_percent', 0):.1f}%")
        
        if metrics.get("memory_percent", 0) > 95 or metrics.get("cpu_percent", 0) > 95:
            health_status = "critical"
        
        return {
            "status": "success",
            "health_status": health_status,
            "issues": issues,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error", 
            "health_status": "error",
            "message": f"헬스체크 오류: {str(e)}"
        }

    elif hedge == "OFF":
        try:
            records = pocket.get_full_list(
                "kimp", query_params={"filter": f'base = "{base}"'}
            )
            binance_amount = 0.0
            binance_records_id = []
            upbit_amount = 0.0
            upbit_records_id = []
            for record in records:
                if record.exchange == "BINANCE":
                    binance_amount += record.amount
                    binance_records_id.append(record.id)
                elif record.exchange == "UPBIT":
                    upbit_amount += record.amount
                    upbit_records_id.append(record.id)

            if binance_amount > 0 and upbit_amount > 0:
                # 바이낸스
                order_info = OrderRequest(
                    exchange="BINANCE",
                    base=base,
                    quote=quote,
                    side="close/buy",
                    amount=binance_amount,
                )
                binance_order_result = bot.market_close(order_info)
                for binance_record_id in binance_records_id:
                    pocket.delete("kimp", binance_record_id)
                # 업비트
                order_info = OrderRequest(
                    exchange="UPBIT",
                    base=base,
                    quote="KRW",
                    side="sell",
                    amount=upbit_amount,
                )
                upbit_order_result = upbit.market_sell(order_info)
                for upbit_record_id in upbit_records_id:
                    pocket.delete("kimp", upbit_record_id)

                log_hedge_message(
                    exchange_name, base, quote, binance_amount, upbit_amount, hedge
                )
            elif binance_amount == 0 and upbit_amount == 0:
                log_message(f"{exchange_name}, UPBIT에 종료할 수량이 없습니다")
            elif binance_amount == 0:
                log_message(f"{exchange_name}에 종료할 수량이 없습니다")
            elif upbit_amount == 0:
                log_message("UPBIT에 종료할 수량이 없습니다")
        except Exception as e:
            background_tasks.add_task(
                log_error_message, traceback.format_exc(), "헷지종료 에러"
            )
            return {"result": "error"}
        else:
            return {"result": "success"}
