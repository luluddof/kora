"""La planche de la charte graphique, dessinee par le jeu (src/kora/theme.py) :
    .venv/Scripts/python.exe tools/planche_charte.py [sortie.png]
Par defaut : docs/charte/planche.png."""
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402


def main(out: Path) -> None:
    pygame.init()
    screen = pygame.display.set_mode((1600, 1120))
    from src.kora import theme as T
    from src.kora.theme import C

    screen.fill(C.nuit)
    T.panel(screen, (24, 20, 1552, 1080), "peau")
    T.title(screen, "Kora — charte « Feu et ocre »", 56, 44, "titre")
    T.text(screen, "Les matières des premiers peuples : le charbon, l'ocre, la peau tannée, la pierre taillée, la lumière du feu.", "recit", C.lin, (58, 96))
    # Couleurs.
    x, y = 58, 140
    T.text(screen, "Couleurs", "etiquette", C.ocre_jaune, (x, y))
    names = ["nuit", "charbon", "cuir", "cuir_clair", "bois", "pierre", "os", "lin", "cendre", "ocre", "braise", "ocre_jaune", "terre_cuite", "bon", "mauvais", "alerte", "savoir", "froid"]
    for i, n in enumerate(names):
        cx, cy = x + (i % 9) * 82, y + 24 + (i // 9) * 70
        col = getattr(C, n)
        pygame.draw.polygon(screen, col, T.chamfer((cx, cy, 70, 40), 5))
        pygame.draw.polygon(screen, C.bois, T.chamfer((cx, cy, 70, 40), 5), 1)
        T.text(screen, n.replace("_", " "), "mini", C.lin, (cx, cy + 44))
    # Lettres.
    x, y = 820, 140
    T.text(screen, "Lettres", "etiquette", C.ocre_jaune, (x, y))
    T.text(screen, "KORA", "logo", C.ocre, (x, y + 10), shadow=True)
    T.text(screen, "Titre : Les villages des Akor", "titre", C.os, (x, y + 118))
    T.text(screen, "Sous-titre : Fonder un village", "h2", C.os, (x, y + 158))
    T.text(screen, "Texte : l'hiver tue. Faites des réserves à l'automne, cherchez les vallées.", "texte", C.os, (x, y + 192))
    T.text(screen, "Petit : 63 personnes · stock 5 sem. · collecte 47 / besoin 63", "petit", C.lin, (x, y + 218))
    T.text(screen, "Récit : Des envoyés des Akor arrivent, les mains vides et ouvertes.", "recit", C.lin, (x, y + 242))
    T.text(screen, "Chiffres : 105  ·  716  ·  41", "chiffre_grand", C.ocre_jaune, (x, y + 268))
    # Fenetres.
    y = 440
    T.text(screen, "Matières", "etiquette", C.ocre_jaune, (58, y))
    T.panel(screen, (58, y + 24, 300, 170), "peau")
    T.title(screen, "Peau", 80, y + 40, "h1")
    T.text(screen, "Les fenêtres latérales.", "petit", C.lin, (82, y + 84))
    T.panel(screen, (380, y + 24, 300, 170), "pierre")
    T.title(screen, "Pierre", 402, y + 40, "h1")
    T.text(screen, "Événements, fondation, situations.", "petit", C.lin, (404, y + 84))
    for i, k in enumerate(("carte", "carte_survol", "carte_choisie")):
        T.panel(screen, (702, y + 24 + i * 58, 260, 50), k)
        T.text(screen, k.replace("_", " "), "petit", C.os, (720, y + 40 + i * 58))
    # Boutons.
    x = 990
    T.text(screen, "Boutons", "etiquette", C.ocre_jaune, (x, y))
    T.button(screen, (x, y + 26, 220, 40), "Commencer la partie", "principal")
    T.button(screen, (x + 236, y + 26, 220, 40), "Commencer la partie", "principal", hover=True)
    T.button(screen, (x, y + 76, 220, 34), "Honorer", "second", icon_key="honorer", key_hint="H")
    T.button(screen, (x + 236, y + 76, 220, 34), "Honorer", "second", hover=True, icon_key="honorer", key_hint="H")
    T.button(screen, (x, y + 120, 220, 34), "Choisi", "second", active=True)
    T.button(screen, (x + 236, y + 120, 220, 34), "Indisponible", "second", on=False)
    T.button(screen, (x, y + 160, 220, 30), "Retour", "discret")
    T.button(screen, (x + 236, y + 160, 220, 30), "Retour (survol)", "discret", hover=True)
    # Icones.
    y = 660
    T.text(screen, "Icônes (game-icons.net, CC BY 3.0)", "etiquette", C.ocre_jaune, (58, y))
    keys = sorted(T.ICON_FILES)
    for i, k in enumerate(keys):
        cx, cy = 58 + (i % 29) * 52, y + 26 + (i // 29) * 58
        screen.blit(T.icon(k, 34, C.os if i % 3 else C.ocre_jaune), (cx, cy))
        T.text(screen, T.fit(T.font("mini"), k, 50), "mini", C.cendre, (cx - 4, cy + 36))
    # Medaillons, barres, pastilles, infobulle.
    y = 880
    T.text(screen, "Médaillons, barres, pastilles, infobulles", "etiquette", C.ocre_jaune, (58, y))
    for i, (k, st) in enumerate((("feu", "normal"), ("savoir", "actif"), ("village", "connu"), ("dolmen", "eteint"), ("epidemie", "danger"), ("conjoncture", "actif"))):
        screen.blit(T.medallion(k, 30, st), (58 + i * 80, y + 28))
    for i, (frac, col) in enumerate(((0.87, C.bon), (0.42, C.alerte), (0.15, C.mauvais), (0.6, C.savoir))):
        T.bar(screen, (560, y + 34 + i * 26, 260, 12), frac, col, marks=(0.2, 0.4))
    cx = 860
    for label, col, ic in (("Pourvu", C.bon, None), ("Disette en vue", C.mauvais, "famine"), ("Bonus : encore 4 ans", C.ocre_jaune, "sablier"), ("Savoir", C.savoir, "savoir")):
        cx += T.chip(screen, cx, y + 34, label, col, ic) + 10
    T.tooltip(screen, [("Chef rassembleur", C.ocre_jaune, "h3"), ("Attachement des clans à la tribu : +10", C.lin), ("Emprise du chef : +4 cases", C.lin), ("Choisi à la création du peuple, il dure 5 ans.", C.cendre, "mini")], 860, y + 70, 340)
    T.dotted(screen, (58, 1060), (1540, 1060), C.ocre_sombre)
    out.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(screen, str(out))
    print("planche :", out)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "charte" / "planche.png")
