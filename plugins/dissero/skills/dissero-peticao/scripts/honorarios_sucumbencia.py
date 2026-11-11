#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'honorarios_sucumbencia.py — as faixas do art. 85, § 3º, do CPC, e o âmbito que vem antes delas.'





























































from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext
from typing import Any, Mapping
from urllib.parse import urlparse


ENGINE_VERSION = "dsr.honorarios_sucumbencia.engine.v1"
REQUEST_VERSION = "dsr.honorarios_sucumbencia.pedido.v1"
MEMORY_VERSION = "dsr.memoria_honorarios_sucumbencia.v1"
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
OFFICIAL_SUFFIXES = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")
ROUNDING = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN, "ROUND_DOWN": ROUND_DOWN}





FAIXAS_ART85_P3 = (
    {"inciso": "I",   "piso_sm": Decimal(0),      "teto_sm": Decimal(200),    "pct_min": Decimal("0.10"), "pct_max": Decimal("0.20")},
    {"inciso": "II",  "piso_sm": Decimal(200),    "teto_sm": Decimal(2000),   "pct_min": Decimal("0.08"), "pct_max": Decimal("0.10")},
    {"inciso": "III", "piso_sm": Decimal(2000),   "teto_sm": Decimal(20000),  "pct_min": Decimal("0.05"), "pct_max": Decimal("0.08")},
    {"inciso": "IV",  "piso_sm": Decimal(20000),  "teto_sm": Decimal(100000), "pct_min": Decimal("0.03"), "pct_max": Decimal("0.05")},
    {"inciso": "V",   "piso_sm": Decimal(100000), "teto_sm": None,            "pct_min": Decimal("0.01"), "pct_max": Decimal("0.03")},
)



FAIXA_ART85_P2 = {"pct_min": Decimal("0.10"), "pct_max": Decimal("0.20")}







REGIMES_RECUSADOS = {
    "mandado_seguranca": (
        "não cabe condenação em honorários em mandado de segurança",
        "art. 25 da Lei 12.016/2009"),
    "juizado_especial_1grau": (
        "não cabem honorários em sentença de primeiro grau nos Juizados Especiais, salvo litigância de má-fé",
        "art. 55 da Lei 9.099/1995"),
    "justica_trabalho": (
        "a sucumbência trabalhista tem sede própria e percentuais próprios (5% a 15%), não os do art. 85",
        "art. 791-A da CLT"),
    "cumprimento_fazenda_precatorio_nao_impugnado": (
        "não são devidos honorários no cumprimento de sentença contra a Fazenda Pública que enseje "
        "precatório, quando não impugnada a execução",
        "art. 85, § 7º, do CPC"),
    "cumprimento_sentenca_art523": (
        "o percentual é FIXADO PELA LEI em 10%, não arbitrado em faixa — não há o que calcular por faixas",
        "art. 523, § 1º, do CPC"),
    "execucao_art827": (
        "o percentual é fixado de plano pela lei em 10%, reduzido à metade no pagamento em três dias",
        "art. 827 do CPC"),
    "monitoria_art701": (
        "o percentual é fixado pela lei em 5% do valor atribuído à causa",
        "art. 701 do CPC"),
}

REGIMES_CALCULAVEIS = {"art_85_p3_fazenda_publica", "art_85_p2_geral"}
ESPECIES_BASE = {"condenacao", "proveito_economico", "valor_atualizado_causa"}

HIPOTESES_SM = {"sentenca_liquida", "decisao_liquidacao"}


