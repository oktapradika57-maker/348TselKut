import streamlit as st
import pandas as pd
import requests
import re
import difflib
import altair as alt
from datetime import datetime, date

# Konfigurasi halaman agar fullscreen, responsif, dan rapi ala slide PPT
st.set_page_config(layout="wide", page_title="Task Force 348 Dashboard")

# --- KREDENSIAL & DATA SOURCE MASTER ---
GOOGLE_SHEET_ID = "1FGKOzWoUrbf3PXN_ahgG1t-83JZT4H4sioQepePbBxM"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxCQUGt5_Jybed2AwFP4xXFru6GxuMoSwQpUZ63aK9o0WlUFnumOoseRWwgRmxZZ9XYtQ/exec"

SUPABASE_URL = "https://sfyfijndolnwqklqnpmj.supabase.co"
SUPABASE_KEY = "sb_publishable_digs5GILs-TEe4lEpPj4qQ_VRrQ7FCm"
SUPABASE_TABLE_DAPOT = "dapot_data"
SUPABASE_TABLE_INAP = "inap_data"

# --- Fungsi Standarisasi & Ekstraksi Format Site ID ---
def format_site_id(site_id):
    if pd.isna(site_id) or str(site_id).strip() == "": return "-"
    s = str(site_id).strip().upper().replace(" ", "").replace("-", "").replace("_", "")
    match = re.search(r'([A-Z]{2,4})(\d+)', s)
    if match: return f"{match.group(1)}{match.group(2).zfill(3)}"
    return re.sub(r'^K+P', 'KKP', s)

def clean_label_name(name):
    if "Log Rectifier" in name: return "Log Recty"
    return re.sub(r'\s*\(.*?\)\s*', '', str(name)).strip()

def cari_site_terdekat(site_appsheet, list_site_supabase):
    if site_appsheet == "-": return None
    cocok = difflib.get_close_matches(site_appsheet, list_site_supabase, n=1, cutoff=0.6)
    return cocok[0] if cocok else None

def konversi_link_gdrive(url_tunggal):
    if not url_tunggal or str(url_tunggal).strip() == "": return None, None, None, None
    link_inter = str(url_tunggal).strip()
    file_id = None
    if "id=" in link_inter:
        id_match = re.search(r'id=([a-zA-Z0-9_-]+)', link_inter)
        if id_match: file_id = id_match.group(1)
    elif "drive.google.com/file/d/" in link_inter:
        id_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', link_inter)
        if id_match: file_id = id_match.group(1)
            
    if file_id:
        thumb_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
        zoom_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w1600"
        dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        embed_url = f"https://drive.google.com/file/d/{file_id}/preview"
        return thumb_url, zoom_url, dl_url, embed_url
    return link_inter, link_inter, link_inter, None

def dapatkan_nilai_teknis(row, kolom_sheet, kolom_supabase):
    val_sheet = None
    if kolom_sheet in row:
        val_sheet = row.get(kolom_sheet)
    elif kolom_sheet == "Type Batteri" and "Type Battery" in row:
        val_sheet = row.get("Type Battery")
    elif kolom_sheet == "Type Batteri.1" and "Type Battery 2" in row:
        val_sheet = row.get("Type Battery 2")
    elif kolom_sheet == "Type Batteri.1" and "Type Battery.1" in row:
        val_sheet = row.get("Type Battery.1")
        
    if pd.notna(val_sheet) and str(val_sheet).strip() not in ["", "-", "nan"]:
        return str(val_sheet).strip()
    
    val_sup = row.get(f"{kolom_supabase}_dapot") if f"{kolom_supabase}_dapot" in row else row.get(kolom_supabase)
    if pd.notna(val_sup) and str(val_sup).strip() not in ["", "-", "nan"]:
        return str(val_sup).strip()
    return "-"

