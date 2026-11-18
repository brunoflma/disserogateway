#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Presunção de relevância pelo valor da causa (CF, art. 105, § 3º, III).'











































from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

try:
    import ficha_capacidade
    import competencia
except ImportError:
    from . import ficha_capacidade, competencia


CAPACIDADE = "relevancia_presuncao_valor"
CHAVE = "DSR_RELEVANCIA_VALOR_EXPERIMENTAL"
VERSAO_PEDIDO = "dsr.relevancia_presuncao_valor.pedido.v1"
VERSAO_MEMORIA = "dsr.relevancia_presuncao_valor.memoria.v1"
MULTIPLO = Decimal(500)
CODIGOS = (
    "capacidade_desabilitada", "pedido_invalido", "atualizacao_sem_origem", "tabela_invalida",
    "tabela_sm_fora_vigencia",
) + ficha_capacidade.CODIGOS
ORIGENS = ("memoria_de_calculo", "declarado_pelo_advogado")
_CHAVES = {"schema_version", "valor_da_causa", "data_interposicao", "valor_atualizado",
           "atualizacao"}
_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?$")
_DATA = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CENTAVOS = Decimal("0.01")
CONFERIDO_EM = "17/11/2026"
_EC125 = "https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc125.htm"
_NOTICIA_30082026 = ("https://www.stj.jus.br/sites/portalp/Paginas/Comunicacao/Noticias/2026/"
                     "30082026-Relevancia-da-questao-federal-o-que-muda-na-atuacao-do-STJ-com-o-"
                     "novo-sistema.aspx")

_ER55 = "https://www.stj.jus.br/publicacaoinstitucional/index.php/Regimento/issue/current"

FUNDAMENTOS = (
    {"regra": "CF, art. 105, § 3º, III (EC 125/2022): há relevância nas ações cujo valor da "
              "causa ultrapasse 500 salários mínimos", "fonte_url": _EC125,
     "conferido_em": CONFERIDO_EM},
    {"regra": "EC 125/2022, art. 2º: a parte pode atualizar o valor da causa, na interposição, "
              "para os fins do inciso III", "fonte_url": _EC125, "conferido_em": CONFERIDO_EM},
    {"regra": "Notícia oficial do STJ de 30/08/2026: mesmo com a relevância presumida, o "
              "recorrente trata da relevância em tópico específico do recurso",
     "fonte_url": _NOTICIA_30082026, "conferido_em": CONFERIDO_EM},
    {"regra": "RISTJ, art. 255-J, parágrafo único (ER 55/2026, DJe 26/08/2026, p. 10): o "
              "recorrente demonstra a relevância inclusive nas hipóteses de presunção, sob pena "
              "de inadmissão ou não conhecimento", "fonte_url": _ER55,
     "conferido_em": CONFERIDO_EM},
    {"regra": "RISTJ, art. 255-K, § 2º (ER 55/2026, p. 10): no inciso III, o STJ pode apreciar "
              "de ofício a correção do valor atribuído à causa, segundo as regras processuais "
              "de fixação, e negar a relevância quando o valor não corresponder aos parâmetros "
              "legais", "fonte_url": _ER55, "conferido_em": CONFERIDO_EM},
)
NOTA_DATA = ("A data de referência do salário mínimo é a da interposição. É interpretação: a "
             "Constituição não fixa a data, e a ER 55/2026 do STJ também não fixa (o art. 255-K, "
             "§ 2º, remete às regras processuais de fixação do valor da causa). A escolha "
             "acompanha o art. 2º da EC 125/2022, que permite atualizar o valor da causa na "
             "interposição.")
LIMITES = (
    "Mesmo com a relevância presumida, o recurso especial trata da relevância em tópico "
    "específico, demonstrando a hipótese no caso concreto (RISTJ, art. 255-J, parágrafo "
    "único; notícia oficial do STJ de 30/08/2026). A conta não substitui o tópico.",
    NOTA_DATA,
    "O STJ pode apreciar de ofício a correção do valor atribuído à causa e negar a relevância "
    "quando ele não corresponder aos parâmetros legais (RISTJ, art. 255-K, § 2º): a conta "
    "parte do valor declarado, e o tópico justifica esse valor.",
    "O valor atualizado é o que o advogado declara ou o que a memória de atualização apurou; "
    "este cálculo não atualiza valor nenhum.",
)


class PresuncaoValorError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def _reais(valor: Decimal) -> str:
    q = valor.quantize(_CENTAVOS, rounding=ROUND_HALF_EVEN)
    inteiro, _, cent = f"{q:.2f}".partition(".")
    grupos = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return "R$ " + ".".join(grupos) + "," + cent


def _q(valor: Decimal) -> str:
    return f"{valor.quantize(_CENTAVOS, rounding=ROUND_HALF_EVEN):.2f}"


