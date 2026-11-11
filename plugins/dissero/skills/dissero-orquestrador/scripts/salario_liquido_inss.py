#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Memória condicional de salário após INSS progressivo (RGPS).'







from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
from ficha_capacidade import FichaRecusada, exigir as exigir_ficha

CAPACIDADE = "salario_liquido_inss"
ENGINE_VERSION = "dsr.salario_liquido_inss.engine.v1"
TABLE_VERSION = "dsr.tabela_inss.v1"
REQUEST_VERSION = "dsr.salario_liquido_inss.pedido.v1"
AUTH_VERSION = "dsr.salario_liquido_inss.autorizacao.v1"
MEMORY_VERSION = "dsr.memoria_salario_liquido_inss.v1"
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
MONTH = re.compile(r"^[0-9]{4}-[0-9]{2}-01$")



HORA_FUSO = re.compile(r"(?P<hora>[0-9]{2}:[0-9]{2}(?P<seg>:[0-9]{2})?)"
                       r"(?(seg)(?:[.,](?P<fracao>[0-9]{1,6})[0-9]*)?)"
                       r"(?P<fuso>[+-][0-9]{2})(?::?(?P<min>[0-9]{2}))?\Z")
OFFICIAL_SUFFIXES = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")
ROUNDING = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN, "ROUND_DOWN": ROUND_DOWN}

class SalarioLiquidoError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))

def _reject_constant(value: str) -> None:
    raise ValueError(value)

def _load_json(path: Any) -> tuple[dict[str, Any], str]:
    if not isinstance(path, (str, os.PathLike)):
        raise SalarioLiquidoError("arquivo_invalido", "caminho local obrigatório")
    original = os.path.abspath(os.fspath(path))
    resolved = os.path.realpath(original)
    if os.path.islink(original) or not os.path.isfile(resolved):
        raise SalarioLiquidoError("arquivo_invalido", "arquivo local ausente ou inseguro")
    current = resolved
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            raise SalarioLiquidoError("arquivo_invalido", "tabelas e autorizações não podem estar dentro de Git")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    try:
        raw = Path(resolved).read_bytes()
        value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise SalarioLiquidoError("arquivo_invalido", "arquivo JSON local ilegível") from exc
    if not isinstance(value, dict):
        raise SalarioLiquidoError("arquivo_invalido", "arquivo JSON deve conter objeto")
    return value, hashlib.sha256(raw).hexdigest()

