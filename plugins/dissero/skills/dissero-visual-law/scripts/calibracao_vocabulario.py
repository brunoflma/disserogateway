#!/usr/bin/env python3
'Calibração do tom da peça pela força da tese (gate L26 do lint_peca).'


















from __future__ import annotations

import argparse
import ast
import datetime as _dt
import json
import re
import sys
from os import path as _path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_VERSION = "dsr.calibracao_vocabulario.v2"
_PASTA = _path.dirname(_path.abspath(__file__))
CONTRATO_PADRAO = _path.join(_PASTA, "estrategia_precedentes.py")
TABELA_PADRAO = _path.join(_PASTA, "vocabulario_por_cobertura.json")


CAMPOS_REVISAO = ("papel", "revisor", "revisado_em", "review_valid_to", "review_valid_from")
CAMPOS_ISENCAO = ("autorizado_por", "expressao_id", "cobertura", "razao")
CAMPOS_NEGACAO = ("fim_de_oracao", "marcadores")



JANELA_TRECHO = 60
MAX_RESUMO = 10
MINIMO_RAZAO_OVERRIDE = 30
MINIMO_MOTIVO_CLASSE = 10

MOTIVO_SEM_COBERTURA = (
    "sem a cobertura de precedente declarada não há como calibrar. Avaliar a força da tese "
    "pelo próprio texto da peça é juízo jurídico, que fica com o advogado. Informe "
    "cobertura_precedente no registro dsr.achados.v3 e rode de novo."
)


def _limpo(x):
    return str(x or "").strip()


def _data(bruto):
    'Data ISO lida de texto, ou None. Só aceita str: um número poderia ser lido como data'

    if isinstance(bruto, str):
        try:
            return _dt.date.fromisoformat(bruto[:10])
        except ValueError:
            pass
    return None


def _defeito_regex(fonte):
    """Mensagem do erro de compilação da expressão regular, ou None se ela compila."""
    try:
        re.compile(fonte, flags=re.IGNORECASE)
    except re.error as exc:
        return str(exc)
    return None


def carregar_tabela(arquivo=TABELA_PADRAO):
    """Lê a tabela e devolve (tabela, erro). Falha de leitura vira texto, nunca exceção."""
    try:
        with open(arquivo, "r", encoding="utf-8-sig") as fp:
            bruto = fp.read()
    except UnicodeDecodeError:
        return None, "a tabela não está em UTF-8"
    except OSError as exc:
        return None, "não consegui abrir a tabela (%s)" % type(exc).__name__
    try:
        return json.loads(bruto), None
    except ValueError as exc:
        return None, "a tabela não é JSON válido (%s)" % exc


def coberturas_do_contrato(arquivo=CONTRATO_PADRAO):
    'Nomes do conjunto COBERTURAS do contrato de estratégia, ou None se ilegível.'





    try:
        with open(arquivo, "r", encoding="utf-8") as fp:
            arvore = ast.parse(fp.read(), filename=arquivo)
    except (OSError, SyntaxError, ValueError):
        return None
    literal = None
    for no in arvore.body:
        if isinstance(no, ast.Assign):
            nomes = {t.id for t in no.targets if isinstance(t, ast.Name)}
        elif isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name):
            nomes = {no.target.id}
        else:
            continue
        if "COBERTURAS" in nomes and no.value is not None:
            literal = no.value
    if literal is None:
        return None
    try:
        conjunto = ast.literal_eval(literal)
    except (ValueError, SyntaxError, TypeError):
        return None
    if isinstance(conjunto, (set, frozenset, list, tuple)) and conjunto:
        return set(map(str, conjunto))
    return None






def _falhas_coberturas(bloco, contrato, falhas):
    """Confere o bloco de coberturas e devolve os nomes declarados (vazio se inválido)."""
    if not isinstance(bloco, dict) or not bloco:
        falhas.append("bloco «coberturas» vazio ou ausente")
        return set()
    declaradas = set(bloco)
    do_contrato = coberturas_do_contrato(contrato)
    if do_contrato is None:
        falhas.append("COBERTURAS ilegível em estrategia_precedentes.py: sem a lista oficial "
                      "a calibração não se faz")
    elif declaradas != do_contrato:
        falhas.append("as coberturas da tabela %s não batem com as do contrato %s"
                      % (sorted(declaradas), sorted(do_contrato)))
    quem_tem = {}
    for nome in sorted(bloco):
        ficha = bloco[nome]
        rank = ficha.get("rank") if isinstance(ficha, dict) else None

        if type(rank) is not int:
            falhas.append("cobertura «%s»: rank precisa ser número inteiro" % nome)
        elif rank in quem_tem:
            falhas.append("coberturas «%s» e «%s» com o mesmo rank: a ordem de solidez fica "
                          "indefinida" % (quem_tem[rank], nome))
        else:
            quem_tem[rank] = nome
    return declaradas