def _valor(texto: Any, campo: str, erros: list[str]) -> Decimal | None:
    if not isinstance(texto, str) or not _DECIMAL.match(texto.strip()):
        erros.append(f"{campo}: decimal com ponto e até duas casas, em reais (ex.: \"850000.00\")")
        return None
    try:
        valor = Decimal(texto.strip())
    except InvalidOperation:
        erros.append(f"{campo}: decimal ilegível")
        return None
    if valor <= 0:
        erros.append(f"{campo}: tem de ser maior que zero")
        return None
    return valor


def _data(texto: Any, campo: str, erros: list[str]) -> dt.date | None:
    if not isinstance(texto, str) or not _DATA.match(texto):
        erros.append(f"{campo}: data no formato AAAA-MM-DD")
        return None
    try:
        return dt.date.fromisoformat(texto)
    except ValueError:
        erros.append(f"{campo}: data inexistente")
        return None


def _tabela(tabela: Any) -> list[dict]:
    if tabela is None:
        return [dict(x) for x in competencia.TABELA_SALARIO_MINIMO]
    try:
        return competencia._validar_tabela(tabela)
    except competencia.ErroCompetencia as exc:
        raise PresuncaoValorError("tabela_invalida", str(exc)) from None


def salario_minimo_em(data: dt.date, tabela: Any = None) -> dict | None:
    """A linha da tabela de salário mínimo vigente em `data`, ou None fora da tabela."""
    iso = data.isoformat()
    for linha in _tabela(tabela):
        if linha["inicio"] <= iso <= linha["fim"]:
            return linha
    return None


def _validar_pedido(pedido: Any) -> tuple[dict, list[str]]:
    if not isinstance(pedido, dict):
        return {}, ["o pedido é um objeto JSON"]
    erros: list[str] = []
    extras = sorted(set(pedido) - _CHAVES)
    if extras:
        erros.append("chave(s) desconhecida(s): " + ", ".join(extras))
    if pedido.get("schema_version") != VERSAO_PEDIDO:
        erros.append(f"schema_version: {VERSAO_PEDIDO}")
    lido = {
        "valor_da_causa": _valor(pedido.get("valor_da_causa"), "valor_da_causa", erros),
        "data_interposicao": _data(pedido.get("data_interposicao"), "data_interposicao", erros),
        "valor_atualizado": None,
        "atualizacao": None,
    }
    if "valor_atualizado" in pedido:
        lido["valor_atualizado"] = _valor(pedido["valor_atualizado"], "valor_atualizado", erros)
        atu = pedido.get("atualizacao")
        if atu is None:
            return lido, erros + ["__sem_origem__"]
        if not isinstance(atu, dict):
            erros.append("atualizacao: objeto com origem e referencia")
        else:
            if atu.get("origem") not in ORIGENS:
                erros.append("atualizacao.origem: " + " ou ".join(ORIGENS))
            if not isinstance(atu.get("referencia"), str) or not atu["referencia"].strip():
                erros.append("atualizacao.referencia: diga de onde vem o valor atualizado")
            sha = atu.get("sha256")
            if atu.get("origem") == "memoria_de_calculo" and not (
                    isinstance(sha, str) and _SHA256.match(sha)):
                erros.append("atualizacao.sha256: a memória de cálculo vai com o sha256 dela")
            elif sha is not None and not (isinstance(sha, str) and _SHA256.match(sha)):
                erros.append("atualizacao.sha256: 64 caracteres hexadecimais minúsculos")
            extras_atu = sorted(set(atu) - {"origem", "referencia", "sha256"})
            if extras_atu:
                erros.append("atualizacao: chave(s) desconhecida(s): " + ", ".join(extras_atu))
            lido["atualizacao"] = {k: atu.get(k) for k in ("origem", "referencia", "sha256")}
    elif "atualizacao" in pedido:
        erros.append("atualizacao sem valor_atualizado: informe o valor atualizado ou retire a "
                     "atualizacao")
    return lido, erros


