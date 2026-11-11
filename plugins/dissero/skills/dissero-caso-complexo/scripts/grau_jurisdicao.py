#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'grau_jurisdicao.py — GRAU DE JURISDIÇÃO da peça e as formas de tratamento que ele impõe.'

























from __future__ import annotations

import re
import unicodedata

GRAUS = ("primeiro", "segundo", "superior")





_CLASSES = (

    ("recurso especial", "superior"),
    ("recurso extraordinario", "superior"),
    ("agravo em recurso especial", "superior"),
    ("agravo em recurso extraordinario", "superior"),
    ("embargos de divergencia", "superior"),
    ("recurso ordinario constitucional", "superior"),
    ("reclamacao constitucional", "superior"),
    ("recurso de revista", "superior"),
    ("agravo de instrumento em recurso de revista", "superior"),
    ("suspensao de liminar", "superior"),
    ("suspensao de seguranca", "superior"),
    ("aresp", "superior"),
    ("resp", "superior"),
    ("agint", "superior"),

    ("razoes de apelacao", "segundo"),
    ("contrarrazoes de apelacao", "segundo"),
    ("apelacao", "segundo"),
    ("agravo de instrumento", "segundo"),
    ("agravo interno", "segundo"),
    ("agravo regimental", "segundo"),
    ("embargos infringentes", "segundo"),
    ("embargos de nulidade", "segundo"),
    ("recurso adesivo", "segundo"),
    ("remessa necessaria", "segundo"),
    ("mandado de seguranca contra ato judicial", "segundo"),
    ("habeas corpus", "segundo"),
    ("conflito de competencia", "segundo"),
    ("recurso em sentido estrito", "segundo"),
    ("carta testemunhavel", "segundo"),
    ("acao rescisoria", "segundo"),

    ("peticao inicial", "primeiro"),
    ("inicial", "primeiro"),
    ("contestacao", "primeiro"),
    ("reconvencao", "primeiro"),
    ("replica", "primeiro"),
    ("impugnacao ao cumprimento", "primeiro"),
    ("impugnacao", "primeiro"),
    ("embargos a execucao", "primeiro"),
    ("embargos de terceiro", "primeiro"),
    ("embargos monitorios", "primeiro"),
    ("cumprimento de sentenca", "primeiro"),
    ("execucao de titulo", "primeiro"),
    ("alegacoes finais", "primeiro"),
    ("memoriais", "primeiro"),
    ("manifestacao", "primeiro"),
    ("tutela cautelar antecedente", "primeiro"),
    ("acao de", "primeiro"),
    ("acao ", "primeiro"),
)




_AMBIGUAS = ("embargos de declaracao", "embargos declaratorios", "peticao simples",
             "peticao intercorrente", "juntada", "dilacao de prazo", "substabelecimento")


