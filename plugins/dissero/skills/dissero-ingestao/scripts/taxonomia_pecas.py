#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'taxonomia_pecas.py - propoe o tipo de uma peca processual a partir da tabela que o advogado'

















































































from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
TABELA_PADRAO = os.path.join(os.path.dirname(AQUI), "references", "taxonomia-pecas.json")
SCHEMA_VERSION = "dsr.taxonomia_pecas.v1"
VARIAVEL_AMBIENTE = "DSR_TAXONOMIA_PECAS"

CAMPOS_TOPO = ("schema_version", "habilitado", "revisao", "procedencia", "pendencia",
               "dominios", "tipos")
CAMPOS_REVISAO = ("revisor", "papel", "revisado_em", "review_valid_from", "review_valid_to")
CAMPOS_PROCEDENCIA = ("origem", "adaptacao")
CAMPOS_PENDENCIA = ("bloqueada", "motivo", "alerta_rito_penal", "decisoes_do_advogado")
DOMINIOS = ("rito", "fase", "polo", "instancia")
EIXOS = ("fase", "polo", "instancia")
CAMPOS_TIPO_OBRIGATORIOS = ("id", "rotulo", "fase", "polo", "instancia", "ritos", "marcadores")
CAMPOS_TIPO_OPCIONAIS = ("aliases",)
ID_TIPO = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
DATA_ISO = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")




















MINIMO_MARCADORES = 2
MARGEM_MINIMA = 1
LIMITE_EVIDENCIA = 120




MINIMO_MOTIVO_PENDENCIA = 40






PISO_LIMIAR = 1

AVISO_TRANSCRICAO = (
    "LIMITE DECLARADO - texto transcrito conta como texto proprio. A contagem varre o "
    "documento inteiro, sem peso de posicao e sem descontar trecho reproduzido ou citado de "
    "outro documento: um documento que transcreve outro casa tambem os marcadores do "
    "transcrito, e pode perder o placar para ele - levando fase, polo e instancia do tipo "
    "errado. Confira a evidencia em `marcadores_casados` antes de aceitar a proposta."
)

MOTIVO_DESLIGADO = (
    "capacidade desligada: `classificar` exige autorizado=True e a CLI exige %s=1. "
    "Capacidade nova nasce desligada nesta casa." % VARIAVEL_AMBIENTE
)
MOTIVO_SEM_RITO = (
    "rito do documento nao declarado: sem ele nao ha classificacao possivel. Este modulo NAO "
    "infere rito a partir do texto - a abertura e o fecho de uma peca sao iguais em ritos "
    "diferentes, e a taxonomia so cobre os ritos que o advogado revisou. Declare o rito e "
    "chame de novo."
)



def _texto(valor):
    """Texto util, ou string vazia. Nao levanta para tipo errado - quem valida e o validador."""
    return valor.strip() if isinstance(valor, str) else ""


def _data(valor):
    """date ou None. Numero, texto torto e None caem todos em None, sem excecao."""
    if not isinstance(valor, str) or not DATA_ISO.fullmatch(valor.strip()):
        return None
    try:
        return _dt.date.fromisoformat(valor.strip())
    except ValueError:
        return None


def _erro_de_piso(nome, valor, piso=PISO_LIMIAR):
    'Texto do erro, ou None. Limiar arbitrario tem piso - ver PISO_LIMIAR.'




    if isinstance(valor, bool) or not isinstance(valor, int) or valor < piso:
        return ("%s=%r esta abaixo do piso: este limiar e arbitrario, mas exige inteiro >= %d. "
                "Abaixo do piso o modulo deixa de recusar e passa a propor tipo sem evidencia "
                "casada, o que e afirmacao sem prova - nao palpite" % (nome, valor, piso))
    return None


def _erros_de_piso(**limiares):
    """Erros de piso de todos os limiares recebidos, em ordem estavel de nome."""
    return [erro for erro in (_erro_de_piso(nome, valor)
                              for nome, valor in sorted(limiares.items())) if erro]


