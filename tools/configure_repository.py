"""Confere configurações do GitHub; somente --apply solicita alterações administrativas.

Usa a autenticação existente do GitHub CLI. Não lê tokens, troca credenciais,
remove branches/labels ou modifica a visibilidade do repositório.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / ".github/repository-settings.json"
SETTINGS = {
    "description", "homepage", "has_wiki", "has_projects", "delete_branch_on_merge",
    "allow_update_branch", "allow_merge_commit", "allow_squash_merge", "allow_rebase_merge",
}
FLAGS = {
    "enforce_admins", "required_conversation_resolution", "allow_force_pushes", "allow_deletions",
}
REVIEWS = {"dismiss_stale_reviews", "require_code_owner_reviews", "required_approving_review_count"}
SECTIONS = ("settings", "topics", "labels", "branch_protection", "private_vulnerability_reporting")
TITLES = {
    "settings": "Apresentação e opções do repositório",
    "topics": "Tópicos",
    "labels": "Labels",
    "branch_protection": "Proteção da branch principal",
    "private_vulnerability_reporting": "Relatos privados de vulnerabilidades",
}


class ConfigError(ValueError):
    pass


class ApiError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _require(condition, message):
    if not condition:
        raise ConfigError(message)


def _keys(value, expected, label):
    _require(isinstance(value, dict) and set(value) == expected, f"Campos inválidos em {label}.")


def validate_config(config):
    """Valida o documento inteiro antes de executar qualquer chamada ao GitHub."""
    _keys(config, {"repository", *SECTIONS}, "configuração")
    repo = config["repository"]
    _require(isinstance(repo, str) and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", repo
    ) and repo.split("/")[1] not in {".", ".."}, "Use repository no formato proprietário/repositório.")
    settings = config["settings"]
    _keys(settings, SETTINGS, "settings")
    _require(isinstance(settings["description"], str) and 0 < len(settings["description"]) <= 350,
             "A descrição deve ter entre 1 e 350 caracteres.")
    homepage = settings["homepage"]
    _require(isinstance(homepage, str), "homepage deve ser uma URL HTTPS.")
    try:
        parsed = urlsplit(homepage)
        valid_url = (
            parsed.scheme == "https" and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
        )
        parsed.port  # Reject malformed ports before sending any change.
    except ValueError:
        valid_url = False
    _require(valid_url and not any(char.isspace() for char in homepage),
             "homepage deve ser uma URL HTTPS sem credenciais.")
    for key in SETTINGS - {"description", "homepage"}:
        _require(type(settings[key]) is bool, f"settings.{key} deve ser booleano.")
    topics = config["topics"]
    _require(isinstance(topics, list) and 1 <= len(topics) <= 20 and all(
        isinstance(item, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", item)
        for item in topics
    ) and len(set(topics)) == len(topics), "topics deve conter de 1 a 20 nomes únicos válidos.")
    labels = config["labels"]
    _require(isinstance(labels, list) and labels, "labels deve conter as definições desejadas.")
    names = set()
    for label in labels:
        _keys(label, {"name", "color", "description"}, "label")
        name = label["name"]
        _require(isinstance(name, str) and 0 < len(name) <= 50 and name == name.strip()
                 and all(char.isprintable() for char in name), "Nome de label inválido.")
        _require(name.casefold() not in names, "Labels duplicadas não são permitidas.")
        names.add(name.casefold())
        _require(isinstance(label["color"], str) and re.fullmatch(r"[0-9a-f]{6}", label["color"]),
                 f"Cor inválida na label {name}.")
        _require(isinstance(label["description"], str) and len(label["description"]) <= 100,
                 f"Descrição inválida na label {name}.")
    protection = config["branch_protection"]
    _keys(protection, {"branch", "required_status_checks", "required_pull_request_reviews",
                       "restrictions", *FLAGS}, "branch_protection")
    _require(protection["branch"] == "main", "Esta configuração protege a branch main.")
    _keys(protection["required_status_checks"], {"strict", "contexts"}, "required_status_checks")
    checks = protection["required_status_checks"]
    contexts = checks["contexts"]
    _require(type(checks["strict"]) is bool and isinstance(contexts, list) and contexts
             and all(isinstance(name, str) and name.strip() == name and name for name in contexts)
             and len(set(contexts)) == len(contexts), "Checks obrigatórios inválidos.")
    for key in FLAGS:
        _require(type(protection[key]) is bool, f"branch_protection.{key} deve ser booleano.")
    _require(protection["restrictions"] is None, "restrictions deve ser null; não gerencia equipes.")
    reviews = protection["required_pull_request_reviews"]
    _keys(reviews, REVIEWS, "required_pull_request_reviews")
    _require(type(reviews["dismiss_stale_reviews"]) is bool
             and type(reviews["require_code_owner_reviews"]) is bool
             and type(reviews["required_approving_review_count"]) is int
             and 0 <= reviews["required_approving_review_count"] <= 6, "Regras de revisão inválidas.")
    _require(config["private_vulnerability_reporting"] is True,
             "private_vulnerability_reporting deve ser true; este script apenas habilita o recurso.")
    return config


def load_config(path):
    try:
        return validate_config(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Não foi possível ler a configuração: {exc}") from exc


class GitHub:
    def request(self, method, path, payload=None, *, paginate=False):
        arguments = [
            "gh", "api", "--hostname", "github.com", "--method", method, path,
            "--header", "Accept: application/vnd.github+json",
            "--header", "X-GitHub-Api-Version: 2022-11-28",
        ]
        if paginate:
            arguments.append("--paginate")
        if payload is not None:
            arguments.extend(("--input", "-"))
        try:
            result = subprocess.run(
                arguments, input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                text=True, capture_output=True, shell=False, timeout=30, check=False,
            )
        except FileNotFoundError as exc:
            raise ApiError("GitHub CLI não encontrado. Instale gh e use sua autenticação existente.") from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ApiError(f"Não foi possível concluir a chamada ao GitHub: {exc}") from exc
        if result.returncode:
            match = re.search(r"HTTP\s+(\d{3})", result.stderr)
            raise ApiError(result.stderr.strip()[:500] or "A chamada ao GitHub falhou.",
                           int(match[1]) if match else None)
        if not result.stdout.strip():
            return None
        try:
            if paginate:
                decoder = json.JSONDecoder()
                remaining = result.stdout.lstrip()
                pages = []
                while remaining:
                    page, end = decoder.raw_decode(remaining)
                    pages.append(page)
                    remaining = remaining[end:].lstrip()
                return pages
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ApiError("O GitHub CLI retornou uma resposta JSON inválida.") from exc


def read_section(api, base, section, config):
    if section == "settings":
        return api.request("GET", base)
    if section == "topics":
        return api.request("GET", base + "/topics")["names"]
    if section == "labels":
        pages = api.request("GET", base + "/labels?per_page=100", paginate=True)
        return [label for page in pages for label in page]
    if section == "branch_protection":
        branch = quote(config[section]["branch"], safe="")
        try:
            return api.request("GET", base + f"/branches/{branch}/protection")
        except ApiError as exc:
            if exc.status == 404:
                return None
            raise
    return api.request("GET", base + "/private-vulnerability-reporting")["enabled"]


def matches(section, current, desired):
    if section == "settings":
        return all(current.get(key) == value for key, value in desired.items())
    if section == "topics":
        return sorted(current) == sorted(desired)
    if section == "labels":
        existing = {item["name"].casefold(): item for item in current}
        return all(all(existing.get(label["name"].casefold(), {}).get(key) == value
                       for key, value in label.items()) for label in desired)
    if section == "branch_protection":
        if not isinstance(current, dict):
            return False
        checks = current.get("required_status_checks") or {}
        reviews = current.get("required_pull_request_reviews") or {}
        return (
            checks.get("strict") == desired["required_status_checks"]["strict"]
            and sorted(checks.get("contexts", ())) == sorted(desired["required_status_checks"]["contexts"])
            and all(reviews.get(key) == value for key, value in desired["required_pull_request_reviews"].items())
            and all((current.get(key) or {}).get("enabled") == desired[key] for key in FLAGS)
            and current.get("restrictions") == desired["restrictions"]
        )
    return current == desired


def apply_section(api, base, section, current, desired):
    if section == "settings":
        api.request("PATCH", base, desired)
    elif section == "topics":
        api.request("PUT", base + "/topics", {"names": desired})
    elif section == "labels":
        existing = {item["name"].casefold(): item for item in current}
        for label in desired:
            previous = existing.get(label["name"].casefold())
            if previous is None:
                api.request("POST", base + "/labels", label)
            elif any(previous.get(key) != value for key, value in label.items()):
                payload = {"new_name": label["name"], "color": label["color"],
                           "description": label["description"]}
                api.request("PATCH", base + "/labels/" + quote(previous["name"], safe=""), payload)
    elif section == "branch_protection":
        payload = {key: value for key, value in desired.items() if key != "branch"}
        api.request("PUT", base + "/branches/" + quote(desired["branch"], safe="") + "/protection", payload)
    else:
        api.request("PUT", base + "/private-vulnerability-reporting")


def configure(config, api, *, apply=False):
    validate_config(config)
    base = "repos/" + config["repository"]
    repository = api.request("GET", base)
    if not isinstance(repository, dict) or str(repository.get("full_name", "")).casefold() != config["repository"].casefold():
        raise ConfigError("A resposta não corresponde ao repositório configurado.")
    if repository.get("default_branch") != config["branch_protection"]["branch"]:
        raise ConfigError("A branch padrão difere da configuração; confira o documento antes de aplicar.")
    failures = 0
    for section in SECTIONS:
        try:
            current = read_section(api, base, section, config)
            if matches(section, current, config[section]):
                print(f"OK: {TITLES[section]}")
            elif not apply:
                failures += 1
                print(f"Pendente: {TITLES[section]}")
            else:
                apply_section(api, base, section, current, config[section])
                if not matches(section, read_section(api, base, section, config), config[section]):
                    raise ApiError("A conferência posterior ainda diverge da configuração desejada.")
                print(f"Aplicado e conferido: {TITLES[section]}")
        except (ApiError, AttributeError, KeyError, TypeError) as exc:
            failures += 1
            print(f"Não concluído: {TITLES[section]}: {exc}", file=sys.stderr)
            if isinstance(exc, ApiError) and exc.status in (401, 403):
                print("Use gh autenticado pelo proprietário/administrador com a permissão necessária "
                      "ou ajuste essa seção nas configurações do GitHub. Nenhuma credencial foi alterada.",
                      file=sys.stderr)
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Somente conferir; é o comportamento padrão.")
    mode.add_argument("--apply", action="store_true", help="Aplicar e conferir configurações usando o gh atual.")
    arguments = parser.parse_args(argv)
    try:
        return configure(load_config(arguments.config), GitHub(), apply=arguments.apply)
    except (ConfigError, ApiError) as exc:
        print(f"Configuração não aplicada: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
