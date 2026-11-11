#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Adaptador read-only para séries mensais públicas do BCB/SGS.'










from __future__ import annotations

import argparse
import calendar
import hashlib
import http.client
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit


SCHEMA_SPEC = "dsr.serie_oficial.spec.v1"
SCHEMA_SNAPSHOT = "dsr.serie_oficial.v1"
API_HOST = "api.bcb.gov.br"
API_SCHEME = "https"
API_PREFIX = "/dados/serie/bcdata.sgs."
MAX_MONTHS = 600
MAX_BODY_BYTES = 16 * 1024 * 1024
DEFAULT_TIMEOUT = 30.0
REQUEST_KEYS = frozenset({
    "spec_path", "metadata_path", "output_path", "start_period", "end_period", "timeout"
})

















CATALOG_KINDS = frozenset({"dados_abertos_ckan", "sgs_serie_declarada"})
IDENTITY_KEYS = frozenset({
    "identity_attested_by", "identity_attested_role", "identity_attested_at",
    "identity_evidence_url",
})
SPEC_REQUIRED = frozenset({
    "provider", "series_id", "series_name", "catalog_url", "catalog_sha256", "catalog_kind",
    "metadata_valid_from", "metadata_valid_to", "frequency", "unit", "value_kind",
    "license", "attribution", "reviewed_by", "reviewed_role", "reviewed_at",
    "segregation_attested",
})
SNAPSHOT_REQUIRED = frozenset({
    "provider", "series_id", "series_name", "catalog_url", "catalog_sha256", "catalog_kind",
    "source_url",
    "source_response_sha256", "retrieved_at", "frequency", "unit", "value_kind", "license",
    "attribution", "metadata_valid_from", "metadata_valid_to", "metadata_reviewed_by",
    "metadata_reviewed_role", "metadata_reviewed_at", "segregation_attested", "coverage",
    "points",
})
COVERAGE_REQUIRED = frozenset({
    "requested_start", "requested_end", "expected_periods", "received_periods",
    "missing_periods", "duplicate_periods", "state",
})
POINT_REQUIRED = frozenset({"period", "value"})
REQUIRED_ROLES = frozenset({"advogado", "contador_judicial", "perito_contabil"})
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
PERIOD_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-01$")
API_DATE_RE = re.compile(r"^[0-9]{2}/[0-9]{2}/[0-9]{4}$")
SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
DATETIME_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)










CATALOGO_SERIES = Path(__file__).with_name("series_sgs_catalogo.json")
UNIDADE_DO_CONTRATO = "percentual ao mês"




FAMILIAS_NAO_INDICE = frozenset({"taxa_media_juros_recursos_livres"})
FAMILIAS_INDICE: frozenset[str] = frozenset()
_CATALOGO_CACHE: dict[str, Any] = {}


class AdapterError(ValueError):
    """Falha de entrada, contrato ou transporte que pode ser serializada."""