def _trecho(texto, inicio, fim, limite=LIMITE_EVIDENCIA):
    """Evidencia do casamento, em UMA linha, cortada no limite com reticencias."""
    bruto = " ".join(texto[inicio:fim].split())
    if limite is not None and limite > 0 and len(bruto) > limite:
        return bruto[:limite].rstrip() + "..."
    return bruto



def carregar_tabela(caminho=TABELA_PADRAO):
    """(tabela, erro). Erro nunca vira excecao - tabela ilegivel e impedimento, nao crash."""
    try:
        with open(caminho, encoding="utf-8-sig") as arquivo:
            tabela = json.load(arquivo)
    except OSError as erro:
        return None, "tabela nao pode ser lida (%s)" % erro.__class__.__name__
    except UnicodeDecodeError:
        return None, "tabela nao e texto UTF-8"
    except ValueError as erro:
        return None, "tabela nao e JSON valido (%s)" % erro
    if not isinstance(tabela, dict):
        return None, "tabela deve ser um objeto JSON"
    return tabela, None



def _checar_topo(tabela, erros):
    if _texto(tabela.get("schema_version")) != SCHEMA_VERSION:
        erros.append("schema_version deve ser %s" % SCHEMA_VERSION)
    for campo in tabela:
        if campo not in CAMPOS_TOPO and not campo.startswith("_"):
            erros.append("campo de topo desconhecido: %s" % campo)
    if tabela.get("habilitado") is not True:
        erros.append("habilitado=false. Capacidade nova nasce desligada; ligar exige resolver "
                     "a pendencia, preencher tipos e a revisao, e so entao virar para true")


def _checar_revisao(tabela, hoje, erros):
    revisao = tabela.get("revisao")
    if not isinstance(revisao, dict):
        erros.append("revisao ausente ou nao e objeto")
        return
    faltando = [c for c in CAMPOS_REVISAO if revisao.get(c) in (None, "")]
    if faltando:
        erros.append("revisao incompleta: falta " + ", ".join(faltando))
        return
    if not _texto(revisao.get("revisor")):
        erros.append("revisao exige revisor identificado")
    if _texto(revisao.get("papel")).lower() != "advogado":
        erros.append("revisao exige papel 'advogado'")
    revisado = _data(revisao.get("revisado_em"))
    desde = _data(revisao.get("review_valid_from"))
    ate = _data(revisao.get("review_valid_to"))
    if revisado is None or revisado > hoje:
        erros.append("revisado_em ausente, ilegivel ou futuro")
    if desde is None or ate is None:
        erros.append("par review_valid_from/review_valid_to ilegivel")
    elif desde > ate:
        erros.append("vigencia da revisao com inicio posterior ao fim")
    elif not desde <= hoje <= ate:
        erros.append("vigencia da revisao da tabela fora de prazo em %s" % hoje.isoformat())


def _checar_procedencia(tabela, erros):
    proc = tabela.get("procedencia")
    if not isinstance(proc, dict):
        erros.append("procedencia ausente ou nao e objeto")
        return
    for campo in CAMPOS_PROCEDENCIA:
        if not _texto(proc.get(campo)):
            erros.append("procedencia.%s ausente ou vazia" % campo)


def _checar_pendencia(tabela, erros, minimo_motivo=MINIMO_MOTIVO_PENDENCIA):
    'A pendencia e o que torna a recusa LEGIVEL. Bloco ausente seria recusa muda.'






    pend = tabela.get("pendencia")
    if not isinstance(pend, dict):
        erros.append("pendencia ausente ou nao e objeto: sem ela a recusa do modulo nao explica "
                     "ao advogado o que falta decidir")
        return
    faltando = [c for c in CAMPOS_PENDENCIA if c not in pend]
    if faltando:
        erros.append("pendencia incompleta: falta " + ", ".join(faltando))
        return
    if not isinstance(pend.get("bloqueada"), bool):
        erros.append("pendencia.bloqueada deve ser booleano")
    if len(_texto(pend.get("motivo"))) < minimo_motivo:
        erros.append("pendencia.motivo precisa de %d+ caracteres" % minimo_motivo)
    if len(_texto(pend.get("alerta_rito_penal"))) < minimo_motivo:
        erros.append("pendencia.alerta_rito_penal precisa de %d+ caracteres" % minimo_motivo)
    if not isinstance(pend.get("decisoes_do_advogado"), list):
        erros.append("pendencia.decisoes_do_advogado deve ser lista")
    if pend.get("bloqueada") is True:
        erros.append("taxonomia BLOQUEADA por decisao juridica pendente (pendencia.bloqueada="
                     "true): %s" % _texto(pend.get("motivo")))


