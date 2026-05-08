import streamlit as st
import pandas as pd
import os
import re

# 📌 1. 페이지 설정 및 디자인
st.set_page_config(page_title="원탑 건축물대장 통합 마스터", page_icon="🏢", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"]  { color: #111111 !important; font-weight: 400 !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 5px; }
    
    div[data-testid="stTextInput"] input {
        font-size: 20px !important; font-weight: 600 !important; padding: 16px 15px !important; 
        background-color: #ffffff !important; border: 2px solid #007bff !important; border-radius: 12px;
    }

    .info-container { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .data-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #e9ecef; }
    .label-col { font-weight: 800; color: #6f42c1; min-width: 70px; }
    .desc-col { color: #111111; text-align: right; font-weight: 600; flex-grow: 1; } 
    .value-col { color: #007bff; font-weight: 800; min-width: 90px; text-align: right; margin-left: 10px; }
    .badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; margin-left: 6px; }
    </style>
    """, unsafe_allow_html=True)

# 📌 2. 데이터 로딩 및 이름표 정리 함수
@st.cache_data
def load_mini_data(file_name):
    if os.path.exists(file_name):
        # 유령 문자(BOM) 방지를 위해 utf-8-sig 사용 시도
        try:
            df = pd.read_csv(file_name, dtype=str)
        except:
            return None
            
        # 칼럼명 앞뒤 공백 및 유령 문자(\ufeff) 완벽 제거
        df.columns = [c.strip().lstrip('\ufeff') for c in df.columns]
        
        # 🚨 한글 이름표를 안전한 내부 이름표로 매핑
        mapping = {
            '대지위치': 'address', '관리건축물대장PK': 'pk', '대장구분코드명': 'bld_type',
            '지상층수': 'floors', '가구수(가구)': 'households', '세대수(세대)': 'units',
            '연면적(㎡)': 'total_area', '사용승인일': 'app_date', 
            '옥내자주식대수(대)': 'parking_in', '옥외자주식대수(대)': 'parking_out',
            '층번호': 'floor_no', '주용도코드명': 'purpose', '기타용도': 'etc', 
            '면적(㎡)': 'area', '호명칭': 'ho', '위반건축물여부': 'violation'
        }
        df.rename(columns=mapping, inplace=True)
        return df
    return None

# 📌 3. 메인 화면 구성
st.markdown('<p class="main-title">🏢 원탑 건축물대장 통합 마스터</p>', unsafe_allow_html=True)
st.caption("수원 전지역 다가구/빌라/아파트 통합 조회")

user_input = st.text_input("🔍 주소 입력", placeholder="예: 세류동 82-18 또는 매탄동 1202-2")

if user_input:
    df_m = load_mini_data("mini_master.csv.gz")
    if df_m is not None:
        # 주소 검색 (공백 및 특수기호 무시)
        search_parts = user_input.replace("-", " ").split()
        mask = df_m['address'].fillna('').str.contains(search_parts[0], na=False)
        for part in search_parts[1:]:
            mask &= df_m['address'].fillna('').str.contains(part, na=False)
        
        res = df_m[mask]

        if not res.empty:
            item = res.iloc[0]
            pk = item.get('pk')
            bld_type = str(item.get('bld_type', '일반'))
            
            # 위반 여부 체크
            v_val = str(item.get('violation', '0')).strip()
            if v_val in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.error("⚠️ 위반건축물 확인 필요 ⚠️")

            st.info(f"📍 **주소:** {item.get('address')} ({bld_type})")

            # 핵심 정보 카드
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("🏗️ 층수", f"지상 {item.get('floors', '0')}층")
            with c2: 
                # 가구수 + 세대수 합산
                h_cnt = int(float(item.get('households', 0))) + int(float(item.get('units', 0)))
                st.metric("🏠 가구수", f"{h_cnt}가구")
            with c3:
                p_cnt = int(float(item.get('parking_in', 0))) + int(float(item.get('parking_out', 0)))
                st.metric("🚗 주차", f"{p_cnt}대")

            # 상세 내역 (집합 vs 일반)
            if "집합" in bld_type:
                st.markdown('<div class="info-container"><b>🔑 호수별 전용면적</b>', unsafe_allow_html=True)
                df_u = load_mini_data("mini_unit.csv.gz")
                if df_u is not None:
                    units = df_u[df_u['pk'] == pk]
                    if not units.empty:
                        # 층수 정렬을 위해 숫자화
                        units['floor_int'] = pd.to_numeric(units['floor_no'], errors='coerce').fillna(0).astype(int)
                        for _, u in units.sort_values(['floor_int', 'ho']).iterrows():
                            st.markdown(f'<div class="data-row"><span>{u.get("floor_no")}층 {u.get("ho")}</span><span style="color:#007bff">{u.get("area")}㎡</span></div>', unsafe_allow_html=True)
                    else: st.write("호별 상세 정보가 없습니다.")
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="info-container"><b>🏢 층별 상세 현황</b>', unsafe_allow_html=True)
                df_f = load_mini_data("mini_floor.csv.gz")
                if df_f is not None:
                    floors = df_f[df_f['pk'] == pk]
                    if not floors.empty:
                        floors['floor_int'] = pd.to_numeric(floors['floor_no'], errors='coerce').fillna(0).astype(int)
                        for _, f in floors.sort_values('floor_int').iterrows():
                            etc = str(f.get('etc', ''))
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            badge = f' <span class="badge">{g.group(0)}</span>' if g else ""
                            st.markdown(f'<div class="data-row"><span>{f.get("floor_no")}층 {f.get("purpose")}</span>{badge}<span style="color:#007bff">{f.get("area")}㎡</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("해당 주소의 데이터를 찾을 수 없습니다. 번지를 정확히 입력했는지 확인해주세요.")
