import streamlit as st
import pandas as pd

# 📌 페이지 설정
st.set_page_config(page_title="원탑부동산 빌딩마스터", layout="centered")

# 📌 스타일 적용 (모바일 가독성)
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; background-color: #007bff; color: white; }
    .result-card { background-color: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    # 깃허브에 올린 파일명과 일치해야 합니다
    df = pd.read_csv("suwon_building_master_v3.csv", dtype=str)
    df['bun_int'] = pd.to_numeric(df['bun'], errors='coerce').fillna(-1).astype(int)
    df['ji_int'] = pd.to_numeric(df['ji'], errors='coerce').fillna(-1).astype(int)
    df['clean_addr'] = df['platPlc'].str.replace(" ", "")
    return df

df = load_data()

st.title("🏢 원탑부동산 매물조회")
st.caption("건축물대장 기반 층수/주차/사용승인일 조회")

# 📌 입력창
user_input = st.text_input("주소를 입력하세요", placeholder="예: 인계동 1030")

if user_input:
    parts = user_input.strip().split()
    if len(parts) >= 2:
        jibun = parts[-1]
        dong_name = "".join(parts[:-1])
        
        if '-' in jibun:
            b_num, j_num = map(int, jibun.split('-'))
        else:
            b_num, j_num = int(jibun), 0

        # 검색 로직 (강력한 텍스트+숫자 복합 검색)
        target_text = f"{dong_name}{b_num}"
        if j_num > 0: target_text += f"-{j_num}"
        
        res = df[df['clean_addr'].str.contains(target_text, na=False)]

        if not res.empty:
            item = res.iloc[0]
            
            # 결과 표시
            st.markdown(f"### 📍 {item['platPlc']}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("층수", f"지상 {item.get('grndFlrCnt', 0)}층")
                u_day = str(item.get('useAprDay', '정보 없음'))
                if len(u_day) == 8: u_day = f"{u_day[:4]}-{u_day[4:6]}-{u_day[6:]}"
                st.write(f"📅 **사용승인:** {u_day}")
            
            with col2:
                # 주차 합산
                p_sum = sum([int(float(item.get(c, 0))) for c in ['indrAutoUtcnt', 'indrMechUtcnt', 'oudrAutoUtcnt', 'oudrMechUtcnt'] if pd.notna(item.get(c))])
                st.metric("주차", f"{p_sum}대")
                hhld = int(float(item.get('hhldCnt', 0))) + int(float(item.get('fmlyCnt', 0)))
                st.write(f"🏠 **세대수:** {hhld}세대")
            
            st.info(f"📋 **용도:** {item.get('mainPurpsCdNm', '정보 없음')}")
            
            # 다방용 팁
            purp = item.get('mainPurpsCdNm', '')
            if '다세대' in purp or '연립' in purp: st.success("👉 다방 체크: [빌라/연립/다세대]")
            elif '다가구' in purp or '단독' in purp: st.success("👉 다방 체크: [단독주택] 또는 [다가구주택]")
            elif '오피스텔' in purp: st.success("👉 다방 체크: [오피스텔]")
        else:
            st.error("데이터를 찾을 수 없습니다.")