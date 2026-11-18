#!/usr/bin/env python3
'Checklist determinístico de admissibilidade recursal.'































from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
from ficha_capacidade import FichaRecusada, exigir as exigir_ficha

CAPACIDADE = "admissibilidade_recursal"

VERSAO_ENTRADA = "dsr.admissibilidade.entrada.v1"
VERSAO_SAIDA = "dsr.admissibilidade_recursal.v1"
CRITERIOS = (
    "cabimento", "legitimidade", "interesse", "tempestividade", "preparo",
    "regularidade_formal", "dialeticidade", "ausencia_fato_impeditivo",
)
ESTADOS = {"satisfeito", "nao_satisfeito", "indeterminado", "nao_aplicavel"}





MEMORIA_PREPARO_VERSAO = "dsr.memoria_preparo_recursal.v1"
MEMORIA_PREPARO_STATUS = "MINUTA_PARA_REVISAO"



















VIGENCIA_LEI_15484 = "2026-09-03"
CRITERIO_RELEVANCIA = "relevancia_questao_federal"


RECURSOS_ESPECIAIS = {"recurso especial", "resp", "recurso especial repetitivo",
                      "agravo em recurso especial", "aresp"}
AGRAVOS_EM_RESP = {"agravo em recurso especial", "aresp"}



INCISOS_PRESUNCAO = ("I", "II", "III", "IV", "V", "VI")


def _conferir_presuncao(item, estado):
    """Erros do campo `presuncao`. Lista vazia = ausente ou bem formado."""
    if "presuncao" not in item:
        return []
    pres = item.get("presuncao")
    if not isinstance(pres, dict):
        return [f"{CRITERIO_RELEVANCIA}: presuncao deve ser objeto {{inciso, fundamento}}"]
    erros = []
    if pres.get("inciso") not in INCISOS_PRESUNCAO:
        erros.append(f"{CRITERIO_RELEVANCIA}: presuncao.inciso deve ser um de "
                     f"{', '.join(INCISOS_PRESUNCAO)} (CF, art. 105, § 3º)")
    if not str(pres.get("fundamento") or "").strip():
        erros.append(f"{CRITERIO_RELEVANCIA}: presuncao.fundamento obrigatório (o fato do caso que "
                     "faz incidir a hipótese de presunção)")
    if estado == "nao_aplicavel":
        erros.append(f"{CRITERIO_RELEVANCIA}: presuncao declarada com `nao_aplicavel`: presunção é o "
                     "conteúdo do tópico, e não dispensa dele")
    return erros


