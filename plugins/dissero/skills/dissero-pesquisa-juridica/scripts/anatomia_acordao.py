#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'anatomia_acordao.py — o acórdão decidiu o MÉRITO, ou parou numa barreira processual?'







































from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

CONFERIDO_EM = "2026-11-16"
_FONTE_STJ = "https://www.stj.jus.br/docs_internet/VerbetesSTJ_asc.pdf"
_FONTE_STF = ("https://www.stf.jus.br/arquivo/cms/jurisprudenciaSumula/anexo/"
              "Enunciados_Sumulas_STF_1_a_736_Completo.pdf")
_FONTE_TST = "https://www.tst.jus.br/documents/10157/63003/Livro-Internet.pdf"




CATALOGO_SUMULAS = {
    ("STJ", 5): "interpretação de cláusula contratual",
    ("STJ", 7): "reexame de prova",
    ("STJ", 83): "orientação do tribunal no mesmo sentido do acórdão recorrido",
    ("STJ", 126): "fundamento constitucional suficiente sem recurso extraordinário",
    ("STJ", 211): "falta de prequestionamento apesar dos embargos de declaração",
    ("STJ", 518): "recurso especial fundado em violação de súmula",
    ("STF", 279): "reexame de prova",
    ("STF", 280): "ofensa a direito local",
    ("STF", 282): "falta de prequestionamento",
    ("STF", 283): "fundamento suficiente não impugnado",
    ("STF", 284): "fundamentação deficiente",
    ("STF", 356): "ponto omisso sem embargos de declaração",
    ("STF", 454): "interpretação de cláusula contratual",
    ("TST", 126): "reexame de fatos e provas",
    ("TST", 297): "falta de prequestionamento",
    ("TST", 333): "decisão conforme a jurisprudência atual do TST",
    ("TST", 422): "fundamentos da decisão recorrida não impugnados",
}
_FONTES = {"STJ": _FONTE_STJ, "STF": _FONTE_STF, "TST": _FONTE_TST}
CATALOGO_SUMULAS = {k: {"barreira": v, "fonte": _FONTES[k[0]], "conferido_em": CONFERIDO_EM}
                    for k, v in CATALOGO_SUMULAS.items()}

ACORDAO_SEM_MERITO = "ACORDAO_SEM_MERITO"
ACORDAO_MERITO_PARCIAL = "ACORDAO_MERITO_PARCIAL"
BARREIRA_PROCESSUAL_APLICADA = "BARREIRA_PROCESSUAL_APLICADA"

_F = re.IGNORECASE
_TITULO = re.compile(r"^[ \t]*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ .\-/]{6,}?)\s+N[º°o.]\s*[\d.\-/]+.*$",
                     re.MULTILINE)
_EMBARGOS = re.compile(r"^\s*EMBARGOS\s+DE\s+DECLARA[ÇC][ÃA]O\b")
_VOTO_VENCIDO = re.compile(r"^[ \t]*VOTO[ \-]VENCIDO\b.*$", re.MULTILINE)
_SECAO = re.compile(r"^[ \t]*(?:VOTO|EMENTA|AC[ÓO]RD[ÃA]O|RELAT[ÓO]RIO|CERTID[ÃA]O)\b.*$",
                    re.MULTILINE)


_VENCIDO = re.compile(
    r"\bvencid[oa]s?\s+(?:em\s+parte\s+)?(?:[oa]s?\s+)?(?:(?:Senhor(?:a|es)?|Sr[as]*\.?|Exm[oa]s?\.?)\s+)?"
    r"(?:Min|Des|Ju[ií]z|Relator|Conselheir|Vogal)\w*\.?"
    r"(?:\b(?:Min|Des|Rel|Exm[oa]s?|Srs?|Sras?|Drs?|Dras?|n)\.|[^.;])*(?:[.;]|$)", _F)


_ASPAS = re.compile(r"[“«][^”»]{0,3000}[”»]|\"[^\"]{20,3000}\"")
_REF_JULGADO = re.compile(r"\((?=[^()]*\bRel(?:\.|ator[a]?\b))(?=[^()]*\b(?:DJe?|julgad[oa]\s+em)\b)[^()]{0,400}\)", _F)

