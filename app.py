import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 시인성 극대화 디자인 (글자 크기 대폭 확대 및 박스 UI)
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    
    /* 제목 및 입력창 */
    .main-title { font-size: 42px; font-weight: 900; color: #111; margin-bottom: 35px; text-align: center; }
    
    div[data-testid="stTextInput"] input {
        border: 4px solid #0056b3 !important; border-radius: 15px; 
        padding: 25px !important; font-size: 28px !important; font-weight: 800;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #0056b3 !important; color: white !important;
        font-weight: 900; border-radius: 15px; padding: 20px; border: none; font-size: 30px;
    }

    /* 결과 안내 텍스트 (박스 제거 버전) */
    .result-summary { font-size: 30px; font-weight: 900; color: #d9480f; text-align: center; margin: 30px 0; }

    /* 주소 카드 */
    .address-card {
        background: white; padding: 35px; border-radius: 20px;
        border-left: 15px solid #0056b3; margin-bottom: 35px; box-shadow: 0 10px 20px rgba(0,0,0,0.08);
    }
    .address-card h3 { font-size: 38px; margin-bottom: 15px; font-weight: 900; color: #222; }
    .address-card p { font-size: 24px; line-height: 1.6; margin: 8px 0; color: #444; }

    /* 4대 지표 네모 박스 */
    .metric-container { display: flex; justify-content: space-between; gap: 15px; margin-bottom: 30px; }
    .metric-card {
        flex: 1; background: white; padding: 30px 10px; border-radius: 18px;
        border: 2px solid #e9ecef; text-align: center; box-shadow: 0 6px 12px rgba(0,0,0,0.05);
    }
    .metric-label { font-size: 22px; font-weight: 700; color: #6c757d; margin-bottom: 12px; }
    .metric-value { font-size: 34px; font-weight: 900; color: #0056b3; }

    /* 주용도 / 사용승인일 박스 */
    .info-box-container { display: flex; gap: 15px; margin-bottom: 40px; }
    .info-box {
        flex: 1; background: #e9ecef; padding: 22px; border-radius: 15px;
        text-align: center; border: 2px solid #ced4da;
    }
    .info-label { font-size: 22px; font-weight: 800; color: #495057; margin-right: 15px; }
    .info-value { font-size: 26px; font-weight: 900; color: #212529; }

    /* 상세 현황 테이블 */
    .table-title { font-size: 30px; font-weight: 900; color: #212529; margin: 0 0 20px 0; }
    .custom-table { width: 100%; border-collapse: collapse; background: white; border-radius: 15px; overflow: hidden; font-size: 22px; }
    .custom-table th { background: #343a40; color: white; padding: 20px; text-align: left; font-size: 24px; }
    .custom-table td { padding: 20px; border-bottom: 1px solid #f1f3f5; color: #333; }
    .row-floor { font-weight: 900; color: #0056b3; }
</style>
""", unsafe_allow_html=True)

# --- 2. 검색 엔진 최적화 (필요한 칼럼만 읽어서 속도 UP) ---
def force_int(v):
    try:
        n = re.sub(r'[^0-9]', '', str(v))
        return int(n) if n else -1
    except: return -1

def clean_txt(c):
    return re.sub(r'[^a-zA-Z0-9가-힣()㎡]', '', str(c)).strip()

def natural_sort(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

@st.cache_data(show_spinner="수원시 전체 대장을 고속 검색 중입니다...")
def search_building(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []

    nums = re.findall(r'\d+', query_str)
    if not nums: return []
    q_main = force_int(nums[0])
    q_sub = force_int(nums[1]) if len(nums) > 1 else 0
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    # 필수 칼럼만 골라 읽기 (속도 향상 핵심)
    cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    found = []
    for chunk in pd.read_csv(f_master, dtype=str, chunksize=70000, usecols=cols):
        chunk.columns = [clean_txt(c) for c in chunk.columns]
        chunk['int_main'] = chunk['번'].apply(force_int)
        chunk['int_sub'] = chunk['지'].apply(force_int)
        
        mask = (chunk['int_main'] == q_main) & (chunk['int_sub'] == q_sub)
        if q_dong: mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty: found.extend(res.to_dict('records'))
    return found

@st.cache_data
def load_all_details(pks):
    f_list, s_list, a_list = [], [], []
    
    # 층별 정보 (구조 정보 추가 추출)
    if os.path.exists("suwon_floor_info.csv.gz"):
        f_cols = ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)', '구조코드명']
        for chunk in pd.read_csv("suwon_floor_info.csv.gz", dtype=str, chunksize=70000, usecols=f_cols):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: f_list.extend(res.to_dict('records'))
            
    # 집합건축물 정보
    if os.path.exists("suwon_unit_status.csv.gz") and os.path.exists("suwon_unit_area.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_status.csv.gz", dtype=str, chunksize=70000):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: s_list.extend(res.to_dict('records'))
        for chunk in pd.read_csv("suwon_unit_area.csv.gz", dtype=str, chunksize=70000):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[(chunk['관리건축물대장PK'].isin(pks)) & (chunk.get('전유공용구분코드', '1') == '1')]
            if not res.empty: a_list.extend(res.to_dict('records'))
            
    return f_list, s_list, a_list

# --- 3. UI 렌더링 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 망포동 6-11 / 세류동 254")
    submitted = st.form_submit_button("🔍 정확한 정보 찾기")

if submitted and query:
    items = search_building(query)
    if items:
        # ✅ "찾았습니다" 박스 제거 -> 깔끔한 텍스트로 변경
        st.markdown(f'<p class="result-summary">✅ {len(items)}개의 건축물을 찾았습니다.</p>', unsafe_allow_html=True)
        
        pks = [i['관리건축물대장PK'] for i in items]
        f_data, s_data, a_data = load_all_details(pks)
        
        for idx, b in enumerate(items):
            pk = b['관리건축물대장PK']
            name = str(b.get('건물명', '')).replace('nan', '').strip()
            dong = str(b.get('동명칭', '')).replace('nan', '').strip()
            title = f"{name} {f'({dong})' if dong else ''}".strip() or f"건축물 {idx+1}"

            # 1. 주소 및 건물명 카드
            st.markdown(f'<div class="address-card">', unsafe_allow_html=True)
            st.markdown(f"<h3>📌 {title}</h3>", unsafe_allow_html=True)
            st.markdown(f"<p><b>📍 지번:</b> {b.get('대지위치', '-')}</p>", unsafe_allow_html=True)
            st.markdown(f"<p><b>🛣️ 도로명:</b> <span style='color:#0056b3; font-weight:900;'>{b.get('도로명대지위치', '정보 없음')}</span></p>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            def get_val(v):
                try: return int(float(str(v).replace('nan', '0') or 0))
                except: return 0

            # 2. 4대 지표 네모 박스
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-card"><div class="metric-label">층수</div><div class="metric-value">{b.get('지상층수', '0')}층</div></div>
                <div class="metric-card"><div class="metric-label">세대/가구</div><div class="metric-value">{get_val(b.get('가구수(가구)')) + get_val(b.get('세대수(세대)'))}호</div></div>
                <div class="metric-card"><div class="metric-label">주차대수</div><div class="metric-value">{get_val(b.get('옥내자주식대수(대)')) + get_val(b.get('옥외자주식대수(대)'))}대</div></div>
                <div class="metric-card"><div class="metric-label">엘리베이터</div><div class="metric-value">{get_val(b.get('승용승강기수')) + get_val(b.get('비상용승강기수'))}대</div></div>
            </div>
            """, unsafe_allow_html=True)

            # 3. 주용도 / 사용승인일 박스
            st.markdown(f"""
            <div class="info-box-container">
                <div class="info-box"><span class="info-label">🏢 주용도</span><span class="info-value">{b.get('주용도코드명', '-')}</span></div>
                <div class="info-box"><span class="info-label">📅 사용승인일</span><span class="info-value">{b.get('사용승인일', '-')}</span></div>
            </div>
            """, unsafe_allow_html=True)

            # 4. 강화된 층별 상세 현황 표
            st.markdown('<p class="table-title">📊 층별 상세 현황 (구조 및 면적)</p>', unsafe_allow_html=True)
            
            if "집합" in str(b.get('대장구분코드명', '')):
                my_s = [s for s in s_data if s['관리건축물대장PK'] == pk]
                my_a = [a for a in a_data if a['관리건축물대장PK'] == pk]
                if my_s and my_a:
                    merged = pd.merge(pd.DataFrame(my_s), pd.DataFrame(my_a), on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                    merged['sort'] = merged['호명칭'].apply(natural_sort)
                    merged = merged.sort_values('sort').drop_duplicates(['층번호', '호명칭'])
                    
                    tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                    for _, r in merged.iterrows():
                        tbl += f'<tr><td class="row-floor">{r.get("층번호")}층 {r.get("호명칭")}</td><td>{r.get("주용도코드명", "-")}</td><td style="text-align:right; font-weight:900; color:#d9480f;">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                    tbl += '</table>'
                    st.markdown(tbl, unsafe_allow_html=True)
            else:
                my_f = [f for f in f_data if f['관리건축물대장PK'] == pk]
                if my_f:
                    f_df = pd.DataFrame(my_f)
                    f_df['sort'] = f_df['층번호'].apply(natural_sort)
                    f_df = f_df.sort_values('sort')
                    
                    # '구조' 항목 추가하여 정보 강화
                    tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th>구조</th><th style="text-align:center;">가구/호</th><th style="text-align:right;">면적</th></tr>'
                    for _, row in f_df.iterrows():
                        etc = str(row.get('기타용도', ''))
                        g = re.search(r'(\d+)\s*(가구|호)', etc)
                        u_info = g.group(0) if g else "-"
                        tbl += f'<tr><td class="row-floor">{row.get("층번호")}층</td><td>{row.get("주용도코드명", "-")}</td><td>{row.get("구조코드명", "-")}</td><td style="text-align:center; font-weight:800;">{u_info}</td><td style="text-align:right; font-weight:900; color:#d9480f;">{row.get("면적(㎡)", "-")} ㎡</td></tr>'
                    tbl += '</table>'
                    st.markdown(tbl, unsafe_allow_html=True)
            
            st.markdown("<br><br>", unsafe_allow_html=True)
        gc.collect()
    else:
        st.error("입력하신 지번을 찾을 수 없습니다. (데이터 병합 상태를 확인해 주세요)")
