import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 초기 이쁜 디자인 유지
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; color: #1e1e1e !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #111111 !important;
        border: 2px solid #007bff !important; border-radius: 12px;
        padding: 14px !important; font-weight: 600 !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white;
        font-weight: 800; border-radius: 10px; padding: 12px; border: none;
    }
    .info-card {
        background-color: #ffffff; padding: 25px; border-radius: 15px;
        border-left: 8px solid #6f42c1; box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        margin-top: 15px; margin-bottom: 30px;
    }
    .address-box {
        background-color: #eef6ff; padding: 15px; border-radius: 10px;
        margin-bottom: 15px; border: 1px solid #d0e3ff;
    }
    .data-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #f1f3f5; font-size: 15px; }
    .label { font-weight: 700; color: #6f42c1; }
    .value { font-weight: 800; color: #007bff; }
    .badge { background-color: #ffc107; color: #212529; font-size: 13px; font-weight: 800; padding: 2px 6px; border-radius: 6px; margin-left: 8px;}
    .bld-header { font-size: 20px; font-weight: 800; color: #007bff; margin-top: 30px; margin-bottom: 10px; padding-bottom: 5px; border-bottom: 2px solid #007bff; }
</style>
""", unsafe_allow_html=True)

# --- 0 제거 및 숫자 변환 ---
def to_int(v):
    try: return str(int(re.sub(r'[^0-9]', '', str(v))))
    except: return "0"

# --- 제목 nan 처리 로직 ---
def get_clean_title(item, idx):
    bld_name = str(item.get('건물명', '')).strip()
    dong_name = str(item.get('동명칭', '')).strip()
    
    names = []
    if bld_name and bld_name.lower() != 'nan':
        names.append(bld_name)
    if dong_name and dong_name.lower() != 'nan':
        names.append(f"({dong_name})")
    
    if not names:
        return f"건축물 {idx + 1}"
    return " ".join(names)

@st.cache_data(show_spinner="정밀 분석 중...")
def strict_search(query_str):
    f_path = "suwon_building_master.csv.gz"
    if not os.path.exists(f_path): return []
    
    # 입력값에서 본번-부번 추출
    nums = re.findall(r'\d+', query_str)
    q_main = str(int(nums[0])) if len(nums) > 0 else ""
    q_sub = str(int(nums[1])) if len(nums) > 1 else "0"
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    results = []
    for chunk in pd.read_csv(f_path, dtype=str, chunksize=50000):
        # 헤더 청소
        chunk.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip() for c in chunk.columns]
        
        # 완전 일치 검색 (번-지 숫자가 정확히 맞아야 함)
        chunk['n_main'] = chunk['번'].apply(to_int)
        chunk['n_sub'] = chunk['지'].apply(to_int)
        
        mask = (chunk['n_main'] == q_main) & (chunk['n_sub'] == q_sub)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            results.extend(res.to_dict('records'))
    return results

# --- 메인 실행 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 세류동 254")
    submitted = st.form_submit_button("🔍 정확한 정보 찾기")

if submitted:
    if query:
        res = strict_search(query)
        if res:
            st.success(f"✅ 총 {len(res)}개의 건축물을 찾았습니다.")
            for idx, item in enumerate(res):
                # nan 없는 깔끔한 제목 가져오기
                title = get_clean_title(item, idx)

                st.markdown(f'<div class="bld-header">📌 {title}</div>', unsafe_allow_html=True)
                
                st.markdown(f"""
                <div class="address-box">
                    <div style="font-size: 14px; color: #555;">📍 지번: {item.get('대지위치', '-')}</div>
                    <div style="font-size: 15px; color: #007bff; font-weight: 800; margin-top: 5px;">🛣️ 도로명: {item.get('도로명대지위치', '정보 없음')}</div>
                </div>
                """, unsafe_allow_html=True)

                st.write(f"🏢 **주용도:** {item.get('주용도코드명', '-')} | 📅 **사용승인:** {item.get('사용승인일', '-')}")
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{item.get('지상층수', '0')}층")
                c2.metric("가구", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
                c3.metric("주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
                c4.metric("엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

                # 상세 현황 섹션 (이전의 깔끔한 박스 형태 유지)
                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                st.write("💡 *층별 상세 현황은 원본 데이터에 따라 가구수가 표시되지 않을 수 있습니다.*")
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("정확히 일치하는 지번이 없습니다.")
