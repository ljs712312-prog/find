import streamlit as st
import pandas as pd
import re
import os

# ==========================================
# 1. 프리미엄 실무 브리핑용 UI 세팅
# ==========================================
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; background-color: #f8fafc; }
    
    /* 검색창 & 버튼 디자인 (고급스럽게) */
    div[data-testid="stTextInput"] input {
        border: 2px solid #cbd5e1 !important; border-radius: 10px; padding: 15px 20px !important; 
        font-size: 20px !important; font-weight: 700; color: #1e293b;
    }
    div[data-testid="stTextInput"] input:focus { border-color: #2563eb !important; box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1) !important; }
    div[data-testid="stFormSubmitButton"] button {
        width: 100%; background-color: #1e293b !important; color: white !important;
        font-weight: 800; border-radius: 10px; padding: 12px; font-size: 20px; transition: 0.2s;
    }
    div[data-testid="stFormSubmitButton"] button:hover { background-color: #0f172a !important; }

    /* 네모 박스 (Metric) 디자인 강제 수정 */
    div[data-testid="metric-container"] {
        background-color: #ffffff; border: 1px solid #e2e8f0; padding: 20px; 
        border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); text-align: center;
    }
    div[data-testid="metric-container"] label { color: #64748b !important; font-size: 16px !important; font-weight: 700 !important; }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] { color: #2563eb !important; font-size: 28px !important; font-weight: 900 !important; }

    /* 건물 정보 헤더 카드 */
    .bld-header {
        background: white; border-radius: 15px; padding: 25px 30px; margin-bottom: 25px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05); border-top: 6px solid #1e293b;
    }
    .bld-title { font-size: 26px; font-weight: 900; color: #0f172a; margin-bottom: 12px; }
    .bld-addr { font-size: 18px; color: #475569; line-height: 1.6; font-weight: 500; }
    .bld-addr strong { color: #1e293b; }

    /* 주용도 & 승인일 다크 박스 */
    .sub-info-card {
        background: #1e293b; color: white; border-radius: 12px; padding: 20px; 
        text-align: center; display: flex; flex-direction: column; justify-content: center;
    }
    .sub-info-label { font-size: 14px; color: #94a3b8; font-weight: 700; margin-bottom: 5px; }
    .sub-info-value { font-size: 20px; font-weight: 900; color: #f8fafc; }
    .highlight-value { color: #fbbf24; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 안전한 데이터 로직 (절대 건드리지 않음)
# ==========================================
def safe_int(val):
    try: return int(re.sub(r'[^0-9]', '', str(val)))
    except: return 0

@st.cache_resource(show_spinner="시스템을 안전하게 준비 중입니다...")
def load_data():
    def read_file_safely(filename):
        if not os.path.exists(filename):
            alt_name = filename.replace('.csv.gz', '.csv')
            if os.path.exists(alt_name): filename = alt_name
            else: return pd.DataFrame()
        try:
            df = pd.read_csv(filename, dtype=str, encoding='utf-8', on_bad_lines='skip')
        except UnicodeDecodeError:
            df = pd.read_csv(filename, dtype=str, encoding='cp949', on_bad_lines='skip')
        except Exception:
            return pd.DataFrame()
        df.columns = [str(c).strip().replace('\ufeff', '') for c in df.columns]
        return df.fillna("")

    master = read_file_safely("suwon_building_master.csv.gz")
    floor = read_file_safely("suwon_floor_info.csv.gz")
    status = read_file_safely("suwon_unit_status.csv.gz")
    area = read_file_safely("suwon_unit_area.csv.gz")
    return master, floor, status, area

# ==========================================
# 3. 메인 앱 구동 (안전한 UI 렌더링)
# ==========================================
st.markdown('<h1 style="text-align:center; font-weight:900; color:#0f172a; margin-bottom:30px;">🏢 원탑 건축물대장</h1>', unsafe_allow_html=True)

df_master, df_floor, df_status, df_area = load_data()

if df_master.empty:
    st.error("🚨 'suwon_building_master.csv.gz' 데이터가 없습니다.")
    st.stop()

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="주소를 입력하세요 (예: 망포동 6-11)")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted and query:
    nums = re.findall(r'\d+', query)
    if not nums:
        st.warning("주소에 지번(숫자)을 포함시켜주세요.")
    else:
        q_main = safe_int(nums[0])
        q_sub = safe_int(nums[1]) if len(nums) > 1 else 0
        q_dong = re.sub(r'[0-9-\s]', '', query).replace("산", "").strip()

        temp_df = df_master.copy()
        if '번' in temp_df.columns and '지' in temp_df.columns:
            temp_df['안전_번'] = temp_df['번'].apply(safe_int)
            temp_df['안전_지'] = temp_df['지'].apply(safe_int)
            
            mask = (temp_df['안전_번'] == q_main) & (temp_df['안전_지'] == q_sub)
            if q_dong and '대지위치' in temp_df.columns:
                mask &= temp_df['대지위치'].str.contains(q_dong, na=False)

            results = temp_df[mask]

            if results.empty:
                st.info("해당 지번의 건축물이 없습니다. 주소를 다시 확인해주세요.")
            else:
                st.markdown(f'<div style="text-align:center; font-size:20px; font-weight:800; color:#059669; margin: 20px 0;">✅ {len(results)}건의 건축물 정보를 불러왔습니다.</div>', unsafe_allow_html=True)
                
                for idx, row in results.iterrows():
                    bldg_name = row.get('건물명', '').strip()
                    dong_name = row.get('동명칭', '').strip()
                    display_name = f"{bldg_name} {dong_name}".strip() or f"일반 건축물 {idx+1}"
                        
                    # 1. 주소 헤더 카드
                    st.markdown(f"""
                    <div class="bld-header">
                        <div class="bld-title">📌 {display_name}</div>
                        <div class="bld-addr">
                            <div><strong>📍 지번:</strong> {row.get('대지위치', '-')}</div>
                            <div style="margin-top:4px;"><strong>🛣️ 도로명:</strong> {row.get('도로명대지위치', '정보 없음')}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # 2. 핵심 4대 지표 (가장 안전한 st.metric 사용)
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("층수", f"{row.get('지상층수', '0')}층")
                    
                    tot_hh = safe_int(row.get('가구수(가구)', 0)) + safe_int(row.get('세대수(세대)', 0))
                    c2.metric("세대/가구", f"{tot_hh}호")
                    
                    tot_park = safe_int(row.get('옥내자주식대수(대)', 0)) + safe_int(row.get('옥외자주식대수(대)', 0))
                    c3.metric("주차대수", f"{tot_park}대")
                    
                    tot_ev = safe_int(row.get('승용승강기수', 0)) + safe_int(row.get('비상용승강기수', 0))
                    c4.metric("엘리베이터", f"{tot_ev}대")

                    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

                    # 3. 주용도 / 승인일 (다크 모드 포인트 카드)
                    c5, c6 = st.columns(2)
                    with c5:
                        st.markdown(f'<div class="sub-info-card"><div class="sub-info-label">주용도</div><div class="sub-info-value">{row.get("주용도코드명", "-")}</div></div>', unsafe_allow_html=True)
                    with c6:
                        st.markdown(f'<div class="sub-info-card"><div class="sub-info-label">사용승인일</div><div class="sub-info-value highlight-value">{row.get("사용승인일", "-")}</div></div>', unsafe_allow_html=True)

                    st.markdown("<div style='margin-bottom: 30px;'></div>", unsafe_allow_html=True)

                    # 4. 층별 상세 표 (안전하고 깔끔한 기본 데이터프레임)
                    st.markdown('<h3 style="font-weight:900; color:#1e293b; font-size:22px; padding-left:10px; border-left:4px solid #2563eb;">📊 층별 상세 현황</h3>', unsafe_allow_html=True)
                    
                    pk = row.get('관리건축물대장PK', '')
                    is_jibhap = "집합" in str(row.get('대장구분코드명', ''))

                    if is_jibhap and not df_status.empty and not df_area.empty:
                        s_data = df_status[df_status.get('관리건축물대장PK', '') == pk]
                        a_data = df_area[df_area.get('관리건축물대장PK', '') == pk]
                        
                        if not s_data.empty and not a_data.empty:
                            merged = pd.merge(s_data, a_data, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                            
                            # 정렬 로직 (자연 정렬)
                            def ns(s): return [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', str(s))]
                            if '호명칭' in merged.columns:
                                merged['sort'] = merged['호명칭'].apply(ns)
                                merged = merged.sort_values('sort').drop_duplicates(['층번호', '호명칭'])
                            
                            cols_to_show = ['층번호', '호명칭', '주용도코드명', '면적(㎡)']
                            avail_cols = [c for c in cols_to_show if c in merged.columns]
                            st.dataframe(merged[avail_cols], use_container_width=True, hide_index=True)
                        else:
                            st.info("상세 호수 데이터가 없습니다.")
                            
                    elif not df_floor.empty:
                        f_data = df_floor[df_floor.get('관리건축물대장PK', '') == pk]
                        if not f_data.empty:
                            disp_df = f_data.copy()
                            
                            def ns(s): return [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', str(s))]
                            if '층번호' in disp_df.columns:
                                disp_df['sort'] = disp_df['층번호'].apply(ns)
                                disp_df = disp_df.sort_values('sort')
                            
                            def extract_unit(txt):
                                m = re.search(r'(\d+)\s*(가구|호)', str(txt))
                                return m.group(0) if m else "-"
                            disp_df['가구/호'] = disp_df.get('기타용도', '').apply(extract_unit)
                            
                            cols_to_show = ['층번호', '주용도코드명', '가구/호', '면적(㎡)']
                            avail_cols = [c for c in cols_to_show if c in disp_df.columns]
                            
                            st.dataframe(disp_df[avail_cols], use_container_width=True, hide_index=True)
                        else:
                            st.info("층별 정보가 없습니다.")
                    
                    st.markdown("<br><hr style='border-top:1px solid #e2e8f0;'><br>", unsafe_allow_html=True)
        else:
            st.error("데이터 파일에 핵심 정보가 누락되어 검색할 수 없습니다.")
