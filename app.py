import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 사용자 이미지 기반 디자인 복구
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; color: #1e1e1e !important; }
    .main-title { font-size: 24px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    
    /* 검색창 스타일 */
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; border: 2px solid #007bff !important;
        border-radius: 12px; padding: 14px !important; font-weight: 600 !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white;
        font-weight: 800; border-radius: 10px; padding: 12px; border: none;
    }

    /* 결과 섹션 레이아웃 */
    .address-box {
        background-color: #eef6ff; padding: 15px; border-radius: 10px;
        margin-bottom: 15px; border: 1px solid #d0e3ff;
    }
    .metric-container { display: flex; justify-content: space-between; margin-top: 15px; }
    .metric-box { text-align: center; width: 23%; }
    .metric-label { font-size: 13px; color: #666; margin-bottom: 5px; }
    .metric-value { font-size: 22px; font-weight: 800; color: #333; }

    /* 층별 상세 테이블 */
    .custom-table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 14px; background: #fff; }
    .custom-table th { background-color: #f1f3f5; padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6; color: #495057; }
    .custom-table td { padding: 10px; border-bottom: 1px solid #eee; }
    .row-floor { font-weight: 700; color: #6f42c1; }
    .row-unit { font-weight: 800; color: #d9480f; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- 정규화 및 유틸 함수 ---
def clean_txt(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

def to_int_str(val):
    try: return str(int(re.sub(r'[^0-9]', '', str(val))))
    except: return "0"

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

# --- 고속 지번 검색 엔진 ---
@st.cache_data(show_spinner="망포동 데이터를 포함하여 전체 분석 중...")
def search_building(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []

    nums = re.findall(r'\d+', query_str)
    q_main = str(int(nums[0])) if len(nums) > 0 else ""
    q_sub = str(int(nums[1])) if len(nums) > 1 else "0"
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    # 이미지 양식에 필요한 필수 칼럼만 읽기
    essential_cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    results = []
    # 지번 매칭률을 위해 0을 떼어내고 비교
    for chunk in pd.read_csv(f_master, dtype=str, usecols=lambda x: clean_txt(x) in essential_cols, chunksize=100000):
        chunk.columns = [clean_txt(c) for c in chunk.columns]
        chunk['n_main'] = chunk['번'].fillna('0').apply(to_int_str)
        chunk['n_sub'] = chunk['지'].fillna('0').apply(to_int_str)
        
        mask = (chunk['n_main'] == q_main) & (chunk['n_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            results.extend(res.to_dict('records'))
    return results

@st.cache_data
def get_floor_info(pk_list):
    # 층별 정보 누락 방지를 위해 PK 매칭 강화
    floor_data = []
    if os.path.exists("suwon_floor_info.csv.gz"):
        cols = ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']
        for chunk in pd.read_csv("suwon_floor_info.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in cols, chunksize=100000):
            chunk.columns = [clean_txt(c) for c in chunk.columns]
            res = chunk[chunk['관리건축물대장PK'].isin(pk_list)]
            if not res.empty: floor_data.extend(res.to_dict('records'))
    return floor_data

# --- 화면 구성 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 세류동 254 / 망포동 6-11")
    submitted = st.form_submit_button("🔍 정확한 정보 찾기")

if submitted:
    if query:
        res = search_building(query)
        if res:
            pk_list = [r['관리건축물대장PK'] for r in res]
            all_floors = get_floor_info(pk_list)
            
            st.success(f"✅ 총 {len(res)}개의 건축물을 찾았습니다.")
            
            for idx, b in enumerate(res):
                pk = b['관리건축물대장PK']
                bld_title = str(b.get('건물명', '')).replace('nan', '').strip() or f"건축물 {idx+1}"
                
                st.markdown(f"### 📌 {bld_title}")
                
                # 주소 박스
                st.markdown(f"""
                <div class="address-box">
                    <div style="font-size: 14px; color: #555;">📍 지번: {b.get('대지위치', '-')}</div>
                    <div style="font-size: 14px; color: #007bff; font-weight: bold; margin-top: 5px;">🛣️ 도로명: {b.get('도로명대지위치', '정보 없음')}</div>
                </div>
                """, unsafe_allow_html=True)
                
                st.write(f"🏢 **주용도:** {b.get('주용도코드명', '-')} | 📅 **사용승인:** {b.get('사용승인일', '-')}")

                # 4대 지표
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{b.get('지상층수', '0')}층")
                c2.metric("가구", f"{int(float(b.get('가구수(가구)', 0) or 0)) + int(float(b.get('세대수(세대)', 0) or 0))}가구")
                c3.metric("주차", f"{int(float(b.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0) if 'item' not in locals() else 0)}대") # 에러방지
                # 주차대수 합산 로직 보정
                parking = int(float(b.get('옥내자주식대수(대)', 0) or 0)) + int(float(b.get('옥외자주식대수(대)', 0) or 0))
                c3.metric("주차", f"{parking}대")
                elevator = int(float(b.get('승용승강기수', 0) or 0)) + int(float(b.get('비상용승강기수', 0) or 0))
                c4.metric("엘베", f"{elevator}대")

                # 층별 상세 현황 표
                st.markdown("<br><b>📊 층별 상세 현황</b>", unsafe_allow_html=True)
                my_floors = [f for f in all_floors if f['관리건축물대장PK'] == pk]
                
                if my_floors:
                    f_df = pd.DataFrame(my_floors)
                    f_df['sort_key'] = f_df['층번호'].apply(natural_sort_key)
                    f_df = f_df.sort_values('sort_key')
                    
                    tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th style="text-align:center;">가구/호</th><th style="text-align:right;">면적</th></tr>'
                    for _, f in f_df.iterrows():
                        etc = str(f.get('기타용도', ''))
                        g = re.search(r'(\d+)\s*(가구|호)', etc)
                        unit = g.group(0) if g else "-"
                        tbl += f'<tr><td class="row-floor">{f.get("층번호")}층</td><td>{f.get("주용도코드명", "-")}</td><td class="row-unit">{unit}</td><td style="text-align:right;">{f.get("면적(㎡)", "-")} ㎡</td></tr>'
                    tbl += '</table>'
                    st.markdown(tbl, unsafe_allow_html=True)
                else:
                    st.write("⚠️ 층별 상세 현황 데이터가 없습니다.")
                
                st.write("---")
            gc.collect()
        else:
            st.error("망포동 6-11을 포함하여 정확히 일치하는 지번 결과가 없습니다.")
