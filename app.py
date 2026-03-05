import streamlit as st
from datetime import date
from io import BytesIO
from statistics import mean
import pandas as pd
import requests
import uuid
import urllib.parse

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# =========================
# Identité
# =========================
AGENCE = "LA PRIORITE IMMOBILIERE"
EMAIL = "sbelhmira@gmail.com"

# =========================
# Open Data Wallonie-Bruxelles (ODWB / WalStat)
# Dataset: 234002 (prix immobilier résidentiel - médiane + quartiles)
# =========================
ODWB_DATASET_ID = "234002"
ODWB_EXPORT_CSV_URL = (
    f"https://www.odwb.be/api/explore/v2.1/catalog/datasets/{ODWB_DATASET_ID}/exports/csv"
    f"?limit=-1&delimiter=%3B"
)

# Dataset codes postaux (ODWB - selon disponibilité)
POSTAL_DATASET = "postal-codes-belgium"

# =========================
# Helpers
# =========================
def euro(x: float) -> str:
    try:
        x = float(x)
    except Exception:
        x = 0.0
    s = f"{x:,.0f}".replace(",", " ")
    return f"{s} €"

def safe_text(x: str, max_len: int = 140) -> str:
    return (x or "").strip()[:max_len]

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def today_iso() -> str:
    return date.today().isoformat()

def parse_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

