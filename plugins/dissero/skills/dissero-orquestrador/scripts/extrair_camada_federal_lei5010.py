#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'extrair_camada_federal_lei5010.py - a camada da JUSTICA FEDERAL, tirada da propria LEI.'















































from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass







BASE_NORMATIVA = "Lei nº 5.010/1966, art. 62, %s (redação da Lei nº 6.741/1979)"
EFEITO_TIPICO = {"recesso_forense": "suspensao_prazo", "suspensao_expediente": "dia_nao_util"}





JUSTIFICATIVA_RECESSO = (
    "o caput do art. 62 da Lei 5.010/1966 diz 'serao feriados', e a Res. CNJ 244/2016, art. 2o, "
    "par. 1o, equipara o recesso ao FERIADO nos orgaos do Judiciario da Uniao; a suspensao de "
    "prazo do art. 220 do CPC corre por cima e nao o absorve, porque o par. 1o do art. 220 "
    "ressalva expressamente 'os feriados instituidos por lei'. De 7 a 20 de janeiro nao ha "
    "feriado: ha expediente normal com prazo suspenso (Res. CNJ 244/2016, art. 3o, par. unico). "
    "Convivencia dos dois efeitos: decisao do advogado registrada na pendencia juridica da base "
    "de calendario (pergunta 4).")



INCISOS = [
    ("I", "Recesso forense", "recesso_forense",
     {"recorrencia": "anual_fixa", "mes_dia_inicio": "12-20", "mes_dia_fim": "01-06"},
     ["20 de dezembro", "6 de janeiro"]),
    ("II", "Semana Santa (quarta-feira ao Domingo de Páscoa)", "suspensao_expediente",
     {"recorrencia": "anual_movel", "ancora": "pascoa",
      "deslocamento_inicio": -4, "deslocamento_fim": 0},
     ["semana santa", "quarta-feira", "domingo de pascoa"]),
    ("III", "Carnaval (segunda e terça-feira)", "suspensao_expediente",
     {"recorrencia": "anual_movel", "ancora": "pascoa",
      "deslocamento_inicio": -48, "deslocamento_fim": -47},
     ["segunda e ter", "carnaval"]),
    ("IV", "Dia do Advogado (11 de agosto)", "suspensao_expediente",
     {"recorrencia": "anual_fixa", "mes_dia_inicio": "08-11"}, ["11 de agosto"]),
    ("IV", "Dia de Todos os Santos (1º de novembro)", "suspensao_expediente",
     {"recorrencia": "anual_fixa", "mes_dia_inicio": "11-01"}, ["1", "de novembro"]),
    ("IV", "Finados (2 de novembro)", "suspensao_expediente",
     {"recorrencia": "anual_fixa", "mes_dia_inicio": "11-02"}, ["2 de novembro"]),
    ("IV", "Dia da Justiça (8 de dezembro)", "suspensao_expediente",
     {"recorrencia": "anual_fixa", "mes_dia_inicio": "12-08"}, ["8 de dezembro"]),
]


class FonteInesperada(Exception):
    """O texto recebido nao e o art. 62 que este modulo sabe ler. Para, e diz o que faltou."""


def sem_acento(valor: str) -> str:
    decomposto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _chave(texto: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(str(texto or "")).lower()).strip()


def texto_da_fonte(dados: bytes) -> str:
    'Devolve o texto corrido. Aceita HTML do Planalto ou texto puro.'



    for encoding in ("utf-8", "latin-1"):
        try:
            bruto = dados.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise FonteInesperada("nao foi possivel decodificar o arquivo (nem utf-8 nem latin-1)")
    if "<" in bruto and ">" in bruto:
        bruto = html.unescape(re.sub(r"<[^>]+>", " ", bruto))
    return re.sub(r"\s+", " ", bruto).strip()


def artigo_62(texto: str) -> str:
    """Recorta o art. 62 - do cabecalho dele ate o proximo artigo."""
    inicio = re.search(r"Art\.\s*62\b", texto)
    if not inicio:
        raise FonteInesperada("nao encontrei 'Art. 62' no texto da fonte")
    resto = texto[inicio.start():]
    fim = re.search(r"Art\.\s*6[3-9]\b", resto)
    trecho = resto[:fim.start()] if fim else resto
    if "feriados" not in _chave(trecho):
        raise FonteInesperada(
            "o trecho do art. 62 nao fala em feriados - a fonte nao e a Lei 5.010/1966?")
    return trecho


