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

# 📌 2. 지번 정규화 로직
def normalize_jibun(text):
    if not text or pd.isna(text): return ""
    nums = re.sub(r'[^0-9-]', '', str(text))
    parts = [str(int(p)) for p in nums.split('-') if p.isdigit()]
    return "-".join(parts)

# 📌 3. 유연한 데이터 로더 (충돌 방지 핵심)
@st.cache_data
def load_safe_data(file_path):
    if not os.path.exists(file_path): return None
    try:
        df = pd.read_csv(file_path, dtype=str)
        # 모든 칼럼명에서 보이지 않는 특수문자나 공백을 완벽히 제거
        df.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip() for c in df.columns]
        return df
    except: return None

# 📌 4. 메인 실행
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기 (최종안정판)</p>', unsafe_allow_html=True)

# 데이터 로딩
master = load_safe_data("mini_master.csv.gz")
floor = load_safe_data("mini_floor.csv.gz")
unit = load_safe_data("mini_unit.csv.gz")

if master is None:
    st.error("데이터 파일을 찾을 수 없습니다. 깃허브에 파일이 있는지 확인해주세요.")
    st.stop()

query = st.text_input("📍 지번 주소 입력", placeholder="예: 매탄동 1202-2")

if query:
    # 파일에 존재하는 실제 주소 칼럼명 찾기 (대지위치가 없으면 무조건 첫 번째 칼럼)
    addr_col = '대지위치' if '대지위치' in master.columns else master.columns[0]
    pk_col = '관리건축물대장PK' if '관리건축물대장PK' in master.columns else master.columns[1]
    
    # 지번 검색을 위한 사전 작업
    master['jibun_key'] = master[addr_col].apply(normalize_jibun)
    q_jibun = normalize_jibun(query)
    q_dong = re.sub(r'[0-9-\s]', '', query)
    
    # 일치하는 데이터 찾기
    mask = (master['jibun_key'] == q_jibun)
    if q_dong: 
        mask &= master[addr_col].fillna('').str.contains(q_dong, na=False)
        
    res = master[mask]

    if not res.empty:
        item = res.iloc[0]
        pk = str(item.get(pk_col, ''))
        
        # 에러를 뱉지 않는 안전한 데이터 추출 (.get 사용)
        bld_type = str(item.get('대장구분코드명', '일반'))
        floors = item.get('지상층수', '0')
        gagu = int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))
        p_in = int(float(item.get('옥내자주식대수(대)', 0) or 0))
        p_out = int(float(item.get('옥외자주식대수(대)', 0) or 0))
        el_ride = int(float(item.get('승용승강기수', 0) or 0))
        el_emgen = int(float(item.get('비상용승강기수', 0) or 0))
        
        # 위반건축물 칼럼이 파일에 존재할 때만 체크
        if '위반건축물여부' in master.columns:
            if str(item['위반건축물여부']).strip() in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.markdown('<div class="violation-active">🚨 위반건축물 주의 🚨</div>', unsafe_allow_html=True)

        st.info(f"📍 **{item.get(addr_col, '주소')}** ({bld_type})")
        
        # 핵심 수치
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("🏗️ 층수", f"{floors}층")
        with c2: st.metric("🏠 가구", f"{gagu}가구")
        with c3: st.metric("🚗 주차", f"{p_in + p_out}대")
        with c4: st.metric("🛗 승강기", f"{el_ride + el_emgen}대")

        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        if "집합" in bld_type:
            st.markdown("### 🔑 호수별 전용면적")
            if unit is not None:
                unit_pk_col = '관리건축물대장PK' if '관리건축물대장PK' in unit.columns else unit.columns[0]
                u_list = unit[unit[unit_pk_col] == pk]
                if not u_list.empty:
                    for _, u in u_list.iterrows():
                        u_flr = u.get('층번호', '')
                        u_ho = u.get('호명칭', '')
                        u_area = u.get('면적(㎡)', '0')
                        st.markdown(f'<div class="data-row"><span>{u_flr}층 {u_ho}</span><span style="color:#007bff; font-weight:800;">{u_area} ㎡</span></div>', unsafe_allow_html=True)
                else:
                    st.write("상세 정보가 없습니다.")
        else:
            st.markdown("### 🏢 층별 상세 현황")
            if floor is not None:
                floor_pk_col = '관리건축물대장PK' if '관리건축물대장PK' in floor.columns else floor.columns[0]
                f_list = floor[floor[floor_pk_col] == pk]
                if not f_list.empty:
                    for _, f in f_list.iterrows():
                        f_flr = f.get('층번호', '')
                        f_purp = f.get('주용도코드명', '')
                        f_etc = str(f.get('기타용도', ''))
                        f_area = f.get('면적(㎡)', '0')
                        
                        g_match = re.search(r'(\d+)\s*(가구|호)', f_etc)
                        badge = f'<span class="badge">{g_match.group(0)}</span>' if g_match else ""
                        st.markdown(f'<div class="data-row"><span>{f_flr}층 {f_purp}</span>{badge}<span style="color:#007bff; font-weight:800;">{f_area} ㎡</span></div>', unsafe_allow_html=True)
                else:
                    st.write("상세 정보가 없습니다.")
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.error("해당 지번의 검색 결과가 없습니다.")
