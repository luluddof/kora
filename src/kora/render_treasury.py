"""L'ecran du TRESOR (money.py), dans le style de l'ecran du commerce :
  - tuiles : le tresor, les rentrees et les depenses du dernier mois, la
    balance, l'impot, l'etat de la solde ;
  - a gauche, le COMPTE DU MOIS (chaque rentree, chaque depense) et ce que
    le mois prochain promet ;
  - au milieu, le BUDGET : l'impot en argent (aucun, leger, moyen, lourd),
    la solde des troupes, les gages des gens de metier, le commerce en
    argent, les droits de passage ;
  - a droite, le graphe du tresor des 24 derniers mois.
treasury_layout et treasury_hit sont purs (tests) ; draw_treasury dessine.
Tout changement passe par commands.py ("budget").
"""

from __future__ import annotations

import pygame

from src.kora import money, tech, theme
from src.kora.peoples import color_of
from src.kora.layout import HUD_HEIGHT
from src.kora.render_tech import BAD, GOLD, GOOD, INK, NOTE, SOFT
from src.kora.theme import C, _gradient_card
from src.kora.render_village import WARN, _fonts, _frame, _hover, _section, _tile, _tip

TOGGLES = money.TOGGLE_KEYS


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
    # Le budget : l'impot (quatre crans), puis trois interrupteurs.
    y = body_y + 24
    cw = (mw - 3 * 8) // 4
    taxes = {lvl: (mid[0] + lvl * (cw + 8), y + 20, cw, 28) for lvl in money.TAX}
    y += 20 + 28 + 46
    toggles = {}
    block = max(64, min(92, (body_y + body_h - y - 60) // len(TOGGLES)))
    for key in TOGGLES:
        toggles[key] = {"row": (mid[0], y, mw, block - 6), "btn": (mid[0] + mw - 150, y + 2, 150, 26)}
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
        "taxes": taxes,
        "toggles": toggles,
        "tolls": tolls,
        "graph": graph,
    }


def treasury_hit(lay: dict, mx: int, my: int):
    if not lay:
        return None
    if _hover(lay["close"], mx, my):
        return "mclose"
    for lvl, rect in lay["taxes"].items():
        if _hover(rect, mx, my):
            return f"mtax:{lvl}"
    for key, rects in lay["toggles"].items():
        if _hover(rects["btn"], mx, my):
            return f"mtoggle:{key}"
    if _hover(lay["box"], mx, my):
        return "panel"
    return None


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
        ("IMPÔT", money.TAX_NAMES[bud["tax"]], f"{_sicles(money.tax_income(state, tid))} sicles / mois", INK),
        (
            "SOLDE",
            {"payee": "Payée", "impayee": "Impayée"}.get(solde_state, ("Promise" if bud["solde"] else "Aucune")),
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
    if bud["solde"]:
        rows.append(("Solde des troupes", -money.solde_cost(state, tid), True))
    if bud["gages"]:
        rows.append(("Gages des gens de métier", -money.gage_cost(state, tid), True))
    if bud["dons"]:
        rows.append(("Présents aux familles", -money.don_cost(state, tid), True))
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


def _draw_budget(r, state, tribe, lay, bud, tips, mx, my) -> None:
    screen = r.screen
    tid = tribe.id
    x, y, w, _h = lay["mid"]
    yy = _section(r, x, y, w, "LE BUDGET")
    screen.blit(r.small.render("Impôt en argent, sur chaque villageois", True, INK), (x, yy - 2))
    for lvl, rect in lay["taxes"].items():
        on = bud["tax"] == lvl
        hover = _hover(rect, mx, my)
        theme.button(screen, rect, money.TAX_NAMES[lvl], "second", True, hover, active=on)
        if hover:
            gain = money.villagers(state, tid) * money.TAX[lvl] * tech.bonuses(tribe).tax * (money.SILVER_TAX if tech.bonuses(tribe).silver else 1.0)
            lines = [(f"Impôt {money.TAX_NAMES[lvl].lower()}", C.os, "petit_gras")]
            if lvl:
                lines += [
                    (f"{money.TAX[lvl]:.2f} sicle par villageois et par mois : environ {_sicles(gain)} sicles.".replace(".", ",", 1), SOFT),
                    (f"Stabilité des villages : {money.TAX_STAB[lvl]}", C.mauvais),
                ]
            else:
                lines.append(("On ne prélève rien : la stabilité ne bouge pas.", SOFT))
            tips.append((lines, rect))
    lvl = bud["tax"]
    eff = f"Stabilité {money.TAX_STAB[lvl]}" if lvl else "Pas d'impôt : pas de mécontentement"
    if tech.bonuses(tribe).silver:
        eff += " · Argent pesé : +25 % de rendement"
    rect = lay["taxes"][0]
    screen.blit(r.tiny.render(theme.fit(r.tiny, eff, w), True, NOTE), (x, rect[1] + rect[3] + 6))
    texts = {
        "solde": (
            "Solde des troupes",
            f"{money.SOLDE:.2f} sicle par homme levé et par mois : {_sicles(money.solde_cost(state, tid))} sicles".replace(".", ",", 1),
            "Payée : moral +5, deux fois moins de fuyards. Promise et pas payée : moral -5, plus de fuyards.",
        ),
        "gages": (
            "Gages des gens de métier",
            f"{money.GAGE:.2f} sicle par artisan et par mois : {_sicles(money.gage_cost(state, tid))} sicles".replace(".", ",", 1),
            "Payés : métiers +10 %, calculateurs +25 %. Promis et pas payés : -10 %.",
        ),
        "commerce": (
            "Commerce en argent",
            "Vos achats sur les routes se paient en sicles (le reste en vivres)",
            "Il faut que l'autre peuple connaisse aussi l'argent. Les vivres restent au grenier.",
        ),
        "dons": (
            "Présents aux familles",
            f"{int(100 * money.DON_SHARE)} % du trésor par mois, au moins un sicle par famille : {_sicles(money.don_cost(state, tid))} sicles",
            f"Faveur des familles +{money.DON_FAVOUR:g} par mois, stabilité des villages +{money.DON_STABILITY}.".replace(".", ",", 1),
        ),
    }
    for key in TOGGLES:
        rects = lay["toggles"][key]
        rx, ry, rw, rh = rects["row"]
        screen.blit(_gradient_card(rw, rh, (44, 34, 26), (30, 23, 18), 6), (rx, ry))
        pygame.draw.rect(screen, (90, 70, 50), rects["row"], 1, border_radius=6)
        name, cost, what = texts[key]
        on = bool(bud[key])
        state_word = ""
        if key in ("solde", "gages", "dons"):
            st = bud.get("etat_" + key, "")
            state_word = {"payee": " · payée" if key != "dons" else " · donnés", "impayee": " · IMPAYÉE"}.get(st, "")
        screen.blit(r.small.render(theme.fit(r.small, name + state_word, rw - 170), True, BAD if "IMPAY" in state_word else INK), (rx + 10, ry + 5))
        screen.blit(r.tiny.render(theme.fit(r.tiny, cost, rw - 20), True, SOFT), (rx + 10, ry + 30))
        wy = ry + 46
        for part in theme.wrap(r.tiny, what, rw - 20):
            if wy + 15 > ry + rh:
                break
            screen.blit(r.tiny.render(part, True, NOTE), (rx + 10, wy))
            wy += 15
        btn = rects["btn"]
        hover = _hover(btn, mx, my)
        label = {
            "solde": ("Payer la solde", "Ne plus payer"),
            "gages": ("Payer les gages", "Ne plus payer"),
            "commerce": ("Payer en argent", "Payer en vivres"),
            "dons": ("Faire des présents", "Plus de présents"),
        }[key]
        theme.button(screen, btn, label[1] if on else label[0], "second", True, hover, active=on)
        if hover:
            tips.append(([(name, C.os, "petit_gras"), (cost, SOFT), (what, NOTE)], btn))
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
