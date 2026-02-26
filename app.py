import streamlit as st
from datetime import date, datetime
from io import BytesIO
from statistics import mean

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

try:
    from PIL import Image
except Exception:
    Image = None


AGENCE = "LA PRIORITE IMMOBILIERE"
EMAIL = "sbelhmira@gmail.com"
LOGO_PATH = "assets/logo.png"


# -----------------------------
# Helpers
# -----------------------------
def euro(x: float) -> str:
    s = f"{x:,.0f}".replace(",", " ")
    return f"{s} €"


def safe_text(x: str, max_len: int = 120) -> str:
    return (x or "").strip()[:max_len]


def draw_header(c: canvas.Canvas, title: str, subtitle: str):
    w, h = A4
    try:
        if Image is not None:
            img = Image.open(LOGO_PATH)
            c.drawImage(ImageReader(img), 40, h - 120, width=140, height=80, mask="auto")
    except Exception:
        pass

    c.setFont("Helvetica-Bold", 14)
    c.drawString(200, h - 55, title)
    c.setFont("Helvetica", 10)
    c.drawString(200, h - 72, AGENCE)
    c.drawString(200, h - 86, f"Contact: {EMAIL}")
    c.drawString(200, h - 100, f"Date: {date.today().strftime('%d/%m/%Y')}")
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(200, h - 114, subtitle)
    c.line(40, h - 130, w - 40, h - 130)


# -----------------------------
# Defaults (référentiel + paramètres)
# -----------------------------
DEFAULT_ZONES = [
    {"zone": "Namur - Centre", "type": "Maison", "base_eur_m2": 2150, "terrain_eur_m2": 20, "commerce_eur_m2": 0},
    {"zone": "Namur - Centre", "type": "Appartement", "base_eur_m2": 2350, "terrain_eur_m2": 0, "commerce_eur_m2": 0},
    {"zone": "Charleroi", "type": "Maison", "base_eur_m2": 1550, "terrain_eur_m2": 12, "commerce_eur_m2": 0},
    {"zone": "Charleroi", "type": "Appartement", "base_eur_m2": 1700, "terrain_eur_m2": 0, "commerce_eur_m2": 0},
    {"zone": "Liege - Axe commercial", "type": "Commerce", "base_eur_m2": 0, "terrain_eur_m2": 0, "commerce_eur_m2": 2400},
]

DEFAULT_PARAMS = {
    # Dégressivité surface
    "seuil_degressif_m2": 160,
    "degressif_pct": 0.06,

    # Fourchette "neutre" (sera modulée par l'indice)
    "fourchette_neutre_pct": 0.06,

    # Toiture (forfait + option grenier)
    "toit_forfait_sans_grenier": 18000,
    "toit_base_avec_grenier": 10000,
    "toit_eur_m2_grenier": 130,
    "toit_impact_factor": 0.70,
    "toit_etat_moyen_coeff": 0.50,

    # Chauffage (impacts)
    "chauff_pac": 8000,
    "chauff_gaz_cond": 3000,
    "chauff_mazout": -5000,
    "chauff_electrique": -8000,
    "chauff_ancien": -10000,

    # Cuisine (impacts)
    "cuisine_bonne": 0,
    "cuisine_moderniser": -5000,
    "cuisine_remplacer": -12000,

    # Salle de bain état (impacts)
    "sdb_bonne": 0,
    "sdb_moderniser": -4000,
    "sdb_remplacer": -9000,

    # Châssis / vitrages (impacts)
    "vitrage_simple": -8000,
    "vitrage_double_ancien": -3000,
    "vitrage_double_recent": 0,
    "vitrage_triple": 4000,

    # PEB (impacts)
    "peb_A": 6000,
    "peb_B": 3000,
    "peb_C": 0,
    "peb_D": -3000,
    "peb_E": -6000,
    "peb_F": -9000,
    "peb_G": -12000,

    # Chambres
    "impact_par_chambre": 8000,

    # Nombre de salles de bain (référence 1)
    "impact_par_sdb_supp": 6000,

    # Étage appartement (étage + ascenseur)
    "etage_avec_ascenseur_bonus": 4000,
    "etage_sans_ascenseur_malus_par_niveau": -2500,
    "etage_rdc_malus": 0,

    # Parking / Garage
    "impact_par_place_parking": 8000,
    "impact_garage": 15000,

    # Balcon / Terrasse
    "impact_balcon": 5000,
    "impact_terrasse": 10000,

    # Jardin / Cave
    "impact_jardin": 12000,
    "impact_cave": 4000,

    # Grenier aménageable (surface)
    "grenier_amenageable_base": 5000,
    "grenier_amenageable_eur_m2": 120,

    # Coefficient expert
    "coef_expert_min": -3.0,
    "coef_expert_max": 3.0,
}


# -----------------------------
# Calculs
# -----------------------------
def apply_degressivity(base_eur_m2: float, surface: float, params: dict) -> float:
    if surface > float(params["seuil_degressif_m2"]):
        return base_eur_m2 * (1.0 - float(params["degressif_pct"]))
    return base_eur_m2


def calc_marche(zone_row: dict, bien: dict, params: dict) -> dict:
    base_m2 = apply_degressivity(float(zone_row["base_eur_m2"]), float(bien["surface"]), params)
    valeur_batie = float(bien["surface"]) * base_m2

    valeur_terrain = 0.0
    if bien["type"] == "Maison":
        valeur_terrain = float(bien["terrain"]) * float(zone_row["terrain_eur_m2"])

    # Commerce : si base_eur_m2 = 0, on prend commerce_eur_m2
    if bien["type"] == "Commerce" and float(zone_row.get("base_eur_m2", 0)) == 0:
        base_m2 = float(zone_row.get("commerce_eur_m2", 0))
        valeur_batie = float(bien["surface"]) * base_m2

    valeur_marche = valeur_batie + valeur_terrain
    return {
        "base_eur_m2": base_m2,
        "valeur_batie": valeur_batie,
        "valeur_terrain": valeur_terrain,
        "valeur_marche": valeur_marche
    }


