#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'squad.py - Executor deterministico de squads juridicos Dissero.'







































































import argparse
import json
import os
import shutil
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(os.path.dirname(AQUI), "references")


INDICE_ROTEAMENTO = os.path.join(AQUI, "roteamento_areas.json")


def _roteiros_conhecidos():
    """Os caminhos de roteiro (`acervo/...`) listados no indice; vazio se o indice faltar."""
    try:
        with open(INDICE_ROTEAMENTO, encoding="utf-8") as f:
            roteiros = json.load(f).get("roteiros")
    except (OSError, ValueError, AttributeError):
        return frozenset()
    return frozenset(r for r in roteiros if isinstance(r, str)) if isinstance(roteiros, list) else frozenset()
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass



try:
    import caso_raiz
except Exception:
    caso_raiz = None
try:
    from schema_mini import validar_schema
except Exception:
    validar_schema = None




try:
    import planejar_turma
except Exception:
    planejar_turma = None
try:
    from aval_subagentes import ler_aval
except Exception:
    ler_aval = None

ETAPAS = (
    "foco", "memoria", "pesquisa", "estrategia", "redacao",
    "minuta", "revisao", "final", "checklist_externo",
)
STATUS = ("planejada", "em_execucao", "concluida", "aguardando_aprovacao", "bloqueada")



AREAS = (
    "administrativo-licitacoes", "advocacia-publica", "aeronautico", "agrario", "ambiental",
    "bancario", "civel", "consumidor", "criminal", "desportivo", "digital-lgpd", "eleitoral",
    "empresarial-recuperacao", "etica-oab", "execucao-cobranca", "familia-sucessoes",
    "imobiliario", "internacional-imigracao", "leiloes", "medico-saude", "militar",
    "notarial-registral", "previdenciario", "propriedade-intelectual",
    "recursos-tribunais-superiores", "seguros", "trabalhista", "transito",
    "tributario-societario", "geral",
)
SQUAD_RESIDUAL = "peca-civel-contencioso"
ROTAS = ("local", "remota")
POLOS = ("defesa", "autor", "reu", "reclamante", "reclamado", "assistente", "terceiro")
SENSIBILIDADES = ("publico", "restrito", "sigiloso")
POLITICAS = ("local", "hibrida")
CHECKPOINTS_PADRAO = ("foco", "estrategia", "minuta", "final")




MODELOS_OFICIO = ("opus", "sonnet", "haiku")
CAMADAS_OFICIO = ("leitor", "especialista")
MAX_CICLOS_PADRAO = 3
SCHEMA_ESTADO = os.path.join(REFS, "squad_state.schema.json")
CATALOGO_SQUADS = os.path.join(REFS, "squads.json")



NOME_TURMA_PLANO = "TURMA_PLANO.json"



EVIDENCIA_EXIGIDA = {
    "foco": ("briefing", "foco exige evidencia do briefing completo"),
    "memoria": ("conferencia_documental",
                "memoria exige CONFERENCIA.json ou evidencia documental equivalente"),
    "pesquisa": ("relacao_precedentes",
                 "pesquisa exige Relacao de Precedentes/achados verificados"),
    "estrategia": ("estrategia", "estrategia exige o documento de estrategia da peca"),
    "redacao": ("minuta", "redacao exige referencia da minuta produzida"),
    "minuta": ("minuta", "minuta exige a referencia da minuta consolidada"),
    "revisao": ("revisao_independente", "revisao exige resultado de revisao independente"),
    "final": ("lint", "final exige o resultado do LINT sobre a peca"),
    "checklist_externo": ("peca_state", "checklist externo exige referencia ao PECA_STATE.json"),
}


class Contrato(Exception):
    """Uso/contrato invalido -> exit 2."""


def _str(valor):
    return isinstance(valor, str) and bool(valor.strip())


def _int(valor):
    return isinstance(valor, int) and not isinstance(valor, bool)


def _agora():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _out(resultado, estado, motivos=(), code=0, **extra):
    saida = {
        "ok": code == 0,
        "resultado": resultado,
        "etapa_atual": estado.get("etapa_atual") if isinstance(estado, dict) else None,
        "motivos": list(motivos),
    }
    saida.update(extra)
    print(json.dumps(saida, ensure_ascii=False))
    return code