def update_action_finding_gsheet(site_id_asli, teks_rekomendasi, teks_finding):
    try:
        payload = {
            "site_id": str(site_id_asli).strip(), 
            "rekomendasi": str(teks_rekomendasi).strip(),
            "finding": str(teks_finding).strip()
        }
        response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=15)
        if response.status_code == 200 and "Sukses" in response.text: return True, "Sukses"
        return False, response.text
    except Exception as e: return False, str(e)

def update_tech_specs_gsheet(site_id_asli, dict_specs):
    try:
        payload = {"site_id": str(site_id_asli).strip(), "tech_specs": dict_specs}
        response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=15)
        if response.status_code == 200 and "Sukses" in response.text: return True, "Sukses"
        return False, response.text
    except Exception as e: return False, str(e)

# --- FUNGSI PULL DATA UTAMA ---
@st.cache_data(ttl=60)
def load_data_from_google_sheets():
    url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export?format=csv"
    try: return pd.read_csv(url)
    except: return pd.DataFrame()

@st.cache_data(ttl=600)
def load_data_from_supabase_dapot():
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_DAPOT}?select=*&limit=5000"
    headers = { "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}" }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200: return pd.DataFrame(response.json())
        return pd.DataFrame()
    except: return pd.DataFrame()

def fetch_inap_for_site(site_clean, site_asli):
    variants = set()
    for s in [site_clean, site_asli]:
        if pd.isna(s) or str(s).strip() in ["", "-", "nan"]: continue
        v = str(s).strip().upper()
        variants.add(v)
        variants.add(v.replace(" ", ""))
        
        match_space = re.search(r'([A-Z]{2,4})[-_ ]*(\d+)', v.replace(" ", ""))
        if match_space:
            letters = match_space.group(1)
            digits = match_space.group(2)
            padded_digits = digits.zfill(3)
            
            variants.add(f"{letters}{padded_digits}")
            variants.add(f"{letters} {padded_digits}")
            variants.add(f"{letters}-{padded_digits}")
            
            try:
                short_digits = str(int(digits))
                if short_digits != padded_digits:
                    variants.add(f"{letters}{short_digits}")
                    variants.add(f"{letters} {short_digits}")
                    variants.add(f"{letters}-{short_digits}")
            except:
                pass
                
    if not variants: return pd.DataFrame()
    
    or_filter = ",".join([f"site_id.eq.{v}" for v in variants])
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE_INAP}"
    headers = { "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}" }
    params = { "or": f"({or_filter})", "limit": 2000 }
    
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code == 200: return pd.DataFrame(res.json())
    except: pass
    return pd.DataFrame()

df_sheet = load_data_from_google_sheets()
df_sup_dapot = load_data_from_supabase_dapot()

if df_sheet.empty:
    st.error("🚨 Gagal memuat data utama dari Google Sheets! Periksa setelan file atau koneksi Anda.")
