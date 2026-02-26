import streamlit as st
from datetime import date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

AGENCE = "LA PRIORITE IMMOBILIERE"
EMAIL = "sbelhmira@gmail.com"

# -----------------------------
# 1) Grille / Referentiel (modifiable par toi)
# -----------------------------
DEFAULT_ZONES = [
    # Zone, Type, Base €/m² habitable, Terrain €/m² (maisons), Commerce €/m² (si méthode €/m²)
    {"zone": "Namur - Centre", "type": "Maison", "base_eur_m2": 2150, "terrain_eur_m2": 20, "commerce_eur_m2": 0},
    {"zone": "Namur - Centre", "type": "Appartement", "base_eur_m2": 2350, "terrain_eur_m2": 0, "commerce_eur_m2": 0},
    {"zone": "Charleroi", "type": "Maison", "base_eur_m2": 1550, "terrain_eur_m2": 12, "commerce_eur_m2": 0},
    {"zone": "Charleroi", "type": "Appartement", "base_eur_m2": 1700, "terrain_eur_m2": 0, "commerce_eur_m2": 0},
    {"zone": "Liege - Axe commercial", "type": "Commerce", "base_eur_m2": 0, "terrain_eur_m2": 0, "commerce_eur_m2": 2400},
]

DEFAULT_PARAMS = {
    # Ajustements PEB (en %)
    "peb_A": +0.06,
    "peb_B": +0.03,
    "peb_C":  0.00,
    "peb_D": -0.03,
    "peb_E": -0.06,
    "peb_F": -0.09,
    "peb_G": -0.12,

    # Ajustements état (en %)
    "etat_renove": +0.08,
    "etat_bon": +0.03,
    "etat_rafraichir": -0.03,
    "etat_renover": -0.10,

    # Annexes (valeurs fixes)
    "garage": 15000,
    "parking": 8000,
    "terrasse": 4000,
    "jardin": 6000,
    "cave": 2000,

    # Dégressivité surface (expert)
    # au-dessus de 160 m²: baisse le €/m² de 6%
    "seuil_degressif_m2": 160,
    "degressif_pct": 0.06,

    # Fourchette (+/-)
    "fourchette_pct": 0.06,
}

# -----------------------------
# Helpers
# -----------------------------
def euro(x: float) -> str:
    return f"{x:,.0f} €".replace(",", " ")

def get_peb_adj(params: dict, peb: str) -> float:
    peb = (peb or "").strip().upper()
    return params.get(f"peb_{peb}", 0.0)

def get_etat_adj(params: dict, etat: str) -> float:
    key = {
        "Renove": "etat_renove",
        "Bon": "etat_bon",
        "A rafraichir": "etat_rafraichir",
        "A renover": "etat_renover",
    }.get(etat, "etat_bon")
    return params.get(key, 0.0)

def apply_degressivity(base_eur_m2: float, surface: float, params: dict) -> float:
    seuil = params["seuil_degressif_m2"]
    if surface > seuil:
        return base_eur_m2 * (1.0 - params["degressif_pct"])
    return base_eur_m2

def estimate_residentiel(zone_row: dict, bien: dict, params: dict) -> dict:
    base_m2 = apply_degressivity(zone_row["base_eur_m2"], bien["surface"], params)

    # Ajustements en %
    adj_pct = get_peb_adj(params, bien["peb"]) + get_etat_adj(params, bien["etat"])

    valeur_batie = bien["surface"] * base_m2 * (1.0 + adj_pct)

    valeur_terrain = 0.0
    if bien["type"] == "Maison":
        valeur_terrain = bien["terrain"] * zone_row["terrain_eur_m2"]

    annexes = 0.0
    annexes += params["garage"] if bien["garage"] else 0.0
    annexes += params["parking"] if bien["parking"] else 0.0
    annexes += params["terrasse"] if bien["terrasse"] else 0.0
    annexes += params["jardin"] if bien["jardin"] else 0.0
    annexes += params["cave"] if bien["cave"] else 0.0

    valeur = valeur_batie + valeur_terrain + annexes

    pct = params["fourchette_pct"]
    return {
        "valeur": valeur,
        "low": valeur * (1.0 - pct),
        "high": valeur * (1.0 + pct),
        "detail": {
            "base_eur_m2": base_m2,
            "adj_pct_total": adj_pct,
            "valeur_batie": valeur_batie,
            "valeur_terrain": valeur_terrain,
            "annexes": annexes,
        }
    }