def calc_toiture_impact(bien: dict, params: dict) -> float:
    etat = bien["toiture_etat"]
    if etat == "Parfaite":
        return 0.0

    has_grenier = bool(bien["toiture_grenier"])
    if not has_grenier:
        calc = float(params["toit_forfait_sans_grenier"])
    else:
        surf = float(bien["toiture_surface_grenier"])
        calc = float(params["toit_base_avec_grenier"]) + surf * float(params["toit_eur_m2_grenier"])

    if etat == "Moyenne":
        calc = calc * float(params["toit_etat_moyen_coeff"])

    impact = calc * float(params["toit_impact_factor"])
    return -abs(impact)


def calc_chauffage_impact(bien: dict, params: dict) -> float:
    mapping = {
        "Pompe a chaleur": float(params["chauff_pac"]),
        "Gaz condensation": float(params["chauff_gaz_cond"]),
        "Mazout": float(params["chauff_mazout"]),
        "Electrique": float(params["chauff_electrique"]),
        "Ancien systeme / poele seul": float(params["chauff_ancien"]),
    }
    return float(mapping.get(bien["chauffage_type"], 0.0))


def calc_cuisine_impact(bien: dict, params: dict) -> float:
    mapping = {
        "Bonne": float(params["cuisine_bonne"]),
        "A moderniser": float(params["cuisine_moderniser"]),
        "A remplacer": float(params["cuisine_remplacer"]),
    }
    return float(mapping.get(bien["cuisine_etat"], 0.0))


def calc_sdb_etat_impact(bien: dict, params: dict) -> float:
    mapping = {
        "Bonne": float(params["sdb_bonne"]),
        "A moderniser": float(params["sdb_moderniser"]),
        "A remplacer": float(params["sdb_remplacer"]),
    }
    return float(mapping.get(bien["sdb_etat"], 0.0))


def calc_vitrage_impact(bien: dict, params: dict) -> float:
    mapping = {
        "Simple": float(params["vitrage_simple"]),
        "Double ancien": float(params["vitrage_double_ancien"]),
        "Double recent": float(params["vitrage_double_recent"]),
        "Triple": float(params["vitrage_triple"]),
    }
    return float(mapping.get(bien["vitrage_type"], 0.0))


def calc_peb_impact(bien: dict, params: dict) -> float:
    l = (bien.get("peb_lettre") or "C").strip().upper()
    mapping = {
        "A": float(params["peb_A"]),
        "B": float(params["peb_B"]),
        "C": float(params["peb_C"]),
        "D": float(params["peb_D"]),
        "E": float(params["peb_E"]),
        "F": float(params["peb_F"]),
        "G": float(params["peb_G"]),
    }
    return float(mapping.get(l, 0.0))


def calc_chambres_impact(bien: dict, params: dict) -> float:
    if bien["type"] == "Commerce":
        return 0.0
    ref = 3 if bien["type"] == "Maison" else 2
    nb = int(bien.get("nb_chambres", ref))
    delta = nb - ref
    return float(delta) * float(params["impact_par_chambre"])


def calc_sdb_count_impact(bien: dict, params: dict) -> float:
    ref = 1
    nb = int(bien.get("nb_sdb", ref))
    delta = nb - ref
    return float(delta) * float(params["impact_par_sdb_supp"])


def calc_etage_appart_impact(bien: dict, params: dict) -> float:
    # Uniquement pour appartement
    if bien["type"] != "Appartement":
        return 0.0

    etage = int(bien.get("etage", 0))
    asc = bool(bien.get("ascenseur", False))

    if etage == 0:
        return float(params["etage_rdc_malus"])

    if asc:
        return float(params["etage_avec_ascenseur_bonus"])

    return float(params["etage_sans_ascenseur_malus_par_niveau"]) * float(etage)


def calc_parking_garage_impact(bien: dict, params: dict) -> float:
    nb = int(bien.get("nb_places_parking", 0))
    impact = nb * float(params["impact_par_place_parking"])
    if bool(bien.get("garage", False)):
        impact += float(params["impact_garage"])
    return float(impact)


def calc_balcon_terrasse_impact(bien: dict, params: dict) -> float:
    impact = 0.0
    if bool(bien.get("balcon", False)):
        impact += float(params["impact_balcon"])
    if bool(bien.get("terrasse", False)):
        impact += float(params["impact_terrasse"])
    return float(impact)


def calc_jardin_cave_grenier_impact(bien: dict, params: dict) -> float:
    impact = 0.0
    if bool(bien.get("jardin", False)):
        impact += float(params["impact_jardin"])
    if bool(bien.get("cave", False)):
        impact += float(params["impact_cave"])
    if bool(bien.get("grenier_amenageable", False)):
        s = float(bien.get("grenier_amenageable_surface_m2", 0.0))
        impact += float(params["grenier_amenageable_base"]) + s * float(params["grenier_amenageable_eur_m2"])
    return float(impact)


