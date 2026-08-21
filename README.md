# 원탑 건축물대장

수원시 지번을 국토교통부 건축HUB 건축물대장정보 서비스로 조회하는
Streamlit 앱입니다. 기존의 정적 CSV 스냅샷 대신 공식 API를 우선 사용하며,
일반/집합건축물, 산번지, 층별개요와 집합건물 호실별 전유·공용면적을
구분해 보여줍니다.

## 지원 범위

- 수원시 56개 현행 법정동의 지번과 산번지
- 일반건축물·집합건축물 표제부
- 층별 면적 및 용도
- 집합건물 전유부와 호실별 전유·공용면적
- 다가구주택의 건축인허가 이력 기반 정밀 면적 참고조회
- 선택적으로 VWorld GIS건물통합정보의 위반건축물 **참고값**
- 사용자가 누를 때만 실행되는 경기부동산포털 건축물 표시 **1차 확인**

건축HUB 건축물대장 공개 API에는 위반건축물 여부와 다가구주택의 별지
제9호 호(가구)별 면적대장 조회 기능이 없습니다. 다가구주택으로 확인된
지번은 별도의 건축인허가정보 API를 사용자가 버튼을 누를 때 조회합니다. 먼저
호별개요와 호별전유공용면적을 관리 PK로 연결하고, 이 행이 없으면 같은 인허가
이력의 비호별 전유공용면적·층별개요·대지위치까지 단계별로 확인합니다. 호 관리
PK가 없는 면적과 층별 면적은 호에 임의 배정하거나 합산하지 않습니다. 모두
인허가 이력 참고값이며 현재 대장 확정값이 아닙니다. 서로 다른 이력은 합치지
않고 누락값을 0으로 추정하지 않습니다. 법적 확인은 관할청·세움터 등에서
발급한 별지 제9호 원본 대장이 필요합니다.

경기부동산포털은 2025년 9월 12일부터 위반건축물 정보를 제공하지
않습니다. 포털의 `해당 사항 없음`은 위반건축물 외에도 보안건축물,
연계 누락 또는 건축물 자료가 없는 경우에 나타날 수 있습니다. 따라서 이
앱은 해당 결과를 위반 확정으로 바꾸지 않고 `추가 확인 필요`로만 표시합니다.
포털의 화면용 내부 요청은 공개 OpenAPI가 아니므로 버튼을 누른 단건 조회에만
사용하고, 실패하면 포털 직접 열기와 정부24 대장 열람을 제공합니다.

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
# secrets.toml에 키 입력
streamlit run app.py
```

필수 Streamlit secret:

```toml
BUILDING_HUB_API_KEY = "..."
```

선택 secret:

```toml
# Streamlit Cloud → 건축HUB 직접 연결이 지속적으로 실패할 때만 사용합니다.
# 무료 운영은 relay/cloudflare-worker/README.md의 Workers 배포 절차를 먼저 완료한 뒤 두 값을 함께 지정합니다.
# BUILDING_HUB_RELAY_URL = "https://your-relay.workers.dev"
# BUILDING_HUB_RELAY_HMAC_SECRET = "long-random-secret"

# 건축인허가 서비스가 별도 인증키를 쓰는 경우에만 지정합니다.
# 생략하면 BUILDING_HUB_API_KEY를 재사용합니다.
ARCH_PMS_HUB_API_KEY = "..."
VWORLD_API_KEY = "..."
VWORLD_DOMAIN = "won-top-finder-work.streamlit.app"
```

키를 저장소, 로그, 오류 메시지 또는 화면에 출력하지 마세요.

### Streamlit Cloud 연결 중계(선택)

공식 건축HUB URL은 `https://apis.data.go.kr/1613000/BldRgstHubService`입니다.
직접 연결이 지속적으로 `connect_timeout`으로 실패하는 배포 환경에서는
추가 결제가 없는 운영을 위해 `relay/cloudflare-worker/`의 Cloudflare Workers Free 중계를 권장합니다. 앱은 먼저
공식 API에 직접 연결하고, TCP 연결·TLS 연결 실패에만 서명된 중계로 자동
전환합니다. 인증·할당량·API 오류나 응답 지연에는 중계로 전환하지 않습니다.

중계 서버에는 `DATA_GO_SERVICE_KEY`를 secret으로 저장하고, Streamlit에는 기존
`BUILDING_HUB_API_KEY`와 중계 URL·별도 HMAC 비밀값을 둡니다. 브라우저가 중계
서버를 직접 호출하거나 API 키를 중계 요청으로 전달하지 않습니다. 무료 배포·운영
절차는 `relay/cloudflare-worker/README.md`를 따르세요.

## 테스트

```powershell
python -m pytest -q
ruff check app.py src tests
```

## 데이터 출처와 한계

- 건축HUB 건축물대장정보 서비스는 월간 갱신이며 발급 대장과 시차가 있을 수
  있습니다.
- 표제부를 먼저 확인한 뒤 층별·호실 등 상세 API가 일시 지연되면, 확인된
  표제부 결과는 표시하고 지연된 상세 항목만 경고로 구분합니다. 부분 결과는
  장기 캐시에 남기지 않아 다음 조회에서 자동 재시도합니다.
- 집합건물 면적은 전유부 관리 PK로 전유공용면적을 결합하고, `전유`와
  `공용` 행을 각각 합산합니다.
- 다가구 면적은 정확도에 따라 분리합니다. 1단계는 `관리허가대장PK →
  동별개요PK → 호별개요PK → 호별전유공용면적PK`의 공식 관계로 연결된
  호별 값입니다. 2단계는 같은 관리허가대장PK의 비호별 전유공용면적 원문,
  3단계는 층별 총량입니다. 2·3단계는 호별 값으로 승격하거나 서로 합산하지
  않습니다.
- 건축물대장 PK와 인허가 PK를 직접 연결하거나, 여러 인허가 이력을 합산하지
  않습니다. 현재 대장의 사용승인일과 정확히 같은 이력을 우선 표시하되, 이
  일치만으로 현재 건물 귀속을 확정하지 않습니다.
- 인허가 참고조회는 다가구 건축물 결과에서 사용자가 요청할 때만 실행해
  개발계정 호출 한도와 불필요한 이력 조회를 줄입니다.
- VWorld GIS건물통합정보는 별도 서비스이며 건물 단위 피처가 여러 개일 수
  있습니다. 서로 다른 위반값이 있으면 단정하지 않고 혼재로 표시합니다.
- 경기부동산포털의 건축물 표시 여부는 지원되는 위반정보 API가 아니며,
  적법·위반 판정에 사용할 수 없습니다.
- 이 앱의 결과는 공식 증명서가 아닙니다.

## Streamlit Cloud 건축HUB 연결 장애: 무료 중계 경로

Streamlit Community Cloud에서 `apis.data.go.kr` 직접 연결이 `connect_timeout`, DNS/connection, TLS 단계에서만 실패할 경우, 앱은 선택적으로 서명된 중계로 전환할 수 있습니다.

추가 결제 없이 운영하려면 `relay/cloudflare-worker/`의 Cloudflare Workers Free 중계를 사용하세요. 기존 `BUILDING_HUB_API_KEY` 직접 호출이 항상 1순위이며, 중계는 네트워크 연결 장애 때만 사용됩니다. GCP Cloud Run은 필수가 아니며 `relay/`의 FastAPI 구현은 유료/대체 배포 옵션으로만 남겨둡니다.

배포 순서는 `relay/cloudflare-worker/README.md`를 따릅니다.
