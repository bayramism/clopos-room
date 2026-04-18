import io
import os
import re
from datetime import datetime

import pandas as pd
import streamlit as st
from openpyxl.styles import Font
from rapidfuzz import fuzz, process

from rules import SPECIAL_RULES  # Qaydaları digər fayldan çəkir

st.set_page_config(page_title="ROOM CLOPOS Online", layout="wide")

if "selected_res" not in st.session_state:
    st.session_state.selected_res = "ROOM"
if "last_export" not in st.session_state:
    st.session_state.last_export = None


def normalize_text(text):
    if not text:
        return ""
    text = str(text).lower().strip()
    text = re.sub(r"\(\s*(?:ed|kg|kq|lt|qr|gr|ml|l)\s*\)", "", text)
    text = re.sub(r"\d+\s*%", "", text)
    text = re.sub(r"\d+[\.,]\d+", "", text)
    text = re.sub(r"\b\d+\b", "", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = (
        text.replace("neü", "new")
        .replace("c", "k")
        .replace("w", "v")
        .replace("x", "ks")
    )
    text = (
        text.replace("ç", "c")
        .replace("ə", "e")
        .replace("ğ", "g")
        .replace("ı", "i")
        .replace("ö", "o")
        .replace("ş", "s")
        .replace("ü", "u")
    )
    return " ".join(text.split())


def apply_special_logic(name, qty):
    n_norm = normalize_text(name)
    for key, val in SPECIAL_RULES.items():
        if normalize_text(key) in n_norm:
            return val[0], qty * val[1], val[1]
    return name, qty, 1


def get_best_match(query_name, choices, threshold=80):
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

    best = process.extractOne(
        q_norm, normalized_choices, scorer=fuzz.token_set_ratio
    )
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


def normalize_restaurant_name(name):
    return str(name).lower().replace("ı", "i").replace("i̇", "i").strip()


def discover_restaurants():
    restaurants = set()
    for file_name in os.listdir("."):
        lower_name = file_name.lower()
        if not lower_name.startswith("ana_"):
            continue
        if not (lower_name.endswith(".xlsx") or lower_name.endswith(".csv")):
            continue
        if "_horeca" in lower_name:
            restaurants.add(file_name[4:].rsplit("_horeca", 1)[0].upper())
        elif "_dk" in lower_name:
            restaurants.add(file_name[4:].rsplit("_dk", 1)[0].upper())
    return sorted(restaurants) if restaurants else ["ROOM", "BIBLIOTEKA", "FINESTRA"]


def _resolve_db_path(res_name, category):
    suffix = "horeca" if category == "Horeca" else "dk"
    target_prefix = f"ana_{normalize_restaurant_name(res_name)}_{suffix}"
    for file_name in os.listdir("."):
        normalized_file = normalize_restaurant_name(file_name)
        if normalized_file.startswith(target_prefix):
            if file_name.lower().endswith((".xlsx", ".csv")):
                return file_name
    return None


@st.cache_data(ttl=30, show_spinner=False)
def get_db(res_name, category):
    path = _resolve_db_path(res_name, category)
    if not path:
        return None
    try:
        if path.lower().endswith(".xlsx"):
            return pd.read_excel(path)
        return pd.read_csv(path)
    except Exception:
        return None


def build_export_file_name(restaurant, category):
    category_tag = "horeca" if category == "Horeca" else "dk"
    restaurant_tag = normalize_restaurant_name(restaurant).replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    return f"clopos_{restaurant_tag}_{category_tag}_{timestamp}.xlsx"


def to_bold_excel_bytes(dataframe):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name="CLOPOS")
        sheet = writer.sheets["CLOPOS"]
        for cell in sheet[1]:
            cell.font = Font(bold=True)
    output.seek(0)
    return output.getvalue()


def _first_id_for_name(df_base, m_name):
    sub = df_base.loc[df_base["ad"] == m_name, "id"]
    if sub.empty:
        raise KeyError("no id")
    return int(sub.iloc[0])


# --- SİDEBAR ---
st.sidebar.markdown("#### 🏢 Restoran seçimi")
res_options = discover_restaurants()
if st.session_state.selected_res not in res_options:
    st.session_state.selected_res = res_options[0]

for res_opt in res_options:
    label = f"{res_opt} ✅" if st.session_state.selected_res == res_opt else res_opt
    if st.sidebar.button(label, key=f"btn_{res_opt}", use_container_width=True):
        st.session_state.selected_res = res_opt
        st.rerun()

st.sidebar.info("Ana baza faylları GitHub mənbəsindən avtomatik oxunur.")

