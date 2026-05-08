import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 실무 맞춤형 디자인
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; color: #1e1e1e !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    
    /* 검색창 및 버튼 */
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; border: 2px solid #007bff !important;
        border-radius: 12px; padding: 14px !important; font-weight: 600 !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff !important; color: white !important;
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
</style>
""", unsafe_allow_html=True)

# --- [검증 1] 숫자 정규화 로직 (0 제거 전문) ---
def clean_col(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

def force_int(v):
    """'0006' -> 6으로 무조건 변환 (망포동 지번 해결의 핵심)"""
    try:
        n = re.sub(r'[^0-9]', '', str(v))
        return int(n) if n else 0
    except:
        return 0

def n_sort(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', str(s))]

# --- [검증 2] 망포동/상가/고시원 전용 검색 엔진 ---
@st.cache_data(show_spinner="망포동 6-11을 포함하여 근생/고시원 데이터를 정밀 수색 중...")
def master_search(query_str):
    f_path = "suwon_building_master.csv.gz"
    if not os.path.exists(f_path): return []

    # 입력값에서 번지 추출 (예: 망포동 6-11 -> 6, 11)
    nums = re.findall(r'\d+', query_str)
    if not nums: return []
    q_main = int(nums[0])
    q_sub = int(nums[1]) if len(nums) > 1 else 0
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    # 필수 컬럼 로드 (메모리 세이브)
    cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    found = []
    # 5만 줄 단위로 읽으며 숫자 필터링 (텍스트가 아닌 숫자로 비교)
    for chunk in pd.read_csv(f_path, dtype=str, usecols=lambda x: clean_col(x) in cols, chunksize=50000):
        chunk.columns = [clean_col(c) for c in chunk.columns]
        
        # 0006 -> 6 변환 로직 적용
        chunk['int_main'] = chunk['번'].fillna('0').apply(force_int)
        chunk['int_sub'] = chunk['지'].fillna('0').apply(force_int)
        
        # 숫자 일치 확인
        mask = (chunk['int_main'] == q_main) & (chunk['int_sub'] == q_sub)
        
        # 동 이름이 입력된 경우 추가 필터링
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            found.extend(res.to_dict('records'))
    return found

@st.cache_data
def load_details(pk_list):
    """상가 및 고시원용 집합대장 데이터까지 모두 로드"""
    det = {"f": [], "s": [], "a": []}
    files = {
        "f": ("suwon_floor_info.csv.gz", ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']),
        "s": ("suwon_unit_status.csv.gz", ['관리건축물대장PK', '호명칭', '층번호']),
        "a": ("suwon_unit_area.csv.gz", ['관리건축물대장PK', '호명칭', '층번호', '전유공용구분코드', '면적(㎡)'])
    }
    for k, (name, cols) in files.items():
        if os.path.exists(name):
            for chunk in pd.read_csv(name, dtype=str, usecols=lambda x: clean_col(x) in cols, chunksize=50000):
                chunk.columns = [clean_col(c) for c in chunk.columns]
                res = chunk[chunk['관리건축물대장PK'].isin(pk_list)]
                if not res.empty:
                    if k == "a": res = res[res.get('전유공용구분코드', '1') == '1']
                    det[k].extend(res.to_dict('records'))
    return det

# --- 3. UI 렌더링 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 망포동 6-11 / 세류동 254")
    submitted = st.form_submit_button("🔍 정확한 정보 찾기")

if submitted:
    if query:
        items = master_search(query)
        if items:
            pks = [i['관리건축물대장PK'] for i in items]
            details = load_details(pks)
            
            st.success(f"✅ 총 {len(items)}개의 건축물을 찾았습니다.")
            
            for idx, b in enumerate(items):
                pk = b['관리건축물대장PK']
                bld_name = str(b.get('건물명', '')).replace('nan', '').strip()
                dong_name = str(b.get('동명칭', '')).replace('nan', '').strip()
                title = f"{bld_name} {f'({dong_name})' if dong_name else ''}".strip() or f"건축물 {idx+1}"

                st.markdown(f"### 📌 {title}")
                
                st.markdown(f"""
                <div class="address-box">
                    <div style="font-size: 14px; color: #555;">📍 지번: {b.get('대지위치', '-')}</div>
                    <div style="font-size: 15px; color: #007bff; font-weight: bold; margin-top: 5px;">🛣️ 도로명: {b.get('도로명대지위치', '정보 없음')}</div>
                </div>
                """, unsafe_allow_html=True)
                
                # 수치 계산 로직 (안정성 강화)
                def get_num(v):
                    try: return int(float(str(v).replace('nan', '0') or 0))
                    except: return 0

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{b.get('지상층수', '0')}층")
                c2.metric("세대/가구", f"{get_num(b.get('가구수(가구)')) + get_num(b.get('세대수(세대)'))}호")
                c3.metric("주차대수", f"{get_num(b.get('옥내자주식대수(대)')) + get_num(b.get('옥외자주식대수(대)'))}대")
                c4.metric("엘리베이터", f"{get_num(b.get('승용승강기수')) + get_num(b.get('비상용승강기수'))}대")

                st.write(f"🏢 **주용도:** {b.get('주용도코드명', '-')} | 📅 **사용승인:** {b.get('사용승인일', '-')}")

                # --- 층별 상세 현황 (상가/고시원 완벽 대응) ---
                st.markdown("<br><b>📊 상세 현황 (층별 용도 및 면적)</b>", unsafe_allow_html=True)
                
                # 집합건축물 (상가, 오피스텔 등)
                if "집합" in str(b.get('대장구분코드명', '')):
                    my_s = [s for s in details["s"] if s['관리건축물대장PK'] == pk]
                    my_a = [a for a in details["a"] if a['관리건축물대장PK'] == pk]
                    if my_s and my_a:
                        u_df, a_df = pd.DataFrame(my_s), pd.DataFrame(my_a)
                        merged = pd.merge(u_df, a_df, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged['sort'] = merged['호명칭'].apply(n_sort)
                        merged = merged.sort_values('sort').drop_duplicates(['층번호', '호명칭'])
                        
                        tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                        for _, r in merged.iterrows():
                            tbl += f'<tr><td class="row-floor">{r.get("층번호")}층 {r.get("호명칭")}</td><td>{r.get("주용도코드명", "-")}</td><td class="row-area">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                
                # 일반건축물 (단독, 다가구 등)
                else:
                    my_f = [f for f in details["f"] if f['관리건축물대장PK'] == pk]
                    if my_f:
                        f_df = pd.DataFrame(my_f)
                        f_df['sort'] = f_df['층번호'].apply(n_sort)
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
            st.error("정확히 일치하는 지번 결과가 없습니다. '망포동 6-11' 형식으로 정확히 입력해주세요.")
