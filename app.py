import streamlit as st
import pandas as pd
from fuzzywuzzy import process, fuzz
import io
import re
import os
from datetime import datetime
from rules import SPECIAL_RULES

st.set_page_config(page_title="CLOPOS AI Analiz", layout="wide")

# --- 1. MƏNTİQİ FUNKSİYALAR ---
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

def get_best_match(query_name, choices, threshold=85):
    if not choices: return None, 0
    q_norm = normalize_text(query_name)
    best_match, score = process.extractOne(query_name, choices, scorer=fuzz.token_sort_ratio)
    return (best_match, score) if score >= threshold else (None, 0)

def get_db(res_name, category):
    suffix = "dk" if category == "Dark Kitchen" else "horeca"
    target_name = f"ana_{res_name.lower().replace('ı', 'i')}_{suffix}"
    for f in os.listdir('.'):
        if f.lower().startswith(target_name):
            try:
                df = pd.read_excel(f) if f.endswith('.xlsx') else pd.read_csv(f)
                df.columns = [str(c).strip().lower() for c in df.columns]
                return df
            except: continue
    return None

# --- 2. SIDEBAR ---
if 'selected_res' not in st.session_state:
    st.session_state.selected_res = "ROOM"

st.sidebar.title("🏢 Restoranlar")
for res in ["ROOM", "BİBLİOTEKA", "FİNESTRA"]:
    if st.sidebar.button(f"{res} {'✅' if st.session_state.selected_res == res else ''}", use_container_width=True):
        st.session_state.selected_res = res
        st.rerun()

curr = st.session_state.selected_res

# --- 3. ƏSAS PANEL ---
st.header(f"🚀 {curr} Analiz Sistemi")
tab1, tab2 = st.tabs(["📊 Analiz", "🔍 Kontrol"])

with tab1:
    col1, col2 = st.columns(2)
    cat = col1.selectbox("Analiz Sahəsi:", ["Horeca", "Dark Kitchen"])
    cek_file = col2.file_uploader("Sklad Çekini Yüklə", type=["xlsx"])

    if cek_file and st.button("Analizi Başlat"):
        # Target adını burada təyin edirik ki, xəta verməsin
        target_file_prefix = f"ana_{curr.lower().replace('ı', 'i')}_{'dk' if cat == 'Dark Kitchen' else 'horeca'}"
        
        df_base = get_db(curr, cat)
        if df_base is not None:
            df_cek = pd.read_excel(cek_file)
            final_data = []
            base_ads = df_base['ad'].tolist() if 'ad' in df_base.columns else []
            
            # Çek sütunlarını tapırıq
            c_cols = df_cek.columns.tolist()
            price_col = next((c for c in c_cols if '1 Vahid' in str(c) or '₼' in str(c)), None)

            for _, row in df_cek.iterrows():
                try:
                    name, qty = str(row['Ad']), float(row['Miqdar'])
                    price = float(row[price_col]) if price_col else 0
                    
                    # COST MƏNTİQİ (Qiymət / Miqdar) / Faktor
                    p_name, p_qty, fct = apply_special_logic(name, qty)
                    cost_val = (price / qty) / fct if qty != 0 else 0
                    
                    m_name, _ = get_best_match(p_name, base_ads)
                    if m_name:
                        mid = df_base[df_base['ad'] == m_name]['id'].values[0]
                        final_data.append({'ID': int(mid), 'QUANTITY': p_qty, 'COST': round(cost_val, 4)})
                except: continue

            if final_data:
                res_df = pd.DataFrame(final_data).groupby('ID').agg({'QUANTITY':'sum', 'COST':'mean'}).reset_index()
                st.success("Analiz tamamlandı!")
                st.dataframe(res_df, use_container_width=True)
                
                buf = io.BytesIO()
                res_df.to_excel(buf, index=False)
                st.download_button("📥 Nəticəni Endir", buf.getvalue(), f"{curr}_{cat}.xlsx")
            else:
                st.warning("Uyğun məhsul tapılmadı.")
        else:
            st.error(f"GitHub-da '{target_file_prefix}' ilə başlayan baza tapılmadı!")

with tab2:
    st.info("Tapılmayan məhsullar üçün analiz edin.")
