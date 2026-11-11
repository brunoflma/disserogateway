#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Memoria condicional de preparo recursal (custas + porte + deposito recursal).'

























































from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

ENGINE_VERSION = "dsr.preparo_recursal.engine.v1"
TABLE_VERSION = "dsr.tabela_preparo_recursal.v1"
REQUEST_VERSION = "dsr.preparo_recursal.pedido.v1"
AUTH_VERSION = "dsr.preparo_recursal.autorizacao.v1"
MEMORY_VERSION = "dsr.memoria_preparo_recursal.v1"

SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")



HORA_FUSO = re.compile(r"(?P<hora>[0-9]{2}:[0-9]{2}(?P<seg>:[0-9]{2})?)"
                       r"(?(seg)(?:[.,](?P<fracao>[0-9]{1,6})[0-9]*)?)"
                       r"(?P<fuso>[+-][0-9]{2})(?::?(?P<min>[0-9]{2}))?\Z")
DECIMAL_CANONICO = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
OFFICIAL_SUFFIXES = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")
ROUNDING = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN, "ROUND_DOWN": ROUND_DOWN}




MODOS = ("valor_fixo", "percentual_sobre_base", "valor_por_unidade")
POLITICAS_ARREDONDAMENTO = ("por_rubrica", "sobre_total")
















CONDICOES = ("autos_fisicos",)
CONDICAO_NAO_DECLARADA = ("a tabela traz rubrica condicionada a %r e o pedido nao declarou "
                          "essa condicao; o motor NAO presume o fato do processo nem omite "
                          "a rubrica em silencio")



PRECISAO_DECIMAL = 60
MIN_NOME_AUTORIZANTE = 3



DISPENSA_NAO_E_ARITMETICA = "zero e decisao de dispensa, nao aritmetica"
ZERO_NAO_E_ARITMETICA = "%s nao pode ser zero: " + DISPENSA_NAO_E_ARITMETICA


class PreparoRecursalError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def _reject_constant(value: str) -> None:
    raise ValueError(value)


def _load_json(path: Any) -> tuple[dict[str, Any], str]:
    'Le JSON local e devolve (objeto, sha256 do byte lido).'




    if not isinstance(path, (str, os.PathLike)):
        raise PreparoRecursalError("arquivo_invalido", "caminho local obrigatorio")
    original = os.path.abspath(os.fspath(path))
    resolved = os.path.realpath(original)
    if os.path.islink(original) or not os.path.isfile(resolved):
        raise PreparoRecursalError("arquivo_invalido", "arquivo local ausente ou inseguro: %s" % original)
    current = resolved
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            raise PreparoRecursalError("arquivo_invalido", "tabelas e autorizacoes nao podem estar dentro de Git")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    try:
        raw = Path(resolved).read_bytes()
        value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise PreparoRecursalError("arquivo_invalido", "arquivo JSON local ilegivel") from exc
    if not isinstance(value, dict):
        raise PreparoRecursalError("arquivo_invalido", "arquivo JSON deve conter objeto")
    return value, hashlib.sha256(raw).hexdigest()


