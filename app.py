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
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 5px; letter-spacing: -0.5px; }
    
    div[data-testid="stTextInput"] input {
        font-size: 20px !important; font-weight: 600 !important; padding: 16px 15px !important; 
        color: #000000 !important; background-color: #ffffff !important; 
        border: 2px solid #007bff !important; border-radius: 12px;
    }

    .violation-box { 
        background-color: #dc3545; color: white; padding: 12px; border-radius: 10px; 
        text-align: center; font-weight: 800; margin-bottom: 15px; font-size: 18px;
        animation: blink 1.5s infinite;
    }
    @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.8;} 100% {opacity: 1;} }
    
    div[data-testid="stMetric"] { background-color: white; border: 1px solid #e0e6ed; padding: 15px 5px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); text-align: center; }
    label[data-testid="stMetricLabel"] { font-size: 14px !important; font-weight: 700 !important; color: #444444 !important; }
    div[data-testid="stMetricValue"] { font-size: 22px !important; font-weight: 800 !important; color: #007bff !important; }

    .info-container { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .data-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #e9ecef; font-size: 15px; }
    .label-col { font-weight: 800; color: #6f42c1; min-width: 70px; }
    .desc-col { color: #111111; text-align: right; font-weight: 600; flex-grow: 1; } 
    .value-col { color: #007bff; font-weight: 800; min-width: 90px; text-align: right; margin-left: 10px; }
    .badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; margin-left: 6px; }
    </style>
    """, unsafe_allow_html=True)

# 📌 2. 만능 이름표(칼럼) 매핑 함수
def standardize_columns(df):
    if df is None: return None
    # 한글 이름표 -> 코드 이름표로 강제 변환
    mapping = {
        '대지위치': 'platPlc', '관리건축물대장PK': 'mgmBldrgstPk', '관리건축물대장pk': 'mgmBldrgstPk',
        '대장구분코드명': 'regstrGbCdNm', '위반건축물여부': 'vlBldYn', '지상층수': 'grndFlrCnt',
        '승용승강기수': 'rideUseElvtCnt', '비상용승강기수': 'emgenUseElvtCnt', '사용승인일': 'useAprDay',
        '연면적': 'totArea', '가구수': 'fmlyCnt', '세대수': 'hhldCnt', '동명칭': 'dongNm', '호명칭': 'hoNm',
        '층번호': 'flrNo', '주용도코드명': 'mainPurpsCdNm', '면적': 'area', '기타용도': 'etcPurps',
        '구분코드': 'objGbCd'
    }
    df.rename(columns=mapping, inplace=True)
    return df

@st.cache_data
def load_data_safe(file_name):
    if os.path.exists(file_name):
        df = pd.read_csv(file_name, dtype=str)
        return standardize_columns(df)
    return None

# 📌 3. 메인 로직 시작
st.markdown('<p class="main-title">🏢 원탑 건축물대장 통합 마스터</p>', unsafe_allow_html=True)
st.caption("수원 전지역 데이터 기반 통합 조회")

user_input = st.text_input("🔍 주소 입력", placeholder="예: 매탄동 1202-2")

if user_input:
    df_m = load_data_safe("suwon_building_master.csv.gz")
    if df_m is not None:
        # 이제 platPlc라는 이름이 무조건 존재함
        df_m['clean_addr'] = df_m['platPlc'].str.replace(" ", "")
        search_term = user_input.replace(" ", "")
        res = df_m[df_m['clean_addr'].str.contains(search_term, na=False)]

        if not res.empty:
            item = res.iloc[0]
            pk = item.get('mgmBldrgstPk')
            bld_type = item.get('regstrGbCdNm', '일반')
            
            # 위반 체크 (강력해진 로직)
            v_val = str(item.get('vlBldYn', '0')).strip().upper()
            if v_val in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.markdown('<div class="violation-box">⚠️ 위반건축물 확인 필요 ⚠️</div>', unsafe_allow_html=True)

            st.info(f"📍 **조회 주소:** {item.get('platPlc', '주소 없음')} ({bld_type})")

            c1, c2, c3 = st.columns(3)
            with c1: st.metric("🏗️ 전체 층수", f"지상 {item.get('grndFlrCnt', '0')}층")
            with c2:
                p_sum = sum([int(float(item.get(c, 0))) for c in ['indrAutoUtcnt', 'indrMechUtcnt', 'oudrAutoUtcnt', 'oudrMechUtcnt'] if pd.notna(item.get(c))])
                st.metric("🚗 주차대수", f"{p_sum}대")
            with c3:
                ride_el = int(float(item.get('rideUseElvtCnt', 0))) if pd.notna(item.get('rideUseElvtCnt')) else 0
                emgen_el = int(float(item.get('emgenUseElvtCnt', 0))) if pd.notna(item.get('emgenUseElvtCnt')) else 0
                st.metric("🛗 승강기", f"{ride_el + emgen_el}대" if (ride_el + emgen_el) > 0 else "없음")

            # --- 다세대(집합) vs 다가구(일반) 분기 ---
            if "집합" in bld_type:
                st.markdown('<div class="info-container"><p style="font-size:17px; font-weight:800; margin-bottom:12px;">🔑 호수별 전용면적 (다세대/아파트)</p>', unsafe_allow_html=True)
                df_unit_status = load_data_safe("suwon_unit_status.csv.gz")
                df_unit_area = load_data_safe("suwon_unit_area.csv.gz")
                
                if df_unit_status is not None and df_unit_area is not None:
                    units = df_unit_status[df_unit_status['mgmBldrgstPk'] == pk].copy()
                    areas = df_unit_area[df_unit_area['mgmBldrgstPk'] == pk].copy()
                    
                    if not units.empty:
                        # 면적 데이터 중 '전용(1)'만 골라내기
                        areas = areas[areas['objGbCd'] == '1']
                        merged = pd.merge(units, areas, on=['mgmBldrgstPk', 'flrNo', 'hoNm'], how='left')
                        merged = merged.sort_values(by=['flrNo', 'hoNm'])

                        for _, u_row in merged.iterrows():
                            ho = f"{u_row.get('hoNm', '미정')}호"
                            flr = f"{u_row.get('flrNo', '?')}층"
                            try: val = f"{float(u_row.get('area', 0)):,.2f} ㎡"
                            except: val = "- ㎡"
                            st.markdown(f'<div class="data-row"><span class="label-col">{flr}</span><span class="desc-col">{ho}</span><span class="value-col">{val}</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                # 다가구 처리
                st.markdown('<div class="info-container"><p style="font-size:17px; font-weight:800; margin-bottom:12px;">🏢 층별 상세 현황 (다가구)</p>', unsafe_allow_html=True)
                df_floor = load_data_safe("suwon_floor_info.csv.gz")
                if df_floor is not None:
                    floors = df_floor[df_floor['mgmBldrgstPk'] == pk].copy()
                    floors['flr_int'] = pd.to_numeric(floors['flrNo'], errors='coerce').fillna(0).astype(int)
                    for _, f_row in floors.sort_values(by='flr_int').iterrows():
                        etc = str(f_row.get('etcPurps', ''))
                        g_match = re.search(r'(\d+)\s*(가구|호)', etc)
                        badge = f' <span class="badge">{g_match.group(1)}{g_match.group(2)}</span>' if g_match else ""
                        try: a_val = f"{float(f_row.get('area', 0)):,.1f} ㎡"
                        except: a_val = "0 ㎡"
                        st.markdown(f'<div class="data-row"><span class="label-col">{f_row.get("flrNo", "")}층</span><span class="desc-col">{f_row.get("mainPurpsCdNm", "")}{badge}</span><span class="value-col">{a_val}</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else: st.error("데이터를 찾을 수 없습니다.")
    else: st.error("데이터 파일이 없습니다. 깃허브 업로드를 확인해주세요.")