def _ler_json(path, rotulo):
    try:
        with open(path, encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except Exception as exc:
        raise Contrato(["%s ilegivel/JSON invalido: %s" % (rotulo, exc)])


def _gravar(path, valor):
    'Gravacao ATOMICA: escreve ao lado e substitui. Interrupcao no meio deixaria um'


    destino = os.path.abspath(path)
    pasta = os.path.dirname(destino) or "."
    try:
        os.makedirs(pasta, exist_ok=True)
        temporario = destino + ".parcial"
        with open(temporario, "w", encoding="utf-8") as arquivo:
            json.dump(valor, arquivo, ensure_ascii=False, indent=2)
        os.replace(temporario, destino)
    except OSError as exc:
        raise Contrato(["nao foi possivel gravar %s: %s" % (destino, exc)])




def raiz_do_caso(args=None):
    session = getattr(args, "session_id", None) if args else None
    if caso_raiz is None:
        return os.getcwd()
    try:
        raiz, _ = caso_raiz.resolver(session_id=session)
        return raiz
    except Exception:
        return os.getcwd()


def caminho_estado(args):
    """`--state` explicito vence; sem ele, a RAIZ DO CASO - nunca o cwd cru."""
    if _str(getattr(args, "state", None)):
        return os.path.abspath(args.state)
    return os.path.join(raiz_do_caso(args), "SQUAD_STATE.json")


def pasta_do_caso(estado_path):
    'A pasta do caso que ESTE comando esta tratando: a que guarda o SQUAD_STATE.'





    return os.path.dirname(os.path.abspath(estado_path)) or "."


def _resolver_ref(ref, args):
    'Referencia de evidencia: absoluta fica; relativa resolve contra a pasta do caso deste'


    if os.path.isabs(ref):
        return ref
    return os.path.join(pasta_do_caso(caminho_estado(args)), ref)




def _validar_catalogo(bruto):
    if not isinstance(bruto, dict) or not isinstance(bruto.get("squads"), list):
        raise Contrato(["catalogo deve ser objeto com a lista `squads`"])
    if bruto.get("schema") != "dsr.squad.catalogo.v1":
        raise Contrato(["catalogo com schema %r desconhecido (esperado dsr.squad.catalogo.v1)"
                        % bruto.get("schema")])
    ids = [item.get("id") for item in bruto["squads"] if isinstance(item, dict)]
    repetidos = sorted({i for i in ids if ids.count(i) > 1 and i})
    if repetidos:
        raise Contrato(["catalogo tem id duplicado: %s - `--squad` casaria o primeiro em "
                        "silencio" % ", ".join(repetidos)])
    return bruto


def _erros_de_oficios(oficios):
    'A turma declarada no catalogo, conferida na FORMA - nunca no merito.'








    if not isinstance(oficios, list) or not oficios:
        return ["definicao.oficios deve ser lista nao-vazia: squad sem oficios e turma que nao "
                "existe, e o plano da turma nao teria a quem atribuir fatia"]
    erros = []
    for indice, oficio in enumerate(oficios):
        rotulo = "definicao.oficios[%d]" % indice
        if not isinstance(oficio, dict):
            erros.append("%s deve ser objeto JSON" % rotulo)
            continue
        for campo in ("id", "titulo"):
            if not _str(oficio.get(campo)):
                erros.append("%s.%s obrigatorio e nao-vazio" % (rotulo, campo))
        if oficio.get("model") not in MODELOS_OFICIO:
            erros.append("%s.model deve ser um de %s - modelo por assento NUNCA e herdado por "
                         "omissao" % (rotulo, MODELOS_OFICIO))
        if oficio.get("camada") not in CAMADAS_OFICIO:
            erros.append("%s.camada deve ser um de %s - assento de camada desconhecida nao se "
                         "sabe se le a fatia ou se opina sobre ela" % (rotulo, CAMADAS_OFICIO))


        roteiros = oficio.get("roteiros")
        if roteiros is not None:
            if not isinstance(roteiros, list) or not all(_str(r) for r in roteiros):
                erros.append("%s.roteiros deve ser lista de caminhos nao-vazios" % rotulo)
            elif oficio.get("camada") != "especialista":
                erros.append("%s.roteiros so cabe em especialista: o leitor de fatia extrai, "
                             "nao redige" % rotulo)



    ids = [o.get("id") for o in oficios if isinstance(o, dict)]
    repetidos = sorted({i for i in ids if ids.count(i) > 1 and i})
    if repetidos:
        erros.append("definicao.oficios tem id duplicado: %s - o segundo assento sumiria em "
                     "silencio" % ", ".join(repetidos))
    return erros


def _oficios_para_o_plano(estado):
    'A turma deste caso, e de onde ela veio. Devolve (oficios, avisos).'









    oficios = estado.get("oficios")
    if isinstance(oficios, list) and oficios:
        return oficios, []
    bruto = _validar_catalogo(_ler_json(CATALOGO_SQUADS, "catalogo de squads"))
    achado = next((i for i in bruto["squads"] if i.get("id") == estado.get("squad")), None)
    if achado is None:
        raise Contrato(["o estado nao traz `oficios` e o squad %r nao esta no catalogo %s - sem "
                        "a turma declarada nao ha a quem atribuir fatia"
                        % (estado.get("squad"), CATALOGO_SQUADS)])
    erros = _erros_de_oficios(achado.get("oficios"))
    if erros:
        raise Contrato(erros)
    return achado["oficios"], [
        "a turma veio do CATALOGO agora (%s), e nao do estado: o estado deste caso nao traz "
        "`oficios`. Se o catalogo mudou desde a abertura, o plano reflete a mudanca"
        % CATALOGO_SQUADS]


def _validar_definicao(definicao):
    erros = []
    if not isinstance(definicao, dict):
        raise Contrato(["definicao do squad deve ser objeto JSON"])
    for campo in ("id", "titulo", "area", "tipo_entrega", "etapas"):
        if campo not in definicao:
            erros.append("definicao.%s obrigatorio" % campo)
    if definicao.get("area") not in AREAS:
        erros.append("definicao.area deve ser um de %s" % (AREAS,))
    etapas = definicao.get("etapas")
    if not isinstance(etapas, list) or not etapas:
        erros.append("definicao.etapas deve ser lista nao-vazia")
    elif tuple(etapas) != ETAPAS:
        erros.append("definicao.etapas deve usar a sequencia canonica do squad de peca")
    checkpoints = definicao.get("checkpoints", list(CHECKPOINTS_PADRAO))
    if not isinstance(checkpoints, list) or any(item not in ETAPAS for item in checkpoints):
        erros.append("definicao.checkpoints deve ser lista de etapas validas")
    erros.extend(_erros_de_oficios(definicao.get("oficios")))





    conhecidos = _roteiros_conhecidos()
    for oficio in definicao.get("oficios") or []:
        if isinstance(oficio, dict) and isinstance(oficio.get("roteiros"), list):
            for roteiro in oficio["roteiros"]:
                if (_str(roteiro) and roteiro not in conhecidos
                        and not os.path.isfile(os.path.join(REFS, roteiro))):
                    erros.append("roteiro %s do oficio %s nao existe no acervo (nem no indice %s, nem em %s)"
                                 % (roteiro, oficio.get("id"), os.path.basename(INDICE_ROTEAMENTO), REFS))
    if erros:
        raise Contrato(erros)
    return definicao


def squad_da_area(area, catalogo=None):
    'O squad da area. Devolve (id, None) ou (None, motivo que diz o que fazer).'



    bruto = _validar_catalogo(_ler_json(catalogo or CATALOGO_SQUADS, "catalogo de squads"))
    achados = [s for s in bruto["squads"] if isinstance(s, dict) and s.get("area") == area]
    if len(achados) == 1:
        return achados[0]["id"], None
    validos = ", ".join(sorted(str(s.get("id")) for s in bruto["squads"] if isinstance(s, dict)))
    if len(achados) > 1:
        return None, ("a area '%s' tem mais de um squad no catalogo (%s): escolha com --squad <id>"
                      % (area, ", ".join(s["id"] for s in achados)))
    return None, (
        "a area '%s' nao tem equipe no catalogo de squads, e o squad e obrigatorio na peca. Como "
        "seguir: (1) abra o squad da area mais proxima com --squad <id> (o civel, %s, e o "
        "residual); ou (2) se esta peca nao deve passar pela turma, declare a dispensa no "
        "nascimento dela: estado_peca.py init ... --sem-squad \"<motivo>\". Squads disponiveis: %s"
        % (area, SQUAD_RESIDUAL, validos))


def _validar_contra_schema(estado):
    """O schema publicado E o contrato. Sem o validador ao lado, o motor DIZ que esta sem ele."""
    if validar_schema is None:
        return ["schema_mini.py indisponivel ao lado do modulo - sem validador o contrato "
                "publicado nao e conferido; corrija a instalacao antes de confiar no estado"]
    try:
        schema = _ler_json(SCHEMA_ESTADO, "squad_state.schema.json")
    except Contrato as exc:
        return list(exc.args[0])
    try:
        problemas = validar_schema(estado, schema)
    except Exception as exc:
        return ["schema nao pode ser aplicado: %s" % exc]
    return [str(p) for p in (problemas or [])]


def _validar_estado(estado):
    if not isinstance(estado, dict):
        raise Contrato(["SQUAD_STATE deve ser objeto JSON"])
    erros = list(_validar_contra_schema(estado))
    for campo in ("squad", "objetivo", "area", "polo", "etapa_atual", "ciclo", "etapas",
                  "documentos", "retornos", "politica_dados", "max_ciclos", "checkpoints"):
        if campo not in estado:
            erros.append("estado.%s obrigatorio" % campo)
    if estado.get("area") not in AREAS:
        erros.append("estado.area deve ser um de %s" % (AREAS,))
    if estado.get("etapa_atual") not in ETAPAS:
        erros.append("estado.etapa_atual invalida")
    if estado.get("politica_dados") not in POLITICAS:
        erros.append("estado.politica_dados deve ser local ou hibrida - ausente, um squad "
                     "declarado LOCAL passaria a aceitar rota remota em silencio")
    if not _int(estado.get("max_ciclos")) or estado.get("max_ciclos", 0) < 1:
        erros.append("estado.max_ciclos deve ser inteiro >= 1 e vive no ESTADO, nao no argumento")
    checkpoints = estado.get("checkpoints")
    if not isinstance(checkpoints, list) or any(c not in ETAPAS for c in checkpoints or []):
        erros.append("estado.checkpoints deve ser lista de etapas validas")
    if not _int(estado.get("ciclo")) or estado.get("ciclo", 0) < 1:
        erros.append("estado.ciclo deve ser inteiro >= 1")
    if not isinstance(estado.get("retornos"), list):
        erros.append("estado.retornos deve ser lista")
    if not isinstance(estado.get("documentos"), list):
        erros.append("estado.documentos deve ser lista")
    registros = estado.get("etapas")
    if not isinstance(registros, dict):
        erros.append("estado.etapas deve ser objeto")
    else:
        desconhecidas = sorted(set(registros) - set(ETAPAS))
        if desconhecidas:
            erros.append("estado.etapas traz etapa desconhecida: %s" % ", ".join(desconhecidas))
        for etapa in ETAPAS:
            registro = registros.get(etapa)
            if not isinstance(registro, dict):
                erros.append("estado.etapas.%s obrigatoria" % etapa)
                continue
            if registro.get("status") not in STATUS:
                erros.append("estado.etapas.%s.status invalido" % etapa)
            if not isinstance(registro.get("evidencias", []), list):
                erros.append("estado.etapas.%s.evidencias deve ser lista" % etapa)
    if erros:
        raise Contrato(erros)
    return estado


def _carregar_estado(path):

    if not os.path.isfile(path):
        raise Contrato(["nao ha SQUAD_STATE em %s: o squad deste caso ainda nao foi aberto. Rode "
                        "`squad.py init --area <area do caso> --state \"%s\" --objetivo ... "
                        "--polo ...` (ou `--squad <id>`) antes deste comando" % (path, path)])
    return _validar_estado(_ler_json(path, "SQUAD_STATE"))




def _bloqueios_de_documento(estado):
    'TODOS os documentos irregulares, nomeados. Reportar so o primeiro deixaria uma'

    politica = estado.get("politica_dados", "hibrida")
    motivos = []
    for doc in estado.get("documentos", []):
        if not isinstance(doc, dict):
            motivos.append("documento sem forma de objeto no estado")
            continue
        ident = doc.get("id") or "(sem id)"


        if doc.get("rota") == "remota" and doc.get("sensibilidade") == "sigiloso":
            motivos.append("documento %s: sigiloso NAO pode usar rota remota - documento "
                           "sigiloso nao sobe para a nuvem. Registre com --rota local (leitura "
                           "nesta maquina); se ele nao for sigiloso, registre com a "
                           "sensibilidade certa" % ident)
        elif doc.get("rota") == "remota" and doc.get("autorizado_remoto") is not True:
            motivos.append("documento %s: rota remota exige autorizacao registrada" % ident)
        if politica == "local" and doc.get("rota") == "remota":
            motivos.append("documento %s: politica LOCAL do squad impede rota remota" % ident)
    return motivos


def _sensibilidade_do_estado(estado, conferencia):
    'Cruza o SIGILO DECLARADO pelo advogado com o inventario da conferencia.'








    documentos = conferencia.get("documentos") if isinstance(conferencia, dict) else None
    if not isinstance(documentos, list):
        return conferencia, []


    declarados = planejar_turma._indexar_declarados(
        [d for d in estado.get("documentos", []) if isinstance(d, dict) and _str(d.get("id"))])
    remotas = planejar_turma.ROTAS_REMOTAS
    politica = estado.get("politica_dados", "hibrida")
    novos, avisos, sem_declaracao = [], [], []
    for doc in documentos:
        if not isinstance(doc, dict):
            novos.append(doc)
            continue
        doc_id = str(doc.get("doc_id") or "").strip()
        arquivo = str(doc.get("arquivo") or "").strip()
        rotulo = doc_id or arquivo or "(sem doc_id)"
        declarado, _como = planejar_turma._declaracao_de(declarados, doc_id, arquivo)
        copia = dict(doc)
        if declarado is None:
            sem_declaracao.append(rotulo)
        else:
            sensibilidade = declarado.get("sensibilidade")
            if sensibilidade in SENSIBILIDADES:
                copia["sensibilidade"] = sensibilidade
                if sensibilidade == "sigiloso":
                    avisos.append(
                        "documento %s: SIGILOSO por declaracao do advogado no estado do squad "
                        "(`squad.py documento`) - a fatia nasce marcada e rota remota e "
                        "rebaixada" % rotulo)
        if politica == "local" and copia.get("rota") in remotas:
            avisos.append(
                "politica de dados LOCAL do squad: o documento %s consta ingerido por rota %r "
                "(remota) no inventario. AVISO, nao rebaixamento - se ele for sigiloso, declare "
                "com `squad.py documento --id %s --sensibilidade sigiloso`"
                % (rotulo, copia.get("rota"), rotulo))
        novos.append(copia)
    if sem_declaracao:
        avisos.append(
            "documento(s) do inventario NAO declarado(s) no estado do squad: %s. O plano NAO "
            "presume sigilo (presumir barraria caso legitimo) nem os trata como publicos em "
            "silencio: a ausencia da declaracao fica DITA. Declare com `squad.py documento "
            "--id <doc_id> --sensibilidade ... --rota ...` antes de despachar leitor por rota "
            "remota" % ", ".join(sem_declaracao))
    enriquecida = dict(conferencia)
    enriquecida["documentos"] = novos
    return enriquecida, avisos


def _carimbar_plano_velho(estado, ident, anterior, nova):
    'Reclassificacao AGRAVANTE depois do plano nao pode deixar o artefato parecendo atual.'









    turma = estado.get("plano_turma")
    if not isinstance(turma, dict):
        return []

    antes = (anterior or {}).get("sensibilidade") or "publico"
    if antes not in SENSIBILIDADES or nova not in SENSIBILIDADES:
        return []
    if SENSIBILIDADES.index(nova) <= SENSIBILIDADES.index(antes):
        return []
    planejados = turma.get("documentos")
    if isinstance(planejados, list):
        if ident not in planejados:
            return []
        origem = "e %s esta entre os documentos que o plano cobre" % ident
    else:
        origem = ("e o plano gravado nao traz a lista de documentos: a participacao de %s nele "
                  "nao pode ser conferida aqui" % ident)
    motivo = "sensibilidade de %s mudou de %r para %r depois do plano; %s" % (
        ident, antes, nova, origem)
    turma["desatualizado_em"] = _agora()
    turma["desatualizado_motivo"] = motivo
    return ["plano da turma marcado como DESATUALIZADO: %s. Rode `squad.py plano "
            "--conferencia ...` de novo antes de despachar leitor - o %s gravado ainda traz a "
            "fatia com a classificacao anterior"
            % (motivo, turma.get("artefato") or NOME_TURMA_PLANO)]


def _avisos_do_plano(estado):
    """Aviso de plano envelhecido, para `status` e painel. Nunca bloqueio."""
    turma = estado.get("plano_turma")
    if not isinstance(turma, dict) or not turma.get("desatualizado_em"):
        return []
    return ["plano da turma DESATUALIZADO desde %s: %s. O %s gravado ainda reflete a "
            "classificacao anterior; replaneje com `squad.py plano --conferencia ...`"
            % (turma.get("desatualizado_em"),
               turma.get("desatualizado_motivo") or "(motivo nao registrado)",
               turma.get("artefato") or NOME_TURMA_PLANO)]


def _evidencia_valida(registro, tipo, args):
    """Evidencia e arquivo que EXISTE. Rotulo com string qualquer nao e evidencia."""
    for item in registro.get("evidencias", []) or []:
        if not isinstance(item, dict) or item.get("tipo") != tipo:
            continue
        ref = item.get("ref")
        if not _str(ref):
            continue
        if os.path.exists(_resolver_ref(ref, args)):
            return item
    return None


def _gate_peca_state(item, args):
    caminho = _resolver_ref(item.get("ref"), args)
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            peca = json.load(arquivo)
    except Exception as exc:
        return ["PECA_STATE ilegivel em %s: %s" % (caminho, exc)]
    if not isinstance(peca, dict):
        return ["PECA_STATE nao e objeto JSON"]
    for campo in ("is_minuta", "fases"):
        if campo not in peca:
            return ["PECA_STATE sem o campo `%s` - nao e um PECA_STATE do contrato, e o squad "
                    "nao afirma liberacao sobre arquivo que nao reconhece" % campo]
    fases = peca.get("fases")
    if not isinstance(fases, dict):
        return ["PECA_STATE.fases deve ser objeto"]
    entrega = fases.get("entrega") if isinstance(fases.get("entrega"), dict) else {}
    if peca.get("is_minuta") is not False or entrega.get("status") != "concluida":
        return ["PECA_STATE nao esta liberado; LINT, Conselho e gate de entrega continuam "
                "obrigatorios"]
    return []


def _gate_etapa(estado, etapa, registro, args):
    exigencia = EVIDENCIA_EXIGIDA.get(etapa)
    if not exigencia:
        return []
    tipo, mensagem = exigencia
    item = _evidencia_valida(registro, tipo, args)
    if item is None:
        return ["%s (evidencia do tipo '%s' com `ref` apontando para arquivo existente)"
                % (mensagem, tipo)]
    if etapa == "checklist_externo":
        return _gate_peca_state(item, args)
    return []


def _encerrado(estado):
    ultimo = estado["etapas"][ETAPAS[-1]]
    return ultimo.get("status") == "concluida"




def _markdown(estado):
    linhas = [
        "# Squad Dissero - %s" % estado["squad"], "",
        "Objetivo: %s" % estado["objetivo"],
        "Area: %s | Polo: %s | Politica de dados: %s" % (estado["area"], estado["polo"],
                                                         estado.get("politica_dados", "-")),
        "Ciclo: %d de %d | Devolucoes: %d" % (estado["ciclo"], estado["max_ciclos"],
                                              len(estado["retornos"])),
        "Etapa atual: %s%s" % (estado["etapa_atual"],
                               "  (SQUAD ENCERRADO)" if _encerrado(estado) else ""),
        "Checkpoints deste squad: %s" % (", ".join(estado.get("checkpoints") or []) or "-"), "",
        "| Etapa | Agente | Status | Evidencias | Aprovacao |", "|---|---|---|---|---|",
    ]
    for etapa in ETAPAS:
        reg = estado["etapas"][etapa]
        evid = ", ".join(str(i.get("tipo", "evidencia")) for i in reg.get("evidencias", [])) or "-"
        apr = reg.get("aprovacao") or {}
        selo = ("%s em %s" % (apr.get("por", "?"), apr.get("em", "?"))) if apr else "-"
        agente = reg.get("agente") or "-"
        if reg.get("agente") and reg.get("agente_conferido"):
            agente = "%s (%s)" % (agente, "conferido no ledger"
                                  if reg["agente_conferido"] == "ledger" else "autodeclarado")
        linhas.append("| %s | %s | %s | %s | %s |"
                      % (etapa, agente, reg["status"], evid, selo))


    oficios = [o for o in estado.get("oficios") or [] if isinstance(o, dict)]
    if oficios:
        linhas.extend(["", "## Turma do squad", "| Oficio | Camada | Modelo | Roteiro do acervo |",
                       "|---|---|---|---|"])
        for oficio in oficios:
            linhas.append("| %s (%s) | %s | %s | %s |"
                          % (oficio.get("titulo"), oficio.get("id"), oficio.get("camada"),
                             oficio.get("model"), ", ".join(oficio.get("roteiros") or []) or "-"))



    turma = estado.get("plano_turma") or {}
    if turma:
        linhas.extend([
            "", "## Turma planejada",
            "%s fatia(s) de leitura | %s agente(s) no total | %s onda(s) | acao: %s"
            % (turma.get("total_fatias", "?"), turma.get("total_agentes", "?"),
               turma.get("ondas", "?"), turma.get("acao", "?")),
            "Cobertura: %s pagina(s) planejada(s) | completa: %s"
            % (turma.get("paginas_planejadas", "?"),
               "sim" if turma.get("cobertura_completa") else "NAO"),
            "Plano completo (fatia por fatia): %s" % (turma.get("artefato") or "-"),
        ])



        linhas.extend(["- %s" % m for m in _avisos_do_plano(estado)])


    linhas.extend(["", "## Documentos e rota"])
    if estado["documentos"]:
        linhas.extend(["| Documento | Sensibilidade | Rota | Autorizado remoto | Retencao |",
                       "|---|---|---|---|---|"])
        for doc in estado["documentos"]:
            linhas.append("| %s | %s | %s | %s | %s |"
                          % (doc.get("id"), doc.get("sensibilidade"), doc.get("rota"),
                             "sim" if doc.get("autorizado_remoto") else "nao",
                             doc.get("retencao", "nao_declarada")))
    else:
        linhas.append("Nenhum documento registrado.")
    bloqueios = _bloqueios_de_documento(estado)
    if bloqueios:
        linhas.extend(["", "## BLOQUEIOS ATIVOS"] + ["- %s" % m for m in bloqueios])
    if estado["retornos"]:
        linhas.extend(["", "## Retornos"])
        for retorno in estado["retornos"]:
            linhas.append("- ciclo %s (%s): %s - %s%s"
                          % (retorno.get("ciclo"), retorno.get("em", "?"), retorno.get("etapa"),
                             retorno.get("motivo"),
                             " [artefato: %s]" % retorno["artefato"] if retorno.get("artefato") else ""))
            reabertas = retorno.get("etapas_reabertas") or {}
            if reabertas:
                linhas.append("  - reabriu, com o que havia registrado: %s"
                              % ", ".join(sorted(reabertas)))
    if estado.get("escalonamentos"):
        linhas.extend(["", "## ESCALADO AO ADVOGADO"])
        for esc in estado["escalonamentos"]:
            linhas.append("- %s: %s" % (esc.get("em"), esc.get("motivo")))
    return "\n".join(linhas) + "\n"


def _gravar_painel(estado, caminho):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(caminho)) or ".", exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as arquivo:
            arquivo.write(_markdown(estado))
    except OSError as exc:
        raise Contrato(["nao foi possivel gravar o painel %s: %s" % (caminho, exc)])


