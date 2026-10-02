"""Recupere les polices et les icones du jeu (une fois ; elles sont dans le
depot ensuite) :
    .venv/Scripts/python.exe tools/recuperer_assets.py

- Polices : Alegreya SC, Alegreya Sans (Google Fonts, licence SIL OFL)
  -> data/fonts/
- Icones : game-icons.net (CC BY 3.0) -> data/icons/<cle>.svg, sans le
  carre noir du fond (on les teinte dans le jeu : theme.icon).
La liste des icones est theme.ICON_FILES (cle -> auteur/nom).
"""
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FONTS_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONTS = {
    "alegreyasc": ["AlegreyaSC-Regular.ttf", "AlegreyaSC-Medium.ttf", "AlegreyaSC-Bold.ttf", "AlegreyaSC-ExtraBold.ttf", "OFL.txt"],
    "alegreyasans": [
        "AlegreyaSans-Regular.ttf",
        "AlegreyaSans-Medium.ttf",
        "AlegreyaSans-Bold.ttf",
        "AlegreyaSans-ExtraBold.ttf",
        "AlegreyaSans-Italic.ttf",
        "AlegreyaSans-MediumItalic.ttf",
    ],
}
ICONS_URL = "https://raw.githubusercontent.com/game-icons/icons/master/"


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def main() -> int:
    from src.kora.theme import ICON_FILES

    fonts = ROOT / "data" / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    for family, files in FONTS.items():
        for name in files:
            target = fonts / name
            if not target.exists():
                target.write_bytes(get(FONTS_URL + family + "/" + name))
    icons = ROOT / "data" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    missing = []
    authors = set()
    for key, path in sorted(ICON_FILES.items()):
        target = icons / f"{key}.svg"
        if target.exists():
            authors.add(path.split("/")[0])
            continue
        try:
            svg = get(ICONS_URL + path + ".svg").decode("utf-8")
        except OSError:
            missing.append(f"{key} ({path})")
            continue
        # Le carre noir du fond : on ne garde que la silhouette blanche.
        svg = re.sub(r'<path d="M0 0h512v512H0z"\s*/>', "", svg, count=1)
        target.write_text(svg, encoding="utf-8")
        authors.add(path.split("/")[0])
    credits = icons / "CREDITS.txt"
    credits.write_text(
        "Icones : game-icons.net, licence Creative Commons Attribution 3.0\n"
        "(https://creativecommons.org/licenses/by/3.0/). Auteurs : "
        + ", ".join(sorted(authors))
        + ".\nTeintees et mises en medaillon par Kora (src/kora/theme.py).\n"
        "Fichiers d'origine : https://github.com/game-icons/icons\n",
        encoding="utf-8",
    )
    if missing:
        print("introuvables :", ", ".join(missing))
        return 1
    print("polices :", len(list(fonts.glob('*.ttf'))), "; icones :", len(list(icons.glob('*.svg'))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
