import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 초기 이쁜 디자인 복구
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

# --- 유틸리티 함수 ---
def clean_col(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip()

def normalize_jibun(q):
    # 입력값에서 숫자만 뽑아 '본번-부번' 형태로 통일
    is_san = '2' if '산' in q else '1'
    nums = re.findall(r'\d+', q)
    main = str(int(nums[0])) if len(nums) > 0 else ""
    sub = str(int(nums[1])) if len(nums) > 1 else "0"
    return is_san, f"{main}-{sub}"

# --- 데이터 검색 로직 (메모리 효율 극대화) ---
@st.cache_data(show_spinner="건물을 찾는 중...")
def search_master(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []
    
    is_san_q, q_jibun_full = normalize_jibun(query_str)
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()
    
    results = []
    # 마스터 파일만 먼저 읽어서 검색 (나머지 파일은 나중에 로드)
    m_cols = ['대지위치', '대지구분코드', '번', '지', '도로명대지위치', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    for chunk in pd.read_csv(f_master, dtype=str, chunksize=50000):
        chunk.columns = [clean_col(c) for c in chunk.columns]
        # 데이터의 0006-0011 -> 6-11 변환
        chunk['search_key'] = chunk['번'].fillna('0').apply(lambda x: str(int(x)) if x.isdigit() else "") + "-" + \
                              chunk['지'].fillna('0').apply(lambda x: str(int(x)) if x.isdigit() else "0")
        
        mask = (chunk['search_key'] == q_jibun_full) & (chunk['대지구분코드'] == is_san_q)
        if q_dong: mask &= chunk['대지위치'].str.contains(q_dong, na=False)
        
        res = chunk[mask]
        if not res.empty: results.extend(res.to_dict('records'))
    return results

@st.cache_data(show_spinner="상세 면적 정보를 가져오는 중...")
def get_details(pks):
    # 상세 정보는 검색된 PK가 있을 때만 해당 줄만 골라서 읽음
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
    return floor, status, area

# --- 메인 화면 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 또는 동 주소 입력", placeholder="예: 망포동 6-11 / 망포동 산 12-3")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    if not query:
        st.warning("검색어를 입력해주세요.")
    else:
        results = search_master(query)
        
        if results:
            st.success(f"✅ 해당 지번에서 총 {len(results)}개의 건축물을 찾았습니다.")
            pks = [r['관리건축물대장PK'] for r in results]
            f_df, s_df, a_df = get_details(pks)
            
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

                st.write(f"🏢 **주용도:** {item.get('주용도코드명', '-')} | 📅 **승인:** {item.get('사용승인일', '-')}")
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{item.get('지상층수', '0')}층")
                c2.metric("가구", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
                c3.metric("주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
                c4.metric("엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                # 상세 정보 (집합 vs 일반)
                if "집합" in str(item.get('대장구분코드명', '')):
                    st.markdown("#### 🔑 호수별 전용면적")
                    t_stat = s_df[s_df['관리건축물대장PK'] == pk]
                    t_area = a_df[a_df['관리건축물대장PK'] == pk]
                    if not t_stat.empty and not t_area.empty:
                        merged = pd.merge(t_stat, t_area, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        for _, u in merged.drop_duplicates(['층번호', '호명칭']).sort_values(['층번호', '호명칭']).iterrows():
                            st.markdown(f'<div class="data-row"><span class="label">{u.get("층번호")}층 {u.get("호명칭")}</span><span class="value">{u.get("면적(㎡)")} ㎡</span></div>', unsafe_allow_html=True)
                    else: st.write("상세 면적 데이터가 없습니다.")
                else:
                    st.markdown("#### 🏢 층별 상세 현황")
                    t_floor = f_df[f_df['관리건축물대장PK'] == pk]
                    if not t_floor.empty:
                        for _, f in t_floor.sort_values('층번호').iterrows():
                            etc = str(f.get('기타용도', ''))
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            badge = f'<span class="badge">{g.group(0)}</span>' if g else ""
                            st.markdown(f'<div class="data-row"><span class="label">{f.get("층번호")}층 {f.get("주용도코드명")}{badge}</span><span class="value">{f.get("면적(㎡)")} ㎡</span></div>', unsafe_allow_html=True)
                    else: st.write("층별 데이터가 없습니다.")
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("결과를 찾을 수 없습니다. 지번(산 포함)과 동 주소를 정확히 입력했는지 확인해주세요.")
