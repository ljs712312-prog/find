import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="원탑 건축물대장", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { color: #111111 !important; font-weight: 500 !important; }
    div[data-testid="stTextInput"] input { background-color: #ffffff !important; color: #000 !important; border: 2px solid #007bff !important; border-radius: 12px; font-weight: 600 !important; }
    div[data-testid="stFormSubmitButton"] button { width: 100%; background-color: #007bff; color: white; font-weight: 800; border-radius: 10px; padding: 10px; }
    .info-card { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 8px solid #6f42c1; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-top: 15px; }
    .violation { background-color: #ff4b4b; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 800; margin-bottom: 10px; }
    .data-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f1f3f5; font-size: 15px; }
    .badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def load_db(filename):
    if os.path.exists(filename):
        return pd.read_csv(filename, dtype=str)
    return None

def extract_pure_jibun(addr):
    if pd.isna(addr): return ""
    matches = re.findall(r'\b\d+(?:-\d+)?\b', str(addr).replace("산", "").strip())
    if matches:
        parts = matches[-1].split('-')
        if len(parts) == 2: return f"{int(parts[0])}-{int(parts[1])}"
        else: return str(int(parts[0]))
    return ""

st.markdown('### 🏢 원탑 건축물대장 조회')

master = load_db("max_master.csv.gz")
floor = load_db("max_floor.csv.gz")
unit = load_db("max_unit.csv.gz")

with st.form("search_form"):
    query = st.text_input("📍 지번 입력 (예: 망포동 6-11 또는 6-11)")
    submitted = st.form_submit_button("🔍 검색")

if submitted:
    if master is None:
        st.error("🚨 데이터가 없습니다. 깃허브에 'max_master.csv.gz' 파일이 있는지 확인하세요.")
        st.stop()
        
    q_jibun = extract_pure_jibun(query)
    q_dong = re.sub(r'[0-9-\s]', '', query)
    
    # 지번 매칭 및 동 이름 포함 확인
    mask = (master['검색용지번'] == q_jibun)
    if q_dong: mask &= master['대지위치'].fillna('').str.contains(q_dong, na=False)
    
    res = master[mask]
    
    if not res.empty:
        item = res.iloc[0]
        pk = str(item.get('관리건축물대장PK', ''))
        
        if str(item.get('위반건축물여부', '')) in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
            st.markdown('<div class="violation">🚨 위반건축물 확인 필요 🚨</div>', unsafe_allow_html=True)

        st.info(f"📍 **{item.get('대지위치')}**\n\n🏢 **용도:** {item.get('주용도코드명', '-')} | 📅 **승인:** {item.get('사용승인일', '-')}")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("층수", f"{item.get('지상층수', '0')}층")
        c2.metric("가구", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
        c3.metric("주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
        c4.metric("엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        if "집합" in str(item.get('대장구분코드명', '')):
            st.markdown("#### 🔑 호수별 전용면적")
            if unit is not None:
                u_list = unit[unit['관리건축물대장PK'] == pk]
                if not u_list.empty:
                    for _, u in u_list.sort_values(['층번호', '호명칭']).iterrows():
                        st.markdown(f'<div class="data-row"><span>{u.get("층번호", "")}층 {u.get("호명칭", "")}</span><span style="color:#007bff; font-weight:800;">{u.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                else:
                    st.write("상세 정보 없음")
        else:
            st.markdown("#### 🏢 층별 상세 현황")
            if floor is not None:
                f_list = floor[floor['관리건축물대장PK'] == pk]
                if not f_list.empty:
                    for _, f in f_list.sort_values('층번호').iterrows():
                        etc = str(f.get('기타용도', ''))
                        g = re.search(r'(\d+)\s*(가구|호)', etc)
                        badge = f' <span class="badge">{g.group(0)}</span>' if g else ""
                        st.markdown(f'<div class="data-row"><span>{f.get("층번호", "")}층 {f.get("주용도코드명", "")}</span>{badge}<span style="color:#007bff; font-weight:800;">{f.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                else:
                    st.write("상세 정보 없음")
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.error("검색 결과가 없습니다. 지번을 다시 확인해주세요.")
