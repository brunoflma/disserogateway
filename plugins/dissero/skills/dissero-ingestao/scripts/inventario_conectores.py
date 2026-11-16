#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'inventario_conectores.py — sozinho por padrão, melhor acompanhado: qual conector atende cada capacidade.'


















































from __future__ import annotations

import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

SCHEMA = "dsr.inventario_conectores.v1"
PREFERENCIAS = ("auto", "nao_usar", "preferir")









CONECTORES = {
    "eluxi": {
        "rotulo": "Eluxi — OCR da casa: leitura de documento escaneado ou volumoso em nuvem, server-side",
        "casa": True,
        "assinaturas": ("iniciar_ingestao", "consultar_catalogo", "consultar_ingestao",
                        "ler_markdown", "buscar_trechos", "consultar_seguranca", "reindexar_indice"),
        "capacidades": ("leitura_nuvem", "seguranca_teor"),
        "consultar_antes": True,
    },
    "fons": {
        "rotulo": "Fons — caderno do caso (da casa), com guia de uso e controle de acesso próprios",
        "casa": True,

        "preferencia_no_perfil": False,


        "assinaturas": ("listar_notebooks", "obter_notebook", "perguntar_ao_notebook", "consultar_resposta_notebook",
                        "ler_texto_fonte_notebook", "listar_fontes_notebook", "resumir_notebook",
                        "ler_historico_notebook", "preparar_consulta_documental", "associar_gemini_notebook",
                        "preparar_fonte_gemini_notebook"),
        "capacidades": ("caderno_caso",),
        "consultar_antes": True,
    },
    "zetema": {
        "rotulo": "Zetema — pesquisa jurídica da casa: fontes oficiais ao vivo, documento oficial por hash, jurimetria, "
                  "CNPJ público",
        "casa": True,



        "assinaturas": ("verificar_documento_oficial", "obter_documento_oficial", "ler_trecho_documento_oficial",
                        "consultar_jurimetria", "consultar_capacidades_fontes",
                        "resolver_numero_mascarado", "consultar_status_fontes",
                        "pesquisar_caso_juridico", "pesquisar_precedentes_qualificados",
                        "conferir_evidencias_pesquisa", "ler_documento_jus", "consultar_fontes_publicas_mcp_ai",
                        "pesquisar_acervo_legislativo", "ler_dispositivo_acervo", "ler_trecho_acervo_legislativo",
                        "navegar_portal_protegido", "consultar_status_acervo", "pesquisar_catalogo_normas",
                        "consultar_metadados_norma"),
        "capacidades": ("descoberta_jurisprudencia", "confirmacao_oficial", "legislacao", "jurimetria",
                        "diligencia_cadastral"),
    },
    "cnpja": {
        "rotulo": "CNPJA — diligência cadastral (CNPJ, sócios, comprovantes)",
        "casa": True,
        "assinaturas": ("consultar_saldo_cnpja", "consultar_empresa_cnpja", "consultar_receita_federal_cnpj"),
        "capacidades": ("diligencia_cadastral",),
    },






    "jusratio": {
        "rotulo": "Jusratio — pesquisa jurisprudencial (terceiro)",
        "casa": False,
        "assinaturas": ("pesquisar_documentos", "obter_resultado_pesquisa", "obter_documento_chunk",
                        "read_decisao_pdf_chunk", "listar_overruling_por_tema", "timeline_decisoes",
                        "solicitar_previa_autos", "confirmar_solicitacao_autos", "consultar_pedido_autos",
                        "listar_pedidos_autos", "cancelar_pedido_autos"),
        "capacidades": ("descoberta_jurisprudencia",),
        "cota": "créditos do plano Pro/Simples; em monthly_quota_exceeded ou research_* com retryable=false, "
                "não repetir; a busca é assíncrona (job_id em obter_resultado_pesquisa, sem refazer a pesquisa); "
                "pedido de autos consome créditos e só com o sim do advogado à prévia",
    },
    "iajus": {
        "rotulo": "IAJUS — pesquisa jurídica Lex (terceiro)",
        "casa": False,
        "assinaturas": ("abrir_painel_iajus", "pesquisa_juridica_lex", "pesquisa_profunda_lex",
                        "consultar_tarefa_lex", "cancelar_tarefa_lex", "consultar_conversa_lex",
                        "listar_conversas_lex", "consultar_ontologia_ojbu", "consultar_cobertura_acervo",
                        "consultar_cobertura_legislacao", "localizar_norma_fonte_oficial",
                        "explorar_relacoes_juridicas"),
        "capacidades": ("descoberta_jurisprudencia",),
        "cota": "Beta: pesquisa comum 3 por dia e 10 por semana; pesquisa profunda 1 por dia e 7 por semana, "
                "somadas entre todos os clientes da conta; em quota_esgotada, não repetir",
    },
    "jurisprudenciaia": {




        "rotulo": "JurisprudênciaIA avulso — servidor da casa, o mesmo que o Zetema integra como jurisprudenciaia_*",
        "casa": True,
        "integrado_ao_zetema": True,
        "preferencia_no_perfil": False,
        "assinaturas": ("consultar_jurisprudenciaia", "buscar_precedentes_qualificados", "analisar_tese_juridica",
                        "comparar_teses_juridicas", "linha_do_tempo_precedentes", "listar_overruling_tema",
                        "historico_alteracoes_norma", "buscar_citacoes_dispositivo", "analisar_jurimetria"),
        "capacidades": ("descoberta_jurisprudencia",),
    },
    "juspilot": {
        "rotulo": "Juspilot — jurisprudência de tribunais superiores (terceiro)",
        "casa": False,
        "assinaturas": ("search_jurisprudencia", "browse_jurisprudencia", "get_jurisprudencia",
                        "related_jurisprudencia", "facets_jurisprudencia"),
        "capacidades": ("descoberta_jurisprudencia",),
    },
    "jusia": {"rotulo": "JusIA (Jusbrasil) — terceiro, ferramentas não confirmadas", "casa": False,
              "assinaturas": (), "capacidades": ("descoberta_jurisprudencia",)},
    "minutaia": {"rotulo": "MinutaIA (Jusbrasil) — terceiro, ferramentas não confirmadas", "casa": False,
                 "assinaturas": (), "capacidades": ("descoberta_jurisprudencia",)},
    "fundamentaia": {"rotulo": "FundamentaIA — terceiro, ferramentas não confirmadas", "casa": False,
                     "assinaturas": (), "capacidades": ("descoberta_jurisprudencia",)},
    "fidelia": {"rotulo": "Fidelia — terceiro, MCP não confirmado", "casa": False,
                "assinaturas": (), "capacidades": ("descoberta_jurisprudencia",)},
    "jurisprudencias_ai": {"rotulo": "Jurisprudências.ai — terceiro, ferramentas não confirmadas", "casa": False,
                           "assinaturas": (), "capacidades": ("descoberta_jurisprudencia",)},
    "exordial": {"rotulo": "Exordial Jurisprudência — terceiro, ferramentas não confirmadas", "casa": False,
                 "assinaturas": (), "capacidades": ("descoberta_jurisprudencia",)},
    "jurisconsulto": {"rotulo": "Jurisconsulto — terceiro, ferramentas não confirmadas", "casa": False,
                      "assinaturas": (), "capacidades": ("descoberta_jurisprudencia",)},


    "wikijuridica": {"rotulo": "Wikijurídica — terceiro, ferramentas só em catálogo", "casa": False,
                     "assinaturas": (), "capacidades": ("descoberta_jurisprudencia",)},
    "mcp_ai": {"rotulo": "MCP.ai Jurisprudência — terceiro, ferramentas não confirmadas", "casa": False,
               "assinaturas": (), "capacidades": ("descoberta_jurisprudencia",)},
}



