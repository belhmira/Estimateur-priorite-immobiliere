import streamlit as st
from datetime import date, datetime
from io import BytesIO
from statistics import mean, median

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


# =========================
# Identité agence
# =========================
AGENCE = "LA PRIORITE IMMOBILIERE"
EMAIL = "sbelhmira@gmail.com"


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


def parse_price_to_float(x) -> float:
    """
    Convertit "250 000", "250000", "250000 €" en float.
    """
    if x is None:
        return 0.0
    s = str(x).strip()
    if not s:
        return 0.0
    s = s.replace("€", "").replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


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


# =========================
# Paramètres (modifiables)
# =========================
DEFAULT_PARAMS = {
    # Prix/m² de départ (par province) — utilisés tant que l'historique n'a pas appris localement
    "base_m2_Hainaut_Maison": 1600,
    "base_m2_Hainaut_Appartement": 1750,
    "base_m2_Hainaut_Commerce": 2100,

    "base_m2_Namur_Maison": 2200,
    "base_m2_Namur_Appartement": 2450,
    "base_m2_Namur_Commerce": 2400,

    "base_m2_Liege_Maison": 2050,
    "base_m2_Liege_Appartement": 2250,
    "base_m2_Liege_Commerce": 2350,

    "base_m2_Brabant_wallon_Maison": 3000,
    "base_m2_Brabant_wallon_Appartement": 3200,
    "base_m2_Brabant_wallon_Commerce": 2800,

    "base_m2_Luxembourg_Maison": 2400,
    "base_m2_Luxembourg_Appartement": 2550,
    "base_m2_Luxembourg_Commerce": 2400,

    # Terrain €/m² (valeurs de départ)
    "terrain_Hainaut": 60,
    "terrain_Namur": 90,
    "terrain_Liege": 85,
    "terrain_Brabant_wallon": 140,
    "terrain_Luxembourg": 80,

    # Dégressivité grandes surfaces
    "seuil_degressif_m2": 160,
    "degressif_pct": 0.06,

    # Fourchette "neutre" (sera modulée par indice)
    "fourchette_neutre_pct": 0.06,

    # Toiture (forfait + option grenier)
    "toit_forfait_sans_grenier": 18000,
    "toit_base_avec_grenier": 10000,
    "toit_eur_m2_grenier": 130,
    "toit_impact_factor": 0.70,
    "toit_etat_moyen_coeff": 0.50,

    # Chauffage
    "chauff_pac": 8000,
    "chauff_gaz_cond": 3000,
    "chauff_mazout": -5000,
    "chauff_electrique": -8000,
    "chauff_ancien": -10000,

    # Cuisine
    "cuisine_bonne": 0,
    "cuisine_moderniser": -5000,
    "cuisine_remplacer": -12000,

    # Salle de bain état
    "sdb_bonne": 0,
    "sdb_moderniser": -4000,
    "sdb_remplacer": -9000,

    # Vitrage
    "vitrage_simple": -8000,
    "vitrage_double_ancien": -3000,
    "vitrage_double_recent": 0,
    "vitrage_triple": 4000,

    # PEB
    "peb_A": 6000,
    "peb_B": 3000,
    "peb_C": 0,
    "peb_D": -3000,
    "peb_E": -6000,
    "peb_F": -9000,
    "peb_G": -12000,

    # Chambres
    "impact_par_chambre": 8000,

    # Nb salles de bain (référence 1)
    "impact_par_sdb_supp": 6000,

    # Étage appartement
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

    # === Nouveaux impacts demandés ===
    # État général
    "etat_neuf": 15000,
    "etat_bon": 5000,
    "etat_moyen": 0,
    "etat_renover": -20000,
    "etat_tres_degrade": -40000,

    # Parachèvement
    "parach_haut": 20000,
    "parach_standard": 0,
    "parach_basique": -8000,
    "parach_non_termine": -20000,

    # Façades
    "facades_2": 0,
    "facades_3": 10000,
    "facades_4": 20000,

    # Extramuros
    "extramuros_eur_m2": 120,

    # Surface habitable vs totale (pénalité si écart trop grand)
    "penalite_surface_non_habitable_eur_m2": -80,

    # Coefficient expert
    "coef_expert_min": -3.0,
    "coef_expert_max": 3.0,

    # Apprentissage: minimum de ventes pour apprendre un prix/m² local
    "min_ventes_apprentissage": 3,

    # Bornes sécurité pour le coef quartier basé sur historique
    "coef_quartier_min": 0.85,
    "coef_quartier_max": 1.15,
}


