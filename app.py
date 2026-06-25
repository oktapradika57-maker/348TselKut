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
    link_bersih = str(url_tunggal).strip()
    file_id = None
    if "id=" in link_bersih:
        id_match = re.search(r'id=([a-zA-Z0-9_-]+)', link_bersih)
        if id_match: file_id = id_match.group(1)
    elif "drive.google.com/file/d/" in link_bersih:
        id_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', link_bersih)
        if id_match: file_id = id_match.group(1)
            
    if file_id:
        thumb_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
        zoom_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w1600"
        dl_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        embed_url = f"https://drive.google.com/file/d/{file_id}/preview"
        return thumb_url, zoom_url, dl_url, embed_url
    return link_bersih, link_bersih, link_bersih, None

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

# --- LOAD & MERGE PROCESS ---
df_sheet = load_data_from_google_sheets()
df_sup_dapot = load_data_from_supabase_dapot()

if df_sheet.empty:
    st.error("🚨 Gagal memuat data utama dari Google Sheets! Periksa koneksi atau ID spreadsheet.")
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
    .custom-footer { text-align: center; font-size: 12px; color: #888; margin-top:
