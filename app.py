import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

# 📌 1. 디자인 (준석 님 스타일: 중간 굵기, 시인성)
st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { color: #111111 !important; font-weight: 500 !important; }
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #000000 !important;
        border: 2px solid #007bff !important; border-radius: 12px; font-weight: 600 !important;
    }
    .info-card { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 8px solid #6f42c1; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-top: 15px; }
    .violation-box { background-color: #ff4b4b; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 800; margin-bottom: 10px; }
    .data-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f1f3f5; font-size: 15px; }
    .badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# 📌 2. 지번 분석 로직 (검색어 처리)
def get_jibun_only(text):
    match = re.search(r'(\d+)(?:-(\d+))?', str(text))
    if match:
        main = str(int(match.group(1)))
        sub = str(int(match.group(2))) if match.group(2) else ""
        return f"{main}-{sub}" if sub else main
    return ""

@st.cache_data
def load_data(f):
    if os.path.exists(f): return pd.read_csv(f, dtype=str)
    return None

st.title("🏢 원탑 건축물대장 추출기")

# 데이터 로딩
master = load_data("master_full.csv.gz")
floor = load_data("floor_full.csv.gz")
status = load_data("unit_status_full.csv.gz")
area = load_data("unit_area_full.csv.gz")

query = st.text_input("📍 지번 주소 입력", placeholder="예: 망포동 6-11 또는 6-11")

if query and master is not None:
    # 검색어 정규화
    q_jibun = get_jibun_only(query)
    q_dong = re.sub(r'[0-9-\s]', '', query) # '망포동' 같은 동 이름만 추출
    
    # [검색 필터] 1.지번 숫자 일치 2.동 이름 포함
    mask = (master['지번숫자'] == q_jibun)
    if q_dong:
        mask &= master['대지위치'].str.contains(q_dong, na=False)
    
    res = master[mask]

    if not res.empty:
        item = res.iloc[0]
        pk = item.get('관리건축물대장PK', '')
        
        # 1. 위반 표시
        if str(item.get('위반건축물여부', '0')).strip() in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
            st.markdown('<div class="violation-box">🚨 위반건축물 확인 필요 🚨</div>', unsafe_allow_html=True)

        # 2. 건물 개요
        st.info(f"📍 **{item.get('대지위치')}**\n\n🏢 **용도:** {item.get('주용도코드명', '-')} | 📅 **사용승인:** {item.get('사용승인일', '-')}")
        
        # 3. 핵심 수치 (층수, 가구수, 주차, 엘베)
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("층수", f"{item.get('지상층수', '0')}층")
        with c2: 
            total_h = int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))
            st.metric("가구", f"{total_h}가구")
        with c3:
            total_p = int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))
            st.metric("주차", f"{total_p}대")
        with c4:
            total_e = int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))
            st.metric("엘베", f"{total_e}대")

        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        # 4. 상세 내역 (집합 vs 다가구)
        if "집합" in str(item.get('대장구분코드명', '')):
            st.markdown("#### 🔑 호수별 전용면적")
            if status is not None and area is not None:
                # 전유부 면적 매칭 (전용면적 코드 '1'만 추출)
                target_area = area[(area['관리건축물대장PK'] == pk) & (area['전유공용구분코드'] == '1')]
                target_status = status[status['관리건축물대장PK'] == pk]
                merged = pd.merge(target_status, target_area, on=['관리건축물대장PK', '호명칭', '층번호'], how='left')
                
                for _, u in merged.sort_values(['층번호', '호명칭']).iterrows():
                    st.markdown(f'<div class="data-row"><span>{u.get("층번호")}층 {u.get("호명칭")}</span><span style="color:#007bff; font-weight:800;">{u.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
        else:
            st.markdown("#### 🏢 층별 상세 현황")
            if floor is not None:
                f_list = floor[floor['관리건축물대장PK'] == pk]
                for _, f in f_list.iterrows():
                    etc = str(f.get('기타용도', ''))
                    g = re.search(r'(\d+)\s*(가구|호)', etc)
                    badge = f' <span class="badge">{g.group(0)}</span>' if g else ""
                    st.markdown(f'<div class="data-row"><span>{f.get("층번호")}층 {f.get("주용도코드명", "")}</span>{badge}<span style="color:#007bff; font-weight:800;">{f.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.error("결과를 찾을 수 없습니다. 지번 숫자를 정확히 입력했는지 확인해주세요.")
