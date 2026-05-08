import streamlit as st
import pandas as pd
import os
import re

# 📌 1. 페이지 설정
st.set_page_config(page_title="원탑부동산 빌딩마스터 v3.5", page_icon="🏢", layout="centered")

# 📌 2. 디자인 CSS
st.markdown("""
    <style>
    .stApp { background-color: #f8faff; }
    .main-title { font-size: 28px; font-weight: 900; color: #1e1e1e; margin-bottom: 5px; }
    .violation-box { background-color: #ff4b4b; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; margin-bottom: 10px; animation: blink 2s infinite; }
    @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.8;} 100% {opacity: 1;} }
    div[data-testid="stMetric"] { background-color: white; border: 1px solid #e0e6ed; padding: 15px 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.03); }
    label[data-testid="stMetricLabel"] { font-size: 16px !important; font-weight: 600 !important; color: #555 !important; }
    div[data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 800 !important; color: #007bff !important; }
    .floor-info-box { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .floor-list { font-size: 16px; color: #333; line-height: 1.8; margin-top: 10px; }
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

# 📌 [핵심 로직] 중복되는 층별 용도 압축 함수 (예: 2층 오피스텔, 3층 오피스텔 -> 2~3층 오피스텔)
def compress_floor_info(raw_text):
    if pd.isna(raw_text) or str(raw_text).strip() == '': return ""
    
    text = str(raw_text).replace('  ', ' ')
    
    # "1층 소매점, 2층 사무소" 처럼 쉼표로 명확히 구분된 텍스트만 압축 시도
    if '층' in text and ',' in text:
        items = [x.strip() for x in text.split(',')]
        compressed = []
        prev_purp = ""
        start_floor = ""
        last_floor = ""

        for item in items:
            # 정규식으로 층수와 용도 분리 시도 (예: "2층 다가구주택" -> "2층", "다가구주택")
            match = re.match(r'(지?\d+층)\s*(.*)', item)
            if match:
                floor, purp = match.groups()
                purp = purp.strip()
                
                if purp == prev_purp:
                    last_floor = floor.replace('층', '') # 같은 용도면 끝 층수만 업데이트
                else:
                    if prev_purp:
                        # 이전 묶음 저장
                        if start_floor == last_floor or not last_floor:
                            compressed.append(f"🔹 {start_floor} {prev_purp}")
                        else:
                            compressed.append(f"🔹 {start_floor}~{last_floor}층 동일 ({prev_purp})")
                    start_floor = floor
                    last_floor = floor.replace('층', '')
                    prev_purp = purp
            else:
                # 패턴이 안 맞으면 그대로 출력
                compressed.append(f"🔹 {item}")
        
        # 마지막 항목 처리
        if prev_purp:
            if start_floor == last_floor or not last_floor:
                compressed.append(f"🔹 {start_floor} {prev_purp}")
            else:
                compressed.append(f"🔹 {start_floor}~{last_floor}층 동일 ({prev_purp})")
                
        return "<br>".join(compressed)
    else:
        # "단독주택외2" 같이 짧게 요약된 원본 데이터는 그대로 표출
        return "🔹 " + text.replace(',', '<br>🔹 ')

# 📌 4. 메인 UI
st.markdown('<p class="main-title">🏢 원탑부동산 빌딩마스터</p>', unsafe_allow_html=True)
st.caption("수원 건축물대장 데이터 통합 조회 시스템")

user_input = st.text_input("🔍 주소 입력", placeholder="예: 인계동 1030-11")

if user_input and df is not None:
    search_term = user_input.replace(" ", "")
    res = df[df['clean_addr'].str.contains(search_term, na=False)]

    if not res.empty:
        item = res.iloc[0]
        
        if item.get('vlBldYn') in ['1', 'Y', '위반']:
            st.markdown('<div class="violation-box">⚠️ 위반건축물 확인 필요</div>', unsafe_allow_html=True)

        st.info(f"📍 **조회 주소:** {item['platPlc']}")

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

        purp = item.get('mainPurpsCdNm', '정보 없음')
        if '다세대' in purp or '연립' in purp:
            st.success(f"📋 **건물 주용도:** {purp} 👉 다방 추천: [빌라/연립/다세대]")
        elif '다가구' in purp or '단독' in purp:
            st.success(f"📋 **건물 주용도:** {purp} 👉 다방 추천: [단독주택/다가구]")
        elif '오피스텔' in purp:
            st.success(f"📋 **건물 주용도:** {purp} 👉 다방 추천: [오피스텔]")
        else:
            st.success(f"📋 **건물 주용도:** {purp} 👉 다방 추천: [기타]")

        # 📌 층별 상세 용도 자동 압축 표출
        etc_purp = item.get('etcPurps', '')
        
        if pd.isna(etc_purp) or str(etc_purp).lower() == 'nan' or str(etc_purp).strip() == '':
            formatted_purp = "🔹 건축물대장(표제부)에 층별 상세 용도가 기재되어 있지 않습니다."
        else:
            formatted_purp = compress_floor_info(etc_purp)

        st.markdown(f"""
            <div class="floor-info-box">
                <p style="font-size:18px; font-weight:bold; color:#1e1e1e; margin-bottom:5px;">🏢 층별 상세 용도</p>
                <div class="floor-list">
                    {formatted_purp}
                </div>
                <p style="font-size:12px; color:#888; margin-top:10px;">※ 원본 데이터 사정에 따라 요약 표기(예: 단독주택외2)로 나올 수 있습니다.</p>
            </div>
        """, unsafe_allow_html=True)

        if pd.notna(item.get('bldNm')):
            st.caption(f"🏢 건물명: {item['bldNm']}")

    else:
        st.error("데이터를 찾을 수 없습니다.")

st.markdown("---")
st.caption("© 원탑부동산 빌딩마스터 v3.5")
