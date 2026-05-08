import streamlit as st
import pandas as pd
import re
import os
import gc

st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

# 📌 가장 직관적이고 예쁜 초기 UI 디자인 적용
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
        margin-top: 20px;
    }
    
    .violation-banner {
        background-color: #d9534f; color: white; padding: 12px; border-radius: 10px;
        text-align: center; font-weight: 800; margin-bottom: 15px;
    }

    .data-row {
        display: flex; justify-content: space-between; padding: 10px 0;
        border-bottom: 1px solid #f1f3f5; font-size: 15px;
    }
    .label { font-weight: 700; color: #6f42c1; }
    .value { font-weight: 800; color: #007bff; }
    .badge { background-color: #ffc107; color: #212529; font-size: 13px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# 📌 0006-0011 같은 쓰레기 지번도 6-11로 완벽 변환
def normalize_jibun(text):
    if pd.isna(text): return ""
    cleaned = re.sub(r'[^0-9-]', '', str(text).replace("산", ""))
    parts = [str(int(p)) for p in cleaned.split('-') if p.isdigit()]
    return "-".join(parts)

# 📌 찌꺼기 완벽 제거 + 메모리 안전 추출기
@st.cache_data(show_spinner="건물 정보를 찾는 중입니다...")
def search_building(query_jibun, query_dong):
    matched_item = None
    if not os.path.exists("suwon_building_master.csv.gz"):
        return None, [], []

    # 1. 표제부 검색 (에러 원천 차단)
    for chunk in pd.read_csv("suwon_building_master.csv.gz", dtype=str, chunksize=50000, on_bad_lines='skip'):
        # 컬럼명 찌꺼기 완벽 청소
        chunk.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)) for c in chunk.columns]
        
        # '대지위치' 글자가 훼손됐어도 첫 번째 칸 강제 인식
        addr_col = '대지위치' if '대지위치' in chunk.columns else chunk.columns[0]
        
        chunk['temp_jibun'] = chunk[addr_col].apply(normalize_jibun)
        mask = (chunk['temp_jibun'] == query_jibun)
        if query_dong:
            mask &= chunk[addr_col].fillna('').str.contains(query_dong, na=False)
            
        res = chunk[mask]
        if not res.empty:
            matched_item = res.iloc[0].to_dict()
            matched_item['_addr_'] = matched_item.get(addr_col, '')
            # PK값도 훼손 대비 (보통 7번째 칸)
            pk_col = '관리건축물대장PK' if '관리건축물대장PK' in chunk.columns else chunk.columns[6]
            matched_item['_pk_'] = matched_item.get(pk_col, '')
            break

    if not matched_item:
        return None, [], []

    pk = matched_item['_pk_']
    bld_type = str(matched_item.get('대장구분코드명', ''))
    
    floor_list = []
    unit_list = []

    # 2. 호수별 면적 (집합건축물)
    if "집합" in bld_type:
        s_df = pd.DataFrame()
        if os.path.exists("suwon_unit_status.csv.gz"):
            for chunk in pd.read_csv("suwon_unit_status.csv.gz", dtype=str, chunksize=50000, on_bad_lines='skip'):
                chunk.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)) for c in chunk.columns]
                s_pk = '관리건축물대장PK' if '관리건축물대장PK' in chunk.columns else chunk.columns[6]
                temp = chunk[chunk[s_pk] == pk]
                if not temp.empty: s_df = pd.concat([s_df, temp])
        
        a_df = pd.DataFrame()
        if os.path.exists("suwon_unit_area.csv.gz"):
            for chunk in pd.read_csv("suwon_unit_area.csv.gz", dtype=str, chunksize=50000, on_bad_lines='skip'):
                chunk.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)) for c in chunk.columns]
                a_pk = '관리건축물대장PK' if '관리건축물대장PK' in chunk.columns else chunk.columns[6]
                temp = chunk[chunk[a_pk] == pk]
                if '전유공용구분코드' in temp.columns:
                    temp = temp[temp['전유공용구분코드'] == '1'] # 전용면적만 추출
                if not temp.empty: a_df = pd.concat([a_df, temp])
                
        if not s_df.empty and not a_df.empty:
            merge_cols = [c for c in ['관리건축물대장PK', '층번호', '호명칭'] if c in s_df.columns and c in a_df.columns]
            if merge_cols:
                unit_data = pd.merge(s_df, a_df, on=merge_cols, how='inner').drop_duplicates()
                unit_list = unit_data.to_dict('records')

    # 3. 층별 상세 (일반건축물)
    else:
        if os.path.exists("suwon_floor_info.csv.gz"):
            for chunk in pd.read_csv("suwon_floor_info.csv.gz", dtype=str, chunksize=50000, on_bad_lines='skip'):
                chunk.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)) for c in chunk.columns]
                f_pk = '관리건축물대장PK' if '관리건축물대장PK' in chunk.columns else chunk.columns[6]
                temp = chunk[chunk[f_pk] == pk]
                if not temp.empty:
                    floor_list.extend(temp.to_dict('records'))

    gc.collect()
    return matched_item, floor_list, unit_list

# 📌 메인 화면 실행
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 망포동 6-11 또는 6-11")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    if not query:
        st.warning("주소를 입력해주세요.")
    elif not os.path.exists("suwon_building_master.csv.gz"):
        st.error("🚨 깃허브에 원본 파일(suwon_...csv.gz)이 올라가 있는지 확인해주세요.")
    else:
        q_jibun = normalize_jibun(query)
        q_dong = re.sub(r'[0-9-\s]', '', query)
        
        item, floors, units = search_building(q_jibun, q_dong)
        
        if item:
            # 위반건축물 경고
            if str(item.get('위반건축물여부', '')).strip() in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.markdown('<div class="violation-banner">🚨 위반건축물 확인 필요 🚨</div>', unsafe_allow_html=True)

            st.info(f"📍 **{item.get('_addr_', '')}**\n\n🏢 **용도:** {item.get('주용도코드명', '-')}  |  📅 **승인일:** {item.get('사용승인일', '-')}")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🏗️ 층수", f"{item.get('지상층수', '0')}층")
            c2.metric("🏠 가구", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
            c3.metric("🚗 주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
            c4.metric("🛗 엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            
            # 집합건축물 (호수별)
            if "집합" in str(item.get('대장구분코드명', '')):
                if units:
                    st.markdown("#### 🔑 호수별 전용면적")
                    # 층, 호수로 정렬하여 출력
                    for u in sorted(units, key=lambda x: (str(x.get('층번호', '')).zfill(3), str(x.get('호명칭', '')).zfill(5))):
                        st.markdown(f'<div class="data-row"><span class="label">{u.get("층번호", "")}층 {u.get("호명칭", "")}</span><span class="value">{u.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                else:
                    st.write("상세 데이터가 없습니다.")
            
            # 일반건축물 (층별)
            else:
                if floors:
                    st.markdown("#### 🏢 층별 상세 현황")
                    for f in sorted(floors, key=lambda x: str(x.get('층번호', '')).zfill(3)):
                        etc = str(f.get('기타용도', ''))
                        g = re.search(r'(\d+)\s*(가구|호)', etc)
                        badge = f'<span class="badge">{g.group(0)}</span>' if g else ""
                        st.markdown(f'<div class="data-row"><span class="label">{f.get("층번호", "")}층 {f.get("주용도코드명", "")}</span>{badge}<span class="value">{f.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                else:
                    st.write("상세 데이터가 없습니다.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("검색 결과가 없습니다. 지번을 정확히 입력했는지 확인해주세요.")
