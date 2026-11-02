#!/usr/bin/env python3
"""Génère le compte rendu PDF du "Brief du lundi" KSE à partir d'un fichier JSON.

Usage : python build_cr.py --data donnees.json --out CR_Brief_du_lundi_AAAA-MM-JJ.pdf

Dépendances : reportlab, matplotlib, pdfplumber (facultatif, pour le contrôle du nombre de pages).
La police Inter est lue dans ../assets/fonts. Le schéma du JSON est décrit dans references/schema-donnees.md.
"""
import argparse, json, os, re, sys, tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, FancyBboxPatch
from matplotlib import font_manager as fm

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                KeepTogether, HRFlowable, Image, Flowable)

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# ---- Charte (couleurs corporate Kiloutou, toujours sur fond blanc)
YELLOW = colors.HexColor("#FFC800")
LBLUE = colors.HexColor("#E5ECFA")
DARK = colors.HexColor("#1E2A3A")
GREY = colors.HexColor("#5F6B7A")
NAVY = colors.HexColor("#1F3A5F")      # en-tête du tableau des dossiers
LINE = colors.HexColor("#D5DAE1")
BLACK = colors.black
HEX_Y, HEX_LB, HEX_DK, HEX_GR = "#FFC800", "#E5ECFA", "#1E2A3A", "#6B7686"


def register_fonts():
    for name, f in (("Inter", "Inter-Regular"), ("Inter-Light", "Inter-Light"),
                    ("Inter-Bold", "Inter-Bold"), ("Inter-Black", "Inter-Black")):
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f"{f}.ttf")))
    pdfmetrics.registerFontFamily("Inter", normal="Inter", bold="Inter-Bold",
                                  italic="Inter", boldItalic="Inter-Bold")
    for f in ("Regular", "Bold"):
        fm.fontManager.addfont(str(FONT_DIR / f"Inter-{f}.ttf"))
    plt.rcParams.update({"font.family": "Inter", "text.color": HEX_DK})


# ------------------------------------------------------------------ visuels KPI
def pct_from(value):
    """'85%' / '0 %' -> 0.85 / 0.0 ; texte non numérique -> None."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", str(value))
    return float(m.group(1).replace(",", ".")) / 100 if m else None



GREEN_H, ORANGE_H, RED_H = "#1E9E4A", "#F28C00", "#D62828"


def trend_arrow(ax, x, y, cur, prev, higher_better=True, size=0.17):
    """Flèche en gras (coin haut droit) : verte = mieux que la semaine précédente,
    orange = iso, rouge = moins bien. Rien n'est dessiné si prev est absent."""
    if prev is None or cur is None:
        return
    if cur == prev:
        col, dy = ORANGE_H, 0
    else:
        up = cur > prev
        col, dy = (GREEN_H if up == higher_better else RED_H), (1 if up else -1)
    kw = dict(arrowstyle="-|>,head_length=0.55,head_width=0.38", color=col, lw=2.6, shrinkA=0, shrinkB=0)
    if dy == 0:
        ax.annotate("", xy=(x + size, y), xytext=(x - size, y), arrowprops=kw)
    else:
        ax.annotate("", xy=(x, y + dy * size), xytext=(x, y - dy * size), arrowprops=kw)