def _checar_dominios(tabela, erros):
    """(dominios_normalizados). Dominio e vocabulario fechado: valor fora dele reprova o tipo."""
    dominios = {nome: set() for nome in DOMINIOS}
    bruto = tabela.get("dominios")
    if not isinstance(bruto, dict):
        erros.append("dominios ausente ou nao e objeto")
        return dominios
    for campo in bruto:
        if campo not in DOMINIOS and not campo.startswith("_"):
            erros.append("dominios contem eixo desconhecido: %s" % campo)
    for nome in DOMINIOS:
        valores = bruto.get(nome)
        if not isinstance(valores, list):
            erros.append("dominios.%s ausente ou nao e lista" % nome)
            continue
        vistos = set()
        for i, valor in enumerate(valores):
            limpo = _texto(valor)
            if not limpo:
                erros.append("dominios.%s[%d] nao e texto util" % (nome, i))
                continue
            if limpo in vistos:
                erros.append("dominios.%s repete o valor '%s'" % (nome, limpo))
                continue
            vistos.add(limpo)
        dominios[nome] = vistos
    return dominios


def _checar_tipo(item, onde, dominios, ids, aliases_vistos, erros):
    if not isinstance(item, dict):
        erros.append("%s nao e objeto" % onde)
        return
    for campo in item:
        if (campo not in CAMPOS_TIPO_OBRIGATORIOS and campo not in CAMPOS_TIPO_OPCIONAIS
                and not campo.startswith("_")):
            erros.append("%s tem campo desconhecido: %s" % (onde, campo))
    faltando = [c for c in CAMPOS_TIPO_OBRIGATORIOS if c not in item]
    if faltando:
        erros.append("%s incompleto: falta %s" % (onde, ", ".join(faltando)))
        return

    ident = _texto(item.get("id"))
    if not ID_TIPO.fullmatch(ident):
        erros.append("%s.id invalido (minusculas, digitos e _; ate 64)" % onde)
    elif ident in ids:
        erros.append("%s.id duplicado: '%s' ja foi declarado" % (onde, ident))
    else:
        ids.add(ident)

    if not _texto(item.get("rotulo")):
        erros.append("%s.rotulo ausente ou vazio" % onde)

    for eixo in EIXOS:
        valor = _texto(item.get(eixo))
        if not valor:
            erros.append("%s.%s ausente ou vazio" % (onde, eixo))
        elif valor not in dominios[eixo]:
            erros.append("%s.%s='%s' fora de dominios.%s" % (onde, eixo, valor, eixo))

    ritos = item.get("ritos")
    if not isinstance(ritos, list) or not ritos:
        erros.append("%s.ritos deve ser lista nao vazia: tipo sem cobertura de rito declarada "
                     "e exatamente o que a pendencia existe para impedir" % onde)
    else:
        for i, rito in enumerate(ritos):
            limpo = _texto(rito)
            if not limpo:
                erros.append("%s.ritos[%d] nao e texto util" % (onde, i))
            elif limpo not in dominios["rito"]:
                erros.append("%s.ritos[%d]='%s' fora de dominios.rito" % (onde, i, limpo))

    marcadores = item.get("marcadores")
    if not isinstance(marcadores, list) or not marcadores:
        erros.append("%s.marcadores deve ser lista nao vazia: tipo sem marcador nunca casa e "
                     "so serve para produzir empate" % onde)
    else:
        for i, padrao in enumerate(marcadores):
            if not isinstance(padrao, str) or not padrao.strip():
                erros.append("%s.marcadores[%d] nao e texto util" % (onde, i))
                continue
            try:
                re.compile(padrao, re.I)
            except re.error as erro:
                erros.append("%s.marcadores[%d] nao compila (%s)" % (onde, i, erro))

    aliases = item.get("aliases", [])
    if not isinstance(aliases, list):
        erros.append("%s.aliases deve ser lista" % onde)
    else:
        for i, alias in enumerate(aliases):
            limpo = _texto(alias).lower()
            if not limpo:
                erros.append("%s.aliases[%d] nao e texto util" % (onde, i))
            elif limpo in aliases_vistos:
                erros.append("%s.aliases[%d]='%s' ja pertence ao tipo '%s'"
                             % (onde, i, limpo, aliases_vistos[limpo]))
            else:
                aliases_vistos[limpo] = ident or onde