_NAO_CONHECE = re.compile(
    r"n[ãa]o\s+(?:se\s+)?conhe[cç]\w*\s+d[oa]s?\b|n[ãa]o\s+conhecid[oa]s?\b|\binadmitid[oa]\b", _F)
_PARCIAL = re.compile(r"conhe[cç]\w*\s+(?:parcialmente|em\s+parte)\b|parcialmente\s+conhecid", _F)
_MERITO = re.compile(
    r"\b(?:dar|d[áa]|dou|deram|negar|nega|negou|nego|deu)[\w\-]*\s+(?:-?lhes?\s+)?(?:parcial\s+)?provimento"
    r"|provimento\s+parcial|\b(?:des|im|n[ãa]o\s+)?provid[oa]s?\b"
    r"|\b(?:rejeitar|rejeitou|acolher|acolheu)\s+os\s+embargos"
    r"|julg\w+\s+(?:im)?procedente", _F)

_TRIB = (r"(?:\s*/\s*|\s+d[oa]\s+(?:col(?:end)?o\.?\s+)?|\s+)"
         r"(STJ|STF|TST|Superior\s+Tribunal\s+de\s+Justi[çc]a|Supremo\s+Tribunal\s+Federal"
         r"|Tribunal\s+Superior\s+do\s+Trabalho)\b")
_SUMULA = re.compile(r"s[úu]mulas?\s+(?:n(?:[º°o]|\.º?|s\.)?\s*)?(\d{1,3}(?:\s*(?:,|e)\s*\d{1,3})*)"
                     + _TRIB, _F)
_TRIB_NOME = {"superior": "STJ", "supremo": "STF", "tribunal": "TST"}
_AFASTADA = re.compile(
    r"\bn[ãa]o\s+(?:incide|incidem|se\s+aplica|se\s+aplicam|tem\s+aplica|h[áa]\s+(?:que\s+se\s+)?falar"
    r"|atrai|[ée]\s+(?:o\s+)?(?:caso|hip[óo]tese)|esbarra|impede|impedem|obsta|obstam"
    r"|h[áa]\s+(?:[óo]bice|incid))"
    r"|\bafast\w*(?:-se)?\s+(?:[oa]s?\s+)?(?:[óo]bice|incid[êe]ncia|s[úu]mula|aplica)"
    r"|\bsuperad[oa]s?\s+[oa]s?\s+(?:[óo]bice|s[úu]mula)"
    r"|\binaplic[áa]ve(?:l|is)\b|\binaplicabilidade\b|\bsem\s+(?:[óo]bice|incid[êe]ncia)", _F)
_RELATADA = re.compile(
    r"\b(?:alega|alegou|alegam|sustenta|sustentou|aduz|aduziu|argumenta|defende|invoca|invocou"
    r"|aponta|apontou|pretende|requer)\b|\bsegundo\s+[oa]s?\s+(?:recorrente|agravante|parte)", _F)
_APLICADA = re.compile(
    r"incid|\batra[ie]\b|aplic|[óo]bice|esbarra|vedad|obst|invi[áa]vel|imped|conhe[cç]|inadmiss"
    r"|\bante\s+[oa]\b|por\s+for[çc]a|nos\s+termos\s+d|em\s+raz[ãa]o\s+d|n[ãa]o\s+(?:cabe|enseja)", _F)
_ABREV = {"n", "nº", "n.º", "art", "arts", "min", "rel", "p", "fl", "fls", "inc", "al", "col",
          "colendo", "eg", "egr", "ns", "dr", "dra", "des", "exmo", "sr", "sra"}
_USO_PROCESSUAL = re.compile(
    r"barreira|[óo]bice|s[úu]mula\s+\d|n[ãa]o\s+conhe[cç]|processual|admissibilidade"
    r"|prequestionamento|reexame", _F)


def _segmentos(texto):
    'Lista de (é_embargos, trecho), cortando nos títulos com número de processo. Quando todo'


    pos = [m.start() for m in _TITULO.finditer(texto)]
    com_titulo = [True] * len(pos)
    if not pos or pos[0] != 0:
        pos, com_titulo = [0] + pos, [False] + com_titulo
    out = []
    for i, ini in enumerate(pos):
        trecho = texto[ini:pos[i + 1] if i + 1 < len(pos) else len(texto)]
        out.append([bool(_EMBARGOS.match(trecho)), trecho, com_titulo[i]])
    if not any(t and not e for e, _, t in out):
        for seg in out:
            if seg[0]:
                seg[0] = False
                break
    return [(e, t) for e, t, _ in out]