def kpi_objectifs_png(kpi, path):
    items = list(kpi["objectifs"])
    W, H = 7.0, 2.35
    n = len(items) + 1
    cw = (W - 0.18 * (n - 1) * 1.0) / n if n != 4 else 1.62
    gap = (W - n * cw) / (n - 1)
    fig = plt.figure(figsize=(W, H), facecolor="white")
    cards = []
    for o in items:
        unit = o.get("unit", "")
        sub = f"{unit} - objectif {o['target']}" if unit else f"objectif {o['target']}"
        cards.append((o["label"], str(o["value"]), min(o["value"] / o["target"], 1), sub,
                      f"{round(100 * o['value'] / o['target'])} % de l'objectif", o["value"], o.get("prev")))
    primes = str(kpi.get("primes", "-"))
    pp = pct_from(primes)
    cards.append(("Primes mensuelles", primes if pp is not None else primes, pp or 0, kpi.get("mois_court", "mois"), None,
                  None if pp is None else round(pp * 100), kpi.get("primes_prev")))
    for i, (name, big, p, sub, badge, cur, prev) in enumerate(cards):
        ax = fig.add_axes([i * (cw + gap) / W, 0, cw / W, 1]); ax.axis("off")
        ax.set_xlim(0, cw); ax.set_ylim(0, H)
        ax.add_patch(FancyBboxPatch((0, 0), cw, H, boxstyle="round,pad=0,rounding_size=0.16", fc=HEX_LB, ec="none"))
        ax.text(cw / 2, H - 0.24, name, ha="center", va="center", fontsize=8, fontweight="bold")
        trend_arrow(ax, cw - 0.15, H - 0.2, cur, prev, size=0.1)
        cx, cy, R = cw / 2, 1.22, 0.60
        ax.add_patch(Wedge((cx, cy), R, 0, 360, width=0.18, fc="white", ec="none"))
        if p > 0:
            ax.add_patch(Wedge((cx, cy), R, 90 - 360 * p, 90, width=0.18, fc=HEX_Y, ec="none"))
        ax.text(cx, cy + 0.07, big, ha="center", va="center", fontsize=18, fontweight="bold")
        ax.text(cx, cy - 0.22, sub, ha="center", va="center", fontsize=6.3, color=HEX_GR)
        if badge:
            ax.text(cw / 2, 0.22, badge, ha="center", va="center", fontsize=7.5, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none"))
    fig.savefig(path, dpi=220, facecolor="white"); plt.close(fig)
    return 2.35 / 7.0


def kpi_devis_png(d, path, dp=None):
    dp = dp or {}
    W, H = 7.0, 2.45
    fig = plt.figure(figsize=(W, H), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off"); ax.set_xlim(0, W); ax.set_ylim(0, H)
    x0, g, h = 1.35, 0.12, 0.72
    cw = (W - x0 - 2 * g) / 3

    def card(col, yb, num, label, fc=HEX_LB, key=None, hb=True):
        x = x0 + col * (cw + g)
        ax.add_patch(FancyBboxPatch((x, yb), cw, h, boxstyle="round,pad=0,rounding_size=0.13", fc=fc, ec="none"))
        ax.text(x + 0.38, yb + h / 2, str(num), ha="center", va="center", fontsize=19, fontweight="bold")
        ax.text(x + 0.78, yb + h / 2, label, ha="left", va="center", fontsize=8, linespacing=1.3)
        if key:
            trend_arrow(ax, x + cw - 0.2, yb + h - 0.19, num, dp.get(key), hb, size=0.12)

    def lab(yb, t):
        ax.text(0.02, yb + h / 2, t, fontsize=8.5, fontweight="bold", va="center", linespacing=1.3)

    yA, yB, yC = 2 * (h + g), h + g, 0.0
    lab(yA, "Devis et\nlocations")
    card(0, yA, d["envoyes"], "Devis\nenvoyés", key="envoyes", hb=True); card(1, yA, d["relances"], "Devis\nrelancés", key="relances", hb=True)
    card(2, yA, d["arrets_loc"], "Arrêts\nde loc", key="arrets_loc", hb=True)
    lab(yB, "Points de\nvigilance")
    # Le chiffre en retard de relance est mis en avant (jaune) s'il est > 0
    card(0, yB, d["retard_relance"], "dont en retard\nde relance", key="retard_relance", hb=False, fc=HEX_Y if d["retard_relance"] > 0 else HEX_LB)
    card(1, yB, d["retard_validation"], "dont en retard\nde validation", key="retard_validation", hb=False,
         fc=HEX_Y if d["retard_validation"] > 0 else HEX_LB)
    lab(yC, "Départs")
    card(0, yC, d["departs_moins_3j"], "Départs\n- 3 jrs", key="departs_moins_3j", hb=True)
    card(1, yC, d["departs_3_14j"], "Départs entre\n3 et 14 jrs", key="departs_3_14j", hb=True)
    card(2, yC, d["departs_14j_plus"], "Départs\n14 jrs et +", key="departs_14j_plus", hb=True)
    fig.savefig(path, dpi=220, facecolor="white"); plt.close(fig)
    return 2.45 / 7.0


# ------------------------------------------------------------------ plan d'action (colonnes)
class Kanban(Flowable):
    def __init__(self, width, columns, widths=None):
        super().__init__()
        self.w, self.g, self.cols = width, 3 * mm, columns
        tot = width - (len(columns) - 1) * self.g
        if not widths:
            wts = [1.35 + 0.35 * len(c["cards"]) for c in columns]
            widths = [x / sum(wts) for x in wts]
        self.cws = [tot * f for f in widths]
        self.h = max(26 + sum(len(simpleSplit(c["text"], "Inter", 8, self.cws[k] - 14)) * 10.2 + 35
                              for c in col["cards"]) for k, col in enumerate(columns))

    def wrap(self, aw, ah):
        return self.w, self.h

    def draw(self):
        c, sw, x = self.canv, pdfmetrics.stringWidth, 0
        for k, col in enumerate(self.cols):
            cw = self.cws[k]; tw = cw - 14; y0 = self.h
            c.setFillColor(YELLOW if col.get("highlight") else LBLUE)
            c.roundRect(x, y0 - 18, cw, 18, 9, fill=1, stroke=0)
            c.setFillColor(DARK); c.setFont("Inter-Bold", 8.5); c.drawString(x + 9, y0 - 12.3, col["name"])
            c.setFont("Inter-Black", 9); c.drawRightString(x + cw - 9, y0 - 12.5, str(len(col["cards"])))
            yy = y0 - 26
            for card in col["cards"]:
                ls = simpleSplit(card["text"], "Inter", 8, tw); hh = len(ls) * 10.2 + 30
                c.setFillColor(LBLUE); c.roundRect(x, yy - hh, cw, hh, 8, fill=1, stroke=0)
                c.setFont("Inter", 8); c.setFillColor(DARK)
                for i, l in enumerate(ls):
                    c.drawString(x + 7, yy - i * 10.2 - 13, l)
                cx = x + 14
                for o in card["owners"]:
                    if o == "Équipe":
                        pw = sw("Équipe", "Inter-Bold", 6.5) + 12
                        c.setFillColor(YELLOW); c.roundRect(x + 7, yy - hh + 6, pw, 12, 6, fill=1, stroke=0)
                        c.setFillColor(DARK); c.setFont("Inter-Bold", 6.5); c.drawString(x + 13, yy - hh + 9.5, "Équipe")
                    else:
                        c.setFillColor(YELLOW); c.circle(cx, yy - hh + 12, 7.5, fill=1, stroke=0)
                        c.setFillColor(DARK); c.setFont("Inter-Bold", 5.8); c.drawCentredString(cx, yy - hh + 10, o)
                        cx += 17
                yy -= hh + 5
            x += cw + self.g


# ------------------------------------------------------------------ document
def build(data, out_pdf):
    register_fonts()
    base = ParagraphStyle("base", fontName="Inter", fontSize=9.5, leading=13.5, textColor=colors.HexColor("#222222"))
    t1 = ParagraphStyle("t1", parent=base, fontName="Inter-Light", fontSize=20, leading=24, textColor=BLACK)
    t2 = ParagraphStyle("t2", parent=base, fontName="Inter-Black", fontSize=60, leading=64, textColor=BLACK)
    t3 = ParagraphStyle("t3", parent=base, fontName="Inter-Light", fontSize=14, leading=18, textColor=BLACK, spaceBefore=6)
    sub = ParagraphStyle("sub", parent=base, textColor=GREY, leading=13)
    h = ParagraphStyle("h", parent=base, fontName="Inter-Bold", fontSize=12, leading=15, textColor=BLACK,
                       spaceBefore=14, spaceAfter=4)
    bul = ParagraphStyle("bul", parent=base, leftIndent=12, bulletIndent=2, spaceAfter=2.5,
                         bulletFontName="Inter", bulletFontSize=9.5)
    cell = ParagraphStyle("cell", parent=base, fontSize=9, leading=12)
    cellb = ParagraphStyle("cellb", parent=cell, fontName="Inter-Bold")
    head = ParagraphStyle("head", parent=cell, fontName="Inter-Bold", textColor=colors.white)
    note = ParagraphStyle("note", parent=base, fontSize=8, leading=11, textColor=GREY)

    def H(t):
        return [Paragraph(t, h), HRFlowable(width="100%", thickness=2.5, color=YELLOW, spaceAfter=6)]

    tmp = tempfile.mkdtemp()
    s = []
    s += [Paragraph("Compte rendu", t1), Paragraph("Brief du lundi", t2), Paragraph(data["date_longue"], t3),
          Spacer(1, 8), Paragraph("Kiloutou Sport &amp; Event", sub),
          Paragraph(f"Participants : {data['participants']} &nbsp;|&nbsp; Absent : {data['absents']}"
                    if data.get("absents") else f"Participants : {data['participants']}", sub)]

    # 1. Débrief
    s += H("1. Débrief de la semaine")
    s += [Paragraph(t, bul, bulletText="\u2022") for t in data["debrief"]]

    # 2. Dossiers en cours
    s += H("2. Dossiers en cours")
    rows = [[Paragraph("Dossier", head), Paragraph("Situation", head)]]
    rows += [[Paragraph(a, cellb), Paragraph(b, cell)] for a, b in data["dossiers"]]
    t = Table(rows, colWidths=[42 * mm, 128 * mm], repeatRows=1)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                           ("BACKGROUND", (0, 0), (-1, 0), NAVY)]))
    s.append(t)

    # 3. Plan d'action
    people = data["personnes"]
    used = []
    for col in data["plan"]["colonnes"]:
        for c in col["cards"]:
            for o in c["owners"]:
                if o != "Équipe" and o not in used:
                    used.append(o)
    legend = " &nbsp;|&nbsp; ".join(f"{k} {people[k]}" for k in used)
    legend += ". « À planifier » : échéance non précisée lors du brief."
    s.append(KeepTogether(H("3. Plan d'action") + [Kanban(170 * mm, data["plan"]["colonnes"], data["plan"].get("largeurs")),
                                                     Spacer(1, 6), Paragraph(legend, note)]))

    # 4. KPI
    k = data["kpi"]
    p1, p2 = os.path.join(tmp, "obj.png"), os.path.join(tmp, "devis.png")
    r1 = kpi_objectifs_png(k, p1); r2 = kpi_devis_png(k["devis"], p2, k.get("devis_prev"))
    img = lambda p, r: Image(p, width=154 * mm, height=154 * mm * r, hAlign="LEFT")
    src = (f"Sources : SoR, onglet KPI's TEAM, au {k['date_lecture']} (A33:F45 pour les objectifs, H34:J44 pour les devis "
           "et départs). Mois en cours : le réalisé n'est pas consolidé ; pourcentages calculés sur l'objectif du mois "
           "complet. Les libellés « dont en retard... » sont placés dans l'alignement des colonnes du tableau source. "
           "Compte rendu rédigé à partir des notes Gemini du Brief du lundi (générées automatiquement, susceptibles de "
           "contenir des erreurs).")
    s.append(KeepTogether([Paragraph("4. Synthèse KPI's", h),
                           HRFlowable(width="100%", thickness=2.5, color=YELLOW, spaceAfter=6),
                           Paragraph(f"<b>Objectifs du mois - {k['mois']}</b>", base), Spacer(1, 4), img(p1, r1),
                           Spacer(1, 5), Paragraph("<b>Suivi des devis et des départs</b>", base), Spacer(1, 4), img(p2, r2),
                           Spacer(1, 5), Paragraph(src, note)]))

    # Un chapitre ne se coupe jamais entre deux pages
    out, cur = [], None
    for it in s:
        if isinstance(it, Paragraph) and it.style.name == "h":
            if cur: out.append(KeepTogether(cur))
            cur = [it]
        elif isinstance(it, KeepTogether):
            if cur: out.append(KeepTogether(cur)); cur = None
            out.append(it)
        elif cur is not None:
            cur.append(it)
        else:
            out.append(it)
    if cur: out.append(KeepTogether(cur))

    def footer(c, d):
        c.saveState(); c.setFont("Inter", 8); c.setFillColor(GREY)
        c.drawString(20 * mm, 10 * mm, f"KSE - Brief du lundi {data['date_courte']}")
        c.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {d.page}")
        c.restoreState()

    doc = SimpleDocTemplate(out_pdf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"CR Brief du lundi - {data['date_courte']}", author="KSE")
    doc.build(out, onFirstPage=footer, onLaterPages=footer)
    return doc.page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    data = json.load(open(a.data, encoding="utf-8"))
    pages = build(data, a.out)
    print(f"PDF généré : {a.out} ({pages} page(s))")
    if pages != 2:
        print("ATTENTION : le CR doit tenir en 2 pages. Raccourcir les libellés (plan d'action, dossiers, débrief).",
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
