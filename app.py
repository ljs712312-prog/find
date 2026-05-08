import streamlit as st
import pandas as pd
import os
import re

# 📌 1. 페이지 설정 및 디자인
st.set_page_config(page_title="원탑 건축물대장 통합 마스터", page_icon="🏢", layout="centered")

st.markdown("""
    <style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"]  { color: #111111 !important; }
    .main-title { font-size: 26px; font-weight: 800; color: #000000; margin-bottom: 5px; }
    div[data-testid="stTextInput"] input {
        font-size: 20px !important; font-weight: 600 !important; padding: 16px 15px !important; 
        background-color: #ffffff !important; border: 2px solid #007bff !important; border-radius: 12px;
    }
    .violation-box { background-color: #dc3545; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 800; margin-bottom: 15px; animation: blink 1.5s infinite; }
    @keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.8;} 100% {opacity: 1;} }
    div[data-testid="stMetric"] { background-color: white; border: 1px solid #e0e6ed; padding: 15px 5px; border-radius: 15px; text-align: center; }
    .info-container { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 6px solid #6f42c1; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-top: 15px; }
    .data-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #e9ecef; }
    .badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
    </style>
    """, unsafe_allow_html=True)

# 📌 2. 칼럼명 정규화 (숨은 글자 제거 및 매핑)
def standardize_columns(df):
    if df is None: return None
    # 🚨 [핵심] 칼럼명 앞뒤 공백 및 보이지 않는 특수기호 제거
    df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
    
    mapping = {
        '대지위치': 'platPlc', '관리건축물대장PK': 'mgmBldrgstPk', '대장구분코드명': 'regstrGbCdNm',
        '위반건축물여부': 'vlBldYn', '지상층수': 'grndFlrCnt', '승용승강기수': 'rideUseElvtCnt',
        '비상용승강기수': 'emgenUseElvtCnt', '사용승인일': 'useAprDay', '연면적': 'totArea',
        '가구수': 'fmlyCnt', '세대수': 'hhldCnt', '동명칭': 'dongNm', '호명칭': 'hoNm',
        '층번호': 'flrNo', '주용도코드명': 'mainPurpsCdNm', '면적': 'area', '기타용도': 'etcPurps',
        '구분코드': 'objGbCd'
    }
    df.rename(columns=mapping, inplace=True)
    
    # 만약 platPlc가 없다면 첫 번째 칼럼을 주소로 강제 지정
    if 'platPlc' not in df.columns and not df.empty:
        df.rename(columns={df.columns[0]: 'platPlc'}, inplace=True)
    return df

@st.cache_data
def load_data_safe(file_name):
    if os.path.exists(file_name):
        try:
            df = pd.read_csv(file_name, dtype=str)
            return standardize_columns(df)
        except Exception as e:
            st.error(f"파일 읽기 오류 ({file_name}): {e}")
    return None

# 📌 3. 메인 로직
st.markdown('<p class="main-title">🏢 원탑 건축물대장 통합 마스터</p>', unsafe_allow_html=True)
st.caption("수원 전지역 데이터 기반 통합 조회")

user_input = st.text_input("🔍 주소 입력", placeholder="예: 매탄동 1202-2")

# --- 디버그 모드 (문제 해결용) ---
with st.sidebar:
    st.header("⚙️ 디버그 설정")
    show_raw = st.checkbox("데이터 원본 미리보기")

