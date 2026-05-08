import streamlit as st
import pandas as pd
import re
import os

# 📌 1. 페이지 설정
st.set_page_config(page_title="원탑 건축물대장 추출기", page_icon="🏢", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { color: #111111 !important; font-weight: 500 !important; }
    .main-title { font-size: 24px; font-weight: 800; color: #000000; margin-bottom: 10px; }
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #000000 !important;
        border: 2px solid #007bff !important; border-radius: 12px; font-weight: 600 !important;
    }
    .violation-active { background-color: #ff4b4b; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 800; margin-bottom: 15px; animation: blink 1.5s infinite; }
    @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.7;} 100% {opacity: 1;} }
    .info-card { background-color: #ffffff; padding: 15px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-top: 15px; }
    .data-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f1f3f5; font-size: 14px; }
    .badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# 📌 2. 지번 정규화 로직 (1202-0002 -> 1202-2)
def normalize_jibun(text):
    if not text: return ""
    nums = re.sub(r'[^0-9-]', '', str(text))
    parts = [str(int(p)) for p in nums.split('-') if p.isdigit()]
    return "-".join(parts)

@st.cache_data
def load_final_data(file_path, d_type):
    if not os.path.exists(file_path): return None
    try:
        df = pd.read_csv(file_path, dtype=str)
        df.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', c).strip() for c in df.columns]
        if d_type == 'master':
            # 컬럼 순서대로 강제 지정 (위반/엘베 포함)
            mapping = ['addr', 'pk', 'bld_type', 'floors', 'gagu', 'sadae', 'tot_area', 'app_date', 'p_in', 'p_out', 'violation', 'el_ride', 'el_emgen']
            df.columns = mapping + list(df.columns[len(mapping):])
            df['jibun_key'] = df['addr'].apply(normalize_jibun)
        elif d_type == 'floor':
            df.columns = ['pk', 'flr_no', 'purpose', 'etc', 'area'] + list(df.columns[5:])
        elif d_type == 'unit':
            df.columns = ['pk', 'dong', 'ho', 'flr_no', 'area'] + list(df.columns[5:])
        return df
    except: return None

# 📌 3. 메인 실행
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기 v9.0</p>', unsafe_allow_html=True)

master = load_final_data("mini_master.csv.gz", "master")
floor = load_final_data("mini_floor.csv.gz", "floor")
unit = load_final_data("mini_unit.csv.gz", "unit")

query = st.text_input("📍 지번 주소 입력", placeholder="예: 매탄동 1202-2")

if query and master is not None:
    q_jibun = normalize_jibun(query)
    q_dong = re.sub(r'[0-9-\s]', '', query)
    
    mask = (master['jibun_key'] == q_jibun)
    if q_dong: mask &= master['addr'].str.contains(q_dong, na=False)
    res = master[mask]

    if not res.empty:
        item = res.iloc[0]
        pk = item['pk']
        
        # 🚨 위반건축물 표시
        if str(item.get('violation', '0')).strip() in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
            st.markdown('<div class="violation-active">🚨 위반건축물 주의 🚨</div>', unsafe_allow_html=True)

        st.info(f"📍 **{item['addr']}** ({item['bld_type']})")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("🏗️ 층수", f"{item['floors']}층")
        with c2: st.metric("🏠 가구", f"{int(float(item['gagu'] or 0)) + int(float(item['sadae'] or 0))}가구")
        with c3: st.metric("🚗 주차", f"{int(float(item['p_in'] or 0)) + int(float(item['p_out'] or 0))}대")
        with c4:
            el = int(float(item.get('el_ride', 0) or 0)) + int(float(item.get('el_emgen', 0) or 0))
            st.metric("🛗 승강기", f"{el}대")

        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        if "집합" in str(item['bld_type']):
            st.markdown("### 🔑 호수별 전용면적")
            if unit is not None:
                u_list = unit[unit['pk'] == pk]
                for _, u in u_list.iterrows():
                    st.markdown(f'<div class="data-row"><span>{u["flr_no"]}층 {u["ho"]}</span><span style="color:#007bff; font-weight:800;">{u["area"]} ㎡</span></div>', unsafe_allow_html=True)
        else:
            st.markdown("### 🏢 층별 상세 현황")
            if floor is not None:
                f_list = floor[floor['pk'] == pk]
                for _, f in f_list.iterrows():
                    g_match = re.search(r'(\d+)\s*(가구|호)', str(f['etc']))
                    badge = f'<span class="badge">{g_match.group(0)}</span>' if g_match else ""
                    st.markdown(f'<div class="data-row"><span>{f["flr_no"]}층 {f["purpose"]}</span>{badge}<span style="color:#007bff; font-weight:800;">{f["area"]} ㎡</span></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
