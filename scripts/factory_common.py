"""Gemeinsame Konfiguration, Rollenpolitik und Audit-Schreibzugriff."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class FactoryError(Exception):
    """Erwarteter Fabrikfehler mit einer lesbaren Meldung."""


class PolicyError(FactoryError):
    """Eine Rolle hat etwas versucht, das die Policy verbietet."""


SECRET_KEY_RE = re.compile(
    r"(password|secret|token|authorization|api_key|credential)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(?i)(app_password|client_secret|refresh_token|access_token|bearer\s+[a-z0-9._\-]{8,})"
)
UNSAFE_CHECK_RE = re.compile(
    r"(?i)(\bgit\s+push\b|\bgit\s+merge\b|\bdeploy\b|\brm\s+-rf\s+/|\bcurl\b[^\n]*\|\s*(?:ba)?sh\b)"
)


def root() -> Path:
    override = os.environ.get("FACTORY_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parent.parent


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise FactoryError(f"Konfiguration ist kein Objekt: {path}")
    return data


def factory_config() -> dict[str, Any]:
    return load_yaml(root() / "config" / "factory.yaml")


def roles_config() -> dict[str, Any]:
    return load_yaml(root() / "config" / "roles.yaml")


def projects_config() -> dict[str, Any]:
    return load_yaml(root() / "config" / "projects.yaml")


def stack_name(key: str) -> str:
    stacks = factory_config()["stacks"]
    try:
        return str(stacks[key])
    except KeyError as exc:
        raise FactoryError(f"Unbekannter Stack-Schlüssel: {key}") from exc


def ensure_runtime_dirs() -> None:
    for relative in ("reports", "logs", "audit", "worktrees", "tickets/ready"):
        (root() / relative).mkdir(parents=True, exist_ok=True)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def credential_file() -> Path | None:
    override = os.environ.get("FACTORY_ENV")
    if override:
        path = Path(override)
        return path if path.is_file() else None
    configured = factory_config().get("harness", {}).get("runner_env")
    if configured:
        path = Path(str(configured))
        if path.is_file():
            return path
    return None


def _setting(file_values: dict[str, str], key: str) -> str:
    if key in os.environ and os.environ[key] != "":
        return os.environ[key]
    return file_values.get(key, "")


def as_bool(value: str, default: bool = True) -> bool:
    if value.strip() == "":
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Credentials:
    base_url: str
    user: str
    secret: str
    source: str
    tls_verify: bool = True

    def __repr__(self) -> str:
        return (
            f"Credentials(user={self.user!r}, base_url={self.base_url!r}, "
            f"source={self.source!r}, secret='***')"
        )

    def label(self) -> str:
        return f"{self.user} @ {self.base_url} ({self.source})"


def load_credentials() -> Credentials | None:
    file_values: dict[str, str] = {}
    path = credential_file()
    if path is not None:
        file_values = parse_env_file(path)
    base = _setting(file_values, "NC_BASE").rstrip("/")
    user = _setting(file_values, "NC_USER")
    password = _setting(file_values, "NC_APP_PASSWORD")
    token = _setting(file_values, "NC_OAUTH_ACCESS_TOKEN") or _setting(file_values, "NC_TOKEN")
    source = _setting(file_values, "FACTORY_TOKEN_SOURCE")
    if not source:
        source = "oauth" if token and not password else "app_password"
    secret = token if source == "oauth" else password
    if not base or not user or not secret:
        return None
    tls_verify = as_bool(_setting(file_values, "NC_TLS_VERIFY"), True)
    return Credentials(
        base_url=base,
        user=user,
        secret=secret,
        source=source,
        tls_verify=tls_verify,
    )


def role_record(role: str) -> dict[str, Any]:
    for record in roles_config().get("accounts", {}).values():
        if record.get("role") == role:
            return record
    raise FactoryError(f"Rolle fehlt in roles.yaml: {role}")


def actor_name(role: str) -> str:
    return str(role_record(role).get("label") or role)


def _pairs(items: list[dict[str, Any]] | None) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for item in items or []:
        pairs.add((str(item["from"]).strip(), str(item["to"]).strip()))
    return pairs


def policy_for(role: str) -> dict[str, Any]:
    policies = roles_config().get("policies", {})
    if role not in policies:
        raise PolicyError(f"Unbekannte Rolle: {role}")
    return policies[role]


def check_transition(role: str, source: str, target: str) -> None:
    policy = policy_for(role)
    pair = (source.strip(), target.strip())
    if pair in _pairs(policy.get("forbidden_transitions")):
        raise PolicyError(f"{role} darf „{pair[0]}“ → „{pair[1]}“ nicht ausführen")
    if pair not in _pairs(policy.get("allowed_transitions")):
        raise PolicyError(f"{role} darf „{pair[0]}“ → „{pair[1]}“ nicht ausführen")


def check_named_approver(role: str, approver: str | None) -> str:
    policy = policy_for(role)
    name = (approver or "").strip()
    if policy.get("approve_requires_human_name") and not name:
        raise PolicyError(
            "Freigabe braucht einen namentlichen Approver: /approve <ticket> approver=<name>"
        )
    if not name:
        raise PolicyError("Freigabe braucht einen namentlichen Approver")
    return name


def assert_no_secrets(value: Any, where: str = "audit") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                raise FactoryError(f"{where}: Feld „{key}“ ist nicht erlaubt")
            assert_no_secrets(item, where)
        return
    if isinstance(value, list):
        for item in value:
            assert_no_secrets(item, where)
        return
    if isinstance(value, str) and SECRET_VALUE_RE.search(value):
        raise FactoryError(f"{where}: Wert sieht nach Zugangsdaten aus")


def audit_path() -> Path:
    configured = factory_config().get("paths", {}).get("audit", "audit/audit.jsonl")
    path = Path(str(configured))
    if not path.is_absolute():
        path = root() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_audit(event: dict[str, Any]) -> Path:
    payload = dict(event)
    payload.setdefault("timestamp", utc_now())
    assert_no_secrets(payload)
    path = audit_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def resolve_project(repo_name: str) -> dict[str, Any]:
    projects = projects_config().get("projects", {})
    if repo_name not in projects:
        raise FactoryError(f"Projekt fehlt in projects.yaml: {repo_name}")
    project = dict(projects[repo_name])
    configured = Path(str(project["repo"]))
    location = "configured"
    chosen = configured
    if not configured.exists() and project.get("local_repo"):
        local = Path(str(project["local_repo"]))
        if not local.is_absolute():
            local = root() / local
        if local.exists():
            chosen = local.resolve()
            location = "local_repo"
    elif not configured.exists():
        location = "missing"
    project["resolved_repo"] = str(chosen)
    project["repo_location"] = location
    return project


def assert_check_command_safe(command: str) -> None:
    if UNSAFE_CHECK_RE.search(command):
        raise PolicyError(f"Check-Befehl ist nicht erlaubt: {command}")


def safe_checks(commands: list[Any]) -> list[str]:
    safe: list[str] = []
    for command in commands:
        text = str(command)
        assert_check_command_safe(text)
        safe.append(text)
    return safe
