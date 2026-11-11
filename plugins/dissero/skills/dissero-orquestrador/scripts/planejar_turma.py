#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'planejar_turma.py — planeja a TURMA de agentes no nível do CASO (não do documento).'











































































import argparse
import hashlib
import json
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(os.path.dirname(AQUI), "references")
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass



try:
    from schema_mini import validar_schema
except Exception:
    validar_schema = None
try:
    from aval_subagentes import ler_aval, PADRAO_SIMULTANEOS, PADRAO_ONDAS
except Exception:
    ler_aval, PADRAO_SIMULTANEOS, PADRAO_ONDAS = None, 2, 1
try:
    import caso_raiz
except Exception:
    caso_raiz = None





_INGESTAO = os.path.join(os.path.dirname(os.path.dirname(AQUI)), "dissero-ingestao", "scripts")
if os.path.isdir(_INGESTAO) and _INGESTAO not in sys.path:
    sys.path.append(_INGESTAO)
try:
    from planejar_blocos import montar_blocos, BLOCO_MAXIMO
except Exception:
    montar_blocos, BLOCO_MAXIMO = None, 20

SCHEMA_VERSION = "dsr.turma_plano.v1"
SCHEMA_CONFERENCIA = "dsr.conferencia.v1"
NOME_ARTEFATO = "TURMA_PLANO.json"
SCHEMA_PLANO = os.path.join(REFS, "turma_plano.schema.json")
CATALOGO_SQUADS = os.path.join(REFS, "squads.json")




BLOCO_PAGINAS = 20
OVERLAP_PAGINAS = 3

CAMADAS = ("leitor", "especialista")
MODELOS = ("opus", "sonnet", "haiku")



ROTAS = ("read_nativo", "local", "nuvem", "visual", "eluxi")




ROTAS_REMOTAS = ("nuvem", "eluxi")

SENSIBILIDADES = ("publico", "restrito", "sigiloso")


CONTEXTO_DA_ESPINHA = ("cronologia", "pedido", "partes")


class Contrato(Exception):
    """Uso/contrato inválido -> exit 2."""


def _s(valor):
    return isinstance(valor, str) and bool(valor.strip())


def _int(valor):
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().lstrip("-").isdigit():
        return int(valor.strip())
    return None


