import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 디자인 (이미지 양식 그대로 복구)
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; color: #1e1e1e !important; }
    .main-title { font-size: 24px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    
    /* 검색창 */
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; border: 2px solid #007bff !important;
        border-radius: 12px; padding: 14px !important; font-weight: 600 !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white;
        font-weight: 800; border-radius: 10px; padding: 12px; border: none;
    }

    /* 주소 및 결과 레이아웃 */
    .address-box {
        background-color: #eef6ff; padding: 15px; border-radius: 10px;
        margin-bottom: 15px; border: 1px solid #d0e3ff;
    }
    .custom-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; background: #fff; }
    .custom-table th { background-color: #f1f3f5; padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6; }
    .custom-table td { padding: 10px; border-bottom: 1px solid #eee; }
    .row-floor { font-weight: 700; color: #6f42c1; }
    .row-area { font-weight: 800; color: #007bff; text-align: right; }
</style>
""", unsafe_allow_html=True)

# --- [검증 로직 1] 컬럼명 및 데이터 청소 ---
def clean_txt(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

def to_padded_str(val):
    # '6' -> '0006'으로 변환하여 망포동 검색 오류 해결
    try:
        num = re.sub(r'[^0-9]', '', str(val))
        return num.zfill(4) if num else "0000"
    except:
        return "0000"

def natural_sort(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

# --- [검증 로직 2] 고속 & 정밀 검색 엔진 ---
@st.cache_data(show_spinner="망포동 데이터를 포함하여 전수 조사 중...")
def search_engine(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []

    # 입력값에서 동, 본번, 부번 추출
    nums = re.findall(r'\d+', query_str)
    q_main = to_padded_str(nums[0]) if len(nums) > 0 else "0000"
    q_sub = to_padded_str(nums[1]) if len(nums) > 1 else "0000"
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    # 필수 컬럼 로드 (메모리 최적화)
    cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    results = []
    # 10만 줄 단위로 읽어 망포동까지 누락 없이 검색
    for chunk in pd.read_csv(f_master, dtype=str, usecols=lambda x: clean_txt(x) in cols, chunksize=100000):
        chunk.columns = [clean_txt(c) for c in chunk.columns]
        
        # 데이터상의 번(0006)과 지(0011)를 입력값과 1:1 매칭
        mask = (chunk['번'] == q_main) & (chunk['지'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            results.extend(res.to_dict('records'))
    return results

# --- [검증 로직 3] 상세 데이터 추출 ---
@st.cache_data
def get_building_details(pk_list):
    floor_data = []
    if os.path.exists("suwon_floor_info.csv.gz"):
        f_cols = ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']
        for chunk in pd.read_csv("suwon_floor_info.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in f_cols, chunksize=100000):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pk_list)]
            if not res.empty: floor_data.extend(res.to_dict('records'))
    return floor_data

# 3. 화면 구성
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 세류동 254 / 망포동 6-11")
    submitted = st.form_submit_button("🔍 정확한 정보 찾기")

if submitted:
    if query:
        items = search_engine(query)
        if items:
            pks = [i['관리건축물대장PK'] for i in items]
            floors = get_building_details(pks)
            
            st.success(f"✅ 총 {len(items)}개의 건축물을 찾았습니다.")
            
            for idx, b in enumerate(items):
                pk = b['관리건축물대장PK']
                # 제목 nan 방지 처리
                b_name = str(b.get('건물명', '')).replace('nan', '').strip()
                d_name = str(b.get('동명칭', '')).replace('nan', '').strip()
                final_title = f"{b_name} {f'({d_name})' if d_name else ''}".strip() or f"건축물 {idx+1}"

                st.markdown(f"### 📌 {final_title}")
                
                # 주소 정보 (지번 + 도로명)
                st.markdown(f"""
                <div class="address-box">
                    <div style="font-size: 14px; color: #555;">📍 지번: {b.get('대지위치', '-')}</div>
                    <div style="font-size: 14px; color: #007bff; font-weight: bold; margin-top: 5px;">🛣️ 도로명: {b.get('도로명대지위치', '정보 없음')}</div>
                </div>
                """, unsafe_allow_html=True)
                
                st.write(f"🏢 **주용도:** {b.get('주용도코드명', '-')} | 📅 **사용승인:** {b.get('사용승인일', '-')}")

                # [검증 완료] 핵심 수치 계산 및 출력 (NameError 원천 차단)
                def safe_int(v):
                    try: return int(float(str(v).replace('nan', '0') or 0))
                    except: return 0

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{b.get('지상층수', '0')}층")
                c2.metric("가구", f"{safe_int(b.get('가구수(가구)')) + safe_int(b.get('세대수(세대)'))}가구")
                c3.metric("주차", f"{safe_int(b.get('옥내자주식대수(대)')) + safe_int(b.get('옥외자주식대수(대)'))}대")
                c4.metric("엘베", f"{safe_int(b.get('승용승강기수')) + safe_int(b.get('비상용승강기수'))}대")

                # [검증 완료] 층별 상세 현황 표
                st.markdown("<br><b>📊 층별 상세 현황</b>", unsafe_allow_html=True)
                my_floors = [f for f in floors if f['관리건축물대장PK'] == pk]
                
                if my_floors:
                    f_df = pd.DataFrame(my_floors)
                    f_df['sort_key'] = f_df['층번호'].apply(natural_sort)
                    f_df = f_df.sort_values('sort_key')
                    
                    tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th style="text-align:center;">가구/호</th><th style="text-align:right;">면적</th></tr>'
                    for _, row in f_df.iterrows():
                        etc = str(row.get('기타용도', ''))
                        unit_match = re.search(r'(\d+)\s*(가구|호)', etc)
                        unit_info = unit_match.group(0) if unit_match else "-"
                        tbl += f'<tr><td class="row-floor">{row.get("층번호")}층</td><td>{row.get("주용도코드명", "-")}</td><td style="text-align:center; color:#d9480f; font-weight:bold;">{unit_info}</td><td class="row-area">{row.get("면적(㎡)", "-")} ㎡</td></tr>'
                    tbl += '</table>'
                    st.markdown(tbl, unsafe_allow_html=True)
                else:
                    st.info("💡 해당 건축물의 층별 현황 정보가 없습니다.")
                
                st.write("---")
            gc.collect()
        else:
            st.error("정확히 일치하는 지번 결과가 없습니다. (망포동 6-11 등 지번 형식을 확인해주세요)")
