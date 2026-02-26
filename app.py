import streamlit as st
from datetime import date, datetime
from io import BytesIO
from math import exp
from statistics import mean, median

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


def euro(x: float) -> str:
    s = f"{x:,.0f}".replace(",", " ")
    return f"{s} EUR"


def pm2(x: float) -> str:
    s = f"{x:,.0f}".replace(",", " ")
    return f"{s} EUR/m2"


def weight(distance_km: float, days_old: int, surf_comp: float, surf_bien: float) -> float:
    distance_km = max(distance_km, 0.1)
    days_old = max(days_old, 1)
    ratio = surf_bien / max(surf_comp, 1.0)
    sim = exp(-abs(1.0 - ratio) * 2.0)
    wd = exp(-distance_km * 0.9)
    wr = exp(-(days_old / 365.0) * 1.3)
    return max(0.0001, sim * wd * wr)


def adj_factor(epc: str, etat: str, params: dict) -> float:
    epc = (epc or "").strip().upper()
    f = params.get(f"epc_{epc}", 0.0)
    etat_key = {
        "Renove": "etat_renove",
        "Bon": "etat_bon",
        "A rafraichir": "etat_rafraichir",
        "A renover": "etat_renover",
    }.get(etat, "etat_bon")
    f += params.get(etat_key, 0.0)
    return f


def estimate(bien: dict, comps: list[dict], params: dict):
    if len(comps) < 3:
        return None

    today = date.today()
    num = 0.0
    den = 0.0

    adj_bien = adj_factor(bien["epc"], bien["etat"], params)

    for c in comps:
        pm2_raw = c["prix"] / max(c["surface"], 1.0)
        d_vente = datetime.strptime(c["date_vente"], "%Y-%m-%d").date()
        days_old = (today - d_vente).days

        adj_comp = adj_factor(c["epc"], c["etat"], params)
        pm2_adj = pm2_raw * (1.0 + (adj_bien - adj_comp))

        w = weight(c["distance_km"], days_old, c["surface"], bien["surface"])
        num += pm2_adj * w
        den += w

    base_pm2 = num / max(den, 1e-9)
    valeur_base = base_pm2 * bien["surface"]

    adj_terrain = bien["terrain"] * params["terrain_eur_m2"]
    adj_garage = params["garage_valeur"] if bien["garage"] else 0.0

    valeur = valeur_base + adj_terrain + adj_garage

    pct = params["fourchette_pct"]
    low = valeur * (1.0 - pct)
    high = valeur * (1.0 + pct)

    return {
        "pm2_estime": base_pm2,
        "valeur_base": valeur_base,
        "adj_terrain": adj_terrain,
        "adj_garage": adj_garage,
        "valeur": valeur,
        "low": low,
        "high": high,
    }


def draw_header(c: canvas.Canvas, title: str, subtitle: str):
    w, h = A4

    # Logo
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