def parse_int(x, default=0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default

# =========================
# Paramètres (modifiable)
# =========================
DEFAULT_PARAMS = {
    # Terrain €/m² auto (bases par province)
    "terrain_Hainaut": 60,
    "terrain_Namur": 90,
    "terrain_Liege": 85,
    "terrain_Brabant_wallon": 140,
    "terrain_Luxembourg": 80,

    # Valeur locative (rendement brut indicatif)
    "rendement_brut_maison": 0.045,
    "rendement_brut_appartement": 0.050,
    "rendement_brut_commerce": 0.060,

    # Coef expert (%)
    "coef_expert_min": -3.0,
    "coef_expert_max": 3.0,

    # Vente rapide / lente
    "vente_rapide_pct": -0.08,
    "vente_lente_pct": 0.05,

    # Humidité
    "hum_non": 0,
    "hum_legere": -6000,
    "hum_importante": -25000,

    # Année construction (impact)
    "annee_apres_2015": 15000,
    "annee_2000_2015": 8000,
    "annee_1980_1999": 3000,
    "annee_1950_1979": 0,
    "annee_avant_1950": -7000,

    # Etats par poste (Bon/Moyen/Mauvais)
    "poste_bon": 0,
    "poste_moyen": -6000,
    "poste_mauvais": -18000,

    # Isolation (Bonne/Moyenne/Mauvaise)
    "isolation_bonne": 6000,
    "isolation_moyenne": 0,
    "isolation_mauvaise": -8000,

    # Cave surface
    "cave_eur_m2": 120,

    # Equipements (cases)
    "eq_pv": 6000,
    "eq_clim": 2500,
    "eq_vmc": 2000,
    "eq_alarme": 1500,
    "eq_domotique": 2500,
    "eq_piscine": 15000,
    "eq_poele_pellet": 2000,

    # Façades
    "facades_2": 0,
    "facades_3": 8000,
    "facades_4": 15000,

    # Caractéristiques (pièces / annexes)
    "impact_par_chambre": 6000,
    "impact_par_sdb_supp": 5000,
    "impact_garage": 12000,
    "impact_par_place_parking": 6000,
    "impact_balcon": 4000,
    "impact_terrasse": 7000,
    "impact_jardin": 8000,

    "grenier_amenageable_base": 3000,
    "grenier_amenageable_eur_m2": 90,

    # Vitrage / chauffage / cuisine / sdb / toiture / PEB
    "vitrage_simple": -8000,
    "vitrage_double_ancien": -3000,
    "vitrage_double_recent": 0,
    "vitrage_triple": 4000,

    "chauff_pac": 8000,
    "chauff_gaz_cond": 3000,
    "chauff_mazout": -5000,
    "chauff_electrique": -8000,
    "chauff_ancien": -10000,

    "cuisine_bonne": 0,
    "cuisine_moderniser": -5000,
    "cuisine_remplacer": -12000,

    "sdb_bonne": 0,
    "sdb_moderniser": -4000,
    "sdb_remplacer": -9000,

    "toit_forfait": 18000,
    "toit_moyen_coeff": 0.5,
    "toit_factor": 0.7,

    "peb_A": 6000,
    "peb_B": 3000,
    "peb_C": 0,
    "peb_D": -3000,
    "peb_E": -6000,
    "peb_F": -9000,
    "peb_G": -12000,

    # Fourchette (marché)
    "fourchette_neutre_pct": 0.06,

    # Garde-fous
    "cap_bonus_pct": 0.12,   # bonus max = +12% base marché
    "cap_malus_pct": -0.35,  # malus max = -35% base marché

    # ===== AJOUTS EXPERT =====
    # Gros œuvre / entretien / parachèvement
    "gros_oeuvre_bon": 0,
    "gros_oeuvre_moyen": -15000,
    "gros_oeuvre_mauvais": -45000,

    "entretien_bon": 0,
    "entretien_moyen": -8000,
    "entretien_mauvais": -20000,

    "parachevement_bon": 0,
    "parachevement_moyen": -6000,
    "parachevement_mauvais": -15000,

    # Égout
    "egout_oui": 0,
    "egout_non": -6000,

    # Equipements utiles / confort
    "equip_utile_bonus": 4000,
    "equip_confort_bonus": 6000,

    # Pondérations surfaces (surface totale auto)
    "pond_cave": 0.30,
    "pond_grenier": 0.50,
}

# =========================
# Open Data (ODWB)
# =========================
@st.cache_data(show_spinner=False, ttl=60 * 60 * 12)
def load_odwb_prices_csv() -> pd.DataFrame:
    r = requests.get(ODWB_EXPORT_CSV_URL, timeout=30)
    r.raise_for_status()
    content = r.content.decode("utf-8", errors="replace")
    df = pd.read_csv(BytesIO(content.encode("utf-8")), sep=";")
    df.columns = [c.strip().lower() for c in df.columns]
    return df

def filter_wallonie(df: pd.DataFrame) -> pd.DataFrame:
    if "region" in df.columns:
        return df[df["region"].astype(str).str.upper().str.contains("WALL")].copy()
    return df.copy()

def detect_columns(df: pd.DataFrame):
    cols = set(df.columns)

    def pick(candidates):
        for c in candidates:
            if c in cols:
                return c
        return None

    commune = pick(["commune", "commune_nom", "nom_commune", "localite", "municipalite"])
    annee = pick(["annee", "year"])
    typ = pick(["type", "type_bien", "bien", "categorie", "typologie"])
    median_price = pick(["prix_median", "median_price", "median", "prixmedian", "prix_median_eur"])
    transactions = pick(["transactions", "nb_transactions", "nombre_transactions", "volume"])
    return commune, annee, typ, median_price, transactions

def detect_quantile_columns(df: pd.DataFrame):
    cols = set(df.columns)

    def pick(cands):
        for c in cands:
            if c in cols:
                return c
        return None

    q1 = pick(["prix_q1", "q1", "prix_25", "prix_quartile_1", "prix_p25"])
    q3 = pick(["prix_q3", "q3", "prix_75", "prix_quartile_3", "prix_p75"])
    return q1, q3

def odwb_series_commune(
    df: pd.DataFrame,
    col_commune: str,
    col_year: str,
    col_type: str | None,
    col_median: str | None,
    commune: str,
    wanted_type_keyword: str
) -> pd.DataFrame:
    if not (col_commune and col_year and col_median):
        return pd.DataFrame(columns=["annee", "prix_median"])

    dff = df[df[col_commune].astype(str).str.strip() == str(commune).strip()].copy()
    if col_type:
        dff = dff[dff[col_type].astype(str).str.lower().str.contains(wanted_type_keyword)].copy()

    dff["annee_num"] = pd.to_numeric(dff[col_year], errors="coerce")
    dff["prix_num"] = pd.to_numeric(dff[col_median], errors="coerce")
    dff = dff.dropna(subset=["annee_num", "prix_num"])

    if len(dff) == 0:
        return pd.DataFrame(columns=["annee", "prix_median"])

    out = dff.groupby("annee_num")["prix_num"].mean().reset_index()
    out.columns = ["annee", "prix_median"]
    out = out.sort_values("annee")
    return out

def evolution_pct(series_df: pd.DataFrame, years_back: int) -> float | None:
    if series_df is None or len(series_df) < 2:
        return None
    last_year = int(series_df["annee"].max())
    target_year = last_year - years_back
    last_val = float(series_df[series_df["annee"] == last_year]["prix_median"].iloc[0])

    older = series_df[series_df["annee"] <= target_year]
    if len(older) == 0:
        return None
    old_year = int(older["annee"].max())
    old_val = float(older[older["annee"] == old_year]["prix_median"].iloc[0])

    if old_val <= 0:
        return None
    return (last_val / old_val - 1.0) * 100.0

@st.cache_data(show_spinner=False, ttl=60 * 60 * 24)
def postal_to_commune(cp: str) -> dict:
    cp = str(cp or "").strip()
    if not cp:
        return {}
    base = f"https://www.odwb.be/api/explore/v2.1/catalog/datasets/{POSTAL_DATASET}/records"
    where = urllib.parse.quote(f"postal_code={cp}")
    url = f"{base}?where={where}&limit=50"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        js = r.json()
        results = js.get("results", []) or []
        if not results:
            return {}
        row = results[0]
        commune = row.get("municipality") or row.get("commune") or row.get("city") or row.get("name") or ""
        locality = row.get("locality") or row.get("sub_municipality") or row.get("place") or ""
        province = row.get("province") or ""
        return {"commune": str(commune).strip(), "locality": str(locality).strip(), "province": str(province).strip()}
    except Exception:
        return {}

# =========================
# Base marché + garde-fous
# =========================
def market_base_value_from_series(series: pd.DataFrame, surface_totale: float, type_bien: str):
    if series is None or len(series) == 0:
        return None
    last_year = int(series["annee"].max())
    median_price = float(series[series["annee"] == last_year]["prix_median"].iloc[0])

    ref_surface = 140 if type_bien == "Maison" else (80 if type_bien == "Appartement" else 120)
    alpha = 0.85  # croissance douce
    ratio = max(float(surface_totale), 1.0) / float(ref_surface)
    base = median_price * (ratio ** alpha)
    return base, last_year

def cap_impacts(total_impacts: float, base: float, params: dict):
    if base <= 0:
        return total_impacts
    lo = float(params["cap_malus_pct"]) * base
    hi = float(params["cap_bonus_pct"]) * base
    return float(clamp(total_impacts, lo, hi))

def cap_by_market_quartiles(valeur: float, q1: float | None, q3: float | None, surface_totale: float, type_bien: str):
    if q1 is None or q3 is None or q1 <= 0 or q3 <= 0:
        return valeur
    ref_surface = 140 if type_bien == "Maison" else (80 if type_bien == "Appartement" else 120)
    alpha = 0.85
    ratio = max(float(surface_totale), 1.0) / float(ref_surface)
    q1_adj = float(q1) * (ratio ** alpha)
    q3_adj = float(q3) * (ratio ** alpha)
    lo = q1_adj * 0.90
    hi = q3_adj * 1.12
    return float(clamp(valeur, lo, hi))

# =========================
# Calculs Expert
# =========================
def terrain_auto(province: str, terrain_m2: float, params: dict) -> float:
    key = f"terrain_{province}"
    return float(terrain_m2) * float(params.get(key, 80))

def rendement_brut(type_bien: str, params: dict) -> float:
    if type_bien == "Maison":
        return float(params["rendement_brut_maison"])
    if type_bien == "Appartement":
        return float(params["rendement_brut_appartement"])
    return float(params["rendement_brut_commerce"])

def locatif_mensuel(valeur: float, type_bien: str, params: dict) -> float:
    return (valeur * rendement_brut(type_bien, params)) / 12.0

def impact_humidite(hum: str, params: dict) -> float:
    m = {"Non": params["hum_non"], "Legere": params["hum_legere"], "Importante": params["hum_importante"]}
    return float(m.get(hum, 0))

def impact_annee(annee: int, params: dict) -> float:
    if annee <= 0:
        return 0.0
    if annee >= 2016:
        return float(params["annee_apres_2015"])
    if 2000 <= annee <= 2015:
        return float(params["annee_2000_2015"])
    if 1980 <= annee <= 1999:
        return float(params["annee_1980_1999"])
    if 1950 <= annee <= 1979:
        return float(params["annee_1950_1979"])
    return float(params["annee_avant_1950"])

def impact_poste(etat: str, params: dict) -> float:
    m = {"Bon": params["poste_bon"], "Moyen": params["poste_moyen"], "Mauvais": params["poste_mauvais"]}
    return float(m.get(etat, 0))

def impact_isolation(etat: str, params: dict) -> float:
    m = {"Bonne": params["isolation_bonne"], "Moyenne": params["isolation_moyenne"], "Mauvaise": params["isolation_mauvaise"]}
    return float(m.get(etat, 0))

def impact_cave_surface(surface_cave_m2: float, params: dict) -> float:
    s = float(surface_cave_m2 or 0.0)
    if s <= 0:
        return 0.0
    return s * float(params["cave_eur_m2"])

def impact_facades(nb: int, params: dict) -> float:
    mapping = {2: params["facades_2"], 3: params["facades_3"], 4: params["facades_4"]}
    return float(mapping.get(int(nb), 0.0))

def impact_equipements(eq: dict, params: dict) -> float:
    total = 0.0
    if eq.get("pv"): total += float(params["eq_pv"])
    if eq.get("clim"): total += float(params["eq_clim"])
    if eq.get("vmc"): total += float(params["eq_vmc"])
    if eq.get("alarme"): total += float(params["eq_alarme"])
    if eq.get("domotique"): total += float(params["eq_domotique"])
    if eq.get("piscine"): total += float(params["eq_piscine"])
    if eq.get("poele_pellet"): total += float(params["eq_poele_pellet"])
    return total

def impact_vitrage(v: str, params: dict) -> float:
    m = {"Simple": params["vitrage_simple"], "Double ancien": params["vitrage_double_ancien"], "Double recent": params["vitrage_double_recent"], "Triple": params["vitrage_triple"]}
    return float(m.get(v, 0.0))

def impact_chauffage(c: str, params: dict) -> float:
    m = {"Pompe a chaleur": params["chauff_pac"], "Gaz condensation": params["chauff_gaz_cond"], "Mazout": params["chauff_mazout"],
         "Electrique": params["chauff_electrique"], "Ancien systeme / poele seul": params["chauff_ancien"]}
    return float(m.get(c, 0.0))

def impact_cuisine(etat: str, params: dict) -> float:
    m = {"Bonne": params["cuisine_bonne"], "A moderniser": params["cuisine_moderniser"], "A remplacer": params["cuisine_remplacer"]}
    return float(m.get(etat, 0.0))

def impact_sdb(etat: str, params: dict) -> float:
    m = {"Bonne": params["sdb_bonne"], "A moderniser": params["sdb_moderniser"], "A remplacer": params["sdb_remplacer"]}
    return float(m.get(etat, 0.0))

def impact_toiture(etat: str, params: dict) -> float:
    if etat == "Parfaite":
        return 0.0
    base = float(params["toit_forfait"])
    if etat == "Moyenne":
        base *= float(params["toit_moyen_coeff"])
    return -abs(base * float(params["toit_factor"]))

def impact_peb(letter: str, params: dict) -> float:
    l = (letter or "C").strip().upper()
    m = {"A": params["peb_A"], "B": params["peb_B"], "C": params["peb_C"], "D": params["peb_D"], "E": params["peb_E"], "F": params["peb_F"], "G": params["peb_G"]}
    return float(m.get(l, 0.0))

def impact_chambres(type_bien: str, nb: int, params: dict) -> float:
    if type_bien == "Commerce":
        return 0.0
    ref = 3 if type_bien == "Maison" else 2
    return float(nb - ref) * float(params["impact_par_chambre"])

def impact_sdb_count(nb: int, params: dict) -> float:
    ref = 1
    return float(nb - ref) * float(params["impact_par_sdb_supp"])

def impact_annexes(bien: dict, params: dict) -> float:
    total = 0.0
    total += int(bien["nb_places_parking"]) * float(params["impact_par_place_parking"])
    if bien["garage"]: total += float(params["impact_garage"])
    if bien["balcon"]: total += float(params["impact_balcon"])
    if bien["terrasse"]: total += float(params["impact_terrasse"])
    if bien["jardin"]: total += float(params["impact_jardin"])
    if bien["grenier_amenageable"]:
        total += float(params["grenier_amenageable_base"]) + float(bien["grenier_amenageable_surface_m2"]) * float(params["grenier_amenageable_eur_m2"])
    return total

# ===== AJOUTS DEMANDÉS (égout, gros oeuvre, parachevement, entretien, travaux, utile/confort) =====
def impact_egout(est_raccorde: str, params: dict) -> float:
    return float(params["egout_oui"] if est_raccorde == "Oui" else params["egout_non"])

def impact_etat3(etat: str, prefix: str, params: dict) -> float:
    key = f"{prefix}_{etat.lower()}"
    return float(params.get(key, 0))

def impact_travaux_budget(travaux_oui_non: str, budget: float) -> float:
    if travaux_oui_non != "Oui":
        return 0.0
    return -abs(float(budget or 0.0))

def impact_equipements_type(utile: bool, confort: bool, params: dict) -> float:
    total = 0.0
    if utile:
        total += float(params["equip_utile_bonus"])
    if confort:
        total += float(params["equip_confort_bonus"])
    return total

def indice_global(bien: dict) -> float:
    map_etat = {"Bon": 9, "Moyen": 6, "Mauvais": 3}
    hum_map = {"Non": 10, "Legere": 6, "Importante": 2}
    peb_map = {"A": 10, "B": 9, "C": 8, "D": 6, "E": 4, "F": 3, "G": 2}
    iso_map = {"Bonne": 9, "Moyenne": 6, "Mauvaise": 3}

    notes = [
        map_etat.get(bien["etat_maconnerie"], 6),
        map_etat.get(bien["etat_toiture_poste"], 6),
        map_etat.get(bien["etat_electricite"], 6),
        map_etat.get(bien["etat_plomberie"], 6),
        map_etat.get(bien["etat_sols"], 6),
        map_etat.get(bien["etat_facades"], 6),
        hum_map.get(bien["humidite"], 6),
        peb_map.get(bien["peb_lettre"], 8),
        iso_map.get(bien["isolation_toiture"], 6),
        iso_map.get(bien["isolation_murs"], 6),
        iso_map.get(bien["isolation_sol"], 6),
        map_etat.get(bien["gros_oeuvre"], 6),
        map_etat.get(bien["entretien_global"], 6),
        map_etat.get(bien["parachevement"], 6),
    ]
    return float(mean(notes))

def fourchette(valeur: float, indice: float, params: dict):
    neutre = float(params["fourchette_neutre_pct"])
    if indice >= 8:
        low_pct, high_pct = 0.05, 0.08
    elif indice >= 6:
        low_pct, high_pct = neutre, neutre
    elif indice >= 4:
        low_pct, high_pct = 0.08, 0.05
    else:
        low_pct, high_pct = 0.10, 0.04
    return valeur * (1 - low_pct), valeur * (1 + high_pct)

# =========================
# PDF (3 pages)
# =========================
def draw_header(c: canvas.Canvas, title: str, subtitle: str):
    w, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, h - 55, title)
    c.setFont("Helvetica", 10)
    c.drawString(40, h - 72, AGENCE)
    c.drawString(40, h - 86, f"Contact: {EMAIL}")
    c.drawString(40, h - 100, f"Date: {date.today().strftime('%d/%m/%Y')}")
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(40, h - 114, subtitle)
    c.line(40, h - 130, w - 40, h - 130)

