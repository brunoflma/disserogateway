#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Contrato estratégico de ``dsr.achados.v3``.'










from __future__ import annotations

import copy
import datetime as _dt
import re

VERSAO_V2 = "dsr.achados.v2"
VERSAO_V3 = "dsr.achados.v3"
ESTADOS_PESQUISA = {
    "nao_iniciada", "concluida_sem_achado", "concluida_com_achado", "bloqueada"
}
COBERTURAS = {"confirmada", "substituivel", "forcada", "inexistente"}

_CERTEZA_RX = re.compile(
    r"\b(?:jurisprud[eê]ncia\s+(?:[ée]\s+)?(?:pac[ií]fica|un[ií]ssona|consolidada)|"
    r"entendimento\s+(?:pac[ií]fico|consolidado)|[ée]\s+assente|n[aã]o\s+h[aá]\s+diverg[eê]ncia|"
    r"inequ[ií]voco|incontroverso)\b", re.I
)
_ANALOGIA_RX = re.compile(
    r"\b(?:por\s+analogia|aplica[cç][aã]o\s+anal[oó]gica|raz[aã]o\s+de\s+decidir|ratio\s+decidendi)\b",
    re.I,
)


def _texto(valor):
    return str(valor or "").strip()


def _data_iso(valor):
    try:
        return _dt.date.fromisoformat(_texto(valor)[:10])
    except (TypeError, ValueError):
        return None


def migrar_v2(dados):
    'Copia v2 para v3 sem promover conclusão alguma.'




    if not isinstance(dados, dict) or dados.get("schema_version") != VERSAO_V2:
        raise ValueError("migrar_v2 exige objeto dsr.achados.v2")
    novo = copy.deepcopy(dados)
    novo["schema_version"] = VERSAO_V3
    estrategia = novo.get("estrategia")
    if estrategia is None:
        estrategia = {}
        novo["estrategia"] = estrategia
    if not isinstance(estrategia, dict):
        raise ValueError("estrategia v2 precisa ser objeto antes da migração")
    estrategia["pesquisa_contraria"] = {
        "estado": "nao_iniciada", "consultas": [], "achado_ids": [],
        "concluida_em": None,
    }
    estrategia["cobertura_precedente"] = "inexistente"
    estrategia["cobertura_revisada_em"] = None
    estrategia["cobertura_valida_ate"] = None
    estrategia["autoridade_substituta_ids"] = []
    estrategia["fundamentacao_analogica"] = None
    estrategia["origem_cobertura"] = "migracao_fail_closed"
    return novo


def para_validacao_v2(dados):
    """Remove somente extensões v3 de uma cópia para reaproveitar o schema v2."""
    if not isinstance(dados, dict) or dados.get("schema_version") != VERSAO_V3:
        raise ValueError("para_validacao_v2 aceita somente dsr.achados.v3")
    base = copy.deepcopy(dados)
    base["schema_version"] = VERSAO_V2
    estrategia = base.get("estrategia")
    if isinstance(estrategia, dict):
        for chave in (
            "pesquisa_contraria", "cobertura_precedente", "cobertura_revisada_em",
            "cobertura_valida_ate", "autoridade_substituta_ids",
            "fundamentacao_analogica", "origem_cobertura",
        ):
            estrategia.pop(chave, None)
        if not estrategia:
            base.pop("estrategia", None)
    return base


