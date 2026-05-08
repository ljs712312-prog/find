import streamlit as st
import pandas as pd
import re
import os
import gc

st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

# --- UI 스타일 ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    div[data-testid="stTextInput"] input { border: 2px solid #007bff !important; border-radius: 12px; padding: 14px !important; }
    div[data-testid="stFormSubmitButton"] button { width: 100%; background-color: #007bff; color: white; font-weight: 800; border-radius: 10px; padding: 12px; }
    .info-card { background-color: #ffffff; padding: 25px; border-radius: 15px; border-left: 8px solid #6f42c1; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 30px; }
    .data-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f1f3f5; }
    .badge { background-color: #ffc107; color: #212529; font-size: 13px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# --- 정밀 검색 로직 ---
def to_int(v):
    try: return str(int(re.sub(r'[^0-9]', '', str(v))))
    except: return "0"

@st.cache_data(show_spinner="정밀 검색 중...")
def strict_search(query_str):
    if not os.path.exists("suwon_building_master.csv.gz"): return []
    
    # 1. 입력값에서 본번-부번 분리 (예: 254-2 -> main: 254, sub: 2)
    nums = re.findall(r'\d+', query_str)
    q_main = str(int(nums[0])) if len(nums) > 0 else ""
    q_sub = str(int(nums[1])) if len(nums) > 1 else "0"
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    results = []
    for chunk in pd.read_csv("suwon_building_master.csv.gz", dtype=str, chunksize=50000):
        chunk.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip() for c in chunk.columns]
        
        # 2. 데이터의 0006 -> 6 변환 후 '정확히' 일치하는지 비교
        chunk['n_main'] = chunk['번'].apply(to_int)
        chunk['n_sub'] = chunk['지'].apply(to_int)
        
        # [핵심 필터] 본번과 부번이 모두 일치해야 함
        mask = (chunk['n_main'] == q_main) & (chunk['n_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            results.extend(res.to_dict('records'))
    return results

# --- 메인 화면 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 세류동 254")
    submitted = st.form_submit_button("🔍 정확한 정보 찾기")

if submitted:
    if query:
        res = strict_search(query)
        if res:
            for item in res:
                st.markdown(f"### 📌 {item.get('건물명', '건축물 정보')} ({item.get('동명칭', '본동')})")
                st.info(f"📍 **지번:** {item.get('대지위치')} | 🛣️ **도로명:** {item.get('도로명대지위치', '-')}")
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{item.get('지상층수', '0')}층")
                c2.metric("가구수", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
                c3.metric("주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
                c4.metric("엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")
                
                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                st.write("🏢 **주용도:**", item.get('주용도코드명', '-'), "| 📅 **사용승인:**", item.get('사용승인일', '-'))
                st.write("---")
                st.write("💡 *층별 상세 현황의 가구수는 대장에 기재된 경우에만 표시됩니다.*")
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("정확히 일치하는 지번이 없습니다. 주소를 다시 확인해주세요.")
