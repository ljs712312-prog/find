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
    
    /* 헤더 및 타이틀 */
    .main-title { font-size: 28px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    
    /* 검색창 시인성 확보 (흰색 배경 고정) */
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #111111 !important;
        border: 2px solid #007bff !important; border-radius: 12px;
        padding: 15px !important; font-weight: 600 !important;
    }
    
    /* 검색 버튼 스타일 */
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white;
        font-weight: 700; border-radius: 10px; padding: 12px; border: none;
    }

    /* 결과 카드 디자인 */
    .info-card {
        background-color: #ffffff; padding: 25px; border-radius: 18px;
        border-left: 10px solid #6f42c1; box-shadow: 0 10px 25px rgba(0,0,0,0.05);
        margin-top: 20px;
    }
    
    .violation-banner {
        background-color: #d9534f; color: white; padding: 12px; border-radius: 10px;
        text-align: center; font-weight: 800; margin-bottom: 15px;
    }

    .data-row {
        display: flex; justify-content: space-between; padding: 12px 0;
        border-bottom: 1px solid #f1f3f5; font-size: 16px;
    }
    .label { font-weight: 700; color: #6f42c1; }
    .value { font-weight: 800; color: #007bff; }
    .badge { background-color: #ffc107; color: #212529; font-size: 13px; font-weight: 800; padding: 3px 8px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# 2. 지번 정규화 로직 (0006-0011 -> 6-11 무적 매칭)
def normalize_jibun(text):
    if pd.isna(text): return ""
    cleaned = re.sub(r'[^0-9-]', '', str(text).replace("산", ""))
    parts = [str(int(p)) for p in cleaned.split('-') if p.isdigit()]
    return "-".join(parts)

# 3. 메모리 세이프 데이터 로더 (원본 5개 파일 직접 사용)
@st.cache_data(show_spinner="데이터를 안전하게 로드하는 중입니다...")
def load_and_match(query_jibun, query_dong):
    # 파일명 정의
    f_master = "suwon_building_master.csv.gz"
    f_floor = "suwon_floor_info.csv.gz"
    f_status = "suwon_unit_status.csv.gz"
    f_area = "suwon_unit_area.csv.gz"

    if not os.path.exists(f_master): return None, None, None

    # 1. 마스터에서 검색 대상 찾기 (메모리 절약을 위해 필요한 칸만 읽음)
    m_cols = ['대지위치', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '위반건축물여부', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    matched_item = None
    
    # 마스터 파일을 쪼개서 읽으며 검색
    for chunk in pd.read_csv(f_master, dtype=str, usecols=m_cols, chunksize=50000):
        chunk.columns = chunk.columns.str.strip()
        chunk['temp_jibun'] = chunk['대지위치'].apply(normalize_jibun)
        
        mask = (chunk['temp_jibun'] == query_jibun)
        if query_dong:
            mask &= chunk['대지위치'].str.contains(query_dong, na=False)
        
        res = chunk[mask]
        if not res.empty:
            matched_item = res.iloc[0]
            break
    
    if matched_item is None: return None, None, None
    
    pk = matched_item['관리건축물대장PK']
    bld_type = str(matched_item['대장구분코드명'])
    
    # 2. 층별 또는 호수별 데이터 가져오기
    floor_data = pd.DataFrame()
    unit_data = pd.DataFrame()

    if "집합" in bld_type:
        # 호수별 데이터 병합 (상태 + 면적)
        if os.path.exists(f_status) and os.path.exists(f_area):
            s_df = pd.read_csv(f_status, dtype=str, usecols=['관리건축물대장PK', '층번호', '호명칭'])
            s_df = s_df[s_df['관리건축물대장PK'] == pk]
            
            a_df = pd.read_csv(f_area, dtype=str, usecols=['관리건축물대장PK', '층번호', '호명칭', '전유공용구분코드', '면적(㎡)'])
            a_df = a_df[(a_df['관리건축물대장PK'] == pk) & (a_df['전유공용구분코드'] == '1')]
            
            unit_data = pd.merge(s_df, a_df, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner').drop_duplicates()
    else:
        # 일반 건축물 층별 현황
        if os.path.exists(f_floor):
            f_df = pd.read_csv(f_floor, dtype=str, usecols=['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)'])
            floor_data = f_df[f_df['관리건축물대장PK'] == pk]

    gc.collect() # 메모리 청소
    return matched_item, floor_data, unit_data

# 4. 앱 화면 구성
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 망포동 6-11 또는 6-11")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    if not query:
        st.warning("주소를 입력해주세요.")
    else:
        q_jibun = normalize_jibun(query)
        q_dong = re.sub(r'[0-9-\s]', '', query)
        
        item, floor_df, unit_df = load_and_match(q_jibun, q_dong)
        
        if item is not None:
            # 위반 표시
            if str(item.get('위반건축물여부', '')).strip() in ['1', 'Y', '위반', '위반건축물']:
                st.markdown('<div class="violation-banner">🚨 위반건축물 확인 필요 🚨</div>', unsafe_allow_html=True)

            st.info(f"📍 **{item['대지위치']}**\n\n🏢 **용도:** {item.get('주용도코드명', '-')}  |  📅 **승인일:** {item.get('사용승인일', '-')}")
            
            # 메트릭 섹션 (상단 카드)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🏗️ 층수", f"{item.get('지상층수', '0')}층")
            c2.metric("🏠 가구", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
            c3.metric("🚗 주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
            c4.metric("🛗 엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            
            # 집합건축물: 호수별 전용면적 복구
            if not unit_df.empty:
                st.markdown("#### 🔑 호수별 전용면적")
                for _, u in unit_df.sort_values(['층번호', '호명칭']).iterrows():
                    st.markdown(f'<div class="data-row"><span class="label">{u["층번호"]}층 {u["호명칭"]}</span><span class="value">{u["면적(㎡)"]} ㎡</span></div>', unsafe_allow_html=True)
            
            # 일반건축물: 층별 현황
            elif not floor_df.empty:
                st.markdown("#### 🏢 층별 상세 현황")
                for _, f in floor_df.sort_values('층번호').iterrows():
                    etc = str(f.get('기타용도', ''))
                    g = re.search(r'(\d+)\s*(가구|호)', etc)
                    badge = f'<span class="badge">{g.group(0)}</span>' if g else ""
                    st.markdown(f'<div class="data-row"><span class="label">{f["층번호"]}층 {f["주용도코드명"]}</span>{badge}<span class="value">{f["면적(㎡)"]} ㎡</span></div>', unsafe_allow_html=True)
            
            else:
                st.write("상세 데이터가 없습니다.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("검색 결과가 없습니다. 지번을 정확히 입력했는지 확인해주세요.")