def calc_indice(bien: dict) -> float:
    # Indice /10 basé sur : toiture, chauffage, cuisine, sdb, vitrage, PEB
    toiture_map = {"Parfaite": 10, "Moyenne": 6, "Mauvaise": 2}
    chauff_map = {
        "Pompe a chaleur": 9,
        "Gaz condensation": 8,
        "Mazout": 5,
        "Electrique": 3,
        "Ancien systeme / poele seul": 2,
    }
    cuisine_map = {"Bonne": 8, "A moderniser": 5, "A remplacer": 2}
    sdb_map = {"Bonne": 8, "A moderniser": 5, "A remplacer": 2}
    vitrage_map = {"Simple": 2, "Double ancien": 5, "Double recent": 8, "Triple": 9}
    peb_map = {"A": 10, "B": 9, "C": 8, "D": 6, "E": 4, "F": 3, "G": 2}

    notes = [
        float(toiture_map.get(bien["toiture_etat"], 6)),
        float(chauff_map.get(bien["chauffage_type"], 6)),
        float(cuisine_map.get(bien["cuisine_etat"], 5)),
        float(sdb_map.get(bien["sdb_etat"], 5)),
        float(vitrage_map.get(bien["vitrage_type"], 6)),
        float(peb_map.get((bien.get("peb_lettre") or "C").upper(), 6)),
    ]
    return float(mean(notes))


def fourchette_from_indice(valeur_finale: float, indice: float, params: dict):
    neutre = float(params["fourchette_neutre_pct"])
    if indice >= 8.0:
        low_pct, high_pct = 0.05, 0.08
    elif indice >= 6.0:
        low_pct, high_pct = neutre, neutre
    elif indice >= 4.0:
        low_pct, high_pct = 0.08, 0.05
    else:
        low_pct, high_pct = 0.10, 0.04

    low = valeur_finale * (1.0 - low_pct)
    high = valeur_finale * (1.0 + high_pct)
    return low, high, low_pct, high_pct


def build_pdf_3pages(bien: dict, zone_row: dict, marche: dict, impacts: dict, indice: float,
                     coef_expert_pct: float, valeur_tech: float, valeur_finale: float,
                     low: float, high: float, low_pct: float, high_pct: float) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # PAGE 1 - Synthèse
    draw_header(c, "Rapport d'estimation - Vente", "Synthese vendeur (page 1/3)")
    y = h - 165

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Bien")
    y -= 18

    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Client: {safe_text(bien['client'], 60) or '-'}"); y -= 14
    c.drawString(55, y, f"Adresse: {safe_text(bien['adresse'], 80) or '-'}"); y -= 14
    c.drawString(55, y, f"Commune: {safe_text(bien['commune'], 40) or '-'}"); y -= 14
    c.drawString(55, y, f"Zone: {zone_row['zone']}  |  Type: {bien['type']}"); y -= 14
    c.drawString(55, y, f"Surface: {bien['surface']:.0f} m2" + (f"  |  Terrain: {bien['terrain']:.0f} m2" if bien["type"] == "Maison" else "")); y -= 14
    c.drawString(55, y, f"Chambres: {int(bien.get('nb_chambres', 0))}  |  Salles de bain: {int(bien.get('nb_sdb', 0))}"); y -= 14

    if bien["type"] == "Appartement":
        c.drawString(55, y, f"Etage: {int(bien.get('etage', 0))}  |  Ascenseur: {'Oui' if bien.get('ascenseur') else 'Non'}"); y -= 14

    c.drawString(55, y, f"PEB: {bien['peb_lettre']}" + (f" ({bien['peb_kwh']:.0f} kWh/m2.an)" if bien['peb_kwh'] else "")); y -= 14
    c.drawString(55, y, f"Vitrage: {bien['vitrage_type']}"); y -= 14

    c.drawString(55, y, f"Parking: {int(bien.get('nb_places_parking', 0))}  |  Garage: {'Oui' if bien.get('garage') else 'Non'}"); y -= 14
    c.drawString(55, y, f"Balcon: {'Oui' if bien.get('balcon') else 'Non'}  |  Terrasse: {'Oui' if bien.get('terrasse') else 'Non'}"); y -= 14
    c.drawString(
        55, y,
        "Jardin: " + ("Oui" if bien.get("jardin") else "Non")
        + "  |  Cave: " + ("Oui" if bien.get("cave") else "Non")
        + "  |  Grenier amenageable: " + ("Oui" if bien.get("grenier_amenageable") else "Non")
        + (f" ({bien.get('grenier_amenageable_surface_m2', 0):.0f} m2)" if bien.get("grenier_amenageable") else "")
    )
    y -= 14

    # Surfaces par étage (infos)
    sp = bien.get("surfaces_etages", [])
    if sp and sum(sp) > 0:
        c.drawString(55, y, "Surfaces par etage: " + " / ".join([f"{s:.0f} m2" for s in sp]))
        y -= 14

    y -= 6
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, f"Indice global d'etat: {indice:.1f} / 10")
    y -= 22

    c.setFont("Helvetica-Bold", 18)
    c.drawString(55, y, f"Valeur finale estimee: {euro(valeur_finale)}")
    y -= 22
    c.setFont("Helvetica", 11)
    c.drawString(55, y, f"Fourchette recommandee: {euro(low)}  ->  {euro(high)}")
    y -= 16
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(55, y, f"Fourchette ajustee par l'indice: -{int(low_pct*100)}% / +{int(high_pct*100)}%")
    y -= 18

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"Coefficient d'appreciation experte: {coef_expert_pct:+.1f}%")
    y -= 14
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Justification: {safe_text(bien['justif_coef'], 95) or '-'}")
    y -= 18

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Document indicatif - base sur un referentiel interne et une analyse technique (outil interne).")
    c.showPage()

    # PAGE 2 - Détail
    draw_header(c, "Detail des calculs", "Marche + impacts (page 2/3)")
    y = h - 165

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Marche (referentiel)")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Base zone/type: {euro(marche['base_eur_m2'])} par m2"); y -= 14
    c.drawString(55, y, f"Valeur batie: {euro(marche['valeur_batie'])}"); y -= 14
    if bien["type"] == "Maison":
        c.drawString(55, y, f"Valeur terrain: {euro(marche['valeur_terrain'])}"); y -= 14
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, f"Valeur marche theorique: {euro(marche['valeur_marche'])}")
    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Impacts appliques automatiquement")
    y -= 18
    c.setFont("Helvetica", 10)

    lines = [
        (f"Toiture ({bien['toiture_etat']})", impacts["toiture"]),
        (f"Chauffage ({bien['chauffage_type']})", impacts["chauffage"]),
        (f"Chassis/Vitrage ({bien['vitrage_type']})", impacts["vitrage"]),
        (f"PEB ({bien['peb_lettre']})", impacts["peb"]),
        (f"Cuisine ({bien['cuisine_etat']})", impacts["cuisine"]),
        (f"Salle de bain - etat ({bien['sdb_etat']})", impacts["sdb_etat"]),
        (f"Chambres (nb={int(bien.get('nb_chambres', 0))})", impacts["chambres"]),
        (f"Nb salles de bain (nb={int(bien.get('nb_sdb', 0))})", impacts["sdb_count"]),
        (f"Etage/Ascenseur (etage={int(bien.get('etage', 0))}, asc={'Oui' if bien.get('ascenseur') else 'Non'})", impacts["etage_appart"]),
        ("Parking/Garage", impacts["parking_garage"]),
        ("Balcon/Terrasse", impacts["balcon_terrasse"]),
        ("Jardin/Cave/Grenier amenageable", impacts["jardin_cave_grenier"]),
    ]

    for label, val in lines:
        if bien["type"] != "Appartement" and label.startswith("Etage/Ascenseur"):
            continue
        c.drawString(55, y, f"{label}: {euro(val)}")
        y -= 14

    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, f"Total impacts: {euro(impacts['total'])}")
    y -= 18

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Synthese calcul")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Valeur technique = Valeur marche + impacts = {euro(valeur_tech)}"); y -= 14
    c.drawString(55, y, f"Valeur finale = Valeur technique x (1 + coef expert) = {euro(valeur_finale)}"); y -= 18

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Les impacts et coefficients sont parametrables dans l'outil interne.")
    c.showPage()

    # PAGE 3 - Méthodologie
    draw_header(c, "Methodologie", "Explications (page 3/3)")
    y = h - 165

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Approche")
    y -= 18
    c.setFont("Helvetica", 10)
    lines3 = [
        "1) Valeur marche: referentiel interne (zone/type) applique a la surface (degressivite si grande surface).",
        "2) Terrain (maisons): valorisation par m2 selon la zone.",
        "3) Impacts: technique + caracteristiques (chambres, sdb, annexes) appliques automatiquement.",
        "4) Indice global (/10): calcule sur toiture, chauffage, cuisine, sdb, vitrage, PEB; il influence la fourchette.",
        "5) Coefficient d'appreciation experte: ajustement final (quartier, nuisances, vue, attractivite).",
    ]
    for ln in lines3:
        c.drawString(55, y, ln)
        y -= 14

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Notes")
    y -= 18
    c.setFont("Helvetica", 10)
    notes = [
        "Le referentiel est a mettre a jour regulierement selon ton marche local.",
        "Les impacts representent l'effet sur la valeur, pas un devis.",
        "La fourchette depend aussi de la demande au moment de la mise en vente.",
    ]
    for ln in notes:
        c.drawString(55, y, f"- {ln}")
        y -= 14

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Outil interne - La Priorite Immobiliere.")
    c.save()

    buf.seek(0)
    return buf.getvalue()


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Estimateur Expert - La Priorite Immobiliere", layout="wide")
st.title("Estimateur Expert - La Priorite Immobiliere (outil interne)")

