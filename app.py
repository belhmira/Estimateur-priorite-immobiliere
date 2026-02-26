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
# Defaults (ta grille + paramètres)
# -----------------------------
DEFAULT_ZONES = [
    # zone, type, base €/m2, terrain €/m2 (maison), commerce €/m2 (si besoin)
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
    "toit_impact_factor": 0.70,       # on applique 70% en impact valeur
    "toit_etat_moyen_coeff": 0.50,    # Moyenne = 50% du calcul

    # Chauffage (impacts ajustables)
    "chauff_pac": 8000,
    "chauff_gaz_cond": 3000,
    "chauff_mazout": -5000,
    "chauff_electrique": -8000,
    "chauff_ancien": -10000,

    # Cuisine (impacts)
    "cuisine_bonne": 0,
    "cuisine_moderniser": -5000,
    "cuisine_remplacer": -12000,

    # Salle de bain (impacts)
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

    # Coefficient expert max (en %)
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
    # Valeur marché (base) + terrain si maison
    base_m2 = apply_degressivity(float(zone_row["base_eur_m2"]), float(bien["surface"]), params)
    valeur_batie = float(bien["surface"]) * base_m2

    valeur_terrain = 0.0
    if bien["type"] == "Maison":
        valeur_terrain = float(bien["terrain"]) * float(zone_row["terrain_eur_m2"])

    # Commerce : si base_eur_m2 = 0, on prend commerce_eur_m2 (au m²)
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
    t = bien["chauffage_type"]
    mapping = {
        "Pompe a chaleur": float(params["chauff_pac"]),
        "Gaz condensation": float(params["chauff_gaz_cond"]),
        "Mazout": float(params["chauff_mazout"]),
        "Electrique": float(params["chauff_electrique"]),
        "Ancien systeme / poele seul": float(params["chauff_ancien"]),
    }
    return float(mapping.get(t, 0.0))


def calc_cuisine_impact(bien: dict, params: dict) -> float:
    et = bien["cuisine_etat"]
    mapping = {
        "Bonne": float(params["cuisine_bonne"]),
        "A moderniser": float(params["cuisine_moderniser"]),
        "A remplacer": float(params["cuisine_remplacer"]),
    }
    return float(mapping.get(et, 0.0))


def calc_sdb_impact(bien: dict, params: dict) -> float:
    et = bien["sdb_etat"]
    mapping = {
        "Bonne": float(params["sdb_bonne"]),
        "A moderniser": float(params["sdb_moderniser"]),
        "A remplacer": float(params["sdb_remplacer"]),
    }
    return float(mapping.get(et, 0.0))


def calc_vitrage_impact(bien: dict, params: dict) -> float:
    t = bien["vitrage_type"]
    mapping = {
        "Simple": float(params["vitrage_simple"]),
        "Double ancien": float(params["vitrage_double_ancien"]),
        "Double recent": float(params["vitrage_double_recent"]),
        "Triple": float(params["vitrage_triple"]),
    }
    return float(mapping.get(t, 0.0))


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


def calc_indice(bien: dict) -> float:
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

    # PAGE 1 - Synthese
    draw_header(c, "Rapport d'estimation - Vente", "Synthese vendeur (page 1/3)")
    y = h - 165

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Bien")
    y -= 18

    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Client: {safe_text(bien['client'], 60) or '-'}")
    y -= 14
    c.drawString(55, y, f"Adresse: {safe_text(bien['adresse'], 80) or '-'}")
    y -= 14
    c.drawString(55, y, f"Commune: {safe_text(bien['commune'], 40) or '-'}")
    y -= 14
    c.drawString(55, y, f"Zone: {zone_row['zone']}  |  Type: {bien['type']}")
    y -= 14
    c.drawString(55, y, f"Surface: {bien['surface']:.0f} m2" + (f"  |  Terrain: {bien['terrain']:.0f} m2" if bien["type"] == "Maison" else ""))
    y -= 14
    c.drawString(55, y, f"PEB: {bien['peb_lettre']}" + (f" ({bien['peb_kwh']:.0f} kWh/m2.an)" if bien['peb_kwh'] else ""))
    y -= 14
    c.drawString(55, y, f"Vitrage: {bien['vitrage_type']}")
    y -= 18

    # Indice global visible
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, f"Indice global d'etat: {indice:.1f} / 10")
    y -= 22

    # Prix
    c.setFont("Helvetica-Bold", 18)
    c.drawString(55, y, f"Valeur finale estimee: {euro(valeur_finale)}")
    y -= 22
    c.setFont("Helvetica", 11)
    c.drawString(55, y, f"Fourchette recommandee: {euro(low)}  ->  {euro(high)}")
    y -= 16
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(55, y, f"Fourchette ajustee par l'indice: -{int(low_pct*100)}% / +{int(high_pct*100)}%")
    y -= 18

    # Coef expert visible
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"Coefficient d'appreciation experte: {coef_expert_pct:+.1f}%")
    y -= 14
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Justification: {safe_text(bien['justif_coef'], 95) or '-'}")
    y -= 18

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Document indicatif - base sur un referentiel interne et une analyse technique (outil interne).")
    c.showPage()

    # PAGE 2 - Detail des calculs
    draw_header(c, "Detail des calculs", "Marche + impacts techniques (page 2/3)")
    y = h - 165

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Marche (referentiel)")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Base zone/type: {euro(marche['base_eur_m2'])} par m2")
    y -= 14
    c.drawString(55, y, f"Valeur batie: {euro(marche['valeur_batie'])}")
    y -= 14
    if bien["type"] == "Maison":
        c.drawString(55, y, f"Valeur terrain: {euro(marche['valeur_terrain'])}")
        y -= 14
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, f"Valeur marche theorique: {euro(marche['valeur_marche'])}")
    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Impacts techniques (appliques automatiquement)")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Toiture ({bien['toiture_etat']}): {euro(impacts['toiture'])}")
    y -= 14
    c.drawString(55, y, f"Chauffage ({bien['chauffage_type']}): {euro(impacts['chauffage'])}")
    y -= 14
    c.drawString(55, y, f"Chassis/Vitrage ({bien['vitrage_type']}): {euro(impacts['vitrage'])}")
    y -= 14
    c.drawString(55, y, f"PEB ({bien['peb_lettre']}): {euro(impacts['peb'])}")
    y -= 14
    c.drawString(55, y, f"Cuisine ({bien['cuisine_etat']}): {euro(impacts['cuisine'])}")
    y -= 14
    c.drawString(55, y, f"Salle de bain ({bien['sdb_etat']}): {euro(impacts['sdb'])}")
    y -= 14
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, f"Total impacts techniques: {euro(impacts['total_tech'])}")
    y -= 18

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Synthese calcul")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Valeur technique = Valeur marche + impacts techniques = {euro(valeur_tech)}")
    y -= 14
    c.drawString(55, y, f"Valeur finale = Valeur technique x (1 + coef expert) = {euro(valeur_finale)}")
    y -= 18

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Les impacts et coefficients sont parametrables dans l'outil interne.")
    c.showPage()

    # PAGE 3 - Methodologie
    draw_header(c, "Methodologie", "Explications (page 3/3)")
    y = h - 165

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Approche")
    y -= 18
    c.setFont("Helvetica", 10)
    lines = [
        "1) Valeur marche: referentiel interne (zone/type) applique a la surface (degressivite si grande surface).",
        "2) Valeur terrain (maisons): valorisation par m2 selon la zone.",
        "3) Impacts techniques: toiture, chauffage, vitrage, PEB, cuisine, salle de bain.",
        "4) Indice global d'etat (/10): calcule a partir des postes; il influence la fourchette.",
        "5) Coefficient d'appreciation experte (+/-): ajuste selon attractivite (quartier, nuisances, vue, etc.).",
    ]
    for ln in lines:
        c.drawString(55, y, ln)
        y -= 14

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Notes")
    y -= 18
    c.setFont("Helvetica", 10)
    notes = [
        "Le referentiel est a mettre a jour regulierement selon ton marche local.",
        "Les impacts techniques representent l'effet sur la valeur, pas un devis.",
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

# Session init
if "zones" not in st.session_state:
    st.session_state["zones"] = DEFAULT_ZONES.copy()
if "params" not in st.session_state:
    st.session_state["params"] = DEFAULT_PARAMS.copy()
if "history" not in st.session_state:
    st.session_state["history"] = []  # liste de dicts

tabs = st.tabs(["1) Marche", "2) Technique", "3) Synthese", "4) Historique"])

# Sidebar : identité + bien + coef expert
with st.sidebar:
    st.subheader("Identite dossier")
    client = st.text_input("Client (interne)", value="")
    adresse = st.text_input("Adresse", value="")
    commune = st.text_input("Commune", value="")

    st.subheader("Bien")
    type_bien = st.selectbox("Type", ["Maison", "Appartement", "Commerce"])

    zones = st.session_state["zones"]
    zone_names = sorted(list({z["zone"] for z in zones}))
    zone_sel = st.selectbox("Zone", zone_names)

    candidates = [z for z in zones if z["zone"] == zone_sel and z["type"] == type_bien]
    zone_row = candidates[0] if candidates else None
    if zone_row is None:
        st.error("Aucune ligne referentiel pour cette zone + ce type. Ajoute-la dans l'onglet Marche > Referentiel.")

    surface = st.number_input("Surface (m2)", min_value=1.0, value=100.0, step=1.0)
    terrain = 0.0
    if type_bien == "Maison":
        terrain = st.number_input("Terrain (m2)", min_value=0.0, value=0.0, step=10.0)

    st.subheader("Appreciation experte (visible)")
    p = st.session_state["params"]
    coef_expert_pct = st.slider(
        "Coefficient expert (%)",
        float(p["coef_expert_min"]), float(p["coef_expert_max"]),
        value=0.0, step=0.5
    )
    justif_coef = st.text_area("Justification", value="", height=80)

# Bien (base)
bien = {
    "client": client,
    "adresse": adresse,
    "commune": commune,
    "type": type_bien,
    "zone": zone_sel,
    "surface": float(surface),
    "terrain": float(terrain),
    "coef_expert_pct": float(coef_expert_pct),
    "justif_coef": justif_coef,

    # Technique defaults
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

params = st.session_state["params"]

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
        toiture_grenier = st.checkbox("Grenier present", value=False)
    with t2:
        toiture_surface_grenier = st.number_input("Surface grenier (m2)", min_value=0.0, value=0.0, step=5.0, disabled=not toiture_grenier)
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

    st.markdown("### Cuisine / Salle de bain")
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
    st.subheader("Parametres techniques (impacts ajustables)")
    with st.expander("Ajuster les impacts (interne)", expanded=False):
        colA, colB, colC = st.columns(3)
        with colA:
            st.write("Toiture")
            params["toit_forfait_sans_grenier"] = st.number_input("Forfait sans grenier", value=int(params["toit_forfait_sans_grenier"]), step=500)
            params["toit_base_avec_grenier"] = st.number_input("Base avec grenier", value=int(params["toit_base_avec_grenier"]), step=500)
            params["toit_eur_m2_grenier"] = st.number_input("EUR/m2 grenier", value=int(params["toit_eur_m2_grenier"]), step=5)
            params["toit_impact_factor"] = st.number_input("Impact factor (ex 0.70)", value=float(params["toit_impact_factor"]), step=0.05)
            params["toit_etat_moyen_coeff"] = st.number_input("Coeff etat Moyenne (ex 0.50)", value=float(params["toit_etat_moyen_coeff"]), step=0.05)

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

        with colC:
            st.write("PEB / Cuisine / SDB")
            params["peb_A"] = st.number_input("PEB A", value=int(params["peb_A"]), step=500)
            params["peb_B"] = st.number_input("PEB B", value=int(params["peb_B"]), step=500)
            params["peb_C"] = st.number_input("PEB C", value=int(params["peb_C"]), step=500)
            params["peb_D"] = st.number_input("PEB D", value=int(params["peb_D"]), step=500)
            params["peb_E"] = st.number_input("PEB E", value=int(params["peb_E"]), step=500)
            params["peb_F"] = st.number_input("PEB F", value=int(params["peb_F"]), step=500)
            params["peb_G"] = st.number_input("PEB G", value=int(params["peb_G"]), step=500)

            params["cuisine_moderniser"] = st.number_input("Cuisine a moderniser", value=int(params["cuisine_moderniser"]), step=500)
            params["cuisine_remplacer"] = st.number_input("Cuisine a remplacer", value=int(params["cuisine_remplacer"]), step=500)
            params["sdb_moderniser"] = st.number_input("SDB a moderniser", value=int(params["sdb_moderniser"]), step=500)
            params["sdb_remplacer"] = st.number_input("SDB a remplacer", value=int(params["sdb_remplacer"]), step=500)

        st.session_state["params"] = params

    # Preview impacts + indice
    impacts = {
        "toiture": calc_toiture_impact(bien, params),
        "chauffage": calc_chauffage_impact(bien, params),
        "vitrage": calc_vitrage_impact(bien, params),
        "peb": calc_peb_impact(bien, params),
        "cuisine": calc_cuisine_impact(bien, params),
        "sdb": calc_sdb_impact(bien, params),
    }
    impacts["total_tech"] = (
        impacts["toiture"] + impacts["chauffage"] + impacts["vitrage"]
        + impacts["peb"] + impacts["cuisine"] + impacts["sdb"]
    )
    indice = calc_indice(bien)

    k1, k2, k3, k4, k5, k6, k7, k8 = st.columns(8)
    k1.metric("Toiture", euro(impacts["toiture"]))
    k2.metric("Chauffage", euro(impacts["chauffage"]))
    k3.metric("Vitrage", euro(impacts["vitrage"]))
    k4.metric("PEB", euro(impacts["peb"]))
    k5.metric("Cuisine", euro(impacts["cuisine"]))
    k6.metric("SDB", euro(impacts["sdb"]))
    k7.metric("Total tech", euro(impacts["total_tech"]))
    k8.metric("Indice", f"{indice:.1f}")

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
        "sdb": calc_sdb_impact(bien, params),
    }
    impacts["total_tech"] = (
        impacts["toiture"] + impacts["chauffage"] + impacts["vitrage"]
        + impacts["peb"] + impacts["cuisine"] + impacts["sdb"]
    )

    indice = calc_indice(bien)

    valeur_tech = marche["valeur_marche"] + impacts["total_tech"]
    coef = float(bien["coef_expert_pct"]) / 100.0
    valeur_finale = valeur_tech * (1.0 + coef)

    low, high, low_pct, high_pct = fourchette_from_indice(valeur_finale, indice, params)

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Valeur marche", euro(marche["valeur_marche"]))
    a2.metric("Total impacts techniques", euro(impacts["total_tech"]))
    a3.metric("Valeur technique", euro(valeur_tech))
    a4.metric("Valeur finale", euro(valeur_finale))

    st.markdown("---")
    b1, b2, b3 = st.columns(3)
    b1.metric("Indice global", f"{indice:.1f} / 10")
    b2.metric("Fourchette basse", euro(low))
    b3.metric("Fourchette haute", euro(high))

    st.caption(f"Fourchette ajustee par l'indice: -{int(low_pct*100)}% / +{int(high_pct*100)}%")
    st.caption(f"Coefficient d'appreciation experte (visible): {bien['coef_expert_pct']:+.1f}%")

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
                "peb_lettre": bien["peb_lettre"],
                "peb_kwh": round(float(bien["peb_kwh"]), 0),
                "vitrage_type": bien["vitrage_type"],
                "toiture_etat": bien["toiture_etat"],
                "toiture_grenier": bool(bien["toiture_grenier"]),
                "toiture_surface_grenier": round(float(bien["toiture_surface_grenier"]), 1),
                "chauffage_type": bien["chauffage_type"],
                "cuisine_etat": bien["cuisine_etat"],
                "sdb_etat": bien["sdb_etat"],
                "indice_etat": round(float(indice), 1),
                "coef_expert_pct": round(float(bien["coef_expert_pct"]), 1),
                "justif_coef": safe_text(bien["justif_coef"], 120),
                "valeur_marche": round(float(marche["valeur_marche"]), 0),
                "impact_total_tech": round(float(impacts["total_tech"]), 0),
                "valeur_finale": round(float(valeur_finale), 0),
                "fourchette_basse": round(float(low), 0),
                "fourchette_haute": round(float(high), 0),
                "prix_vendu": "",
                "date_vente": "",
            }
            st.session_state["history"].insert(0, record)
            st.success("Estimation enregistree dans l'historique.")
    with colS2:
        st.info("Tu peux ensuite aller dans Historique pour encoder le prix vendu.")

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
