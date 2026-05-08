import streamlit as st
import pandas as pd
import re
import os

# 📌 페이지 설정
st.set_page_config(page_title="원탑 건축물대장 추출기", page_icon="🏢", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { color: #111111 !important; font-weight: 500 !important; }
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #111111 !important;
        border: 2px solid #007bff !important; border-radius: 12px; font-weight: 600 !important;
    }
    .info-card { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 8px solid #6f42c1; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-top: 15px; }
    .data-row { display: flex; justify-content: space-between; border-bottom: 1px solid #f1f3f5; padding: 10px 0; }
    .violation-tag { background-color: #ff4b4b; color: white; padding: 10px; border-radius: 10px; text-align: center; font-weight: 800; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

def normalize_query(text):
    # 사용자가 입력한 주소도 데이터와 똑같은 방식으로 정규화
    text = str(text).replace("번지", "").replace(" ", "").replace("-", " ")
    parts = text.split()
    if not parts: return ""
    dong = parts[0] if not parts[0].isdigit() else ""
    jibun = parts[-1]
    if ' ' in text and len(parts) >= 2:
        jibun = parts[-1]
        if '-' in jibun or jibun.isdigit():
            # 1202-02 -> 1202-2
            j_parts = [str(int(p)) for p in jibun.split('-') if p.isdigit()]
            return f"{dong}{'-'.join(j_parts)}"
    return text

@st.cache_data
def load_data(f):
    if os.path.exists(f): return pd.read_csv(f, dtype=str)
    return None

st.markdown('### 🏢 원탑 건축물대장 추출기 (최종안정판)')

master = load_data("final_master.csv.gz")
floor = load_data("final_floor.csv.gz")
unit = load_data("final_unit.csv.gz")

if master is not None:
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 매탄동 1202-2")

    if query:
        q_key = normalize_query(query)
        # 검색키에서 사용자가 입력한 지번이 포함된 것 찾기
        res = master[master['검색키'].str.contains(q_key, na=False)]

        if not res.empty:
            item = res.iloc[0]
            pk = item.get('관리건축물대장PK', '')
            
            # 위반 표시
            if str(item.get('위반건축물여부', '0')) in ['1', 'Y', '위반', '위반건축물']:
                st.markdown('<div class="violation-tag">🚨 위반건축물 주의 🚨</div>', unsafe_allow_html=True)

            st.info(f"📍 **{item.get('대지위치')}**\n\n🏢 **용도:** {item.get('주용도코드명', '-')} | 📅 **승인일:** {item.get('사용승인일', '-')}")

            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("층수", f"{item.get('지상층수', '0')}층")
            with c2: st.metric("가구", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
            with c3: st.metric("주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
            with c4: st.metric("엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            if "집합" in str(item.get('대장구분코드명', '')):
                st.markdown("#### 🔑 호수별 전용면적")
                if unit is not None:
                    u_list = unit[unit['관리건축물대장PK'] == pk]
                    for _, u in u_list.iterrows():
                        st.markdown(f'<div class="data-row"><span>{u.get("층번호")}층 {u.get("호명칭")}</span><span style="color:#007bff; font-weight:800;">{u.get("면적(㎡)", u.get("전유면적(㎡)", "-"))} ㎡</span></div>', unsafe_allow_html=True)
            else:
                st.markdown("#### 🏢 층별 상세 현황")
                if floor is not None:
                    f_list = floor[floor['관리건축물대장PK'] == pk]
                    for _, f in f_list.iterrows():
                        etc = str(f.get('기타용도', ''))
                        g = re.search(r'(\d+)\s*(가구|호)', etc)
                        badge = f' <span style="background:#ffc107; padding:2px 5px; border-radius:5px; font-size:12px;">{g.group(0)}</span>' if g else ""
                        st.markdown(f'<div class="data-row"><span>{f.get("층번호")}층 {f.get("주용도코드명")}</span>{badge}<span style="color:#007bff; font-weight:800;">{f.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("결과를 찾을 수 없습니다. 지번을 정확히 입력해주세요.")
