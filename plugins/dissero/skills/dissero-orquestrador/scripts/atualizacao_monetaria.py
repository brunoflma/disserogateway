#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Memória determinística de atualização monetária por séries oficiais.'





























from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import os
import re
import sys
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    localcontext,
)
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

try:
    import bcb_sgs_adapter
except ImportError:
    from . import bcb_sgs_adapter
try:
    import ficha_capacidade
except ImportError:
    from . import ficha_capacidade


CAPACIDADE = "atualizacao_monetaria"
ENGINE_VERSION = "dsr.atualizacao_monetaria.engine.v1"
REGIME_VERSION = "dsr.regime_atualizacao.v1"
REQUEST_VERSION = "dsr.atualizacao_monetaria.pedido.v1"
MEMORY_VERSION = "dsr.memoria_atualizacao.v1"
AUTH_VERSION = "dsr.atualizacao_monetaria.autorizacao.v1"
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")



_HORA_FUSO = re.compile(r"(?P<hora>[0-9]{2}:[0-9]{2}(?P<seg>:[0-9]{2})?)"
                        r"(?(seg)(?:[.,](?P<fracao>[0-9]{1,6})[0-9]*)?)"
                        r"(?P<fuso>[+-][0-9]{2})(?::?(?P<min>[0-9]{2}))?\Z")
_OFFICIAL_SUFFIXES = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")
_ROUNDING = {
    "ROUND_HALF_UP": ROUND_HALF_UP,
    "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
    "ROUND_DOWN": ROUND_DOWN,
}
_REGIME_KEYS = {
    "schema_version", "regime_id", "name", "legal_source_url",
    "legal_source_sha256", "review_valid_from", "review_valid_to",
    "reviewed_by", "reviewed_role", "reviewed_at", "segregation_attested",
    "rounding", "segment_rules",
}
_RULE_KEYS = {
    "id", "order", "series_id", "operator", "boundary_policy",
    "fractional_period_policy", "applicable_from", "applicable_to", "legal_basis",
    "day_count_basis", "fraction_scale",
}




_OPERADORES = {"compound_percentage", "simple_percentage"}
_POLITICAS_FRACAO = {"reject", "pro_rata"}
_BASES_CONTAGEM = {"dias_corridos_mes_civil"}
_REQUEST_KEYS = {
    "schema_version", "principal", "currency", "data_base", "calculation_date",
    "regime_path", "regime_sha256", "legal_source_path", "authorization_path", "segments",
}
_SEGMENT_KEYS = {"id", "snapshot_path", "snapshot_sha256", "periods", "fracoes"}


class AtualizacaoError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def _reject_constant(value: str) -> None:
    raise ValueError(f"constante JSON inválida: {value}")


def _safe_json_loads(text: str) -> Any:
    return json.loads(text, parse_constant=_reject_constant)


def _sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def _regular_file(path: Any, *, outside_git: bool = True) -> str | None:
    if not isinstance(path, (str, os.PathLike)):
        return None
    resolved = os.path.realpath(os.path.abspath(os.fspath(path)))
    if os.path.islink(os.path.abspath(os.fspath(path))) or not os.path.isfile(resolved):
        return None
    if outside_git and _is_git_path(resolved):
        return None
    return resolved


def _load_file(path: Any, *, outside_git: bool = True) -> tuple[dict[str, Any], str, str]:
    resolved = _regular_file(path, outside_git=outside_git)
    if resolved is None:
        raise AtualizacaoError("arquivo_invalido", "arquivo local ausente, inseguro ou dentro de Git")
    try:
        raw = Path(resolved).read_bytes()
        value = _safe_json_loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise AtualizacaoError("arquivo_invalido", "arquivo JSON local ilegível") from exc
    if not isinstance(value, dict):
        raise AtualizacaoError("arquivo_invalido", "arquivo JSON deve conter objeto")
    return value, hashlib.sha256(raw).hexdigest(), resolved