PREFIXOS_EXCLUSIVOS = {"jurisprudenciaia_": "zetema"}


SEM_ASSINATURA_CONHECIDA = tuple(c for c, v in CONECTORES.items() if not v["assinaturas"])


CASA_PESQUISA = "zetema"
AVULSO_DA_CASA = "jurisprudenciaia"
CAPACIDADES_DE_PESQUISA = ("descoberta_jurisprudencia", "confirmacao_oficial", "legislacao", "jurimetria")
CRITERIO_INSUFICIENCIA = ("insuficiente = nenhum precedente útil para a tese, nenhum do tribunal de destino, sem link "
                          "oficial ou inteiro teor para confirmar, ou lacuna de cobertura declarada pela ferramenta")
ORIENTACAO_ZETEMA = ("o Zetema, a pesquisa jurídica da casa, não está conectado nesta sessão: se a pesquisa ficar "
                     "insuficiente, oriente o advogado a conectá-lo (no claude.ai, em Configurações → Conectores; no "
                     "Claude Code, pelo conector zetema do plugin) e siga com o que houver; nada é inventado")
REGRA_TERCEIROS = ("o que vier dos terceiros é pista de descoberta (discovery.provider e discovery.url) e passa pela "
                   "mesma confirmação oficial; uma rodada por tese, sem laço, respeitando a cota de cada um")



