"""LES NOTES DU DEPOT : ce que les IA lisent avant de travailler. Elles
doivent rester VRAIES : leurs dates, la version, les fichiers et les
fonctions qu'elles citent, et leurs parties tirees du code.

    python tools/notes.py status            l'etat des notes (debut de session)
    python tools/notes.py status --court    en quelques lignes (crochet SessionStart)
    python tools/notes.py check             tout verifier ; sortie 1 si une note ment
    python tools/notes.py write             refaire les parties automatiques

LES NOTES VIVANTES disent ce qui est vrai AUJOURD'HUI : CLAUDE.md,
docs/VISION-KORA.txt (sauf sa section 3, l'histoire), docs/code/*.txt,
docs/charte-graphique.txt, README.md, et les docstrings des modules (la
carte du depot les recopie). Tout nom "module.fonction" ou "Classe.champ"
qu'elles citent doit exister, tout fichier aussi. Les specs et la section
3 de la VISION sont l'HISTOIRE : leurs dates et les specs qu'elles citent
doivent etre justes ; les noms de fonctions peuvent y dater.

LES DATES se LISENT (le jour de la machine, git), jamais ne s'inventent ni
ne s'incrementent d'un chantier a l'autre : une spec ne porte pas une date
posterieure a son entree dans git ni a la version qu'elle dit faite ; une
entree de la VISION ne porte pas une date posterieure a son etiquette.

LES PARTIES AUTOMATIQUES, entre "<<< auto : NOM >>>" et "<<< fin auto >>>",
se tirent du code (docstrings, tools/dependances.LAYERS, tailles) : ne pas
les ecrire a la main ; `write` les refait, `check` dit si elles retardent.

tests/test_notes.py lance check : une note qui ment casse les tests. Ce
module n'importe pas le jeu (tout se lit par ast) : rapide, sans pygame.
"""
from __future__ import annotations

import ast
import datetime as dt
import pathlib
import re
import subprocess
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "kora"
TOOLS = ROOT / "tools"
TESTS = ROOT / "tests"
DOCS = ROOT / "docs"
SPECS = DOCS / "superpowers" / "specs"
PLANS = DOCS / "superpowers" / "plans"
HISTORY = DOCS / "historique"
VISION = DOCS / "VISION-KORA.txt"
CARTE = DOCS / "code" / "carte-du-depot.txt"
RECETTE = DOCS / "code" / "ajouter-un-systeme.txt"
CHARTE = DOCS / "charte-graphique.txt"
CLAUDE = ROOT / "CLAUDE.md"
README = ROOT / "README.md"
# Les notes de chaque version publiee (GitHub Releases) : release.yml les joint.
RELEASE_NOTES = ROOT / ".github" / "release-notes.md"
# Les notes vivantes (elles disent ce qui est vrai aujourd'hui).
LIVING = (CLAUDE, VISION, CARTE, RECETTE, CHARTE, README)

sys.path.insert(0, str(TOOLS))
import dependances  # noqa: E402

DATE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")
SPEC_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9][a-z0-9.-]*\.txt$")
SPEC_REF = re.compile(r"\b(\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9.-]*[a-z0-9])(?:\.txt)?")
VERSION = re.compile(r"\b(\d+\.\d+\.\d+)\b")
# Une date "dans le futur" : on tolere un jour (fuseaux horaires de la CI).
SLACK = dt.timedelta(days=1)
# Une entree de la VISION est livree au plus tard deux jours apres sa date.
DELIVERY = dt.timedelta(days=2)
AUTO = re.compile(r"(<<< auto : ([\w-]+) >>>\n)(.*?)(<<< fin auto >>>)", re.S)
# Ce qui suit un point sans etre un nom (sim.py, kora.json...).
FILE_EXT = {"py", "txt", "json", "png", "spec", "exe", "ogg", "md", "yml", "zip", "wav", "svg", "ini", "bat"}
# Les noms d'une instance courante dans les notes : state.tick_count...
ALIASES = {
    "state": "GameState", "tribe": "Tribe", "band": "Band", "site": "Site", "world": "World",
    "renderer": "Renderer", "clock": "Clock", "play": "Play",
}
# Les attributs herites (Enum, dataclass, NamedTuple) qu'on ne declare pas.
INHERITED = {"value", "name", "q", "r", "get", "items", "keys", "values", "copy", "count", "index"}