def validar_v3(dados, hoje=None):
    erros = []
    if not isinstance(dados, dict) or dados.get("schema_version") != VERSAO_V3:
        return ["$: contrato dsr.achados.v3 obrigatório"]
    achados = dados.get("achados")
    if not isinstance(achados, list):
        erros.append("$.achados: lista obrigatória no v3")
        achados = []
    ids = {a.get("id") for a in achados if isinstance(a, dict)
           and isinstance(a.get("id"), str) and _texto(a.get("id"))}
    selecionados = [a for a in achados if isinstance(a, dict) and a.get("selected_for_use") is True]
    estrategia = dados.get("estrategia")
    if not isinstance(estrategia, dict):
        return ["$.estrategia: objeto obrigatório no v3"]

    pesquisa = estrategia.get("pesquisa_contraria")
    if not isinstance(pesquisa, dict):
        erros.append("$.estrategia.pesquisa_contraria: objeto obrigatório")
        pesquisa = {}
    estado = pesquisa.get("estado")
    if estado not in ESTADOS_PESQUISA:
        erros.append("$.estrategia.pesquisa_contraria.estado: valor inválido")
    consultas = pesquisa.get("consultas")
    if not isinstance(consultas, list):
        erros.append("$.estrategia.pesquisa_contraria.consultas: lista obrigatória")
        consultas = []
    for i, consulta in enumerate(consultas):
        if not isinstance(consulta, dict):
            erros.append(f"$.estrategia.pesquisa_contraria.consultas[{i}]: objeto obrigatório")
            continue
        for campo in ("fonte", "termos", "executada_em"):
            if not _texto(consulta.get(campo)):
                erros.append(f"$.estrategia.pesquisa_contraria.consultas[{i}].{campo}: obrigatório")
    achado_ids = pesquisa.get("achado_ids")
    if not isinstance(achado_ids, list):
        erros.append("$.estrategia.pesquisa_contraria.achado_ids: lista obrigatória")
        achado_ids = []
    invalidos = [x for x in achado_ids if not isinstance(x, str)]
    if invalidos:
        erros.append("$.estrategia.pesquisa_contraria.achado_ids: todos os IDs devem ser texto")
    achado_ids = [x for x in achado_ids if isinstance(x, str)]
    desconhecidos = sorted({_texto(x) for x in achado_ids if _texto(x) and x not in ids})
    if desconhecidos:
        erros.append("$.estrategia.pesquisa_contraria.achado_ids: IDs ausentes: " + ", ".join(desconhecidos))
    if estado in ("concluida_sem_achado", "concluida_com_achado") and not consultas:
        erros.append("pesquisa contrária concluída exige ao menos uma consulta registrada")
    if estado == "concluida_com_achado" and not achado_ids:
        erros.append("pesquisa contrária com achado exige achado_ids")
    if estado == "concluida_com_achado":
        contrarios = {
            a.get("id") for a in achados if isinstance(a, dict)
            and isinstance(a.get("id"), str)
            and isinstance(a.get("estrategia_uso"), dict)
            and a["estrategia_uso"].get("posicao") == "contrario"
        }
        if not (set(achado_ids) & contrarios):
            erros.append("pesquisa contrária com achado exige ao menos um ID classificado como contrário")
    if selecionados and estado not in ("concluida_sem_achado", "concluida_com_achado"):
        erros.append("precedente selecionado exige pesquisa contrária concluída")

    cobertura = estrategia.get("cobertura_precedente")
    if cobertura not in COBERTURAS:
        erros.append("$.estrategia.cobertura_precedente: valor inválido")
    favoraveis = [
        a for a in selecionados
        if isinstance(a.get("estrategia_uso"), dict)
        and a["estrategia_uso"].get("posicao") == "favoravel"
        and a.get("use_status") == "allowed"
    ]
    substitutos = estrategia.get("autoridade_substituta_ids")
    if not isinstance(substitutos, list):
        erros.append("$.estrategia.autoridade_substituta_ids: lista obrigatória")
        substitutos = []
    substitutos_invalidos = [x for x in substitutos if not isinstance(x, str)]
    if substitutos_invalidos:
        erros.append("$.estrategia.autoridade_substituta_ids: todos os IDs devem ser texto")
    substitutos = [x for x in substitutos if isinstance(x, str)]
    if cobertura == "confirmada" and not favoraveis:
        erros.append("cobertura confirmada exige precedente favorável selecionado e liberado")
    if cobertura == "substituivel":
        if not substitutos:
            erros.append("cobertura substituível exige autoridade_substituta_ids")
        por_id = {a.get("id"): a for a in achados if isinstance(a, dict)
                  and isinstance(a.get("id"), str)}
        for ident in substitutos:
            if ident not in ids:
                erros.append(f"autoridade substituta ausente: {ident}")
            else:
                substituto = por_id.get(ident) or {}
                if (substituto.get("use_status") != "allowed"
                        or substituto.get("selected_for_use") is not True):
                    erros.append(f"autoridade substituta não confirmada/selecionada: {ident}")
    if cobertura == "forcada" and len(_texto(estrategia.get("fundamentacao_analogica"))) < 20:
        erros.append("cobertura forçada exige fundamentação analógica com 20+ caracteres")
    if cobertura == "inexistente" and favoraveis:
        erros.append("cobertura inexistente não pode manter precedente favorável selecionado")

    if hoje is None:
        hoje = _dt.date.today()
    elif isinstance(hoje, _dt.datetime) or not isinstance(hoje, _dt.date):
        erros.append("parâmetro hoje deve ser date")
        hoje = _dt.date.today()
    revisada = _data_iso(estrategia.get("cobertura_revisada_em"))
    valida_ate = _data_iso(estrategia.get("cobertura_valida_ate"))
    if cobertura in ("confirmada", "substituivel", "forcada"):
        if not revisada:
            erros.append("cobertura utilizável exige cobertura_revisada_em ISO")
        if not valida_ate:
            erros.append("cobertura utilizável exige cobertura_valida_ate ISO")
        elif valida_ate < hoje:
            erros.append("cobertura de precedentes vencida — reverifique antes do protocolo")
    return erros


