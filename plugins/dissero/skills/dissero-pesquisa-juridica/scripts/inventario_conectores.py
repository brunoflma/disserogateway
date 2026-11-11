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
    },
    "zetema": {
        "rotulo": "Zetema — pesquisa jurídica da casa: fontes oficiais ao vivo, documento oficial por hash, jurimetria, "
                  "CNPJ público",
        "casa": True,
        "assinaturas": ("verificar_documento_oficial", "obter_documento_oficial", "ler_trecho_documento_oficial",
                        "consultar_jurimetria", "consultar_capacidades_fontes",
                        "resolver_numero_mascarado", "consultar_status_fontes"),
        "capacidades": ("descoberta_jurisprudencia", "confirmacao_oficial", "legislacao", "jurimetria",
                        "diligencia_cadastral"),
    },
    "cnpja": {
        "rotulo": "CNPJA — diligência cadastral (CNPJ, sócios, comprovantes)",
        "casa": True,
        "assinaturas": ("consultar_saldo_cnpja", "consultar_empresa_cnpja", "consultar_receita_federal_cnpj"),
        "capacidades": ("diligencia_cadastral",),
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
        "sem_conector": "degradada",
        "aviso": "sem o Eluxi não há OCR: documento escaneado só se lê por imagem, página a página, ou "
                 "escala ao advogado; documento volumoso é lido por partes (planejar_blocos.py), sem "
                 "índice do OCR; o ilegível nunca é improvisado",
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
        "embarcada": "fontes públicas por script (normas_leg_br.py, consultar_dou.py) e o julgado que o advogado "
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
}

_ASSINATURA_PARA_CONECTOR = {}
for _cid, _c in CONECTORES.items():
    for _s in _c["assinaturas"]:
        if _s in _ASSINATURA_PARA_CONECTOR:
            raise ValueError(f"assinatura ambígua entre conectores: {_s}")
        _ASSINATURA_PARA_CONECTOR[_s] = _cid


def sufixo(nome):
    """`mcp__servidor__tool` → `tool`; nome já nu → ele mesmo. Nunca olha o id do servidor."""
    n = (nome or "").strip()
    if n.startswith("mcp__") and n.count("__") >= 2:
        return n.split("__")[-1]
    return n


def conectores_presentes(ferramentas):
    presentes = set()
    for f in ferramentas or ():
        cid = _ASSINATURA_PARA_CONECTOR.get(sufixo(f))
        if cid:
            presentes.add(cid)
    return presentes


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


def inventariar(ferramentas=None, conectores=None, perfil=None):
    """Rota por capacidade a partir das ferramentas da sessão, dos ids já identificados e do perfil."""
    presentes = conectores_presentes(ferramentas) | {c for c in (conectores or ()) if c in CONECTORES}
    desconhecidos = sorted({c for c in (conectores or ()) if c not in CONECTORES})
    prefs, avisos = preferencias_do_perfil(perfil)
    estado = {}
    for cid, c in CONECTORES.items():
        pref = prefs.get(cid, "auto")
        pres = cid in presentes
        usar = pres and pref != "nao_usar"
        if pres and pref == "nao_usar":
            motivo = "presente na sessão, mas o advogado optou por não usar (perfil conectores.%s = nao_usar)" % cid
        elif pres:
            motivo = "presente na sessão" + (" · preferido pelo advogado" if pref == "preferir" else "")
        elif pref == "nao_usar":
            motivo = "ausente, e o advogado optou por não usar: não propor conectar"
        else:
            motivo = "ausente nesta sessão (não é falha; vale a rota embarcada da capacidade)"
        estado[cid] = {"rotulo": c["rotulo"], "casa": c["casa"], "presente": pres,
                       "preferencia_perfil": pref, "usar": usar, "motivo": motivo}
    caps = {}
    for capid, cap in CAPACIDADES.items():
        ordem = _ordem_com_preferencia(cap, prefs)
        usaveis = [c for c in ordem if estado[c]["usar"]]
        recusados = [c for c in ordem if estado[c]["presente"] and not estado[c]["usar"]]
        if usaveis:
            escolhidos = usaveis[:1]
            rota = "conector"
            instrucao = (cap.get("instrucao_por_conector") or {}).get(escolhidos[0]) or "usar " + escolhidos[0]
        else:
            escolhidos = []
            rota = "embarcada" if cap["sem_conector"] in ("embarcada", "degradada") else cap["sem_conector"]
            instrucao = cap["embarcada"] or cap["aviso"]
        caps[capid] = {
            "rotulo": cap["rotulo"], "rota": rota, "conectores": escolhidos,
            "recusados_pelo_advogado": recusados,
            "rota_embarcada": cap["embarcada"], "grau_sem_conector": cap["sem_conector"],
            "aviso": (cap["aviso"] if not usaveis else ""), "instrucao": instrucao,
        }
    resumo = {
        "conectores_presentes": sorted(presentes),
        "conectores_em_uso": sorted(c for c, e in estado.items() if e["usar"]),
        "conectores_recusados": sorted(c for c, e in estado.items() if e["presente"] and not e["usar"]),
        "capacidades_por_conector": sorted(c for c, v in caps.items() if v["rota"] == "conector"),
        "capacidades_embarcadas": sorted(c for c, v in caps.items() if v["rota"] == "embarcada"),
        "capacidades_indisponiveis": sorted(c for c, v in caps.items() if v["rota"] in ("indisponivel", "lacuna")),
    }
    if desconhecidos:
        avisos.append("conectores desconhecidos ignorados: " + ", ".join(desconhecidos))
    return {"schema_version": SCHEMA, "sozinho_por_padrao": True, "conectores": estado,
            "capacidades": caps, "resumo": resumo, "avisos": avisos,
            "regra": "ausência de conector não é falha nem indisponibilidade; detectar não é autorizar (§5, §13, §14)"}


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
        for capid, cap in inv["capacidades"].items():
            print(f"- {cap['rotulo']}: {cap['rota']} → {cap['instrucao']}")
    print(json.dumps(inv, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
