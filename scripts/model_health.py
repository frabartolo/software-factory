#!/usr/bin/env python3
"""Prüft die OpenAI-kompatiblen Endpunkte von kiara, flaps und hathi."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory_common import FactoryError, factory_config


def message_text(message: dict[str, Any]) -> tuple[str, str]:
    """Liest die Antwort. flaps legt sie manchmal nur in reasoning_content ab."""
    content = message.get("content")
    reasoning = message.get("reasoning_content")
    if isinstance(content, str) and content.strip():
        return content.strip(), "content"
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip(), "reasoning_content"
    return "", "leer"


def _is_local(url: str) -> bool:
    return "127.0.0.1" in url or "localhost" in url


def ordered(urls: list[str]) -> list[str]:
    host = socket.gethostname().split(".")[0].lower()
    local = [url for url in urls if _is_local(url)]
    remote = [url for url in urls if not _is_local(url)]
    if host == "kiara":
        return local + remote
    return remote + local


def endpoint_urls(route: dict[str, Any]) -> list[str]:
    health = route.get("health") or {}
    if health.get("endpoints"):
        return [str(url) for url in health["endpoints"]]
    if health.get("endpoint"):
        return [str(health["endpoint"])]
    return []


def get_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "Accept-Encoding": "identity"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:180]
        raise FactoryError(f"HTTP {exc.code} von {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FactoryError(f"{url} nicht erreichbar: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise FactoryError(f"{url} hat nicht rechtzeitig geantwortet") from exc


def model_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = payload.get("data") if isinstance(payload, dict) else None
    for item in data or []:
        if not isinstance(item, dict):
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        status = item.get("status") if isinstance(item.get("status"), dict) else {}
        rows.append(
            {
                "id": item.get("id"),
                "n_ctx": meta.get("n_ctx"),
                "status": status.get("value"),
            }
        )
    if rows:
        return rows
    for item in (payload.get("models") if isinstance(payload, dict) else None) or []:
        if isinstance(item, dict):
            rows.append({"id": item.get("name") or item.get("model"), "n_ctx": None, "status": None})
    return rows


def check_route(name: str, route: dict[str, Any]) -> tuple[bool, str]:
    errors: list[str] = []
    for url in ordered(endpoint_urls(route)):
        try:
            payload = get_json(url, timeout=5)
        except FactoryError as exc:
            errors.append(str(exc))
            continue
        rows = model_rows(payload)
        if not rows:
            errors.append(f"{url} lieferte keine Modelle")
            continue
        details = []
        for row in rows:
            bits = [str(row.get("id") or "?")]
            if row.get("n_ctx"):
                bits.append(f"n_ctx={row['n_ctx']}")
            if row.get("status"):
                bits.append(str(row["status"]))
            details.append(" ".join(bits))
        base = url.removesuffix("/models")
        return True, f"{name}: erreichbar {base} — " + ", ".join(details)
    required = bool((route.get("health") or {}).get("required"))
    detail = "; ".join(errors) if errors else "kein Endpunkt konfiguriert"
    return (not required), f"{name}: nicht erreichbar ({detail})"


def ping(base: str, model: str, max_tokens: int) -> str:
    url = base.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "Antworte nur mit dem Wort OK."}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:180]
        raise FactoryError(f"HTTP {exc.code} von {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FactoryError(f"{url} nicht erreichbar: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise FactoryError(
            f"{url} hat in 90 Sekunden nicht geantwortet. "
            "llama.cpp hat oft nur einen Slot; eine laufende Chat-Antwort blockiert weitere Anfragen."
        ) from exc
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices:
        raise FactoryError(f"{url} lieferte keine choices")
    message = choices[0].get("message") or {}
    text, field = message_text(message)
    snippet = text.replace("\n", " ")[:80]
    return f"Antwortfeld {field}: {snippet or '(leer)'}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Modell-Endpunkte von kiara, flaps und hathi prüfen")
    parser.add_argument(
        "--ping",
        action="store_true",
        help="einen kurzen Satz an den erreichbaren Worker schicken",
    )
    parser.add_argument("--max-tokens", type=int, default=16)
    args = parser.parse_args(argv)
    config = factory_config()
    routing = config.get("routing") or {}
    if "kiara" not in routing:
        print("routing.kiara fehlt in factory.yaml", file=sys.stderr)
        return 2

    ok = True
    reached: dict[str, str] = {}
    order = [name for name in ("kiara", "flaps", "hathi") if name in routing]
    order.extend(name for name in routing if name not in order)
    for name in order:
        route = routing.get(name)
        if not route:
            continue
        healthy, line = check_route(name, route)
        print(line)
        if not healthy:
            ok = False
        elif line.startswith(f"{name}: erreichbar"):
            base = line.split(" erreichbar ", 1)[1].split(" — ", 1)[0].strip()
            reached[name] = base

    if args.ping and reached:
        models = config.get("models") or {}
        target = next(name for name in ("kiara", "flaps", "hathi") if name in reached)
        model_key = {"kiara": "worker_model", "flaps": "flaps_model", "hathi": "hathi_model"}[target]
        model = models.get(model_key)
        try:
            print(f"{target} ping: " + ping(reached[target], str(model), args.max_tokens))
        except FactoryError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