def _date(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


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
    return (parsed.scheme == "https" and bool(host)
            and any(host.endswith(x) for x in OFFICIAL_SUFFIXES)
            and not parsed.username and not parsed.password and not parsed.fragment)


def _decimal(value: Any, field: str, *, nonnegative: bool = False, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not DECIMAL_CANONICO.fullmatch(value):
        raise PreparoRecursalError("entrada_invalida", "%s deve ser decimal canonico em string" % field)
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise PreparoRecursalError("entrada_invalida", "%s invalido" % field) from exc
    if not result.is_finite() or (nonnegative and result < 0) or (positive and result <= 0):
        raise PreparoRecursalError("entrada_invalida", "%s fora do dominio" % field)
    return result


def _fmt(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0", "-"} else text


def _unknown(value: Mapping[str, Any], allowed: set[str], prefix: str) -> list[str]:
    return ["%s contem campo nao permitido: %s" % (prefix, key) for key in value if key not in allowed]


def validar_tabela(table: Any, *, hoje: dt.date | None = None) -> list[str]:
    """Valida a tabela oficial externa. Lista de erros vazia significa aprovada."""
    if not isinstance(table, Mapping):
        return ["tabela deve ser objeto"]
    allowed = {"schema_version", "table_id", "name", "legal_source_url", "legal_source_sha256",
               "valid_from", "valid_to", "extracted_at", "reviewed_by", "reviewed_role", "reviewed_at",
               "segregation_attested", "rounding", "politica_arredondamento", "jurisdicao",
               "covered_recursos", "rubricas"}
    errors = _unknown(table, allowed, "tabela")
    if table.get("schema_version") != TABLE_VERSION:
        errors.append("schema_version deve ser %s" % TABLE_VERSION)
    if not isinstance(table.get("table_id"), str) or not ID.fullmatch(str(table.get("table_id"))):
        errors.append("table_id invalido")
    for field in ("name", "reviewed_by", "jurisdicao"):
        if not isinstance(table.get(field), str) or not table[field].strip():
            errors.append("%s obrigatorio" % field)
    if not _official_url(table.get("legal_source_url")):
        errors.append("legal_source_url deve ser HTTPS oficial")
    if not isinstance(table.get("legal_source_sha256"), str) or not SHA256.fullmatch(str(table.get("legal_source_sha256"))):
        errors.append("legal_source_sha256 invalido")
    if table.get("reviewed_role") != "advogado":
        errors.append("reviewed_role deve ser advogado")
    if table.get("segregation_attested") is not True:
        errors.append("segregation_attested=true e obrigatorio")
    if table.get("politica_arredondamento") not in POLITICAS_ARREDONDAMENTO:
        errors.append("politica_arredondamento deve ser um de %s" % (list(POLITICAS_ARREDONDAMENTO),))
    today = hoje or dt.date.today()
    start, end, extracted, reviewed = (_date(table.get(k)) for k in ("valid_from", "valid_to", "extracted_at", "reviewed_at"))
    if start is None or end is None or start > end or not start <= today <= end:
        errors.append("vigencia da tabela invalida, ausente ou vencida")
    if extracted is None or extracted > today:
        errors.append("extracted_at invalido ou futuro")
    if reviewed is None or reviewed > today:
        errors.append("reviewed_at invalido ou futuro")
    rounding = table.get("rounding")
    if (not isinstance(rounding, Mapping) or set(rounding) != {"scale", "mode"}
            or isinstance(rounding.get("scale"), bool) or not isinstance(rounding.get("scale"), int)
            or not 0 <= rounding["scale"] <= 8 or rounding.get("mode") not in ROUNDING):
        errors.append("rounding invalido")
    recursos = table.get("covered_recursos")
    if not isinstance(recursos, list) or not recursos or any(not isinstance(x, str) or not x.strip() for x in recursos):
        errors.append("covered_recursos invalido")
        recursos = []
    elif len(set(recursos)) != len(recursos):
        errors.append("covered_recursos com repeticao")
    errors.extend(_validar_rubricas(table.get("rubricas"), recursos))
    return errors


def _validar_rubricas(rubricas: Any, recursos: list[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(rubricas, list) or not rubricas:
        return ["rubricas deve ser lista nao vazia"]
    vistos: set[str] = set()
    cobertos: set[str] = set()
    for index, rubrica in enumerate(rubricas):
        prefix = "rubricas[%d]" % index
        if not isinstance(rubrica, Mapping):
            errors.append("%s deve ser objeto" % prefix)
            continue
        modo = rubrica.get("modo")
        if modo == "valor_fixo":
            allowed = {"rubrica_id", "descricao", "recurso", "modo", "valor", "condicao"}

            required = {"rubrica_id", "descricao", "recurso", "modo", "valor"}
        elif modo == "percentual_sobre_base":
            allowed = {"rubrica_id", "descricao", "recurso", "modo", "aliquota", "base_ref",
                       "piso", "teto", "condicao"}
            required = {"rubrica_id", "descricao", "recurso", "modo", "aliquota", "base_ref"}
        elif modo == "valor_por_unidade":
            allowed = {"rubrica_id", "descricao", "recurso", "modo", "valor_unitario",
                       "unidade_ref", "condicao"}
            required = {"rubrica_id", "descricao", "recurso", "modo", "valor_unitario",
                        "unidade_ref"}
        else:
            errors.append("%s.modo deve ser um de %s" % (prefix, list(MODOS)))
            continue
        errors.extend(_unknown(rubrica, allowed, prefix))
        for field in sorted(required - set(rubrica)):
            errors.append("%s.%s obrigatorio para modo %s" % (prefix, field, modo))
        rubrica_id = rubrica.get("rubrica_id")
        if not isinstance(rubrica_id, str) or not ID.fullmatch(rubrica_id):
            errors.append("%s.rubrica_id invalido" % prefix)
        elif rubrica_id in vistos:
            errors.append("%s.rubrica_id repetido: %s" % (prefix, rubrica_id))
        else:
            vistos.add(rubrica_id)
        if not isinstance(rubrica.get("descricao"), str) or not str(rubrica.get("descricao")).strip():
            errors.append("%s.descricao obrigatoria" % prefix)
        recurso = rubrica.get("recurso")
        if not isinstance(recurso, str) or recurso not in recursos:
            errors.append("%s.recurso fora de covered_recursos" % prefix)
        else:
            cobertos.add(recurso)
        if "condicao" in rubrica and rubrica.get("condicao") not in CONDICOES:
            errors.append("%s.condicao deve ser um de %s (vocabulario fechado)"
                          % (prefix, list(CONDICOES)))
        errors.extend(_validar_valores_rubrica(rubrica, modo, prefix))
    faltando = sorted(set(recursos) - cobertos)
    if faltando:
        errors.append("covered_recursos sem rubrica: %s - cobertura sem rubrica somaria zero, e %s"
                      % (faltando, DISPENSA_NAO_E_ARITMETICA))
    return errors


def _validar_valores_rubrica(rubrica: Mapping[str, Any], modo: str, prefix: str) -> list[str]:
    'Valores da rubrica. `valor`, `valor_unitario`, `aliquota` e `teto` exigem POSITIVO;'

    errors: list[str] = []

    def positivo(campo: str) -> Decimal | None:
        'Le campo que nao pode ser zero. A segunda passada, com `nonnegative`, distingue'

        rotulo = "%s.%s" % (prefix, campo)
        try:
            return _decimal(rubrica.get(campo), rotulo, positive=True)
        except PreparoRecursalError as exc:
            errors.extend(exc.errors)
        try:
            if _decimal(rubrica.get(campo), rotulo, nonnegative=True) == 0:
                errors.append(ZERO_NAO_E_ARITMETICA % rotulo)
        except PreparoRecursalError:
            pass
        return None

    if modo == "valor_fixo":
        positivo("valor")
        return errors
    if modo == "valor_por_unidade":
        positivo("valor_unitario")
        unidade_ref = rubrica.get("unidade_ref")
        if not isinstance(unidade_ref, str) or not ID.fullmatch(unidade_ref):
            errors.append("%s.unidade_ref invalido" % prefix)
        return errors
    base_ref = rubrica.get("base_ref")
    if not isinstance(base_ref, str) or not ID.fullmatch(base_ref):
        errors.append("%s.base_ref invalido" % prefix)
    rate = positivo("aliquota")
    if rate is not None and rate > 1:
        errors.append("%s.aliquota acima de 1" % prefix)
    limites: dict[str, Decimal] = {}
    if "teto" in rubrica:
        teto = positivo("teto")
        if teto is not None:
            limites["teto"] = teto
    if "piso" in rubrica:
        try:
            limites["piso"] = _decimal(rubrica.get("piso"), "%s.piso" % prefix, nonnegative=True)
        except PreparoRecursalError as exc:
            errors.extend(exc.errors)
    if "piso" in limites and "teto" in limites and limites["piso"] > limites["teto"]:
        errors.append("%s: piso maior que teto" % prefix)
    return errors


def validar_pedido(request: Any, *, hoje: dt.date | None = None) -> list[str]:
    """Valida o pedido do advogado. Lista de erros vazia significa aprovado."""
    if not isinstance(request, Mapping):
        return ["pedido deve ser objeto"]
    allowed = {"schema_version", "table_path", "table_sha256", "authorization_path", "jurisdicao",
               "recurso", "data_referencia", "bases", "recolhimentos", "hipoteses_excepcionais",
               "condicoes"}
    errors = _unknown(request, allowed, "pedido")
    if request.get("schema_version") != REQUEST_VERSION:
        errors.append("schema_version deve ser %s" % REQUEST_VERSION)
    for field in ("table_path", "authorization_path", "jurisdicao", "recurso"):
        if not isinstance(request.get(field), str) or not request[field].strip():
            errors.append("%s obrigatorio" % field)
    if not isinstance(request.get("table_sha256"), str) or not SHA256.fullmatch(str(request.get("table_sha256"))):
        errors.append("table_sha256 invalido")
    if _date(request.get("data_referencia")) is None:
        errors.append("data_referencia deve ser data ISO AAAA-MM-DD")
    bases = request.get("bases")
    if not isinstance(bases, Mapping):
        errors.append("bases deve ser objeto (pode ser vazio)")
    else:
        for key, value in bases.items():
            if not isinstance(key, str) or not ID.fullmatch(key):
                errors.append("bases contem rotulo invalido: %r" % (key,))
            try:
                _decimal(value, "bases.%s" % key, nonnegative=True)
            except PreparoRecursalError as exc:
                errors.extend(exc.errors)
    recolhimentos = request.get("recolhimentos")
    if not isinstance(recolhimentos, list):
        errors.append("recolhimentos deve ser lista (pode ser vazia)")
    else:
        for index, item in enumerate(recolhimentos):
            prefix = "recolhimentos[%d]" % index
            if not isinstance(item, Mapping):
                errors.append("%s deve ser objeto" % prefix)
                continue
            errors.extend(_unknown(item, {"rubrica_id", "valor"}, prefix))
            if not isinstance(item.get("rubrica_id"), str) or not ID.fullmatch(str(item.get("rubrica_id"))):
                errors.append("%s.rubrica_id invalido" % prefix)
            try:
                _decimal(item.get("valor"), "%s.valor" % prefix, nonnegative=True)
            except PreparoRecursalError as exc:
                errors.extend(exc.errors)
    hipoteses = request.get("hipoteses_excepcionais")
    if not isinstance(hipoteses, list) or any(not isinstance(x, str) or not x.strip() for x in hipoteses):
        errors.append("hipoteses_excepcionais deve ser lista de textos (pode ser vazia)")





    if "condicoes" in request:
        condicoes = request.get("condicoes")
        if not isinstance(condicoes, Mapping):
            errors.append("condicoes deve ser objeto (pode ser vazio)")
        else:
            for nome, valor in condicoes.items():
                if nome not in CONDICOES:
                    errors.append("condicoes contem nome desconhecido: %r (conhecidos: %s)"
                                  % (nome, list(CONDICOES)))
                if not isinstance(valor, bool):
                    errors.append("condicoes[%r] deve ser true ou false (booleano), recebido %r"
                                  % (nome, valor))
    return errors


def _authorize(path: Any, table_hash: str, now: dt.datetime) -> None:
    auth, _ = _load_json(path)
    errors = []
    if set(auth) != {"schema_version", "authorized_by_lawyer", "scope", "table_sha256", "expires_at", "authorized_by"}:
        errors.append("autorizacao contem campos nao permitidos ou ausentes")
    if auth.get("schema_version") != AUTH_VERSION:
        errors.append("schema_version deve ser %s" % AUTH_VERSION)
    if auth.get("authorized_by_lawyer") is not True or auth.get("scope") != "calculo_experimental":
        errors.append("autorizacao juridica experimental invalida")
    declared = auth.get("table_sha256")
    if (not isinstance(declared, str) or not SHA256.fullmatch(declared)
            or declared.casefold() != table_hash.casefold()):
        errors.append("autorizacao nao corresponde a tabela")
    expires = _datetime(auth.get("expires_at"))
    if expires is None or expires <= now:
        errors.append("autorizacao ausente, invalida ou vencida")
    if not isinstance(auth.get("authorized_by"), str) or len(auth["authorized_by"].strip()) < MIN_NOME_AUTORIZANTE:
        errors.append("authorized_by invalido")
    if errors:
        raise PreparoRecursalError("autorizacao_invalida", errors)


def _valor_rubrica(rubrica: Mapping[str, Any], bases: Mapping[str, Any]) -> tuple[Decimal, dict[str, Any]]:
    """Aritmetica pura sobre valores declarados. Nenhuma escolha de indice ou aliquota."""
    detalhe: dict[str, Any] = {"rubrica_id": rubrica["rubrica_id"], "descricao": rubrica["descricao"],
                               "modo": rubrica["modo"]}
    if rubrica["modo"] == "valor_fixo":
        valor = _decimal(rubrica["valor"], "valor", nonnegative=True)
        detalhe["valor_tabela"] = _fmt(valor)
        detalhe["limite_aplicado"] = "nenhum"
        return valor, detalhe
    if rubrica["modo"] == "valor_por_unidade":
        unidade_ref = rubrica["unidade_ref"]
        quantidade = _decimal(bases[unidade_ref], "bases.%s" % unidade_ref, nonnegative=True)
        unitario = _decimal(rubrica["valor_unitario"], "valor_unitario", nonnegative=True)
        detalhe.update({"unidade_ref": unidade_ref, "unidade_quantidade": _fmt(quantidade),
                        "valor_unitario": _fmt(unitario), "limite_aplicado": "nenhum"})
        return quantidade * unitario, detalhe
    base_ref = rubrica["base_ref"]
    base = _decimal(bases[base_ref], "bases.%s" % base_ref, nonnegative=True)
    rate = _decimal(rubrica["aliquota"], "aliquota", nonnegative=True)
    bruto = base * rate
    detalhe.update({"base_ref": base_ref, "base_valor": _fmt(base), "aliquota": _fmt(rate),
                    "valor_antes_dos_limites": _fmt(bruto), "limite_aplicado": "nenhum"})
    valor = bruto
    if "piso" in rubrica:
        piso = _decimal(rubrica["piso"], "piso", nonnegative=True)
        detalhe["piso"] = _fmt(piso)
        if valor < piso:
            valor = piso
            detalhe["limite_aplicado"] = "piso"
    if "teto" in rubrica:
        teto = _decimal(rubrica["teto"], "teto", nonnegative=True)
        detalhe["teto"] = _fmt(teto)
        if valor > teto:
            valor = teto
            detalhe["limite_aplicado"] = "teto"
    return valor, detalhe


def calcular(request: Any, *, hoje: dt.date | None = None, agora: dt.datetime | None = None,
             experimental_authorized: bool = False) -> dict[str, Any]:
    """Produz a memoria de preparo. Falha fechada em tudo que nao for aritmetica."""
    if experimental_authorized is not True:
        raise PreparoRecursalError("capacidade_desabilitada",
                                   "preparo recursal experimental exige autorizacao explicita nesta execucao")
    now = agora or dt.datetime.combine(hoje or dt.date.today(), dt.time(12), tzinfo=dt.timezone.utc)
    now = now.astimezone(dt.timezone.utc) if now.tzinfo and now.utcoffset() is not None else now
    today = hoje or now.date()

    errors = validar_pedido(request, hoje=today)
    if errors:
        raise PreparoRecursalError("pedido_invalido", errors)
    if request["hipoteses_excepcionais"]:
        raise PreparoRecursalError("decisao_juridica_externa", [
            "hipotese excepcional declarada: %s" % item for item in request["hipoteses_excepcionais"]
        ] + ["dispensa, gratuidade, complementacao e recolhimento em dobro sao decisao do advogado; "
             "o motor nao produz valor sob regime excepcional"])

    table, table_hash = _load_json(request["table_path"])
    if table_hash.casefold() != request["table_sha256"].casefold():
        raise PreparoRecursalError("hash_divergente", "table_sha256 diverge do arquivo lido")
    _authorize(request["authorization_path"], table_hash, now)
    table_errors = validar_tabela(table, hoje=today)
    if table_errors:
        raise PreparoRecursalError("tabela_invalida", table_errors)

    faltas = []
    if request["jurisdicao"] != table["jurisdicao"]:
        faltas.append("tabela e da jurisdicao %r; pedido pede %r" % (table["jurisdicao"], request["jurisdicao"]))
    if request["recurso"] not in table["covered_recursos"]:
        faltas.append("tabela nao cobre o recurso %r (cobre %s)" % (request["recurso"], table["covered_recursos"]))
    if not table["valid_from"] <= request["data_referencia"] <= table["valid_to"]:
        faltas.append("tabela vigente de %s a %s nao cobre a data de referencia %s"
                      % (table["valid_from"], table["valid_to"], request["data_referencia"]))
    if faltas:
        raise PreparoRecursalError("cobertura_ausente", faltas)

    do_recurso = [r for r in table["rubricas"] if r["recurso"] == request["recurso"]]
    if not do_recurso:
        raise PreparoRecursalError("cobertura_ausente", "nenhuma rubrica aplicavel ao recurso %r" % request["recurso"])




    condicoes = dict(request.get("condicoes") or {})
    exigidas_por_rubrica = {r["condicao"] for r in do_recurso if "condicao" in r}
    nao_declaradas = sorted(exigidas_por_rubrica - set(condicoes))
    if nao_declaradas:
        raise PreparoRecursalError("condicao_nao_declarada",
                                   [CONDICAO_NAO_DECLARADA % nome for nome in nao_declaradas]
                                   + ["declare em `condicoes` do pedido, com true ou false: %s"
                                      % ", ".join(nao_declaradas)])


    sobrando_cond = sorted(set(condicoes) - exigidas_por_rubrica)
    if sobrando_cond:
        raise PreparoRecursalError("condicao_sem_rubrica",
                                   ["condicao declarada sem rubrica correspondente neste recurso: %s"
                                    % nome for nome in sobrando_cond])

    aplicaveis = [r for r in do_recurso if "condicao" not in r or condicoes[r["condicao"]] is True]
    afastadas = [{"rubrica_id": r["rubrica_id"], "descricao": r["descricao"],
                  "condicao": r["condicao"], "motivo": "condicao declarada como false pelo advogado"}
                 for r in do_recurso if "condicao" in r and condicoes[r["condicao"]] is not True]
    if not aplicaveis:
        raise PreparoRecursalError(
            "cobertura_ausente",
            ["todas as rubricas do recurso %r foram afastadas por condicao declarada como false"
             % request["recurso"]]
            + ["afastada: %s (%s)" % (a["rubrica_id"], a["condicao"]) for a in afastadas]
            + ["o motor nao conclui que nada e devido: total zerado por afastamento e dispensa, "
               + DISPENSA_NAO_E_ARITMETICA])





    exigidas = ({r["base_ref"] for r in aplicaveis if r["modo"] == "percentual_sobre_base"}
                | {r["unidade_ref"] for r in aplicaveis if r["modo"] == "valor_por_unidade"})
    informadas = set(request["bases"])
    ausentes = sorted(exigidas - informadas)
    sobrando = sorted(informadas - exigidas)
    if ausentes or sobrando:
        raise PreparoRecursalError("bases_invalidas",
                                   (["base exigida pela tabela e nao informada: %s" % b for b in ausentes]
                                    + ["base informada sem rubrica correspondente: %s" % b for b in sobrando]))

    ids_aplicaveis = {r["rubrica_id"] for r in aplicaveis}
    ids_afastados = {a["rubrica_id"] for a in afastadas}



    pagos_afastados = sorted({i["rubrica_id"] for i in request["recolhimentos"]
                              if i["rubrica_id"] in ids_afastados})
    if pagos_afastados:
        raise PreparoRecursalError(
            "recolhimento_de_rubrica_afastada",
            ["ha recolhimento informado para rubrica afastada por condicao: %s" % r
             for r in pagos_afastados]
            + ["ou a condicao declarada esta errada, ou houve recolhimento indevido; "
               "as duas leituras sao juridicas e nenhuma e do motor"])
    recolhido_por_rubrica: dict[str, Decimal] = {}
    orfaos = []
    for item in request["recolhimentos"]:
        if item["rubrica_id"] not in ids_aplicaveis:
            orfaos.append(item["rubrica_id"])
            continue
        valor = _decimal(item["valor"], "recolhimentos.valor", nonnegative=True)
        recolhido_por_rubrica[item["rubrica_id"]] = recolhido_por_rubrica.get(item["rubrica_id"], Decimal(0)) + valor
    if orfaos:
        raise PreparoRecursalError("recolhimento_sem_rubrica",
                                   ["recolhimento aponta rubrica inexistente para este recurso: %s" % r
                                    for r in sorted(set(orfaos))])

    rounding = table["rounding"]
    quantum = Decimal(1).scaleb(-rounding["scale"])
    modo_arredondamento = ROUNDING[rounding["mode"]]
    por_rubrica = table["politica_arredondamento"] == "por_rubrica"
    detalhes = []
    total_devido = Decimal(0)
    total_recolhido = Decimal(0)
    zeradas = []
    with localcontext() as context:
        context.prec = PRECISAO_DECIMAL
        for rubrica in aplicaveis:
            valor, detalhe = _valor_rubrica(rubrica, request["bases"])
            if por_rubrica:
                valor = valor.quantize(quantum, rounding=modo_arredondamento)
            if valor <= 0:
                zeradas.append(rubrica["rubrica_id"])
            recolhido = recolhido_por_rubrica.get(rubrica["rubrica_id"], Decimal(0))
            detalhe["valor_devido"] = _fmt(valor)
            detalhe["valor_recolhido_informado"] = _fmt(recolhido)
            detalhe["diferenca"] = _fmt(valor - recolhido)
            detalhes.append(detalhe)
            total_devido += valor
            total_recolhido += recolhido
        if not por_rubrica:
            total_devido = total_devido.quantize(quantum, rounding=modo_arredondamento)
        diferenca = total_devido - total_recolhido
    if zeradas:
        raise PreparoRecursalError("zero_nao_e_aritmetica",
                                   [ZERO_NAO_E_ARITMETICA % ("valor devido da rubrica %s" % r)
                                    for r in zeradas]
                                   + ["confira a base informada e a tabela: valor devido zerado costuma "
                                      "ser campo que nao converteu na extracao, e nao dispensa deferida"])
    if total_devido <= 0:
        raise PreparoRecursalError("zero_nao_e_aritmetica",
                                   [ZERO_NAO_E_ARITMETICA % "total devido",
                                    "o arredondamento declarado na tabela (%s, escala %s, politica %s) "
                                    "zerou o total; o motor nao afirma que nada e devido"
                                    % (rounding["mode"], rounding["scale"], table["politica_arredondamento"])])

    return {
        "schema_version": MEMORY_VERSION,
        "status": "MINUTA_PARA_REVISAO",
        "engine_version": ENGINE_VERSION,
        "resumo": {
            "total_devido": _fmt(total_devido),
            "total_recolhido_informado": _fmt(total_recolhido),
            "diferenca": _fmt(diferenca),
            "politica_arredondamento": table["politica_arredondamento"],
        },
        "pedido": {
            "jurisdicao": request["jurisdicao"],
            "recurso": request["recurso"],
            "data_referencia": request["data_referencia"],
            "bases": {k: _fmt(_decimal(v, "bases.%s" % k, nonnegative=True)) for k, v in request["bases"].items()},
            "condicoes_declaradas": dict(sorted(condicoes.items())),
        },
        "tabela": {
            "table_id": table["table_id"],
            "name": table["name"],
            "table_sha256": table_hash,
            "legal_source_url": table["legal_source_url"],
            "legal_source_sha256": table["legal_source_sha256"],
            "valid_from": table["valid_from"],
            "valid_to": table["valid_to"],
            "reviewed_by": table["reviewed_by"],
            "jurisdicao": table["jurisdicao"],
        },
        "rubricas": detalhes,
        "rubricas_afastadas": afastadas,
        "warnings": ([
            "RUBRICA AFASTADA POR CONDICAO DECLARADA - o total NAO inclui: %s. O afastamento "
            "vem da condicao que o advogado declarou no pedido, nao de leitura do motor; se a "
            "condicao estiver errada, o total esta menor do que o devido."
            % ", ".join("%s (%s=false)" % (a["rubrica_id"], a["condicao"]) for a in afastadas)
        ] if afastadas else []) + [
            "MINUTA_PARA_REVISAO: calculo condicional para conferencia do advogado, nunca para protocolo direto.",
            "O motor apenas soma rubricas declaradas na tabela oficial externa; nao escolhe tribunal, "
            "rubrica, aliquota nem valor de deposito recursal.",
            "O motor nao aplica dispensa, gratuidade, complementacao nem recolhimento em dobro, e nao "
            "afirma desercao: a diferenca sai como numero com sinal e o enquadramento e do advogado.",
            "Conferir cada valor contra a guia oficial do tribunal antes de recolher; o arredondamento "
            "declarado na tabela pode divergir do adotado pelo sistema de custas.",
        ],
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise PreparoRecursalError("argumentos_invalidos", message)


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(prog="preparo_recursal.py")
        parser.add_argument("--request", required=True)
        args = parser.parse_args(argv)
        if os.environ.get("DSR_PREPARO_RECURSAL_EXPERIMENTAL") != "1":
            raise PreparoRecursalError("capacidade_desabilitada", "DSR_PREPARO_RECURSAL_EXPERIMENTAL=1 e obrigatorio")
        request, _ = _load_json(args.request)
        result = calcular(request, experimental_authorized=True)
    except (PreparoRecursalError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "status": "INCONCLUSIVO", "error_code": getattr(exc, "code", "falha"),
                          "errors": getattr(exc, "errors", [str(exc)])}, ensure_ascii=False, sort_keys=True))
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
