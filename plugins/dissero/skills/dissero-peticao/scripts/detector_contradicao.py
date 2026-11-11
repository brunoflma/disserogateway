#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'detector_contradicao.py - PROPOE pares de passagens que PODEM se contradizer. Nunca conclui.'



























































































from __future__ import annotations

import argparse
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

try:
    import conferencia_contract as _conf
except Exception:
    _conf = None

try:
    from contradicao_contract import (MINIMO_CONFERIVEL, MINIMO_PARTE_CONFERIVEL,
                                      sha256_texto, texto)
except Exception:
    MINIMO_CONFERIVEL = MINIMO_PARTE_CONFERIVEL = None
    sha256_texto = texto = None

try:
    from schema_mini import validar_schema
except Exception:
    validar_schema = None

SCHEMA_PADRAO = os.path.join(AQUI, "schema_contradicao_proposta.json")
SCHEMA_VERSION = "dsr.contradicao_proposta.v1"
NOME_ARTEFATO = "PROPOSTAS-CONTRADICAO.json"



JUIZO = "a_confirmar"

EIXOS = ("negacao", "valor", "data")


MINIMO_NUCLEO = 3


TETO_PROPOSTAS = 200



MINIMO_TOKEN = 3

INDISPONIVEL_CONF = ("conferencia_contract.py indisponivel ao lado do detector - sem o "
                     "normalizador e o comparador da casa nao ha varredura possivel, e "
                     "improvisar um segundo comparador seria pior que nao varrer")
INDISPONIVEL_CONTRATO = ("contradicao_contract.py indisponivel ao lado do detector - os pisos "
                         "do lastro vem de la e nao se reinventam aqui")









NEGACOES = ("nao", "nunca", "jamais", "nenhum", "nenhuma", "nenhuns", "nenhumas",
            "inexistente", "inexistentes", "inexiste", "inexistem", "improcedente",
            "improcedentes", "descabe", "descabida", "descabido", "indevida", "indevido",
            "inocorrencia", "ausencia", "ausente")



STOPWORDS = frozenset("""
a as o os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas para
com sem sob sobre entre ate apos ante contra desde perante e ou mas porem contudo todavia
que se como quando onde qual quais cujo cuja cujos cujas
ser sao foi foram era eram sido sendo estar esta estao estava estavam
ter tem tinha tinham havido haver ha havia
este esta estes estas esse essa esses essas aquele aquela aqueles aquelas isto isso aquilo
seu sua seus suas dele dela deles delas meu minha nosso nossa
mesmo mesma mesmos mesmas outro outra outros outras tal tais
ainda ja tambem so apenas muito mais menos bem mal assim entao portanto pois porque
fls fl art arts inc incs par parag caput alinea item itens
autor autora reu re requerente requerido exequente executado agravante agravado
r rs
""".split())


def _exigir_dependencias():
    """Lista de indisponibilidades. Vazia = da para varrer."""
    faltas = []
    if _conf is None:
        faltas.append(INDISPONIVEL_CONF)
    if MINIMO_CONFERIVEL is None:
        faltas.append(INDISPONIVEL_CONTRATO)
    return faltas






_MARCA_PAGINA = re.compile(r"-{2,}\s*P[aá]gina\s+\d+\s*-{2,}", re.IGNORECASE)



_ABREVIACOES = ("art", "arts", "inc", "incs", "par", "parag", "fls", "fl", "n", "no", "nos",
                "dr", "dra", "sr", "sra", "exmo", "exma", "ilmo", "ilma", "cf", "cc", "cpc",
                "clt", "ltda", "obs", "pag", "pags", "ss", "seg", "segs", "ed", "org", "vol")



_FIM_FRASE = re.compile(r"(?<=[.;!?])\s+(?=[A-ZÀ-ÖØ-Þ])")


def _e_abreviacao(fragmento):
    """True quando o fragmento termina numa abreviacao conhecida (logo, nao terminou frase)."""
    cauda = re.split(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ]+", fragmento.strip().rstrip("."))
    return bool(cauda) and cauda[-1].casefold() in _ABREVIACOES


def frases(bruto):
    'Fatia um trecho lido em frases. Devolve os RECORTES VERBATIM, sem normalizar nada.'




    limpo = _MARCA_PAGINA.sub("\n", str(bruto or ""))
    saida = []
    for linha in limpo.splitlines():
        pedacos = _FIM_FRASE.split(linha)
        acumulado = ""
        for pedaco in pedacos:
            acumulado = (acumulado + " " + pedaco).strip() if acumulado else pedaco.strip()
            if not _e_abreviacao(acumulado):
                if acumulado.strip():
                    saida.append(acumulado.strip())
                acumulado = ""
        if acumulado.strip():
            saida.append(acumulado.strip())
    return saida




