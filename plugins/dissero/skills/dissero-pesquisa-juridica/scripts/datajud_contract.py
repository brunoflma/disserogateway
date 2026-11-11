#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Contrato local para consultas e cobertura do DataJud.'







from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from datetime import timedelta, date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


SCHEMA_VERSION = "dsr.datajud.coverage.v1"
SCHEMA_NAME = "datajud_coverage.schema.json"

_DATA14 = re.compile(r"^\d{14}$")
_INDEX_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TRIBUNAL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_UF = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}





DATAJUD_API_KEY_PUBLICA = (
    "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
)

TRIBUNAIS_DATAJUD = frozenset(
    {"STJ", "TST", "TSE", "STM"}
    | {f"TRF{i}" for i in range(1, 7)}
    | {f"TRT{i}" for i in range(1, 25)}
    | {f"TJ{uf}" for uf in _UF if uf != "DF"}
    | {"TJDFT", "TJMMG", "TJMRS", "TJMSP"}
)
INDICES_DATAJUD = {tribunal: f"api_publica_{tribunal.casefold()}" for tribunal in TRIBUNAIS_DATAJUD}
_INDICES_TRIBUNAIS = {indice: tribunal for tribunal, indice in INDICES_DATAJUD.items()}
_CREDENTIAL_KEY = re.compile(
    r"(?:authorization|api[_-]?key|cookie|token|session(?:id)?|sess[aã]o|password|senha|secret|segredo|bearer|credencial)",
    re.IGNORECASE,
)
_CREDENTIAL_VALUE = re.compile(
    r"(?:bearer|basic)\s+\S+|(?:authorization|api[_-]?key|cookie|token|session(?:id)?|password|senha|secret|credencial)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_ISODATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISODATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$"
)


_ISODATETIME_COMUM = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ](?:[01]\d|2[0-3]):\d{2}:\d{2}"
    r"(?:\.\d{3}|\.\d{6})?(?:Z|[+-]\d{2}:\d{2})?$"
)
_MOVEMENT_CODES = {22, 246}
_WARNING_CLOSURE = (
    "Os movimentos TPU 246/22 são apenas sinais de encerramento e variam por tribunal; "
    "não constituem prova de encerramento real do processo."
)


def _texto(value: Any) -> str:
    return str(value or "").strip()


