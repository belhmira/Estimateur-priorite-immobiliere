import streamlit as st
from datetime import date, datetime
from io import BytesIO
from statistics import mean
import pandas as pd
import requests

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

AGENCE = "LA PRIORITE IMMOBILIERE"
EMAIL = "sbelhmira@gmail.com"

# Open Data Wallonie-Bruxelles (ODWB / WalStat) - dataset 234002 (prix immobilier résidentiel)
# Explore API v2.1 (swagger): https://www.odwb.be/api/explore/v2.1/swagger.json
ODWB_DATASET_ID = "234002"
ODWB_EXPORT_CSV_URL = f"https://www.odwb.be/api/explore/v2.1/catalog/datasets/{ODWB_DATASET_ID}/exports/csv?limit=-1&delimiter=%3B"


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


# ----------------------------
# PARAMS (impacts expert)
# ----------------------------
DEFAULT_PARAMS = {
    # Terrain €/m² automatique (Wallonie - bases)
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

    # Equipements (bonus)
    "eq_pv": 6000,
    "eq_clim": 2500,
    "eq_vmc": 2000,
    "eq_alarme": 1500,
    "eq_domotique": 2500,
    "eq_piscine": 15000,
    "eq_poele_pellet": 2000,

    # Caractéristiques
    "impact_par_chambre": 8000,
    "impact_par_sdb_supp": 6000,
    "impact_garage": 15000,
    "impact_par_place_parking": 8000,
    "impact_balcon": 5000,
    "impact_terrasse": 10000,
    "impact_jardin": 12000,
    "impact_cave": 4000,
    "grenier_amenageable_base": 5000,
    "grenier_amenageable_eur_m2": 120,

    # Vitrage / chauffage / cuisine / sdb / toiture / PEB (simple mais utile)
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
    "toit_moyen_coeff": 0.5,   # Moyenne = moitié du forfait
    "toit_factor": 0.7,        # impact appliqué

    "peb_A": 6000,
    "peb_B": 3000,
    "peb_C": 0,
    "peb_D": -3000,
    "peb_E": -6000,
    "peb_F": -9000,
    "peb_G": -12000,

    # Fourchette
    "fourchette_neutre_pct": 0.06,
}


# ----------------------------
# OPEN DATA (comparateurs)
# ----------------------------
@st.cache_data(show_spinner=False, ttl=60 * 60 * 12)
def load_odwb_prices_csv() -> pd.DataFrame:
    """
    Télécharge l'export CSV ODWB (dataset 234002). C'est du CSV ';'.
    """
    r = requests.get(ODWB_EXPORT_CSV_URL, timeout=30)
    r.raise_for_status()
    content = r.content.decode("utf-8", errors="replace")
    df = pd.read_csv(BytesIO(content.encode("utf-8")), sep=";")
    # Nettoyage colonnes
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def detect_columns(df: pd.DataFrame):
    """
    Essaye de deviner les colonnes utiles (commune, annee, type, prix median, prix m2, transactions)
    car le schéma peut varier selon publication.
    """
    cols = set(df.columns)

    def pick(candidates):
        for c in candidates:
            if c in cols:
                return c
        return None

    commune = pick(["commune", "commune_nom", "nom_commune", "localite", "municipalite"])
    annee = pick(["annee", "year"])
    typ = pick(["type", "type_bien", "bien", "categorie", "typologie"])
    # prix
    median_price = pick(["prix_median", "median_price", "median", "prixmedian", "prix_median_eur"])
    median_m2 = pick(["prix_median_m2", "median_m2", "prix_m2_median", "prix_m2"])
    transactions = pick(["transactions", "nb_transactions", "nombre_transactions", "volume"])

    return commune, annee, typ, median_price, median_m2, transactions


def filter_wallonie(df: pd.DataFrame) -> pd.DataFrame:
    # Si une colonne region existe, on filtre WALLONIE
    if "region" in df.columns:
        return df[df["region"].astype(str).str.upper().str.contains("WALL")].copy()
    return df.copy()