def build_pdf(
    bien, client, comp, evol5, evol10, impacts,
    valeur_base, valeur_terrain, valeur_finale, low, high,
    loyer_mensuel, vente_rapide, vente_lente, indice,
    coef_expert_pct, justif, micro_coef_pct
) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Page 1 - synthèse vendeur
    draw_header(c, "Rapport d'estimation - Professionnel", "Synthèse vendeur (page 1/3)")
    y = h - 165
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Bien"); y -= 18
    c.setFont("Helvetica", 10)

    c.drawString(55, y, f"Client: {safe_text(client.get('nom',''), 70) or '-'}"); y -= 14
    c.drawString(55, y, f"Adresse: {safe_text(bien['adresse'], 120) or '-'}"); y -= 14
    c.drawString(55, y, f"Code postal: {safe_text(bien.get('code_postal',''), 10) or '-'}  |  Commune marché: {safe_text(bien['commune'], 60) or '-'}"); y -= 14
    if bien.get("zone"):
        c.drawString(55, y, f"Zone / quartier: {safe_text(bien.get('zone',''), 60)}"); y -= 14

    c.drawString(55, y, f"Province: {bien['province']}  |  Type: {bien['type_bien']}"); y -= 14
    c.drawString(55, y, f"Année construction: {bien['annee_construction'] or '-'}  |  Façades: {int(bien['nb_facades'])}"); y -= 14

    c.drawString(55, y, f"Surface habitable (auto): {bien['surface_habitable']:.0f} m²  |  Surface totale (auto): {bien['surface_totale']:.0f} m²"); y -= 14
    if bien["type_bien"] == "Maison":
        c.drawString(55, y, f"Terrain: {bien['terrain_m2']:.0f} m²  |  Valeur terrain auto: {euro(valeur_terrain)}"); y -= 14

    etages_str = " / ".join([f"{s:.0f} m²" for s in (bien.get("surfaces_etages") or [])]) if (bien.get("surfaces_etages") and sum(bien.get("surfaces_etages")) > 0) else "-"
    c.drawString(
        55, y,
        f"Mesures intramuros: RDC {bien.get('surface_rdc',0):.0f} m² | Étages {etages_str} | Sous-sol {bien.get('surface_sous_sol',0):.0f} m² | Total {bien.get('surface_intramuros_totale',0):.0f} m²"
    )
    y -= 14

    c.drawString(55, y, f"Gros œuvre: {bien.get('gros_oeuvre','-')} | Entretien: {bien.get('entretien_global','-')} | Parachèvement: {bien.get('parachevement','-')}")
    y -= 14
    c.drawString(55, y, f"Relié à l’égout: {bien.get('egout','-')} | Travaux à prévoir: {bien.get('travaux','-')} (budget {euro(bien.get('budget_travaux',0))})")
    y -= 14
    if bien.get("details_travaux"):
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(55, y, f"Détails travaux: {safe_text(bien.get('details_travaux',''), 110)}")
        y -= 14
        c.setFont("Helvetica", 10)

    c.drawString(55, y, f"Isolation toiture/murs/sol: {bien['isolation_toiture']} / {bien['isolation_murs']} / {bien['isolation_sol']}"); y -= 14
    c.drawString(55, y, f"Humidité: {bien['humidite']}  |  Cave: {bien.get('surface_cave_m2', 0):.0f} m²"); y -= 14
    c.drawString(55, y, f"PEB: {bien['peb_lettre']}" + (f" ({bien['peb_kwh']:.0f} kWh/m².an)" if bien["peb_kwh"] else "")); y -= 14
    c.drawString(55, y, f"Chauffage: {bien['chauffage']}  |  Vitrage: {bien['vitrage']}"); y -= 14
    c.drawString(55, y, f"Cuisine: {bien['etat_cuisine']}  |  Salle de bain: {bien['etat_sdb']}"); y -= 14

    c.drawString(55, y, f"Chambres: {bien['chambres']}  |  SDB: {bien['sdb']}  |  Étage (si appart): {bien.get('etage', '-') }"); y -= 14
    c.drawString(55, y, f"Garage: {'Oui' if bien['garage'] else 'Non'}  |  Parking: {bien['nb_places_parking']}  |  Balcon: {'Oui' if bien['balcon'] else 'Non'}  |  Terrasse: {'Oui' if bien['terrasse'] else 'Non'}"); y -= 14
    c.drawString(55, y, f"Jardin: {'Oui' if bien['jardin'] else 'Non'}  |  Grenier aménageable: {'Oui' if bien['grenier_amenageable'] else 'Non'} ({bien.get('grenier_amenageable_surface_m2',0):.0f} m²)"); y -= 14
    c.drawString(55, y, f"Équipements: utiles={'Oui' if bien.get('equip_utile') else 'Non'} | confort={'Oui' if bien.get('equip_confort') else 'Non'}"); y -= 14

    y -= 4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"Valeur estimée: {euro(valeur_finale)}"); y -= 18
    c.setFont("Helvetica", 11)
    c.drawString(40, y, f"Fourchette conseillée: {euro(low)}  →  {euro(high)}"); y -= 16
    c.drawString(40, y, f"Vente rapide: {euro(vente_rapide)}  |  Vente lente: {euro(vente_lente)}"); y -= 16
    c.drawString(40, y, f"Valeur locative mensuelle (indicative): {euro(loyer_mensuel)}"); y -= 16

    c.setFont("Helvetica", 10)
    if comp.get("ok"):
        c.drawString(40, y, f"Marché (open data): année {comp.get('year','-')} | Evol 5 ans: {('%.1f' % evol5 + '%') if evol5 is not None else '—'} | Evol 10 ans: {('%.1f' % evol10 + '%') if evol10 is not None else '—'}"); y -= 14
    else:
        c.drawString(40, y, "Marché (open data): non trouvé (commune/type) → base prudente appliquée."); y -= 14

    c.drawString(40, y, f"Indice global: {indice:.1f}/10 | Coef expert: {coef_expert_pct:+.1f}% | Micro coef CP: {micro_coef_pct:+.1f}%"); y -= 14
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(40, y, f"Justification coef expert: {safe_text(justif, 110) or '-'}"); y -= 18

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Estimation professionnelle basée sur open data + analyse technique + garde-fous. Fourchette conseillée.")
    c.showPage()

    # Page 2 - détail calcul
    draw_header(c, "Détail des calculs", "Impacts poste par poste (page 2/3)")
    y = h - 165
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Valeur de base"); y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Valeur base marché (surface ajustée): {euro(valeur_base)}"); y -= 14
    if bien["type_bien"] == "Maison":
        c.drawString(55, y, f"Valeur terrain auto: {euro(valeur_terrain)}"); y -= 14

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Impacts (poste par poste)"); y -= 18
    c.setFont("Helvetica", 10)
    for k, v in impacts.items():
        c.drawString(55, y, f"{k}: {euro(v)}")
        y -= 14
        if y < 80:
            c.showPage()
            draw_header(c, "Détail des calculs (suite)", "Impacts (page 2/3)")
            y = h - 165
            c.setFont("Helvetica", 10)

    c.showPage()

    # Page 3 - méthodologie
    draw_header(c, "Méthodologie", "Explications (page 3/3)")
    y = h - 165
    c.setFont("Helvetica", 10)
    txt = [
        "1) Marché: prix médians par commune via WalStat/Statbel (ODWB).",
        "2) Ajustement surface: transformation de la médiane en base adaptée à la surface du bien (croissance douce).",
        "3) Expertise technique: impacts chiffrés (structure, finitions, humidité, isolation, PEB, chauffage, postes techniques...).",
        "4) Terrain: estimation automatique selon province (base interne).",
        "5) Garde-fous: limitation des bonus/malus + plafonnement par quartiles (si disponibles) pour éviter la surestimation.",
        "6) Micro-ajustement par code postal: appris via tes dossiers (prix validés) pour affiner la réalité locale.",
        "Note: l’estimation immobilière reste une fourchette; l’objectif est une valeur défendable et cohérente marché.",
    ]
    for line in txt:
        c.drawString(40, y, line); y -= 14

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Outil interne - La Priorite Immobiliere.")
    c.save()

    buf.seek(0)
    return buf.getvalue()

