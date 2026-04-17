import streamlit as st
import pandas as pd
from fuzzywuzzy import process, fuzz
import io
import re
import os
from datetime import datetime
from rules import SPECIAL_RULES # Qaydaları digər fayldan çəkir

st.set_page_config(page_title="ROOM CLOPOS Online", layout="wide")

if 'selected_res' not in st.session_state:
    st.session_state.selected_res = "ROOM"

def normalize_text(text):
    if not text: return ""
    text = str(text).lower().strip()
    text = re.sub(r'\(\s*(?:ed|kg|kq|lt|qr|gr|ml|l)\s*\)', '', text)
    text = re.sub(r'\d+\s*%', '', text)
    text = re.sub(r'\d+[\.,]\d+', '', text)
    text = re.sub(r'\b\d+\b', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
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
    if not choices:
        return None, 0

    q_norm = normalize_text(query_name)

    for choice in choices:
        if q_norm == normalize_text(choice):
            return choice, 100

    normalized_choices = [normalize_text(c) for c in choices]
    norm_to_original = {}
    for original, normalized in zip(choices, normalized_choices):
        norm_to_original.setdefault(normalized, original)

    best = process.extractOne(q_norm, normalized_choices, scorer=fuzz.token_set_ratio)
    if not best:
        return None, 0

    best_norm = best[0]
    score = best[1]
    best_match = norm_to_original.get(best_norm)
    if best_match:
        m_norm = normalize_text(best_match)
        q_words = [w for w in q_norm.split() if len(w) > 2]
        if q_words and not any(w in m_norm for w in q_words):
            return None, 0
        return (best_match, score) if score >= threshold else (None, 0)

    return None, 0


def standardize_columns(df):
    renamed = {}
    for col in df.columns:
        key = normalize_text(col)
        if key == "ad":
            renamed[col] = "ad"
        elif "miqdar" in key:
            renamed[col] = "miqdar"
        elif any(k in key for k in ["vahid", "qiym", "azn", "₼"]):
            renamed[col] = "price"
        elif key == "id":
            renamed[col] = "id"
    return df.rename(columns=renamed)

# --- SİDEBAR ---
st.sidebar.markdown("#### 📁 ANA BAZALAR")
res_options = ["ROOM", "BİBLİOTEKA", "FİNESTRA"]
for res_opt in res_options:
    with st.sidebar.expander(f"🏢 {res_opt}", expanded=(st.session_state.selected_res == res_opt)):
        if st.button(f"Seç {res_opt}", key=f"btn_{res_opt}"):
            st.session_state.selected_res = res_opt
            st.rerun()
        st.file_uploader("Horeca", type=["xlsx"], key=f"u_{res_opt}_h")
        st.file_uploader("DK", type=["xlsx"], key=f"u_{res_opt}_dk")

# Lokal bazaları yükləmə məntiqi (Online-da işləməsi üçün)
def get_db(res_name, category):
    key = f"u_{res_name}_{'h' if category == 'Horeca' else 'dk'}"
    uploaded_file = st.session_state.get(key)
    if uploaded_file:
        return pd.read_excel(uploaded_file)
    return None

# --- PANELLƏR ---
curr = st.session_state.selected_res
st.markdown(f"<h3 style='text-align: center;'>{curr} | Online Panel</h3>", unsafe_allow_html=True)
tab1, tab2 = st.tabs(["🚀 ANALİZ", "🔍 KONTROL"])

with tab1:
    col_a, col_b = st.columns(2)
    cat = col_a.selectbox("Sahə:", ["Horeca", "Dark Kitchen"])
    cek = col_b.file_uploader("📄 Sklad Çekini Yüklə", type=["xlsx"])

    if cek and st.button("⚡ Başlat"):
        df_base = get_db(curr, cat)
        if df_base is not None:
            df_c = pd.read_excel(cek)
            df_c = standardize_columns(df_c)
            df_base = standardize_columns(df_base)

            required_cek = {"ad", "miqdar"}
            required_base = {"ad", "id"}
            if not required_cek.issubset(set(df_c.columns)):
                st.error("Çek faylında `Ad` və `Miqdar` sütunları tapılmadı.")
                st.stop()
            if not required_base.issubset(set(df_base.columns)):
                st.error("Baza faylında `Ad` və `id` sütunları tapılmadı.")
                st.stop()

            final_list = []
            errors = 0
            choices = df_base["ad"].astype(str).tolist()
            for _, row in df_c.iterrows():
                try:
                    o_name = str(row.get("ad", "")).strip()
                    o_qty = float(row.get("miqdar", 0))
                    o_prc = float(row.get("price", 0))
                    if not o_name or o_qty == 0:
                        continue

                    p_name, p_qty, fct = apply_special_logic(o_name, o_qty)
                    cost = (o_prc / o_qty) / fct if o_qty != 0 else 0
                    m_name, _ = get_best_match(p_name, choices, threshold=80)
                    if m_name:
                        mid = df_base[df_base["ad"] == m_name]["id"].values[0]
                        final_list.append(
                            {
                                "ID": int(mid),
                                "QUANTITY": p_qty,
                                "COST": round(cost, 4),
                                "LINE_TOTAL": round(p_qty * cost, 4),
                            }
                        )
                except (ValueError, TypeError, KeyError):
                    errors += 1
                    continue

            if not final_list:
                st.warning("Uyğun məhsul tapılmadı. Bazanı və çek sütunlarını yoxlayın.")
                st.stop()

            res_df = (
                pd.DataFrame(final_list)
                .groupby("ID", as_index=False)
                .agg({"QUANTITY": "sum", "LINE_TOTAL": "sum"})
            )
            res_df["COST"] = (res_df["LINE_TOTAL"] / res_df["QUANTITY"]).round(4)
            res_df = res_df[["ID", "QUANTITY", "COST"]]

            st.success(f"{len(res_df)} məhsul hazırlandı.")
            if errors:
                st.info(f"{errors} sətir format xətasına görə keçildi.")

            st.dataframe(res_df, use_container_width=True)
            buf = io.BytesIO()
            res_df.to_excel(buf, index=False)
            st.download_button("📥 Endir", buf.getvalue(), f"{curr}_{datetime.now().strftime('%Y%m%d')}.xlsx")
        else: st.error("Sidebar-dan müvafiq bazanı yükləyin!")

with tab2:
    f_orig = st.file_uploader("1. Orijinal Çek", type=["xlsx"], key="ko")
    f_bot = st.file_uploader("2. Analiz Faylı", type=["xlsx"], key="kb")
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
        else: st.error("Baza yüklənməyib!")
