#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Aquisição PJe estritamente local: importação manual de autos que o advogado já tem.'

















from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

import pje_aquisicao_contract as contract


AUTH_SCHEMA_VERSION = "dsr.pje.aquisicao.autorizacao.v1"
MANIFEST_NAME = "manifest.json"
ADAPTER_MANUAL = "manual-local"
SUPPORTED_EXTENSIONS = frozenset({
    ".csv", ".doc", ".docx", ".htm", ".html", ".jpeg", ".jpg", ".odt",
    ".pdf", ".png", ".rtf", ".tif", ".tiff", ".txt", ".xls", ".xlsx", ".xml",
})
CLOUD_SEGMENTS = frozenset({
    "box", "dropbox", "google drive", "googledrive", "icloud", "onedrive",
    "pcloud", "sharepoint", "syncthing",
})
AUTH_KEYS = frozenset({
    "schema_version", "processo_cnj", "authorized_by_lawyer", "adapter", "expires_at",
})




EXPIRES_AT_RE = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2}[Tt ](?:[01][0-9]|2[0-3]):[0-9]{2})"
    r"(?::([0-9]{2})(?:\.([0-9]+))?)?(Z|[+-][0-9]{2}:[0-9]{2})"
)


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _iso_now() -> str:
    return _utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_json_loads(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"constante JSON inválida: {value}")

    return json.loads(text, parse_constant=reject_constant)


def _write_json_atomic(path: str, value: Mapping[str, Any]) -> None:
    target = os.path.realpath(os.path.abspath(path))
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pje-manifest-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        _fsync_directory(parent)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _fsync_directory(path: str) -> None:
    """Melhor esforço: o Windows não permite abrir diretório como descritor comum."""
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _is_inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(root)]) == os.path.realpath(root)
    except ValueError:
        return False


def _is_git_path(path: str) -> bool:
    current = os.path.realpath(os.path.abspath(path))
    if not os.path.isdir(current):
        current = os.path.dirname(current)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def _path_parts(path: str) -> list[str]:
    return [part.casefold() for part in Path(path).parts if part not in {os.sep, ""}]


def _has_cloud_segment(path: str) -> bool:
    for part in _path_parts(os.path.abspath(path)):
        normalized = "".join(ch for ch in part if ch.isalnum())
        if normalized == "box" or normalized.startswith(("boxsync", "boxdrive")):
            return True
        if any(normalized.startswith(marker.replace(" ", ""))
               for marker in CLOUD_SEGMENTS if marker != "box"):
            return True
    return False


def _relative_path(path: str) -> str | None:
    if not isinstance(path, str) or not path.strip() or os.path.isabs(path):
        return None
    normalized = path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _confined_path(root: str, relative: str) -> str | None:
    safe = _relative_path(relative)
    if safe is None:
        return None
    candidate = os.path.realpath(os.path.join(root, *safe.split("/")))
    if not _is_inside(candidate, root) or candidate == os.path.realpath(root):
        return None
    return candidate


def _regular_non_symlink(path: str) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)


def _path_has_symlink_segment(path: str) -> bool:
    candidate = os.path.abspath(path)
    drive, tail = os.path.splitdrive(candidate)
    current = drive + os.sep if drive else os.sep
    for part in Path(tail).parts:
        if part in {os.sep, ""}:
            continue
        current = os.path.join(current, part)
        if os.path.lexists(current) and os.path.islink(current):
            return True
    return False


def _directory_has_symlink(path: str) -> bool:
    for current, directories, files in os.walk(path, topdown=True, followlinks=False):
        for name in directories + files:
            candidate = os.path.join(current, name)
            try:
                if stat.S_ISLNK(os.lstat(candidate).st_mode):
                    return True
            except OSError:
                return True
    return False


def _load_object(value: Any) -> tuple[Mapping[str, Any] | None, str | None, list[str]]:
    if isinstance(value, Mapping):
        return dict(value), None, []
    if not isinstance(value, (str, os.PathLike)):
        return None, None, ["autorização local ausente"]
    path = os.path.realpath(os.path.abspath(os.fspath(value)))
    if _is_git_path(path):
        return None, path, ["arquivo de autorização dentro de repositório Git"]
    if not _regular_non_symlink(path):
        return None, path, ["autorização local ausente"]
    try:
        with open(path, "r", encoding="utf-8") as stream:
            payload = _safe_json_loads(stream.read())
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None, path, ["autorização local ilegível"]
    if not isinstance(payload, Mapping):
        return None, path, ["autorização local deve ser objeto JSON"]
    return dict(payload), path, []