# =========================
# “DB” simple (CRM + historique) + micro CP
# =========================
CLIENTS_COLS = ["client_id", "nom", "telephone", "email", "notes", "date_creation"]
BIENS_COLS = [
    "bien_id", "client_id", "adresse", "code_postal", "zone", "commune", "province", "type_bien",
    "surface_habitable", "surface_totale", "terrain_m2", "nb_facades",
    "peb_lettre", "peb_kwh", "statut", "notes", "date_creation"
]
ESTIM_COLS = [
    "estimation_id", "bien_id", "client_id", "date_estimation",
    "valeur_base", "valeur_terrain", "total_impacts", "coef_expert_pct", "micro_coef_pct",
    "valeur_finale", "fourchette_basse", "fourchette_haute",
    "vente_rapide", "vente_lente", "loyer_mensuel",
    "indice_global", "commune_marche", "annee_marche", "evol_5ans", "evol_10ans"
]
MICRO_COLS = ["code_postal", "type_bien", "coef_pct", "n_obs", "last_update"]

def ensure_tables():
    if "params" not in st.session_state:
        st.session_state["params"] = DEFAULT_PARAMS.copy()
    if "clients" not in st.session_state:
        st.session_state["clients"] = pd.DataFrame(columns=CLIENTS_COLS)
    if "biens" not in st.session_state:
        st.session_state["biens"] = pd.DataFrame(columns=BIENS_COLS)
    if "estimations" not in st.session_state:
        st.session_state["estimations"] = pd.DataFrame(columns=ESTIM_COLS)
    if "micro_cp" not in st.session_state:
        st.session_state["micro_cp"] = pd.DataFrame(columns=MICRO_COLS)

def add_client(nom, telephone, email, notes):
    df = st.session_state["clients"]
    row = {
        "client_id": str(uuid.uuid4()),
        "nom": (nom or "Client").strip(),
        "telephone": (telephone or "").strip(),
        "email": (email or "").strip(),
        "notes": (notes or "").strip(),
        "date_creation": today_iso(),
    }
    st.session_state["clients"] = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    return row["client_id"]

def add_bien(client_id, adresse, code_postal, zone, commune, province, type_bien,
             surface_habitable, surface_totale, terrain_m2, nb_facades,
             peb_lettre, peb_kwh, statut, notes):
    df = st.session_state["biens"]
    row = {
        "bien_id": str(uuid.uuid4()),
        "client_id": client_id,
        "adresse": (adresse or "").strip(),
        "code_postal": (code_postal or "").strip(),
        "zone": (zone or "").strip(),
        "commune": (commune or "").strip(),
        "province": province,
        "type_bien": type_bien,
        "surface_habitable": float(surface_habitable),
        "surface_totale": float(surface_totale),
        "terrain_m2": float(terrain_m2),
        "nb_facades": int(nb_facades),
        "peb_lettre": peb_lettre,
        "peb_kwh": float(peb_kwh),
        "statut": statut,
        "notes": (notes or "").strip(),
        "date_creation": today_iso(),
    }
    st.session_state["biens"] = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    return row["bien_id"]

def add_estimation(row: dict):
    df = st.session_state["estimations"]
    st.session_state["estimations"] = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

def export_all_to_txt():
    clients = st.session_state["clients"].copy()
    biens = st.session_state["biens"].copy()
    estim = st.session_state["estimations"].copy()
    micro = st.session_state["micro_cp"].copy()

    out = BytesIO()
    out.write(b"###CLIENTS###\n")
    out.write(clients.to_csv(index=False).encode("utf-8"))
    out.write(b"\n###BIENS###\n")
    out.write(biens.to_csv(index=False).encode("utf-8"))
    out.write(b"\n###ESTIMATIONS###\n")
    out.write(estim.to_csv(index=False).encode("utf-8"))
    out.write(b"\n###MICROCP###\n")
    out.write(micro.to_csv(index=False).encode("utf-8"))
    out.seek(0)
    return out.getvalue()

