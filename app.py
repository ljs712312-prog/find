import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 사용자 맞춤 디자인 적용
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; color: #1e1e1e !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    
    /* 검색창 디자인 */
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #111111 !important;
        border: 2px solid #007bff !important; border-radius: 12px;
        padding: 14px !important; font-weight: 600 !important;
    }
    
    /* 버튼 디자인 */
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white;
        font-weight: 800; border-radius: 10px; padding: 12px; border: none;
    }

    /* 결과 카드 및 주소 박스 */
    .info-card {
        background-color: #ffffff; padding: 25px; border-radius: 15px;
        border-left: 8px solid #6f42c1; box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        margin-top: 15px; margin-bottom: 30px;
    }
    .address-box {
        background-color: #eef6ff; padding: 15px; border-radius: 10px;
        margin-bottom: 15px; border: 1px solid #d0e3ff;
    }
    .bld-header { font-size: 20px; font-weight: 800; color: #007bff; margin-top: 30px; margin-bottom: 10px; border-bottom: 2px solid #007bff; }
    
    /* 층별 상세 테이블 */
    .custom-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }
    .custom-table th { background-color: #f1f3f5; padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6; color: #495057; font-weight: 700; }
    .custom-table td { padding: 10px; border-bottom: 1px solid #eee; }
    .row-floor { font-weight: 700; color: #6f42c1; }
    .row-area { font-weight: 800; color: #007bff; text-align: right; }
    .row-unit { font-weight: 800; color: #d9480f; text-align: center; }
</style>
""", unsafe_allow_html=True)

# 2. 로직: 지번 숫자 정규화
def to_strict_num(val):
    try: return str(int(re.sub(r'[^0-9]', '', str(val))))
    except: return "0"

def clean_col(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

# 3. 고속 검색 엔진 (필요한 칼럼만 골라 읽기)
@st.cache_data(show_spinner="건축물 정보를 실시간 검색 중...")
def fast_search(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []

    # 입력값 분리 (예: 망포동 6-11 -> 본번: 6, 부번: 11)
    nums = re.findall(r'\d+', query_str)
    q_main = str(int(nums[0])) if len(nums) > 0 else ""
    q_sub = str(int(nums[1])) if len(nums) > 1 else "0"
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    # 메모리 절약을 위해 필요한 핵심 칼럼 14개만 지정
    essential_cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    results = []
    # 5만 줄 단위로 읽으며 숫자 일치 여부 확인
    for chunk in pd.read_csv(f_master, dtype=str, usecols=lambda x: clean_col(x) in essential_cols, chunksize=50000):
        chunk.columns = [clean_col(c) for c in chunk.columns]
        chunk['n_main'] = chunk['번'].fillna('0').apply(to_strict_num)
        chunk['n_sub'] = chunk['지'].fillna('0').apply(to_strict_num)
        
        mask = (chunk['n_main'] == q_main) & (chunk['n_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            results.extend(res.to_dict('records'))
    return results

@st.cache_data
def fetch_floor_details(pk_list):
    # 상세 데이터도 PK가 일치하는 것만 메모리에 올림
    details = {"floor": [], "status": [], "area": []}
    
    files = {
        "floor": ("suwon_floor_info.csv.gz", ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']),
        "status": ("suwon_unit_status.csv.gz", ['관리건축물대장PK', '호명칭', '층번호']),
        "area": ("suwon_unit_area.csv.gz", ['관리건축물대장PK', '호명칭', '층번호', '전유공용구분코드', '면적(㎡)'])
    }
    
    for key, (f_name, cols) in files.items():
        if os.path.exists(f_name):
            for chunk in pd.read_csv(f_name, dtype=str, usecols=lambda x: clean_col(x) in cols, chunksize=50000):
                chunk.columns = [clean_col(c) for c in chunk.columns]
                res = chunk[chunk['관리건축물대장PK'].isin(pk_list)]
                if not res.empty: 
                    if key == "area": # 전용면적만 필터링
                        res = res[res.get('전유공용구분코드', '1') == '1']
                    details[key].extend(res.to_dict('records'))
    return details

# 4. 메인 화면 구성
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 세류동 254 / 망포동 6-11")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    if query:
        buildings = fast_search(query)
        if buildings:
            pks = [b['관리건축물대장PK'] for b in buildings]
            det = fetch_floor_details(pks)
            
            st.success(f"✅ 총 {len(buildings)}개의 건축물을 찾았습니다.")
            
            for idx, item in enumerate(buildings):
                pk = item['관리건축물대장PK']
                b_name = str(item.get('건물명', '')).replace('nan', '').strip()
                d_name = str(item.get('동명칭', '')).replace('nan', '').strip()
                title = f"{b_name} {f'({d_name})' if d_name else ''}".strip() or f"건축물 {idx+1}"

                st.markdown(f'<div class="bld-header">📌 {title}</div>', unsafe_allow_html=True)
                
                # 지번 + 도로명 주소 박스
                st.markdown(f"""
                <div class="address-box">
                    <div style="font-size: 14px; color: #555;">📍 지번: {item.get('대지위치', '-')}</div>
                    <div style="font-size: 15px; color: #007bff; font-weight: 800; margin-top: 5px;">🛣️ 도로명: {item.get('도로명대지위치', '정보 없음')}</div>
                </div>
                """, unsafe_allow_html=True)

                # 상단 4대 메트릭
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{item.get('지상층수', '0')}층")
                c2.metric("가구수", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
                c3.metric("주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
                c4.metric("엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                st.write(f"🏢 **주용도:** {item.get('주용도코드명', '-')}  |  📅 **사용승인:** {item.get('사용승인일', '-')}")
                
                st.markdown("<br><b>📊 층별 상세 현황</b>", unsafe_allow_html=True)
                
                # 집합건축물 면적 표
                if "집합" in str(item.get('대장구분코드명', '')):
                    t_s = [s for s in det["status"] if s['관리건축물대장PK'] == pk]
                    t_a = [a for a in det["area"] if a['관리건축물대장PK'] == pk]
                    if t_s and t_a:
                        s_df, a_df = pd.DataFrame(t_s), pd.DataFrame(t_a)
                        merged = pd.merge(s_df, a_df, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged['sort_key'] = merged['호명칭'].apply(natural_sort_key)
                        merged = merged.sort_values('sort_key').drop_duplicates(['층번호', '호명칭'])
                        
                        tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                        for _, u in merged.iterrows():
                            tbl += f'<tr><td class="row-floor">{u.get("층번호")}층 {u.get("호명칭")}</td><td>{u.get("주용도코드명", "-")}</td><td class="row-area">{u.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                
                # 일반건축물 층별 표
                else:
                    t_f = [f for f in det["floor"] if f['관리건축물대장PK'] == pk]
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
            gc.collect()
        else:
            st.error("정확히 일치하는 지번 결과가 없습니다.")
