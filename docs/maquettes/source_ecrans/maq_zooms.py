"""AVANT / APRES EN GRAND, une image par changement (0.32.0, 2026-11-19) :
le meme morceau d'ecran pris avec la 0.31 (regard_neuf/) et la 0.32
(lisibles/), sur SES parties (des copies), agrandi.
python maq_zooms.py DOSSIER_REGARD_NEUF DOSSIER_LISIBLES DOSSIER_SORTIE"""
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import pygame  # noqa: E402

from src.kora import theme  # noqa: E402
from src.kora.theme import C  # noqa: E402

before, after, out = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
A3, A48 = "partie_an3", "partie_an48"
# (fichier, titre, ce qu'il faut regarder, [(capture, rectangle 1600x900, zoom, "pile" ou "cote")])
CHANGES = (
    ("01_fiche_de_la_bande", "La fiche de la bande",
     "Avant : « Stock : 0 sem. » était écrit comme « Jungle · Été ». Après : deux jauges. VIVRES (sa réserve, en "
     "semaines) et COLLECTE (ce qu'elle trouve, le trait blanc étant ce qu'il lui faut). Orange puis rouge quand la faim "
     "approche, avec une phrase. Les ordres impossibles sont vraiment éteints ; seul « Scinder » est possible ici.",
     [(f"{A3}/05_unite_choisie.png", (528, 622, 544, 272), 2, "pile")]),
    ("02_barre_du_haut", "La barre du haut (la souris sur les vivres)",
     "Avant : trois nombres sans nom, rien au survol. Après : chacun son nom (vivres, gens, prestige), une petite pointe "
     "quand il monte ou baisse depuis un mois, rouge quand ça va mal (14 vivres pour 42 personnes), et une fiche au "
     "survol qui explique. « Choisir un savoir » est un vrai bouton.",
     [(f"{A3}/x3_hud_survol.png", (960, 0, 640, 160), 2, "pile")]),
    ("03_colonne_de_gauche", "La colonne de gauche : ce qui vous attend",
     "En haut, votre partie de l'an 48 : avant, les cartes d'événement seules ; après, une alerte (« Disette en vue à "
     "Ilsen », un clic ouvre le village) au-dessus d'elles. En bas, votre partie neuve de l'an 3 : avant, rien ; après, "
     "le chemin du premier village, ses quatre étapes et ce qui manque à celle en cours.",
     [(f"{A48}/02_panneau_tribu.png", (0, 52, 310, 220), 2, "cote"),
      (f"{A3}/05_unite_choisie.png", (0, 52, 310, 170), 2, "cote")]),
    ("04_carte_evenement", "Une carte d'événement",
     "Avant : « +4 à 7 personnes, -1 sem. de vivres » en or, le gain et la perte pareils. Après : des pastilles, le gain "
     "en vert avec une pointe vers le haut, la perte en rouge avec une pointe vers le bas. « Plus tard » est un bouton.",
     [(f"{A3}/06_evenement.png", (420, 300, 762, 300), 1.6, "pile")]),
    ("05_panneau_village_haut", "Le panneau Village : la liste des villages",
     "Avant : l'icône couvrait le « I » d'Ilsen, « disette en vue » sans dire pourquoi. Après : le nom en entier ; une "
     "ligne qui dit ce que deviendra le grain (« le grain manquera 2 sem. : rationnez, achetez... ») ; la stabilité dit "
     "ce qui la porte (vert) et ce qui la mine (rouge).",
     [(f"{A48}/02_panneau_tribu.png", (846, 64, 680, 270), 1.8, "pile")]),
    ("06_panneau_village_bas", "Le panneau Village : la réserve du peuple",
     "Avant : dix biens sur une place prévue pour quatre ; les lignes s'écrivaient les unes sur les autres. Après : "
     "dix biens sur cinq rangs, un point plein quand le bien est pourvu, un rond vide quand il manque.",
     [(f"{A48}/02_panneau_tribu.png", (846, 520, 680, 202), 1.8, "pile")]),
    ("07_fiche_et_panneau_tribu", "La fiche de la bande et le panneau Tribu",
     "Avant : le panneau Tribu s'ouvrait par-dessus la fiche de la bande et la coupait. Après : la fiche se range à "
     "gauche du panneau (et s'efface, sur un petit écran, s'il n'y a pas la place).",
     [(f"{A3}/x1_tribu_bande.png", (0, 52, 1600, 848), 0.78, "pile")]),
    ("08_decisions", "Les décisions",
     "Avant : les titres en capitales, « ce que ça fait » tout en vert. Après : le titre commun (petites capitales, "
     "points dessous) ; ce que ça coûte marqué d'une pointe rouge, ce que ça fait d'une pointe verte.",
     [(f"{A48}/04_decisions.png", (522, 140, 980, 380), 1.25, "pile")]),
    ("09_commerce_marche", "Le commerce : le marché du peuple",
     "Avant : quatre éléments par bien (prix, barre, réserve, « fait 0,0 · mange 1,0 / sem. ») : 30 lignes pour 10 "
     "biens. Après : deux lignes par bien (le prix ; pourvu ou non, la réserve, ce qu'on en fait), le reste au survol.",
     [(f"{A48}/04_commerce.png", (24, 185, 470, 520), 1.3, "cote")]),
    ("10_lieues_et_fermer", "Les lieues, et Fermer",
     "Avant : « 10 cases » alors qu'il n'y a plus de cases, et Fermer en orange (comme l'action principale). Après : "
     "« 10 lieues » (dans 42 textes du jeu), et Fermer gris partout.",
     [(f"{A48}/04_commerce.png", (1040, 760, 470, 110), 2, "pile"),
      (f"{A48}/04_commerce.png", (1350, 70, 170, 36), 2, "cote")]),
    ("11_village_titres_contrastes", "L'écran du village : titres et contrastes",
     "Avant : « CHAMPS » et « RÉCOLTES DES DERNIÈRES ANNÉES » en capitales simples, à côté de titres en petites "
     "capitales ; le gris des étiquettes pâle sur la pierre. Après : un seul style de titre ; un fond plus sombre et des "
     "gris plus clairs (assez de contraste partout).",
     [(f"{A48}/03_village_village.png", (24, 148, 1150, 380), 1.1, "pile")]),
    ("12_journal", "Le journal (votre partie neuve, filtre Survie)",
     "Avant : « Famine : 1 morts. » semaine après semaine, 17 lignes. Après : une ligne, « Famine : 17 morts », an 1, "
     "semaines 26 à 52, 17 fois. Les nouvelles en bas à droite ne s'empilent plus non plus.",
     [(f"{A3}/x2_journal_survie.png", (1188, 66, 340, 560), 1.6, "cote")]),
    ("13_onglets", "Les onglets à droite",
     "Avant : « Commer... » et « Décisio... » coupés. Après : les noms en entier.",
     [(f"{A48}/02_panneau_tribu.png", (1532, 380, 66, 230), 3, "cote")]),
)