CONSULTAR_ANTES = {
    "eluxi": {
        "assunto": "leitura de documento em nuvem (OCR) na ingestão",
        "pergunta": "O Eluxi está conectado na sua conta. Quer que eu use a leitura dele para este documento?",
        "registro": "antes de perguntar, dissero-ingestao/scripts/consulta_conector.py mostrar --conector eluxi "
                    "--conectado; sim: o aval por autorizar_ingestao.py (é o que o gate_ingestao confere); "
                    "não: consulta_conector.py registrar --resposta nao, e a rota local; vale para o caso",
        "excecao": "documento sigiloso segue pela rota local, sem perguntar pelo Eluxi",
    },
    "fons": {
        "assunto": "caderno do caso (estudo dos autos)",
        "pergunta": "O Fons está conectado na sua conta. Quer que eu use o caderno do caso dele para estudar estes autos?",
        "registro": "antes de perguntar, dissero-ingestao/scripts/consulta_conector.py mostrar --conector fons "
                    "--conectado; a resposta se grava com consulta_conector.py registrar --resposta sim|nao e vale "
                    "para o caso; não: os autos são lidos pela dissero-ingestao",
        "excecao": "",
    },
}




ROTA_PUBLICA_CNPJ = ("usar zetema, só pela rota pública de CNPJ que ele registra "
                     "(`consultar_estabelecimento_cnpj_publico`, `consultar_cep_cnpja_publico`): dados públicos "
                     "apenas (razão social, natureza jurídica, sede, situação cadastral e quadro de sócios), sem "
                     "saldo, sem comprovante e sem pessoa física; o que só a rota paga do CNPJá entrega "
                     "(comprovante em PDF, CCC, Simples/MEI, SUFRAMA, busca por nome) vira [COMPLETAR] para o advogado")







CAPACIDADES = {
    "leitura_nuvem": {
        "rotulo": "Leitura de documento escaneado ou volumoso em nuvem",
        "ordem": ("eluxi",),
        "embarcada": "rota LOCAL da dissero-ingestao: parse_local.py (Word pela stdlib, PDF com camada de texto) "
                     "e leitura por partes (planejar_blocos.py); escaneado sem conector, conferência visual "
                     "(pdftoppm + leitura da imagem) ou escalar ao advogado",
        "instrucao_por_conector": {"eluxi": "perguntar antes ao advogado (consultar_antes); com o sim, usar eluxi; "
                                            "com o não, a rota local; sigiloso, a rota local sem perguntar"},
        "sem_conector": "degradada",

        "aviso": "sem leitura em nuvem não há OCR: documento escaneado só se lê por imagem, página a página, ou "
                 "escala ao advogado; documento volumoso é lido por partes (planejar_blocos.py); o ilegível "
                 "nunca é improvisado",
    },
    "seguranca_teor": {
        "rotulo": "Varredura de instrução oculta no teor extraído",
        "ordem": ("eluxi",),
        "embarcada": "detectar_injecao.py e varredura_documento.py locais (rodam SEMPRE; o conector é segunda opinião)",
        "sem_conector": "embarcada", "aviso": "",
    },
    "descoberta_jurisprudencia": {
        "rotulo": "Descoberta de precedentes",
        "ordem": ("zetema",),
        "terceiros": True,
        "embarcada":"fontes públicas por script (normas_leg_br.py, consultar_dou.py) e o julgado que o advogado "
                     "indicar; a confirmação oficial continua embarcada",
        "sem_conector": "degradada",
        "aviso": "sem conector de descoberta, a pesquisa parte do que o advogado indicar; nada é inventado",
    },
    "confirmacao_oficial": {
        "rotulo": "Confirmação do julgado na fonte oficial",
        "ordem": ("zetema",),
        "embarcada": "verificar_citacao.py contra fontes_oficiais.json (host exato, hash) + folha de atestação humana "
                     "(folha_atestacao.py / registrar_confirmacao_manual.py)",
        "sem_conector": "embarcada", "aviso": "",
    },
    "legislacao": {
        "rotulo": "Legislação: redações e vigência",
        "ordem": ("zetema",),
        "embarcada": "normas_leg_br.py (todas as redações do dispositivo, vigência marcada)",
        "sem_conector": "embarcada", "aviso": "",
    },
    "jurimetria": {
        "rotulo": "Jurimetria e capa/movimentos do DataJud",
        "ordem": ("zetema",),
        "embarcada": "datajud_client.py com a chave pública do CNJ embutida (tempo_tramitacao.py, admissibilidade_numero.py)",
        "sem_conector": "embarcada", "aviso": "",
    },
    "diligencia_cadastral": {
        "rotulo": "Qualificação de pessoa jurídica (razão social, sede, sócios)",


        "ordem": ("cnpja", "zetema"),
        "instrucao_por_conector": {"zetema": ROTA_PUBLICA_CNPJ},
        "embarcada": "",
        "sem_conector": "lacuna",
        "aviso": "sem conector cadastral a qualificação vira [COMPLETAR] no briefing e o advogado a fornece; o plugin não pergunta o que a fonte responderia",
    },
    "caderno_caso": {
        "rotulo": "Caderno do caso: estudo dos autos em caderno",
        "ordem": ("fons",),
        "instrucao_por_conector": {"fons": "perguntar antes ao advogado (consultar_antes); com o sim, usar fons "
                                           "(o que ele responde é apoio, conferido nos autos antes da peça); com o "
                                           "não, ler os autos pela dissero-ingestao"},

        "embarcada": "ler os autos pela dissero-ingestao; o cenário do caderno não é oferecido nem mencionado",
        "sem_conector": "embarcada", "aviso": "",
    },
}