def normalize_str(s: str) -> str:
    return (s or "").strip().lower()


def get_communes_list(df: pd.DataFrame, col_commune: str) -> list:
    if not col_commune:
        return []
    communes = sorted({str(x).strip() for x in df[col_commune].dropna().unique() if str(x).strip()})
    return communes


def latest_year(df: pd.DataFrame, col_year: str) -> int | None:
    if not col_year:
        return None
    yrs = pd.to_numeric(df[col_year], errors="coerce").dropna()
    if len(yrs) == 0:
        return None
    return int(yrs.max())


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
    rb = rendement_brut(type_bien, params)
    return (valeur * rb) / 12.0


# ----------------------------
# IMPACTS EXPERT
# ----------------------------
def impact_humidite(hum: str, params: dict) -> float:
    m = {
        "Non": float(params["hum_non"]),
        "Legere": float(params["hum_legere"]),
        "Importante": float(params["hum_importante"]),
    }
    return float(m.get(hum, 0.0))


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
    m = {
        "Bon": float(params["poste_bon"]),
        "Moyen": float(params["poste_moyen"]),
        "Mauvais": float(params["poste_mauvais"]),
    }
    return float(m.get(etat, 0.0))


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
    m = {
        "Simple": float(params["vitrage_simple"]),
        "Double ancien": float(params["vitrage_double_ancien"]),
        "Double recent": float(params["vitrage_double_recent"]),
        "Triple": float(params["vitrage_triple"]),
    }
    return float(m.get(v, 0.0))


def impact_chauffage(c: str, params: dict) -> float:
    m = {
        "Pompe a chaleur": float(params["chauff_pac"]),
        "Gaz condensation": float(params["chauff_gaz_cond"]),
        "Mazout": float(params["chauff_mazout"]),
        "Electrique": float(params["chauff_electrique"]),
        "Ancien systeme / poele seul": float(params["chauff_ancien"]),
    }
    return float(m.get(c, 0.0))


def impact_cuisine(etat: str, params: dict) -> float:
    m = {
        "Bonne": float(params["cuisine_bonne"]),
        "A moderniser": float(params["cuisine_moderniser"]),
        "A remplacer": float(params["cuisine_remplacer"]),
    }
    return float(m.get(etat, 0.0))


def impact_sdb(etat: str, params: dict) -> float:
    m = {
        "Bonne": float(params["sdb_bonne"]),
        "A moderniser": float(params["sdb_moderniser"]),
        "A remplacer": float(params["sdb_remplacer"]),
    }
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
    m = {
        "A": float(params["peb_A"]),
        "B": float(params["peb_B"]),
        "C": float(params["peb_C"]),
        "D": float(params["peb_D"]),
        "E": float(params["peb_E"]),
        "F": float(params["peb_F"]),
        "G": float(params["peb_G"]),
    }
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
    if bien["cave"]: total += float(params["impact_cave"])
    if bien["grenier_amenageable"]:
        total += float(params["grenier_amenageable_base"]) + float(bien["grenier_amenageable_surface_m2"]) * float(params["grenier_amenageable_eur_m2"])
    return total


