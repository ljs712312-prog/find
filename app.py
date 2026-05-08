import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 부동산 실무 디자인
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; color: #1e1e1e !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    
    /* 입력창 및 검색 버튼 */
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; border: 2px solid #007bff !important;
        border-radius: 12px; padding: 14px !important; font-weight: 600 !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white;
        font-weight: 800; border-radius: 10px; padding: 12px; border: none;
    }

    /* 주소 박스 및 정보 카드 */
    .address-box {
        background-color: #eef6ff; padding: 15px; border-radius: 10px;
        margin-bottom: 15px; border: 1px solid #d0e3ff;
    }
    .custom-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; background: #fff; }
    .custom-table th { background-color: #f1f3f5; padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6; color: #495057; }
    .custom-table td { padding: 10px; border-bottom: 1px solid #eee; }
    .row-floor { font-weight: 700; color: #6f42c1; }
    .row-area { font-weight: 800; color: #007bff; text-align: right; }
    .row-unit { font-weight: 800; color: #d9480f; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- 정밀 매칭 함수 ---
def to_int(v):
    # '0006' -> 6으로 강제 변환하여 망포동 6-11 매칭 성공 유도
    try:
        n = re.sub(r'[^0-9]', '', str(v))
        return int(n) if n else 0
    except:
        return 0

def clean_col(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

def natural_sort(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

# --- 고속 검색 엔진 (용도 필터링 해제) ---
@st.cache_data(show_spinner="망포동 6-11을 포함하여 전 구역을 전수 조사 중입니다...")
def building_finder(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []

    # 검색어 정규화 (본번, 부번 추출)
    nums = re.findall(r'\d+', query_str)
    if not nums: return []
    q_main = int(nums[0])
    q_sub = int(nums[1]) if len(nums) > 1 else 0
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    # 필수 칼럼 로드 (NameError 방지를 위해 모든 수치 칼럼 포함)
    target_cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    found = []
    # 5만 줄씩 읽으며 숫자 비교 (지번 검색 1순위)
    for chunk in pd.read_csv(f_master, dtype=str, usecols=lambda x: clean_col(x) in target_cols, chunksize=50000):
        chunk.columns = [clean_col(c) for c in chunk.columns]
        
        # '0006' -> 6으로 변환하여 q_main과 비교
        chunk['n_main'] = chunk['번'].fillna('0').apply(to_int)
        chunk['n_sub'] = chunk['지'].fillna('0').apply(to_int)
        
        mask = (chunk['n_main'] == q_main) & (chunk['n_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            found.extend(res.to_dict('records'))
    return found

@st.cache_data
def get_all_details(pks):
    details = {"f": [], "s": [], "a": []}
    # 층별 정보 ( floor_info )
    if os.path.exists("suwon_floor_info.csv.gz"):
        for chunk in pd.read_csv("suwon_floor_info.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_col(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: details["f"].extend(res.to_dict('records'))
            
    # 호수별 정보 ( unit_status + unit_area )
    if os.path.exists("suwon_unit_status.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_status.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_col(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pks)]
            if not res.empty: details["s"].extend(res.to_dict('records'))
            
    if os.path.exists("suwon_unit_area.csv.gz"):
        for chunk in pd.read_csv("suwon_unit_area.csv.gz", dtype=str, chunksize=50000):
            chunk.columns = [clean_col(c) for c in chunk.columns]
            res = chunk[(chunk['관리건축물대장PK'].isin(pks)) & (chunk.get('전유공용구분코드', '1') == '1')]
            if not res.empty: details["a"].extend(res.to_dict('records'))
            
    return details

# --- 화면 렌더링 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 망포동 6-11 / 세류동 254")
    submitted = st.form_submit_button("🔍 정확한 정보 찾기")

if submitted:
    if query:
        items = building_finder(query)
        if items:
            pks = [i['관리건축물대장PK'] for i in items]
            det = get_all_details(pks)
            
            st.success(f"✅ 총 {len(items)}개의 건축물을 찾았습니다.")
            
            for idx, b in enumerate(items):
                pk = b['관리건축물대장PK']
                bld_name = str(b.get('건물명', '')).replace('nan', '').strip()
                dong_name = str(b.get('동명칭', '')).replace('nan', '').strip()
                title = f"{bld_name} {f'({dong_name})' if dong_name else ''}".strip() or f"건축물 {idx+1}"

                st.markdown(f"### 📌 {title}")
                
                # 주소 정보
                st.markdown(f"""
                <div class="address-box">
                    <div style="font-size: 14px; color: #555;">📍 지번: {b.get('대지위치', '-')}</div>
                    <div style="font-size: 15px; color: #007bff; font-weight: bold; margin-top: 5px;">🛣️ 도로명: {b.get('도로명대지위치', '정보 없음')}</div>
                </div>
                """, unsafe_allow_html=True)
                
                # 수치 계산 (NameError 방지 위해 내부에서 직접 계산)
                def get_val(v):
                    try: return int(float(str(v).replace('nan', '0') or 0))
                    except: return 0

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{b.get('지상층수', '0')}층")
                c2.metric("가구/세대", f"{get_val(b.get('가구수(가구)')) + get_val(b.get('세대수(세대)'))}호")
                c3.metric("주차대수", f"{get_val(b.get('옥내자주식대수(대)')) + get_val(b.get('옥외자주식대수(대)'))}대")
                c4.metric("엘베", f"{get_val(b.get('승용승강기수')) + get_val(b.get('비상용승강기수'))}대")

                st.write(f"🏢 **주용도:** {b.get('주용도코드명', '-')} | 📅 **사용승인:** {b.get('사용승인일', '-')}")

                # [개선] 층별 상세 현황 표 (집합건축물 대응 포함)
                st.markdown("<br><b>📊 상세 현황 (용도 및 면적)</b>", unsafe_allow_html=True)
                
                # 상가/고시원은 '집합건축물'인 경우가 많아 unit_area 파일 확인 필수
                if "집합" in str(b.get('대장구분코드명', '')):
                    my_s = [s for s in det["s"] if s['관리건축물대장PK'] == pk]
                    my_a = [a for a in det["a"] if a['관리건축물대장PK'] == pk]
                    if my_s and my_a:
                        s_df, a_df = pd.DataFrame(my_s), pd.DataFrame(my_a)
                        merged = pd.merge(s_df, a_df, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged['sort'] = merged['호명칭'].apply(natural_sort)
                        merged = merged.sort_values('sort').drop_duplicates(['층번호', '호명칭'])
                        
                        tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                        for _, row in merged.iterrows():
                            tbl += f'<tr><td class="row-floor">{row.get("층번호")}층 {row.get("호명칭")}</td><td>{row.get("주용도코드명", "-")}</td><td class="row-area">{row.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                else:
                    # 다가구/단독 등 일반 건축물
                    my_f = [f for f in det["f"] if f['관리건축물대장PK'] == pk]
                    if my_f:
                        f_df = pd.DataFrame(my_f)
                        f_df['sort'] = f_df['층번호'].apply(natural_sort)
                        f_df = f_df.sort_values('sort')
                        
                        tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th style="text-align:center;">가구/호</th><th style="text-align:right;">면적</th></tr>'
                        for _, row in f_df.iterrows():
                            etc = str(row.get('기타용도', ''))
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            unit_info = g.group(0) if g else "-"
                            tbl += f'<tr><td class="row-floor">{row.get("층번호")}층</td><td>{row.get("주용도코드명", "-")}</td><td class="row-unit">{unit_info}</td><td class="row-area">{row.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                st.write("---")
            gc.collect()
        else:
            st.error("정확히 일치하는 지번 결과가 없습니다. '망포동 6-11'처럼 동과 번호를 정확히 입력했는지 확인해주세요.")
