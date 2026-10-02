"""Remet les accents du francais dans les TEXTES AFFICHES du jeu (chaines
de caracteres qui ne sont ni des identifiants ni des docstrings) :
    .venv/Scripts/python.exe tools/accents.py [--dry] [fichiers...]
Sans fichiers : src/kora/*.py et tests/*.py. --dry : montre sans ecrire.

Un dictionnaire de mots sans ambiguite (MOTS), des tournures (PHRASES) pour
les mots a double sens (cote/côté, ou/où, a/à...), et la regle du « à »
(devant un article, un nombre, un infinitif...). Charte graphique, section 3 :
le francais avec ses accents, toujours.
"""
import ast
import io
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
IDENT = re.compile(r"^[a-z0-9_:+\-./%{}\[\]#]*$")

from src.kora.francais import WORD, convert  # noqa: E402


def docstring_lines(src: str) -> set:
    out = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                out.update(range(body[0].lineno, body[0].end_lineno + 1))
    return out


def prose(inner: str) -> bool:
    return not IDENT.match(inner) and bool(WORD.search(inner))


def process(path: Path, dry: bool) -> list:
    src = path.read_text(encoding="utf-8")
    doc = docstring_lines(src)
    lines = src.split("\n")
    starts = [0]
    for ln in lines:
        starts.append(starts[-1] + len(ln) + 1)
    edits = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.start[0] in doc:
            continue
        a = starts[tok.start[0] - 1] + tok.start[1]
        b = starts[tok.end[0] - 1] + tok.end[1]
        piece = src[a:b]
        if tok.type == tokenize.STRING:
            m = re.match(r"^([rbuRBUfF]*)('''|\"\"\"|'|\")", piece)
            if not m or "b" in m.group(1).lower():
                continue
            q = len(m.group(1)) + len(m.group(2))
            inner = piece[q:-len(m.group(2))]
            if not prose(inner):
                continue
            new = piece[:q] + convert(inner) + piece[-len(m.group(2)):]
        elif tok.type == getattr(tokenize, "FSTRING_MIDDLE", -1):
            if not prose(piece):
                continue
            new = convert(piece, src[b:b + 1])
        else:
            continue
        if new != piece:
            edits.append((a, b, piece, new, tok.start[0]))
    if not dry and edits:
        out = src
        for a, b, _old, new, _ln in sorted(edits, reverse=True):
            out = out[:a] + new + out[b:]
        compile(out, str(path), "exec")
        path.write_text(out, encoding="utf-8")
    return edits


def main(argv) -> None:
    dry = "--dry" in argv
    files = [Path(a) for a in argv if not a.startswith("--")]
    if not files:
        files = sorted((ROOT / "src" / "kora").glob("*.py")) + sorted((ROOT / "tests").glob("*.py"))
    total = 0
    for p in files:
        if p.name in ("accents.py", "francais.py"):
            continue
        edits = process(p, dry)
        total += len(edits)
        if dry and "--montrer" in argv:
            for _a, _b, old, new, ln in edits:
                print(f"{p.name}:{ln}: {old[:120]!r}\n{'':>{len(p.name) + len(str(ln)) + 3}}{new[:120]!r}")
    print(total, "textes", "a changer" if dry else "changes")


if __name__ == "__main__":
    main(sys.argv[1:])