def build_pdf_3pages(bien: dict, comps: list[dict], result: dict, params: dict) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # PAGE 1 - Couverture / Synthese
    draw_header(c, "Rapport d'estimation - Vente", "Synthese vendeur (page 1/3)")
    y = h - 165

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Bien estime")
    y -= 18
    c.setFont("Helvetica", 10)

    info = [
        f"Commune: {bien['commune']}",
        f"Type: {bien['type_bien']}",
        f"Surface habitable: {bien['surface']:.0f} m2",
        f"Terrain: {bien['terrain']:.0f} m2",
        f"Etat: {bien['etat']}",
        f"EPC: {bien['epc']}",
        f"Garage/Parking: {'Oui' if bien['garage'] else 'Non'}",
        f"Remarques: {bien['remarques'] or '-'}",
    ]
    for ln in info:
        c.drawString(55, y, ln)
        y -= 14

    y -= 8
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Resultat")
    y -= 22
    c.setFont("Helvetica-Bold", 18)
    c.drawString(55, y, f"Prix conseille: {euro(result['valeur'])}")
    y -= 22
    c.setFont("Helvetica", 11)
    c.drawString(55, y, f"Fourchette: {euro(result['low'])}  ->  {euro(result['high'])}")
    y -= 16
    c.drawString(55, y, f"Reference: {pm2(result['pm2_estime'])}")
    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Points cles")
    y -= 18
    c.setFont("Helvetica", 10)
    bullets = [
        "Estimation basee sur comparables ponderes (distance, recence, surface).",
        "Ajustements EPC/etat appliques par difference entre bien et comparables.",
        "Fourchette recommandee pour tenir compte de la negociation.",
        "Conseil: positionner le prix selon l'objectif (vente rapide vs optimisation).",
    ]
    for b in bullets:
        c.drawString(55, y, f"- {b}")
        y -= 14

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Document indicatif - base sur les informations communiquees et les comparables fournis.")
    c.showPage()

    # PAGE 2 - Analyse / details ajustements
    draw_header(c, "Analyse & justification", "Methode et ajustements (page 2/3)")
    y = h - 165
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Methode")
    y -= 18
    c.setFont("Helvetica", 10)
    method = [
        "1) Selection de comparables proches et recents.",
        "2) Calcul du prix au m2 de chaque comparable.",
        "3) Ponderation: distance + recence + similarite surface.",
        "4) Ajustements EPC/etat + ajustements fixes (terrain/garage).",
    ]
    for ln in method:
        c.drawString(55, y, ln)
        y -= 14

    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Detail des ajustements")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Valeur base (comparables): {euro(result['valeur_base'])}")
    y -= 14
    c.drawString(55, y, f"Ajustement terrain ({params['terrain_eur_m2']:.0f} EUR/m2): {euro(result['adj_terrain'])}")
    y -= 14
    c.drawString(55, y, f"Ajustement garage/parking: {euro(result['adj_garage'])}")
    y -= 14
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, f"Prix conseille total: {euro(result['valeur'])}")
    y -= 14
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Fourchette (+/- {int(params['fourchette_pct']*100)}%): {euro(result['low'])} -> {euro(result['high'])}")

    y -= 24
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Conseils de positionnement")
    y -= 18
    c.setFont("Helvetica", 10)
    tips = [
        "Vente rapide: viser le bas de la fourchette pour augmenter les demandes.",
        "Optimisation prix: viser le prix conseille avec marge de negociation.",
        "Si peu de contacts: revoir le prix ou l'annonce apres 2 semaines.",
    ]
    for t in tips:
        c.drawString(55, y, f"- {t}")
        y -= 14

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Les coefficients sont ajustables selon la realite du marche local.")
    c.showPage()

    # PAGE 3 - Comparables
    draw_header(c, "Comparables", "Liste & stats (page 3/3)")
    y = h - 165

    pm2_list = [(cc["prix"] / max(cc["surface"], 1.0)) for cc in comps]
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Statistiques (EUR/m2 non ajuste)")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Moyenne: {pm2(mean(pm2_list))}")
    c.drawString(260, y, f"Mediane: {pm2(median(pm2_list))}")
    y -= 14
    c.drawString(55, y, f"Min: {pm2(min(pm2_list))}")
    c.drawString(260, y, f"Max: {pm2(max(pm2_list))}")
    y -= 22

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Tableau des comparables")
    y -= 16

    c.setFont("Helvetica-Bold", 9)
    headers = ["#", "Prix", "Surf", "EUR/m2", "Date", "Dist(km)", "Etat", "EPC", "Note"]
    x = [40, 60, 120, 170, 235, 295, 350, 410, 440]
    for i, hd in enumerate(headers):
        c.drawString(x[i], y, hd)
    y -= 10
    c.line(40, y, w - 40, y)
    y -= 12

    c.setFont("Helvetica", 9)
    for idx, comp in enumerate(comps[:14], start=1):
        vpm2 = comp["prix"] / max(comp["surface"], 1.0)
        row = [
            str(idx),
            f"{comp['prix']:,.0f}".replace(",", " "),
            f"{comp['surface']:.0f}",
            f"{vpm2:,.0f}".replace(",", " "),
            comp["date_vente"],
            f"{comp['distance_km']:.1f}",
            comp["etat"],
            comp["epc"],
            (comp.get("note") or "")[:22],
        ]
        for i, cell in enumerate(row):
            c.drawString(x[i], y, cell)
        y -= 12
        if y < 70:
            c.showPage()
            draw_header(c, "Comparables (suite)", "")
            y = h - 165

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Comparables conseilles: proches, recents, et similaires (type/surface).")
    c.save()

    buf.seek(0)
    return buf.getvalue()


# ---------------- UI ----------------
st.set_page_config(page_title="Estimateur - La Priorite Immobiliere", layout="wide")
st.title("Estimateur web - La Priorite Immobiliere (Wallonie)")

