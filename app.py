import streamlit as st
import pandas as pd
from fuzzywuzzy import process, fuzz
import io
import re
import os
from datetime import datetime
from rules import SPECIAL_RULES

st.set_page_config(page_title="ROOM CLOPOS Online", layout="wide")

if 'selected_res' not in st.session_state:
    st.session_state.selected_res = "ROOM"

# --- SMART FUNKSİYALAR ---
def normalize_text(text):
    if not text: return ""
    text = str(text).lower().strip()
    replace_map = {'ç': 'c', 'ə': 'e', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u'}
    for k, v in replace_map.items():
        text = text.replace(k, v)
    text = re.sub(r'\(ed\)|\(kg\)|\(kq\)|ed|gr|qr|kg|kq', '', text)
    return " ".join(text.split())

def apply_special_logic(name, qty):
    n_norm = normalize_text(name)
    for key, val in SPECIAL_RULES.items():
        if normalize_text(key) in n_norm:
            return val[0], qty * val[1], val[1]
    return name, qty, 1

def get_best_match(query_name, choices, threshold=90):
    if not choices: return None, 0
    q_norm = normalize_text(query_name)
    for choice in choices:
        if q_norm == normalize_text(choice): return choice, 100
    best_match, score = process.extractOne(query_name, choices, scorer=fuzz.token_sort_ratio)
    return (best_match, score) if score >= threshold else (None, 0)

def get_db(res_name, category):
    sfx = "dk" if category == "Dark Kitchen" else "horeca"
    target = f"ana_{res_name.lower().replace('ı', 'i')}_{sfx}"
    for f in os.listdir('.'):
        if f.lower().startswith(target):
            try:
                df = pd.read_excel(f) if f.endswith('.xlsx') else pd.read_csv(f)
                df.columns = [str(c).strip().lower() for c in df.columns]
                return df
            except: continue
    return None

# --- SIDEBAR ---
st.sidebar.markdown("### 🏢 RESTORAN SEÇİMİ")
res_options = ["ROOM", "BİBLİOTEKA", "FİNESTRA"]
curr = st.session_state.selected_res

for res_opt in res_options:
    col1, col2 = st.sidebar.columns([3, 1])
    if col1.button(f"{res_opt}", key=f"btn_{res_opt}", use_container_width=True):
        st.session_state.selected_res = res_opt
        st.rerun()
    if curr == res_opt:
        col2.markdown("✅")

# --- ƏSAS PANEL ---
st.markdown(f"<h3 style='text-align: center;'>{curr} | Tədarük Sistemi</h3>", unsafe_allow_html=True)
tab1, tab2 = st.tabs(["🚀 ANALİZ", "🔍 KONTROL"])

with tab1:
    c1, c2 = st.columns(2)
    cat = c1.selectbox("Analiz Sahəsi:", ["Horeca", "Dark Kitchen"])
    cek = c2.file_uploader("📄 Sklad Çekini Yüklə", type=["xlsx"])

    if cek and st.button("⚡ Analizi Başlat"):
        df_base = get_db(curr, cat)
        if df_base is not None:
            df_c = pd.read_excel(cek)
            final_list = []
            base_ads = df_base['ad'].tolist() if 'ad' in df_base.columns else []
            
            # Çek sütunlarını dinamik tapmaq üçün (₼ və vergül problemi üçün)
            c_cols = {str(c).strip(): c for c in df_c.columns}
            price_col = next((c for c in df_c.columns if '1 Vahid' in str(c) or '₼' in str(c)), '1 Vahid, ₼')

            for _, row in df_c.iterrows():
                try:
                    o_name = str(row['Ad'])
                    o_qty = float(row['Miqdar'])
                    o_prc = float(row[price_col])
                    
                    # COST HESABLAMASI BURADADIR
                    p_name, p_qty, fct = apply_special_logic(o_name, o_qty)
                    # Maya dəyəri = (Vahid Qiymət / Miqdar) / Faktor
                    cost = (o_prc / o_qty) / fct if o_qty != 0 else 0
                    
                    m_name, _ = get_best_match(p_name, base_ads)
                    if m_name:
                        mid = df_base[df_base['ad'] == m_name]['id'].values[0]
                        final_list.append({'ID': int(mid), 'QUANTITY': p_qty, 'COST': round(cost, 4)})
                except:
                    continue
            
            if final_list:
                res_df = pd.DataFrame(final_list).groupby('ID').agg({'QUANTITY':'sum', 'COST':'mean'}).reset_index()
                st.success("Analiz tamamlandı!")
                st.dataframe(res_df, use_container_width=True)
                buf = io.BytesIO()
                res_df.to_excel(buf, index=False)
                st.download_button("📥 Endir", buf.getvalue(), f"{curr}_{cat}.xlsx")
            else:
                st.warning("Məhsul tapılmadı.")
        else:
            st.error(f"⚠️ {curr} üçün {cat} bazası GitHub-da tapılmadı!")

with tab2:
    st.markdown("#### 🔍 Tapılmayanlar")
    f_orig = st.file_uploader("Orijinal Sklad Çeki", type=["xlsx"], key="ko")
    f_bot = st.file_uploader("Botun Analiz Faylı", type=["xlsx"], key="kb")
    if f_orig and f_bot and st.button("🔍 Siyahını Çıxar"):
        df_o, df_b = pd.read_excel(f_orig), pd.read_excel(f_bot)
        db = get_db(curr, cat)
        if db is not None:
            missing = []
            db_ads = db['ad'].tolist()
            for _, row in df_o.iterrows():
                try:
                    name = str(row['Ad'])
                    p_name, _, _ = apply_special_logic(name, 1)
                    m_name, _ = get_best_match(p_name, db_ads, threshold=80)
                    if m_name:
                        tid = db[db['ad'] == m_name]['id'].values[0]
                        if int(tid) not in df_b['ID'].values:
                            missing.append(name)
                    else:
                        missing.append(f"{name} (Bazada yoxdur)")
                except: continue
            st.table(pd.DataFrame(missing, columns=["Tapılmayanlar"]))
