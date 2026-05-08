import streamlit as st
import pandas as pd
import re

# ─────────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="수원 건축물대장 조회",
    page_icon="🏢",
    layout="centered",
)

# ─────────────────────────────────────────────
# 글로벌 CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans KR', sans-serif !important;
    font-weight: 500;
}

/* 검색창 고정 스타일 (다크/라이트 무관) */
input[type="text"], div[data-testid="stTextInput"] input {
    background-color: #ffffff !important;
    color: #111111 !important;
    border: 1.5px solid #d0d0d0 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
}

/* 메트릭 카드 */
div[data-testid="metric-container"] {
    background: linear-gradient(135deg, #f0f4ff 0%, #e8f0fe 100%);
    border: 1px solid #c5d3f0;
    border-radius: 12px;
    padding: 12px 16px;
    text-align: center;
}
div[data-testid="metric-container"] label {
    font-size: 0.78rem !important;
    color: #4a5568 !important;
    font-weight: 600 !important;
}
div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #1a3a6e !important;
}

/* 섹션 헤더 */
.section-header {
    background: #1a3a6e;
    color: white;
    padding: 8px 16px;
    border-radius: 8px;
    font-weight: 700;
    font-size: 0.95rem;
    margin: 20px 0 10px 0;
    letter-spacing: 0.03em;
}

/* 행 카드 */
.row-card {
    background: #f8faff;
    border: 1px solid #dde6f7;
    border-left: 4px solid #3b6fd4;
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 8px;
    font-size: 0.9rem;
    line-height: 1.6;
}

/* 가구수 뱃지 */
.badge {
    display: inline-block;
    background: #e53e3e;
    color: white;
    border-radius: 20px;
    padding: 1px 9px;
    font-size: 0.75rem;
    font-weight: 700;
    margin-left: 6px;
    vertical-align: middle;
}

/* 주소 결과 목록 */
.addr-item {
    background: #ffffff;
    border: 1px solid #dde6f7;
    border-radius: 8px;
    padding: 9px 14px;
    margin-bottom: 6px;
    cursor: pointer;
    font-size: 0.88rem;
    font-weight: 500;
    transition: background 0.15s;
}
.addr-item:hover { background: #eef3ff; }

/* 앱 타이틀 */
.app-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #1a3a6e;
    letter-spacing: -0.02em;
    margin-bottom: 4px;
}
.app-sub {
    font-size: 0.85rem;
    color: #718096;
    margin-bottom: 20px;
    font-weight: 500;
}

