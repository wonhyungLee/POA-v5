#!/bin/bash

# POA 환경 변수 관리 스크립트
# 사용법: ./env_manager.sh [명령어] [옵션들]

ENV_FILE="/root/.env"
BACKUP_DIR="/root/backups"
LOG_FILE="/root/logs/env_manager.log"

# 로그 함수
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# 디렉토리 생성
mkdir -p "$BACKUP_DIR"
mkdir -p "/root/logs"

# 환경 변수 백업
backup_env() {
    if [ -f "$ENV_FILE" ]; then
        local backup_file="$BACKUP_DIR/.env.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$backup_file"
        log_message "환경 변수 백업 완료: $backup_file"
    else
        log_message "환경 변수 파일이 존재하지 않음: $ENV_FILE"
    fi
}

# KIS 계정 추가
add_kis_account() {
    local kis_num=$1
    local key=$2
    local secret=$3
    local account_number=$4
    local account_code=$5
    
    if [ -z "$kis_num" ] || [ -z "$key" ] || [ -z "$secret" ] || [ -z "$account_number" ] || [ -z "$account_code" ]; then
        echo "사용법: add_kis kis_number key secret account_number account_code"
        exit 1
    fi
    
    # KIS 번호 범위 체크
    if [ "$kis_num" -lt 1 ] || [ "$kis_num" -gt 50 ]; then
        echo "오류: KIS 번호는 1-50 범위여야 합니다."
        exit 1
    fi
    
    backup_env
    
    # 기존 설정 제거 (있다면)
    if [ -f "$ENV_FILE" ]; then
        sed -i "/^KIS${kis_num}_/d" "$ENV_FILE"
    fi
    
    # 새 설정 추가
    echo "KIS${kis_num}_KEY=\"$key\"" >> "$ENV_FILE"
    echo "KIS${kis_num}_SECRET=\"$secret\"" >> "$ENV_FILE"
    echo "KIS${kis_num}_ACCOUNT_NUMBER=\"$account_number\"" >> "$ENV_FILE"
    echo "KIS${kis_num}_ACCOUNT_CODE=\"$account_code\"" >> "$ENV_FILE"
    
    log_message "KIS${kis_num} 계정 추가 완료"
}

# 환경 변수 업데이트
update_env_var() {
    local var_name=$1
    local var_value=$2
    
    if [ -z "$var_name" ] || [ -z "$var_value" ]; then
        echo "사용법: update variable_name value"
        exit 1
    fi
    
    backup_env
    
    if [ -f "$ENV_FILE" ]; then
        if grep -q "^${var_name}=" "$ENV_FILE"; then
            sed -i "s/^${var_name}=.*/${var_name}=\"${var_value}\"/" "$ENV_FILE"
            log_message "${var_name} 업데이트 완료"
        else
            echo "${var_name}=\"${var_value}\"" >> "$ENV_FILE"
            log_message "${var_name} 추가 완료"
        fi
    else
        echo "${var_name}=\"${var_value}\"" > "$ENV_FILE"
        log_message "${var_name} 추가 완료 (새 파일 생성)"
    fi
}

# KIS 계정 삭제
remove_kis_account() {
    local kis_num=$1
    
    if [ -z "$kis_num" ]; then
        echo "사용법: remove_kis kis_number"
        exit 1
    fi
    
    backup_env
    
    if [ -f "$ENV_FILE" ]; then
        sed -i "/^KIS${kis_num}_/d" "$ENV_FILE"
        log_message "KIS${kis_num} 계정 삭제 완료"
    else
        log_message "환경 변수 파일이 존재하지 않음"
    fi
}

# 서비스 재시작
restart_services() {
    log_message "서비스 재시작 시작"
    
    # PM2 재시작
    if command -v pm2 >/dev/null 2>&1; then
        pm2 restart POA
        log_message "PM2 재시작 완료"
    else
        log_message "PM2가 설치되어 있지 않음"
    fi
    
    # PocketBase 재시작
    if systemctl is-active --quiet pocketbase; then
        systemctl restart pocketbase
        log_message "PocketBase 재시작 완료"
    else
        log_message "PocketBase 서비스가 비활성화되어 있음"
    fi
    
    log_message "서비스 재시작 완료"
}

# 환경 변수 목록 표시
list_env_vars() {
    echo "=== 현재 환경 변수 설정 ==="
    
    if [ -f "$ENV_FILE" ]; then
        echo "기본 설정:"
        grep -E "^(PASSWORD|PORT|DISCORD_WEBHOOK_URL|WHITELIST|DB_)" "$ENV_FILE" | sed 's/=.*/=***/' || echo "  없음"
        
        echo ""
        echo "거래소 설정:"
        grep -E "^(BINANCE|UPBIT|BYBIT|BITGET|OKX)_" "$ENV_FILE" | sed 's/=.*/=***/' || echo "  없음"
        
        echo ""
        echo "KIS 계정 설정:"
        grep -E "^KIS[0-9]+_" "$ENV_FILE" | sed 's/=.*/=***/' | sort -V || echo "  없음"
    else
        echo "환경 변수 파일이 존재하지 않음: $ENV_FILE"
    fi
}

# 환경 변수 검증
validate_env() {
    if [ -f "$ENV_FILE" ]; then
        echo "환경 변수 검증 중..."
        cd /root/POA
        python3 -c "
from exchange.utils.validation import validate_environment, print_environment_summary
is_valid, errors = validate_environment()
print_environment_summary()
if not is_valid:
    print('검증 실패:')
    for error in errors:
        print(f'  - {error}')
    exit(1)
else:
    print('검증 성공!')
"
    else
        echo "환경 변수 파일이 존재하지 않음: $ENV_FILE"
        exit 1
    fi
}

# 도움말 표시
show_help() {
    echo "POA 환경 변수 관리 스크립트"
    echo ""
    echo "사용법:"
    echo "  $0 add_kis kis_number key secret account_number account_code"
    echo "  $0 update variable_name value"
    echo "  $0 remove_kis kis_number"
    echo "  $0 restart"
    echo "  $0 list"
    echo "  $0 validate"
    echo "  $0 help"
    echo ""
    echo "예시:"
    echo "  $0 add_kis 5 \"your_key\" \"your_secret\" \"account_number\" \"account_code\""
    echo "  $0 update \"PASSWORD\" \"new_password\""
    echo "  $0 remove_kis 5"
    echo "  $0 restart"
}

# 메인 로직
case "$1" in
    add_kis)
        add_kis_account "$2" "$3" "$4" "$5" "$6"
        ;;
    update)
        update_env_var "$2" "$3"
        ;;
    remove_kis)
        remove_kis_account "$2"
        ;;
    restart)
        restart_services
        ;;
    list)
        list_env_vars
        ;;
    validate)
        validate_env
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "오류: 잘못된 명령어입니다."
        echo ""
        show_help
        exit 1
        ;;
esac
