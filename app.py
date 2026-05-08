import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 사용자 맞춤형 '박스' 디자인
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
    .stApp { background-color: #f1f3f5; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    
    /* 제목 및 검색창 */
    .main-title { font-size: 28px; font-weight: 900; color: #1a1a1a; margin-bottom: 25px; text-align: center; }
    div[data-testid="stTextInput"] input {
        border: 2px solid #007bff !important; border-radius: 12px; padding: 15px !important; font-size: 16px;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff !important; color: white !important;
        font-weight: 800; border-radius: 12px; padding: 12px; border: none; font-size: 18px;
    }

    /* 상단 4대 지표 네모 박스 */
    .metric-container { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 20px; }
    .metric-card {
        flex: 1; background: white; padding: 15px 5px; border-radius: 12px;
        border: 1px solid #dee2e6; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .metric-label { font-size: 13px; font-weight: 700; color: #6c757d; margin-bottom: 8px; }
    .metric-value { font-size: 18px; font-weight: 900; color: #007bff; }

    /* 주용도 / 사용승인일 박스 */
    .info-box-container { display: flex; gap: 10px; margin-bottom: 20px; }
    .info-box {
        flex: 1; background: #e9ecef; padding: 12px; border-radius: 10px;
        text-align: center; border: 1px solid #ced4da;
    }
    .info-label { font-size: 12px; font-weight: 700; color: #495057; margin-right: 8px; }
    .info-value { font-size: 14px; font-weight: 800; color: #212529; }

    /* 주소 박스 */
    .address-card {
        background: white; padding: 20px; border-radius: 15px;
        border-left: 8px solid #007bff; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }

    /* 상세 현황 테이블 */
    .table-title { font-size: 18px; font-weight: 800; color: #343a40; margin: 25px 0 10px 0; }
    .custom-table { width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; }
    .custom-table th { background: #343a40; color: white; padding: 12px; text-align: left; font-size: 14px; }
    .custom-table td { padding: 12px; border-bottom: 1px solid #eee; font-size: 14px; }
    .row-floor { font-weight: 700; color: #007bff; }
</style>
""", unsafe_allow_html=True)

# --- 2. 팩트체크 완료된 초정밀 검색 로직 ---
def normalize_to_int(val):
    """'0006' -> 6 으로 변환하여 망포동 검색 실패 원천 차단"""
    try:
        clean = re.sub(r'[^0-9]', '', str(val))
        return str(int(clean)) if clean else "0"
    except:
        return "0"

def clean_column(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

@st.cache_data(show_spinner="망포동 데이터를 포함하여 정밀 수색 중...")
def execute_search(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []

    # 입력값에서 동, 번, 지 추출
    nums = re.findall(r'\d+', query_str)
    if not nums: return []
    q_main = normalize_to_int(nums[0])
    q_sub = normalize_to_int(nums[1]) if len(nums) > 1 else "0"
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    matched = []
    # 0을 떼어낸 숫자끼리 비교하므로 '0006'과 '6'이 완벽하게 매칭됨
    for chunk in pd.read_csv(f_master, dtype=str, usecols=lambda x: clean_column(x) in cols, chunksize=50000):
        chunk.columns = [clean_column(c) for c in chunk.columns]
        chunk['match_main'] = chunk['번'].apply(normalize_to_int)
        chunk['match_sub'] = chunk['지'].apply(normalize_to_int)
        
        mask = (chunk['match_main'] == q_main) & (chunk['match_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            matched.extend(res.to_dict('records'))
    return matched

@st.cache_data
def load_details(pks):
    f_list, s_list, a_list = [], [], []
    # 층별 정보
    if os.path.exists("suwon_floor_info.csv.gz"):
        for chunk in pd.read_csv("suwon_floor_info.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_column(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: f_list.extend(res.to_dict('records'))
    # 집합건축물 정보
    if os.path.exists("suwon_unit_status.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_status.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_column(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: s_list.extend(res.to_dict('records'))
    if os.path.exists("suwon_unit_area.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_area.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_column(c) for c in chunk.columns]
            res = chunk[(chunk['관리건축물대장PK'].isin(pks)) & (chunk.get('전유공용구분코드', '1') == '1')]
            if not res.empty: a_list.extend(res.to_dict('records'))
            
    return f_list, s_list, a_list

# --- 3. UI 구현 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 망포동 6-11 / 세류동 254")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    if query:
        buildings = execute_search(query)
        if buildings:
            pks = [b['관리건축물대장PK'] for b in buildings]
            f_data, s_data, a_data = load_details(pks)
            
            st.success(f"✅ 총 {len(buildings)}개의 건축물을 찾았습니다.")
            
            for idx, b in enumerate(buildings):
                pk = b['관리건축물대장PK']
                name = str(b.get('건물명', '')).replace('nan', '').strip()
                dong = str(b.get('동명칭', '')).replace('nan', '').strip()
                title = f"{name} {f'({dong})' if dong else ''}".strip() or f"건축물 {idx+1}"

                # 1. 주소 및 건물명 (도로명 주소 포함)
                st.markdown(f'<div class="address-card">', unsafe_allow_html=True)
                st.markdown(f"<h3 style='margin-top:0;'>{title}</h3>", unsafe_allow_html=True)
                st.markdown(f"**📍 지번:** {b.get('대지위치', '-')}")
                st.markdown(f"**🛣️ 도로명:** <span style='color:#007bff; font-weight:bold;'>{b.get('도로명대지위치', '정보 없음')}</span>", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

                # 2. 4대 지표 네모 박스 UI
                def s_int(v):
                    try: return int(float(str(v).replace('nan', '0') or 0))
                    except: return 0

                st.markdown(f"""
                <div class="metric-container">
                    <div class="metric-card"><div class="metric-label">층수</div><div class="metric-value">{b.get('지상층수', '0')}층</div></div>
                    <div class="metric-card"><div class="metric-label">세대/가구</div><div class="metric-value">{s_int(b.get('가구수(가구)')) + s_int(b.get('세대수(세대)'))}호</div></div>
                    <div class="metric-card"><div class="metric-label">주차대수</div><div class="metric-value">{s_int(b.get('옥내자주식대수(대)')) + s_int(b.get('옥외자주식대수(대)'))}대</div></div>
                    <div class="metric-card"><div class="metric-label">엘리베이터</div><div class="metric-value">{s_int(b.get('승용승강기수')) + s_int(b.get('비상용승강기수'))}대</div></div>
                </div>
                """, unsafe_allow_html=True)

                # 3. 주용도 / 사용승인일 박스 UI
                st.markdown(f"""
                <div class="info-box-container">
                    <div class="info-box"><span class="info-label">🏢 주용도</span><span class="info-value">{b.get('주용도코드명', '-')}</span></div>
                    <div class="info-box"><span class="info-label">📅 사용승인일</span><span class="info-value">{b.get('사용승인일', '-')}</span></div>
                </div>
                """, unsafe_allow_html=True)

                # 4. 층별 상세 현황 표
                st.markdown('<p class="table-title">📊 층별 상세 현황 (용도 및 면적)</p>', unsafe_allow_html=True)
                
                if "집합" in str(b.get('대장구분코드명', '')):
                    my_s = [s for s in s_data if s['관리건축물대장PK'] == pk]
                    my_a = [a for a in a_data if a['관리건축물대장PK'] == pk]
                    if my_s and my_a:
                        merged = pd.merge(pd.DataFrame(my_s), pd.DataFrame(my_a), on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged = merged.drop_duplicates(['층번호', '호명칭'])
                        
                        tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                        for _, r in merged.iterrows():
                            tbl += f'<tr><td class="row-floor">{r.get("층번호")}층 {r.get("호명칭")}</td><td>{r.get("주용도코드명", "-")}</td><td style="text-align:right; font-weight:bold;">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                else:
                    my_f = [f for f in f_data if f['관리건축물대장PK'] == pk]
                    if my_f:
                        tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th style="text-align:center;">비고</th><th style="text-align:right;">면적</th></tr>'
                        for f in my_f:
                            etc = str(f.get('기타용도', ''))
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            unit_info = g.group(0) if g else "-"
                            tbl += f'<tr><td class="row-floor">{f.get("층번호")}층</td><td>{f.get("주용도코드명", "-")}</td><td style="text-align:center;">{unit_info}</td><td style="text-align:right; font-weight:bold;">{f.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                
                st.markdown("<br><hr>", unsafe_allow_html=True)
            gc.collect()
        else:
            st.error("정확히 일치하는 지번 결과가 없습니다. '망포동 6-11' 형식으로 입력해주세요.")
