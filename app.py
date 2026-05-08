import streamlit as st
import pandas as pd
import re
import os

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
        margin-top: 20px;
    }
    
    .violation-banner {
        background-color: #d9534f; color: white; padding: 12px; border-radius: 10px;
        text-align: center; font-weight: 800; margin-bottom: 15px;
    }

    .data-row {
        display: flex; justify-content: space-between; align-items: center; padding: 10px 0;
        border-bottom: 1px solid #f1f3f5; font-size: 15px;
    }
    .label { font-weight: 700; color: #6f42c1; }
    .value { font-weight: 800; color: #007bff; }
    .badge { background-color: #ffc107; color: #212529; font-size: 13px; font-weight: 800; padding: 2px 6px; border-radius: 6px; margin-left: 8px;}
</style>
""", unsafe_allow_html=True)

def normalize_jibun(text):
    if pd.isna(text): return ""
    cleaned = re.sub(r'[^0-9-]', '', str(text).replace("산", ""))
    parts = [str(int(p)) for p in cleaned.split('-') if p.isdigit()]
    return "-".join(parts)

def clean_col(c):
    return re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c))

@st.cache_data(show_spinner="대용량 원본 데이터를 분석 중입니다. (최초 1회 약 20초 소요)")
def load_data():
    master_cols = ['대지위치', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '위반건축물여부', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    floor_cols = ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']
    status_cols = ['관리건축물대장PK', '호명칭', '층번호']
    area_cols = ['관리건축물대장PK', '호명칭', '층번호', '전유공용구분코드', '면적(㎡)']

    def safe_read(file_path, target_cols):
        if not os.path.exists(file_path): return pd.DataFrame()
        try:
            df = pd.read_csv(file_path, dtype=str, usecols=lambda x: clean_col(x) in target_cols, on_bad_lines='skip')
            df.columns = [clean_col(c) for c in df.columns]
            return df
        except:
            return pd.DataFrame()

    master = safe_read("suwon_building_master.csv.gz", master_cols)
    if not master.empty and '대지위치' in master.columns:
        master['검색용지번'] = master['대지위치'].apply(normalize_jibun)

    floor = safe_read("suwon_floor_info.csv.gz", floor_cols)
    status = safe_read("suwon_unit_status.csv.gz", status_cols)
    
    area = safe_read("suwon_unit_area.csv.gz", area_cols)
    if not area.empty and '전유공용구분코드' in area.columns:
        area = area[area['전유공용구분코드'] == '1'] # 공용면적 제외, 전용면적만 추출

    return master, floor, status, area

st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

master, floor, status, area = load_data()

with st.form("search_form"):
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 망포동 6-11 또는 6-11")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    if not query:
        st.warning("주소를 입력해주세요.")
    elif master.empty:
        st.error("🚨 깃허브에 원본 파일(suwon_...csv.gz)이 없습니다. 데이터 파일을 먼저 업로드해주세요.")
    else:
        q_jibun = normalize_jibun(query)
        q_dong = re.sub(r'[0-9-\s]', '', query)
        
        mask = (master['검색용지번'] == q_jibun)
        if q_dong: mask &= master['대지위치'].fillna('').str.contains(q_dong, na=False)
        
        res = master[mask]
        
        if not res.empty:
            item = res.iloc[0]
            pk = str(item.get('관리건축물대장PK', ''))
            
            if str(item.get('위반건축물여부', '')).strip() in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.markdown('<div class="violation-banner">🚨 위반건축물 확인 필요 🚨</div>', unsafe_allow_html=True)

            st.info(f"📍 **{item.get('대지위치', '')}**\n\n🏢 **용도:** {item.get('주용도코드명', '-')} | 📅 **승인:** {item.get('사용승인일', '-')}")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🏗️ 층수", f"{item.get('지상층수', '0')}층")
            c2.metric("🏠 가구", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
            c3.metric("🚗 주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
            c4.metric("🛗 엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            
            # 집합건축물 (다세대, 아파트, 오피스텔 등)
            if "집합" in str(item.get('대장구분코드명', '')):
                st.markdown("#### 🔑 호수별 전용면적")
                if not status.empty and not area.empty:
                    t_stat = status[status['관리건축물대장PK'] == pk]
                    t_area = area[area['관리건축물대장PK'] == pk]
                    if not t_stat.empty and not t_area.empty:
                        merged = pd.merge(t_stat, t_area, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        for _, u in merged.drop_duplicates(['층번호', '호명칭']).sort_values(['층번호', '호명칭']).iterrows():
                            st.markdown(f'<div class="data-row"><span class="label">{u.get("층번호", "")}층 {u.get("호명칭", "")}</span><span class="value">{u.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                    else: st.write("상세 정보가 없습니다.")
                else: st.write("상세 정보가 없습니다.")
            
            # 일반건축물 (단독, 다가구 등)
            else:
                st.markdown("#### 🏢 층별 상세 현황")
                if not floor.empty:
                    f_list = floor[floor['관리건축물대장PK'] == pk]
                    if not f_list.empty:
                        for _, f in f_list.sort_values('층번호').iterrows():
                            etc = str(f.get('기타용도', ''))
                            # 수기 기재된 'N가구/호' 정규식 추출
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            badge = f'<span class="badge">{g.group(0)}</span>' if g else ""
                            st.markdown(f'<div class="data-row"><span class="label">{f.get("층번호", "")}층 {f.get("주용도코드명", "")}{badge}</span><span class="value">{f.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                    else: st.write("상세 정보가 없습니다.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("검색 결과가 없습니다. 지번을 확인해주세요.")
