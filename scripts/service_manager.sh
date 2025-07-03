#!/bin/bash

# POA 서비스 관리 스크립트
# 사용법: ./service_manager.sh [명령어] [옵션들]

LOG_FILE="/root/logs/service_manager.log"

# 로그 함수
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# 디렉토리 생성
mkdir -p "/root/logs"

# 서비스 상태 확인
check_services() {
    echo "=== 서비스 상태 확인 ==="
    
    echo "PM2 프로세스:"
    if command -v pm2 >/dev/null 2>&1; then
        pm2 list
        echo ""
        echo "PM2 프로세스 상태:"
        pm2 describe POA 2>/dev/null || echo "  POA 프로세스가 실행 중이 아님"
    else
        echo "  PM2가 설치되어 있지 않음"
    fi
    
    echo ""
    echo "PocketBase 서비스:"
    if systemctl is-active --quiet pocketbase; then
        echo "  ✓ PocketBase 실행 중"
        systemctl status pocketbase --no-pager -l
    else
        echo "  ✗ PocketBase 실행 중이 아님"
    fi
    
    echo ""
    echo "시간 동기화 서비스:"
    if systemctl is-active --quiet ntpd-sync.timer; then
        echo "  ✓ NTPD 동기화 타이머 실행 중"
    else
        echo "  ✗ NTPD 동기화 타이머 실행 중이 아님"
    fi
    
    echo ""
    echo "시스템 리소스:"
    echo "  CPU 사용률: $(top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}')%"
    echo "  메모리 사용률: $(free | grep Mem | awk '{printf \"%.1f%%\", $3/$2 * 100.0}')"
    echo "  디스크 사용률: $(df -h / | awk 'NR==2{printf \"%s\", $5}')"
    
    echo ""
    echo "네트워크 연결:"
    echo "  포트 80: $(netstat -tlnp | grep ':80 ' | wc -l)개 연결"
    echo "  포트 8090: $(netstat -tlnp | grep ':8090 ' | wc -l)개 연결"
}

# 로그 확인
check_logs() {
    echo "=== 최근 로그 확인 ==="
    
    echo "PM2 로그:"
    if command -v pm2 >/dev/null 2>&1; then
        pm2 logs POA --lines 10 2>/dev/null || echo "  POA 로그를 찾을 수 없음"
    else
        echo "  PM2가 설치되어 있지 않음"
    fi
    
    echo ""
    echo "PocketBase 로그:"
    if systemctl is-active --quiet pocketbase; then
        journalctl -u pocketbase --lines 10 --no-pager
    else
        echo "  PocketBase 서비스가 실행 중이 아님"
    fi
    
    echo ""
    echo "시스템 로그 (오류만):"
    journalctl --since "1 hour ago" --priority=3 --no-pager | tail -10
}

# 서비스 재시작
restart_all() {
    log_message "=== 모든 서비스 재시작 시작 ==="
    
    # PM2 재시작
    if command -v pm2 >/dev/null 2>&1; then
        log_message "PM2 재시작 중..."
        pm2 restart POA
        if [ $? -eq 0 ]; then
            log_message "PM2 재시작 성공"
        else
            log_message "PM2 재시작 실패"
        fi
    else
        log_message "PM2가 설치되어 있지 않음"
    fi
    
    # PocketBase 재시작
    log_message "PocketBase 재시작 중..."
    systemctl restart pocketbase
    if [ $? -eq 0 ]; then
        log_message "PocketBase 재시작 성공"
    else
        log_message "PocketBase 재시작 실패"
    fi
    
    # 시간 동기화 서비스 재시작
    log_message "시간 동기화 서비스 재시작 중..."
    systemctl restart ntpd-sync.timer
    if [ $? -eq 0 ]; then
        log_message "시간 동기화 서비스 재시작 성공"
    else
        log_message "시간 동기화 서비스 재시작 실패"
    fi
    
    # 서비스 상태 확인
    sleep 5
    log_message "서비스 상태 확인 중..."
    
    if command -v pm2 >/dev/null 2>&1; then
        pm2_status=$(pm2 describe POA 2>/dev/null | grep -c "online")
        if [ "$pm2_status" -gt 0 ]; then
            log_message "✓ POA 서비스 정상 실행 중"
        else
            log_message "✗ POA 서비스 실행 실패"
        fi
    fi
    
    if systemctl is-active --quiet pocketbase; then
        log_message "✓ PocketBase 서비스 정상 실행 중"
    else
        log_message "✗ PocketBase 서비스 실행 실패"
    fi
    
    log_message "=== 서비스 재시작 완료 ==="
}

