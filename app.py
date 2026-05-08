import streamlit as st
import pandas as pd
import re
import os
import gc

st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

# --- UI 스타일 (이전의 이쁜 디자인 유지) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #111111 !important;
        border: 2px solid #007bff !important; border-radius: 12px; padding: 14px !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white; font-weight: 800; border-radius: 10px; padding: 12px;
    }
    .info-card {
        background-color: #ffffff; padding: 25px; border-radius: 15px;
        border-left: 8px solid #6f42c1; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 30px;
    }
    .data-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f1f3f5; }
    .label { font-weight: 700; color: #6f42c1; }
    .value { font-weight: 800; color: #007bff; }
    .badge { background-color: #ffc107; color: #212529; font-size: 13px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# --- 핵심 로직 ---
def normalize_num(val):
    try:
        return str(int(re.sub(r'[^0-9]', '', str(val))))
    except:
        return "0"

@st.cache_data(show_spinner="주택 정보를 분석 중입니다...")
def search_house(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []

    # 1. 검색어에서 동 이름과 번지 분리
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()
    nums = re.findall(r'\d+', query_str)
    q_main = str(int(nums[0])) if len(nums) > 0 else ""
    q_sub = str(int(nums[1])) if len(nums) > 1 else "0"

    results = []
    # 2. 마스터 파일에서 일반 대지(대지구분코드 1) 및 주택 위주로 검색
    for chunk in pd.read_csv(f_master, dtype=str, chunksize=50000):
        chunk.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip() for c in chunk.columns]
        
        # '산' 주소 제외 (코드 1만 허용) 및 숫자 매칭
        chunk['t_main'] = chunk['번'].apply(normalize_num)
        chunk['t_sub'] = chunk['지'].apply(normalize_num)
        
        mask = (chunk['t_main'] == q_main) & (chunk['t_sub'] == q_sub) & (chunk['대지구분코드'] == '1')
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
        
        # 주택 위주 필터링 (주용도에 '주택'이 포함된 것)
        res = chunk[mask]
        if not res.empty:
            results.extend(res.to_dict('records'))
    
    return results

@st.cache_data
def get_building_details(pks):
    # 층별 정보 및 호수별 면적 로드
    f_floor = "suwon_floor_info.csv.gz"
    f_status = "suwon_unit_status.csv.gz"
    f_area = "suwon_unit_area.csv.gz"
    
    df_f = pd.read_csv(f_floor, dtype=str) if os.path.exists(f_floor) else pd.DataFrame()
    df_s = pd.read_csv(f_status, dtype=str) if os.path.exists(f_status) else pd.DataFrame()
    df_a = pd.read_csv(f_area, dtype=str) if os.path.exists(f_area) else pd.DataFrame()
    
    for df in [df_f, df_s, df_a]:
        if not df.empty:
            df.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip() for c in df.columns]
            
    return df_f[df_f['관리건축물대장PK'].isin(pks)], df_s[df_s['관리건축물대장PK'].isin(pks)], df_a[df_a['관리건축물대장PK'].isin(pks)]

# --- 메인 화면 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 세류동 254 또는 254-9")
    submitted = st.form_submit_button("🔍 주택 정보 추출")

if submitted:
    if not query:
        st.warning("주소를 입력해주세요.")
    else:
        res = search_house(query)
        if res:
            pks = [r['관리건축물대장PK'] for r in res]
            floor_df, status_df, area_df = get_building_details(pks)
            
            for item in res:
                pk = item['관리건축물대장PK']
                st.markdown(f"### 📌 {item.get('건물명', '건축물 정보')}")
                st.info(f"📍 **지번:** {item.get('대지위치', '-')}  |  🛣️ **도로명:** {item.get('도로명대지위치', '-')}")
                
                # 상단 핵심 메트릭
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{item.get('지상층수', '0')}층")
                c2.metric("가구수", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
                c3.metric("주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
                c4.metric("엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                # 상세 정보 표시 (집합 vs 일반)
                if "집합" in str(item.get('대장구분코드명', '')):
                    st.markdown("#### 🔑 호수별 전용면적")
                    t_s = status_df[status_df['관리건축물대장PK'] == pk]
                    t_a = area_df[(area_df['관리건축물대장PK'] == pk) & (area_df.get('전유공용구분코드', '1') == '1')]
                    if not t_s.empty and not t_a.empty:
                        merged = pd.merge(t_s, t_a, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        for _, u in merged.drop_duplicates(['층번호', '호명칭']).sort_values(['층번호', '호명칭']).iterrows():
                            st.markdown(f'<div class="data-row"><span class="label">{u.get("층번호")}층 {u.get("호명칭")}</span><span class="value">{u.get("면적(㎡)")} ㎡</span></div>', unsafe_allow_html=True)
                else:
                    st.markdown("#### 🏢 층별 상세 현황")
                    t_f = floor_df[floor_df['관리건축물대장PK'] == pk]
                    if not t_f.empty:
                        for _, f in t_f.sort_values('층번호').iterrows():
                            etc = str(f.get('기타용도', ''))
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            badge = f'<span class="badge">{g.group(0)}</span>' if g else ""
                            st.markdown(f'<div class="data-row"><span class="label">{f.get("층번호")}층 {f.get("주용도코드명")}{badge}</span><span class="value">{f.get("면적(㎡)")} ㎡</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            gc.collect()
        else:
            st.error("검색 결과가 없습니다. 지번이 정확한지 확인해주세요.")
