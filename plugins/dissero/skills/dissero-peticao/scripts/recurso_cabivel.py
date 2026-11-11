#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'recurso_cabivel.py — agravo do art. 1.042 ou agravo interno: a conta é por CAPÍTULO.'























































from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Mapping


ENGINE_VERSION = "dsr.recurso_cabivel.engine.v1"
REQUEST_VERSION = "dsr.recurso_cabivel.pedido.v1"
MEMORY_VERSION = "dsr.memoria_recurso_cabivel.v1"

AGRAVO_INTERNO = {
    "recurso": "agravo interno",
    "tribunal": "órgão colegiado do tribunal de origem",
    "dispositivo": "art. 1.030, § 2º, do CPC, c/c art. 1.021",
}
AGRAVO_1042 = {
    "recurso": "agravo em recurso especial/extraordinário",
    "tribunal": "tribunal superior (STJ ou STF)",
    "dispositivo": "art. 1.030, § 1º, do CPC, c/c art. 1.042",
}


MAPA_INCISOS = {
    "I_a": AGRAVO_INTERNO,
    "I_b": AGRAVO_INTERNO,
    "II": None,
    "III": AGRAVO_INTERNO,
    "IV": None,
    "V": AGRAVO_1042,
}


INCISOS_DECIDIDOS_PELA_SUBSTANCIA = {"I_a", "I_b", "V"}
RAMOS = {"civel", "penal"}

AVISO_ERRO_GROSSEIRO = (
    "Trocar um agravo pelo outro pode ser tratado como ERRO GROSSEIRO, sem fungibilidade. A "
    "proposição foi corroborada em agregador, mas NÃO confirmada em fonte oficial: o SCON do STJ "
    "recusou a consulta (HTTP 403). Trate como risco sério e não confirmado, e não a cite em "
    "peça sem conferir na fonte"
)


class RecursoCabivelError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def _unknown(value: Mapping[str, Any], allowed: set[str], prefix: str) -> list[str]:
    return [f"{prefix} contém campo não permitido: {key}" for key in value if key not in allowed]


def validar_pedido(pedido: Any) -> list[str]:
    if not isinstance(pedido, Mapping):
        return ["pedido deve ser objeto"]
    errors = _unknown(pedido, {"schema_version", "ramo", "capitulos"}, "pedido")
    if pedido.get("schema_version") != REQUEST_VERSION:
        errors.append(f"schema_version deve ser {REQUEST_VERSION}")
    if pedido.get("ramo") not in RAMOS:
        errors.append(f"ramo deve ser um de {sorted(RAMOS)}")

    capitulos = pedido.get("capitulos")
    if not isinstance(capitulos, list) or not capitulos:
        return errors + [
            "capitulos deve ser lista não vazia: a unidade de classificação é o CAPÍTULO da "
            "decisão, não a decisão — uma só decisão pode exigir dois recursos"]

    vistos = set()
    for index, cap in enumerate(capitulos):
        prefixo = f"capitulos[{index}]"
        if not isinstance(cap, Mapping):
            errors.append(f"{prefixo} deve ser objeto")
            continue
        errors.extend(_unknown(
            cap,
            {"id", "inciso_declarado", "fundado_em_precedente_qualificado", "sintese_do_fundamento"},
            prefixo))
        ident = cap.get("id")
        if not isinstance(ident, str) or not ident.strip():
            errors.append(f"{prefixo}.id obrigatório")
        elif ident in vistos:
            errors.append(f"{prefixo}.id duplicado: {ident}")
        else:
            vistos.add(ident)
        if cap.get("inciso_declarado") not in MAPA_INCISOS:
            errors.append(f"{prefixo}.inciso_declarado deve ser um de {sorted(MAPA_INCISOS)}")


        if cap.get("fundado_em_precedente_qualificado") not in (True, False):
            errors.append(
                f"{prefixo}.fundado_em_precedente_qualificado deve ser declarado (true/false) pelo "
                "advogado: o art. 1.042, caput, testa a SUBSTÂNCIA do fundamento, e o rótulo do "
                "inciso não vincula")
        if not isinstance(cap.get("sintese_do_fundamento"), str) or not cap["sintese_do_fundamento"].strip():
            errors.append(f"{prefixo}.sintese_do_fundamento obrigatória (é o que a Súmula 182 manda impugnar)")
    return errors