def _indice_explicito(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("índice deve ser um único nome textual explícito")
    indice = value.strip()
    indice = indice.casefold()
    if not _INDEX_NAME.fullmatch(indice) or indice not in _INDICES_TRIBUNAIS:
        raise ValueError("índice deve ser um alias oficial explícito da API Pública DataJud")
    return indice


def _tribunal_explicito(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("tribunal deve ser um único nome textual explícito")
    tribunal = value.strip().upper()
    if not _TRIBUNAL_NAME.fullmatch(tribunal) or tribunal not in TRIBUNAIS_DATAJUD:
        raise ValueError("tribunal não consta da allowlist oficial da API Pública DataJud")
    return tribunal


def indice_do_tribunal(tribunal: Any) -> str:
    """Retorna o alias oficial e impede composição livre de path/índice."""
    return INDICES_DATAJUD[_tribunal_explicito(tribunal)]


def _query_contem_credencial(value: Any, path: str = "$") -> list[str]:
    achados: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _CREDENTIAL_KEY.search(key_text):
                achados.append(child_path)
            achados.extend(_query_contem_credencial(child, child_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            achados.extend(_query_contem_credencial(child, f"{path}[{index}]"))
    elif isinstance(value, str) and _CREDENTIAL_VALUE.search(value):
        achados.append(path)
    return achados


def normalizar_query(query: Any) -> Any:
    """Normaliza datas do DSL e rejeita qualquer material de autenticação."""
    if not isinstance(query, (Mapping, list, tuple)) or not query:
        raise ValueError("query deve ser um objeto ou lista DSL não vazia")
    if _query_contem_credencial(query):
        raise ValueError("query não pode conter cabeçalhos ou credenciais")
    return _normalizar_query(query)


def _canonical_datetime(value: datetime) -> str:
    'AAAAMMDDHHMMSS a partir de um datetime — e SÓ quando ele não é ambíguo.'










    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime de dataAjuizamento deve declarar fuso horário")
    if value.utcoffset() != timedelta(0):
        raise ValueError(
            "dataAjuizamento com fuso diferente de UTC é AMBÍGUA: o formato de 14 dígitos do "
            "DataJud não carrega fuso, e a semântica do campo (UTC ou horário local) não está "
            "declarada na documentação pública do CNJ. Converter em silêncio deslocaria a "
            "consulta em horas e viraria o dia para instantes antes das 03:00. Passe a data "
            "(AAAA-MM-DD), que é como o próprio DataJud a devolve, ou um datetime já em UTC")
    value = value.replace(tzinfo=None)
    if value.microsecond:
        raise ValueError("dataAjuizamento com fração de segundo não é conversível sem perda")
    return value.strftime("%Y%m%d%H%M%S")


def normalizar_data_ajuizamento(value: Any) -> str:
    'Converte uma data segura para ``AAAAMMDDHHMMSS``.'








    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, date):
        return value.strftime("%Y%m%d000000")
    if not isinstance(value, str):
        raise ValueError("dataAjuizamento deve ser string ISO, date ou datetime")

    raw = value.strip()
    if _DATA14.fullmatch(raw):
        try:
            parsed = datetime.strptime(raw, "%Y%m%d%H%M%S")
        except ValueError as exc:
            raise ValueError("dataAjuizamento AAAAMMDDHHMMSS inválida") from exc
        return parsed.strftime("%Y%m%d%H%M%S")
    if _ISODATE.fullmatch(raw):
        try:
            return date.fromisoformat(raw).strftime("%Y%m%d000000")
        except ValueError as exc:
            raise ValueError("dataAjuizamento ISO inválida") from exc
    if not _ISODATETIME.fullmatch(raw):
        raise ValueError(
            "dataAjuizamento deve ser AAAAMMDDHHMMSS ou datetime ISO sem formato ambíguo"
        )
    iso = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        if not _ISODATETIME_COMUM.fullmatch(raw):
            raise ValueError(raw)
        parsed = datetime.fromisoformat(iso)
    except ValueError as exc:
        raise ValueError("dataAjuizamento datetime ISO inválida") from exc
    return _canonical_datetime(parsed)


def _normalizar_query(value: Any, data_key: bool = False) -> Any:
    """Copia a DSL e normaliza somente valores sob ``dataAjuizamento``."""
    if data_key:
        if isinstance(value, Mapping):
            return {str(k): _normalizar_query(v, True) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_normalizar_query(v, True) for v in value]
        return normalizar_data_ajuizamento(value)
    if isinstance(value, Mapping):
        return {
            str(k): _normalizar_query(v, str(k).casefold() == "dataajuizamento")
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_normalizar_query(v) for v in value]
    if isinstance(value, tuple):
        return [_normalizar_query(v) for v in value]
    return copy.deepcopy(value)


def _nonnegative_int(value: Any, name: str, *, allow_none: bool = True) -> int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} deve ser inteiro não negativo")
    return value


def _timestamp_iso(value: Any) -> str:
    if value is None:
        raise ValueError("timestamp ausente; evidência externa não recebe horário por omissão")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp deve ser datetime ISO com fuso")
    raw = value.strip()
    iso = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError as exc:
        raise ValueError("timestamp deve ser datetime ISO com fuso") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp deve declarar fuso horário")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _failed_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError("shards_failed inválido")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("shards_failed deve ser não negativo")
        return value
    if isinstance(value, (list, tuple, set, Mapping)):
        return len(value)
    raise ValueError("shards_failed deve ser contagem ou coleção de shards")


def _coverage_state(
    shards_esperados: int | None,
    shards_recebidos: int | None,
    paginas_esperadas: int | None,
    paginas_recebidas: int | None,
    timed_out: bool,
    failed_count: int,
    hits: int | None,
) -> str:
    if timed_out or failed_count:
        return "parcial"
    pairs = (
        (shards_esperados, shards_recebidos),
        (paginas_esperadas, paginas_recebidas),
    )
    if any(expected is None or received is None for expected, received in pairs):
        return "indeterminado"
    if any(received > expected for expected, received in pairs):
        return "indeterminado"
    if any(received < expected for expected, received in pairs):
        return "parcial"

    if hits is None:
        return "indeterminado"
    return "completo"


def construir_cobertura(
    tribunal: str,
    indice: str,
    query: Any,
    shards_esperados: int | None,
    shards_recebidos: int | None,
    paginas_esperadas: int | None,
    paginas_recebidas: int | None,
    timed_out: bool,
    shards_failed: Any,
    hits: int | None,
    timestamp: Any,
) -> dict[str, Any]:
    'Monta o registro de cobertura, fail-closed, a partir da evidência do adaptador.'






    tribunal_text = _tribunal_explicito(tribunal)
    indice_text = _indice_explicito(indice)
    if INDICES_DATAJUD[tribunal_text] != indice_text:
        raise ValueError("índice não corresponde ao tribunal declarado")
    query_normalizada = normalizar_query(query)
    if not isinstance(timed_out, bool):
        raise ValueError("timed_out deve ser booleano")

    counts = {
        "shards_esperados": _nonnegative_int(shards_esperados, "shards_esperados"),
        "shards_recebidos": _nonnegative_int(shards_recebidos, "shards_recebidos"),
        "paginas_esperadas": _nonnegative_int(paginas_esperadas, "paginas_esperadas"),
        "paginas_recebidas": _nonnegative_int(paginas_recebidas, "paginas_recebidas"),
        "hits": _nonnegative_int(hits, "hits"),
    }
    for campo in ("shards_esperados", "paginas_esperadas"):
        if counts[campo] == 0:
            raise ValueError(f"{campo} deve ser positivo quando informado")
    failed_count = _failed_count(shards_failed)
    estado = _coverage_state(
        counts["shards_esperados"],
        counts["shards_recebidos"],
        counts["paginas_esperadas"],
        counts["paginas_recebidas"],
        timed_out,
        failed_count,
        counts["hits"],
    )
    timestamp = _timestamp_iso(timestamp)

    warnings = []
    if estado != "completo":
        warnings.append(
            "Cobertura não completa: resposta parcial, vazia ou incompleta não prova ausência."
        )
    if estado == "completo" and counts["hits"] == 0:
        warnings.append("Ausência conclusiva somente porque a cobertura está completa e hits=0.")

    return {
        "schema_version": SCHEMA_VERSION,
        "tribunal": tribunal_text,
        "indice": indice_text,
        "query": query_normalizada,
        **counts,
        "timed_out": bool(timed_out),
        "shards_failed": copy.deepcopy(shards_failed),
        "shards_failed_count": failed_count,
        "timestamp": timestamp,
        "state": estado,
        "warnings": warnings,
    }


def pode_concluir_ausencia(coverage: Mapping[str, Any]) -> bool:
    """True só para evidência completa com resultado conhecido de zero hits."""
    return (
        isinstance(coverage, Mapping)
        and not validar_cobertura(coverage)
        and coverage.get("state") == "completo"
        and coverage.get("hits") == 0
    )


def deve_repetir(http_status: int, coverage_state: str, tentativa: int) -> bool:
    """Política de uma só repetição; 504 nunca é repetido."""
    if isinstance(http_status, bool) or not isinstance(http_status, int):
        return False
    if isinstance(tentativa, bool) or not isinstance(tentativa, int) or tentativa != 0:
        return False
    if http_status == 504:
        return False
    return http_status == 429 or (http_status == 200 and coverage_state == "parcial")


def _movement_code(movement: Any) -> int | None:
    if isinstance(movement, bool):
        return None
    if isinstance(movement, int):
        return movement if movement in _MOVEMENT_CODES else None
    if isinstance(movement, str):
        value = movement.strip()
        return int(value) if value.isdigit() and int(value) in _MOVEMENT_CODES else None
    if not isinstance(movement, Mapping):
        return None
    for key in (
        "codigo",
        "codigo_movimento",
        "codigoMovimento",
        "codigo_tpu",
        "codigoTpu",
        "codigoMovimentoNacional",
        "codigoMovimentoTpu",
        "codigo_tpu_nacional",
        "codigoNacional",
        "id",
        "code",
        "movement_code",
    ):
        if key in movement:
            found = _movement_code(movement[key])
            if found is not None:
                return found
    for key in ("movimento", "movement", "evento", "movimentoNacional"):
        if key in movement:
            found = _movement_code(movement[key])
            if found is not None:
                return found
    return None


def classificar_encerramento(movimentos: Iterable[Any], tribunal: str) -> dict[str, Any]:
    """Classifica os sinais de encerramento da TPU sem promovê-los a prova."""
    if movimentos is None or isinstance(movimentos, (str, bytes, Mapping)):
        movimentos = [] if movimentos is None else [movimentos]
    encontrados = {22: 0, 246: 0}
    for movement in movimentos:
        code = _movement_code(movement)
        if code in encontrados:
            encontrados[code] += 1
    if encontrados[22] and encontrados[246]:
        estado = "sinal_completo"
    elif encontrados[22] or encontrados[246]:
        estado = "sinal_parcial"
    else:
        estado = "sem_sinal"
    return {
        "tribunal": _tribunal_explicito(tribunal),
        "state": estado,
        "movimentos_observados": {
            "22": encontrados[22] > 0,
            "246": encontrados[246] > 0,
        },
        "contagens": {str(code): count for code, count in encontrados.items()},
        "warning": _WARNING_CLOSURE,
    }


def validar_cobertura(coverage: Mapping[str, Any]) -> list[str]:
    """Validador estrutural curto, para quem não carrega o JSON Schema."""
    errors: list[str] = []
    if not isinstance(coverage, Mapping):
        return ["cobertura deve ser objeto"]
    if coverage.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version deve ser {SCHEMA_VERSION}")
    try:
        tribunal = _tribunal_explicito(coverage.get("tribunal"))
    except ValueError as exc:
        tribunal = ""
        errors.append(str(exc))
    try:
        indice = _indice_explicito(coverage.get("indice"))
    except ValueError as exc:
        indice = ""
        errors.append(str(exc))
    if tribunal and indice and INDICES_DATAJUD[tribunal] != indice:
        errors.append("índice não corresponde ao tribunal declarado")
    if coverage.get("state") not in {"completo", "parcial", "indeterminado"}:
        errors.append("state inválido")
    if not isinstance(coverage.get("query"), (Mapping, list)) or not coverage.get("query"):
        errors.append("query deve ser objeto/lista não vazia")
    elif _query_contem_credencial(coverage.get("query")):
        errors.append("query não pode conter cabeçalhos ou credenciais")
    if not isinstance(coverage.get("timed_out"), bool):
        errors.append("timed_out deve ser booleano")
    if coverage.get("hits") is not None and (
        isinstance(coverage.get("hits"), bool)
        or not isinstance(coverage.get("hits"), int)
        or coverage.get("hits") < 0
    ):
        errors.append("hits inválido")
    if not isinstance(coverage.get("warnings"), list):
        errors.append("warnings deve ser lista")
    try:
        _timestamp_iso(coverage.get("timestamp"))
    except ValueError as exc:
        errors.append(str(exc))
    try:
        failed_count = _failed_count(coverage.get("shards_failed"))
        derivado = _coverage_state(
            _nonnegative_int(coverage.get("shards_esperados"), "shards_esperados"),
            _nonnegative_int(coverage.get("shards_recebidos"), "shards_recebidos"),
            _nonnegative_int(coverage.get("paginas_esperadas"), "paginas_esperadas"),
            _nonnegative_int(coverage.get("paginas_recebidas"), "paginas_recebidas"),
            coverage.get("timed_out") if isinstance(coverage.get("timed_out"), bool) else True,
            failed_count,
            _nonnegative_int(coverage.get("hits"), "hits"),
        )
        for campo in ("shards_esperados", "paginas_esperadas"):
            if coverage.get(campo) == 0:
                errors.append(f"{campo} deve ser positivo quando informado")
        if coverage.get("shards_failed_count") != failed_count:
            errors.append("shards_failed_count diverge da evidência")
        if coverage.get("state") != derivado:
            errors.append(f"state diverge da evidência; derivado={derivado}")
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def _json_input(value: str | None) -> Any:
    if value is None:
        raise ValueError("entrada JSON obrigatória")
    candidate = Path(value)



    if os.path.isfile(candidate):
        return json.loads(candidate.read_text(encoding="utf-8"))
    return json.loads(value)


def _cli_output(value: Any, code: int = 0) -> int:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contrato offline de cobertura DataJud")
    sub = parser.add_subparsers(dest="command", required=True)

    date_parser = sub.add_parser("validate-query")
    date_parser.add_argument("value")

    coverage_parser = sub.add_parser("coverage")
    coverage_parser.add_argument("input", nargs="?")
    coverage_parser.add_argument("--input", dest="input_opt")

    retry_parser = sub.add_parser("retry")
    retry_parser.add_argument("--http-status", type=int, required=True)
    retry_parser.add_argument("--coverage-state", required=True)
    retry_parser.add_argument("--tentativa", type=int, required=True)

    closure_parser = sub.add_parser("closure")
    closure_parser.add_argument("input", nargs="?")
    closure_parser.add_argument("--input", dest="input_opt")
    closure_parser.add_argument("--tribunal", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "validate-query":
            return _cli_output({"ok": True, "dataAjuizamento": normalizar_data_ajuizamento(args.value)})
        if args.command == "retry":
            return _cli_output({
                "retry": deve_repetir(args.http_status, args.coverage_state, args.tentativa)
            })
        if args.command == "coverage":
            payload = _json_input(args.input_opt or args.input)
            if not isinstance(payload, Mapping):
                raise ValueError("entrada coverage deve ser objeto")
            out = construir_cobertura(**payload)
            return _cli_output(out)
        if args.command == "closure":
            payload = _json_input(args.input_opt or args.input)
            return _cli_output(classificar_encerramento(payload, args.tribunal))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _cli_output({"ok": False, "erro": str(exc)}, 2)
    return 2


if __name__ == "__main__":
    sys.exit(main())
