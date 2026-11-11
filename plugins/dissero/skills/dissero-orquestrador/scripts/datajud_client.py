#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Cliente local, somente leitura, da API Pública DataJud.'









from __future__ import annotations

import argparse
import copy
import http.client
import json
import math
import os
import re
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import credenciais
import datajud_contract


SCHEMA_VERSION = "dsr.datajud.consulta.v1"
HOST = "api-publica.datajud.cnj.jus.br"
BASE_URL = f"https://{HOST}"
_PATH = re.compile(r"^/api_publica_[a-z0-9]+/_search$")
_MAX_BODY = 131_072
_MAX_RESPONSE = 16 * 1024 * 1024
_FORBIDDEN_DSL_KEYS = {
    "aggs", "aggregations", "collapse", "highlight", "pit", "runtime_mappings",
    "script", "script_fields", "script_score", "stored_fields", "suggest",
}
_TOP_LEVEL_INPUT = {"query", "_source"}


class DataJudError(RuntimeError):
    """Erro operacional sanitizado; nunca contém header ou credencial."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RespostaHTTP:
    status: int
    body: bytes
    headers: Mapping[str, str]


Transport = Callable[[str, Mapping[str, str], bytes, float, int], RespostaHTTP]


def _agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def endpoint_datajud(tribunal: Any) -> str:
    indice = datajud_contract.indice_do_tribunal(tribunal)
    url = f"{BASE_URL}/{indice}/_search"
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != HOST
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not _PATH.fullmatch(parsed.path)
    ):
        raise DataJudError("endpoint_invalido", "Endpoint DataJud recusado pela allowlist local.")
    return url


def resolver_api_key() -> str:
    credenciais.carregar()
    chave = (os.environ.get("DATAJUD_API_KEY") or "").strip()
    if not chave:

        chave = (datajud_contract.DATAJUD_API_KEY_PUBLICA or "").strip()
    if not chave:
        raise DataJudError(
            "chave_ausente",
            "DATAJUD_API_KEY ausente e chave publica embutida vazia; defina-a no dsr_credenciais.env.",
        )
    if len(chave) > 8192 or any(char.isspace() for char in chave):
        raise DataJudError("chave_invalida", "DATAJUD_API_KEY tem formato local inválido.")
    return chave


def _http_post(
    url: str,
    headers: Mapping[str, str],
    payload: bytes,
    timeout: float,
    max_response_bytes: int,
) -> RespostaHTTP:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != HOST
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not _PATH.fullmatch(parsed.path)
    ):
        raise DataJudError("endpoint_invalido", "Endpoint DataJud recusado pela allowlist local.")
    connection = http.client.HTTPSConnection(
        HOST,
        443,
        timeout=timeout,
        context=ssl.create_default_context(),
    )
    try:
        connection.request("POST", parsed.path, body=payload, headers=dict(headers))
        response = connection.getresponse()
        content_length = response.getheader("Content-Length")
        if content_length:
            try:
                if int(content_length) > max_response_bytes:
                    raise DataJudError("resposta_grande", "Resposta DataJud excede o teto local.")
            except ValueError:
                pass
        body = response.read(max_response_bytes + 1)
        if len(body) > max_response_bytes:
            raise DataJudError("resposta_grande", "Resposta DataJud excede o teto local.")
        response_headers = {key.casefold(): value for key, value in response.getheaders()}
        return RespostaHTTP(response.status, body, response_headers)
    except DataJudError:
        raise
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        raise DataJudError("falha_transporte", "Falha de transporte na API Pública DataJud.") from exc
    finally:
        connection.close()


def _reject_constant(value: str) -> None:
    raise ValueError(f"constante JSON inválida: {value}")


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DataJudError("resposta_invalida", "Resposta DataJud não é JSON válido.") from exc
    if not isinstance(value, dict):
        raise DataJudError("resposta_invalida", "Resposta DataJud deve ser um objeto JSON.")
    return value


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    achados: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text.casefold() in _FORBIDDEN_DSL_KEYS:
                achados.append(child_path)
            achados.extend(_walk_forbidden(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            achados.extend(_walk_forbidden(child, f"{path}[{index}]"))
    return achados




















_RAIZES_DE_PARTE = frozenset({
    "partes", "parte", "polo", "poloativo", "polopassivo",
    "nomeparte", "nomedaparte", "documentoparte",
    "nomeadvogado", "advogado", "advogados", "representantes", "cpf", "cnpj",
})

_CHAVES_COM_CAMPO = (
    "match", "match_phrase", "match_bool_prefix", "term", "terms", "terms_set",
    "prefix", "wildcard", "regexp", "fuzzy", "range",
)


def _raiz_de_campo(campo: Any) -> str:
    texto = str(campo or "").strip().lower()
    return texto.split(".", 1)[0] if texto else ""


def _campos_da_query(valor: Any) -> set[str]:
    """Nomes de campo citados na DSL, em qualquer profundidade."""
    achados: set[str] = set()
    if isinstance(valor, Mapping):
        for chave, filho in valor.items():
            nome = str(chave)
            if nome in _CHAVES_COM_CAMPO and isinstance(filho, Mapping):
                achados.update(str(k) for k in filho)
            elif nome == "exists" and isinstance(filho, Mapping):
                if filho.get("field"):
                    achados.add(str(filho["field"]))
            elif nome == "nested" and isinstance(filho, Mapping):
                if filho.get("path"):
                    achados.add(str(filho["path"]))
            elif nome in ("fields", "includes") and isinstance(filho, (list, tuple)):
                achados.update(str(x) for x in filho)
            elif nome == "_source":
                if isinstance(filho, str):
                    achados.add(filho)
                elif isinstance(filho, (list, tuple)):
                    achados.update(str(x) for x in filho)
            achados.update(_campos_da_query(filho))
    elif isinstance(valor, (list, tuple)):
        for filho in valor:
            achados.update(_campos_da_query(filho))
    return achados


def campos_de_parte(entrada: Any) -> list[str]:
    """Campos da consulta que tentam filtrar por PARTE. Lista vazia = nada a recusar."""
    return sorted({c for c in _campos_da_query(entrada)
                   if _raiz_de_campo(c) in _RAIZES_DE_PARTE})


def preparar_consulta(entrada: Any, *, page_size: int) -> dict[str, Any]:
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 10 <= page_size <= 10_000:
        raise DataJudError("consulta_invalida", "page_size deve ficar entre 10 e 10000.")
    if not isinstance(entrada, Mapping) or not entrada:
        raise DataJudError("consulta_invalida", "Consulta DataJud deve ser objeto JSON não vazio.")
    extras = sorted(set(map(str, entrada.keys())) - _TOP_LEVEL_INPUT)
    if extras:
        raise DataJudError(
            "consulta_invalida",
            "Campos de transporte/paginação são controlados pelo cliente local.",
        )
    if "query" not in entrada or not isinstance(entrada.get("query"), Mapping) or not entrada["query"]:
        raise DataJudError("consulta_invalida", "Campo query deve ser objeto DSL não vazio.")
    if _walk_forbidden(entrada):
        raise DataJudError("consulta_invalida", "Consulta contém recurso DSL não permitido.")
    de_parte = campos_de_parte(entrada)
    if de_parte:
        raise DataJudError(
            "consulta_invalida",
            "A API Pública do DataJud NÃO carrega dado de parte, e consultar assim devolve "
            "ZERO em silêncio (HTTP 200, total=0; o `_source` não tem campo de parte). Quem "
            "levanta carteira por nome recebe '0 processos' e conclui que o cliente não tem "
            "processo: falso negativo com cara de resposta. Campo(s) recusado(s): "
            + ", ".join(de_parte)
            + ". O caminho da carteira é o índice do escritório (o DataJud entra depois, "
            "ENRIQUECENDO por `numeroProcesso`) — ver a referência "
            "busca-por-parte-datajud.md da skill dissero-pesquisa-juridica.")
    try:
        normalizada = datajud_contract.normalizar_query(dict(entrada))
    except ValueError as exc:
        raise DataJudError("consulta_invalida", str(exc)) from exc
    body = dict(normalizada)
    body["size"] = page_size
    body["track_total_hits"] = True








    body["sort"] = [
        {"@timestamp": {"order": "asc"}},
        {"id.keyword": {"order": "asc"}},
    ]
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > _MAX_BODY:
        raise DataJudError("consulta_invalida", "Consulta DataJud excede o teto local.")
    return body


def _total_exato(response: Mapping[str, Any]) -> int | None:
    hits = response.get("hits")
    if not isinstance(hits, Mapping):
        return None
    total = hits.get("total")
    if isinstance(total, bool):
        return None
    if isinstance(total, int) and total >= 0:
        return total
    if isinstance(total, Mapping):
        value = total.get("value")
        relation = total.get("relation")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0 and relation == "eq":
            return value
    return None


def _hits(response: Mapping[str, Any]) -> list[Mapping[str, Any]] | None:
    hits = response.get("hits")
    if not isinstance(hits, Mapping) or not isinstance(hits.get("hits"), list):
        return None
    if not all(isinstance(item, Mapping) for item in hits["hits"]):
        return None
    return list(hits["hits"])


def _shards(response: Mapping[str, Any]) -> tuple[int | None, int | None, int]:
    shards = response.get("_shards")
    if not isinstance(shards, Mapping):
        return None, None, 0
    total = shards.get("total")
    successful = shards.get("successful")
    failed = shards.get("failed", 0)
    valores = (total, successful, failed)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in valores):
        return None, None, 0
    return total, successful, failed


def _timestamp_resposta(headers: Mapping[str, str]) -> str | None:
    value = headers.get("date")
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _retry_after(headers: Mapping[str, str]) -> float:
    raw = headers.get("retry-after", "").strip()
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return max(0.0, min(value, 5.0))


def consultar(
    tribunal: Any,
    entrada: Mapping[str, Any],
    *,
    page_size: int = 100,
    max_pages: int = 20,
    timeout: float = 30.0,
    max_response_bytes: int = _MAX_RESPONSE,
    transport: Transport = _http_post,
    sleep_fn: Callable[[float], None] = time.sleep,
    api_key: str | None = None,
) -> dict[str, Any]:
    tribunal_text = str(tribunal or "").strip().upper()
    indice = datajud_contract.indice_do_tribunal(tribunal_text)
    endpoint = endpoint_datajud(tribunal_text)
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 1000:
        raise DataJudError("consulta_invalida", "max_pages deve ficar entre 1 e 1000.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 120:
        raise DataJudError("consulta_invalida", "timeout deve ficar entre 1 e 120 segundos.")
    if (
        isinstance(max_response_bytes, bool)
        or not isinstance(max_response_bytes, int)
        or not 1024 <= max_response_bytes <= 64 * 1024 * 1024
    ):
        raise DataJudError("consulta_invalida", "Teto de resposta local inválido.")
    body_base = preparar_consulta(entrada, page_size=page_size)
    chave = api_key if api_key is not None else resolver_api_key()
    if (
        not isinstance(chave, str)
        or not chave
        or len(chave) > 8192
        or any(char.isspace() for char in chave)
    ):
        raise DataJudError("chave_invalida", "DATAJUD_API_KEY tem formato local inválido.")
    headers = {
        "Authorization": f"ApiKey {chave}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "dissero-datajud/1",
    }

    records: list[dict[str, Any]] = []
    ids: set[str] = set()
    expected_total: int | None = None
    expected_pages: int | None = None
    pages_received = 0
    shard_total_per_page: int | None = None
    shards_received = 0
    failed_markers: list[str] = []
    timed_out = False
    cursor: list[Any] | None = None
    previous_cursor: list[Any] | None = None
    response_timestamp: str | None = None
    retry_used = False
    error_code: str | None = None

    for page_number in range(1, max_pages + 1):
        request_body = copy.deepcopy(body_base)
        if cursor is not None:
            request_body["search_after"] = cursor
        payload = json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        while True:
            try:
                response = transport(endpoint, headers, payload, float(timeout), max_response_bytes)
            except DataJudError as exc:
                error_code = exc.code
                break
            except Exception:
                error_code = "falha_transporte"
                break
            if response.status == 429 and not retry_used and datajud_contract.deve_repetir(429, "indeterminado", 0):
                retry_used = True
                espera = _retry_after(response.headers)
                if espera:
                    sleep_fn(espera)
                continue
            if response.status == 504:
                error_code = "http_504"
                break
            if 300 <= response.status < 400:
                error_code = "redirecionamento_recusado"
                break
            if response.status != 200:
                error_code = "http_429" if response.status == 429 else "http_erro"
                break

            try:
                parsed = _json_object(response.body)
            except DataJudError as exc:
                error_code = exc.code
                break
            page_timed_out = parsed.get("timed_out") is True
            total_shards, successful_shards, failed_shards = _shards(parsed)
            partial_200 = page_timed_out or failed_shards > 0
            if partial_200 and not retry_used and datajud_contract.deve_repetir(200, "parcial", 0):
                retry_used = True
                continue
            timed_out = timed_out or page_timed_out
            if total_shards is None or successful_shards is None:
                failed_markers.append(f"page-{page_number}-shards")
            else:
                if shard_total_per_page is None:
                    shard_total_per_page = total_shards
                elif shard_total_per_page != total_shards:
                    failed_markers.append(f"page-{page_number}-shard-count")
                shards_received += successful_shards
            if failed_shards:
                failed_markers.append(f"page-{page_number}-failed-{failed_shards}")

            timestamp_page = _timestamp_resposta(response.headers)
            if timestamp_page is None:
                failed_markers.append(f"page-{page_number}-date-header")
            else:
                response_timestamp = timestamp_page
            page_total = _total_exato(parsed)
            page_hits = _hits(parsed)
            if page_total is None or page_hits is None:
                error_code = "resposta_invalida"
                failed_markers.append(f"page-{page_number}-shape")
                break
            if expected_total is None:
                expected_total = page_total
                expected_pages = max(1, math.ceil(expected_total / page_size))
            elif expected_total != page_total:
                failed_markers.append(f"page-{page_number}-total-changed")

            pages_received += 1
            page_cursor: list[Any] | None = None
            for hit in page_hits:
                hit_id = hit.get("_id")
                hit_sort = hit.get("sort")
                if not isinstance(hit_id, str) or not hit_id:
                    failed_markers.append(f"page-{page_number}-id")
                    continue
                if not isinstance(hit_sort, list) or len(hit_sort) != 2:
                    failed_markers.append(f"page-{page_number}-sort")
                    continue
                if hit_id in ids:
                    failed_markers.append(f"page-{page_number}-duplicate")
                    continue
                ids.add(hit_id)
                page_cursor = list(hit_sort)
                records.append({
                    "_id": hit_id,
                    "_source": copy.deepcopy(hit.get("_source")) if isinstance(hit.get("_source"), Mapping) else {},
                    "sort": list(hit_sort),
                })

            if expected_total == 0 or not page_hits:
                cursor = None
            else:
                cursor = page_cursor
                if cursor is None or cursor == previous_cursor:
                    failed_markers.append(f"page-{page_number}-cursor")
                    cursor = None
                previous_cursor = list(cursor) if cursor is not None else previous_cursor
            if partial_200:
                error_code = "cobertura_parcial"
            break

        if error_code or failed_markers:
            break
        if expected_pages is not None and pages_received >= expected_pages:
            break
        if cursor is None:
            break

    if expected_total is not None and len(records) != expected_total:
        failed_markers.append("contagem-divergente")
    if expected_pages is not None and pages_received < expected_pages:
        failed_markers.append("paginas-incompletas")
    shards_expected = (
        shard_total_per_page * expected_pages
        if shard_total_per_page is not None and expected_pages is not None
        else None
    )
    coverage = datajud_contract.construir_cobertura(
        tribunal_text,
        indice,
        entrada,
        shards_expected,
        shards_received if shard_total_per_page is not None else None,
        expected_pages,
        pages_received if expected_pages is not None else None,
        timed_out,
        failed_markers,
        expected_total,
        response_timestamp or _agora_iso(),
    )
    if response_timestamp is None:
        coverage["warnings"].append(
            "Timestamp HTTP oficial ausente; o horário local não serve como prova de cobertura."
        )
    if retry_used:
        coverage["warnings"].append("Uma única repetição de transporte foi consumida.")
    if error_code:
        coverage["warnings"].append("Consulta interrompida; confira a fonte oficial diretamente.")
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": coverage["state"] == "completo" and error_code is None,
        "tribunal": tribunal_text,
        "indice": indice,
        "coverage": coverage,
        "records": records,
        "error_code": error_code,
    }


def _load_json(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin, parse_constant=_reject_constant)
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=_reject_constant)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cliente somente leitura da API Pública DataJud")
    sub = parser.add_subparsers(dest="command", required=True)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--tribunal")
    dry_parser = sub.add_parser("dry-run")
    dry_parser.add_argument("--tribunal", required=True)
    dry_parser.add_argument("--entrada", required=True, help="JSON em arquivo; use - para stdin")
    dry_parser.add_argument("--page-size", type=int, default=100)
    query_parser = sub.add_parser("consultar")
    query_parser.add_argument("--tribunal", required=True)
    query_parser.add_argument("--entrada", required=True, help="JSON em arquivo; use - para stdin")
    query_parser.add_argument("--page-size", type=int, default=100)
    query_parser.add_argument("--max-pages", type=int, default=20)
    query_parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            credenciais.carregar()
            out: dict[str, Any] = {
                "configured": bool(os.environ.get("DATAJUD_API_KEY") or datajud_contract.DATAJUD_API_KEY_PUBLICA),
                "origem_chave": "ambiente" if os.environ.get("DATAJUD_API_KEY") else "publica_embutida",
                "host": HOST,
            }
            if args.tribunal:
                out["endpoint"] = endpoint_datajud(args.tribunal)
            print(json.dumps(out, ensure_ascii=False))
            return 0
        entrada = _load_json(args.entrada)
        if args.command == "dry-run":
            body = preparar_consulta(entrada, page_size=args.page_size)
            print(json.dumps({
                "ok": True,
                "endpoint": endpoint_datajud(args.tribunal),
                "indice": datajud_contract.indice_do_tribunal(args.tribunal),
                "body": body,
                "network": False,
            }, ensure_ascii=False))
            return 0
        result = consultar(
            args.tribunal,
            entrada,
            page_size=args.page_size,
            max_pages=args.max_pages,
            timeout=args.timeout,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 2
    except (DataJudError, ValueError, OSError, json.JSONDecodeError) as exc:
        code = exc.code if isinstance(exc, DataJudError) else "entrada_invalida"
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "error_code": code,
            "message": str(exc),
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