def calcular(pedido: Any, *, hoje: dt.date | None = None, experimental_authorized: bool = False,
             registro_capacidades: Any = None, tabela_salario_minimo: Any = None) -> dict:
    'Memória da conta; desabilitado por padrão.'



    if experimental_authorized is not True:
        raise PresuncaoValorError(
            "capacidade_desabilitada",
            "A conta da presunção pelo valor da causa é experimental e exige autorização "
            "explícita nesta execução.")
    hoje = hoje or dt.date.today()
    try:
        ficha_capacidade.exigir(CAPACIDADE, hoje=hoje, registro=registro_capacidades)
    except ficha_capacidade.FichaRecusada as exc:
        raise PresuncaoValorError(exc.codigo, exc.mensagem) from None
    lido, erros = _validar_pedido(pedido)
    if "__sem_origem__" in erros:
        raise PresuncaoValorError(
            "atualizacao_sem_origem",
            "O valor atualizado veio sem a origem da atualização. Informe `atualizacao` com a "
            "origem (memória de cálculo, com o sha256, ou valor declarado pelo advogado) e a "
            "referência.")
    if erros:
        raise PresuncaoValorError("pedido_invalido", erros)

    data = lido["data_interposicao"]
    sm = salario_minimo_em(data, tabela_salario_minimo)
    if sm is None:
        raise PresuncaoValorError(
            "tabela_sm_fora_vigencia",
            f"A tabela de salário mínimo não cobre {data.strftime('%d/%m/%Y')}. Atualize a "
            f"tabela (--salario-minimo-tabela) com a norma oficial do período; o limite não se "
            f"estima.")
    valor_sm = Decimal(sm["valor"])
    limite = valor_sm * MULTIPLO
    atualizado = lido["valor_atualizado"]
    considerado = atualizado if atualizado is not None else lido["valor_da_causa"]
    base = "valor_atualizado" if atualizado is not None else "valor_da_causa"
    presume = considerado > limite
    avisos = []
    if atualizado is not None and atualizado < lido["valor_da_causa"]:
        avisos.append("O valor atualizado é menor que o valor da causa original. Confira a "
                      "memória de atualização antes de usá-lo.")
    if not presume and considerado == limite:
        avisos.append("O valor é exatamente 500 salários mínimos: o texto exige que o valor "
                      "ultrapasse o limite, e aqui não ultrapassa.")
    nome_valor = "valor atualizado da causa" if base == "valor_atualizado" else "valor da causa"
    resultado = (
        f"O {nome_valor}, {_reais(considerado)}, "
        + ("ultrapassa" if presume else "não ultrapassa")
        + f" 500 salários mínimos ({_reais(limite)}, com o salário mínimo de "
        f"{_reais(valor_sm)} vigente em {data.strftime('%d/%m/%Y')}, data da interposição).")
    sugestao = None
    if presume:
        sugestao = {
            "inciso": "III",
            "fundamento": (
                f"Relevância presumida (CF, art. 105, § 3º, III): o {nome_valor} "
                f"({_reais(considerado)}) ultrapassa 500 salários mínimos ({_reais(limite)}), "
                f"pelo salário mínimo vigente na data da interposição "
                f"({data.strftime('%d/%m/%Y')})."),
        }
    return {
        "schema_version": VERSAO_MEMORIA,
        "status": "MINUTA PARA REVISÃO",
        "capacidade": CAPACIDADE,
        "valor_da_causa": _q(lido["valor_da_causa"]),
        "valor_atualizado": _q(atualizado) if atualizado is not None else None,
        "atualizacao": lido["atualizacao"],
        "base_do_valor": base,
        "valor_considerado": _q(considerado),
        "salario_minimo": {"valor": _q(valor_sm), "norma": sm.get("norma"),
                           "fonte_url": sm.get("fonte_url"),
                           "conferido_em": sm.get("conferido_em"),
                           "vigencia": {"inicio": sm["inicio"], "fim": sm["fim"]}},
        "data_de_referencia": {"data": data.isoformat(), "criterio": "data da interposição",
                               "situacao": "interpretacao_a_confirmar", "nota": NOTA_DATA},
        "limite": _q(limite),
        "razao_em_salarios_minimos": _q(considerado / valor_sm),
        "presume": presume,
        "resultado": resultado,
        "presuncao_sugerida": sugestao,
        "fundamentos": [dict(f) for f in FUNDAMENTOS],
        "avisos": avisos,
        "limites": list(LIMITES),
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PresuncaoValorError("pedido_invalido", message)


def _ler_json(caminho: str, codigo: str, o_que: str):
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, UnicodeError, ValueError):
        raise PresuncaoValorError(codigo, f"{o_que} não pôde ser lido como JSON") from None


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description="Presunção de relevância pelo valor da causa (500 SM)")
    parser.add_argument("--pedido", required=True, help="caminho do JSON do pedido")
    parser.add_argument("--salario-minimo-tabela", help="lista [{valor, inicio, fim, norma, "
                                                        "fonte_url}] que substitui a tabela")
    try:
        args = parser.parse_args(argv)
        pedido = _ler_json(args.pedido, "pedido_invalido", "o pedido")
        tabela = (_ler_json(args.salario_minimo_tabela, "tabela_invalida", "a tabela")
                  if args.salario_minimo_tabela else None)
        memoria = calcular(pedido, experimental_authorized=os.environ.get(CHAVE) == "1",
                           tabela_salario_minimo=tabela)
    except PresuncaoValorError as exc:
        print(json.dumps({"ok": False, "error_code": exc.code, "errors": exc.errors,
                          "status": "INCONCLUSIVO"}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"ok": True, "memoria": memoria}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
