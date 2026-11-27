#!/usr/bin/env python3
'Contrato e regras cruzadas de dsr.achados v2/v3, sem dependências externas.'
















from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from schema_mini import validar_schema

AQUI = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PADRAO = os.path.join(AQUI, "schema_achado.json")
FONTES_PADRAO = os.path.join(AQUI, "fontes_oficiais.json")


def texto(valor):
    return str(valor or "").strip()


def sha256_texto(valor):
    return hashlib.sha256(texto(valor).encode("utf-8")).hexdigest()


def carregar_json(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def derivar_use_status(achado):
    verificacao = achado.get("verification") or {}
    resultado = verificacao.get("result")
    metodo = verificacao.get("method")
    if resultado == "confirmed" and metodo == "human":
        return "allowed"



    if resultado == "confirmed" and metodo == "automatic":
        return "allowed" if isinstance(verificacao.get("ratificacao"), dict) else "pending"
    if resultado in ("blocked", "partial"):
        return "pending"
    return "prohibited"







def _motivos_do_recibo(achado):
    try:
        import recibo_conferencia
    except Exception as erro:
        return [f"verificador do recibo da conferência indisponível ({erro}); reinstale o plugin"]
    return recibo_conferencia.motivos_do_recibo(achado)


MOTIVO_FALTA_RATIFICAR = ("teor conferido pela máquina, falta ratificar na conferência do Minha "
                          "banca")


def falta_ratificar(achado):
    'True quando a máquina confirmou o teor na fonte e a ratificação da tela não foi gravada (D2):'

    v = (achado or {}).get("verification") or {}
    return (v.get("method") == "automatic" and v.get("result") == "confirmed"
            and not isinstance(v.get("ratificacao"), dict))


def rebaixar_confirmacoes_sem_recibo(dados):
    'Leva a pendente toda liberação que o recibo final não sustenta e devolve os ids rebaixados:'


















    rebaixados = []
    achados = [a for a in ((dados.get("achados") or []) if isinstance(dados, dict) else [])
               if isinstance(a, dict)]
    for achado in achados:
        if falta_ratificar(achado) and achado.get("use_status") == "allowed":
            v = achado["verification"]
            sinais = dict(v.get("signals") or {})
            sinais["reconferir_na_tela"] = True
            v["signals"] = sinais
            achado["use_status"] = "pending"
            rebaixados.append(texto(achado.get("id")))
    try:
        import recibo_conferencia as rc
    except Exception:
        return rebaixados
    try:
        chave = rc.carregar_chave()
        instalacao_ok = not (chave["teste"] and os.environ.get(rc.VARIAVEL_CHAVE_TESTE) != "1")
    except rc.ErroRecibo:
        instalacao_ok = False
    for achado in achados:
        if not rc.confirmacao_sem_recibo_valido(achado):
            continue
        v = achado["verification"]
        ha = v.get("human_attestation") or {}
        selo = ha.get("recibo") if v.get("method") == "human" else v.get("ratificacao")
        tem_recibo = isinstance(selo, dict) and isinstance(selo.get("envelope"), dict)
        if tem_recibo and not instalacao_ok:
            continue
        if v.get("method") == "automatic":
            motivo = rc.motivos_do_recibo(achado)[0][:200]
            rat = v.pop("ratificacao")
            sinais = dict(v.get("signals") or {})
            sinais.pop("ratificado_na_tela", None)
            sinais["reconferir_na_tela"] = True
            sinais["ratificacao_anterior"] = {"por": texto(rat.get("por")),
                                              "em": texto(rat.get("em")), "motivo": motivo}
            v["signals"] = sinais
            achado["use_status"] = "pending"
            rebaixados.append(texto(achado.get("id")))
            continue
        sinais = {k: val for k, val in (v.get("signals") or {}).items()
                  if k not in ("attested_by_lawyer", "conferido_pela_equipe", "conferido_na_tela")}
        sinais["reconferir_na_tela"] = True
        sinais["atestacao_anterior"] = {"por": texto(ha.get("actor")), "em": texto(ha.get("date")),
                                        "motivo": rc.motivos_do_recibo(achado)[0][:200]}
        achado["verification"] = {"result": "partial", "method": "none",
                                  "checked_at": v.get("checked_at"),
                                  "final_url": v.get("final_url"), "signals": sinais,
                                  "human_attestation": None}
        achado["use_status"] = "pending"
        rebaixados.append(texto(achado.get("id")))
    return rebaixados


def validar_regras(achado, fontes):
    """Violações das regras cruzadas de UM achado, cada uma prefixada pelo rótulo do achado."""
    rotulo = texto(achado.get("reference"))[:60] or texto(achado.get("id"))
    return [f"{rotulo}: {motivo}" for motivo in motivos_das_regras(achado, fontes)]


def motivos_das_regras(achado, fontes):
    'As regras que o schema não expressa, sem prefixo. `fontes` None = catálogo ausente: as'

    erros = []
    citacao = achado.get("citation") or {}
    verificacao = achado.get("verification") or {}
    natureza = achado.get("nature")
    resultado = verificacao.get("result")
    metodo = verificacao.get("method")
    url = texto(achado.get("official_url"))
    final_url = texto(verificacao.get("final_url"))
    host = (urlparse(final_url or url).hostname or "").lower()
    com_catalogo = fontes is not None
    meta_host = fontes.get("hosts", {}).get(host, {}) if com_catalogo else {}

    esperado = derivar_use_status(achado)
    if achado.get("use_status") != esperado:
        erros.append(f"use_status deve ser derivado como {esperado}")
    if achado.get("selected_for_use") and esperado == "prohibited":
        erros.append("achado proibido não pode ser selecionado para uso")
    atestacao_doc = (verificacao.get("human_attestation") or {}) if isinstance(verificacao.get("human_attestation"), dict) else {}




    por_documento = (metodo == "human" and not url and isinstance(atestacao_doc.get("documento"), dict))
    if resultado == "confirmed" and not url and not por_documento:
        erros.append("confirmed exige official_url")
    if resultado == "confirmed" and final_url != url:
        erros.append("confirmed exige final_url idêntica a official_url")




    host_travado = "confirmacao_teor" in meta_host.get("travas_locais", [])

    if metodo == "automatic" and resultado == "confirmed":
        capacidades = meta_host.get("capacidades", [])
        if com_catalogo and host_travado:
            erros.append(f"DataJud/LexML não confirmam o teor: {host} serve metadado ou "
                         "índice; confirme no documento do tribunal ou do órgão que o publicou")
        elif com_catalogo and (not meta_host or "confirmacao_teor" not in capacidades):
            erros.append("confirmação automática exige host exato catalogado com capacidade confirmacao_teor")
        if texto((achado.get("discovery") or {}).get("provider")).lower() in ("datajud", "lexml"):
            erros.append("DataJud/LexML não confirmam sozinhos o teor")
    if metodo == "none" and resultado == "confirmed":
        erros.append("confirmed não admite método none")




    if verificacao.get("ratificacao") is not None:
        if metodo != "automatic" or resultado != "confirmed":
            erros.append("ratificacao_fora_da_verificacao_automatica: a ratificação da tela só "
                         "cabe no julgado que a máquina confirmou na fonte (method automatic, "
                         "result confirmed)")
        elif isinstance(verificacao.get("ratificacao"), dict):
            erros.extend(_motivos_do_recibo(achado))

    atestacao = verificacao.get("human_attestation")
    if metodo == "human":
        if resultado != "confirmed" or not isinstance(atestacao, dict):
            erros.append("confirmação humana exige result=confirmed e human_attestation")
        elif por_documento:
            doc = atestacao.get("documento") or {}
            if atestacao.get("official_url"):
                erros.append("atestação pelo documento não leva endereço: ou um, ou outro")
            if not (re.fullmatch(r"[0-9a-f]{64}", texto(doc.get("sha256")))
                    and re.fullmatch(r"[0-9a-f]{64}", texto(doc.get("sha256_extracao")))
                    and len(texto(doc.get("origem"))) >= 3):
                erros.append("atestação pelo documento exige hash do arquivo, hash da extração e a "
                             "origem dita pelo advogado")
            procedencias = [r for r in achado.get("procedencia_literal") or [] if isinstance(r, dict)]
            if not any(r.get("campo") == "syllabus_literal" and r.get("nivel") == "verbatim"
                       and texto(r.get("sha256_extracao")) == texto(doc.get("sha256_extracao"))
                       for r in procedencias):
                erros.append("atestação pelo documento exige o trecho conferido verbatim pela "
                             "máquina nesse mesmo documento (procedência literal)")
            if atestacao.get("syllabus_sha256") != sha256_texto(achado.get("syllabus_literal")):
                erros.append("ementa alterada invalida a confirmação humana")
        else:
            oficial_humano = (not com_catalogo) or (bool(host) and (host in fontes.get("hosts", {}) or any(host.endswith(sufixo) for sufixo in fontes.get("sufixos_oficiais", []))))
            if not oficial_humano:
                erros.append("confirmação humana exige URL de host oficial")
            elif host_travado:
                erros.append(f"DataJud/LexML não confirmam o teor: {host} serve metadado ou "
                             "índice; ateste no documento do tribunal ou do órgão que o publicou")
            if texto(atestacao.get("official_url")) != url or final_url != url:
                erros.append("URL alterada invalida a confirmação humana")
            if atestacao.get("syllabus_sha256") != sha256_texto(achado.get("syllabus_literal")):
                erros.append("ementa alterada invalida a confirmação humana")
        if resultado == "confirmed" and isinstance(atestacao, dict):
            erros.extend(_motivos_do_recibo(achado))
    elif atestacao is not None:
        erros.append("human_attestation só é aceita com method=human")

    ementa = texto(achado.get("syllabus_literal"))
    if natureza == "acordao":
        obrigatorios = {"número": citacao.get("case_number"), "relator": citacao.get("rapporteur"), "trecho literal": ementa}
    elif natureza in ("sumula", "tema"):
        obrigatorios = {"identificador": citacao.get("identifier"), "tese literal": ementa, "status": citacao.get("status")}
    elif natureza == "norma":
        obrigatorios = {"tipo": citacao.get("norm_type"), "número": citacao.get("norm_number"), "data": citacao.get("norm_date"), "dispositivo": citacao.get("provision"), "texto": ementa, "vigência": citacao.get("validity")}
    else:
        obrigatorios = {"identificador": citacao.get("identifier") or citacao.get("case_number"), "trecho literal": ementa}
    if resultado == "confirmed":
        ausentes = [nome for nome, valor in obrigatorios.items() if not texto(valor)]
        if ausentes:
            erros.append("confirmed sem critérios próprios: " + ", ".join(ausentes))
        if achado.get("selected_for_use") and len(ementa) < 120:
            erros.append(f"syllabus_literal com {len(ementa)} caracteres; mínimo de 120 para uso na peça")

    erros.extend(motivos_situacao_tema(achado))



    return erros




SITUACOES_SEM_TESE_FIRMADA = ("afetado_com_suspensao", "afetado_sem_suspensao")

_RX_STATUS_AFETADO = re.compile(r"\bafeta(?:d[oa]s?|ção|cao)\b", re.IGNORECASE)


def motivos_situacao_tema(achado):
    '`situacao_tema` só cabe em tema ou precedente qualificado (nota B); tema afetado não entra'



    situacao = achado.get("situacao_tema")
    confirmado = (achado.get("verification") or {}).get("result") == "confirmed"
    tema = achado.get("nature") == "tema"
    nota_b = achado.get("authority") == "B"
    erros = []
    if situacao is None:
        status = texto((achado.get("citation") or {}).get("status"))
        if confirmado and tema:
            erros.append("situacao_tema_ausente_em_tema_confirmado: tema confirmado exige "
                         "situacao_tema (julgado ou revisado); confira na página do tribunal se "
                         "o tema foi julgado, revisado, cancelado ou só afetado")
        elif confirmado and nota_b and _RX_STATUS_AFETADO.search(status):
            erros.append("situacao_tema_ausente_em_tema_confirmado: o status da citação diz "
                         "afetação; registre situacao_tema, e tema afetado entra como partial")
        return erros
    if not tema and not nota_b:
        erros.append("situacao_tema_fora_de_precedente_qualificado: situacao_tema só se aplica a "
                     "tema, repetitivo, repercussão geral, IRDR ou IAC (nature tema ou nota B)")
    if situacao in SITUACOES_SEM_TESE_FIRMADA and confirmado:
        erros.append("tema_afetado_sem_tese_firmada: tema afetado ainda não tem tese firmada e "
                     "não entra como confirmed; registre a afetação como partial (pendente) e "
                     "trate o efeito da suspensão sobre o cliente como análise de risco, não "
                     "como prognóstico")
    if situacao == "cancelado" and confirmado and achado.get("selected_for_use"):
        erros.append("tema_cancelado_sem_tese_aplicavel: tema cancelado não tem tese aplicável e "
                     "não vai à peça como fundamento; registre-o sem selected_for_use")
    return erros


def validar_documento(dados, schema_path=SCHEMA_PADRAO, fontes_path=FONTES_PADRAO):
    versao = dados.get("schema_version") if isinstance(dados, dict) else None
    if versao == "dsr.achados.v3":
        try:
            import estrategia_precedentes as estrategia
        except Exception as erro:
            return [f"$: validador estratégico v3 indisponível: {erro}"]
        base = estrategia.para_validacao_v2(dados)
        schema = carregar_json(SCHEMA_PADRAO)
        erros = validar_schema(base, schema)
        if not erros:
            erros.extend(estrategia.validar_v3(dados))
    elif versao == "dsr.achados.v2":
        schema = carregar_json(schema_path or SCHEMA_PADRAO)
        erros = validar_schema(dados, schema)
    else:
        return ["$.schema_version: esperado dsr.achados.v2 ou dsr.achados.v3"]
    fontes = carregar_json(fontes_path)
    if erros:
        return erros
    for achado in dados["achados"]:
        erros.extend(validar_regras(achado, fontes))
    return erros


_RX_INDICE_ACHADO = re.compile(r"^\$\.achados\[(\d+)\](?:\.(.*))?$")


def violacoes_por_achado(dados, indices, schema_path=SCHEMA_PADRAO, fontes_path=FONTES_PADRAO):
    'Conferência do contrato só dos achados de `indices` (posições em `dados["achados"]`).'







    resultado = {"documento": [], "achados": {}, "catalogo": os.path.isfile(fontes_path)}
    versao = dados.get("schema_version") if isinstance(dados, dict) else None
    if versao not in ("dsr.achados.v2", "dsr.achados.v3"):
        resultado["documento"].append("$.schema_version: esperado dsr.achados.v2 ou dsr.achados.v3")
        return resultado
    if not isinstance(dados.get("achados"), list):
        resultado["documento"].append("$.achados: lista obrigatória")
        return resultado
    base = dados
    if versao == "dsr.achados.v3":
        try:
            import estrategia_precedentes as estrategia
        except Exception as erro:
            resultado["documento"].append(f"$: validador estratégico v3 indisponível: {erro}")
            return resultado
        base = estrategia.para_validacao_v2(dados)
    pedidos = set(indices)
    for erro in validar_schema(base, carregar_json(schema_path or SCHEMA_PADRAO)):
        caminho, _, motivo = erro.partition(": ")
        m = _RX_INDICE_ACHADO.match(caminho)
        if not m:
            resultado["documento"].append(erro)
            continue
        indice = int(m.group(1))
        if indice in pedidos:
            onde = m.group(2) or "achado"
            resultado["achados"].setdefault(indice, []).append(f"{onde}: {motivo}")
    fontes = carregar_json(fontes_path) if resultado["catalogo"] else None
    for indice in sorted(pedidos):
        if indice in resultado["achados"] or not 0 <= indice < len(dados["achados"]):
            continue
        achado = dados["achados"][indice]
        motivos = motivos_das_regras(achado, fontes) if isinstance(achado, dict) else []
        if motivos:
            resultado["achados"][indice] = motivos
    return resultado