def impedimentos(tabela, hoje=None, minimo_motivo=MINIMO_MOTIVO_PENDENCIA):
    'Tudo que impede USAR esta tabela agora. Lista vazia = tabela utilizavel.'










    hoje = hoje or _dt.date.today()
    piso = _erro_de_piso("minimo_motivo", minimo_motivo)
    if piso:
        return [piso]
    erros = []
    if not isinstance(tabela, dict):
        return ["tabela deve ser um objeto JSON"]
    _checar_topo(tabela, erros)
    _checar_revisao(tabela, hoje, erros)
    _checar_procedencia(tabela, erros)
    _checar_pendencia(tabela, erros, minimo_motivo=minimo_motivo)
    dominios = _checar_dominios(tabela, erros)

    tipos = tabela.get("tipos")
    if not isinstance(tipos, list):
        erros.append("tipos ausente ou nao e lista")
        return erros
    if not tipos:
        erros.append("tabela de tipos VAZIA: nenhuma peca pode ser classificada. Escolher os "
                     "tipos e juizo juridico do advogado; leia o bloco `pendencia` da tabela")
        return erros
    ids, aliases_vistos = set(), {}
    for i, item in enumerate(tipos):
        _checar_tipo(item, "tipos[%d]" % i, dominios, ids, aliases_vistos, erros)
    return erros



def _casamentos(texto, tipo, limite_evidencia):
    'Marcadores DISTINTOS que casam, com a evidencia do primeiro casamento de cada um.'




    casados = []
    for padrao in tipo.get("marcadores", []):
        try:
            achado = re.compile(padrao, re.I).search(texto)
        except re.error:
            continue
        if achado:
            casados.append({"padrao": padrao,
                            "trecho": _trecho(texto, achado.start(), achado.end(),
                                              limite_evidencia)})
    return casados


def _aliases_casados(texto, tipo):
    'Aliases sao REGISTRADOS, nao pontuados.'




    baixo = texto.lower()
    return [a for a in tipo.get("aliases", []) if isinstance(a, str) and a.strip()
            and a.strip().lower() in baixo]


