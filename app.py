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

# --- 1. YADDAŞI HAZIRLAYIRIQ (Faylın yuxarısında, tabs-dan əvvəl də ola bilər) ---
if 'missing_items' not in st.session_state:
    st.session_state.missing_items = []

# --- 2. TABLARIN YARADILMASI ---
tab1, tab2 = st.tabs(["📊 Analiz", "🔍 Kontrol"])

with tab1:
    col1, col2 = st.columns(2)
    cat = col1.selectbox("Analiz Sahəsi:", ["Horeca", "Dark Kitchen"])
    cek_file = col2.file_uploader("Sklad Çekini Yüklə", type=["xlsx"])

    if cek_file and st.button("⚡ Analizi Başlat"):
        # 1. Yaddaşı sıfırla
        st.session_state.missing_items = []
        
        df_base = get_db(curr, cat)
        if df_base is not None:
            df_cek = pd.read_excel(cek_file)
            
            # Sütunları normallaşdır
            df_cek.columns = [str(c).strip().lower() for c in df_cek.columns]
            df_base.columns = [str(c).strip().lower() for c in df_base.columns]
            
            final_data = []
            base_ads = df_base['ad'].tolist()
            
            # Qiymət sütununu (1 Vahid, ₼) tapmaq
            price_col = next((c for c in df_cek.columns if any(k in c for k in ['vahid', '₼', 'qiym'])), None)

            # --- ANALİZ DÖNGÜSÜ ---
            for _, row in df_cek.iterrows():
                try:
                    raw_name = str(row.get('ad', '')).strip()
                    raw_qty = float(row.get('miqdar', 0))
                    
                    if not raw_name or raw_name == 'nan' or raw_qty == 0:
                        continue
                    
                    # 2. Riyazi qaydalar və təmizləmə
                    p_name, p_qty, fct = apply_special_logic(raw_name, raw_qty)
                    
                    # 3. Qiyməti hesabla
                    price_val = float(row[price_col]) if price_col else 0
                    cost_val = (price_val / raw_qty) / fct if raw_qty != 0 else 0
                    
                    # 4. BAZADA AXTAR (AD ÜZƏRİNDƏN)
                    m_name, score = get_best_match(p_name, base_ads, threshold=60)
                    
                    if m_name:
                        # Tapıldısa: Ana bazadan ID-ni götür
                        real_id = df_base[df_base['ad'] == m_name]['id'].values[0]
                        final_data.append({
                            'ID': int(real_id), 
                            'QUANTITY': p_qty, 
                            'COST': round(cost_val, 4)
                        })
                    else:
                        # Tapılmadısa: Kontrol siyahısına at
                        st.session_state.missing_items.append({
                            "Çekdəki Ad": raw_name,
                            "Təmizlənmiş Ad": p_name,
                            "Ehtimal": "Bazada tapılmadı"
                        })
                except Exception as e:
                    continue

            # --- NƏTİCƏNİ ÇIXAR ---
            if final_data:
                res_df = pd.DataFrame(final_data).groupby('ID').agg({'QUANTITY':'sum', 'COST':'mean'}).reset_index()
                st.success(f"Analiz tamamlandı! {len(res_df)} məhsul eyniləşdi.")
                st.dataframe(res_df, use_container_width=True)
                
                buf = io.BytesIO()
                res_df.to_excel(buf, index=False)
                st.download_button("📥 Faylı (.xlsx) Endir", buf.getvalue(), f"{curr}_Analiz.xlsx")
            else:
                st.error("Eyniləşmə alınmadı. Kontrol bölməsinə baxın.")
        else:
            st.error("Baza tapılmadı!")

with tab2:
    st.markdown("#### 🔍 Kontrol Paneli")
    st.info("Bu hissə Analizdən asılı deyil. Sklad çeki ilə Ana Bazanı (Ad üzərindən) müqayisə edir.")
    
    # Müqayisə düyməsi
    if st.button("🔎 Tapılmayanları Göstər"):
        # Analiz hissəsində yüklənmiş cek_file-dan istifadə edirik
        if cek_file is not None:
            df_s = pd.read_excel(cek_file)
            db = get_db(curr, cat)
            
            if db is not None:
                # Sütunları standartlaşdırırıq
                df_s.columns = [str(c).strip().lower() for c in df_s.columns]
                db.columns = [str(c).strip().lower() for c in db.columns]
                
                db_adlar = db['ad'].tolist()
                tapilmayanlar = []

                for _, row in df_s.iterrows():
                    ad_cek = str(row.get('ad', '')).strip()
                    if not ad_cek or ad_cek == 'nan': continue
                    
                    # Analiz hissəsindəki eyni axtarış məntiqi
                    p_name, _, _ = apply_special_logic(ad_cek, 1)
                    m_name, score = get_best_match(p_name, db_adlar)
                    
                    # Əgər bot tapmayıbsa (score < threshold)
                    if not m_name:
                        tapilmayanlar.append({
                            "Çekdəki Orijinal Ad": ad_cek,
                            "Botun Təmizlədiyi": p_name,
                            "Status": "Bazada bu ada bənzər mal tapılmadı"
                        })
                
                if tapilmayanlar:
                    st.warning(f"⚠️ Cəmi {len(tapilmayanlar)} məhsul bazada tapılmadı:")
                    st.table(pd.DataFrame(tapilmayanlar))
                else:
                    st.success("✅ Əla! Çekdəki bütün adlar bazada tapıldı.")
            else:
                st.error("Ana baza faylı tapılmadı.")
        else:
            st.warning("Zəhmət olmasa əvvəlcə Analiz hissəsində çek faylını yükləyin.")