def indice_global(bien: dict) -> float:
    # indice simple /10 basé sur postes + humidité + PEB (utilisé pour fourchette)
    map_etat = {"Bon": 9, "Moyen": 6, "Mauvais": 3}
    hum_map = {"Non": 10, "Legere": 6, "Importante": 2}
    peb_map = {"A": 10, "B": 9, "C": 8, "D": 6, "E": 4, "F": 3, "G": 2}

    notes = [
        map_etat.get(bien["etat_maconnerie"], 6),
        map_etat.get(bien["etat_toiture_poste"], 6),
        map_etat.get(bien["etat_electricite"], 6),
        map_etat.get(bien["etat_plomberie"], 6),
        map_etat.get(bien["etat_sols"], 6),
        map_etat.get(bien["etat_facades"], 6),
        hum_map.get(bien["humidite"], 6),
        peb_map.get(bien["peb_lettre"], 8),
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

    return valeur * (1 - low_pct), valeur * (1 + high_pct), low_pct, high_pct


# ----------------------------
# PDF 3 pages
# ----------------------------
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


def build_pdf(bien, comparateurs, impacts, valeur_base, valeur_terrain, valeur_finale,
              loyer_mensuel, indice, low, high, coef_expert_pct, justif) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Page 1
    draw_header(c, "Rapport d'estimation - Expert", "Synthèse vendeur (page 1/3)")
    y = h - 165
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Bien"); y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Client: {safe_text(bien['client'], 60) or '-'}"); y -= 14
    c.drawString(55, y, f"Adresse: {safe_text(bien['adresse'], 120) or '-'}"); y -= 14
    c.drawString(55, y, f"Commune (comparateurs): {safe_text(bien['commune'], 60) or '-'}"); y -= 14
    c.drawString(55, y, f"Province: {bien['province']}  |  Type: {bien['type_bien']}"); y -= 14
    c.drawString(55, y, f"Année construction: {bien['annee_construction'] or '-'}"); y -= 14

    c.drawString(55, y, f"Surface habitable: {bien['surface_habitable']:.0f} m²  |  Surface totale: {bien['surface_totale']:.0f} m²"); y -= 14
    if bien["type_bien"] == "Maison":
        c.drawString(55, y, f"Terrain: {bien['terrain_m2']:.0f} m²  |  Valeur terrain auto: {euro(valeur_terrain)}"); y -= 14

    # Surfaces par étage
    if bien["surfaces_etages"] and sum(bien["surfaces_etages"]) > 0:
        c.drawString(55, y, "Surfaces par étage: " + " / ".join([f"{s:.0f} m²" for s in bien["surfaces_etages"]]))
        y -= 14

    c.drawString(55, y, f"Humidité: {bien['humidite']}  |  PEB: {bien['peb_lettre']}" + (f" ({bien['peb_kwh']:.0f})" if bien["peb_kwh"] else "")); y -= 14
    c.drawString(55, y, f"Chauffage: {bien['chauffage']}  |  Vitrage: {bien['vitrage']}"); y -= 14
    c.drawString(55, y, f"Cuisine: {bien['etat_cuisine']}  |  Salle de bain: {bien['etat_sdb']}"); y -= 14

    c.drawString(55, y, f"Chambres: {bien['chambres']}  |  SDB: {bien['sdb']}"); y -= 14
    c.drawString(55, y, f"Garage: {'Oui' if bien['garage'] else 'Non'}  |  Parking: {bien['nb_places_parking']}"); y -= 14
    c.drawString(55, y, f"Terrasse: {'Oui' if bien['terrasse'] else 'Non'}  |  Balcon: {'Oui' if bien['balcon'] else 'Non'}"); y -= 14
    c.drawString(55, y, f"Jardin: {'Oui' if bien['jardin'] else 'Non'}  |  Cave: {'Oui' if bien['cave'] else 'Non'}"); y -= 14

    y -= 6
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"Valeur finale estimée: {euro(valeur_finale)}"); y -= 18
    c.setFont("Helvetica", 11)
    c.drawString(40, y, f"Fourchette conseillée: {euro(low)}  →  {euro(high)}"); y -= 16
    c.drawString(40, y, f"Valeur locative mensuelle (indicative): {euro(loyer_mensuel)}"); y -= 16
    c.drawString(40, y, f"Indice global: {indice:.1f}/10   |   Coef expert: {coef_expert_pct:+.1f}%"); y -= 16
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(40, y, f"Justification coef expert: {safe_text(justif, 110) or '-'}"); y -= 18

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Document indicatif - basé sur open data (WalStat/Statbel) + analyse technique.")
    c.showPage()

    # Page 2: Détail calcul
    draw_header(c, "Détail des calculs", "Impacts expert (page 2/3)")
    y = h - 165
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Base marché (comparateurs open data)"); y -= 18
    c.setFont("Helvetica", 10)

    if comparateurs.get("ok"):
        c.drawString(55, y, f"Année données: {comparateurs.get('year') or '-'}"); y -= 14
        c.drawString(55, y, f"Prix médian maison commune: {euro(comparateurs.get('median_house', 0))}"); y -= 14
        c.drawString(55, y, f"Prix médian appartement commune: {euro(comparateurs.get('median_apartment', 0))}"); y -= 14
        if comparateurs.get("transactions") is not None:
            c.drawString(55, y, f"Transactions (indicatif): {comparateurs.get('transactions')}"); y -= 14
    else:
        c.drawString(55, y, "Comparateurs: données non trouvées (vérifier l'orthographe de la commune)."); y -= 14

    y -= 6
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Valeur de base"); y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Valeur base (commune/type + surfaces): {euro(valeur_base)}"); y -= 14
    if bien["type_bien"] == "Maison":
        c.drawString(55, y, f"Valeur terrain auto: {euro(valeur_terrain)}"); y -= 14

    y -= 6
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

    # Page 3: Méthodologie
    draw_header(c, "Méthodologie", "Explications (page 3/3)")
    y = h - 165
    c.setFont("Helvetica", 10)
    txt = [
        "1) Comparateurs automatiques: prix médians par commune (open data WalStat/Statbel via ODWB).",
        "2) Valeur de base: combinaison médiane commune + surfaces (habitable/totale) et type de bien.",
        "3) Expertise technique: impacts chiffrés par poste (toiture, élec, humidité, etc.) + équipements.",
        "4) Valeur terrain: estimation automatique selon province (base interne paramétrable).",
        "5) Valeur locative: rendement brut indicatif selon type de bien.",
        "6) Coef expert: ajustement final (rue, nuisances, vue, attractivité, rareté) + justification.",
        "",
        "Note: l'open data est souvent au niveau COMMUNE (pas toujours au niveau village/quartier).",
        "Pour du micro-quartier, encode les ventes réelles dans l'historique de l'app.",
    ]
    for line in txt:
        c.drawString(40, y, line)
        y -= 14

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Outil interne - La Priorite Immobiliere.")
    c.save()

    buf.seek(0)
    return buf.getvalue()


