import streamlit as st
import pandas as pd
import os
import re  # 문자열에서 가구수를 찾기 위한 정규식 모듈 추가

# 📌 1. 페이지 설정
st.set_page_config(page_title="원탑 건축물대장 조회", page_icon="🏢", layout="centered")

# 📌 2. 디자인 CSS
st.markdown("""
    <style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"]  { color: #222222 !important; font-weight: 400 !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #111111; margin-bottom: 5px; letter-spacing: -0.5px; }
    
    div[data-testid="stTextInput"] input {
        font-size: 20px !important; font-weight: 600 !important; padding: 16px 15px !important; 
        color: #111111 !important; background-color: #ffffff !important; 
        border: 2px solid #007bff !important; border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,123,255,0.1); 
    }

    .violation-box { 
        background-color: #dc3545; color: white; padding: 12px; border-radius: 10px; 
        text-align: center; font-weight: 800; margin-bottom: 15px; font-size: 18px;
        animation: blink 1.5s infinite;
    }
    @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.8;} 100% {opacity: 1;} }
    
    div[data-testid="stMetric"] { background-color: white; border: 1px solid #e0e6ed; padding: 15px 10px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); text-align: center; }
    label[data-testid="stMetricLabel"] { font-size: 14px !important; font-weight: 600 !important; color: #555555 !important; }
    div[data-testid="stMetricValue"] { font-size: 22px !important; font-weight: 700 !important; color: #007bff !important; }
    
    .floor-info-box { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .floor-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #e9ecef; font-size: 15px; }
    .floor-label { font-weight: 800; color: #6f42c1; min-width: 65px; }
    .floor-use { color: #222222; text-align: right; font-weight: 600; flex-grow: 1; } 
    .floor-area { color: #007bff; font-weight: 800; min-width: 90px; text-align: right; margin-left: 10px; }
    
    /* 가구수 뱃지 디자인 */
    .gagu-badge { background-color: #ffc107; color: #212529; font-size: 13px; font-weight: 800; padding: 2px 6px; border-radius: 6px; margin-left: 6px; }
    </style>
    """, unsafe_allow_html=True)

# 📌 3. 데이터 로딩
@st.cache_data
def load_all_data():
    master_file = "suwon_building_master_v3.csv.gz"
    floor_file = "suwon_floor_info.csv.gz"
    
    if not os.path.exists(master_file) or not os.path.exists(floor_file):
        st.error("❌ 데이터 파일이 부족합니다. 표제부 파일과 층별개요 파일을 모두 올려주세요.")
        return None, None
        
    try:
        df_m = pd.read_csv(master_file, dtype=str)
        df_m['clean_addr'] = df_m['platPlc'].str.replace(" ", "")
        
        df_f = pd.read_csv(floor_file, dtype=str)
        
        # 🚨 '면적'과 '기타용도(가구수 파악용)' 칼럼 추가 매핑
        col_mapping = {
            '관리건축물대장pk': 'mgmBldrgstPk', '관리건축물대장PK': 'mgmBldrgstPk',
            '층번호': 'flrNo', '층구분코드명': 'flrGbCdNm', '층구분명': 'flrGbCdNm',
            '주용도코드명': 'mainPurpsCdNm', '주용도명': 'mainPurpsCdNm',
            '면적': 'area', '기타용도': 'etcPurps'
        }
        df_f.rename(columns=col_mapping, inplace=True)
        
        if 'flrNo' not in df_f.columns:
            st.error(f"❌ 층별 데이터에 층번호 칼럼이 없습니다.")
            return df_m, None

        df_f['flrNo_int'] = pd.to_numeric(df_f['flrNo'], errors='coerce').fillna(0).astype(int)
        
        return df_m, df_f
    except Exception as e:
        st.error(f"데이터 로딩 오류: {e}")
        return None, None

df_master, df_floor = load_all_data()

# 📌 4. 메인 화면
st.markdown('<p class="main-title">🏢 원탑 건축물대장 조회</p>', unsafe_allow_html=True)
st.caption("수원 건축물대장 [표제부 + 층별개요] 통합 시스템")

user_input = st.text_input("🔍 주소 입력", placeholder="예: 인계동 1030-11")