def _date(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None

def _month(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not MONTH.fullmatch(value):
        return None
    return _date(value)

def _datetime(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    hora = HORA_FUSO.search(candidate)
    if hora:
        fracao = dt.datetime.strptime(hora["fracao"], "%f").strftime(".%f") if hora["fracao"] else ""
        candidate = candidate[:hora.start()] + hora["hora"] + fracao + hora["fuso"] + ":%02d" % int(hora["min"] or 0)
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo and parsed.utcoffset() is not None else None

def _official_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and bool(host) and any(host.endswith(x) for x in OFFICIAL_SUFFIXES) and not parsed.username and not parsed.password and not parsed.fragment

def _decimal(value: Any, field: str, *, nonnegative: bool = False, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise SalarioLiquidoError("entrada_invalida", f"{field} deve ser decimal canônico em string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise SalarioLiquidoError("entrada_invalida", f"{field} inválido") from exc
    if not result.is_finite() or (nonnegative and result < 0) or (positive and result <= 0):
        raise SalarioLiquidoError("entrada_invalida", f"{field} fora do domínio")
    return result

def _fmt(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text

def _unknown(value: Mapping[str, Any], allowed: set[str], prefix: str) -> list[str]:
    return [f"{prefix} contém campo não permitido: {key}" for key in value if key not in allowed]

def validar_tabela(table: Any, *, hoje: dt.date | None = None) -> list[str]:
    if not isinstance(table, Mapping):
        return ["tabela deve ser objeto"]
    allowed = {"schema_version", "table_id", "name", "legal_source_url", "legal_source_sha256", "valid_from", "valid_to", "extracted_at", "reviewed_by", "reviewed_role", "reviewed_at", "segregation_attested", "rounding", "covered_categories", "faixas", "teto_salario_contribuicao"}
    errors = _unknown(table, allowed, "tabela")
    if table.get("schema_version") != TABLE_VERSION: errors.append(f"schema_version deve ser {TABLE_VERSION}")
    if not isinstance(table.get("table_id"), str) or not ID.fullmatch(str(table.get("table_id"))): errors.append("table_id inválido")
    for field in ("name", "reviewed_by"):
        if not isinstance(table.get(field), str) or not table[field].strip(): errors.append(f"{field} obrigatório")
    if not _official_url(table.get("legal_source_url")): errors.append("legal_source_url deve ser HTTPS oficial")
    if not isinstance(table.get("legal_source_sha256"), str) or not SHA256.fullmatch(table["legal_source_sha256"]): errors.append("legal_source_sha256 inválido")
    if table.get("reviewed_role") != "advogado": errors.append("reviewed_role deve ser advogado")
    if table.get("segregation_attested") is not True: errors.append("segregation_attested=true é obrigatório")
    today = hoje or dt.date.today()
    start, end, extracted, reviewed = (_date(table.get(k)) for k in ("valid_from", "valid_to", "extracted_at", "reviewed_at"))
    if start is None or end is None or start > end or not start <= today <= end: errors.append("vigência da tabela inválida, ausente ou vencida")
    if extracted is None or extracted > today: errors.append("extracted_at inválido ou futuro")
    if reviewed is None or reviewed > today: errors.append("reviewed_at inválido ou futuro")
    rounding = table.get("rounding")
    if not isinstance(rounding, Mapping) or set(rounding) != {"scale", "mode"} or isinstance(rounding.get("scale"), bool) or not isinstance(rounding.get("scale"), int) or not 0 <= rounding["scale"] <= 8 or rounding.get("mode") not in ROUNDING: errors.append("rounding inválido")
    categories = table.get("covered_categories")
    if not isinstance(categories, list) or not categories or any(not isinstance(x, str) for x in categories): errors.append("covered_categories inválido")
    try: ceiling = _decimal(table.get("teto_salario_contribuicao"), "teto_salario_contribuicao", positive=True)
    except SalarioLiquidoError as exc: errors.extend(exc.errors); ceiling = None
    brackets = table.get("faixas")
    if not isinstance(brackets, list) or not brackets: return errors + ["faixas deve ser lista não vazia"]
    previous = Decimal(0)
    for index, bracket in enumerate(brackets):
        prefix = f"faixas[{index}]"
        if not isinstance(bracket, Mapping) or set(bracket) != {"faixa_index", "limite_inferior", "limite_superior_exclusivo", "aliquota"}: errors.append(f"{prefix} inválida"); continue
        if bracket.get("faixa_index") != index + 1: errors.append(f"{prefix}.faixa_index inválido")
        try: lower = _decimal(bracket.get("limite_inferior"), f"{prefix}.limite_inferior", nonnegative=True); upper = _decimal(bracket.get("limite_superior_exclusivo"), f"{prefix}.limite_superior_exclusivo", positive=True); rate = _decimal(bracket.get("aliquota"), f"{prefix}.aliquota", nonnegative=True)
        except SalarioLiquidoError as exc: errors.extend(exc.errors); continue
        if lower != previous or upper <= lower or rate > 1: errors.append(f"{prefix}: faixas devem ser contíguas e ordenadas")
        previous = upper
    if ceiling is not None and previous != ceiling + Decimal("0.01"): errors.append("última faixa deve cobrir até o teto + 1 centavo")
    return errors

def validar_pedido(request: Any, *, hoje: dt.date | None = None) -> list[str]:
    if not isinstance(request, Mapping): return ["pedido deve ser objeto"]
    allowed = {"schema_version", "table_path", "table_sha256", "authorization_path", "months"}
    errors = _unknown(request, allowed, "pedido")
    if request.get("schema_version") != REQUEST_VERSION: errors.append(f"schema_version deve ser {REQUEST_VERSION}")
    if not isinstance(request.get("table_path"), str) or not request["table_path"].strip(): errors.append("table_path obrigatório")
    if not isinstance(request.get("authorization_path"), str) or not request["authorization_path"].strip(): errors.append("authorization_path obrigatório")
    if not isinstance(request.get("table_sha256"), str) or not SHA256.fullmatch(request["table_sha256"]): errors.append("table_sha256 inválido")
    months = request.get("months")
    if not isinstance(months, list) or not months: return errors + ["months deve ser lista não vazia"]
    previous = None
    for index, month in enumerate(months):
        prefix = f"months[{index}]"
        if not isinstance(month, Mapping): errors.append(f"{prefix} deve ser objeto"); continue
        allowed_month = {"competencia", "verbas_remuneratorias", "verbas_indenizatorias", "outros_salarios_contribuicao_mes", "outros_descontos_inss_mes", "tipo"}
        errors.extend(_unknown(month, allowed_month, prefix))
        period = _month(month.get("competencia"))
        if period is None or (previous is not None and period <= previous): errors.append(f"{prefix}.competencia deve ser mensal, única e ordenada")
        previous = period
        if month.get("tipo") != "mensal": errors.append(f"{prefix}.tipo deve ser mensal; 13º e rescisão não são suportados nesta versão")
        for field in ("verbas_remuneratorias", "verbas_indenizatorias"):
            values = month.get(field)
            if not isinstance(values, list) or not values: errors.append(f"{prefix}.{field} deve ser lista não vazia")
            else:
                for value in values:
                    try: _decimal(value, f"{prefix}.{field}", nonnegative=True)
                    except SalarioLiquidoError as exc: errors.extend(exc.errors)
        for field in ("outros_salarios_contribuicao_mes", "outros_descontos_inss_mes"):
            try: _decimal(month.get(field), f"{prefix}.{field}", nonnegative=True)
            except SalarioLiquidoError as exc: errors.extend(exc.errors)
    return errors

def _authorize(path: Any, table_hash: str, now: dt.datetime) -> None:
    auth, _ = _load_json(path)
    errors = []
    if set(auth) != {"schema_version", "authorized_by_lawyer", "scope", "table_sha256", "expires_at", "authorized_by"}: errors.append("autorização contém campos não permitidos")
    if auth.get("schema_version") != AUTH_VERSION: errors.append(f"schema_version deve ser {AUTH_VERSION}")
    if auth.get("authorized_by_lawyer") is not True or auth.get("scope") != "calculo_experimental": errors.append("autorização jurídica experimental inválida")
    if not isinstance(auth.get("table_sha256"), str) or not SHA256.fullmatch(auth["table_sha256"]) or auth["table_sha256"].casefold() != table_hash.casefold(): errors.append("autorização não corresponde à tabela")
    expires = _datetime(auth.get("expires_at"))
    if expires is None or expires <= now: errors.append("autorização ausente, inválida ou vencida")
    if not isinstance(auth.get("authorized_by"), str) or len(auth["authorized_by"].strip()) < 3: errors.append("authorized_by inválido")
    if errors: raise SalarioLiquidoError("autorizacao_invalida", errors)

def _progressive(base: Decimal, table: Mapping[str, Any]) -> tuple[Decimal, list[dict[str, str]]]:
    ceiling = _decimal(table["teto_salario_contribuicao"], "teto_salario_contribuicao", positive=True)
    applied = min(base, ceiling)
    total = Decimal(0)
    breakdown = []
    for bracket in table["faixas"]:
        lower = _decimal(bracket["limite_inferior"], "limite_inferior")
        upper = _decimal(bracket["limite_superior_exclusivo"], "limite_superior_exclusivo")
        rate = _decimal(bracket["aliquota"], "aliquota")
        portion = max(Decimal(0), min(applied, upper) - lower)
        contribution = portion * rate
        if portion:
            breakdown.append({"faixa_index": str(bracket["faixa_index"]), "base_na_faixa": _fmt(portion), "aliquota": _fmt(rate), "contribuicao_faixa": _fmt(contribution)})
        total += contribution
    return total, breakdown

def calcular(request: Any, *, hoje: dt.date | None = None, agora: dt.datetime | None = None, experimental_authorized: bool = False, registro_capacidades: Any = None) -> dict[str, Any]:
    'Memória condicional. `registro_capacidades` (dict ou caminho) substitui o registro'

    if experimental_authorized is not True: raise SalarioLiquidoError("capacidade_desabilitada", "salário líquido e INSS experimental exige autorização explícita nesta execução")
    now = agora or dt.datetime.combine(hoje or dt.date.today(), dt.time(12), tzinfo=dt.timezone.utc)
    now = now.astimezone(dt.timezone.utc) if now.tzinfo and now.utcoffset() is not None else now
    today = hoje or now.date()
    try:
        exigir_ficha(CAPACIDADE, hoje=today, registro=registro_capacidades)
    except FichaRecusada as exc:
        raise SalarioLiquidoError(exc.codigo, exc.mensagem) from None
    errors = validar_pedido(request, hoje=today)
    if errors: raise SalarioLiquidoError("pedido_invalido", errors)
    table, table_hash = _load_json(request["table_path"])
    if table_hash.casefold() != request["table_sha256"].casefold(): raise SalarioLiquidoError("hash_divergente", "table_sha256 diverge do arquivo")
    _authorize(request["authorization_path"], table_hash, now)
    table_errors = validar_tabela(table, hoje=today)
    if table_errors: raise SalarioLiquidoError("tabela_invalida", table_errors)
    rounding = table["rounding"]; quantum = Decimal(1).scaleb(-rounding["scale"]); memories = []
    totals = {"remuneratorio": Decimal(0), "indenizatorio": Decimal(0), "base_inss": Decimal(0), "desconto_inss": Decimal(0)}
    with localcontext() as context:
        context.prec = 60
        for month in request["months"]:
            competence = month["competencia"]
            if not table["valid_from"] <= competence <= table["valid_to"]: raise SalarioLiquidoError("cobertura_ausente", f"tabela sem cobertura para {competence}")
            remun = sum((_decimal(x, f"{competence}.verbas_remuneratorias", nonnegative=True) for x in month["verbas_remuneratorias"]), Decimal(0))
            inden = sum((_decimal(x, f"{competence}.verbas_indenizatorias", nonnegative=True) for x in month["verbas_indenizatorias"]), Decimal(0))
            other_base = _decimal(month["outros_salarios_contribuicao_mes"], f"{competence}.outros_salarios_contribuicao_mes", nonnegative=True)
            other_paid = _decimal(month["outros_descontos_inss_mes"], f"{competence}.outros_descontos_inss_mes", nonnegative=True)
            aggregate = remun + other_base
            aggregate_contribution, breakdown = _progressive(aggregate, table)
            own_contribution = max(Decimal(0), aggregate_contribution - other_paid)
            own_contribution = own_contribution.quantize(quantum, rounding=ROUNDING[rounding["mode"]])
            base = min(aggregate, _decimal(table["teto_salario_contribuicao"], "teto_salario_contribuicao"))
            net = remun + inden - own_contribution
            for key, value in (("remuneratorio", remun), ("indenizatorio", inden), ("base_inss", base), ("desconto_inss", own_contribution)): totals[key] += value
            memories.append({"competencia": competence, "salario_remuneratorio": _fmt(remun), "verbas_indenizatorias": _fmt(inden), "outros_salarios_contribuicao_mes": _fmt(other_base), "outros_descontos_inss_mes": _fmt(other_paid), "base_calculo_inss_agregada": _fmt(base), "decomposicao_faixas_agregada": breakdown, "desconto_inss_deste_vinculo": _fmt(own_contribution), "salario_liquido_apos_inss": _fmt(net)})
    return {"schema_version": MEMORY_VERSION, "status": "MINUTA_PARA_REVISAO", "engine_version": ENGINE_VERSION, "resumo": {"total_remuneratorio": _fmt(totals["remuneratorio"]), "total_indenizatorio": _fmt(totals["indenizatorio"]), "total_base_inss": _fmt(totals["base_inss"]), "total_desconto_inss": _fmt(totals["desconto_inss"]), "total_liquido_apos_inss": _fmt(totals["remuneratorio"] + totals["indenizatorio"] - totals["desconto_inss"])}, "tabela": {"table_id": table["table_id"], "name": table["name"], "table_sha256": table_hash, "legal_source_url": table["legal_source_url"], "legal_source_sha256": table["legal_source_sha256"], "valid_from": table["valid_from"], "valid_to": table["valid_to"], "reviewed_by": table["reviewed_by"]}, "months": memories, "warnings": ["MINUTA_PARA_REVISAO: cálculo condicional para conferência do advogado.", "O motor calcula somente INSS/RGPS sobre as rubricas classificadas no pedido; não calcula IRRF nem interpreta natureza jurídica.", "Múltiplos vínculos exigem base e desconto já recolhido informados para a mesma competência.", "13º, rescisão, RRA e outras modalidades não são suportados nesta versão."]}

class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None: raise SalarioLiquidoError("argumentos_invalidos", message)

def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(prog="salario_liquido_inss.py"); parser.add_argument("--request", required=True); args = parser.parse_args(argv)
        request, _ = _load_json(args.request)
        if os.environ.get("DSR_SALARIO_LIQUIDO_EXPERIMENTAL") != "1": raise SalarioLiquidoError("capacidade_desabilitada", "DSR_SALARIO_LIQUIDO_EXPERIMENTAL=1 é obrigatório")
        result = calcular(request, experimental_authorized=True)
    except (SalarioLiquidoError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "status": "INCONCLUSIVO", "error_code": getattr(exc, "code", "falha"), "errors": getattr(exc, "errors", [str(exc)])}, ensure_ascii=False, sort_keys=True)); return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
