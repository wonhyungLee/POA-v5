# POA v5 - KIS 확장 지원

## 주요 변경사항

### 1. KIS4 실전투자 전환
- kis.py에서 모든 KIS 번호가 실전투자 URL을 사용하도록 변경됨
- 기존: KIS4만 모의투자 URL 사용
- 변경: 모든 KIS(1-50)가 실전투자 URL 사용

### 2. KIS 50개까지 확장 지원
- KIS1부터 KIS50까지 지원
- 동적 설정 시스템으로 유연한 관리 가능

### 3. 환경 변수 설정
.env 파일에 다음과 같이 설정:

```
# KIS1 설정
KIS1_KEY="your_key"
KIS1_SECRET="your_secret"
KIS1_ACCOUNT_NUMBER="your_account_number"
KIS1_ACCOUNT_CODE="01"

# KIS2 설정
KIS2_KEY="your_key"
KIS2_SECRET="your_secret"
KIS2_ACCOUNT_NUMBER="your_account_number"
KIS2_ACCOUNT_CODE="01"

# ... KIS3 ~ KIS49 동일한 형식으로 설정 ...

# KIS50 설정
KIS50_KEY="your_key"
KIS50_SECRET="your_secret"
KIS50_ACCOUNT_NUMBER="your_account_number"
KIS50_ACCOUNT_CODE="01"
```

### 4. API 호출 예시
```json
{
  "password": "your_password",
  "exchange": "KRX",
  "kis_number": 5,  // 1-50 범위 사용 가능
  "base": "005930",
  "quote": "KRW",
  "side": "buy",
  "amount": 10
}
```

### 5. Cloud-init 설정
- GitHub 리포지토리가 POA-v5로 변경됨
- KIS5-KIS10 예시 환경변수 추가 (필요시 KIS50까지 확장 가능)

## 주의사항
1. 실전투자 사용 시 실제 자금이 사용됨
2. KIS 번호는 1-50 범위만 지원
3. 각 KIS 설정은 .env 파일에 모두 정의되어야 함
