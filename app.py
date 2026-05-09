import streamlit as st
import pandas as pd
import re
import os

# ==========================================
# 1. 원탑 맞춤형 모던 UI/UX 디자인 세팅
# ==========================================
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; background-color: #f4f6f8; }
    
    /* 검색창 & 버튼 세련되게 */
    .main-title { font-size: 36px; font-weight: 900; color: #111827; margin-bottom: 25px; text-align: center; letter-spacing: -1px; }
    div[data-testid="stTextInput"] input {
        border: 2px solid #cbd5e1 !important; border-radius: 12px; padding: 20px !important; font-size: 22px !important; font-weight: 700; color: #1e293b;
    }
    div[data-testid="stTextInput"] input:focus { border-color: #3b82f6 !important; box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2) !important; }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #1e293b !important; color: white !important;
        font-weight: 800; border-radius: 12px; padding: 15px; font-size: 22px; transition: all 0.2s;
    }
    div[data-testid="stFormSubmitButton"] button:hover { background-color: #0f172a !important; transform: translateY(-2px); }

    /* 찾았습니다 텍스트 (박스 없이 깔끔하게) */
    .result-text { font-size: 24px; font-weight: 800; color: #059669; text-align: center; margin: 30px 0 20px 0; }

    /* 📌 통합 대시보드 카드 (사진 느낌 완벽 구현) */
    .dashboard-card {
        background: #ffffff; border-radius: 20px; padding: 30px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.05); margin-bottom: 40px; border: 1px solid #e2e8f0;
    }
    
    /* 주소 영역 */
    .bld-title { font-size: 28px; font-weight: 900; color: #0f172a; margin-bottom: 15px; display: flex; align-items: center; gap: 8px; }
    .bld-addr { font-size: 18px; color: #475569; margin-bottom: 25px; line-height: 1.6; font-weight: 500; background: #f8fafc; padding: 15px; border-radius: 12px; }
    .bld-addr strong { color: #1e293b; }

    /* 6대 핵심 지표 그리드 (4칸 + 2칸) */
    .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 12px; }
    .grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 30px; }
    .info-box {
        background: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; padding: 20px 10px; text-align: center;
    }
    .info-box.highlight { background: #f8fafc; border-color: #e2e8f0; }
    .info-label { font-size: 15px; font-weight: 700; color: #64748b; margin-bottom: 8px; }
    .info-value { font-size: 24px; font-weight: 900; color: #2563eb; }
    .info-value.dark { color: #0f172a; font-size: 22px; }

    /* 층별 상세 현황 표 */
    .table-title { font-size: 22px; font-weight: 800; color: #1e293b; margin-bottom: 15px; padding-left: 10px; border-left: 4px solid #3b82f6; }
    .custom-table { width: 100%; border-collapse: collapse; border-radius: 12px; overflow: hidden; box-shadow: 0 0 0 1px #e2e8f0; }
    .custom-table th { background: #f1f5f9; color: #334155; padding: 16px; font-size: 16px; font-weight: 800; text-align: center; border-bottom: 2px solid #cbd5e1; }
    .custom-table td { padding: 16px; font-size: 17px; text-align: center; border-bottom: 1px solid #e2e8f0; color: #1e293b; font-weight: 500; }
    .td-floor { font-weight: 800; color: #2563eb; }
    .td-unit { font-weight: 800; color: #ea580c; }
    .td-area { font-weight: 800; text-align: right; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 초고속 메모리 캐싱 로직 (기존 성공 로직 그대로)
# ==========================================
def force_int(v):
    try: return int(re.sub(r'[^0-9]', '', str(v)))
    except: return 0

def clean_txt(c):
    return re.sub(r'[^a-zA-Z0-9가-힣()㎡]', '', str(c)).strip()

def natural_sort(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', str(s))]

@st.cache_data(show_spinner="최초 1회 데이터를 메모리에 적재 중입니다... 🚀")
def load_all_data():
    master, floor, status, area = None, None, None, None
    
    if os.path.exists("suwon_building_master.csv.gz"):
        cols = ['대지위치', '도로명대지위치', '번', '지', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '건물명', '동명칭', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
        master = pd.read_csv("suwon_building_master.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in cols)
        master.columns = [clean_txt(c) for c in master.columns]
        master['int_main'] = master['번'].apply(force_int)
        master['int_sub'] = master['지'].apply(force_int)
        
    if os.path.exists("suwon_floor_info.csv.gz"):
        f_cols = ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)']
        floor = pd.read_csv("suwon_floor_info.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in f_cols)
        floor.columns = [clean_txt(c) for c in floor.columns]
        
    if os.path.exists("suwon_unit_status.csv.gz"):
        status = pd.read_csv("suwon_unit_status.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in ['관리건축물대장PK', '호명칭', '층번호'])
        status.columns = [clean_txt(c) for c in status.columns]
        
    if os.path.exists("suwon_unit_area.csv.gz"):
        area = pd.read_csv("suwon_unit_area.csv.gz", dtype=str, usecols=lambda x: clean_txt(x) in ['관리건축물대장PK', '호명칭', '층번호', '전유공용구분코드', '면적(㎡)'])
        area.columns = [clean_txt(c) for c in area.columns]

    return master, floor, status, area

# ==========================================
# 3. 메인 앱 구동 및 UI 렌더링
# ==========================================
st.markdown('<div class="main-title">🏢 원탑 건축물대장 추출기</div>', unsafe_allow_html=True)

# 데이터 메모리 적재 (초고속 준비)
df_master, df_floor, df_status, df_area = load_all_data()

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="주소를 입력하세요 (예: 세류동 254)")
    submitted = st.form_submit_button("🔍 정보 초고속 추출")

if submitted and query:
    if df_master is None:
        st.error("데이터 파일(suwon_building_master.csv.gz)을 찾을 수 없습니다.")
    else:
        nums = re.findall(r'\d+', query)
        q_main = force_int(nums[0]) if len(nums) > 0 else -1
        q_sub = force_int(nums[1]) if len(nums) > 1 else 0
        q_dong = re.sub(r'[0-9-\s]', '', query).replace("산", "").strip()

        # 초고속 메모리 필터링
        mask = (df_master['int_main'] == q_main) & (df_master['int_sub'] == q_sub)
        if q_dong:
            mask &= df_master['대지위치'].str.contains(q_dong, na=False)
            
        items = df_master[mask].to_dict('records')

        if items:
            # 💡 휑한 박스 대신 깔끔한 안내 텍스트
            st.markdown(f'<div class="result-text">✅ {len(items)}개의 건축물 정보를 0.1초 만에 불러왔습니다.</div>', unsafe_allow_html=True)
            
            for idx, b in enumerate(items):
                pk = b['관리건축물대장PK']
                name = str(b.get('건물명', '')).replace('nan', '').strip()
                dong = str(b.get('동명칭', '')).replace('nan', '').strip()
                title = f"{name} {f'({dong})' if dong else ''}".strip() or f"일반 건축물 {idx+1}"

                is_jibhap = "집합" in str(b.get('대장구분코드명', ''))
                
                # 상세 표 HTML 생성 로직
                table_html = ""
                if is_jibhap and df_status is not None and df_area is not None:
                    my_s = df_status[df_status['관리건축물대장PK'] == pk]
                    my_a = df_area[df_area['관리건축물대장PK'] == pk]
                    if not my_s.empty and not my_a.empty:
                        merged = pd.merge(my_s, my_a, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged['sort'] = merged['호명칭'].apply(natural_sort)
                        merged = merged.sort_values('sort').drop_duplicates(['층번호', '호명칭'])
                        
                        table_html = '<table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right; padding-right:20px;">전용면적</th></tr>'
                        for _, r in merged.iterrows():
                            table_html += f'<tr><td class="td-floor">{r.get("층번호")}층 {r.get("호명칭")}</td><td>{r.get("주용도코드명", "-")}</td><td class="td-area" style="padding-right:20px;">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        table_html += '</table>'
                elif df_floor is not None:
                    my_f = df_floor[df_floor['관리건축물대장PK'] == pk]
                    if not my_f.empty:
                        my_f_copy = my_f.copy()
                        my_f_copy['sort'] = my_f_copy['층번호'].apply(natural_sort)
                        my_f_copy = my_f_copy.sort_values('sort')
                        
                        table_html = '<table class="custom-table"><tr><th>층</th><th>용도</th><th>가구/호</th><th style="text-align:right; padding-right:20px;">면적</th></tr>'
                        for _, r in my_f_copy.iterrows():
                            etc_text = str(r.get('기타용도', ''))
                            extracted_unit = "-"
                            # ✅ 공무원이 적은 N가구, N호만 깔끔하게 긁어오는 핵심 정규식
                            unit_match = re.search(r'(\d+)\s*(가구|호)', etc_text)
                            if unit_match: extracted_unit = unit_match.group(0)
                                
                            table_html += f'<tr><td class="td-floor">{r.get("층번호")}층</td><td>{r.get("주용도코드명", "-")}</td><td class="td-unit">{extracted_unit}</td><td class="td-area" style="padding-right:20px;">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        table_html += '</table>'

                if not table_html:
                    table_html = '<div style="padding:15px; color:#64748b; text-align:center; background:#f8fafc; border-radius:8px;">상세 정보가 없습니다.</div>'

                # 💡 사진처럼 이쁘게 다듬은 통합 대시보드 UI 렌더링
                st.markdown(f"""
                <div class="dashboard-card">
                    <div class="bld-title">📌 {title}</div>
                    <div class="bld-addr">
                        <div><strong>📍 지번:</strong> {b.get('대지위치', '-')}</div>
                        <div style="margin-top:5px;"><strong>🛣️ 도로명:</strong> {b.get('도로명대지위치', '정보 없음')}</div>
                    </div>
                    
                    <div class="grid-4">
                        <div class="info-box"><div class="info-label">층수</div><div class="info-value">{b.get('지상층수', '0')}층</div></div>
                        <div class="info-box"><div class="info-label">세대/가구</div><div class="info-value">{force_int(b.get('가구수(가구)')) + force_int(b.get('세대수(세대)'))}호</div></div>
                        <div class="info-box"><div class="info-label">주차대수</div><div class="info-value">{force_int(b.get('옥내자주식대수(대)')) + force_int(b.get('옥외자주식대수(대)'))}대</div></div>
                        <div class="info-box"><div class="info-label">엘리베이터</div><div class="info-value">{force_int(b.get('승용승강기수')) + force_int(b.get('비상용승강기수'))}대</div></div>
                    </div>
                    
                    <div class="grid-2">
                        <div class="info-box highlight"><div class="info-label">주용도</div><div class="info-value dark">{b.get('주용도코드명', '-')}</div></div>
                        <div class="info-box highlight"><div class="info-label">사용승인일</div><div class="info-value dark">{b.get('사용승인일', '-')}</div></div>
                    </div>
                    
                    <div class="table-title">📊 층별 상세 현황</div>
                    {table_html}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.error("입력하신 지번을 찾을 수 없습니다. (주소를 다시 확인해 주세요)")
