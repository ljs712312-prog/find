import streamlit as st
import pandas as pd
import os

# 📌 1. 페이지 설정
st.set_page_config(page_title="원탑 건축물대장 조회", page_icon="🏢", layout="centered")

# 📌 2. 디자인 CSS (폰트 진하게, 검색창 크게 개선)
st.markdown("""
    <style>
    /* 전체 배경 및 기본 폰트 색상/굵기 진하게 설정 */
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"]  {
        color: #111111 !important; /* 텍스트를 아주 진한 검정색으로 */
        font-weight: 500 !important; /* 기본 굵기를 한 단계 올려서 또렷하게 */
    }

    /* 제목 스타일 */
    .main-title { font-size: 28px; font-weight: 900; color: #000000; margin-bottom: 5px; letter-spacing: -0.5px; }
    
    /* 🚨 [핵심] 검색창 크기 및 폰트 대폭 확대 */
    div[data-testid="stTextInput"] input {
        font-size: 22px !important; /* 검색어 글자 크기 대폭 키움 */
        font-weight: 800 !important; /* 검색어 아주 굵게 */
        padding: 18px 15px !important; /* 위아래 여백을 늘려 입력창 자체를 뚱뚱하게 만듦 */
        color: #000000 !important;
        border: 2px solid #007bff !important; /* 파란색 테두리로 눈에 띄게 */
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,123,255,0.1); /* 약간의 그림자 효과 */
    }

    /* 위반건축물 경고창 */
    .violation-box { background-color: #ff4b4b; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: bold; margin-bottom: 10px; font-size: 18px;}
    
    /* 4대 핵심 정보 카드 디자인 */
    div[data-testid="stMetric"] { background-color: white; border: 1px solid #e0e6ed; padding: 15px 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    label[data-testid="stMetricLabel"] { font-size: 16px !important; font-weight: 700 !important; color: #333333 !important; }
    div[data-testid="stMetricValue"] { font-size: 26px !important; font-weight: 900 !important; color: #007bff !important; }
    
    /* 층별 상세 현황 리스트 디자인 */
    .floor-info-box { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .floor-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #e9ecef; font-size: 16px; }
    .floor-label { font-weight: 800; color: #6f42c1; min-width: 85px; }
    .floor-use { color: #000000; text-align: right; font-weight: 600; } /* 용도 글씨도 아주 진하게 */
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
        # 마스터 데이터 (표제부)
        df_m = pd.read_csv(master_file, dtype=str)
        df_m['clean_addr'] = df_m['platPlc'].str.replace(" ", "")
        
        # 층별 데이터 (상세 용도)
        df_f = pd.read_csv(floor_file, dtype=str)
        
        # 한글/영문 칼럼명 자동 호환 로직
        col_mapping = {
            '관리건축물대장pk': 'mgmBldrgstPk', '관리건축물대장PK': 'mgmBldrgstPk',
            '층번호': 'flrNo', '층구분코드명': 'flrGbCdNm', '층구분명': 'flrGbCdNm',
            '주용도코드명': 'mainPurpsCdNm', '주용도명': 'mainPurpsCdNm'
        }
        df_f.rename(columns=col_mapping, inplace=True)
        
        if 'flrNo' not in df_f.columns:
            st.error(f"❌ 층별 데이터에 층번호 칼럼이 없습니다. 현재 파일의 칼럼 목록: {list(df_f.columns)}")
            return df_m, None

        # 층수 정렬을 위해 숫자화
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
        
        # ⚠️ 위반건축물 체크
        if item.get('vlBldYn') in ['1', 'Y', '위반']:
            st.markdown('<div class="violation-box">⚠️ 위반건축물 확인 필요</div>', unsafe_allow_html=True)

        st.info(f"📍 **조회 주소:** {item['platPlc']}")

        # 상단 4대 핵심 정보
        c1, c2 = st.columns(2)
        with c1: st.metric("🏗️ 전체 층수", f"지상 {item.get('grndFlrCnt', '0')}층")
        with c2:
            p_sum = sum([int(float(item.get(c, 0))) for c in ['indrAutoUtcnt', 'indrMechUtcnt', 'oudrAutoUtcnt', 'oudrMechUtcnt'] if pd.notna(item.get(c))])
            st.metric("🚗 총 주차대수", f"{p_sum}대")

        c3, c4 = st.columns(2)
        with c3:
            u_day = str(item.get('useAprDay', '정보 없음'))
            if len(u_day) >= 8: u_day = f"{u_day[:4]}-{u_day[4:6]}-{u_day[6:8]}"
            st.metric("📅 사용승인일", u_day)
        with c4:
            hhld = int(float(item.get('hhldCnt', 0))) if pd.notna(item.get('hhldCnt')) else 0
            fmly = int(float(item.get('fmlyCnt', 0))) if pd.notna(item.get('fmlyCnt')) else 0
            st.metric("🏠 총 세대(가구)수", f"{hhld + fmly}세대")

        # 📌 층별 상세 용도 리스트업
        st.markdown('<div class="floor-info-box"><p style="font-size:18px; font-weight:900; margin-bottom:15px; color:#000000;">🏢 층별 상세 현황</p>', unsafe_allow_html=True)
        
        if df_floor is not None:
            floors = df_floor[df_floor['mgmBldrgstPk'] == pk].sort_values(by='flrNo_int')
            
            if not floors.empty:
                display_list = []
                temp_floors = []
                prev_purp = ""
                
                for _, f_row in floors.iterrows():
                    f_name = f"{f_row.get('flrGbCdNm', '')} {f_row.get('flrNo', '')}층".replace('지상 ', '').strip()
                    f_purp = f_row.get('mainPurpsCdNm', '정보 없음')
                    
                    if f_purp == prev_purp:
                        temp_floors.append(f_row.get('flrNo', ''))
                    else:
                        if prev_purp:
                            if len(temp_floors) > 1:
                                display_list.append((f"{temp_floors[0]}~{temp_floors[-1]}층", f"{prev_purp} (동일)"))
                            else:
                                display_list.append((f"{temp_floors[0]}층", prev_purp))
                        temp_floors = [f_row.get('flrNo', '')]
                        prev_purp = f_purp
                
                if prev_purp:
                    if len(temp_floors) > 1:
                        display_list.append((f"{temp_floors[0]}~{temp_floors[-1]}층", f"{prev_purp} (동일)"))
                    else:
                        display_list.append((f"{temp_floors[0]}층", prev_purp))

                for flr, purp in display_list:
                    st.markdown(f"""
                        <div class="floor-row">
                            <span class="floor-label">{flr}</span>
                            <span class="floor-use">{purp}</span>
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
