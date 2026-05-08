import streamlit as st
import pandas as pd
import os
import re

# 📌 1. 페이지 설정 및 디자인 (가독성 & 모바일 최적화)
st.set_page_config(page_title="원탑 건축물대장 통합 마스터", page_icon="🏢", layout="centered")

st.markdown("""
    <style>
    /* 배경 및 기본 폰트 설정 (중간 굵기) */
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { color: #111111 !important; font-weight: 500 !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 5px; letter-spacing: -0.5px; }
    
    /* 🚨 검색창 디자인: 모바일 다크모드에서도 흰색 배경 유지 */
    div[data-testid="stTextInput"] input {
        font-size: 20px !important; font-weight: 600 !important; padding: 16px 15px !important; 
        color: #000000 !important; background-color: #ffffff !important; 
        border: 2px solid #007bff !important; border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,123,255,0.1);
    }

    /* 위반건축물 깜빡임 경고 */
    .violation-box { 
        background-color: #dc3545; color: white; padding: 12px; border-radius: 10px; 
        text-align: center; font-weight: 800; margin-bottom: 15px; font-size: 18px;
        animation: blink 1.5s infinite;
    }
    @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.8;} 100% {opacity: 1;} }
    
    /* 핵심 수치 카드 (메트릭) */
    div[data-testid="stMetric"] { background-color: white; border: 1px solid #e0e6ed; padding: 15px 5px; border-radius: 15px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    label[data-testid="stMetricLabel"] { font-size: 14px !important; font-weight: 700 !important; color: #555555 !important; }
    div[data-testid="stMetricValue"] { font-size: 22px !important; font-weight: 800 !important; color: #007bff !important; }

    /* 리스트 컨테이너 */
    .info-container { background-color: #ffffff; padding: 18px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .data-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #f1f3f5; font-size: 15px; }
    .label-col { font-weight: 800; color: #6f42c1; min-width: 65px; }
    .desc-col { color: #111111; text-align: right; font-weight: 600; flex-grow: 1; } 
    .value-col { color: #007bff; font-weight: 800; min-width: 85px; text-align: right; margin-left: 10px; }
    .gagu-badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; margin-left: 6px; }
    </style>
    """, unsafe_allow_html=True)

# 📌 2. 만능 데이터 로더 (이름표 자동 정리)
def robust_load(file_name):
    if not os.path.exists(file_name):
        return None
    try:
        # 유령 문자(BOM) 제거를 위해 utf-8-sig 혹은 기본 로드 후 처리
        df = pd.read_csv(file_name, dtype=str)
        # 칼럼명 앞뒤 공백 및 보이지 않는 특수문자 제거
        df.columns = [str(c).strip().replace('\ufeff', '') for c in df.columns]
        
        # 🚨 한글 이름표를 코드 내부 이름으로 강제 매핑 (데이터 다이어트 칼럼 기준)
        mapping = {
            '대지위치': 'addr', '관리건축물대장PK': 'pk', '대장구분코드명': 'bld_type',
            '위반건축물여부': 'is_violation', '지상층수': 'floors', 
            '가구수(가구)': 'gagu', '세대수(세대)': 'sadae', '연면적(㎡)': 'tot_area',
            '옥내자주식대수(대)': 'p_in', '옥외자주식대수(대)': 'p_out',
            '층번호': 'flr_no', '주용도코드명': 'purpose', '기타용도': 'etc', '면적(㎡)': 'area',
            '호명칭': 'ho', '동명칭': 'dong'
        }
        df.rename(columns=mapping, inplace=True)
        return df
    except:
        return None

# 📌 3. 메인 로직 시작
st.markdown('<p class="main-title">🏢 원탑 건축물대장 통합 마스터</p>', unsafe_allow_html=True)
st.caption("수원 전지역 [다가구/빌라/아파트] 핵심 정보 조회")

user_input = st.text_input("🔍 주소 입력", placeholder="예: 매탄동 1202-2")