def avaliar_linguagem(texto, dados, hoje=None):
    """Retorna (erros, pendências) para o linter de peça."""
    erros, pendencias = [], []
    if not isinstance(texto, str):
        erros.append("texto da peça deve ser string para calibração")
        texto = ""
    if not isinstance(dados, dict):
        return ["registro de precedentes ausente ou inválido"], pendencias
    if dados.get("schema_version") == VERSAO_V2:
        fortes = sorted(set(m.group(0) for m in _CERTEZA_RX.finditer(texto or "")))
        estrategia_v2 = dados.get("estrategia") if isinstance(dados.get("estrategia"), dict) else {}
        chaves_v3 = {
            "pesquisa_contraria", "cobertura_precedente", "cobertura_revisada_em",
            "cobertura_valida_ate", "autoridade_substituta_ids", "fundamentacao_analogica",
            "origem_cobertura",
        }
        if set(estrategia_v2) & chaves_v3:
            erros.append("registro marcado como v2 contém estratégia v3; restaure a versão correta")
        achados_v2 = dados.get("achados")
        if not isinstance(achados_v2, list):
            erros.append("registro v2 deve conter lista de achados")
            achados_v2 = []
        favoravel_selecionado = any(
            isinstance(a, dict) and a.get("selected_for_use") is True
            and isinstance(a.get("estrategia_uso"), dict)
            and a["estrategia_uso"].get("posicao") == "favoravel"
            for a in achados_v2
        )
        if estrategia_v2.get("tese_central") or favoravel_selecionado:
            pendencias.append("registro v2 com tese/precedente favorável exige migração e revisão v3 antes do protocolo")
        if fortes:
            erros.append("registro v2 não prova pesquisa contrária/cobertura para linguagem de certeza: "
                         + ", ".join(fortes[:5]))
        return erros, pendencias
    if dados.get("schema_version") != VERSAO_V3:
        return ["contrato de precedentes v2/v3 obrigatório"], pendencias
    estrategia = dados.get("estrategia")
    if not isinstance(estrategia, dict):
        return ["estratégia v3 deve ser objeto"], pendencias
    cobertura = estrategia.get("cobertura_precedente")
    pesquisa = estrategia.get("pesquisa_contraria")
    if not isinstance(pesquisa, dict):
        return ["pesquisa contrária v3 deve ser objeto"], pendencias
    if pesquisa.get("estado") not in ("concluida_sem_achado", "concluida_com_achado"):
        pendencias.append("a pesquisa de precedente contrário ainda não foi concluída")
    fortes = sorted(set(m.group(0) for m in _CERTEZA_RX.finditer(texto or "")))
    if cobertura in ("substituivel", "forcada", "inexistente") and fortes:
        erros.append("linguagem de certeza incompatível com a cobertura: " + ", ".join(fortes[:5]))
    if cobertura == "forcada" and not _ANALOGIA_RX.search(texto or ""):
        erros.append("precedente de aderência forçada exige linguagem analógica explícita")
    if cobertura == "inexistente" and fortes:
        pendencias.append("não há precedente aderente para sustentar afirmação categórica")
    erros.extend(validar_v3(dados, hoje=hoje))
    return list(dict.fromkeys(erros)), list(dict.fromkeys(pendencias))









def _ler_json(caminho):
    import json
    with open(caminho, encoding="utf-8") as fh:
        return json.load(fh)