# --- lire --------------------------------------------------------------------------


def version() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', (SRC / "__init__.py").read_text(encoding="utf-8"))
    return m.group(1) if m else "?"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _date(s: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


class Git:
    """Ce que git sait (rien dans une copie superficielle, comme la CI)."""

    def __init__(self) -> None:
        shallow = _git("rev-parse", "--is-shallow-repository")
        self.ok = shallow is not None and shallow.strip() == "false"
        self.tags: dict[str, dt.date] = {}
        self.added: dict[str, dt.datetime] = {}
        if not self.ok:
            return
        for line in (_git("for-each-ref", "--format=%(refname:short) %(creatordate:iso-strict)", "refs/tags") or "").splitlines():
            name, _, when = line.partition(" ")
            if name.startswith("v") and when:
                self.tags[name[1:]] = dt.datetime.fromisoformat(when).date()
        self.added = self._added()

    def _added(self) -> dict[str, dt.datetime]:
        """Fichier de docs -> l'instant ou il est entre dans git (en suivant
        les renommages : un fichier renomme garde sa date d'entree)."""
        log = _git("log", "--format=@%ad", "--date=iso-strict", "--name-status", "-M", "--", "docs") or ""
        first: dict[str, dt.datetime] = {}
        renamed: dict[str, str] = {}
        when = None
        for line in log.splitlines():
            if line.startswith("@"):
                when = dt.datetime.fromisoformat(line[1:])
                continue
            parts = line.split("\t")
            if not parts or when is None:
                continue
            if parts[0] == "A" and len(parts) == 2:
                first[parts[1]] = when
            elif parts[0].startswith("R") and len(parts) == 3:
                renamed[parts[2]] = parts[1]
        out = {}
        for path in set(first) | set(renamed):
            p, seen = path, set()
            while p in renamed and p not in seen:
                seen.add(p)
                p = renamed[p]
            if p in first:
                out[path] = first[p]
        return out

    def added_at(self, path: pathlib.Path) -> dt.datetime | None:
        return self.added.get(path.relative_to(ROOT).as_posix())

    def last_change(self, path: pathlib.Path) -> dt.date | None:
        out = _git("log", "-1", "--format=%ad", "--date=short", "--", path.relative_to(ROOT).as_posix())
        return _date(out.strip()) if out and out.strip() else None


def spec_files() -> list[pathlib.Path]:
    out = []
    for d in (SPECS, PLANS, HISTORY):
        if d.is_dir():
            out.extend(sorted(d.glob("*.txt")))
    return out


def vision_sections(text: str) -> dict[int, str]:
    """Les sections numerotees de la VISION ("3. SES DEMANDES" ...)."""
    out: dict[int, str] = {}
    current, lines = 0, []
    for line in text.splitlines(keepends=True):
        m = re.match(r"^(\d+)\. [A-Z]", line)
        if m:
            out[current] = out.get(current, "") + "".join(lines)
            current, lines = int(m.group(1)), []
        lines.append(line)
    out[current] = out.get(current, "") + "".join(lines)
    return out


# --- l'index du code ----------------------------------------------------------------


def _top_names(body) -> set:
    names = set()
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                names |= {n.id for n in ast.walk(t) if isinstance(n, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, (ast.If, ast.Try, ast.With)):
            names |= _top_names(getattr(node, "body", []))
            names |= _top_names(getattr(node, "orelse", []))
            for h in getattr(node, "handlers", []):
                names |= _top_names(h.body)
    return names


class CodeIndex:
    """Les modules (src/kora, tools) et leurs noms ; les classes et leurs
    champs (declares, ou poses sur self dans une methode)."""

    def __init__(self) -> None:
        self.modules: dict[str, set] = {}
        self.classes: dict[str, set] = {}
        self.trees: dict[str, ast.Module] = {}
        self.bases: dict[str, set] = {}
        for folder in (SRC, TOOLS):
            for p in sorted(folder.glob("*.py")):
                if p.stem == "__init__":
                    continue
                tree = ast.parse(_read(p))
                if folder == SRC:
                    self.trees[p.stem] = tree
                self.modules.setdefault(p.stem, set()).update(_top_names(tree.body))
                for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
                    attrs = _top_names(cls.body)
                    for node in ast.walk(cls):
                        if (
                            isinstance(node, ast.Attribute)
                            and isinstance(node.value, ast.Name)
                            and node.value.id == "self"
                            and isinstance(node.ctx, ast.Store)
                        ):
                            attrs.add(node.attr)
                    self.classes.setdefault(cls.name, set()).update(attrs)
                    for b in cls.bases:
                        base = b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", None)
                        if base:
                            self.bases.setdefault(cls.name, set()).add(base)
                # world.atlas = ... (un champ pose du dehors, sur un nom d'instance connu)
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Attribute)
                        and isinstance(node.ctx, ast.Store)
                        and isinstance(node.value, ast.Name)
                        and node.value.id in ALIASES
                    ):
                        self.classes.setdefault(ALIASES[node.value.id], set()).add(node.attr)
        # ce qu'une classe herite de ses bases (Play : MapInput, ScreenClicks)
        for cls in list(self.classes):
            seen, todo = set(), list(self.bases.get(cls, ()))
            while todo:
                b = todo.pop()
                if b in seen or b not in self.classes:
                    continue
                seen.add(b)
                self.classes[cls] |= self.classes[b]
                todo.extend(self.bases.get(b, ()))

    def knows(self, left: str, right: str) -> bool | None:
        """Vrai / faux si "left.right" est un nom du jeu qu'on sait juger ;
        None si ce n'en est pas un (un mot qui suit un point)."""
        if right in FILE_EXT:
            return None
        found = None
        if left in self.modules:
            found = right in self.modules[left]
        cls = left if left in self.classes else ALIASES.get(left)
        if cls in self.classes:
            ok = right in self.classes[cls] or right in INHERITED
            found = ok or bool(found)
        return found


