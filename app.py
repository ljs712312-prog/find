import streamlit as st
import pandas as pd
import os

# 📌 1. 페이지 설정 및 디자인
st.set_page_config(
    page_title="원탑부동산 빌딩마스터",
    page_icon="🏢",
    layout="centered"
)

# 모바일 가독성을 위한 커스텀 CSS
st.markdown("""
    <style>
    .stApp { background-color: #fcfcfc; }
    .main-title { font-size: 26px; font-weight: 800; color: #1e1e1e; margin-bottom: 0px; }
    .sub-title { font-size: 14px; color: #666; margin-bottom: 25px; }
    .stMetric { background-color: #ffffff; border: 1px solid #eee; padding: 15px; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    [data-testid="stMetricValue"] { font-size: 22px !important; color: #007bff !important; }
    .reportview-container .main .block-container { padding-top: 2rem; }
    </style>
    """, unsafe_allow_html=True)

# 📌 2. 데이터 로딩 (압축 파일 전용)
@st.cache_data
def load_data():
    # 요청하신 정확한 파일명 설정
    file_path = "suwon_building_master_v3.csv.gz"
    
    if not os.path.exists(file_path):
        st.error(f"❌ '{file_path}' 파일을 찾을 수 없습니다. 깃허브에 파일이 정상적으로 올라갔는지 확인해주세요.")
        return None
        
    try:
        # 압축된 CSV 읽기
        df = pd.read_csv(file_path, dtype=str)
        
        # 검색 정확도를 위한 숫자 전처리
        df['bun_int'] = pd.to_numeric(df['bun'], errors='coerce').fillna(-1).astype(int)
        df['ji_int'] = pd.to_numeric(df['ji'], errors='coerce').fillna(-1).astype(int)
        df['clean_addr'] = df['platPlc'].str.replace(" ", "")
        return df
    except Exception as e:
        st.error(f"데이터 로딩 중 오류 발생: {e}")
        return None

df = load_data()

# 📌 3. 메인 UI 구성
st.markdown('<p class="main-title">🏢 원탑부동산 빌딩마스터</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">수원 전 지역 건축물대장 간편 조회 시스템</p>', unsafe_allow_html=True)

# 검색창 (모바일에서 클릭하기 쉽게 크게 설정)
user_input = st.text_input("주소를 입력하세요", placeholder="예: 인계동 1030 또는 파장동 22-3")

if user_input:
    if df is not None:
        parts = user_input.strip().split()
        if len(parts) >= 2:
            jibun = parts[-1]
            dong_name = "".join(parts[:-1])
            
            # 지번 분리 (하이픈 대응)
            if '-' in jibun:
                try:
                    b_num, j_num = map(int, jibun.split('-'))
                except:
                    st.error("지번 형식이 올바르지 않습니다.")
                    st.stop()
            else:
                b_num, j_num = int(jibun), 0

            # 🔍 강력한 텍스트+숫자 조합 검색
            target_text = f"{dong_name}{b_num}"
            if j_num > 0: target_text += f"-{j_num}"
            
            res = df[df['clean_addr'].str.contains(target_text, na=False)]

            if not res.empty:
                item = res.iloc[0]
                
                # 결과 헤더
                st.info(f"📍 **조회 주소:** {item['platPlc']}")
                
                # 메인 정보 카드 (2열 배치)
                c1, c2 = st.columns(2)
                
                with c1:
                    st.metric("📊 전체 층수", f"지상 {item.get('grndFlrCnt', '0')}층")
                    
                    # 사용승인일 (useAprDay)
                    u_day = str(item.get('useAprDay', '정보 없음'))
                    if len(u_day) >= 8:
                        u_day = f"{u_day[:4]}-{u_day[4:6]}-{u_day[6:8]}"
                    st.write(f"📅 **사용승인:** `{u_day}`")

                with c2:
                    # 주차 합산
                    p_cols = ['indrAutoUtcnt', 'indrMechUtcnt', 'oudrAutoUtcnt', 'oudrMechUtcnt']
                    p_sum = 0
                    for col in p_cols:
                        val = item.get(col, 0)
                        p_sum += int(float(val)) if pd.notna(val) and str(val).replace('.','').isdigit() else 0
                    
                    st.metric("🚗 총 주차대수", f"{p_sum}대")
                    
                    # 세대수 합산
                    hhld = int(float(item.get('hhldCnt', 0))) if pd.notna(item.get('hhldCnt')) else 0
                    fmly = int(float(item.get('fmlyCnt', 0))) if pd.notna(item.get('fmlyCnt')) else 0
                    st.write(f"🏠 **세대(가구):** `{hhld + fmly}세대`")

                # 하단 상세 정보
                st.divider()
                main_purp = item.get('mainPurpsCdNm', '정보 없음')
                st.markdown(f"📋 **건축물 용도:** {main_purp}")
                
                # 다방 매물유형 추천 팁
                if '다세대' in main_purp or '연립' in main_purp:
                    st.warning("💡 **다방 추천:** [빌라/연립/다세대]")
                elif '다가구' in main_purp or '단독' in main_purp:
                    st.warning("💡 **다방 추천:** [단독주택] 또는 [다가구주택]")
                elif '오피스텔' in main_purp:
                    st.warning("💡 **다방 추천:** [오피스텔]")
                else:
                    st.success("💡 **다방 추천:** [기타] (직접 확인 필요)")
                
                # 건물명 (있을 경우만 표시)
                bld_nm = item.get('bldNm')
                if pd.notna(bld_nm) and bld_nm != 'nan':
                    st.caption(f"🏢 건물명: {bld_nm}")

            else:
                st.error("❗ 해당 지번의 데이터를 찾을 수 없습니다.")
                # 비슷한 번지수 힌트
                similar = df[(df['clean_addr'].str.contains(dong_name)) & (df['bun_int'] == b_num)]
                if not similar.empty:
                    st.write("💡 **혹시 아래 주소를 찾으시나요?**")
                    for s_addr in similar['platPlc'].unique()[:3]:
                        st.write(f"- {s_addr}")
        else:
            st.warning("동 이름과 지번을 띄어쓰기로 구분해 입력해주세요. (예: 인계동 1111)")

# 하단 푸터
st.markdown("<br><br>", unsafe_allow_html=True)
st.caption("원탑부동산 전용 건축물대장 조회 도구 v3.0 (Gzip Optimized)")
