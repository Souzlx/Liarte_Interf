"""Check tracked repository files without importing the application or using the network.

Markdown coverage: single-line inline links/images, including angle-bracket paths,
balanced parentheses and optional titles. Fenced blocks and inline code are ignored.
Reference-style links, HTML, external URLs and fragment/anchor contents are outside
this check. Known generated/private filenames are checked, not secret contents.
"""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import posixpath
import re
import string
import subprocess
from urllib.parse import unquote


REQUIRED_FILES = (
    "README.md",
    "CONTRIBUTING.md",
    "SUPPORT.md",
    "docs/README.md",
    "docs/ARQUITETURA.md",
    "docs/STATUS.md",
    ".gitignore",
    "pyproject.toml",
    "requirements.txt",
    ".github/repository-settings.json",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/pull_request_template.md",
    ".github/workflows/tests.yml",
    ".github/workflows/repository.yml",
)
GENERATED_DIRECTORIES = {
    "__pycache__", ".venv", "venv", "env", ".liarte-desktop-env",
    "build", "dist", "logs", "log", "profile", "profiles",
    "instalador", "release_assets", "release_bundle", "node_modules",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "htmlcov",
}
PRIVATE_OR_GENERATED_SUFFIXES = {".pbix", ".pbit", ".exe", ".whl", ".pyc", ".pyo"}
ROOT_GENERATED_FILES = {
    "preparacao-desktop.log", "preparacao.lock", "ambiente-verificado.json",
    "validacao-qt.json",
}
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
ESCAPE = re.compile(r"\\([" + re.escape(string.punctuation + " ") + r"])")
TITLE_END = re.compile(r'''\s+(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\((?:\\.|[^)\\])*\))\s*\)''')


