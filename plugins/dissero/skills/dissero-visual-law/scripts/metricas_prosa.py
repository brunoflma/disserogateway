#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'metricas_prosa.py — medições de PROSA que complementam as de estrutura do linter.'


































from __future__ import annotations

import re
from collections import Counter













RX_HIFEN_NAO_MEDIDO = "-"
TRAVESSAO = "—"
MEIA_RISCA = "–"



















TETO_AVISO_DENSIDADE = 6.0
TETO_ERRO_DENSIDADE = 10.0
TETO_AVISO_EMENDA = 4.0


MAX_OCORRENCIAS_LISTADAS = 8




MINIMO_PALAVRAS = 400




LIMITE_ANCORA = 6

_RX_PALAVRA = re.compile(r"\S+")




_ANCORAS = (
    ("valor", re.compile(r"R\$\s?\d{1,3}(?:\.\d{3})*,\d{2}")),
    ("data", re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")),
    ("ID dos autos", re.compile(r"\bID\s?\d{6,}\b")),
    ("conta judicial", re.compile(r"\b\d{4,10}-\d\b")),
    ("matrícula/averbação", re.compile(r"\bAV-?\d+/\d[\d.]*\b", re.I)),


    ("dispositivo", re.compile(
        r"\bart(?:igo)?\.?\s?\d+(?:\.\d{3})*[ºo]?(?:\s?,\s?§\s?\d+[ºo]?)?"
        r"(?:\s?,\s?(?:inciso\s+)?[IVXLC]{1,6}\b)?", re.I)),
)


def _palavras(texto):
    return len(_RX_PALAVRA.findall(texto or ""))


_RX_FIM_PERIODO = re.compile(r"[.;:!?](?=\s)|[.;:!?]$")



try:
    import jusmanizer as _jm
except Exception as _e:
    raise ImportError(f"jusmanizer.py indisponível ao lado de metricas_prosa.py ({_e})")


def _periodos(texto):
    'Períodos do parágrafo. O corte é na pontuação final SEGUIDA de espaço (ou fim), o que'


    partes, ini = [], 0
    for m in _RX_FIM_PERIODO.finditer(texto):
        partes.append(texto[ini:m.end()])
        ini = m.end()
    if ini < len(texto):
        partes.append(texto[ini:])
    return partes


def _classifica_periodo(periodo):
    "[(posição, 'emenda'|'aposto')] de cada travessão do período, em ordem."











    pos = [r["inicio"] for r in _jm.riscas(periodo)]
    pares = 2 * (len(pos) // 2)
    return [(p, "aposto" if i < pares else "emenda") for i, p in enumerate(pos)]


def medir_travessoes(paragrafos):
    'Travessões do CORPO AUTORAL, UM A UM, mais a densidade.'










    paras = [str(p or "") for p in paragrafos]
    corpo = "\n".join(paras)
    palavras = _palavras(corpo)
    emendas = apostos = 0
    ocorrencias = []
    for txt in paras:
        for periodo in _periodos(txt):
            for pos, classe in _classifica_periodo(periodo):
                if classe == "emenda":
                    emendas += 1
                else:
                    apostos += 1
                ocorrencias.append({
                    "classe": classe,
                    "trecho": periodo.strip(),
                    "contexto": periodo[max(0, pos - 60):pos + 60].strip(),
                })

    ocorrencias.sort(key=lambda o: 0 if o["classe"] == "emenda" else 1)
    exemplos = [o["contexto"] for o in ocorrencias if o["classe"] == "emenda"][:3]
    total = emendas + apostos
    if palavras < MINIMO_PALAVRAS:



        return {"palavras": palavras, "total": total, "emenda": emendas, "aposto": apostos,
                "densidade": 0.0, "densidade_emenda": 0.0,
                "veredito": "listar" if total else "limpo",
                "ocorrencias": ocorrencias, "exemplos": exemplos,
                "motivo": f"corpo com {palavras} palavras (< {MINIMO_PALAVRAS}) — a DENSIDADE "
                          f"em amostra curta é ruído, não medição; as ocorrências seguem "
                          f"listadas uma a uma"}
    dens = round(total * 1000.0 / palavras, 2)
    dens_em = round(emendas * 1000.0 / palavras, 2)







    if dens >= TETO_ERRO_DENSIDADE and dens_em >= TETO_AVISO_EMENDA:
        veredito = "erro"
    elif dens >= TETO_AVISO_DENSIDADE or dens_em >= TETO_AVISO_EMENDA:
        veredito = "aviso"
    elif total:
        veredito = "listar"
    else:
        veredito = "limpo"
    return {"palavras": palavras, "total": total, "emenda": emendas, "aposto": apostos,
            "densidade": dens, "densidade_emenda": dens_em, "veredito": veredito,
            "ocorrencias": ocorrencias, "exemplos": exemplos, "motivo": ""}


def resumo_travessoes(medida, maximo=MAX_OCORRENCIAS_LISTADAS):
    """As ocorrências por extenso, para a saída do linter: emenda primeiro, aposto depois."""
    ocs = medida.get("ocorrencias") or []
    linhas = [f"[{o['classe']}] «{o['contexto']}»" for o in ocs[:maximo]]
    if len(ocs) > maximo:
        resto = len(ocs) - maximo
        n_em = sum(1 for o in ocs[maximo:] if o["classe"] == "emenda")
        linhas.append(f"… e mais {resto} ocorrência(s), {n_em} de emenda")
    return " · ".join(linhas)


def ancoras_repetidas(paragrafos, limite=LIMITE_ANCORA, ignorar=()):
    'Âncoras (valor, data, ID, conta, matrícula, dispositivo) repetidas acima do limite.'






    texto = "\n".join(str(p or "") for p in paragrafos)
    fora = {str(x).strip() for x in ignorar if str(x).strip()}
    saida = []
    for classe, rx in _ANCORAS:
        contagem = Counter(m.group(0).strip() for m in rx.finditer(texto))
        for valor, n in contagem.items():
            if n >= limite and valor not in fora and not any(valor in f for f in fora):
                saida.append({"classe": classe, "valor": valor, "ocorrencias": n})
    saida.sort(key=lambda d: (-d["ocorrencias"], d["classe"], d["valor"]))
    return saida


def resumo_ancoras(itens, maximo=10):
    'Uma linha por âncora, para a mensagem consolidada do linter. A saída é UM bloco, não'


    linhas = [f"{d['ocorrencias']}× {d['valor']} ({d['classe']})" for d in itens[:maximo]]
    if len(itens) > maximo:
        linhas.append(f"… e mais {len(itens) - maximo} âncora(s) acima do limite")
    return "; ".join(linhas)
