import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 실무용 디자인 (준석 님 확정 양식)
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; color: #1e1e1e !important; }
    .main-title { font-size: 24px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    
    /* 검색창 및 버튼 */
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; border: 2px solid #007bff !important;
        border-radius: 12px; padding: 14px !important; font-weight: 600 !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white;
        font-weight: 800; border-radius: 10px; padding: 12px; border: none;
    }

    /* 결과 레이아웃 */
    .address-box {
        background-color: #eef6ff; padding: 15px; border-radius: 10px;
        margin-bottom: 15px; border: 1px solid #d0e3ff;
    }
    .custom-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; background: #fff; }
    .custom-table th { background-color: #f1f3f5; padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6; }
    .custom-table td { padding: 10px; border-bottom: 1px solid #eee; }
    .row-floor { font-weight: 700; color: #6f42c1; }
    .row-area { font-weight: 800; color: #007bff; text-align: right; }
</style>
""", unsafe_allow_html=True)

# --- [초강력 정규화 로직] ---
def clean_txt(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

def to_pure_num(val):
    # '0006' -> '6' / '0011' -> '11' 로 변환하여 모든 형태의 지번 대응
    try:
        n = re.sub(r'[^0-9]', '', str(val))
        return str(int(n)) if n else "0"
    except:
        return "0"

def natural_sort(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

# --- [용도 무제한 검색 엔진] ---
@st.cache_data(show_spinner="상가 및 고시원 정보를 포함하여 망포동 데이터를 정밀 검색 중...")
def building_search_engine(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []

    # 입력값 분석
    nums = re.findall(r'\d+', query_str)
    q_main = to_pure_num(nums[0]) if len(nums) > 0 else "0"
    q_sub = to_pure_num(nums[1]) if len(nums) > 1 else "0"
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    results = []
    # 데이터 끝까지 완벽하게 뒤지기 위해 Chunk 단위 검색 수행
    for chunk in pd.read_csv(f_master, dtype=str, usecols=lambda x: clean_txt(x) in cols, chunksize=50000):
        chunk.columns = [clean_txt(c) for c in chunk.columns]
        
        # 데이터의 '0006'을 '6'으로 변환하여 매칭 (가장 확실한 방법)
        chunk['p_main'] = chunk['번'].fillna('0').apply(to_pure_num)
        chunk['p_sub'] = chunk['지'].fillna('0').apply(to_pure_num)
        
        mask = (chunk['p_main'] == q_main) & (chunk['p_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            results.extend(res.to_dict('records'))
    return results

@st.cache_data
def get_extended_details(pk_list):
    # 층별 정보 (상가/고시원 용도 포함)
    f_data = []
    if os.path.exists("suwon_floor_info.csv.gz"):
        f_cols = ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']
        for chunk in pd.read_csv("suwon_floor_info.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in f_cols, chunksize=50000):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pk_list)]
            if not res.empty: f_data.extend(res.to_dict('records'))
            
    # 집합건축물(상가/오피스텔) 호수별 면적
    s_data, a_data = [], []
    if os.path.exists("suwon_unit_status.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_status.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pk_list)]
            if not res.empty: s_data.extend(res.to_dict('records'))
    
    if os.path.exists("suwon_unit_area.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_area.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[(chunk['관리건축물대장PK'].isin(pk_list)) & (chunk.get('전유공용구분코드', '1') == '1')]
            if not res.empty: a_data.extend(res.to_dict('records'))
            
    return f_data, s_data, a_data

# 3. 화면 구현
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 망포동 6-11 / 세류동 254")
    submitted = st.form_submit_button("🔍 정확한 정보 찾기")

if submitted:
    if query:
        items = building_search_engine(query)
        if items:
            pks = [i['관리건축물대장PK'] for i in items]
            floors, units, areas = get_extended_details(pks)
            
            st.success(f"✅ 총 {len(items)}개의 건축물을 찾았습니다.")
            
            for idx, b in enumerate(items):
                pk = b['관리건축물대장PK']
                b_name = str(b.get('건물명', '')).replace('nan', '').strip()
                d_name = str(b.get('동명칭', '')).replace('nan', '').strip()
                title = f"{b_name} {f'({d_name})' if d_name else ''}".strip() or f"건축물 {idx+1}"

                st.markdown(f"### 📌 {title}")
                st.markdown(f"""
                <div class="address-box">
                    <div style="font-size: 14px; color: #555;">📍 지번: {b.get('대지위치', '-')}</div>
                    <div style="font-size: 14px; color: #007bff; font-weight: bold; margin-top: 5px;">🛣️ 도로명: {b.get('도로명대지위치', '정보 없음')}</div>
                </div>
                """, unsafe_allow_html=True)
                
                def s_int(v):
                    try: return int(float(str(v).replace('nan', '0') or 0))
                    except: return 0

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{b.get('지상층수', '0')}층")
                c2.metric("가구/세대", f"{s_int(b.get('가구수(가구)')) + s_int(b.get('세대수(세대)'))}호")
                c3.metric("주차대수", f"{s_int(b.get('옥내자주식대수(대)')) + s_int(b.get('옥외자주식대수(대)'))}대")
                c4.metric("엘베", f"{s_int(b.get('승용승강기수')) + s_int(b.get('비상용승강기수'))}대")

                st.write(f"🏢 **주용도:** {b.get('주용도코드명', '-')} | 📅 **사용승인:** {b.get('사용승인일', '-')}")

                # [개선] 집합건축물(상가/고시원)과 일반건축물(다가구)을 모두 지원하는 상세 표
                st.markdown("<br><b>📊 상세 현황 (용도 및 면적)</b>", unsafe_allow_html=True)
                
                if "집합" in str(b.get('대장구분코드명', '')):
                    my_u = [u for u in units if u['관리건축물대장PK'] == pk]
                    my_a = [a for a in areas if a['관리건축물대장PK'] == pk]
                    if my_u and my_a:
                        u_df, a_df = pd.DataFrame(my_u), pd.DataFrame(my_a)
                        merged = pd.merge(u_df, a_df, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged['sort'] = merged['호명칭'].apply(natural_sort)
                        merged = merged.sort_values('sort').drop_duplicates(['층번호', '호명칭'])
                        
                        tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                        for _, r in merged.iterrows():
                            tbl += f'<tr><td class="row-floor">{r.get("층번호")}층 {r.get("호명칭")}</td><td>{r.get("주용도코드명", "-")}</td><td class="row-area">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                else:
                    my_f = [f for f in floors if f['관리건축물대장PK'] == pk]
                    if my_f:
                        f_df = pd.DataFrame(my_f)
                        f_df['sort'] = f_df['층번호'].apply(natural_sort)
                        f_df = f_df.sort_values('sort')
                        
                        tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th style="text-align:center;">비고</th><th style="text-align:right;">면적</th></tr>'
                        for _, row in f_df.iterrows():
                            etc = str(row.get('기타용도', ''))
                            u_match = re.search(r'(\d+)\s*(가구|호)', etc)
                            u_info = u_match.group(0) if u_match else "-"
                            tbl += f'<tr><td class="row-floor">{row.get("층번호")}층</td><td>{row.get("주용도코드명", "-")}</td><td style="text-align:center;">{u_info}</td><td class="row-area">{row.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                st.write("---")
            gc.collect()
        else:
            st.error("정확히 일치하는 지번 결과가 없습니다. 망포동 6-11처럼 본번-부번을 정확히 입력해주세요.")
