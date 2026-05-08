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
    
    /* 검색창 최적화 */
    div[data-testid="stTextInput"] input {
        font-size: 20px !important; font-weight: 600 !important; padding: 16px 15px !important; 
        color: #000000 !important; background-color: #ffffff !important; 
        border: 2px solid #007bff !important; border-radius: 12px;
    }

    /* 위반건축물 경고 */
    .violation-box { 
        background-color: #dc3545; color: white; padding: 12px; border-radius: 10px; 
        text-align: center; font-weight: 800; margin-bottom: 15px; font-size: 18px;
        animation: blink 1.5s infinite;
    }
    @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.8;} 100% {opacity: 1;} }
    
    /* 카드 및 리스트 디자인 */
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

# 📌 2. 데이터 로딩 함수
@st.cache_data
def load_data(file_name):
    if os.path.exists(file_name):
        return pd.read_csv(file_name, dtype=str)
    return None

# 📌 3. 메인 로직
st.markdown('<p class="main-title">🏢 원탑 건축물대장 통합 마스터</p>', unsafe_allow_html=True)
st.caption("수원 전지역 [표제부/층별/전유부] 통합 조회 시스템")

user_input = st.text_input("🔍 주소 입력", placeholder="예: 세류동 82-18 또는 인계동 1030-11")

if user_input:
    # 1. 표제부 데이터 로드 및 검색
    df_m = load_data("suwon_building_master.csv.gz")
    if df_m is not None:
        df_m['clean_addr'] = df_m['platPlc'].str.replace(" ", "")
        search_term = user_input.replace(" ", "")
        res = df_m[df_m['clean_addr'].str.contains(search_term, na=False)]

        if not res.empty:
            item = res.iloc[0]
            pk = item.get('mgmBldrgstPk')
            bld_type = item.get('regstrGbCdNm', '일반') # 집합 vs 일반
            
            # 위반 체크
            v_val = str(item.get('vlBldYn', item.get('위반건축물여부', '0'))).strip().upper()
            if v_val in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.markdown('<div class="violation-box">⚠️ 위반건축물 확인 필요 ⚠️</div>', unsafe_allow_html=True)

            st.info(f"📍 **조회 주소:** {item['platPlc']} ({bld_type}건축물)")

            # 상단 핵심 정보
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("🏗️ 전체 층수", f"지상 {item.get('grndFlrCnt', '0')}층")
            with c2:
                p_sum = sum([int(float(item.get(c, 0))) for c in ['indrAutoUtcnt', 'indrMechUtcnt', 'oudrAutoUtcnt', 'oudrMechUtcnt'] if pd.notna(item.get(c))])
                st.metric("🚗 주차대수", f"{p_sum}대")
            with c3:
                el_cnt = int(float(item.get('rideUseElvtCnt', 0))) + int(float(item.get('emgenUseElvtCnt', 0)))
                st.metric("🛗 승강기", f"{el_cnt}대" if el_cnt > 0 else "없음")

            # --- 분기 처리: 집합(다세대/아파트) vs 일반(다가구) ---
            
            if "집합" in bld_type:
                st.markdown('<div class="info-container"><p style="font-size:17px; font-weight:800; margin-bottom:12px;">🔑 호수별 전용면적 현황 (다세대/아파트)</p>', unsafe_allow_html=True)
                # 전유부/전유공용 데이터 로드
                df_unit_status = load_data("suwon_unit_status.csv.gz")
                df_unit_area = load_data("suwon_unit_area.csv.gz")
                
                if df_unit_status is not None and df_unit_area is not None:
                    # PK로 해당 건물의 호수들 추출
                    units = df_unit_status[df_unit_status['mgmBldrgstPk'] == pk].copy()
                    areas = df_unit_area[df_unit_area['mgmBldrgstPk'] == pk].copy()
                    
                    # 호수와 면적 합치기 (동, 층, 호 기준)
                    if not units.empty:
                        # 전용면적(objGbCd == '1')만 필터링
                        areas = areas[areas['objGbCd'] == '1']
                        merged_units = pd.merge(units, areas, on=['mgmBldrgstPk', 'dongNm', 'hoNm', 'flrNo'], how='left')
                        merged_units = merged_units.sort_values(by=['flrNo', 'hoNm'])

                        for _, u_row in merged_units.iterrows():
                            ho_name = f"{u_row.get('hoNm', '미정')}호"
                            flr_name = f"{u_row.get('flrNo', '?')}층"
                            try: area_val = f"{float(u_row.get('area', 0)):,.2f} ㎡"
                            except: area_val = "- ㎡"
                            
                            st.markdown(f"""
                                <div class="data-row">
                                    <span class="label-col">{flr_name}</span>
                                    <span class="desc-col">{ho_name}</span>
                                    <span class="value-col">{area_val}</span>
                                </div>
                            """, unsafe_allow_html=True)
                    else: st.write("호별 상세 정보가 없습니다.")
                st.markdown('</div>', unsafe_allow_html=True)

            else:
                # 일반/다가구: 층별 현황 표시
                st.markdown('<div class="info-container"><p style="font-size:17px; font-weight:800; margin-bottom:12px;">🏢 층별 상세 현황 (다가구/단독)</p>', unsafe_allow_html=True)
                df_floor = load_data("suwon_floor_info.csv.gz")
                if df_floor is not None:
                    floors = df_floor[df_floor['mgmBldrgstPk'] == pk].copy()
                    floors['flrNo_int'] = pd.to_numeric(floors['flrNo'], errors='coerce').fillna(0).astype(int)
                    floors = floors.sort_values(by='flrNo_int')
                    
                    for _, f_row in floors.iterrows():
                        f_purp = str(f_row.get('mainPurpsCdNm', '정보 없음'))
                        etc_p = str(f_row.get('etcPurps', ''))
                        g_match = re.search(r'(\d+)\s*(가구|호)', etc_p)
                        badge = f' <span class="badge">{g_match.group(1)}{g_match.group(2)}</span>' if g_match else ""
                        
                        try: area_val = f"{float(f_row.get('area', 0)):,.1f} ㎡"
                        except: area_val = "0 ㎡"
                        
                        st.markdown(f"""
                            <div class="data-row">
                                <span class="label-col">{f_row.get('flrNo', '')}층</span>
                                <span class="desc-col">{f_purp}{badge}</span>
                                <span class="value-col">{area_val}</span>
                            </div>
                        """, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

        else: st.error("데이터를 찾을 수 없습니다. 주소를 다시 확인해주세요.")
    else: st.error("기본 데이터 파일(master)을 찾을 수 없습니다.")

st.markdown("---")
st.caption("© 원탑 건축물대장 통합 마스터 v5.0")