if user_input and df_master is not None:
    search_term = user_input.replace(" ", "")
    res = df_master[df_master['clean_addr'].str.contains(search_term, na=False)]

    if not res.empty:
        item = res.iloc[0]
        pk = item['mgmBldrgstPk'] 
        
        # 위반건축물 체크
        is_violation = False
        v_val = item.get('vlBldYn', item.get('위반건축물여부', '0'))
        
        if pd.notna(v_val):
            v_str = str(v_val).strip().upper()
            if v_str in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                is_violation = True
                
        if is_violation:
            st.markdown('<div class="violation-box">⚠️ 위반건축물 확인 필요 ⚠️</div>', unsafe_allow_html=True)

        st.info(f"📍 **조회 주소:** {item['platPlc']}")

        c1, c2, c3 = st.columns(3)
        with c1: st.metric("🏗️ 전체 층수", f"지상 {item.get('grndFlrCnt', '0')}층")
        with c2:
            p_sum = sum([int(float(item.get(c, 0))) for c in ['indrAutoUtcnt', 'indrMechUtcnt', 'oudrAutoUtcnt', 'oudrMechUtcnt'] if pd.notna(item.get(c))])
            st.metric("🚗 주차대수", f"{p_sum}대")
        with c3:
            ride_el = int(float(item.get('rideUseElvtCnt', 0))) if pd.notna(item.get('rideUseElvtCnt')) else 0
            emgen_el = int(float(item.get('emgenUseElvtCnt', 0))) if pd.notna(item.get('emgenUseElvtCnt')) else 0
            total_el = ride_el + emgen_el
            st.metric("🛗 승강기", f"있음 ({total_el}대)" if total_el > 0 else "없음")

        c4, c5 = st.columns(2)
        with c4:
            u_day = str(item.get('useAprDay', '정보 없음'))
            if len(u_day) >= 8: u_day = f"{u_day[:4]}-{u_day[4:6]}-{u_day[6:8]}"
            st.metric("📅 사용승인일", u_day)
        with c5:
            hhld = int(float(item.get('hhldCnt', 0))) if pd.notna(item.get('hhldCnt')) else 0
            fmly = int(float(item.get('fmlyCnt', 0))) if pd.notna(item.get('fmlyCnt')) else 0
            st.metric("🏠 총 세대(가구)수", f"{hhld + fmly}세대")

        # 📌 층별 상세 용도 & 면적 & 수기 가구수
        st.markdown('<div class="floor-info-box"><p style="font-size:18px; font-weight:800; margin-bottom:15px; color:#111111;">🏢 층별 상세 현황 (용도 / 면적)</p>', unsafe_allow_html=True)
        
        if df_floor is not None:
            floors = df_floor[df_floor['mgmBldrgstPk'] == pk].sort_values(by='flrNo_int')
            
            if not floors.empty:
                display_list = []
                temp_floors = []
                prev_key = None
                prev_purp = ""
                prev_area = ""
                
                for _, f_row in floors.iterrows():
                    f_purp = f_row.get('mainPurpsCdNm', '정보 없음')
                    f_etc_purp = str(f_row.get('etcPurps', ''))
                    
                    # 🚨 [핵심 기능] 기타용도에서 '숫자+가구' 또는 '숫자+호' 추출
                    gagu_match = re.search(r'(\d+)\s*(가구|호)', f_etc_purp)
                    if gagu_match:
                        # 추출된 가구수를 노란색 뱃지로 예쁘게 표시
                        extracted = f"{gagu_match.group(1)}{gagu_match.group(2)}"
                        f_purp += f' <span class="gagu-badge">{extracted}</span>'

                    f_area_raw = f_row.get('area', '0')
                    
                    try:
                        f_area = f"{float(f_area_raw):,.1f}"
                    except:
                        f_area = str(f_area_raw)
                        
                    curr_key = f"{f_purp}_{f_area}"
                    
                    if curr_key == prev_key:
                        temp_floors.append(f_row.get('flrNo', ''))
                    else:
                        if prev_key is not None:
                            if len(temp_floors) > 1:
                                display_list.append((f"{temp_floors[0]}~{temp_floors[-1]}층", prev_purp, f"각 {prev_area} ㎡"))
                            else:
                                display_list.append((f"{temp_floors[0]}층", prev_purp, f"{prev_area} ㎡"))
                        temp_floors = [f_row.get('flrNo', '')]
                        prev_key = curr_key
                        prev_purp = f_purp
                        prev_area = f_area
                
                if prev_key is not None:
                    if len(temp_floors) > 1:
                        display_list.append((f"{temp_floors[0]}~{temp_floors[-1]}층", prev_purp, f"각 {prev_area} ㎡"))
                    else:
                        display_list.append((f"{temp_floors[0]}층", prev_purp, f"{prev_area} ㎡"))

                # 결과 출력
                for flr, purp, area in display_list:
                    st.markdown(f"""
                        <div class="floor-row">
                            <span class="floor-label">{flr}</span>
                            <span class="floor-use">{purp}</span>
                            <span class="floor-area">{area}</span>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.write("해당 건물의 층별 상세 데이터가 없습니다.")
        else:
            st.error("층별 데이터를 불러오지 못했습니다.")
        
        st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.error("데이터를 찾을 수 없습니다.")

st.markdown("---")
st.caption("© 원탑 건축물대장 조회")