pygame.init()
pygame.display.set_mode((10, 10))
GAP, PAD = 24, 28
f_note = theme.font("texte")
cache: dict = {}


def load(path):
    if path not in cache:
        cache[path] = pygame.image.load(path)
    return cache[path]


def piece(base, name, rect, zoom):
    img = load(os.path.join(base, name)).subsurface(pygame.Rect(rect)).copy()
    w, h = int(rect[2] * zoom), int(rect[3] * zoom)
    if zoom == int(zoom):
        return pygame.transform.scale(img, (w, h))
    return pygame.transform.smoothscale(img, (w, h))


def tag(surf, x, y, label, rank):
    f = theme.font("petit_gras")
    tw = f.size(label)[0] + 16
    pygame.draw.rect(surf, C.charbon if rank == 0 else C.ocre_sombre, (x, y, tw, 24), border_radius=4)
    pygame.draw.rect(surf, C.bois_clair if rank == 0 else C.ocre, (x, y, tw, 24), 1, border_radius=4)
    surf.blit(f.render(label, True, C.os), (x + 8, y + 2))


for fname, title, note, pairs in CHANGES:
    blocks = []
    for name, rect, zoom, mode in pairs:
        a = piece(before, name, rect, zoom)
        b = piece(after, name, rect, zoom)
        blocks.append((a, b, mode))
    # La largeur : la plus large des rangees.
    def row_w(a, b, mode):
        return a.get_width() + GAP + b.get_width() if mode == "cote" else max(a.get_width(), b.get_width())

    W = max(1100, max(row_w(*bl) for bl in blocks) + 2 * PAD)
    lines = theme.wrap(f_note, note, W - 2 * PAD)
    H = 70 + len(lines) * 24 + 20
    for a, b, mode in blocks:
        H += (34 + max(a.get_height(), b.get_height())) if mode == "cote" else (34 + a.get_height() + 16 + 34 + b.get_height())
        H += 24
    s = pygame.Surface((W, H))
    s.fill(C.nuit)
    theme.title(s, title, PAD, 16, "h1")
    y = 70
    for line in lines:
        s.blit(f_note.render(line, True, C.lin), (PAD, y))
        y += 24
    y += 20
    for a, b, mode in blocks:
        if mode == "cote":
            x = PAD
            for k, img in enumerate((a, b)):
                tag(s, x, y, "AVANT (0.31)" if k == 0 else "APRÈS (0.32)", k)
                s.blit(img, (x, y + 32))
                pygame.draw.rect(s, C.bois_clair if k == 0 else C.ocre, (x - 1, y + 31, img.get_width() + 2, img.get_height() + 2), 1 if k == 0 else 2)
                x += img.get_width() + GAP
            y += 34 + max(a.get_height(), b.get_height()) + 24
        else:
            for k, img in enumerate((a, b)):
                tag(s, PAD, y, "AVANT (0.31)" if k == 0 else "APRÈS (0.32)", k)
                s.blit(img, (PAD, y + 32))
                pygame.draw.rect(s, C.bois_clair if k == 0 else C.ocre, (PAD - 1, y + 31, img.get_width() + 2, img.get_height() + 2), 1 if k == 0 else 2)
                y += 34 + img.get_height() + 16
            y += 8
    path = os.path.join(out, f"{fname}.png")
    pygame.image.save(s, path)
    print(path, s.get_size())