def _date(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _month(value: Any) -> dt.date | None:
    result = _date(value)
    return result if result is not None and result.day == 1 else None


def _datetime(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    hora = _HORA_FUSO.search(candidate)
    if hora:
        fracao = dt.datetime.strptime(hora["fracao"], "%f").strftime(".%f") if hora["fracao"] else ""
        candidate = candidate[:hora.start()] + hora["hora"] + fracao + hora["fuso"] + ":%02d" % int(hora["min"] or 0)
    try:
        result = dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if result.tzinfo is None or result.utcoffset() is None:
        return None
    return result.astimezone(dt.timezone.utc)


def _next_month(value: dt.date) -> dt.date:
    return dt.date(value.year + (1 if value.month == 12 else 0), 1 if value.month == 12 else value.month + 1, 1)


def _official_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").casefold()
    return (
        parsed.scheme == "https"
        and bool(host)
        and any(host.endswith(suffix) for suffix in _OFFICIAL_SUFFIXES)
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )


def _decimal(value: Any, name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        raise AtualizacaoError("pedido_invalido", f"{name} deve ser decimal positivo em string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise AtualizacaoError("pedido_invalido", f"{name} inválido") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise AtualizacaoError("pedido_invalido", f"{name} deve ser maior que zero")
    return result


def _fmt(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def validar_regime(regime: Any, *, hoje: dt.date | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(regime, Mapping):
        return ["regime deve ser objeto"]
    unknown = sorted(set(map(str, regime)) - _REGIME_KEYS)
    if unknown:
        errors.append("campos de regime não permitidos: " + ", ".join(unknown))
    if regime.get("schema_version") != REGIME_VERSION:
        errors.append(f"schema_version deve ser {REGIME_VERSION}")
    for field in ("regime_id", "name", "reviewed_by"):
        if not isinstance(regime.get(field), str) or len(regime[field].strip()) < (3 if field == "reviewed_by" else 1):
            errors.append(f"{field} deve ser texto não vazio")
    if isinstance(regime.get("regime_id"), str) and not _ID.fullmatch(regime["regime_id"]):
        errors.append("regime_id deve ser identificador estável")
    if not _official_url(regime.get("legal_source_url")):
        errors.append("legal_source_url deve ser URL HTTPS oficial")
    if not isinstance(regime.get("legal_source_sha256"), str) or not _SHA256.fullmatch(regime["legal_source_sha256"]):
        errors.append("legal_source_sha256 inválido")
    if regime.get("reviewed_role") != "advogado":
        errors.append("reviewed_role deve ser advogado")
    if regime.get("segregation_attested") is not True:
        errors.append("segregation_attested=true é obrigatório")
    today = hoje or dt.date.today()
    start = _date(regime.get("review_valid_from"))
    end = _date(regime.get("review_valid_to"))
    reviewed = _date(regime.get("reviewed_at"))
    if start is None or end is None or start > end:
        errors.append("vigência da revisão inválida")
    elif not start <= today <= end:
        errors.append("revisão jurídica ausente, futura ou vencida")
    if reviewed is None or reviewed > today:
        errors.append("reviewed_at inválido ou futuro")
    rounding = regime.get("rounding")
    if not isinstance(rounding, Mapping) or set(map(str, rounding)) != {"scale", "mode"}:
        errors.append("rounding deve declarar somente scale e mode")
    else:
        scale = rounding.get("scale")
        if isinstance(scale, bool) or not isinstance(scale, int) or not 0 <= scale <= 8:
            errors.append("rounding.scale deve ficar entre 0 e 8")
        if rounding.get("mode") not in _ROUNDING:
            errors.append("rounding.mode não suportado")
    rules = regime.get("segment_rules")
    if not isinstance(rules, list) or not rules:
        errors.append("segment_rules deve ser lista não vazia")
        return errors
    ids: set[str] = set()
    ranges: list[tuple[dt.date, dt.date, str]] = []
    orders: list[int] = []
    for index, rule in enumerate(rules):
        prefix = f"segment_rules[{index}]"
        if not isinstance(rule, Mapping):
            errors.append(f"{prefix} deve ser objeto")
            continue
        extras = sorted(set(map(str, rule)) - _RULE_KEYS)
        if extras:
            errors.append(f"{prefix}: campos não permitidos: {', '.join(extras)}")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not _ID.fullmatch(rule_id):
            errors.append(f"{prefix}.id inválido")
            rule_id = f"invalid-{index}"
        elif rule_id in ids:
            errors.append(f"{prefix}.id duplicado")
        ids.add(rule_id)
        order = rule.get("order")
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            errors.append(f"{prefix}.order inválido")
        else:
            orders.append(order)
        series_id = rule.get("series_id")
        if isinstance(series_id, bool) or not isinstance(series_id, int) or series_id <= 0:
            errors.append(f"{prefix}.series_id inválido")
        else:


            try:
                recusa = bcb_sgs_adapter.serie_nao_e_indice_de_correcao(series_id)
            except bcb_sgs_adapter.AdapterError as exc:
                recusa = str(exc)
            if recusa:
                errors.append(f"{prefix}: {recusa}")
        if rule.get("operator") not in _OPERADORES:
            errors.append(
                f"{prefix}.operator não suportado; o motor não converte operador "
                f"(declare um de: {', '.join(sorted(_OPERADORES))})")
        if rule.get("boundary_policy") != "explicit_periods_only":
            errors.append(f"{prefix}.boundary_policy deve ser explicit_periods_only")
        politica = rule.get("fractional_period_policy")
        if politica not in _POLITICAS_FRACAO:
            errors.append(
                f"{prefix}.fractional_period_policy deve ser um de: "
                f"{', '.join(sorted(_POLITICAS_FRACAO))}")
        elif politica == "pro_rata":
            if rule.get("day_count_basis") not in _BASES_CONTAGEM:
                errors.append(
                    f"{prefix}.day_count_basis é obrigatório quando a política é pro_rata "
                    f"e só aceita: {', '.join(sorted(_BASES_CONTAGEM))} — a norma não fixa a "
                    f"base de contagem, então quem a escolhe é a revisão jurídica, não o motor")
            escala = rule.get("fraction_scale")
            if isinstance(escala, bool) or not isinstance(escala, int) or not 0 <= escala <= 8:
                errors.append(
                    f"{prefix}.fraction_scale é obrigatório com pro_rata e deve ficar entre 0 "
                    f"e 8 — o quociente dias/mês quase nunca termina, e arredondar por conta "
                    f"própria seria o motor fixando precisão que a norma não fixou")
        else:
            mudos = sorted({"day_count_basis", "fraction_scale"} & set(map(str, rule)))
            if mudos:
                errors.append(
                    f"{prefix}: {', '.join(mudos)} só cabe(m) quando "
                    f"fractional_period_policy=pro_rata")
        applicable_from = _month(rule.get("applicable_from"))
        applicable_to = _month(rule.get("applicable_to"))
        if applicable_from is None or applicable_to is None or applicable_from > applicable_to:
            errors.append(f"{prefix}: vigência mensal inválida")
        else:
            ranges.append((applicable_from, applicable_to, rule_id))
        if not isinstance(rule.get("legal_basis"), str) or len(rule["legal_basis"].strip()) < 3:
            errors.append(f"{prefix}.legal_basis obrigatório")
    if orders and sorted(orders) != list(range(1, len(rules) + 1)):
        errors.append("ordem dos segmentos deve ser contígua de 1 a N")
    for index, (start_a, end_a, id_a) in enumerate(ranges):
        for start_b, end_b, id_b in ranges[index + 1:]:
            if max(start_a, start_b) <= min(end_a, end_b):
                errors.append(f"segmentos {id_a} e {id_b} têm vigência sobreposta")
    return errors


def _validate_request(request: Any, *, hoje: dt.date) -> list[str]:
    errors: list[str] = []
    if not isinstance(request, Mapping):
        return ["pedido deve ser objeto"]
    unknown = sorted(set(map(str, request)) - _REQUEST_KEYS)
    if unknown:
        errors.append("campos de pedido não permitidos: " + ", ".join(unknown))
    if request.get("schema_version") != REQUEST_VERSION:
        errors.append(f"schema_version deve ser {REQUEST_VERSION}")
    try:
        _decimal(request.get("principal"), "principal", positive=True)
    except AtualizacaoError as exc:
        errors.extend(exc.errors)
    if request.get("currency") != "BRL":
        errors.append("currency deve ser BRL")
    base = _date(request.get("data_base"))
    calculation = _date(request.get("calculation_date"))
    if base is None or calculation is None or base > calculation:
        errors.append("data_base/calculation_date inválidas")
    elif calculation > hoje:
        errors.append("calculation_date futura não é permitida")
    for field in ("regime_path", "legal_source_path", "authorization_path"):
        if not isinstance(request.get(field), str) or not request[field].strip():
            errors.append(f"{field} obrigatório")
    if not isinstance(request.get("regime_sha256"), str) or not _SHA256.fullmatch(request["regime_sha256"]):
        errors.append("regime_sha256 inválido")
    segments = request.get("segments")
    if not isinstance(segments, list) or not segments:
        errors.append("segments deve ser lista não vazia")
    else:
        for index, segment in enumerate(segments):
            prefix = f"segments[{index}]"
            if not isinstance(segment, Mapping):
                errors.append(f"{prefix} deve ser objeto")
                continue
            extras = sorted(set(map(str, segment)) - _SEGMENT_KEYS)
            if extras:
                errors.append(f"{prefix}: campos não permitidos: {', '.join(extras)}")
            if not isinstance(segment.get("id"), str) or not _ID.fullmatch(segment["id"]):
                errors.append(f"{prefix}.id inválido")
            if not isinstance(segment.get("snapshot_path"), str) or not segment["snapshot_path"].strip():
                errors.append(f"{prefix}.snapshot_path obrigatório")
            if not isinstance(segment.get("snapshot_sha256"), str) or not _SHA256.fullmatch(segment["snapshot_sha256"]):
                errors.append(f"{prefix}.snapshot_sha256 inválido")
            periods = segment.get("periods")
            if not isinstance(periods, list) or not periods:
                errors.append(f"{prefix}.periods deve ser lista não vazia")
            elif not all(_month(value) is not None for value in periods):
                errors.append(f"{prefix}.periods aceita somente primeiro dia de cada mês")
    return errors


def _load_authorization(path: Any, regime_hash: str, *, agora: dt.datetime,
                        escopo: str = "calculo_experimental") -> dict[str, Any]:
    'Autorização do advogado presa a um hash. No regime revisado, o hash é o do regime; na'


    authorization, _hash, _ = _load_file(path, outside_git=True)
    allowed = {
        "schema_version", "authorized_by_lawyer", "scope", "regime_sha256",
        "expires_at", "authorized_by",
    }
    errors: list[str] = []
    extras = sorted(set(map(str, authorization)) - allowed)
    if extras:
        errors.append("campos de autorização não permitidos: " + ", ".join(extras))
    if authorization.get("schema_version") != AUTH_VERSION:
        errors.append(f"schema_version da autorização deve ser {AUTH_VERSION}")
    if authorization.get("authorized_by_lawyer") is not True:
        errors.append("authorized_by_lawyer=true é obrigatório")
    if authorization.get("scope") != escopo:
        errors.append(f"scope da autorização inválido (esperado: {escopo})")
    declared_hash = authorization.get("regime_sha256")
    if not isinstance(declared_hash, str) or not _SHA256.fullmatch(declared_hash):
        errors.append("regime_sha256 da autorização inválido")
    elif declared_hash.casefold() != regime_hash.casefold():
        errors.append("autorização não corresponde ao regime")
    expires = _datetime(authorization.get("expires_at"))
    if expires is None or expires <= agora.astimezone(dt.timezone.utc):
        errors.append("autorização ausente, inválida ou vencida")
    if not isinstance(authorization.get("authorized_by"), str) or len(authorization["authorized_by"].strip()) < 3:
        errors.append("authorized_by inválido")
    if errors:
        raise AtualizacaoError("autorizacao_invalida", errors)
    return authorization


def _validate_periods(periods: list[str], *, prefix: str) -> list[dt.date]:
    parsed = [_month(value) for value in periods]
    if any(value is None for value in parsed):
        raise AtualizacaoError("periodos_invalidos", f"{prefix}: período mensal inválido")
    dates = [value for value in parsed if value is not None]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise AtualizacaoError("periodos_invalidos", f"{prefix}: períodos devem ser únicos e ordenados")
    for previous, current in zip(dates, dates[1:]):
        if _next_month(previous) != current:
            raise AtualizacaoError("periodos_invalidos", f"{prefix}: lacuna mensal não é permitida")
    return dates


def _validate_fracoes(bruto: Any, rule: Mapping[str, Any], periods: list[dt.date],
                      *, prefix: str) -> dict[str, tuple[int, int]]:
    'Confere as frações pro rata DECLARADAS no pedido — o motor nunca as infere.'










    politica = rule.get("fractional_period_policy")
    if bruto is None:
        if politica == "pro_rata":
            raise AtualizacaoError(
                "fracao_invalida",
                f"{prefix}: política pro_rata declarada sem nenhuma fração no pedido — "
                f"se não há ponta fracionada, declare fractional_period_policy=reject")
        return {}
    if politica != "pro_rata":
        raise AtualizacaoError(
            "fracao_invalida",
            f"{prefix}: pedido traz frações, mas o regime declara "
            f"fractional_period_policy={politica!r}")
    if not isinstance(bruto, Mapping) or not bruto:
        raise AtualizacaoError("fracao_invalida", f"{prefix}: fracoes deve ser objeto não vazio")
    pontas = {periods[0].isoformat(), periods[-1].isoformat()}
    saida: dict[str, tuple[int, int]] = {}
    for chave, valor in bruto.items():
        if not isinstance(chave, str) or _month(chave) is None:
            raise AtualizacaoError("fracao_invalida", f"{prefix}: período de fração inválido")
        if chave not in {p.isoformat() for p in periods}:
            raise AtualizacaoError(
                "fracao_invalida", f"{prefix}: fração em {chave}, fora dos períodos do segmento")
        if chave not in pontas:
            raise AtualizacaoError(
                "fracao_invalida",
                f"{prefix}: fração em {chave} não é ponta do segmento; mês do meio é integral")
        if not isinstance(valor, Mapping) or set(map(str, valor)) != {"dias", "dias_no_mes"}:
            raise AtualizacaoError(
                "fracao_invalida", f"{prefix}: fração {chave} deve declarar só dias e dias_no_mes")
        dias, dias_no_mes = valor.get("dias"), valor.get("dias_no_mes")
        for nome, numero in (("dias", dias), ("dias_no_mes", dias_no_mes)):
            if isinstance(numero, bool) or not isinstance(numero, int) or numero < 1:
                raise AtualizacaoError(
                    "fracao_invalida", f"{prefix}: fração {chave}.{nome} deve ser inteiro >= 1")
        mes = _month(chave)
        assert mes is not None
        real = calendar.monthrange(mes.year, mes.month)[1]
        if dias_no_mes != real:
            raise AtualizacaoError(
                "fracao_invalida",
                f"{prefix}: fração {chave} declara {dias_no_mes} dias no mês; o calendário "
                f"civil tem {real} — a base declarada é dias_corridos_mes_civil")
        if dias >= dias_no_mes:
            raise AtualizacaoError(
                "fracao_invalida",
                f"{prefix}: fração {chave} cobre {dias} de {dias_no_mes} dias; mês integral "
                f"não é fração — remova-a em vez de declará-la cheia")
        saida[chave] = (dias, dias_no_mes)
    return saida


def calcular(
    pedido: Any,
    *,
    hoje: dt.date | None = None,
    agora: dt.datetime | None = None,
    experimental_authorized: bool = False,
    registro_capacidades: Any = None,
) -> dict[str, Any]:
    'Executa uma memória condicional; desabilitado por padrão.'



    if experimental_authorized is not True:
        raise AtualizacaoError(
            "capacidade_desabilitada",
            "atualização monetária experimental exige autorização explícita nesta execução",
        )
    if agora is None:
        now = (
            dt.datetime.combine(hoje, dt.time(12, 0), tzinfo=dt.timezone.utc)
            if hoje is not None
            else dt.datetime.now(dt.timezone.utc)
        )
    elif not isinstance(agora, dt.datetime) or agora.tzinfo is None or agora.utcoffset() is None:
        raise AtualizacaoError("autorizacao_invalida", "agora deve ser datetime com fuso horário")
    else:
        now = agora.astimezone(dt.timezone.utc)
    today = hoje or now.date()
    try:
        ficha_capacidade.exigir(CAPACIDADE, hoje=today, registro=registro_capacidades)
    except ficha_capacidade.FichaRecusada as exc:
        raise AtualizacaoError(exc.codigo, exc.mensagem) from None
    request_errors = _validate_request(pedido, hoje=today)
    if request_errors:
        raise AtualizacaoError("pedido_invalido", request_errors)
    assert isinstance(pedido, Mapping)
    principal = _decimal(pedido["principal"], "principal", positive=True)

    regime, regime_hash, _ = _load_file(pedido["regime_path"])
    if regime_hash.casefold() != str(pedido["regime_sha256"]).casefold():
        raise AtualizacaoError("hash_divergente", "regime_sha256 diverge do arquivo")
    authorization = _load_authorization(pedido["authorization_path"], regime_hash, agora=now)
    regime_errors = validar_regime(regime, hoje=today)
    if any(": serie_nao_e_indice_de_correcao:" in erro for erro in regime_errors):
        raise AtualizacaoError("serie_nao_e_indice_de_correcao", regime_errors)
    if regime_errors:
        raise AtualizacaoError("regime_invalido", regime_errors)

    legal_path = _regular_file(pedido["legal_source_path"], outside_git=True)
    if legal_path is None:
        raise AtualizacaoError("fonte_juridica_invalida", "captura da fonte jurídica ausente ou insegura")
    if _sha256_file(legal_path).casefold() != str(regime["legal_source_sha256"]).casefold():
        raise AtualizacaoError("hash_divergente", "hash da fonte jurídica diverge do regime")

    calculation_date = _date(pedido["calculation_date"])
    assert calculation_date is not None
    if not (_date(regime["review_valid_from"]) <= today <= _date(regime["review_valid_to"])):
        raise AtualizacaoError("regime_vencido", "revisão jurídica fora da vigência")

    rules = sorted(regime["segment_rules"], key=lambda item: item["order"])
    request_segments = pedido["segments"]
    if [item["id"] for item in request_segments] != [item["id"] for item in rules]:
        raise AtualizacaoError("pedido_invalido", "segmentos do pedido devem corresponder à ordem do regime")

    memory_segments: list[dict[str, Any]] = []
    avisos_mes_corrente: list[str] = []
    factor_total = Decimal(1)
    all_periods: set[dt.date] = set()
    with localcontext() as context:
        context.prec = 50
        for rule, request_segment in zip(rules, request_segments):
            segment_id = rule["id"]
            snapshot, snapshot_hash, _ = _load_file(request_segment["snapshot_path"])
            if snapshot_hash.casefold() != str(request_segment["snapshot_sha256"]).casefold():
                raise AtualizacaoError("hash_divergente", f"{segment_id}: snapshot_sha256 diverge")


            nao_fechado = bcb_sgs_adapter.mes_nao_fechado(snapshot, request_segment["periods"])
            if nao_fechado:
                raise AtualizacaoError("mes_nao_fechado", f"{segment_id}: {nao_fechado}")
            corrente = bcb_sgs_adapter.aviso_mes_corrente(snapshot, request_segment["periods"])
            if corrente:
                avisos_mes_corrente.append(f"{segment_id}: {corrente}")
            snapshot_errors = bcb_sgs_adapter.validar_snapshot(snapshot, hoje=today)
            if snapshot_errors:
                raise AtualizacaoError("snapshot_invalido", [f"{segment_id}: {error}" for error in snapshot_errors])
            if snapshot.get("coverage", {}).get("state") != "complete":
                raise AtualizacaoError("cobertura_incompleta", f"{segment_id}: snapshot parcial")
            if snapshot.get("series_id") != rule["series_id"]:
                raise AtualizacaoError("serie_divergente", f"{segment_id}: series_id diverge do regime")
            if snapshot.get("frequency") != "monthly" or snapshot.get("unit") != "percent_per_month" or snapshot.get("value_kind") != "percentage_rate":
                raise AtualizacaoError("serie_divergente", f"{segment_id}: unidade/periodicidade/value_kind não suportado")
            if rule["operator"] not in _OPERADORES:
                raise AtualizacaoError("operador_nao_suportado", f"{segment_id}: operador não suportado")
            periods = _validate_periods(request_segment["periods"], prefix=segment_id)
            applicable_from = _month(rule["applicable_from"])
            applicable_to = _month(rule["applicable_to"])
            assert applicable_from is not None and applicable_to is not None
            if any(period < applicable_from or period > applicable_to for period in periods):
                raise AtualizacaoError("vigencia_invalida", f"{segment_id}: período fora da vigência declarada")
            duplicate_global = all_periods.intersection(periods)
            if duplicate_global:
                raise AtualizacaoError("periodos_invalidos", f"{segment_id}: período aplicado em mais de um segmento")
            all_periods.update(periods)
            points = snapshot.get("points")
            if not isinstance(points, list):
                raise AtualizacaoError("snapshot_invalido", f"{segment_id}: points ausente")
            point_map = {item.get("period"): item.get("value") for item in points if isinstance(item, Mapping)}
            missing = [period.isoformat() for period in periods if period.isoformat() not in point_map]
            if missing:
                raise AtualizacaoError("cobertura_incompleta", f"{segment_id}: períodos ausentes: {', '.join(missing)}")
            simples = rule["operator"] == "simple_percentage"
            fracoes = _validate_fracoes(request_segment.get("fracoes"), rule, periods,
                                        prefix=segment_id)
            factor_segment = Decimal(1)
            soma_simples = Decimal(0)
            memory_points: list[dict[str, str]] = []
            for period in periods:
                raw_value = point_map[period.isoformat()]
                try:
                    value = Decimal(str(raw_value))
                except InvalidOperation as exc:
                    raise AtualizacaoError("snapshot_invalido", f"{segment_id}: valor decimal inválido") from exc
                if not value.is_finite():
                    raise AtualizacaoError("snapshot_invalido", f"{segment_id}: valor decimal inválido")
                ponto: dict[str, str] = {"period": period.isoformat(),
                                         "value_serie": _fmt(value)}
                fracao = fracoes.get(period.isoformat())
                if fracao is not None:
                    dias, dias_no_mes = fracao
                    quantum_fracao = Decimal(1).scaleb(-rule["fraction_scale"])
                    value = (value * Decimal(dias) / Decimal(dias_no_mes)).quantize(
                        quantum_fracao, rounding=_ROUNDING[regime["rounding"]["mode"]])
                    ponto["dias"] = str(dias)
                    ponto["dias_no_mes"] = str(dias_no_mes)
                ponto["value"] = _fmt(value)
                if simples:



                    soma_simples += value
                else:
                    if value <= Decimal(-100):
                        raise AtualizacaoError(
                            "snapshot_invalido", f"{segment_id}: taxa produz fator não positivo")
                    factor = Decimal(1) + (value / Decimal(100))
                    factor_segment *= factor
                    ponto["factor"] = _fmt(factor)
                memory_points.append(ponto)
            if simples:
                factor_segment = Decimal(1) + (soma_simples / Decimal(100))
                if factor_segment <= 0:
                    raise AtualizacaoError(
                        "snapshot_invalido",
                        f"{segment_id}: soma simples das taxas produz fator não positivo")
            factor_total *= factor_segment
            memory_segments.append({
                "id": segment_id,
                "order": rule["order"],
                "series_id": rule["series_id"],
                "operator": rule["operator"],
                "boundary_policy": rule["boundary_policy"],
                "fractional_period_policy": rule["fractional_period_policy"],
                "day_count_basis": rule.get("day_count_basis"),
                "fraction_scale": rule.get("fraction_scale"),
                "acumulacao": "juros_simples" if simples else "capitalizacao_composta",
                "legal_basis": rule["legal_basis"],
                "snapshot_sha256": snapshot_hash,
                "source_url": snapshot["source_url"],
                "source_response_sha256": snapshot["source_response_sha256"],
                "periods": memory_points,
                "factor_segment": _fmt(factor_segment),
            })
        rounding = regime["rounding"]
        quantum = Decimal(1).scaleb(-rounding["scale"])
        updated = (principal * factor_total).quantize(quantum, rounding=_ROUNDING[rounding["mode"]])
        principal_rounded = principal.quantize(quantum, rounding=_ROUNDING[rounding["mode"]])
        difference = (updated - principal_rounded).quantize(quantum, rounding=_ROUNDING[rounding["mode"]])

    return {
        "schema_version": MEMORY_VERSION,
        "status": "MINUTA_PARA_REVISAO",
        "engine_version": ENGINE_VERSION,
        "principal": _fmt(principal),
        "currency": "BRL",
        "data_base": pedido["data_base"],
        "calculation_date": pedido["calculation_date"],
        "regime": {
            "regime_id": regime["regime_id"],
            "name": regime["name"],
            "regime_sha256": regime_hash,
            "legal_source_url": regime["legal_source_url"],
            "legal_source_sha256": regime["legal_source_sha256"],
            "reviewed_by": regime["reviewed_by"],
            "reviewed_role": regime["reviewed_role"],
            "reviewed_at": regime["reviewed_at"],
            "segregation_attested": True,
            "authorization": {
                "authorized_by_lawyer": True,
                "authorized_by": authorization["authorized_by"],
                "scope": authorization["scope"],
                "expires_at": authorization["expires_at"],
                "regime_sha256": authorization["regime_sha256"],
            },
        },
        "rounding": {"scale": rounding["scale"], "mode": rounding["mode"], "applied_once_at_end": True},
        "segments": memory_segments,
        "factor_total": _fmt(factor_total),
        "conditional_updated_value": format(updated, f".{rounding['scale']}f"),
        "conditional_difference": format(difference, f".{rounding['scale']}f"),
        "warnings": _avisos(memory_segments) + avisos_mes_corrente,
    }


def _avisos(segments: list[dict[str, Any]]) -> list[str]:
    'Os avisos da memória descrevem o que ESTE cálculo fez.'





    avisos = [
        "MINUTA PARA REVISÃO: memória condicional ao regime humano anexado.",
        "O motor não escolhe índice, não interpreta a natureza do débito e não afirma valor devido.",
        "Não há interpolação nem conversão automática de operador, unidade ou periodicidade.",
    ]
    simples = sorted(s["id"] for s in segments if s.get("acumulacao") == "juros_simples")
    if simples:
        avisos.append(
            "Acumulação por JUROS SIMPLES, declarada no regime revisado, nos segmentos: "
            + ", ".join(simples)
            + ". As taxas do período se somam; não há capitalização.")
    fracionados = sorted(s["id"] for s in segments
                         if any("dias" in p for p in s.get("periods", [])))
    if fracionados:
        avisos.append(
            "Fração pro rata aplicada nas pontas dos segmentos: " + ", ".join(fracionados)
            + ". A contagem de dias veio do pedido e a base, do regime revisado.")
    else:
        avisos.append("Não há fração de mês: todo período entrou integral.")
    return avisos

























CAPACIDADE_LEI_9430 = "tributo_federal_lei_9430"
PEDIDO_LEI_9430_VERSION = "dsr.atualizacao_monetaria.lei9430.pedido.v1"
MEMORIA_LEI_9430_VERSION = "dsr.memoria_atualizacao.lei9430.v1"
FONTE_LEI_9430 = "https://www.planalto.gov.br/ccivil_03/leis/l9430.htm"
ESCOPO_LEI_9430 = "calculo_lei_9430"
SERIE_SELIC_ACUMULADA_MES = 4390
INICIO_DO_REGIME_9430 = dt.date(1997, 1, 1)
MULTA_POR_DIA = Decimal("0.33")
TETO_DA_MULTA = Decimal("20")
JUROS_NO_MES_DO_PAGAMENTO = Decimal("1")
CENTAVO = Decimal("0.01")





TRECHOS_LEI_9430_ART_61 = (
    "cujos fatos geradores ocorrerem a partir de 1o de janeiro de 1997",
    "trinta e tres centesimos por cento, por dia de atraso",
    "calculada a partir do primeiro dia subsequente ao do vencimento do prazo",
    "limitado a vinte por cento",
    "primeiro dia do mes subsequente ao vencimento do prazo ate o mes anterior ao do pagamento",
    "um por cento no mes de pagamento",
)
TRECHOS_LEI_9430_ART_5 = ("acumulada mensalmente",)
TRECHOS_LEI_9430 = TRECHOS_LEI_9430_ART_61 + TRECHOS_LEI_9430_ART_5


CONFERENCIA_LEI_9430 = {
    "url": FONTE_LEI_9430,
    "conferido_em": "2026-11-16",
    "sha256_da_captura": "3196b769bc152bb88560d6f3f572440cb502c2200501ab496cb3951929a014d6",
    "bytes_da_captura": 565058,
    "dispositivos": ("art. 61, caput", "art. 61, § 1º", "art. 61, § 2º", "art. 61, § 3º",
                     "art. 5º, § 3º"),
}

_ART_61 = (re.compile(r"\bArt\. 61\b"), re.compile(r"\bArt\. 62\b"))
_ART_5 = (re.compile(r"\bArt\. 5o?\b"), re.compile(r"\bArt\. 6o?\b"))
_PEDIDO_9430_KEYS = {
    "schema_version", "principal", "currency", "fato_gerador", "vencimento",
    "inicio_contagem_multa", "pagamento", "legal_source_path", "authorization_path",
    "selic_snapshot_path", "selic_snapshot_sha256",
}


def centavos(valor: Decimal) -> Decimal:
    """Ao centavo, meia unidade para cima, no fim da parcela."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _texto_normalizado(raw: bytes) -> str:
    'Texto vigente da captura, sem tag, sem acento e com espaços colapsados; o texto tachado'

    import html
    import unicodedata
    try:
        texto = raw.decode("utf-8")
    except UnicodeDecodeError:
        texto = raw.decode("cp1252", errors="replace")
    texto = re.sub(r"<(strike|del|s)\b[^>]*>.*?</\1\s*>", " ", texto, flags=re.I | re.S)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto))
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto)
                    if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto)


def _dispositivo(texto: str, marcas: tuple[re.Pattern[str], re.Pattern[str]]) -> str:
    """Recorte do texto entre o cabeçalho do artigo e o do seguinte; vazio se faltar um deles."""
    inicio = marcas[0].search(texto)
    if inicio is None:
        return ""
    fim = marcas[1].search(texto, inicio.end())
    if fim is None:
        return ""
    return texto[inicio.start():fim.start()].casefold()


def _meses_entre(primeiro: dt.date, ultimo: dt.date) -> list[dt.date]:
    meses: list[dt.date] = []
    atual = primeiro
    while atual <= ultimo:
        meses.append(atual)
        atual = _next_month(atual)
    return meses


def calcular_lei_9430(
    pedido: Any,
    *,
    hoje: dt.date | None = None,
    agora: dt.datetime | None = None,
    experimental_authorized: bool = False,
    registro_capacidades: Any = None,
) -> dict[str, Any]:
    'Acréscimos moratórios do art. 61 da Lei 9.430/1996: multa de mora e juros pela Selic.'




    if experimental_authorized is not True:
        raise AtualizacaoError(
            "capacidade_desabilitada",
            "atualização monetária experimental exige autorização explícita nesta execução")
    if agora is None:
        now = (dt.datetime.combine(hoje, dt.time(12, 0), tzinfo=dt.timezone.utc)
               if hoje is not None else dt.datetime.now(dt.timezone.utc))
    elif not isinstance(agora, dt.datetime) or agora.utcoffset() is None:
        raise AtualizacaoError("autorizacao_invalida", "agora deve ser datetime com fuso horário")
    else:
        now = agora.astimezone(dt.timezone.utc)
    today = hoje or now.date()
    try:
        ficha_capacidade.exigir(CAPACIDADE_LEI_9430, hoje=today, registro=registro_capacidades)
    except ficha_capacidade.FichaRecusada as exc:
        raise AtualizacaoError(exc.codigo, exc.mensagem) from None

    if not isinstance(pedido, Mapping):
        raise AtualizacaoError("pedido_invalido", "pedido deve ser objeto")
    erros: list[str] = []
    extras = sorted(set(map(str, pedido)) - _PEDIDO_9430_KEYS)
    if extras:
        erros.append("campos de pedido não permitidos: " + ", ".join(extras))
    if pedido.get("schema_version") != PEDIDO_LEI_9430_VERSION:
        erros.append(f"schema_version deve ser {PEDIDO_LEI_9430_VERSION}")
    if pedido.get("currency") != "BRL":
        erros.append("currency deve ser BRL")
    datas = {nome: _date(pedido.get(nome)) for nome in
             ("fato_gerador", "vencimento", "inicio_contagem_multa", "pagamento")}
    erros.extend(f"{nome} deve ser data AAAA-MM-DD" for nome, valor in datas.items() if valor is None)
    for campo in ("legal_source_path", "authorization_path"):
        if not isinstance(pedido.get(campo), str) or not pedido[campo].strip():
            erros.append(f"{campo} obrigatório")
    if erros:
        raise AtualizacaoError("pedido_invalido", erros)
    principal = _decimal(pedido.get("principal"), "principal", positive=True)
    if principal != principal.quantize(CENTAVO):
        raise AtualizacaoError("principal_fora_do_centavo",
                               "o valor principal do débito deve vir em reais e centavos")
    fato, venc, inicio, pagto = (datas["fato_gerador"], datas["vencimento"],
                                 datas["inicio_contagem_multa"], datas["pagamento"])
    if not (fato and venc and inicio and pagto):
        raise AtualizacaoError("pedido_invalido", ["datas do regime incompletas"])
    if fato < INICIO_DO_REGIME_9430:
        raise AtualizacaoError(
            "fato_gerador_anterior_a_1997",
            "o art. 61 da Lei 9.430/1996 vale para fato gerador a partir de 01/01/1997")
    if pagto <= venc:
        raise AtualizacaoError("sem_atraso", "pagamento até o vencimento não tem acréscimo moratório")
    if not venc < inicio <= pagto:
        raise AtualizacaoError(
            "inicio_contagem_invalido",
            "o primeiro dia da contagem da multa tem de cair depois do vencimento e até o pagamento")

    legal_path = _regular_file(pedido["legal_source_path"], outside_git=True)
    if legal_path is None:
        raise AtualizacaoError("fonte_juridica_invalida", "captura da fonte jurídica ausente ou insegura")
    legal_raw = Path(legal_path).read_bytes()
    legal_hash = hashlib.sha256(legal_raw).hexdigest()
    texto = _texto_normalizado(legal_raw)
    art_61, art_5 = _dispositivo(texto, _ART_61), _dispositivo(texto, _ART_5)
    faltam = ([f"art. 61: {t}" for t in TRECHOS_LEI_9430_ART_61 if t not in art_61]
              + [f"art. 5º: {t}" for t in TRECHOS_LEI_9430_ART_5 if t not in art_5])
    if faltam:
        raise AtualizacaoError(
            "fonte_juridica_divergente",
            "a captura da fonte não traz o texto do art. 61 (e do art. 5º, § 3º) que este cálculo "
            "executa; confira se a lei mudou: " + "; ".join(faltam))
    authorization = _load_authorization(pedido["authorization_path"], legal_hash, agora=now,
                                        escopo=ESCOPO_LEI_9430)

    venc_mes = dt.date(venc.year, venc.month, 1)
    pagto_mes = dt.date(pagto.year, pagto.month, 1)
    meses = _meses_entre(_next_month(venc_mes), dt.date(
        pagto_mes.year - (pagto_mes.month == 1), 12 if pagto_mes.month == 1 else pagto_mes.month - 1, 1))
    pontos_selic: list[dict[str, str]] = []
    snapshot_hash = None
    soma = Decimal(0)
    with localcontext() as contexto:
        contexto.prec = 50
        if meses:
            caminho = pedido.get("selic_snapshot_path")
            esperado = pedido.get("selic_snapshot_sha256")
            if not isinstance(caminho, str) or not isinstance(esperado, str) or not _SHA256.fullmatch(esperado):
                raise AtualizacaoError(
                    "pedido_invalido",
                    "há meses de Selic entre o vencimento e o pagamento: informe "
                    "selic_snapshot_path e selic_snapshot_sha256 da série 4390")
            snapshot, snapshot_hash, _ = _load_file(caminho)
            if snapshot_hash.casefold() != esperado.casefold():
                raise AtualizacaoError("hash_divergente", "selic_snapshot_sha256 diverge do arquivo")
            if snapshot.get("series_id") != SERIE_SELIC_ACUMULADA_MES:
                raise AtualizacaoError(
                    "serie_divergente",
                    "os juros do art. 61 usam a Selic acumulada no mês (série 4390 do SGS)")
            isos = [m.isoformat() for m in meses]
            nao_fechado = bcb_sgs_adapter.mes_nao_fechado(snapshot, isos)
            if nao_fechado:
                raise AtualizacaoError("mes_nao_fechado", nao_fechado)
            erros_snap = bcb_sgs_adapter.validar_snapshot(snapshot, hoje=today)
            if erros_snap:
                raise AtualizacaoError("snapshot_invalido", erros_snap)
            mapa = {p.get("period"): p.get("value") for p in snapshot.get("points", [])
                    if isinstance(p, Mapping)}
            ausentes = [m for m in isos if m not in mapa]
            if ausentes:
                raise AtualizacaoError("cobertura_incompleta",
                                       "meses de Selic ausentes do snapshot: " + ", ".join(ausentes))
            for iso in isos:
                valor = Decimal(str(mapa[iso]))
                soma += valor
                pontos_selic.append({"period": iso, "value": _fmt(valor)})
        juros_pct = soma + (JUROS_NO_MES_DO_PAGAMENTO if pagto_mes > venc_mes else Decimal(0))
        dias = (pagto - inicio).days + 1
        multa_apurada = MULTA_POR_DIA * dias
        multa_pct = min(multa_apurada, TETO_DA_MULTA)
        multa = centavos(principal * multa_pct / 100)
        juros = centavos(principal * juros_pct / 100)
        total = principal + multa + juros

    avisos = [
        "MINUTA PARA REVISÃO: acréscimos moratórios do art. 61 da Lei 9.430/1996, para débito "
        "federal administrado pela Receita Federal; não afirma valor devido.",
        f"Multa de mora contada de {inicio:%d/%m/%Y} a {pagto:%d/%m/%Y} ({dias} dias), dia inicial "
        "informado no pedido. A lei fala em primeiro dia subsequente ao vencimento; a orientação "
        "da Receita Federal conta do primeiro dia útil seguinte. Confira o dia inicial e o próprio "
        "vencimento, que o cálculo não ajusta por feriado.",
        "Juros pela soma das taxas mensais da Selic do mês seguinte ao vencimento até o mês "
        "anterior ao pagamento, mais 1% no mês do pagamento, sem capitalização.",
        "Arredondamento: cada parcela ao centavo, com a metade do centavo para cima, só ao fim "
        "da conta dela; o total soma as parcelas já arredondadas.",
    ]
    if pagto_mes == venc_mes:
        avisos.append("Pagamento no próprio mês do vencimento: sem juros de mora, como orienta a "
                      "Receita Federal; só a multa de mora.")
    if pagto > today:
        avisos.append(f"Pagamento em {pagto:%d/%m/%Y}, depois de hoje ({today:%d/%m/%Y}): o "
                      "cálculo é simulação. Os dias de multa e o 1% do mês do pagamento valem só "
                      "se o pagamento sair nessa data; refaça a conta na data real.")
    if (inicio - venc).days > 4:
        avisos.append(f"O dia inicial da multa fica {(inicio - venc).days} dias depois do "
                      "vencimento: confira se não há erro na data.")
    pendencias = [
        "==[MULTA DE OFÍCIO A CONFERIR]== Se houve lançamento de ofício, a multa de ofício e os "
        "juros sobre ela não entram neste cálculo.",
        "==[ENCARGO LEGAL A CONFERIR]== Inscrito o débito em dívida ativa, o encargo legal não "
        "entra neste cálculo.",
        "==[REGIME ESPECIAL A CONFERIR]== Parcelamento, denúncia espontânea, transação ou decisão "
        "judicial podem alterar os acréscimos.",
    ]
    return {
        "schema_version": MEMORIA_LEI_9430_VERSION,
        "status": "MINUTA_PARA_REVISAO",
        "engine_version": ENGINE_VERSION,
        "regime": {
            "nome": "Acréscimos moratórios de débito federal (Lei 9.430/1996, art. 61)",
            "fonte_oficial": FONTE_LEI_9430,
            "conferida_em": "2026-11-16",
            "legal_source_sha256": legal_hash,
            "authorization": {
                "authorized_by_lawyer": True,
                "authorized_by": authorization["authorized_by"],
                "scope": authorization["scope"],
                "expires_at": authorization["expires_at"],
            },
        },
        "principal": format(principal, ".2f"),
        "currency": "BRL",
        "fato_gerador": fato.isoformat(),
        "vencimento": venc.isoformat(),
        "pagamento": pagto.isoformat(),
        "multa_de_mora": {
            "inicio_contagem": inicio.isoformat(),
            "dias_de_atraso": dias,
            "percentual_por_dia": _fmt(MULTA_POR_DIA),
            "percentual_apurado": _fmt(multa_apurada),
            "percentual_aplicado": _fmt(multa_pct),
            "teto_aplicado": multa_apurada > TETO_DA_MULTA,
            "valor": format(multa, ".2f"),
        },
        "juros_de_mora": {
            "serie_selic": SERIE_SELIC_ACUMULADA_MES,
            "selic_snapshot_sha256": snapshot_hash,
            "meses_selic": pontos_selic,
            "soma_selic": _fmt(soma),
            "mes_do_pagamento": _fmt(juros_pct - soma),
            "percentual": _fmt(juros_pct),
            "valor": format(juros, ".2f"),
        },
        "total": format(total, ".2f"),
        "arredondamento": {"escala": 2, "modo": "ROUND_HALF_UP", "momento": "fim_de_cada_parcela"},
        "avisos": avisos,
        "pendencias": pendencias,
    }


def _load_request(value: str) -> Mapping[str, Any] | None:
    try:
        if value == "-":
            payload = _safe_json_loads(sys.stdin.read())
        else:
            resolved = _regular_file(value, outside_git=True)
            if resolved is None:
                return None
            payload = _safe_json_loads(Path(resolved).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Memória condicional de atualização monetária")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-regime")
    validate.add_argument("--request", required=True, help="regime JSON fora de Git; use - para stdin")
    calculate = sub.add_parser("calculate")
    calculate.add_argument("--request", required=True, help="pedido JSON fora de Git; use - para stdin")
    lei_9430 = sub.add_parser("calculate-lei-9430",
                              help="acréscimos moratórios do art. 61 da Lei 9.430/1996 (ficha própria)")
    lei_9430.add_argument("--request", required=True, help="pedido JSON fora de Git; use - para stdin")
    args = parser.parse_args(argv)
    payload = _load_request(args.request)
    if payload is None:
        print(json.dumps({"ok": False, "error_code": "entrada_invalida"}, ensure_ascii=False))
        return 2
    if args.command == "validate-regime":
        errors = validar_regime(payload)
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False))
        return 0 if not errors else 2
    authorized = os.environ.get("DSR_ATUALIZACAO_MONETARIA_EXPERIMENTAL") == "1"
    try:
        rota = calcular_lei_9430 if args.command == "calculate-lei-9430" else calcular
        memory = rota(payload, experimental_authorized=authorized)
        print(json.dumps({"ok": True, "memory": memory}, ensure_ascii=False, allow_nan=False))
        return 0
    except AtualizacaoError as exc:
        print(json.dumps({
            "ok": False,
            "error_code": exc.code,
            "errors": exc.errors,
            "status": "INCONCLUSIVO",
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
