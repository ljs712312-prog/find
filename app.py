import streamlit as st
import pandas as pd
import os
import re

# 📌 1. 페이지 설정
st.set_page_config(page_title="원탑 건축물대장 조회", page_icon="🏢", layout="centered")

# 📌 2. 디자인 CSS (가독성 및 모바일 최적화)
st.markdown("""
    <style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"]  { color: #222222 !important; font-weight: 400 !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #111111; margin-bottom: 5px; letter-spacing: -0.5px; }
    
    /* 검색창 배경 흰색 고정 및 굵기 조절 */
    div[data-testid="stTextInput"] input {
        font-size: 20px !important; font-weight: 600 !important; padding: 16px 15px !important; 
        color: #111111 !important; background-color: #ffffff !important; 
        border: 2px solid #007bff !important; border-radius: 12px;
    }

    /* 위반건축물 경고창 */
    .violation-box { 
        background-color: #dc3545; color: white; padding: 12px; border-radius: 10px; 
        text-align: center; font-weight: 800; margin-bottom: 15px; font-size: 18px;
        animation: blink 1.5s infinite;
    }
    @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.8;} 100% {opacity: 1;} }
    
    /* 핵심 메트릭 카드 디자인 */
    div[data-testid="stMetric"] { background-color: white; border: 1px solid #e0e6ed; padding: 15px 5px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); text-align: center; }
    label[data-testid="stMetricLabel"] { font-size: 14px !important; font-weight: 700 !important; color: #444444 !important; }
    div[data-testid="stMetricValue"] { font-size: 22px !important; font-weight: 800 !important; color: #007bff !important; }

    /* 평균 면적 강조 박스 */
    .avg-area-box { background-color: #e7f3ff; padding: 10px; border-radius: 10px; border: 1px dashed #007bff; text-align: center; margin-bottom: 20px; color: #0056b3; font-weight: 700; font-size: 15px; }
    
    .floor-info-box { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .floor-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #e9ecef; font-size: 15px; }
    .floor-label { font-weight: 800; color: #6f42c1; min-width: 65px; }
    .floor-use { color: #222222; text-align: right; font-weight: 600; flex-grow: 1; } 
    .floor-area { color: #007bff; font-weight: 800; min-width: 90px; text-align: right; margin-left: 10px; }
    .gagu-badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; margin-left: 6px; }
    </style>
    """, unsafe_allow_html=True)

# 📌 3. 데이터 로딩 (칼럼 매핑 보강)
@st.cache_data
def load_all_data():
    master_file = "suwon_building_master_v3.csv.gz"
    floor_file = "suwon_floor_info.csv.gz"
    if not os.path.exists(master_file) or not os.path.exists(floor_file):
        st.error("❌ 데이터 파일이 부족합니다. 표제부(master)와 층별개요(floor) 파일을 모두 확인해주세요.")
        return None, None
    try:
        df_m = pd.read_csv(master_file, dtype=str)
        df_m['clean_addr'] = df_m['platPlc'].str.replace(" ", "")
        # 표제부 한글 칼럼 매핑
        m_cols = {'연면적': 'totArea', '가구수': 'fmlyCnt', '세대수': 'hhldCnt', '위반건축물여부': 'vlBldYn'}
        df_m.rename(columns=m_cols, inplace=True)

        df_f = pd.read_csv(floor_file, dtype=str)
        f_cols = {'층번호': 'flrNo', '주용도코드명': 'mainPurpsCdNm', '면적': 'area', '기타용도': 'etcPurps'}
        df_f.rename(columns=f_cols, inplace=True)
        df_f['flrNo_int'] = pd.to_numeric(df_f['flrNo'], errors='coerce').fillna(0).astype(int)
        
        return df_m, df_f
    except Exception as e:
        st.error(f"로딩 오류: {e}")
        return None, None

df_master, df_floor = load_all_data()

# 📌 4. 메인 화면
st.markdown('<p class="main-title">🏢 원탑 건축물대장 조회</p>', unsafe_allow_html=True)
user_input = st.text_input("🔍 주소 입력", placeholder="예: 인계동 1030-11")