def caminho_painel(args, estado_path):
    if _str(getattr(args, "saida", None)):
        return os.path.abspath(args.saida)
    return os.path.join(os.path.dirname(estado_path) or ".", "PAINEL_SQUAD.md")




def cmd_init(args):
    destino = caminho_estado(args)
    if os.path.exists(destino) and not args.recomecar:
        return _out("bloqueado", None,
                    ["ja existe um SQUAD_STATE em %s - `init` NAO sobrescreve caso em "
                     "andamento. Use `status` para retomar, ou `--recomecar` para comecar de "
                     "novo (o estado atual e copiado para .bak.json antes)" % destino],
                    1, caminho=destino)
    bruto = _ler_json(args.definicao, "definicao")
    area = getattr(args, "area", None)
    if area and args.squad:
        raise Contrato(["use --squad <id> OU --area <area>, nao os dois: o squad da area poderia "
                        "nao ser o pedido, e um deles seria ignorado em silencio"])
    if area:
        if area not in AREAS:
            raise Contrato(["area '%s' desconhecida; as areas sao: %s"
                            % (area, ", ".join(AREAS))])
        args.squad, motivo = squad_da_area(area, args.definicao)
        if args.squad is None:
            return _out("sem_squad_da_area", None, [motivo], 1, area=area)
    if args.squad:
        _validar_catalogo(bruto)
        definicao = next((i for i in bruto["squads"] if i.get("id") == args.squad), None)
        if definicao is None:
            validos = sorted(str(i.get("id")) for i in bruto["squads"] if isinstance(i, dict))
            dica = ""
            if args.squad in AREAS:
                sid, _ = squad_da_area(args.squad, args.definicao)
                dica = (" - '%s' e nome de AREA: use --area %s%s"
                        % (args.squad, args.squad, " (abre o %s)" % sid if sid else ""))
            raise Contrato(["squad '%s' nao encontrado na definicao%s; os validos sao: %s"
                            % (args.squad, dica, ", ".join(validos))])
    else:
        definicao = bruto
    definicao = _validar_definicao(definicao)
    if not _str(args.objetivo):
        raise Contrato(["--objetivo nao pode ser vazio: e o unico texto de briefing que o "
                        "estado guarda"])
    if args.polo not in POLOS:
        raise Contrato(["--polo deve ser um de %s" % (POLOS,)])
    if args.max_ciclos < 1:
        raise Contrato(["--max-ciclos deve ser >= 1"])

    copia = None
    if os.path.exists(destino):
        copia = destino.replace(".json", "") + ".bak.json"
        try:
            shutil.copy2(destino, copia)
        except OSError as exc:
            raise Contrato(["nao foi possivel salvar a copia antes de recomecar: %s" % exc])

    estado = {
        "schema_version": "dsr.squad_state.v1",
        "squad": definicao["id"], "objetivo": args.objetivo.strip(), "area": definicao["area"],
        "polo": args.polo, "politica_dados": args.politica,
        "checkpoints": list(definicao.get("checkpoints") or CHECKPOINTS_PADRAO),



        "oficios": [dict(o) for o in definicao.get("oficios") or []],
        "max_ciclos": args.max_ciclos,
        "etapa_atual": "foco", "ciclo": 1, "criado_em": _agora(),
        "documentos": [], "retornos": [], "escalonamentos": [],
        "etapas": {e: {"status": "planejada", "agente": "", "evidencias": []} for e in ETAPAS},
    }
    _validar_estado(estado)
    _gravar(destino, estado)
    painel = caminho_painel(args, destino)
    _gravar_painel(estado, painel)
    motivos = ["SQUAD_STATE criado em %s" % destino, "painel em %s" % painel]
    if copia:
        motivos.append("estado anterior preservado em %s" % copia)
    return _out("inicializado", estado, motivos, 0, caminho=destino, painel=painel)


