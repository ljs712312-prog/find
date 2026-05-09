import streamlit as st
import pandas as pd
import re
import os
import gc

# ==========================================
# 1. 원탑 실무용 프리미엄 디자인 (글자 크기 +8pt 확대)
# ==========================================
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
    .stApp { background-color: #f0f2f6; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    
    /* 타이틀 및 입력창 */
    .main-title { font-size: 44px; font-weight: 900; color: #1e1e1e; margin-bottom: 30px; text-align: center; }
    div[data-testid="stTextInput"] input {
        border: 4px solid #0056b3 !important; border-radius: 15px; 
        padding: 25px !important; font-size: 30px !important; font-weight: 800;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #0056b3 !important; color: white !important;
        font-weight: 900; border-radius: 15px; padding: 20px; border: none; font-size: 32px;
    }

    /* 결과 요약 (박스 제거, 깔끔한 텍스트) */
    .result-summary { font-size: 32px; font-weight: 900; color: #d9480f; text-align: center; margin: 35px 0; }

    /* 메인 정보 대시보드 (준석님 요청 반영) */
    .dashboard-container {
        background: white; border-radius: 25px; padding: 35px;
        box-shadow: 0 12px 24px rgba(0,0,0,0.1); border-top: 15px solid #0056b3; margin-bottom: 40px;
    }
    .bld-header { font-size: 40px; font-weight: 900; color: #222; margin-bottom: 20px; }
    .bld-address { font-size: 24px; color: #555; margin-bottom: 30px; line-height: 1.6; }

    /* 핵심 6대 지표 그리드 레이아웃 */
    .grid-container { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 25px; }
    .grid-item {
        background: #f8f9fa; padding: 25px; border-radius: 20px; border: 2px solid #e9ecef;
        text-align: center; display: flex; flex-direction: column; justify-content: center;
    }
    .grid-label { font-size: 20px; font-weight: 700; color: #6c757d; margin-bottom: 10px; }
    .grid-value { font-size: 34px; font-weight: 900; color: #0056b3; }
    
    /* 주용도 및 승인일 (강조형 하단 박스) */
    .sub-info-container { display: flex; gap: 15px; }
    .sub-info-box {
        flex: 1; background: #343a40; color: white; padding: 22px; border-radius: 18px;
        text-align: center; display: flex; align-items: center; justify-content: center;
    }
    .sub-label { font-size: 20px; font-weight: 700; margin-right: 15px; color: #adb5bd; }
    .sub-value { font-size: 24px; font-weight: 800; color: #ffc107; }

    /* 상세 현황 테이블 */
    .table-title { font-size: 32px; font-weight: 900; color: #212529; margin-bottom: 20px; padding-left: 10px; border-left: 10px solid #0056b3; }
    .custom-table { width: 100%; border-collapse: collapse; background: white; border-radius: 20px; overflow: hidden; font-size: 22px; }
    .custom-table th { background: #343a40; color: white; padding: 22px; text-align: left; }
    .custom-table td { padding: 22px; border-bottom: 1px solid #f1f3f5; }
    .row-floor { font-weight: 900; color: #0056b3; }
    .row-area { font-weight: 900; color: #d9480f; text-align: right; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 고속 엔진 및 안전 로직 (에러 원천 차단)
# ==========================================
def force_int(v):
    try: return int(re.sub(r'[^0-9]', '', str(v)))
    except: return 0

def clean_txt(c):
    return re.sub(r'[^a-zA-Z0-9가-힣()㎡]', '', str(c)).strip()

def natural_sort(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

@st.cache_data(show_spinner="수원시 데이터를 광속으로 분석하고 있습니다...")
def fast_search(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []

    nums = re.findall(r'\d+', query_str)
    if not nums: return []
    q_main, q_sub = force_int(nums[0]), (force_int(nums[1]) if len(nums) > 1 else 0)
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    # 필요한 칼럼만 지정하여 속도 최적화
    cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    found = []
    # usecols 람다를 사용하여 파일에 실제로 존재하는 칼럼만 안전하게 로드
    for chunk in pd.read_csv(f_master, dtype=str, chunksize=100000, usecols=lambda x: clean_txt(x) in cols):
        chunk.columns = [clean_txt(c) for c in chunk.columns]
        chunk['int_main'] = chunk['번'].apply(force_int)
        chunk['int_sub'] = chunk['지'].apply(force_int)
        
        mask = (chunk['int_main'] == q_main) & (chunk['int_sub'] == q_sub)
        if q_dong: mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty: found.extend(res.to_dict('records'))
    return found

@st.cache_data
def load_details(pks):
    f_list, s_list, a_list = [], [], []
    
    # 층별 정보 (ValueError 방지를 위해 칼럼 존재 여부 체크)
    if os.path.exists("suwon_floor_info.csv.gz"):
        f_cols = ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']
        for chunk in pd.read_csv("suwon_floor_info.csv.gz", dtype=str, chunksize=100000, usecols=lambda x: clean_txt(x) in f_cols):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: f_list.extend(res.to_dict('records'))
            
    # 집합건축물 정보 로드
    if os.path.exists("suwon_unit_status.csv.gz") and os.path.exists("suwon_unit_area.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_status.csv.gz", dtype=str, chunksize=100000, usecols=lambda x: clean_txt(x) in ['관리건축물대장PK', '호명칭', '층번호']):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: s_list.extend(res.to_dict('records'))
        for chunk in pd.read_csv("suwon_unit_area.csv.gz", dtype=str, chunksize=100000, usecols=lambda x: clean_txt(x) in ['관리건축물대장PK', '호명칭', '층번호', '전유공용구분코드', '면적(㎡)']):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[(chunk['관리건축물대장PK'].isin(pks)) & (chunk.get('전유공용구분코드', '1') == '1')]
            if not res.empty: a_list.extend(res.to_dict('records'))
            
    return f_list, s_list, a_list

# ==========================================
# 3. 화면 UI 구현 (대시보드 스타일)
# ==========================================
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력 (예: 망포동 6-11)", placeholder="주소를 입력하세요")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted and query:
    items = fast_search(query)
    if items:
        st.markdown(f'<p class="result-summary">✅ {len(items)}개의 건축물을 찾았습니다.</p>', unsafe_allow_html=True)
        
        pks = [i['관리건축물대장PK'] for i in items]
        f_data, s_data, a_data = load_details(pks)
        
        for idx, b in enumerate(items):
            pk = b['관리건축물대장PK']
            name = str(b.get('건물명', '')).replace('nan', '').strip()
            dong = str(b.get('동명칭', '')).replace('nan', '').strip()
            final_title = f"📌 {name} {f'({dong})' if dong else ''}".strip() or f"📌 건축물 {idx+1}"

            # 🛑 [핵심 수정] 모든 정보를 하나의 대시보드 박스에 통합
            st.markdown(f"""
            <div class="dashboard-container">
                <div class="bld-header">{final_title}</div>
                <div class="bld-address">
                    📍 <b>지번:</b> {b.get('대지위치', '-')}<br>
                    🛣️ <b>도로명:</b> <span style="color:#0056b3;">{b.get('도로명대지위치', '정보 없음')}</span>
                </div>
                
                <div class="grid-container">
                    <div class="grid-item"><div class="grid-label">층수</div><div class="grid-value">{b.get('지상층수', '0')}층</div></div>
                    <div class="grid-item"><div class="grid-label">세대/가구</div><div class="grid-value">{force_int(b.get('가구수(가구)')) + force_int(b.get('세대수(세대)'))}호</div></div>
                    <div class="grid-item"><div class="grid-label">주차대수</div><div class="grid-value">{force_int(b.get('옥내자주식대수(대)')) + force_int(b.get('옥외자주식대수(대)'))}대</div></div>
                    <div class="grid-item"><div class="grid-label">엘리베이터</div><div class="grid-value">{force_int(b.get('승용승강기수')) + force_int(b.get('비상용승강기수'))}대</div></div>
                </div>

                <div class="sub-info-container">
                    <div class="sub-info-box"><span class="sub-label">🏢 주용도</span><span class="sub-value">{b.get('주용도코드명', '-')}</span></div>
                    <div class="sub-info-box"><span class="sub-label">📅 사용승인일</span><span class="sub-value">{b.get('사용승인일', '-')}</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 상세 테이블 섹션
            st.markdown('<p class="table-title">📊 층별 상세 현황 (용도 및 면적)</p>', unsafe_allow_html=True)
            
            if "집합" in str(b.get('대장구분코드명', '')):
                my_s = [s for s in s_data if s['관리건축물대장PK'] == pk]
                my_a = [a for a in a_data if a['관리건축물대장PK'] == pk]
                if my_s and my_a:
                    merged = pd.merge(pd.DataFrame(my_s), pd.DataFrame(my_a), on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                    merged['sort'] = merged['호명칭'].apply(natural_sort)
                    merged = merged.sort_values('sort').drop_duplicates(['층번호', '호명칭'])
                    
                    tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                    for _, r in merged.iterrows():
                        tbl += f'<tr><td class="row-floor">{r.get("층번호")}층 {r.get("호명칭")}</td><td>{r.get("주용도코드명", "-")}</td><td class="row-area">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                    st.markdown(tbl + '</table>', unsafe_allow_html=True)
            else:
                my_f = [f for f in f_data if f['관리건축물대장PK'] == pk]
                if my_f:
                    f_df = pd.DataFrame(my_f)
                    f_df['sort'] = f_df['층번호'].apply(natural_sort)
                    f_df = f_df.sort_values('sort')
                    
                    tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th style="text-align:center;">가구/호</th><th style="text-align:right;">면적</th></tr>'
                    for _, row in f_df.iterrows():
                        etc = str(row.get('기타용도', ''))
                        g = re.search(r'(\d+)\s*(가구|호)', etc)
                        tbl += f'<tr><td class="row-floor">{row.get("층번호")}층</td><td>{row.get("주용도코드명", "-")}</td><td style="text-align:center; font-weight:800;">{g.group(0) if g else "-"}</td><td class="row-area">{row.get("면적(㎡)", "-")} ㎡</td></tr>'
                    st.markdown(tbl + '</table>', unsafe_allow_html=True)
            
            st.markdown("<br><hr style='border: 1px solid #ddd;'><br>", unsafe_allow_html=True)
        gc.collect()
    else:
        st.error("입력하신 지번을 찾을 수 없습니다. (망포동 6-11 등 정확한 주소인지 확인하세요)")