def _falhas_classes(bloco, coberturas, minimo_motivo, falhas):
    """Confere as classes; devolve o bloco para a checagem das expressões."""
    if not isinstance(bloco, dict) or not bloco:
        falhas.append("bloco «classes» vazio ou ausente")
        return {}
    for nome in sorted(bloco):
        ficha = bloco[nome]
        if not isinstance(ficha, dict):
            falhas.append("classe «%s» precisa ser objeto" % nome)
            continue
        if _limpo(ficha.get("exige_cobertura")) not in coberturas:
            falhas.append("classe «%s» pede cobertura que o contrato não conhece" % nome)
        if len(_limpo(ficha.get("motivo"))) < minimo_motivo:
            falhas.append("classe «%s»: o motivo tem menos de %d caracteres, e é ele que "
                          "explica o apontamento ao advogado" % (nome, minimo_motivo))
    return bloco


def _falhas_expressoes(lista, classes, coberturas, falhas):
    """Confere cada expressão; devolve os ids aceitos, que as isenções podem citar."""
    aceitos = set()
    if not isinstance(lista, list) or not lista:
        falhas.append("bloco «expressoes» vazio ou ausente")
        return aceitos
    for pos, expr in enumerate(lista):
        rotulo = "expressoes[%d]" % pos
        if not isinstance(expr, dict):
            falhas.append("%s precisa ser objeto" % rotulo)
            continue
        nome = _limpo(expr.get("id"))
        if not nome:
            falhas.append("%s: falta o id" % rotulo)
        elif nome in aceitos:
            falhas.append("%s: id «%s» repetido" % (rotulo, nome))
        else:
            aceitos.add(nome)
        classe = _limpo(expr.get("classe"))
        if classe not in classes:
            falhas.append("%s: a classe «%s» não existe na tabela" % (rotulo, classe))
        propria = expr.get("exige_cobertura")
        if propria is not None and _limpo(propria) not in coberturas:
            falhas.append("%s: exige_cobertura «%s» fora do contrato" % (rotulo, _limpo(propria)))
        regex = expr.get("padrao")
        if not isinstance(regex, str) or regex == "":
            falhas.append("%s: falta o padrão" % rotulo)
            continue
        defeito = _defeito_regex(regex)
        if defeito:
            falhas.append("%s: padrão inválido (%s)" % (rotulo, defeito))
    return aceitos


def _falhas_negacao(bloco, falhas):
    'O bloco de negação é obrigatório: sem ele a frase que concede («não é pacífico»)'

    if not isinstance(bloco, dict):
        falhas.append("bloco «negacao» ausente ou malformado: sem ele a calibração não separa "
                      "a afirmação da negação")
        return
    for campo in CAMPOS_NEGACAO:
        expr = bloco.get(campo)
        if not (isinstance(expr, str) and expr.strip()):
            falhas.append("negacao.%s precisa ser texto não vazio" % campo)
            continue
        defeito = _defeito_regex(expr)
        if defeito:
            falhas.append("negacao.%s: padrão inválido (%s)" % (campo, defeito))


def _falhas_isencoes(lista, ids, coberturas, minimo_razao, falhas):
    """Isenção incompleta invalida a tabela inteira: exceção sem razão escrita não vale."""
    if not isinstance(lista, list):
        falhas.append("«isencoes» precisa ser lista")
        return
    for pos, registro in enumerate(lista):
        rotulo = "isencoes[%d]" % pos
        if not isinstance(registro, dict):
            falhas.append("%s precisa ser objeto" % rotulo)
            continue
        vazios = [campo for campo in CAMPOS_ISENCAO if not _limpo(registro.get(campo))]
        if vazios:
            falhas.append("%s: faltam %s" % (rotulo, ", ".join(vazios)))
            continue
        alvo = _limpo(registro["expressao_id"])
        if alvo not in ids:
            falhas.append("%s: expressao_id «%s» não existe na tabela" % (rotulo, alvo))
        sob = _limpo(registro["cobertura"])
        if sob not in coberturas:
            falhas.append("%s: cobertura «%s» fora do contrato" % (rotulo, sob))
        if len(_limpo(registro["razao"])) < minimo_razao:
            falhas.append("%s: a razão tem menos de %d caracteres" % (rotulo, minimo_razao))


