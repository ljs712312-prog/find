import streamlit as st
import pandas as pd
import re
import os

# ==========================================
# 1. 깔끔한 실무용 UI 디자인 세팅
# ==========================================
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    
    /* 입력창 및 버튼 디자인 */
    div[data-testid="stTextInput"] input {
        border: 3px solid #0056b3 !important; border-radius: 10px; padding: 20px !important; font-size: 24px !important; font-weight: 800;
    }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #0056b3 !important; color: white !important;
        font-weight: 900; border-radius: 10px; padding: 15px; font-size: 24px;
    }
    
    /* 주소 박스 */
    .address-box {
        background: #f8f9fa; padding: 20px; border-radius: 15px; border-left: 10px solid #0056b3; margin-bottom: 25px;
    }
    .address-title { font-size: 32px; font-weight: 900; color: #111; margin-bottom: 10px; }
    .address-text { font-size: 20px; color: #444; margin: 5px 0; }

    /* 주용도 및 승인일 박스 */
    .sub-box-container { display: flex; gap: 15px; margin-bottom: 30px; margin-top: 15px; }
    .sub-box {
        flex: 1; background: #343a40; color: white; padding: 15px; border-radius: 10px; text-align: center;
    }
    .sub-box span { font-size: 20px; font-weight: 700; margin-right: 10px; color: #adb5bd; }
    .sub-box strong { font-size: 24px; font-weight: 900; color: #ffc107; }

    /* 깔끔한 표 디자인 */
    .custom-table { width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .custom-table th { background: #0056b3; color: white; padding: 15px; text-align: center; font-size: 18px; }
    .custom-table td { padding: 15px; border-bottom: 1px solid #eee; font-size: 18px; text-align: center; }
    .row-floor { font-weight: 900; color: #0056b3; }
    .row-unit { font-weight: 900; color: #d9480f; }
    .row-area { font-weight: 900; text-align: right; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 초고속 메모리 캐싱 로직 (속도 향상의 핵심)
# ==========================================
def force_int(v):
    try: return int(re.sub(r'[^0-9]', '', str(v)))
    except: return 0

def clean_txt(c):
    return re.sub(r'[^a-zA-Z0-9가-힣()㎡]', '', str(c)).strip()

def natural_sort(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

# ✅ 앱을 켤 때 딱 1번만 데이터를 메모리에 올립니다. (이후 검색은 0.1초 컷)
@st.cache_data(show_spinner="최초 1회 데이터를 메모리에 적재 중입니다... (이후부터는 초고속으로 검색됩니다!)")
def load_all_data():
    master, floor, status, area = None, None, None, None
    
    # 1. 표제부 로드
    if os.path.exists("suwon_building_master.csv.gz"):
        cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
        master = pd.read_csv("suwon_building_master.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in cols)
        master.columns = [clean_txt(c) for c in master.columns]
        master['int_main'] = master['번'].apply(force_int)
        master['int_sub'] = master['지'].apply(force_int)
        
    # 2. 층별개요 로드
    if os.path.exists("suwon_floor_info.csv.gz"):
        f_cols = ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']
        floor = pd.read_csv("suwon_floor_info.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in f_cols)
        floor.columns = [clean_txt(c) for c in floor.columns]
        
    # 3. 전유부 & 면적 로드 (집합건축물용)
    if os.path.exists("suwon_unit_status.csv.gz"):
        status = pd.read_csv("suwon_unit_status.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in ['관리건축물대장PK', '호명칭', '층번호'])
        status.columns = [clean_txt(c) for c in status.columns]
        
    if os.path.exists("suwon_unit_area.csv.gz"):
        area = pd.read_csv("suwon_unit_area.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in ['관리건축물대장PK', '호명칭', '층번호', '전유공용구분코드', '면적(㎡)'])
        area.columns = [clean_txt(c) for c in area.columns]

    return master, floor, status, area

# ==========================================
# 3. 메인 앱 구동
# ==========================================
st.markdown('<p class="main-title">🏢 원탑 건축물대장 추출기</p>', unsafe_allow_html=True)

# 데이터 메모리 적재 (최초 1회만 실행됨)
df_master, df_floor, df_status, df_area = load_all_data()

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 망포동 6-11 / 세류동 254")
    submitted = st.form_submit_button("🔍 정보 초고속 추출")

if submitted and query:
    if df_master is None:
        st.error("데이터 파일(suwon_building_master.csv.gz)을 찾을 수 없습니다.")
    else:
        # 검색어 분석
        nums = re.findall(r'\d+', query)
        q_main = force_int(nums[0]) if len(nums) > 0 else -1
        q_sub = force_int(nums[1]) if len(nums) > 1 else 0
        q_dong = re.sub(r'[0-9-\s]', '', query).replace("산", "").strip()

        # 메모리 상의 데이터프레임에서 즉시 필터링 (초고속)
        mask = (df_master['int_main'] == q_main) & (df_master['int_sub'] == q_sub)
        if q_dong:
            mask &= df_master['대지위치'].str.contains(q_dong, na=False)
            
        items = df_master[mask].to_dict('records')

        if items:
            st.success(f"✅ {len(items)}개의 건축물 정보를 0.1초 만에 불러왔습니다.")
            
            for b in items:
                pk = b['관리건축물대장PK']
                name = str(b.get('건물명', '')).replace('nan', '').strip()
                dong = str(b.get('동명칭', '')).replace('nan', '').strip()
                title = f"{name} {f'({dong})' if dong else ''}".strip() or "일반 건축물"

                # 1. 주소 섹션
                st.markdown(f"""
                <div class="address-box">
                    <div class="address-title">📌 {title}</div>
                    <div class="address-text"><b>📍 지번:</b> {b.get('대지위치', '-')}</div>
                    <div class="address-text"><b>🛣️ 도로명:</b> <span style="color:#0056b3; font-weight:800;">{b.get('도로명대지위치', '정보 없음')}</span></div>
                </div>
                """, unsafe_allow_html=True)

                # 2. 핵심 4대 지표 (Streamlit 내장 Metric 사용 - 깔끔하고 안정적임)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{b.get('지상층수', '0')}층")
                c2.metric("세대/가구", f"{force_int(b.get('가구수(가구)')) + force_int(b.get('세대수(세대)'))}호")
                c3.metric("주차대수", f"{force_int(b.get('옥내자주식대수(대)')) + force_int(b.get('옥외자주식대수(대)'))}대")
                c4.metric("엘리베이터", f"{force_int(b.get('승용승강기수')) + force_int(b.get('비상용승강기수'))}대")

                # 3. 주용도 / 승인일 하단 박스
                st.markdown(f"""
                <div class="sub-box-container">
                    <div class="sub-box"><span>🏢 주용도</span><strong>{b.get('주용도코드명', '-')}</strong></div>
                    <div class="sub-box"><span>📅 사용승인일</span><strong>{b.get('사용승인일', '-')}</strong></div>
                </div>
                """, unsafe_allow_html=True)

                # 4. 상세 현황 표
                st.markdown('<h3 style="font-weight:900; color:#222;">📊 층별 상세 현황</h3>', unsafe_allow_html=True)
                
                is_jibhap = "집합" in str(b.get('대장구분코드명', ''))
                
                # 상가/고시원 (집합건축물) 처리
                if is_jibhap and df_status is not None and df_area is not None:
                    my_s = df_status[df_status['관리건축물대장PK'] == pk]
                    my_a = df_area[df_area['관리건축물대장PK'] == pk]
                    
                    if not my_s.empty and not my_a.empty:
                        merged = pd.merge(my_s, my_a, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged['sort'] = merged['호명칭'].apply(natural_sort)
                        merged = merged.sort_values('sort').drop_duplicates(['층번호', '호명칭'])
                        
                        tbl = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th>전용면적</th></tr>'
                        for _, r in merged.iterrows():
                            tbl += f'<tr><td class="row-floor">{r.get("층번호")}층 {r.get("호명칭")}</td><td>{r.get("주용도코드명", "-")}</td><td class="row-area">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        st.markdown(tbl + '</table>', unsafe_allow_html=True)
                    else:
                        st.info("해당 건물의 상세 호수 정보가 없습니다.")
                        
                # 단독/다가구 (일반건축물) 처리 - N가구 추출 로직 완벽 적용
                elif df_floor is not None:
                    my_f = df_floor[df_floor['관리건축물대장PK'] == pk]
                    if not my_f.empty:
                        my_f_copy = my_f.copy()
                        my_f_copy['sort'] = my_f_copy['층번호'].apply(natural_sort)
                        my_f_copy = my_f_copy.sort_values('sort')
                        
                        tbl = '<table class="custom-table"><tr><th>층</th><th>용도</th><th>가구/호</th><th>면적</th></tr>'
                        for _, r in my_f_copy.iterrows():
                            # ✅ 공무원이 적어둔 '기타용도'에서 N가구, N호만 귀신같이 긁어옵니다.
                            etc_text = str(r.get('기타용도', ''))
                            extracted_unit = "-"
                            unit_match = re.search(r'(\d+)\s*(가구|호)', etc_text)
                            if unit_match:
                                extracted_unit = unit_match.group(0) # 예: "2가구", "1호"
                                
                            tbl += f'<tr><td class="row-floor">{r.get("층번호")}층</td><td>{r.get("주용도코드명", "-")}</td><td class="row-unit">{extracted_unit}</td><td class="row-area">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        st.markdown(tbl + '</table>', unsafe_allow_html=True)
                    else:
                        st.info("해당 건물의 층별 정보가 없습니다.")

                st.markdown("<br><hr style='border-top:2px dashed #ccc;'><br>", unsafe_allow_html=True)
        else:
            st.error("입력하신 지번을 찾을 수 없습니다. (주소를 다시 확인해 주세요)")