def estimate_commerce(zone_row: dict, bien: dict, params: dict) -> dict:
    # Deux méthodes : €/m² commercial OU rendement
    methode = bien["methode_commerce"]

    if methode == "Rendement":
        # Valeur = loyer annuel / taux
        loyer_annuel = bien["loyer_mensuel"] * 12.0
        taux = max(bien["taux_rendement"] / 100.0, 0.01)
        valeur = loyer_annuel / taux
        detail = {
            "methode": "Rendement",
            "loyer_annuel": loyer_annuel,
            "taux": taux,
        }
    else:
        # Valeur = surface commerciale * €/m² commerce (zone)
        base = zone_row["commerce_eur_m2"]
        valeur = bien["surface"] * base
        detail = {
            "methode": "€/m² commercial",
            "commerce_eur_m2": base,
        }

    pct = params["fourchette_pct"]
    return {
        "valeur": valeur,
        "low": valeur * (1.0 - pct),
        "high": valeur * (1.0 + pct),
        "detail": detail
    }

def make_pdf_3pages(bien: dict, zone_row: dict, res: dict, params: dict) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    def header(title, subtitle):
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, h - 50, title)
        c.setFont("Helvetica", 10)
        c.drawString(40, h - 68, AGENCE)
        c.drawString(40, h - 82, f"Contact: {EMAIL}")
        c.drawString(40, h - 96, f"Date: {date.today().strftime('%d/%m/%Y')}")
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(40, h - 112, subtitle)
        c.line(40, h - 125, w - 40, h - 125)

    # Page 1 : synthèse
    header("Rapport d'estimation - Vente", "Synthese (page 1/3)")
    y = h - 155

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Bien")
    y -= 18
    c.setFont("Helvetica", 10)
    lines = [
        f"Zone referentiel: {zone_row['zone']}  |  Type: {bien['type']}",
        f"Adresse/Commune: {bien['commune']}",
        f"Surface: {bien['surface']:.0f} m2",
    ]
    if bien["type"] == "Maison":
        lines.append(f"Terrain: {bien['terrain']:.0f} m2")
    if bien["type"] in ["Maison", "Appartement"]:
        lines.append(f"Etat: {bien['etat']}  |  PEB: {bien['peb']}")
    if bien["type"] == "Commerce":
        lines.append(f"Methode commerce: {bien['methode_commerce']}")

    for ln in lines:
        c.drawString(55, y, ln)
        y -= 14

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Estimation")
    y -= 22
    c.setFont("Helvetica-Bold", 18)
    c.drawString(55, y, f"Prix conseille: {euro(res['valeur'])}")
    y -= 22
    c.setFont("Helvetica", 11)
    c.drawString(55, y, f"Fourchette: {euro(res['low'])} -> {euro(res['high'])}")

    y -= 24
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Conclusion")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, "Estimation basee sur referentiel interne + ajustements techniques (mode expert).")

    c.showPage()

    # Page 2 : détails calculs
    header("Detail des calculs", "Calculs (page 2/3)")
    y = h - 155

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Base et ajustements")
    y -= 18
    c.setFont("Helvetica", 10)

    if bien["type"] in ["Maison", "Appartement"]:
        d = res["detail"]
        c.drawString(55, y, f"Base zone/type: {euro(d['base_eur_m2'])} par m2")
        y -= 14
        c.drawString(55, y, f"Ajustement total (PEB + etat): {d['adj_pct_total']*100:.1f}%")
        y -= 14
        c.drawString(55, y, f"Valeur batie: {euro(d['valeur_batie'])}")
        y -= 14
        if bien["type"] == "Maison":
            c.drawString(55, y, f"Valeur terrain ({euro(zone_row['terrain_eur_m2'])} par m2): {euro(d['valeur_terrain'])}")
            y -= 14
        c.drawString(55, y, f"Annexes: {euro(d['annexes'])}")
        y -= 14
        c.setFont("Helvetica-Bold", 10)
        c.drawString(55, y, f"Total: {euro(res['valeur'])}")
    else:
        d = res["detail"]
        c.drawString(55, y, f"Methode: {d['methode']}")
        y -= 14
        if d["methode"] == "Rendement":
            c.drawString(55, y, f"Loyer annuel: {euro(d['loyer_annuel'])}")
            y -= 14
            c.drawString(55, y, f"Taux rendement: {d['taux']*100:.2f}%")
            y -= 14
            c.setFont("Helvetica-Bold", 10)
            c.drawString(55, y, f"Valeur: {euro(res['valeur'])}")
        else:
            c.drawString(55, y, f"€/m2 commercial (zone): {euro(d['commerce_eur_m2'])}")
            y -= 14
            c.setFont("Helvetica-Bold", 10)
            c.drawString(55, y, f"Valeur: {euro(res['valeur'])}")

    c.showPage()

    # Page 3 : grille et hypothèses
    header("Referentiel utilise", "Grille & hypotheses (page 3/3)")
    y = h - 155
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Ligne referentiel selectionnee")
    y -= 18
    c.setFont("Helvetica", 10)

    c.drawString(55, y, f"Zone: {zone_row['zone']}")
    y -= 14
    c.drawString(55, y, f"Type: {zone_row['type']}")
    y -= 14
    if zone_row["type"] in ["Maison", "Appartement"]:
        c.drawString(55, y, f"Base €/m2: {euro(zone_row['base_eur_m2'])}")
        y -= 14
        if zone_row["type"] == "Maison":
            c.drawString(55, y, f"Terrain €/m2: {euro(zone_row['terrain_eur_m2'])}")
            y -= 14
    if zone_row["type"] == "Commerce":
        c.drawString(55, y, f"Commerce €/m2 (si methode €/m2): {euro(zone_row['commerce_eur_m2'])}")
        y -= 14

    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Parametres (extraits)")
    y -= 18
    c.setFont("Helvetica", 9)
    c.drawString(55, y, f"PEB A:+6%  B:+3%  C:0%  D:-3%  E:-6%  F:-9%  G:-12%")
    y -= 12
    c.drawString(55, y, f"Etat Renove:+8%  Bon:+3%  A rafraichir:-3%  A renover:-10%")
    y -= 12
    c.drawString(55, y, f"Fourchette: +/- {int(params['fourchette_pct']*100)}%")
    y -= 12
    c.drawString(55, y, f"Annexes (garage/parking/terrasse/jardin/cave): valeurs fixes (modifiables)")

    c.save()
    buf.seek(0)
    return buf.getvalue()


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="Estimateur Expert - La Priorite Immobiliere", layout="wide")
st.title("Estimateur Expert - La Priorite Immobiliere")