if user_input and df_master is not None:
    search_term = user_input.replace(" ", "")
    res = df_master[df_master['clean_addr'].str.contains(search_term, na=False)]

    if not res.empty:
        item = res.iloc[0]
        pk = item.get('mgmBldrgstPk')
        
        # 1. 위반건축물 체크 (새 데이터 대비 로직 보강)
        v_val = str(item.get('vlBldYn', item.get('위반건축물여부', '0'))).strip().upper()
        if v_val in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
            st.markdown('<div class="violation-box">⚠️ 위반건축물 확인 필요 ⚠️</div>', unsafe_allow_html=True)

        st.info(f"📍 **조회 주소:** {item['platPlc']}")

        # 🚀 [준석 님 요청] 핵심 정보: 총 연면적 / 총 가구수 중심 배치
        tot_area = float(item.get('totArea', 0)) if pd.notna(item.get('totArea')) else 0
        fmly_cnt = int(float(item.get('fmlyCnt', 0))) if pd.notna(item.get('fmlyCnt')) else 0
        hhld_cnt = int(float(item.get('hhldCnt', 0))) if pd.notna(item.get('hhldCnt')) else 0
        total_units = fmly_cnt + hhld_cnt

        c1, c2, c3 = st.columns(3)
        with c1: st.metric("📏 총 연면적", f"{tot_area:,.1f} ㎡")
        with c2: st.metric("🏠 총 가구수", f"{total_units} 가구")
        with c3:
            # 승강기 대수 합산
            el_cnt = int(float(item.get('rideUseElvtCnt', 0))) + int(float(item.get('emgenUseElvtCnt', 0)))
            st.metric("🛗 승강기", f"{el_cnt}대" if el_cnt > 0 else "없음")

        # 💡 [자동 유추] 가구당 평균 면적 계산
        if total_units > 0:
            avg_area = tot_area / total_units
            avg_pyung = avg_area * 0.3025
            st.markdown(f"""
                <div class="avg-area-box">
                    💡 가구당 평균 연면적: 약 {avg_area:.1f} ㎡ (약 {avg_pyung:.1f}평)
                    <br><span style="font-size:12px; font-weight:400;">※ 복도, 계단 포함 수치로 실면적은 이보다 작습니다.</span>
                </div>
            """, unsafe_allow_html=True)

        # 사용승인일 및 주차
        c4, c5 = st.columns(2)
        with c4:
            u_day = str(item.get('useAprDay', '정보 없음'))
            if len(u_day) >= 8: u_day = f"{u_day[:4]}-{u_day[4:6]}-{u_day[6:8]}"
            st.metric("📅 사용승인일", u_day)
        with c5:
            p_sum = sum([int(float(item.get(c, 0))) for c in ['indrAutoUtcnt', 'indrMechUtcnt', 'oudrAutoUtcnt', 'oudrMechUtcnt'] if pd.notna(item.get(c))])
            st.metric("🚗 주차대수", f"{p_sum}대")

        # 층별 상세 현황
        st.markdown('<div class="floor-info-box"><p style="font-size:17px; font-weight:800; margin-bottom:12px;">🏢 층별 상세 현황</p>', unsafe_allow_html=True)
        if df_floor is not None:
            floors = df_floor[df_floor['mgmBldrgstPk'] == pk].sort_values(by='flrNo_int')
            if not floors.empty:
                for _, f_row in floors.iterrows():
                    f_purp = str(f_row.get('mainPurpsCdNm', '정보 없음'))
                    etc_p = str(f_row.get('etcPurps', ''))
                    # 수기 가구수 추출
                    g_match = re.search(r'(\d+)\s*(가구|호)', etc_p)
                    badge = f' <span class="gagu-badge">{g_match.group(1)}{g_match.group(2)}</span>' if g_match else ""
                    
                    try: area_val = f"{float(f_row.get('area', 0)):,.1f} ㎡"
                    except: area_val = "0 ㎡"
                    
                    st.markdown(f"""
                        <div class="floor-row">
                            <span class="floor-label">{f_row.get('flrNo', '')}층</span>
                            <span class="floor-use">{f_purp}{badge}</span>
                            <span class="floor-area">{area_val}</span>
                        </div>
                    """, unsafe_allow_html=True)
            else: st.write("층별 상세 정보가 없습니다.")
        st.markdown('</div>', unsafe_allow_html=True)
    else: st.error("데이터를 찾을 수 없습니다.")

st.markdown("---")
st.caption("© 원탑 건축물대장 조회 v4.5")
