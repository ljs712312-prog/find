import streamlit as st
import pandas as pd
import re
import os
import textwrap

# ==========================================
# 1. 프리미엄 실무용 UI 디자인 세팅
# ==========================================
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; background-color: #f8fafc; }
    
    div[data-testid="stTextInput"] input { border: 2px solid #cbd5e1 !important; border-radius: 12px; padding: 15px 20px !important; font-size: 20px !important; font-weight: 700; color: #1e293b; }
    div[data-testid="stFormSubmitButton"] button { width: 100%; background-color: #1e293b !important; color: white !important; font-weight: 800; border-radius: 12px; padding: 12px; font-size: 20px; transition: 0.2s; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 고속 데이터 로직 & 에러 방지 함수
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

@st.cache_resource(show_spinner="시스템을 안전하게 준비 중입니다...")
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
st.markdown('<h1 style="text-align:center; font-weight:900; color:#0f172a; margin-bottom:30px;">🏢 원탑 건축물대장</h1>', unsafe_allow_html=True)

df_master, df_floor, df_status, df_area = load_data()

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="주소를 입력하세요 (예: 망포동 6-11)")
    submitted = st.form_submit_button("🔍 정보 초고속 추출")

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
                
                # 층별 상세 표 HTML 생성
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
                        
                        table_html = '<div style="margin-top:20px; border-radius:12px; overflow:hidden; border:1px solid #e2e8f0;"><table style="width:100%; border-collapse:collapse; background:white;"><tr><th style="background:#f8fafc; padding:15px; border-bottom:2px solid #e2e8f0;">층/호</th><th style="background:#f8fafc; padding:15px; border-bottom:2px solid #e2e8f0;">용도</th><th style="background:#f8fafc; padding:15px; border-bottom:2px solid #e2e8f0; text-align:right; padding-right:25px;">전용면적</th></tr>'
                        for _, r in merged.iterrows():
                            table_html += f'<tr><td style="padding:15px; border-bottom:1px solid #f1f5f9; text-align:center; font-weight:800; color:#2563eb;">{r.get("층번호")}층 {r.get("호명칭")}</td><td style="padding:15px; border-bottom:1px solid #f1f5f9; text-align:center;">{r.get("주용도코드명", "-")}</td><td style="padding:15px; border-bottom:1px solid #f1f5f9; text-align:right; padding-right:25px; font-weight:800;">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        table_html += '</table></div>'
                elif not df_floor.empty:
                    my_f = df_floor[df_floor['관리건축물대장PK'] == pk]
                    if not my_f.empty:
                        my_f = my_f.copy().fillna("").astype(str) 
                        my_f['sort'] = my_f['층번호'].apply(natural_sort)
                        my_f = my_f.sort_values('sort')
                        table_html = '<div style="margin-top:20px; border-radius:12px; overflow:hidden; border:1px solid #e2e8f0;"><table style="width:100%; border-collapse:collapse; background:white;"><tr><th style="background:#f8fafc; padding:15px; border-bottom:2px solid #e2e8f0;">층</th><th style="background:#f8fafc; padding:15px; border-bottom:2px solid #e2e8f0;">용도</th><th style="background:#f8fafc; padding:15px; border-bottom:2px solid #e2e8f0;">가구/호</th><th style="background:#f8fafc; padding:15px; border-bottom:2px solid #e2e8f0; text-align:right; padding-right:25px;">면적</th></tr>'
                        for _, r in my_f.iterrows():
                            unit_match = re.search(r'(\d+)\s*(가구|호)', str(r.get('기타용도', '')))
                            table_html += f'<tr><td style="padding:15px; border-bottom:1px solid #f1f5f9; text-align:center; font-weight:800; color:#2563eb;">{r.get("층번호")}층</td><td style="padding:15px; border-bottom:1px solid #f1f5f9; text-align:center;">{r.get("주용도코드명", "-")}</td><td style="padding:15px; border-bottom:1px solid #f1f5f9; text-align:center; font-weight:800; color:#ea580c;">{unit_match.group(0) if unit_match else "-"}</td><td style="padding:15px; border-bottom:1px solid #f1f5f9; text-align:right; padding-right:25px; font-weight:800;">{r.get("면적(㎡)", "-")} ㎡</td></tr>'
                        table_html += '</table></div>'

                # 💡 핵심: 띄어쓰기를 완전히 제거하여 코드 노출 버그 방지
                dashboard_html = textwrap.dedent(f"""
<div style="background:white; border-radius:20px; padding:30px; box-shadow:0 10px 25px rgba(0,0,0,0.05); border:1px solid #e2e8f0; margin-bottom:40px;">
<div style="font-size:30px; font-weight:900; color:#0f172a; margin-bottom:15px;">📌 {title}</div>
<div style="font-size:19px; color:#475569; line-height:1.6; font-weight:500; background:#f1f5f9; padding:15px; border-radius:12px; margin-bottom:25px;">
<b>📍 지번:</b> {b.get('대지위치', '-')}<br>
<b>🛣️ 도로명:</b> {b.get('도로명대지위치', '정보 없음')}
</div>
<div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin-bottom:12px;">
<div style="background:#ffffff; border:2px solid #f1f5f9; border-radius:15px; padding:20px 10px; text-align:center;">
<div style="font-size:15px; font-weight:700; color:#64748b; margin-bottom:8px;">층수</div>
<div style="font-size:26px; font-weight:900; color:#2563eb;">{b.get('지상층수', '0')}층</div>
</div>
<div style="background:#ffffff; border:2px solid #f1f5f9; border-radius:15px; padding:20px 10px; text-align:center;">
<div style="font-size:15px; font-weight:700; color:#64748b; margin-bottom:8px;">세대/가구</div>
<div style="font-size:26px; font-weight:900; color:#2563eb;">{safe_int(b.get('가구수(가구)')) + safe_int(b.get('세대수(세대)'))}호</div>
</div>
<div style="background:#ffffff; border:2px solid #f1f5f9; border-radius:15px; padding:20px 10px; text-align:center;">
<div style="font-size:15px; font-weight:700; color:#64748b; margin-bottom:8px;">주차대수</div>
<div style="font-size:26px; font-weight:900; color:#2563eb;">{safe_int(b.get('옥내자주식대수(대)')) + safe_int(b.get('옥외자주식대수(대)'))}대</div>
</div>
<div style="background:#ffffff; border:2px solid #f1f5f9; border-radius:15px; padding:20px 10px; text-align:center;">
<div style="font-size:15px; font-weight:700; color:#64748b; margin-bottom:8px;">엘리베이터</div>
<div style="font-size:26px; font-weight:900; color:#2563eb;">{safe_int(b.get('승용승강기수')) + safe_int(b.get('비상용승강기수'))}대</div>
</div>
</div>
<div style="display:grid; grid-template-columns:repeat(2, 1fr); gap:12px; margin-bottom:30px;">
<div style="background:#1e293b; color:white; border-radius:12px; padding:20px; text-align:center;">
<div style="font-size:14px; color:#94a3b8; font-weight:700; margin-bottom:5px;">주용도</div>
<div style="font-size:22px; font-weight:900;">{b.get('주용도코드명', '-')}</div>
</div>
<div style="background:#1e293b; color:white; border-radius:12px; padding:20px; text-align:center;">
<div style="font-size:14px; color:#94a3b8; font-weight:700; margin-bottom:5px;">사용승인일</div>
<div style="font-size:22px; font-weight:900; color:#fbbf24;">{format_date(b.get('사용승인일', '-'))}</div>
</div>
</div>
<div style="font-size:22px; font-weight:800; color:#1e293b; margin-left:5px;">📊 층별 상세 현황</div>
{table_html if table_html else '<p style="text-align:center; padding:20px; color:#64748b;">상세 정보가 없습니다.</p>'}
</div>
""").strip()
                st.markdown(dashboard_html, unsafe_allow_html=True)
        else:
            st.error("검색 결과가 없습니다.")
