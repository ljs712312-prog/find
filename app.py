import streamlit as st
import pandas as pd
import re
import os
import gc

# ==========================================
# 1. 시인성 극대화 디자인 (글자 크기 대폭 확대)
# ==========================================
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
    .stApp { background-color: #f1f3f5; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    
    /* 제목 및 입력창 */
    .main-title { font-size: 38px; font-weight: 900; color: #111; margin-bottom: 30px; text-align: center; }
    
    div[data-testid="stTextInput"] input {
        border: 4px solid #007bff !important; border-radius: 15px; 
        padding: 25px !important; font-size: 28px !important; font-weight: 700;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff !important; color: white !important;
        font-weight: 900; border-radius: 15px; padding: 18px; border: none; font-size: 28px;
    }

    /* 4대 지표 네모 박스 */
    .metric-container { display: flex; justify-content: space-between; gap: 15px; margin-bottom: 30px; }
    .metric-card {
        flex: 1; background: white; padding: 30px 10px; border-radius: 20px;
        border: 2px solid #dee2e6; text-align: center; box-shadow: 0 8px 16px rgba(0,0,0,0.1);
    }
    .metric-label { font-size: 20px; font-weight: 700; color: #555; margin-bottom: 15px; }
    .metric-value { font-size: 32px; font-weight: 900; color: #007bff; }

    /* 주용도 / 사용승인일 박스 */
    .info-box-container { display: flex; gap: 15px; margin-bottom: 30px; }
    .info-box {
        flex: 1; background: #e9ecef; padding: 20px; border-radius: 15px;
        text-align: center; border: 2px solid #adb5bd;
    }
    .info-label { font-size: 20px; font-weight: 700; color: #333; margin-right: 15px; }
    .info-value { font-size: 22px; font-weight: 900; color: #000; }

    /* 주소 박스 */
    .address-card {
        background: white; padding: 30px; border-radius: 25px;
        border-left: 15px solid #007bff; margin-bottom: 35px; box-shadow: 0 10px 20px rgba(0,0,0,0.12);
    }
    .address-card h3 { font-size: 36px; margin-bottom: 15px; font-weight: 900; }
    .address-card p { font-size: 22px; line-height: 1.8; margin: 5px 0; }

    /* 상세 현황 테이블 */
    .table-title { font-size: 28px; font-weight: 900; color: #222; margin: 40px 0 20px 0; }
    .custom-table { width: 100%; border-collapse: collapse; background: white; border-radius: 20px; overflow: hidden; font-size: 20px; }
    .custom-table th { background: #222; color: white; padding: 20px; text-align: left; font-size: 22px; }
    .custom-table td { padding: 20px; border-bottom: 1px solid #eee; }
    .row-floor { font-weight: 900; color: #007bff; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 망포동 타겟팅 검색 엔진 (숫자 100% 매칭)
# ==========================================
def to_numeric_id(v):
    """지번의 0을 무시하고 순수 숫자로만 매칭 (망포동 해결 핵심)"""
    try:
        clean = re.sub(r'[^0-9]', '', str(v))
        return int(clean) if clean else -1
    except:
        return -1

def clean_col(c):
    return re.sub(r'[^a-zA-Z0-9가-힣()㎡]', '', str(c)).strip()

def get_file_name(base_name):
    """압축(.gz) 파일 우선, 없으면 일반 .csv 파일 사용"""
    if os.path.exists(base_name + ".gz"): return base_name + ".gz"
    if os.path.exists(base_name): return base_name
    return None

@st.cache_data(show_spinner="전체 건축물 데이터를 검색 중입니다...")
def start_search(query_str):
    f_master = get_file_name("suwon_building_master.csv")
    if not f_master: return []

    nums = re.findall(r'\d+', query_str)
    if not nums: return []
    q_main = to_numeric_id(nums[0])
    q_sub = to_numeric_id(nums[1]) if len(nums) > 1 else 0
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    found = []
    # 숫자(int)로 완벽하게 1:1 매칭 (0006 == 6)
    for chunk in pd.read_csv(f_master, dtype=str, chunksize=50000):
        chunk.columns = [clean_col(c) for c in chunk.columns]
        chunk['int_main'] = chunk['번'].apply(to_numeric_id)
        chunk['int_sub'] = chunk['지'].apply(to_numeric_id)
        
        mask = (chunk['int_main'] == q_main) & (chunk['int_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            found.extend(res.to_dict('records'))
    return found

@st.cache_data
def load_all_details(pks):
    f_list, s_list, a_list = [], [], []
    
    f_floor = get_file_name("suwon_floor_info.csv")
    if f_floor:
        for chunk in pd.read_csv(f_floor, dtype=str, chunksize=50000):
            chunk.columns = [clean_col(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: f_list.extend(res.to_dict('records'))
            
    f_status = get_file_name("suwon_unit_status.csv")
    f_area = get_file_name("suwon_unit_area.csv")
    
    if f_status and f_area:
        for chunk in pd.read_csv(f_status, dtype=str, chunksize=50000):
            chunk.columns = [clean_col(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: s_list.extend(res.to_dict('records'))
        for chunk in pd.read_csv(f_area, dtype=str, chunksize=50000):
            chunk.columns = [clean_col(c) for c in chunk.columns]
            res = chunk[(chunk['관리건축물대장PK'].isin(pks)) & (chunk.get('전유공용구분코드', '1') == '1')]
            if not res.empty: a_list.extend(res.to_dict('records'))
            
    return f_list, s_list, a_list

# ==========================================
# 3. 메인 웹사이트 UI 렌더링
# ==========================================
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 망포동 6-11 / 세류동 254")
    submitted = st.form_submit_button("🔍 정확한 정보 찾기")

if submitted:
    if query:
        items = start_search(query)
        if items:
            pks = [i['관리건축물대장PK'] for i in items]
            f_data, s_data, a_data = load_all_details(pks)
            
            st.success(f"✅ 총 {len(items)}개의 건축물을 찾았습니다.")

            for idx, b in enumerate(items):
                pk = b['관리건축물대장PK']
                name = str(b.get('건물명', '')).replace('nan', '').strip()
                dong = str(b.get('동명칭', '')).replace('nan', '').strip()
                final_title = f"{name} {f'({dong})' if dong else ''}".strip() or f"건축물 {idx+1}"

                # 주소 박스
                st.markdown(f'<div class="address-card">', unsafe_allow_html=True)
                st.markdown(f"<h3>{final_title}</h3>", unsafe_allow_html=True)
                st.markdown(f"<p><b>📍 지번:</b> {b.get('대지위치', '-')}</p>", unsafe_allow_html=True)
                st.markdown(f"<p><b>🛣️ 도로명:</b> <span style='color:#007bff; font-weight:bold;'>{b.get('도로명대지위치', '정보 없음')}</span></p>", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

                # 4대 지표 수치 계산 (에러 방지)
                def get_int(v):
                    try: return int(float(str(v).replace('nan', '0') or 0))
                    except: return 0

                st.markdown(f"""
                <div class="metric-container">
                    <div class="metric-card"><div class="metric-label">층수</div><div class="metric-value">{b.get('지상층수', '0')}층</div></div>
                    <div class="metric-card"><div class="metric-label">세대/가구</div><div class="metric-value">{get_int(b.get('가구수(가구)')) + get_int(b.get('세대수(세대)'))}호</div></div>
                    <div class="metric-card"><div class="metric-label">주차대수</div><div class="metric-value">{get_int(b.get('옥내자주식대수(대)')) + get_int(b.get('옥외자주식대수(대)'))}대</div></div>
                    <div class="metric-card"><div class="metric-label">엘리베이터</div><div class="metric-value">{get_int(b.get('승용승강기수')) + get_int(b.get('비상용승강기수'))}대</div></div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f"""
                <div class="info-box-container">
                    <div class="info-box"><span class="info-label">🏢 주용도</span><span class="info-value">{b.get('주용도코드명', '-')}</span></div>
                    <div class="info-box"><span class="info-label">📅 사용승인일</span><span class="info-value">{b.get('사용승인일', '-')}</span></div>
                </div>
                """, unsafe_allow_html=True)

                # 층별 상세 표 (집합 vs 일반)
                st.markdown('<p class="table-title">📊 층별 상세 현황 (용도 및 면적)</p>', unsafe_allow_html=True)
                
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
            st.error("정확히 일치하는 지번 결과가 없습니다. (입력하신 지번 데이터가 파일에 포함되어 있는지 확인해주세요)")