# ----------------------------
# STREAMLIT UI
# ----------------------------
st.set_page_config(page_title="Estimateur Expert - La Priorite Immobiliere", layout="wide")
st.title("Estimateur Expert (Wallonie) - La Priorite Immobiliere")

if "params" not in st.session_state:
    st.session_state["params"] = DEFAULT_PARAMS.copy()

params = st.session_state["params"]

tabs = st.tabs(["1) Encodage bien", "2) Comparateurs (Open data)", "3) Synthèse + PDF", "4) Paramètres"])


# Sidebar dossier
with st.sidebar:
    st.subheader("Dossier")
    client = st.text_input("Client", value="")
    adresse = st.text_input("Adresse complète", value="")

    province = st.selectbox("Province", ["Hainaut", "Namur", "Liege", "Brabant_wallon", "Luxembourg"])
    type_bien = st.selectbox("Type de bien", ["Maison", "Appartement", "Commerce"])

    st.subheader("Surfaces")
    surface_habitable = st.number_input("Surface habitable (m²)", min_value=0.0, value=100.0, step=1.0)
    surface_totale = st.number_input("Surface totale (m²)", min_value=1.0, value=120.0, step=1.0)

    terrain_m2 = 0.0
    if type_bien == "Maison":
        terrain_m2 = st.number_input("Terrain (m²)", min_value=0.0, value=0.0, step=10.0)

    st.subheader("Surfaces par étage")
    nb_etages = st.number_input("Nombre d'étages", min_value=1, max_value=10, value=1, step=1)
    surfaces_etages = []
    for i in range(int(nb_etages)):
        surfaces_etages.append(
            st.number_input(f"Surface étage {i+1} (m²)", min_value=0.0, value=0.0, step=5.0, key=f"surf_{i}")
        )

    st.subheader("Construction")
    annee_construction = st.number_input("Année de construction", min_value=0, max_value=2100, value=0, step=1)

    st.subheader("Humidité")
    humidite = st.selectbox("Présence d'humidité", ["Non", "Legere", "Importante"], index=0)

    st.subheader("Techniques")
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
    etat_facades = st.selectbox("Façades", ["Bon", "Moyen", "Mauvais"], index=0)

    st.subheader("Pièces")
    chambres = st.number_input("Nombre de chambres", min_value=0, value=2, step=1)
    sdb = st.number_input("Nombre de salles de bain", min_value=0, value=1, step=1)

    st.subheader("Annexes")
    nb_places_parking = st.number_input("Places parking", min_value=0, value=0, step=1)
    garage = st.checkbox("Garage", value=False)
    balcon = st.checkbox("Balcon", value=False)
    terrasse = st.checkbox("Terrasse", value=False)
    jardin = st.checkbox("Jardin", value=False)
    cave = st.checkbox("Cave", value=False)
    grenier_amenageable = st.checkbox("Grenier aménageable", value=False)
    grenier_amenageable_surface_m2 = st.number_input("Surface grenier aménageable (m²)", min_value=0.0, value=0.0, step=5.0, disabled=not grenier_amenageable)

    st.subheader("Equipements")
    eq_pv = st.checkbox("Panneaux photovoltaïques", value=False)
    eq_clim = st.checkbox("Climatisation", value=False)
    eq_vmc = st.checkbox("VMC", value=False)
    eq_alarme = st.checkbox("Alarme", value=False)
    eq_domotique = st.checkbox("Domotique", value=False)
    eq_piscine = st.checkbox("Piscine", value=False)
    eq_poele_pellet = st.checkbox("Poêle / pellet", value=False)

    st.subheader("Ajustement expert")
    coef_expert_pct = st.slider("Coefficient expert (%)", float(params["coef_expert_min"]), float(params["coef_expert_max"]), value=0.0, step=0.5)
    justif_coef = st.text_area("Justification coef expert", value="", height=70)


