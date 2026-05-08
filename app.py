import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 초기 디자인 복구
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; color: #1e1e1e !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    
    /* 검색창 시인성 */
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #111111 !important;
        border: 2px solid #007bff !important; border-radius: 12px; padding: 14px !important; font-weight: 600 !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white; font-weight: 800; border-radius: 10px; padding: 12px; border: none;
    }
    
    /* 결과 카드 및 주소 박스 */
    .info-card {
        background-color: #ffffff; padding: 25px; border-radius: 15px;
        border-left: 8px solid #6f42c1; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 30px;
    }
    .address-box {
        background-color: #eef6ff; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid #d0e3ff;
    }
    .bld-header { font-size: 20px; font-weight: 800; color: #007bff; margin-top: 30px; margin-bottom: 10px; padding-bottom: 5px; border-bottom: 2px solid #007bff; }
    
    /* 상세 현황 테이블 스타일 */
    .custom-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }
    .custom-table th { background-color: #f1f3f5; padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6; color: #495057; }
    .custom-table td { padding: 10px; border-bottom: 1px solid #eee; }
    .row-floor { font-weight: 700; color: #6f42c1; }
    .row-area { font-weight: 800; color: #007bff; text-align: right; }
    .row-unit { font-weight: 800; color: #d9480f; text-align: center; }
</style>
""", unsafe_allow_html=True)

# 2. 핵심 로직 (정규화 검색)
def to_int_str(val):
    try: return str(int(re.sub(r'[^0-9]', '', str(val))))
    except: return "0"

def clean_col(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

@st.cache_data(show_spinner="정보를 분석 중입니다...")
def powerful_search(query_str):
    f_path = "suwon_building_master.csv.gz"
    if not os.path.exists(f_path): return None, None, None, None
    
    # 입력값 분리 (세류동 254-2 -> 동: 세류동, 본번: 254, 부번: 2)
    nums = re.findall(r'\d+', query_str)
    q_main = str(int(nums[0])) if len(nums) > 0 else ""
    q_sub = str(int(nums[1])) if len(nums) > 1 else "0"
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    matched_results = []
    # 1. 마스터 검색 (지번 완전 일치 필터)
    for chunk in pd.read_csv(f_path, dtype=str, chunksize=50000):
        chunk.columns = [clean_col(c) for c in chunk.columns]
        chunk['n_main'] = chunk['번'].apply(to_int_str)
        chunk['n_sub'] = chunk['지'].apply(to_int_str)
        
        # [수정] 본번과 부번이 정확히 일치해야 함 (254 검색 시 254-2 안 나옴)
        mask = (chunk['n_main'] == q_main) & (chunk['n_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            matched_results.extend(res.to_dict('records'))

    if not matched_results: return None, None, None, None

    pks = [r['관리건축물대장PK'] for r in matched_results]
    
    # 2. 층별/호수별 데이터 로드
    floor = pd.read_csv("suwon_floor_info.csv.gz", dtype=str)
    floor.columns = [clean_col(c) for c in floor.columns]
    floor = floor[floor['관리건축물대장PK'].isin(pks)]

    status = pd.read_csv("suwon_unit_status.csv.gz", dtype=str)
    status.columns = [clean_col(c) for c in status.columns]
    status = status[status['관리건축물대장PK'].isin(pks)]

    area = pd.read_csv("suwon_unit_area.csv.gz", dtype=str)
    area.columns = [clean_col(c) for c in area.columns]
    area = area[(area['관리건축물대장PK'].isin(pks)) & (area.get('전유공용구분코드', '1') == '1')]

    gc.collect()
    return matched_results, floor, status, area

# 3. 화면 구성
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 세류동 254")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    if query:
        results, floor_df, status_df, area_df = powerful_search(query)
        if results:
            st.success(f"✅ 총 {len(results)}개의 건축물을 찾았습니다.")
            for idx, item in enumerate(results):
                pk = item['관리건축물대장PK']
                # nan 제거 제목
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
                
                # --- 층별 상세 현황 테이블 섹션 ---
                st.markdown("<br><b>📊 층별 상세 현황</b>", unsafe_allow_html=True)
                
                if "집합" in str(item.get('대장구분코드명', '')):
                    t_s = status_df[status_df['관리건축물대장PK'] == pk]
                    t_a = area_df[area_df['관리건축물대장PK'] == pk]
                    if not t_s.empty and not t_a.empty:
                        merged = pd.merge(t_s, t_a, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged['sort'] = merged['호명칭'].apply(natural_sort_key)
                        merged = merged.sort_values('sort')
                        
                        tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                        for _, u in merged.drop_duplicates(['층번호', '호명칭']).iterrows():
                            tbl += f'<tr><td class="row-floor">{u.get("층번호")}층 {u.get("호명칭")}</td><td>{u.get("주용도코드명", "-")}</td><td class="row-area">{u.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                else:
                    t_f = floor_df[floor_df['관리건축물대장PK'] == pk].copy()
                    if not t_f.empty:
                        t_f['sort'] = t_f['층번호'].apply(natural_sort_key)
                        t_f = t_f.sort_values('sort')
                        
                        tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th style="text-align:center;">가구/호</th><th style="text-align:right;">면적</th></tr>'
                        for _, f in t_f.iterrows():
                            etc = str(f.get('기타용도', ''))
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            unit = g.group(0) if g else "-"
                            tbl += f'<tr><td class="row-floor">{f.get("층번호")}층</td><td>{f.get("주용도코드명", "-")}</td><td class="row-unit">{unit}</td><td class="row-area">{f.get("면적(㎡)", "-")} ㎡</td></tr>'
                        tbl += '</table>'
                        st.markdown(tbl, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("정확히 일치하는 지번이 없습니다.")