def _agora():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _teto_ondas(quantos, simultaneos):
    """Ondas necessárias para `quantos` disparos, `simultaneos` de cada vez (teto da divisão)."""
    if quantos <= 0:
        return 0
    simultaneos = simultaneos if (isinstance(simultaneos, int) and simultaneos > 0) else 1
    return -(-quantos // simultaneos)


def _base_paginacao(d):
    'Página em que a numeração do documento COMEÇA. Devolve (base, erro).'











    numeracao = d.get("numeracao")
    numeracao = numeracao.strip().lower() if _s(numeracao) else ""
    inicial = _int(d.get("pagina_inicial"))
    if numeracao == "autos":
        if inicial is None or inicial < 1:
            return None, ("numeracao 'autos' sem `pagina_inicial` >= 1 (recebido %r): a base "
                          "das folhas nao pode ser inventada" % (d.get("pagina_inicial"),))
        return inicial, None
    return 1, None


def _indexar_declarados(documentos_declarados):
    'Índice dos documentos que o ADVOGADO declarou no `SQUAD_STATE.json` (de onde vem o'





    if documentos_declarados is None:
        return None
    if not isinstance(documentos_declarados, list):
        raise Contrato("`documentos_declarados` deve ser lista (veio do SQUAD_STATE.json)")
    indice = {}
    for item in documentos_declarados:
        if not isinstance(item, dict) or not _s(item.get("id")):
            raise Contrato("documento declarado sem `id`: %r" % (item,))
        indice[item["id"].strip().casefold()] = item
    return indice


def _declaracao_de(indice, doc_id, arquivo):
    'A declaração do advogado para este documento, e COMO ela foi encontrada.'












    if indice is None:
        return None, ""
    base = os.path.basename(arquivo.strip()) if _s(arquivo) else ""
    for chave, como in ((doc_id, "id"), (arquivo, "arquivo"), (base, "nome_base")):
        if _s(chave):
            achado = indice.get(chave.strip().casefold())
            if achado is not None:
                return achado, como
    return None, ""


def _disparos_ja_gastos(aval):
    'Disparos que a SESSÃO já gastou. Devolve (quantos, origem) — (None, "") se não dá para saber.'










    if not isinstance(aval, dict):
        return None, ""
    ja = _int(aval.get("ja_disparados"))
    if ja is not None and ja >= 0:
        return ja, "aval_subagentes"
    return None, ""




def _validar_conferencia(conferencia):
    'O inventário é de OUTRO contrato (`dsr.conferencia.v1`), produzido pela ingestão.'



    if not isinstance(conferencia, dict):
        raise Contrato("inventario deve ser objeto `%s`" % SCHEMA_CONFERENCIA)
    if conferencia.get("schema_version") != SCHEMA_CONFERENCIA:
        raise Contrato("inventario com schema_version %r desconhecido (esperado %s)"
                       % (conferencia.get("schema_version"), SCHEMA_CONFERENCIA))
    if not isinstance(conferencia.get("documentos"), list):
        raise Contrato("inventario sem a lista `documentos`")


def _caso_opaco(valor):
    'O código opaco do caso (caso-<12 hex>) passa; outro valor (CNJ, nome da parte) vira vazio,'

    v = str(valor or "").strip()
    return v if re.fullmatch(r"caso-[0-9a-f]{12}", v) else ""


def _validar_oficios(oficios):
    'Ofício é DADO (vem de `squads.json`), mas dado malformado vira agente sem ofício.'



    if oficios is None:
        return []
    if not isinstance(oficios, list):
        raise Contrato("`oficios` deve ser lista")
    limpos = []
    vistos = set()
    for item in oficios:
        if not isinstance(item, dict) or not _s(item.get("id")):
            raise Contrato("cada oficio precisa de `id`: %r" % (item,))
        if item.get("camada") not in CAMADAS:
            raise Contrato("oficio %r sem `camada` em %s" % (item.get("id"), list(CAMADAS)))


        if item["id"].strip() in vistos:
            raise Contrato("oficio duplicado na turma: %r" % item["id"])
        vistos.add(item["id"].strip())
        limpos.append(item)
    return limpos


def _instrucao_leitura(rota, processo, arquivo, ini, fim):
    'Como o leitor da fatia obtem o teor — e como registra a leitura.'







    if rota == "eluxi":
        alvo = processo or "<processo ausente no inventario>"
        return {
            "ferramenta": "ler_markdown",
            "processo": processo or None,
            "instrucao": ('ler_markdown(processo="%s", pagina_inicio=%d, pagina_fim=%d); depois: '
                          'python3 dissero-ingestao/scripts/gerar_conferencia.py --acrescentar-leitura '
                          '--processo "%s" '
                          '--paginas-lidas %d-%d --trechos <json [{pagina, trecho_literal}] citados>'
                          % (alvo, ini, fim, alvo, ini, fim)),
        }
    return {
        "ferramenta": "Read",
        "processo": None,
        "instrucao": 'Read("%s", pages="%d-%d") — PDF com caminho no disco ou markdown extraido localmente'
                     % (arquivo or "<arquivo>", ini, fim),
    }


def _validar_fatiamento(bloco, overlap):
    'O cap de 20 páginas NÃO é tuning: é o teto de páginas consecutivas que o `ler_markdown`'






    bloco, overlap = _int(bloco), _int(overlap)
    if not bloco or bloco < 2:
        raise Contrato("`bloco_paginas` deve ser >= 2 (recebido %r)" % bloco)
    if bloco > BLOCO_MAXIMO:
        raise Contrato("`bloco_paginas` %d excede %d: e o cap de paginas consecutivas do "
                       "`ler_markdown`/`Read` — fatia maior nao pode ser lida"
                       % (bloco, BLOCO_MAXIMO))
    if overlap is None or overlap < 0:
        raise Contrato("`overlap` deve ser >= 0 (recebido %r)" % overlap)
    if overlap >= bloco:


        raise Contrato("`overlap` %d deve ser MENOR que `bloco_paginas` %d: sobreposicao que "
                       "iguala a fatia nao avanca" % (overlap, bloco))




def montar_espinha(conferencia, documentos):
    'O contexto mínimo que TODO leitor de fatia recebe junto do seu pedaço.'




    lista = []
    total = 0
    for d in documentos:
        paginas = _int(d.get("paginas_total"))
        if paginas and paginas > 0:
            total += paginas



        numeracao = d.get("numeracao")
        lista.append({
            "doc_id": str(d.get("doc_id") or ""),
            "arquivo": str(d.get("arquivo") or ""),
            "paginas_total": paginas,
            "leitura_status": str(d.get("leitura_status") or ""),
            "numeracao": numeracao.strip().lower() if _s(numeracao) else "",
            "pagina_inicial": _int(d.get("pagina_inicial")),
        })
    espinha = {
        "caso": _caso_opaco(conferencia.get("caso")),
        "documentos": lista,
        "paginas_totais": total,
        "faltando": [],
    }
    for chave in CONTEXTO_DA_ESPINHA:
        valor = conferencia.get(chave)
        if valor in (None, "", [], {}):
            espinha["faltando"].append(chave)
        else:
            espinha[chave] = valor
    bruto = json.dumps(espinha, ensure_ascii=False, sort_keys=True)
    espinha["ref"] = hashlib.sha256(bruto.encode("utf-8")).hexdigest()
    return espinha




def planejar(conferencia, oficios, teto, bloco_paginas=BLOCO_PAGINAS, overlap=OVERLAP_PAGINAS,
             max_simultaneos=None, aval=None, session_id=None, documentos_declarados=None,
             politica_dados=None, sem_paginacao_autorizado=False):
    'Plano da turma no nível do caso (`dsr.turma_plano.v1`).'










    _validar_conferencia(conferencia)
    oficios = _validar_oficios(oficios)
    _validar_fatiamento(bloco_paginas, overlap)
    declarados = _indexar_declarados(documentos_declarados)






    documentos, entradas_invalidas = [], []
    for i, d in enumerate(conferencia["documentos"]):
        if isinstance(d, dict):
            documentos.append(d)
        else:
            entradas_invalidas.append({"posicao": i, "tipo": type(d).__name__})
    espinha = montar_espinha(conferencia, documentos)
    avisos = []
    if politica_dados is not None:
        avisos.append("politica de dados do squad: %r — ela nao rebaixa rota por si; quem "
                      "rebaixa e a `sensibilidade` declarada por documento"
                      % (politica_dados,))

    leitores = [o for o in oficios if o.get("camada") == "leitor"]
    especialistas = [o for o in oficios if o.get("camada") == "especialista"]
    oficio_leitor = leitores[0]["id"].strip() if leitores else None
    if oficio_leitor is None:
        avisos.append("nenhum oficio de camada `leitor` informado: as fatias saem sem assento "
                      "atribuido (informe --squad ou --oficios)")




    leitores_ociosos = [o["id"].strip() for o in leitores[1:]]
    if leitores_ociosos:
        avisos.append("oficio(s) de leitor sem fatia atribuida: %s — as fatias vao todas para "
                      "%r (o plano nao distribui fatias entre varios leitores)"
                      % (", ".join(leitores_ociosos), oficio_leitor))

    fatias, planejados, nao_lidos, sem_paginacao = [], [], [], []
    nao_declarados, sem_base = [], []

    for d in documentos:
        doc_id = str(d.get("doc_id") or "")
        arquivo = str(d.get("arquivo") or "")


        if str(d.get("leitura_status") or "") == "nao_lido":
            nao_lidos.append(doc_id)
            continue
        paginas = _int(d.get("paginas_total"))
        if not paginas or paginas < 1:
            sem_paginacao.append(doc_id)
            continue
        base, erro_base = _base_paginacao(d)
        if base is None:
            sem_base.append("%s: %s" % (doc_id, erro_base))
            continue




        declaracao, como_casou = _declaracao_de(declarados, doc_id, arquivo)
        if declaracao is not None and como_casou == "nome_base":


            avisos.append("documento %s casou com a declaracao do advogado pelo "
                          "NOME DO ARQUIVO, nao pelo id: confira se e o mesmo "
                          "documento" % (doc_id or arquivo))
        if declaracao is None and declarados is not None:

            nao_declarados.append(doc_id)
            avisos.append("documento %s nao foi declarado pelo advogado no estado do squad: a "
                          "sensibilidade dele e DESCONHECIDA (registre com `squad.py documento "
                          "--id %s --sensibilidade ... --rota ...`); a fatia NAO e presumida "
                          "sigilosa" % (doc_id, doc_id or arquivo))
        sensibilidade = str((declaracao or {}).get("sensibilidade")
                            or d.get("sensibilidade") or "")
        sigiloso = sensibilidade == "sigiloso"

        rota = d.get("rota") if d.get("rota") in ROTAS else None
        if rota is None:
            avisos.append("documento %s com rota %r fora do contrato: fatia vai por `local`"
                          % (doc_id, d.get("rota")))
            rota = "local"
        rebaixada = False
        if sigiloso and rota in ROTAS_REMOTAS:


            avisos.append("documento %s e sigiloso (declarado no estado do squad): rota %r "
                          "REBAIXADA para `local` — rota remota sobe o documento para fora da "
                          "maquina do escritorio. A fatia le o teor ja extraido localmente; "
                          "documento escaneado sem camada de texto nao tem leitor local, e ai "
                          "a decisao e do advogado" % (doc_id, rota))
            rota, rebaixada = "local", True
        elif (declaracao is not None and declaracao.get("rota") == "local"
                and declaracao.get("autorizado_remoto") is not True and rota in ROTAS_REMOTAS):


            avisos.append("documento %s foi declarado com rota `local` pelo advogado: rota %r "
                          "do inventario REBAIXADA para `local`" % (doc_id, rota))
            rota, rebaixada = "local", True

        if montar_blocos is None:
            raise Contrato("modulo irmao `planejar_blocos.py` (dissero-ingestao) ausente: o "
                           "fatiamento nao pode ser refeito aqui sem produzir duas maquinas "
                           "para o mesmo fato — rode `python sincronizar_shared.py --sync`")
        blocos = montar_blocos(paginas, pagina_inicial=base, bloco=bloco_paginas,
                               overlap=overlap)
        planejados.append(doc_id)
        numeracao = d.get("numeracao")
        processo = str(d.get("processo") or "")
        if rota == "eluxi" and not processo:
            avisos.append("documento %s tem rota eluxi mas o inventario nao traz `processo`: o leitor "
                          "nao consegue chamar ler_markdown — registre-o com "
                          "`dissero-ingestao/scripts/gerar_conferencia.py --indice-eluxi "
                          "--processo <id>`" % doc_id)
        for b in blocos:
            ini, fim = b["paginas"]
            fatias.append({
                "fatia_id": "%s-p%d-%d" % (doc_id, ini, fim),




                "leitura": _instrucao_leitura(rota, processo, arquivo, ini, fim),
                "doc_id": doc_id,
                "arquivo": arquivo,
                "sha256_arquivo": str(d.get("sha256_arquivo") or ""),
                "pagina_inicial": ini,
                "pagina_final": fim,
                "total_paginas": fim - ini + 1,
                "numeracao": numeracao.strip().lower() if _s(numeracao) else "",
                "pagina_inicial_documento": base,
                "sigiloso": bool(sigiloso),
                "sensibilidade_declarada": sensibilidade or None,
                "rota": rota,
                "rota_rebaixada": bool(rebaixada),
                "oficio": oficio_leitor,
                "espinha_ref": espinha["ref"],
            })



    faltando = []
    paginas_planejadas = 0
    for d in documentos:
        doc_id = str(d.get("doc_id") or "")
        if doc_id not in planejados:
            continue
        paginas = _int(d.get("paginas_total")) or 0
        paginas_planejadas += paginas



        base = _base_paginacao(d)[0] or 1
        esperado = set(range(base, base + paginas))
        coberto = set()
        for f in fatias:
            if f["doc_id"] == doc_id:
                coberto.update(range(f["pagina_inicial"], f["pagina_final"] + 1))
        buraco = sorted(esperado - coberto)
        if buraco:
            faltando.append({"doc_id": doc_id, "paginas": buraco[:20],
                             "total_faltando": len(buraco)})

    total_fatias = len(fatias)
    total_agentes = total_fatias + len(especialistas)


    ja_disparados, origem_contagem = _disparos_ja_gastos(aval)
    teto_cheio = _int(teto) or 0
    if ja_disparados is None:
        restante = teto_cheio
    else:
        restante = max(0, teto_cheio - ja_disparados)
        if ja_disparados:
            avisos.append("a sessao ja gastou %d disparo(s) de subagente (fonte: %s): do teto "
                          "de %d resta(m) %d — o teto do §13 e orcamento da SESSAO, nao desta "
                          "turma" % (ja_disparados, origem_contagem, teto_cheio, restante))
    simult = _int(max_simultaneos)
    if simult and simult > 0:
        origem = "informado pelo aval"
    else:
        simult = max(1, _int(teto) or 1)
        origem = "teto do aval (split simultaneos x ondas nao informado)"




    ondas = _teto_ondas(total_fatias, simult)

    plano = {
        "schema_version": SCHEMA_VERSION,
        "caso": _caso_opaco(conferencia.get("caso")),
        "gerado_em": _agora(),
        "acao": "planejada",
        "total_fatias": total_fatias,
        "total_agentes": total_agentes,



        "agentes_apos_checkpoint": len(especialistas),
        "ondas": ondas,
        "bloco_paginas": int(bloco_paginas),
        "overlap": int(overlap),
        "espinha": espinha,
        "fatias": fatias,
        "oficios": [{
            "id": str(o.get("id")).strip(),
            "titulo": str(o.get("titulo") or ""),
            "model": o.get("model") if o.get("model") in MODELOS else None,
            "camada": o.get("camada"),


            "agentes": (total_fatias if str(o.get("id")).strip() == oficio_leitor else 0)
                       if o.get("camada") == "leitor" else 1,
        } for o in oficios],
        "cobertura": {
            "paginas_planejadas": paginas_planejadas,
            "documentos_planejados": planejados,
            "nao_lidos": nao_lidos,
            "sem_paginacao": sem_paginacao,
            "sem_paginacao_autorizado": bool(sem_paginacao_autorizado and sem_paginacao),
            "entradas_invalidas": entradas_invalidas,
            "nao_declarados": nao_declarados,
            "completa": not faltando,
            "faltando": faltando,
        },
        "aval_subagentes": {
            "teto_autorizado": teto_cheio,
            "ja_disparados": ja_disparados,
            "restante": restante,
            "origem_da_contagem": origem_contagem,
            "max_simultaneos_considerado": simult,
            "origem_do_simultaneo": origem,
            "detalhe": aval if isinstance(aval, dict) else {},
        },
        "avisos": avisos,
        "motivo": "",
    }

    motivos = []
    if not documentos:
        motivos.append("inventario sem documento: nao ha o que planejar")
    if entradas_invalidas:
        motivos.append("entrada(s) fora do contrato na lista `documentos` (posicao/tipo: %s) — "
                       "nao viram fatia e nao podem sumir caladas"
                       % ", ".join("%d/%s" % (x["posicao"], x["tipo"])
                                   for x in entradas_invalidas))
    if nao_lidos:
        motivos.append("documento(s) NAO LIDO(S) no inventario: %s — leitura sobre o que "
                       "ninguem leu e ficcao" % ", ".join(nao_lidos))
    if sem_base:
        motivos.append("documento(s) com numeracao 'autos' sem base de folha: %s — o contrato "
                       "ja exige `pagina_inicial` ai" % "; ".join(sem_base))
    if sem_paginacao and not sem_paginacao_autorizado:




        motivos.append("documento(s) sem paginacao: %s — fatiar sem pagina e inventar "
                       "fronteira; para seguir SEM ler esse(s) arquivo(s), autorize "
                       "expressamente (--sem-paginacao-autorizado) e a decisao fica gravada "
                       "no plano" % ", ".join(sem_paginacao))
    elif sem_paginacao:
        avisos.append("documento(s) sem paginacao SEGUEM FORA DO LEQUE por autorizacao "
                      "expressa: %s — ninguem vai ler esse(s) arquivo(s) nesta turma"
                      % ", ".join(sem_paginacao))
    if faltando:
        motivos.append("cobertura INCOMPLETA: %s — pagina fora de fatia e conteudo perdido "
                       "em silencio" % ", ".join(x["doc_id"] for x in faltando))
    if documentos and not fatias:


        motivos.append("nenhuma fatia foi planejada: leque inexistente nao e leque completo — "
                       "reconciliar sobre o conjunto vazio fecha sempre")
    if total_agentes > restante:
        if ja_disparados:
            motivos.append("%d agente(s) previsto(s) (%d de leitura + %d apos o checkpoint) "
                           "excede(m) o RESTANTE de %d do teto de %d (§13): a sessao ja gastou "
                           "%d disparo(s)" % (total_agentes, total_fatias, len(especialistas),
                                              restante, teto_cheio, ja_disparados))
        else:
            motivos.append("%d agente(s) previsto(s) (%d de leitura + %d apos o checkpoint) "
                           "excede(m) o teto autorizado de %s (§13)"
                           % (total_agentes, total_fatias, len(especialistas), teto))



        raiz_do_aval = ""
        if isinstance(aval, dict) and _s(aval.get("caminho")):
            raiz_do_aval = os.path.dirname(os.path.abspath(aval["caminho"]))
        simult_aval = PADRAO_SIMULTANEOS or 2
        plano["comando_aval"] = (
            'python scripts/autorizar_subagentes.py --session-id %s%s --max-simultaneos %d '
            '--ondas %d --escopo "turma do caso: %d fatias de leitura + %d especialista(s) '
            'apos o checkpoint"'
            % (session_id or "<id da sessao>",
               (' --raiz "%s"' % raiz_do_aval) if raiz_do_aval else "",
               simult_aval,
               _teto_ondas(total_agentes + (ja_disparados or 0), simult_aval),
               total_fatias, len(especialistas)))

    if motivos:
        plano["acao"] = "escalar"
        plano["erro"] = " | ".join(motivos)
        plano["motivo"] = ("o advogado decide ANTES de gastar: metade do leque disparado e "
                           "depois barrado e desperdicio puro")
    else:
        plano["motivo"] = ("%d fatia(s) cobrindo %d pagina(s) de %d documento(s); leque e o "
                           "PADRAO no nivel do caso, e a leitura direta e que precisaria de "
                           "motivo" % (total_fatias, paginas_planejadas, len(planejados)))
    return plano


def validar_plano(plano, caminho_schema=None):
    'Confere o plano contra o contrato PUBLICADO. Devolve lista de problemas (vazia = ok).'



    if validar_schema is None:
        return ["modulo irmao `schema_mini.py` ausente: o contrato nao pode ser conferido"]
    alvo = caminho_schema or SCHEMA_PLANO
    try:
        with open(alvo, encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, ValueError) as exc:
        return ["schema %s ilegivel: %s" % (alvo, exc)]
    return validar_schema(plano, schema)




def _ler_json(caminho, rotulo):
    try:
        with open(caminho, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise Contrato("%s ilegivel/JSON invalido: %s" % (rotulo, exc))


def _oficios_do_squad(squad_id, caminho=None):
    catalogo = _ler_json(caminho or CATALOGO_SQUADS, "catalogo de squads")
    if not isinstance(catalogo, dict) or not isinstance(catalogo.get("squads"), list):
        raise Contrato("catalogo de squads sem a lista `squads`")
    for item in catalogo["squads"]:
        if isinstance(item, dict) and item.get("id") == squad_id:
            return item.get("oficios") or []
    raise Contrato("squad %r nao existe no catalogo" % squad_id)


def _resumo(plano):
    'O resumo legível é o modo DEFAULT do CLI — é ele que o advogado lê.'




    a = plano.get("aval_subagentes") or {}
    det = a.get("detalhe") if isinstance(a.get("detalhe"), dict) else {}
    linhas = ["acao: %s" % plano["acao"],
              "fatias: %d · agentes: %d (%d apos o checkpoint) · ondas de leitura: %d"
              % (plano["total_fatias"], plano["total_agentes"],
                 plano.get("agentes_apos_checkpoint") or 0, plano["ondas"]),
              "cobertura: %d pagina(s) em %d documento(s) · completa=%s"
              % (plano["cobertura"]["paginas_planejadas"],
                 len(plano["cobertura"]["documentos_planejados"]),
                 plano["cobertura"]["completa"])]
    linhas.append("aval: %s · teto %s · ja gastos %s · resta %s · escopo: %s"
                  % (det.get("caminho") or "—", a.get("teto_autorizado"),
                     "?" if a.get("ja_disparados") is None else a.get("ja_disparados"),
                     a.get("restante"), det.get("escopo") or "(nao declarado)"))





    if det.get("aviso_paridade"):
        linhas.append("ATENCAO · o teto acima NAO obriga o gate: %s" % det["aviso_paridade"])
    if plano.get("erro"):
        linhas.append("ESCALAR: %s" % plano["erro"])
    if plano.get("comando_aval"):
        linhas.append("comando do aval (as `--ondas` cobrem TODOS os agentes, nao so as "
                      "ondas de leitura acima):")
        linhas.append(plano["comando_aval"])
    for aviso in plano.get("avisos") or []:
        linhas.append("aviso: %s" % aviso)
    return "\n".join(linhas)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Planeja a turma de agentes no nivel do CASO (uma fatia por agente)")
    ap.add_argument("--conferencia", required=True,
                    help="CONFERENCIA.json (dsr.conferencia.v1) — o inventario do que foi lido")
    ap.add_argument("--squad", help="id do squad em references/squads.json, de onde saem os oficios")
    ap.add_argument("--oficios", help="JSON com a lista de oficios (alternativa a --squad)")
    ap.add_argument("--catalogo", help="caminho alternativo do catalogo de squads")
    ap.add_argument("--bloco", type=int, default=BLOCO_PAGINAS,
                    help="paginas por fatia (default %d = cap do ler_markdown)" % BLOCO_PAGINAS)
    ap.add_argument("--overlap", type=int, default=OVERLAP_PAGINAS,
                    help="paginas de sobreposicao entre fatias vizinhas (default %d)"
                         % OVERLAP_PAGINAS)
    ap.add_argument("--session-id", dest="session_id",
                    help="id da sessao do harness — sem ele o aval §13 nao e conferido")
    ap.add_argument("--raiz", help="forca a pasta do caso (default: caso_raiz.py)")
    ap.add_argument("--estado", help="SQUAD_STATE.json — de onde vem a `sensibilidade` "
                                     "DECLARADA de cada documento (o sigilo nao vem do "
                                     "inventario: o dsr.conferencia.v1 nao tem esse campo)")
    ap.add_argument("--sem-paginacao-autorizado", dest="sem_paginacao_autorizado",
                    action="store_true",
                    help="autoriza EXPRESSAMENTE seguir com documento(s) sem paginacao fora do "
                         "leque; eles continuam nomeados e a decisao fica gravada no plano")
    ap.add_argument("--json", action="store_true",
                    help="imprime o plano inteiro em JSON (default: resumo legivel)")
    args = ap.parse_args(argv)

    try:
        conferencia = _ler_json(args.conferencia, "inventario")
        if _s(args.oficios):
            oficios = _ler_json(args.oficios, "oficios")
        elif _s(args.squad):
            oficios = _oficios_do_squad(args.squad.strip(), args.catalogo)
        else:
            oficios = []

        if ler_aval is None:
            raise Contrato("modulo irmao `aval_subagentes.py` ausente: o aval do §13 nao pode "
                           "ser lido — rode `python sincronizar_shared.py --sync`")
        teto, detalhe = ler_aval(args.session_id, args.raiz)

        declarados, politica = None, None
        if _s(args.estado):
            estado = _ler_json(args.estado, "estado do squad")
            if not isinstance(estado, dict):
                raise Contrato("estado do squad deve ser objeto")
            declarados = estado.get("documentos") or []
            politica = estado.get("politica_dados")

        plano = planejar(conferencia, oficios, teto, bloco_paginas=args.bloco,
                         overlap=args.overlap,
                         max_simultaneos=detalhe.get("max_simultaneos"),
                         aval=detalhe, session_id=args.session_id,
                         documentos_declarados=declarados, politica_dados=politica,
                         sem_paginacao_autorizado=args.sem_paginacao_autorizado)
    except Contrato as exc:
        print(json.dumps({"ok": False, "erro": str(exc)}, ensure_ascii=False))
        return 2



    problemas = validar_plano(plano)
    if problemas:
        print(json.dumps({"ok": False, "erro": "plano fora do contrato %s" % SCHEMA_VERSION,
                          "problemas": problemas[:10]}, ensure_ascii=False))
        return 2

    print(json.dumps(plano, ensure_ascii=False) if args.json else _resumo(plano))
    return 1 if plano["acao"] == "escalar" else 0


if __name__ == "__main__":
    sys.exit(main())
