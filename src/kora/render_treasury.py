"""L'ecran du TRESOR (money.py), dans le style de l'ecran du commerce :
  - tuiles : le tresor, les rentrees et les depenses du dernier mois, la
    balance, l'impot, l'etat de la solde ;
  - a gauche, le COMPTE DU MOIS (chaque rentree, chaque depense) et ce que
    le mois prochain promet ;
  - au milieu, le BUDGET, en CURSEURS : l'impot en argent (0 a 8 sicles pour
    cent villageois), la solde des troupes, les gages des gens de metier,
    les presents aux familles, la paie des batisseurs (0 a 200 % du tarif) ;
    puis les droits de passage et ce que l'argent fait ailleurs ;
  - a droite, le graphe du tresor des 24 derniers mois.
treasury_layout et treasury_hit sont purs (tests) ; draw_treasury dessine.
Tout changement passe par commands.py ("budget").
"""

from __future__ import annotations

import pygame

from src.kora import laws, money, tech, theme
from src.kora.peoples import color_of
from src.kora.layout import HUD_HEIGHT
from src.kora.render_tech import BAD, GOLD, GOOD, INK, NOTE, SOFT
from src.kora.theme import C, _gradient_card
from src.kora.render_village import WARN, _fonts, _frame, _hover, _section, _tile, _tip

SLIDERS = money.SLIDER_KEYS