# Bien dict
bien = {
    "client": client,
    "adresse": adresse,
    "province": province,
    "type_bien": type_bien,

    "surface_habitable": float(surface_habitable),
    "surface_totale": float(surface_totale),
    "terrain_m2": float(terrain_m2),

    "surfaces_etages": [float(x) for x in surfaces_etages],

    "annee_construction": int(annee_construction),
    "humidite": humidite,

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

    "chambres": int(chambres),
    "sdb": int(sdb),

    "nb_places_parking": int(nb_places_parking),
    "garage": bool(garage),
    "balcon": bool(balcon),
    "terrasse": bool(terrasse),
    "jardin": bool(jardin),
    "cave": bool(cave),
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

    "coef_expert_pct": float(coef_expert_pct),
    "justif_coef": justif_coef,
}


# ----------------------------
# TAB 1: Encodage
# ----------------------------
with tabs[0]:
    st.subheader("Résumé encodage")
    c1, c2, c3 = st.columns(3)
    c1.metric("Surface habitable", f"{bien['surface_habitable']:.0f} m²")
    c2.metric("Surface totale", f"{bien['surface_totale']:.0f} m²")
    if type_bien == "Maison":
        c3.metric("Terrain", f"{bien['terrain_m2']:.0f} m²")
    else:
        c3.metric("Terrain", "—")

    if sum(bien["surfaces_etages"]) > 0:
        st.write("Surfaces par étage :", " / ".join([f"{s:.0f} m²" for s in bien["surfaces_etages"]]))
        if abs(sum(bien["surfaces_etages"]) - bien["surface_totale"]) > 5:
            st.warning("⚠️ Surfaces par étage ≠ surface totale (écart > 5 m²).")