if "zones" not in st.session_state:
    st.session_state["zones"] = DEFAULT_ZONES.copy()
if "params" not in st.session_state:
    st.session_state["params"] = DEFAULT_PARAMS.copy()
if "history" not in st.session_state:
    st.session_state["history"] = []

tabs = st.tabs(["1) Marche", "2) Technique", "3) Synthese", "4) Historique"])

params = st.session_state["params"]
zones = st.session_state["zones"]

# Sidebar
with st.sidebar:
    st.subheader("Identite dossier")
    client = st.text_input("Client (interne)", value="")
    adresse = st.text_input("Adresse", value="")
    commune = st.text_input("Commune", value="")

    st.subheader("Bien")
    type_bien = st.selectbox("Type", ["Maison", "Appartement", "Commerce"])

    zone_names = sorted(list({z["zone"] for z in zones}))
    zone_sel = st.selectbox("Zone", zone_names)

    candidates = [z for z in zones if z["zone"] == zone_sel and z["type"] == type_bien]
    zone_row = candidates[0] if candidates else None
    if zone_row is None:
        st.error("Aucune ligne referentiel pour cette zone + ce type. Ajoute-la dans l'onglet Marche > Referentiel.")

    surface = st.number_input("Surface totale (m2)", min_value=1.0, value=100.0, step=1.0)
    terrain = 0.0
    if type_bien == "Maison":
        terrain = st.number_input("Terrain (m2)", min_value=0.0, value=0.0, step=10.0)

    nb_chambres = st.number_input("Nombre de chambres", min_value=0, value=2, step=1)
    nb_sdb = st.number_input("Nombre de salles de bain", min_value=0, value=1, step=1)

    # Étage/ascenseur (appart)
    etage = st.number_input("Etage (0 = RDC)", min_value=0, value=0, step=1)
    ascenseur = st.checkbox("Ascenseur", value=False)

    st.subheader("Annexes")
    nb_places_parking = st.number_input("Places parking (nb)", min_value=0, value=0, step=1)
    garage = st.checkbox("Garage", value=False)
    balcon = st.checkbox("Balcon", value=False)
    terrasse = st.checkbox("Terrasse", value=False)

    st.subheader("Espaces + dependances")
    jardin = st.checkbox("Jardin", value=False)
    cave = st.checkbox("Cave", value=False)

    grenier_amenageable = st.checkbox("Grenier amenageable", value=False)
    grenier_amenageable_surface_m2 = st.number_input(
        "Surface grenier amenageable (m2)",
        min_value=0.0, value=0.0, step=5.0,
        disabled=not grenier_amenageable
    )

    st.subheader("Surfaces par etage")
    nb_etages = st.number_input("Nombre d'etages (1 = un seul niveau)", min_value=1, value=1, step=1)
    surfaces_etages = []
    for i in range(int(nb_etages)):
        s = st.number_input(
            f"Surface etage {i+1} (m2)",
            min_value=0.0, value=0.0, step=5.0,
            key=f"surf_etage_{i+1}"
        )
        surfaces_etages.append(float(s))

    st.subheader("Appreciation experte (visible)")
    coef_expert_pct = st.slider(
        "Coefficient expert (%)",
        float(params["coef_expert_min"]), float(params["coef_expert_max"]),
        value=0.0, step=0.5
    )
    justif_coef = st.text_area("Justification", value="", height=80)

