#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'extrair_calendario_portaria_trt15.py - transcreve o anexo do TRT-15 lendo a GRADE do PDF.'




























































from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import zlib
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
         "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
         "dezembro": 12}

CABECALHO_ESPERADO = ["S", "T", "Q", "Q", "S"]
DIA_DA_COLUNA = [0, 1, 2, 3, 4]
NOME_DA_COLUNA = ["segunda", "terca", "quarta", "quinta", "sexta"]


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

RECESSO = ("recesso",)





LEGENDA_CONHECIDA = ("suspensao de expediente",)
TRIBUNAL = "TRT-15"





FOLGA = 1.5


def sem_acento(valor: str) -> str:
    decomposto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _chave(texto: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(str(texto or "")).lower()).strip()


class EstruturaInesperada(Exception):
    'O PDF nao e a grade que este modulo sabe ler. Para, e diz o que faltou.'









def _objetos(dados: bytes) -> dict:
    return {int(m.group(1)): m.group(2)
            for m in re.finditer(rb"(\d+)\s+0\s+obj(.*?)endobj", dados, re.S)}


def _fluxo(objs: dict, numero: int) -> bytes:
    achado = re.search(rb"stream\r?\n(.*?)endstream", objs.get(numero, b""), re.S)
    if not achado:
        raise EstruturaInesperada("objeto %d nao tem stream" % numero)
    try:
        return zlib.decompress(achado.group(1))
    except zlib.error:
        return achado.group(1)