# --- PANELLƏR ---
curr = st.session_state.selected_res
st.markdown(
    f"<h3 style='text-align: center;'>{curr} | Online Panel</h3>",
    unsafe_allow_html=True,
)
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
            df_base = df_base.drop_duplicates(subset=["ad"], keep="first")

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
                    m_name, _ = get_best_match(p_name, choices, threshold=75)
                    if m_name:
                        mid = _first_id_for_name(df_base, m_name)
                        final_list.append(
                            {
                                "ID": mid,
                                "QUANTITY": p_qty,
                                "COST": round(cost, 4),
                                "LINE_TOTAL": round(p_qty * cost, 4),
                            }
                        )
                    else:
                        errors += 1
                except (ValueError, TypeError, KeyError):
                    errors += 1
                    continue

            if not final_list:
                st.warning(
                    "Uyğun məhsul tapılmadı. Ad yazılışları fərqli ola bilər və ya baza faylı uyğun deyil."
                )
                st.info(
                    f"Yoxlanan çek sətri: {len(df_c)} | Baza məhsulu: {len(df_base)} | "
                    f"Uğursuz emal/match sayı: {errors}"
                )
                sample = (
                    df_c[["ad", "miqdar"]]
                    .dropna(subset=["ad"])
                    .head(10)
                    .rename(columns={"ad": "Çekdə ad", "miqdar": "Miqdar"})
                )
                if not sample.empty:
                    st.markdown("İlk 10 çek adı (baza ilə vizual müqayisə üçün):")
                    st.dataframe(sample, use_container_width=True)
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
            export_name = build_export_file_name(curr, cat)
            export_bytes = to_bold_excel_bytes(res_df)
            st.session_state.last_export = {
                "restaurant": curr,
                "category": cat,
                "rows": len(res_df),
                "file_name": export_name,
                "file_bytes": export_bytes,
                "preview_df": res_df,
            }
            st.success(f"Hazır fayl: `{export_name}`")
            st.download_button(
                "📥 Endir",
                export_bytes,
                export_name,
                key="download_current",
            )
        else:
            st.error(
                "Uyğun ana baza tapılmadı. Repo daxilində fayl adı `ana_<restoran>_<horeca/dk>` formatında olmalıdır."
            )

    saved_export = st.session_state.get("last_export")
    if saved_export:
        st.markdown("---")
        st.markdown("### Son hazırlanmış fayl")
        st.write(
            f"Restoran: **{saved_export['restaurant']}** | "
            f"Sahə: **{saved_export['category']}** | "
            f"Sətir sayı: **{saved_export['rows']}**"
        )
        st.write(f"Fayl adı: `{saved_export['file_name']}`")
        st.dataframe(saved_export["preview_df"], use_container_width=True)
        st.download_button(
            "📥 Son faylı yenidən endir",
            saved_export["file_bytes"],
            saved_export["file_name"],
            key="download_saved",
        )

with tab2:
    ctrl_cat = st.selectbox(
        "Kontrol üçün baza sahəsi:",
        ["Horeca", "Dark Kitchen"],
        key="tab2_cat",
    )
    f_orig = st.file_uploader("1. Orijinal Çek", type=["xlsx"], key="ko")
    f_bot = st.file_uploader("2. Analiz Faylı", type=["xlsx"], key="kb")
    if f_orig and f_bot and st.button("🔍 Yoxla"):
        df_o, df_b = pd.read_excel(f_orig), pd.read_excel(f_bot)
        df_o = standardize_columns(df_o)
        df_b = standardize_columns(df_b)
        db = get_db(curr, ctrl_cat)
        if db is not None:
            db = standardize_columns(db)
            db = db.drop_duplicates(subset=["ad"], keep="first")
            if "id" not in df_b.columns:
                st.error("Analiz faylında `ID` / `id` sütunu tapılmadı.")
                st.stop()
            bot_ids = set(df_b["id"].astype(int).tolist())
            missing = []
            for _, row in df_o.iterrows():
                name = str(row.get("ad", ""))
                p_name, _, _ = apply_special_logic(name, 1)
                m_name, _ = get_best_match(p_name, db["ad"].tolist(), threshold=80)
                if m_name:
                    tid = _first_id_for_name(db, m_name)
                    if tid not in bot_ids:
                        missing.append(name)
                else:
                    missing.append(f"{name} (Bazada yoxdur)")
            st.table(pd.DataFrame(missing, columns=["Tapılmayanlar"]))
        else:
            st.error("Uyğun ana baza tapılmadı.")
