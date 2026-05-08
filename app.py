import streamlit as st
import pandas as pd
import re
import os
import gc

st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

# 📌 깔끔하고 시인성 높은 UI 스타일 지정
st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    html, body, [class*="css"] { color: #111111 !important; font-weight: 500 !important; }
    div[data-testid="stTextInput"] input { background-color: #ffffff !important; color: #111111 !important; border: 2px solid #007bff !important; border-radius: 12px; font-weight: 600 !important; }
    div[data-testid="stFormSubmitButton"] button { width: 100%; background-color: #007bff; color: white; font-weight: 800; border-radius: 10px; padding: 10px; border: none; }
    .info-card { background-color: #ffffff; padding: 20px; border-radius: 15px; border-left: 8px solid #6f42c1; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-top: 15px; }
    .violation { background-color: #ff4b4b; color: white; padding: 12px; border-radius: 10px; text-align: center; font-weight: 800; margin-bottom: 10px; }
    .data-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f1f3f5; font-size: 15px; }
    .badge { background-color: #ffc107; color: #212529; font-size: 12px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# 📌 무적 지번 검색기 (0이 몇 개든, 번지가 붙든 다 걸러냄)
def parse_jibun(text):
    if pd.isna(text): return ""
    cleaned = re.sub(r'[^0-9-]', '', str(text).replace("산", ""))
    parts = [str(int(p)) for p in cleaned.split('-') if p.isdigit()]
    return "-".join(parts)

# 📌 메모리 폭발(OOM) 방지를 위한 청크(Chunk) 로더
@st.cache_data(show_spinner="최초 1회 데이터 최적화 중입니다. (약 30초 소요)")
def load_and_optimize():
    def read_chunked(file_name, target_cols, is_area=False):
        if not os.path.exists(file_name): return pd.DataFrame()
        try:
            # 헤더만 읽어서 필요한 칼럼 이름 맞추기
            header = pd.read_csv(file_name, nrows=0).columns
            use_cols = [c for c in header if c.strip() in target_cols]
            
            chunks = []
            # 5만 줄씩 잘라서 읽어오기 (메모리 안정성 확보)
            for chunk in pd.read_csv(file_name, usecols=use_cols, dtype=str, chunksize=50000, on_bad_lines='skip'):
                chunk.columns = chunk.columns.str.strip()
                
                # 전유부의 경우, 엄청난 용량을 차지하는 공용면적을 버리고 전용면적(1)만 남김
                if is_area and '전유공용구분코드' in chunk.columns:
                    chunk = chunk[chunk['전유공용구분코드'] == '1']
                    chunk = chunk.drop(columns=['전유공용구분코드'])
                
                chunks.append(chunk)
            
            return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
        except:
            return pd.DataFrame()

    m_cols = ['대지위치', '관리건축물대장PK', '대장구분코드명', '주용도코드명', '위반건축물여부', '지상층수', '가구수(가구)', '세대수(세대)', '사용승인일', '옥내자주식대수(대)', '옥외자주식대수(대)', '승용승강기수', '비상용승강기수']
    master = read_chunked("suwon_building_master.csv.gz", m_cols)
    if not master.empty:
        master['검색키'] = master['대지위치'].apply(parse_jibun)

    floor = read_chunked("suwon_floor_info.csv.gz", ['관리건축물대장PK', '층번호', '주용도코드명', '기타용도', '면적(㎡)'])
    status = read_chunked("suwon_unit_status.csv.gz", ['관리건축물대장PK', '호명칭', '층번호'])
    area = read_chunked("suwon_unit_area.csv.gz", ['관리건축물대장PK', '호명칭', '층번호', '전유공용구분코드', '면적(㎡)'], is_area=True)

    # 읽기 완료 후 메모리 강제 청소
    gc.collect()
    return master, floor, status, area

st.markdown('### 🏢 원탑 건축물대장 추출기')

master, floor, status, area = load_and_optimize()

with st.form("search_form"):
    query = st.text_input("📍 지번 입력", placeholder="예: 망포동 6-11 또는 6-11")
    submitted = st.form_submit_button("🔍 정보 추출하기")

if submitted:
    if master.empty:
        st.error("🚨 깃허브에 원본 파일(suwon_...csv.gz)이 5개 모두 올라가 있는지 확인해주세요.")
    elif query:
        q_jibun = parse_jibun(query)
        q_dong = re.sub(r'[0-9-\s]', '', query)
        
        mask = (master['검색키'] == q_jibun)
        if q_dong: mask &= master['대지위치'].fillna('').str.contains(q_dong, na=False)
        
        res = master[mask]
        
        if not res.empty:
            item = res.iloc[0]
            pk = str(item.get('관리건축물대장PK', ''))
            
            if str(item.get('위반건축물여부', '')).strip() in ['1', 'Y', '위반', '위반건축물', 'O', '유']:
                st.markdown('<div class="violation">🚨 위반건축물 확인 필요 🚨</div>', unsafe_allow_html=True)

            st.info(f"📍 **{item.get('대지위치', '')}**\n\n🏢 **용도:** {item.get('주용도코드명', '-')} | 📅 **승인:** {item.get('사용승인일', '-')}")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("층수", f"{item.get('지상층수', '0')}층")
            c2.metric("가구", f"{int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))}가구")
            c3.metric("주차", f"{int(float(item.get('옥내자주식대수(대)', 0) or 0)) + int(float(item.get('옥외자주식대수(대)', 0) or 0))}대")
            c4.metric("엘베", f"{int(float(item.get('승용승강기수', 0) or 0)) + int(float(item.get('비상용승강기수', 0) or 0))}대")

            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            if "집합" in str(item.get('대장구분코드명', '')):
                st.markdown("#### 🔑 호수별 전용면적")
                if not status.empty and not area.empty:
                    t_stat = status[status['관리건축물대장PK'] == pk]
                    t_area = area[area['관리건축물대장PK'] == pk]
                    if not t_stat.empty and not t_area.empty:
                        merged = pd.merge(t_stat, t_area, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                        for _, u in merged.drop_duplicates(['층번호', '호명칭']).sort_values(['층번호', '호명칭']).iterrows():
                            st.markdown(f'<div class="data-row"><span>{u.get("층번호", "")}층 {u.get("호명칭", "")}</span><span style="color:#007bff; font-weight:800;">{u.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                    else: st.write("상세 정보 없음")
                else: st.write("상세 정보 없음")
            else:
                st.markdown("#### 🏢 층별 상세 현황")
                if not floor.empty:
                    f_list = floor[floor['관리건축물대장PK'] == pk]
                    if not f_list.empty:
                        for _, f in f_list.sort_values('층번호').iterrows():
                            etc = str(f.get('기타용도', ''))
                            g = re.search(r'(\d+)\s*(가구|호)', etc)
                            badge = f' <span class="badge">{g.group(0)}</span>' if g else ""
                            st.markdown(f'<div class="data-row"><span>{f.get("층번호", "")}층 {f.get("주용도코드명", "")}</span>{badge}<span style="color:#007bff; font-weight:800;">{f.get("면적(㎡)", "-")} ㎡</span></div>', unsafe_allow_html=True)
                    else: st.write("상세 정보 없음")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.error("검색 결과가 없습니다. 지번을 확인해주세요.")