def _norm(s):
    """Minúsculas, sem acento, espaços colapsados — para comparar rótulo de classe."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.lower()).strip()


def derivar(classe_processual, tribunal=None):
    "Grau a partir da CLASSE processual do briefing. Devolve 'primeiro'|'segundo'|"





    c = _norm(classe_processual)
    if not c:
        return None
    if any(a in c for a in _AMBIGUAS):
        t = _norm(tribunal)
        if any(x in t for x in ("stj", "stf", "tst", "tse", "stm", "superior tribunal",
                                "supremo tribunal")):
            return "superior"
        if any(x in t for x in ("tribunal de justica", "tjsp", "tjce", "trf", "trt",
                                "camara", "turma recursal", "desembargador")):
            return "segundo"
        return None
    for chave, grau in _CLASSES:
        if chave in c:
            return grau
    return None



_RX_SUPERIOR = re.compile(
    r"superior tribunal de justica|supremo tribunal federal|tribunal superior do trabalho"
    r"|tribunal superior eleitoral|eminentes? ministros?|colendo superior")
_RX_SEGUNDO = re.compile(
    r"egregio tribunal|colenda camara|colenda turma|inclitos? desembargadores?"
    r"|tribunal de justica|tribunal regional|razoes de apelacao|contrarrazoes de apelacao"
    r"|camara de direito|orgao especial")
_RX_PRIMEIRO = re.compile(
    r"juiz(?:o)? de direito|vara (?:civel|criminal|do trabalho|de familia|federal|unica)"
    r"|meritissim|douto juizo|mm\.? *juiz|juizado especial|comarca de")


def detectar_no_texto(paragrafos, limite=12):
    'Grau inferido do ENDEREÇAMENTO (primeiros parágrafos). Fallback quando o chamador não'







    cabeca = _norm(" \n ".join(str(p) for p in list(paragrafos)[:limite]))
    if not cabeca:
        return None
    if _RX_SUPERIOR.search(cabeca):
        return "superior"
    if _RX_SEGUNDO.search(cabeca):
        return "segundo"
    if _RX_PRIMEIRO.search(cabeca):
        return "primeiro"
    return None










_RX_MM_JUIZ = re.compile(r"\bM\.?\s?M\.?\s+Juiz|\bMM\b\.?\s+Ju[íi]z", re.I)

_RX_MERITISSIMO = re.compile(r"\bmerit[íi]ssim[oa]s?\b", re.I)
_RX_DOUTO_JUIZO = re.compile(r"\bdout[oa]s?\s+ju[íi]z[oa]\b", re.I)
_RX_EXMO_JUIZ = re.compile(r"\bexcelent[íi]ssimo\s+senhor\s+(?:doutor\s+)?ju[íi]z", re.I)

_COLEGIADO_VEDADOS = (
    ("vocativo singular 'Note Excelência'",
     re.compile(r"\b(?:note|veja|observe|atente|repare|perceba)[- ]?(?:se)?\s+(?:bem\s+)?"
                r"(?:,\s*)?(?:vossa\s+)?excel[êe]ncia\b", re.I),
     "em peça colegiada o destinatário é o órgão: 'note-se', 'observe esta Colenda Câmara', "
     "'cumpre destacar a este Egrégio Tribunal'"),
    ("vocativo singular 'Vossa Excelência' no corpo",
     re.compile(r"\bvossa\s+excel[êe]ncia\b", re.I),
     "no corpo, use o tratamento colegiado ('Vossas Excelências', 'esta Colenda Câmara', "
     "'este Egrégio Tribunal'); a fórmula de fecho do perfil permanece intocada"),
    ("tratamento de primeiro grau 'Douto Juízo'",
     _RX_DOUTO_JUIZO,
     "'este Egrégio Tribunal', 'esta Colenda Câmara' — o juízo é o de origem, não o "
     "destinatário do recurso"),
    ("tratamento de primeiro grau 'MM. Juiz'",
     _RX_MM_JUIZ,
     "'Ínclitos Desembargadores', 'Eméritos Ministros' conforme o tribunal"),
    ("tratamento de primeiro grau 'Meritíssimo'",
     _RX_MERITISSIMO,
     "'Ínclitos Desembargadores' / 'Eméritos Ministros'"),
    ("tratamento de primeiro grau 'Excelentíssimo Senhor Doutor Juiz'",
     _RX_EXMO_JUIZ,
     "endereçamento colegiado ('EGRÉGIO TRIBUNAL… / COLENDA CÂMARA… / ÍNCLITOS "
     "DESEMBARGADORES')"),
)



_RX_DESEMBARGADORES = re.compile(r"\b(?:[íi]nclit|egr[ée]gi|dout|nobr)[oa]s?\s+desembargador",
                                 re.I)
_RX_MINISTROS = re.compile(r"\bem[ée]rit[oa]s?\s+ministr|eminentes?\s+ministr", re.I)

_PRIMEIRO_VEDADOS = (
    ("tratamento colegiado 'Colenda Câmara' em peça de primeiro grau",
     re.compile(r"\bcolend[oa]s?\s+(?:c[âa]mara|turma|se[çc][ãa]o|corte)\b", re.I),
     "'este MM. Juízo', 'Vossa Excelência' — o destinatário é o juiz da causa"),
    ("tratamento colegiado 'Ínclitos Desembargadores' em peça de primeiro grau",
     _RX_DESEMBARGADORES,
     "'Meritíssimo Juiz', 'Vossa Excelência'"),
    ("tratamento colegiado 'Egrégio Tribunal' como vocativo em peça de primeiro grau",
     re.compile(r"\begr[ée]gi[oa]\s+tribunal\b", re.I),
     "citar o tribunal como referência é legítimo; como VOCATIVO, não — o destinatário é o "
     "MM. Juízo da causa"),
    ("tratamento colegiado 'Eméritos Ministros' em peça de primeiro grau",
     _RX_MINISTROS,
     "'Meritíssimo Juiz', 'Vossa Excelência'"),
)









_INTERPOSICAO_VEDADOS = (
    ("tratamento colegiado 'Ínclitos Desembargadores'",
     _RX_DESEMBARGADORES,
     "a interposição se dirige ao juízo de origem: 'Vossa Excelência', 'este MM. Juízo'; o "
     "tratamento colegiado vai na folha de razões"),
    ("tratamento colegiado 'Eméritos Ministros'",
     _RX_MINISTROS,
     "a interposição se dirige ao juízo de origem: 'Vossa Excelência'; o tratamento "
     "colegiado vai na folha de razões"),
)











_RX_DESEMBARGADORES_PLURAL = re.compile(
    r"\b(?:[íi]nclit|egr[ée]gi|dout|nobr)[oa]s\s+desembargador", re.I)
_RX_MINISTROS_PLURAL = re.compile(r"\bem[ée]rit[oa]s\s+ministr|\beminentes\s+ministr", re.I)

_RX_TURMA_RECURSAL = re.compile(r"\b(?:turmas?|colegios?)\s+recursa(?:l|is)\b")
_RX_ALCADA = re.compile(r"\b(?:causas?\s+de\s+)?alcada\b|\blei\s+(?:n\S*\s+)?6\.?830\b")
_REMEDIO_PRESIDENCIA = ("a interposição se dirige à Presidência ou à Vice-Presidência do "
                        "tribunal recorrido: 'Vossa Excelência'")
_INTERPOSICAO_SUPERIOR_JUIZ = (
    ("tratamento de primeiro grau 'MM. Juiz'",
     _RX_MM_JUIZ,
     _REMEDIO_PRESIDENCIA),
    ("tratamento de primeiro grau 'Meritíssimo'",
     _RX_MERITISSIMO,
     _REMEDIO_PRESIDENCIA),
    ("tratamento de primeiro grau 'Douto Juízo'",
     _RX_DOUTO_JUIZO,
     _REMEDIO_PRESIDENCIA + "; o juízo de primeiro grau não é o destinatário desta folha"),
    ("tratamento de primeiro grau 'Excelentíssimo Senhor Doutor Juiz'",
     _RX_EXMO_JUIZ,
     _REMEDIO_PRESIDENCIA + "; no endereçamento, o Presidente ou o Vice-Presidente do "
     "tribunal recorrido (desembargador; ministro, no RE contra acórdão do STJ)"),
)
_INTERPOSICAO_SUPERIOR_VEDADOS = (
    ("tratamento colegiado 'Ínclitos Desembargadores'",
     _RX_DESEMBARGADORES_PLURAL,
     _REMEDIO_PRESIDENCIA + "; o tratamento colegiado vai na folha de razões"),
    ("tratamento colegiado 'Eméritos Ministros'",
     _RX_MINISTROS_PLURAL,
     _REMEDIO_PRESIDENCIA + "; o tratamento colegiado vai na folha de razões"),
) + _INTERPOSICAO_SUPERIOR_JUIZ


def _dirigida_a_turma_recursal(paragrafos):
    'A folha se dirige a juiz no RE da Súmula 640: nomeia Turma Recursal ou Colégio Recursal'

    texto = _norm(" \n ".join(paragrafos))
    return bool(_RX_TURMA_RECURSAL.search(texto) or _RX_ALCADA.search(texto))

VEDADOS_INTERPOSICAO = {
    "segundo": _INTERPOSICAO_VEDADOS,
    "superior": _INTERPOSICAO_SUPERIOR_VEDADOS,
}


DESTINATARIO_INTERPOSICAO = {
    "segundo": "ao juízo de origem",
    "superior": "à Presidência ou à Vice-Presidência do tribunal recorrido",
}

VEDADOS = {
    "primeiro": _PRIMEIRO_VEDADOS,
    "segundo": _COLEGIADO_VEDADOS,
    "superior": _COLEGIADO_VEDADOS,
}





_RX_FECHO = re.compile(
    r"\bnestes?\s+termos\b|\btermos\s+em\s+que\b|\bpede\s+deferimento\b|\bp\.\s*deferimento\b"
    r"|\baguarda\s+deferimento\b|\bnesses?\s+termos\b", re.I)





_RX_ROGO = re.compile(
    r"\b(?:rog|requer|pleite|postul|pede|pedem)\w*\b[^.!?]{0,60}?\ba\s+vossa\s+excel[êe]ncia\b",
    re.I)


def indice_fecho(paragrafos, fracao_cauda=0.15, minimo_cauda=12):
    'Índice do 1º parágrafo do FECHO, ou len(paragrafos) quando não há fecho reconhecível.'







    paras = list(paragrafos)
    n = len(paras)
    if not n:
        return 0
    inicio = max(0, n - max(minimo_cauda, int(n * fracao_cauda)))
    for i in range(inicio, n):
        if _RX_FECHO.search(str(paras[i] or "")):
            return i
    return n











RX_FORMULA_FECHO = re.compile(r"(?i)\b(?:termos em que|nestes termos|pede\w* e espera|"
                              r"espera(?:ndo)? deferimento|pede deferimento)")
FORMULA_FECHO_MAX = 120
RX_DATA_LINHA = re.compile(r"(?i)(?:\b\d{1,2}\s+de\s+[a-zà-ÿ]+\s+de\s+\d{4}\b"
                           r"|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"
                           r"|\[[^\]\n]*\bDATA\b[^\]\n]*\])")

_RX_INICIO_RAZOES = re.compile(
    r"^(?:contra)?razoes\b"
    r"|^(?:(?:a|ao|aos|as)\s+)?(?:egregi[oa]s?|colend[oa]s?|excels[oa]|inclit[oa]s"
    r"|eminentes?|emerit[oa]s|(?:superior|supremo)\s+tribunal"
    r"|tribunal\s+(?:de\s+justica|regional|superior)"
    r"|excelentissim[oa]s?\s+senhor(?:es)?\s+(?:doutor(?:es)?\s+)?(?:desembargador|ministr))\b")


_LINHA_ASSINATURA_MAX = 160
_JANELA_ASSINATURA = 10


def _e_formula_fecho(texto):
    t = (texto or "").strip()
    m = RX_FORMULA_FECHO.search(t)
    return bool(m) and m.start() == 0 and len(t) <= FORMULA_FECHO_MAX


def fronteira_interposicao(paragrafos, e_fecho=None, e_data=None):
    'Índice do 1º parágrafo das RAZÕES quando a peça traz a folha de interposição antes'









    e_fecho = e_fecho or _e_formula_fecho
    e_data = e_data or (lambda t: bool(RX_DATA_LINHA.search(t or "")))
    paras = [str(p or "") for p in paragrafos]
    n = len(paras)
    for d, linha in enumerate(paras):
        t = linha.strip()
        if not t or len(t) > _LINHA_ASSINATURA_MAX or not e_data(t):
            continue
        j = d - 1
        while j >= 0 and not paras[j].strip():
            j -= 1
        if not e_fecho(t) and (j < 0 or not e_fecho(paras[j])):
            continue
        assinaturas = 0
        for k in range(d + 1, n):
            alvo = paras[k].strip()
            if not alvo:
                continue
            if _RX_INICIO_RAZOES.search(_norm(alvo)):
                if assinaturas:
                    return k
                break
            assinaturas += 1
            if assinaturas > _JANELA_ASSINATURA or len(alvo) > _LINHA_ASSINATURA_MAX:
                break
    return None


def vocativos_indevidos(paragrafos, grau, indices_isentos=(), fronteira=None):
    'Ocorrências de tratamento incompatível com o grau, no CORPO da peça.'



















    regras = VEDADOS.get(grau)
    if not regras:
        return []
    paras = [str(p or "") for p in paragrafos]
    n = len(paras)
    if (grau in VEDADOS_INTERPOSICAO and isinstance(fronteira, int)
            and 0 < fronteira < n):
        folhas = ((0, fronteira, "interposição", VEDADOS_INTERPOSICAO[grau]),
                  (fronteira, n, "razões", regras))
    else:
        folhas = ((0, n, None, regras),)
    isentos = set(indices_isentos)
    achados = []
    for ini, fim, folha, vedados in folhas:
        if (folha == "interposição" and grau == "superior"
                and _dirigida_a_turma_recursal(paras[ini:fim])):
            vedados = tuple(r for r in vedados if r not in _INTERPOSICAO_SUPERIOR_JUIZ)
        fecho = ini + indice_fecho(paras[ini:fim])
        for i in range(ini, fim):
            txt = paras[i]
            if i in isentos or not txt.strip():
                continue
            no_fecho = i >= fecho or bool(_RX_ROGO.search(txt))
            for rotulo, rx, remedio in vedados:
                for m in rx.finditer(txt):


                    if no_fecho and "excel" in m.group(0).lower():
                        continue
                    achados.append({
                        "indice": i, "rotulo": rotulo, "trecho": m.group(0).strip(),
                        "contexto": txt.strip()[:160], "remedio": remedio, "folha": folha,
                    })
    return achados


def descrever(grau):
    """Frase curta para relatório/briefing. Nunca levanta."""
    return {
        "primeiro": "primeiro grau — destinatário é o MM. Juízo (tratamento singular)",
        "segundo": "segundo grau — destinatário é o órgão colegiado (Câmara/Turma; "
                   "tratamento plural)",
        "superior": "tribunal superior — destinatário é o órgão colegiado (Turma/Seção/"
                    "Corte Especial; tratamento plural)",
    }.get(grau, "grau de jurisdição NÃO DECLARADO — o tratamento não é conferido")