def classificar(texto, rito=None, tabela=None, caminho=TABELA_PADRAO, hoje=None,
                autorizado=False, minimo_marcadores=MINIMO_MARCADORES,
                margem_minima=MARGEM_MINIMA, limite_evidencia=LIMITE_EVIDENCIA,
                minimo_motivo=MINIMO_MOTIVO_PENDENCIA):
    'Propoe o tipo de peca de UM texto, ou recusa dizendo por que.'









    hoje = hoje or _dt.date.today()
    saida = {"schema_version": SCHEMA_VERSION, "rito_declarado": rito if isinstance(rito, str)
             else None}

    def inconclusivo(motivos):
        resultado = dict(saida)
        resultado["estado"] = "inconclusivo"
        resultado["motivos"] = list(motivos)
        return resultado

    if autorizado is not True:
        return inconclusivo([MOTIVO_DESLIGADO])

    pisos = _erros_de_piso(minimo_marcadores=minimo_marcadores,
                           margem_minima=margem_minima,
                           limite_evidencia=limite_evidencia,
                           minimo_motivo=minimo_motivo)
    if pisos:
        return inconclusivo(pisos)

    if tabela is None:
        tabela, erro = carregar_tabela(caminho)
        if erro:
            return inconclusivo([erro])

    erros = impedimentos(tabela, hoje=hoje, minimo_motivo=minimo_motivo)
    if erros:
        return inconclusivo(erros)

    if not isinstance(texto, str):
        return inconclusivo(["texto do documento deve ser string"])

    limpo_rito = _texto(rito)
    if not limpo_rito:
        return inconclusivo([MOTIVO_SEM_RITO])

    ritos_cobertos = set()
    for item in tabela.get("tipos", []):
        for r in item.get("ritos", []):
            if _texto(r):
                ritos_cobertos.add(_texto(r))
    if limpo_rito not in ritos_cobertos:
        return inconclusivo([
            "rito '%s' nao esta coberto por nenhum tipo revisado desta taxonomia (cobertos: "
            "%s). O modulo recusa em vez de emprestar o vocabulario de outro rito - e a "
            "protecao que existe para o rito penal." % (limpo_rito,
                                                        ", ".join(sorted(ritos_cobertos)) or "nenhum")])

    candidatos = []
    for item in tabela["tipos"]:
        if limpo_rito not in [_texto(r) for r in item.get("ritos", [])]:
            continue
        casados = _casamentos(texto, item, limite_evidencia)
        candidatos.append({"id": _texto(item.get("id")), "rotulo": _texto(item.get("rotulo")),
                           "casados": len(casados), "marcadores_casados": casados,
                           "aliases_casados": _aliases_casados(texto, item),
                           "_item": item})
    candidatos.sort(key=lambda c: (-c["casados"], c["id"]))
    placar = [{"id": c["id"], "casados": c["casados"]} for c in candidatos]

    if not candidatos:
        return inconclusivo(["nenhum tipo desta taxonomia cobre o rito '%s'" % limpo_rito])

    melhor = candidatos[0]
    if melhor["casados"] < minimo_marcadores:
        resultado = inconclusivo([
            "nenhum tipo alcancou o minimo de %d marcadores distintos (melhor: '%s' com %d)"
            % (minimo_marcadores, melhor["id"], melhor["casados"])])
        resultado["placar"] = placar
        return resultado

    segundo = candidatos[1]["casados"] if len(candidatos) > 1 else -1
    if melhor["casados"] - segundo < margem_minima:
        empatados = [c["id"] for c in candidatos if c["casados"] == melhor["casados"]]
        resultado = inconclusivo([
            "empate: %s casaram %d marcadores e a margem minima e %d. Empate nao vira palpite"
            % (", ".join(sorted(empatados)), melhor["casados"], margem_minima)])
        resultado["placar"] = placar
        return resultado

    item = melhor["_item"]
    resultado = dict(saida)
    resultado["estado"] = "a_confirmar"
    resultado["tipo_proposto"] = {
        "id": melhor["id"], "rotulo": melhor["rotulo"],
        "fase": _texto(item.get("fase")), "polo": _texto(item.get("polo")),
        "instancia": _texto(item.get("instancia")),
    }
    resultado["marcadores_casados"] = melhor["marcadores_casados"]
    resultado["aliases_casados"] = melhor["aliases_casados"]
    resultado["placar"] = placar
    resultado["avisos"] = [
        "MINUTA_PARA_REVISAO: proposta de tipo, nao classificacao. Conferencia do advogado "
        "e obrigatoria - `a_confirmar` e o melhor estado que este modulo sabe produzir.",
        "A proposta vale apenas para o rito declarado ('%s'); o modulo nao conferiu o rito."
        % limpo_rito,
        AVISO_TRANSCRICAO,
    ]



    concorrentes = [c["id"] for c in candidatos[1:] if c["casados"] > 0]
    if concorrentes:
        resultado["avisos"].append(
            "outro(s) tipo(s) tambem casaram marcadores neste mesmo documento (%s). Se o "
            "documento reproduz outro dentro de si, confira de quem sao os marcadores casados "
            "antes de aceitar a proposta." % ", ".join(concorrentes))
    return resultado


