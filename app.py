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
    text = re.sub(r'\(ed\)|\(kg\)|\(kq\)|ed|gr|qr|kg|kq', '', text)
    text = text.replace('neü', 'new').replace('c', 'k').replace('w', 'v').replace('x', 'ks')
    text = text.replace('ç', 'c').replace('ə', 'e').replace('ğ', 'g').replace('ı', 'i').replace('ö', 'o').replace('ş', 's').replace('ü', 'u')
    return " ".join(text.split())

def apply_special_logic(name, qty):
    n_norm = normalize_text(name)
    for key, val in SPECIAL_RULES.items():
        if normalize_text(key) in n_norm:
            return val[0], qty * val[1], val[1]
    return name, qty, 1

def get_best_match(query_name, choices, threshold=95):
    if not choices: return None, 0
    q_norm = normalize_text(query_name)
    for choice in choices:
        if q_norm == normalize_text(choice): return choice, 100
    best_match, score = process.extractOne(query_name, choices, scorer=fuzz.token_sort_ratio)
    if best_match:
        m_norm = normalize_text(best_match)
        q_words = [w for w in q_norm.split() if len(w) > 2]
        if q_words and not any(w in m_norm for w in q_words): return None, 0
        return (best_match, score) if score >= threshold else (None, 0)
    return None, 0

def get_db(res_name, category):
 # GitHub-dakı bütün faylları siyahıla
    files = os.listdir('.')
    
    # Axtardığımız açar söz (məsələn: ana_biblioteka_horeca)
    suffix = "dk" if category == "Dark Kitchen" else "horeca"
    target = f"ana_{res_name.lower().replace('ı', 'i')}_{suffix}"
    
    for f in files:
        # Faylın adı həm bizim hədəflə başlamalı, həm də CSV və ya XLSX olmalıdır
        if f.lower().startswith(target):
            try:
                if f.lower().endswith('.csv'):
                    df = pd.read_csv(f)
                    # Sütun adlarını normallaşdıraq (id -> ID, Ad -> Ad)
                    df.columns = [c.strip().lower() for c in df.columns]
                    if 'id' in df.columns: df = df.rename(columns={'id': 'id'})
                    return df
                elif f.lower().endswith('.xlsx'):
                    df = pd.read_excel(f)
                    df.columns = [c.strip().lower() for c in df.columns]
                    return df
            except Exception as e:
                st.error(f"Fayl oxunarkən xəta: {e}")
    return None

# --- SIDEBAR (Səliqəli Versiya) ---
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

st.sidebar.markdown("---")
# Baza yükləmə hissəsini gizli "Ayarlar" daxilinə salırıq
with st.sidebar.expander("⚙️ Bazanı Yenilə (Ehtiyac olarsa)"):
    st.info("GitHub-dakı bazanı müvəqqəti əvəzləmək üçün istifadə edin.")
    st.file_uploader(f"{curr} - Horeca", type=["xlsx"], key=f"u_{curr}_h")
    st.file_uploader(f"{curr} - DK", type=["xlsx"], key=f"u_{curr}_dk")

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
            df_base.columns = df_base.columns.str.strip()
            final_list = []
            for _, row in df_c.iterrows():
                try:
                    o_name, o_qty, o_prc = str(row['Ad']), float(row['Miqdar']), float(row['1 Vahid, ₼'])
                    p_name, p_qty, fct = apply_special_logic(o_name, o_qty)
                    cost = (o_prc / o_qty) / fct if o_qty != 0 else 0
                    m_name, _ = get_best_match(p_name, df_base['Ad'].tolist())
                    if m_name:
                        mid = df_base[df_base['Ad'] == m_name]['id'].values[0]
                        final_list.append({'ID': int(mid), 'QUANTITY': p_qty, 'COST': round(cost, 4)})
                except: continue
            
            if final_list:
                res_df = pd.DataFrame(final_list).groupby('ID').agg({'QUANTITY':'sum', 'COST':'mean'}).reset_index()
                st.dataframe(res_df, use_container_width=True)
                buf = io.BytesIO(); res_df.to_excel(buf, index=False)
                st.download_button("📥 Endir", buf.getvalue(), f"{curr}_{cat}_{datetime.now().strftime('%Y%m%d')}.xlsx")
            else: st.warning("Heç bir məhsul eyniləşdirilmədi.")
        else: st.error("⚠️ Baza tapılmadı! GitHub-a faylı yüklədiyinizdən əmin olun.")

with tab2:
    st.markdown("#### Tapılmayan Məhsullar")
    f_orig = st.file_uploader("Orijinal Çek", type=["xlsx"], key="ko")
    f_bot = st.file_uploader("Analiz Faylı", type=["xlsx"], key="kb")
    if f_orig and f_bot and st.button("🔍 Yoxla"):
        df_o, df_b = pd.read_excel(f_orig), pd.read_excel(f_bot)
        db = get_db(curr, "Horeca")
        if db is not None:
            missing = []
            for _, row in df_o.iterrows():
                name = str(row['Ad'])
                p_name, _, _ = apply_special_logic(name, 1)
                m_name, _ = get_best_match(p_name, db['Ad'].tolist(), threshold=80)
                if m_name:
                    tid = db[db['Ad'] == m_name]['id'].values[0]
                    if int(tid) not in df_b['ID'].values: missing.append(name)
                else: missing.append(f"{name} (Bazada yoxdur)")
            st.table(pd.DataFrame(missing, columns=["Tapılmayanlar"]))
