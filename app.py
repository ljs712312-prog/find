import streamlit as st
import pandas as pd
import os
import re

# 📌 1. 페이지 설정 및 디자인
st.set_page_config(page_title="원탑 건축물대장 통합 마스터", page_icon="🏢", layout="centered")

st.markdown("""
    <style>
    /* 기본 폰트 설정 (중간 굵기 500-600) */
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { color: #111111 !important; font-weight: 500 !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 5px; }
    
    /* 검색창: 모바일/다크모드 대응 흰색 배경 고정 */
    div[data-testid="stTextInput"] input {
        font-size: 18px !important; font-weight: 600 !important; padding: 14px 15px !important; 
        color: #000000 !important; background-color: #ffffff !important; 
        border: 2px solid #007bff !important; border-radius: 12px;
    }

    /* 위반/정보 박스 디자인 */
    .violation-box { background-color: #dc3545; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 800; margin-bottom: 15px; }
    div[data-testid="stMetric"] { background-color: white; border: 1px solid #e0e6ed; padding: 15px 5px; border-radius: 15px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    
    .info-container { background-color: #ffffff; padding: 18px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .data-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #f1f3f5; font-size: 15px; }
    .label-col { font-weight: 800; color: #6f42c1; min-width: 65px; }
    .value-col { color: #007bff; font-weight: 800; min-width: 85px; text-align: right; }
    .badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; margin-left: 6px; }
    </style>
    """, unsafe_allow_html=True)

# 📌 2. 어떤 상황에서도 죽지 않는 데이터 로더
def super_load(file_name, file_type):
    if not os.path.exists(file_name):
        return None
    try:
        df = pd.read_csv(file_name, dtype=str)
        # 🚨 핵심: 칼럼명에서 보이지 않는 모든 쓰레기 문자 제거
        df.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', c) for c in df.columns]
        
        # 🚨 강제 매핑 (순서 기반 - 파일 구조가 바뀌지 않는 한 무조건 성공)
        if file_type == 'master':
            # mini_master: 0:주소, 1:PK, 2:구분, 3:층수, 4:가구, 5:세대, 6:면적, 7:사용일, 8:주차1, 9:주차2
            new_names = ['addr', 'pk', 'bld_type', 'floors', 'gagu', 'sadae', 'tot_area', 'app_date', 'p_in', 'p_out']
            df.columns = new_names + list(df.columns[len(new_names):])
        elif file_type == 'floor':
            # mini_floor: 0:PK, 1:층번호, 2:주용도, 3:기타용도, 4:면적
            new_names = ['pk', 'flr_no', 'purpose', 'etc', 'area']
            df.columns = new_names + list(df.columns[len(new_names):])
        elif file_type == 'unit':
            # mini_unit: 0:PK, 1:동, 2:호, 3:층, 4:면적
            new_names = ['pk', 'dong', 'ho', 'flr_no', 'area']
            df.columns = new_names + list(df.columns[len(new_names):])
            
        return df
    except:
        return None

# 📌 3. 메인 화면
st.markdown('<p class="main-title">🏢 원탑 건축물대장 통합 마스터</p>', unsafe_allow_html=True)
user_input = st.text_input("🔍 주소 입력", placeholder="예: 매탄동 1202-2")

if user_input:
    df_m = super_load("mini_master.csv.gz", "master")
    
    if df_m is not None:
        # 주소 검색 (하이픈, 공백 제거 후 비교)
        clean_input = user_input.replace(" ", "").replace("-", "")
        df_m['search'] = df_m['addr'].str.replace(" ", "").str.replace("-", "")
        res = df_m[df_m['search'].str.contains(clean_input, na=False)]

        if not res.empty:
            item = res.iloc[0]
            pk = item.get('pk')
            b_type = str(item.get('bld_type', ''))
            
            # 상단 정보
            st.info(f"📍 **주소:** {item.get('addr')} ({b_type})")

            c1, c2, c3 = st.columns(3)
            with c1: st.metric("🏗️ 층수", f"{item.get('floors', '0')}층")
            with c2: 
                h_sum = int(float(item.get('gagu', 0))) + int(float(item.get('sadae', 0)))
                st.metric("🏠 가구수", f"{h_sum}가구")
            with c3:
                p_sum = int(float(item.get('p_in', 0))) + int(float(item.get('p_out', 0)))
                st.metric("🚗 주차", f"{p_sum}대")

            # 상세 내역
            if "집합" in b_type:
                st.markdown('<div class="info-container"><b>🔑 호수별 전용면적</b>', unsafe_allow_html=True)
                df_u = super_load("mini_unit.csv.gz", "unit")
                if df_u is not None:
                    units = df_u[df_u['pk'] == pk]
                    if not units.empty:
                        # 층수 정렬
                        units['flr_int'] = pd.to_numeric(units['flr_no'], errors='coerce').fillna(0).astype(int)
                        for _, u in units.sort_values(['flr_int', 'ho']).iterrows():
                            st.markdown(f'<div class="data-row"><span class="label-col">{u.get("flr_no")}층</span><span>{u.get("ho")}</span><span class="value-col">{u.get("area")}㎡</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="info-container"><b>🏢 층별 상세 현황</b>', unsafe_allow_html=True)
                df_f = super_load("mini_floor.csv.gz", "floor")
                if df_f is not None:
                    floors = df_f[df_f['pk'] == pk]
                    if not floors.empty:
                        floors['flr_int'] = pd.to_numeric(floors['flr_no'], errors='coerce').fillna(0).astype(int)
                        for _, f in floors.sort_values('flr_int').iterrows():
                            etc = str(f.get('etc', ''))
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            badge = f' <span class="badge">{g.group(0)}</span>' if g else ""
                            st.markdown(f'<div class="data-row"><span class="label-col">{f.get("flr_no")}층</span><span>{f.get("purpose")}{badge}</span><span class="value-col">{f.get("area")}㎡</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("일치하는 주소가 없습니다. 번지수를 다시 확인해주세요.")
    else:
        st.error("데이터 로딩 실패. 파일 업로드 상태를 확인하세요.")