def _sem_transcricao(texto):
    'Tira ementa de outro julgado transcrita no voto: trecho entre aspas e parágrafo fechado'

    texto = _ASPAS.sub(" ", texto)
    paragrafos = re.split(r"\n[ \t]*\n", texto)
    manter = []
    for par in paragrafos:
        if _REF_JULGADO.search(par):
            if par.strip().startswith("(") and manter:
                manter.pop()
            continue
        manter.append(par)
    return "\n\n".join(manter)


def _aplicada(frase):
    'A frase diz que a súmula se aplica? Verbo com "não" anteposto não conta ("não esbarra",'

    for m in _APLICADA.finditer(frase):
        tok = m.group(0).lower()
        negado = re.search(r"\bn[ãa]o\s+(?:se\s+|lhe\s+|o\s+|a\s+)?$", frase[:m.start()], _F)
        if not negado or tok.startswith(("conhe", "não", "nao")):
            return True
    return False


def _sem_voto_vencido(trecho):
    m = _VOTO_VENCIDO.search(trecho)
    if not m:
        return trecho
    prox = _SECAO.search(trecho, m.end())
    return trecho[:m.start()] + (trecho[prox.start():] if prox else "")


def _frases(texto):
    """Frases cortadas em '.'/';' seguidos de espaço, sem cortar em abreviação ('n. 7')."""
    frases, ini = [], 0
    for m in re.finditer(r"[.;](?=\s|$)", texto):
        antes = re.search(r"([\wº.]+)$", texto[ini:m.start()])
        if antes and antes.group(1).lower().rstrip(".") in _ABREV:
            continue
        frases.append(texto[ini:m.end()])
        ini = m.end()
    if texto[ini:].strip():
        frases.append(texto[ini:])
    return frases


def _tribunal(nome):
    nome = nome.strip()
    return nome.upper() if len(nome) == 3 else _TRIB_NOME[nome.split()[0].lower()]


def _sumulas(texto):
    aplicadas, afastadas, vistos = [], [], set()
    for frase in _frases(texto):
        for m in _SUMULA.finditer(frase):
            trib = _tribunal(m.group(2))
            for num in (int(n) for n in re.findall(r"\d{1,3}", m.group(1))):
                cat = CATALOGO_SUMULAS.get((trib, num))
                if not cat:
                    continue
                reg = {"tribunal": trib, "numero": num, "barreira": cat["barreira"],
                       "trecho": " ".join(frase.split())[:240]}
                if _AFASTADA.search(frase):
                    destino = afastadas
                elif _RELATADA.search(frase) or not _aplicada(frase):
                    continue
                else:
                    destino = aplicadas
                chave = (id(destino), trib, num)
                if chave not in vistos:
                    vistos.add(chave)
                    destino.append(reg)
    afastadas = [a for a in afastadas
                 if (a["tribunal"], a["numero"]) not in {(b["tribunal"], b["numero"]) for b in aplicadas}]
    return aplicadas, afastadas


def _dispositivo(texto):
    nc, parcial, merito = (bool(r.search(texto)) for r in (_NAO_CONHECE, _PARCIAL, _MERITO))
    if parcial:
        return "conhecimento_parcial"
    if nc and merito:
        return "misto"
    if nc:
        return "nao_conhecimento"
    if merito:
        return "merito"
    return None


def analisar(texto):
    """Anatomia do acórdão: dispositivo, mérito alcançado, barreiras, votação."""
    texto = unicodedata.normalize("NFC", texto or "")
    segs = _segmentos(texto)
    principais = [t for emb, t in segs if not emb]
    embargos_anexados = bool(principais) and any(emb for emb, _ in segs)
    principal = "\n".join(principais) if principais else texto
    principal = _sem_voto_vencido(principal)
    if re.search(r"por\s+unanimidade", principal, _F):
        votacao = "unanimidade"
    elif re.search(r"por\s+maioria", principal, _F) or _VENCIDO.search(principal):
        votacao = "maioria"
    else:
        votacao = None
    limpo = _sem_transcricao(_VENCIDO.sub(" ", principal))
    dispositivo = _dispositivo(limpo)
    barreiras, afastadas = _sumulas(limpo)
    if dispositivo == "nao_conhecimento":
        merito = False
    elif dispositivo == "conhecimento_parcial":
        merito = "parcial"
    elif dispositivo == "merito":
        merito = None if barreiras else True
    else:
        merito = None
    return {"dispositivo": dispositivo, "merito_alcancado": merito, "barreiras": barreiras,
            "barreiras_afastadas": afastadas, "votacao": votacao,
            "embargos_anexados": embargos_anexados}