# ----------------------------
# TAB 2: Comparateurs Open Data
# ----------------------------
with tabs[1]:
    st.subheader("Comparateurs automatiques (Open Data Wallonie)")
    st.caption("Données WalStat/Statbel via ODWB (niveau commune).")

    try:
        df = load_odwb_prices_csv()
        df = filter_wallonie(df)
        col_commune, col_year, col_type, col_median, col_m2, col_tx = detect_columns(df)

        if not col_commune or not col_year:
            st.error("Schéma open data inattendu: impossible de détecter 'commune' et/ou 'année'.")
            st.stop()

        communes = get_communes_list(df, col_commune)
        commune_sel = st.selectbox("Commune (pour comparateurs)", communes, index=0 if communes else None)
        bien["commune"] = commune_sel

        year_latest = latest_year(df, col_year)
        year_sel = st.selectbox("Année (open data)", sorted(df[col_year].dropna().unique(), reverse=True), index=0)
        # Filtre commune+année
        dff = df[(df[col_commune].astype(str).str.strip() == str(commune_sel).strip()) &
                 (df[col_year].astype(str) == str(year_sel))].copy()

        # On essaye de sortir médian maison/appartement si possible
        comp = {"ok": False, "year": year_sel}

        def pick_val(d, wanted):
            if not col_type or not col_median:
                return None
            tmp = d[d[col_type].astype(str).str.lower().str.contains(wanted)]
            if len(tmp) == 0:
                return None
            v = pd.to_numeric(tmp[col_median], errors="coerce").dropna()
            return float(v.iloc[0]) if len(v) else None

        # Heuristiques sur libellés type
        median_house = pick_val(dff, "maison") or pick_val(dff, "house")
        median_apartment = pick_val(dff, "appart") or pick_val(dff, "apartment")

        # Si col_median existe mais pas de type -> on prend médiane globale
        if (median_house is None) and (median_apartment is None) and col_median and len(dff) > 0:
            v = pd.to_numeric(dff[col_median], errors="coerce").dropna()
            if len(v):
                # on met ça en "maison" par défaut
                median_house = float(v.iloc[0])

        transactions = None
        if col_tx and len(dff) > 0:
            tx = pd.to_numeric(dff[col_tx], errors="coerce").dropna()
            if len(tx):
                transactions = int(tx.iloc[0])

        comp["median_house"] = median_house or 0
        comp["median_apartment"] = median_apartment or 0
        comp["transactions"] = transactions
        comp["ok"] = True

        a1, a2, a3 = st.columns(3)
        a1.metric("Prix médian maison (commune)", euro(comp["median_house"]))
        a2.metric("Prix médian appartement (commune)", euro(comp["median_apartment"]))
        a3.metric("Transactions (indicatif)", str(comp["transactions"]) if comp["transactions"] is not None else "—")

        st.write("Aperçu des lignes open data filtrées :")
        st.dataframe(dff.head(20), use_container_width=True)

    except Exception as e:
        st.error("Impossible de charger l'open data (ODWB). Réessaie plus tard.")
        st.caption(str(e))


