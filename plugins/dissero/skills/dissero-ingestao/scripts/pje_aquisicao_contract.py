#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Contrato seguro para aquisições locais do PJe.'








from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Mapping


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


SCHEMA_VERSION = "dsr.pje.aquisicao.v1"
SCHEMA_NAME = "pje_aquisicao.schema.json"
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
try:
    import numero_cnj as _NUMERO_CNJ
except Exception:
    try:
        from . import numero_cnj as _NUMERO_CNJ
    except Exception:
        _NUMERO_CNJ = None
CNJ_VALIDATOR_SOURCE = "numero_cnj" if _NUMERO_CNJ is not None else "unavailable"
MOTIVOS_INCONCLUSIVOS = {
    "falha_transporte": "Aquisição interrompida por falha de transporte; confira os autos localmente.",
    "cobertura_parcial": "Aquisição parcial; ausência de peça não foi demonstrada.",
}


LOCAL_ADAPTERS = {"manual-local"}

_KEY_MARKERS = (
    "cookie",
    "token",
    "session",
    "sessao",
    "authorization",
    "autorizacao",
    "password",
    "senha",
    "secret",
    "segredo",
    "apikey",
    "chaveapi",
    "credential",
    "credencial",
    "bearer",
    "jsessionid",
    "chave",
)
_VALUE_MARKER = re.compile(
    r"(?:"
    r"(?:bearer|basic)\s+\S+|"
    r"(?:cookie|cookies|token|session(?:id)?|sess[aã]o|authorization|autorização|"
    r"password|senha|secret|segredo|api[_-]?key|chave[_-]?api|credencial)"
    r"\s*(?:[-:=]|\s)\s*[^\s,;]+|"
    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r")",
    re.IGNORECASE,
)
_CONFIDENTIAL_KEYS = {"confidentialcontent", "conteudoconfidencial", "conteudosigiloso"}
_SAFE_DOCUMENT_KEYS = ("id", "name", "sha256", "bytes", "acquired_at")
_TOP_LEVEL_KEYS = {
    "schema_version", "processo_cnj", "status", "local_execution",
    "authorized_by_lawyer", "retention", "adapter", "source", "documents",
    "timeline", "confidential_content", "expected_documents", "acquired_documents",
    "previous_manifest_sha256",
}
_DOCUMENT_KEYS = set(_SAFE_DOCUMENT_KEYS) | {"path", "confidential_content"}
_SAFE_TIMELINE_KEYS = {
    "id",
    "event_id",
    "type",
    "kind",
    "status",
    "at",
    "timestamp",
    "acquired_at",
    "document_id",
    "name",
    "bytes",
    "sha256",
    "count",
    "page",
    "pages",
}
_UNSAFE_VALUE_KEYS = {
    "path",
    "filepath",
    "file",
    "content",
    "confidential_content",
    "conteudo",
    "texto",
    "body",
    "html",
    "url",
    "details",
    "detalhes",
}


def _key_normalizada(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value)).casefold()
    return "".join(ch for ch in raw if not unicodedata.combining(ch) and ch.isalnum())


def _chave_credencial(value: Any) -> bool:
    normalized = _key_normalizada(value)


    if normalized in {"authorizedbylawyer", "autorizadopeloadvogado"}:
        return False
    if normalized in {"auth", "autenticacao", "autenticación"}:
        return True
    return any(marker in normalized for marker in _KEY_MARKERS)


def _valor_credencial(value: Any) -> bool:
    return isinstance(value, str) and bool(_VALUE_MARKER.search(value))