def _gravar_atomico(dados, caminho):
    import json
    import os
    import tempfile
    pasta = os.path.dirname(os.path.abspath(caminho)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".estrategia-", suffix=".tmp", dir=pasta)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(dados, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, caminho)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def aplicar_definicao(dados, *, pesquisa_contraria=None, consultas=(), achados_contrarios=(),
                      concluida_em=None, cobertura=None, revisada_em=None, valida_ate=None,
                      selecionar=(), desselecionar=(), fundamentacao_analogica=None,
                      autoridades_substitutas=None, tese_central=None, hoje=None):
    'Devolve (cópia alterada, erros de entrada). Não valida o contrato: isso é do chamador.'



    erros = []
    if not isinstance(dados, dict) or dados.get("schema_version") != VERSAO_V3:
        versao = dados.get("schema_version") if isinstance(dados, dict) else None
        dica = " (registro v2: migre para v3 antes)" if versao == VERSAO_V2 else ""
        return None, ["o registro precisa ser dsr.achados.v3" + dica]
    novo = copy.deepcopy(dados)
    achados = novo.get("achados") if isinstance(novo.get("achados"), list) else []
    por_id = {a.get("id"): a for a in achados if isinstance(a, dict) and isinstance(a.get("id"), str)}
    estrategia = novo.get("estrategia")
    if not isinstance(estrategia, dict):
        return None, ["o registro não tem o objeto de estratégia"]
    hoje = hoje or _dt.date.today()

    def data(rotulo, valor):
        if valor is None:
            return None
        d = _data_iso(valor)
        if d is None or len(_texto(valor)) != 10:
            erros.append(f"{rotulo}: data AAAA-MM-DD obrigatória (recebido {valor!r})")
            return None
        return d.isoformat()

    def ids(rotulo, lista):
        faltam = [x for x in lista if x not in por_id]
        if faltam:
            erros.append(f"{rotulo}: IDs ausentes do registro: " + ", ".join(faltam))
        return [x for x in lista if x in por_id]

    mexe_pesquisa = pesquisa_contraria is not None or consultas or achados_contrarios \
        or concluida_em is not None
    if mexe_pesquisa:
        pesquisa = estrategia.get("pesquisa_contraria")
        if not isinstance(pesquisa, dict):
            pesquisa = {"estado": "nao_iniciada", "consultas": [], "achado_ids": [],
                        "concluida_em": None}
            estrategia["pesquisa_contraria"] = pesquisa
        if not isinstance(pesquisa.get("consultas"), list):
            pesquisa["consultas"] = []
        if not isinstance(pesquisa.get("achado_ids"), list):
            pesquisa["achado_ids"] = []
        if pesquisa_contraria is not None:
            if pesquisa_contraria not in ESTADOS_PESQUISA:
                erros.append("pesquisa contrária: estado inválido; use "
                             + ", ".join(sorted(ESTADOS_PESQUISA)))
            pesquisa["estado"] = pesquisa_contraria
        for i, consulta in enumerate(consultas):
            fonte, termos, quando = (list(consulta) + [None, None, None])[:3]
            iso = data(f"consulta {i + 1}", quando)
            if not _texto(fonte) or not _texto(termos):
                erros.append(f"consulta {i + 1}: fonte e termos são obrigatórios")
            pesquisa["consultas"].append({"fonte": _texto(fonte), "termos": _texto(termos),
                                          "executada_em": iso or _texto(quando)})
        for ident in ids("achado contrário", list(achados_contrarios)):
            if ident not in pesquisa["achado_ids"]:
                pesquisa["achado_ids"].append(ident)
        if concluida_em is not None:
            pesquisa["concluida_em"] = data("pesquisa concluída em", concluida_em)
        elif pesquisa.get("estado") in ("concluida_sem_achado", "concluida_com_achado") \
                and not pesquisa.get("concluida_em"):
            pesquisa["concluida_em"] = hoje.isoformat()
    if cobertura is not None:
        if cobertura not in COBERTURAS:
            erros.append("cobertura: valor inválido; use " + ", ".join(sorted(COBERTURAS)))
        estrategia["cobertura_precedente"] = cobertura
        estrategia["origem_cobertura"] = "comando_definir"
    if revisada_em is not None:
        estrategia["cobertura_revisada_em"] = data("cobertura revisada em", revisada_em)
    if valida_ate is not None:
        estrategia["cobertura_valida_ate"] = data("cobertura válida até", valida_ate)
    if fundamentacao_analogica is not None:
        estrategia["fundamentacao_analogica"] = _texto(fundamentacao_analogica) or None
    if autoridades_substitutas is not None:
        estrategia["autoridade_substituta_ids"] = ids("autoridade substituta",
                                                      list(autoridades_substitutas))
    if tese_central is not None:
        estrategia["tese_central"] = _texto(tese_central)
    em_ambos = sorted(set(selecionar) & set(desselecionar))
    if em_ambos:
        erros.append("o mesmo ID não pode ser selecionado e tirado da seleção: " + ", ".join(em_ambos))
    for ident in ids("selecionar", list(selecionar)):
        por_id[ident]["selected_for_use"] = True
    for ident in ids("tirar da seleção", list(desselecionar)):
        por_id[ident]["selected_for_use"] = False
    return novo, erros