_ASSINATURA_PARA_CONECTOR = {}
for _cid, _c in CONECTORES.items():
    for _s in _c["assinaturas"]:
        if _s in _ASSINATURA_PARA_CONECTOR:
            raise ValueError(f"assinatura ambígua entre conectores: {_s}")
        _ASSINATURA_PARA_CONECTOR[_s] = _cid
for _pref, _cid in PREFIXOS_EXCLUSIVOS.items():
    if _cid not in CONECTORES:
        raise ValueError(f"prefixo exclusivo de conector inexistente: {_pref}")
    for _s in _ASSINATURA_PARA_CONECTOR:
        if _s.startswith(_pref):
            raise ValueError(f"assinatura cai no prefixo exclusivo de {_cid}: {_s}")
for _capid in CAPACIDADES_DE_PESQUISA:
    if CASA_PESQUISA not in CAPACIDADES[_capid]["ordem"]:
        raise ValueError(f"capacidade de pesquisa sem a casa: {_capid}")
for _cid in CONSULTAR_ANTES:
    if not CONECTORES[_cid].get("consultar_antes"):
        raise ValueError(f"pergunta prévia de conector sem a marca consultar_antes: {_cid}")


def sufixo(nome):
    """`mcp__servidor__tool` → `tool`; nome já nu → ele mesmo. Nunca olha o id do servidor."""
    n = (nome or "").strip()
    if n.startswith("mcp__") and n.count("__") >= 2:
        return n.split("__")[-1]
    return n


def identificar(nome):
    """Conector a que a ferramenta pertence (assinatura exata ou prefixo exclusivo), ou None."""
    s = sufixo(nome)
    cid = _ASSINATURA_PARA_CONECTOR.get(s)
    if cid:
        return cid
    for pref, dono in PREFIXOS_EXCLUSIVOS.items():
        if s.startswith(pref) and len(s) > len(pref):
            return dono
    return None


def conectores_presentes(ferramentas):
    presentes = set()
    for f in ferramentas or ():
        cid = identificar(f)
        if cid:
            presentes.add(cid)
    return presentes


def _terceiros_da(capid):
    """Terceiros de pesquisa que atendem a capacidade (nunca a casa)."""
    return [c for c, v in CONECTORES.items() if not v["casa"] and capid in v["capacidades"]]