def _parse_expiration(value: Any) -> _dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    forma = EXPIRES_AT_RE.fullmatch(value.strip())
    if forma is None:
        return None
    hora, segundos, fracao, fuso = forma.groups()

    candidate = (hora + (":" + segundos if segundos else "")
                 + ("." + (fracao + "00000")[:6] if fracao else "")
                 + ("+00:00" if fuso == "Z" else fuso))
    try:
        result = _dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if result.tzinfo is None or result.utcoffset() is None:
        return None
    return result.astimezone(_dt.timezone.utc)


def _cnj_equal(left: Any, right: Any) -> bool:
    try:
        import numero_cnj

        return bool(numero_cnj.validar(left) and numero_cnj.validar(right)
                    and numero_cnj.normalizar(left) == numero_cnj.normalizar(right))
    except (ImportError, AttributeError, TypeError, ValueError):
        return False


def validar_autorizacao(
    autorizacao: Any,
    *,
    processo_cnj: str | None = None,
    adapter: str | None = None,
    agora: _dt.datetime | None = None,
) -> list[str]:
    """Erros da autorização local (lista vazia = válida), sem expor o conteúdo dela."""
    payload, path, errors = _load_object(autorizacao)
    if errors:
        return errors
    assert payload is not None
    unknown = sorted(set(map(str, payload)) - AUTH_KEYS)
    if unknown:
        errors.append("campos de autorização não permitidos")
    if payload.get("schema_version") != AUTH_SCHEMA_VERSION:
        errors.append("schema de autorização inválido")
    if payload.get("authorized_by_lawyer") is not True:
        errors.append("autorização expressa do advogado ausente")
    if not contract._validar_cnj(payload.get("processo_cnj")):
        errors.append("processo_cnj da autorização inválido")
    if processo_cnj is not None and not _cnj_equal(payload.get("processo_cnj"), processo_cnj):
        errors.append("processo_cnj da autorização não corresponde à aquisição")
    auth_adapter = payload.get("adapter")
    if auth_adapter != ADAPTER_MANUAL:
        errors.append("adapter da autorização inválido")
    if adapter is not None and auth_adapter != adapter:
        errors.append("adapter da autorização não corresponde à aquisição")
    expires = _parse_expiration(payload.get("expires_at"))
    if expires is None:
        errors.append("expires_at deve ser ISO 8601 com fuso horário")
    else:
        reference = agora or _utc_now()
        if not isinstance(reference, _dt.datetime):
            errors.append("agora deve ser datetime com fuso horário")
        elif reference.tzinfo is None or reference.utcoffset() is None:
            errors.append("agora deve ter fuso horário")
        elif expires <= reference.astimezone(_dt.timezone.utc):
            errors.append("autorização vencida")
    if path is not None and _is_git_path(path):
        errors.append("arquivo de autorização dentro de repositório Git")
    return errors


def _inconclusive(
    processo_cnj: str,
    *,
    expected_documents: int | None = None,
) -> dict[str, Any]:
    expected = expected_documents if isinstance(expected_documents, int) and expected_documents >= 0 else None
    processo_text = processo_cnj if isinstance(processo_cnj, str) else ""
    return {
        "schema_version": contract.SCHEMA_VERSION,
        "processo_cnj": processo_text,
        "status": "inconclusive",
        "local_execution": True,
        "authorized_by_lawyer": False,
        "retention": "local",
        "adapter": ADAPTER_MANUAL,
        "source": "local",
        "expected_documents": expected,
        "acquired_documents": 0,
        "documents": [],
        "timeline": [{"type": "acquisition_inconclusive", "status": "inconclusive", "at": _iso_now()}],
        "confidential_content": True,
    }


def _doc_id(relative: str) -> str:
    return "doc-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]


def _manifest_path(destination: str) -> str:
    return os.path.join(destination, MANIFEST_NAME)


def _read_previous(
    destination: str,
    processo_cnj: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, bool]:
    path = _manifest_path(destination)
    if not os.path.isfile(path) or os.path.islink(path):
        return None, None, True
    try:
        raw = Path(path).read_bytes()
        payload = _safe_json_loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None, None, False
    if not isinstance(payload, dict) or contract.validar_manifest(payload):
        return None, hashlib.sha256(raw).hexdigest(), False
    if processo_cnj is not None and not _cnj_equal(payload.get("processo_cnj"), processo_cnj):
        return payload, hashlib.sha256(raw).hexdigest(), False
    return payload, hashlib.sha256(raw).hexdigest(), True