if user_input:
    df_m = load_data_safe("suwon_building_master.csv.gz")
    
    if df_m is not None:
        if show_raw: st.write("📄 데이터 상단 5줄:", df_m.head())
        
        # 🔍 [핵심 수정] 검색 로직 강화: 공백 제거 및 부분 일치 검색
        df_m['clean_addr'] = df_m['platPlc'].str.replace(" ", "").str.replace("-", "")
        search_term = user_input.replace(" ", "").replace("-", "")
        
        # 주소에 검색어가 포함되어 있는지 확인
        res = df_m[df_m['clean_addr'].str.contains(search_term, na=False)]

        if not res.empty:
            item = res.iloc[0]
            pk = item.get('mgmBldrgstPk')
            bld_type = str(item.get('regstrGbCdNm', '일반'))
            
            # 위반 체크
            v_val = str(item.get('vlBldYn', '0')).strip().upper()
            if v_val in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.markdown('<div class="violation-box">⚠️ 위반건축물 확인 필요 ⚠️</div>', unsafe_allow_html=True)

            st.info(f"📍 **조회 주소:** {item.get('platPlc')} ({bld_type})")

            # 메트릭 카드
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("🏗️ 전체 층수", f"지상 {item.get('grndFlrCnt', '0')}층")
            with c2:
                p_cols = ['indrAutoUtcnt', 'indrMechUtcnt', 'oudrAutoUtcnt', 'oudrMechUtcnt']
                p_sum = sum([int(float(item.get(c, 0))) for c in p_cols if pd.notna(item.get(c))])
                st.metric("🚗 주차대수", f"{p_sum}대")
            with c3:
                el_cnt = int(float(item.get('rideUseElvtCnt', 0))) + int(float(item.get('emgenUseElvtCnt', 0)))
                st.metric("🛗 승강기", f"{el_cnt}대" if el_cnt > 0 else "없음")

            # 상세 정보 분기
            if "집합" in bld_type:
                st.markdown('<div class="info-container"><p style="font-size:17px; font-weight:800; margin-bottom:12px;">🔑 호수별 전용면적 (다세대/아파트)</p>', unsafe_allow_html=True)
                df_u_status = load_data_safe("suwon_unit_status.csv.gz")
                df_u_area = load_data_safe("suwon_unit_area.csv.gz")
                
                if df_u_status is not None and df_u_area is not None:
                    units = df_u_status[df_u_status['mgmBldrgstPk'] == pk].copy()
                    areas = df_u_area[(df_u_area['mgmBldrgstPk'] == pk) & (df_u_area['objGbCd'] == '1')].copy()
                    
                    if not units.empty:
                        merged = pd.merge(units, areas, on=['mgmBldrgstPk', 'flrNo', 'hoNm'], how='left')
                        merged = merged.sort_values(by=['flrNo', 'hoNm'])
                        for _, u_row in merged.iterrows():
                            st.markdown(f'<div class="data-row"><span>{u_row.get("flrNo")}층</span><b>{u_row.get("hoNm")}호</b><span style="color:#007bff">{float(u_row.get("area", 0)):.2f}㎡</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="info-container"><p style="font-size:17px; font-weight:800; margin-bottom:12px;">🏢 층별 상세 현황 (다가구)</p>', unsafe_allow_html=True)
                df_floor = load_data_safe("suwon_floor_info.csv.gz")
                if df_floor is not None:
                    floors = df_floor[df_floor['mgmBldrgstPk'] == pk].copy()
                    floors['flr_int'] = pd.to_numeric(floors['flrNo'], errors='coerce').fillna(0).astype(int)
                    for _, f_row in floors.sort_values(by='flr_int').iterrows():
                        etc = str(f_row.get('etcPurps', ''))
                        g_match = re.search(r'(\d+)\s*(가구|호)', etc)
                        badge = f' <span class="badge">{g_match.group(1)}{g_match.group(2)}</span>' if g_match else ""
                        st.markdown(f'<div class="data-row"><span>{f_row.get("flrNo")}층</span><b>{f_row.get("mainPurpsCdNm")}{badge}</b><span style="color:#007bff">{float(f_row.get("area", 0)):.1f}㎡</span></div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error(f"주소 '{user_input}'와(과) 일치하는 데이터를 찾을 수 없습니다.")
            st.warning("팁: 동 이름과 번지만 입력해 보세요. (예: 매탄동 1202-2)")
    else: st.error("기본 데이터 파일(master)을 불러올 수 없습니다.")

st.markdown("---")
st.caption("© 원탑 건축물대장 통합 마스터 v5.2")