# ----------------------------
# TAB 3: Synthèse + PDF
# ----------------------------
with tabs[2]:
    st.subheader("Estimation expert + valeur locative + PDF vendeur (3 pages)")

    # 1) Comparateurs (si disponibles)
    comp = {"ok": False, "year": None, "median_house": 0, "median_apartment": 0, "transactions": None}
    commune_for_report = ""

    try:
        df = load_odwb_prices_csv()
        df = filter_wallonie(df)
        col_commune, col_year, col_type, col_median, col_m2, col_tx = detect_columns(df)

        if col_commune and col_year and "commune" in bien and bien["commune"]:
            commune_for_report = bien["commune"]
            y_latest = latest_year(df, col_year)
            if y_latest is not None:
                dff = df[(df[col_commune].astype(str).str.strip() == str(commune_for_report).strip()) &
                         (pd.to_numeric(df[col_year], errors="coerce") == y_latest)].copy()

                def pick_val(d, wanted):
                    if not col_type or not col_median:
                        return None
                    tmp = d[d[col_type].astype(str).str.lower().str.contains(wanted)]
                    if len(tmp) == 0:
                        return None
                    v = pd.to_numeric(tmp[col_median], errors="coerce").dropna()
                    return float(v.iloc[0]) if len(v) else None

                median_house = pick_val(dff, "maison") or pick_val(dff, "house")
                median_apartment = pick_val(dff, "appart") or pick_val(dff, "apartment")

                transactions = None
                if col_tx and len(dff) > 0:
                    tx = pd.to_numeric(dff[col_tx], errors="coerce").dropna()
                    if len(tx):
                        transactions = int(tx.iloc[0])

                comp = {
                    "ok": True,
                    "year": y_latest,
                    "median_house": median_house or 0,
                    "median_apartment": median_apartment or 0,
                    "transactions": transactions
                }
    except Exception:
        pass

    # 2) Valeur base (expert simple): médiane commune + ajustement surfaces
    #    (si pas dispo, on retombe sur une base "surface_totale * 2000" indicative)
    if type_bien == "Maison" and comp["ok"] and comp["median_house"] > 0:
        base_commune = comp["median_house"]
    elif type_bien == "Appartement" and comp["ok"] and comp["median_apartment"] > 0:
        base_commune = comp["median_apartment"]
    else:
        base_commune = bien["surface_totale"] * 2000  # fallback

    # Ajustement surfaces: si surface_totale > 120, +1% par tranche de 20m² (cap)
    surf_adj = 1.0 + clamp((bien["surface_totale"] - 120) / 20.0, -2.0, 3.0) * 0.01
    valeur_base = base_commune * surf_adj

    # 3) Terrain auto
    valeur_terrain = terrain_auto(bien["province"], bien["terrain_m2"], params) if type_bien == "Maison" else 0.0

    # 4) Impacts expert
    impacts = {}
    impacts["Humidité"] = impact_humidite(bien["humidite"], params)
    impacts["Année construction"] = impact_annee(bien["annee_construction"], params)

    impacts["Maçonnerie/fissures"] = impact_poste(bien["etat_maconnerie"], params)
    impacts["Toiture (poste)"] = impact_poste(bien["etat_toiture_poste"], params)
    impacts["Electricité"] = impact_poste(bien["etat_electricite"], params)
    impacts["Plomberie"] = impact_poste(bien["etat_plomberie"], params)
    impacts["Sols"] = impact_poste(bien["etat_sols"], params)
    impacts["Façades"] = impact_poste(bien["etat_facades"], params)

    impacts["Toiture (état)"] = impact_toiture(bien["toiture_etat"], params)
    impacts["Chauffage"] = impact_chauffage(bien["chauffage"], params)
    impacts["Vitrage"] = impact_vitrage(bien["vitrage"], params)
    impacts["PEB"] = impact_peb(bien["peb_lettre"], params)
    impacts["Cuisine"] = impact_cuisine(bien["etat_cuisine"], params)
    impacts["Salle de bain"] = impact_sdb(bien["etat_sdb"], params)

    impacts["Chambres"] = impact_chambres(type_bien, bien["chambres"], params)
    impacts["Salles de bain (nb)"] = impact_sdb_count(bien["sdb"], params)
    impacts["Annexes (parking/garage/terrasse…)"] = impact_annexes(bien, params)

    impacts["Equipements"] = impact_equipements(bien["equipements"], params)

    total_impacts = sum(impacts.values())

    # 5) Valeur finale
    valeur_tech = valeur_base + valeur_terrain + total_impacts
    coef = float(bien["coef_expert_pct"]) / 100.0
    valeur_finale = valeur_tech * (1.0 + coef)

    # 6) Locatif
    loyer_mensuel = locatif_mensuel(valeur_finale, type_bien, params)

    # 7) Indice + fourchette
    indice = indice_global(bien)
    low, high, low_pct, high_pct = fourchette(valeur_finale, indice, params)

    # Affichage
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Valeur base (comparateurs)", euro(valeur_base))
    m2.metric("Valeur terrain auto", euro(valeur_terrain))
    m3.metric("Total impacts expert", euro(total_impacts))
    m4.metric("Valeur finale", euro(valeur_finale))

    n1, n2, n3 = st.columns(3)
    n1.metric("Indice global", f"{indice:.1f} / 10")
    n2.metric("Fourchette basse", euro(low))
    n3.metric("Fourchette haute", euro(high))

    st.metric("Valeur locative mensuelle (indicative)", euro(loyer_mensuel))

    with st.expander("Voir impacts (poste par poste)"):
        st.dataframe(pd.DataFrame([{"poste": k, "impact": v} for k, v in impacts.items()]), use_container_width=True)

    # PDF
    if "commune" not in bien:
        bien["commune"] = ""

    pdf = build_pdf(
        bien=bien,
        comparateurs=comp,
        impacts=impacts,
        valeur_base=valeur_base,
        valeur_terrain=valeur_terrain,
        valeur_finale=valeur_finale,
        loyer_mensuel=loyer_mensuel,
        indice=indice,
        low=low,
        high=high,
        coef_expert_pct=float(bien["coef_expert_pct"]),
        justif=bien["justif_coef"],
    )

    st.download_button(
        "Télécharger rapport vendeur (PDF - 3 pages)",
        data=pdf,
        file_name=f"Rapport_Expert_{date.today().isoformat()}.pdf",
        mime="application/pdf",
    )


