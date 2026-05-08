import streamlit as st
import pandas as pd
import os

# 📌 1. 페이지 설정
st.set_page_config(
    page_title="원탑부동산 빌딩마스터 v3.3",
    page_icon="🏢",
    layout="centered"
)

# 📌 2. 디자인 개선 CSS
st.markdown("""
    <style>
    .stApp { background-color: #f8faff; }
    .main-title { font-size: 28px; font-weight: 900; color: #1e1e1e; margin-bottom: 5px; }
    
    .violation-box { background-color: #ff4b4b; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; margin-bottom: 10px; animation: blink 2s infinite; }
    @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.8;} 100% {opacity: 1;} }

    div[data-testid="stMetric"] { background-color: white; border: 1px solid #e0e6ed; padding: 15px 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.03); }
    label[data-testid="stMetricLabel"] { font-size: 16px !important; font-weight: 600 !important; color: #555 !important; }
    div[data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 800 !important; color: #007bff !important; }

    /* 층별/상세 용도 섹션 */
    .floor-info-box { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .highlight-text { background-color: #ffeeba; font-weight: bold; padding: 2px 5px; border-radius: 4px; color: #d39e00; }
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

# 📌 4. 메인 UI
st.markdown('<p class="main-title">🏢 원탑부동산 빌딩마스터</p>', unsafe_allow_html=True)
st.caption("수원 건축물대장 데이터 통합 조회 시스템")

# 검색창 2개 (주소 + 층/호수)
col_search1, col_search2 = st.columns([2, 1])
with col_search1:
    user_input = st.text_input("🔍 주소 입력", placeholder="예: 인계동 1030-11")
with col_search2:
    target_floor = st.text_input("🏢 확인 층 (선택)", placeholder="예: 2층, 1층")

if user_input and df is not None:
    search_term = user_input.replace(" ", "")
    res = df[df['clean_addr'].str.contains(search_term, na=False)]

    if not res.empty:
        item = res.iloc[0]
        
        # ⚠️ 위반건축물 체크
        if item.get('vlBldYn') in ['1', 'Y', '위반']:
            st.markdown('<div class="violation-box">⚠️ 위반건축물 확인 필요</div>', unsafe_allow_html=True)

        st.info(f"📍 **조회 주소:** {item['platPlc']}")

        # 📌 4대 핵심 정보 (2x2 배열)
        col1, col2 = st.columns(2)
        with col1:
            st.metric("🏗️ 전체 층수", f"지상 {item.get('grndFlrCnt', '0')}층")
        with col2:
            p_cols = ['indrAutoUtcnt', 'indrMechUtcnt', 'oudrAutoUtcnt', 'oudrMechUtcnt']
            p_sum = sum([int(float(item.get(c, 0))) for c in p_cols if pd.notna(item.get(c))])
            st.metric("🚗 총 주차대수", f"{p_sum}대")

        col3, col4 = st.columns(2)
        with col3:
            u_day = str(item.get('useAprDay', '정보 없음'))
            if len(u_day) >= 8: u_day = f"{u_day[:4]}-{u_day[4:6]}-{u_day[6:8]}"
            st.metric("📅 사용승인일", u_day)
        with col4:
            hhld = int(float(item.get('hhldCnt', 0))) if pd.notna(item.get('hhldCnt')) else 0
            fmly = int(float(item.get('fmlyCnt', 0))) if pd.notna(item.get('fmlyCnt')) else 0
            st.metric("🏠 총 세대수", f"{hhld + fmly}세대")

        st.markdown("<br>", unsafe_allow_html=True)

        # 📌 대표 건축물 용도 & 다방 팁
        purp = item.get('mainPurpsCdNm', '정보 없음')
        if '다세대' in purp or '연립' in purp:
            st.success(f"📋 **건물 주용도:** {purp} 👉 다방 추천: [빌라/연립/다세대]")
        elif '다가구' in purp or '단독' in purp:
            st.success(f"📋 **건물 주용도:** {purp} 👉 다방 추천: [단독주택/다가구]")
        elif '오피스텔' in purp:
            st.success(f"📋 **건물 주용도:** {purp} 👉 다방 추천: [오피스텔]")
        else:
            st.success(f"📋 **건물 주용도:** {purp} 👉 다방 추천: [기타]")

        # 📌 [신규] 층별 상세 용도 섹션 (기타용도 데이터 활용)
        etc_purp = item.get('etcPurps', '')
        if pd.isna(etc_purp) or etc_purp == 'nan' or etc_purp == '':
            etc_purp_display = "상세 층별 용도 정보가 기재되어 있지 않습니다. (건축물대장 원본 확인 필요)"
        else:
            etc_purp_display = etc_purp
            # 사용자가 입력한 층이 있으면 노란색으로 하이라이트
            if target_floor:
                target_text = target_floor.strip()
                if target_text in etc_purp_display:
                    etc_purp_display = etc_purp_display.replace(target_text, f'<span class="highlight-text">{target_text}</span>')

        st.markdown(f"""
            <div class="floor-info-box">
                <p style="font-size:18px; font-weight:bold; color:#1e1e1e; margin-bottom:10px;">🔍 층별 상세 용도 (기타용도 기재사항)</p>
                <p style="font-size:16px; color:#444; line-height:1.6;">{etc_purp_display}</p>
                <p style="font-size:12px; color:#888; margin-top:10px; margin-bottom:0;">※ 표제부 데이터 기반이며, 개별 호실(예: 203호)의 확장 여부 등은 전유부 대장 확인이 필요합니다.</p>
            </div>
        """, unsafe_allow_html=True)

        if pd.notna(item.get('bldNm')):
            st.caption(f"🏢 건물명: {item['bldNm']}")

    else:
        st.error("데이터를 찾을 수 없습니다. 주소를 확인해 주세요.")

st.markdown("---")
st.caption("© 원탑부동산 빌딩마스터 v3.3")
