import streamlit as st
import pandas as pd
import re
import os

st.set_page_config(page_title="원탑 건축물대장 추출기", layout="centered")

def extract_jibun(addr):
    nums = re.findall(r'\d+', str(addr))
    if len(nums) >= 2:
        return f"{int(nums[-2])}-{int(nums[-1])}"
    elif len(nums) == 1:
        return str(int(nums[0]))
    return ""

@st.cache_data
def load_data(file_path):
    if not os.path.exists(file_path): 
        return None
    return pd.read_csv(file_path, dtype=str)

st.title("🏢 원탑 건축물대장 추출기")

master = load_data("processed_master.csv.gz")
floor = load_data("processed_floor.csv.gz")
unit = load_data("processed_unit.csv.gz")

if master is None:
    st.error("가공된 데이터 파일을 찾을 수 없습니다.")
    st.stop()

query = st.text_input("📍 지번 주소 입력 (예: 매탄동 1202-2 또는 1202-2)")

if query:
    q_jibun = extract_jibun(query)
    q_dong = re.sub(r'[0-9-\s]', '', query)
    
    # 지번 일치 및 동 이름 포함 여부 확인
    mask = (master['지번검색키'] == q_jibun)
    if q_dong: 
        mask &= master['대지위치'].fillna('').str.contains(q_dong, na=False)
        
    res = master[mask]

    if not res.empty:
        item = res.iloc[0]
        pk = str(item.get('관리건축물대장PK', ''))
        bld_type = str(item.get('대장구분코드명', '정보 없음'))
        
        # 위반건축물 표시
        if '위반건축물여부' in item and str(item['위반건축물여부']).strip() in ['1', 'Y', '위반']:
            st.error("🚨 위반건축물 주의")

        st.subheader(f"📍 {item.get('대지위치', '')} ({bld_type})")
        st.write(f"🏢 **주용도:** {item.get('주용도코드명', '정보 없음')} | 📅 **사용승인일:** {item.get('사용승인일', '정보 없음')}")
        
        # 수치 계산 로직
        gagu = int(float(item.get('가구수(가구)', 0) or 0)) + int(float(item.get('세대수(세대)', 0) or 0))
        
        # 주차 및 승강기 대수 안전 합산
        park_cols = ['총주차수', '옥내자주식대수(대)', '옥외자주식대수(대)', '옥내기계식대수(대)', '옥외기계식대수(대)']
        park_total = sum([int(float(item.get(c, 0) or 0)) for c in park_cols if c in item])
        
        el_cols = ['승용승강기수', '비상용승강기수']
        el_total = sum([int(float(item.get(c, 0) or 0)) for c in el_cols if c in item])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("층수", f"지상 {item.get('지상층수', '0')}층")
        c2.metric("가구수", f"{gagu}가구")
        c3.metric("주차", f"{park_total}대")
        c4.metric("승강기", f"{el_total}대")

        st.divider()

        # 세부 정보 출력
        if "집합" in bld_type:
            st.markdown("### 🔑 호수별 전용면적")
            if unit is not None:
                u_list = unit[unit['관리건축물대장PK'] == pk]
                if not u_list.empty:
                    for _, u in u_list.iterrows():
                        st.write(f"- {u.get('층번호', '')}층 {u.get('호명칭', '')} : **{u.get('면적(㎡)', '0')} ㎡**")
                else:
                    st.write("상세 정보가 없습니다.")
        else:
            st.markdown("### 🏢 층별 상세 현황")
            if floor is not None:
                f_list = floor[floor['관리건축물대장PK'] == pk]
                if not f_list.empty:
                    for _, f in f_list.iterrows():
                        f_etc = str(f.get('기타용도', ''))
                        g_match = re.search(r'(\d+)\s*(가구|호)', f_etc)
                        badge = f" ({g_match.group(0)})" if g_match else ""
                        st.write(f"- {f.get('층번호', '')}층 {f.get('주용도코드명', '')}{badge} : **{f.get('면적(㎡)', '0')} ㎡**")
                else:
                    st.write("상세 정보가 없습니다.")
    else:
        st.warning("일치하는 검색 결과가 없습니다.")
