#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'juntada_contract.py — contrato e regras cruzadas de `dsr.juntada.v1`.'
































from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema_mini import validar_schema

AQUI = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PADRAO = os.path.join(AQUI, "schema_juntada.json")

SCHEMA_VERSION = "dsr.juntada.v1"
NOME_ARTEFATO = "JUNTADA_TRACKER.json"


def texto(valor):
    return str(valor or "").strip()


def carregar_json(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def validar_regras(tracker):
    erros = []
    documentos = tracker.get("documentos") or []
    numeros = [d.get("numero") for d in documentos]

    if len(set(numeros)) != len(numeros):
        repetidos = sorted({n for n in numeros if numeros.count(n) > 1})
        erros.append(f"número de documento repetido: {repetidos}")
    if numeros:
        esperado = list(range(1, len(numeros) + 1))
        if sorted(numeros) != esperado:
            erros.append(f"numeração com salto/lacuna — números {sorted(numeros)}; esperado "
                         f"contador contínuo a partir de 01 (regra dissero-juntada)")
        maior = max(numeros)
        if tracker.get("contador") != maior:
            erros.append(f"contador deve ser o maior número atribuído ({maior}); veio "
                         f"{tracker.get('contador')!r}")
    elif tracker.get("contador") != 0:
        erros.append("tracker sem documentos exige contador 0")

    vistos_arquivo, vistos_sha = {}, {}
    for doc in documentos:
        numero = doc.get("numero")
        prefixo = f"Doc. {numero:02d}: " if isinstance(numero, int) else "Doc. ?: "
        status = doc.get("status")
        sha = texto(doc.get("sha256_arquivo"))
        ids = doc.get("evidence_ids") or []

        if status == "curado":
            if not sha:
                erros.append(prefixo + "status curado exige sha256_arquivo (o arquivo que foi lido)")
            if not ids:
                erros.append(prefixo + "status curado exige evidence_ids — documento sem bloco de "
                                       "leitura não entra na juntada (governança §2.8)")
        if status == "ilegivel" and ids:
            erros.append(prefixo + "status ilegivel com evidence_ids: se há trecho lido, não é ilegível")
        if status == "gerado" and (sha or ids):
            erros.append(prefixo + "status gerado (GUIA) não tem arquivo-fonte nem evidência")

        arquivo = texto(doc.get("arquivo"))
        if arquivo:
            if arquivo in vistos_arquivo:
                erros.append(prefixo + f"arquivo já numerado como Doc. {vistos_arquivo[arquivo]:02d}")
            else:
                vistos_arquivo[arquivo] = numero
        if sha:
            if sha in vistos_sha:
                erros.append(prefixo + f"mesmo conteúdo (sha256) já numerado como Doc. {vistos_sha[sha]:02d}")
            else:
                vistos_sha[sha] = numero
    return erros


def validar_documento(dados, schema_path=SCHEMA_PADRAO):
    """[] quando o ledger está íntegro; lista de erros legíveis quando não."""
    erros = validar_schema(dados, carregar_json(schema_path))
    if erros:
        return erros
    return validar_regras(dados)


def cruzar_com_conferencia(tracker, conferencia):
    'Erros do cruzamento tracker → CONFERENCIA.json. Direção única e declarada: documento da'


    import conferencia_contract as conf

    erros = []
    por_sha = conf.indexar(conferencia)
    ids_validos = conf.evidence_ids(conferencia)
    for doc in tracker.get("documentos") or []:
        numero = doc.get("numero")
        prefixo = f"Doc. {numero:02d}: " if isinstance(numero, int) else "Doc. ?: "
        sha = texto(doc.get("sha256_arquivo"))
        if doc.get("status") != "curado":
            continue
        registro = por_sha.get(sha)
        if registro is None:
            erros.append(prefixo + f"arquivo AUSENTE da conferência de ingestão (sha256 "
                                   f"{sha[:12] or '—'}…) — nada prova que ele foi lido")
            continue
        if registro.get("leitura_status") != "lido":
            erros.append(prefixo + f"conferência registra leitura_status="
                                   f"{registro.get('leitura_status')!r} — só documento LIDO entra "
                                   f"curado na juntada")
        for eid in doc.get("evidence_ids") or []:
            if texto(eid) not in ids_validos:
                erros.append(prefixo + f"evidence_id {eid} não existe na conferência de ingestão")
    return erros


def indexar_por_numero(tracker):
    """{numero: documento} — usado pelo cruzamento do `lint_peca.py --juntada`."""
    return {d.get("numero"): d for d in (tracker.get("documentos") or [])
            if isinstance(d.get("numero"), int)}