# Bien dict
bien = {
    "client": client,
    "adresse": adresse,
    "commune": commune,
    "type": type_bien,
    "zone": zone_sel,
    "surface": float(surface),
    "terrain": float(terrain),
    "nb_chambres": int(nb_chambres),
    "nb_sdb": int(nb_sdb),
    "etage": int(etage),
    "ascenseur": bool(ascenseur),
    "nb_places_parking": int(nb_places_parking),
    "garage": bool(garage),
    "balcon": bool(balcon),
    "terrasse": bool(terrasse),
    "jardin": bool(jardin),
    "cave": bool(cave),
    "grenier_amenageable": bool(grenier_amenageable),
    "grenier_amenageable_surface_m2": float(grenier_amenageable_surface_m2),
    "nb_etages": int(nb_etages),
    "surfaces_etages": list(surfaces_etages),
    "coef_expert_pct": float(coef_expert_pct),
    "justif_coef": justif_coef,

    # Technique defaults (sera rempli onglet Technique)
    "toiture_grenier": False,
    "toiture_surface_grenier": 0.0,
    "toiture_etat": "Parfaite",
    "chauffage_type": "Gaz condensation",
    "cuisine_etat": "Bonne",
    "sdb_etat": "Bonne",
    "vitrage_type": "Double recent",
    "peb_lettre": "C",
    "peb_kwh": 0.0,
}


# ---------------- TAB 1 : MARCHE ----------------
with tabs[0]:
    st.subheader("Referentiel (ta grille)")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.write("Grille actuelle (modifiable).")
        st.dataframe(st.session_state["zones"], use_container_width=True)

    with col2:
        st.write("Ajouter une ligne referentiel")
        nz = st.text_input("Nouvelle zone", value="")
        nt = st.selectbox("Type (referentiel)", ["Maison", "Appartement", "Commerce"], key="ref_type")
        nb = st.number_input("Base €/m2 (habitable)", min_value=0, value=0, step=50)
        ntm2 = st.number_input("Terrain €/m2 (maison)", min_value=0, value=0, step=1)
        ncm2 = st.number_input("Commerce €/m2", min_value=0, value=0, step=50)
        if st.button("Ajouter au referentiel"):
            if nz.strip():
                st.session_state["zones"].append({
                    "zone": nz.strip(),
                    "type": nt,
                    "base_eur_m2": int(nb),
                    "terrain_eur_m2": int(ntm2),
                    "commerce_eur_m2": int(ncm2),
                })
                st.success("Ligne ajoutee.")

    st.markdown("---")
    st.subheader("Parametres (base)")
    cA, cB, cC = st.columns(3)
    with cA:
        params["seuil_degressif_m2"] = st.number_input("Seuil degressif (m2)", value=int(params["seuil_degressif_m2"]), step=10)
        params["degressif_pct"] = st.number_input("Degressif (%)", value=float(params["degressif_pct"] * 100)) / 100.0
    with cB:
        params["fourchette_neutre_pct"] = st.number_input("Fourchette neutre (+/- %)", value=float(params["fourchette_neutre_pct"] * 100)) / 100.0
    with cC:
        params["coef_expert_min"] = st.number_input("Coef expert min (%)", value=float(params["coef_expert_min"]), step=0.5)
        params["coef_expert_max"] = st.number_input("Coef expert max (%)", value=float(params["coef_expert_max"]), step=0.5)
    st.session_state["params"] = params

    st.markdown("---")
    st.subheader("Calcul marche (dossier actuel)")
    if zone_row is None:
        st.stop()

    marche = calc_marche(zone_row, bien, params)
    m1, m2, m3 = st.columns(3)
    m1.metric("Base €/m2 appliquee", euro(marche["base_eur_m2"]))
    m2.metric("Valeur batie", euro(marche["valeur_batie"]))
    m3.metric("Valeur marche theorique", euro(marche["valeur_marche"]))
    if type_bien == "Maison":
        st.caption(f"Valeur terrain: {euro(marche['valeur_terrain'])}")


