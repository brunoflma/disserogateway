#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'poscorrecao_ocr.py - APONTA termo juridico provavelmente corrompido pelo OCR. Nunca reescreve.'





























from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)



try:
    from quality_scorer import LEGAL_PORTUGUESE_KEYWORDS as _BASE
except Exception:
    _BASE = None

INDISPONIVEL_VOCAB = ("quality_scorer.py indisponivel ao lado do modulo - sem o vocabulario "
                      "juridico da casa nao ha com o que comparar, e inventar uma segunda "
                      "lista aqui seria criar divergencia calada")




_EXTRA = {
    "acordao", "acordaos", "agravante", "agravado", "alegacoes", "apelante", "apelado",
    "audiencia", "autoria", "camara", "citacao", "coisa", "competencia", "conclusao",
    "condenacao", "contestacao", "contrarrazoes", "cumprimento", "danos", "decadencia",
    "deferimento", "denunciacao", "depoimento", "desembargador", "despacho", "dilacao",
    "embargante", "embargado", "ementa", "exceptio", "exequente", "executado", "exordial",
    "fundamentacao", "homologacao", "honorarios", "impugnacao", "improcedencia", "inicial",
    "instrucao", "interlocutoria", "intimacao", "julgamento", "juntada", "liminar",
    "litigancia", "mandado", "manifestacao", "meritorio", "ministerio", "nulidade",
    "obrigacao", "pagamento", "peticao", "possessoria", "prazo", "precatorio", "preliminar",
    "prescricao", "procedencia", "procuracao", "provimento", "publico", "reconvencao",
    "recorrente", "recorrido", "relator", "reparacao", "replica", "requerimento", "rescisao",
    "revelia", "sentenca", "sucumbencia", "sustentacao", "tempestivo", "testemunha",
    "transito", "tutela", "usucapiao", "verba", "vistos",
}


def vocabulario():
    """O vocabulario efetivo, ou None quando a dependencia nao veio no pacote."""
    if _BASE is None:
        return None
    return frozenset(_BASE) | _EXTRA







CONFUSOES = (
    ("rn", "m"), ("m", "rn"),
    ("cl", "d"), ("d", "cl"),
    ("ii", "n"), ("n", "ii"),
    ("ri", "n"),
    ("nn", "m"),
    ("vv", "w"),
    ("1", "l"), ("l", "1"),
    ("1", "i"), ("i", "1"),
    ("0", "o"), ("o", "0"),
    ("5", "s"), ("s", "5"),
    ("8", "b"), ("b", "8"),
    ("6", "g"), ("g", "6"),
    ("2", "z"), ("z", "2"),
)

MINIMO_TOKEN = 4
LIMIAR_ESCALONAMENTO = 0.02
TETO_SUSPEITAS = 500

_PALAVRA = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+")


def dobrar(valor):
    'Forma de comparacao: sem acento, minuscula. NAO altera o texto de origem - so a chave.'



    decomposto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def candidatos(base, vocab):
    'Termos do vocabulario alcancaveis a partir de `base` por UMA confusao conhecida.'



    achados = set()
    for errado, certo in CONFUSOES:
        inicio = base.find(errado)
        while inicio >= 0:
            troca = base[:inicio] + certo + base[inicio + len(errado):]
            if troca in vocab:
                achados.add(troca)
            inicio = base.find(errado, inicio + 1)
    return achados


def suspeitas(texto, minimo_token=MINIMO_TOKEN, vocab=None, teto=TETO_SUSPEITAS):
    '(lista_de_suspeitas, tokens_considerados, truncado).'



    vocab = vocabulario() if vocab is None else vocab
    if vocab is None:
        raise RuntimeError(INDISPONIVEL_VOCAB)
    saida, considerados, truncado = [], 0, False
    for achado in _PALAVRA.finditer(str(texto or "")):
        token = achado.group(0)
        base = dobrar(token)
        if len(base) < minimo_token:
            continue
        considerados += 1
        if base in vocab:
            continue
        possiveis = candidatos(base, vocab)
        if len(possiveis) != 1:


            continue
        if len(saida) >= teto:
            truncado = True
            break
        saida.append({"token": token, "base": base, "candidato": sorted(possiveis)[0],
                      "inicio": achado.start(), "fim": achado.end()})
    return saida, considerados, truncado


def avaliar(texto, minimo_token=MINIMO_TOKEN, limiar=LIMIAR_ESCALONAMENTO, vocab=None,
            teto=TETO_SUSPEITAS):
    'Relatorio completo, com a recomendacao derivada da densidade.'



    achados, considerados, truncado = suspeitas(texto, minimo_token, vocab, teto)
    densidade = (len(achados) / considerados) if considerados else 0.0



    escalar = bool(achados) and considerados > 0 and densidade >= limiar
    return {
        "suspeitas": achados,
        "total_suspeitas": len(achados),
        "tokens_considerados": considerados,
        "densidade": round(densidade, 4),
        "truncado": truncado,
        "limiares": {"minimo_token": minimo_token, "limiar_escalonamento": limiar,
                     "teto": teto},
        "recomendacao": "escalar" if escalar else "processar",
        "motivo": (f"densidade de suspeita {densidade:.4f} >= limiar {limiar} - o teor tem "
                   "termo juridico provavelmente corrompido em quantidade que nao se confere "
                   "a mao; reextrair da fonte e mais barato que emendar"
                   if escalar else
                   f"densidade de suspeita {densidade:.4f} < limiar {limiar}"),


        "aviso": ("Este modulo NAO corrige. A lista aponta onde olhar; emendar teor extraido "
                  "quebraria o sha256 da conferencia e transformaria erro de leitura em prova "
                  "adulterada. Quando o teor importa, reextraia da fonte."),
    }


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Aponta termo juridico provavelmente corrompido pelo OCR. NAO corrige.")
    ap.add_argument("arquivo", help="arquivo de texto/markdown, ou '-' para stdin")
    ap.add_argument("--minimo-token", type=int, default=MINIMO_TOKEN, dest="minimo_token",
                    help=f"tamanho minimo do token considerado (padrao {MINIMO_TOKEN}). "
                         "Baixar INUNDA de colisao curta.")
    ap.add_argument("--limiar-escalonamento", type=float, default=LIMIAR_ESCALONAMENTO,
                    dest="limiar", help=f"densidade de suspeita a partir da qual se recomenda "
                                        f"escalar (padrao {LIMIAR_ESCALONAMENTO}, um em ~50 "
                                        "tokens considerados)")
    ap.add_argument("--teto", type=int, default=TETO_SUSPEITAS,
                    help=f"maximo de suspeitas listadas (padrao {TETO_SUSPEITAS}). O corte e "
                         "ANUNCIADO em `truncado`.")
    args = ap.parse_args(argv)

    if vocabulario() is None:
        print(json.dumps({"ok": False, "erro": INDISPONIVEL_VOCAB}, ensure_ascii=False))
        return 2
    try:
        if args.arquivo == "-":
            texto = sys.stdin.read()
        else:
            with open(args.arquivo, encoding="utf-8", errors="replace") as arquivo:
                texto = arquivo.read()
    except Exception as erro:
        print(json.dumps({"ok": False,
                          "erro": f"{args.arquivo} ilegivel: {erro.__class__.__name__}: {erro}"},
                         ensure_ascii=False))
        return 2

    relatorio = avaliar(texto, args.minimo_token, args.limiar, teto=args.teto)
    relatorio["ok"] = True
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