def import_from_txt(content: bytes):
    text = content.decode("utf-8", errors="replace")
    for marker in ["###CLIENTS###", "###BIENS###", "###ESTIMATIONS###", "###MICROCP###"]:
        if marker not in text:
            raise ValueError("Fichier invalide (export attendu).")

    part_clients = text.split("###CLIENTS###\n", 1)[1].split("\n###BIENS###\n", 1)[0]
    part_biens = text.split("\n###BIENS###\n", 1)[1].split("\n###ESTIMATIONS###\n", 1)[0]
    part_estim = text.split("\n###ESTIMATIONS###\n", 1)[1].split("\n###MICROCP###\n", 1)[0]
    part_micro = text.split("\n###MICROCP###\n", 1)[1]

    cdf = pd.read_csv(BytesIO(part_clients.encode("utf-8")))
    bdf = pd.read_csv(BytesIO(part_biens.encode("utf-8")))
    edf = pd.read_csv(BytesIO(part_estim.encode("utf-8")))
    mdf = pd.read_csv(BytesIO(part_micro.encode("utf-8")))

    for col in CLIENTS_COLS:
        if col not in cdf.columns: cdf[col] = ""
    for col in BIENS_COLS:
        if col not in bdf.columns: bdf[col] = ""
    for col in ESTIM_COLS:
        if col not in edf.columns: edf[col] = ""
    for col in MICRO_COLS:
        if col not in mdf.columns: mdf[col] = ""

    st.session_state["clients"] = cdf[CLIENTS_COLS]
    st.session_state["biens"] = bdf[BIENS_COLS]
    st.session_state["estimations"] = edf[ESTIM_COLS]
    st.session_state["micro_cp"] = mdf[MICRO_COLS]

def get_micro_coef(cp: str, type_bien: str) -> float:
    df = st.session_state.get("micro_cp", pd.DataFrame(columns=MICRO_COLS))
    if df is None or len(df) == 0:
        return 0.0
    d = df[(df["code_postal"].astype(str) == str(cp)) & (df["type_bien"].astype(str) == str(type_bien))]
    if len(d) == 0:
        return 0.0
    return float(d.iloc[0]["coef_pct"]) / 100.0

def update_micro_coef(cp: str, type_bien: str, ratio: float):
    if not cp:
        return
    coef_new_pct = (float(ratio) - 1.0) * 100.0
    coef_new_pct = clamp(coef_new_pct, -20.0, 20.0)

    df = st.session_state["micro_cp"]
    mask = (df["code_postal"].astype(str) == str(cp)) & (df["type_bien"].astype(str) == str(type_bien))

    if mask.any():
        idx = df[mask].index[0]
        old = float(df.loc[idx, "coef_pct"])
        n = parse_int(df.loc[idx, "n_obs"], 0)
        new = (old * n + coef_new_pct) / (n + 1)
        df.loc[idx, "coef_pct"] = round(new, 2)
        df.loc[idx, "n_obs"] = n + 1
        df.loc[idx, "last_update"] = today_iso()
    else:
        row = {"code_postal": str(cp), "type_bien": str(type_bien), "coef_pct": round(coef_new_pct, 2), "n_obs": 1, "last_update": today_iso()}
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    st.session_state["micro_cp"] = df

# =========================
# UI
# =========================
st.set_page_config(page_title="Logiciel Agence - La Priorite Immobiliere", layout="wide")
ensure_tables()
params = st.session_state["params"]

st.title("Logiciel Agence (Wallonie) - La Priorite Immobiliere")

tabs = st.tabs([
    "1) Estimation PRO",
    "2) Marché & évolution",
    "3) Historique estimations",
    "4) CRM Clients",
    "5) Fiches biens",
    "6) Sauvegarde / Import",
])

# =========================
# SIDEBAR (encodage)
# =========================
with st.sidebar:
    st.subheader("Client (optionnel)")
    client_nom = st.text_input("Nom client", value="")
    client_tel = st.text_input("Téléphone", value="")
    client_email = st.text_input("Email", value="")
    client_notes = st.text_area("Notes client", value="", height=70)

    st.subheader("Bien")
    adresse = st.text_input("Adresse complète", value="")
    province = st.selectbox("Province", ["Hainaut", "Namur", "Liege", "Brabant_wallon", "Luxembourg"])
    type_bien = st.selectbox("Type de bien", ["Maison", "Appartement", "Commerce"])

    st.subheader("Localisation")
    code_postal = st.text_input("Code postal (Wallonie)", value="")
    info_cp = postal_to_commune(code_postal) if code_postal else {}
    zone = st.text_input("Zone / quartier (optionnel)", value="")
    commune = st.text_input("Commune (marché) – auto via code postal", value=(info_cp.get("commune") or ""))

    terrain_m2 = 0.0
    if type_bien == "Maison":
        terrain_m2 = st.number_input("Terrain (m²)", min_value=0.0, value=0.0, step=10.0)

    nb_facades = st.selectbox("Nombre de façades", [2, 3, 4], index=0)

    # ===== Intramuros détaillé =====
    st.subheader("Mesures intramuros (détaillées)")
    surface_rdc = st.number_input("Surface RDC (m²) - intramuros", min_value=0.0, value=0.0, step=5.0)
    nb_etages_hors_rdc = st.number_input("Nombre d'étages (hors RDC)", min_value=0, max_value=10, value=0, step=1)

    surfaces_etages = []
    for i in range(int(nb_etages_hors_rdc)):
        surfaces_etages.append(
            st.number_input(
                f"Surface étage {i+1} (m²) - intramuros",
                min_value=0.0, value=0.0, step=5.0,
                key=f"surf_et_{i}"
            )
        )

    surface_sous_sol = st.number_input("Surface sous-sol (m²) - intramuros (optionnel)", min_value=0.0, value=0.0, step=5.0)
    surface_intramuros_totale = float(surface_rdc) + float(sum(surfaces_etages)) + float(surface_sous_sol)
    st.caption(f"Total intramuros calculé: {surface_intramuros_totale:.0f} m²")

    st.subheader("Construction / état")
    annee_construction = st.number_input("Année de construction", min_value=0, max_value=2100, value=0, step=1)
    humidite = st.selectbox("Humidité", ["Non", "Legere", "Importante"], index=0)

    st.subheader("Isolation")
    isolation_toiture = st.selectbox("Isolation toiture", ["Bonne", "Moyenne", "Mauvaise"], index=1)
    isolation_murs = st.selectbox("Isolation murs", ["Bonne", "Moyenne", "Mauvaise"], index=1)
    isolation_sol = st.selectbox("Isolation sol", ["Bonne", "Moyenne", "Mauvaise"], index=1)

    st.subheader("Technique")
    toiture_etat = st.selectbox("Toiture (état)", ["Parfaite", "Moyenne", "Mauvaise"], index=0)
    chauffage = st.selectbox("Chauffage", ["Pompe a chaleur", "Gaz condensation", "Mazout", "Electrique", "Ancien systeme / poele seul"], index=1)
    vitrage = st.selectbox("Châssis/Vitrage", ["Simple", "Double ancien", "Double recent", "Triple"], index=2)

    peb_lettre = st.selectbox("PEB (lettre)", ["A", "B", "C", "D", "E", "F", "G"], index=2)
    peb_kwh = st.number_input("PEB (kWh/m².an) optionnel", min_value=0.0, value=0.0, step=1.0)

    etat_cuisine = st.selectbox("Cuisine (état)", ["Bonne", "A moderniser", "A remplacer"], index=0)
    etat_sdb = st.selectbox("Salle de bain (état)", ["Bonne", "A moderniser", "A remplacer"], index=0)

    st.subheader("Etat par poste (expert)")
    etat_maconnerie = st.selectbox("Maçonnerie / fissures", ["Bon", "Moyen", "Mauvais"], index=0)
    etat_toiture_poste = st.selectbox("Toiture (poste)", ["Bon", "Moyen", "Mauvais"], index=0)
    etat_electricite = st.selectbox("Electricité", ["Bon", "Moyen", "Mauvais"], index=0)
    etat_plomberie = st.selectbox("Plomberie", ["Bon", "Moyen", "Mauvais"], index=0)
    etat_sols = st.selectbox("Sols / carrelage", ["Bon", "Moyen", "Mauvais"], index=0)
    etat_facades = st.selectbox("Façades (poste)", ["Bon", "Moyen", "Mauvais"], index=0)

    st.subheader("Structure & entretien (expert)")
    gros_oeuvre = st.selectbox("Gros œuvre", ["Bon", "Moyen", "Mauvais"], index=0)
    entretien_global = st.selectbox("Etat d’entretien global", ["Bon", "Moyen", "Mauvais"], index=0)
    parachevement = st.selectbox("Parachèvement (finitions)", ["Bon", "Moyen", "Mauvais"], index=0)

    st.subheader("Réseaux")
    egout = st.selectbox("Relié à l’égout ?", ["Oui", "Non"], index=0)

    st.subheader("Travaux à prévoir")
    travaux = st.selectbox("Travaux à prévoir ?", ["Non", "Oui"], index=0)
    budget_travaux = st.number_input("Budget estimatif travaux (€)", min_value=0.0, value=0.0, step=1000.0, disabled=(travaux != "Oui"))
    details_travaux = st.text_area("Détails travaux (optionnel)", value="", height=70)

    st.subheader("Pièces")
    chambres = st.number_input("Chambres", min_value=0, value=2, step=1)
    sdb = st.number_input("Salles de bain", min_value=0, value=1, step=1)
    etage = st.number_input("Étage (si appartement)", min_value=0, value=0, step=1)

    st.subheader("Annexes")
    surface_cave_m2 = st.number_input("Surface cave (m²)", min_value=0.0, value=0.0, step=5.0)
    nb_places_parking = st.number_input("Places parking", min_value=0, value=0, step=1)
    garage = st.checkbox("Garage", value=False)
    balcon = st.checkbox("Balcon", value=False)
    terrasse = st.checkbox("Terrasse", value=False)
    jardin = st.checkbox("Jardin", value=False)

    grenier_amenageable = st.checkbox("Grenier aménageable", value=False)
    grenier_amenageable_surface_m2 = st.number_input(
        "Surface grenier aménageable (m²)",
        min_value=0.0, value=0.0, step=5.0,
        disabled=not grenier_amenageable
    )

    # ===== SURFACES AUTO (habitable + totale) =====
    pond_cave = float(params.get("pond_cave", 0.30))
    pond_grenier = float(params.get("pond_grenier", 0.50))
    cave = float(surface_cave_m2 or 0.0)
    grenier = float(grenier_amenageable_surface_m2 or 0.0) if grenier_amenageable else 0.0

    surface_habitable_auto = max(0.0, float(surface_intramuros_totale))
    surface_totale_auto = max(1.0, float(surface_intramuros_totale) + pond_cave * cave + pond_grenier * grenier)

    st.subheader("Surfaces (auto)")
    st.number_input("Surface habitable (m²) - auto", min_value=0.0, value=float(surface_habitable_auto), step=1.0, disabled=True)
    st.number_input("Surface totale (m²) - auto", min_value=1.0, value=float(surface_totale_auto), step=1.0, disabled=True)
    st.caption(f"Formule surface totale: intramuros + {pond_cave:.2f}×cave + {pond_grenier:.2f}×grenier")

    st.subheader("Equipements (détaillés)")
    eq_pv = st.checkbox("Panneaux photovoltaïques", value=False)
    eq_clim = st.checkbox("Climatisation", value=False)
    eq_vmc = st.checkbox("VMC", value=False)
    eq_alarme = st.checkbox("Alarme", value=False)
    eq_domotique = st.checkbox("Domotique", value=False)
    eq_piscine = st.checkbox("Piscine", value=False)
    eq_poele_pellet = st.checkbox("Poêle / pellet", value=False)

    st.subheader("Equipements (utile / confort)")
    equip_utile = st.checkbox("Equipements utiles (ex: citerne, adoucisseur, ventilation…)", value=False)
    equip_confort = st.checkbox("Equipements confort (ex: jacuzzi, home cinema…)", value=False)

    st.subheader("Ajustement expert (rare)")
    coef_expert_pct = st.slider(
        "Coefficient expert (%)",
        float(params["coef_expert_min"]),
        float(params["coef_expert_max"]),
        value=0.0,
        step=0.5
    )
    justif_coef = st.text_area("Justification coef expert", value="", height=70)