# 서비스 중지
stop_all() {
    log_message "=== 모든 서비스 중지 시작 ==="
    
    # PM2 중지
    if command -v pm2 >/dev/null 2>&1; then
        log_message "PM2 중지 중..."
        pm2 stop POA
        pm2 delete POA
        log_message "PM2 중지 완료"
    fi
    
    # PocketBase 중지
    log_message "PocketBase 중지 중..."
    systemctl stop pocketbase
    log_message "PocketBase 중지 완료"
    
    log_message "=== 서비스 중지 완료 ==="
}

# 백업 및 업데이트
backup_and_update() {
    log_message "=== 백업 및 업데이트 시작 ==="
    
    # 백업 디렉토리 생성
    backup_dir="/root/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    # 현재 설정 백업
    log_message "설정 백업 중..."
    if [ -f "/root/.env" ]; then
        cp "/root/.env" "$backup_dir/"
        log_message "환경 변수 백업 완료"
    fi
    
    if [ -d "/root/db/pb_data" ]; then
        cp -r "/root/db/pb_data" "$backup_dir/"
        log_message "PocketBase 데이터 백업 완료"
    fi
    
    # 코드 업데이트
    log_message "코드 업데이트 중..."
    cd /root/POA
    git stash
    git pull --rebase
    if [ $? -eq 0 ]; then
        log_message "코드 업데이트 성공"
    else
        log_message "코드 업데이트 실패"
        exit 1
    fi
    
    # 의존성 업데이트
    log_message "의존성 업데이트 중..."
    /root/POA/.venv/bin/python3.10 -m pip install -r /root/POA/requirements.txt
    if [ $? -eq 0 ]; then
        log_message "의존성 업데이트 성공"
    else
        log_message "의존성 업데이트 실패"
    fi
    
    # 서비스 재시작
    restart_all
    
    log_message "=== 백업 및 업데이트 완료 ==="
}

# 헬스체크
health_check() {
    echo "=== 헬스체크 실행 ==="
    
    health_status=0
    
    # PM2 상태 확인
    if command -v pm2 >/dev/null 2>&1; then
        pm2_status=$(pm2 describe POA 2>/dev/null | grep -c "online")
        if [ "$pm2_status" -gt 0 ]; then
            echo "✓ POA 서비스: 정상"
        else
            echo "✗ POA 서비스: 오류"
            health_status=1
        fi
    else
        echo "✗ PM2: 설치되지 않음"
        health_status=1
    fi
    
    # PocketBase 상태 확인
    if systemctl is-active --quiet pocketbase; then
        echo "✓ PocketBase: 정상"
    else
        echo "✗ PocketBase: 오류"
        health_status=1
    fi
    
    # API 엔드포인트 확인
    if curl -s http://localhost:80/hi | grep -q "hi"; then
        echo "✓ API 엔드포인트: 정상"
    else
        echo "✗ API 엔드포인트: 오류"
        health_status=1
    fi
    
    # 디스크 사용량 확인
    disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 80 ]; then
        echo "⚠ 디스크 사용량: ${disk_usage}% (경고)"
        health_status=1
    else
        echo "✓ 디스크 사용량: ${disk_usage}% (정상)"
    fi
    
    # 메모리 사용량 확인
    memory_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')
    if [ "$memory_usage" -gt 80 ]; then
        echo "⚠ 메모리 사용량: ${memory_usage}% (경고)"
        health_status=1
    else
        echo "✓ 메모리 사용량: ${memory_usage}% (정상)"
    fi
    
    if [ $health_status -eq 0 ]; then
        echo "=== 전체 시스템 상태: 정상 ==="
        log_message "헬스체크 통과"
    else
        echo "=== 전체 시스템 상태: 문제 있음 ==="
        log_message "헬스체크 실패"
    fi
    
    return $health_status
}

# 도움말 표시
show_help() {
    echo "POA 서비스 관리 스크립트"
    echo ""
    echo "사용법:"
    echo "  $0 status      - 서비스 상태 확인"
    echo "  $0 logs        - 로그 확인"
    echo "  $0 restart     - 서비스 재시작"
    echo "  $0 stop        - 서비스 중지"
    echo "  $0 update      - 백업 및 업데이트"
    echo "  $0 health      - 헬스체크"
    echo "  $0 help        - 도움말"
}

# 메인 로직
case "$1" in
    status)
        check_services
        ;;
    logs)
        check_logs
        ;;
    restart)
        restart_all
        ;;
    stop)
        stop_all
        ;;
    update)
        backup_and_update
        ;;
    health)
        health_check
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