def _catalogo_series(caminho: str | os.PathLike[str] | None = None) -> Mapping[str, Any]:
    'Lê o catálogo da casa uma vez. Ausente ou ilegível falha FECHADO, com código nomeado:'

    alvo = Path(caminho) if caminho is not None else CATALOGO_SERIES
    chave = str(alvo)
    if chave in _CATALOGO_CACHE:
        return _CATALOGO_CACHE[chave]
    try:
        bruto = alvo.read_bytes()
        dados = json.loads(bruto.decode("utf-8"), parse_constant=_reject_constant,
                           object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise AdapterError(
            "catalogo_series_indisponivel: o catálogo de séries da casa "
            "(series_sgs_catalogo.json) não pôde ser lido ao lado do adaptador") from exc
    series = dados.get("series") if isinstance(dados, dict) else None
    if not isinstance(series, dict):
        raise AdapterError(
            "catalogo_series_indisponivel: o catálogo de séries da casa não traz o bloco `series`")
    _CATALOGO_CACHE[chave] = series
    return series


def recusa_da_serie(series_id: int,
                    catalogo: str | os.PathLike[str] | None = None) -> str | None:
    'Recusa nomeada quando o catálogo da casa registra a série com forma fora do contrato.'








    entrada = _catalogo_series(catalogo).get(str(series_id))
    if not isinstance(entrada, Mapping):
        return None
    unidade = entrada.get("unidade")
    if unidade is not None and unidade != UNIDADE_DO_CONTRATO:
        par = entrada.get("par_na_outra_unidade")
        return (
            f"serie_unidade_incompativel: o catálogo da casa registra a série {series_id} em "
            f"{unidade}; o adaptador só lê percentual ao mês"
            + (f" (a série ao mês correspondente é a {par})" if par else ""))
    if "catalog_kind" in entrada and entrada.get("catalog_kind") is None:
        return (
            f"serie_fora_do_contrato: o catálogo da casa registra a série {series_id} com "
            f"forma incompatível com o contrato do adaptador ({entrada.get('forma_medida')})")
    return None


def serie_nao_e_indice_de_correcao(series_id: int,
                                   catalogo: str | os.PathLike[str] | None = None) -> str | None:
    'Recusa nomeada quando o catálogo põe a série numa família que não é índice de correção.'




    entrada = _catalogo_series(catalogo).get(str(series_id))
    if not isinstance(entrada, Mapping):
        return None
    familia = entrada.get("familia")
    if familia in FAMILIAS_NAO_INDICE:
        return (
            f"serie_nao_e_indice_de_correcao: a série {series_id} é taxa média de juros de "
            f"mercado por modalidade; serve para comparar com a taxa do contrato e não se "
            f"acumula como índice de atualização monetária")
    return None


def _reject_constant(value: str) -> None:
    raise ValueError(f"constante JSON inválida: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"chave JSON duplicada: {key}")
        result[key] = value
    return result


def _strict_json_bytes(raw: bytes) -> Any:
    if not isinstance(raw, (bytes, bytearray)):
        raise AdapterError("corpo HTTP não é uma sequência de bytes")
    try:
        text = bytes(raw).decode("utf-8")
        return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise AdapterError("resposta não é JSON UTF-8 estrito") from exc


def _strict_json_text(text: str) -> Any:
    try:
        return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AdapterError("JSON de entrada inválido") from exc


def _read_json_file(path: str | os.PathLike[str]) -> Any:
    try:
        raw = Path(path).read_bytes()
    except (OSError, ValueError) as exc:
        raise AdapterError("arquivo JSON não pôde ser lido") from exc
    if len(raw) > MAX_BODY_BYTES:
        raise AdapterError("arquivo JSON excede o limite de 16 MiB")
    return _strict_json_bytes(raw)


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"{field} deve ser texto não vazio")
    return value.strip()


def _series_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AdapterError("series_id deve ser inteiro positivo")
    return value


def _parse_iso_date(value: Any, field: str) -> date:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise AdapterError(f"{field} deve estar em ISO AAAA-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AdapterError(f"{field} é uma data ISO inválida") from exc


def _parse_period(value: Any, field: str) -> date:
    if not isinstance(value, str) or not PERIOD_RE.fullmatch(value):
        raise AdapterError(f"{field} deve ser o primeiro dia do mês em ISO AAAA-MM-01")
    return _parse_iso_date(value, field)


def _today(value: Any = None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return _parse_iso_date(value, "hoje")


def _parse_timezone_datetime(value: Any, field: str = "retrieved_at") -> datetime:
    if not isinstance(value, str) or not DATETIME_RE.fullmatch(value):
        raise AdapterError(f"{field} deve ser datetime ISO com fuso horário")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise AdapterError(f"{field} é um datetime ISO inválido") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AdapterError(f"{field} deve declarar fuso horário")
    return parsed


def _canonical_decimal(value: Any, field: str = "valor") -> str:
    if not isinstance(value, str) or not DECIMAL_RE.fullmatch(value):
        raise AdapterError(f"{field} deve ser string decimal canônica")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AdapterError(f"{field} deve ser string decimal finita") from exc
    if not number.is_finite():
        raise AdapterError(f"{field} não pode ser NaN ou infinito")
    result = format(number, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    if result in {"", "-0"}:
        result = "0"
    return result


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except (OSError, ValueError) as exc:
        raise AdapterError("arquivo de metadados não pôde ser lido") from exc
    return digest.hexdigest()


def _unknown_fields(value: Mapping[str, Any], allowed: frozenset[str], where: str) -> list[str]:
    return [f"{where} contém campo não permitido: {key}" for key in value if key not in allowed]


def _catalog_kind(value: Any) -> str:
    if value not in CATALOG_KINDS:
        raise AdapterError(
            "catalog_kind deve ser um de: " + ", ".join(sorted(CATALOG_KINDS)))
    return str(value)


def _catalog_url(value: Any, series_id: int, kind: str = "dados_abertos_ckan") -> str:
    url = _nonempty_string(value, "catalog_url")
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise AdapterError("catalog_url contém porta inválida") from exc
    host = "dadosabertos.bcb.gov.br" if kind == "dados_abertos_ckan" else "api.bcb.gov.br"
    if (
        parsed.scheme != API_SCHEME
        or parsed.hostname != host
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
    ):
        raise AdapterError(
            f"catalog_url deve ser HTTPS em {host} sem credenciais, porta ou fragmento")
    if kind == "dados_abertos_ckan":
        if parsed.query:
            raise AdapterError("catalog_url do CKAN não aceita query")
        if not parsed.path.startswith("/dataset/"):
            raise AdapterError("catalog_url deve apontar para um dataset oficial")
        if not re.search(rf"(?<![0-9]){series_id}(?![0-9])", parsed.path):
            raise AdapterError("catalog_url não contém o series_id no caminho do dataset")
        return url


    if not re.fullmatch(rf"/dados/serie/bcdata\.sgs\.{series_id}/dados", parsed.path):
        raise AdapterError(
            "catalog_url de sgs_serie_declarada deve ser "
            f"/dados/serie/bcdata.sgs.{series_id}/dados")
    return url


def _identidade_atestada(value: Mapping[str, Any], where: str, hoje_: date) -> list[str]:
    'Atestação nominal exigida quando o catálogo oficial não liga código a nome.'






    errors: list[str] = []
    faltando = sorted(IDENTITY_KEYS - set(value))
    if faltando:
        errors.append(
            f"{where}: catalog_kind=sgs_serie_declarada exige atestação de identidade "
            f"(campo(s) ausente(s): {', '.join(faltando)}) — a URL da série prova que o "
            f"código serve dado, não que ele é a série que se afirma")
        return errors
    try:
        _nonempty_string(value.get("identity_attested_by"), "identity_attested_by")
    except AdapterError as exc:
        errors.append(str(exc))
    if value.get("identity_attested_role") not in REQUIRED_ROLES:
        errors.append("identity_attested_role não é um papel de revisão permitido")
    try:
        quando = _parse_iso_date(value.get("identity_attested_at"), "identity_attested_at")
        if quando > hoje_:
            errors.append("identity_attested_at não pode estar no futuro")
    except AdapterError as exc:
        errors.append(str(exc))
    prova = value.get("identity_evidence_url")
    if not isinstance(prova, str) or not prova.startswith("https://"):
        errors.append("identity_evidence_url deve ser URL HTTPS de documento oficial")
    return errors


def _recusas_do_catalogo(series_id: int) -> list[str]:
    try:
        recusa = recusa_da_serie(series_id)
    except AdapterError as exc:
        return [str(exc)]
    return [recusa] if recusa else []


def _periods_between(start: date, end: date) -> list[date]:
    if start > end:
        raise AdapterError("período inicial não pode ser posterior ao final")
    count = (end.year - start.year) * 12 + end.month - start.month + 1
    if count > MAX_MONTHS:
        raise AdapterError("intervalo excede 600 meses")
    return [date(start.year + (start.month - 1 + offset) // 12,
                 (start.month - 1 + offset) % 12 + 1, 1) for offset in range(count)]


def _period_text(value: date) -> str:
    return value.isoformat()


def _api_path(series_id: int, start: date, end: date) -> str:
    first = start.strftime("%d/%m/%Y")
    last_day = calendar.monthrange(end.year, end.month)[1]
    final = date(end.year, end.month, last_day).strftime("%d/%m/%Y")
    return (
        f"{API_PREFIX}{series_id}/dados?formato=json&dataInicial={first}&dataFinal={final}"
    )


def _validate_common_spec_fields(spec: Any, metadata_path: str | os.PathLike[str] | None,
                                 hoje: Any = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, Mapping):
        return ["spec deve ser um objeto JSON"]
    errors.extend(_unknown_fields(spec, SPEC_REQUIRED | IDENTITY_KEYS, "spec"))
    missing = sorted(SPEC_REQUIRED - set(spec))
    errors.extend(f"spec não contém campo obrigatório: {field}" for field in missing)
    kind: str | None = None
    try:
        kind = _catalog_kind(spec.get("catalog_kind"))
    except AdapterError as exc:
        errors.append(str(exc))
    try:
        if spec.get("provider") != "BCB_SGS":
            raise AdapterError("provider deve ser BCB_SGS")
    except AdapterError as exc:
        errors.append(str(exc))
    series_id: int | None = None
    try:
        series_id = _series_id(spec.get("series_id"))
    except AdapterError as exc:
        errors.append(str(exc))
    for field in ("series_name", "attribution", "reviewed_by"):
        try:
            _nonempty_string(spec.get(field), field)
        except AdapterError as exc:
            errors.append(str(exc))
    if series_id is not None:
        errors.extend(_recusas_do_catalogo(series_id))
    if series_id is not None and kind is not None:
        try:
            _catalog_url(spec.get("catalog_url"), series_id, kind)
        except AdapterError as exc:
            errors.append(str(exc))
    if kind == "sgs_serie_declarada":
        errors.extend(_identidade_atestada(spec, "spec", _today(hoje)))
    elif kind is not None:
        sobrando = sorted(IDENTITY_KEYS & set(spec))
        if sobrando:
            errors.append(
                "spec: " + ", ".join(sobrando) + " só cabe(m) com "
                "catalog_kind=sgs_serie_declarada; no CKAN quem liga código a nome é o dataset")
    sha = spec.get("catalog_sha256")
    if not isinstance(sha, str) or not SHA256_RE.fullmatch(sha):
        errors.append("catalog_sha256 deve ter 64 dígitos hexadecimais")
    dates: dict[str, date] = {}
    for field in ("metadata_valid_from", "metadata_valid_to", "reviewed_at"):
        try:
            dates[field] = _parse_iso_date(spec.get(field), field)
        except AdapterError as exc:
            errors.append(str(exc))
    if "metadata_valid_from" in dates and "metadata_valid_to" in dates:
        if dates["metadata_valid_from"] > dates["metadata_valid_to"]:
            errors.append("metadata_valid_from não pode ser posterior a metadata_valid_to")
    try:
        current = _today(hoje)
        if "reviewed_at" in dates and dates["reviewed_at"] > current:
            errors.append("reviewed_at não pode estar no futuro")
        if "metadata_valid_from" in dates and "metadata_valid_to" in dates:
            if not dates["metadata_valid_from"] <= current <= dates["metadata_valid_to"]:
                errors.append("hoje deve estar dentro da validade dos metadados")
    except AdapterError as exc:
        errors.append(str(exc))
    constants = {
        "frequency": "monthly",
        "unit": "percent_per_month",
        "value_kind": "percentage_rate",
        "license": "ODbL-1.0",
    }
    for field, expected in constants.items():
        if spec.get(field) != expected:
            errors.append(f"{field} deve ser {expected}")
    if spec.get("reviewed_role") not in REQUIRED_ROLES:
        errors.append("reviewed_role não é um papel de revisão permitido")
    if spec.get("segregation_attested") is not True:
        errors.append("segregation_attested deve ser true")
    if metadata_path is None:
        errors.append("metadata_path é obrigatório para conferir catalog_sha256")
    elif isinstance(sha, str) and SHA256_RE.fullmatch(sha):
        try:
            actual = _sha256_file(metadata_path)
            if actual.casefold() != sha.casefold():
                errors.append("catalog_sha256 não corresponde ao arquivo de metadados")
        except AdapterError as exc:
            errors.append(str(exc))
    return errors


def validar_spec(spec: Any, metadata_path: str | os.PathLike[str] | None = None,
                 hoje: Any = None) -> list[str]:
    """Retorna todos os erros verificáveis da especificação, sem lançar exceção."""
    return _validate_common_spec_fields(spec, metadata_path, hoje)


def _validate_snapshot_metadata(snapshot: Mapping[str, Any], hoje: Any,
                                errors: list[str]) -> tuple[int | None, date | None, date | None]:
    series_id: int | None = None
    try:
        series_id = _series_id(snapshot.get("series_id"))
    except AdapterError as exc:
        errors.append(str(exc))
    if snapshot.get("provider") != "BCB_SGS":
        errors.append("provider deve ser BCB_SGS")
    for field in ("series_name", "attribution", "metadata_reviewed_by"):
        try:
            _nonempty_string(snapshot.get(field), field)
        except AdapterError as exc:
            errors.append(str(exc))
    kind: str | None = None
    try:
        kind = _catalog_kind(snapshot.get("catalog_kind"))
    except AdapterError as exc:
        errors.append(str(exc))
    if series_id is not None:
        errors.extend(_recusas_do_catalogo(series_id))
    if series_id is not None and kind is not None:
        try:
            _catalog_url(snapshot.get("catalog_url"), series_id, kind)
        except AdapterError as exc:
            errors.append(str(exc))
    if kind == "sgs_serie_declarada":
        errors.extend(_identidade_atestada(snapshot, "snapshot", _today(hoje)))
    elif kind is not None:
        sobrando = sorted(IDENTITY_KEYS & set(snapshot))
        if sobrando:
            errors.append(
                "snapshot: " + ", ".join(sobrando) + " só cabe(m) com "
                "catalog_kind=sgs_serie_declarada")
    for field in ("catalog_sha256", "source_response_sha256"):
        value = snapshot.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            errors.append(f"{field} deve ter 64 dígitos hexadecimais")
    constants = {
        "frequency": "monthly",
        "unit": "percent_per_month",
        "value_kind": "percentage_rate",
        "license": "ODbL-1.0",
    }
    for field, expected in constants.items():
        if snapshot.get(field) != expected:
            errors.append(f"{field} deve ser {expected}")
    if snapshot.get("metadata_reviewed_role") not in REQUIRED_ROLES:
        errors.append("metadata_reviewed_role não é um papel de revisão permitido")
    if snapshot.get("segregation_attested") is not True:
        errors.append("segregation_attested deve ser true")
    dates: dict[str, date] = {}
    for field in ("metadata_valid_from", "metadata_valid_to", "metadata_reviewed_at"):
        try:
            dates[field] = _parse_iso_date(snapshot.get(field), field)
        except AdapterError as exc:
            errors.append(str(exc))
    start = end = None
    if "metadata_valid_from" in dates and "metadata_valid_to" in dates:
        if dates["metadata_valid_from"] > dates["metadata_valid_to"]:
            errors.append("metadata_valid_from não pode ser posterior a metadata_valid_to")
        try:
            current = _today(hoje)
            if "metadata_reviewed_at" in dates and dates["metadata_reviewed_at"] > current:
                errors.append("metadata_reviewed_at não pode estar no futuro")
            if dates["metadata_valid_from"] > current or current > dates["metadata_valid_to"]:
                errors.append("hoje deve estar dentro da validade dos metadados")
        except AdapterError as exc:
            errors.append(str(exc))
    try:
        _parse_timezone_datetime(snapshot.get("retrieved_at"))
    except AdapterError as exc:
        errors.append(str(exc))
    if series_id is not None:
        try:
            source = _nonempty_string(snapshot.get("source_url"), "source_url")
            source_parts = urlsplit(source)
            if source_parts.scheme != API_SCHEME or source_parts.hostname != API_HOST:
                raise AdapterError("source_url deve usar HTTPS direto no host oficial")
            if source_parts.username or source_parts.password or source_parts.port:
                raise AdapterError("source_url não pode conter credenciais ou porta")
            expected_path_prefix = f"{API_PREFIX}{series_id}/dados"
            if source_parts.path != expected_path_prefix:
                raise AdapterError("source_url não corresponde ao series_id")
        except (AdapterError, ValueError) as exc:
            errors.append(str(exc))
    coverage = snapshot.get("coverage")
    if not isinstance(coverage, Mapping):
        errors.append("coverage deve ser um objeto")
    else:
        errors.extend(_unknown_fields(coverage, COVERAGE_REQUIRED, "coverage"))
        errors.extend(
            f"coverage não contém campo obrigatório: {field}"
            for field in sorted(COVERAGE_REQUIRED - set(coverage))
        )
        try:
            start = _parse_period(coverage.get("requested_start"), "coverage.requested_start")
            end = _parse_period(coverage.get("requested_end"), "coverage.requested_end")
            expected = _periods_between(start, end)
            if coverage.get("expected_periods") != len(expected):
                errors.append("coverage.expected_periods não corresponde ao intervalo")
        except AdapterError as exc:
            errors.append(str(exc))
            expected = []
        received = coverage.get("received_periods")
        if isinstance(received, bool) or not isinstance(received, int) or received < 0:
            errors.append("coverage.received_periods deve ser inteiro não negativo")
        if coverage.get("state") not in {"complete", "partial"}:
            errors.append("coverage.state deve ser complete ou partial")
        for field in ("missing_periods", "duplicate_periods"):
            values = coverage.get(field)
            if not isinstance(values, list):
                errors.append(f"coverage.{field} deve ser uma lista")
                continue
            for item in values:
                try:
                    _parse_period(item, f"coverage.{field}")
                except AdapterError as exc:
                    errors.append(str(exc))
    points = snapshot.get("points")
    seen: dict[str, int] = {}
    if not isinstance(points, list):
        errors.append("points deve ser uma lista")
        points = []
    for index, point in enumerate(points):
        if not isinstance(point, Mapping):
            errors.append(f"points[{index}] deve ser um objeto")
            continue
        errors.extend(_unknown_fields(point, POINT_REQUIRED, f"points[{index}]"))
        errors.extend(
            f"points[{index}] não contém campo obrigatório: {field}"
            for field in sorted(POINT_REQUIRED - set(point))
        )
        try:
            period = _parse_period(point.get("period"), f"points[{index}].period")
            period_text = _period_text(period)
            seen[period_text] = seen.get(period_text, 0) + 1
        except AdapterError as exc:
            errors.append(str(exc))
        try:
            value = _canonical_decimal(point.get("value"), f"points[{index}].value")
            if point.get("value") != value:
                errors.append(f"points[{index}].value não está na forma canônica")
        except AdapterError as exc:
            errors.append(str(exc))
    if isinstance(coverage, Mapping) and start is not None and end is not None:
        if series_id is not None:
            try:
                expected_source = f"{API_SCHEME}://{API_HOST}{_api_path(series_id, start, end)}"
                if snapshot.get("source_url") != expected_source:
                    errors.append("source_url não corresponde ao intervalo solicitado")
            except AdapterError as exc:
                errors.append(str(exc))
        expected_text = {_period_text(value) for value in _periods_between(start, end)}
        unique_text = set(seen)
        outside = sorted(unique_text - expected_text)
        if outside:
            errors.append("points contém períodos fora do intervalo solicitado")
        missing = sorted(expected_text - unique_text)
        duplicates = sorted(period for period, count in seen.items() if count > 1)
        supplied_missing = coverage.get("missing_periods")
        supplied_duplicates = coverage.get("duplicate_periods")
        if supplied_missing != missing:
            errors.append("coverage.missing_periods não corresponde aos pontos")
        if supplied_duplicates != duplicates:
            errors.append("coverage.duplicate_periods não corresponde aos pontos")
        has_warnings = isinstance(snapshot.get("warnings"), list) and bool(snapshot.get("warnings"))
        expected_state = (
            "complete" if not missing and not duplicates and not outside and not has_warnings else "partial"
        )
        if coverage.get("state") != expected_state:
            errors.append("coverage.state não corresponde à cobertura observada")
        if coverage.get("received_periods") != len(points):
            errors.append("coverage.received_periods não corresponde à quantidade de pontos")
        if expected_state != "complete":
            errors.append("snapshot possui cobertura parcial; calculadora deve rejeitá-lo")
        if expected_state == "complete" and coverage.get("expected_periods") != len(points):
            errors.append("snapshot completo não cobre todos os períodos esperados")
    warnings = snapshot.get("warnings")
    if warnings is not None and (
        not isinstance(warnings, list) or any(not isinstance(item, str) or not item.strip() for item in warnings)
    ):
        errors.append("warnings deve ser uma lista de textos não vazios")
    return series_id, start, end


def validar_snapshot(snapshot: Any, hoje: Any = None) -> list[str]:
    """Retorna os erros de contrato de um snapshot; cobertura parcial é rejeitada."""
    if not isinstance(snapshot, Mapping):
        return ["snapshot deve ser um objeto JSON"]
    allowed = SNAPSHOT_REQUIRED | IDENTITY_KEYS | {"warnings"}
    errors = _unknown_fields(snapshot, allowed, "snapshot")
    errors.extend(
        f"snapshot não contém campo obrigatório: {field}"
        for field in sorted(SNAPSHOT_REQUIRED - set(snapshot))
    )
    _validate_snapshot_metadata(snapshot, hoje, errors)
    return errors


def _request_mapping(request: Any) -> dict[str, Any]:
    if not isinstance(request, Mapping):
        raise AdapterError("request deve ser um objeto JSON")
    unknown = set(request) - REQUEST_KEYS
    if unknown:
        raise AdapterError("request contém campos não permitidos")
    missing = REQUEST_KEYS - {"timeout"} - set(request)
    if missing:
        raise AdapterError("request não contém todos os campos obrigatórios")
    result = dict(request)
    for field in ("spec_path", "metadata_path", "output_path"):
        _nonempty_string(result.get(field), field)
    start = _parse_period(result.get("start_period"), "start_period")
    end = _parse_period(result.get("end_period"), "end_period")
    _periods_between(start, end)
    timeout = result.get("timeout", DEFAULT_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 120:
        raise AdapterError("timeout deve ser número entre 1 e 120 segundos")
    result["start"] = start
    result["end"] = end
    result["timeout_value"] = float(timeout)
    return result


def _is_inside_git(path: str | os.PathLike[str]) -> bool:
    try:
        current = Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    if not current.exists():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return True
    return False


def _read_request_argument(argument: str) -> Any:
    if argument == "-":
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        raw = stream.read(MAX_BODY_BYTES + 1)
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if len(raw) > MAX_BODY_BYTES:
            raise AdapterError("request excede o limite de 16 MiB")
        return _strict_json_bytes(raw)
    if not isinstance(argument, str) or not argument.strip():
        raise AdapterError("--request deve ser caminho ou -")
    if _is_inside_git(argument):
        raise AdapterError("request deve ficar fora de um repositório Git")
    return _read_json_file(argument)


def _headers_mapping(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    if isinstance(headers, Mapping):
        return {str(key).casefold(): str(value) for key, value in headers.items()}
    try:
        return {str(key).casefold(): str(value) for key, value in headers}
    except (TypeError, ValueError) as exc:
        raise AdapterError("cabeçalhos HTTP inválidos") from exc


def _default_transport(host: str, path: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPSConnection(host, timeout=timeout)
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        body = response.read(MAX_BODY_BYTES + 1)
        if not isinstance(body, bytes):
            raise AdapterError("resposta HTTP não é binária")
        return int(response.status), _headers_mapping(response.getheaders()), body
    finally:
        connection.close()


def _transport_response(result: Any) -> tuple[int, dict[str, str], bytes]:
    if isinstance(result, tuple) and len(result) == 3:
        status, headers, body = result
        if not isinstance(body, (bytes, bytearray)):
            raise AdapterError("transporte devolveu corpo não binário")
        return int(status), _headers_mapping(headers), bytes(body)
    status = getattr(result, "status", None)
    if status is None:
        raise AdapterError("transporte devolveu resposta inválida")
    raw_headers = getattr(result, "headers", None)
    if raw_headers is None and callable(getattr(result, "getheaders", None)):
        raw_headers = result.getheaders()
    headers = _headers_mapping(raw_headers)
    reader = getattr(result, "read", None)
    if not callable(reader):
        raise AdapterError("transporte não fornece leitura de corpo")
    try:
        body = reader(MAX_BODY_BYTES + 1)
    except TypeError:
        body = reader()
    if not isinstance(body, (bytes, bytearray)):
        raise AdapterError("transporte devolveu corpo não binário")
    return int(status), headers, bytes(body)


def _fetch(series_id: int, start: date, end: date, timeout: float,
           transport: Callable[[str, str, float], Any] | None = None) -> tuple[bytes, dict[str, str], str]:
    path = _api_path(series_id, start, end)
    fetch = transport or _default_transport
    try:
        response = _transport_response(fetch(API_HOST, path, timeout))
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError("falha no transporte HTTPS") from exc
    status, headers, body = response
    if len(body) > MAX_BODY_BYTES:
        raise AdapterError("resposta excede o limite de 16 MiB")
    if status != 200:
        if 300 <= status < 400:
            raise AdapterError("redirecionamento HTTP recusado")
        raise AdapterError("BCB/SGS respondeu com status HTTP não aceito")
    return body, headers, f"{API_SCHEME}://{API_HOST}{path}"


def _parse_body(body: bytes, start: date, end: date) -> tuple[list[dict[str, str]], list[str], list[str], int]:
    parsed = _strict_json_bytes(body)
    if not isinstance(parsed, list):
        raise AdapterError("resposta BCB/SGS deve ser uma lista JSON")
    periods = _periods_between(start, end)
    expected = {_period_text(period) for period in periods}
    counts: dict[str, int] = {}
    points: list[dict[str, str]] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, Mapping) or set(item) != {"data", "valor"}:
            raise AdapterError(f"ponto {index} deve conter exatamente data e valor")
        raw_date = item.get("data")
        if not isinstance(raw_date, str) or not API_DATE_RE.fullmatch(raw_date):
            raise AdapterError(f"ponto {index}.data deve estar em DD/MM/AAAA")
        try:
            parsed_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
        except ValueError as exc:
            raise AdapterError(f"ponto {index}.data é inválida") from exc
        if parsed_date.day != 1:
            raise AdapterError(f"ponto {index}.data deve ser o primeiro dia do mês")
        period = _period_text(parsed_date)
        if period not in expected:
            raise AdapterError("resposta contém período fora do intervalo solicitado")
        counts[period] = counts.get(period, 0) + 1
        points.append({
            "period": period,
            "value": _canonical_decimal(item.get("valor"), f"ponto {index}.valor"),
        })
    points.sort(key=lambda point: point["period"])
    missing = sorted(expected - set(counts))
    duplicates = sorted(period for period, count in counts.items() if count > 1)
    return points, missing, duplicates, len(parsed)


def _retrieved_at(headers: Mapping[str, str]) -> tuple[str, list[str]]:
    raw = headers.get("date")
    if raw:
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), []
        except (TypeError, ValueError, OverflowError):
            pass
    observed = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return observed, ["Cabeçalho HTTP Date ausente ou inválido; retrieved_at é observação local."]


def _make_snapshot(spec: Mapping[str, Any], source_url: str, raw: bytes,
                   headers: Mapping[str, str], start: date, end: date) -> dict[str, Any]:
    points, missing, duplicates, received_count = _parse_body(raw, start, end)
    retrieved_at, warnings = _retrieved_at(headers)
    snapshot: dict[str, Any] = {
        "provider": spec["provider"],
        "series_id": spec["series_id"],
        "series_name": spec["series_name"],
        "catalog_url": spec["catalog_url"],
        "catalog_sha256": spec["catalog_sha256"],
        "catalog_kind": spec["catalog_kind"],



        **{k: spec[k] for k in sorted(IDENTITY_KEYS) if k in spec},
        "source_url": source_url,
        "source_response_sha256": _sha256_bytes(raw),
        "retrieved_at": retrieved_at,
        "frequency": spec["frequency"],
        "unit": spec["unit"],
        "value_kind": spec["value_kind"],
        "license": spec["license"],
        "attribution": spec["attribution"],
        "metadata_valid_from": spec["metadata_valid_from"],
        "metadata_valid_to": spec["metadata_valid_to"],
        "metadata_reviewed_by": spec["reviewed_by"],
        "metadata_reviewed_role": spec["reviewed_role"],
        "metadata_reviewed_at": spec["reviewed_at"],
        "segregation_attested": True,
        "coverage": {
            "requested_start": _period_text(start),
            "requested_end": _period_text(end),
            "expected_periods": len(_periods_between(start, end)),
            "received_periods": received_count,
            "missing_periods": missing,
            "duplicate_periods": duplicates,
            "state": "complete" if not missing and not duplicates and not warnings else "partial",
        },
        "points": points,
    }
    if warnings:
        snapshot["warnings"] = warnings
    return snapshot


def _fsync_directory(path: str) -> None:
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


def _atomic_write_bytes(path: str | os.PathLike[str], raw: bytes) -> None:
    target = Path(path).expanduser().resolve()
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        _fsync_directory(str(parent))
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _atomic_write_json(path: str | os.PathLike[str], value: Mapping[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    _atomic_write_bytes(path, encoded)


def _raw_path(output_path: str | os.PathLike[str]) -> Path:
    target = Path(output_path).expanduser().resolve()
    raw = target.with_suffix(".raw.json")
    if raw == target:
        raise AdapterError("output_path não pode ser o próprio arquivo bruto")
    return raw


def _load_and_validate_spec(request: Mapping[str, Any]) -> Mapping[str, Any]:
    spec = _read_json_file(request["spec_path"])
    errors = validar_spec(spec, request["metadata_path"])
    if errors:
        raise AdapterError("spec inválida: " + "; ".join(errors))
    return spec


def capturar_snapshot(request: Mapping[str, Any],
                      transport: Callable[[str, str, float], Any] | None = None) -> dict[str, Any]:
    'Busca, preserva a resposta e publica o snapshot por último.'




    normalized = _request_mapping(request)
    spec = _load_and_validate_spec(normalized)
    series_id = _series_id(spec["series_id"])
    raw, headers, source_url = _fetch(
        series_id, normalized["start"], normalized["end"], normalized["timeout_value"], transport
    )
    raw_path = _raw_path(normalized["output_path"])
    _atomic_write_bytes(raw_path, raw)
    snapshot = _make_snapshot(spec, source_url, raw, headers, normalized["start"], normalized["end"])
    _atomic_write_json(normalized["output_path"], snapshot)
    return {
        "ok": True,
        "mode": "snapshot",
        "state": snapshot["coverage"]["state"],
        "output": str(Path(normalized["output_path"]).expanduser().resolve()),
        "raw_output": str(raw_path),
        "expected_periods": snapshot["coverage"]["expected_periods"],
        "received_periods": snapshot["coverage"]["received_periods"],
    }


def dry_run(request: Mapping[str, Any]) -> dict[str, Any]:
    """Valida tudo que é local e calcula o plano, sem rede ou credenciais."""
    normalized = _request_mapping(request)
    spec = _load_and_validate_spec(normalized)
    source_url = (
        f"{API_SCHEME}://{API_HOST}"
        f"{_api_path(spec['series_id'], normalized['start'], normalized['end'])}"
    )
    return {
        "ok": True,
        "mode": "dry-run",
        "provider": spec["provider"],
        "series_id": spec["series_id"],
        "source_url": source_url,
        "requested_start": _period_text(normalized["start"]),
        "requested_end": _period_text(normalized["end"]),
        "expected_periods": len(_periods_between(normalized["start"], normalized["end"])),
    }


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AdapterError(f"argumentos inválidos: {message}")


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="bcb_sgs_adapter.py", add_help=True)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("dry-run", "snapshot"):
        child = commands.add_parser(command)
        child.add_argument("--request", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        request = _read_request_argument(args.request)
        result = dry_run(request) if args.command == "dry-run" else capturar_snapshot(request)
    except (AdapterError, OSError, TypeError, ValueError) as exc:
        result = {"ok": False, "error": {"code": "adapter_failure", "message": str(exc)}}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
