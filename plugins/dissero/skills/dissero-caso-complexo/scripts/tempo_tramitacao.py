#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tempo_tramitacao.py - quanto tempo demora, por ORGAO e nunca por magistrado.

O QUE ESTE MODULO NAO FAZ, E A DISTINCAO QUE ELE EXISTE PARA MANTER. Este modulo NAO perfila
julgador, e nao e por escrupulo abstrato: a API publica do DataJud nao tem campo de
magistrado. O que ela tem e `orgaoJulgador`, que e a UNIDADE - "2a Vara Civel de tal
comarca" -, nao a pessoa que decide. Vara nao e juiz: o titular muda, ha substituicao,
mutirao e auxilio, e um numero colhido por vara atribuido a uma pessoa e erro de fato antes
de ser qualquer outra coisa. Por isso o campo se chama `orgao` em toda a superficie deste
modulo, e ha teste que le o proprio fonte para provar que nao existe funcao de perfil de
magistrado.

O QUE ELE MEDE. Tempo decorrido entre o ajuizamento e a PRIMEIRA ocorrencia de um movimento
declarado pelo chamador, sobre um conjunto de processos que o chamador ja tem. Devolve
mediana e quartis, nunca so a media.

POR QUE MEDIANA E QUARTIS, E NAO MEDIA. Tempo de tramitacao tem cauda longa: um punhado de
processos parados por anos puxa a media para um valor que nao descreve caso nenhum. A
mediana descreve o caso do meio, e o intervalo entre o primeiro e o terceiro quartil diz a
dispersao - que e a informacao que o cliente realmente quer quando pergunta "quanto tempo
demora". A media entra na saida por completude, marcada, e nunca sozinha.

POR QUE NAO HA CONSULTA DE REDE AQUI. O calculo e sobre dado que o chamador ja tem: o
cliente somente-leitura da casa (`datajud_client.py`) so aceita `query` e `_source` no topo,
entao NAO HA `aggs` - agregacao no servidor esta fora, por desenho de seguranca. A conta e no
cliente, sobre amostra. Isso nao e limitacao contornavel: e a forma da rota.

O PISO DE AMOSTRA E O DE `admissibilidade_numero.py`, importado de la em vez de redigitado.
Numero sobre amostra rasa e anedota com casas decimais, e a regra nao muda por ser tempo em
vez de proporcao. `admissibilidade_numero.py` e a porta; este modulo mede o que passa por ela.

FALHA FECHADA DUPLA, igual aos irmaos: a funcao publica exige `autorizado=True`, e a CLI
exige DSR_TEMPO_TRAMITACAO=1 no ambiente. Alem das duas, a ficha `jurimetria_admissibilidade`
do registro de capacidades (a mesma de `admissibilidade_numero.py`) e lida a cada medida:
desligada (`ficha_desligada`) ou vencida (`ficha_vencida`), recusa, com o codigo no campo
`ficha_recusada`.

SIGILO. A entrada traz data de ajuizamento e movimentos de processos reais. A SAIDA e
estatistica agregada e NAO carrega numero de processo, nome de parte nem identificador -
ha teste que verifica isso sobre entrada contaminada de proposito. Ainda assim: resultado
deste modulo e saida de execucao, nunca conteudo de repositorio.

O PAR CODIGO/ROTULO. Conferido na fonte oficial (SGT do CNJ, tabela de movimentos na versao
de 26/05/2026):

    22  "Baixa Definitiva"   Distribuidor -> Serventuario
    246 "Definitivo"         ARQUIVAMENTO -> Escrivao/Diretor de Secretaria -> Serventuario
        glossario: "Indica a acao de arquivamento definitivo do processo, nas situacoes em
        que nao ha expectativa de prosseguimento por situacoes normais."

Sao coisas diferentes, e a distincao e do oficio: baixa e o encerramento na estatistica do
tribunal; arquivamento e a guarda dos autos. Processo pode ser baixado sem arquivamento
definitivo e vice-versa - medir ate 246 chamando de "baixa" mede uma coisa e diz outra.

COMO RECONFERIR: o SGT do CNJ tem WebService SOAP publico, sem autenticacao. Endpoint,
namespace, operacoes e parametros estao na skill dissero-orquestrador, em
`references/acervo/tabelas-processuais-unificadas-cnj.md`; a linhagem de um movimento se monta
seguindo `cod_item_pai`.

Stdlib apenas. Uso:
    DSR_TEMPO_TRAMITACAO=1 python tempo_tramitacao.py --arquivo amostra.json \\
        --movimento-alvo 22 --rotulo "baixa definitiva"
    # ate o ARQUIVAMENTO definitivo o par e outro:
    #     --movimento-alvo 246 --rotulo "arquivamento definitivo"
Exit 0 medida utilizavel - 2 RECUSADO (falha fechada).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