if user_input:
    df_m = robust_load("mini_master.csv.gz")
    
    if df_m is not None:
        # 🔍 검색 로직: 공백/하이픈 제거 후 지능적 부분 일치 검색
        clean_input = user_input.replace(" ", "").replace("-", "")
        df_m['search_target'] = df_m['addr'].str.replace(" ", "").str.replace("-", "")
        
        res = df_m[df_m['search_target'].str.contains(clean_input, na=False)]

        if not res.empty:
            item = res.iloc[0]
            pk = item.get('pk')
            b_type = str(item.get('bld_type', '일반'))
            
            # 🚨 위반 체크 (mini_master에 칼럼이 있을 경우)
            v_val = str(item.get('is_violation', '0')).strip()
            if v_val in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.markdown('<div class="violation-box">⚠️ 위반건축물 확인 필요 ⚠️</div>', unsafe_allow_html=True)

            st.info(f"📍 **조회:** {item.get('addr')} ({b_type})")

            # 상단 핵심 메트릭
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("🏗️ 층수", f"지상 {item.get('floors', '0')}층")
            with c2: 
                # 가구수/세대수 합산
                total_h = int(float(item.get('gagu', 0))) + int(float(item.get('sadae', 0)))
                st.metric("🏠 총 가구수", f"{total_h}가구")
            with c3:
                # 주차 합산
                total_p = int(float(item.get('p_in', 0))) + int(float(item.get('p_out', 0)))
                st.metric("🚗 주차", f"{total_p}대")

            # --- 결과 상세 (집합 vs 일반) ---
            if "집합" in b_type:
                st.markdown('<div class="info-container"><p style="font-size:17px; font-weight:800; margin-bottom:10px;">🔑 호수별 전용면적 (집합)</p>', unsafe_allow_html=True)
                df_u = robust_load("mini_unit.csv.gz")
                if df_u is not None:
                    units = df_u[df_u['pk'] == pk]
                    if not units.empty:
                        # 층수 정렬 처리
                        units['flr_int'] = pd.to_numeric(units['flr_no'], errors='coerce').fillna(0).astype(int)
                        for _, u in units.sort_values(['flr_int', 'ho']).iterrows():
                            st.markdown(f"""
                                <div class="data-row">
                                    <span class="label-col">{u.get('flr_no')}층</span>
                                    <span class="desc-col">{u.get('ho', '호실')}</span>
                                    <span class="value-col">{u.get('area', '0')} ㎡</span>
                                </div>
                            """, unsafe_allow_html=True)
                    else: st.write("호별 상세 데이터가 없습니다.")
                st.markdown('</div>', unsafe_allow_html=True)
            
            else:
                st.markdown('<div class="info-container"><p style="font-size:17px; font-weight:800; margin-bottom:10px;">🏢 층별 상세 현황 (일반/다가구)</p>', unsafe_allow_html=True)
                df_f = robust_load("mini_floor.csv.gz")
                if df_f is not None:
                    floors = df_f[df_f['pk'] == pk]
                    if not floors.empty:
                        floors['flr_int'] = pd.to_numeric(floors['flr_no'], errors='coerce').fillna(0).astype(int)
                        for _, f in floors.sort_values('flr_int').iterrows():
                            etc = str(f.get('etc', ''))
                            # 수기 가구수 추출
                            g_match = re.search(r'(\d+)\s*(가구|호)', etc)
                            badge = f' <span class="gagu-badge">{g_match.group(0)}</span>' if g_match else ""
                            
                            st.markdown(f"""
                                <div class="data-row">
                                    <span class="label-col">{f.get('flr_no')}층</span>
                                    <span class="desc-col">{f.get('purpose', '')}{badge}</span>
                                    <span class="value-col">{f.get('area', '0')} ㎡</span>
                                </div>
                            """, unsafe_allow_html=True)
                    else: st.write("층별 상세 정보가 없습니다.")
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error(f"주소 '{user_input}'와(과) 일치하는 데이터를 찾지 못했습니다.")
            st.warning("번지만 입력하거나 동 이름을 확인해 보세요. (예: 1202-2)")
    else:
        st.error("데이터 파일(`mini_master.csv.gz`)을 읽을 수 없습니다.")

st.markdown("---")
st.caption("© 원탑 건축물대장 통합 마스터 v6.0")