# ---------------- TAB 2 : TECHNIQUE ----------------
with tabs[1]:
    st.subheader("Analyse technique (details)")

    st.markdown("### Toiture")
    t1, t2, t3 = st.columns(3)
    with t1:
        toiture_grenier = st.checkbox("Grenier present (toiture)", value=False)
    with t2:
        toiture_surface_grenier = st.number_input("Surface grenier (toiture) (m2)", min_value=0.0, value=0.0, step=5.0, disabled=not toiture_grenier)
    with t3:
        toiture_etat = st.selectbox("Etat toiture", ["Parfaite", "Moyenne", "Mauvaise"])

    st.markdown("### Chauffage")
    chauffage_type = st.selectbox(
        "Type de chauffage",
        ["Pompe a chaleur", "Gaz condensation", "Mazout", "Electrique", "Ancien systeme / poele seul"]
    )

    st.markdown("### Chassis / vitrages")
    vitrage_type = st.selectbox("Type de vitrage", ["Simple", "Double ancien", "Double recent", "Triple"])

    st.markdown("### PEB (Belgique)")
    peb_lettre = st.selectbox("PEB (lettre)", ["A", "B", "C", "D", "E", "F", "G"], index=2)
    peb_kwh = st.number_input("PEB (kWh/m2.an) - optionnel", min_value=0.0, value=0.0, step=1.0)

    st.markdown("### Cuisine / Salle de bain (etat)")
    c1, c2 = st.columns(2)
    with c1:
        cuisine_etat = st.selectbox("Etat cuisine", ["Bonne", "A moderniser", "A remplacer"])
    with c2:
        sdb_etat = st.selectbox("Etat salle de bain", ["Bonne", "A moderniser", "A remplacer"])

    # Apply to bien
    bien["toiture_grenier"] = bool(toiture_grenier)
    bien["toiture_surface_grenier"] = float(toiture_surface_grenier)
    bien["toiture_etat"] = toiture_etat
    bien["chauffage_type"] = chauffage_type
    bien["vitrage_type"] = vitrage_type
    bien["peb_lettre"] = peb_lettre
    bien["peb_kwh"] = float(peb_kwh)
    bien["cuisine_etat"] = cuisine_etat
    bien["sdb_etat"] = sdb_etat

    st.markdown("---")
    st.subheader("Parametres (impacts ajustables)")
    with st.expander("Modifier les impacts (interne)", expanded=False):
        colA, colB, colC = st.columns(3)
        with colA:
            st.write("Toiture")
            params["toit_forfait_sans_grenier"] = st.number_input("Forfait sans grenier", value=int(params["toit_forfait_sans_grenier"]), step=500)
            params["toit_base_avec_grenier"] = st.number_input("Base avec grenier", value=int(params["toit_base_avec_grenier"]), step=500)
            params["toit_eur_m2_grenier"] = st.number_input("EUR/m2 grenier (toiture)", value=int(params["toit_eur_m2_grenier"]), step=5)
            params["toit_impact_factor"] = st.number_input("Impact factor (ex 0.70)", value=float(params["toit_impact_factor"]), step=0.05)
            params["toit_etat_moyen_coeff"] = st.number_input("Coeff etat Moyenne (ex 0.50)", value=float(params["toit_etat_moyen_coeff"]), step=0.05)

            st.write("Chambres / SDB")
            params["impact_par_chambre"] = st.number_input("Impact par chambre (delta vs ref)", value=int(params["impact_par_chambre"]), step=500)
            params["impact_par_sdb_supp"] = st.number_input("Impact par SDB supplementaire", value=int(params["impact_par_sdb_supp"]), step=500)

        with colB:
            st.write("Chauffage / Vitrage")
            params["chauff_pac"] = st.number_input("PAC", value=int(params["chauff_pac"]), step=500)
            params["chauff_gaz_cond"] = st.number_input("Gaz condensation", value=int(params["chauff_gaz_cond"]), step=500)
            params["chauff_mazout"] = st.number_input("Mazout", value=int(params["chauff_mazout"]), step=500)
            params["chauff_electrique"] = st.number_input("Electrique", value=int(params["chauff_electrique"]), step=500)
            params["chauff_ancien"] = st.number_input("Ancien systeme", value=int(params["chauff_ancien"]), step=500)

            params["vitrage_simple"] = st.number_input("Vitrage simple", value=int(params["vitrage_simple"]), step=500)
            params["vitrage_double_ancien"] = st.number_input("Double ancien", value=int(params["vitrage_double_ancien"]), step=500)
            params["vitrage_double_recent"] = st.number_input("Double recent", value=int(params["vitrage_double_recent"]), step=500)
            params["vitrage_triple"] = st.number_input("Triple", value=int(params["vitrage_triple"]), step=500)

            st.write("Etage appart")
            params["etage_avec_ascenseur_bonus"] = st.number_input("Etage avec ascenseur (bonus)", value=int(params["etage_avec_ascenseur_bonus"]), step=500)
            params["etage_sans_ascenseur_malus_par_niveau"] = st.number_input("Sans ascenseur (malus/etage)", value=int(params["etage_sans_ascenseur_malus_par_niveau"]), step=500)
            params["etage_rdc_malus"] = st.number_input("RDC (malus/bonus)", value=int(params["etage_rdc_malus"]), step=500)

        with colC:
            st.write("PEB / Cuisine / SDB etat")
            params["peb_A"] = st.number_input("PEB A", value=int(params["peb_A"]), step=500)
            params["peb_B"] = st.number_input("PEB B", value=int(params["peb_B"]), step=500)
            params["peb_C"] = st.number_input("PEB C", value=int(params["peb_C"]), step=500)
            params["peb_D"] = st.number_input("PEB D", value=int(params["peb_D"]), step=500)
            params["peb_E"] = st.number_input("PEB E", value=int(params["peb_E"]), step=500)
            params["peb_F"] = st.number_input("PEB F", value=int(params["peb_F"]), step=500)
            params["peb_G"] = st.number_input("PEB G", value=int(params["peb_G"]), step=500)

            params["cuisine_moderniser"] = st.number_input("Cuisine a moderniser", value=int(params["cuisine_moderniser"]), step=500)
            params["cuisine_remplacer"] = st.number_input("Cuisine a remplacer", value=int(params["cuisine_remplacer"]), step=500)
            params["sdb_moderniser"] = st.number_input("SDB etat a moderniser", value=int(params["sdb_moderniser"]), step=500)
            params["sdb_remplacer"] = st.number_input("SDB etat a remplacer", value=int(params["sdb_remplacer"]), step=500)

            st.write("Parking / Balcon / Jardin / Grenier amenageable")
            params["impact_par_place_parking"] = st.number_input("Impact/place parking", value=int(params["impact_par_place_parking"]), step=500)
            params["impact_garage"] = st.number_input("Impact garage", value=int(params["impact_garage"]), step=500)
            params["impact_balcon"] = st.number_input("Impact balcon", value=int(params["impact_balcon"]), step=500)
            params["impact_terrasse"] = st.number_input("Impact terrasse", value=int(params["impact_terrasse"]), step=500)
            params["impact_jardin"] = st.number_input("Impact jardin", value=int(params["impact_jardin"]), step=500)
            params["impact_cave"] = st.number_input("Impact cave", value=int(params["impact_cave"]), step=500)
            params["grenier_amenageable_base"] = st.number_input("Grenier amenageable (base)", value=int(params["grenier_amenageable_base"]), step=500)
            params["grenier_amenageable_eur_m2"] = st.number_input("Grenier amenageable (EUR/m2)", value=int(params["grenier_amenageable_eur_m2"]), step=5)

        st.session_state["params"] = params

    # Compute preview impacts + indice
    impacts = {
        "toiture": calc_toiture_impact(bien, params),
        "chauffage": calc_chauffage_impact(bien, params),
        "vitrage": calc_vitrage_impact(bien, params),
        "peb": calc_peb_impact(bien, params),
        "cuisine": calc_cuisine_impact(bien, params),
        "sdb_etat": calc_sdb_etat_impact(bien, params),
        "chambres": calc_chambres_impact(bien, params),
        "sdb_count": calc_sdb_count_impact(bien, params),
        "etage_appart": calc_etage_appart_impact(bien, params),
        "parking_garage": calc_parking_garage_impact(bien, params),
        "balcon_terrasse": calc_balcon_terrasse_impact(bien, params),
        "jardin_cave_grenier": calc_jardin_cave_grenier_impact(bien, params),
    }

    impacts["total"] = (
        impacts["toiture"] + impacts["chauffage"] + impacts["vitrage"] + impacts["peb"]
        + impacts["cuisine"] + impacts["sdb_etat"]
        + impacts["chambres"] + impacts["sdb_count"] + impacts["etage_appart"]
        + impacts["parking_garage"] + impacts["balcon_terrasse"] + impacts["jardin_cave_grenier"]
    )

    indice = calc_indice(bien)

    # Affichage (2 lignes)
    r1 = st.columns(6)
    r1[0].metric("Toiture", euro(impacts["toiture"]))
    r1[1].metric("Chauffage", euro(impacts["chauffage"]))
    r1[2].metric("Vitrage", euro(impacts["vitrage"]))
    r1[3].metric("PEB", euro(impacts["peb"]))
    r1[4].metric("Parking/Garage", euro(impacts["parking_garage"]))
    r1[5].metric("Balcon/Terrasse", euro(impacts["balcon_terrasse"]))

    r2 = st.columns(6)
    r2[0].metric("Cuisine", euro(impacts["cuisine"]))
    r2[1].metric("SDB etat", euro(impacts["sdb_etat"]))
    r2[2].metric("Chambres", euro(impacts["chambres"]))
    r2[3].metric("Nb SDB", euro(impacts["sdb_count"]))
    r2[4].metric("Etage appart", euro(impacts["etage_appart"]) if bien["type"] == "Appartement" else "0 €")
    r2[5].metric("Jardin/Cave/Grenier", euro(impacts["jardin_cave_grenier"]))

    r3 = st.columns(3)
    r3[0].metric("Total impacts", euro(impacts["total"]))
    r3[1].metric("Indice global", f"{indice:.1f} / 10")
    # Contrôle surfaces par étage
    total_etages = sum(bien["surfaces_etages"])
    if total_etages > 0 and abs(total_etages - bien["surface"]) > 5:
        r3[2].warning("Surfaces par etage ≠ surface totale")
    else:
        r3[2].success("Surfaces par etage OK (ou non renseigne)")