def _tokens(valor):
    """Tokens na forma canonica da casa (`conferencia_contract.normalizar_trecho`)."""
    return _conf.normalizar_trecho(valor).split()


def _sem_plural(token):
    'Dobra de plural minima: cai o `s` final de token com 5+ caracteres.'





    return token[:-1] if len(token) >= 5 and token.endswith("s") else token


def nucleo(valor):
    'Conjunto de tokens de CONTEUDO da frase - o que decide se duas frases falam do mesmo.'




    saida = set()
    for token in _tokens(valor):
        if token.isdigit() or len(token) < MINIMO_TOKEN:
            continue
        if token in STOPWORDS or token in NEGACOES:
            continue
        saida.add(_sem_plural(token))
    return saida


def negacoes(valor, lexico=NEGACOES):
    """Marcas de negacao presentes na frase. Conjunto vazio = frase afirmativa."""
    presentes = set(_tokens(valor))
    return {marca for marca in lexico if marca in presentes}




_NUMERO = re.compile(r"\d[\d.]*(?:,\d+)?")


_DATA_NUM = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
_MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
          "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
          "dezembro": 12}
_DATA_EXT = re.compile(r"\b(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})\b")


def _canonico(numero):
    "'1.234,56' e '1234,56' viram o MESMO valor. Sem isto, a mesma quantia escrita de dois"

    limpo = numero.replace(".", "").replace(",", ".")
    try:
        return f"{float(limpo):.4f}"
    except ValueError:
        return None


def valores(valor):
    'Conjunto canonico dos numeros da frase. Datas saem antes: `10/03/2024` nao e tres'

    sem_datas = _DATA_NUM.sub(" ", str(valor or ""))
    saida = set()
    for achado in _NUMERO.findall(sem_datas):
        canon = _canonico(achado)
        if canon is not None:
            saida.add(canon)
    return saida


def datas(valor):
    'Conjunto canonico (aaaa-mm-dd) das datas da frase, numericas e por extenso.'



    bruto = str(valor or "")
    saida = set()
    for dia, mes, ano in _DATA_NUM.findall(bruto):
        if len(ano) != 4:
            continue
        try:
            d, m, a = int(dia), int(mes), int(ano)
        except ValueError:
            continue
        if 1 <= d <= 31 and 1 <= m <= 12:
            saida.add(f"{a:04d}-{m:02d}-{d:02d}")
    for dia, mes, ano in _DATA_EXT.findall(_conf.normalizar_trecho(bruto)):
        numero_mes = _MESES.get(mes)
        if numero_mes and 1 <= int(dia) <= 31:
            saida.add(f"{int(ano):04d}-{numero_mes:02d}-{int(dia):02d}")
    return saida




def avaliar_par(texto_a, texto_b, minimo_nucleo=MINIMO_NUCLEO, lexico=NEGACOES):
    '[(eixo, motivo)] para o par. Lista vazia = nada a propor.'



    nuc_a, nuc_b = nucleo(texto_a), nucleo(texto_b)
    comum = nuc_a & nuc_b
    if len(comum) < minimo_nucleo:
        return []

    rotulo = ", ".join(sorted(comum)[:6])
    achados = []

    neg_a, neg_b = negacoes(texto_a, lexico), negacoes(texto_b, lexico)
    if bool(neg_a) != bool(neg_b):
        marcas = ", ".join(sorted(neg_a or neg_b))
        lado = "a primeira" if neg_a else "a segunda"
        achados.append(("negacao",
                        f"nucleo compartilhado ({rotulo}) e {lado} passagem nega ({marcas}), "
                        "a outra nao"))

    val_a, val_b = valores(texto_a), valores(texto_b)
    if val_a and val_b and not (val_a & val_b):
        achados.append(("valor",
                        f"nucleo compartilhado ({rotulo}) e nenhum valor em comum: "
                        f"{sorted(val_a)} contra {sorted(val_b)}"))

    dat_a, dat_b = datas(texto_a), datas(texto_b)
    if dat_a and dat_b and not (dat_a & dat_b):
        achados.append(("data",
                        f"nucleo compartilhado ({rotulo}) e nenhuma data em comum: "
                        f"{sorted(dat_a)} contra {sorted(dat_b)}"))
    return achados




def _rotulo_peca(documento):
    'Rotulo legivel da peca. BASENAME, nunca o caminho: caminho de pasta de cliente nao entra'


    arquivo = texto(documento.get("arquivo"))
    return os.path.basename(arquivo.replace("\\", "/")) or texto(documento.get("doc_id")) or "?"