# =========================
# Calculs marché + apprentissage
# =========================
def apply_degressivity(prix_m2: float, surface: float, params: dict) -> float:
    if surface > float(params["seuil_degressif_m2"]):
        return prix_m2 * (1.0 - float(params["degressif_pct"]))
    return prix_m2


def base_price_m2_from_province(province: str, type_bien: str, params: dict) -> float:
    key = f"base_m2_{province}_{type_bien}"
    return float(params.get(key, 2000))


def base_terrain_m2_from_province(province: str, params: dict) -> float:
    key = f"terrain_{province}"
    return float(params.get(key, 80))


def calc_price_m2_learned(history: list, cp: str, localite: str, type_bien: str, min_n: int) -> float | None:
    """
    Apprend un prix/m² à partir des ventes (prix_vendu) pour le même CP + localité + type.
    prix/m² = prix_vendu / surface_totale (ou surface si pas dispo)
    Retourne médiane si assez de ventes, sinon None.
    """
    cp = (cp or "").strip()
    loc = (localite or "").strip().lower()
    t = (type_bien or "").strip()

    values = []
    for r in history:
        try:
            if str(r.get("cp", "")).strip() != cp:
                continue
            if str(r.get("localite", "")).strip().lower() != loc:
                continue
            if str(r.get("type_bien", "")).strip() != t:
                continue

            vendu = parse_price_to_float(r.get("prix_vendu", ""))
            if vendu <= 0:
                continue

            # surface totale prioritaire si enregistrée
            surf = float(r.get("surface_totale_m2", 0) or 0)
            if surf <= 5:
                surf = float(r.get("surface_m2", 0) or 0)
            if surf <= 5:
                continue

            values.append(vendu / surf)
        except Exception:
            continue

    if len(values) < int(min_n):
        return None

    return float(median(values))


def calc_coef_quartier(history: list, cp: str, localite: str, type_bien: str, params: dict) -> float:
    """
    Coef auto basé sur ratios vendu/estimé, même CP + localité + type.
    Si pas assez de ventes -> 1.00
    """
    min_n = int(params["min_ventes_apprentissage"])
    cp = (cp or "").strip()
    loc = (localite or "").strip().lower()
    t = (type_bien or "").strip()

    ratios = []
    for r in history:
        try:
            if str(r.get("cp", "")).strip() != cp:
                continue
            if str(r.get("localite", "")).strip().lower() != loc:
                continue
            if str(r.get("type_bien", "")).strip() != t:
                continue

            vendu = parse_price_to_float(r.get("prix_vendu", ""))
            if vendu <= 0:
                continue

            estime = float(r.get("valeur_finale", 0) or 0)
            if estime <= 0:
                continue

            ratios.append(vendu / estime)
        except Exception:
            continue

    if len(ratios) < min_n:
        return 1.00

    coef = sum(ratios) / len(ratios)
    coef = max(float(params["coef_quartier_min"]), min(float(params["coef_quartier_max"]), coef))
    return float(coef)


def calc_marche_auto(bien: dict, params: dict, history: list) -> dict:
    """
    Marché automatique:
    - prix/m² appris (si assez de ventes) sinon prix/m² province
    - applique dégressivité surface_totale
    - terrain €/m² province (pour maison)
    """
    province = bien["province"]
    type_bien = bien["type"]
    surface_totale = float(bien["surface_totale_m2"])
    terrain = float(bien["terrain_m2"])

    learned = calc_price_m2_learned(
        history=history,
        cp=bien["cp"],
        localite=bien["localite"],
        type_bien=type_bien,
        min_n=int(params["min_ventes_apprentissage"])
    )

    prix_m2_base = learned if learned is not None else base_price_m2_from_province(province, type_bien, params)
    prix_m2_applique = apply_degressivity(prix_m2_base, surface_totale, params)

    valeur_batie = surface_totale * prix_m2_applique

    valeur_terrain = 0.0
    terrain_m2 = 0.0
    if type_bien == "Maison":
        terrain_m2 = base_terrain_m2_from_province(province, params)
        valeur_terrain = terrain * terrain_m2

    valeur_marche = valeur_batie + valeur_terrain

    return {
        "prix_m2_base": float(prix_m2_base),
        "prix_m2_applique": float(prix_m2_applique),
        "prix_m2_source": "appris (ventes)" if learned is not None else "base province",
        "terrain_m2": float(terrain_m2),
        "valeur_batie": float(valeur_batie),
        "valeur_terrain": float(valeur_terrain),
        "valeur_marche": float(valeur_marche),
    }


