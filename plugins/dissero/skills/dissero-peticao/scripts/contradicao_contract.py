#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'contradicao_contract.py - contrato `dsr.contradicao.v1`: contradicao entre pecas so pode'


































































from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

try:
    from schema_mini import validar_schema
except Exception:
    validar_schema = None

try:
    import conferencia_contract as _conf
except Exception:
    _conf = None

SCHEMA_PADRAO = os.path.join(AQUI, "schema_contradicao.json")
SCHEMA_VERSION = "dsr.contradicao.v1"
NOME_ARTEFATO = "CONTRADICOES.json"
STATUS = ("lastreada", "inconclusiva")



LADOS_EXIGIDOS = 2







MINIMO_CONFERIVEL = 25






MINIMO_PARTE_CONFERIVEL = 12

INDISPONIVEL_SCHEMA = ("schema_mini.py indisponivel ao lado do contrato - sem validador nada "
                       "e conferido, e nada e aprovado (falha fechado)")
INDISPONIVEL_CONF = ("conferencia_contract.py indisponivel ao lado do contrato - a conferencia "
                     "verbatim do lastro nao pode ser feita")
INDISPONIVEL_PISO = ("o confere_transcricao ao alcance nao aceita minimo_parte - o piso de "
                     "cada parte da citacao ficaria fora do controle deste contrato, e lastro "
                     "conferido sob regra desconhecida nao e lastro conferido")


def texto(valor):
    return str(valor or "").strip()


def sha256_texto(valor):
    'SHA-256 na MESMA convencao de `conferencia_contract.sha256_texto` (str + strip antes'



    return hashlib.sha256(texto(valor).encode("utf-8")).hexdigest()


