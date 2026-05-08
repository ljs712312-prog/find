import streamlit as st
import pandas as pd
import re
import os

# 📌 1. 페이지 설정 및 디자인
st.set_page_config(page_title="원탑 건축물대장 추출기", page_icon="🏢", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { color: #111111 !important; font-weight: 500 !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 10px; }
    
    /* 검색창 디자인 (시인성 강조) */
    div[data-testid="stTextInput"] input {
        font-size: 18px !important; font-weight: 600 !important; padding: 14px 15px !important; 
        background-color: #ffffff !important; color: #000000 !important;
        border: 2px solid #007bff !important; border-radius: 12px;
    }

    .info-card { background-color: #ffffff; padding: 18px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-top: 15px; }
    .data-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #f1f3f5; }
    .label-col { font-weight: 800; color: #6f42c1; min-width: 65px; }
    .value-col { color: #007bff; font-weight: 800; min-width: 85px; text-align: right; }
    .gagu-badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; margin-left: 6px; }
</style>
""", unsafe_allow_html=True)

# 📌 2. 지번 숫자 정규화 함수 (핵심!)
def normalize_jibun(text):
    if not text: return ""
    # 숫자와 하이픈(-)만 남김
    nums = re.sub(r'[^0-9-]', '', str(text))
    # '1202-0002' -> ['1202', '0002'] -> ['1202', '2'] -> '1202-2' 로 변환
    parts = [str(int(p)) for p in nums.split('-') if p.isdigit()]
    return "-".join(parts)

@st.cache_data
def load_data_v8(file_path, d_type):
    if not os.path.exists(file_path): return None
    try:
        df = pd.read_csv(file_path, dtype=str)
        # 컬럼명 쓰레기 문자 제거
        df.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', c).strip() for c in df.columns]
        
        if d_type == 'master':
            # 순서대로 강제 매칭
            new_cols = ['addr', 'pk', 'bld_type', 'floors', 'gagu', 'sadae', 'tot_area', 'app_date', 'p_in', 'p_out']
            df.columns = new_cols + list(df.columns[len(new_cols):])
            # 데이터 내의 지번을 '1202-2' 형태로 미리 정규화해서 저장
            df['jibun_key'] = df['addr'].apply(normalize_jibun)
        elif d_type == 'floor':
            df.columns = ['pk', 'flr_no', 'purpose', 'etc', 'area'] + list(df.columns[5:])
        elif d_type == 'unit':
            df.columns = ['pk', 'dong', 'ho', 'flr_no', 'area'] + list(df.columns[5:])
        return df
    except: return None

# 📌 3. 실행부
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기 v8.0</p>', unsafe_allow_html=True)

master = load_data_v8("mini_master.csv.gz", "master")
floor = load_data_v8("mini_floor.csv.gz", "floor")
unit = load_data_v8("mini_unit.csv.gz", "unit")

query = st.text_input("📍 지번 주소 입력 (동 제외 숫자만 쳐보세요)", placeholder="예) 매탄동 1202-2 또는 1202-2")

if query:
    if master is not None:
        # 1. 입력한 주소에서 숫자-숫자 부분만 추출
        q_jibun = normalize_jibun(query)
        
        # 2. 동 이름 추출 (입력값에 문자가 섞여있을 경우)
        q_dong = re.sub(r'[0-9-\s]', '', query)

        # 3. 검색 필터링
        # 지번 숫자(`1202-2`)가 일치하고, 동 이름이 포함된 행 찾기
        mask = (master['jibun_key'] == q_jibun)
        if q_dong:
            mask &= master['addr'].str.contains(q_dong, na=False)
            
        res = master[mask]

        if not res.empty:
            item = res.iloc[0]
            pk = item['pk']
            st.info(f"📍 **조회 주소:** {item['addr']} ({item['bld_type']})")
            
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("🏗️ 층수", f"{item['floors']}층")
            with c2: st.metric("🏠 가구", f"{int(float(item['gagu'] or 0)) + int(float(item['sadae'] or 0))}가구")
            with c3: st.metric("🚗 주차", f"{int(float(item['p_in'] or 0)) + int(float(item['p_out'] or 0))}대")

            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            if "집합" in str(item['bld_type']):
                st.markdown("### 🔑 호수별 전용면적")
                if unit is not None:
                    u_list = unit[unit['pk'] == pk]
                    for _, u in u_list.iterrows():
                        st.markdown(f'<div class="data-row"><span>{u["flr_no"]}층 {u["ho"]}</span><span class="value">{u["area"]} ㎡</span></div>', unsafe_allow_html=True)
            else:
                st.markdown("### 🏢 층별 상세 현황")
                if floor is not None:
                    f_list = floor[floor['pk'] == pk]
                    for _, f in f_list.iterrows():
                        g_match = re.search(r'(\d+)\s*(가구|호)', str(f['etc']))
                        badge = f'<span class="gagu-badge">{g_match.group(0)}</span>' if g_match else ""
                        st.markdown(f'<div class="data-row"><span>{f["flr_no"]}층 {f["purpose"]}</span>{badge}<span class="value">{f["area"]} ㎡</span></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error(f"'{query}' (지번: {q_jibun}) 정보를 찾을 수 없습니다.")
