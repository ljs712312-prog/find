import streamlit as st
import pandas as pd
import re
import os

# 1. 페이지 설정
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

# 2. UI 디자인
st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { color: #111111 !important; font-weight: 500 !important; }
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #111111 !important;
        border: 2px solid #007bff !important; border-radius: 12px; font-weight: 600 !important;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white; font-weight: 800; border-radius: 10px; padding: 10px;
    }
    .info-card { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 8px solid #6f42c1; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-top: 15px; }
    .violation { background-color: #ff4b4b; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 800; margin-bottom: 10px; }
    .data-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f1f3f5; font-size: 15px; }
    .badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

def normalize_jibun(text):
    if pd.isna(text): return ""
    cleaned = re.sub(r'[^0-9-]', '', str(text).replace("산", ""))
    parts = [str(int(p)) for p in cleaned.split('-') if p.isdigit()]
    return "-".join(parts)

# 🚨 파일 읽기 실패 시에도 프로그램이 멈추지 않도록 예외 처리 강화
@st.cache_data(show_spinner="데이터를 분석 중입니다...")
def load_raw_data():
    files = {
        "master": ("suwon_building_master.csv.gz", ['대지위치', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '위반건축물여부', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']),
        "floor": ("suwon_floor_info.csv.gz", ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']),
        "status": ("suwon_unit_status.csv.gz", ['관리건축물대장PK', '호명칭', '층번호']),
        "area": ("suwon_unit_area.csv.gz", ['관리건축물대장PK', '호명칭', '층번호', '전유공용구분코드', '면적(㎡)'])
    }
    
    data = {}
    for key, (f, cols) in files.items():
        df = pd.DataFrame() # 기본값을 빈 데이터로 설정
        if os.path.exists(f):
            try:
                df_temp = pd.read_csv(f, nrows=1)
                actual_cols = [c for c in cols if c in df_temp.columns]
                df = pd.read_csv(f, dtype=str, usecols=actual_cols)
                df.columns = [c.strip() for c in df.columns]
            except Exception:
                pass # 파일이 깨져있어도 멈추지 않고 넘어감
        data[key] = df
            
    if not data["master"].empty and '대지위치' in data["master"].columns:
        data["master"]['norm_jibun'] = data["master"]['대지위치'].apply(normalize_jibun)
        
    return data["master"], data["floor"], data["status"], data["area"]

st.markdown('### 🏢 원탑 건축물대장 추출기')

master, floor, status, area = load_raw_data()

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 망포동 6-11 / 세류동 147-9")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    # 🚨 오류 수정 포인트: master가 None인지 확인하는 조건 추가
    if master is None or master.empty:
        st.error("서버에 원본 데이터가 없거나 파일을 읽지 못했습니다. 깃허브에 원본 압축파일이 제대로 올라갔는지 확인해주세요.")
    elif query:
        q_norm = normalize_jibun(query)
        q_dong = re.sub(r'[0-9-\s]', '', query)
        
        mask = (master['norm_jibun'] == q_norm)
        if q_dong:
            mask &= master['대지위치'].fillna('').str.contains(q_dong, na=False)
            
        res = master[mask]
        
        if not res.empty:
            item = res.iloc[0]
            pk = str(item.get('관리건축물대장PK', ''))
            
            if str(item.get('위반건축물여부', '')).strip() in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.markdown('<div class="violation">🚨 위반건축물 확인 필요 🚨</div>', unsafe_allow_html=True)

            st.info(f"📍 **{item.get('대지위치', '주소 없음')}**\n\n🏢 **용도:** {item.get('주용도코드명', '-')} | 📅 **승인:** {item.get('사용승인일', '-')}")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("층수", f"{item.get('지상층수', '0')}층")
            c2.metric("가구", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
            c3.metric("주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
            c4.metric("엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            if "집합" in str(item.get('대장구분코드명', '')):
                st.markdown("#### 🔑 호수별 전용면적")
                if status is not None and not status.empty and area is not None and not area.empty:
                    t_stat = status[status['관리건축물대장PK'] == pk]
                    t_area = area[(area['관리건축물대장PK'] == pk) & (area.get('전유공용구분코드', '1') == '1')]
                    if not t_stat.empty and not t_area.empty:
                        merged = pd.merge(t_stat, t_area, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        for _, u in merged.drop_duplicates(['층번호', '호명칭']).sort_values(['층번호', '호명칭']).iterrows():
                            st.markdown(f'<div class="data-row"><span>{u.get("층번호")}층 {u.get("호명칭")}</span><span style="color:#007bff; font-weight:800;">{u.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                    else: st.write("상세 정보 없음")
                else: st.write("상세 정보 없음")
            else:
                st.markdown("#### 🏢 층별 상세 현황")
                if floor is not None and not floor.empty:
                    f_list = floor[floor['관리건축물대장PK'] == pk]
                    for _, f in f_list.sort_values('층번호').iterrows():
                        etc = str(f.get('기타용도', ''))
                        g = re.search(r'(\d+)\s*(가구|호)', etc)
                        badge = f' <span class="badge">{g.group(0)}</span>' if g else ""
                        st.markdown(f'<div class="data-row"><span>{f.get("층번호")}층 {f.get("주용도코드명", "")}</span>{badge}<span style="color:#007bff; font-weight:800;">{f.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                else: st.write("상세 정보 없음")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error(f"'{query}' 정보를 찾을 수 없습니다. (지번: {q_norm})")