def carregar_json(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def aceita_piso_de_parte(comparador):
    'True se o `confere_transcricao` ao alcance aceita `minimo_parte`.'






    try:
        return "minimo_parte" in inspect.signature(comparador).parameters
    except Exception:
        return False


def indexar_evidencias(conferencia):
    '{evidence_id: (documento, trecho)} a partir de um dataset `dsr.conferencia.v1`.'



    indice = {}
    if not isinstance(conferencia, dict):
        return indice
    documentos = conferencia.get("documentos")
    for documento in documentos if isinstance(documentos, list) else []:
        if not isinstance(documento, dict):
            continue
        trechos = documento.get("trechos")
        for trecho in trechos if isinstance(trechos, list) else []:
            if not isinstance(trecho, dict):
                continue
            eid = texto(trecho.get("evidence_id"))
            if eid:
                indice.setdefault(eid, (documento, trecho))
    return indice


def indice_de(conferencia):
    'None quando NAO HA conferencia (nada e conferivel) - dict quando ha. A distincao'


    if conferencia is None:
        return None
    return indexar_evidencias(conferencia)


def motivos_do_lado(lado, indice, minimo=MINIMO_CONFERIVEL,
                    minimo_parte=MINIMO_PARTE_CONFERIVEL):
    '[] quando o lastro DESTE lado confere - lista de motivos legiveis quando nao.'








    if not isinstance(lado, dict):
        return ["lado nao e um objeto"]

    motivos = []
    literal = lado.get("trecho_literal")
    if not texto(literal):
        motivos.append("sem trecho_literal - contradicao afirmada sem citacao literal")
    elif texto(lado.get("sha256_trecho")) != sha256_texto(literal):
        motivos.append("sha256_trecho nao corresponde ao trecho_literal (citacao alterada "
                       "depois do registro)")

    eid = texto(lado.get("evidence_id"))
    if not eid:
        motivos.append("sem evidence_id - nada aponta para o teor lido")
        return motivos
    if _conf is None:
        motivos.append(INDISPONIVEL_CONF)
        return motivos
    if indice is None:
        motivos.append(f"evidence_id {eid} nao conferido - nenhum CONFERENCIA.json foi "
                       "apresentado ao validador")
        return motivos

    achado = indice.get(eid)
    if achado is None:
        motivos.append(f"evidence_id {eid} nao existe na conferencia de ingestao")
        return motivos
    documento, trecho = achado

    doc_id_real = texto(documento.get("doc_id"))
    doc_id_dito = texto(lado.get("doc_id"))
    if doc_id_dito != doc_id_real:
        motivos.append(f"evidence_id {eid} pertence ao doc_id {doc_id_real or '-'}, e nao ao "
                       f"doc_id {doc_id_dito or '-'} declarado neste lado - citacao atribuida "
                       "a peca errada")




    fonte = getattr(_conf, "trechos_de_texto", None)
    if fonte is None or not any(t is trecho for t in fonte(documento)):
        motivos.append(f"evidence_id {eid} vem de leitura so por imagem (ou de pagina sem camada "
                       "de texto) - o teor registrado e descricao, nao citacao literal, e nao "
                       "serve de lastro de contradicao")
        return motivos

    if not texto(literal):
        return motivos
    if len(_conf.normalizar_trecho(literal)) < minimo:
        motivos.append(f"trecho_literal com menos de {minimo} caracteres normalizados: abaixo "
                       "desse tamanho o comparador da casa devolve True por construcao, e "
                       "lastro que nao pode ser conferido nao e lastro")
    elif not aceita_piso_de_parte(_conf.confere_transcricao):
        motivos.append(INDISPONIVEL_PISO)
    elif not _conf.confere_transcricao(literal, [trecho.get("trecho_literal") or ""],
                                       minimo=minimo, minimo_parte=minimo_parte):
        motivos.append(f"trecho_literal NAO confere com o teor lido em {eid} - citacao que o "
                       "documento nao diz")
    return motivos


def derivar_status(contradicao, conferencia=None, minimo=MINIMO_CONFERIVEL,
                   minimo_parte=MINIMO_PARTE_CONFERIVEL):
    "'lastreada' | 'inconclusiva' - DERIVADO, nunca aceito como declarado."








    if not isinstance(contradicao, dict):
        return "inconclusiva"
    lados = contradicao.get("lados")
    if not isinstance(lados, list) or len(lados) != LADOS_EXIGIDOS:
        return "inconclusiva"
    ids = [texto(lado.get("evidence_id")) if isinstance(lado, dict) else "" for lado in lados]
    if "" in ids or len(set(ids)) != len(ids):
        return "inconclusiva"
    indice = indice_de(conferencia)
    for lado in lados:
        if motivos_do_lado(lado, indice, minimo, minimo_parte):
            return "inconclusiva"
    return "lastreada"


def validar_regras(contradicao, conferencia=None, exigir_lastro=True, minimo=MINIMO_CONFERIVEL,
                   minimo_parte=MINIMO_PARTE_CONFERIVEL):
    'Erros de UMA contradicao. Lista vazia = registro integro.'






    if not isinstance(contradicao, dict):
        return ["contradicao nao e um objeto"]

    erros = []
    rotulo = f"contradicao {texto(contradicao.get('id')) or '?'}: "

    brutos = contradicao.get("lados")
    lados = brutos if isinstance(brutos, list) else []
    if not isinstance(brutos, list):
        erros.append(rotulo + "lados deve ser uma lista")
    elif len(lados) != LADOS_EXIGIDOS:
        erros.append(rotulo + f"exige exatamente {LADOS_EXIGIDOS} lados com lastro literal, "
                              f"veio {len(lados)} - afirmar contradicao com um lado so e "
                              "afirmar sobre o lado que ninguem mostrou")
    else:
        ids = [texto(lado.get("evidence_id")) if isinstance(lado, dict) else "" for lado in lados]
        if "" not in ids and len(set(ids)) != len(ids):
            erros.append(rotulo + f"os dois lados apontam o mesmo evidence_id ({ids[0]}) - o "
                                  "mesmo trecho citado duas vezes e um lastro, nao dois")

    derivado = derivar_status(contradicao, conferencia, minimo, minimo_parte)
    declarado = contradicao.get("status")
    if declarado != derivado:
        erros.append(rotulo + f"status declarado {declarado!r}, derivado {derivado!r} - status "
                              "e derivado do lastro, nunca declarado")

    if exigir_lastro and derivado != "lastreada":
        indice = indice_de(conferencia)
        for posicao, lado in enumerate(lados):
            for motivo in motivos_do_lado(lado, indice, minimo, minimo_parte):
                erros.append(rotulo + f"lado[{posicao}]: " + motivo)
        if not erros:
            erros.append(rotulo + "sem os dois lastros conferidos - contradicao nao afirmada")
    return erros


def validar_documento(dados, conferencia=None, schema_path=SCHEMA_PADRAO, exigir_lastro=True,
                      minimo=MINIMO_CONFERIVEL, minimo_parte=MINIMO_PARTE_CONFERIVEL):
    '[] quando o dataset esta integro - lista de erros legiveis quando nao.'






    if validar_schema is None:
        return [INDISPONIVEL_SCHEMA]
    try:
        schema = carregar_json(schema_path)
    except Exception as erro:
        return [f"schema {schema_path} ilegivel: {erro.__class__.__name__}: {erro}"]

    erros = validar_schema(dados, schema)
    if erros:
        return erros

    vistos = set()
    for contradicao in dados["contradicoes"]:
        erros.extend(validar_regras(contradicao, conferencia, exigir_lastro, minimo,
                                    minimo_parte))
        cid = texto(contradicao.get("id")) if isinstance(contradicao, dict) else ""
        if cid and cid in vistos:
            erros.append(f"contradicao {cid}: id repetido no dataset")
        elif cid:
            vistos.add(cid)
    return erros


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Valida um CONTRADICOES.json (dsr.contradicao.v1). Nao decide se ha "
                    "contradicao: confere se a afirmacao vem com os dois lastros literais.")
    ap.add_argument("contradicoes", help="caminho do CONTRADICOES.json")
    ap.add_argument("--conferencia", default=None,
                    help="caminho do CONFERENCIA.json (dsr.conferencia.v1). Sem ele NADA e "
                         "conferivel e nenhuma contradicao pode ser lastreada.")
    ap.add_argument("--permitir-inconclusiva", action="store_true",
                    help="modo triagem: aceita registro honestamente declarado inconclusiva. "
                         "Por padrao o contrato EXIGE lastro.")
    ap.add_argument("--minimo", type=int, default=MINIMO_CONFERIVEL,
                    help=f"piso do TOTAL normalizado da citacao para ela poder ser lastro "
                         f"(padrao {MINIMO_CONFERIVEL}, herdado de confere_transcricao). "
                         "Baixar AFROUXA: aceita citacao mais curta.")
    ap.add_argument("--minimo-parte", type=int, default=MINIMO_PARTE_CONFERIVEL,
                    dest="minimo_parte",
                    help=f"piso de CADA parte separada por elipse dentro da citacao (padrao "
                         f"{MINIMO_PARTE_CONFERIVEL}, herdado de confere_transcricao). Parte "
                         "abaixo do piso e ignorada na comparacao; baixar APERTA, porque passa "
                         "a cobrar pedaco menor.")
    args = ap.parse_args(argv)

    try:
        dados = carregar_json(args.contradicoes)
    except Exception as erro:
        print(f"ERRO {args.contradicoes} ilegivel: {erro.__class__.__name__}: {erro}")
        return 2
    conferencia = None
    if args.conferencia:
        try:
            conferencia = carregar_json(args.conferencia)
        except Exception as erro:
            print(f"ERRO {args.conferencia} ilegivel: {erro.__class__.__name__}: {erro}")
            return 2

    erros = validar_documento(dados, conferencia,
                              exigir_lastro=not args.permitir_inconclusiva,
                              minimo=args.minimo, minimo_parte=args.minimo_parte)
    for erro in erros:
        print("REPROVA " + erro)
    if erros:
        return 1
    total = len(dados.get("contradicoes") or []) if isinstance(dados, dict) else 0


    print(f"OK {total} registro(s) de contradicao com lastro conferido "
          f"(minimo={args.minimo}, minimo_parte={args.minimo_parte})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
