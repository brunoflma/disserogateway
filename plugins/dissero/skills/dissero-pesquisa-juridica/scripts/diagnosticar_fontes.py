#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'diagnosticar_fontes.py — a `official_url` ABRE o julgado, ou abre outra coisa?'






































import argparse
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
FONTES = os.path.join(AQUI, "fontes_oficiais.json")
SUFIXOS_PADRAO = (".jus.br", ".gov.br", ".leg.br", ".mp.br", ".def.br")

CNJ = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

ESAJ_DOC = re.compile(r"getArquivo\.do\?[^#]*cdAcordao=\d{4,9}(?:&|$)", re.I)
ESAJ_CONSULTA = re.compile(r"(consultaCompleta|consultaSimples|resultadoCompleta|resultadoSimples)\.do", re.I)
STJ_DOC = re.compile(r"GetInteiroTeorDoAcordao\?[^#]*num_registro=\d{6,}", re.I)

SESSAO = re.compile(r"(ticket=|jsessionid|documentoSemLoginHTML|abrirDocumentoEdt|"
                    r"cdServico=\d+&?.*ticket|idProcessoDoc=\d+.*ca=[0-9a-f]{40,})", re.I)

PJE_PROCESSO = re.compile(r"ConsultaPublica/[^?]*listView\.seam\?[^#]*ca=[0-9a-f]{16,}", re.I)
BUSCA = re.compile(r"(pesquisar\.jsp|/pesquisa|search|consultaSimples\.do)", re.I)

SEM_PARAMETRO = re.compile(r"\.do/?$", re.I)


def _sufixos_oficiais(caminho=FONTES):
    """Os `sufixos_oficiais` do catálogo; o padrão quando o catálogo não abre ou não os traz."""
    try:
        sufixos = json.load(io.open(caminho, encoding="utf-8")).get("sufixos_oficiais")
    except Exception:
        return SUFIXOS_PADRAO
    if not isinstance(sufixos, list):
        return SUFIXOS_PADRAO
    return tuple(s.lower() for s in sufixos if isinstance(s, str) and s) or SUFIXOS_PADRAO


def classificar(url, sufixos=None):
    'Devolve (classe, explicação). Só a FORMA da URL — sem rede.'



    if not isinstance(url, str):
        return "ausente", f"official_url não é texto ({type(url).__name__})"
    u = url.strip()
    if not u:
        return "ausente", "achado sem official_url"
    sufixos = sufixos or _sufixos_oficiais()
    host = re.sub(r"^https?://", "", u).split("/")[0].lower()
    if not any(host.endswith(s) for s in sufixos):
        return "agregador", f"host {host} fora do catálogo de fontes oficiais"
    if SESSAO.search(u):
        return ("efemera", "URL com credencial de sessão (ticket/jsessionid/documento sem login): "
                           "abre para quem acabou de navegar e expira — o tribunal responde "
                           "'sua sessão expirou' no acesso a frio")
    if ESAJ_DOC.search(u) or STJ_DOC.search(u):
        return "documento", "padrão que entrega o inteiro teor"
    if PJE_PROCESSO.search(u):
        return ("processo", "página oficial do processo no PJe: confirma identidade e dá acesso aos "
                            "documentos; a ementa não está nela")
    if ESAJ_CONSULTA.search(u) and CNJ.search(u):
        return ("nao_abre", "número CNJ no parâmetro cdAcordao do e-SAJ, que espera id interno "
                            "numérico — abre o formulário de busca VAZIO")
    if SEM_PARAMETRO.search(u):
        return "nao_abre", "endpoint sem parâmetro algum — não resolve documento"
    if BUSCA.search(u) or ESAJ_CONSULTA.search(u):
        return "busca", "abre busca, não o acórdão"
    return "documento", "host oficial, padrão não catalogado (tratado como plausível)"


def diagnosticar(dados, fontes=FONTES):
    """(usados, diagnóstico) dos achados selecionados, com os sufixos do catálogo `fontes`."""
    achados = dados.get("achados", []) if isinstance(dados, dict) else (dados or [])
    usados = [a for a in achados if isinstance(a, dict) and a.get("selected_for_use") is True
              and a.get("use_status") in ("allowed", "pending")]
    sufixos = _sufixos_oficiais(fontes)
    out = []
    for i, a in enumerate(usados, 1):
        classe, motivo = classificar(a.get("official_url"), sufixos)
        conf = a.get("conferencia") or {}
        if classe in ("nao_abre", "busca") and conf.get("processo") and conf.get("codigo"):
            classe, motivo = ("conferencia_por_codigo",
                              "formulário de conferência do e-SAJ com processo e código "
                              "registrados: conferível, não é link quebrado")
        out.append({"i": i, "reference": a.get("reference", "")[:80],
                    "url": (a.get("official_url") or ""), "classe": classe, "motivo": motivo})
    return usados, out


def main():
    ap = argparse.ArgumentParser(description="Diagnostica se a official_url abre o julgado.")
    ap.add_argument("achados_json")
    ap.add_argument("--gravar", action="store_true", help="grava `diagnostico_link` em cada achado")
    ap.add_argument("--json", action="store_true", help="saída JSON")
    a = ap.parse_args()

    dados = json.load(io.open(a.achados_json, encoding="utf-8"))
    usados, diag = diagnosticar(dados)
    contagem = {}
    for d in diag:
        contagem[d["classe"]] = contagem.get(d["classe"], 0) + 1

    if a.gravar:
        for achado, d in zip(usados, diag):
            achado["diagnostico_link"] = {"classe": d["classe"], "motivo": d["motivo"],
                                          "avaliado_em_forma_da_url": True}
        json.dump(dados, io.open(a.achados_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        io.open(a.achados_json, "a", encoding="utf-8").write("\n")

    if a.json:
        print(json.dumps({"total": len(diag), "contagem": contagem, "achados": diag},
                         ensure_ascii=False))
    else:
        print(f"== DIAGNÓSTICO DE FONTES == {len(diag)} julgado(s) selecionado(s)")
        for classe in ("nao_abre", "efemera", "busca", "agregador", "ausente",
                       "conferencia_por_codigo", "processo", "documento"):
            itens = [d for d in diag if d["classe"] == classe]
            if not itens:
                continue
            motivos = sorted({d["motivo"] for d in itens})
            print(f"\n{classe.upper()} — {len(itens)}")
            for m in motivos:
                iguais = [d for d in itens if d["motivo"] == m]
                print(f"  · {m} ({len(iguais)})")
                for d in iguais:
                    print(f"      #{d['i']:2} {d['url'][:92]}")
        if a.gravar:
            print("\n`diagnostico_link` gravado em cada achado.")

    return 1 if (contagem.get("nao_abre") or contagem.get("ausente")
                 or contagem.get("efemera")) else 0


if __name__ == "__main__":
    sys.exit(main())
