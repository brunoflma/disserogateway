#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Memória condicional de horas extras e reflexos.'







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


CAPACIDADE = "horas_extras"
ENGINE_VERSION = "dsr.horas_extras.engine.v1"
DECISION_VERSION = "dsr.horas_extras.decisao.v1"
REQUEST_VERSION = "dsr.horas_extras.pedido.v1"
AUTH_VERSION = "dsr.horas_extras.autorizacao.v1"
MEMORY_VERSION = "dsr.memoria_horas_extras.v1"
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PERIOD = re.compile(r"^[0-9]{4}-[0-9]{2}-01$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")



HORA_FUSO = re.compile(r"(?P<hora>[0-9]{2}:[0-9]{2}(?P<seg>:[0-9]{2})?)"
                       r"(?(seg)(?:[.,](?P<fracao>[0-9]{1,6})[0-9]*)?)"
                       r"(?P<fuso>[+-][0-9]{2})(?::?(?P<min>[0-9]{2}))?\Z")
OFFICIAL_SUFFIXES = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")
ROUNDING = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN, "ROUND_DOWN": ROUND_DOWN}


class HorasExtrasError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def _reject_constant(value: str) -> None:
    raise ValueError(f"constante JSON inválida: {value}")


def _load_json(path: Any) -> tuple[dict[str, Any], str]:
    if not isinstance(path, (str, os.PathLike)):
        raise HorasExtrasError("arquivo_invalido", "caminho local obrigatório")
    original = os.path.abspath(os.fspath(path))
    resolved = os.path.realpath(original)
    if os.path.islink(original) or not os.path.isfile(resolved):
        raise HorasExtrasError("arquivo_invalido", "arquivo local ausente ou inseguro")
    current = resolved
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            raise HorasExtrasError("arquivo_invalido", "arquivos de decisão não podem estar dentro de Git")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    try:
        raw = Path(resolved).read_bytes()
        value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise HorasExtrasError("arquivo_invalido", "arquivo JSON local ilegível") from exc
    if not isinstance(value, dict):
        raise HorasExtrasError("arquivo_invalido", "arquivo JSON deve conter objeto")
    return value, hashlib.sha256(raw).hexdigest()