def redacao_vigente(trecho: str, numeral: str) -> tuple:
    'O inciso na redacao VIGENTE, e o motivo da escolha.'





    padrao = re.compile(r"\b%s\s*[-–]\s*(.+?)(?=\b[IVX]{1,4}\s*[-–]|Art\.\s*6[3-9]|$)"
                        % re.escape(numeral))
    achados = [m.group(1).strip() for m in padrao.finditer(trecho)]
    if not achados:
        return None, "inciso %s nao encontrado no art. 62" % numeral
    marcados = [a for a in achados if "redacao dada" in _chave(a)]
    if len(marcados) == 1:
        return marcados[0], "redação marcada como dada por lei posterior"
    if len(marcados) > 1:
        return None, ("inciso %s tem %d redações marcadas como posteriores; qual prevalece é "
                      "leitura jurídica e o módulo não escolhe" % (numeral, len(marcados)))
    if len(achados) == 1:
        return achados[0], "redação única no texto"
    return None, ("inciso %s aparece %d vezes e nenhuma está marcada com 'Redação dada'; o "
                  "módulo não sabe qual é a vigente" % (numeral, len(achados)))


def _grafias_colididas(tribunais) -> list:
    'Dois nomes que sao O MESMO tribunal escrito de dois jeitos.'




    por_chave: dict = {}
    for nome in tribunais:
        por_chave.setdefault(re.sub(r"[^a-z0-9]", "", _chave(nome)), set()).add(nome)
    return [{"grafias": sorted(g),
             "aviso": ("o mesmo tribunal foi declarado com grafias diferentes; na base viram "
                       "dois escopos e a consulta só acha um. Unifique antes de carregar")}
            for g in por_chave.values() if len(g) > 1]