def _cmaps(objs: dict) -> dict:
    'Mapa /Fn -> {codigo: caractere}, lido do /ToUnicode de cada fonte.'





    fontes = {}
    for numero, corpo in objs.items():
        for nome, ref in re.findall(rb"/(F\d+)\s+(\d+)\s+0\s+R", corpo):
            alvo = objs.get(int(ref), b"")
            if b"/Font" not in alvo and b"/ToUnicode" not in alvo:
                continue
            achado = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", alvo)
            if not achado:
                continue
            texto = _fluxo(objs, int(achado.group(1))).decode("latin-1")
            if "beginbfrange" in texto:
                raise EstruturaInesperada(
                    "a fonte %s usa CMap com beginbfrange, que este leitor nao decodifica"
                    % nome.decode())
            faixa = re.search(r"begincodespacerange\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", texto)
            if faixa and len(faixa.group(1)) != 2:
                raise EstruturaInesperada(
                    "a fonte %s usa codigo de %d bytes; este leitor so le byte unico"
                    % (nome.decode(), len(faixa.group(1)) // 2))
            tabela = {}
            for bloco in re.findall(r"beginbfchar(.*?)endbfchar", texto, re.S):
                for cod, uni in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", bloco):
                    tabela[int(cod, 16)] = chr(int(uni, 16))
            fontes[nome.decode()] = tabela
    if not fontes:
        raise EstruturaInesperada(
            "nenhuma fonte com /ToUnicode encontrada - o PDF pode usar object streams "
            "comprimidos (/ObjStm), que este leitor nao abre")
    return fontes


def _conteudo_da_pagina(objs: dict) -> str:
    for numero, corpo in objs.items():
        if b"stream" not in corpo:
            continue
        try:
            dados = _fluxo(objs, numero)
        except EstruturaInesperada:
            continue



        if b"BT" in dados and b"Tf" in dados:
            return dados.decode("latin-1")
    raise EstruturaInesperada("nenhum content stream com bloco de texto (BT/Tf)")


def _tracos(conteudo: str) -> tuple:
    'Reguas horizontais (y, x_inicial, x_final) e colunas verticais (x).'




    horizontais, verticais = set(), set()
    for m in re.finditer(r"(-?[\d.]+)\s+(-?[\d.]+)\s+m\s+(-?[\d.]+)\s+(-?[\d.]+)\s+l", conteudo):
        x1, y1, x2, y2 = (float(g) for g in m.groups())
        if abs(y1 - y2) < FOLGA and abs(x2 - x1) > 40:
            horizontais.add((round(y1, 1), round(min(x1, x2), 1), round(max(x1, x2), 1)))
        elif abs(x1 - x2) < FOLGA and abs(y2 - y1) > 40:
            verticais.add(round(x1, 1))
    return sorted(horizontais, reverse=True), sorted(verticais)


_TEXTO = re.compile(
    r"(-?[\d.]+)\s+(-?[\d.]+)\s+Td|/(F\d+)\s+[\d.]+\s+Tf|<([0-9A-Fa-f]*)>\s*Tj|\[(.*?)\]\s*TJ",
    re.S)


def _textos(conteudo: str, fontes: dict) -> list:
    'Cada fragmento de texto com a coordenada em que foi posto: (y, x, texto).'



    if re.search(r"\bTm\b", conteudo):
        raise EstruturaInesperada(
            "o content stream usa o operador Tm, que reposiciona o texto de um jeito que este "
            "leitor nao acompanha - as coordenadas sairiam erradas em silencio")
    achados, fonte, x, y = [], None, 0.0, 0.0
    for m in _TEXTO.finditer(conteudo):
        if m.group(1) is not None:
            x, y = float(m.group(1)), float(m.group(2))
        elif m.group(3) is not None:
            fonte = m.group(3)
        else:
            bruto = ([m.group(4)] if m.group(4) is not None
                     else re.findall(r"<([0-9A-Fa-f]*)>", m.group(5)))
            tabela = fontes.get(fonte or "", {})
            texto = "".join("".join(tabela.get(c, "�") for c in bytes.fromhex(h))
                            for h in bruto if len(h) % 2 == 0)
            if texto:
                achados.append((round(y, 1), round(x, 1), texto))
    return achados


def ler_geometria(dados: bytes) -> dict:
    """Le o PDF e devolve a grade: colunas, reguas e texto posicionado."""
    objs = _objetos(dados)
    if not objs:
        raise EstruturaInesperada("nenhum objeto PDF encontrado - o arquivo e um PDF?")
    conteudo = _conteudo_da_pagina(objs)
    horizontais, verticais = _tracos(conteudo)
    return {"reguas": horizontais, "colunas": verticais,
            "textos": _textos(conteudo, _cmaps(objs))}



def _bordas_da_coluna(geometria: dict, indice: int) -> list:
    """As reguas que atravessam a coluna INTEIRA. Regua parcial nao corta esta coluna."""
    colunas = geometria["colunas"]
    esquerda, direita = colunas[indice], colunas[indice + 1]
    return sorted({y for y, a, b in geometria["reguas"]
                   if a <= esquerda + FOLGA and b >= direita - FOLGA}, reverse=True)


def _faixa(geometria: dict, indice: int, altura: float):
    """(topo, base) da celula da coluna `indice` que contem a altura `altura`."""
    bordas = _bordas_da_coluna(geometria, indice)
    for topo, base in zip(bordas, bordas[1:]):
        if base < altura <= topo:
            return (topo, base)
    return None


def _linhas_da_faixa(geometria: dict, indice: int, faixa) -> list:
    'As LINHAS da celula, de cima para baixo, como (altura, texto).'







    if not faixa:
        return []
    colunas = geometria["colunas"]
    esquerda, direita = colunas[indice], colunas[indice + 1]
    linhas: dict = {}
    for y, x, t in geometria["textos"]:
        if esquerda - FOLGA <= x < direita - FOLGA and faixa[1] < y <= faixa[0]:
            linhas.setdefault(y, []).append((x, t))
    saida = []
    for y in sorted(linhas, reverse=True):
        texto = re.sub(r"\s+", " ", "".join(t for _, t in sorted(linhas[y]))).strip()
        if texto:
            saida.append((y, texto))
    return saida


def _texto_da_faixa(geometria: dict, indice: int, faixa) -> str:
    return re.sub(r"\s+", " ",
                  " ".join(t for _, t in _linhas_da_faixa(geometria, indice, faixa))).strip()


def _confere_cabecalho(geometria: dict) -> None:
    """A grade tem de ser a que este modulo conhece: 8 colunas e S T Q Q S no cabecalho."""
    colunas = geometria["colunas"]
    if len(colunas) != 9:
        raise EstruturaInesperada(
            "a grade tem %d colunas verticais; o anexo do TRT-15 tem 9 bordas (mes, cinco dias, "
            "motivo, legislacao)" % len(colunas))
    bordas = _bordas_da_coluna(geometria, 1)
    if len(bordas) < 2:
        raise EstruturaInesperada("nao ha reguas horizontais suficientes para formar linhas")
    cabecalho = [_texto_da_faixa(geometria, i, (bordas[0], bordas[1])) for i in range(1, 6)]
    if [c.strip().upper() for c in cabecalho] != CABECALHO_ESPERADO:
        raise EstruturaInesperada(
            "o cabecalho das colunas de dia leu %r, e nao %r - a grade mudou de forma"
            % (cabecalho, CABECALHO_ESPERADO))


_DIA = re.compile(r"^(\d{1,2})(\*{0,2})$")
_MARCA = re.compile(r"^(\*{1,2})$")


def _dias_marcados(geometria: dict) -> list:
    'Cada numero de dia com sua coluna, sua altura e o MARCADOR que lhe pertence.'




    achados = []
    colunas = geometria["colunas"]
    for indice in range(1, 6):
        esquerda, direita = colunas[indice], colunas[indice + 1]
        na_coluna = [(y, x, t.strip()) for y, x, t in geometria["textos"]
                     if esquerda - FOLGA <= x < direita - FOLGA and t.strip()]
        for altura, _, texto in na_coluna:
            achado = _DIA.match(texto)
            if not achado:
                continue
            faixa = _faixa(geometria, indice, altura)
            marca = achado.group(2)
            if not marca and faixa:
                soltos = [t for y, _, t in na_coluna
                          if faixa[1] < y <= faixa[0] and _MARCA.match(t)]
                marca = soltos[0] if len(soltos) == 1 else ""
            achados.append({"dia": int(achado.group(1)), "coluna": indice,
                            "altura": altura, "marca": marca, "faixa": faixa})
    return sorted(achados, key=lambda d: (-d["altura"], d["coluna"]))


def _fragmentos(linhas: list) -> tuple:
    'Reparte as linhas da celula de motivo em (principais, {marcador: legenda}).'















    principais, legendas, atual = [], {}, None
    for altura, texto in linhas:
        marcador = re.match(r"^(\*{1,2})\s*", texto)
        if marcador:
            chave = marcador.group(1)
            corpo = texto[marcador.end():].strip()
            legendas[chave] = (legendas.get(chave, "") + " " + corpo).strip()
            reconhecida = any(_chave(corpo).startswith(termo) for termo in LEGENDA_CONHECIDA)
            atual = None if (reconhecida and not corpo.rstrip().endswith("/")) else chave
            continue
        if atual is not None:
            legendas[atual] = (legendas[atual] + " " + texto).strip()
            if any(_chave(legendas[atual]).startswith(termo) for termo in LEGENDA_CONHECIDA) \
                    and not texto.rstrip().endswith("/"):
                atual = None
            continue
        principais.append((altura, texto))
    return principais, {k: re.sub(r"\s+", " ", v).strip(" /") for k, v in legendas.items()}


def _tipo(rotulo: str, celula: str) -> str:
    'O tipo sai do ESCOPO, nao da natureza do feriado - a mesma regra do TRT-2.'






    if any(termo in _chave(rotulo) + " " + _chave(celula) for termo in RECESSO):
        return "recesso_forense"
    return "suspensao_expediente"


def extrair(geometria: dict, ano: int, procedencia: dict) -> dict:
    """Le a grade e devolve registros, pendentes de efeito e nao lidos."""
    _confere_cabecalho(geometria)
    registros, pendentes, nao_lidos = [], [], []

    for achado in _dias_marcados(geometria):
        dia, indice, altura, marca = (achado["dia"], achado["coluna"],
                                      achado["altura"], achado["marca"])

        def recusar(motivo: str) -> None:
            nao_lidos.append({"dia": dia, "coluna": NOME_DA_COLUNA[indice - 1],
                              "altura": altura, "motivo": motivo})

        faixa_mes = _faixa(geometria, 0, altura)
        mes_escrito = _texto_da_faixa(geometria, 0, faixa_mes)
        mes = MESES.get(_chave(mes_escrito).replace(" ", ""))
        if mes is None:
            recusar("a celula de mes leu %r, que nao e nome de mes" % mes_escrito)
            continue

        try:
            quando = date(ano, mes, dia)
        except ValueError:
            recusar("%02d/%02d/%d nao existe no calendario" % (dia, mes, ano))
            continue
        if quando.weekday() != DIA_DA_COLUNA[indice - 1]:
            recusar("o dia esta na coluna de %s, mas %s cai numa outra"
                    % (NOME_DA_COLUNA[indice - 1], quando.isoformat()))
            continue

        faixa_motivo = _faixa(geometria, 6, altura)
        linhas_motivo = _linhas_da_faixa(geometria, 6, faixa_motivo)
        celula_motivo = _texto_da_faixa(geometria, 6, faixa_motivo)
        principais, legendas = _fragmentos(linhas_motivo)
        do_bloco = False
        if marca:
            if marca not in legendas:
                recusar("o dia esta marcado com %r e a celula de motivo nao traz essa legenda: %r"
                        % (marca, celula_motivo))
                continue
            rotulo = legendas[marca]
        else:




            propria = [t for y, t in principais
                       if achado["faixa"] and achado["faixa"][1] < y <= achado["faixa"][0]]
            if propria and achado["faixa"] != faixa_motivo:
                rotulo = re.sub(r"\s+", " ", " ".join(propria)).strip(" /")
            else:
                rotulo = re.sub(r"\s+", " ", " ".join(t for _, t in principais)).strip(" /")





                do_bloco = " / " in rotulo
        if not rotulo:
            recusar("a celula de motivo nao traz motivo fora das legendas para este dia")
            continue

        faixa_lei = _faixa(geometria, 7, altura)
        fundamento = _texto_da_faixa(geometria, 7, faixa_lei)



        tipo = _tipo(rotulo, "" if marca else celula_motivo)

        registro = {
            "id": "trt15-%s-%s%s" % (ano, quando.isoformat(), "-marcado" if marca else ""),
            "tipo": tipo,
            "rotulo": rotulo,
            "escopo": {"nivel": "tribunal", "valor": TRIBUNAL},
            "efeito": EFEITO_TIPICO[tipo],
            "recorrencia": "unica",
            "data_inicio": quando.isoformat(),
            "vigencia_inicio": quando.isoformat(),
            "vigencia_fim": None,
            "base_normativa": fundamento or "(o anexo nao imprimiu fundamento nesta linha)",
            "procedencia": dict(procedencia),
            "conferido_por": {"oraculo": "coluna do dia da semana na grade",
                              "coluna": NOME_DA_COLUNA[indice - 1]},
        }
        if not fundamento:
            registro["_conferir"] = "dia sem fundamento impresso no anexo"
        if do_bloco:
            registro["_rotulo_do_bloco"] = (
                "o anexo poe varios motivos numa celula so e nao diz qual dia e qual; o rotulo "
                "acima e o BLOCO inteiro, nao a linha deste dia. Reparta a mao antes de usar")



        if re.search(r"transferid|antecipa", _chave(rotulo)):
            registro["_instituto_a_conferir"] = (
                "o anexo declara TRANSFERENCIA de feriado, que nao e prorrogacao nem suspensao: "
                "o dia nao util muda de data e a data legal volta a ser util. A base nao tem "
                "esse instituto - decisao do advogado")
        if re.search(r"lei municipal|municipal em", _chave(celula_motivo) + " " + _chave(fundamento)):
            registro["_abrangencia_a_conferir"] = (
                "o fundamento desta linha invoca lei MUNICIPAL, que nao alcanca a 15a Regiao "
                "inteira; o anexo nem sempre nomeia o municipio. Confira o foro antes de usar")
        if tipo in EFEITO_EM_ABERTO and _recesso_e_feriado(quando):



            registro["efeito"] = "dia_nao_util"
            registro["justificativa_efeito"] = JUSTIFICATIVA_RECESSO
            registros.append(registro)
        elif tipo in EFEITO_EM_ABERTO:
            registro["_efeito_em_aberto"] = (
                "dia de recesso FORA da janela de 20/12 a 06/01, que e a que o art. 62, I da "
                "Lei 5.010/66 alcanca. A decisao sobre o alcance do art. 62 na Justica do "
                "Trabalho NAO se estende aqui: pela Res. CNJ 244/2016, art. 3o, par. unico, de "
                "7 a 20 de janeiro ha expediente forense normal - dia util com prazo suspenso. "
                "Efeito deste dia segue do advogado")
            pendentes.append(registro)
        else:
            registros.append(registro)

    duplicados = _datas_repetidas(registros + pendentes)
    return {
        "schema_version": "dsr.extracao_calendario_trt.v1",
        "tribunal": TRIBUNAL,
        "ano": ano,
        "procedencia": dict(procedencia),
        "avisos_de_escopo": duplicados,
        "registros": registros,
        "pendentes_de_efeito": pendentes,
        "nao_lidos": nao_lidos,
        "resumo": {"registros": len(registros), "pendentes_de_efeito": len(pendentes),
                   "nao_lidos": len(nao_lidos), "avisos_de_escopo": len(duplicados)},
        "aviso": ("Transcricao do ANEXO, conferida dia a dia pela coluna do dia da semana em que "
                  "a grade poe cada numero. NAO e consulta ao vivo: suspensoes supervenientes "
                  "saem por ato PROPRIO do tribunal (ex.: o Provimento GP-CR 008/2026 suspendeu "
                  "13 a 17/07/2026) e nao estao neste anexo. NAO grava na base compartilhada: "
                  "leve para o perfil."),
    }


def _datas_repetidas(todos: list) -> list:
    'Mesma data saindo duas vezes com rotulos diferentes.'




    por_data: dict = {}
    for registro in todos:
        por_data.setdefault(registro["data_inicio"], []).append(registro["rotulo"])
    return [{"data": data, "rotulos": sorted(set(rotulos)),
             "aviso": ("a mesma data aparece mais de uma vez na grade; confira se sao o mesmo "
                       "dia nao util antes de carregar")}
            for data, rotulos in sorted(por_data.items()) if len(rotulos) > 1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Transcreve o anexo anual de feriados do TRT-15 lendo a GRADE do PDF. "
                    "Confere cada data pela coluna do dia da semana em que o anexo a poe.")
    ap.add_argument("--pdf", required=True, help="o PDF do anexo, baixado de host oficial")
    ap.add_argument("--ano", type=int, required=True)
    ap.add_argument("--url", required=True, help="URL do PDF em host oficial")
    ap.add_argument("--sha256", required=True,
                    help="sha256 esperado; o modulo CONFERE o do arquivo lido")
    ap.add_argument("--ato", default="Portaria GP-CR")
    ap.add_argument("--numero", required=True, help='ex.: "016/2025"')
    ap.add_argument("--data-ato", required=True, help="AAAA-MM-DD do ato")
    ap.add_argument("--data-coleta", required=True, help="AAAA-MM-DD em que o PDF foi baixado")
    ap.add_argument("--saida", help="grava o JSON aqui; sem isto, imprime")
    ap.add_argument("--parcial", action="store_true",
                    help="aceita saida com dia nao lido (por padrao isso e falha)")
    args = ap.parse_args(argv)

    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256 or ""):
        print("ERRO: --sha256 deve ser o hash de 64 hex do PDF")
        return 2
    if not str(args.url).startswith("https://") or ".jus.br/" not in str(args.url):
        print("ERRO: --url deve ser https em host oficial (.jus.br) - a base exige procedencia")
        return 2

    with open(args.pdf, "rb") as fh:
        dados = fh.read()
    medido = hashlib.sha256(dados).hexdigest()
    if medido.lower() != args.sha256.lower():
        print("ERRO: o sha256 do arquivo lido e %s, e nao o informado %s.\n"
              "      Ou o ato foi republicado (o tribunal republica por erro material), ou "
              "este nao e o arquivo que se pensa."
              % (medido, args.sha256.lower()), file=sys.stderr)
        return 2

    procedencia = {"ato": args.ato, "numero": args.numero, "data": args.data_ato,
                   "url_fonte_oficial": args.url, "sha256_documento": medido,
                   "data_coleta": args.data_coleta}
    try:
        saida = extrair(ler_geometria(dados), args.ano, procedencia)
    except EstruturaInesperada as erro:
        print("ERRO DE ESTRUTURA: %s" % erro, file=sys.stderr)
        print("      O modulo para em vez de transcrever errado. Confira o PDF a mao.",
              file=sys.stderr)
        return 2

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
        print("  DATA REPETIDA %s: %s" % (aviso["data"], " / ".join(aviso["rotulos"])),
              file=sys.stderr)
    for item in saida["nao_lidos"]:
        print("  NAO LIDO dia %s (coluna %s): %s"
              % (item["dia"], item["coluna"], item["motivo"]), file=sys.stderr)
    if saida["nao_lidos"] and not args.parcial:
        print("FALHA: ha dia nao lido. Confira-o no PDF; use --parcial para aceitar assim.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
