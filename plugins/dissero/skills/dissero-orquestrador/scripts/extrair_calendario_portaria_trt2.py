#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'extrair_calendario_portaria_trt2.py - transcreve a portaria anual do TRT-2 em registros.'







































from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
         "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
         "dezembro": 12}

SEMANA = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "dom": 6}









RECESSO = ("recesso forense", "recesso")



MOTIVOS_CONHECIDOS = {
    "recesso forense", "suspensao do expediente", "dia de cinzas",
    "feriado religioso local", "aniversario do municipio", "dia de corpus christi",
    "feriado religioso local e aniversario do municipio",
    "aniversario do municipio e feriado religioso local", "feriado municipal",
    "consciencia negra", "dia da consciencia negra", "semana santa", "carnaval",
    "dia de tiradentes", "dia do trabalhador", "confraternizacao universal",
    "independencia do brasil", "nossa senhora aparecida", "finados", "dia de finados",
    "proclamacao da republica", "dia da proclamacao da republica", "natal",
    "dia de todos os santos", "comemoracao do dia da justica",
    "comemoracao do dia do servidor publico", "dia do servidor publico",
}

EFEITO_TIPICO = {
    "feriado_nacional": "dia_nao_util",
    "feriado_estadual": "dia_nao_util",
    "feriado_municipal": "dia_nao_util",
    "recesso_forense": "suspensao_prazo",
    "suspensao_expediente": "dia_nao_util",
}


EFEITO_EM_ABERTO = ("recesso_forense",)









RECESSO_FERIADO = ((12, 20), (1, 6))
JUSTIFICATIVA_RECESSO = (
    "art. 62, I da Lei 5.010/1966 c/c Res. CNJ 244/2016, art. 2o, par. 1o, que equipara o "
    "recesso ao FERIADO nos orgaos do Judiciario da Uniao; a suspensao do art. 775-A da CLT "
    "corre por cima e nao o absorve (art. 220, par. 1o do CPC ressalva os feriados de lei). "
    "Alcance do art. 62 sobre a Justica do Trabalho: decisao do advogado registrada na "
    "pendencia juridica da base de calendario (pergunta 2)")


def _recesso_e_feriado(quando: date) -> bool:
    """True quando a data cai na janela em que o recesso E feriado (20/12 a 06/01)."""
    inicio, fim = RECESSO_FERIADO
    return (quando.month, quando.day) >= inicio or (quando.month, quando.day) <= fim

ABRANGENCIA_TRIBUNAL = "segunda regiao"

_LINHA = re.compile(r"^\s*(\d{1,2})(?:º|o)?\s+([A-Za-zÀ-ÿ]{3})\.\s+(.+?)\s*$")
_FUNDAMENTO = re.compile(r"\s(?=-?(?:Lei|Decreto|Portaria|Provimento|Ato|Emenda|Constitui)\b)")




FOLGA_COLUNA = 4


def _e_cabecalho_de_mes(linha: str) -> int | None:
    'Cabecalho de mes e a linha cujo conteudo, sozinho, E o nome do mes.'





    limpo = _chave(linha.replace("\x0c", " "))
    return MESES.get(limpo)


def sem_acento(valor: str) -> str:
    decomposto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _chave(texto: str) -> str:
    'Forma comparavel: sem acento, minuscula, espaco unico. A tabela do PDF separa'

    return re.sub(r"\s+", " ", sem_acento(str(texto or "")).lower()).strip()


def _partes(resto: str) -> tuple[str, str]:
    "Separa 'abrangencia + motivo' do 'fundamento'. O fundamento sempre comeca pelo nome"


    pedacos = _FUNDAMENTO.split(resto, maxsplit=1)
    esquerda = pedacos[0].strip()
    fundamento = re.sub(r"\s+", " ", pedacos[1].strip()) if len(pedacos) > 1 else ""
    return esquerda, fundamento


def _abrangencia_e_motivo(esquerda: str) -> tuple[str, str] | None:
    'Separa a coluna de abrangencia da coluna de motivo. None quando nao da para separar.'











    palavras = esquerda.split()
    for corte in range(1, len(palavras)):
        motivo = " ".join(palavras[corte:])




        if _motivo_reconhecido(motivo):
            return " ".join(palavras[:corte]).strip(), re.sub(r"\s+", " ", motivo)
    partes = re.split(r"\s{2,}", esquerda.strip(), maxsplit=1)
    if len(partes) == 2 and partes[0].strip() and partes[1].strip():
        return partes[0].strip(), re.sub(r"\s+", " ", partes[1].strip())
    return None






