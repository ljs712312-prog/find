import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { color: #111111 !important; font-weight: 500 !important; }
    div[data-testid="stTextInput"] input {
        background-color: #ffffff !important; color: #000000 !important;
        border: 2px solid #007bff !important; border-radius: 12px; font-weight: 600 !important;
    }
    /* 검색 버튼 스타일 지정 */
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff; color: white; font-weight: 800; border-radius: 10px; padding: 10px; border: none;
    }
    .info-card { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 8px solid #6f42c1; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-top: 15px; }
    .violation-box { background-color: #ff4b4b; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 800; margin-bottom: 10px; }
    .data-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f1f3f5; font-size: 15px; }
    .badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

def get_jibun_only(text):
    match = re.search(r'(\d+)(?:-(\d+))?', str(text))
    if match:
        main = str(int(match.group(1)))
        sub = str(int(match.group(2))) if match.group(2) else ""
        return f"{main}-{sub}" if sub else main
    return ""

@st.cache_data
def load_data(file_key):
    # 사용자가 어떤 이름으로 파일을 올렸든 다 찾아서 실행 (에러 방지)
    possible_names = [
        f"{file_key}_full.csv.gz",
        f"processed_{file_key}.csv.gz",
        f"mini_{file_key}.csv.gz"
    ]
    if file_key == "unit_status": possible_names.append("suwon_unit_status.csv.gz")
    if file_key == "unit_area": possible_names.append("suwon_unit_area.csv.gz")
    if file_key == "master": possible_names.append("suwon_building_master.csv.gz")

    for name in possible_names:
        if os.path.exists(name):
            try:
                df = pd.read_csv(name, dtype=str)
                df.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', str(c)).strip() for c in df.columns]
                return df
            except: pass
    return None

st.title("🏢 원탑 건축물대장 추출기")

master = load_data("master")
floor = load_data("floor")
status = load_data("unit_status")
area = load_data("unit_area")

# 🚨 모바일 엔터 버그 해결을 위해 Form(폼) 형태로 묶음
with st.form("search_form"):
    query = st.text_input("📍 지번 주소 입력", placeholder="예: 망포동 6-11 또는 6-11")
    submitted = st.form_submit_button("🔍 검색하기")

if submitted:
    if not query:
        st.warning("주소를 입력해주세요.")
    elif master is None:
        st.error("🚨 깃허브에 데이터 파일이 하나도 없습니다. 데이터 파일을 먼저 업로드해주세요.")
    else:
        with st.spinner("검색 중입니다..."):
            addr_col = '대지위치' if '대지위치' in master.columns else master.columns[0]
            
            # 파일에 지번숫자 칼럼이 없으면 즉석에서 생성
            if '지번숫자' not in master.columns:
                master['지번숫자'] = master[addr_col].apply(get_jibun_only)
            
            q_jibun = get_jibun_only(query)
            q_dong = re.sub(r'[0-9-\s]', '', query)
            
            mask = (master['지번숫자'] == q_jibun)
            if q_dong:
                mask &= master[addr_col].fillna('').str.contains(q_dong, na=False)
            
            res = master[mask]

            if not res.empty:
                item = res.iloc[0]
                pk_col = '관리건축물대장PK' if '관리건축물대장PK' in master.columns else master.columns[1]
                pk = item.get(pk_col, '')
                
                # 위반 표시
                if str(item.get('위반건축물여부', '0')).strip() in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                    st.markdown('<div class="violation-box">🚨 위반건축물 확인 필요 🚨</div>', unsafe_allow_html=True)

                st.info(f"📍 **{item.get(addr_col, '주소')}**\n\n🏢 **용도:** {item.get('주용도코드명', '-')} | 📅 **사용승인:** {item.get('사용승인일', '-')}")
                
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
                if "집합" in str(item.get('대장구분코드명', '')):
                    st.markdown("#### 🔑 호수별 전용면적")
                    if status is not None and area is not None:
                        s_pk = '관리건축물대장PK' if '관리건축물대장PK' in status.columns else status.columns[0]
                        a_pk = '관리건축물대장PK' if '관리건축물대장PK' in area.columns else area.columns[0]
                        
                        t_status = status[status[s_pk] == pk]
                        t_area = area[(area[a_pk] == pk) & (area['전유공용구분코드'] == '1')] if '전유공용구분코드' in area.columns else area[area[a_pk] == pk]
                        
                        if not t_status.empty and not t_area.empty:
                            common_cols = [c for c in ['호명칭', '층번호'] if c in t_status.columns and c in t_area.columns]
                            merged = pd.merge(t_status, t_area, on=[s_pk] + common_cols, how='left')
                            for _, u in merged.sort_values(common_cols).iterrows():
                                st.markdown(f'<div class="data-row"><span>{u.get("층번호", "")}층 {u.get("호명칭", "")}</span><span style="color:#007bff; font-weight:800;">{u.get("면적(㎡)", u.get("전유면적(㎡)", "-"))} ㎡</span></div>', unsafe_allow_html=True)
                        else:
                            st.write("호수별 데이터가 없습니다.")
                else:
                    st.markdown("#### 🏢 층별 상세 현황")
                    if floor is not None:
                        f_pk = '관리건축물대장PK' if '관리건축물대장PK' in floor.columns else floor.columns[0]
                        f_list = floor[floor[f_pk] == pk]
                        if not f_list.empty:
                            for _, f in f_list.iterrows():
                                etc = str(f.get('기타용도', ''))
                                g = re.search(r'(\d+)\s*(가구|호)', etc)
                                badge = f' <span class="badge">{g.group(0)}</span>' if g else ""
                                st.markdown(f'<div class="data-row"><span>{f.get("층번호", "")}층 {f.get("주용도코드명", "")}</span>{badge}<span style="color:#007bff; font-weight:800;">{f.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                        else:
                            st.write("층별 데이터가 없습니다.")
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.error("결과를 찾을 수 없습니다.")
