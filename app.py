import streamlit as st
import pandas as pd
import os

# 📌 1. 페이지 설정
st.set_page_config(
    page_title="원탑부동산 빌딩마스터 v3.1",
    page_icon="🏢",
    layout="centered"
)

# 📌 2. 모바일/PC 통합 디자인 CSS
st.markdown("""
    <style>
    .stApp { background-color: #f8faff; }
    /* 제목 스타일 */
    .main-title { font-size: 28px; font-weight: 900; color: #1e1e1e; margin-bottom: 5px; }
    
    /* 위반건축물 경고창 */
    .violation-box {
        background-color: #ff4b4b;
        color: white;
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        font-weight: bold;
        font-size: 20px;
        margin-bottom: 15px;
        animation: blink 2s infinite;
    }
    @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.7;} 100% {opacity: 1;} }

    /* 메트릭 카드 디자인 (글자 크기 키움) */
    div[data-testid="stMetric"] {
        background-color: white;
        border: 1px solid #e0e6ed;
        padding: 15px 20px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.03);
    }
    label[data-testid="stMetricLabel"] { font-size: 16px !important; font-weight: 600 !important; color: #555 !important; }
    div[data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 800 !important; color: #007bff !important; }

    /* 용도 박스 스타일 */
    .info-card {
        background-color: white;
        padding: 20px;
        border-radius: 15px;
        border-left: 6px solid #28a745;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

# 📌 3. 데이터 로딩
@st.cache_data
def load_data():
    file_path = "suwon_building_master_v3.csv.gz"
    if not os.path.exists(file_path): return None
    try:
        df = pd.read_csv(file_path, dtype=str)
        df['clean_addr'] = df['platPlc'].str.replace(" ", "")
        return df
    except: return None

df = load_data()

# 📌 4. 메인 화면
st.markdown('<p class="main-title">🏢 원탑부동산 빌딩마스터</p>', unsafe_allow_html=True)
st.caption("수원 건축물대장 데이터 통합 조회 시스템")

user_input = st.text_input("주소 입력", placeholder="예: 조원동 456-39")

if user_input and df is not None:
    # 검색 로직 (공백 제거 후 검색)
    search_term = user_input.replace(" ", "")
    res = df[df['clean_addr'].str.contains(search_term, na=False)]

    if not res.empty:
        item = res.iloc[0]
        
        # ⚠️ 위반건축물 체크 (vlBldYn 컬럼 기준)
        # 만약 컬럼이 없거나 값이 '1' 또는 'Y'인 경우 위반으로 표기
        is_violation = item.get('vlBldYn', '0')
        if is_violation in ['1', 'Y', '위반']:
            st.markdown('<div class="violation-box">⚠️ 위반건축물 확인 필요</div>', unsafe_allow_html=True)

        st.info(f"📍 **조회 주소:** {item['platPlc']}")

        # 📌 상단 4대 핵심 정보 (2x2 그리드)
        col1, col2 = st.columns(2)
        with col1:
            st.metric("🏗️ 전체 층수", f"지상 {item.get('grndFlrCnt', '0')}층")
        with col2:
            # 주차 합산
            p_cols = ['indrAutoUtcnt', 'indrMechUtcnt', 'oudrAutoUtcnt', 'oudrMechUtcnt']
            p_sum = sum([int(float(item.get(c, 0))) for c in p_cols if pd.notna(item.get(c))])
            st.metric("🚗 총 주차대수", f"{p_sum}대")

        col3, col4 = st.columns(2)
        with col3:
            # 사용승인일 (큰 글씨)
            u_day = str(item.get('useAprDay', '정보 없음'))
            if len(u_day) >= 8: u_day = f"{u_day[:4]}-{u_day[4:6]}-{u_day[6:8]}"
            st.metric("📅 사용승인일", u_day)
        with col4:
            # 총 세대수 (큰 글씨)
            hhld = int(float(item.get('hhldCnt', 0))) if pd.notna(item.get('hhldCnt')) else 0
            fmly = int(float(item.get('fmlyCnt', 0))) if pd.notna(item.get('fmlyCnt')) else 0
            st.metric("🏠 총 세대수", f"{hhld + fmly}세대")

        st.markdown("<br>", unsafe_allow_html=True)

        # 📌 하단 용도 정보 카드
        purp = item.get('mainPurpsCdNm', '정보 없음')
        etc_purp = item.get('etcPurps', '') # 기타 용도에 층별 정보가 섞여있는 경우가 많음
        
        st.markdown(f"""
            <div class="info-card">
                <p style="font-size:18px; margin-bottom:5px;">📋 <b>건축물 용도</b></p>
                <p style="font-size:22px; color:#28a745; font-weight:bold;">{purp}</p>
                <p style="color:#666; font-size:14px;">{etc_purp if pd.notna(etc_purp) else ""}</p>
            </div>
        """, unsafe_allow_html=True)

        # 다방 추천 팁
        if '다세대' in purp or '연립' in purp:
            st.warning("💡 **다방 추천:** [빌라/연립/다세대]")
        elif '다가구' in purp or '단독' in purp:
            st.warning("💡 **다방 추천:** [단독주택] 또는 [다가구주택]")
        elif '오피스텔' in purp:
            st.warning("💡 **다방 추천:** [오피스텔]")
        
        # 건물명 표시
        if pd.notna(item.get('bldNm')):
            st.caption(f"🏢 건물명: {item['bldNm']}")

    else:
        st.error("데이터를 찾을 수 없습니다. 주소를 다시 확인해 주세요.")

st.markdown("---")
st.caption("© 원탑부동산 빌딩마스터 v3.1")
