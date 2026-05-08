import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 디자인 (원탑 부동산 전용 스타일)
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; color: #1e1e1e !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    
    /* 검색창 시인성 강화 */
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #111111 !important;
        border: 2px solid #007bff !important; border-radius: 12px; padding: 14px !important; font-weight: 600 !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white; font-weight: 800; border-radius: 10px; padding: 12px; border: none;
    }
    
    /* 카드 및 주소 박스 */
    .info-card {
        background-color: #ffffff; padding: 25px; border-radius: 15px;
        border-left: 8px solid #6f42c1; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 30px;
    }
    .address-box {
        background-color: #eef6ff; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid #d0e3ff;
    }
    .bld-header { font-size: 20px; font-weight: 800; color: #007bff; margin-top: 30px; margin-bottom: 10px; padding-bottom: 5px; border-bottom: 2px solid #007bff; }
    
    /* 상세 현황 테이블 */
    .custom-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }
    .custom-table th { background-color: #f1f3f5; padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6; color: #495057; font-weight: 700; }
    .custom-table td { padding: 10px; border-bottom: 1px solid #eee; }
    .row-floor { font-weight: 700; color: #6f42c1; }
    .row-area { font-weight: 800; color: #007bff; text-align: right; }
    .row-unit { font-weight: 800; color: #d9480f; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- 핵심 로직 ---
def clean_col(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

def to_int_str(val):
    try: return str(int(re.sub(r'[^0-9]', '', str(val))))
    except: return "0"

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

# --- 검색 엔진 (속도 향상을 위한 Chunk 검색 방식) ---
def find_matching_buildings(query_str):
    if not os.path.exists("suwon_building_master.csv.gz"): return []
    
    # 1. 입력값에서 지번 분리 (숫자만 정확히 추출)
    nums = re.findall(r'\d+', query_str)
    q_main = str(int(nums[0])) if len(nums) > 0 else ""
    q_sub = str(int(nums[1])) if len(nums) > 1 else "0"
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    matched_results = []
    # 파일을 5만 줄씩 쪼개서 읽으며 매칭 (메모리 보호 & 속도)
    for chunk in pd.read_csv("suwon_building_master.csv.gz", dtype=str, chunksize=50000):
        chunk.columns = [clean_col(c) for c in chunk.columns]
        # '0006' -> '6'으로 변환하여 지번 매칭
        chunk['n_main'] = chunk['번'].fillna('0').apply(to_int_str)
        chunk['n_sub'] = chunk['지'].fillna('0').apply(to_int_str)
        
        mask = (chunk['n_main'] == q_main) & (chunk['n_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            matched_results.extend(res.to_dict('records'))
            
    return matched_results

def fetch_details(pk_list):
    # 층별/호별 정보도 전체 로드하지 않고 PK가 맞는 줄만 필터링해서 읽음
    details = {"floor": [], "status": [], "area": []}
    
    if os.path.exists("suwon_floor_info.csv.gz"):
        for chunk in pd.read_csv("suwon_floor_info.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_col(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pk_list)]
            if not res.empty: details["floor"].extend(res.to_dict('records'))
            
    if os.path.exists("suwon_unit_status.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_status.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_col(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pk_list)]
            if not res.empty: details["status"].extend(res.to_dict('records'))
            
    if os.path.exists("suwon_unit_area.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_area.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_col(c) for c in chunk.columns]
            # 전용면적(1)만 필터링
            res = chunk[(chunk['관리건축물대장PK'].isin(pk_list)) & (chunk.get('전유공용구분코드', '1') == '1')]
            if not res.empty: details["area"].extend(res.to_dict('records'))
            
    return details

# --- 메인 화면 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 세류동 254 / 망포동 6-11")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    if query:
        with st.spinner("정보를 실시간 분석 중입니다..."):
            buildings = find_matching_buildings(query)
            
            if buildings:
                pk_list = [b['관리건축물대장PK'] for b in buildings]
                details = fetch_details(pk_list)
                
                st.success(f"✅ 총 {len(buildings)}개의 건축물을 찾았습니다.")
                
                for idx, item in enumerate(buildings):
                    pk = item['관리건축물대장PK']
                    b_name = str(item.get('건물명', '')).replace('nan', '').strip()
                    d_name = str(item.get('동명칭', '')).replace('nan', '').strip()
                    title = f"{b_name} {f'({d_name})' if d_name else ''}".strip() or f"건축물 {idx+1}"

                    st.markdown(f'<div class="bld-header">📌 {title}</div>', unsafe_allow_html=True)
                    st.markdown(f"""
                    <div class="address-box">
                        <div style="font-size: 14px; color: #555;">📍 지번: {item.get('대지위치', '-')}</div>
                        <div style="font-size: 15px; color: #007bff; font-weight: 800; margin-top: 5px;">🛣️ 도로명: {item.get('도로명대지위치', '정보 없음')}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("층수", f"{item.get('지상층수', '0')}층")
                    c2.metric("가구수", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
                    c3.metric("주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
                    c4.metric("엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

                    st.markdown('<div class="info-card">', unsafe_allow_html=True)
                    st.write(f"🏢 **주용도:** {item.get('주용도코드명', '-')}  |  📅 **사용승인:** {item.get('사용승인일', '-')}")
                    
                    # 층별 상세 현황 (표 형식)
                    st.markdown("<br><b>📊 층별 상세 현황</b>", unsafe_allow_html=True)
                    
                    # 집합건축물
                    if "집합" in str(item.get('대장구분코드명', '')):
                        t_s = [s for s in details["status"] if s['관리건축물대장PK'] == pk]
                        t_a = [a for a in details["area"] if a['관리건축물대장PK'] == pk]
                        if t_s and t_a:
                            s_df = pd.DataFrame(t_s)
                            a_df = pd.DataFrame(t_a)
                            merged = pd.merge(s_df, a_df, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                            merged['sort_key'] = merged['호명칭'].apply(natural_sort_key)
                            merged = merged.sort_values('sort_key').drop_duplicates(['층번호', '호명칭'])
                            
                            tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                            for _, u in merged.iterrows():
                                tbl += f'<tr><td class="row-floor">{u.get("층번호")}층 {u.get("호명칭")}</td><td>{u.get("주용도코드명", "-")}</td><td class="row-area">{u.get("면적(㎡)", "-")} ㎡</td></tr>'
                            tbl += '</table>'
                            st.markdown(tbl, unsafe_allow_html=True)
                    # 일반건축물
                    else:
                        t_f = [f for f in details["floor"] if f['관리건축물대장PK'] == pk]
                        if t_f:
                            f_df = pd.DataFrame(t_f)
                            f_df['sort_key'] = f_df['층번호'].apply(natural_sort_key)
                            f_df = f_df.sort_values('sort_key')
                            
                            tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th style="text-align:center;">가구/호</th><th style="text-align:right;">면적</th></tr>'
                            for _, f in f_df.iterrows():
                                etc = str(f.get('기타용도', ''))
                                g = re.search(r'(\d+)\s*(가구|호)', etc)
                                unit = g.group(0) if g else "-"
                                tbl += f'<tr><td class="row-floor">{f.get("층번호")}층</td><td>{f.get("주용도코드명", "-")}</td><td class="row-unit">{unit}</td><td class="row-area">{f.get("면적(㎡)", "-")} ㎡</td></tr>'
                            tbl += '</table>'
                            st.markdown(tbl, unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.error("결과를 찾을 수 없습니다. 지번을 정확히 입력했는지 확인해주세요.")