def cmd_documento(args):
    destino = caminho_estado(args)
    estado = _carregar_estado(destino)
    if not _str(args.id):
        return _out("bloqueado", estado, ["documento requer --id nao-vazio"], 1)
    anterior = next((d for d in estado["documentos"] if d.get("id") == args.id), None)


    if anterior and SENSIBILIDADES.index(args.sensibilidade) < \
            SENSIBILIDADES.index(anterior.get("sensibilidade", "publico")):
        if not args.reclassificar:
            return _out("bloqueado", estado,
                        ["documento %s ja esta registrado como %r e este comando o rebaixaria "
                         "para %r; rebaixar sensibilidade exige --reclassificar. Se a mudanca "
                         "e intencional, repita o mesmo comando com --reclassificar (a "
                         "classificacao anterior deixa de valer)"
                         % (args.id, anterior.get("sensibilidade"), args.sensibilidade)], 1)
    doc = {"id": args.id, "sensibilidade": args.sensibilidade, "rota": args.rota,
           "autorizado_remoto": bool(args.autorizado_remoto),
           "retencao": args.retencao, "registrado_em": _agora()}
    candidato = dict(estado)
    candidato["documentos"] = [d for d in estado["documentos"] if d.get("id") != args.id] + [doc]


    bloqueios = _bloqueios_de_documento(candidato)
    proprios = [m for m in bloqueios if m.startswith("documento %s:" % args.id)]
    if proprios:
        return _out("bloqueado", estado, proprios, 1)
    estado["documentos"] = candidato["documentos"]



    avisos = _carimbar_plano_velho(estado, args.id, anterior, args.sensibilidade)
    _gravar(destino, estado)
    _gravar_painel(estado, caminho_painel(args, destino))
    return _out("documento_registrado", estado, avisos, 0)


