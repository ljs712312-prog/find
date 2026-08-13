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
- 선택적으로 VWorld GIS건물통합정보의 위반건축물 **참고값**

건축HUB 공개 API에는 위반건축물 여부와 다가구주택의 별지 제9호
호(가구)별 면적대장 조회 기능이 없습니다. 따라서 앱은 누락값을 정상 또는
0으로 추정하지 않습니다. 위반 여부는 VWorld 키가 있을 때도 참고정보로만
표시하며, 법적 확인은 세움터·정부24 등에서 발급한 원본 대장이 필요합니다.

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
VWORLD_API_KEY = "..."
VWORLD_DOMAIN = "won-top-finder-work.streamlit.app"
```

키를 저장소, 로그, 오류 메시지 또는 화면에 출력하지 마세요.

## 테스트

```powershell
python -m pytest -q
ruff check app.py src tests
```

## 데이터 출처와 한계

- 건축HUB 건축물대장정보 서비스는 월간 갱신이며 발급 대장과 시차가 있을 수
  있습니다.
- 집합건물 면적은 전유부 관리 PK로 전유공용면적을 결합하고, `전유`와
  `공용` 행을 각각 합산합니다.
- VWorld GIS건물통합정보는 별도 서비스이며 건물 단위 피처가 여러 개일 수
  있습니다. 서로 다른 위반값이 있으면 단정하지 않고 혼재로 표시합니다.
- 이 앱의 결과는 공식 증명서가 아닙니다.
