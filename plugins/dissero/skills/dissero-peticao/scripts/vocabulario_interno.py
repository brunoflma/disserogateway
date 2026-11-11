#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'vocabulario_interno.py — fronteira entre a MÁQUINA e o DOCUMENTO DO ESCRITÓRIO.'






























from __future__ import annotations

import re




SUBSTITUICOES = [

    (r"\bregistrar_confirmacao_manual\.py\b", "o registro de conferência do escritório"),
    (r"\bvalidar_achados\.py\b", "a validação desta Relação"),
    (r"\bdiagnosticar_fontes\.py\b", "o diagnóstico dos links das fontes"),
    (r"\bverificar_citacao\.py\b", "a verificação da citação"),
    (r"\bbuild_precedentes\.py\b", "a geração desta Relação"),
    (r"\blint_peca\.py\b", "a conferência final da peça"),
    (r"\bbuild_docx\.py\b", "a geração da peça"),

    (r"\bdissero-pesquisa-juridica\b", "a pesquisa jurisprudencial"),
    (r"\bdissero-visual-law\b", "a formatação da peça"),
    (r"\bdissero-peticao\b", "a redação da peça"),
    (r"\bdissero-caso-complexo\b", "a redação do caso"),
    (r"\bdissero-ingestao\b", "a leitura dos autos"),
    (r"\bdissero-juntada\b", "a juntada de documentos"),
    (r"\bdissero-orquestrador\b", "a triagem do caso"),


    (r"\b(?:[a-z]+-)?clone-juridico\b", "o padrão de redação do escritório"),




    (r"\bDataJud\b", "a base de dados processuais"),
    (r"\bLexML\b", "o repositório de legislação"),

    (r"\bdsr\.achados?\.v\d+\b", "o padrão desta Relação"),
    (r"\bdsr\.juntada\.v\d+\b", "o registro da juntada"),
    (r"\bdsr\.conferencia\.v\d+\b", "o registro de conferência da leitura"),
    (r"\bschema_version\b", "versão do padrão"),
    (r"\bsyllabus_literal\b", "a ementa literal"),
    (r"\bofficial_url\b", "o endereço da fonte oficial"),
    (r"\bpendencia_fonte\b", "a pendência de fonte"),
    (r"\bselected_for_use\b", "a seleção para uso na peça"),
    (r"\bhuman_attestation\b", "a atestação do advogado"),
    (r"\bfull_text\b", "o inteiro teor"),
    (r"\buse_status\b", "a situação do precedente"),

    (r"\bprohibited\b", "vedado"),
    (r"\ballowed\b", "liberado"),
    (r"\bpending\b", "a conferir"),



    (r"\bCNPJa\b", "o cadastro oficial de pessoa jurídica"),

    (r"\bplaceholders?\b", "marcação provisória"),
    (r"\bdatasets?\b", "a Relação de Precedentes"),
    (r"\blinter\b", "a conferência final"),
    (r"\bCONV-\d+\b", "a convenção do escritório"),
    (r"\bnesta sess(?:ão|ao)\b", "nesta pesquisa"),
]

_SUBS = [(re.compile(rx, re.IGNORECASE), novo) for rx, novo in SUBSTITUICOES]










CLASSES = [
    ("nome de skill do plugin", r"\bdissero-[a-z][a-z\-]{2,}\b"),
    ("nome de script", r"\b[a-z][a-z0-9_]{2,}\.py\b"),


    ("nome de script", r"\bestado[\W_]{1,3}peca\b(?!\.py\b)"),
    ("nome de contrato interno", r"\bdsr\.[a-z_]+(?:\.[a-z_]+)*\.v\d+\b"),
    ("nome de campo do registro",
     r"\b(?:use_status|selected_for_use|official_url|syllabus_literal|pendencia_fonte"
     r"|full_text|human_attestation|schema_version|checked_at|judgment_date"
     r"|case_number|norm_number)\b"),
    ("estado do registro em inglês", r"\b(?:allowed|prohibited|pending)\b"),
    ("jargão de ferramenta",
     r"\b(?:placeholders?|datasets?|linter|parser|hardcoded|commit|payload|endpoint"
     r"|schema|json|log)\b"),
    ("marca de conector", r"\b(?:DataJud|LexML|CNPJa)\b"),













    ("identificador de ferramenta ou campo", r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b(?!\.py\b)"),
    ("referência a convenção interna", r"\bCONV-\d+\b"),
    ("diagnóstico de sessão",
     r"\b(?:nesta sess(?:ão|ao)|reverifica(?:ção|cao) autom(?:á|a)tica"
     r"|verifica(?:ção|cao) autom(?:á|a)tica pendente)\b"),
]

_CLASSES = [(rotulo, re.compile(rx, re.IGNORECASE)) for rotulo, rx in CLASSES]






_EMAIL_RX = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_URL_RX = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)


_ZW = "​"


def _sem_enderecos(texto):
    s = (texto or "").replace(_ZW, "")
    return _URL_RX.sub(" ", _EMAIL_RX.sub(" ", s))


def sanitizar(texto):
    'Troca o vocabulário interno conhecido pelo equivalente em linguagem de advogado.'



    s = texto or ""
    for rx, novo in _SUBS:
        s = rx.sub(novo, s)
    return s


def residuos(texto, contexto=""):
    'Vocabulário interno encontrado em `texto`.'








    s = _sem_enderecos(texto)
    achados, vistos = [], set()
    for rotulo, rx in _CLASSES:
        for m in rx.finditer(s):
            termo = m.group(0)
            if termo.lower() in vistos:
                continue
            vistos.add(termo.lower())
            achados.append({"classe": rotulo, "termo": termo, "contexto": contexto})
    return achados


def limpo(texto):
    """Atalho de leitura: True quando nada do vocabulário interno sobrou."""
    return not residuos(texto)