def preferencias_do_perfil(perfil):
    """`conectores.<id>` do perfil → dict id→preferência válida; valor inválido cai em `auto` e é anotado."""
    prefs, avisos = {}, []
    bloco = (perfil or {}).get("conectores") if isinstance(perfil, dict) else None
    if not isinstance(bloco, dict):
        return prefs, avisos
    for cid, val in bloco.items():
        if cid.startswith("_"):
            continue
        if cid not in CONECTORES:
            avisos.append(f"perfil: conector desconhecido '{cid}' ignorado")
            continue
        v = str(val or "").strip().lower()
        if v not in PREFERENCIAS:
            avisos.append(f"perfil: preferência inválida '{val}' para {cid}; tratada como auto")
            v = "auto"
        prefs[cid] = v
    return prefs, avisos


def _ordem_com_preferencia(cap, prefs):
    'Ordem da capacidade depois do `preferir` do perfil. O preferido vai à frente só entre os'



    parciais = cap.get("instrucao_por_conector") or {}
    ordem = list(cap["ordem"])
    completos = sorted((c for c in ordem if c not in parciais),
                       key=lambda c: 0 if prefs.get(c) == "preferir" else 1)
    fila = iter(completos)
    return [c if c in parciais else next(fila) for c in ordem]


def _rota_descoberta(capid, livre, presentes, prefs):
    'Descoberta (16/11/2026): terceiros presentes = principal; a casa (o Zetema, ou o avulso quando'

    principais = sorted((c for c in _terceiros_da(capid) if livre(c)),
                        key=lambda c: (0 if prefs.get(c) == "preferir" else 1, c))
    recusados = [c for c in _terceiros_da(capid) + [CASA_PESQUISA, AVULSO_DA_CASA]
                 if c in presentes and not livre(c)]
    casa_id = CASA_PESQUISA if livre(CASA_PESQUISA) else (AVULSO_DA_CASA if livre(AVULSO_DA_CASA) else None)
    redundantes = [AVULSO_DA_CASA] if casa_id == CASA_PESQUISA and livre(AVULSO_DA_CASA) else []
    papel = None if not casa_id else ("complemento" if principais else "principal")
    conectores = principais + ([casa_id] if casa_id else [])
    nomes = ", ".join(principais)
    if principais and casa_id:
        instrucao = (f"usar primeiro {nomes} (pesquisa principal, as ferramentas do advogado); acionar o {casa_id} "
                     f"como complemento só se o resultado for insuficiente ({CRITERIO_INSUFICIENCIA}); " + REGRA_TERCEIROS)
    elif principais:
        instrucao = f"usar {nomes} como pesquisa principal; " + REGRA_TERCEIROS
    elif casa_id:
        instrucao = f"usar {casa_id} como pesquisa principal, depois de conferir_terceiros"
    else:
        instrucao = ""



    sem_ass = [CONECTORES[c]["rotulo"].split(" (")[0].split(" —")[0] + f" ({c})" for c in SEM_ASSINATURA_CONHECIDA
               if capid in CONECTORES[c]["capacidades"] and prefs.get(c) != "nao_usar"]
    conferir = "" if principais or not sem_ass else (
        "antes, confira nos nomes e descrições das ferramentas da sessão se há " + ", ".join(sem_ass)
        + "; havendo, rode o inventário de novo com --conectores <id>, e ele passa a ser a pesquisa principal; "
        "na dúvida, pergunte uma vez ao advogado se usa ferramenta de pesquisa própria")
    orientacao = ("" if CASA_PESQUISA in presentes or prefs.get(CASA_PESQUISA) == "nao_usar"
                  else ORIENTACAO_ZETEMA)
    return conectores, recusados, instrucao, {
        "principais": principais,
        "zetema": papel if casa_id == CASA_PESQUISA else None,
        "casa": {"conector": casa_id, "papel": papel} if casa_id else None,
        "criterio_insuficiencia": CRITERIO_INSUFICIENCIA,
        "conferir_terceiros": conferir,
        "redundantes_com_zetema": redundantes,
        "cotas": {c: CONECTORES[c]["cota"] for c in principais if CONECTORES[c].get("cota")},
        "orientacao": orientacao,
    }