def _nomes(barreiras):
    return "; ".join(f"Súmula {b['numero']} do {b['tribunal']} ({b['barreira']})"
                     for b in barreiras) or "barreira processual não identificada no texto"


def aviso_uso_merito(anat, uso_declarado=None):
    'AVISO quando o acórdão pode não sustentar tese de mérito; None quando não há o que avisar'

    if uso_declarado and _USO_PROCESSUAL.search(uso_declarado):
        return None
    disp, merito, barr = anat.get("dispositivo"), anat.get("merito_alcancado"), anat.get("barreiras") or []
    if disp == "nao_conhecimento":
        codigo = ACORDAO_SEM_MERITO
        msg = (f"o acórdão não conheceu do recurso ({_nomes(barr)}): não decidiu a tese de mérito "
               f"e não serve para sustentá-la")
    elif disp == "conhecimento_parcial":
        codigo = ACORDAO_MERITO_PARCIAL
        msg = (f"o acórdão conheceu só em parte do recurso ({_nomes(barr)}): confira se a tese "
               f"citada está na parte conhecida")
    elif merito is None and barr:
        codigo = BARREIRA_PROCESSUAL_APLICADA
        msg = (f"o acórdão aplica barreira processual ({_nomes(barr)}): o provimento ou "
               f"desprovimento pode ser só do óbice, e não da tese de mérito")
    else:
        return None
    return {"codigo": codigo, "nivel": "aviso", "mensagem": msg,
            "o_que_fazer": ("leia o dispositivo e o voto condutor; se o julgado não enfrentou a "
                            "tese, troque o precedente ou cite-o só pelo que decidiu (a barreira)")}


def aviso_do_achado(achado, texto_documento):
    'Aviso para UM achado de pesquisa (achados.json) contra o texto do acórdão dele. O uso'

    uso = (achado.get("estrategia_uso") or {}).get("finalidade") if isinstance(
        achado.get("estrategia_uso"), dict) else None
    aviso = aviso_uso_merito(analisar(texto_documento), uso if isinstance(uso, str) else None)
    if aviso:
        aviso["id"] = achado.get("id")
    return aviso


_VEREDITO = {"nao_conhecimento": "NÃO CONHECIMENTO", "conhecimento_parcial": "CONHECIMENTO PARCIAL",
             "merito": "MÉRITO", "misto": "DISPOSITIVO MISTO", None: "DISPOSITIVO NÃO IDENTIFICADO"}


def _ler(caminho):
    if caminho.lower().endswith(".pdf"):
        exe = shutil.which("pdftotext")
        if not exe:
            raise OSError("pdftotext não encontrado no PATH: salve o acórdão em .txt")
        return subprocess.run([exe, "-layout", "-enc", "UTF-8", caminho, "-"], capture_output=True,
                              check=True).stdout.decode("utf-8", "replace")
    with open(caminho, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Anatomia do acórdão: barreira processual × mérito.")
    ap.add_argument("arquivo")
    ap.add_argument("--uso", help="para que o julgado é citado na peça")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.arquivo):
        print(f"ERRO: arquivo não encontrado: {a.arquivo}")
        return 2
    try:
        texto = _ler(a.arquivo)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"ERRO: não foi possível ler o acórdão: {e}")
        return 2
    anat = analisar(texto)
    aviso = aviso_uso_merito(anat, a.uso)
    linha = _VEREDITO[anat["dispositivo"]]
    if anat["merito_alcancado"] is None and anat["dispositivo"] == "merito":
        linha += " (alcance do mérito incerto: há barreira aplicada)"
    print(linha + (f" — AVISO {aviso['codigo']}: {aviso['mensagem']}" if aviso else ""))
    print(json.dumps(dict(anat, aviso=aviso), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