# =========================
# Impacts (techniques + caractéristiques)
# =========================
def calc_toiture_impact(bien: dict, params: dict) -> float:
    etat = bien["toiture_etat"]
    if etat == "Parfaite":
        return 0.0

    has_grenier = bool(bien["toiture_grenier"])
    if not has_grenier:
        calc = float(params["toit_forfait_sans_grenier"])
    else:
        surf = float(bien["toiture_surface_grenier_m2"])
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


# === Nouveaux impacts demandés ===
def calc_etat_general_impact(bien: dict, params: dict) -> float:
    mapping = {
        "Neuf / parfait": float(params["etat_neuf"]),
        "Bon etat": float(params["etat_bon"]),
        "Etat moyen": float(params["etat_moyen"]),
        "A renover": float(params["etat_renover"]),
        "Tres degrade": float(params["etat_tres_degrade"]),
    }
    return float(mapping.get(bien["etat_general"], 0.0))


def calc_parachevement_impact(bien: dict, params: dict) -> float:
    mapping = {
        "Haut standing": float(params["parach_haut"]),
        "Standard": float(params["parach_standard"]),
        "Basique": float(params["parach_basique"]),
        "Non termine": float(params["parach_non_termine"]),
    }
    return float(mapping.get(bien["parachevement"], 0.0))


def calc_facades_impact(bien: dict, params: dict) -> float:
    mapping = {
        2: float(params["facades_2"]),
        3: float(params["facades_3"]),
        4: float(params["facades_4"]),
    }
    return float(mapping.get(int(bien["nb_facades"]), 0.0))


def calc_extramuros_impact(bien: dict, params: dict) -> float:
    # extramuros (balcon couvert, annexes hors murs etc.) valorisé au m²
    s = float(bien.get("surface_extramuros_m2", 0.0))
    if s <= 0:
        return 0.0
    return s * float(params["extramuros_eur_m2"])