def cmd_iniciar(args):
    destino = caminho_estado(args)
    estado = _carregar_estado(destino)
    if args.etapa not in ETAPAS:
        raise Contrato(["etapa invalida"])
    if _encerrado(estado):
        return _out("bloqueado", estado, ["squad encerrado; reabra por `devolver`"], 1)
    if args.etapa != estado["etapa_atual"]:
        return _out("bloqueado", estado, ["somente a etapa atual pode ser iniciada"], 1)
    registro = estado["etapas"][args.etapa]


    if registro["status"] not in ("planejada", "bloqueada"):
        return _out("bloqueado", estado,
                    ["etapa em %r; so inicia quando estiver planejada ou bloqueada"
                     % registro["status"]], 1)
    bloqueios = _bloqueios_de_documento(estado)
    if bloqueios:
        registro["status"] = "bloqueada"
        _gravar(destino, estado)
        _gravar_painel(estado, caminho_painel(args, destino))
        return _out("bloqueado", estado, bloqueios, 1)



    if not _str(args.agente):
        return _out("bloqueado", estado,
                    ["--agente nao pode ser vazio: e o identificador do agente que executou a "
                     "etapa, e sem ele a equipe volta a ser etiqueta"], 1)
    registro["status"] = "em_execucao"
    registro["agente"] = args.agente.strip()




    ids, ledger = _ids_do_ledger(destino)
    registro["agente_conferido"] = "ledger" if registro["agente"] in ids else "autodeclarado"
    avisos = []
    if ledger and registro["agente_conferido"] != "ledger":
        avisos.append("o agente '%s' nao consta do PROVENIENCIA.jsonl do caso (%s): a etapa fica "
                      "marcada como autodeclarada. Se ela foi feita por subagente, use o "
                      "identificador que o harness gravou no ledger" % (registro["agente"], ledger))
    registro["iniciada_em"] = _agora()
    _gravar(destino, estado)
    _gravar_painel(estado, caminho_painel(args, destino))
    return _out("em_execucao", estado, [], 0, avisos=avisos)


