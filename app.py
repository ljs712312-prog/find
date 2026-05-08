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
    .main-title { font-size: 24px; font-weight: 800; color: #000000; margin-bottom: 10px; }
    
    div[data-testid="stTextInput"] input {
        font-size: 18px !important; font-weight: 600 !important; padding: 12px 15px !important; 
        background-color: #ffffff !important; border: 2px solid #007bff !important; border-radius: 12px;
    }

    .info-container { background-color: #ffffff; padding: 15px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .data-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #e9ecef; font-size: 14px; }
    .label-col { font-weight: 800; color: #6f42c1; min-width: 60px; }
    .desc-col { color: #111111; text-align: right; font-weight: 600; flex-grow: 1; } 
    .value-col { color: #007bff; font-weight: 800; min-width: 80px; text-align: right; margin-left: 10px; }
    .badge { background-color: #ffc107; color: #212529; font-size: 11px; font-weight: 800; padding: 2px 5px; border-radius: 6px; margin-left: 5px; }
    </style>
    """, unsafe_allow_html=True)

# 📌 2. 이름표 강제 매핑 함수 (매우 강력함)
def robust_mapping(df):
    if df is None: return None
    # 칼럼명 청소 (공백 및 특수기호 제거)
    df.columns = [str(c).strip().replace('\ufeff', '') for c in df.columns]
    
    # 키워드 기반 자동 매핑 규칙
    target_rules = {
        'address': ['대지위치', '주소', 'platPlc'],
        'pk': ['관리건축물대장PK', '관리건축물대장pk', 'mgmBldrgstPk', 'pk'],
        'violation': ['위반건축물여부', 'vlBldYn', '위반'],
        'bld_type': ['대장구분코드명', 'regstrGbCdNm'],
        'floors': ['지상층수', 'grndFlrCnt'],
        'households': ['가구수(가구)', '가구수', 'fmlyCnt'],
        'units': ['세대수(세대)', '세대수', 'hhldCnt'],
        'floor_no': ['층번호', 'flrNo'],
        'purpose': ['주용도코드명', 'mainPurpsCdNm'],
        'area': ['면적(㎡)', '면적', 'area'],
        'ho': ['호명칭', 'hoNm'],
        'etc': ['기타용도', 'etcPurps']
    }
    
    new_cols = {}
    for final_name, candidates in target_rules.items():
        for col in df.columns:
            if any(cand in col for cand in candidates):
                new_cols[col] = final_name
                break
    
    df.rename(columns=new_cols, inplace=True)
    
    # 🚨 주소(address)를 못 찾으면 첫 번째 열을 주소로 강제 지정
    if 'address' not in df.columns and len(df.columns) > 0:
        df.rename(columns={df.columns[0]: 'address'}, inplace=True)
        
    return df

@st.cache_data
def load_mini_data(file_name):
    if os.path.exists(file_name):
        try:
            df = pd.read_csv(file_name, dtype=str)
            return robust_mapping(df)
        except:
            return None
    return None

# 📌 3. 메인 로직
st.markdown('<p class="main-title">🏢 원탑 건축물대장 통합 마스터</p>', unsafe_allow_html=True)
user_input = st.text_input("🔍 주소 입력", placeholder="예: 매탄동 1202-2")

if user_input:
    df_m = load_mini_data("mini_master.csv.gz")
    if df_m is not None and 'address' in df_m.columns:
        # 검색 로직 (공백 및 대시 무시)
        search_parts = user_input.replace("-", " ").split()
        mask = df_m['address'].fillna('').str.contains(search_parts[0], na=False)
        for part in search_parts[1:]:
            mask &= df_m['address'].fillna('').str.contains(part, na=False)
        
        res = df_m[mask]

        if not res.empty:
            item = res.iloc[0]
            pk = item.get('pk')
            bld_type = str(item.get('bld_type', '일반'))
            
            # 위반 체크
            if str(item.get('violation', '0')).strip() in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.error("⚠️ 위반건축물 확인 필요 ⚠️")

            st.info(f"📍 **주소:** {item.get('address')} ({bld_type})")

            # 핵심 정보
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("🏗️ 층수", f"지상 {item.get('floors', '0')}층")
            with c2: 
                h_cnt = int(float(item.get('households', 0))) + int(float(item.get('units', 0)))
                st.metric("🏠 가구수", f"{h_cnt}가구")
            with c3:
                # 주차 대수 (최적화된 이름표 사용)
                p_sum = 0
                for col in item.keys():
                    if '자주식' in col or '기계식' in col:
                        try: p_sum += int(float(item.get(col, 0)))
                        except: pass
                st.metric("🚗 주차", f"{p_sum}대")

            # 상세 정보
            if "집합" in bld_type:
                st.markdown('<div class="info-container"><b>🔑 호수별 전용면적</b>', unsafe_allow_html=True)
                df_u = load_mini_data("mini_unit.csv.gz")
                if df_u is not None:
                    units = df_u[df_u['pk'] == pk]
                    if not units.empty:
                        for _, u in units.sort_values(['floor_no', 'ho']).iterrows():
                            st.markdown(f'<div class="data-row"><span>{u.get("floor_no")}층 {u.get("ho", "")}</span><span class="value-col">{u.get("area", "-")}㎡</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="info-container"><b>🏢 층별 상세 현황</b>', unsafe_allow_html=True)
                df_f = load_mini_data("mini_floor.csv.gz")
                if df_f is not None:
                    floors = df_f[df_f['pk'] == pk]
                    if not floors.empty:
                        for _, f in floors.sort_values('floor_no').iterrows():
                            etc = str(f.get('etc', ''))
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            badge = f' <span class="badge">{g.group(0)}</span>' if g else ""
                            st.markdown(f'<div class="data-row"><span>{f.get("floor_no")}층 {f.get("purpose", "")}</span>{badge}<span class="value-col">{f.get("area", "-")}㎡</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("데이터를 찾을 수 없습니다.")
    else:
        st.error("기본 데이터 파일 로딩에 실패했습니다.")