# ---------------- TAB 3 : SYNTHESE ----------------
with tabs[2]:
    st.subheader("Synthese experte (calcul final)")
    if zone_row is None:
        st.stop()

    marche = calc_marche(zone_row, bien, params)

    impacts = {
        "toiture": calc_toiture_impact(bien, params),
        "chauffage": calc_chauffage_impact(bien, params),
        "vitrage": calc_vitrage_impact(bien, params),
        "peb": calc_peb_impact(bien, params),
        "cuisine": calc_cuisine_impact(bien, params),
        "sdb_etat": calc_sdb_etat_impact(bien, params),
        "chambres": calc_chambres_impact(bien, params),
        "sdb_count": calc_sdb_count_impact(bien, params),
        "etage_appart": calc_etage_appart_impact(bien, params),
        "parking_garage": calc_parking_garage_impact(bien, params),
        "balcon_terrasse": calc_balcon_terrasse_impact(bien, params),
        "jardin_cave_grenier": calc_jardin_cave_grenier_impact(bien, params),
    }

    impacts["total"] = (
        impacts["toiture"] + impacts["chauffage"] + impacts["vitrage"] + impacts["peb"]
        + impacts["cuisine"] + impacts["sdb_etat"]
        + impacts["chambres"] + impacts["sdb_count"] + impacts["etage_appart"]
        + impacts["parking_garage"] + impacts["balcon_terrasse"] + impacts["jardin_cave_grenier"]
    )

    indice = calc_indice(bien)
    valeur_tech = marche["valeur_marche"] + impacts["total"]
    coef = float(bien["coef_expert_pct"]) / 100.0
    valeur_finale = valeur_tech * (1.0 + coef)

    low, high, low_pct, high_pct = fourchette_from_indice(valeur_finale, indice, params)

    # contrôle surfaces par étage
    total_etages = sum(bien["surfaces_etages"])
    if total_etages > 0 and abs(total_etages - bien["surface"]) > 5:
        st.warning("Attention: la somme des surfaces par etage ne correspond pas a la surface totale (ecart > 5 m2).")

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Valeur marche", euro(marche["valeur_marche"]))
    a2.metric("Total impacts", euro(impacts["total"]))
    a3.metric("Valeur technique", euro(valeur_tech))
    a4.metric("Valeur finale", euro(valeur_finale))

    b1, b2, b3 = st.columns(3)
    b1.metric("Indice global", f"{indice:.1f} / 10")
    b2.metric("Fourchette basse", euro(low))
    b3.metric("Fourchette haute", euro(high))
    st.caption(f"Fourchette ajustee: -{int(low_pct*100)}% / +{int(high_pct*100)}% (selon indice)")

    pdf = build_pdf_3pages(
        bien=bien,
        zone_row=zone_row,
        marche=marche,
        impacts=impacts,
        indice=indice,
        coef_expert_pct=float(bien["coef_expert_pct"]),
        valeur_tech=valeur_tech,
        valeur_finale=valeur_finale,
        low=low,
        high=high,
        low_pct=low_pct,
        high_pct=high_pct,
    )

    st.download_button(
        "Telecharger rapport vendeur (PDF - 3 pages)",
        data=pdf,
        file_name=f"Rapport_Expert_{date.today().isoformat()}.pdf",
        mime="application/pdf",
    )

    st.markdown("---")
    st.subheader("Sauvegarde (Historique)")
    colS1, colS2 = st.columns([1, 2])
    with colS1:
        if st.button("Enregistrer cette estimation"):
            record = {
                "date_estimation": date.today().isoformat(),
                "client": safe_text(bien["client"], 60),
                "adresse": safe_text(bien["adresse"], 80),
                "commune": safe_text(bien["commune"], 40),
                "zone": zone_row["zone"],
                "type_bien": bien["type"],
                "surface_m2": round(float(bien["surface"]), 1),
                "terrain_m2": round(float(bien["terrain"]), 1),
                "nb_chambres": int(bien["nb_chambres"]),
                "nb_sdb": int(bien["nb_sdb"]),
                "etage": int(bien["etage"]),
                "ascenseur": bool(bien["ascenseur"]),
                "peb_lettre": bien["peb_lettre"],
                "peb_kwh": round(float(bien["peb_kwh"]), 0),
                "vitrage_type": bien["vitrage_type"],
                "toiture_etat": bien["toiture_etat"],
                "toiture_grenier": bool(bien["toiture_grenier"]),
                "toiture_surface_grenier": round(float(bien["toiture_surface_grenier"]), 1),
                "chauffage_type": bien["chauffage_type"],
                "cuisine_etat": bien["cuisine_etat"],
                "sdb_etat": bien["sdb_etat"],
                "nb_places_parking": int(bien["nb_places_parking"]),
                "garage": bool(bien["garage"]),
                "balcon": bool(bien["balcon"]),
                "terrasse": bool(bien["terrasse"]),
                "jardin": bool(bien["jardin"]),
                "cave": bool(bien["cave"]),
                "grenier_amenageable": bool(bien["grenier_amenageable"]),
                "grenier_amenageable_surface_m2": round(float(bien["grenier_amenageable_surface_m2"]), 1),
                "nb_etages": int(bien["nb_etages"]),
                "surfaces_etages": " / ".join([str(int(s)) for s in bien.get("surfaces_etages", [])]),
                "indice_etat": round(float(indice), 1),
                "coef_expert_pct": round(float(bien["coef_expert_pct"]), 1),
                "justif_coef": safe_text(bien["justif_coef"], 120),
                "valeur_marche": round(float(marche["valeur_marche"]), 0),
                "impact_total": round(float(impacts["total"]), 0),
                "valeur_finale": round(float(valeur_finale), 0),
                "fourchette_basse": round(float(low), 0),
                "fourchette_haute": round(float(high), 0),
                "prix_vendu": "",
                "date_vente": "",
            }
            st.session_state["history"].insert(0, record)
            st.success("Estimation enregistree dans l'historique.")
    with colS2:
        st.info("Ensuite: onglet Historique pour encoder le prix vendu.")