with st.expander("Parametres (ajustables)", expanded=False):
    params = {
        "epc_A": st.number_input("EPC A (%)", value=6.0) / 100.0,
        "epc_B": st.number_input("EPC B (%)", value=3.0) / 100.0,
        "epc_C": st.number_input("EPC C (%)", value=0.0) / 100.0,
        "epc_D": st.number_input("EPC D (%)", value=-3.0) / 100.0,
        "epc_E": st.number_input("EPC E (%)", value=-6.0) / 100.0,
        "epc_F": st.number_input("EPC F (%)", value=-9.0) / 100.0,
        "epc_G": st.number_input("EPC G (%)", value=-12.0) / 100.0,
        "etat_renove": st.number_input("Etat Renove (%)", value=8.0) / 100.0,
        "etat_bon": st.number_input("Etat Bon (%)", value=3.0) / 100.0,
        "etat_rafraichir": st.number_input("Etat A rafraichir (%)", value=-3.0) / 100.0,
        "etat_renover": st.number_input("Etat A renover (%)", value=-10.0) / 100.0,
        "garage_valeur": st.number_input("Valeur garage (EUR)", value=15000.0, step=1000.0),
        "terrain_eur_m2": st.number_input("Valeur terrain (EUR/m2)", value=15.0, step=1.0),
        "fourchette_pct": st.number_input("Fourchette (+/- %)", value=6.0) / 100.0,
    }

colA, colB = st.columns(2)

with colA:
    st.subheader("1) Bien a estimer")
    bien = {
        "commune": st.text_input("Commune"),
        "type_bien": st.selectbox("Type", ["Maison", "Appartement"]),
        "surface": st.number_input("Surface habitable (m2)", min_value=10.0, value=120.0, step=1.0),
        "terrain": st.number_input("Terrain (m2)", min_value=0.0, value=0.0, step=10.0),
        "etat": st.selectbox("Etat", ["Bon", "Renove", "A rafraichir", "A renover"]),
        "epc": st.selectbox("EPC", ["A", "B", "C", "D", "E", "F", "G"], index=2),
        "garage": st.checkbox("Garage / parking"),
        "remarques": st.text_area("Remarques (optionnel)"),
    }

with colB:
    st.subheader("2) Comparables")
    if "comps" not in st.session_state:
        st.session_state["comps"] = []

    with st.form("add_comp", clear_on_submit=True):
        prix = st.number_input("Prix (EUR)", min_value=10000.0, value=250000.0, step=1000.0)
        surface_c = st.number_input("Surface (m2)", min_value=10.0, value=120.0, step=1.0)
        date_vente = st.date_input("Date de vente", value=date(2025, 10, 1))
        distance_km = st.number_input("Distance (km)", min_value=0.0, value=1.0, step=0.1)
        etat_c = st.selectbox("Etat (comp)", ["Bon", "Renove", "A rafraichir", "A renover"])
        epc_c = st.selectbox("EPC (comp)", ["A", "B", "C", "D", "E", "F", "G"], index=2)
        note = st.text_input("Note (optionnel)")
        ok = st.form_submit_button("Ajouter comparable")
        if ok:
            st.session_state["comps"].append({
                "prix": float(prix),
                "surface": float(surface_c),
                "date_vente": date_vente.isoformat(),
                "distance_km": float(distance_km),
                "etat": etat_c,
                "epc": epc_c,
                "note": note,
            })

    if st.session_state["comps"]:
        st.dataframe(st.session_state["comps"], use_container_width=True)
        if st.button("Supprimer le dernier comparable"):
            st.session_state["comps"].pop()

st.markdown("---")
st.subheader("3) Resultats & Rapport vendeur (PDF 3 pages)")

res = estimate(bien, st.session_state["comps"], params)
if res is None:
    st.warning("Ajoute au moins 3 comparables (idealement 5 a 8) pour generer une estimation.")
else:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prix conseille", euro(res["valeur"]))
    c2.metric("Basse", euro(res["low"]))
    c3.metric("Haute", euro(res["high"]))
    c4.metric("EUR/m2 estime", pm2(res["pm2_estime"]))

    pdf = build_pdf_3pages(bien, st.session_state["comps"], res, params)
    st.download_button(
        "Telecharger le rapport vendeur (PDF - 3 pages)",
        data=pdf,
        file_name=f"Rapport_estimation_{date.today().isoformat()}.pdf",
        mime="application/pdf",
    )