try:
    from admissibilidade_numero import PISO_AMOSTRA, TETO_CONTAGEM_EXATA
except ImportError:

    PISO_AMOSTRA = None
    TETO_CONTAGEM_EXATA = None
from ficha_capacidade import FichaRecusada, exigir as exigir_ficha

SCHEMA_VERSION = "dsr.tempo_tramitacao.v1"
VARIAVEL_AMBIENTE = "DSR_TEMPO_TRAMITACAO"
CAPACIDADE = "jurimetria_admissibilidade"

MOTIVO_DESLIGADO = (
    "modulo nao autorizado: a funcao publica exige autorizado=True e a linha de comando "
    "exige %s=1 no ambiente" % VARIAVEL_AMBIENTE)

MOTIVO_SEM_IRMAO = (
    "admissibilidade_numero.py nao pode ser importado, entao o piso de amostra e "
    "desconhecido. Inventar piso proprio aqui criaria DUAS reguas para a mesma pergunta, e "
    "a mais frouxa venceria na hora do aperto")

AVISO_ORGAO_NAO_E_JUIZ = (
    "ORGAO NAO E MAGISTRADO: esta medida e por UNIDADE JUDICIARIA (vara, camara, turma), e "
    "nao por pessoa. O titular muda, ha substituicao, auxilio e mutirao. A API publica do "
    "DataJud NAO expoe magistrado - nao ha como perfilar juiz por esta rota, e atribuir a "
    "uma pessoa um numero colhido por vara e erro de fato")

AVISO_PROXY = (
    "PROXY, NAO PROGNOSTICO: tempo observado em processos passados descreve o passado "
    "daquela unidade. Nao e previsao para este caso, e nao entra em peca como se fosse")

AVISO_CAUDA = (
    "LEIA A MEDIANA, NAO A MEDIA: tempo de tramitacao tem cauda longa, e a media e puxada "
    "por poucos processos muito parados. O intervalo entre os quartis diz a dispersao")

AVISO_CENSURA = (
    "PROCESSOS SEM O MOVIMENTO FORAM EXCLUIDOS (%d de %d). Isso ENVIESA PARA BAIXO: o que "
    "ainda nao terminou tende a ser justamente o que demora mais. A medida descreve os que "
    "JA chegaram ao movimento, e nao o acervo")


def _data(valor):
    """Data ISO em texto, ou None. Aceita 'AAAA-MM-DD' e o formato do DataJud com hora."""
    if not isinstance(valor, str):
        return None
    bruto = valor.strip()
    if len(bruto) < 10:
        return None
    try:
        return _dt.date(int(bruto[0:4]), int(bruto[5:7]), int(bruto[8:10]))
    except (ValueError, TypeError):
        return None


def _quantil(ordenados, q):
    """Interpolacao linear entre pontos vizinhos. Lista NAO vazia e ordenada."""
    if not ordenados:
        return None
    if len(ordenados) == 1:
        return float(ordenados[0])
    pos = q * (len(ordenados) - 1)
    baixo = int(pos)
    alto = min(baixo + 1, len(ordenados) - 1)
    peso = pos - baixo
    return ordenados[baixo] * (1.0 - peso) + ordenados[alto] * peso


def _dias_ate_movimento(processo, codigos_alvo):
    """Dias do ajuizamento ate a PRIMEIRA ocorrencia de um dos codigos. None se nao houve."""
    inicio = _data(processo.get("dataAjuizamento"))
    if inicio is None:
        return None
    melhor = None
    for mov in processo.get("movimentos") or []:
        if not isinstance(mov, dict):
            continue
        try:
            codigo = int(mov.get("codigo"))
        except (TypeError, ValueError):
            continue
        if codigo not in codigos_alvo:
            continue
        quando = _data(mov.get("dataHora"))
        if quando is None:
            continue
        dias = (quando - inicio).days
        if dias < 0:
            continue
        if melhor is None or dias < melhor:
            melhor = dias
    return melhor