def _ids_do_ledger(destino):
    '(ids, caminho) do PROVENIENCIA.jsonl do caso: o de `DSR_PROV_LEDGER`, senao o que mora'


    candidatos = [os.environ.get("DSR_PROV_LEDGER"),
                  os.path.join(os.path.dirname(os.path.abspath(destino)), "PROVENIENCIA.jsonl")]
    for caminho in candidatos:
        if not caminho or not os.path.isfile(caminho):
            continue
        ids = set()
        try:
            with open(caminho, encoding="utf-8") as fh:
                for linha in fh:
                    try:
                        aid = json.loads(linha).get("agent_id")
                    except Exception:
                        continue
                    if _str(aid):
                        ids.add(aid.strip())
        except OSError:
            continue
        return ids, caminho
    return set(), None


def cmd_concluir(args):
    destino = caminho_estado(args)
    estado = _carregar_estado(destino)
    if args.etapa not in ETAPAS or args.etapa != estado["etapa_atual"]:
        return _out("bloqueado", estado, ["somente a etapa atual pode ser concluida"], 1)
    registro = estado["etapas"][args.etapa]
    if registro["status"] != "em_execucao":
        return _out("bloqueado", estado, ["etapa precisa estar em_execucao antes de concluir"], 1)
    try:
        evidencias = json.loads(args.evidencias)
    except Exception as exc:
        raise Contrato(["--evidencias JSON invalido: %s" % exc])
    if not isinstance(evidencias, list):
        raise Contrato(["--evidencias deve ser lista JSON"])
    for item in evidencias:
        if not isinstance(item, dict) or not _str(item.get("tipo")) or not _str(item.get("ref")):
            raise Contrato(["cada evidencia precisa de `tipo` e `ref` nao-vazios"])


    bloqueios = _bloqueios_de_documento(estado)
    if bloqueios:
        registro["status"] = "bloqueada"
        _gravar(destino, estado)
        _gravar_painel(estado, caminho_painel(args, destino))
        return _out("bloqueado", estado, bloqueios, 1)
    anteriores = registro.get("evidencias") or []
    registro["evidencias"] = evidencias
    bloqueios = _gate_etapa(estado, args.etapa, registro, args)
    if bloqueios:


        registro["evidencias"] = anteriores
        _gravar(destino, estado)
        _gravar_painel(estado, caminho_painel(args, destino))
        return _out("bloqueado", estado, bloqueios, 1)
    registro["concluida_em"] = _agora()
    if args.etapa in (estado.get("checkpoints") or []):
        registro["status"] = "aguardando_aprovacao"
        _gravar(destino, estado)
        _gravar_painel(estado, caminho_painel(args, destino))
        return _out("aguardando_aprovacao", estado, ["checkpoint humano obrigatorio"], 0,
                    aguarda_aprovacao=True)
    return _concluir_e_avancar(args, destino, estado, args.etapa, registro, "etapa_concluida")