# Init session state
if "zones" not in st.session_state:
    st.session_state["zones"] = DEFAULT_ZONES.copy()
if "params" not in st.session_state:
    st.session_state["params"] = DEFAULT_PARAMS.copy()

tab1, tab2 = st.tabs(["1) Referentiel (ta grille)", "2) Estimation + Rapport"])

with tab1:
    st.subheader("Ta grille de reference (modifiable)")
    st.write("Tu peux adapter les prix €/m2 par zone et par type. C'est ta base expert.")

    zones = st.session_state["zones"]
    st.dataframe(zones, use_container_width=True)

    st.markdown("### Ajouter une ligne referentiel")
    c1, c2, c3 = st.columns(3)
    zone = c1.text_input("Zone (ex: Namur - Centre)")
    typ = c2.selectbox("Type", ["Maison", "Appartement", "Commerce"])
    base = c3.number_input("Base €/m2 (habitable)", min_value=0, value=0, step=50)

    c4, c5 = st.columns(2)
    terrain = c4.number_input("Terrain €/m2 (maisons)", min_value=0, value=0, step=1)
    commerce_m2 = c5.number_input("Commerce €/m2 (si commerce)", min_value=0, value=0, step=50)

    if st.button("Ajouter au referentiel"):
        if zone.strip():
            zones.append({"zone": zone.strip(), "type": typ, "base_eur_m2": int(base), "terrain_eur_m2": int(terrain), "commerce_eur_m2": int(commerce_m2)})
            st.session_state["zones"] = zones
            st.success("Ligne ajoutee.")

    st.markdown("### Parametres (ajustements)")
    p = st.session_state["params"]
    colA, colB = st.columns(2)
    with colA:
        st.write("PEB (en %)")
        p["peb_A"] = st.number_input("PEB A", value=float(p["peb_A"]*100)) / 100.0
        p["peb_B"] = st.number_input("PEB B", value=float(p["peb_B"]*100)) / 100.0
        p["peb_C"] = st.number_input("PEB C", value=float(p["peb_C"]*100)) / 100.0
        p["peb_D"] = st.number_input("PEB D", value=float(p["peb_D"]*100)) / 100.0
        p["peb_E"] = st.number_input("PEB E", value=float(p["peb_E"]*100)) / 100.0
        p["peb_F"] = st.number_input("PEB F", value=float(p["peb_F"]*100)) / 100.0
        p["peb_G"] = st.number_input("PEB G", value=float(p["peb_G"]*100)) / 100.0
    with colB:
        st.write("Etat (en %)")
        p["etat_renove"] = st.number_input("Renove", value=float(p["etat_renove"]*100)) / 100.0
        p["etat_bon"] = st.number_input("Bon", value=float(p["etat_bon"]*100)) / 100.0
        p["etat_rafraichir"] = st.number_input("A rafraichir", value=float(p["etat_rafraichir"]*100)) / 100.0
        p["etat_renover"] = st.number_input("A renover", value=float(p["etat_renover"]*100)) / 100.0

    st.write("Annexes (valeurs fixes)")
    p["garage"] = st.number_input("Garage", value=int(p["garage"]), step=500)
    p["parking"] = st.number_input("Parking", value=int(p["parking"]), step=500)
    p["terrasse"] = st.number_input("Terrasse", value=int(p["terrasse"]), step=250)
    p["jardin"] = st.number_input("Jardin", value=int(p["jardin"]), step=250)
    p["cave"] = st.number_input("Cave", value=int(p["cave"]), step=250)

    st.write("Degressivite (expert)")
    p["seuil_degressif_m2"] = st.number_input("Seuil m2", value=int(p["seuil_degressif_m2"]), step=10)
    p["degressif_pct"] = st.number_input("Baisse % au-dessus du seuil", value=float(p["degressif_pct"]*100)) / 100.0

    st.write("Fourchette")
    p["fourchette_pct"] = st.number_input("+/- %", value=float(p["fourchette_pct"]*100)) / 100.0

    st.session_state["params"] = p
    st.success("Parametres mis a jour (sauvegarde en session).")