def _falhas_revisao(assinatura, hoje, falhas):
    """Tabela ligada exige revisão de advogado identificado, vigente na data de referência."""
    if not isinstance(assinatura, dict):
        falhas.append("revisão ausente: tabela ligada precisa de revisão assinada")
        return
    ausentes = [campo for campo in CAMPOS_REVISAO if assinatura.get(campo) in (None, "")]
    if ausentes:
        falhas.append("revisão incompleta: faltam %s" % ", ".join(ausentes))
        return

    if not _limpo(assinatura.get("revisor")):
        falhas.append("revisão sem revisor identificado")
    if _limpo(assinatura.get("papel")).lower() != "advogado":
        falhas.append("revisão precisa ser de advogado (papel «advogado»)")
    assinada_em = _data(assinatura.get("revisado_em"))
    if assinada_em is None or assinada_em > hoje:
        falhas.append("revisado_em ausente, ilegível ou no futuro")
    desde = _data(assinatura.get("review_valid_from"))
    vence = _data(assinatura.get("review_valid_to"))
    if None in (desde, vence):
        falhas.append("review_valid_from/review_valid_to ilegíveis")
    elif desde > vence:
        falhas.append("review_valid_from posterior a review_valid_to")
    elif hoje < desde or hoje > vence:
        falhas.append("revisão fora da vigência em %s" % hoje.isoformat())


def impedimentos(tabela, hoje=None, *, minimo_motivo=MINIMO_MOTIVO_CLASSE,
                 minimo_razao=MINIMO_RAZAO_OVERRIDE, contrato=CONTRATO_PADRAO):
    'Lista o que impede usar a tabela na data `hoje`; lista vazia quer dizer pronta.'




    if not isinstance(tabela, dict):
        return ["a tabela de vocabulário não é um objeto JSON"]
    falhas = []
    if tabela.get("schema_version") != SCHEMA_VERSION:
        falhas.append("schema_version precisa ser %s" % SCHEMA_VERSION)
    coberturas = _falhas_coberturas(tabela.get("coberturas"), contrato, falhas)
    classes = _falhas_classes(tabela.get("classes"), coberturas, minimo_motivo, falhas)
    ids = _falhas_expressoes(tabela.get("expressoes"), classes, coberturas, falhas)
    _falhas_negacao(tabela.get("negacao"), falhas)
    _falhas_isencoes(tabela.get("isencoes", []), ids, coberturas, minimo_razao, falhas)
    if tabela.get("habilitado") is not True:
        falhas.append("tabela DESLIGADA (habilitado diferente de true): para ligar, preencha a "
                      "revisão do advogado com o par de vigência e ponha habilitado em true")
    else:
        _falhas_revisao(tabela.get("revisao"), hoje or _dt.date.today(), falhas)
    return falhas




def _negada(texto, pos, neg, corte):
    'True se houver marcador de negação (`neg`) antes de `pos`, na mesma oração.'





    comeco = texto.rfind("\n", 0, pos) + 1
    for fecho in corte.finditer(texto, comeco, pos):
        comeco = fecho.end()
    return bool(neg.search(texto, comeco, pos))


def _recorte(texto, ini, fim, janela):
    """Trecho em volta do termo, preso à linha dele, com reticências onde houve corte."""
    linha_ini = texto.rfind("\n", 0, ini) + 1
    linha_fim = texto.find("\n", fim)
    if linha_fim == -1:
        linha_fim = len(texto)
    de = max(linha_ini, ini - janela)
    ate = min(linha_fim, fim + janela)
    antes = "..." if de > linha_ini else ""
    depois = "..." if ate < linha_fim else ""
    return antes + texto[de:ate].strip() + depois


def _um_por_trecho(candidatos):
    'Um apontamento por trecho de texto. Vence o casamento mais longo; no empate, o que'

    def prioridade(a):
        return (a["inicio"] - a["fim"], -a["exige_rank"], a["expressao_id"])

    ficam = []
    for cand in sorted(candidatos, key=prioridade):
        if all(cand["fim"] <= f["inicio"] or f["fim"] <= cand["inicio"] for f in ficam):
            ficam.append(cand)
    ficam.sort(key=lambda a: a["inicio"])
    return ficam