def _concluir_e_avancar(args, destino, estado, etapa, registro, rotulo):
    registro["status"] = "concluida"
    indice = ETAPAS.index(etapa)
    fim = indice >= len(ETAPAS) - 1
    if not fim:
        estado["etapa_atual"] = ETAPAS[indice + 1]
    _gravar(destino, estado)
    _gravar_painel(estado, caminho_painel(args, destino))
    if fim:
        return _out("squad_encerrado", estado,
                    ["ultima etapa concluida; a liberacao da peca continua sendo do "
                     "estado_peca.py, do LINT, do Conselho e do gate de entrega"], 0,
                    encerrado=True)
    return _out(rotulo, estado, [], 0)


def cmd_aprovar(args):
    destino = caminho_estado(args)
    estado = _carregar_estado(destino)
    etapa = estado["etapa_atual"]
    registro = estado["etapas"][etapa]
    if registro["status"] != "aguardando_aprovacao":
        return _out("bloqueado", estado, ["nao ha checkpoint aguardando aprovacao"], 1)
    if etapa not in (estado.get("checkpoints") or []):
        return _out("bloqueado", estado,
                    ["etapa %s nao e checkpoint deste squad" % etapa], 1)
    if args.aprovado is not True:
        return _out("bloqueado", estado, ["aprovacao exige --aprovado"], 1)
    if not _str(args.por):
        return _out("bloqueado", estado,
                    ["--por e obrigatorio: aprovacao sem autor nao se distingue de etapa "
                     "concluida sozinha, e e ela que o checkpoint humano existe para registrar"],
                    1)


    bloqueios = _gate_etapa(estado, etapa, registro, args)
    if bloqueios:
        registro["status"] = "bloqueada"
        _gravar(destino, estado)
        _gravar_painel(estado, caminho_painel(args, destino))
        return _out("bloqueado", estado, ["na aprovacao: %s" % m for m in bloqueios], 1)
    registro["aprovacao"] = {"por": args.por.strip(), "em": _agora()}
    return _concluir_e_avancar(args, destino, estado, etapa, registro, "aprovado")


def cmd_devolver(args):
    destino = caminho_estado(args)
    estado = _carregar_estado(destino)
    if args.para not in ETAPAS:
        raise Contrato(["--para deve ser uma etapa valida: %s" % ", ".join(ETAPAS)])
    if not _str(args.motivo):
        raise Contrato(["--motivo nao pode ser vazio: o motivo E o registro da devolucao"])


    if args.max_ciclos is not None:
        raise Contrato(["--max-ciclos nao existe em `devolver`: o limite e declarado no `init` "
                        "e vive no estado. Limite que o chamador escolhe a cada chamada nao e "
                        "limite"])
    destino_idx = ETAPAS.index(args.para)
    atual_idx = ETAPAS.index(estado["etapa_atual"])

    if destino_idx > atual_idx:
        return _out("bloqueado", estado,
                    ["devolucao so anda para TRAS: a etapa atual e %s e %s vem depois dela. "
                     "Andar para frente pularia os checkpoints humanos"
                     % (estado["etapa_atual"], args.para)], 1)
    if len(estado["retornos"]) >= estado["max_ciclos"]:
        escal = {"em": _agora(),
                 "motivo": "limite de %d devolucoes atingido na etapa %s; decisao do advogado"
                           % (estado["max_ciclos"], estado["etapa_atual"])}
        estado.setdefault("escalonamentos", []).append(escal)
        _gravar(destino, estado)
        _gravar_painel(estado, caminho_painel(args, destino))
        return _out("bloqueado", estado,
                    ["limite de %d devolucoes atingido; escalado ao advogado e REGISTRADO no "
                     "estado e no painel" % estado["max_ciclos"]], 1, escalado=True)


    reabertas = {}
    for etapa in ETAPAS[destino_idx:]:
        registro = estado["etapas"][etapa]
        if registro.get("status") != "planejada" or registro.get("evidencias"):
            reabertas[etapa] = registro
        estado["etapas"][etapa] = {"status": "planejada", "agente": "", "evidencias": []}
    estado["ciclo"] += 1
    estado["etapa_atual"] = args.para
    estado["retornos"].append({
        "ciclo": estado["ciclo"], "etapa": args.para, "motivo": args.motivo.strip(),
        "em": _agora(), "artefato": (args.artefato or "").strip() or None,
        "etapas_reabertas": reabertas,
    })
    _gravar(destino, estado)
    _gravar_painel(estado, caminho_painel(args, destino))
    return _out("devolvido", estado,
                ["motivo registrado; %d etapa(s) reaberta(s), com o que havia nelas arquivado "
                 "no retorno" % len(reabertas)], 0)


def cmd_plano(args):
    'Planeja a TURMA do caso e REGISTRA o plano no estado. Nao dispara nada.'







    destino = caminho_estado(args)
    estado = _carregar_estado(destino)
    if planejar_turma is None or ler_aval is None:
        raise Contrato(["modulos irmaos `planejar_turma.py`/`aval_subagentes.py` ausentes ao "
                        "lado do motor: sem eles a turma sairia sem o gate do §13. Rode "
                        "`python sincronizar_shared.py --sync`"])
    conferencia = _ler_json(args.conferencia, "CONFERENCIA")
    oficios, avisos = _oficios_para_o_plano(estado)


    conferencia, avisos_sigilo = _sensibilidade_do_estado(estado, conferencia)
    avisos = list(avisos) + list(avisos_sigilo)
    raiz = pasta_do_caso(destino)
    teto, detalhe = ler_aval(getattr(args, "session_id", None), raiz)
    try:



        plano = planejar_turma.planejar(conferencia, oficios, teto,
                                        max_simultaneos=detalhe.get("max_simultaneos"),
                                        aval=detalhe,
                                        session_id=getattr(args, "session_id", None))
    except planejar_turma.Contrato as exc:
        raise Contrato(["plano da turma recusado: %s" % exc])



    problemas = planejar_turma.validar_plano(plano)
    if problemas:
        raise Contrato(["o plano produzido nao passa no contrato publicado %s: %s"
                        % (planejar_turma.SCHEMA_VERSION,
                           " | ".join(str(p) for p in problemas[:5]))])

    artefato = os.path.join(raiz, NOME_TURMA_PLANO)
    _gravar(artefato, plano)
    resumo = {
        "acao": plano["acao"],
        "total_fatias": plano["total_fatias"],
        "total_agentes": plano["total_agentes"],
        "ondas": plano["ondas"],
        "paginas_planejadas": plano["cobertura"]["paginas_planejadas"],
        "cobertura_completa": bool(plano["cobertura"]["completa"]),



        "documentos": list(plano["cobertura"].get("documentos_planejados") or []),
        "espinha_ref": plano["espinha"]["ref"],
        "artefato": artefato,
        "gerado_em": plano["gerado_em"],
    }
    estado["plano_turma"] = resumo
    _gravar(destino, estado)
    _gravar_painel(estado, caminho_painel(args, destino))

    motivos = list(avisos) + list(plano.get("avisos") or [])
    if plano["acao"] == "escalar":
        motivos.append(plano.get("erro") or "plano escalado ao advogado")
        if plano.get("comando_aval"):
            motivos.append(plano["comando_aval"])
        return _out("escalar", estado, motivos, 1, plano_turma=resumo, artefato=artefato)
    motivos.append(plano.get("motivo") or "")
    motivos.append("plano completo em %s - o disparo e da skill, pela ferramenta de "
                   "subagente do ambiente; o motor planeja e recusa" % artefato)
    return _out("plano_da_turma", estado, motivos, 0, plano_turma=resumo, artefato=artefato)