def calc_surface_mix_impact(bien: dict, params: dict) -> float:
    """
    Si surface totale >> habitable, on pénalise une partie non habitable.
    C’est une règle simple “expert” (modifiable).
    """
    hab = float(bien["surface_habitable_m2"])
    tot = float(bien["surface_totale_m2"])
    if tot <= 0 or hab <= 0:
        return 0.0

    non_hab = max(0.0, tot - hab)
    if non_hab <= 0:
        return 0.0

    # pénalité au m² non habitable
    return non_hab * float(params["penalite_surface_non_habitable_eur_m2"])


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
    etat_map = {"Neuf / parfait": 10, "Bon etat": 8, "Etat moyen": 6, "A renover": 3, "Tres degrade": 1}
    parach_map = {"Haut standing": 9, "Standard": 7, "Basique": 5, "Non termine": 2}

    notes = [
        float(toiture_map.get(bien["toiture_etat"], 6)),
        float(chauff_map.get(bien["chauffage_type"], 6)),
        float(cuisine_map.get(bien["cuisine_etat"], 5)),
        float(sdb_map.get(bien["sdb_etat"], 5)),
        float(vitrage_map.get(bien["vitrage_type"], 6)),
        float(peb_map.get((bien.get("peb_lettre") or "C").upper(), 6)),
        float(etat_map.get(bien["etat_general"], 6)),
        float(parach_map.get(bien["parachevement"], 6)),
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


# =========================
# PDF vendeur 3 pages
# =========================
def build_pdf_3pages(bien: dict, marche: dict, impacts: dict, indice: float,
                     coef_quartier: float, coef_expert_pct: float,
                     valeur_tech: float, valeur_finale: float,
                     low: float, high: float, low_pct: float, high_pct: float) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Page 1
    draw_header(c, "Rapport d'estimation - Vente", "Synthese vendeur (page 1/3)")
    y = h - 165

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Bien")
    y -= 18

    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Client: {safe_text(bien['client'], 60) or '-'}"); y -= 14
    c.drawString(55, y, f"Adresse complete: {safe_text(bien['adresse'], 120) or '-'}"); y -= 14
    c.drawString(55, y, f"Code postal: {safe_text(bien['cp'], 10)}  |  Localite: {safe_text(bien['localite'], 40)}"); y -= 14
    c.drawString(55, y, f"Province: {bien['province']}  |  Type: {bien['type']}"); y -= 14

    c.drawString(55, y, f"Surface habitable: {bien['surface_habitable_m2']:.0f} m2  |  Surface totale: {bien['surface_totale_m2']:.0f} m2  |  Extramuros: {bien['surface_extramuros_m2']:.0f} m2"); y -= 14
    if bien["type"] == "Maison":
        c.drawString(55, y, f"Terrain: {bien['terrain_m2']:.0f} m2"); y -= 14

    c.drawString(55, y, f"Façades: {int(bien['nb_facades'])}  |  Etat general: {bien['etat_general']}  |  Parachevement: {bien['parachevement']}"); y -= 14

    c.drawString(55, y, f"Chambres: {int(bien.get('nb_chambres', 0))}  |  Salles de bain: {int(bien.get('nb_sdb', 0))}"); y -= 14

    if bien["type"] == "Appartement":
        c.drawString(55, y, f"Etage: {int(bien.get('etage', 0))}  |  Ascenseur: {'Oui' if bien.get('ascenseur') else 'Non'}"); y -= 14

    c.drawString(55, y, f"PEB: {bien['peb_lettre']}" + (f" ({bien['peb_kwh']:.0f} kWh/m2.an)" if bien['peb_kwh'] else "")); y -= 14
    c.drawString(55, y, f"Vitrage: {bien['vitrage_type']}  |  Chauffage: {bien['chauffage_type']}"); y -= 14

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

    sp = bien.get("surfaces_etages", [])
    if sp and sum(sp) > 0:
        c.drawString(55, y, "Surfaces par etage: " + " / ".join([f"{s:.0f} m2" for s in sp]))
        y -= 14

    y -= 8
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
    c.drawString(40, y, f"Coef quartier (auto): {coef_quartier:.2f}  |  Coef expert: {coef_expert_pct:+.1f}%")
    y -= 14
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Justification coef expert: {safe_text(bien['justif_coef'], 95) or '-'}")
    y -= 18

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Document indicatif - base marche auto (apprentissage) + analyse technique (outil interne).")
    c.showPage()

    # Page 2
    draw_header(c, "Detail des calculs", "Marche + impacts (page 2/3)")
    y = h - 165

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Marche (automatique)")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Prix/m2 base: {euro(marche['prix_m2_base'])}  |  Applique: {euro(marche['prix_m2_applique'])}  |  Source: {marche['prix_m2_source']}"); y -= 14
    c.drawString(55, y, f"Valeur batie (surface totale): {euro(marche['valeur_batie'])}"); y -= 14
    if bien["type"] == "Maison":
        c.drawString(55, y, f"Terrain: {euro(marche['terrain_m2'])}/m2  |  Valeur terrain: {euro(marche['valeur_terrain'])}"); y -= 14
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, f"Valeur marche (avant technique): {euro(marche['valeur_marche'])}")
    y -= 18

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Ajustements / Impacts (detail)")
    y -= 18
    c.setFont("Helvetica", 10)

    lines = [
        ("Coef quartier (auto)", (coef_quartier - 1.0) * marche["valeur_marche"]),
        ("Etat general", impacts["etat_general"]),
        ("Parachevement", impacts["parachevement"]),
        ("Nombre de facades", impacts["facades"]),
        ("Extramuros", impacts["extramuros"]),
        ("Surface non habitable (penalite)", impacts["surface_mix"]),
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
        if y < 80:
            c.showPage()
            draw_header(c, "Detail des calculs (suite)", "Impacts (page 2/3)")
            y = h - 165
            c.setFont("Helvetica", 10)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y, f"Total impacts (hors coef expert): {euro(impacts['total'])}")
    y -= 18

    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Synthese calcul")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(55, y, f"Valeur technique = (marche x coef quartier) + impacts = {euro(valeur_tech)}"); y -= 14
    c.drawString(55, y, f"Valeur finale = Valeur technique x (1 + coef expert) = {euro(valeur_finale)}"); y -= 18

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Les impacts et coefficients sont parametrables dans l'outil interne.")
    c.showPage()

    # Page 3
    draw_header(c, "Methodologie", "Explications (page 3/3)")
    y = h - 165

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Approche")
    y -= 18
    c.setFont("Helvetica", 10)
    lines3 = [
        "1) Marche automatique: base province + apprentissage (ventes encodees).",
        "2) Coef quartier (auto): ajuste selon ratios Vendu/Estime sur meme CP+localite+type.",
        "3) Impacts: etat general, parachèvement, facades, surfaces, technique + caracteristiques.",
        "4) Indice global (/10): toiture, chauffage, cuisine, sdb, vitrage, PEB, etat, parachèvement; influence la fourchette.",
        "5) Coef expert: ajustement final (rue, nuisances, vue, attractivite) avec justification.",
    ]
    for ln in lines3:
        c.drawString(55, y, ln)
        y -= 14

    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Recommandations")
    y -= 18
    c.setFont("Helvetica", 10)
    notes = [
        "Encoder le prix vendu apres chaque vente: l'outil devient plus precis automatiquement.",
        "Plusieurs ventes par localite => meilleure correction micro-zone (ex: Gilly vs Ransart).",
        "Les impacts representent un effet valeur, pas un devis travaux.",
    ]
    for ln in notes:
        c.drawString(55, y, f"- {ln}")
        y -= 14

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 40, "Outil interne - La Priorite Immobiliere.")
    c.save()

    buf.seek(0)
    return buf.getvalue()