def _cli(argv=None):
    import argparse
    import json
    import os
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Atualiza a estratégia de precedentes do achados.json com validação: só grava "
                    "se o documento inteiro continuar no contrato.")
    sub = ap.add_subparsers(dest="comando", required=True)
    d = sub.add_parser("definir", help="aplica pesquisa contrária, cobertura e seleção")
    d.add_argument("--achados", required=True, help="achados.json (dsr.achados.v3)")
    d.add_argument("-o", "--saida", help="onde gravar (padrão: o próprio --achados)")
    d.add_argument("--pesquisa-contraria", choices=sorted(ESTADOS_PESQUISA))
    d.add_argument("--consulta", nargs=3, action="append", default=[],
                   metavar=("FONTE", "TERMOS", "DATA"),
                   help="consulta da pesquisa contrária (repetível; DATA AAAA-MM-DD)")
    d.add_argument("--achado-contrario", action="append", default=[], metavar="ID",
                   help="ID de julgado contrário localizado (repetível)")
    d.add_argument("--concluida-em", help="AAAA-MM-DD (padrão: hoje, ao concluir)")
    d.add_argument("--cobertura", choices=sorted(COBERTURAS))
    d.add_argument("--revisada-em", help="AAAA-MM-DD da revisão da cobertura")
    d.add_argument("--valida-ate", help="AAAA-MM-DD até quando a cobertura vale")
    d.add_argument("--selecionar", action="append", default=[], metavar="ID",
                   help="leva o julgado à peça (repetível)")
    d.add_argument("--desselecionar", action="append", default=[], metavar="ID",
                   help="tira o julgado da peça (repetível)")
    d.add_argument("--fundamentacao-analogica")
    d.add_argument("--autoridade-substituta", action="append", default=None, metavar="ID",
                   help="substitui a lista de autoridades substitutas (repetível)")
    d.add_argument("--tese-central")
    d.add_argument("--fontes", help="fontes_oficiais.json (padrão: o do contrato)")
    a = ap.parse_args(argv)

    def sai(ok, rc, **extra):
        print(json.dumps({"ok": ok, **extra}, ensure_ascii=False))
        return rc

    destino = a.saida or a.achados
    try:
        dados = _ler_json(a.achados)
    except Exception as erro:
        return sai(False, 2, gravado=False, erros=[f"registro ilegível ({erro})"])
    novo, erros = aplicar_definicao(
        dados, pesquisa_contraria=a.pesquisa_contraria, consultas=a.consulta,
        achados_contrarios=a.achado_contrario, concluida_em=a.concluida_em,
        cobertura=a.cobertura, revisada_em=a.revisada_em, valida_ate=a.valida_ate,
        selecionar=a.selecionar, desselecionar=a.desselecionar,
        fundamentacao_analogica=a.fundamentacao_analogica,
        autoridades_substitutas=a.autoridade_substituta, tese_central=a.tese_central)
    if erros:
        return sai(False, 2, gravado=False, erros=erros)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import achado_contract
    except Exception as erro:
        return sai(False, 1, gravado=False, erros=[f"validador do contrato indisponível ({erro})"])
    kwargs = {"fontes_path": a.fontes} if a.fontes else {}
    violacoes = achado_contract.validar_documento(novo, **kwargs)
    if violacoes:
        return sai(False, 1, gravado=False, erros=violacoes)
    try:
        _gravar_atomico(novo, destino)
    except OSError as erro:
        return sai(False, 1, gravado=False, erros=[f"não foi possível gravar ({erro})"])
    est = novo["estrategia"]
    return sai(True, 0, gravado=True, saida=destino,
               pesquisa_contraria=(est.get("pesquisa_contraria") or {}).get("estado"),
               cobertura=est.get("cobertura_precedente"),
               selecionados=[x.get("id") for x in novo.get("achados") or []
                             if isinstance(x, dict) and x.get("selected_for_use") is True])


if __name__ == "__main__":
    raise SystemExit(_cli())