def _date(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _period(value: Any) -> dt.date | None:
    parsed = _date(value)
    return parsed if parsed is not None and parsed.day == 1 else None


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
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").casefold()
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(host) and any(host.endswith(s) for s in OFFICIAL_SUFFIXES) and not parsed.username and not parsed.password and not parsed.fragment


def _decimal(value: Any, field: str, *, nonnegative: bool = False, positive: bool = False) -> Decimal:




    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise HorasExtrasError("entrada_invalida", f"{field} deve ser decimal canônico em string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise HorasExtrasError("entrada_invalida", f"{field} inválido") from exc
    if not result.is_finite() or (nonnegative and result < 0) or (positive and result <= 0):
        raise HorasExtrasError("entrada_invalida", f"{field} fora do domínio")
    return result


def _fmt(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _unknown(value: Mapping[str, Any], allowed: set[str], prefix: str) -> list[str]:
    return [f"{prefix} contém campo não permitido: {key}" for key in value if key not in allowed]


def validar_decisao(decisao: Any, *, hoje: dt.date | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(decisao, Mapping):
        return ["decisão deve ser objeto"]
    allowed = {"schema_version", "decision_id", "name", "legal_source_url", "legal_source_sha256", "review_valid_from", "review_valid_to", "reviewed_by", "reviewed_role", "reviewed_at", "segregation_attested", "rounding", "monthly_rules"}
    errors.extend(_unknown(decisao, allowed, "decisão"))
    if decisao.get("schema_version") != DECISION_VERSION:
        errors.append(f"schema_version deve ser {DECISION_VERSION}")
    if not isinstance(decisao.get("decision_id"), str) or not ID.fullmatch(str(decisao.get("decision_id"))):
        errors.append("decision_id inválido")
    if not isinstance(decisao.get("name"), str) or not decisao["name"].strip():
        errors.append("name obrigatório")
    if not _official_url(decisao.get("legal_source_url")):
        errors.append("legal_source_url deve ser HTTPS oficial")
    if not isinstance(decisao.get("legal_source_sha256"), str) or not SHA256.fullmatch(decisao["legal_source_sha256"]):
        errors.append("legal_source_sha256 inválido")
    if decisao.get("reviewed_role") != "advogado":
        errors.append("reviewed_role deve ser advogado")
    if decisao.get("segregation_attested") is not True:
        errors.append("segregation_attested=true é obrigatório")
    today = hoje or dt.date.today()
    start, end, reviewed = (_date(decisao.get(k)) for k in ("review_valid_from", "review_valid_to", "reviewed_at"))
    if start is None or end is None or start > end or not start <= today <= end:
        errors.append("vigência da decisão inválida, ausente ou vencida")
    if reviewed is None or reviewed > today:
        errors.append("reviewed_at inválido ou futuro")
    rounding = decisao.get("rounding")
    if not isinstance(rounding, Mapping) or set(rounding) != {"scale", "mode"}:
        errors.append("rounding deve declarar scale e mode")
    elif isinstance(rounding.get("scale"), bool) or not isinstance(rounding.get("scale"), int) or not 0 <= rounding["scale"] <= 8 or rounding.get("mode") not in ROUNDING:
        errors.append("rounding inválido")
    rules = decisao.get("monthly_rules")
    if not isinstance(rules, list) or not rules:
        errors.append("monthly_rules deve ser lista não vazia")
        return errors
    seen: set[str] = set()
    for index, rule in enumerate(rules):
        prefix = f"monthly_rules[{index}]"
        if not isinstance(rule, Mapping):
            errors.append(f"{prefix} deve ser objeto")
            continue
        allowed_rule = {"competencia", "divisor", "he_rates", "night_rule", "interval_rule", "reflex_rules", "dsr_rule"}
        errors.extend(_unknown(rule, allowed_rule, prefix))




        dsr_rule = rule.get("dsr_rule")
        if dsr_rule is not None and (not isinstance(dsr_rule, Mapping) or set(dsr_rule) != {"enabled"}
                                     or not isinstance(dsr_rule.get("enabled"), bool)):
            errors.append(f"{prefix}.dsr_rule deve declarar somente enabled (booleano)")
        competencia = _period(rule.get("competencia"))
        if competencia is None or competencia.isoformat() in seen:
            errors.append(f"{prefix}.competencia inválida ou duplicada")
        elif competencia is not None:
            seen.add(competencia.isoformat())
        try:
            _decimal(rule.get("divisor"), f"{prefix}.divisor", positive=True)
        except HorasExtrasError as exc:
            errors.extend(exc.errors)
        rates = rule.get("he_rates")
        if not isinstance(rates, Mapping) or set(rates) != {"he_50", "he_100"}:
            errors.append(f"{prefix}.he_rates deve declarar he_50 e he_100")
        else:
            for key in ("he_50", "he_100"):
                try:
                    _decimal(rates.get(key), f"{prefix}.he_rates.{key}", nonnegative=True)
                except HorasExtrasError as exc:
                    errors.extend(exc.errors)
        night = rule.get("night_rule")
        if not isinstance(night, Mapping) or set(night) != {"enabled", "hour_factor", "additional_rate"}:
            errors.append(f"{prefix}.night_rule deve declarar enabled, hour_factor e additional_rate")
        else:
            if not isinstance(night.get("enabled"), bool):
                errors.append(f"{prefix}.night_rule.enabled inválido")
            for key in ("hour_factor", "additional_rate"):
                try:
                    _decimal(night.get(key), f"{prefix}.night_rule.{key}", nonnegative=True)
                except HorasExtrasError as exc:
                    errors.extend(exc.errors)
        interval = rule.get("interval_rule")
        if not isinstance(interval, Mapping) or set(interval) != {"enabled", "additional_rate", "nature"}:
            errors.append(f"{prefix}.interval_rule deve declarar enabled, additional_rate e nature")
        else:
            if not isinstance(interval.get("enabled"), bool) or interval.get("nature") not in {"salarial", "indenizatoria"}:
                errors.append(f"{prefix}.interval_rule inválida")
            try:
                _decimal(interval.get("additional_rate"), f"{prefix}.interval_rule.additional_rate", nonnegative=True)
            except HorasExtrasError as exc:
                errors.extend(exc.errors)
        reflex = rule.get("reflex_rules")
        if not isinstance(reflex, list):
            errors.append(f"{prefix}.reflex_rules deve ser lista")
            continue
        nodes = set()
        for node_index, node in enumerate(reflex):
            np = f"{prefix}.reflex_rules[{node_index}]"
            if not isinstance(node, Mapping) or set(node) != {"id", "sources", "rate"}:
                errors.append(f"{np} deve declarar id, sources e rate")
                continue
            node_id = node.get("id")
            if not isinstance(node_id, str) or not ID.fullmatch(node_id) or node_id in nodes:
                errors.append(f"{np}.id inválido ou duplicado")
            nodes.add(str(node_id))
            if not isinstance(node.get("sources"), list) or not node["sources"] or any(not isinstance(x, str) for x in node["sources"]):
                errors.append(f"{np}.sources inválido")
            try:
                _decimal(node.get("rate"), f"{np}.rate", nonnegative=True)
            except HorasExtrasError as exc:
                errors.extend(exc.errors)
        if isinstance(reflex, list):



            known = {"he_50", "he_100", "night", "interval", "dsr"}
            for node_index, node in enumerate(reflex):
                if isinstance(node, Mapping):
                    sources = node.get("sources")
                    for source in sources if isinstance(sources, list) else []:
                        if not isinstance(source, str) or source in known:
                            continue

                        if source in nodes:
                            errors.append(f"{prefix}.reflex_rules[{node_index}]: reflex source {source} "
                                          "é reflexo declarado depois deste (ou é ele mesmo); declare a "
                                          "fonte antes de quem a usa")
                        else:
                            errors.append(f"{prefix}: reflex source desconhecido: {source}")
                    known.add(str(node.get("id")))
    return errors


def _intervalo_indenizatorio_em_reflexo(decisao: Mapping[str, Any]) -> list[str]:
    'Reflexo que tem o intervalo como fonte numa competência em que a decisão o declara'



    erros: list[str] = []
    for rule in decisao.get("monthly_rules") or []:
        if (rule.get("interval_rule") or {}).get("nature") != "indenizatoria":
            continue
        for node in rule.get("reflex_rules") or []:
            if "interval" in (node.get("sources") or []):
                erros.append(
                    f"competência {rule.get('competencia')}: o reflexo {node.get('id')} tem o "
                    "intervalo entre as fontes, e a decisão declara o intervalo indenizatório "
                    "(CLT, art. 71, § 4º, na redação da Lei 13.467/2017), que não reflete. Tire "
                    "'interval' das sources desse reflexo ou, se a decisão revisada fixou natureza "
                    "salarial, declare interval_rule.nature 'salarial'.")
    return erros


def validar_pedido(pedido: Any, *, hoje: dt.date | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(pedido, Mapping):
        return ["pedido deve ser objeto"]
    allowed = {"schema_version", "principal", "decision_path", "decision_sha256", "authorization_path", "months"}
    errors.extend(_unknown(pedido, allowed, "pedido"))
    if pedido.get("schema_version") != REQUEST_VERSION:
        errors.append(f"schema_version deve ser {REQUEST_VERSION}")
    try:
        _decimal(pedido.get("principal"), "principal", positive=True)
    except HorasExtrasError as exc:
        errors.extend(exc.errors)
    if not isinstance(pedido.get("decision_path"), str) or not pedido["decision_path"].strip():
        errors.append("decision_path obrigatório")
    if not isinstance(pedido.get("authorization_path"), str) or not pedido["authorization_path"].strip():
        errors.append("authorization_path obrigatório")
    if not isinstance(pedido.get("decision_sha256"), str) or not SHA256.fullmatch(pedido["decision_sha256"]):
        errors.append("decision_sha256 inválido")
    months = pedido.get("months")
    if not isinstance(months, list) or not months:
        errors.append("months deve ser lista não vazia")
    else:
        previous = None
        for index, month in enumerate(months):
            prefix = f"months[{index}]"
            if not isinstance(month, Mapping):
                errors.append(f"{prefix} deve ser objeto")
                continue
            allowed_month = {"competencia", "salary_base", "components", "he_50_minutes", "he_100_minutes", "night_minutes", "interval_minutes", "paid_days", "rest_days"}
            errors.extend(_unknown(month, allowed_month, prefix))
            current = _period(month.get("competencia"))
            if current is None or (previous is not None and current <= previous):
                errors.append(f"{prefix}.competencia deve ser mensal, única e ordenada")
            previous = current
            for key in ("salary_base",):
                try:
                    _decimal(month.get(key), f"{prefix}.{key}", nonnegative=True)
                except HorasExtrasError as exc:
                    errors.extend(exc.errors)
            components = month.get("components")
            if not isinstance(components, list) or any(not isinstance(x, str) for x in components):
                errors.append(f"{prefix}.components deve ser lista de decimais")
            else:
                for component in components:
                    try:
                        _decimal(component, f"{prefix}.components", nonnegative=True)
                    except HorasExtrasError as exc:
                        errors.extend(exc.errors)
            for key in ("he_50_minutes", "he_100_minutes", "night_minutes", "interval_minutes", "paid_days", "rest_days"):
                value = month.get(key)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    errors.append(f"{prefix}.{key} deve ser inteiro não negativo")




            if isinstance(month.get("paid_days"), int) and month.get("paid_days", 0) == 0 and isinstance(month.get("rest_days"), int) and month.get("rest_days", 0) > 0:
                errors.append(f"{prefix}.paid_days deve ser positivo quando há DSR")
    return errors


def _authorize(path: Any, decision_hash: str, now: dt.datetime) -> None:
    auth, _ = _load_json(path)
    errors = []
    if set(auth) != {"schema_version", "authorized_by_lawyer", "scope", "decision_sha256", "expires_at", "authorized_by"}:
        errors.append("autorização contém campos não permitidos")
    if auth.get("schema_version") != AUTH_VERSION:
        errors.append(f"schema_version deve ser {AUTH_VERSION}")
    if auth.get("authorized_by_lawyer") is not True or auth.get("scope") != "calculo_experimental":
        errors.append("autorização jurídica experimental inválida")
    if not isinstance(auth.get("decision_sha256"), str) or not SHA256.fullmatch(auth["decision_sha256"]) or auth["decision_sha256"].casefold() != decision_hash.casefold():
        errors.append("autorização não corresponde à decisão")
    expires = _datetime(auth.get("expires_at"))
    if expires is None or expires <= now:
        errors.append("autorização ausente, inválida ou vencida")
    if not isinstance(auth.get("authorized_by"), str) or len(auth["authorized_by"].strip()) < 3:
        errors.append("authorized_by inválido")
    if errors:
        raise HorasExtrasError("autorizacao_invalida", errors)


def calcular(pedido: Any, *, hoje: dt.date | None = None, agora: dt.datetime | None = None, experimental_authorized: bool = False, registro_capacidades: Any = None) -> dict[str, Any]:
    'Memória condicional. `registro_capacidades` (dict ou caminho) substitui o registro'

    if experimental_authorized is not True:
        raise HorasExtrasError("capacidade_desabilitada", "horas extras experimental exige autorização explícita nesta execução")
    now = agora or dt.datetime.combine(hoje or dt.date.today(), dt.time(12), tzinfo=dt.timezone.utc)
    if not isinstance(now, dt.datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise HorasExtrasError("autorizacao_invalida", "agora deve ser datetime com fuso horário")
    now = now.astimezone(dt.timezone.utc)
    today = hoje or now.date()
    try:
        exigir_ficha(CAPACIDADE, hoje=today, registro=registro_capacidades)
    except FichaRecusada as exc:
        raise HorasExtrasError(exc.codigo, exc.mensagem) from None
    request_errors = validar_pedido(pedido, hoje=today)
    if request_errors:
        raise HorasExtrasError("pedido_invalido", request_errors)
    assert isinstance(pedido, Mapping)
    principal = _decimal(pedido["principal"], "principal", positive=True)
    decision, decision_hash = _load_json(pedido["decision_path"])
    if decision_hash.casefold() != str(pedido["decision_sha256"]).casefold():
        raise HorasExtrasError("hash_divergente", "decision_sha256 diverge do arquivo")
    _authorize(pedido["authorization_path"], decision_hash, now)
    decision_errors = validar_decisao(decision, hoje=today)
    if decision_errors:
        raise HorasExtrasError("decisao_invalida", decision_errors)
    reflexos_indenizatorios = _intervalo_indenizatorio_em_reflexo(decision)
    if reflexos_indenizatorios:
        raise HorasExtrasError("intervalo_indenizatorio_em_reflexo", reflexos_indenizatorios)
    legal_source_hash = str(decision["legal_source_sha256"])
    by_period = {rule["competencia"]: rule for rule in decision["monthly_rules"]}
    with localcontext() as context:
        context.prec = 60
        total = Decimal(0)
        memories = []
        for month in pedido["months"]:
            competence = month["competencia"]
            rule = by_period.get(competence)
            if rule is None:
                raise HorasExtrasError("cobertura_ausente", f"não há decisão para {competence}")
            hourly = (_decimal(month["salary_base"], f"{competence}.salary_base") + sum((_decimal(x, f"{competence}.components") for x in month["components"]), Decimal(0))) / _decimal(rule["divisor"], f"{competence}.divisor", positive=True)
            rates = rule["he_rates"]
            he50 = hourly * (Decimal(month["he_50_minutes"]) / 60) * (Decimal(1) + _decimal(rates["he_50"], f"{competence}.he_50"))
            he100 = hourly * (Decimal(month["he_100_minutes"]) / 60) * (Decimal(1) + _decimal(rates["he_100"], f"{competence}.he_100"))
            night_rule = rule["night_rule"]
            night = Decimal(0)
            if night_rule["enabled"] and month["night_minutes"]:
                night = hourly * (Decimal(month["night_minutes"]) / 60) * _decimal(night_rule["hour_factor"], f"{competence}.night_factor", nonnegative=True) * (Decimal(1) + _decimal(night_rule["additional_rate"], f"{competence}.night_rate", nonnegative=True))
            interval_rule = rule["interval_rule"]
            interval = Decimal(0)
            if interval_rule["enabled"] and month["interval_minutes"]:
                interval = hourly * (Decimal(month["interval_minutes"]) / 60) * (Decimal(1) + _decimal(interval_rule["additional_rate"], f"{competence}.interval_rate", nonnegative=True))
            he_total = he50 + he100 + night + interval



            natureza_do_intervalo = interval_rule["nature"]
            base_do_dsr = he50 + he100 + night + (interval if natureza_do_intervalo == "salarial" else Decimal(0))
            dsr = Decimal(0)
            dsr_ligado = (rule.get("dsr_rule") or {}).get("enabled", True)
            if month["rest_days"] and dsr_ligado:
                if not month["paid_days"]:
                    raise HorasExtrasError("entrada_invalida", f"{competence}.paid_days deve ser positivo")
                dsr = base_do_dsr * Decimal(month["rest_days"]) / Decimal(month["paid_days"])
            values = {"he_50": he50, "he_100": he100, "night": night, "interval": interval, "dsr": dsr}
            for node in rule["reflex_rules"]:
                values[node["id"]] = sum((values[source] for source in node["sources"]), Decimal(0)) * _decimal(node["rate"], f"{competence}.{node['id']}.rate", nonnegative=True)
            month_total = he_total + dsr + sum((values[node["id"]] for node in rule["reflex_rules"]), Decimal(0))
            total += month_total
            memories.append({"competencia": competence, "dsr_compensado_pela_decisao": not dsr_ligado, "natureza_do_intervalo": natureza_do_intervalo, "hourly_rate": _fmt(hourly), "components": {"he_50": _fmt(he50), "he_100": _fmt(he100), "night": _fmt(night), "interval": _fmt(interval), "dsr": _fmt(dsr), "reflexes": {node["id"]: _fmt(values[node["id"]]) for node in rule["reflex_rules"]}}, "month_total": _fmt(month_total), "decision_rule": rule})
        rounding = decision["rounding"]
        quantum = Decimal(1).scaleb(-rounding["scale"])
        amount = total.quantize(quantum, rounding=ROUNDING[rounding["mode"]])
        principal_amount = principal.quantize(quantum, rounding=ROUNDING[rounding["mode"]])
    return {"schema_version": MEMORY_VERSION, "status": "MINUTA_PARA_REVISAO", "engine_version": ENGINE_VERSION, "principal": _fmt(principal), "conditional_overtime_and_reflexes": _fmt(amount), "conditional_total_with_principal": _fmt(principal_amount + amount), "decision": {"decision_id": decision["decision_id"], "name": decision["name"], "decision_sha256": decision_hash, "legal_source_url": decision["legal_source_url"], "legal_source_sha256": legal_source_hash, "reviewed_by": decision["reviewed_by"]}, "months": memories, "warnings": ["MINUTA_PARA_REVISAO: cálculo condicional para conferência do advogado.", "O motor não escolhe divisor, adicional, regra noturna, natureza do intervalo, DSR ou cadeia de reflexos.", "Base do DSR: o intervalo entra só quando a decisão o declara salarial; declarado indenizatório (CLT, art. 71, § 4º, na redação da Lei 13.467/2017), fica fora. A natureza usada em cada competência está em natureza_do_intervalo.", "Fontes normativas e decisões coletivas devem ser conferidas quanto à vigência antes de qualquer uso."]}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise HorasExtrasError("argumentos_invalidos", message)


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(prog="horas_extras.py")
        parser.add_argument("--request", required=True)
        args = parser.parse_args(argv)


        request, _ = _load_json(args.request)
        if os.environ.get("DSR_HORAS_EXTRAS_EXPERIMENTAL") != "1":
            raise HorasExtrasError("capacidade_desabilitada", "DSR_HORAS_EXTRAS_EXPERIMENTAL=1 é obrigatório")
        result = calcular(request, experimental_authorized=True)
    except (HorasExtrasError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "status": "INCONCLUSIVO", "error_code": getattr(exc, "code", "falha"), "errors": getattr(exc, "errors", [str(exc)])}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
