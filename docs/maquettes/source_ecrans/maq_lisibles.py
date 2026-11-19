"""La planche AVANT / APRES des interfaces lisibles (0.32.0, 2026-11-19) :
a gauche les captures de la 0.31 (regard_neuf/), a droite les memes ecrans
de la 0.32 (lisibles/), sur SES parties (des copies).
python maq_lisibles.py DOSSIER_REGARD_NEUF DOSSIER_LISIBLES SORTIE.png"""
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import pygame  # noqa: E402

from src.kora import theme  # noqa: E402
from src.kora.theme import C  # noqa: E402

before, after, out = sys.argv[1], sys.argv[2], sys.argv[3]
# (capture, titre, ce qui a change)
ROWS = (
    ("partie_an3/05_unite_choisie.png", "La bande choisie (sa partie neuve, an 3)",
     "Des jauges (les vivres, la collecte) rouges quand ça menace ; les ordres éteints effacés ; "
     "la barre du haut nommée, sa tendance ; à gauche, le chemin du premier village."),
    ("partie_an3/06_evenement.png", "Une carte d'événement",
     "Les effets en pastilles : un gain en vert, une perte en rouge, chacun sa pointe ; « Plus tard » est un bouton."),
    ("partie_an48/02_panneau_tribu.png", "Le panneau Village (sa partie de l'an 48)",
     "Plus rien ne s'écrit sur rien ; le grain dit ce qu'il deviendra ; la stabilité dit ce qui la porte et la mine ; "
     "à gauche, une alerte (la disette en vue) qui mène au village."),
    ("partie_an48/04_commerce.png", "Le commerce",
     "Deux lignes par bien au lieu de quatre ; des lieues, plus de cases ; Fermer en gris ; un seul style de titre."),
)
TW, TH = 760, 428
pygame.init()
pygame.display.set_mode((10, 10))
W = 2 * TW + 3 * 24
H = 110 + len(ROWS) * (TH + 70) + 10
s = pygame.Surface((W, H))
s.fill(C.nuit)
theme.title(s, "Des interfaces qui se lisent · avant (0.31) et après (0.32)", 24, 18, "h1")
theme.text(s, "Les mêmes écrans, sur vos parties. À gauche avant, à droite après.", "petit", C.lin, (26, 62))
for i, (name, title, note) in enumerate(ROWS):
    y = 110 + i * (TH + 70)
    theme.text(s, title, "h3", C.ocre_jaune, (24, y - 6))
    for k, base in enumerate((before, after)):
        x = 24 + k * (TW + 24)
        path = os.path.join(base, name)
        if not os.path.exists(path):
            continue
        img = pygame.image.load(path)
        s.blit(pygame.transform.smoothscale(img, (TW, TH)), (x, y + 18))
        pygame.draw.rect(s, C.bois_clair if k == 0 else C.ocre, (x - 1, y + 17, TW + 2, TH + 2), 1 if k == 0 else 2)
        tag = "AVANT" if k == 0 else "APRÈS"
        f = theme.font("mini_gras")
        tw = f.size(tag)[0] + 12
        pygame.draw.rect(s, C.charbon if k == 0 else C.ocre_sombre, (x + 6, y + 24, tw, 20), border_radius=3)
        s.blit(f.render(tag, True, C.os), (x + 12, y + 25))
    for j, line in enumerate(theme.wrap(theme.font("petit"), note, W - 60)[:2]):
        theme.text(s, line, "petit", C.lin, (26, y + TH + 22 + j * 20))
pygame.image.save(s, out)
print("planche :", out)