REF = re.compile(r"(?<![\w./\\-])([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)")
PATH_REF = re.compile(r"(?<![\w/])((?:src/kora|tools|tests|docs|data|\.github)/[\w./-]*[\w])")
PY_REF = re.compile(r"(?<![\w/.-])([a-z_][a-z0-9_]*\.py)\b")


def _known_files() -> set:
    out = {p.name for d in (SRC, TOOLS, TESTS) for p in d.glob("*.py")}
    out |= {p.name for p in ROOT.glob("*.py")}
    return out


def check_refs(name: str, text: str, index: CodeIndex) -> list[str]:
    """Les noms et fichiers cites par une note vivante existent."""
    out = []
    files = _known_files()
    for n, line in enumerate(text.splitlines(), 1):
        for m in REF.finditer(line):
            if index.knows(m.group(1), m.group(2)) is False:
                out.append(f"{name}:{n} : {m.group(0)} n'existe pas dans le code")
        for m in PATH_REF.finditer(line):
            rel = m.group(1).rstrip(".")
            if line[m.end():m.end() + 1] in ("<", "*") or (ROOT / rel).exists():
                continue
            base, _, attr = rel.rpartition(".")
            if base and (ROOT / f"{base}.py").exists() and attr not in FILE_EXT:
                if index.knows(pathlib.Path(base).name, attr) is False:
                    out.append(f"{name}:{n} : {rel} n'existe pas dans le code")
                continue
            out.append(f"{name}:{n} : le fichier {rel} n'existe pas")
        for m in PY_REF.finditer(line):
            if m.group(1) not in files:
                out.append(f"{name}:{n} : le module {m.group(1)} n'existe pas")
    return out