def medir(processos, codigos_alvo, rotulo, autorizado=False, piso_amostra=None, hoje=None,
          registro_capacidades=None):
    'Mediana e quartis do tempo ate o movimento, por orgao julgador e no conjunto.'



    motivos = []
    ficha_recusada = None

    if autorizado is not True:
        motivos.append(MOTIVO_DESLIGADO)
    try:
        exigir_ficha(CAPACIDADE, hoje=hoje, registro=registro_capacidades)
    except FichaRecusada as exc:
        ficha_recusada = exc.codigo
        motivos.append(exc.mensagem)
    if PISO_AMOSTRA is None:
        motivos.append(MOTIVO_SEM_IRMAO)

    piso = PISO_AMOSTRA if piso_amostra is None else piso_amostra
    if PISO_AMOSTRA is not None and piso < PISO_AMOSTRA:
        motivos.append("piso_amostra=%d abaixo do piso da casa (%d)" % (piso, PISO_AMOSTRA))

    if not isinstance(processos, list):
        motivos.append("processos deve ser lista")
    if not isinstance(codigos_alvo, (list, tuple, set)) or not codigos_alvo:
        motivos.append("codigos_alvo deve ser conjunto nao vazio de codigos de movimento TPU")
    if not str(rotulo or "").strip():
        motivos.append("rotulo ausente: sem dizer QUE movimento foi medido, o numero nao e "
                       "conferivel por quem le")

    if motivos:
        recusa = {"schema_version": SCHEMA_VERSION, "estado": "recusado", "motivos": motivos}
        if ficha_recusada:
            recusa["ficha_recusada"] = ficha_recusada
        return recusa

    try:
        alvos = {int(c) for c in codigos_alvo}
    except (TypeError, ValueError):
        return {"schema_version": SCHEMA_VERSION, "estado": "recusado",
                "motivos": ["codigos_alvo tem valor que nao e inteiro"]}

    por_orgao = {}
    todos = []
    sem_movimento = 0
    for p in processos:
        if not isinstance(p, dict):
            continue
        dias = _dias_ate_movimento(p, alvos)
        if dias is None:
            sem_movimento += 1
            continue
        todos.append(dias)
        orgao = ((p.get("orgaoJulgador") or {}).get("nome")
                 if isinstance(p.get("orgaoJulgador"), dict) else None)
        por_orgao.setdefault(str(orgao or "(orgao nao declarado)"), []).append(dias)

    n = len(todos)
    if n < piso:
        return {
            "schema_version": SCHEMA_VERSION, "estado": "recusado",
            "motivos": ["AMOSTRA RASA: %d processos chegaram ao movimento, abaixo do piso "
                        "de %d. Nao ha medida, ha anedota" % (n, piso)],
            "considerados": len(processos), "com_movimento": n,
            "sem_movimento": sem_movimento,
        }

    avisos = [AVISO_ORGAO_NAO_E_JUIZ, AVISO_PROXY, AVISO_CAUDA]
    if sem_movimento:
        avisos.append(AVISO_CENSURA % (sem_movimento, len(processos)))
    if TETO_CONTAGEM_EXATA is not None and len(processos) >= TETO_CONTAGEM_EXATA:
        avisos.append("AMOSTRA NO TETO: o conjunto tem %d processos, e a API publica do "
                      "DataJud para de contar em %d ('gte'). Se a amostra veio dela, ela e "
                      "PISO e pode nao representar o acervo"
                      % (len(processos), TETO_CONTAGEM_EXATA))

    def resumo(valores):
        v = sorted(valores)
        return {
            "n": len(v),
            "mediana_dias": _quantil(v, 0.5),
            "p25_dias": _quantil(v, 0.25),
            "p75_dias": _quantil(v, 0.75),
            "minimo_dias": v[0],
            "maximo_dias": v[-1],
            "media_dias_LEIA_O_AVISO": sum(v) / len(v),
        }

    orgaos = {}
    orgaos_rasos = []
    for nome, valores in sorted(por_orgao.items()):
        if len(valores) < piso:
            orgaos_rasos.append({"orgao": nome, "n": len(valores)})
            continue
        orgaos[nome] = resumo(valores)

    return {
        "schema_version": SCHEMA_VERSION,
        "estado": "medido",
        "rotulo": str(rotulo).strip(),
        "codigos_alvo": sorted(alvos),
        "considerados": len(processos),
        "com_movimento": n,
        "sem_movimento": sem_movimento,
        "conjunto": resumo(todos),
        "por_orgao": orgaos,
        "orgaos_com_amostra_rasa": orgaos_rasos,
        "avisos": avisos,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arquivo", required=True,
                    help="JSON com a lista de processos (dataAjuizamento + movimentos)")
    ap.add_argument("--movimento-alvo", required=True,
                    help="codigos TPU separados por virgula")
    ap.add_argument("--rotulo", required=True)
    ap.add_argument("--piso-amostra", type=int, default=None)
    args = ap.parse_args(argv)

    try:
        dado = json.load(io.open(args.arquivo, encoding="utf-8"))
    except (OSError, ValueError) as erro:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "estado": "recusado",
                          "motivos": ["arquivo ilegivel: %s" % erro]}, ensure_ascii=False))
        return 2
    if isinstance(dado, dict):
        dado = dado.get("processos") or dado.get("hits") or []

    codigos = [c.strip() for c in str(args.movimento_alvo).split(",") if c.strip()]
    r = medir(dado, codigos, args.rotulo,
              autorizado=os.environ.get(VARIAVEL_AMBIENTE) == "1",
              piso_amostra=args.piso_amostra)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["estado"] == "medido" else 2


if __name__ == "__main__":
    sys.exit(main())