def cmd_status(args):
    destino = caminho_estado(args)
    estado = _carregar_estado(destino)
    return _out("status", estado, [], 0, caminho=destino, encerrado=_encerrado(estado),
                bloqueios=_bloqueios_de_documento(estado),
                avisos_plano=_avisos_do_plano(estado),
                devolucoes=len(estado["retornos"]), max_ciclos=estado["max_ciclos"],
                oficios=estado.get("oficios") or [],
                etapas={k: v["status"] for k, v in estado["etapas"].items()})


def cmd_painel(args):
    destino = caminho_estado(args)
    estado = _carregar_estado(destino)
    saida = caminho_painel(args, destino)
    _gravar_painel(estado, saida)
    return _out("painel_gerado", estado, ["painel Markdown criado em %s" % saida], 0, painel=saida)




def _comum(parser):
    parser.add_argument("--state", default=None,
                        help="caminho do SQUAD_STATE; sem ele, a RAIZ DO CASO (caso_raiz.py)")
    parser.add_argument("--session-id", default=None)
    return parser


def main(argv=None):
    parser = argparse.ArgumentParser(description="Executor de squads juridicos Dissero")
    subs = parser.add_subparsers(dest="cmd", required=True)

    init = _comum(subs.add_parser("init"))

    init.add_argument("--definicao", default=os.path.join(REFS, "squads.json"))
    init.add_argument("--squad", help="id do squad no catalogo (ex.: peca-trabalhista)")
    init.add_argument("--area", help="modulo de area do acervo (ex.: previdenciario): abre o "
                                     "squad dessa area")
    init.add_argument("--objetivo", required=True)
    init.add_argument("--polo", required=True, choices=POLOS)
    init.add_argument("--politica", choices=POLITICAS, default="hibrida")
    init.add_argument("--max-ciclos", type=int, default=MAX_CICLOS_PADRAO, dest="max_ciclos")
    init.add_argument("--recomecar", action="store_true",
                      help="descarta um squad em andamento (grava .bak.json antes)")
    init.add_argument("--saida", default=None, help="caminho do PAINEL_SQUAD.md")

    doc = _comum(subs.add_parser("documento"))
    doc.add_argument("--id", required=True)
    doc.add_argument("--sensibilidade", choices=SENSIBILIDADES, required=True)
    doc.add_argument("--rota", choices=ROTAS, required=True)
    doc.add_argument("--autorizado-remoto", action="store_true", dest="autorizado_remoto")
    doc.add_argument("--retencao", default="nao_declarada")
    doc.add_argument("--reclassificar", action="store_true",
                     help="autoriza REBAIXAR a sensibilidade ja registrada")
    doc.add_argument("--saida", default=None)

    iniciar = _comum(subs.add_parser("iniciar"))
    iniciar.add_argument("--etapa", required=True)
    iniciar.add_argument("--agente", required=True,
                         help="identificador do agente que executa a etapa, o mesmo que o "
                              "harness grava no PROVENIENCIA.jsonl")
    iniciar.add_argument("--saida", default=None)

    plano = _comum(subs.add_parser("plano"))
    plano.add_argument("--conferencia", required=True,
                       help="CONFERENCIA.json (dsr.conferencia.v1) - o inventario do que foi lido")

    concluir = _comum(subs.add_parser("concluir"))
    concluir.add_argument("--etapa", required=True)
    concluir.add_argument(
        "--evidencias", required=True,
        help="lista JSON [{\"tipo\": ..., \"ref\": <arquivo que existe>}]. Tipo exigido por "
             "etapa: " + "; ".join("%s=%s" % (e, EVIDENCIA_EXIGIDA[e][0]) for e in ETAPAS)
             + ". Na pesquisa sem julgado citado, a relacao diz isso.")
    concluir.add_argument("--saida", default=None)

    aprovar = _comum(subs.add_parser("aprovar"))
    aprovar.add_argument("--aprovado", action="store_true")
    aprovar.add_argument("--por", required=True, help="quem aprovou o checkpoint")
    aprovar.add_argument("--saida", default=None)

    devolver = _comum(subs.add_parser("devolver"))
    devolver.add_argument("--para", required=True)
    devolver.add_argument("--motivo", default="")
    devolver.add_argument("--artefato", default=None, help="artefato afetado pela devolucao")


    devolver.add_argument("--max-ciclos", type=int, default=None, dest="max_ciclos",
                          help=argparse.SUPPRESS)
    devolver.add_argument("--saida", default=None)

    _comum(subs.add_parser("status"))
    painel = _comum(subs.add_parser("painel"))
    painel.add_argument("--saida", default=None)

    args = parser.parse_args(argv)
    if not hasattr(args, "saida"):
        args.saida = None
    try:
        return {"init": cmd_init, "documento": cmd_documento, "iniciar": cmd_iniciar,
                "concluir": cmd_concluir, "aprovar": cmd_aprovar, "devolver": cmd_devolver,
                "plano": cmd_plano, "status": cmd_status, "painel": cmd_painel}[args.cmd](args)
    except Contrato as exc:
        return _out("contrato_invalido", None, exc.args[0], 2)


if __name__ == "__main__":
    sys.exit(main())