else:
    kolom_site_sheet = 'Site' if 'Site' in df_sheet.columns else ([c for c in df_sheet.columns if "site" in c.lower() or "id" in c.lower()] + [df_sheet.columns[0]])[0]
    df_sheet['site_clean_sheet'] = df_sheet[kolom_site_sheet].apply(format_site_id)
    
    if not df_sup_dapot.empty:
        df_sup_dapot['site_clean_sup'] = df_sup_dapot['site_id'].apply(format_site_id)
        list_site_sup = df_sup_dapot['site_clean_sup'].dropna().unique().tolist()
        mapping_fuzzy = {site_s: (site_s if site_s in list_site_sup else cari_site_terdekat(site_s, list_site_sup)) for site_s in df_sheet['site_clean_sheet'].unique()}
        df_sheet['matched_site_sup'] = df_sheet['site_clean_sheet'].map(mapping_fuzzy)
        df_merged = pd.merge(df_sheet, df_sup_dapot, left_on='matched_site_sup', right_on='site_clean_sup', how='left', suffixes=('', '_dapot'))
    else:
        df_merged = df_sheet.copy()
        df_merged['matched_site_sup'] = None

    def susun_nama_dropdown(row):
        s_id = row['site_clean_sheet'] if pd.isna(row.get('matched_site_sup')) or not row['matched_site_sup'] else row['matched_site_sup']
        s_name = row.get('site_name') if pd.notna(row.get('site_name')) else None
        if not s_name and kolom_site_sheet in row:
            s_name = row[kolom_site_sheet]
        return f"[{s_id}] ➔ {s_name if pd.notna(s_name) else 'Belum Terdata di Supabase'}"
        
    df_merged['dropdown_label'] = df_merged.apply(susun_nama_dropdown, axis=1)

    # --- CSS CUSTOM ---
    st.markdown("""<style>
    .block-container { padding-top: 3.2rem !important; padding-bottom: 1rem !important; }
    .ppt-card-blue { background-color: #1e3d59; color: white; padding: 12px; border-radius: 6px; margin-bottom: 10px; border-left: 5px solid #ffc13b; }
    .ppt-card-gold { background-color: #ffc13b; color: #1e3d59; padding: 12px; border-radius: 6px; margin-bottom: 10px; border-left: 5px solid #1e3d59; }
    .gallery-container { display: flex; overflow-x: auto; padding: 10px; background-color: #111; border-radius: 8px; border: 1px solid #333; }
    .photo-card { flex: 0 0 auto; width: 110px; margin-right: 12px; text-align: center; position: relative; cursor: pointer; }
    .hide-checkbox { display: none; }
    .hide-checkbox:checked + .photo-card { display: none; }
    .exclude-btn { position: absolute; top: 1px; right: 8px; background: rgba(211,47,47,0.9); color: white; border-radius: 50%; width: 16px; height: 16px; font-size: 10px; line-height: 16px; cursor: pointer; font-weight: bold; z-index: 10; }
    .lightbox { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 9999999; justify-content: center; align-items: center; }
    .lightbox:target { display: flex; }
    .lightbox img, .lightbox iframe { max-width: 80%; max-height: 80%; border-radius: 6px; box-shadow: 0px 5px 25px rgba(0,0,0,0.5); }
    .lightbox .close-lightbox { position: absolute; top: 20px; right: 40px; color: #fff; font-size: 40px; text-decoration: none; font-weight: bold; z-index: 99999999; text-shadow: 0px 2px 5px #000; }
    .lightbox .nav-arrow { position: absolute; top: 50%; color: #fff; font-size: 50px; font-weight: bold; text-decoration: none; transform: translateY(-50%); padding: 20px; z-index: 99999999; text-shadow: 0px 2px 8px #000; }
    .lightbox .prev-arrow { left: 40px; } .lightbox .next-arrow { right: 40px; }
    .lightbox .caption-text { position: absolute; bottom: 30px; color: #ffc13b; font-size: 18px; font-weight: bold; text-align: center; width: 100%; text-shadow: 0px 2px 4px rgba(0,0,0,0.8); z-index: 99999999; font-family: sans-serif; letter-spacing: 0.5px; }
    .video-overlay-btn { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(211, 47, 47, 0.85); color: white; border-radius: 50%; width: 26px; height: 24px; line-height: 24px; font-size: 11px; font-weight: bold; pointer-events: none; box-shadow: 0px 2px 5px rgba(0,0,0,0.5); }
    
    .btn-download-media { display: block; background-color: #2e7d32; color: #ffffff !important; font-size: 9px; font-weight: bold; padding: 4px 2px; margin-top: 5px; border-radius: 3px; text-decoration: none !important; border: 1px solid #1b5e20; text-align: center; }
    .btn-download-media:hover { background-color: #4caf50; }
    
    div[data-testid="stMetric"] { background-color: #262730; padding: 5px 10px; border-radius: 4px; border: 1px solid #444; }
    .findings-grid { display: grid; grid-template-columns: auto auto; gap: 8px 15px; background-color: #262730; padding: 12px; border-radius: 6px; font-size: 13px; margin-bottom: 10px; border: 1px solid #444; }
    .f-item { display: flex; justify-content: space-between; border-bottom: 1px solid #333; padding-bottom: 4px; }
    .custom-footer { text-align: center; font-size: 12px; color: #888; margin-top: 30px; border-top: 1px solid #333; padding-top: 10px; }
    </style>""", unsafe_allow_html=True)

    # --- FITUR TAMBAHAN: PROSES & FILTER TIMESTAMP ---
    if 'Timestamp' in df_merged.columns:
        # Konversi kolom Timestamp ke format DateTime yang aman
        df_merged['parsed_timestamp'] = pd.to_datetime(df_merged['Timestamp'], errors='coerce')
        # Buat kolom pembantu bertipe Date saja (tanpa Jam) untuk komparasi filter kalender
        df_merged['date_only'] = df_merged['parsed_timestamp'].dt.date
        
        # Cari tanggal terkecil dan terbesar yang ada di data asli sebagai default range
        valid_dates = df_merged['date_only'].dropna()
        min_date_val = valid_dates.min() if not valid_dates.empty else date(2025, 1, 1)
        max_date_val = valid_dates.max() if not valid_dates.empty else date.today()
    else:
        df_merged['date_only'] = date.today()
        min_date_val = date(2025, 1, 1)
        max_date_val = date.today()

    # --- ROW 1: HEADER & FILTERS ---
    # Memisahkan Header menjadi 3 kolom: Judul Dashboard, Filter Rentang Waktu, & Dropdown Site Target
    col_head_title, col_head_date, col_head_select = st.columns([1.5, 0.6, 0.9])
    
    with col_head_title:
        st.markdown("""<div style='background: linear-gradient(135deg, #ed1c24 0%, #b71c1c 50%, #1a1a1a 100%); padding: 12px 20px; border-radius: 6px; color: white; border-left: 6px solid #ffc13b; box-shadow: 0 4px 6px rgba(0,0,0,0.3);'><h3 style='margin:0; font-size:22px; font-weight:900; letter-spacing: 0.5px;'>🚀 TASK FORCE 348 <span style='color: #ffc13b;'>|</span> NOP PALANGKARAYA</h3><p style='margin: 2px 0 0 0; font-size: 12px; opacity: 0.9; font-weight: 500;'>TELECOMMUNICATION & NETWORK OPERATION DASHBOARD</p></div>""", unsafe_allow_html=True)
    
    with col_head_date:
        # Menambahkan widget filter Rentang Waktu (Calendar)
        rentang_waktu = st.date_input(
            "📅 Filter Tanggal Data:",
            value=(min_date_val, max_date_val),
            min_value=date(2024, 1, 1),
            max_value=date(2030, 12, 31),
            key="filter_timestamp_range"
        )
        
    # Memfilter data secara dinamis berdasarkan input range tanggal yang dipilih user
    if isinstance(rentang_waktu, tuple) and len(rentang_waktu) == 2:
        start_date, end_date = rentang_waktu
        df_filtered_view = df_merged[(df_merged['date_only'] >= start_date) & (df_merged['date_only'] <= end_date)]
    else:
        # Jika user baru mengeklik satu tanggal, pakai default seluruh data terlebih dahulu
        df_filtered_view = df_merged

    with col_head_select:
        # Menampilkan Dropdown Site Target yang sudah terfilter rentang waktunya saja
        if not df_filtered_view.empty:
            list_dropdown_pilihan = sorted(df_filtered_view['dropdown_label'].unique())
            label_pilihan = st.selectbox("🎯 Target Monitoring:", list_dropdown_pilihan, label_visibility="visible")
            data_site = df_filtered_view[df_filtered_view['dropdown_label'] == label_pilihan].iloc[0]
        else:
            st.warning("⚠️ Tidak ada data pada tanggal tersebut!")
            st.stop()

    st.markdown(f"<p style='text-align: right; margin: -10px 5px 8px 0; font-size: 13px;'><b>Last Data Timestamp:</b> {data_site.get('Timestamp', '-')}</p>", unsafe_allow_html=True)

    t_id_asli = str(data_site.get(kolom_site_sheet, '')).strip()
    t_id_clean = str(data_site.get('site_clean_sheet', '')).strip()

    # --- ROW 2: MAIN GRID (4 COLUMNS) ---
    c1, c2, c3, c4 = st.columns([1, 1.2, 1.2, 1])

    with c1:
        st.markdown("<div class='ppt-card-blue'><b style='font-size:14px;'>📋 Site Master Specification</b></div>", unsafe_allow_html=True)
        master_list = {
            "Parameter": ["Site ID", "Site Name", "Class", "Grid", "Hub", "Phase", "Grounding KWH"],
            "Value": [
                data_site.get(kolom_site_sheet, '-'), data_site.get('site_name', '-'),
                data_site.get('site_class', '-'), data_site.get('grid_category_new', '-'),
                data_site.get('hub_site', '-'), data_site.get('Phase PLN', '-'),
                data_site.get('Grounding KWH', '-')
            ]
        }
        st.dataframe(pd.DataFrame(master_list), hide_index=True, use_container_width=True, height=280)

    with c2:
        st.markdown("<div class='ppt-card-blue'><b style='font-size:14px;'>⚙️ Site Technical Detailed Specs</b></div>", unsafe_allow_html=True)
        tech_mapping = [
            ("Main Power", "Main Power", "Power Type"), 
            ("Daya PLN", "Daya PLN", "Capacity"), 
            ("Kapasitas MCB", "Kapasitas MCB", "Kapasitas MCB"),
            ("Tegangan R - N", "Tegangan PLN (R-N)", "Tegangan PLN (R-N)"), 
            ("Tegangan S - N", "Tegangan PLN (S-N)", "Tegangan PLN (S-N)"), 
            ("Tegangan T - N", "Tegangan PLN (T-N)", "Tegangan PLN (T-N)"),
            ("Arus R", "Beban PLN (R)", "Beban PLN (R)"), 
            ("Arus S", "Beban PLN (S)", "Beban PLN (S)"), 
            ("Arus T", "Beban PLN (T)", "Beban PLN (T)"),
            ("Type recti 1", "Type Rectifier", "Type Rectifier"), 
            ("Jumlah Module 1", "Jumlah Module", "Jumlah Module"), 
            ("Type batt 1", "Type Batteri", "Type Battery"),        
            ("Jumlah batt 1", "Jumlah Battery", "Jumlah Battery"), 
            ("DC Voltage 1", "DC Voltage", "DC Voltage"), 
            ("Load Current 1", "Rectifier Current", "Rectifier Current"),
            ("Type recti 2", "Type Rectifier 2", "Type Rectifier 2"), 
            ("Jumlah Module 2", "Jumlah Module 2", "Jumlah Module 2"), 
            ("Type batt 2", "Type Batteri.1", "Type Battery 2"),    
            ("Jumlah batt 2", "Jumlah Battery 2", "Jumlah Battery 2"), 
            ("Load current recti 2", "Load current recti 2", "Load current recti 2")
        ]
        tech_rows = [{"Detail Parameter": l, "Value": dapatkan_nilai_teknis(data_site, cs, csb)} for l, cs, csb in tech_mapping]
        
        df_editable = pd.DataFrame(tech_rows)
        edited_df = st.data_editor(
            df_editable, 
            hide_index=True, 
            use_container_width=True, 
            disabled=["Detail Parameter"], 
            key=f"tech_editor_{t_id_clean}",
            height=750
        )
        
        if st.button("💾 Push Spek Teknis", use_container_width=True):
            payload_specs = {}
            for index, row in edited_df.iterrows():
                lbl = row["Detail Parameter"]
                val = row["Value"]
                real_col_gsheet = next((m[1] for m in tech_mapping if m[0] == lbl), None)
                if real_col_gsheet:
                    clean_col_name = real_col_gsheet.replace(".1", "")
                    payload_specs[clean_col_name] = val
            
            with st.spinner("Pushing to GSheet..."):
                status_ok, return_msg = update_tech_specs_gsheet(data_site[kolom_site_sheet], payload_specs)
                if status_ok:
                    st.success("Spek Teknis Berhasil Di-update!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Gagal Pushing: {return_msg}")

    with c3:
        st.markdown("<div class='ppt-card-gold'><b style='font-size:14px;'>🔍 Field Findings</b></div>", unsafe_allow_html=True)
        st.markdown(f"""<div class='findings-grid'><div class='f-item'><b>Arus Recty:</b> <span>{data_site.get('Rectifier Current', '-')} A</span></div><div class='f-item'><b>Modul:</b> <span>{data_site.get('Jumlah Module', '-')} <span style='color:#ff5252;'>(F: {data_site.get('Total Module faulty', '-')})</span></span></div><div class='f-item'><b>BBT:</b> <span>{data_site.get('BBT >4 Jam', '-')}</span></div><div class='f-item'><b>Enva Val:</b> <span>{data_site.get('Enva Validasi', '-')}</span></div><div class='f-item'><b>LPU Enva:</b> <span>{data_site.get('Kondisi Modul Enva LPU', '-')}</span></div><div class='f-item'><b>Arrester:</b> <span>{data_site.get('Arrester Rectifier', '-')}</span></div></div>""", unsafe_allow_html=True)
        
        st.markdown("<b style='font-size:11px; color:#aaa;'>📈 Daily Availability Trend</b>", unsafe_allow_html=True)
        
        df_trend = fetch_inap_for_site(t_id_clean, t_id_asli)
            
        if not df_trend.empty:
            col_date = next((c for c in df_trend.columns if any(k == str(c).lower().strip() for k in ['period', 'periode'])), None)
            if not col_date:
                col_date = next((c for c in df_trend.columns if any(k in str(c).lower() for k in ['date', 'waktu', 'tgl', 'tanggal', 'time', 'timestamp'])), None)
            
            col_avail = None
            for c in df_trend.columns:
                c_lower = str(c).lower().strip()
                if 'avail' in c_lower and 'power' not in c_lower and 'pwr' not in c_lower and 'trans' not in c_lower:
                    col_avail = c
                    break
            if not col_avail:
                col_avail = next((c for c in df_trend.columns if 'avail' in str(c).lower()), None)

            if col_date and col_avail:
                chart_data = df_trend[[col_date, col_avail]].copy()
                chart_data[col_date] = pd.to_datetime(chart_data[col_date], errors='coerce')
                chart_data = chart_data.dropna(subset=[col_date])
                
                batas_wajar = pd.Timestamp.now() + pd.Timedelta(days=7)
                chart_data = chart_data[(chart_data[col_date].dt.year > 2000) & (chart_data[col_date] <= batas_wajar)]
                chart_data[col_avail] = chart_data[col_avail].astype(str).str.replace('%', '').str.replace(',', '.')
                chart_data[col_avail] = pd.to_numeric(chart_data[col_avail], errors='coerce')
                chart_data = chart_data.dropna(subset=[col_avail])
                
                if not chart_data.empty:
                    chart_data = chart_data.sort_values(by=col_date)
                    site_class = str(data_site.get('site_class', '')).upper().strip()
                    if 'DIAMOND' in site_class: target_val = 99.6
                    elif 'PLATINUM' in site_class: target_val = 99.2
                    elif 'GOLD' in site_class: target_val = 99.0
                    elif 'SILVER' in site_class: target_val = 97.0
                    elif 'BRONZE' in site_class: target_val = 95.0
                    else: target_val = 95.0
                    
                    chart_data['Target'] = target_val
                    df_altair = chart_data.reset_index(drop=True)
                    
                    min_date = df_altair[col_date].min().isoformat()
                    max_date = df_altair[col_date].max().isoformat()
                    
                    base = alt.Chart(df_altair).encode(
                        x=alt.X(f'{col_date}:T', 
                                scale=alt.Scale(domain=(min_date, max_date)),
                                axis=alt.Axis(format='%d %b %Y', labelOverlap=True, title=None))
                    )
                    line_avail = base.mark_line(color='#00E5FF', strokeWidth=2, interpolate='monotone').encode(
                        y=alt.Y(f'{col_avail}:Q', scale=alt.Scale(zero=False), title='Availability (%)'),
                        tooltip=[
                            alt.Tooltip(f'{col_date}:T', title='Tanggal', format='%d %b %Y'),
                            alt.Tooltip(f'{col_avail}:Q', title='Availability (%)', format='.2f')
                        ]
                    )
                    line_target = base.mark_line(color='#ff5252', strokeDash=[4, 4], opacity=0.6, strokeWidth=1.5).encode(
                        y=alt.Y('Target:Q')
                    )
                    st.altair_chart(alt.layer(line_avail, line_target).properties(height=260), use_container_width=True)
                else:
                    st.caption("ℹ️ Data ketersediaan site ini kosong atau format angka tidak valid.")
            else:
                st.caption(f"ℹ️ Format kolom tanggal atau availability tidak ditemukan.")
        else: 
            st.caption(f"ℹ️ Belum ada data harian untuk site ini di tabel inap_data.")

    # KOLOM 4: FINDINGS & ACTION PLAN
    with c4:
        st.markdown("<div class='ppt-card-gold'><b style='font-size:14px;'>📝 Findings & Action Plan</b></div>", unsafe_allow_html=True)
        
        kolom_finding = next((c for c in df_sheet.columns if "hasil" in str(c).lower() and "analis" in str(c).lower()), 'Hasil Analisa')
        finding_val = data_site.get(kolom_finding, '')
        if pd.isna(finding_val): finding_val = ""
        st_finding_input = st.text_area(
            "🔍 Hasil Analisa:", 
            value=str(finding_val), 
            placeholder="Tulis Final Finding di baris pertama...\n\n1. Detail Kondisi...", 
            key=f"input_finding_{t_id_clean}", 
            height=180
        )
        
        kolom_reko = next((c for c in df_sheet.columns if "rekomendasi" in str(c).lower()), 'Rekomendasi Perbaikan')
        reko_val = data_site.get(kolom_reko, '')
        if pd.isna(reko_val): reko_val = ""
        st_rekomendasi_input = st.text_area(
            "📝 Rekomendasi Perbaikan:", 
            value=str(reko_val), 
            placeholder="Input rekomendasi...", 
            key=f"input_reko_{t_id_clean}", 
            height=180
        )
        
        @st.dialog("Konfirmasi Update")
        def popup_konfirmasi(teks_find, teks_reko):
            st.write(f"Simpan update data untuk site **{data_site[kolom_site_sheet]}**?")
            st.info(f"**🔍 Hasil Analisa:**\n{teks_find}\n\n**📝 Rekomendasi:**\n{teks_reko}")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("👍 Ya, Simpan", use_container_width=True):
                    with st.spinner("Saving..."):
                        s, p = update_action_finding_gsheet(data_site[kolom_site_sheet], teks_reko, teks_find)
                        if s: 
                            st.success("Tersimpan!")
                            st.cache_data.clear()
                            st.rerun()
                        else: st.error(f"Gagal: {p}")
            with b2:
                if st.button("❌ Batal", use_container_width=True): st.rerun()

        if st.button("💾 Push Update Data", use_container_width=True):
            popup_konfirmasi(st_finding_input, st_rekomendasi_input)

    # --- ROW 3: EVIDENCE SECURE & CAPTION POPUP ---
    st.markdown("<div style='margin-top:10px; font-size:14px;'><b>📁 Evidence & Dokumentasi Slide</b></div>", unsafe_allow_html=True)
    all_photos, all_csvs, seen_urls = [], [], set()
    
    for col_name in df_sheet.columns:
        val = data_site.get(col_name)
        if pd.isna(val) or not val: continue
        urls = re.findall(r'(https?://[^\s,"\'\}]+)', str(val))
        for idx, url in enumerate(urls):
            if url in seen_urls: continue
            seen_urls.add(url)
            
            is_csv = "csv" in col_name.lower() or ".csv" in url.lower() or "data" in col_name.lower() or ".xlsx" in url.lower()
            is_video = "voltage" in col_name.lower() or "backup" in col_name.lower() or ".mp4" in url.lower() or ".mov" in url.lower()
            
            thumb_url, zoom_url, dl_url, embed_url = konversi_link_gdrive(url)
            label = f"{clean_label_name(col_name)} #{idx+1}" if len(urls) > 1 else clean_label_name(col_name)
            
            if thumb_url and not is_csv:
                all_photos.append({'label': label, 'col': col_name, 'idx': idx, 'thumb': thumb_url, 'zoom': zoom_url, 'is_vid': is_video, 'embed': embed_url, 'dl_url': dl_url})
            elif is_csv: 
                all_csvs.append({'label': label, 'url': dl_url if dl_url else url})

    b_csv, b_gal = st.columns([0.8, 2.2])
    with b_csv:
        if all_csvs:
            for f in all_csvs: st.link_button(f"📥 {f['label']}", f['url'], use_container_width=True)
        else: st.caption("No CSV/Excel Files uploaded.")
        
    with b_gal:
        html_str = ""
        total = len(all_photos)
        for i, p in enumerate(all_photos):
            sid = re.sub(r'[^a-zA-Z0-9]', '', f"{p['col']}{p['idx']}")
            sid_p = re.sub(r'[^a-zA-Z0-9]', '', f"{all_photos[(i-1)%total]['col']}{all_photos[(i-1)%total]['idx']}")
            sid_n = re.sub(r'[^a-zA-Z0-9]', '', f"{all_photos[(i+1)%total]['col']}{all_photos[(i+1)%total]['idx']}")
            nav = f'<a href="#lightbox-{sid_p}" class="nav-arrow prev-arrow">❮</a><a href="#lightbox-{sid_n}" class="nav-arrow next-arrow">❯</a>'
            
            content = f'<iframe src="{p["embed"]}" width="80%" height="80%" style="border:none; background:#000; border-radius:8px;" allow="autoplay"></iframe>' if p['is_vid'] else f'<img src="{p["zoom"]}">'
            ovr = '<div class="video-overlay-btn">▶</div>' if p['is_vid'] else ''
            
            html_str += f'<input type="checkbox" id="hide-{sid}" class="hide-checkbox"><div class="photo-card"><label for="hide-{sid}" class="exclude-btn" title="Hide">&times;</label><a href="#lightbox-{sid}"><div style="position:relative;"><img src="{p["thumb"]}" style="width:100px; height:75px; object-fit:cover; border:1px solid #555; border-radius:4px;"/><div class="video-overlay-btn">{ovr}</div></div></a><div style="font-size:10px; margin-top:4px; color:#ccc; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="{p["label"]}">{p["label"]}</div><a href="{p["dl_url"]}" target="_blank" class="btn-download-media" download>📥 Download</a></div><div id="lightbox-{sid}" class="lightbox"><a href="#" class="close-lightbox">&times;</a>{nav}{content}<div class="caption-text">{p["label"]}</div></div>'
            
        if html_str: st.markdown(f'<div class="gallery-container">{html_str}</div>', unsafe_allow_html=True)
        else: st.caption("No unique documentation photos found.")

    st.markdown("<div class='custom-footer'>© 2026 | Created with ❤️ by Fauzi Ramdani - 97122</div>", unsafe_allow_html=True)