class HonorariosError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise HonorariosError("entrada_invalida", f"{field} deve ser decimal canônico em string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise HonorariosError("entrada_invalida", f"{field} inválido") from exc
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise HonorariosError("entrada_invalida", f"{field} fora do domínio")
    return result


def _fmt(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _date(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _official_url(value: Any) -> bool:
    'HTTPS em host oficial. O host é lido pelo `urlparse`, e não por corte de string, para'


    if not isinstance(value, str) or not value.startswith("https://") or "@" in value or "#" in value:
        return False
    try:
        host = (urlparse(value).hostname or "").casefold()
    except ValueError:
        return False
    return bool(host) and any(host.endswith(s) for s in OFFICIAL_SUFFIXES)


def _unknown(value: Mapping[str, Any], allowed: set[str], prefix: str) -> list[str]:
    return [f"{prefix} contém campo não permitido: {key}" for key in value if key not in allowed]


def validar_pedido(pedido: Any, *, hoje: dt.date | None = None) -> list[str]:
    """Valida a forma do pedido. NÃO decide âmbito — quem recusa regime é `calcular`."""
    if not isinstance(pedido, Mapping):
        return ["pedido deve ser objeto"]
    allowed = {"schema_version", "regime", "fazenda_publica", "base", "salario_minimo", "arredondamento"}
    errors = _unknown(pedido, allowed, "pedido")
    if pedido.get("schema_version") != REQUEST_VERSION:
        errors.append(f"schema_version deve ser {REQUEST_VERSION}")

    regime = pedido.get("regime")
    if not isinstance(regime, str) or (regime not in REGIMES_CALCULAVEIS and regime not in REGIMES_RECUSADOS):
        errors.append("regime desconhecido: declare o regime processual explicitamente")




    if pedido.get("fazenda_publica") not in (True, False):
        errors.append("fazenda_publica deve ser declarada (true/false) pelo advogado, não é inferida")
    if regime == "art_85_p3_fazenda_publica" and pedido.get("fazenda_publica") is not True:
        errors.append("regime do § 3º exige fazenda_publica=true")
    if regime == "art_85_p2_geral" and pedido.get("fazenda_publica") is True:
        errors.append("com Fazenda Pública na lide o regime é o do § 3º, não o do § 2º")

    base = pedido.get("base")
    if not isinstance(base, Mapping) or set(base) != {"especie", "valor"}:
        errors.append("base deve declarar especie e valor")
    else:
        if base.get("especie") not in ESPECIES_BASE:
            errors.append(f"base.especie deve ser uma de {sorted(ESPECIES_BASE)}")
        try:
            _decimal(base.get("valor"), "base.valor", positive=True)
        except HonorariosError as exc:
            errors.extend(exc.errors)

    sm = pedido.get("salario_minimo")
    if not isinstance(sm, Mapping) or set(sm) != {"valor", "data_referencia", "hipotese_art85_p4_iv", "fonte_url"}:
        errors.append("salario_minimo deve declarar valor, data_referencia, hipotese_art85_p4_iv e fonte_url")
    else:
        try:
            _decimal(sm.get("valor"), "salario_minimo.valor", positive=True)
        except HonorariosError as exc:
            errors.extend(exc.errors)
        data = _date(sm.get("data_referencia"))
        if data is None or data > (hoje or dt.date.today()):
            errors.append("salario_minimo.data_referencia inválida ou futura")
        if sm.get("hipotese_art85_p4_iv") not in HIPOTESES_SM:
            errors.append(
                "salario_minimo.hipotese_art85_p4_iv deve ser sentenca_liquida ou decisao_liquidacao: "
                "fora dessas duas o art. 85, § 4º, IV, não diz qual salário-mínimo converte as faixas")
        if not _official_url(sm.get("fonte_url")):
            errors.append("salario_minimo.fonte_url deve ser HTTPS de host oficial")

    arred = pedido.get("arredondamento")
    if (not isinstance(arred, Mapping) or set(arred) != {"scale", "mode"}
            or isinstance(arred.get("scale"), bool) or not isinstance(arred.get("scale"), int)
            or not 0 <= arred["scale"] <= 8 or arred.get("mode") not in ROUNDING):
        errors.append("arredondamento inválido: scale (0-8) e mode declarados")
    return errors


def _porcao_da_faixa(base_sm: Decimal, faixa: Mapping[str, Any]) -> Decimal:
    'Art. 85, § 5º: a porção da base que cai DENTRO desta faixa.'





    teto = faixa["teto_sm"]
    topo = base_sm if teto is None else min(base_sm, teto)
    return max(Decimal(0), topo - faixa["piso_sm"])


def calcular(pedido: Any, *, hoje: dt.date | None = None, experimental_authorized: bool = False) -> dict[str, Any]:
    if experimental_authorized is not True:
        raise HonorariosError(
            "capacidade_desabilitada",
            "cálculo de honorários exige autorização explícita nesta execução")
    today = hoje or dt.date.today()
    errors = validar_pedido(pedido, hoje=today)
    if errors:
        raise HonorariosError("pedido_invalido", errors)
    assert isinstance(pedido, Mapping)

    regime = pedido["regime"]
    if regime in REGIMES_RECUSADOS:
        motivo, norma = REGIMES_RECUSADOS[regime]
        raise HonorariosError(
            "regime_fora_do_art_85",
            f"{motivo} — quem rege é {norma}. Este motor não converte percentual legal fixo em faixa, "
            f"e não devolve zero: honorários iguais a zero são conclusão jurídica, não conta")

    base_valor = _decimal(pedido["base"]["valor"], "base.valor", positive=True)
    sm_valor = _decimal(pedido["salario_minimo"]["valor"], "salario_minimo.valor", positive=True)
    scale = pedido["arredondamento"]["scale"]
    mode = ROUNDING[pedido["arredondamento"]["mode"]]
    quantum = Decimal(1).scaleb(-scale)

    with localcontext() as ctx:
        ctx.prec = 40
        base_sm = base_valor / sm_valor
        decomposicao: list[dict[str, str]] = []
        total_min = Decimal(0)
        total_max = Decimal(0)

        if regime == "art_85_p2_geral":

            total_min = base_valor * FAIXA_ART85_P2["pct_min"]
            total_max = base_valor * FAIXA_ART85_P2["pct_max"]
            decomposicao.append({
                "fundamento": "art. 85, § 2º, do CPC",
                "base_na_faixa": _fmt(base_valor.quantize(quantum, rounding=mode)),
                "percentual_minimo": _fmt(FAIXA_ART85_P2["pct_min"]),
                "percentual_maximo": _fmt(FAIXA_ART85_P2["pct_max"]),
                "minimo": _fmt(total_min.quantize(quantum, rounding=mode)),
                "maximo": _fmt(total_max.quantize(quantum, rounding=mode)),
            })
        else:
            for faixa in FAIXAS_ART85_P3:
                porcao_sm = _porcao_da_faixa(base_sm, faixa)
                if porcao_sm <= 0:
                    continue
                porcao_valor = porcao_sm * sm_valor
                minimo = porcao_valor * faixa["pct_min"]
                maximo = porcao_valor * faixa["pct_max"]
                total_min += minimo
                total_max += maximo
                decomposicao.append({
                    "fundamento": f"art. 85, § 3º, {faixa['inciso']}, do CPC",
                    "base_na_faixa_sm": _fmt(porcao_sm.quantize(Decimal("0.0001"), rounding=mode)),
                    "base_na_faixa": _fmt(porcao_valor.quantize(quantum, rounding=mode)),
                    "percentual_minimo": _fmt(faixa["pct_min"]),
                    "percentual_maximo": _fmt(faixa["pct_max"]),
                    "minimo": _fmt(minimo.quantize(quantum, rounding=mode)),
                    "maximo": _fmt(maximo.quantize(quantum, rounding=mode)),
                })

        total_min = total_min.quantize(quantum, rounding=mode)
        total_max = total_max.quantize(quantum, rounding=mode)

    return {
        "schema_version": MEMORY_VERSION,
        "engine_version": ENGINE_VERSION,
        "estado": "MINUTA_PARA_REVISAO",
        "regime": regime,
        "base": {"especie": pedido["base"]["especie"], "valor": _fmt(base_valor)},
        "salario_minimo": {
            "valor": _fmt(sm_valor),
            "data_referencia": pedido["salario_minimo"]["data_referencia"],
            "hipotese_art85_p4_iv": pedido["salario_minimo"]["hipotese_art85_p4_iv"],
            "fonte_url": pedido["salario_minimo"]["fonte_url"],
        },
        "base_em_salarios_minimos": _fmt(base_sm.quantize(Decimal("0.0001"), rounding=mode)),
        "intervalo": {"minimo": _fmt(total_min), "maximo": _fmt(total_max)},
        "decomposicao": decomposicao,
        "o_que_falta_decidir": [
            "o percentual DENTRO de cada faixa é juízo do art. 85, § 2º, I a IV (grau de zelo, lugar da "
            "prestação do serviço, natureza e importância da causa, trabalho realizado e tempo exigido): "
            "o motor entrega o piso e o teto legais, e o arbitramento é do juízo",
            "a espécie da base (condenação, proveito econômico ou valor atualizado da causa) foi DECLARADA "
            "pelo chamador e não conferida por este motor",
            "a qualificação da parte como Fazenda Pública para efeito do § 3º foi DECLARADA e não conferida",
        ],
        "avisos": [
            "Tema 1076/STJ, que torna cogentes as faixas e excepcional a equidade, estava registrado como "
            "'Acórdão Publicado - RE Pendente' na consulta oficial de 13/08/2026 — reconsulte na data do "
            "cálculo em vez de confiar neste aviso",
        ],
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise HonorariosError("uso_invalido", message)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Honorários de sucumbência — faixas do art. 85, § 3º, do CPC")
    parser.add_argument("--pedido", required=True, help="caminho do JSON do pedido")
    parser.add_argument("--autorizar-experimental", action="store_true",
                        help="habilita o cálculo nesta execução (desabilitado por padrão)")
    try:
        args = parser.parse_args(argv)
        with open(args.pedido, encoding="utf-8") as handle:
            pedido = json.load(handle)
        saida = calcular(pedido, experimental_authorized=args.autorizar_experimental)
    except HonorariosError as exc:
        print(json.dumps({"erro": exc.code, "detalhes": exc.errors}, ensure_ascii=False, indent=2))
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"erro": "arquivo_invalido", "detalhes": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