# =========================
# Données bien (avec surfaces auto)
# =========================
bien = {
    "client_nom": client_nom,
    "client_tel": client_tel,
    "client_email": client_email,
    "client_notes": client_notes,

    "adresse": adresse,
    "code_postal": code_postal.strip(),
    "zone": zone.strip(),
    "commune": commune.strip(),
    "province": province,
    "type_bien": type_bien,

    "surface_habitable": float(surface_habitable_auto),
    "surface_totale": float(surface_totale_auto),
    "terrain_m2": float(terrain_m2),
    "nb_facades": int(nb_facades),

    "surface_rdc": float(surface_rdc),
    "surfaces_etages": [float(x) for x in surfaces_etages],
    "surface_sous_sol": float(surface_sous_sol),
    "surface_intramuros_totale": float(surface_intramuros_totale),

    "annee_construction": int(annee_construction),
    "humidite": humidite,

    "isolation_toiture": isolation_toiture,
    "isolation_murs": isolation_murs,
    "isolation_sol": isolation_sol,

    "toiture_etat": toiture_etat,
    "chauffage": chauffage,
    "vitrage": vitrage,
    "peb_lettre": peb_lettre,
    "peb_kwh": float(peb_kwh),
    "etat_cuisine": etat_cuisine,
    "etat_sdb": etat_sdb,

    "etat_maconnerie": etat_maconnerie,
    "etat_toiture_poste": etat_toiture_poste,
    "etat_electricite": etat_electricite,
    "etat_plomberie": etat_plomberie,
    "etat_sols": etat_sols,
    "etat_facades": etat_facades,

    "gros_oeuvre": gros_oeuvre,
    "entretien_global": entretien_global,
    "parachevement": parachevement,
    "egout": egout,
    "travaux": travaux,
    "budget_travaux": float(budget_travaux),
    "details_travaux": details_travaux,

    "chambres": int(chambres),
    "sdb": int(sdb),
    "etage": int(etage),

    "surface_cave_m2": float(surface_cave_m2),
    "nb_places_parking": int(nb_places_parking),
    "garage": bool(garage),
    "balcon": bool(balcon),
    "terrasse": bool(terrasse),
    "jardin": bool(jardin),
    "grenier_amenageable": bool(grenier_amenageable),
    "grenier_amenageable_surface_m2": float(grenier_amenageable_surface_m2),

    "equipements": {
        "pv": bool(eq_pv),
        "clim": bool(eq_clim),
        "vmc": bool(eq_vmc),
        "alarme": bool(eq_alarme),
        "domotique": bool(eq_domotique),
        "piscine": bool(eq_piscine),
        "poele_pellet": bool(eq_poele_pellet),
    },
    "equip_utile": bool(equip_utile),
    "equip_confort": bool(equip_confort),

    "coef_expert_pct": float(coef_expert_pct),
    "justif_coef": justif_coef,
}