def classificar_lote(itens, caminho=TABELA_PADRAO, tabela=None, hoje=None, autorizado=False,
                     minimo_marcadores=MINIMO_MARCADORES, margem_minima=MARGEM_MINIMA,
                     limite_evidencia=LIMITE_EVIDENCIA,
                     minimo_motivo=MINIMO_MOTIVO_PENDENCIA):
    'Classifica varios documentos com UMA leitura e UMA validacao da tabela.'













    hoje = hoje or _dt.date.today()
    pisos = _erros_de_piso(minimo_marcadores=minimo_marcadores,
                           margem_minima=margem_minima,
                           limite_evidencia=limite_evidencia,
                           minimo_motivo=minimo_motivo)
    if tabela is None:
        tabela, erro = carregar_tabela(caminho)
        if erro:
            tabela = None
    else:
        erro = None
    erros = [erro] if erro else (impedimentos(tabela, hoje=hoje, minimo_motivo=minimo_motivo)
                                 if tabela is not None else ["tabela ausente"])
    if autorizado is not True:
        erros = [MOTIVO_DESLIGADO]
    elif pisos:
        erros = pisos

    resultados = []
    for i, item in enumerate(itens if isinstance(itens, list) else []):
        ref = (item.get("ref") if isinstance(item, dict) else None)
        if ref is None:
            ref = i
        if erros:
            resultados.append({"ref": ref, "schema_version": SCHEMA_VERSION,
                               "rito_declarado": (item.get("rito") if isinstance(item, dict)
                                                  else None),
                               "estado": "inconclusivo", "motivos": list(erros)})
            continue
        um = classificar(item.get("texto"), rito=item.get("rito"), tabela=tabela, hoje=hoje,
                         autorizado=True, minimo_marcadores=minimo_marcadores,
                         margem_minima=margem_minima, limite_evidencia=limite_evidencia,
                         minimo_motivo=minimo_motivo)
        um["ref"] = ref
        resultados.append(um)

    return {"schema_version": SCHEMA_VERSION,
            "tabela_utilizavel": not erros,
            "impedimentos": list(erros),
            "resultados": resultados}



def resumo(resultado):
    """Uma linha para quem roda na mao."""
    if not isinstance(resultado, dict):
        return "INCONCLUSIVO - resultado malformado"
    if resultado.get("estado") != "a_confirmar":
        motivos = resultado.get("motivos") or ["motivo nao declarado"]
        return "INCONCLUSIVO - " + "; ".join(str(m) for m in motivos)
    tipo = resultado.get("tipo_proposto") or {}
    return ("A CONFIRMAR - proposta: %s (%s) | %d marcadores | fase=%s polo=%s instancia=%s"
            % (tipo.get("rotulo", "?"), tipo.get("id", "?"),
               len(resultado.get("marcadores_casados") or []),
               tipo.get("fase", "?"), tipo.get("polo", "?"), tipo.get("instancia", "?")))



