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
    
    if
