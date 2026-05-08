"""
다방 광고 등록용 건축물대장 정보 추출기
필요 파일 (앱과 같은 폴더):
  - mini_master_csv.gz
  - mini_floor_csv.gz
  - mini_unit_csv.gz
실행: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import re

# ════════════════════════════════════════════════════════════
# 페이지 설정
# ════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="다방 광고 정보 추출기",
    page_icon="🏠",
    layout="centered",
)

# ════════════════════════════════════════════════════════════
# CSS
# ════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans KR', sans-serif !important;
}

/* 검색창: 다크/라이트 무관 흰 배경 + 검은 글자 고정 */
div[data-testid="stTextInput"] input {
    background-color: #ffffff !important;
    color: #111111 !important;
    caret-color: #111111 !important;
    border: 2px solid #e0e0e0 !important;
    border-radius: 10px !important;
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    font-family: 'Noto Sans KR', sans-serif !important;
    transition: border-color 0.2s !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: #FF5252 !important;
    box-shadow: 0 0 0 3px rgba(255,82,82,0.15) !important;
    outline: none !important;
}

/* 헤더 */
.app-header {
    background: linear-gradient(135deg, #FF5252 0%, #FF8A65 100%);
    border-radius: 14px;
    padding: 22px 24px 18px;
    margin-bottom: 20px;
    color: white;
}
.app-header-title {
    font-size: 1.4rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    margin-bottom: 3px;
}
.app-header-sub {
    font-size: 0.82rem;
    opacity: 0.9;
    font-weight: 500;
}

/* 주소 결과 박스 */
.addr-box {
    background: #fff8f8;
    border: 1.5px solid #FF5252;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 18px;
}
.addr-text {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1a1a1a;
}
.addr-type {
    display: inline-block;
    background: #FF5252;
    color: white;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 2px 10px;
    border-radius: 20px;
    margin-left: 8px;
    vertical-align: middle;
}

/* 핵심 정보 카드 */
.metric-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 18px;
}
.metric-card {
    background: #f9f9f9;
    border: 1px solid #ebebeb;
    border-radius: 12px;
    padding: 14px 12px 12px;
    text-align: center;
}
.metric-icon {
    font-size: 1.3rem;
    margin-bottom: 4px;
}
.metric-label {
    font-size: 0.68rem;
    font-weight: 700;
    color: #999;
    letter-spacing: 0.04em;
    margin-bottom: 4px;
}
.metric-value {
    font-size: 1.2rem;
    font-weight: 800;
    color: #1a1a1a;
    letter-spacing: -0.02em;
    line-height: 1.1;
}
.metric-value.accent { color: #FF5252; }
.elev-yes {
    display: inline-block;
    background: #e8f5e9;
    color: #2e7d32;
    border-radius: 20px;
    padding: 2px 12px;
    font-size: 0.8rem;
    font-weight: 700;
}
.elev-no {
    display: inline-block;
    background: #ffebee;
    color: #c62828;
    border-radius: 20px;
    padding: 2px 12px;
    font-size: 0.8rem;
    font-weight: 700;
}

/* 섹션 제목 */
.sec-title {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    color: #aaa;
    text-transform: uppercase;
    border-bottom: 1px solid #f0f0f0;
    padding-bottom: 6px;
    margin: 20px 0 10px;
}

/* 층별/호실 행 */
.row-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    background: #fafafa;
    border: 1px solid #f0f0f0;
    border-radius: 9px;
    margin-bottom: 7px;
    font-size: 0.9rem;
}
.row-item:hover { background: #fff3f3; border-color: #ffcdd2; }
.row-left {
    font-weight: 600;
    color: #222;
}
.row-sub {
    font-size: 0.77rem;
    color: #999;
    font-weight: 400;
    margin-top: 1px;
}
.row-right {
    font-weight: 700;
    color: #FF5252;
    font-size: 0.95rem;
    white-space: nowrap;
}
.usage-badge {
    display: inline-block;
    background: #fff3e0;
    color: #e65100;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 1px 8px;
    border-radius: 20px;
    margin-left: 6px;
    vertical-align: middle;
}

/* 사용승인일 */
.approval-bar {
    background: #f5f5f5;
    border-radius: 8px;
    padding: 10px 16px;
    margin-bottom: 16px;
    font-size: 0.88rem;
    font-weight: 600;
    color: #555;
}
.approval-bar span {
    font-weight: 800;
    color: #1a1a1a;
    margin-left: 6px;
}

/* 검색 결과 목록 */
.search-result-item {
    padding: 9px 14px;
    background: white;
    border: 1px solid #e8e8e8;
    border-radius: 8px;
    margin-bottom: 5px;
    font-size: 0.88rem;
    font-weight: 500;
    cursor: pointer;
}

/* 빈 상태 */
.empty-state {
    text-align: center;
    padding: 50px 20px;
    color: #bbb;
}
.empty-icon { font-size: 2.5rem; margin-bottom: 10px; }
.empty-text { font-size: 0.95rem; font-weight: 500; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# 유틸리티 함수
# ════════════════════════════════════════════════════════════

def robust_load(filepath: str) -> pd.DataFrame:
    """
    CSV.GZ 로드 + 컬럼명 즉시 정규화
    - BOM 제거 (utf-8-sig)
    - 앞뒤 공백·불가시 특수문자 제거
    """
    df = pd.read_csv(
        filepath,
        compression='gzip',
        encoding='utf-8-sig',
        low_memory=False,
        dtype=str,  # 모든 컬럼 문자열로 읽기 (PK 손실 방지)
    )
    df.columns = (
        df.columns
        .str.strip()
        .str.replace(r'[\u200b\u00a0\ufeff\r\n\t]', '', regex=True)
    )
    return df


def normalize_addr(text: str) -> str:
    """주소 비교용: 공백·하이픈·'번지' 제거 후 소문자"""
    s = re.sub(r'[\s\-]', '', str(text))
    s = s.replace('번지', '')
    return s.lower()


def fmt_date(val: str) -> str:
    """19860523 → 1986년 05월 23일"""
    s = str(val).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}년 {s[4:6]}월 {s[6:8]}일"
    return s if s not in ('nan', '', 'None') else '-'


def fmt_area(val) -> str:
    try:
        return f"{float(val):,.2f} ㎡"
    except Exception:
        return '-'


def safe_int(val, default=0) -> int:
    try:
        v = str(val).strip()
        return int(float(v)) if v not in ('nan', '', 'None') else default
    except Exception:
        return default


def has_elevator(floor_df: pd.DataFrame, pk: str) -> bool:
    """층별 개요의 기타용도에서 엘리베이터/승강기 언급 확인"""
    rows = floor_df[floor_df['관리건축물대장PK'] == pk]
    combined = ' '.join(rows['기타용도'].fillna('').astype(str))
    return bool(re.search(r'승강기|엘리베이터|ELEV|EV', combined, re.IGNORECASE))


# ════════════════════════════════════════════════════════════
# 데이터 로딩 (캐시)
# ════════════════════════════════════════════════════════════

@st.cache_data(show_spinner="📂 데이터 로딩 중…")
def load_all():
    master = robust_load("mini_master_csv.gz")
    floor  = robust_load("mini_floor_csv.gz")
    unit   = robust_load("mini_unit_csv.gz")

    # 검색용 정규화 주소
    master['addr_norm'] = master['대지위치'].apply(normalize_addr)

    # 집합건물 pk 정수 변환 (unit 범위 매핑용)
    master['pk_int'] = pd.to_numeric(master['관리건축물대장PK'], errors='coerce')
    unit['pk_int']   = pd.to_numeric(unit['관리건축물대장PK'], errors='coerce')

    return master, floor, unit


# ════════════════════════════════════════════════════════════
# Unit 매핑: master pk < unit pk < 다음 master pk
# ════════════════════════════════════════════════════════════

def get_units_for_building(master: pd.DataFrame, unit: pd.DataFrame, pk_str: str) -> pd.DataFrame:
    """
    집합건물의 pk_str을 기준으로 해당 건물의 전유부(호실) 데이터를 반환.
    원리: unit pk는 master pk + 1 ~ 다음 master pk - 1 범위에 존재.
    같은 앞 12자리(블록) 내에서 정수 범위로 필터링.
    """
    try:
        target_pk_int = int(pk_str)
    except ValueError:
        return pd.DataFrame()

    block12 = pk_str[:12]

    # 같은 블록에서 정수형 master pk 목록 (집합만)
    block_masters = master[
        (master['대장구분코드명'].str.contains('집합', na=False)) &
        (master['관리건축물대장PK'].str.startswith(block12))
    ].copy()
    block_masters = block_masters.dropna(subset=['pk_int'])
    block_masters['pk_int'] = block_masters['pk_int'].astype(int)
    block_masters = block_masters.sort_values('pk_int')

    # 다음 master pk 찾기
    greater = block_masters[block_masters['pk_int'] > target_pk_int]
    next_pk_int = int(greater.iloc[0]['pk_int']) if len(greater) > 0 else target_pk_int + 99999

    # unit 필터
    u = unit.dropna(subset=['pk_int']).copy()
    u['pk_int'] = u['pk_int'].astype(int)
    result = u[(u['pk_int'] > target_pk_int) & (u['pk_int'] < next_pk_int)].copy()

    # 층번호 정렬
    result['층번호_int'] = pd.to_numeric(result['층번호'], errors='coerce').fillna(0).astype(int)
    result = result.sort_values(['층번호_int', '호명칭'])
    return result


# ════════════════════════════════════════════════════════════
# 건물 정보 렌더링
# ════════════════════════════════════════════════════════════

def render_building(row: pd.Series, floor: pd.DataFrame, unit: pd.DataFrame, master: pd.DataFrame):
    pk      = str(row['관리건축물대장PK']).strip()
    rtype   = str(row.get('대장구분코드명', '')).strip()
    addr    = str(row.get('대지위치', '-')).strip()
    is_집합  = '집합' in rtype

    # ── 주소 + 대장 유형
    type_label = '집합건물' if is_집합 else '일반/다가구'
    st.markdown(
        f"<div class='addr-box'>"
        f"<div class='addr-text'>{addr}"
        f"<span class='addr-type'>{type_label}</span>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    # ── 사용승인일
    approval = fmt_date(row.get('사용승인일', ''))
    st.markdown(
        f"<div class='approval-bar'>🗓️ 사용승인일<span>{approval}</span></div>",
        unsafe_allow_html=True,
    )

    # ── 핵심 지표 계산
    floors_above = safe_int(row.get('지상층수'))
    household    = safe_int(row.get('가구수(가구)'))
    unit_count   = safe_int(row.get('세대수(세대)'))
    total_hh     = household + unit_count
    park_in      = safe_int(row.get('옥내자주식대수(대)'))
    park_out     = safe_int(row.get('옥외자주식대수(대)'))
    total_park   = park_in + park_out
    elev         = has_elevator(floor, pk)
    elev_html    = "<span class='elev-yes'>✓ 있음</span>" if elev else "<span class='elev-no'>✗ 없음</span>"

    # ── 핵심 지표 카드 (4개)
    st.markdown(
        f"<div class='metric-row'>"
        f"  <div class='metric-card'><div class='metric-icon'>🏗️</div>"
        f"      <div class='metric-label'>지상층수</div>"
        f"      <div class='metric-value accent'>{floors_above}층</div></div>"
        f"  <div class='metric-card'><div class='metric-icon'>👥</div>"
        f"      <div class='metric-label'>총 세대수</div>"
        f"      <div class='metric-value accent'>{total_hh}세대</div></div>"
        f"  <div class='metric-card'><div class='metric-icon'>🚗</div>"
        f"      <div class='metric-label'>총 주차대수</div>"
        f"      <div class='metric-value accent'>{total_park}대</div></div>"
        f"  <div class='metric-card'><div class='metric-icon'>🛗</div>"
        f"      <div class='metric-label'>엘리베이터</div>"
        f"      <div class='metric-value' style='font-size:0.9rem;'>{elev_html}</div></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ════════════════════════
    # 분기: 집합 → 호실별 면적 / 일반 → 층별 용도
    # ════════════════════════
    if is_집합:
        # ── 호실별 전용면적
        st.markdown("<div class='sec-title'>🏠 호실별 전용면적</div>", unsafe_allow_html=True)
        units = get_units_for_building(master, unit, pk)

        if units.empty:
            st.info("전유부 데이터가 없습니다.")
        else:
            for _, u in units.iterrows():
                floor_no  = safe_int(u.get('층번호'))
                unit_name = str(u.get('호명칭', '-')).strip()
                area      = fmt_area(u.get('면적(㎡)'))
                dong      = str(u.get('동명칭', '')).strip()
                dong_html = f"<span style='color:#bbb;font-size:0.78rem;margin-right:4px;'>{dong}동</span>" if dong and dong != 'nan' else ''
                st.markdown(
                    f"<div class='row-item'>"
                    f"  <div><div class='row-left'>{dong_html}{unit_name}</div>"
                    f"      <div class='row-sub'>{floor_no}층</div></div>"
                    f"  <div class='row-right'>{area}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ── 층별 건축물용도 (집합/일반 모두 표시)
    st.markdown("<div class='sec-title'>📋 층별 건축물 용도</div>", unsafe_allow_html=True)
    floors = floor[floor['관리건축물대장PK'] == pk].copy()

    if floors.empty:
        st.info("층별 개요 데이터가 없습니다.")
    else:
        floors['층번호_int'] = pd.to_numeric(floors['층번호'], errors='coerce').fillna(0).astype(int)
        floors = floors.sort_values('층번호_int')

        for _, f in floors.iterrows():
            floor_no   = safe_int(f.get('층번호'))
            usage      = str(f.get('주용도코드명', '-')).strip()
            other      = str(f.get('기타용도', '')).strip()
            area       = fmt_area(f.get('면적(㎡)'))

            # 기타용도 표시 (승강기 등 제외하고 의미있는 내용만)
            other_clean = other if other and other != 'nan' else ''
            elev_terms  = re.compile(r'승강기|엘리베이터|ELEV|EV', re.I)
            other_display = '' if (not other_clean or elev_terms.search(other_clean)) else other_clean
            other_html = f"<span class='usage-badge'>{other_display}</span>" if other_display else ''

            floor_label = f"{floor_no}층" if floor_no >= 0 else f"지하{abs(floor_no)}층"

            st.markdown(
                f"<div class='row-item'>"
                f"  <div><div class='row-left'>{floor_label}&nbsp; {usage}{other_html}</div></div>"
                f"  <div class='row-right'>{area}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ════════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════════

def main():
    # 헤더
    st.markdown(
        "<div class='app-header'>"
        "<div class='app-header-title'>🏠 다방 광고 정보 추출기</div>"
        "<div class='app-header-sub'>지번 입력 → 건축물대장 핵심 정보 자동 추출</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # 데이터 로드
    try:
        master, floor, unit = load_all()
    except FileNotFoundError as e:
        st.error(
            f"❌ 파일을 찾을 수 없습니다: `{e}`\n\n"
            "`mini_master_csv.gz`, `mini_floor_csv.gz`, `mini_unit_csv.gz`를 "
            "`app.py`와 같은 폴더에 넣어주세요."
        )
        return
    except Exception as e:
        st.error(f"❌ 데이터 로드 오류: {e}")
        st.exception(e)
        return

    # 검색창
    query = st.text_input(
        "📍 지번 주소 입력",
        placeholder="예) 매탄동 1202-2   /   세류동 82-18   /   영통동 996",
        help="동 이름 + 지번을 입력하세요. 공백·하이픈·'번지'는 자동 처리됩니다.",
    )

    if not query.strip():
        st.markdown(
            "<div class='empty-state'>"
            "<div class='empty-icon'>🔍</div>"
            "<div class='empty-text'>위 검색창에 지번 주소를 입력하면<br>다방 광고에 필요한 정보가 바로 표시됩니다.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # 검색 실행
    q_norm = normalize_addr(query)
    matched = master[master['addr_norm'].str.contains(q_norm, na=False, regex=False)]

    if matched.empty:
        st.warning(f"**'{query}'** 에 해당하는 건물을 찾을 수 없습니다. 동 이름과 지번을 확인해주세요.")
        return

    # 결과가 여러 개이면 selectbox
    if len(matched) > 1:
        st.caption(f"🔎 {len(matched)}건 검색됨 — 건물을 선택하세요")
        addr_list   = matched['대지위치'].tolist()
        addr_types  = matched['대장구분코드명'].tolist()
        options     = [f"{a}  ({t})" for a, t in zip(addr_list, addr_types)]
        selected_i  = st.selectbox("건물 선택", range(len(options)), format_func=lambda i: options[i])
        row = matched.iloc[selected_i]
    else:
        row = matched.iloc[0]

    st.divider()
    render_building(row, floor, unit, master)


if __name__ == "__main__":
    main()