with tab2:
    st.subheader("Estimation (mode expert, sans comparables)")
    zones = st.session_state["zones"]
    params = st.session_state["params"]

    zone_names = sorted(list({z["zone"] for z in zones}))
    zone_sel = st.selectbox("Choisir la zone", zone_names)

    type_sel = st.selectbox("Type de bien", ["Maison", "Appartement", "Commerce"])

    # Filtrer lignes
    possible = [z for z in zones if z["zone"] == zone_sel and z["type"] == type_sel]
    if not possible:
        st.error("Aucune ligne referentiel pour cette zone + ce type. Ajoute-la dans l'onglet Referentiel.")
        st.stop()

    zone_row = possible[0]  # si plusieurs, on prend la premiere (on peut affiner plus tard)

    commune = st.text_input("Adresse / Commune (texte)")
    surface = st.number_input("Surface (m2)", min_value=1, value=100, step=1)

    bien = {
        "type": type_sel,
        "commune": commune.strip(),
        "surface": float(surface),
        "terrain": 0.0,
        "etat": "Bon",
        "peb": "C",
        "garage": False,
        "parking": False,
        "terrasse": False,
        "jardin": False,
        "cave": False,
        "methode_commerce": "€/m2",
        "loyer_mensuel": 0.0,
        "taux_rendement": 7.0,
    }

    if type_sel == "Maison":
        bien["terrain"] = float(st.number_input("Terrain (m2)", min_value=0, value=0, step=10))
        bien["etat"] = st.selectbox("Etat", ["Bon", "Renove", "A rafraichir", "A renover"])
        bien["peb"] = st.selectbox("PEB", ["A","B","C","D","E","F","G"], index=2)
    elif type_sel == "Appartement":
        bien["etat"] = st.selectbox("Etat", ["Bon", "Renove", "A rafraichir", "A renover"])
        bien["peb"] = st.selectbox("PEB", ["A","B","C","D","E","F","G"], index=2)
    else:
        bien["methode_commerce"] = st.selectbox("Methode commerce", ["€/m2", "Rendement"])
        if bien["methode_commerce"] == "Rendement":
            bien["loyer_mensuel"] = float(st.number_input("Loyer mensuel (EUR)", min_value=0, value=0, step=50))
            bien["taux_rendement"] = float(st.number_input("Taux rendement (%)", min_value=1.0, value=7.0, step=0.25))

    st.markdown("### Annexes")
    a1, a2, a3, a4, a5 = st.columns(5)
    bien["garage"] = a1.checkbox("Garage")
    bien["parking"] = a2.checkbox("Parking")
    bien["terrasse"] = a3.checkbox("Terrasse")
    bien["jardin"] = a4.checkbox("Jardin")
    bien["cave"] = a5.checkbox("Cave")

    st.markdown("---")

    if type_sel in ["Maison", "Appartement"]:
        res = estimate_residentiel(zone_row, {"type": type_sel, **bien}, params)
    else:
        res = estimate_commerce(zone_row, bien, params)

    c1, c2, c3 = st.columns(3)
    c1.metric("Prix conseille", euro(res["valeur"]))
    c2.metric("Fourchette basse", euro(res["low"]))
    c3.metric("Fourchette haute", euro(res["high"]))

    pdf = make_pdf_3pages(bien, zone_row, res, params)
    st.download_button(
        "Telecharger rapport vendeur (PDF - 3 pages)",
        data=pdf,
        file_name=f"Rapport_Expert_{date.today().isoformat()}.pdf",
        mime="application/pdf",
    )
