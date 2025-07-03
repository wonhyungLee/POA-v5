#!/bin/bash

# POA 시스템 초기 설정 스크립트
# 사용법: ./initial_setup.sh

echo "=============================================="
echo "POA 시스템 초기 설정을 시작합니다"
echo "=============================================="

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 필수 디렉토리 생성
create_directories() {
    log_info "필수 디렉토리 생성 중..."
    
    directories=(
        "/root/backups"
        "/root/logs"
        "/root/scripts"
        "/root/db"
        "/root/config"
    )
    
    for dir in "${directories[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            log_success "디렉토리 생성: $dir"
        else
            log_info "디렉토리 존재: $dir"
        fi
    done
}

# 환경 변수 파일 설정
setup_env_file() {
    log_info "환경 변수 파일 설정 중..."
    
    if [ ! -f "/root/.env" ]; then
        if [ -f "/root/POA/templates/.env.template" ]; then
            cp "/root/POA/templates/.env.template" "/root/.env"
            log_success "환경 변수 템플릿 복사 완료"
            log_warning "편집 필요: nano /root/.env"
        else
            log_error "환경 변수 템플릿을 찾을 수 없습니다"
            return 1
        fi
    else
        log_info "환경 변수 파일이 이미 존재합니다: /root/.env"
    fi
}

# 스크립트 권한 설정
setup_script_permissions() {
    log_info "스크립트 권한 설정 중..."
    
    scripts=(
        "/root/POA/scripts/env_manager.sh"
        "/root/POA/scripts/service_manager.sh"
        "/root/.bash_functions"
    )
    
    for script in "${scripts[@]}"; do
        if [ -f "$script" ]; then
            chmod +x "$script"
            log_success "권한 설정 완료: $script"
        else
            log_warning "스크립트 파일을 찾을 수 없습니다: $script"
        fi
    done
}

# 시스템 서비스 확인
check_system_services() {
    log_info "시스템 서비스 상태 확인 중..."
    
    # PM2 확인
    if command -v pm2 >/dev/null 2>&1; then
        log_success "PM2 설치 확인됨"
    else
        log_error "PM2가 설치되지 않았습니다"
        log_info "PM2 설치: npm install pm2@latest -g"
    fi
    
    # Python 가상환경 확인
    if [ -d "/root/POA/.venv" ]; then
        log_success "Python 가상환경 확인됨"
    else
        log_error "Python 가상환경이 없습니다"
        log_info "가상환경 생성: python3.10 -m venv /root/POA/.venv"
    fi
    
    # PocketBase 확인
    if [ -f "/root/db/pocketbase" ]; then
        log_success "PocketBase 확인됨"
    else
        log_error "PocketBase가 설치되지 않았습니다"
    fi
}

# 파이썬 의존성 확인
check_python_dependencies() {
    log_info "Python 의존성 확인 중..."
    
    if [ -f "/root/POA/requirements.txt" ]; then
        log_success "requirements.txt 파일 확인됨"
        
        if [ -f "/root/POA/.venv/bin/pip" ]; then
            log_info "의존성 설치 확인 중..."
            missing_packages=$(/root/POA/.venv/bin/pip freeze -r /root/POA/requirements.txt 2>&1 | grep -c "not installed")
            
            if [ "$missing_packages" -gt 0 ]; then
                log_warning "누락된 패키지가 있습니다"
                log_info "의존성 설치: /root/POA/.venv/bin/pip install -r /root/POA/requirements.txt"
            else
                log_success "모든 의존성이 설치되어 있습니다"
            fi
        else
            log_error "Python 가상환경이 활성화되지 않았습니다"
        fi
    else
        log_error "requirements.txt 파일을 찾을 수 없습니다"
    fi
}

# 네트워크 포트 확인
check_network_ports() {
    log_info "네트워크 포트 확인 중..."
    
    ports=(80 8090)
    
    for port in "${ports[@]}"; do
        if netstat -tlnp | grep ":$port " >/dev/null 2>&1; then
            log_warning "포트 $port가 이미 사용 중입니다"
        else
            log_success "포트 $port 사용 가능"
        fi
    done
}

# 방화벽 설정 확인
check_firewall() {
    log_info "방화벽 설정 확인 중..."
    
    if command -v ufw >/dev/null 2>&1; then
        if ufw status | grep -q "Status: active"; then
            log_success "UFW 방화벽 활성화됨"
            
            if ufw status | grep -q "80/tcp"; then
                log_success "HTTP 포트 (80) 허용됨"
            else
                log_warning "HTTP 포트 (80)가 허용되지 않았습니다"
            fi
        else
            log_warning "UFW 방화벽이 비활성화되어 있습니다"
        fi
    else
        log_warning "UFW 방화벽이 설치되지 않았습니다"
    fi
}

# 시스템 정보 표시
show_system_info() {
    log_info "시스템 정보:"
    echo "  OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'=' -f2 | tr -d '\"')"
    echo "  CPU: $(nproc) cores"
    echo "  Memory: $(free -h | grep '^Mem:' | awk '{print $2}') total, $(free -h | grep '^Mem:' | awk '{print $7}') available"
    echo "  Disk: $(df -h / | awk 'NR==2{print $2}') total, $(df -h / | awk 'NR==2{print $4}') available"
    echo "  Python: $(python3 --version 2>/dev/null || echo 'Not installed')"
    echo "  Node.js: $(node --version 2>/dev/null || echo 'Not installed')"
    echo "  npm: $(npm --version 2>/dev/null || echo 'Not installed')"
}

# 설정 가이드 표시
show_setup_guide() {
    echo ""
    echo "=============================================="
    echo "다음 단계를 따라 설정을 완료하세요:"
    echo "=============================================="
    echo ""
    echo "1. 환경 변수 설정:"
    echo "   nano /root/.env"
    echo "   - PASSWORD: 시스템 접근 비밀번호 설정"
    echo "   - KIS 계정 정보 입력 (최소 1개)"
    echo "   - 거래소 API 키 입력 (선택사항)"
    echo ""
    echo "2. 설정 검증:"
    echo "   cd /root/POA"
    echo "   python3 -c \"from exchange.utils.validation import validate_environment; print(validate_environment())\""
    echo ""
    echo "3. 서비스 시작:"
    echo "   /root/POA/scripts/service_manager.sh restart"
    echo ""
    echo "4. 상태 확인:"
    echo "   /root/POA/scripts/service_manager.sh status"
    echo ""
    echo "5. 웹 인터페이스 접근:"
    echo "   http://your-server-ip/config/status"
    echo ""
    echo "6. 로그 확인:"
    echo "   /root/POA/scripts/service_manager.sh logs"
    echo ""
    echo "=============================================="
    echo "도움말:"
    echo "=============================================="
    echo "- 환경 변수 관리: /root/POA/scripts/env_manager.sh help"
    echo "- 서비스 관리: /root/POA/scripts/service_manager.sh help"
    echo "- 시스템 모니터링: curl http://localhost/monitor/status"
    echo "- 설정 API: curl http://localhost/config/validate"
    echo ""
}

# 메인 실행
main() {
    show_system_info
    echo ""
    
    create_directories
    setup_env_file
    setup_script_permissions
    check_system_services
    check_python_dependencies
    check_network_ports
    check_firewall
    
    echo ""
    log_success "초기 설정 완료!"
    
    show_setup_guide
}

# 스크립트 실행
main "$@"