def inventariar(ferramentas=None, conectores=None, perfil=None):
    """Rota por capacidade a partir das ferramentas da sessão, dos ids já identificados e do perfil."""
    presentes = conectores_presentes(ferramentas) | {c for c in (conectores or ()) if c in CONECTORES}
    desconhecidos = sorted({c for c in (conectores or ()) if c not in CONECTORES})
    prefs, avisos = preferencias_do_perfil(perfil)

    def livre(cid):
        return cid in presentes and prefs.get(cid, "auto") != "nao_usar"

    caps = {}
    for capid, cap in CAPACIDADES.items():
        extra = {}
        if cap.get("terceiros"):
            escolhidos, recusados, instrucao, extra = _rota_descoberta(capid, livre, presentes, prefs)
        else:
            ordem = _ordem_com_preferencia(cap, prefs)
            escolhidos = [c for c in ordem if livre(c)][:1]
            recusados = [c for c in ordem if c in presentes and not livre(c)]
            instrucao = ((cap.get("instrucao_por_conector") or {}).get(escolhidos[0]) or "usar " + escolhidos[0]
                         if escolhidos else "")
        if escolhidos:
            rota = "conector"
        else:
            rota = "embarcada" if cap["sem_conector"] in ("embarcada", "degradada") else cap["sem_conector"]
            instrucao = cap["embarcada"] or cap["aviso"]
        caps[capid] = {
            "rotulo": cap["rotulo"], "rota": rota, "conectores": escolhidos,
            "recusados_pelo_advogado": recusados,
            "rota_embarcada": cap["embarcada"], "grau_sem_conector": cap["sem_conector"],
            "aviso": (cap["aviso"] if not escolhidos else ""), "instrucao": instrucao,
            **extra,
        }
    em_uso = sorted({c for v in caps.values() for c in v["conectores"]})
    desc = caps["descoberta_jurisprudencia"]
    estado = {}
    for cid, c in CONECTORES.items():
        pref = prefs.get(cid, "auto")
        pres = cid in presentes
        if pres and pref == "nao_usar":
            motivo = "presente na sessão, mas o advogado optou por não usar (perfil conectores.%s = nao_usar)" % cid
        elif cid == CASA_PESQUISA and not pres:
            motivo = "ausente nesta sessão: " + ORIENTACAO_ZETEMA
        elif pres and c.get("consultar_antes"):
            motivo = "presente na sessão · perguntar ao advogado antes do primeiro uso (consultar_antes)"
        elif pres and c.get("integrado_ao_zetema"):
            motivo = ("presente na sessão · da casa: " + ("redundante com o Zetema, que já o integra (não gasta consulta)"
                      if cid in desc["redundantes_com_zetema"] else "no lugar do Zetema, que falta; nunca confirmação"))
        elif pres and not c["casa"]:
            motivo = "presente na sessão · terceiro: pesquisa principal de descoberta, nunca confirmação"
        elif cid == CASA_PESQUISA:
            motivo = "presente na sessão · na descoberta, " + (
                "complemento por insuficiência dos terceiros" if desc["zetema"] == "complemento" else "pesquisa principal")
        elif pres:
            motivo = "presente na sessão" + (" · preferido pelo advogado" if pref == "preferir" else "")
        elif pref == "nao_usar":
            motivo = "ausente, e o advogado optou por não usar: não propor conectar"
        elif c.get("consultar_antes"):
            motivo = "ausente nesta sessão: não perguntar nem mencionar ao advogado (vale a rota embarcada)"
        else:
            motivo = "ausente nesta sessão (não é falha; vale a rota embarcada da capacidade)"
        estado[cid] = {"rotulo": c["rotulo"], "casa": c["casa"], "presente": pres,
                       "preferencia_perfil": pref, "usar": cid in em_uso, "motivo": motivo}
        if c.get("cota"):
            estado[cid]["cota"] = c["cota"]
    consultar_antes = [{"conector": cid, **CONSULTAR_ANTES[cid]} for cid in CONSULTAR_ANTES if cid in em_uso]
    pesquisa = {
        "principais": desc["principais"], "zetema": desc["zetema"], "casa": desc["casa"],
        "criterio_insuficiencia": CRITERIO_INSUFICIENCIA, "orientacao": desc["orientacao"],
        "terceiros_sem_assinatura_conhecida": list(SEM_ASSINATURA_CONHECIDA),
        "regra": ("as ferramentas de pesquisa do advogado são a principal; o Zetema complementa só quando o "
                  "resultado delas for insuficiente e, sem terceiro, é o principal; nao_usar vale; terceiro nunca "
                  "confirma; " + REGRA_TERCEIROS),
    }
    resumo = {
        "conectores_presentes": sorted(presentes),
        "conectores_em_uso": em_uso,

        "conectores_recusados": sorted(c for c in presentes if prefs.get(c) == "nao_usar" and c not in em_uso),
        "redundantes_com_zetema": list(desc["redundantes_com_zetema"]),
        "capacidades_por_conector": sorted(c for c, v in caps.items() if v["rota"] == "conector"),
        "capacidades_embarcadas": sorted(c for c, v in caps.items() if v["rota"] == "embarcada"),
        "capacidades_indisponiveis": sorted(c for c, v in caps.items() if v["rota"] in ("indisponivel", "lacuna")),
    }
    if desconhecidos:
        avisos.append("conectores desconhecidos ignorados: " + ", ".join(desconhecidos))
    return {"schema_version": SCHEMA, "sozinho_por_padrao": True, "conectores": estado,
            "capacidades": caps, "pesquisa": pesquisa, "consultar_antes": consultar_antes,
            "resumo": resumo, "avisos": avisos,
            "regra": ("ausência de conector não é falha nem indisponibilidade; detectar não é autorizar (§5, §13, §14); "
                      "conector de consultar_antes ausente não se pergunta nem se menciona")}


