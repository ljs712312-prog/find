import streamlit as st
import pandas as pd
import re
import os

# ==========================================
# 1. 기본 설정 (가장 안전한 순정 레이아웃)
# ==========================================
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

# 최소한의 디자인: 순정 박스(Metric)에 테두리만 살짝 입혀서 가독성 확보
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }
    div[data-testid="metric-container"] {
        border: 2px solid #e5e7eb; padding: 15px; border-radius: 12px; text-align: center;
        background-color: transparent;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 에러 원천 차단 데이터 로직
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

@st.cache_resource(show_spinner="데이터베이스 연결 중... (절대 튕기지 않습니다) 🚀")
def load_data():
    def read_file_safely(filename):
        if not os.path.exists(filename): return pd.DataFrame()
        try:
            # 모든 데이터를 강제로 '문자(String)'로 읽어들여 Arrow 에러 원천 차단
            df = pd.read_csv(filename, dtype=str, encoding='utf-8', on_bad_lines='skip')
        except:
            df = pd.read_csv(filename, dtype=str, encoding='cp949', on_bad_lines='skip')
        df.columns = [clean_txt(c) for c in df.columns]
        return df.fillna("").astype(str)

    master = read_file_safely("suwon_building_master.csv.gz")
    floor = read_file_safely("suwon_floor_info.csv.gz")
    status = read_file_safely("suwon_unit_status.csv.gz")
    area = read_file_safely("suwon_unit_area.csv.gz")
    return master, floor, status, area

# ==========================================
# 3. 메인 앱 구동 (순정 컴포넌트 사용)
# ==========================================
st.markdown('<h2 style="text-align:center; font-weight:900;">🏢 원탑 건축물대장</h2>', unsafe_allow_html=True)

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
            st.success(f"✅ {len(items)}건의 건축물 정보를 안전하게 불러왔습니다.")
            
            for b in items:
                pk = b.get('관리건축물대장PK', '')
                title = f"{b.get('건물명', '')} {b.get('동명칭', '')}".strip() or "일반 건축물"
                
                st.markdown("---")
                
                # 1. 주소 영역 (기본 Markdown)
                st.subheader(f"📌 {title}")
                st.write(f"**📍 지번:** {b.get('대지위치', '-')}")
                st.write(f"**🛣️ 도로명:** {b.get('도로명대지위치', '정보 없음')}")
                st.write("") # 여백
                
                # 2. 4대 지표 (순정 Metric - 모바일/다크모드 완벽 자동 대응)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("층수", f"{b.get('지상층수', '0')}층")
                c2.metric("세대/가구", f"{safe_int(b.get('가구수(가구)')) + safe_int(b.get('세대수(세대)'))}호")
                c3.metric("주차대수", f"{safe_int(b.get('옥내자주식대수(대)')) + safe_int(b.get('옥외자주식대수(대)'))}대")
                c4.metric("엘리베이터", f"{safe_int(b.get('승용승강기수')) + safe_int(b.get('비상용승강기수'))}대")
                
                # 3. 주용도 / 사용승인일 (순정 Info 박스)
                st.write("")
                col_a, col_b = st.columns(2)
                col_a.info(f"**🏢 주용도:** {b.get('주용도코드명', '-')}")
                col_b.warning(f"**📅 사용승인일:** {format_date(b.get('사용승인일', '-'))}")
                
                # 4. 상세 층별 표 (에러를 유발하는 Arrow를 우회하는 st.table 사용)
                st.write("#### 📊 층별 상세 현황")
                
                is_jibhap = "집합" in str(b.get('대장구분코드명', ''))
                
                if is_jibhap and not df_status.empty and not df_area.empty:
                    my_s = df_status[df_status['관리건축물대장PK'] == pk]
                    my_a = df_area[df_area['관리건축물대장PK'] == pk]
                    if not my_s.empty and not my_a.empty:
                        merged = pd.merge(my_s, my_a, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        merged['sort'] = merged['호명칭'].apply(natural_sort)
                        merged = merged.sort_values('sort').drop_duplicates(['층번호', '호명칭'])
                        
                        # 표 데이터를 이쁘게 세팅
                        merged['층/호'] = merged['층번호'] + "층 " + merged['호명칭']
                        merged['전용면적'] = merged['면적(㎡)'] + " ㎡"
                        disp_df = merged[['층/호', '주용도코드명', '전용면적']].copy()
                        disp_df.columns = ['층/호', '용도', '전용면적']
                        
                        # Arrow 에러를 절대 일으키지 않는 순정 정적 테이블
                        st.table(disp_df.set_index('층/호'))
                    else:
                        st.write("상세 정보가 없습니다.")
                        
                elif not df_floor.empty:
                    my_f = df_floor[df_floor['관리건축물대장PK'] == pk]
                    if not my_f.empty:
                        my_f = my_f.copy()
                        my_f['sort'] = my_f['층번호'].apply(natural_sort)
                        my_f = my_f.sort_values('sort')
                        
                        # 표 데이터를 이쁘게 세팅
                        my_f['층'] = my_f['층번호'] + "층"
                        my_f['면적'] = my_f['면적(㎡)'] + " ㎡"
                        
                        def extract_unit(txt):
                            m = re.search(r'(\d+)\s*(가구|호)', str(txt))
                            return m.group(0) if m else "-"
                        my_f['가구/호'] = my_f['기타용도'].apply(extract_unit)
                        
                        disp_df = my_f[['층', '주용도코드명', '가구/호', '면적']].copy()
                        disp_df.columns = ['층', '용도', '가구/호', '면적']
                        
                        # Arrow 에러를 절대 일으키지 않는 순정 정적 테이블
                        st.table(disp_df.set_index('층'))
                    else:
                        st.write("상세 정보가 없습니다.")
        else:
            st.error("검색 결과가 없습니다.")
