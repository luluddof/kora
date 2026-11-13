"""La planche de choix d'une serie du rework : pour chaque interface,
l'actuelle puis les propositions, en vignettes.
python maq_planche.py DOSSIER_EXISTANT DOSSIER_SERIE SORTIE.png"""
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import pygame  # noqa: E402

from src.kora import theme  # noqa: E402
from src.kora.theme import C  # noqa: E402

old_dir, new_dir, out = sys.argv[1], sys.argv[2], sys.argv[3]
ROWS = (
    ("La barre du haut et le rail", "01_carte", ("HUD_A_bandeau_des_comptes", "HUD_B_les_alertes", "HUD_C_le_dock"),
     ("A  le bandeau des comptes", "B  les alertes", "C  le dock en bas")),
    ("Le panneau Village", "02_panneau_tribu", ("VIL_A_le_tableau", "VIL_B_le_portrait"), ("A  le tableau", "B  le portrait du peuple")),
    ("L'unité choisie", "05_unite_choisie", ("UNI_A_la_fiche_a_jauges", "UNI_B_la_fiche_laterale"), ("A  la fiche à jauges", "B  la fiche latérale")),
    ("La carte d'événement", "06_evenement", ("EVE_A_le_recit_illustre", "EVE_B_la_carte_a_jouer", "EVE_C_dans_le_coin"),
     ("A  le récit illustré", "B  la carte à jouer", "C  dans le coin")),
    ("Le journal", "02_panneau_journal", ("JOU_A_la_chronique", "JOU_B_a_faire_et_nouvelles"), ("A  la chronique", "B  à faire / nouvelles")),
)
TW, TH = 400, 225
GAP = 16
LEFT = 200
pygame.init()
pygame.display.set_mode((10, 10))
W = LEFT + 4 * (TW + GAP) + GAP
H = 90 + len(ROWS) * (TH + 56)
s = pygame.Surface((W, H))
s.fill(C.nuit)
theme.title(s, "Le rework des interfaces · première série", 24, 18, "h1")
theme.text(s, "Sur votre partie (an 48). À gauche : aujourd'hui. Choisissez une lettre par ligne (ou un mélange).", "petit", C.lin, (26, 56))
y = 96
for title, old, news, labels in ROWS:
    for line_i, line in enumerate(theme.wrap(theme.font("h3"), title, LEFT - 30)):
        theme.text(s, line, "h3", C.ocre_jaune, (24, y + 80 + line_i * 24))
    cells = [(old_dir, old, "Aujourd'hui")] + [(new_dir, n, lab) for n, lab in zip(news, labels)]
    for i, (folder, name, lab) in enumerate(cells):
        x = LEFT + GAP + i * (TW + GAP)
        img = pygame.image.load(os.path.join(folder, name + ".png"))
        s.blit(pygame.transform.smoothscale(img, (TW, TH)), (x, y))
        pygame.draw.rect(s, C.cendre if i == 0 else C.ocre, (x - 1, y - 1, TW + 2, TH + 2), 1)
        theme.text(s, lab, "petit_gras", C.cendre if i == 0 else C.os, (x, y + TH + 6))
    y += TH + 56
pygame.image.save(s, out)
print("planche :", out)
