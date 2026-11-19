"""La planche annotee de la critique des interfaces (2026-11-19) : les
captures de la 0.31 (regard_neuf/), des cadres numerotes sur les problemes.
python maq_critique.py DOSSIER_REGARD_NEUF SORTIE.png"""
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import pygame  # noqa: E402

from src.kora import theme  # noqa: E402
from src.kora.theme import C  # noqa: E402

base, out = sys.argv[1], sys.argv[2]
# (capture, titre, [(numero, rectangle dans la capture 1600x900, note)])
PANELS = (
    ("partie_an3/05_unite_choisie.png", "La bande choisie (partie neuve)", [
        (1, (548, 680, 260, 20), "0 sem. de vivres : écrit comme le reste"),
        (2, (548, 785, 505, 62), "10 ordres, actifs et éteints presque pareils"),
        (3, (1400, 10, 195, 32), "Trois chiffres sans nom"),
        (4, (40, 60, 1480, 560), "Une carte vide : rien à faire, rien à viser"),
    ]),
    ("partie_an3/06_evenement.png", "La carte d'événement", [
        (5, (490, 478, 220, 20), "« −1 sem. de vivres » en or, comme un gain"),
        (6, (1070, 324, 80, 20), "« Plus tard » : un lien discret, loin des choix"),
    ]),
    ("partie_an48/02_panneau_tribu.png", "Le panneau Village (B)", [
        (7, (860, 640, 650, 70), "Des lignes écrites les unes sur les autres"),
        (8, (856, 212, 40, 28), "L'icône couvre la première lettre"),
        (9, (860, 250, 650, 330), "Un grand vide au milieu"),
    ]),
    ("partie_an48/04_commerce.png", "Le commerce", [
        (10, (30, 210, 450, 480), "30 lignes de chiffres pour 10 biens"),
        (11, (1044, 580, 450, 165), "Un mur de texte orange"),
        (12, (1044, 772, 200, 18), "« 10 cases » : il n'y a plus de cases"),
        (13, (1360, 76, 140, 26), "Fermer en orange ici, en gris ailleurs"),
    ]),
)
TW, TH = 760, 428
pygame.init()
pygame.display.set_mode((10, 10))
W = 2 * TW + 3 * 24
H = 100 + 2 * (TH + 96) + 24
s = pygame.Surface((W, H))
s.fill(C.nuit)
theme.title(s, "Regard neuf sur les interfaces · ce qui gêne", 24, 18, "h1")
theme.text(s, "Captures de la 0.31 sur vos parties. Les numéros renvoient à la critique (docs/superpowers/specs/2026-11-19-critique-interfaces.txt).", "petit", C.lin, (26, 58))
sx, sy = TW / 1600.0, TH / 900.0
for i, (name, title, notes) in enumerate(PANELS):
    x = 24 + (i % 2) * (TW + 24)
    y = 100 + (i // 2) * (TH + 96)
    img = pygame.image.load(os.path.join(base, name))
    s.blit(pygame.transform.smoothscale(img, (TW, TH)), (x, y))
    pygame.draw.rect(s, C.bois_clair, (x - 1, y - 1, TW + 2, TH + 2), 1)
    theme.text(s, title, "h3", C.ocre_jaune, (x, y + TH + 6))
    for n, (rx, ry, rw, rh), note in notes:
        r = pygame.Rect(x + int(rx * sx) - 2, y + int(ry * sy) - 2, int(rw * sx) + 4, int(rh * sy) + 4)
        pygame.draw.rect(s, C.mauvais, r, 2, border_radius=3)
        f = theme.font("mini_gras")
        tag = f"{n}"
        tw = f.size(tag)[0] + 10
        pygame.draw.rect(s, C.mauvais, (r.x, r.y - 16, tw, 16), border_radius=3)
        s.blit(f.render(tag, True, C.os), (r.x + 5, r.y - 16))
    # La legende sous la capture : une note par ligne.
    for k, (n, _r, note) in enumerate(notes):
        theme.text(s, f"{n}. {note}", "mini", C.lin, (x + 300, y + TH + 6 + k * 18), TW - 300)
pygame.image.save(s, out)
print("planche :", out)
