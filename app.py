import streamlit as st
import pandas as pd
from fuzzywuzzy import process, fuzz
import io
import re
import os
from rules import SPECIAL_RULES

st.set_page_config(page_title="CLOPOS AI Analiz", layout="wide")


# --- 1. MƏNTİQİ FUNKSİYALAR ---

def normalize_text(text):
    if not text:
        return ""
    text = str(text).lower().strip()

    # Azərbaycan → latın
    az_map = {
        'ç': 'c', 'ə': 'e', 'ğ': 'g', 'ı': 'i',
        'i̇': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u'
    }
    for k, v in az_map.items():
        text = text.replace(k, v)

    # Mötərizəli vahidləri sil: (ed), (kg), (kq), (lt), (qr), (gr), (ml), (l)
    text = re.sub(r'\(\s*(?:ed|kg|kq|lt|qr|gr|ml|l)\s*\)', '', text)

    # Faiz, ölçü, xüsusi simvolları sil — bunlar matching-ə mane olur
    text = re.sub(r'\d+\s*%', '', text)        # "33%", "3.5 %" → sil
    text = re.sub(r'\d+[\.,]\d+', '', text)    # "1.5", "2,5" kimi rəqəmləri sil
    text = re.sub(r'\b\d+\b', '', text)        # tək rəqəmləri sil
    text = re.sub(r'[^\w\s]', ' ', text)       # tire, nöqtə, vergül → boşluq

    return " ".join(text.split())


def get_best_match(query_name, choices, threshold=72):
    """
    Çoxmərhələli fuzzy matching:
    1. Tam eyniləşdirmə (normalizasiya edilmiş)
    2. Token Set Ratio  — söz sırasına baxmır
    3. Token Sort Ratio — sıranı düzəldib müqayisə edir
    4. Partial Ratio    — qısaldılmış adlar üçün
    """
    if not choices:
        return None, 0

    q_norm = normalize_text(query_name)

    # MƏRHƏLƏ 1 — Tam eynilik
    for choice in choices:
        if q_norm == normalize_text(choice):
            return choice, 100

    # Seçimləri əvvəlcədən normalizasiya et (bir dəfə)
    norm_choices = {c: normalize_text(c) for c in choices}

    # MƏRHƏLƏ 2 — Token Set Ratio (söz sırası fərqinə tab gətirir)
    # "Qaymaq Petmol" ↔ "Petmol Qaymaq" → 100
    best_ts, score_ts = process.extractOne(
        q_norm,
        norm_choices,
        scorer=fuzz.token_set_ratio
    )
    # extractOne norm dict üzərindədir, orijinal key-i qaytar
    best_ts_orig = [k for k, v in norm_choices.items() if v == best_ts][0] if best_ts in norm_choices.values() else best_ts

    if score_ts >= 88:
        return best_ts_orig, score_ts

    # MƏRHƏLƏ 3 — Token Sort Ratio
    best_tsr, score_tsr = process.extractOne(
        q_norm,
        norm_choices,
        scorer=fuzz.token_sort_ratio
    )
    best_tsr_orig = [k for k, v in norm_choices.items() if v == best_tsr][0] if best_tsr in norm_choices.values() else best_tsr

    if score_tsr >= 85:
        return best_tsr_orig, score_tsr

    # MƏRHƏLƏ 4 — Partial Ratio (çekdə qısaldılmış ad: "Qaymaq" ↔ "Qaymaq Petmol 33%")
    best_pr, score_pr = process.extractOne(
        q_norm,
        norm_choices,
        scorer=fuzz.partial_ratio
    )
    best_pr_orig = [k for k, v in norm_choices.items() if v == best_pr][0] if best_pr in norm_choices.values() else best_pr

    if score_pr >= 80:
        return best_pr_orig, score_pr

    # Heç biri keçmədi — ən yaxşı token_set nəticəsini threshold ilə ver
    if score_ts >= threshold:
        return best_ts_orig, score_ts

    return None, 0


def apply_special_logic(name, qty):
    n_norm = normalize_text(name)
    for key, val in SPECIAL_RULES.items():
        if normalize_text(key) in n_norm:
            return val[0], qty * val[1], val[1]
    return name, qty, 1


def get_db(res_name, category):
    sfx = "dk" if category == "Dark Kitchen" else "horeca"
    res_clean = (
        res_name.lower()
        .replace('ı', 'i')
        .replace('i̇', 'i')
        .strip()
    )
    target = f"ana_{res_clean}_{sfx}"

    for f in os.listdir('.'):
        f_norm = f.lower().replace('ı', 'i').replace('i̇', 'i')
        if f_norm.startswith(target):
            try:
                return pd.read_excel(f) if f.endswith('.xlsx') else pd.read_csv(f)
            except Exception:
                continue
    return None