# ----------------------------
# TAB 4: Paramètres
# ----------------------------
with tabs[3]:
    st.subheader("Paramètres (si tu veux ajuster)")
    st.caption("Tu peux modifier les impacts (humidité, postes, équipements, rendement locatif, terrain €/m²).")

    c1, c2 = st.columns(2)

    with c1:
        st.write("Terrain €/m² (maisons)")
        params["terrain_Hainaut"] = st.number_input("Hainaut", value=int(params["terrain_Hainaut"]), step=5)
        params["terrain_Namur"] = st.number_input("Namur", value=int(params["terrain_Namur"]), step=5)
        params["terrain_Liege"] = st.number_input("Liège", value=int(params["terrain_Liege"]), step=5)
        params["terrain_Brabant_wallon"] = st.number_input("Brabant wallon", value=int(params["terrain_Brabant_wallon"]), step=5)
        params["terrain_Luxembourg"] = st.number_input("Luxembourg", value=int(params["terrain_Luxembourg"]), step=5)

        st.write("Humidité")
        params["hum_legere"] = st.number_input("Humidité légère (impact €)", value=int(params["hum_legere"]), step=1000)
        params["hum_importante"] = st.number_input("Humidité importante (impact €)", value=int(params["hum_importante"]), step=1000)

    with c2:
        st.write("Rendement brut locatif")
        params["rendement_brut_maison"] = st.number_input("Maison (%)", value=float(params["rendement_brut_maison"] * 100), step=0.1) / 100.0
        params["rendement_brut_appartement"] = st.number_input("Appartement (%)", value=float(params["rendement_brut_appartement"] * 100), step=0.1) / 100.0
        params["rendement_brut_commerce"] = st.number_input("Commerce (%)", value=float(params["rendement_brut_commerce"] * 100), step=0.1) / 100.0

        st.write("Postes (Moyen/Mauvais)")
        params["poste_moyen"] = st.number_input("Poste moyen (impact €)", value=int(params["poste_moyen"]), step=1000)
        params["poste_mauvais"] = st.number_input("Poste mauvais (impact €)", value=int(params["poste_mauvais"]), step=1000)

    st.session_state["params"] = params