def _inconclusivo(cobertura, motivos):
    sem_repeticao = list(dict.fromkeys(motivos))
    return {"estado": "inconclusivo", "motivos": sem_repeticao, "schema_version": SCHEMA_VERSION,
            "cobertura": None if not isinstance(cobertura, str) else cobertura}


def calibrar(texto, cobertura, *, tabela=None, janela=JANELA_TRECHO, hoje=None,
             caminho=TABELA_PADRAO, minimo_motivo=MINIMO_MOTIVO_CLASSE,
             minimo_razao=MINIMO_RAZAO_OVERRIDE, contrato=CONTRATO_PADRAO):
    'Aponta as expressões cuja firmeza a cobertura declarada não sustenta.'





    declarada = cobertura.strip() if isinstance(cobertura, str) else ""
    if not declarada:
        return _inconclusivo(cobertura, [MOTIVO_SEM_COBERTURA])
    do_arquivo = tabela is None
    if do_arquivo:
        tabela, problema = carregar_tabela(caminho)
        if problema:
            return _inconclusivo(cobertura, [problema])
    falhas = impedimentos(tabela, hoje or _dt.date.today(), minimo_motivo=minimo_motivo,
                          minimo_razao=minimo_razao, contrato=contrato)
    if falhas:
        return _inconclusivo(cobertura, falhas)
    ranks = {nome: ficha["rank"] for nome, ficha in tabela["coberturas"].items()}
    if declarada not in ranks:
        return _inconclusivo(cobertura, [
            "cobertura declarada «%s» fora do contrato (%s): não há calibração para ela"
            % (declarada, ", ".join(sorted(ranks)))])
    if not isinstance(texto, str):
        return _inconclusivo(cobertura, ["o texto da peça precisa chegar como string"])

    classes = tabela["classes"]
    neg = re.compile(tabela["negacao"]["marcadores"], flags=re.IGNORECASE)
    corte = re.compile(tabela["negacao"]["fim_de_oracao"], flags=re.IGNORECASE)
    isencoes = {}
    for registro in tabela.get("isencoes", []):
        if isinstance(registro, dict):
            chave = (_limpo(registro.get("expressao_id")), _limpo(registro.get("cobertura")))
            isencoes[chave] = registro

    candidatos, aplicadas = [], []
    for expr in tabela["expressoes"]:
        classe = _limpo(expr.get("classe"))
        minima = _limpo(expr.get("exige_cobertura")) or _limpo(classes[classe].get("exige_cobertura"))
        if ranks[minima] <= ranks[declarada]:
            continue
        regex = re.compile(expr["padrao"], flags=re.IGNORECASE)
        achados = [m for m in regex.finditer(texto) if not _negada(texto, m.start(), neg, corte)]
        if not achados:
            continue
        nome = _limpo(expr.get("id"))
        isencao = isencoes.get((nome, declarada))
        if isencao:
            aplicadas.append(dict(
                cobertura=declarada, expressao_id=nome, ocorrencias=len(achados),
                autorizado_por=_limpo(isencao.get("autorizado_por")),
                razao=_limpo(isencao.get("razao"))))
            continue
        explicacao = ("%s; sob a cobertura «%s» a expressão vai além da força da tese, e só "
                      "caberia a partir de «%s»"
                      % (_limpo(classes[classe].get("motivo")), declarada, minima))
        for m in achados:
            candidatos.append(dict(
                classe=classe, expressao_id=nome, termo=m.group(0),
                linha=texto.count("\n", 0, m.start()) + 1, inicio=m.start(), fim=m.end(),
                trecho=_recorte(texto, m.start(), m.end(), janela),
                cobertura_declarada=declarada, exige_cobertura=minima,
                exige_rank=ranks[minima], motivo=explicacao))

    assinatura = tabela.get("revisao") or {}
    return {
        "estado": "calibrado",
        "schema_version": SCHEMA_VERSION,
        "cobertura_rank": ranks[declarada],
        "cobertura": declarada,
        "isencoes_aplicadas": aplicadas,
        "apontamentos": _um_por_trecho(candidatos),
        "tabela": {
            "review_valid_to": assinatura.get("review_valid_to"),
            "revisor": _limpo(assinatura.get("revisor")),
            "caminho": caminho if do_arquivo else None,
        },
    }


