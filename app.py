import streamlit as st
import pandas as pd
import re
import os

# ==========================================
# 1. 모바일 & 다크모드 완벽 대응 UI 세팅
# ==========================================
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    
    /* 검색창 & 버튼 디자인 */
    div[data-testid="stTextInput"] input { border-radius: 10px; padding: 15px !important; font-size: 18px !important; font-weight: 700; }
    div[data-testid="stFormSubmitButton"] button { width: 100%; font-weight: 800; border-radius: 10px; padding: 10px; font-size: 18px; transition: 0.2s; background-color: #2563eb !important; color: white !important; border: none; }

    /* 기본(라이트 모드) 대시보드 디자인 */
    .dashboard-card { background: #ffffff; border-radius: 16px; padding: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-bottom: 30px; border: 1px solid #e2e8f0; }
    .bld-title { font-size: 24px; font-weight: 900; color: #0f172a; margin-bottom: 12px; }
    .bld-addr { font-size: 16px; color: #475569; line-height: 1.5; font-weight: 500; background: #f1f5f9; padding: 12px; border-radius: 10px; margin-bottom: 20px; }
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 15px; }
    .metric-box { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 15px 8px; text-align: center; }
    .metric-label { font-size: 13px; font-weight: 700; color: #64748b; margin-bottom: 4px; }
    .metric-value { font-size: 20px; font-weight: 900; color: #2563eb; }
    .sub-info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 25px; }
    .sub-box { background: #1e293b; color: white; border-radius: 12px; padding: 15px; text-align: center; }
    .sub-label { font-size: 13px; color: #94a3b8; font-weight: 700; margin-bottom: 4px; }
    .sub-value { font-size: 18px; font-weight: 900; }
    .highlight-date { color: #fbbf24; }
    .table-container { margin-top: 15px; border-radius: 10px; overflow-x: auto; border: 1px solid #e2e8f0; }
    .custom-table { width: 100%; border-collapse: collapse; background: white; min-width: 320px; }
    .custom-table th { background: #f8fafc; color: #334155; padding: 12px; font-size: 14px; font-weight: 800; border-bottom: 2px solid #e2e8f0; text-align: center; white-space: nowrap; }
    .custom-table td { padding: 12px; font-size: 14px; text-align: center; border-bottom: 1px solid #f1f5f9; color: #1e293b; white-space: nowrap; }
    .td-floor { font-weight: 800; color: #2563eb; }
    .td-unit { font-weight: 800; color: #ea580c; }
    .td-area { font-weight: 800; text-align: right; color: #0f172a; }

    /* 📱 모바일 최적화 (화면이 작아지면 4칸 -> 2칸으로 자동 변환) */
    @media (max-width: 600px) {
        .dashboard-card { padding: 16px; }
        .metric-grid { grid-template-columns: repeat(2, 1fr); }
        .sub-info-grid { grid-template-columns: 1fr; }
        .bld-title { font-size: 20px; }
        .metric-value { font-size: 22px; }
    }

    /* 🌙 다크 모드 최적화 (글씨가 안 보이는 현상 완벽 해결) */
    @media (prefers-color-scheme: dark) {
        .dashboard-card { background: #1e293b; border-color: #334155; }
        .bld-title { color: #f8fafc; }
        .bld-addr { background: #0f172a; color: #cbd5e1; }
        .metric-box { background: #0f172a; border-color: #334155; }
        .metric-label { color: #94a3b8; }
        .metric-value { color: #60a5fa; }
        .sub-box { background: #0f172a; border: 1px solid #334155; }
        .custom-table { background: #1e293b; }
        .custom-table th { background: #0f172a; color: #e2e8f0; border-bottom-color: #334155; }
        .custom-table td { border-bottom-color: #334155; color: #f8fafc; }
        .td-floor { color: #60a5fa; }
        .td-unit { color: #fb923c; }
        .td-area { color: #f8fafc; }
        .table-container { border-color: #334155; }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 고속 데이터 로직 (그대로 유지)
# ==========================================
def safe_int(val):
    try: return int(re.sub(r'[^0-9]', '', str(val)))
    except: return 0

def clean_txt(c):
    return re.sub(r'[^a-zA-Z0-9가-힣()㎡]', '', str(c)).strip()

def natural_sort(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', str(s))]

def format_date(val):
    d = str(val).strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}년 {d[4:6]}월 {d[6:]}일"
    return d

@st.cache_resource(show_spinner="데이터를 안전하게 준비 중입니다...")
def load_data():
    def read_file_safely(filename):
        if not os.path.exists(filename): return pd.DataFrame()
        try:
            df = pd.read_csv(filename, dtype=str, encoding='utf-8', on_bad_lines='skip')
        except:
            df = pd.read_csv(filename, dtype=str, encoding='cp949', on_bad_lines='skip')
        df.columns = [clean_txt(c) for c in df.columns]
        return df.fillna("")

    master = read_file_safely("suwon_building_master.csv.gz")
    floor = read_file_safely("suwon_floor_info.csv.gz")
    status = read_file_safely("suwon_unit_status.csv.gz")
    area = read_file_safely("suwon_unit_area.csv.gz")
    return master, floor, status, area

# ==========================================
# 3. 메인 앱 구동
# ==========================================
st.markdown('<h2 style="text-align:center; font-weight:900; margin-bottom:20px;">🏢 원탑 건축물대장</h2>', unsafe_allow_html=True)

df_master, df_floor, df_status, df_area = load_data()

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="주소를 입력하세요 (예: 망포동 6-11)")
    submitted = st.form_submit_button("🔍 정보 확인하기")

if submitted and query:
    if df_master.empty:
        st.error("데이터 파일을 찾을 수 없습니다.")
    else:
        nums = re.findall(r'\d+', query)
        q_main, q_sub = (safe_int(nums[0]) if nums else -1), (safe_int(nums[1]) if len(nums) > 1 else 0)
        q_dong = re.sub(r'[0-9-\s]', '', query).replace("산", "").strip()

        df_master['안전_번'] = df_master.get('번', pd.Series(dtype=str)).apply(safe_int)
        df_master['안전_지'] = df_master.get('지', pd.Series(dtype=str)).apply(safe_int)
        mask = (df_master['안전_번'] == q_main) & (df_master['안전_지'] == q_sub)
        if q_dong:
            mask &= df_master['대지위치'].str.contains(q_dong, na=False)
            
        items = df_master[mask].to_dict('records')

        if items:
            for b in items:
                pk = b.get('관리건축물대장PK', '')
                title = f"{b.get('건물명', '')} {b.get('동명칭', '')}".strip() or "일반 건축물"
                
                table_html = ""
                is_jibhap = "집합" in str(b.get('대장구분코드명', ''))
                
                if is_jibhap and not df_status.empty and not df_area.empty:
                    my_s = df_status[df_status['관리건축물대장PK'] == pk]
                    my_a = df_area[df_area['관리건축물대장PK'] == pk]
                    if not my_s.empty and not my_a.empty:
                        merged = pd.merge(my_s, my_a, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged = merged.fillna("").astype(str) 
                        merged['sort'] = merged['호명칭'].apply(natural_sort)
                        merged = merged.sort_values('sort').drop_duplicates(['층번호', '호명칭'])
                        
                        table_html = '<div class="table-container"><table class="custom-table"><tr><th>층/호</th><th>용도</th><th style="text-align:right;">전용면적</th></tr>'
                        for _, r in merged.iterrows():
                            table_html += f'<tr><td class="td-floor">{r.get("층번호")}층 {r.get("호명칭")}</td><td>{r.get("주용도코드명", "-")}</td><td class="td-area">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        table_html += '</table></div>'
                elif not df_floor.empty:
                    my_f = df_floor[df_floor['관리건축물대장PK'] == pk]
                    if not my_f.empty:
                        my_f = my_f.copy().fillna("").astype(str) 
                        my_f['sort'] = my_f['층번호'].apply(natural_sort)
                        my_f = my_f.sort_values('sort')
                        table_html = '<div class="table-container"><table class="custom-table"><tr><th>층</th><th>용도</th><th>가구/호</th><th style="text-align:right;">면적</th></tr>'
                        for _, r in my_f.iterrows():
                            unit_match = re.search(r'(\d+)\s*(가구|호)', str(r.get('기타용도', '')))
                            extracted_unit = unit_match.group(0) if unit_match else "-"
                            table_html += f'<tr><td class="td-floor">{r.get("층번호")}층</td><td>{r.get("주용도코드명", "-")}</td><td class="td-unit">{extracted_unit}</td><td class="td-area">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        table_html += '</table></div>'

                html_block = f"""
<div class="dashboard-card">
    <div class="bld-title">📌 {title}</div>
    <div class="bld-addr">
        <b>📍 지번:</b> {b.get('대지위치', '-')}<br>
        <div style="margin-top:4px;"><b>🛣️ 도로명:</b> {b.get('도로명대지위치', '정보 없음')}</div>
    </div>
    
    <div class="metric-grid">
        <div class="metric-box"><div class="metric-label">층수</div><div class="metric-value">{b.get('지상층수', '0')}층</div></div>
        <div class="metric-box"><div class="metric-label">세대/가구</div><div class="metric-value">{safe_int(b.get('가구수(가구)')) + safe_int(b.get('세대수(세대)'))}호</div></div>
        <div class="metric-box"><div class="metric-label">주차대수</div><div class="metric-value">{safe_int(b.get('옥내자주식대수(대)')) + safe_int(b.get('옥외자주식대수(대)'))}대</div></div>
        <div class="metric-box"><div class="metric-label">엘리베이터</div><div class="metric-value">{safe_int(b.get('승용승강기수')) + safe_int(b.get('비상용승강기수'))}대</div></div>
    </div>
    
    <div class="sub-info-grid">
        <div class="sub-box"><div class="sub-label">🏢 주용도</div><div class="sub-value">{b.get('주용도코드명', '-')}</div></div>
        <div class="sub-box"><div class="sub-label">📅 사용승인일</div><div class="sub-value highlight-date">{format_date(b.get('사용승인일', '-'))}</div></div>
    </div>
    
    <div style="font-size:18px; font-weight:800; margin-left:5px; margin-top:10px;">📊 층별 상세 현황</div>
    {table_html if table_html else '<p style="text-align:center; padding:20px; color:#64748b;">상세 정보가 없습니다.</p>'}
</div>
"""
                st.markdown(html_block, unsafe_allow_html=True)
        else:
            st.error("검색 결과가 없습니다.")