def _norm(s):
    import unicodedata
    s = str(s or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _norm_recurso(s):
    """Nome do recurso normalizado: sem acento, `_` e `-` viram espaço, espaços colapsados."""
    import re
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", _norm(s))).strip()



_NAO_LEEM_RELEVANCIA = ("agravo interno", "embargos", "contrarrazoes", "contraminuta", "resposta")


def _especial_fora_do_vocabulario(nome_norm):
    'True quando o nome fala em recurso especial mas não está no vocabulário fechado: o'

    import re
    if not nome_norm or nome_norm in RECURSOS_ESPECIAIS or nome_norm.startswith(_NAO_LEEM_RELEVANCIA):
        return False
    palavras = set(re.split(r"[^a-z0-9]+", nome_norm))
    return bool(palavras & {"especial", "resp", "aresp"})


def _data_iso(valor):
    """date de `AAAA-MM-DD` estrito; None se o texto tiver outra forma ou data inexistente."""
    import re
    texto = str(valor or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        return None
    try:
        return dt.date.fromisoformat(texto)
    except ValueError:
        return None


def _conferir_memoria_preparo(item, recurso_declarado=None):
    'Erros da memória de preparo anexada. Lista vazia = memória aceita.'




    erros = []
    memoria = item.get("memoria")
    if not isinstance(memoria, dict):
        return ["preparo: `satisfeito` exige a memória do motor em `criterios.preparo.memoria` "
                "— evidência em texto livre não prova recolhimento. Rode "
                "`preparo_recursal.py` e anexe a saída"]
    if memoria.get("schema_version") != MEMORIA_PREPARO_VERSAO:
        erros.append("preparo: memoria.schema_version deve ser %s (veio %r)"
                     % (MEMORIA_PREPARO_VERSAO, memoria.get("schema_version")))
    if memoria.get("status") != MEMORIA_PREPARO_STATUS:
        erros.append("preparo: memoria.status deve ser %s — memória em outro estado não foi "
                     "produzida pelo caminho revisável" % MEMORIA_PREPARO_STATUS)
    tabela = memoria.get("tabela")
    if not isinstance(tabela, dict):
        erros.append("preparo: memoria.tabela ausente — sem ela não se sabe contra QUE tabela "
                     "o valor foi apurado, e tabela de preparo muda por ato do tribunal")
    else:
        sha = tabela.get("table_sha256")
        if not isinstance(sha, str) or len(sha) != 64:
            erros.append("preparo: memoria.tabela.table_sha256 inválido — é o que liga o "
                         "cálculo à tabela oficial daquela data")
        if not str(tabela.get("legal_source_url") or "").startswith("https://"):
            erros.append("preparo: memoria.tabela.legal_source_url deve ser URL oficial HTTPS")
    resumo = memoria.get("resumo")
    if not isinstance(resumo, dict):
        erros.append("preparo: memoria.resumo ausente")
    else:
        try:


            from decimal import Decimal
            dif = Decimal(str(resumo.get("diferenca")))
            if dif > 0:
                erros.append("preparo: a memória aponta diferença DEVEDORA de %s — o preparo "
                             "não está satisfeito, e seguir assim é deserção" % resumo.get("diferenca"))
        except Exception:
            erros.append("preparo: memoria.resumo.diferenca ilegível")
    pedido = memoria.get("pedido")
    if isinstance(pedido, dict) and recurso_declarado:
        if str(pedido.get("recurso") or "").strip().casefold() != str(recurso_declarado).strip().casefold():
            erros.append("preparo: a memória foi apurada para o recurso %r, e a entrada "
                         "declara %r — preparo de outro recurso não serve"
                         % (pedido.get("recurso"), recurso_declarado))
    return erros


def avaliar(dados, hoje=None, registro_capacidades=None):
    'Checklist dos pressupostos. `hoje` é a data em que a ficha é lida;'

    try:
        exigir_ficha(CAPACIDADE, hoje=hoje, registro=registro_capacidades)
    except FichaRecusada as exc:
        return {"ok": False, "codigo": exc.codigo.upper(), "violacoes": [exc.mensagem]}
    erros = []
    if not isinstance(dados, dict) or dados.get("schema_version") != VERSAO_ENTRADA:
        return {"ok": False, "codigo": "CONTRATO_INVALIDO",
                "violacoes": [f"schema_version deve ser {VERSAO_ENTRADA}"]}
    criterios = dados.get("criterios")
    if not isinstance(criterios, dict):
        return {"ok": False, "codigo": "CONTRATO_INVALIDO",
                "violacoes": ["criterios deve ser objeto"]}
    resultado = {}
    for nome in CRITERIOS:
        item = criterios.get(nome)
        if not isinstance(item, dict):
            erros.append(f"{nome}: critério ausente")
            continue
        estado = item.get("estado")
        evidencias = item.get("evidencias")
        if estado not in ESTADOS:
            erros.append(f"{nome}: estado inválido")
        if not isinstance(evidencias, list):
            erros.append(f"{nome}: evidencias deve ser lista")
            evidencias = []
        if estado == "satisfeito" and not any(str(x).strip() for x in evidencias):
            erros.append(f"{nome}: satisfeito sem evidência")
        ficha = {"estado": estado, "evidencias": evidencias,
                 "observacao": item.get("observacao")}
        if nome == "preparo":
            if estado == "satisfeito":
                falhas = _conferir_memoria_preparo(item, dados.get("recurso"))
                erros.extend(falhas)
                if not falhas:
                    tab = item["memoria"]["tabela"]



                    ficha["memoria_preparo"] = {
                        "table_id": tab.get("table_id"),
                        "table_sha256": tab.get("table_sha256"),
                        "legal_source_url": tab.get("legal_source_url"),
                        "valid_from": tab.get("valid_from"),
                        "valid_to": tab.get("valid_to"),
                        "diferenca": item["memoria"]["resumo"].get("diferenca"),
                        "total_devido": item["memoria"]["resumo"].get("total_devido"),
                    }
            elif estado == "nao_aplicavel" and not str(item.get("observacao") or "").strip():
                erros.append("preparo: `nao_aplicavel` exige `observacao` dizendo POR QUE "
                             "(gratuidade deferida, isenção legal, Fazenda Pública, recurso "
                             "sem preparo). Dispensa sem razão escrita é como a deserção passa")
            elif "memoria" in item and estado != "satisfeito":
                erros.append("preparo: `memoria` anexada com estado %r — memória do motor só "
                             "cabe para sustentar `satisfeito`" % estado)
        elif "memoria" in item:
            erros.append(f"{nome}: `memoria` só é lida no critério `preparo`")
        resultado[nome] = ficha
    recurso_norm = _norm_recurso(dados.get("recurso"))
    item_rel = criterios.get(CRITERIO_RELEVANCIA)
    pub = str(dados.get("acordao_publicado_em") or "").strip()
    data_pub = _data_iso(pub) if pub else None
    if pub and data_pub is None:
        erros.append(f"acordao_publicado_em: AAAA-MM-DD (recebido {pub!r}); data em outra forma "
                     "não se compara com a vigência da Lei 15.484")
    if _especial_fora_do_vocabulario(recurso_norm):
        erros.append(f"recurso: {dados.get('recurso')!r} fala em recurso especial fora do vocabulário; "
                     "use 'recurso especial' ou 'agravo em recurso especial' (no agravo do art. 1.042 "
                     "contra REsp e RE, um checklist por recurso)")
    if recurso_norm in RECURSOS_ESPECIAIS:
        if not isinstance(item_rel, dict):
            erros.append(f"{CRITERIO_RELEVANCIA}: critério ausente — recurso especial exige o tópico de "
                         f"relevância (CPC 1.035-A, Lei 15.484/2026, acórdãos publicados desde "
                         f"{VIGENCIA_LEI_15484}) ou a razão da dispensa em `nao_aplicavel`")
        else:
            estado = item_rel.get("estado")
            evid = item_rel.get("evidencias")
            if estado not in ESTADOS:
                erros.append(f"{CRITERIO_RELEVANCIA}: estado inválido")
            if not isinstance(evid, list):
                erros.append(f"{CRITERIO_RELEVANCIA}: evidencias deve ser lista")
                evid = []
            if estado == "satisfeito" and not any(str(x).strip() for x in evid):
                erros.append(f"{CRITERIO_RELEVANCIA}: satisfeito sem evidência (onde está o tópico)")
            obs = str(item_rel.get("observacao") or "").strip()
            sob_a_lei = data_pub is not None and data_pub >= dt.date.fromisoformat(VIGENCIA_LEI_15484)
            erros.extend(_conferir_presuncao(item_rel, estado))
            if estado == "nao_aplicavel" and not obs:
                erros.append(f"{CRITERIO_RELEVANCIA}: `nao_aplicavel` exige `observacao` dizendo POR QUE "
                             f"(acórdão publicado antes de {VIGENCIA_LEI_15484})")
            if estado == "nao_aplicavel" and not pub:
                erros.append(f"{CRITERIO_RELEVANCIA}: `nao_aplicavel` exige `acordao_publicado_em`: a "
                             f"única dispensa do tópico é o acórdão publicado antes de {VIGENCIA_LEI_15484}")
            if estado == "nao_aplicavel" and sob_a_lei:
                no_dia = data_pub == dt.date.fromisoformat(VIGENCIA_LEI_15484)
                exigencia = ("o tópico é exigido por cautela da casa (a Lei 15.484, art. 4º, e a ER "
                             "55/2026, art. 5º, falam em acórdão publicado após a vigência)"
                             if no_dia else "o tópico é obrigatório")
                erros.append(f"{CRITERIO_RELEVANCIA}: acórdão publicado em {pub}, já sob a Lei 15.484 — "
                             f"{exigencia} e a presunção não dispensa o tópico (CPC 1.035-A, "
                             f"§§ 2º a 4º). Hipótese do art. 105, § 3º, da CF: estado `satisfeito`, "
                             f"`evidencias` com o lugar do tópico e `presuncao` com inciso e fundamento")
            aresp = recurso_norm in AGRAVOS_EM_RESP
            if aresp and not pub:
                erros.append(f"{CRITERIO_RELEVANCIA}: no agravo em recurso especial declare "
                             "`acordao_publicado_em` (data do acórdão atacado pelo recurso especial de "
                             "origem, não a da decisão de inadmissão); sem ela o tópico da origem não é "
                             "conferido")
            origem = item_rel.get("topico_no_resp_origem")
            if "topico_no_resp_origem" in item_rel and not aresp:
                erros.append(f"{CRITERIO_RELEVANCIA}: `topico_no_resp_origem` só se lê no agravo em "
                             "recurso especial")
            elif aresp and sob_a_lei and estado != "nao_aplicavel":
                if origem not in (True, False):
                    erros.append(f"{CRITERIO_RELEVANCIA}: no agravo em recurso especial o critério é o "
                                 "tópico do recurso especial de origem; declare `topico_no_resp_origem` "
                                 "(true/false)")
                elif origem is False and estado == "satisfeito":
                    erros.append(f"{CRITERIO_RELEVANCIA}: `satisfeito` com o recurso especial de origem "
                                 "sem o tópico (CPC 1.035-A, § 3º); o estado é `nao_satisfeito`")
            ficha_rel = {"estado": estado, "evidencias": evid, "observacao": item_rel.get("observacao"),
                         "vigencia_lei_15484": VIGENCIA_LEI_15484,
                         "acordao_publicado_em": pub or None}
            if isinstance(item_rel.get("presuncao"), dict):
                ficha_rel["presuncao"] = item_rel["presuncao"]
            if aresp and origem in (True, False):
                ficha_rel["topico_no_resp_origem"] = origem
            resultado[CRITERIO_RELEVANCIA] = ficha_rel
    elif isinstance(item_rel, dict):
        erros.append(f"{CRITERIO_RELEVANCIA}: só se lê em recurso especial (recurso declarado: "
                     f"{dados.get('recurso')!r})")
    if erros:
        return {"ok": False, "codigo": "CONTRATO_INVALIDO", "violacoes": erros}
    negativos = [n for n, x in resultado.items() if x["estado"] == "nao_satisfeito"]
    incertos = [n for n, x in resultado.items() if x["estado"] == "indeterminado"]
    decisao = "bloqueado" if negativos else ("inconclusivo" if incertos else "apto_para_revisao")
    return {
        "ok": decisao == "apto_para_revisao",
        "schema_version": VERSAO_SAIDA,
        "resultado": decisao,
        "criterios": resultado,
        "nao_satisfeitos": negativos,
        "indeterminados": incertos,
        "minuta": True,
        "revisao_advogado_obrigatoria": True,
        "protocolo_automatico": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("arquivo")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        with open(args.arquivo, encoding="utf-8") as f:
            out = avaliar(json.load(f))
    except Exception as erro:
        out = {"ok": False, "codigo": "ENTRADA_INVALIDA", "violacoes": [str(erro)]}
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    elif out.get("ok"):
        print("APTO PARA REVISÃO")
    elif str(out.get("codigo", "")).startswith(("FICHA_", "REGISTRO_")):

        print("RECUSADO: " + " ".join(out["violacoes"]))
    else:
        print("BLOQUEADO/INCONCLUSIVO")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
