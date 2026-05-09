import streamlit as st
import pandas as pd
import re
import os

# 1. 기본 설정 (가장 안정적인 형태)
st.set_page_config(page_title="원탑 건축물대장 추출기", layout="wide")

# 2. 안전한 숫자 변환 함수
def safe_int(val):
    try:
        return int(re.sub(r'[^0-9]', '', str(val)))
    except:
        return -1

# 3. 궁극의 에러 방지 데이터 로딩 (어떤 파일이 들어와도 안 튕김)
@st.cache_resource(show_spinner="안전하게 데이터를 불러오고 있습니다...")
def load_data():
    def read_file_safely(filename):
        # gz 파일이 없으면 일반 csv를 찾도록 안전망 추가
        if not os.path.exists(filename):
            alt_name = filename.replace('.csv.gz', '.csv')
            if os.path.exists(alt_name):
                filename = alt_name
            else:
                return pd.DataFrame() # 파일 없으면 빈 데이터 반환 (에러 방지)
                
        # 인코딩 에러 원천 차단
        try:
            df = pd.read_csv(filename, dtype=str, encoding='utf-8', on_bad_lines='skip')
        except UnicodeDecodeError:
            df = pd.read_csv(filename, dtype=str, encoding='cp949', on_bad_lines='skip')
        except Exception:
            return pd.DataFrame()

        # 칼럼명에 숨어있는 특수문자나 공백 제거 (KeyError의 주범 해결)
        df.columns = [str(c).strip().replace('\ufeff', '') for c in df.columns]
        return df.fillna("")

    master = read_file_safely("suwon_building_master.csv.gz")
    floor = read_file_safely("suwon_floor_info.csv.gz")
    status = read_file_safely("suwon_unit_status.csv.gz")
    area = read_file_safely("suwon_unit_area.csv.gz")

    return master, floor, status, area

# 4. 화면 구성 (기본 인터페이스 사용)
st.title("🏢 원탑 건축물대장 (안정성 최우선 버전)")

# 데이터 로딩
df_master, df_floor, df_status, df_area = load_data()

# 파일 누락 체크
if df_master.empty:
    st.error("🚨 'suwon_building_master.csv.gz' 데이터가 없습니다. 파일 위치를 확인해주세요.")
    st.stop()

# 검색 영역
query = st.text_input("📍 지번 입력 (예: 망포동 6-11)", placeholder="주소를 입력 후 엔터를 누르세요")

if st.button("🔍 검색") or query:
    if not query:
        st.warning("주소를 입력해주세요.")
    else:
        nums = re.findall(r'\d+', query)
        if not nums:
            st.warning("주소에 지번(숫자)을 포함시켜주세요.")
        else:
            q_main = safe_int(nums[0])
            q_sub = safe_int(nums[1]) if len(nums) > 1 else 0
            q_dong = re.sub(r'[0-9-\s]', '', query).replace("산", "").strip()

            # 원본 데이터를 훼손하지 않고 복사본 사용
            temp_df = df_master.copy()
            
            # '번'과 '지' 칼럼이 제대로 있는지 확인 (KeyError 방지)
            if '번' in temp_df.columns and '지' in temp_df.columns:
                temp_df['안전_번'] = temp_df['번'].apply(safe_int)
                temp_df['안전_지'] = temp_df['지'].apply(safe_int)
                
                mask = (temp_df['안전_번'] == q_main) & (temp_df['안전_지'] == q_sub)
                
                # '대지위치' 칼럼이 있을 때만 동 이름 필터링
                if q_dong and '대지위치' in temp_df.columns:
                    mask &= temp_df['대지위치'].str.contains(q_dong, na=False)

                results = temp_df[mask]

                if results.empty:
                    st.info("해당 지번의 건축물이 없습니다. (주소를 다시 확인해주세요)")
                else:
                    st.success(f"✅ 총 {len(results)}건의 건축물을 안전하게 불러왔습니다.")
                    
                    for idx, row in results.iterrows():
                        st.markdown("---")
                        
                        # 건물명 처리
                        bldg_name = row.get('건물명', '').strip()
                        dong_name = row.get('동명칭', '').strip()
                        display_name = f"{bldg_name} {dong_name}".strip()
                        if not display_name:
                            display_name = f"건축물 {idx+1}"
                            
                        st.subheader(f"📌 {display_name}")
                        st.write(f"**📍 지번:** {row.get('대지위치', '-')}")
                        st.write(f"**🛣️ 도로명:** {row.get('도로명대지위치', '-')}")

                        # 4대 지표 (스트림릿 기본 박스 사용 - 오류 절대 안남)
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("층수", f"{row.get('지상층수', '0')}층")
                        
                        tot_hh = safe_int(row.get('가구수(가구)', 0)) + safe_int(row.get('세대수(세대)', 0))
                        c2.metric("세대/가구", f"{tot_hh}호")
                        
                        tot_park = safe_int(row.get('옥내자주식대수(대)', 0)) + safe_int(row.get('옥외자주식대수(대)', 0))
                        c3.metric("주차대수", f"{tot_park}대")
                        
                        tot_ev = safe_int(row.get('승용승강기수', 0)) + safe_int(row.get('비상용승강기수', 0))
                        c4.metric("엘리베이터", f"{tot_ev}대")

                        c5, c6 = st.columns(2)
                        c5.info(f"**🏢 주용도:** {row.get('주용도코드명', '-')}")
                        c6.info(f"**📅 사용승인일:** {row.get('사용승인일', '-')}")

                        # 층별 표 (스트림릿 기본 데이터프레임 사용)
                        st.markdown("#### 📊 층별 상세 현황")
                        pk = row.get('관리건축물대장PK', '')
                        is_jibhap = "집합" in str(row.get('대장구분코드명', ''))

                        if is_jibhap and not df_status.empty and not df_area.empty:
                            s_data = df_status[df_status.get('관리건축물대장PK', '') == pk]
                            a_data = df_area[df_area.get('관리건축물대장PK', '') == pk]
                            
                            if not s_data.empty and not a_data.empty:
                                merged = pd.merge(s_data, a_data, on=['관리건축물대장PK', '층번호', '호명칭'], how='inner')
                                # 표출할 칼럼만 선택
                                cols_to_show = ['층번호', '호명칭', '주용도코드명', '면적(㎡)']
                                avail_cols = [c for c in cols_to_show if c in merged.columns]
                                
                                # 데이터 정렬 및 스트림릿 기본 표 렌더링
                                st.dataframe(merged[avail_cols].sort_values('층번호'), use_container_width=True, hide_index=True)
                            else:
                                st.write("상세 호수 데이터가 없습니다.")
                                
                        elif not df_floor.empty:
                            f_data = df_floor[df_floor.get('관리건축물대장PK', '') == pk]
                            if not f_data.empty:
                                disp_df = f_data.copy()
                                
                                # 공무원 메모에서 [N가구/N호] 안전하게 추출
                                def extract_unit(txt):
                                    m = re.search(r'(\d+)\s*(가구|호)', str(txt))
                                    return m.group(0) if m else "-"
                                disp_df['가구/호'] = disp_df.get('기타용도', '').apply(extract_unit)
                                
                                cols_to_show = ['층번호', '주용도코드명', '가구/호', '면적(㎡)']
                                avail_cols = [c for c in cols_to_show if c in disp_df.columns]
                                
                                st.dataframe(disp_df[avail_cols].sort_values('층번호'), use_container_width=True, hide_index=True)
                            else:
                                st.write("층별 정보가 없습니다.")
            else:
                st.error("데이터 파일에 핵심 정보(번, 지)가 누락되어 검색할 수 없습니다.")