def check_spec_refs(name: str, text: str) -> list[str]:
    """Les specs citees (AAAA-MM-JJ-nom) existent."""
    stems = {p.stem for p in spec_files()}
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in SPEC_REF.finditer(line):
            ref = m.group(1).removesuffix(".txt")
            if ref not in stems and not any(s.startswith(ref) for s in stems):
                out.append(f"{name}:{n} : la spec {ref} n'existe pas")
    return out


# --- les dates ----------------------------------------------------------------------


def check_future(name: str, text: str, today: dt.date) -> list[str]:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in DATE.finditer(line):
            d = _date(m.group(1))
            if d and d > today + SLACK:
                out.append(f"{name}:{n} : {d} est dans le futur (aujourd'hui : {today}) : une date se lit, elle ne s'invente pas")
    return out


def check_spec(path: pathlib.Path, text: str, today: dt.date, git: Git) -> list[str]:
    name = path.relative_to(ROOT).as_posix()
    m = SPEC_NAME.match(path.name)
    if not m:
        return [f"{name} : le nom doit etre AAAA-MM-JJ-sujet.txt"]
    day = _date(m.group(1))
    out = []
    if day is None:
        return [f"{name} : date impossible"]
    if day > today + SLACK:
        out.append(f"{name} : datee du {day}, dans le futur (aujourd'hui : {today})")
    line = re.search(r"^Date\s*:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    if line and line.group(1) != m.group(1):
        out.append(f"{name} : 'Date : {line.group(1)}' ne dit pas la date du nom ({m.group(1)})")
    added = git.added_at(path) if git.ok else None
    if added and day > added.date():
        out.append(f"{name} : datee du {day} mais entree dans git le {added.date()} : la renommer")
    done = re.search(r"Statut\s*:\s*FAIT\s*\(version\s*(\d+\.\d+\.\d+)", text)
    if done and done.group(1) in git.tags and day > git.tags[done.group(1)]:
        out.append(f"{name} : datee du {day} mais la version {done.group(1)} est sortie le {git.tags[done.group(1)]}")
    return out


def check_vision(text: str, today: dt.date, tags: dict, current: str) -> list[str]:
    out = []
    sections = vision_sections(text)
    story = sections.get(3, "")
    if not story:
        return ["VISION : pas de section 3 (ses demandes)"]
    last = None
    for n, line in enumerate(story.splitlines(), 1):
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\b(.*)$", line)
        if not m:
            continue
        day = _date(m.group(1))
        if day is None:
            out.append(f"VISION section 3 : date impossible '{line.strip()}'")
            continue
        if last and day < last:
            out.append(f"VISION section 3 : {day} vient apres {last} (l'ordre des jours)")
        last = day
        if day > today + SLACK:
            out.append(f"VISION section 3 : {day} est dans le futur (aujourd'hui : {today})")
        for v in VERSION.findall(m.group(2)):
            t = tags.get(v)
            if t and not (day <= t <= day + DELIVERY):
                out.append(f"VISION section 3 : l'entree du {day} dit {v}, sortie le {t} : la date est fausse")
    head = re.search(r"Derniere mise a jour\s*:\s*(\d{4}-\d{2}-\d{2})", text)
    if not head:
        out.append("VISION : pas de 'Derniere mise a jour : AAAA-MM-JJ' en tete")
    else:
        d = _date(head.group(1))
        if last and d and d < last:
            out.append(f"VISION : 'Derniere mise a jour : {d}' avant sa derniere entree ({last})")
        if d and d > today + SLACK:
            out.append(f"VISION : 'Derniere mise a jour : {d}' est dans le futur")
    m = re.search(r"Version du jeu\s*:\s*(\d+\.\d+\.\d+)", sections.get(5, ""))
    if not m:
        out.append("VISION section 5 : pas de 'Version du jeu : X.Y.Z'")
    elif m.group(1) != current:
        out.append(f"VISION section 5 : 'Version du jeu : {m.group(1)}' mais le jeu est en {current}")
    return out


def check_release_notes(text: str, current: str) -> list[str]:
    """Les notes de version disent la version publiee (\"Nouveau dans la X.Y\")."""
    m = re.search(r"Nouveau dans la (\d+\.\d+)", text)
    major_minor = ".".join(current.split(".")[:2])
    if not m:
        return [".github/release-notes.md : pas de 'Nouveau dans la X.Y'"]
    if m.group(1) != major_minor:
        return [f".github/release-notes.md : 'Nouveau dans la {m.group(1)}' mais le jeu est en {current} : les reecrire avant de publier"]
    return []


def check_carte_version(text: str, current: str) -> list[str]:
    m = re.search(r"A jour pour la version\s*:\s*(\d+\.\d+\.\d+)", text)
    if not m:
        return ["carte-du-depot : pas de 'A jour pour la version : X.Y.Z' en tete"]
    if m.group(1) != current:
        return [f"carte-du-depot : 'A jour pour la version : {m.group(1)}' mais le jeu est en {current} : la relire et la mettre a jour"]
    return []


# --- les parties automatiques -------------------------------------------------------


def _doc(path: pathlib.Path) -> str:
    return ast.get_docstring(ast.parse(_read(path))) or ""


def _first_par(doc: str) -> list[str]:
    par = doc.strip().split("\n\n")[0]
    return [line.rstrip() for line in par.splitlines()]


def _wrap(label: str, names: list[str], indent: str) -> list[str]:
    if not names:
        return []
    return textwrap.wrap(
        f"{label} : " + ", ".join(names), width=78, initial_indent=indent, subsequent_indent=indent + "  ",
        break_on_hyphens=False, break_long_words=False,
    )


def _public(tree: ast.Module) -> tuple[list, list, list]:
    funcs, classes, consts = [], [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            funcs.append(node.name)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            classes.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id.isupper() and not t.id.startswith("_"):
                    consts.append(t.id)
    uniq = lambda xs: list(dict.fromkeys(xs))  # noqa: E731
    return uniq(funcs), uniq(classes), uniq(consts)


def _layers() -> list[tuple[str, list[str]]]:
    out = [(f"{i}  {dependances.LAYER_NAMES[i]}", list(ms)) for i, ms in enumerate(dependances.LAYERS)]
    out.append(("-  l'interface (pygame)", sorted(dependances.presentation())))
    return out


def gen_etages() -> str:
    lines = []
    for title, ms in _layers():
        lines.append(f"  {title}")
        lines += textwrap.wrap(", ".join(ms), width=78, initial_indent=" " * 7, subsequent_indent=" " * 7, break_on_hyphens=False)
    return "\n".join(lines) + "\n"


def gen_modules() -> str:
    lines = []
    known = set()
    for title, ms in _layers():
        lines += ["", f"ETAGE {title}", ""]
        for m in ms:
            p = SRC / f"{m}.py"
            if not p.exists():
                continue
            known.add(m)
            tree = ast.parse(_read(p))
            lines.append(f"  {m}.py")
            for line in _first_par(ast.get_docstring(tree) or "(SANS DOCSTRING)"):
                lines.append(f"    {line}".rstrip())
            funcs, classes, consts = _public(tree)
            lines += _wrap("classes", classes, "    ")
            lines += _wrap("fonctions", funcs, "    ")
            lines += _wrap("constantes", consts, "    ")
            lines.append("")
    rest = sorted(p.stem for p in SRC.glob("*.py") if p.stem not in known and p.stem != "__init__")
    if rest:
        lines += ["SANS ETAGE (tools/dependances.LAYERS) : " + ", ".join(rest), ""]
    return "\n".join(lines).lstrip("\n")


def gen_outils() -> str:
    lines = []
    for p in sorted(TOOLS.glob("*.py")):
        lines.append(f"  tools/{p.name}")
        lines += [f"    {line}".rstrip() for line in _first_par(_doc(p) or "(SANS DOCSTRING)")]
    return "\n".join(lines) + "\n"


def gen_tests() -> str:
    lines = []
    for p in sorted(TESTS.glob("*.py")):
        doc = _doc(p)
        first = _first_par(doc)[0] if doc else "(SANS DOCSTRING)"
        lines += textwrap.wrap(f"{first}", width=78, initial_indent=f"  {p.name:28s}", subsequent_indent=" " * 30)
    return "\n".join(lines) + "\n"


def gen_specs() -> str:
    lines = []
    for p in spec_files():
        text = _read(p)
        title = text.splitlines()[0].strip() if text else p.stem
        title = re.sub(r"^(Kora|KORA)\s*[-—:]\s*", "", title)
        statut = re.search(r"Statut\s*:\s*([^\n]*)", text)
        rel = p.relative_to(DOCS / "superpowers").as_posix() if DOCS / "superpowers" in p.parents else p.relative_to(DOCS).as_posix()
        lines.append(f"  {rel}")
        lines += textwrap.wrap(title, width=74, initial_indent="    ", subsequent_indent="    ")
        if statut:
            lines += textwrap.wrap("Statut : " + statut.group(1).strip(), width=74, initial_indent="    ", subsequent_indent="      ")
    return "\n".join(lines) + "\n"


def gen_gros_modules() -> str:
    rows = []
    for p in sorted(SRC.glob("*.py")):
        n = len(_read(p).splitlines())
        if n >= 1000:
            rows.append((n, p.name))
    rows.sort(reverse=True)
    if not rows:
        return "  (aucun module de plus de 1000 lignes)\n"
    return "\n".join(f"  {name:22s} ~{round(n, -2)} lignes" for n, name in rows) + "\n"


GENERATORS = {
    "etages": gen_etages,
    "modules": gen_modules,
    "outils": gen_outils,
    "tests": gen_tests,
    "specs": gen_specs,
    "gros-modules": gen_gros_modules,
}


def refresh(text: str) -> str:
    def one(m: re.Match) -> str:
        gen = GENERATORS.get(m.group(2))
        body = gen() if gen else m.group(3)
        return m.group(1) + body + m.group(4)

    return AUTO.sub(one, text)


def check_auto(name: str, text: str) -> list[str]:
    out = []
    for m in AUTO.finditer(text):
        if m.group(2) not in GENERATORS:
            out.append(f"{name} : partie automatique inconnue '{m.group(2)}'")
    if refresh(text) != text:
        out.append(f"{name} : ses parties automatiques retardent sur le code : python tools/notes.py write")
    return out


# --- tout ensemble ------------------------------------------------------------------


def check(today: dt.date | None = None) -> list[str]:
    today = today or dt.date.today()
    git = Git()
    index = CodeIndex()
    current = version()
    out: list[str] = []
    for path in LIVING:
        if not path.exists():
            out.append(f"{path.name} : la note n'existe pas")
            continue
        text = _read(path)
        name = path.relative_to(ROOT).as_posix()
        out += check_future(name, text, today)
        out += check_spec_refs(name, text)
        out += check_auto(name, text)
        living = text
        if path == VISION:
            secs = vision_sections(text)
            # la section 3 (l'histoire) blanchie : les numeros de ligne restent justes
            living = "".join(v if k != 3 else "\n" * v.count("\n") for k, v in sorted(secs.items()))
            out += check_vision(text, today, git.tags, current)
        elif path == CARTE:
            out += check_carte_version(text, current)
        out += check_refs(name, refresh(living) if AUTO.search(living) else living, index)
    if RELEASE_NOTES.exists():
        out += check_release_notes(_read(RELEASE_NOTES), current)
    for path in spec_files():
        text = _read(path)
        out += check_spec(path, text, today, git)
        out += check_spec_refs(path.relative_to(ROOT).as_posix(), text)
    for folder in (SRC, TOOLS, TESTS):
        for p in sorted(folder.glob("*.py")):
            if p.stem in ("__init__", "conftest"):
                continue
            doc = _doc(p)
            if not doc.strip():
                out.append(f"{p.relative_to(ROOT).as_posix()} : sans docstring (la carte du depot la recopie)")
            elif folder == SRC:
                out += check_refs(f"{p.relative_to(ROOT).as_posix()} (docstring)", doc, index)
    return out


def write() -> list[str]:
    changed = []
    for path in LIVING:
        if not path.exists():
            continue
        text = _read(path)
        new = refresh(text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(path.relative_to(ROOT).as_posix())
    return changed


def latest_spec(git: Git) -> pathlib.Path | None:
    def key(p: pathlib.Path):
        m = SPEC_NAME.match(p.name)
        added = git.added_at(p) if git.ok else None
        when = added.timestamp() if added else p.stat().st_mtime
        return (m.group(1) if m else "", when)

    specs = sorted(SPECS.glob("*.txt"), key=key) if SPECS.is_dir() else []
    return specs[-1] if specs else None


def status(short: bool = False) -> str:
    today = dt.date.today()
    git = Git()
    current = version()
    lines = ["KORA - l'etat des notes (python tools/notes.py status)"]
    lines.append(f"  Aujourd'hui : {today} (la date de la machine : c'est elle qu'on ecrit, jamais une date inventee ou incrementee)")
    head = _git("log", "-1", "--format=%ad|%s", "--date=short") or ""
    when, _, subject = head.strip().partition("|")
    dirty = _git("status", "--porcelain") or ""
    n_dirty = len([x for x in dirty.splitlines() if x.strip()])
    lines.append(f"  Version du jeu : {current} ; dernier commit : {when} \"{subject}\" ; {n_dirty} fichier(s) non commite(s)")
    spec = latest_spec(git)
    if spec:
        lines.append(f"  Derniere spec : {spec.relative_to(ROOT).as_posix()}")
    vt = _read(VISION) if VISION.exists() else ""
    days = re.findall(r"^(\d{4}-\d{2}-\d{2})", vision_sections(vt).get(3, ""), re.M)
    if days:
        lines.append(f"  VISION : derniere demande datee du {days[-1]}")
    if git.ok and not short:
        stale = []
        for path in LIVING:
            last = git.last_change(path)
            if last:
                behind = sum(1 for d in git.tags.values() if d > last)
                if behind >= 3:
                    stale.append(f"{path.relative_to(ROOT).as_posix()} ({behind} versions sans retouche)")
        if stale:
            lines.append("  A relire (ne ment peut-etre pas, mais n'a pas suivi le jeu) : " + "; ".join(stale))
    problems = check(today)
    if problems:
        lines.append(f"  {len(problems)} probleme(s) dans les notes (python tools/notes.py check) :")
        lines += [f"    - {p}" for p in problems[: 5 if short else 40]]
        if len(problems) > (5 if short else 40):
            lines.append("    ...")
    else:
        lines.append("  Les notes disent vrai (check : 0 probleme).")
    if short:
        lines.append("  A faire : lire CLAUDE.md, docs/VISION-KORA.txt, la derniere spec ; en fin de chantier : notes.py write puis check.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        try:
            print(status(short="--court" in argv))
        except Exception as exc:  # le crochet de debut de session ne doit jamais casser
            print(f"KORA - notes.py status a echoue ({exc!r}) ; date du jour : {dt.date.today()}")
        return 0
    if cmd == "check":
        problems = check()
        for p in problems:
            print(p)
        print(f"{len(problems)} probleme(s).")
        return 1 if problems else 0
    if cmd == "write":
        changed = write()
        print("refait :", ", ".join(changed) if changed else "rien (deja a jour)")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