# ---------------- TAB 4 : HISTORIQUE ----------------
with tabs[3]:
    st.subheader("Historique des estimations (interne)")
    hist = st.session_state["history"]
    if not hist:
        st.warning("Aucune estimation enregistree pour le moment.")
        st.stop()

    st.dataframe(hist, use_container_width=True)

    st.markdown("---")
    st.subheader("Mettre a jour un dossier (prix vendu)")
    idx = st.number_input(
        "Numero de ligne (0 = la plus recente)",
        min_value=0, max_value=max(0, len(hist) - 1),
        value=0, step=1
    )
    rec = hist[int(idx)]

    c1, c2, c3 = st.columns(3)
    with c1:
        prix_vendu = st.text_input("Prix vendu (EUR)", value=str(rec.get("prix_vendu", "")))
    with c2:
        date_vente = st.text_input("Date vente (YYYY-MM-DD)", value=str(rec.get("date_vente", "")))
    with c3:
        if st.button("Enregistrer prix vendu"):
            dv = date_vente.strip()
            if dv:
                try:
                    datetime.strptime(dv, "%Y-%m-%d")
                except Exception:
                    st.error("Date vente invalide. Format attendu: YYYY-MM-DD")
                    st.stop()
            rec["prix_vendu"] = prix_vendu.strip()
            rec["date_vente"] = dv
            st.session_state["history"][int(idx)] = rec
            st.success("Mise a jour faite.")