def candidatas(conferencia, minimo=None, rotulos=None):
    '[{doc_id, peca, evidence_id, pagina, texto}] - toda frase que PODE ser lastro.'



    piso = MINIMO_CONFERIVEL if minimo is None else minimo
    rotulos = rotulos or {}
    saida = []
    if not isinstance(conferencia, dict):
        return saida
    documentos = conferencia.get("documentos")
    for documento in documentos if isinstance(documentos, list) else []:
        if not isinstance(documento, dict):
            continue
        doc_id = texto(documento.get("doc_id"))
        peca = rotulos.get(doc_id) or _rotulo_peca(documento)


        trechos = _conf.trechos_de_texto(documento)
        for trecho in trechos if isinstance(trechos, list) else []:
            if not isinstance(trecho, dict):
                continue
            eid = texto(trecho.get("evidence_id"))
            if not eid:
                continue
            for frase in frases(trecho.get("trecho_literal")):
                if len(_conf.normalizar_trecho(frase)) < piso:
                    continue
                saida.append({"doc_id": doc_id, "peca": peca, "evidence_id": eid,
                              "pagina": trecho.get("pagina"), "texto": frase})
    return saida


def _lado(candidata):
    return {"peca": candidata["peca"], "doc_id": candidata["doc_id"],
            "evidence_id": candidata["evidence_id"],
            "trecho_literal": candidata["texto"],
            "sha256_trecho": sha256_texto(candidata["texto"])}


def propor(conferencia, minimo_nucleo=MINIMO_NUCLEO, intra_peca=False,
           teto=TETO_PROPOSTAS, minimo=None, lexico=NEGACOES, rotulos=None, caso=None,
           gerado_em=None, caminho_conferencia=None):
    'Dataset `dsr.contradicao_proposta.v1`. Levanta RuntimeError se faltar dependencia.'




    faltas = _exigir_dependencias()
    if faltas:
        raise RuntimeError("; ".join(faltas))

    lista = candidatas(conferencia, minimo=minimo, rotulos=rotulos)
    propostas, avaliados, truncado = [], 0, False
    for i in range(len(lista)):
        for j in range(i + 1, len(lista)):
            a, b = lista[i], lista[j]
            if a["evidence_id"] == b["evidence_id"]:
                continue
            if not intra_peca and a["doc_id"] == b["doc_id"]:
                continue
            avaliados += 1
            for eixo, motivo in avaliar_par(a["texto"], b["texto"], minimo_nucleo, lexico):
                if len(propostas) >= teto:
                    truncado = True
                    break
                propostas.append({"id": f"prop-{len(propostas) + 1:04d}",
                                  "juizo": JUIZO, "eixo": eixo, "motivo": motivo,
                                  "lados": [_lado(a), _lado(b)]})
            if truncado:
                break
        if truncado:
            break

    dados = {"schema_version": SCHEMA_VERSION,
             "conferencia": caminho_conferencia,
             "limiares": {"minimo_nucleo": minimo_nucleo,
                          "minimo": MINIMO_CONFERIVEL if minimo is None else minimo,
                          "minimo_parte": MINIMO_PARTE_CONFERIVEL,
                          "teto": teto},
             "intra_peca": bool(intra_peca),
             "frases": len(lista),
             "pares_avaliados": avaliados,
             "truncado": truncado,
             "propostas": propostas}
    if caso:
        dados["caso"] = caso
    if gerado_em:
        dados["gerado_em"] = gerado_em
    return dados




def converter_para_contrato(propostas, teses, caminho_conferencia=None):
    'Converte propostas em `dsr.contradicao.v1` - EXIGINDO uma tese humana por proposta.'






    registros, erros = [], []
    for proposta in (propostas.get("propostas") or []):
        pid = texto(proposta.get("id"))
        tese = texto((teses or {}).get(pid))
        if not tese:
            erros.append(f"proposta {pid or '?'}: sem tese humana - o que se contradiz e "
                         "juizo de quem le, e o detector nao o escreve")
            continue
        registros.append({"id": pid, "afirmada_por": "modelo", "tese": tese,
                          "status": "lastreada", "lados": proposta.get("lados")})
    dados = {"schema_version": "dsr.contradicao.v1",
             "conferencia": caminho_conferencia if caminho_conferencia is not None
             else propostas.get("conferencia"),
             "contradicoes": registros}
    return dados, erros