MAX_PALAVRAS_MUNICIPIO = 5


def _nome_de_municipio_plausivel(nome: str) -> str | None:
    'None quando o nome passa; string com o defeito quando nao passa.'






    limpo = re.sub(r"\s+", " ", str(nome or "").strip())
    if not limpo:
        return "vazio"
    if len(limpo.split()) > MAX_PALAVRAS_MUNICIPIO:
        return "%d palavras - coluna provavelmente colada" % len(limpo.split())
    if re.search(r"\d", limpo):
        return "contem digito - fundamento colado no nome"
    chave = _chave(limpo)
    if chave.startswith(ABRANGENCIA_TRIBUNAL):
        return "comeca pela abrangencia do tribunal - a separacao falhou"
    for conhecido in MOTIVOS_CONHECIDOS:
        if conhecido in chave:
            return "carrega o motivo %r dentro do nome" % conhecido
    return None


def _motivo_reconhecido(motivo: str) -> bool:
    'Reconhece por PREFIXO, nao por igualdade. A coluna de motivo carrega, em algumas'




    chave = _chave(motivo)
    return any(chave == conhecido or chave.startswith(conhecido + " ")
               for conhecido in MOTIVOS_CONHECIDOS)


def _tipo_por_escopo(abrangencia: str, motivo: str) -> tuple[str, dict]:
    'Tipo e escopo saem da ABRANGENCIA declarada na portaria, nao da natureza do feriado.'



    if _chave(abrangencia) == ABRANGENCIA_TRIBUNAL:
        tipo = "recesso_forense" if _chave(motivo) in RECESSO else "suspensao_expediente"
        return tipo, {"nivel": "tribunal", "valor": "TRT-2"}
    return "feriado_municipal", {"nivel": "municipio", "valor": re.sub(r"\s+", " ", abrangencia)}


def _confere_semana(dia: int, mes: int, ano: int, abreviacao: str) -> date | None:
    'ORACULO. Devolve a data quando o dia da semana IMPRESSO na portaria bate com o'

    chave = _chave(abreviacao)[:3]
    if chave not in SEMANA:
        return None
    try:
        alvo = date(ano, mes, dia)
    except ValueError:
        return None
    return alvo if alvo.weekday() == SEMANA[chave] else None