# =========================
# Streamlit UI
# =========================
st.set_page_config(page_title="Estimateur Expert - La Priorite Immobiliere", layout="wide")
st.title("Estimateur Expert - La Priorite Immobiliere (Wallonie)")

if "params" not in st.session_state:
    st.session_state["params"] = DEFAULT_PARAMS.copy()
if "history" not in st.session_state:
    st.session_state["history"] = []

params = st.session_state["params"]
history = st.session_state["history"]

tabs = st.tabs(["1) Marche auto", "2) Technique", "3) Synthese + PDF", "4) Historique (ventes)"])


# =========================
# Sidebar (données dossier)
# =========================
with st.sidebar:
    st.subheader("Identite dossier")
    client = st.text_input("Client (interne)", value="")
    adresse = st.text_input("Adresse complete (Rue + numero, CP, localite)", value="")
    cp = st.text_input("Code postal (Wallonie)", value="")
    localite = st.text_input("Localite / village", value="")

    province = st.selectbox("Province", ["Hainaut", "Namur", "Liege", "Brabant_wallon", "Luxembourg"])

    st.subheader("Bien")
    type_bien = st.selectbox("Type", ["Maison", "Appartement", "Commerce"])

    # === Surfaces (demandé) ===
    surface_habitable = st.number_input("Surface habitable (m²)", min_value=0.0, value=100.0, step=1.0)
    surface_totale = st.number_input("Surface totale (m²)", min_value=1.0, value=120.0, step=1.0)
    surface_extramuros = st.number_input("Surface extramuros (m²)", min_value=0.0, value=0.0, step=1.0)

    terrain = 0.0
    if type_bien == "Maison":
        terrain = st.number_input("Terrain (m²)", min_value=0.0, value=0.0, step=10.0)

    nb_facades = st.selectbox("Nombre de facades", [2, 3, 4])

    etat_general = st.selectbox(
        "Etat general du bien",
        ["Neuf / parfait", "Bon etat", "Etat moyen", "A renover", "Tres degrade"]
    )

    parachevement = st.selectbox(
        "Niveau de parachèvement",
        ["Haut standing", "Standard", "Basique", "Non termine"]
    )

    nb_chambres = st.number_input("Nombre de chambres", min_value=0, value=2, step=1)
    nb_sdb = st.number_input("Nombre de salles de bain", min_value=0, value=1, step=1)

    # Appartement
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
        "Surface grenier amenageable (m²)",
        min_value=0.0, value=0.0, step=5.0,
        disabled=not grenier_amenageable
    )

    st.subheader("Surfaces par etage")
    nb_etages = st.number_input("Nombre d'etages (1 = un seul niveau)", min_value=1, value=1, step=1)
    surfaces_etages = []
    for i in range(int(nb_etages)):
        s = st.number_input(
            f"Surface etage {i+1} (m²)",
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
    justif_coef = st.text_area("Justification coef expert", value="", height=80)


# Bien dict
bien = {
    "client": client,
    "adresse": adresse,
    "cp": cp.strip(),
    "localite": localite.strip(),
    "province": province,
    "type": type_bien,

    # surfaces
    "surface_habitable_m2": float(surface_habitable),
    "surface_totale_m2": float(surface_totale),
    "surface_extramuros_m2": float(surface_extramuros),

    "terrain_m2": float(terrain),

    "nb_facades": int(nb_facades),
    "etat_general": etat_general,
    "parachevement": parachevement,

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

    # Technique defaults (remplis onglet technique)
    "toiture_grenier": False,
    "toiture_surface_grenier_m2": 0.0,
    "toiture_etat": "Parfaite",
    "chauffage_type": "Gaz condensation",
    "cuisine_etat": "Bonne",
    "sdb_etat": "Bonne",
    "vitrage_type": "Double recent",
    "peb_lettre": "C",
    "peb_kwh": 0.0,
}


def compute_impacts(bien: dict, params: dict) -> dict:
    impacts = {
        "etat_general": calc_etat_general_impact(bien, params),
        "parachevement": calc_parachevement_impact(bien, params),
        "facades": calc_facades_impact(bien, params),
        "extramuros": calc_extramuros_impact(bien, params),
        "surface_mix": calc_surface_mix_impact(bien, params),

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
        impacts["etat_general"] + impacts["parachevement"] + impacts["facades"]
        + impacts["extramuros"] + impacts["surface_mix"]
        + impacts["toiture"] + impacts["chauffage"] + impacts["vitrage"] + impacts["peb"]
        + impacts["cuisine"] + impacts["sdb_etat"]
        + impacts["chambres"] + impacts["sdb_count"] + impacts["etage_appart"]
        + impacts["parking_garage"] + impacts["balcon_terrasse"] + impacts["jardin_cave_grenier"]
    )
    return impacts


# =========================
# TAB 1 : Marché auto
# =========================
with tabs[0]:
    st.subheader("Marche automatique (sans saisir prix/m2)")
    if not bien["cp"] or not bien["localite"]:
        st.info("Remplis au minimum: Code postal + Localite (dans la barre de gauche).")

    marche = calc_marche_auto(bien, params, history)
    coef_quartier = calc_coef_quartier(history, bien["cp"], bien["localite"], bien["type"], params)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prix/m2 (source)", f"{marche['prix_m2_source']}")
    c2.metric("Prix/m2 applique", euro(marche["prix_m2_applique"]))
    c3.metric("Coef quartier (auto)", f"{coef_quartier:.2f}")
    c4.metric("Valeur marche (ajustee)", euro(marche["valeur_marche"] * coef_quartier))

    if bien["type"] == "Maison":
        st.caption(f"Terrain: {euro(marche['terrain_m2'])}/m2 | Valeur terrain: {euro(marche['valeur_terrain'])}")

    st.markdown("---")
    st.subheader("Rappel surfaces (dossier)")
    s1, s2, s3 = st.columns(3)
    s1.metric("Habitable", f"{bien['surface_habitable_m2']:.0f} m²")
    s2.metric("Totale", f"{bien['surface_totale_m2']:.0f} m²")
    s3.metric("Extramuros", f"{bien['surface_extramuros_m2']:.0f} m²")

    st.markdown("---")
    st.subheader("Parametres marche (optionnel)")
    with st.expander("Ajuster les bases province (si tu veux)"):
        colA, colB = st.columns(2)
        with colA:
            st.write("Bases €/m2 (province)")
            params["base_m2_Hainaut_Maison"] = st.number_input("Hainaut Maison", value=int(params["base_m2_Hainaut_Maison"]), step=50)
            params["base_m2_Hainaut_Appartement"] = st.number_input("Hainaut Appartement", value=int(params["base_m2_Hainaut_Appartement"]), step=50)
            params["base_m2_Hainaut_Commerce"] = st.number_input("Hainaut Commerce", value=int(params["base_m2_Hainaut_Commerce"]), step=50)

            params["base_m2_Namur_Maison"] = st.number_input("Namur Maison", value=int(params["base_m2_Namur_Maison"]), step=50)
            params["base_m2_Namur_Appartement"] = st.number_input("Namur Appartement", value=int(params["base_m2_Namur_Appartement"]), step=50)
            params["base_m2_Namur_Commerce"] = st.number_input("Namur Commerce", value=int(params["base_m2_Namur_Commerce"]), step=50)

            params["base_m2_Liege_Maison"] = st.number_input("Liege Maison", value=int(params["base_m2_Liege_Maison"]), step=50)
            params["base_m2_Liege_Appartement"] = st.number_input("Liege Appartement", value=int(params["base_m2_Liege_Appartement"]), step=50)
            params["base_m2_Liege_Commerce"] = st.number_input("Liege Commerce", value=int(params["base_m2_Liege_Commerce"]), step=50)

        with colB:
            params["base_m2_Brabant_wallon_Maison"] = st.number_input("Brabant wallon Maison", value=int(params["base_m2_Brabant_wallon_Maison"]), step=50)
            params["base_m2_Brabant_wallon_Appartement"] = st.number_input("Brabant wallon Appartement", value=int(params["base_m2_Brabant_wallon_Appartement"]), step=50)
            params["base_m2_Brabant_wallon_Commerce"] = st.number_input("Brabant wallon Commerce", value=int(params["base_m2_Brabant_wallon_Commerce"]), step=50)

            params["base_m2_Luxembourg_Maison"] = st.number_input("Luxembourg Maison", value=int(params["base_m2_Luxembourg_Maison"]), step=50)
            params["base_m2_Luxembourg_Appartement"] = st.number_input("Luxembourg Appartement", value=int(params["base_m2_Luxembourg_Appartement"]), step=50)
            params["base_m2_Luxembourg_Commerce"] = st.number_input("Luxembourg Commerce", value=int(params["base_m2_Luxembourg_Commerce"]), step=50)

            st.write("Terrain €/m2 (maisons)")
            params["terrain_Hainaut"] = st.number_input("Terrain Hainaut", value=int(params["terrain_Hainaut"]), step=5)
            params["terrain_Namur"] = st.number_input("Terrain Namur", value=int(params["terrain_Namur"]), step=5)
            params["terrain_Liege"] = st.number_input("Terrain Liege", value=int(params["terrain_Liege"]), step=5)
            params["terrain_Brabant_wallon"] = st.number_input("Terrain Brabant wallon", value=int(params["terrain_Brabant_wallon"]), step=5)
            params["terrain_Luxembourg"] = st.number_input("Terrain Luxembourg", value=int(params["terrain_Luxembourg"]), step=5)

        params["seuil_degressif_m2"] = st.number_input("Seuil degressif (m2)", value=int(params["seuil_degressif_m2"]), step=10)
        params["degressif_pct"] = st.number_input("Degressif (%)", value=float(params["degressif_pct"] * 100)) / 100.0

    st.session_state["params"] = params


# =========================
# TAB 2 : Technique
# =========================
with tabs[1]:
    st.subheader("Analyse technique (details)")

    st.markdown("### Toiture")
    t1, t2, t3 = st.columns(3)
    with t1:
        toiture_grenier = st.checkbox("Grenier present (toiture)", value=False)
    with t2:
        toiture_surface_grenier = st.number_input("Surface grenier (toiture) (m²)", min_value=0.0, value=0.0, step=5.0, disabled=not toiture_grenier)
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
    bien["toiture_surface_grenier_m2"] = float(toiture_surface_grenier)
    bien["toiture_etat"] = toiture_etat
    bien["chauffage_type"] = chauffage_type
    bien["vitrage_type"] = vitrage_type
    bien["peb_lettre"] = peb_lettre
    bien["peb_kwh"] = float(peb_kwh)
    bien["cuisine_etat"] = cuisine_etat
    bien["sdb_etat"] = sdb_etat

    impacts = compute_impacts(bien, params)
    indice = calc_indice(bien)

    st.markdown("---")
    st.subheader("Impacts (résumé)")
    r1 = st.columns(6)
    r1[0].metric("Etat general", euro(impacts["etat_general"]))
    r1[1].metric("Parachevement", euro(impacts["parachevement"]))
    r1[2].metric("Facades", euro(impacts["facades"]))
    r1[3].metric("Extramuros", euro(impacts["extramuros"]))
    r1[4].metric("Surface non hab.", euro(impacts["surface_mix"]))
    r1[5].metric("Toiture", euro(impacts["toiture"]))

    r2 = st.columns(6)
    r2[0].metric("Chauffage", euro(impacts["chauffage"]))
    r2[1].metric("Vitrage", euro(impacts["vitrage"]))
    r2[2].metric("PEB", euro(impacts["peb"]))
    r2[3].metric("Cuisine", euro(impacts["cuisine"]))
    r2[4].metric("SDB etat", euro(impacts["sdb_etat"]))
    r2[5].metric("Chambres", euro(impacts["chambres"]))

    r3 = st.columns(6)
    r3[0].metric("Nb SDB", euro(impacts["sdb_count"]))
    r3[1].metric("Etage appart", euro(impacts["etage_appart"]) if bien["type"] == "Appartement" else "0 €")
    r3[2].metric("Parking/Garage", euro(impacts["parking_garage"]))
    r3[3].metric("Balcon/Terrasse", euro(impacts["balcon_terrasse"]))
    r3[4].metric("Jardin/Cave/Grenier", euro(impacts["jardin_cave_grenier"]))
    r3[5].metric("TOTAL impacts", euro(impacts["total"]))

    st.metric("Indice global", f"{indice:.1f} / 10")

    total_etages = sum(bien["surfaces_etages"])
    if total_etages > 0 and abs(total_etages - bien["surface_totale_m2"]) > 5:
        st.warning("Surfaces par etage ≠ surface totale (ecart > 5 m2)")


# =========================
# TAB 3 : Synthèse + PDF + Save
# =========================
with tabs[2]:
    st.subheader("Synthese experte + Rapport vendeur")

    marche = calc_marche_auto(bien, params, history)
    coef_quartier = calc_coef_quartier(history, bien["cp"], bien["localite"], bien["type"], params)

    impacts = compute_impacts(bien, params)
    indice = calc_indice(bien)

    valeur_marche_ajustee = marche["valeur_marche"] * coef_quartier
    valeur_tech = valeur_marche_ajustee + impacts["total"]
    coef = float(bien["coef_expert_pct"]) / 100.0
    valeur_finale = valeur_tech * (1.0 + coef)

    low, high, low_pct, high_pct = fourchette_from_indice(valeur_finale, indice, params)

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Valeur marche (auto)", euro(marche["valeur_marche"]))
    a2.metric("Coef quartier (auto)", f"{coef_quartier:.2f}")
    a3.metric("Total impacts", euro(impacts["total"]))
    a4.metric("Valeur finale", euro(valeur_finale))

    b1, b2, b3 = st.columns(3)
    b1.metric("Indice global", f"{indice:.1f} / 10")
    b2.metric("Fourchette basse", euro(low))
    b3.metric("Fourchette haute", euro(high))

    st.caption(f"Prix/m2 source: {marche['prix_m2_source']} | Prix/m2 applique: {euro(marche['prix_m2_applique'])}")

    pdf = build_pdf_3pages(
        bien=bien,
        marche=marche,
        impacts=impacts,
        indice=indice,
        coef_quartier=coef_quartier,
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
    st.subheader("Enregistrer cette estimation (Historique)")

    if st.button("Enregistrer"):
        record = {
            "date_estimation": date.today().isoformat(),
            "client": safe_text(bien["client"], 60),
            "adresse_complete": safe_text(bien["adresse"], 140),
            "cp": safe_text(bien["cp"], 10),
            "localite": safe_text(bien["localite"], 40),
            "province": bien["province"],
            "type_bien": bien["type"],

            "surface_habitable_m2": round(float(bien["surface_habitable_m2"]), 1),
            "surface_totale_m2": round(float(bien["surface_totale_m2"]), 1),
            "surface_extramuros_m2": round(float(bien["surface_extramuros_m2"]), 1),
            "terrain_m2": round(float(bien["terrain_m2"]), 1),

            "nb_facades": int(bien["nb_facades"]),
            "etat_general": bien["etat_general"],
            "parachevement": bien["parachevement"],

            "nb_chambres": int(bien["nb_chambres"]),
            "nb_sdb": int(bien["nb_sdb"]),
            "etage": int(bien["etage"]),
            "ascenseur": bool(bien["ascenseur"]),

            "peb_lettre": bien["peb_lettre"],
            "peb_kwh": round(float(bien["peb_kwh"]), 0),
            "vitrage_type": bien["vitrage_type"],

            "toiture_etat": bien["toiture_etat"],
            "toiture_grenier": bool(bien["toiture_grenier"]),
            "toiture_surface_grenier_m2": round(float(bien["toiture_surface_grenier_m2"]), 1),

            "chauffage_type": bien["chauffage_type"],
            "cuisine_etat": bien["cuisine_etat"],
            "sdb_etat": bien["sdb_etat"],

            "parking_places": int(bien["nb_places_parking"]),
            "garage": bool(bien["garage"]),
            "balcon": bool(bien["balcon"]),
            "terrasse": bool(bien["terrasse"]),
            "jardin": bool(bien["jardin"]),
            "cave": bool(bien["cave"]),

            "grenier_amenageable": bool(bien["grenier_amenageable"]),
            "grenier_amenageable_surface_m2": round(float(bien["grenier_amenageable_surface_m2"]), 1),

            "nb_etages": int(bien["nb_etages"]),
            "surfaces_etages": " / ".join([str(int(s)) for s in bien.get("surfaces_etages", [])]),

            "prix_m2_source": marche["prix_m2_source"],
            "prix_m2_applique": round(float(marche["prix_m2_applique"]), 1),
            "coef_quartier": round(float(coef_quartier), 3),

            "indice_etat": round(float(indice), 1),
            "coef_expert_pct": round(float(bien["coef_expert_pct"]), 1),
            "justif_coef": safe_text(bien["justif_coef"], 140),

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


# =========================
# TAB 4 : Historique + prix vendu (pour apprendre)
# =========================
with tabs[3]:
    st.subheader("Historique des estimations (et ventes)")

    hist = st.session_state["history"]
    if not hist:
        st.info("Aucune estimation enregistree pour le moment. Fais une estimation puis clique sur 'Enregistrer'.")
        st.stop()

    st.dataframe(hist, use_container_width=True)

    st.markdown("---")
    st.subheader("Encoder une vente (IMPORTANT: l’outil apprend automatiquement)")

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
        if st.button("Enregistrer la vente"):
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
            st.success("Vente enregistree. Le marche auto s’améliore pour ce CP/localite/type.")
