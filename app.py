import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 시인성 극대화 디자인 (글씨체 대폭 확대)
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
    .stApp { background-color: #f1f3f5; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    
    /* 전체 글씨 크기 확대 (기존 대비 +8pt 이상) */
    .main-title { font-size: 36px; font-weight: 900; color: #1a1a1a; margin-bottom: 30px; text-align: center; }
    
    div[data-testid="stTextInput"] input {
        border: 3px solid #007bff !important; border-radius: 15px; padding: 20px !important; font-size: 24px !important; font-weight: 700;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff !important; color: white !important;
        font-weight: 900; border-radius: 15px; padding: 15px; border: none; font-size: 26px;
    }

    /* 상단 4대 지표 네모 박스 (글자 크게) */
    .metric-container { display: flex; justify-content: space-between; gap: 15px; margin-bottom: 25px; }
    .metric-card {
        flex: 1; background: white; padding: 25px 10px; border-radius: 18px;
        border: 2px solid #dee2e6; text-align: center; box-shadow: 0 6px 12px rgba(0,0,0,0.08);
    }
    .metric-label { font-size: 18px; font-weight: 700; color: #6c757d; margin-bottom: 12px; }
    .metric-value { font-size: 30px; font-weight: 900; color: #007bff; }

    /* 주용도 / 사용승인일 박스 */
    .info-box-container { display: flex; gap: 15px; margin-bottom: 25px; }
    .info-box {
        flex: 1; background: #e9ecef; padding: 18px; border-radius: 12px;
        text-align: center; border: 2px solid #ced4da;
    }
    .info-label { font-size: 18px; font-weight: 700; color: #495057; margin-right: 12px; }
    .info-value { font-size: 20px; font-weight: 900; color: #212529; }

    /* 주소 박스 */
    .address-card {
        background: white; padding: 25px; border-radius: 20px;
        border-left: 12px solid #007bff; margin-bottom: 30px; box-shadow: 0 6px 16px rgba(0,0,0,0.1);
    }
    .address-card h3 { font-size: 32px; margin-bottom: 15px; }
    .address-card p { font-size: 20px; line-height: 1.6; }

    /* 상세 현황 테이블 (글자 크기 확대) */
    .table-title { font-size: 24px; font-weight: 900; color: #343a40; margin: 35px 0 15px 0; }
    .custom-table { width: 100%; border-collapse: collapse; background: white; border-radius: 15px; overflow: hidden; font-size: 18px; }
    .custom-table th { background: #343a40; color: white; padding: 18px; text-align: left; font-size: 19px; }
    .custom-table td { padding: 18px; border-bottom: 1px solid #eee; }
    .row-floor { font-weight: 800; color: #007bff; }
</style>
""", unsafe_allow_html=True)

# --- 2. 검증된 초정밀 검색 로직 (Leading Zero 무력화) ---
def to_pure_int(val):
    try:
        clean = re.sub(r'[^0-9]', '', str(val))
        return int(clean) if clean else 0
    except:
        return 0

def clean_col_name(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

@st.cache_data(show_spinner="망포동 데이터를 포함하여 전수 조사 중...")
def perform_search(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []

    nums = re.findall(r'\d+', query_str)
    if not nums: return []
    q_main = to_pure_int(nums[0])
    q_sub = to_pure_int(nums[1]) if len(nums) > 1 else 0
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    # 필수 칼럼 로드 (용도 구분 없이 싹 다 긁음)
    cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    found = []
    # 숫자로 직접 비교하여 0006 == 6 매칭 성공 유도
    for chunk in pd.read_csv(f_master, dtype=str, usecols=lambda x: clean_col_name(x) in cols, chunksize=50000):
        chunk.columns = [clean_col_name(c) for c in chunk.columns]
        chunk['n_main'] = chunk['번'].fillna('0').apply(to_pure_int)
        chunk['n_sub'] = chunk['지'].fillna('0').apply(to_pure_int)
        
        mask = (chunk['n_main'] == q_main) & (chunk['n_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            found.extend(res.to_dict('records'))
    return found

@st.cache_data
def get_extended_details(pks):
    f_list, s_list, a_list = [], [], []
    # 층별 정보
    if os.path.exists("suwon_floor_info.csv.gz"):
        f_cols = ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']
        for chunk in pd.read_csv("suwon_floor_info.csv.gz", dtype=str, usecols=lambda x: clean_col_name(x) in f_cols, chunksize=50000):
            chunk.columns = [clean_col_name(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: f_list.extend(res.to_dict('records'))
    # 상가/고시원(집합대장) 정보
    if os.path.exists("suwon_unit_status.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_status.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_col_name(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: s_list.extend(res.to_dict('records'))
    if os.path.exists("suwon_unit_area.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_area.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_col_name(c) for c in chunk.columns]
            res = chunk[(chunk['관리건축물대장PK'].isin(pks)) & (chunk.get('전유공용구분코드', '1') == '1')]
            if not res.empty: a_list.extend(res.to_dict('records'))
            
    return f_list, s_list, a_list

# --- 3. UI 구현 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 망포동 6-11 / 세류동 254")
    submitted = st.form_submit_button("🔍 정확한 정보 찾기")

if submitted:
    if query:
        items = perform_search(query)
        if items:
            pks = [i['관리건축물대장PK'] for i in items]
            f_data, s_data, a_data = get_extended_details(pks)
            
            st.success(f"✅ 총 {len(items)}개의 건축물을 찾았습니다.")
            
            # [수정] 불필요한 네모 박스 제거 로직 (기존의 빈 bar 스타일 삭제됨)

            for idx, b in enumerate(items):
                pk = b['관리건축물대장PK']
                name = str(b.get('건물명', '')).replace('nan', '').strip()
                dong = str(b.get('동명칭', '')).replace('nan', '').strip()
                final_title = f"{name} {f'({dong})' if dong else ''}".strip() or f"건축물 {idx+1}"

                # 1. 주소 및 건물명
                st.markdown(f'<div class="address-card">', unsafe_allow_html=True)
                st.markdown(f"<h3>{final_title}</h3>", unsafe_allow_html=True)
                st.markdown(f"<p><b>📍 지번:</b> {b.get('대지위치', '-')}</p>", unsafe_allow_html=True)
                st.markdown(f"<p><b>🛣️ 도로명:</b> <span style='color:#007bff; font-weight:bold;'>{b.get('도로명대지위치', '정보 없음')}</span></p>", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

                # 2. 4대 지표 네모 박스 (폰트 크게 보강)
                def get_s_int(v):
                    try: return int(float(str(v).replace('nan', '0') or 0))
                    except: return 0

                st.markdown(f"""
                <div class="metric-container">
                    <div class="metric-card"><div class="metric-label">층수</div><div class="metric-value">{b.get('지상층수', '0')}층</div></div>
                    <div class="metric-card"><div class="metric-label">세대/가구</div><div class="metric-value">{get_s_int(b.get('가구수(가구)')) + get_s_int(b.get('세대수(세대)'))}호</div></div>
                    <div class="metric-card"><div class="metric-label">주차대수</div><div class="metric-value">{get_s_int(b.get('옥내자주식대수(대)')) + get_s_int(b.get('옥외자주식대수(대)'))}대</div></div>
                    <div class="metric-card"><div class="metric-label">엘리베이터</div><div class="metric-value">{get_s_int(b.get('승용승강기수')) + get_s_int(b.get('비상용승강기수'))}대</div></div>
                </div>
                """, unsafe_allow_html=True)

                # 3. 주용도 / 사용승인일 박스
                st.markdown(f"""
                <div class="info-box-container">
                    <div class="info-box"><span class="info-label">🏢 주용도</span><span class="info-value">{b.get('주용도코드명', '-')}</span></div>
                    <div class="info-box"><span class="info-label">📅 사용승인일</span><span class="info-value">{b.get('사용승인일', '-')}</span></div>
                </div>
                """, unsafe_allow_html=True)

                # 4. 층별 상세 현황 표 (집합대장 우선 순위)
                st.markdown('<p class="table-title">📊 층별 상세 현황 (용도 및 면적)</p>', unsafe_allow_html=True)
                
                # 기숙사/상가 등 집합건축물 체크
                if "집합" in str(b.get('대장구분코드명', '')):
                    my_s = [s for s in s_data if s['관리건축물대장PK'] == pk]
                    my_a = [a for a in a_data if a['관리건축물대장PK'] == pk]
                    if my_s and my_a:
                        merged = pd.merge(pd.DataFrame(my_s), pd.DataFrame(my_a), on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged = merged.drop_duplicates(['층번호', '호명칭'])
                        
                        tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                        for _, r in merged.iterrows():
                            tbl += f'<tr><td class="row-floor">{r.get("층번호")}층 {r.get("호명칭")}</td><td>{r.get("주용도코드명", "-")}</td><td style="text-align:right; font-weight:900; color:#007bff;">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                else:
                    my_f = [f for f in f_data if f['관리건축물대장PK'] == pk]
                    if my_f:
                        tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th style="text-align:center;">비고</th><th style="text-align:right;">면적</th></tr>'
                        for f in my_f:
                            etc = str(f.get('기타용도', ''))
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            u_info = g.group(0) if g else "-"
                            tbl += f'<tr><td class="row-floor">{f.get("층번호")}층</td><td>{f.get("주용도코드명", "-")}</td><td style="text-align:center; color:#d9480f; font-weight:bold;">{u_info}</td><td style="text-align:right; font-weight:900; color:#007bff;">{f.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                
                st.markdown("<br><hr>", unsafe_allow_html=True)
            gc.collect()
        else:
            st.error("정확히 일치하는 지번 결과가 없습니다. 망포동 6-11처럼 본번-부번을 정확히 입력해주세요.")