# --- 2. SIDEBAR ---

if 'selected_res' not in st.session_state:
    st.session_state.selected_res = "ROOM"

st.sidebar.title("🏢 Restoranlar")
for res in ["ROOM", "BİBLİOTEKA", "FİNESTRA"]:
    label = f"{res} ✅" if st.session_state.selected_res == res else res
    if st.sidebar.button(label, use_container_width=True):
        st.session_state.selected_res = res
        st.rerun()

curr = st.session_state.selected_res


# --- 3. ANA PANEL ---

st.markdown(f"### 📊 {curr} Paneli")

c1, c2 = st.columns(2)
cat = c1.selectbox("Analiz Sahəsi:", ["Horeca", "Dark Kitchen"])
cek_file = c2.file_uploader("Faylı seç", type=["xlsx"])

if cek_file and st.button("⚡ Analizi Başlat"):
    db_df = get_db(curr, cat)

    if db_df is None:
        st.error("❌ Baza tapılmadı! Fayl adını yoxlayın.")
        st.stop()

    df_cek = pd.read_excel(cek_file)
    df_base = db_df

    # Sütun adlarını standartlaşdır
    df_cek.columns  = [str(c).strip().lower() for c in df_cek.columns]
    df_base.columns = [str(c).strip().lower() for c in df_base.columns]

    base_ads  = df_base['ad'].tolist()
    price_col = next(
        (c for c in df_cek.columns if any(k in c for k in ['vahid', '₼', 'qiym'])),
        None
    )

    found_rows   = []   # Tapılanlar
    missing_rows = []   # Tapılmayanlar
    low_conf_rows = []  # Aşağı inamla tapılanlar (manual yoxlama üçün)

    progress = st.progress(0, text="Analiz gedir...")
    total = len(df_cek)

    for idx, (_, row) in enumerate(df_cek.iterrows()):
        try:
            nm = str(row.get('ad', '')).strip()
            mq = float(row.get('miqdar', 0))
            pr = float(row[price_col]) if price_col else 0

            if not nm or mq == 0:
                continue

            p_nm, p_mq, fct = apply_special_logic(nm, mq)
            cst = (pr / mq) / fct if mq != 0 else 0
            m_nm, score = get_best_match(p_nm, base_ads)

            if m_nm:
                real_id = df_base[df_base['ad'] == m_nm]['id'].values[0]
                found_rows.append({
                    'ID':       int(real_id),
                    'QUANTITY': p_mq,
                    'COST':     round(cst, 4)
                })
                # 72–79 aralığını aşağı inamlı kimi qeyd et
                if score < 80:
                    low_conf_rows.append({
                        "Çekdəki ad":  nm,
                        "Uyğun tapılan": m_nm,
                        "Oxşarlıq (%)": score
                    })
            else:
                missing_rows.append({"Məhsul": nm, "Status": "Bazada yoxdur"})

        except Exception:
            continue

        progress.progress((idx + 1) / total, text=f"Analiz gedir... {idx+1}/{total}")

    progress.empty()

    # --- NƏTİCƏLƏR ---

    if found_rows:
        res_df = (
            pd.DataFrame(found_rows)
            .groupby('ID')
            .agg({'QUANTITY': 'sum', 'COST': 'mean'})
            .reset_index()
        )
        st.success(f"✅ {len(res_df)} unikal məhsul hazırlandı.")
        st.dataframe(res_df, use_container_width=True)

        buf = io.BytesIO()
        res_df.to_excel(buf, index=False)
        st.download_button("📥 Faylı Endir", buf.getvalue(), "analiz.xlsx")

    # Aşağı inamlı uyğunlaşmalar — istifadəçi özü yoxlasın
    if low_conf_rows:
        with st.expander(f"⚠️ {len(low_conf_rows)} məhsul — aşağı inamlı uyğunlaşma (yoxlayın)"):
            st.dataframe(pd.DataFrame(low_conf_rows), use_container_width=True)

    # Tapılmayanlar
    if missing_rows:
        st.markdown("---")
        st.warning(f"🔍 {len(missing_rows)} məhsul bazada tapılmadı")
        st.table(pd.DataFrame(missing_rows))

    if not found_rows and not missing_rows:
        st.info("Faylda emal ediləcək sətir tapılmadı.")