class _Campos(dict):
    """Dicionário para format_map: campo ausente sai como None, sem KeyError."""

    def __missing__(self, chave):
        return None


def resumo(resultado, maximo=MAX_RESUMO):
    """Texto curto para o gate. Nunca devolve a peça, alterada ou não."""
    if resultado.get("estado") == "calibrado":
        itens = resultado.get("apontamentos") or []
        partes = ["linha {linha}: «{termo}» ({classe}) {trecho}".format_map(_Campos(a))
                  for a in itens[:maximo]]
        if len(itens) > maximo:
            partes.append("e outros %d apontamento(s)" % (len(itens) - maximo))

        partes += ["ISENÇÃO do advogado: {expressao_id}, autorizada por {autorizado_por}. "
                   "Razão: {razao}".format_map(_Campos(i))
                   for i in resultado.get("isencoes_aplicadas") or []]
        sob = resultado.get("cobertura")
        if partes:
            return ("CALIBRADO, %d apontamento(s) sob a cobertura «%s»:" % (len(itens), sob)
                    + "".join("\n  " + p for p in partes))
        return "CALIBRADO: sob a cobertura «%s», nenhuma expressão vai além da força da tese" % sob
    motivos = resultado.get("motivos") or ["motivo não informado"]
    return "INCONCLUSIVO: " + "; ".join(map(str, motivos))



_FLAGS_DE_LIMIAR = (
    ("--janela-trecho", JANELA_TRECHO,
     "contexto, em caracteres, mostrado em volta do termo apontado"),
    ("--max-resumo", MAX_RESUMO,
     "quantos apontamentos o resumo lista antes de resumir o resto"),
    ("--minimo-razao-override", MINIMO_RAZAO_OVERRIDE,
     "tamanho mínimo da razão de uma isenção; valor menor afrouxa o gate"),
    ("--minimo-motivo-classe", MINIMO_MOTIVO_CLASSE,
     "tamanho mínimo do texto de motivo de cada classe"),
)


def _ler_peca(arquivo):
    """(texto, erro) do arquivo da peça."""
    try:
        with open(arquivo, "r", encoding="utf-8-sig") as fp:
            return fp.read(), None
    except OSError as exc:
        return None, "não consegui ler %s (%s)" % (arquivo, type(exc).__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Aponta, sem reescrever, a firmeza de linguagem que a cobertura de "
                    "precedente declarada não sustenta.")
    parser.add_argument("--cobertura", help="cobertura_precedente declarada no registro dsr.achados.v3")
    parser.add_argument("--arquivo", help="arquivo de texto com a peça (prevalece sobre --texto)")
    parser.add_argument("--texto", help="texto da peça na própria linha de comando")
    parser.add_argument("--tabela", default=TABELA_PADRAO, help="outra tabela no lugar da padrão")
    parser.add_argument("--hoje", help="data de referência AAAA-MM-DD (padrão: hoje)")
    parser.add_argument("--json", dest="como_json", action="store_true",
                        help="imprime o resultado completo em JSON")
    for flag, padrao, ajuda in _FLAGS_DE_LIMIAR:
        parser.add_argument(flag, type=int, default=padrao, help="%s (padrão %d)" % (ajuda, padrao))
    args = parser.parse_args(argv)


    if not args.arquivo and args.texto is None:
        print("peça não informada; informe --arquivo ou --texto")
        return 2
    texto = args.texto or ""
    if args.arquivo:
        texto, problema = _ler_peca(args.arquivo)
        if problema:
            print(problema)
            return 2
    hoje = None
    if args.hoje:
        hoje = _data(args.hoje)
        if hoje is None:
            print("data inválida em --hoje; use AAAA-MM-DD")
            return 2

    resultado = calibrar(texto=texto, cobertura=args.cobertura, caminho=args.tabela, hoje=hoje,
                         janela=args.janela_trecho, minimo_motivo=args.minimo_motivo_classe,
                         minimo_razao=args.minimo_razao_override)
    if args.como_json:
        saida = json.dumps(resultado, indent=2, sort_keys=True, ensure_ascii=False)
    else:
        saida = resumo(resultado, args.max_resumo)
    print(saida)
    if resultado["estado"] == "calibrado":
        return 1 if resultado["apontamentos"] else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