def carregar_perfil(caminho=None):
    'Perfil do advogado: o caminho dado; senão `$DSR_PERFIL`; senão o espelho instalado'

    if caminho:
        try:
            with open(caminho, encoding="utf-8") as f:
                return json.load(f), caminho
        except (OSError, json.JSONDecodeError) as erro:
            return None, f"perfil ilegível: {erro}"




    candidatos = [os.environ.get("DSR_PERFIL", "")]
    try:
        candidatos.append(os.path.join(os.path.expanduser("~"), ".config", "dissero", "perfil.json"))
    except Exception:
        pass
    for c in candidatos:
        if c and os.path.isfile(c):
            try:
                with open(c, encoding="utf-8") as f:
                    return json.load(f), c
            except (OSError, json.JSONDecodeError):
                return None, f"perfil ilegível: {c}"
    return None, None


def _lista(valor):
    return [x.strip() for x in (valor or "").split(",") if x.strip()]


def main(argv=None):
    p = argparse.ArgumentParser(description="Inventário de conectores da sessão → rota por capacidade (sozinho por padrão).")
    p.add_argument("--ferramentas", default=None, help="nomes de ferramentas visíveis na sessão, separados por vírgula (mcp__servidor__tool ou só o sufixo)")
    p.add_argument("--conectores", default=None, help="ids de conector já identificados, separados por vírgula: " + ",".join(CONECTORES))
    p.add_argument("--perfil", default=None, help="perfil.json do advogado (padrão: $DSR_PERFIL ou ~/.config/dissero/perfil.json)")
    p.add_argument("--sem-perfil", action="store_true", help="ignora o perfil (preferências = auto)")
    p.add_argument("--resumo", action="store_true", help="imprime linhas legíveis antes do JSON")
    a = p.parse_args(argv)
    perfil, origem = (None, None) if a.sem_perfil else carregar_perfil(a.perfil)
    inv = inventariar(_lista(a.ferramentas), _lista(a.conectores), perfil)
    inv["perfil"] = origem
    if a.resumo:
        r = inv["resumo"]
        print("Conectores presentes: " + (", ".join(r["conectores_presentes"]) or "nenhum — o plugin roda embarcado"))
        if r["conectores_recusados"]:
            print("Recusados pelo advogado (perfil): " + ", ".join(r["conectores_recusados"]))
        if r["redundantes_com_zetema"]:
            print("Redundantes com o Zetema (ele já os integra; não gastam consulta): "
                  + ", ".join(r["redundantes_com_zetema"]))
        pq = inv["pesquisa"]
        casa = pq["casa"] or {}
        print("Pesquisa: principal = " + (", ".join(pq["principais"]) or casa.get("conector") or "rota embarcada")
              + ("; " + casa["conector"] + " como complemento por insuficiência" if casa.get("papel") == "complemento" else "")
              + ("; " + pq["orientacao"] if pq["orientacao"] else ""))
        for c in inv["consultar_antes"]:
            print(f"Perguntar antes ({c['conector']}): {c['pergunta']}")
        for capid, cap in inv["capacidades"].items():
            print(f"- {cap['rotulo']}: {cap['rota']} → {cap['instrucao']}")
    print(json.dumps(inv, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