# =========================
# TAB 1) Estimation PRO
# =========================
with tabs[0]:
    st.subheader("Estimation PRO (fiable + garde-fous)")

    comp = {"ok": False, "year": None}
    evol5 = None
    evol10 = None
    q1_val = None
    q3_val = None

    # Fallback prudente (évite prix trop hauts)
    fallback_eur_m2 = 1500 if type_bien == "Maison" else (2000 if type_bien == "Appartement" else 1700)
    valeur_base = bien["surface_totale"] * fallback_eur_m2

    if bien["commune"]:
        try:
            df = filter_wallonie(load_odwb_prices_csv())
            col_commune, col_year, col_type, col_median, col_tx = detect_columns(df)
            q1_col, q3_col = detect_quantile_columns(df)

            want_kw = "maison" if type_bien == "Maison" else ("appart" if type_bien == "Appartement" else "commerce")
            series = odwb_series_commune(df, col_commune, col_year, col_type, col_median, bien["commune"], want_kw)

            mb = market_base_value_from_series(series, bien["surface_totale"], type_bien)
            if mb is not None:
                valeur_base, last_year = mb
                comp = {"ok": True, "year": last_year}
                evol5 = evolution_pct(series, 5)
                evol10 = evolution_pct(series, 10)

                if q1_col and q3_col and col_type:
                    dff = df[
                        (df[col_commune].astype(str).str.strip() == str(bien["commune"]).strip()) &
                        (df[col_type].astype(str).str.lower().str.contains(want_kw))
                    ].copy()
                    dff["annee_num"] = pd.to_numeric(dff[col_year], errors="coerce")
                    dff = dff[dff["annee_num"] == last_year]
                    if len(dff) > 0:
                        q1_val = parse_float(dff[q1_col].iloc[0], None)
                        q3_val = parse_float(dff[q3_col].iloc[0], None)

        except Exception:
            pass

    valeur_terrain = terrain_auto(bien["province"], bien["terrain_m2"], params) if type_bien == "Maison" else 0.0

    impacts = {}
    impacts["Humidité"] = impact_humidite(bien["humidite"], params)
    impacts["Année construction"] = impact_annee(bien["annee_construction"], params)
    impacts["Façades (nombre)"] = impact_facades(bien["nb_facades"], params)

    impacts["Isolation toiture"] = impact_isolation(bien["isolation_toiture"], params)
    impacts["Isolation murs"] = impact_isolation(bien["isolation_murs"], params)
    impacts["Isolation sol"] = impact_isolation(bien["isolation_sol"], params)

    impacts["Cave (surface)"] = impact_cave_surface(bien["surface_cave_m2"], params)

    impacts["Maçonnerie/fissures"] = impact_poste(bien["etat_maconnerie"], params)
    impacts["Toiture (poste)"] = impact_poste(bien["etat_toiture_poste"], params)
    impacts["Electricité"] = impact_poste(bien["etat_electricite"], params)
    impacts["Plomberie"] = impact_poste(bien["etat_plomberie"], params)
    impacts["Sols / carrelage"] = impact_poste(bien["etat_sols"], params)
    impacts["Façades (poste)"] = impact_poste(bien["etat_facades"], params)

    impacts["Toiture (état)"] = impact_toiture(bien["toiture_etat"], params)
    impacts["Chauffage"] = impact_chauffage(bien["chauffage"], params)
    impacts["Vitrage"] = impact_vitrage(bien["vitrage"], params)
    impacts["PEB"] = impact_peb(bien["peb_lettre"], params)
    impacts["Cuisine"] = impact_cuisine(bien["etat_cuisine"], params)
    impacts["Salle de bain"] = impact_sdb(bien["etat_sdb"], params)

    impacts["Chambres"] = impact_chambres(type_bien, bien["chambres"], params)
    impacts["SDB (nb)"] = impact_sdb_count(bien["sdb"], params)
    impacts["Annexes (parking/garage/terrasse/jardin…)"] = impact_annexes(bien, params)
    impacts["Equipements (cases)"] = impact_equipements(bien["equipements"], params)

    impacts["Gros œuvre"] = impact_etat3(bien["gros_oeuvre"], "gros_oeuvre", params)
    impacts["Entretien global"] = impact_etat3(bien["entretien_global"], "entretien", params)
    impacts["Parachèvement"] = impact_etat3(bien["parachevement"], "parachevement", params)
    impacts["Raccordement égout"] = impact_egout(bien["egout"], params)
    impacts["Travaux à prévoir (budget)"] = impact_travaux_budget(bien["travaux"], bien["budget_travaux"])
    impacts["Equipements utile/confort"] = impact_equipements_type(bien["equip_utile"], bien["equip_confort"], params)

    total_impacts_raw = sum(impacts.values())
    total_impacts = cap_impacts(total_impacts_raw, valeur_base, params)

    valeur_tech = valeur_base + valeur_terrain + total_impacts
    valeur_finale = valeur_tech * (1.0 + (bien["coef_expert_pct"] / 100.0))

    micro = get_micro_coef(bien.get("code_postal", ""), type_bien)
    micro_coef_pct = micro * 100.0
    valeur_finale = valeur_finale * (1.0 + micro)

    valeur_finale = cap_by_market_quartiles(valeur_finale, q1_val, q3_val, bien["surface_totale"], type_bien)

    indice = indice_global(bien)
    low, high = fourchette(valeur_finale, indice, params)

    loyer_mensuel = locatif_mensuel(valeur_finale, type_bien, params)
    vente_rapide = valeur_finale * (1.0 + float(params["vente_rapide_pct"]))
    vente_lente = valeur_finale * (1.0 + float(params["vente_lente_pct"]))

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Valeur base marché", euro(valeur_base))
    a2.metric("Terrain auto", euro(valeur_terrain))
    a3.metric("Impacts (plafonnés)", euro(total_impacts))
    a4.metric("Valeur estimée", euro(valeur_finale))

    b1, b2, b3 = st.columns(3)
    b1.metric("Fourchette basse", euro(low))
    b2.metric("Fourchette haute", euro(high))
    b3.metric("Indice global", f"{indice:.1f} / 10")

    c1, c2, c3 = st.columns(3)
    c1.metric("Vente rapide", euro(vente_rapide))
    c2.metric("Vente lente", euro(vente_lente))
    c3.metric("Valeur locative / mois", euro(loyer_mensuel))

    if comp["ok"]:
        st.info(
            f"Marché open data (commune {bien['commune']}): année {comp['year']} | "
            f"Evolution 5 ans: {('%.1f' % evol5 + '%') if evol5 is not None else '—'} | "
            f"Evolution 10 ans: {('%.1f' % evol10 + '%') if evol10 is not None else '—'}"
        )
    else:
        st.warning("Marché open data non trouvé → base prudente appliquée (évite les prix trop hauts).")

    st.caption(f"Micro-ajustement CP appliqué: {micro_coef_pct:+.1f}% (se construit avec tes références enregistrées).")

    with st.expander("Détail impacts (poste par poste)"):
        st.dataframe(pd.DataFrame([{"poste": k, "impact": v} for k, v in impacts.items()]), use_container_width=True)

    client_for_pdf = {"nom": bien["client_nom"], "telephone": bien["client_tel"], "email": bien["client_email"], "notes": bien["client_notes"]}
    pdf = build_pdf(
        bien=bien,
        client=client_for_pdf,
        comp=comp,
        evol5=evol5,
        evol10=evol10,
        impacts=impacts,
        valeur_base=valeur_base,
        valeur_terrain=valeur_terrain,
        valeur_finale=valeur_finale,
        low=low,
        high=high,
        loyer_mensuel=loyer_mensuel,
        vente_rapide=vente_rapide,
        vente_lente=vente_lente,
        indice=indice,
        coef_expert_pct=float(bien["coef_expert_pct"]),
        justif=bien["justif_coef"],
        micro_coef_pct=micro_coef_pct,
    )

    st.download_button(
        "Télécharger rapport vendeur (PDF - 3 pages)",
        data=pdf,
        file_name=f"Rapport_Expert_{today_iso()}.pdf",
        mime="application/pdf",
    )

    st.markdown("---")
    st.subheader("Apprentissage (rend l’estimation très précise par code postal)")
    st.caption("Quand tu connais le prix validé (mise en vente / vendu), encode-le une fois. Ensuite le CP devient précis automatiquement.")

    prix_reel = st.number_input("Prix réel validé (optionnel)", min_value=0.0, value=0.0, step=1000.0)
    if st.button("Enregistrer prix réel pour ce code postal"):
        if prix_reel > 0 and valeur_finale > 0:
            ratio = prix_reel / valeur_finale
            update_micro_coef(bien.get("code_postal", ""), type_bien, ratio)
            st.success("Référence enregistrée ✅ (l’outil s’améliore automatiquement)")
        else:
            st.error("Encode un prix réel > 0 et fais une estimation.")

    st.markdown("---")
    st.subheader("Enregistrer dans CRM (client + bien + estimation)")

    clients_df = st.session_state["clients"]
    client_id = None
    if len(clients_df) > 0:
        options = ["(Créer nouveau client)"] + [
            f"{row['nom']} • {row['email']} • {row['telephone']} • {row['client_id']}"
            for _, row in clients_df.iterrows()
        ]
        pick = st.selectbox("Associer à un client CRM", options, index=0)
        if pick != "(Créer nouveau client)":
            client_id = pick.split(" • ")[-1].strip()

    if st.button("Enregistrer dossier complet"):
        if client_id is None:
            client_id = add_client(bien["client_nom"] or "Client", bien["client_tel"], bien["client_email"], bien["client_notes"])

        bien_id = add_bien(
            client_id=client_id,
            adresse=bien["adresse"],
            code_postal=bien["code_postal"],
            zone=bien["zone"],
            commune=bien["commune"],
            province=bien["province"],
            type_bien=bien["type_bien"],
            surface_habitable=bien["surface_habitable"],
            surface_totale=bien["surface_totale"],
            terrain_m2=bien["terrain_m2"],
            nb_facades=bien["nb_facades"],
            peb_lettre=bien["peb_lettre"],
            peb_kwh=bien["peb_kwh"],
            statut="Estimation",
            notes="Créé depuis estimation",
        )

        est_row = {
            "estimation_id": str(uuid.uuid4()),
            "bien_id": bien_id,
            "client_id": client_id,
            "date_estimation": today_iso(),
            "valeur_base": round(valeur_base, 0),
            "valeur_terrain": round(valeur_terrain, 0),
            "total_impacts": round(total_impacts, 0),
            "coef_expert_pct": float(bien["coef_expert_pct"]),
            "micro_coef_pct": round(micro_coef_pct, 2),
            "valeur_finale": round(valeur_finale, 0),
            "fourchette_basse": round(low, 0),
            "fourchette_haute": round(high, 0),
            "vente_rapide": round(vente_rapide, 0),
            "vente_lente": round(vente_lente, 0),
            "loyer_mensuel": round(loyer_mensuel, 0),
            "indice_global": round(indice, 1),
            "commune_marche": bien["commune"],
            "annee_marche": comp.get("year", ""),
            "evol_5ans": evol5 if evol5 is not None else "",
            "evol_10ans": evol10 if evol10 is not None else "",
        }
        add_estimation(est_row)
        st.success("Dossier enregistré ✅")