def tracked_files(root: Path) -> set[str]:
    """Use the index so staged additions/renames/deletions match the next checkout."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "-z"],
        capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError("Não foi possível consultar o índice Git. Informe a raiz do repositório.")
    return set(result.stdout.decode("utf-8", errors="surrogateescape").split("\0")) - {""}


def file_policy_error(name: str) -> str | None:
    path = PurePosixPath(name)
    if path.suffix.casefold() in PRIVATE_OR_GENERATED_SUFFIXES:
        return "arquivo privado ou compilado; use dados sintéticos ou os artefatos/releases"
    for part in path.parts[:-1]:
        lower = part.casefold()
        if (
            lower in GENERATED_DIRECTORIES
            or lower.startswith(".liarte-dev-profile")
            or lower.startswith(".liarte-desktop-env.")
        ):
            return "diretório de ambiente, perfil ou saída gerada não deve ser versionado"
    lower = path.name.casefold()
    if lower == ".env" or (
        lower.startswith(".env.") and lower.rsplit(".", 1)[-1] not in {"example", "sample", "template"}
    ):
        return "arquivo de variáveis local; mantenha somente exemplos sem valores privados"
    if len(path.parts) == 1 and lower in ROOT_GENERATED_FILES:
        return "resultado local de preparação não deve ser versionado"
    return None


def mask_inline_code(line: str) -> str:
    """Keep positions while masking matched backtick spans."""
    return re.sub(r"(`+)(?!`)(.*?)(?<!`)\1(?!`)", lambda match: " " * len(match[0]), line)


def inline_target(line: str, start: int) -> tuple[str, int] | None:
    index = start
    while index < len(line) and line[index].isspace():
        index += 1
    begin = index
    angle = index < len(line) and line[index] == "<"
    if angle:
        begin = index = index + 1
    depth = 0
    while index < len(line):
        char = line[index]
        if char == "\\":
            index += 2
            continue
        if angle and char == ">":
            target = line[begin:index]
            end = index + 1
            if end < len(line) and line[end] == ")":
                return target, end + 1
            title = TITLE_END.match(line, end)
            return (target, title.end()) if title else None
        if not angle:
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    return line[begin:index], index + 1
                depth -= 1
            elif char.isspace() and depth == 0:
                title = TITLE_END.match(line, index)
                return (line[begin:index], title.end()) if title else None
        index += 1
    return None


def inline_links(text: str):
    fence_char, fence_length = "", 0
    for number, original in enumerate(text.splitlines(), 1):
        fence = FENCE.match(original)
        if fence:
            marker = fence[1]
            if not fence_char:
                fence_char, fence_length = marker[0], len(marker)
            elif (
                marker[0] == fence_char and len(marker) >= fence_length
                and not original[fence.end():].strip()
            ):
                fence_char = ""
            continue
        if fence_char:
            continue
        line = mask_inline_code(original)
        brackets = []
        index = 0
        while index < len(line):
            if line[index] == "\\":
                index += 2
                continue
            if line[index] == "[":
                brackets.append(index)
            elif line[index] == "]" and brackets:
                brackets.pop()
                if index + 1 < len(line) and line[index + 1] == "(":
                    parsed = inline_target(line, index + 2)
                    if parsed:
                        target, index = parsed
                        yield number, ESCAPE.sub(r"\1", target)
                        continue
            index += 1


def markdown_target(source: str, target: str) -> str | None:
    if not target or target.startswith(("#", "//")) or SCHEME.match(target):
        return None
    path = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not path:
        return None
    if "\\" in path:
        raise ValueError("use '/' nos caminhos Markdown")
    if path.startswith("/"):
        normalized = posixpath.normpath(path.lstrip("/"))
    else:
        normalized = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError("o destino sai da raiz do repositório")
    return normalized


def check_repository(root: Path) -> list[str]:
    root = root.resolve()
    files = tracked_files(root)
    directories = {"."}
    for name in files:
        directories.update(str(parent) for parent in PurePosixPath(name).parents)
    targets = files | directories
    folded = {}
    for name in sorted(targets):
        folded.setdefault(name.casefold(), name)
    errors = []
    for required in REQUIRED_FILES:
        if required not in files:
            errors.append(f"{required}: arquivo essencial ausente do índice Git; adicione-o antes de enviar")
        elif not (root / required).is_file():
            errors.append(f"{required}: arquivo essencial não existe na árvore de trabalho")
    for name in sorted(files):
        if reason := file_policy_error(name):
            errors.append(f"{name}: {reason}")
        if PurePosixPath(name).suffix.casefold() not in {".md", ".markdown"}:
            continue
        source = root / name
        if not source.resolve().is_relative_to(root):
            errors.append(f"{name}: o arquivo Markdown aponta para fora do repositório")
            continue
        try:
            text = source.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            errors.append(f"{name}: não foi possível ler o Markdown em UTF-8 ({error})")
            continue
        for line, target in inline_links(text):
            prefix = f"{name}:{line}: {target!r}"
            try:
                relative = markdown_target(name, target)
                if relative is None:
                    continue
                destination = root / relative
                if not destination.resolve().is_relative_to(root):
                    raise ValueError("o destino ou link simbólico sai da raiz do repositório")
                if relative not in targets:
                    if expected := folded.get(relative.casefold()):
                        raise ValueError(f"maiúsculas/minúsculas divergentes; use {expected!r}")
                    raise ValueError("destino ausente do índice Git; corrija o link ou versione o arquivo")
                if not destination.exists():
                    raise ValueError("destino não existe na árvore de trabalho")
            except (OSError, ValueError) as error:
                errors.append(f"{prefix}: {error}")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        errors = check_repository(args.root)
    except (OSError, RuntimeError) as error:
        print(f"ERRO: {error}")
        return 2
    if errors:
        for error in errors:
            print(f"ERRO: {error}")
        print(f"\nOrganização do repositório: {len(errors)} problema(s).")
        return 1
    print("Organização do repositório: arquivos essenciais, links locais e política de arquivos válidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