def extrair(dados: bytes, procedencia: dict, tribunais) -> dict:
    tribunais = [str(t).strip() for t in (tribunais or []) if str(t).strip()]
    if not tribunais:
        raise FonteInesperada(
            "nenhum tribunal declarado: use --tribunal (repetível). O módulo não inventa em "
            "que tribunais o escritório atua, e sem escopo o registro não casa com consulta "
            "nenhuma - o feriado existiria e não seria encontrado")
    trecho = artigo_62(texto_da_fonte(dados))
    registros, nao_confirmados = [], []
    cache: dict = {}
    for numeral, rotulo, tipo, recorrencia, expressoes in INCISOS:
        if numeral not in cache:
            cache[numeral] = redacao_vigente(trecho, numeral)
        corpo, porque = cache[numeral]
        if corpo is None:
            nao_confirmados.append({"inciso": numeral, "rotulo": rotulo, "motivo": porque})
            continue
        chave = _chave(corpo)
        faltam = [e for e in expressoes if _chave(e) not in chave]
        if faltam:
            nao_confirmados.append({
                "inciso": numeral, "rotulo": rotulo,
                "motivo": "a redação vigente do inciso não confirma %r (leu: %r)"
                          % (faltam, corpo[:120])})
            continue
        efeito = "dia_nao_util"


        for tribunal in tribunais:
            registro = {
                "id": "jf-lei5010-art62-%s-%s-%s"
                      % (re.sub(r"[^a-z0-9]+", "-", _chave(tribunal)).strip("-"),
                         numeral.lower(),
                         re.sub(r"[^a-z0-9]+", "-", _chave(rotulo))[:40].strip("-")),
                "tipo": tipo,
                "rotulo": rotulo,
                "escopo": {"nivel": "tribunal", "valor": tribunal},
                "efeito": efeito,
                "vigencia_inicio": "1979-12-11",
                "vigencia_fim": None,
                "base_normativa": BASE_NORMATIVA % ("inciso " + numeral),
                "procedencia": dict(procedencia),
                "conferido_por": {"oraculo": "expressão do inciso encontrada no texto oficial",
                                  "expressoes": list(expressoes), "redacao": porque},
            }
            registro.update(recorrencia)
            if efeito != EFEITO_TIPICO[tipo]:
                registro["justificativa_efeito"] = JUSTIFICATIVA_RECESSO
            registros.append(registro)

    return {
        "schema_version": "dsr.extracao_camada_federal.v1",
        "escopos_declarados": list(tribunais),
        "procedencia": dict(procedencia),
        "registros": registros,
        "nao_confirmados": nao_confirmados,
        "grafias_divergentes": _grafias_colididas(tribunais),
        "resumo": {"registros": len(registros), "nao_confirmados": len(nao_confirmados),
                   "tribunais": len(tribunais),
                   "grafias_divergentes": len(_grafias_colididas(tribunais))},
        "como_consultar": ["--escopo tribunal=%s" % t for t in tribunais],
        "aviso_de_escopo": (
            "A base casa por escopo EXATO. Estes registros valem para os tribunais declarados "
            "acima e para mais nenhum: processo em tribunal NÃO declarado fica sem camada "
            "federal, e o art. 62 alcança toda a Justiça Federal, inclusive os Tribunais "
            "Superiores. Rode de novo com o tribunal que faltar — não replicar faz o feriado "
            "existir e não ser encontrado, que é o pior desfecho para dado de prazo. Use as "
            "linhas de `como_consultar` LITERALMENTE: 'TRF-3' e 'TRF 3' são dois escopos. "
            "E o módulo NÃO verifica que o tribunal declarado está de fato alcançado pelo art. "
            "62 — ele transcreve a lei e grava no escopo que recebeu. Se o alcance sobre aquele "
            "tribunal for discutível, a leitura é de quem declarou."),
        "aviso": (
            "Transcrição do art. 62 da Lei 5.010/1966, conferida expressão a expressão contra o "
            "texto oficial recebido. É LEI PERMANENTE: ao contrário do TJSP e dos TRTs, não há "
            "ato anual a recolher. O que NÃO está aqui é a suspensão local, que continua vindo "
            "por ato de cada tribunal. NÃO grava na base compartilhada: leve para o perfil."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Transcreve o art. 62 da Lei 5.010/1966 (feriados forenses da Justiça "
                    "Federal) em registros da base de calendário, conferindo cada data contra "
                    "o texto oficial.")
    ap.add_argument("--fonte", required=True, help="arquivo com o texto da lei (HTML ou texto)")
    ap.add_argument("--tribunal", action="append", default=[], metavar="NOME",
                    help="tribunal em que o escritório atua, NA GRAFIA que você usa na consulta "
                         "(ex.: TRF-3). Repetível, e obrigatório: o módulo não inventa a lista")
    ap.add_argument("--url", required=True, help="URL do texto em host oficial")
    ap.add_argument("--sha256", required=True, help="sha256 esperado; o módulo CONFERE o do arquivo")
    ap.add_argument("--ato", default="Lei")
    ap.add_argument("--numero", default="5.010/1966")
    ap.add_argument("--data-ato", default="1966-05-30")
    ap.add_argument("--data-coleta", required=True, help="AAAA-MM-DD em que a fonte foi baixada")
    ap.add_argument("--saida", help="grava o JSON aqui; sem isto, imprime")
    ap.add_argument("--parcial", action="store_true",
                    help="aceita saída com inciso não confirmado (por padrão isso é falha)")
    args = ap.parse_args(argv)

    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256 or ""):
        print("ERRO: --sha256 deve ser o hash de 64 hex do arquivo")
        return 2
    oficiais = (".jus.br/", ".gov.br/", ".leg.br/")
    if not str(args.url).startswith("https://") or not any(o in str(args.url) for o in oficiais):
        print("ERRO: --url deve ser https em host oficial (.jus.br, .gov.br, .leg.br)")
        return 2

    with open(args.fonte, "rb") as fh:
        dados = fh.read()
    medido = hashlib.sha256(dados).hexdigest()
    if medido.lower() != args.sha256.lower():
        print("ERRO: o sha256 do arquivo lido é %s, e não o informado %s.\n"
              "      A página do Planalto muda de bytes sem mudar de texto (rodapé, script). "
              "Reconfira o arquivo e o hash antes de transcrever lei." % (medido, args.sha256),
              file=sys.stderr)
        return 2

    procedencia = {"ato": args.ato, "numero": args.numero, "data": args.data_ato,
                   "url_fonte_oficial": args.url, "sha256_documento": medido,
                   "data_coleta": args.data_coleta}
    try:
        saida = extrair(dados, procedencia, args.tribunal)
    except FonteInesperada as erro:
        print("ERRO DE FONTE: %s" % erro, file=sys.stderr)
        return 2

    texto = json.dumps(saida, ensure_ascii=False, indent=1, sort_keys=False)
    if args.saida:
        with open(args.saida, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto + "\n")
        print("gravado em %s" % args.saida)
    else:
        print(texto)
    r = saida["resumo"]
    print("registros %d (%d por tribunal x %d tribunais) - NAO CONFIRMADOS %d"
          % (r["registros"], r["registros"] // max(r["tribunais"], 1), r["tribunais"],
             r["nao_confirmados"]), file=sys.stderr)
    print("  escopos: %s" % ", ".join(saida["escopos_declarados"]), file=sys.stderr)
    print("  consulte com: %s" % " | ".join(saida["como_consultar"]), file=sys.stderr)
    for aviso in saida["grafias_divergentes"]:
        print("  GRAFIA DIVERGENTE: %s" % " / ".join(aviso["grafias"]), file=sys.stderr)
    print("  ATENCAO: tribunal NAO declarado fica sem camada federal - o art. 62 alcanca toda "
          "a Justica Federal, inclusive os Superiores.", file=sys.stderr)
    for item in saida["nao_confirmados"]:
        print("  NAO CONFIRMADO %s (%s): %s" % (item["inciso"], item["rotulo"], item["motivo"]),
              file=sys.stderr)
    if saida["nao_confirmados"] and not args.parcial:
        print("FALHA: há inciso não confirmado pelo texto oficial. Confira a fonte; use "
              "--parcial para aceitar assim.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