# =========================
# TAB 2) Marché & évolution
# =========================
with tabs[1]:
    st.subheader("Marché & évolution (Open Data)")
    if not bien["commune"]:
        st.info("Encode un code postal (idéal) ou une commune dans la barre de gauche.")
    else:
        try:
            df = filter_wallonie(load_odwb_prices_csv())
            col_commune, col_year, col_type, col_median, col_tx = detect_columns(df)
            want_kw = "maison" if bien["type_bien"] == "Maison" else ("appart" if bien["type_bien"] == "Appartement" else "commerce")
            series = odwb_series_commune(df, col_commune, col_year, col_type, col_median, bien["commune"], want_kw)
            if len(series) == 0:
                st.warning("Pas de série trouvée pour cette commune/type.")
            else:
                e5 = evolution_pct(series, 5)
                e10 = evolution_pct(series, 10)
                x1, x2, x3 = st.columns(3)
                x1.metric("Dernière année", str(int(series["annee"].max())))
                x2.metric("Evolution 5 ans", f"{e5:.1f}%" if e5 is not None else "—")
                x3.metric("Evolution 10 ans", f"{e10:.1f}%" if e10 is not None else "—")
                st.line_chart(series.set_index("annee")["prix_median"])
                st.dataframe(series, use_container_width=True)
        except Exception as e:
            st.error("Erreur chargement marché open data.")
            st.caption(str(e))

# =========================
# TAB 3) Historique estimations
# =========================
with tabs[2]:
    st.subheader("Historique des estimations")
    estim = st.session_state["estimations"]
    biens_df = st.session_state["biens"]
    clients_df = st.session_state["clients"]

    if len(estim) == 0:
        st.info("Aucune estimation enregistrée.")
    else:
        view = estim.merge(biens_df[["bien_id", "adresse", "code_postal", "zone", "commune", "type_bien", "statut"]], on="bien_id", how="left")
        view = view.merge(clients_df[["client_id", "nom", "email", "telephone"]], on="client_id", how="left")
        view = view.sort_values("date_estimation", ascending=False)
        st.dataframe(view, use_container_width=True)

        st.markdown("---")
        st.subheader("Modifier statut d’un bien (pipeline)")
        if len(biens_df) > 0:
            options = [f"{row['adresse']} • {row['code_postal']} • {row['type_bien']} • {row['bien_id']}" for _, row in biens_df.iterrows()]
            pick = st.selectbox("Sélectionner le bien", options)
            bien_id = pick.split(" • ")[-1].strip()
            statut = st.selectbox("Nouveau statut", ["Estimation", "Mandat signé", "En vente", "Vendu", "Perdu"], index=0)
            if st.button("Appliquer statut"):
                mask = st.session_state["biens"]["bien_id"] == bien_id
                st.session_state["biens"].loc[mask, "statut"] = statut
                st.success("Statut mis à jour ✅")

# =========================
# TAB 4) CRM Clients
# =========================
with tabs[3]:
    st.subheader("CRM Clients")
    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown("### Ajouter un client")
        nom = st.text_input("Nom", value="", key="crm_nom")
        tel = st.text_input("Téléphone", value="", key="crm_tel")
        email = st.text_input("Email", value="", key="crm_email")
        notes = st.text_area("Notes", value="", key="crm_notes", height=80)
        if st.button("Créer client"):
            add_client(nom or "Client", tel, email, notes)
            st.success("Client créé ✅")

    with c2:
        st.markdown("### Clients")
        st.dataframe(st.session_state["clients"].sort_values("date_creation", ascending=False), use_container_width=True)

    st.markdown("---")
    st.markdown("### Détails client")
    if len(st.session_state["clients"]) > 0:
        options = [f"{row['nom']} • {row['email']} • {row['telephone']} • {row['client_id']}" for _, row in st.session_state["clients"].iterrows()]
        pick = st.selectbox("Choisir client", options)
        cid = pick.split(" • ")[-1].strip()

        biens = st.session_state["biens"][st.session_state["biens"]["client_id"] == cid].copy()
        estim = st.session_state["estimations"][st.session_state["estimations"]["client_id"] == cid].copy()

        st.write("Biens du client:")
        st.dataframe(biens, use_container_width=True)

        st.write("Estimations du client:")
        st.dataframe(estim.sort_values("date_estimation", ascending=False), use_container_width=True)

# =========================
# TAB 5) Fiches biens
# =========================
with tabs[4]:
    st.subheader("Fiches biens")
    biens_df = st.session_state["biens"]
    clients_df = st.session_state["clients"]

    if len(biens_df) == 0:
        st.info("Aucun bien enregistré.")
    else:
        view = biens_df.merge(clients_df[["client_id", "nom", "email", "telephone"]], on="client_id", how="left")
        view = view.sort_values("date_creation", ascending=False)
        st.dataframe(view, use_container_width=True)

    st.markdown("---")
    st.subheader("Micro-coefficients par code postal (apprentissage)")
    st.dataframe(st.session_state["micro_cp"].sort_values("last_update", ascending=False), use_container_width=True)

# =========================
# TAB 6) Sauvegarde / Import
# =========================
with tabs[5]:
    st.subheader("Sauvegarde / Import (important)")
    st.caption("Streamlit peut réinitialiser la mémoire. Fais un export régulièrement (1 fichier), surtout sur iPad.")

    export_bytes = export_all_to_txt()
    st.download_button(
        "Exporter CRM + Biens + Estimations + MicroCP (1 fichier)",
        data=export_bytes,
        file_name=f"backup_priorite_immobiliere_{today_iso()}.txt",
        mime="text/plain",
    )

    up = st.file_uploader("Importer un export (restaure tout)", type=["txt"])
    if up is not None:
        try:
            import_from_txt(up.read())
            st.success("Import OK ✅ (tout restauré)")
        except Exception as e:
            st.error("Import impossible. Vérifie que c’est bien un export de l’app.")
            st.caption(str(e))
