import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 초기 디자인 (가장 만족하셨던 버전 기반)
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;800&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; color: #1e1e1e !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 20px; }
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #111111 !important;
        border: 2px solid #007bff !important; border-radius: 12px; padding: 14px !important; font-weight: 600 !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white; font-weight: 800; border-radius: 10px; padding: 12px; border: none;
    }
    .info-card {
        background-color: #ffffff; padding: 25px; border-radius: 15px;
        border-left: 8px solid #6f42c1; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 30px;
    }
    .address-box {
        background-color: #eef6ff; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid #d0e3ff;
    }
    .data-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #f1f3f5; font-size: 15px; }
    .label { font-weight: 700; color: #6f42c1; }
    .value { font-weight: 800; color: #007bff; }
    .badge { background-color: #ffc107; color: #212529; font-size: 13px; font-weight: 800; padding: 2px 6px; border-radius: 6px; margin-left: 8px;}
    .bld-header { font-size: 20px; font-weight: 800; color: #007bff; margin-top: 30px; margin-bottom: 10px; padding-bottom: 5px; border-bottom: 2px solid #007bff; }
</style>
""", unsafe_allow_html=True)

# 2. 검색 엔진 로직 (4단계 무적 시스템)
def clean_col_name(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

def to_int_str(val):
    # '0006' -> '6'으로 변환하는 핵심 함수
    try:
        return str(int(re.sub(r'[^0-9]', '', str(val))))
    except:
        return "0"

@st.cache_data(show_spinner="정보를 분석 중입니다...")
def powerful_search(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return None, None, None, None

    # [1단계] 입력값 전처리
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()
    nums = re.findall(r'\d+', query_str)
    q_main = str(int(nums[0])) if len(nums) > 0 else ""
    q_sub = str(int(nums[1])) if len(nums) > 1 else "0"
    is_san = '2' if '산' in query_str else '1'

    matched_results = []
    
    # [2단계] 숫자 정규화 매칭 (Main & Sub & San)
    # [3단계] 텍스트 포함 매칭 (Fallback)
    for chunk in pd.read_csv(f_master, dtype=str, chunksize=50000):
        chunk.columns = [clean_col_name(c) for c in chunk.columns]
        
        # 데이터의 번/지를 숫자로 변환 (0006 -> 6)
        chunk['norm_main'] = chunk['번'].apply(to_int_str)
        chunk['norm_sub'] = chunk['지'].apply(to_int_str)
        
        # 조건 A: 숫자와 대지구분(산 여부)이 완벽히 일치할 때
        mask = (chunk['norm_main'] == q_main) & (chunk['norm_sub'] == q_sub) & (chunk['대지구분코드'] == is_san)
        if q_dong:
            mask &= chunk['대지위치'].str.contains(q_dong, na=False)
        
        res = chunk[mask]
        
        # [4단계] 위 조건으로 안 나올 경우, 텍스트 기반 부분 일치 검색
        if res.empty and q_main:
            target_str = f"{q_main}-{q_sub}" if q_sub != "0" else q_main
            mask_fallback = chunk['대지위치'].str.contains(target_str, na=False)
            if q_dong:
                mask_fallback &= chunk['대지위치'].str.contains(q_dong, na=False)
            res = chunk[mask_fallback]
            
        if not res.empty:
            matched_results.extend(res.to_dict('records'))

    if not matched_results: return None, None, None, None

    pks = [r['관리건축물대장PK'] for r in matched_results]
    
    # 상세 데이터 로드
    floor = pd.read_csv("suwon_floor_info.csv.gz", dtype=str)
    floor.columns = [clean_col_name(c) for c in floor.columns]
    floor = floor[floor['관리건축물대장PK'].isin(pks)]

    status = pd.read_csv("suwon_unit_status.csv.gz", dtype=str)
    status.columns = [clean_col_name(c) for c in status.columns]
    status = status[status['관리건축물대장PK'].isin(pks)]

    area = pd.read_csv("suwon_unit_area.csv.gz", dtype=str)
    area.columns = [clean_col_name(c) for c in area.columns]
    area = area[(area['관리건축물대장PK'].isin(pks)) & (area.get('전유공용구분코드', '1') == '1')]

    gc.collect()
    return matched_results, floor, status, area

# 3. 화면 구성
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 세류동 147-9 / 망포동 6-11")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    if not query:
        st.warning("주소를 입력해주세요.")
    else:
        results, floor_df, status_df, area_df = powerful_search(query)
        
        if results:
            st.success(f"✅ 총 {len(results)}개의 건축물을 찾았습니다.")
            for idx, item in enumerate(results):
                pk = item['관리건축물대장PK']
                names = [n for n in [str(item.get('건물명', '')).strip(), str(item.get('동명칭', '')).strip()] if n and n != 'nan']
                title = " ".join(names) if names else f"건축물 {idx+1}"

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

                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                if "집합" in str(item.get('대장구분코드명', '')):
                    st.markdown("#### 🔑 호수별 전용면적")
                    t_stat = status_df[status_df['관리건축물대장PK'] == pk]
                    t_area = area_df[area_df['관리건축물대장PK'] == pk]
                    if not t_stat.empty and not t_area.empty:
                        merged = pd.merge(t_stat, t_area, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        for _, u in merged.drop_duplicates(['층번호', '호명칭']).sort_values(['층번호', '호명칭']).iterrows():
                            st.markdown(f'<div class="data-row"><span class="label">{u.get("층번호")}층 {u.get("호명칭")}</span><span class="value">{u.get("면적(㎡)")} ㎡</span></div>', unsafe_allow_html=True)
                else:
                    st.markdown("#### 🏢 층별 상세 현황")
                    f_list = floor_df[floor_df['관리건축물대장PK'] == pk]
                    for _, f in f_list.sort_values('층번호').iterrows():
                        etc = str(f.get('기타용도', ''))
                        g = re.search(r'(\d+)\s*(가구|호)', etc)
                        badge = f'<span class="badge">{g.group(0)}</span>' if g else ""
                        st.markdown(f'<div class="data-row"><span class="label">{f.get("층번호")}층 {f.get("주용도코드명")}{badge}</span><span class="value">{f.get("면적(㎡)")} ㎡</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("결과를 찾을 수 없습니다. 지번과 동 이름을 다시 확인해주세요.")