def _existing_documents(destination: str, previous: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not previous:
        return result
    for item in previous.get("documents", []):
        if not isinstance(item, Mapping):
            continue
        relative = _relative_path(item.get("path"))
        if relative is None:
            continue
        candidate = _confined_path(destination, relative)
        if candidate is None or not _regular_non_symlink(candidate):
            continue
        try:
            size = os.path.getsize(candidate)
            digest = _sha256_file(candidate)
        except OSError:
            continue
        if digest != item.get("sha256") or size != item.get("bytes"):
            continue
        preserved = dict(item)
        preserved["path"] = relative
        preserved["bytes"] = size
        preserved["sha256"] = digest
        result[relative] = preserved
    return result


def _manifest_document(destination: str, relative: str, acquired_at: str | None = None) -> dict[str, Any]:
    path = _confined_path(destination, relative)
    if path is None or not _regular_non_symlink(path):
        raise ValueError("documento fora do destino")
    return {
        "id": _doc_id(relative),
        "name": os.path.basename(relative),
        "path": relative,
        "sha256": _sha256_file(path),
        "bytes": os.path.getsize(path),
        "acquired_at": acquired_at or _iso_now(),
    }


def _source_files(source: str) -> list[tuple[str, str]]:
    source = os.path.realpath(os.path.abspath(source))
    if not os.path.isdir(source) or os.path.islink(source) or _directory_has_symlink(source):
        raise ValueError("origem deve conter somente arquivos regulares sem symlink")
    files: list[tuple[str, str]] = []
    for current, _directories, names in os.walk(source, topdown=True, followlinks=False):
        for name in sorted(names):
            candidate = os.path.join(current, name)
            if not _regular_non_symlink(candidate):
                raise ValueError("origem contém arquivo não regular")
            relative = os.path.relpath(candidate, source).replace(os.sep, "/")
            if os.path.basename(relative).casefold() == MANIFEST_NAME.casefold():
                continue
            if contract._valor_credencial(relative):
                raise ValueError("nome de arquivo contém material de credencial")
            if os.path.splitext(name)[1].casefold() in SUPPORTED_EXTENSIONS:
                files.append((relative, candidate))
    return files


def _promote_staged_file(
    staged: str,
    destination: str,
    relative: str,
    rollback_root: str,
) -> tuple[str, str | None]:
    target = _confined_path(destination, relative)
    if target is None:
        raise ValueError("caminho de documento fora do destino")
    if os.path.lexists(target) and not _regular_non_symlink(target):
        raise ValueError("destino existente não é arquivo regular")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    backup: str | None = None
    if os.path.exists(target):
        backup = _confined_path(rollback_root, relative)
        if backup is None:
            raise ValueError("rollback fora do staging")
        os.makedirs(os.path.dirname(backup), exist_ok=True)
        os.replace(target, backup)
    try:
        os.replace(staged, target)
        _fsync_directory(os.path.dirname(target))
    except Exception:
        if backup and os.path.exists(backup):
            os.replace(backup, target)
        raise
    return target, backup


def _rollback_promotions(promotions: list[tuple[str, str | None]]) -> None:
    for target, backup in reversed(promotions):
        try:
            if backup and os.path.exists(backup):
                os.replace(backup, target)
            elif os.path.isfile(target) and not os.path.islink(target):
                os.unlink(target)
        except OSError:
            pass


def _build_manifest(
    processo_cnj: str,
    *,
    adapter: str,
    authorized: bool,
    expected_documents: int | None,
    documents: list[dict[str, Any]],
    previous_hash: str | None,
) -> dict[str, Any]:
    acquired = len(documents)
    complete = (
        authorized
        and adapter in contract.LOCAL_ADAPTERS
        and isinstance(expected_documents, int)
        and expected_documents > 0
        and acquired == expected_documents
        and bool(documents)
    )
    manifest: dict[str, Any] = {
        "schema_version": contract.SCHEMA_VERSION,
        "processo_cnj": processo_cnj,
        "status": "complete" if complete else "partial",
        "local_execution": True,
        "authorized_by_lawyer": authorized,
        "retention": "local",
        "adapter": adapter,
        "source": "local",
        "expected_documents": expected_documents,
        "acquired_documents": acquired,
        "documents": documents,
        "timeline": [{
            "type": "documents_acquired",
            "status": "complete" if complete else "partial",
            "at": _iso_now(),
            "count": acquired,
        }],
        "confidential_content": True,
    }
    if previous_hash:
        manifest["previous_manifest_sha256"] = previous_hash
    return manifest


def importar_manual(
    processo_cnj: str,
    origem: str | os.PathLike[str],
    destino: str | os.PathLike[str],
    *,
    autorizacao: Any = None,
    expected_documents: int | None = None,
    confidential_content: bool = True,
) -> dict[str, Any]:
    'Importa os arquivos locais suportados de `origem` para `destino` e publica o manifesto'

    result = _inconclusive(processo_cnj, expected_documents=expected_documents)
    if not contract._validar_cnj(processo_cnj):
        return result
    if not isinstance(origem, (str, os.PathLike)) or not isinstance(destino, (str, os.PathLike)):
        return result
    if confidential_content is not True:
        return result
    if not isinstance(autorizacao, (str, os.PathLike)):
        return result
    if expected_documents is not None and (
        isinstance(expected_documents, bool) or not isinstance(expected_documents, int) or expected_documents < 0
    ):
        return result
    destination_input = os.path.abspath(os.fspath(destino))
    if _path_has_symlink_segment(destination_input):
        return result
    destination = os.path.realpath(destination_input)
    if _has_cloud_segment(destination):
        return result
    auth_errors = validar_autorizacao(
        autorizacao, processo_cnj=processo_cnj, adapter=ADAPTER_MANUAL
    )
    if auth_errors:
        return result
    authorized = True
    source_input = os.path.abspath(os.fspath(origem))
    if os.path.islink(source_input):
        return result
    source = os.path.realpath(source_input)
    if _path_has_symlink_segment(source_input):
        return result
    if _is_inside(source, destination) or _is_inside(destination, source):
        return result
    try:
        previous, previous_hash, previous_ok = _read_previous(destination, processo_cnj)
        if not previous_ok:
            return result
        files = _source_files(source)
        os.makedirs(destination, exist_ok=True)
        staging = tempfile.mkdtemp(prefix=".pje-stage-", dir=os.path.dirname(destination))
        promotions: list[tuple[str, str | None]] = []
        try:
            documents_by_path = _existing_documents(destination, previous)
            for relative, source_file in files:
                digest = _sha256_file(source_file)
                size = os.path.getsize(source_file)
                existing = documents_by_path.get(relative)
                if existing and existing.get("sha256") == digest and existing.get("bytes") == size:
                    continue
                staged_file = _confined_path(staging, relative)
                if staged_file is None:
                    raise ValueError("arquivo de origem fora do staging")
                os.makedirs(os.path.dirname(staged_file), exist_ok=True)
                shutil.copyfile(source_file, staged_file)
                promotions.append(_promote_staged_file(
                    staged_file, destination, relative, os.path.join(staging, ".rollback")
                ))
                documents_by_path[relative] = _manifest_document(destination, relative)
            documents = [documents_by_path[key] for key in sorted(documents_by_path)]
            manifest = _build_manifest(
                processo_cnj,
                adapter=ADAPTER_MANUAL,
                authorized=authorized,
                expected_documents=expected_documents,
                documents=documents,
                previous_hash=previous_hash,
            )
            errors = contract.validar_manifest(manifest)
            if errors:
                _rollback_promotions(promotions)
                return result
            _write_json_atomic(_manifest_path(destination), manifest)
            return manifest
        except Exception:
            _rollback_promotions(promotions)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    except (OSError, ValueError, TypeError):
        return result


def _json_output(value: Mapping[str, Any], code: int = 0) -> int:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return code


def _load_request(value: str) -> Mapping[str, Any] | None:
    try:
        if value == "-":
            payload = _safe_json_loads(sys.stdin.read())
        else:
            path = os.path.realpath(os.path.abspath(value))
            if _is_git_path(path) or not _regular_non_symlink(path):
                return None
            payload = _safe_json_loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aquisição PJe estritamente local")
    sub = parser.add_subparsers(dest="command", required=True)
    manual = sub.add_parser("manual")
    manual.add_argument("--request", required=True, help="JSON fora do Git; use - para stdin")
    args = parser.parse_args(argv)
    request = _load_request(args.request)
    if request is None:
        return _json_output(_inconclusive(""), 1)
    allowed = {"processo_cnj", "origem", "destino", "autorizacao", "expected_documents"}
    if set(map(str, request)) - allowed:
        return _json_output(_inconclusive(str(request.get("processo_cnj") or "")), 1)
    value = importar_manual(
        request.get("processo_cnj"), request.get("origem"), request.get("destino"),
        autorizacao=request.get("autorizacao"),
        expected_documents=request.get("expected_documents"),
    )
    return _json_output(value, 0 if value.get("status") != "inconclusive" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