def treasury_layout(width: int, height: int) -> dict:
    bx = 12
    by = HUD_HEIGHT + 6
    bw = max(760, width - 66 - 24)
    bh = max(480, height - HUD_HEIGHT - 14)
    close = (bx + bw - 24 - 136, by + 16, 136, 28)
    tiles_y = by + 62
    n = 6
    tw = (bw - 48 - (n - 1) * 10) // n
    tiles = [(bx + 24 + i * (tw + 10), tiles_y, tw, 56) for i in range(n)]
    body_y = tiles_y + 56 + 14
    body_h = by + bh - 14 - body_y
    inner = bw - 48
    lw = int(inner * 0.30)
    mw = int(inner * 0.38)
    rw = inner - lw - mw - 32
    left = (bx + 24, body_y, lw, body_h)
    mid = (left[0] + lw + 16, body_y, mw, body_h)
    right = (mid[0] + mw + 16, body_y, rw, body_h)
    # Le budget : un curseur par ligne (l'impot, puis les depenses).
    y = body_y + 24
    sliders = {}
    block = max(66, min(84, (body_y + body_h - y - 110) // len(SLIDERS)))
    for key in SLIDERS:
        row = (mid[0], y, mw, block - 6)
        track = (mid[0] + 40, y + 32, mw - 80 - 120, 14)
        sliders[key] = {
            "row": row,
            "track": track,
            "minus": (mid[0] + 8, y + 27, 24, 24),
            "plus": (track[0] + track[2] + 8, y + 27, 24, 24),
        }
        y += block
    tolls = (mid[0], y, mw, max(40, body_y + body_h - y))
    graph = (right[0], body_y + 24, rw, max(120, min(320, body_h // 2)))
    return {
        "box": (bx, by, bw, bh),
        "close": close,
        "tiles": tiles,
        "left": left,
        "mid": mid,
        "right": right,
        "sliders": sliders,
        "tolls": tolls,
        "graph": graph,
    }


def treasury_hit(lay: dict, mx: int, my: int):
    if not lay:
        return None
    if _hover(lay["close"], mx, my):
        return "mclose"
    for key, rects in lay["sliders"].items():
        if _hover(rects["minus"], mx, my):
            return f"mminus:{key}"
        if _hover(rects["plus"], mx, my):
            return f"mplus:{key}"
        tx, ty, tw, th = rects["track"]
        if _hover((tx - 8, ty - 8, tw + 16, th + 16), mx, my):
            return f"mslide:{key}"
    if _hover(lay["box"], mx, my):
        return "panel"
    return None


def slider_span(key: str) -> tuple:
    """(plus petit, plus grand, pas) d'un curseur du budget."""
    if key == "impot":
        return 0, money.TAX_MAX, 1
    return 0.0, money.PAY_MAX, money.PAY_STEP


def slider_value(lay: dict, key: str, mx: int):
    """La valeur du curseur `key` sous la souris (a son pas le plus proche)."""
    tx, _ty, tw, _th = lay["sliders"][key]["track"]
    lo, hi, step = slider_span(key)
    t = max(0.0, min(1.0, (mx - tx) / max(1, tw)))
    v = round((lo + t * (hi - lo)) / step) * step
    return int(v) if key == "impot" else float(v)


def slider_step(bud: dict, key: str, sign: int):
    lo, hi, step = slider_span(key)
    v = max(lo, min(hi, bud[key] + sign * step))
    return int(v) if key == "impot" else float(v)


def _dec(v: float, n: int = 1) -> str:
    """Un nombre a virgule, a la francaise."""
    return f"{v:.{n}f}".replace(".", ",")


def _sicles(v: float, sign: bool = False) -> str:
    s = f"{abs(v):.1f}".replace(".", ",") if abs(v) < 100 else f"{abs(v):.0f}"
    if sign:
        return ("+" if v >= 0 else "-") + s
    return ("-" if v < 0 else "") + s


def draw_treasury(r, state, ui) -> None:
    tid = state.viewer
    tribe = state.tribes.get(tid)
    if tribe is None or not money.has_money(state, tid):
        r.treasury_hits = {}
        return
    title_font, head_font = _fonts(r)
    screen = r.screen
    mx, my = pygame.mouse.get_pos()
    w, h = screen.get_size()
    lay = treasury_layout(w, h)
    r.treasury_hits = lay
    _frame(r, lay["box"])
    bx, by, bw, bh = lay["box"]
    b = tech.bonuses(tribe)
    pygame.draw.rect(screen, color_of(tribe), (bx + 22, by + 18, 6, 34), border_radius=2)
    screen.blit(title_font.render(f"Trésor des {tribe.name}", True, GOLD), (bx + 36, by + 12))
    sub = (
        "L'argent pesé : des sicles de métal blanc, pesés à la balance."
        if b.silver
        else "Valeurs d'échange : perles, coquillages, haches polies, comptés en sicles. Argent pesé : le métal."
    )
    screen.blit(r.tiny.render(theme.fit(r.tiny, sub, bw - 240), True, NOTE), (bx + 38, by + 42))
    theme.button(screen, lay["close"], "Fermer [Échap]", "second", True, _hover(lay["close"], mx, my))
    tips: list = []
    bud = money.budget(tribe)
    month = money.last_month(tribe)
    income = sum(v for v in month.values() if v > 0)
    spent = -sum(v for v in month.values() if v < 0)
    bal = income - spent
    solde_state = bud.get("etat_solde", "")
    tiles = (
        ("TRÉSOR", f"{_sicles(tribe.money)} sicles", "ce que le peuple possède", GOLD),
        ("RENTRÉES", _sicles(income, True), "le dernier mois", GOOD if income else INK),
        ("DÉPENSES", "-" + _sicles(spent), "le dernier mois", WARN if spent else INK),
        ("BALANCE", _sicles(bal, True), "sicles, dernier mois", GOOD if bal > 0 else BAD if bal < 0 else INK),
        ("IMPÔT", f"{bud['impot']} pour cent" if bud["impot"] else "Aucun", f"{_sicles(money.tax_income(state, tid))} sicles / mois", INK),
        (
            "SOLDE",
            {"payee": f"Payée ({round(100 * bud['solde'])} %)", "impayee": "Impayée"}.get(solde_state, ("Promise" if bud["solde"] else "Aucune")),
            f"{money.soldiers(state, tid)} hommes sous les armes",
            GOOD if solde_state == "payee" else BAD if solde_state == "impayee" else INK,
        ),
    )
    for rect, (label, value, sub_t, col) in zip(lay["tiles"], tiles):
        _tile(r, rect, label, value, sub_t, col)
    _draw_account(r, state, tribe, lay, month)
    _draw_budget(r, state, tribe, lay, bud, tips, mx, my)
    _draw_graph(r, tribe, lay)
    for lines, avoid in tips:
        _tip(r, lines, mx, my, avoid)


def _draw_account(r, state, tribe, lay, month) -> None:
    screen = r.screen
    tid = tribe.id
    x, y, w, h = lay["left"]
    yy = _section(r, x, y, w, "LE COMPTE DU DERNIER MOIS")
    if not month:
        screen.blit(r.tiny.render("Rien encore : le compte se fait à la fin du mois.", True, NOTE), (x, yy))
        yy += 18
    for key in sorted(month, key=lambda k: (-month[k] if month[k] > 0 else 1e9 - month[k])):
        v = month[key]
        name = money.KEY_NAMES.get(key, key)
        col = GOOD if v > 0 else WARN
        screen.blit(r.small.render(theme.fit(r.small, name, w - 90), True, SOFT), (x, yy))
        t = r.small.render(_sicles(v, True), True, col)
        screen.blit(t, (x + w - t.get_width(), yy))
        yy += 22
    yy = _section(r, x, yy + 10, w, "LE MOIS PROCHAIN (à peu près)")
    bud = money.budget(tribe)
    rows = [("Impôt", money.tax_income(state, tid), True)]
    for key in money.PAY_KEYS:
        if bud[key]:
            rows.append((money.PAY_NAMES[key], -money.COSTS[key](state, tid), True))
    for name, v, _on in rows:
        screen.blit(r.small.render(name, True, SOFT), (x, yy))
        t = r.small.render(_sicles(v, True), True, GOOD if v > 0 else WARN if v < 0 else NOTE)
        screen.blit(t, (x + w - t.get_width(), yy))
        yy += 22
    notes = [
        "Les mines, les ventes en argent, le tribut et les péages s'y ajoutent.",
        f"Un sicle vaut {money.VPS:.0f} vivres sur les routes.",
    ]
    for text in notes:
        for part in theme.wrap(r.tiny, text, w):
            if yy + 15 > y + h:
                return
            screen.blit(r.tiny.render(part, True, NOTE), (x, yy))
            yy += 15


def _slider_texts(state, tribe, bud) -> dict:
    """Pour chaque curseur : (nom, valeur, ce que ca coute ou rapporte, ce que ca fait)."""
    tid = tribe.id
    pts = bud["impot"]
    silver = " Argent pesé : +25 %." if tech.bonuses(tribe).silver else ""

    def pct(key):
        return f"{round(100 * bud[key])} %"

    e = {k: money.eff(bud[k]) for k in money.PAY_KEYS}
    return {
        "impot": (
            "Impôt en argent",
            f"{pts} pour cent" if pts else "aucun",
            f"{pts} sicles pour cent villageois par mois : {_sicles(money.tax_income(state, tid))} sicles" if pts else "On ne prélève rien",
            (f"Stabilité des villages {money.tax_stab(pts)}." + silver) if pts else "Pas d'impôt : pas de mécontentement.",
        ),
        "solde": (
            "Solde des troupes",
            pct("solde"),
            f"{_dec(money.SOLDE, 2)} sicle par homme levé au tarif : {_sicles(money.solde_cost(state, tid))} sicles par mois",
            f"Payée : moral +{_dec(5 * e['solde'])}, fuyards x{_dec(max(0.2, 1 - 0.5 * e['solde']), 2)}. Promise et pas payée : moral -5, plus de fuyards."
            if bud["solde"] else "Pas de solde : les troupes se battent pour le butin.",
        ),
        "gages": (
            "Gages des gens de métier",
            pct("gages"),
            f"{_dec(money.GAGE, 2)} sicle par artisan au tarif : {_sicles(money.gage_cost(state, tid))} sicles par mois",
            f"Payés : métiers +{_dec(10 * e['gages'])} %, calculateurs +{_dec(25 * e['gages'])} %. Promis et pas payés : -10 %."
            if bud["gages"] else "Pas de gages : les métiers travaillent pour leur part de vivres.",
        ),
        "dons": (
            "Présents aux familles",
            pct("dons"),
            f"{int(100 * money.DON_SHARE)} % du trésor au tarif, au moins un sicle par famille : {_sicles(money.don_cost(state, tid))} sicles",
            f"Faveur des familles +{_dec(money.DON_FAVOUR * e['dons'])} par mois, stabilité des villages +{round(money.DON_STABILITY * e['dons'])}."
            if bud["dons"] else "Pas de présents : les familles comptent sur leurs charges.",
        ),
        "chantiers": (
            "Paie des bâtisseurs",
            pct("chantiers"),
            f"{_dec(money.CHANTIER)} sicle par chantier au tarif ; {money.chantiers(state, tid)} chantier(s) : {_sicles(money.chantier_cost(state, tid))} sicles",
            f"Payés : les chantiers avancent {round(100 * money.CHANTIER_SPEED * e['chantiers'])} % plus vite."
            if bud["chantiers"] else "Les villageois bâtissent entre deux travaux des champs.",
        ),
    }


def _draw_budget(r, state, tribe, lay, bud, tips, mx, my) -> None:
    screen = r.screen
    x, y, w, _h = lay["mid"]
    _section(r, x, y, w, "LE BUDGET (glissez les curseurs)")
    texts = _slider_texts(state, tribe, bud)
    for key in SLIDERS:
        rects = lay["sliders"][key]
        rx, ry, rw, rh = rects["row"]
        screen.blit(_gradient_card(rw, rh, (44, 34, 26), (30, 23, 18), 6), (rx, ry))
        pygame.draw.rect(screen, (90, 70, 50), rects["row"], 1, border_radius=6)
        name, value, cost, what = texts[key]
        st = bud.get("etat_" + key, "") if key != "impot" else ""
        word = {"payee": " · donnés" if key == "dons" else " · payée", "impayee": " · IMPAYÉE"}.get(st, "")
        screen.blit(r.small.render(theme.fit(r.small, name + word, rw - 130), True, BAD if "IMPAY" in word else INK), (rx + 10, ry + 5))
        vt = r.small.render(value, True, GOLD if (bud[key] if key != "impot" else bud["impot"]) else NOTE)
        screen.blit(vt, (rx + rw - vt.get_width() - 10, ry + 5))
        # Le curseur : la piste, la part remplie, la poignee.
        tx, ty, tw, th = rects["track"]
        lo, hi, _step = slider_span(key)
        frac = (bud[key] - lo) / (hi - lo)
        hover = _hover((tx - 8, ty - 8, tw + 16, th + 16), mx, my)
        pygame.draw.rect(screen, (24, 18, 14), rects["track"], border_radius=7)
        if key != "impot":
            # Le tarif (100 %) : un trait.
            mark = tx + int(tw * (1.0 - lo) / (hi - lo))
            pygame.draw.line(screen, (120, 98, 70), (mark, ty - 4), (mark, ty + th + 3), 1)
        fill = int(tw * frac)
        if fill > 0:
            pygame.draw.rect(screen, (166, 120, 52) if key != "impot" else (150, 96, 70), (tx, ty, fill, th), border_radius=7)
        pygame.draw.rect(screen, (120, 92, 62), rects["track"], 1, border_radius=7)
        kx = tx + fill
        pygame.draw.circle(screen, (60, 44, 30), (kx, ty + th // 2), 11)
        pygame.draw.circle(screen, GOLD if hover else (217, 180, 110), (kx, ty + th // 2), 9)
        for btn, label in ((rects["minus"], "−"), (rects["plus"], "+")):
            theme.button(screen, btn, label, "second", True, _hover(btn, mx, my))
        # Ce que la ligne rapporte (l'impot) ou coute chaque mois.
        flow = money.tax_income(state, tribe.id) if key == "impot" else -money.COSTS[key](state, tribe.id)
        ft = r.tiny.render(f"{_sicles(flow, True)} / mois" if flow else "rien", True, GOOD if flow > 0 else WARN if flow < 0 else NOTE)
        screen.blit(ft, (rx + rw - ft.get_width() - 10, ty))
        screen.blit(r.tiny.render(theme.fit(r.tiny, what, rw - 20), True, NOTE), (rx + 10, ry + rh - 18))
        if hover or _hover(rects["row"], mx, my) and not (_hover(rects["minus"], mx, my) or _hover(rects["plus"], mx, my)):
            tips.append(([(name, C.os, "petit_gras"), (cost, SOFT), (what, NOTE)], rects["row"]))
    tx, ty, tw, th = lay["tolls"]
    yy = _section(r, tx, ty + 4, tw, "DROITS DE PASSAGE")
    if tech.bonuses(tribe).tolls:
        got = sum(v for k, v in money.last_month(tribe).items() if k == "peages" and v > 0)
        text = (
            f"Les convois étrangers qui traversent votre pays paient un demi-sicle par convoi et {int(100 * money.TOLL)} % de leur charge : "
            f"{_sicles(got)} sicles le dernier mois."
        )
    else:
        text = "Avec Droits de passage, les convois étrangers qui traversent votre pays paieront leur passage."
    for part in theme.wrap(r.tiny, text, tw):
        if yy + 15 > ty + th:
            break
        screen.blit(r.tiny.render(part, True, NOTE), (tx, yy))
        yy += 15
    if yy + 40 > ty + th:
        return
    yy = _section(r, tx, yy + 8, tw, "L'ARGENT AILLEURS")
    pay = laws.option_name(tribe, "paiement").lower()
    for text in (
        f"Le commerce se paie {pay} : la loi « Paiement en argent » (Pays, onglet Lois [N]).",
        "Des présents en sicles aux autres peuples : l'écran Peuples.",
        f"Le tribut de vos tributaires : {int(100 * money.VASSAL_SHARE)} % de leur trésor chaque mois.",
    ):
        for part in theme.wrap(r.tiny, text, tw):
            if yy + 15 > ty + th:
                return
            screen.blit(r.tiny.render(part, True, NOTE), (tx, yy))
            yy += 15


def _draw_graph(r, tribe, lay) -> None:
    screen = r.screen
    x, y, w, h = lay["right"]
    _section(r, x, y, w, "LE TRÉSOR, MOIS APRÈS MOIS")
    gx, gy, gw, gh = lay["graph"]
    screen.blit(_gradient_card(gw, gh, (30, 23, 18), (20, 16, 12), 6), (gx, gy))
    hist = list(getattr(tribe, "money_hist", None) or [])
    if not hist:
        t = r.tiny.render("Le premier mois n'est pas fini.", True, NOTE)
        screen.blit(t, (gx + (gw - t.get_width()) // 2, gy + gh // 2 - 8))
        return
    # Deux echelles : le tresor (la ligne), les rentrees et depenses (les barres).
    top = max([h_[4] for h_ in hist] + [5.0])
    flow = max([h_[2] for h_ in hist] + [h_[3] for h_ in hist] + [2.0])
    slot = (gw - 12) / money.HISTORY
    n = len(hist)
    base_y = gy + gh - 22
    pts = []
    for i, (_yr, _wk, inc, out, tre, _m) in enumerate(hist):
        x0 = gx + 6 + (money.HISTORY - n + i) * slot
        hi = int((gh - 44) * 0.45 * inc / flow)
        ho = int((gh - 44) * 0.45 * out / flow)
        bw_ = max(2, int(slot / 2) - 1)
        if hi:
            pygame.draw.rect(screen, (157, 191, 110), (int(x0) + 1, base_y - hi, bw_, hi))
        if ho:
            pygame.draw.rect(screen, (210, 110, 90), (int(x0) + 1 + bw_, base_y - ho, bw_, ho))
        pts.append((int(x0 + slot / 2), int(base_y - (gh - 44) * tre / top)))
    if len(pts) >= 2:
        pygame.draw.lines(screen, GOLD, False, pts, 2)
    for p in pts:
        pygame.draw.circle(screen, GOLD, p, 3)
    screen.blit(r.tiny.render(f"trésor (max {_sicles(top)} sicles)", True, GOLD), (gx + 8, gy + 4))
    screen.blit(r.tiny.render(f"rentrées (max {_sicles(flow)})", True, (157, 191, 110)), (gx + 8, gy + gh - 17))
    t = r.tiny.render("dépenses", True, (210, 110, 90))
    screen.blit(t, (gx + 8 + r.tiny.size(f"rentrées (max {_sicles(flow)})")[0] + 12, gy + gh - 17))
    # Sous le graphe : d'ou vient l'argent depuis deux ans.
    yy = gy + gh + 14
    totals: dict = {}
    for h_ in hist:
        for k, v in h_[5].items():
            totals[k] = totals.get(k, 0.0) + v
    if totals:
        yy = _section(r, x, yy, w, f"SUR {n} MOIS")
        for k in sorted(totals, key=lambda k: -abs(totals[k])):
            if yy + 18 > y + h:
                break
            v = totals[k]
            screen.blit(r.tiny.render(money.KEY_NAMES.get(k, k), True, SOFT), (x, yy))
            t = r.tiny.render(_sicles(v, True), True, GOOD if v > 0 else WARN)
            screen.blit(t, (x + w - t.get_width(), yy))
            yy += 17