/* 구분코드 뱃지 */
.type-badge {
    display: inline-block;
    border-radius: 20px;
    padding: 2px 11px;
    font-size: 0.78rem;
    font-weight: 700;
    margin-left: 8px;
    vertical-align: middle;
}
.type-집합 { background: #3b6fd4; color: white; }
.type-일반 { background: #38a169; color: white; }
.type-기타 { background: #805ad5; color: white; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 데이터 로드 유틸리티
# ─────────────────────────────────────────────
def robust_load(filepath: str) -> pd.DataFrame:
    """
    CSV.GZ 파일을 읽고 컬럼명을 즉시 정규화한다.
    - BOM 제거 (UTF-8 BOM: \\ufeff)
    - 앞뒤 공백 제거 (strip)
    - 보이지 않는 특수 공백 제거
    """
    df = pd.read_csv(
        filepath,
        compression='gzip',
        encoding='utf-8-sig',   # BOM 자동 제거
        low_memory=False,
    )
    # 컬럼명 정규화
    df.columns = (
        df.columns
        .str.strip()
        .str.replace(r'[\u200b\u00a0\ufeff\r\n]', '', regex=True)  # 특수 공백/제어문자
    )
    return df


def normalize_addr(text: str) -> str:
    """주소 비교를 위해 공백·하이픈 제거"""
    return re.sub(r'[\s\-]', '', str(text))


# ─────────────────────────────────────────────
# 컬럼 매핑 함수
# ─────────────────────────────────────────────
def map_master_cols(df: pd.DataFrame) -> pd.DataFrame:
    """표제부 컬럼을 영문 키로 매핑"""
    mapping = {
        '대지위치':            'addr',
        '관리건축물대장PK':    'pk',
        '대장구분코드명':       'register_type',
        '지상층수':            'floors_above',
        '가구수':              'household',
        '세대수':              'unit_count',
        '연면적':              'total_area',
        '사용승인일':          'approval_date',
        '옥내자주식대수':       'parking_indoor',
        '옥외자주식대수':       'parking_outdoor',
    }
    # 유연 매핑: 컬럼에 키워드가 포함되면 매핑
    rename = {}
    for col in df.columns:
        for k, v in mapping.items():
            if k in col and v not in rename.values():
                rename[col] = v
                break
    return df.rename(columns=rename)


def map_floor_cols(df: pd.DataFrame) -> pd.DataFrame:
    """층별 개요 컬럼 매핑"""
    mapping = {
        '관리건축물대장PK': 'pk',
        '층번호':           'floor_no',
        '주용도코드명':      'usage',
        '기타용도':         'other_usage',
        '면적':             'area',
    }
    rename = {}
    for col in df.columns:
        for k, v in mapping.items():
            if k in col and v not in rename.values():
                rename[col] = v
                break
    return df.rename(columns=rename)


def map_unit_cols(df: pd.DataFrame) -> pd.DataFrame:
    """전유부 컬럼 매핑"""
    mapping = {
        '관리건축물대장PK': 'pk',
        '호명칭':           'unit_name',
        '층번호':           'floor_no',
        '면적':             'area',
    }
    rename = {}
    for col in df.columns:
        for k, v in mapping.items():
            if k in col and v not in rename.values():
                rename[col] = v
                break
    return df.rename(columns=rename)


# ─────────────────────────────────────────────
# 가구수 정규식 추출
# ─────────────────────────────────────────────
def extract_household_badge(text: str) -> str | None:
    """기타용도에서 수기 가구수(예: '3가구', '5호') 추출"""
    if pd.isna(text):
        return None
    m = re.search(r'(\d+)(가구|호)', str(text))
    return f"{m.group(1)}{m.group(2)}" if m else None


# ─────────────────────────────────────────────
# 데이터 로딩 (캐시)
# ─────────────────────────────────────────────
@st.cache_data(show_spinner="데이터 로딩 중…")
def load_all():
    master = robust_load("mini_master.csv.gz")
    floor  = robust_load("mini_floor.csv.gz")
    unit   = robust_load("mini_unit.csv.gz")

    master = map_master_cols(master)
    floor  = map_floor_cols(floor)
    unit   = map_unit_cols(unit)

    # 검색용 정규화 주소 컬럼 추가
    if 'addr' in master.columns:
        master['addr_norm'] = master['addr'].apply(normalize_addr)

    return master, floor, unit


# ─────────────────────────────────────────────
# 숫자 포맷 헬퍼
# ─────────────────────────────────────────────
def safe_int(val, default=0) -> int:
    try:
        v = float(val)
        return int(v) if not pd.isna(v) else default
    except Exception:
        return default


def fmt_area(val) -> str:
    try:
        return f"{float(val):,.1f} ㎡"
    except Exception:
        return "-"


# ─────────────────────────────────────────────
# 건물 상세 렌더링
# ─────────────────────────────────────────────
def render_building(row: pd.Series, floor_df: pd.DataFrame, unit_df: pd.DataFrame):
    pk   = row.get('pk', '')
    rtype = str(row.get('register_type', ''))
    addr  = row.get('addr', '-')

    # ── 대장 구분 뱃지
    if '집합' in rtype:
        badge_class = 'type-집합'
    elif '일반' in rtype:
        badge_class = 'type-일반'
    else:
        badge_class = 'type-기타'

    st.markdown(
        f"<div style='font-size:1.1rem;font-weight:700;color:#1a3a6e;margin-bottom:4px;'>"
        f"📍 {addr}"
        f"<span class='type-badge {badge_class}'>{rtype}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 사용승인일
    approval = row.get('approval_date', '')
    if not pd.isna(approval) and str(approval).strip():
        st.caption(f"🗓️ 사용승인일: {approval}")

    # ── 연면적
    total_area = row.get('total_area', None)
    if total_area is not None and not pd.isna(total_area):
        st.caption(f"📐 연면적: {fmt_area(total_area)}")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 상단 메트릭 카드
    floors_above  = safe_int(row.get('floors_above'))
    household     = safe_int(row.get('household'))
    unit_count    = safe_int(row.get('unit_count'))
    total_hh      = household + unit_count
    park_in       = safe_int(row.get('parking_indoor'))
    park_out      = safe_int(row.get('parking_outdoor'))
    total_park    = park_in + park_out

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("🏗️ 지상층수", f"{floors_above}층" if floors_above else "-")
    with c2:
        st.metric("👥 총 가구·세대수", f"{total_hh}" if total_hh else "-")
    with c3:
        st.metric("🚗 총 주차대수", f"{total_park}대" if total_park else "-")

    # ─────────────────────────────────────────
    # 분기: 집합 → 전유부(호수별), 그 외 → 층별 개요
    # ─────────────────────────────────────────
    if '집합' in rtype:
        # 전유부 출력
        st.markdown("<div class='section-header'>🏠 호수별 전용면적 (전유부)</div>", unsafe_allow_html=True)

        units = unit_df[unit_df['pk'] == pk].copy() if 'pk' in unit_df.columns else pd.DataFrame()

        if units.empty:
            st.info("전유부 데이터가 없습니다.")
        else:
            # 층번호 정렬
            try:
                units['floor_no'] = pd.to_numeric(units['floor_no'], errors='coerce')
                units = units.sort_values(['floor_no', 'unit_name'])
            except Exception:
                pass

            for _, u in units.iterrows():
                floor_label = f"{int(u['floor_no'])}층" if not pd.isna(u.get('floor_no')) else '-'
                unit_name   = u.get('unit_name', '-')
                area_str    = fmt_area(u.get('area'))
                st.markdown(
                    f"<div class='row-card'>"
                    f"<b>{floor_label} · {unit_name}</b> &nbsp;|&nbsp; 전용면적 {area_str}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
    else:
        # 층별 개요 출력
        st.markdown("<div class='section-header'>📋 층별 용도 및 면적</div>", unsafe_allow_html=True)

        floors = floor_df[floor_df['pk'] == pk].copy() if 'pk' in floor_df.columns else pd.DataFrame()

        if floors.empty:
            st.info("층별 개요 데이터가 없습니다.")
        else:
            try:
                floors['floor_no'] = pd.to_numeric(floors['floor_no'], errors='coerce')
                floors = floors.sort_values('floor_no')
            except Exception:
                pass

            for _, f in floors.iterrows():
                floor_no    = f.get('floor_no')
                floor_label = f"{int(floor_no)}층" if not pd.isna(floor_no) else '-'
                usage       = f.get('usage', '-')
                other       = f.get('other_usage', '')
                area_str    = fmt_area(f.get('area'))

                # 수기 가구수 뱃지
                hh_badge = extract_household_badge(other)
                badge_html = f"<span class='badge'>{hh_badge}</span>" if hh_badge else ""

                # 기타용도 표시
                other_html = f"<span style='color:#718096;font-size:0.83rem;'> ({other})</span>" if (not pd.isna(other) and str(other).strip()) else ""

                st.markdown(
                    f"<div class='row-card'>"
                    f"<b>{floor_label}</b> &nbsp;·&nbsp; {usage}{badge_html}{other_html}"
                    f"<br><span style='color:#4a5568;font-size:0.85rem;'>면적: {area_str}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def main():
    st.markdown("<div class='app-title'>🏢 수원 건축물대장 통합 조회</div>", unsafe_allow_html=True)
    st.markdown("<div class='app-sub'>수원시 건축물대장 데이터 기반 · 표제부 / 층별 개요 / 전유부 통합 검색</div>", unsafe_allow_html=True)

    # ── 데이터 로드
    try:
        master, floor, unit = load_all()
    except FileNotFoundError as e:
        st.error(f"❌ 데이터 파일을 찾을 수 없습니다: {e}\n\n`mini_master.csv.gz`, `mini_floor.csv.gz`, `mini_unit.csv.gz` 파일을 앱과 같은 폴더에 넣어주세요.")
        return
    except Exception as e:
        st.error(f"❌ 데이터 로드 중 오류: {e}")
        st.exception(e)
        return

    # ── 검색창
    query = st.text_input(
        "🔍 주소 검색",
        placeholder="예: 매탄동 1202-2  또는  영통동 996",
        help="동 이름, 지번 등을 입력하세요. 공백·하이픈은 무시됩니다.",
    )

    if not query.strip():
        st.markdown(
            "<div style='text-align:center;color:#a0aec0;padding:40px 0;font-size:0.95rem;'>"
            "위 검색창에 주소를 입력하면 건축물 상세 정보가 표시됩니다.</div>",
            unsafe_allow_html=True,
        )
        return

    # ── 검색 실행
    query_norm = normalize_addr(query)

    if 'addr_norm' not in master.columns:
        st.error("주소 컬럼(대지위치)을 찾을 수 없습니다. 데이터 파일을 확인하세요.")
        return

    matched = master[master['addr_norm'].str.contains(query_norm, na=False, regex=False)]

    if matched.empty:
        st.warning(f"**'{query}'** 에 해당하는 건축물을 찾지 못했습니다. 동 이름이나 지번을 다시 확인해보세요.")
        return

    st.markdown(f"<div style='font-size:0.85rem;color:#4a5568;margin-bottom:12px;'>🔎 {len(matched)}건 검색됨</div>", unsafe_allow_html=True)

    # ── 결과가 여러 개면 선택
    if len(matched) > 1:
        addr_list = matched['addr'].tolist()
        addr_options = {addr: idx for idx, addr in enumerate(addr_list)}

        selected_addr = st.selectbox(
            "주소를 선택하세요",
            options=addr_list,
            format_func=lambda x: x,
        )
        row = matched.iloc[addr_options[selected_addr]]
    else:
        row = matched.iloc[0]

    st.divider()
    render_building(row, floor, unit)


if __name__ == "__main__":
    main()
