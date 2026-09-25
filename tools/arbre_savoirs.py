"""Ecrit l'arbre des savoirs (donnees de tech.py) en texte.

Usage :
  python tools/arbre_savoirs.py            -> affiche l'arbre
  python tools/arbre_savoirs.py --spec     -> remplace la section 5 de
      docs/superpowers/specs/2026-09-23-savoirs-design.txt
Le texte des effets est celui du jeu (tech.effect_lines).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.kora import tech  # noqa: E402


class _Tribe:
    id = 0
    knowledge: set = set()
    practice: dict = {}
    prestige = 0
    shore_seen = steppe_seen = False
    flags: dict = {}


def _cond_label(cond) -> str:
    # Libelle sans l'etat d'une partie (valeurs a zero).
    class _State:
        bands: dict = {}
        tribes: dict = {}
        sites: dict = {}
        diplo = None

    try:
        return tech.cond_progress(_State(), _Tribe(), cond)[2]
    except Exception:
        return cond.label or cond.kind


def tree_text() -> str:
    out: list[str] = []
    for era_name, tiers, branches in tech.ERAS:
        out.append(f"=== {era_name} ===")
        out.append("")
        for tier in tiers:
            techs = [t for t in tech.TECHS.values() if t.tier == tier]
            if not techs:
                continue
            cost = f"  (apprentissage : {tech.TIER_COST[tier]} points)" if tier else ""
            out.append(f"Palier {tier} - {tech.TIER_NAMES[tier]}{cost}")
            out.append("-" * 60)
            for t in sorted(techs, key=lambda t: t.branch):
                out.append(f"  {t.name}   [{branches[t.branch]}]")
                out.append(f"    {t.about}")
                if t.prereqs:
                    out.append("    Il faut connaitre : " + ", ".join(tech.TECHS[p].name for p in t.prereqs))
                if t.conds:
                    out.append("    Il faut avoir vecu : " + " ; ".join(_cond_label(c) for c in t.conds))
                for line in tech.effect_lines(t):
                    out.append(f"    -> {line}")
                out.append("")
    return "\n".join(out)


def write_spec() -> None:
    path = ROOT / "docs" / "superpowers" / "specs" / "2026-09-23-savoirs-design.txt"
    text = path.read_text(encoding="utf-8")
    head, sep, _rest = text.partition("5. L'ARBRE\n----------\n")
    if not sep:
        raise SystemExit("section 5 introuvable")
    path.write_text(head + sep + "\n" + tree_text() + "\n", encoding="utf-8")


if __name__ == "__main__":
    if "--spec" in sys.argv:
        write_spec()
    else:
        print(tree_text())