def validar_documento(dados, schema_path=SCHEMA_PADRAO):
    """[] quando o dataset de propostas esta integro. Falha fechado sem validador."""
    if validar_schema is None:
        return ["schema_mini.py indisponivel ao lado do detector - nada e conferido, e nada e "
                "aprovado (falha fechado)"]
    try:
        with open(schema_path, encoding="utf-8") as arquivo:
            schema = json.load(arquivo)
    except Exception as erro:
        return [f"schema {schema_path} ilegivel: {erro.__class__.__name__}: {erro}"]

    erros = validar_schema(dados, schema)
    if erros:
        return erros
    vistos = set()
    for proposta in dados["propostas"]:
        pid = texto(proposta.get("id")) if isinstance(proposta, dict) else ""
        lados = proposta.get("lados") if isinstance(proposta, dict) else None
        if not isinstance(lados, list) or len(lados) != 2:
            erros.append(f"proposta {pid or '?'}: exige exatamente 2 lados")
        else:
            ids = [texto(l.get("evidence_id")) if isinstance(l, dict) else "" for l in lados]
            if "" not in ids and len(set(ids)) != len(ids):
                erros.append(f"proposta {pid or '?'}: os dois lados apontam o mesmo "
                             f"evidence_id ({ids[0]}) - um lastro, nao dois")
        if pid and pid in vistos:
            erros.append(f"proposta {pid}: id repetido no dataset")
        elif pid:
            vistos.add(pid)
    return erros




def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Varre um CONFERENCIA.json e PROPOE pares que podem se contradizer. Nao "
                    "afirma contradicao nenhuma: toda saida nasce 'a_confirmar' e sem tese.")
    ap.add_argument("conferencia", help="caminho do CONFERENCIA.json (dsr.conferencia.v1)")
    ap.add_argument("-o", "--saida", default=None,
                    help=f"onde gravar o {NOME_ARTEFATO} (padrao: imprime resumo, nao grava)")
    ap.add_argument("--minimo-nucleo", type=int, default=MINIMO_NUCLEO, dest="minimo_nucleo",
                    help=f"tokens de conteudo que as duas frases tem de compartilhar (padrao "
                         f"{MINIMO_NUCLEO}). Baixar INUNDA, subir CEGA - ver o cabecalho.")
    ap.add_argument("--minimo", type=int, default=None,
                    help=f"piso do total normalizado para a frase poder ser lastro (padrao "
                         f"{MINIMO_CONFERIVEL}, herdado do contrato)")
    ap.add_argument("--intra-peca", action="store_true", dest="intra_peca",
                    help="tambem cruza frases do MESMO documento (autocontradicao). Nasce "
                         "desligado: a taxa de ruido e outra.")
    ap.add_argument("--teto", type=int, default=TETO_PROPOSTAS,
                    help=f"maximo de propostas (padrao {TETO_PROPOSTAS}). O corte e ANUNCIADO.")
    ap.add_argument("--caso", default=None, help="rotulo do caso, informativo")
    ap.add_argument("--gerado-em", default=None, dest="gerado_em",
                    help="carimbo de tempo, informativo (o modulo nao le o relogio)")
    args = ap.parse_args(argv)

    faltas = _exigir_dependencias()
    if faltas:
        for falta in faltas:
            print("ERRO " + falta)
        return 2
    try:
        with open(args.conferencia, encoding="utf-8") as arquivo:
            conferencia = json.load(arquivo)
    except Exception as erro:
        print(f"ERRO {args.conferencia} ilegivel: {erro.__class__.__name__}: {erro}")
        return 2

    dados = propor(conferencia, minimo_nucleo=args.minimo_nucleo, intra_peca=args.intra_peca,
                   teto=args.teto, minimo=args.minimo, caso=args.caso,
                   gerado_em=args.gerado_em, caminho_conferencia=args.conferencia)

    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        print(f"GRAVADO {args.saida}")

    print(f"VARREDURA {dados['frases']} frase(s) conferivel(is), "
          f"{dados['pares_avaliados']} par(es) avaliado(s), "
          f"{len(dados['propostas'])} proposta(s) "
          f"(minimo_nucleo={args.minimo_nucleo}, intra_peca={bool(args.intra_peca)})")

    if dados["truncado"]:
        print(f"TRUNCADO no teto de {args.teto} proposta(s) - HA MAIS PARES NAO AVALIADOS. "
              "Suba --teto ou --minimo-nucleo para ver o resto.")
    for proposta in dados["propostas"]:
        print(f"  {proposta['id']} [{proposta['eixo']}] {proposta['motivo']}")
        for lado in proposta["lados"]:
            print(f"      {lado['peca']}: \"{lado['trecho_literal'][:110]}\"")
    if dados["propostas"]:
        print("TODAS a_confirmar - nenhuma tem tese, e nenhuma vira registro sem alguem "
              "escrever o que se contradiz.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