def _encontrar_credenciais(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _chave_credencial(key_text):
                found.append(f"{child_path}: chave de credencial não permitida")
            if _valor_credencial(child):
                found.append(f"{child_path}: marcador de credencial não permitido")
            found.extend(_encontrar_credenciais(child, child_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            if _valor_credencial(child):
                found.append(f"{child_path}: marcador de credencial não permitido")
            found.extend(_encontrar_credenciais(child, child_path))
    return found


def _confidential_true(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _key_normalizada(key) in _CONFIDENTIAL_KEYS and child is True:
                return True
            if _confidential_true(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_confidential_true(child) for child in value)
    return False


def _processo_cnj(manifest: Mapping[str, Any]) -> Any:
    return manifest.get("processo_cnj")


def _validar_cnj(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if _NUMERO_CNJ is None:
        return False
    try:
        return bool(_NUMERO_CNJ.validar(value))
    except (AttributeError, TypeError, ValueError):
        return False


def _validar_documento(doc: Any, index: int, errors: list[str]) -> None:
    prefix = f"documents[{index}]"
    if not isinstance(doc, Mapping):
        errors.append(f"{prefix} deve ser objeto")
        return
    desconhecidos = sorted(set(map(str, doc.keys())) - _DOCUMENT_KEYS)
    if desconhecidos:
        errors.append(f"{prefix}: campos não permitidos: {', '.join(desconhecidos)}")
    for field in _SAFE_DOCUMENT_KEYS:
        if field not in doc:
            errors.append(f"{prefix}.{field} obrigatório")
    for field in ("id", "name", "path", "acquired_at"):
        if field in doc and (not isinstance(doc[field], str) or not doc[field].strip()):
            errors.append(f"{prefix}.{field} deve ser texto não vazio")
    if "sha256" in doc and (
        not isinstance(doc["sha256"], str) or not _SHA256.fullmatch(doc["sha256"])
    ):
        errors.append(f"{prefix}.sha256 deve ter 64 hexadecimais")
    if "bytes" in doc and (
        isinstance(doc["bytes"], bool) or not isinstance(doc["bytes"], int) or doc["bytes"] < 0
    ):
        errors.append(f"{prefix}.bytes deve ser inteiro não negativo")
    if "confidential_content" in doc and not isinstance(doc["confidential_content"], bool):
        errors.append(f"{prefix}.confidential_content deve ser booleano")


def validar_manifest(manifest: Mapping[str, Any], *, require_schema: bool = True) -> list[str]:
    """Erros de validação determinísticos; lista vazia significa manifesto válido."""
    errors: list[str] = []
    if not isinstance(manifest, Mapping):
        return ["manifest deve ser objeto"]
    if require_schema and manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version deve ser {SCHEMA_VERSION}")
    desconhecidos = sorted(set(map(str, manifest.keys())) - _TOP_LEVEL_KEYS)
    if desconhecidos:
        errors.append("campos de topo não permitidos: " + ", ".join(desconhecidos))

    credentials = _encontrar_credenciais(manifest)
    errors.extend(credentials)
    if _NUMERO_CNJ is None:
        errors.append("validador CNJ canônico indisponível; fallback não é permitido")
    if not _validar_cnj(_processo_cnj(manifest)):
        errors.append("processo_cnj inválido ou ausente (dígito verificador CNJ)")

    status = manifest.get("status")
    if status not in {"complete", "partial", "inconclusive"}:
        errors.append("status deve ser complete, partial ou inconclusive")
    for field in ("local_execution", "authorized_by_lawyer"):
        if not isinstance(manifest.get(field), bool):
            errors.append(f"{field} deve ser booleano")
    if manifest.get("retention") not in {"zero", "local"}:
        errors.append("retention deve ser zero ou local")
    adapter = manifest.get("adapter") if isinstance(manifest.get("adapter"), str) else ""
    if not adapter:
        errors.append("adapter explícito é obrigatório")
    elif adapter not in LOCAL_ADAPTERS:
        errors.append("adapter deve ser manual-local")
    if "source" in manifest and not isinstance(manifest.get("source"), str):
        errors.append("source deve ser texto")
    if "confidential_content" in manifest and not isinstance(manifest.get("confidential_content"), bool):
        errors.append("confidential_content deve ser booleano")

    documents = manifest.get("documents")
    if not isinstance(documents, list):
        errors.append("documents deve ser lista")
    else:
        for index, doc in enumerate(documents):
            _validar_documento(doc, index, errors)
    expected = manifest.get("expected_documents")
    if expected is not None and (
        isinstance(expected, bool) or not isinstance(expected, int) or expected < 0
    ):
        errors.append("expected_documents deve ser inteiro não negativo ou nulo")
    acquired = manifest.get("acquired_documents")
    if isinstance(acquired, bool) or not isinstance(acquired, int) or acquired < 0:
        errors.append("acquired_documents deve ser inteiro não negativo")
    elif isinstance(documents, list) and acquired != len(documents):
        errors.append("acquired_documents deve ser igual ao número de documents")
    previous_hash = manifest.get("previous_manifest_sha256")
    if previous_hash is not None and (
        not isinstance(previous_hash, str) or not _SHA256.fullmatch(previous_hash)
    ):
        errors.append("previous_manifest_sha256 deve ter 64 hexadecimais")
    timeline = manifest.get("timeline")
    if not isinstance(timeline, list):
        errors.append("timeline deve ser lista")
    else:
        for index, event in enumerate(timeline):
            if not isinstance(event, Mapping):
                errors.append("timeline deve conter somente eventos objeto")
                continue
            permitidas = {_key_normalizada(k) for k in _SAFE_TIMELINE_KEYS}
            extras = sorted(str(k) for k in event if _key_normalizada(k) not in permitidas)
            if extras:
                errors.append(f"timeline[{index}]: campos não permitidos: {', '.join(extras)}")
            if any(isinstance(v, (Mapping, list, tuple)) for v in event.values()):
                errors.append(f"timeline[{index}]: somente metadados escalares são permitidos")



    if status == "complete" and manifest.get("authorized_by_lawyer") is not True:
        errors.append("status complete exige authorized_by_lawyer=true")
    if status == "complete":
        if manifest.get("local_execution") is not True:
            errors.append("status complete exige local_execution=true")
        if adapter not in LOCAL_ADAPTERS:
            errors.append("status complete exige adapter local permitido")
        if not isinstance(expected, int) or isinstance(expected, bool) or expected <= 0:
            errors.append("status complete exige expected_documents inteiro maior que zero")
        if isinstance(acquired, int) and not isinstance(acquired, bool) and (
            not isinstance(expected, int) or acquired != expected
        ):
            errors.append("status complete exige acquired_documents igual a expected_documents")
        if not isinstance(documents, list) or not documents:
            errors.append("status complete exige documents não vazio")



    external = manifest.get("local_execution") is False or adapter not in LOCAL_ADAPTERS
    if external and _confidential_true(manifest):
        errors.append("manifesto de adaptador externo não pode conter confidential_content=true")
    if external and manifest.get("retention") != "zero":
        errors.append("adaptador externo exige retention=zero")
    return errors


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def _safe_timeline_event(event: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in event.items():
        key_text = str(key)
        normalized = _key_normalizada(key_text)
        if normalized in {_key_normalizada(k) for k in _UNSAFE_VALUE_KEYS}:
            continue
        if normalized in {_key_normalizada(k) for k in _SAFE_TIMELINE_KEYS}:
            scalar = _safe_scalar(value)
            if (scalar is not None or value is None) and not _valor_credencial(value):
                safe[key_text] = scalar
    return safe


def sanitize_for_ledger(manifest: Mapping[str, Any]) -> dict[str, Any]:
    'Metadados seguros para o ledger do caso, sem caminho nem credencial.'





    if not isinstance(manifest, Mapping):
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "inconclusive",
            "completude": False,
            "documents": [],
            "timeline": [],
        }
    errors = validar_manifest(manifest)
    status = manifest.get("status") if manifest.get("status") in {
        "complete", "partial", "inconclusive"
    } else "inconclusive"
    if errors or status != "complete" or manifest.get("authorized_by_lawyer") is not True:
        status = "inconclusive" if errors or status == "complete" else status
    if status in {"partial", "inconclusive"}:
        complete_claim = False
    else:
        complete_claim = True

    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "completude": complete_claim,
        "local_execution": bool(manifest.get("local_execution")) if isinstance(
            manifest.get("local_execution"), bool
        ) else False,
        "authorized_by_lawyer": bool(manifest.get("authorized_by_lawyer")) if isinstance(
            manifest.get("authorized_by_lawyer"), bool
        ) else False,
        "retention": manifest.get("retention") if manifest.get("retention") in {"zero", "local"} else "zero",
        "validator_source": CNJ_VALIDATOR_SOURCE,
        "documents": [],
        "timeline": [],
    }
    expected = manifest.get("expected_documents")
    if expected is None or (isinstance(expected, int) and not isinstance(expected, bool) and expected >= 0):
        out["expected_documents"] = expected
    acquired = manifest.get("acquired_documents")
    if isinstance(acquired, int) and not isinstance(acquired, bool) and acquired >= 0:
        out["acquired_documents"] = acquired
    previous_hash = manifest.get("previous_manifest_sha256")
    if isinstance(previous_hash, str) and _SHA256.fullmatch(previous_hash):
        out["previous_manifest_sha256"] = previous_hash
    process = _processo_cnj(manifest)
    if isinstance(process, str) and _validar_cnj(process):
        out["processo_cnj"] = process
    for doc in manifest.get("documents") or []:
        if not isinstance(doc, Mapping):
            continue
        safe_doc = {
            key: _safe_scalar(doc.get(key))
            for key in _SAFE_DOCUMENT_KEYS
            if key in doc and not _valor_credencial(doc.get(key))
        }


        if isinstance(safe_doc.get("sha256"), str) and not _SHA256.fullmatch(safe_doc["sha256"]):
            safe_doc.pop("sha256", None)
        out["documents"].append(safe_doc)
    for event in manifest.get("timeline") or []:
        if isinstance(event, Mapping):
            safe_event = _safe_timeline_event(event)
            if safe_event:
                out["timeline"].append(safe_event)
    if errors:
        out["warning"] = "Aquisição não validada; o registro é inconclusivo e exige conferência local."
    return out


def marcar_inconclusivo(manifest: Mapping[str, Any], motivo: str | None = None) -> dict[str, Any]:
    out = sanitize_for_ledger(manifest)
    out["status"] = "inconclusive"
    out["completude"] = False
    out["warning"] = MOTIVOS_INCONCLUSIVOS.get(
        str(motivo or ""),
        "Aquisição inconclusiva; ausência de documentos não foi demonstrada.",
    )
    return out


def _json_input(value: str | None) -> Any:
    if value is None:
        raise ValueError("entrada JSON obrigatória")
    candidate = Path(value)



    if os.path.isfile(candidate):
        return json.loads(candidate.read_text(encoding="utf-8"))
    return json.loads(value)


def _output(value: Any, code: int = 0) -> int:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contrato offline de aquisição PJe")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "sanitize", "inconclusive"):
        cmd = sub.add_parser(name)
        cmd.add_argument("input", nargs="?")
        cmd.add_argument("--input", dest="input_opt")

    args = parser.parse_args(argv)
    try:
        payload = _json_input(args.input_opt or args.input)
        if args.command == "validate":
            errors = validar_manifest(payload)
            return _output({"ok": not errors, "errors": errors}, 0 if not errors else 1)
        if args.command == "sanitize":
            return _output(sanitize_for_ledger(payload))
        if args.command == "inconclusive":
            return _output(marcar_inconclusivo(payload))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _output({"ok": False, "erro": str(exc)}, 2)
    return 2


if __name__ == "__main__":
    sys.exit(main())
