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
    # Azərbaycan şrifti və simvol təmizliyi
    rep = {'ç':'c','ə':'e','ğ':'g','ı':'i','i̇':'i','ö':'o','ş':'s','ü':'u'}
    for k, v in rep.items():
        text = text.replace(k, v)
    # (ed), (kg) kimi maneələri silirik
    text = re.sub(r'\(ed\)|\(kg\)|\(kq\)|\(lt\)|\(qr\)|\(gr\)', '', text)
    return " ".join(text.split())

def get_best_match(query_name, choices, threshold=60): # Threshold-u 60-a endirdik
    if not choices: return None, 0
    q_norm = normalize_text(query_name)
    
    # 1. Tam eynidirsə dərhal qaytar
    for choice in choices:
        if q_norm == normalize_text(choice):
            return choice, 100
            
    # 2. Fuzzy match - daha dərindən axtarış
    # token_set_ratio sözlərin sırasına baxmır, bu bizə lazımdır
    best_match, score = process.extractOne(query_name, choices, scorer=fuzz.token_set_ratio)
    
    return (best_match, score) if score >= threshold else (None, 0)

def apply_special_logic(name, qty):
    n_norm = normalize_text(name)
    for key, val in SPECIAL_RULES.items():
        if normalize_text(key) in n_norm:
            return val[0], qty * val[1], val[1]
    return name, qty, 1

def get_best_match(query_name, choices, threshold=85):
    if not choices: return None, 0
    
    # 1. MƏRHƏLƏ: Tam eyniləşdirmə (Normalizasiya olunmuş formada)
    q_norm = normalize_text(query_name)
    for choice in choices:
        if q_norm == normalize_text(choice):
            return choice, 100
            
    # 2. MƏRHƏLƏ: Söz-söz yoxlama (Token Set Ratio)
    # Bu, "Qaymaq Petmol" ilə "Petmol Qaymaq" arasındakı fərqi yox edir.
    best_match, score = process.extractOne(query_name, choices, scorer=fuzz.token_set_ratio)
    
    # 3. MƏRHƏLƏ: Əgər hesab 80-dən yuxarıdırsa, deməli demək olar ki, eynidir
    if score >= 80:
        return best_match, score
    
    # 4. MƏRHƏLƏ: Daha riskli, amma lazımlı axtarış (Partial Ratio)
    # Məsələn, çekdə "Qaymaq" yazılıb, bazada "Qaymaq Petmol 33%". 
    # Partial ratio bunu tuta bilir.
    p_match, p_score = process.extractOne(query_name, choices, scorer=fuzz.partial_ratio)
    
    if p_score > 85: # Qısaldılmış adlar üçün yüksək limit
        return p_match, p_score
        
    return (best_match, score) if score >= threshold else (None, 0)

def get_db(res_name, category):
    import os
    # Sahəni seçirik
    sfx = "dk" if category == "Dark Kitchen" else "horeca"
    
    # Hər şeyi (həm restoran adını, həm fayl adını) tam təmizləyirik
    res_clean = res_name.lower().replace('ı', 'i').replace('i̇', 'i').strip()
    target = f"ana_{res_clean}_{sfx}"
    
    for f in os.listdir('.'):
        # Faylın adındakı bütün gizli nöqtəli İ-ləri və s. təmizləyib yoxlayırıq
        f_norm = f.lower().replace('ı', 'i').replace('i̇', 'i')
        if f_norm.startswith(target):
            try:
                # Excel-dirsə belə oxu
                return pd.read_excel(f) if f.endswith('.xlsx') else pd.read_csv(f)
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

# --- 1. SAHƏ: GİRİŞ VƏ FAYL YÜKLƏMƏ ---
st.markdown(f"### 📊 {curr} Paneli")

c1, c2 = st.columns(2)
cat = c1.selectbox("Analiz Sahəsi:", ["Horeca", "Dark Kitchen"])
cek_file = c2.file_uploader("Faylı seç", type=["xlsx"])

# DÜYMƏNİ BURADAN BAŞLA
if cek_file and st.button("⚡ Analizi Başlat"):
    db_file = get_db(curr, cat)
    if db_file is not None:
        # 1. Faylları oxu
        df_cek = pd.read_excel(cek_file)
        df_base = db_file # get_db-dən gələn df
        
        # Sütunları standartlaşdır
        df_cek.columns = [str(c).strip().lower() for c in df_cek.columns]
        df_base.columns = [str(c).strip().lower() for c in df_base.columns]
        
        f_data = [] # Tapılanlar
        m_data = [] # Tapılmayanlar
        
        base_ads = df_base['ad'].tolist()
        price_col = next((c for c in df_cek.columns if any(k in c for k in ['vahid', '₼', 'qiym'])), None)

        # 2. Döngünü başlat
        for _, row in df_cek.iterrows():
            try:
                nm = str(row.get('ad', '')).strip()
                mq = float(row.get('miqdar', 0))
                pr = float(row[price_col]) if price_col else 0
                if not nm or mq == 0: continue

                # Sənin o əsas funksiyaların
                p_nm, p_mq, fct = apply_special_logic(nm, mq)
                cst = (pr / mq) / fct if mq != 0 else 0
                m_nm, _ = get_best_match(p_nm, base_ads)
                
                if m_nm:
                    # ID-ni ana bazadan çəkirik
                    real_id = df_base[df_base['ad'] == m_nm]['id'].values[0]
                    f_data.append({'ID': int(real_id), 'QUANTITY': p_mq, 'COST': round(cst, 4)})
                else:
                    # Tapılmayanları siyahıya yığırıq
                    m_data.append({"Məhsul": nm, "Status": "Bazada yoxdur"})
            except:
                continue

        # 3. Nəticəni dərhal ekrana ver
        if f_data:
            res_df = pd.DataFrame(f_data).groupby('ID').agg({'QUANTITY':'sum', 'COST':'mean'}).reset_index()
            st.success(f"✅ {len(res_df)} məhsul hazırlandı.")
            st.dataframe(res_df)
            
            # Excel düyməsi
            buf = io.BytesIO()
            res_df.to_excel(buf, index=False)
            st.download_button("📥 Faylı Endir", buf.getvalue(), "analiz.xlsx")
        
        if m_data:
            st.markdown("---")
            st.warning("🔍 Kontrol: Aşağıdakılar bazada tapılmadı")
            st.table(pd.DataFrame(m_data))
    else:
        st.error("Baza tapılmadı!")