def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Propoe o tipo de uma peca processual a partir da taxonomia revisada. "
                    "Sem tabela utilizavel, rito declarado e %s=1, a resposta e "
                    "INCONCLUSIVO." % VARIAVEL_AMBIENTE)
    ap.add_argument("--validar", action="store_true",
                    help="so valida a tabela e lista os impedimentos (nao exige %s)"
                         % VARIAVEL_AMBIENTE)
    ap.add_argument("--rito", help="rito processual DECLARADO do documento (obrigatorio para "
                                   "classificar; o rito nao e inferido do texto)")
    ap.add_argument("--texto", help="texto do documento, literal")
    ap.add_argument("--arquivo", help="arquivo .txt/.md com o texto do documento")
    ap.add_argument("--tabela", default=TABELA_PADRAO, help="tabela de taxonomia")
    ap.add_argument("--hoje", help="relogio injetado AAAA-MM-DD")
    ap.add_argument("--json", action="store_true", dest="como_json", help="saida estruturada")


    ap.add_argument("--minimo-marcadores", type=int, default=MINIMO_MARCADORES,
                    help="marcadores distintos exigidos do vencedor (padrao %d, minimo %d); "
                         "baixar transforma recusa honesta em palpite"
                         % (MINIMO_MARCADORES, PISO_LIMIAR))
    ap.add_argument("--margem-minima", type=int, default=MARGEM_MINIMA,
                    help="vantagem exigida sobre o segundo colocado (padrao %d, minimo %d)"
                         % (MARGEM_MINIMA, PISO_LIMIAR))
    ap.add_argument("--limite-evidencia", type=int, default=LIMITE_EVIDENCIA,
                    help="caracteres do trecho de evidencia (padrao %d, minimo %d)"
                         % (LIMITE_EVIDENCIA, PISO_LIMIAR))
    ap.add_argument("--minimo-motivo-pendencia", type=int, default=MINIMO_MOTIVO_PENDENCIA,
                    help="caracteres minimos dos textos da pendencia (padrao %d, minimo %d)"
                         % (MINIMO_MOTIVO_PENDENCIA, PISO_LIMIAR))
    args = ap.parse_args(argv)

    hoje = _data(args.hoje) if args.hoje else None
    if args.hoje and hoje is None:
        print("--hoje deve ser AAAA-MM-DD")
        return 2




    pisos = _erros_de_piso(limite_evidencia=args.limite_evidencia,
                           margem_minima=args.margem_minima,
                           minimo_marcadores=args.minimo_marcadores,
                           minimo_motivo=args.minimo_motivo_pendencia)
    if pisos:
        for aviso in pisos:
            print(aviso)
        return 2

    tabela, erro = carregar_tabela(args.tabela)
    if erro:
        print(json.dumps({"estado": "inconclusivo", "motivos": [erro]}, ensure_ascii=False)
              if args.como_json else "INCONCLUSIVO - " + erro)
        return 2

    if args.validar:
        erros = impedimentos(tabela, hoje=hoje, minimo_motivo=args.minimo_motivo_pendencia)
        tipos = tabela.get("tipos") or []
        ritos = sorted({r for tp in tipos for r in (tp.get("ritos") or [])})
        if args.como_json:
            print(json.dumps({"tabela_utilizavel": not erros, "impedimentos": erros,
                              "tipos": len(tipos), "ritos": ritos,
                              "habilitado": bool(tabela.get("habilitado"))},
                             ensure_ascii=False, indent=2, sort_keys=True))
        elif erros:
            print("TABELA INUTILIZAVEL - %d impedimento(s):" % len(erros))
            for e in erros:
                print("  - %s" % e)
        else:
            print("TABELA UTILIZAVEL - nenhum impedimento.")
            print("  tipos: %d | ritos: %s | habilitado: %s"
                  % (len(tipos), ", ".join(ritos) or "(nenhum)",
                     "sim" if tabela.get("habilitado") else "nao"))
        return 2 if erros else 0


    autorizado = os.environ.get(VARIAVEL_AMBIENTE, "").strip() == "1"

    texto = args.texto
    if args.arquivo:
        try:
            with open(args.arquivo, encoding="utf-8-sig") as arquivo:
                texto = arquivo.read()
        except OSError as erro_io:
            print("nao foi possivel ler %s (%s)" % (args.arquivo, erro_io.__class__.__name__))
            return 2
    if texto is None:
        texto = ""

    resultado = classificar(texto, rito=args.rito, tabela=tabela, hoje=hoje,
                            autorizado=autorizado,
                            minimo_marcadores=args.minimo_marcadores,
                            margem_minima=args.margem_minima,
                            limite_evidencia=args.limite_evidencia,
                            minimo_motivo=args.minimo_motivo_pendencia)
    if args.como_json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(resumo(resultado))
    return 0 if resultado.get("estado") == "a_confirmar" else 2


if __name__ == "__main__":
    sys.exit(main())