def extrair(linhas, ano: int, procedencia: dict) -> dict:
    """Le as linhas do PDF em modo tabela e devolve registros, pendentes e nao lidos."""
    registros, pendentes, nao_lidos = [], [], []
    mes_atual = None
    ultimo_bruto = None
    pulando_rodape = False

    for numero, linha in enumerate(linhas, start=1):
        crua = linha.rstrip("\n")
        if not crua.strip():
            continue





        if crua.lstrip().startswith("Fonte:"):
            pulando_rodape = True
            ultimo_bruto = _fechar(ultimo_bruto, registros, pendentes, nao_lidos, procedencia)
            continue
        mes_lido = _e_cabecalho_de_mes(crua)
        if mes_lido is not None:
            ultimo_bruto = _fechar(ultimo_bruto, registros, pendentes, nao_lidos, procedencia)
            mes_atual, pulando_rodape = mes_lido, False
            continue

        achado_linha = _LINHA.match(crua)
        if pulando_rodape and not achado_linha:
            continue
        pulando_rodape = False
        if not achado_linha:



            if ultimo_bruto is not None and crua.startswith(" ") and crua.strip():



                if _FUNDAMENTO.search(" " + crua.strip()):
                    ultimo_bruto = _fechar(ultimo_bruto, registros, pendentes,
                                           nao_lidos, procedencia)
                    nao_lidos.append({"linha": numero,
                                      "texto": re.sub(r"\s+", " ", crua.strip()),
                                      "motivo": "linha sem dia, mas com fundamento "
                                                "proprio: o dia ficou noutra linha"})
                    continue
                recuo = len(crua) - len(crua.lstrip())
                campo = ("abrangencia"
                         if abs(recuo - ultimo_bruto["coluna_abrangencia"]) <= FOLGA_COLUNA
                         else "motivo")
                ultimo_bruto[campo] = (ultimo_bruto[campo] + " " + crua.strip()).strip()
                _finalizar(ultimo_bruto, registros, pendentes, nao_lidos, procedencia)
                ultimo_bruto = None
            continue

        if ultimo_bruto is not None:
            _finalizar(ultimo_bruto, registros, pendentes, nao_lidos, procedencia)
            ultimo_bruto = None
        dia_txt, semana, resto = achado_linha.groups()
        esquerda, fundamento = _partes(resto)
        separado = _abrangencia_e_motivo(esquerda)
        ultimo_bruto = {"linha": numero, "crua": re.sub(r"\s+", " ", crua.strip()),
                        "dia": int(dia_txt), "semana": semana, "mes": mes_atual, "ano": ano,
                        "coluna_abrangencia": achado_linha.start(3),
                        "abrangencia": separado[0] if separado else "",
                        "motivo": separado[1] if separado else "",
                        "esquerda": esquerda, "fundamento": fundamento}

    if ultimo_bruto is not None:
        _finalizar(ultimo_bruto, registros, pendentes, nao_lidos, procedencia)

    return {
        "schema_version": "dsr.extracao_calendario_trt.v1",
        "tribunal": "TRT-2",
        "ano": ano,
        "procedencia": dict(procedencia),
        "avisos_de_escopo": _colisoes_de_escopo(registros + pendentes),
        "registros": registros,
        "pendentes_de_efeito": pendentes,
        "nao_lidos": nao_lidos,
        "resumo": {"registros": len(registros), "pendentes_de_efeito": len(pendentes),
                   "nao_lidos": len(nao_lidos),
                   "avisos_de_escopo": len(_colisoes_de_escopo(registros + pendentes))},
        "aviso": ("Transcricao do ATO, conferida linha a linha pelo dia da semana impresso na "
                  "propria portaria. NAO e consulta ao vivo: o art. 2o, par. 1o da "
                  "Portaria GP 50/2025 preve que suspensoes locais do ano corrente saem por "
                  "portaria PROPRIA "
                  "e so aparecem no portal - o que esta aqui e a grade anual, nao o ano inteiro. "
                  "NAO grava na base compartilhada: leve para o perfil do advogado."),
    }


def _colisoes_de_escopo(todos) -> list:
    'Escopos que sao O MESMO LUGAR escrito de dois jeitos.'






    por_chave: dict = {}
    for registro in todos:
        escopo = registro.get("escopo") or {}
        if escopo.get("nivel") != "municipio":
            continue
        por_chave.setdefault(_chave(escopo.get("valor")), set()).add(escopo.get("valor"))
    return [{"grafias": sorted(grafias),
             "aviso": ("o mesmo municipio aparece com grafias diferentes; na base viram dois "
                       "escopos e a consulta so acha um. Unifique antes de carregar")}
            for grafias in por_chave.values() if len(grafias) > 1]


def _fechar(bruto, registros, pendentes, nao_lidos, procedencia):
    """Fecha o evento pendente, se houver, e devolve None - para o chamador reatribuir."""
    if bruto is not None:
        _finalizar(bruto, registros, pendentes, nao_lidos, procedencia)
    return None


