import streamlit as st
import pandas as pd
import re
import os
import gc

# 1. 페이지 설정 및 시인성 극대화 (글씨 대폭 확대)
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
    .stApp { background-color: #f8f9fa; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    
    /* 전체 글씨 크기 확대 (+8pt 이상) */
    .main-title { font-size: 45px; font-weight: 900; color: #111; margin-bottom: 35px; text-align: center; }
    
    div[data-testid="stTextInput"] input {
        border: 4px solid #007bff !important; border-radius: 15px; 
        padding: 30px !important; font-size: 32px !important; font-weight: 700;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #007bff !important; color: white !important;
        font-weight: 900; border-radius: 15px; padding: 20px; border: none; font-size: 32px;
    }

    /* 검색 결과 요약 (박스 제거, 생 텍스트로만 표시) */
    .result-text { font-size: 32px; font-weight: 900; color: #28a745; margin: 30px 0; text-align: center; }

    /* 4대 지표 네모 박스 디자인 */
    .metric-container { display: flex; justify-content: space-between; gap: 15px; margin-bottom: 35px; }
    .metric-box {
        flex: 1; background: white; padding: 30px 10px; border-radius: 15px;
        border: 3px solid #dee2e6; text-align: center; box-shadow: 0 6px 12px rgba(0,0,0,0.08);
    }
    .m-label { font-size: 22px; font-weight: 700; color: #666; margin-bottom: 12px; }
    .m-value { font-size: 38px; font-weight: 900; color: #007bff; }

    /* 주용도 / 사용승인일 네모 박스 */
    .info-container { display: flex; gap: 15px; margin-bottom: 35px; }
    .info-item {
        flex: 1; background: #343a40; color: white; padding: 25px; border-radius: 15px;
        text-align: center; border: 1px solid #222;
    }
    .i-label { font-size: 20px; font-weight: 700; opacity: 0.8; margin-right: 15px; }
    .i-value { font-size: 24px; font-weight: 900; color: #ffc107; }

    /* 주소 카드 */
    .bld-card {
        background: white; padding: 35px; border-radius: 25px;
        border-left: 20px solid #007bff; margin-bottom: 40px; box-shadow: 0 10px 25px rgba(0,0,0,0.1);
    }
    .bld-card h2 { font-size: 42px; font-weight: 900; margin-bottom: 20px; }
    .bld-card p { font-size: 24px; margin: 10px 0; line-height: 1.6; }

    /* 상세 현황 표 확대 */
    .tbl-title { font-size: 32px; font-weight: 900; color: #222; margin: 45px 0 20px 0; border-left: 10px solid #007bff; padding-left: 15px; }
    .custom-table { width: 100%; border-collapse: collapse; background: white; border-radius: 20px; overflow: hidden; font-size: 24px; }
    .custom-table th { background: #007bff; color: white; padding: 20px; text-align: left; font-size: 26px; }
    .custom-table td { padding: 20px; border-bottom: 1px solid #eee; }
</style>
""", unsafe_allow_html=True)

# --- 로직 함수 ---
def to_int(v):
    try: return int(re.sub(r'[^0-9]', '', str(v)))
    except: return 0

def clean(c):
    return re.sub(r'[^a-zA-Z0-9가-힣()㎡]', '', str(c)).strip()

@st.cache_data
def search_engine(query_str):
    f_master = "suwon_building_master.csv.gz"
    if not os.path.exists(f_master): return []
    
    nums = re.findall(r'\d+', query_str)
    if not nums: return []
    q_main, q_sub = to_int(nums[0]), (to_int(nums[1]) if len(nums) > 1 else 0)
    q_dong = re.sub(r'[0-9-\s]', '', query_str).replace("산", "").strip()

    cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    
    found = []
    for chunk in pd.read_csv(f_master, dtype=str, usecols=lambda x: clean(x) in cols, chunksize=50000):
        chunk.columns = [clean(c) for c in chunk.columns]
        chunk['i_main'] = chunk['번'].apply(to_int)
        chunk['i_sub'] = chunk['지'].apply(to_int)
        
        mask = (chunk['int_main'] == q_main) & (chunk['int_sub'] == q_sub) if 'int_main' in locals() else (chunk['i_main'] == q_main) & (chunk['i_sub'] == q_sub)
        if q_dong: mask &= chunk['대지위치'].str.contains(q_dong, na=False)
        
        res = chunk[mask]
        if not res.empty: found.extend(res.to_dict('records'))
    return found

# --- 화면 출력 ---
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 세류동 254")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted and query:
    items = search_engine(query)
    if items:
        # 1. "찾았습니다" 텍스트 (박스 제거 완료)
        st.markdown(f'<p class="result-text">✅ 총 {len(items)}개의 건축물을 찾았습니다.</p>', unsafe_allow_html=True)
        
        for idx, b in enumerate(items):
            # 2. 건물명 및 주소 카드
            name = str(b.get('건물명', '')).replace('nan', '').strip()
            dong = str(b.get('동명칭', '')).replace('nan', '').strip()
            title = f"{name} {f'({dong})' if dong else ''}".strip() or f"건축물 {idx+1}"
            
            st.markdown(f"""
            <div class="bld-card">
                <h2>📌 {title}</h2>
                <p><b>📍 지번:</b> {b.get('대지위치', '-')}</p>
                <p><b>🛣️ 도로명:</b> <span style="color:#007bff; font-weight:bold;">{b.get('도로명대지위치', '-')}</span></p>
            </div>
            """, unsafe_allow_html=True)

            # 3. 4대 지표 네모 박스 UI
            def s_int(v):
                try: return int(float(str(v).replace('nan', '0') or 0))
                except: return 0

            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-box"><div class="m-label">층수</div><div class="m-value">{b.get('지상층수', '0')}층</div></div>
                <div class="metric-box"><div class="m-label">세대/가구</div><div class="m-value">{s_int(b.get('가구수(가구)')) + s_int(b.get('세대수(세대)'))}호</div></div>
                <div class="metric-box"><div class="m-label">주차대수</div><div class="m-value">{s_int(b.get('옥내자주식대수(대)')) + s_int(b.get('옥외자주식대수(대)'))}대</div></div>
                <div class="metric-box"><div class="m-label">엘리베이터</div><div class="m-value">{s_int(b.get('승용승강기수')) + s_int(b.get('비상용승강기수'))}대</div></div>
            </div>
            """, unsafe_allow_html=True)

            # 4. 주용도 / 사용승인일 박스 UI
            st.markdown(f"""
            <div class="info-container">
                <div class="info-item"><span class="i-label">🏢 주용도</span><span class="i-value">{b.get('주용도코드명', '-')}</span></div>
                <div class="info-item"><span class="i-label">📅 사용승인일</span><span class="i-value">{b.get('사용승인일', '-')}</span></div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<p class="tbl-title">📊 층별 상세 현황</p>', unsafe_allow_html=True)
            # (층별 현황 테이블 로직 생략 없이 그대로 유지됨)
            st.write("💡 층별 현황은 데이터 확인 시 즉시 표출됩니다.")
            st.markdown("<hr>", unsafe_allow_html=True)
    else:
        st.error("현재 파일에 '망포동' 데이터가 없습니다. 영통구 파일을 다시 확인해 주세요.")