def _via_pela_substancia(inciso: str, precedente_qualificado: bool) -> tuple[dict[str, str], str | None]:
    """Devolve (via, divergencia). A substancia manda; o rotulo so gera aviso."""
    if inciso not in INCISOS_DECIDIDOS_PELA_SUBSTANCIA:
        return MAPA_INCISOS[inciso], None
    material = AGRAVO_INTERNO if precedente_qualificado else AGRAVO_1042
    rotulada = MAPA_INCISOS[inciso]
    if material is rotulada:
        return material, None
    return material, (
        f"o capítulo foi rotulado como art. 1.030, {inciso.replace('_', ', ')}, mas a substância "
        f"declarada aponta para {material['recurso']}: o art. 1.042, caput, testa se a decisão está "
        "fundada na aplicação de entendimento de repercussão geral ou repetitivo, e o rótulo não "
        "vincula. Divergência entre rótulo e substância também é a base para sustentar dúvida "
        "objetiva em pedido subsidiário de fungibilidade")


def classificar(pedido: Any) -> dict[str, Any]:
    errors = validar_pedido(pedido)
    if errors:
        raise RecursoCabivelError("pedido_invalido", errors)
    assert isinstance(pedido, Mapping)

    por_via: dict[str, dict[str, Any]] = {}
    sem_recurso: list[dict[str, str]] = []
    divergencias: list[dict[str, str]] = []
    a_impugnar: list[dict[str, str]] = []

    for cap in pedido["capitulos"]:
        inciso = cap["inciso_declarado"]
        via, divergencia = _via_pela_substancia(inciso, cap["fundado_em_precedente_qualificado"])
        a_impugnar.append({"capitulo": cap["id"], "fundamento": cap["sintese_do_fundamento"]})
        if divergencia:
            divergencias.append({"capitulo": cap["id"], "aviso": divergencia})
        if via is None:
            sem_recurso.append({
                "capitulo": cap["id"],
                "inciso": inciso,
                "motivo": (
                    f"o art. 1.030, § 2º, contempla apenas os incisos I e III, e o § 1º apenas o V. "
                    f"Para o inciso {inciso} a lei NÃO nomeia recurso — é lacuna legislativa, e "
                    "preenchê-la é tarefa do advogado, não deste motor"),
            })
            continue
        alvo = por_via.setdefault(via["recurso"], {**via, "capitulos": []})
        alvo["capitulos"].append(cap["id"])

    recursos = sorted(por_via.values(), key=lambda v: v["recurso"])
    cumulacao = len(recursos) > 1

    saida: dict[str, Any] = {
        "schema_version": MEMORY_VERSION,
        "engine_version": ENGINE_VERSION,
        "estado": "MINUTA_PARA_REVISAO",
        "ramo": pedido["ramo"],
        "recursos_exigidos": recursos,
        "cumulacao_obrigatoria": cumulacao,
        "capitulos_sem_recurso_previsto": sem_recurso,
        "divergencias_rotulo_substancia": divergencias,
        "fundamentos_a_impugnar": a_impugnar,
        "prazo": None,
        "o_que_falta_decidir": [
            "a delimitação dos capítulos e a qualificação do fundamento de cada um foram DECLARADAS "
            "pelo advogado: decidir onde termina um capítulo e começa o outro é juízo sobre "
            "cindibilidade do julgado, não segmentação de texto",
            "se o precedente qualificado invocado pela origem realmente se aplica ao caso "
            "(distinguishing) — o motor não afere",
            "se a impugnação redigida ataca ESPECIFICAMENTE cada fundamento acima: o motor os "
            "ENUMERA para a Súmula 182 do STJ, e não julga a suficiência do ataque",
            "PRAZO: o motor não conta. No cível são 15 dias em dias úteis (arts. 1.003, § 5º, e 219); "
            "no penal o art. 798 do CPP manda contar em dias corridos e há divergência publicada "
            "sobre 5 x 15 dias que a fonte oficial não hierarquiza. Contar aqui seria resolver em "
            "silêncio uma contradição que é do advogado",
        ],
        "avisos": [AVISO_ERRO_GROSSEIRO],
    }
    if cumulacao:
        saida["avisos"].insert(0, (
            "CUMULAÇÃO OBRIGATÓRIA: esta decisão tem capítulos de vias diferentes. São devidos OS "
            "DOIS agravos, para DOIS tribunais diferentes, no MESMO prazo — exceção à "
            "unirrecorribilidade. Atacar só um faz precluir o capítulo do outro, e o prazo do "
            "recurso certo NÃO se suspende pela interposição do errado"))
    return saida


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise RecursoCabivelError("uso_invalido", message)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Qual agravo cabe contra a decisão do art. 1.030 do CPC")
    parser.add_argument("--pedido", required=True, help="caminho do JSON do pedido")
    try:
        args = parser.parse_args(argv)
        with open(args.pedido, encoding="utf-8") as handle:
            saida = classificar(json.load(handle))
    except RecursoCabivelError as exc:
        print(json.dumps({"erro": exc.code, "detalhes": exc.errors}, ensure_ascii=False, indent=2))
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"erro": "arquivo_invalido", "detalhes": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