def _finalizar(bruto, registros, pendentes, nao_lidos, procedencia) -> None:
    """Valida um evento lido e o encaminha para a lista certa. Toda recusa e nomeada."""
    def recusar(motivo: str) -> None:
        nao_lidos.append({"linha": bruto["linha"], "texto": bruto["crua"], "motivo": motivo})

    if bruto["mes"] is None:
        return recusar("linha de evento antes de qualquer cabecalho de mes")
    quando = _confere_semana(bruto["dia"], bruto["mes"], bruto["ano"], bruto["semana"])
    if quando is None:
        return recusar("o dia da semana impresso (%s) nao confere com %02d/%02d/%d"
                       % (bruto["semana"], bruto["dia"], bruto["mes"], bruto["ano"]))
    abrangencia, motivo = bruto["abrangencia"], bruto["motivo"]
    if not abrangencia or not motivo:
        return recusar("nao deu para separar abrangencia de motivo em %r" % bruto["esquerda"])
    tipo, escopo = _tipo_por_escopo(abrangencia, motivo)
    if escopo["nivel"] == "municipio":


        if not _motivo_reconhecido(motivo):
            return recusar("abrangencia municipal %r com motivo desconhecido %r"
                           % (abrangencia, motivo))
        defeito = _nome_de_municipio_plausivel(escopo["valor"])
        if defeito:
            return recusar("nome de municipio implausivel %r: %s"
                           % (escopo["valor"], defeito))

    registro = {
        "id": "trt2-%s-%s-%s" % (bruto["ano"], quando.isoformat(),
                                 re.sub(r"[^a-z0-9]+", "-", _chave(abrangencia)).strip("-")),
        "tipo": tipo,
        "rotulo": motivo,
        "escopo": escopo,
        "efeito": EFEITO_TIPICO[tipo],
        "recorrencia": "unica",
        "data_inicio": quando.isoformat(),
        "vigencia_inicio": quando.isoformat(),
        "vigencia_fim": None,
        "base_normativa": bruto["fundamento"] or "(a portaria nao imprimiu fundamento nesta linha)",
        "procedencia": dict(procedencia),
    }
    if not bruto["fundamento"]:


        registro["_conferir"] = "linha sem fundamento impresso na portaria"
    if tipo in EFEITO_EM_ABERTO and _recesso_e_feriado(quando):



        registro["efeito"] = "dia_nao_util"
        registro["justificativa_efeito"] = JUSTIFICATIVA_RECESSO
        registros.append(registro)
    elif tipo in EFEITO_EM_ABERTO:
        registro["_efeito_em_aberto"] = (
            "dia de recesso FORA da janela de 20/12 a 06/01, que e a que o art. 62, I da Lei "
            "5.010/66 alcanca. A decisao sobre o alcance do art. 62 na Justica do Trabalho "
            "NAO se estende aqui: pela Res. CNJ 244/2016, art. 3o, par. unico, de 7 a 20 de "
            "janeiro ha expediente forense normal - dia util com prazo suspenso. Efeito deste "
            "dia segue do advogado")
        pendentes.append(registro)
    else:
        registros.append(registro)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Transcreve a portaria anual de feriados do TRT-2 em registros da base de "
                    "calendario. Confere cada data pelo dia da semana impresso no ato.")
    ap.add_argument("--texto", required=True,
                    help="saida de `pdftotext -table -enc UTF-8 <portaria>.pdf`")
    ap.add_argument("--ano", type=int, required=True)
    ap.add_argument("--url", required=True, help="URL do PDF em host oficial")
    ap.add_argument("--sha256", required=True, help="sha256 do PDF baixado")
    ap.add_argument("--ato", default="Portaria GP")
    ap.add_argument("--numero", required=True, help='ex.: "50/2025"')
    ap.add_argument("--data-ato", required=True, help="AAAA-MM-DD do ato")
    ap.add_argument("--data-coleta", required=True, help="AAAA-MM-DD em que o PDF foi baixado")
    ap.add_argument("--saida", help="grava o JSON aqui; sem isto, imprime")
    ap.add_argument("--parcial", action="store_true",
                    help="aceita saida com linhas nao lidas (por padrao isso e falha)")
    args = ap.parse_args(argv)

    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256 or ""):
        print("ERRO: --sha256 deve ser o hash de 64 hex do PDF")
        return 2
    if not str(args.url).startswith("https://") or ".jus.br/" not in str(args.url):
        print("ERRO: --url deve ser https em host oficial (.jus.br) - a base exige procedencia")
        return 2

    with open(args.texto, encoding="utf-8") as fh:
        linhas = fh.readlines()
    procedencia = {"ato": args.ato, "numero": args.numero, "data": args.data_ato,
                   "url_fonte_oficial": args.url, "sha256_documento": args.sha256,
                   "data_coleta": args.data_coleta}
    saida = extrair(linhas, args.ano, procedencia)

    texto = json.dumps(saida, ensure_ascii=False, indent=1, sort_keys=False)
    if args.saida:
        with open(args.saida, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto + "\n")
        print("gravado em %s" % args.saida)
    else:
        print(texto)
    r = saida["resumo"]
    print("registros %d - pendentes de efeito %d - NAO LIDOS %d"
          % (r["registros"], r["pendentes_de_efeito"], r["nao_lidos"]), file=sys.stderr)
    for aviso in saida["avisos_de_escopo"]:
        print("  GRAFIA DIVERGENTE: %s" % " / ".join(aviso["grafias"]), file=sys.stderr)
    for item in saida["nao_lidos"]:
        print("  NAO LIDO linha %s: %s | %s" % (item["linha"], item["motivo"], item["texto"][:90]),
              file=sys.stderr)
    if saida["nao_lidos"] and not args.parcial:
        print("FALHA: ha linha nao lida. Confira-a no PDF; use --parcial para aceitar assim.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
