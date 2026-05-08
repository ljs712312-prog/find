import streamlit as st
import pandas as pd
import re
import os

# ════════════════════════════════════════════════════════════
# 페이지 설정 및 디자인 (준석 님 취향 반영: 폰트 굵기 500-600)
# ════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="원탑 건축물대장 추출기",
    page_icon="🏢",
    layout="centered",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;600;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans KR', sans-serif !important;
    font-weight: 500 !important; /* 중간 굵기 고정 */
    color: #111111 !important;
}

/* 검색창: 배경 흰색, 글자 검정 고정 (시인성 확보) */
div[data-testid="stTextInput"] input {
    background-color: #ffffff !important;
    color: #111111 !important;
    font-weight: 600 !important;
    border: 2px solid #007bff !important;
    border-radius: 10px;
    padding: 12px !important;
}

/* 위반건축물 경고 */
.violation-box {
    background-color: #ff4b4b;
    color: white;
    padding: 15px;
    border-radius: 10px;
    text-align: center;
    font-weight: 800;
    margin-bottom: 20px;
    animation: blink 1.5s infinite;
}
@keyframes blink { 0% {opacity: 1;} 50% {opacity: 0.7;} 100% {opacity: 1;} }

/* 결과 컨테이너 */
.info-card {
    background-color: #ffffff;
    padding: 20px;
    border-radius: 15px;
    border-left: 8px solid #6f42c1;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    margin-top: 20px;
}

.data-row {
    display: flex;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid #f0f2f6;
}

.label { font-weight: 700; color: #6f42c1; }
.value { font-weight: 800; color: #007bff; }
.gagu-badge {
    background-color: #ffc107;
    color: #212529;
    padding: 2px 8px;
    border-radius: 5px;
    font-size: 13px;
    font-weight: 800;
}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 유연한 데이터 로딩 함수 (KeyError 방지용)
# ════════════════════════════════════════════════════════════
@st.cache_data
def load_data(file_path, data_type):
    if not os.path.exists(file_path):
        return None
    try:
        df = pd.read_csv(file_path, dtype=str)
        # 컬럼명 유령 문자 및 공백 제거
        df.columns = [re.sub(r'[^a-zA-Z0-9ㄱ-ㅣ가-힣()㎡]', '', c).strip() for c in df.columns]
        
        # 순서 기반 강제 매핑 (이름이 바뀌어도 에러 방지)
        if data_type == 'master':
            new_cols = ['addr', 'pk', 'bld_type', 'floors', 'gagu', 'sadae', 'tot_area', 'app_date', 'p_in', 'p_out']
            df.columns = new_cols + list(df.columns[len(new_cols):])
            # 검색용 정규화 주소 생성
            df['addr_norm'] = df['addr'].str.replace(r'[\s-]', '', regex=True)
        elif data_type == 'floor':
            new_cols = ['pk', 'flr_no', 'purpose', 'etc', 'area']
            df.columns = new_cols + list(df.columns[len(new_cols):])
        elif data_type == 'unit':
            new_cols = ['pk', 'dong', 'ho', 'flr_no', 'area']
            df.columns = new_cols + list(df.columns[len(new_cols):])
        return df
    except:
        return None

# ════════════════════════════════════════════════════════════
# 메인 실행 로직
# ════════════════════════════════════════════════════════════
def main():
    st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)
    
    # 데이터 로드
    master = load_data("mini_master.csv.gz", "master")
    floor = load_data("mini_floor.csv.gz", "floor")
    unit = load_data("mini_unit.csv.gz", "unit")

    if master is None:
        st.error("❌ 'mini_master.csv.gz' 파일을 찾을 수 없습니다.")
        return

    # 주소 검색창
    query = st.text_input("📍 지번 주소 입력", placeholder="예) 매탄동 1202-2")

    if query:
        q_norm = re.sub(r'[\s-]', '', query)
        matched = master[master['addr_norm'].str.contains(q_norm, na=False)]

        if matched.empty:
            st.warning("일치하는 건물이 없습니다. 지번을 확인해주세요.")
        else:
            # 여러 건일 경우 선택 (보통은 1건)
            if len(matched) > 1:
                selected_addr = st.selectbox("여러 건이 검색되었습니다. 선택하세요:", matched['addr'].tolist())
                item = matched[matched['addr'] == selected_addr].iloc[0]
            else:
                item = matched.iloc[0]

            pk = item['pk']
            b_type = str(item['bld_type'])

            # 상단 메트릭 요약 (주차, 가구수 등)
            st.info(f"📍 **조회 주소:** {item['addr']} ({b_type})")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("🏗️ 층수", f"{item['floors']}층")
            with col2:
                total_h = int(float(item['gagu'] or 0)) + int(float(item['sadae'] or 0))
                st.metric("🏠 가구수", f"{total_h}가구")
            with col3:
                total_p = int(float(item['p_in'] or 0)) + int(float(item['p_out'] or 0))
                st.metric("🚗 주차", f"{total_p}대")

            # 상세 정보 출력 분기
            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            
            if "집합" in b_type:
                st.markdown("### 🔑 호수별 전용면적 (다세대/아파트)")
                if unit is not None:
                    target_units = unit[unit['pk'] == pk]
                    if not target_units.empty:
                        for _, u in target_units.iterrows():
                            st.markdown(f"""
                            <div class="data-row">
                                <span class="label">{u['flr_no']}층 {u['ho']}</span>
                                <span class="value">{u['area']} ㎡</span>
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    st.write("상세 면적 데이터가 없습니다.")
            
            else:
                st.markdown("### 🏢 층별 상세 현황 (다가구/단독)")
                if floor is not None:
                    target_floors = floor[floor['pk'] == pk]
                    if not target_floors.empty:
                        for _, f in target_floors.iterrows():
                            # 수기 가구수 Regex 추출
                            etc_text = str(f['etc'])
                            g_match = re.search(r'(\d+)\s*(가구|호)', etc_text)
                            badge = f'<span class="gagu-badge">{g_match.group(0)}</span>' if g_match else ""
                            
                            st.markdown(f"""
                            <div class="data-row">
                                <span class="label">{f['flr_no']}층 {f['purpose']}</span>
                                {badge}
                                <span class="value">{f['area']} ㎡</span>
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    st.write("층별 데이터가 없습니다.")
            
            st.markdown('</div>', unsafe_allow_html=True)

            # 광고 등록 팁 (준석 님 전용 메모)
            with st.expander("💡 광고 등록 팁"):
                st.write("- **도보권 기준:** 네이버 지도 검색 시 10분 이내여야 '도보권' 문구 사용 가능.")
                st.write("- **면적:** 위 수치는 복도/계단 포함 연면적일 수 있으니 실측 평수 확인 권장.")

if __name__ == "__main__":
    main()
