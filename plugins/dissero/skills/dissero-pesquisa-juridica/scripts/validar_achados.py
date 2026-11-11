#!/usr/bin/env python3
"""Valida estritamente dsr.achados v2/v3 e reverifica confirmações automáticas."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

import acentuacao_pt
from achado_contract import FONTES_PADRAO, SCHEMA_PADRAO, texto, validar_documento

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
VERIFICADOR = os.path.join(AQUI, "verificar_citacao.py")


def _emitir_trace(violacoes):
    destino = os.environ.get("DSR_TRACE")
    if not destino:
        return
    try:
        with open(destino, "a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps({"fase": "verificacao", "evento": "validar_achados",
                                      "dados": {"violacoes": violacoes}}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def verificar_online(achado, fontes):
    citacao = achado["citation"]
    comando = [sys.executable, VERIFICADOR, "--url", texto(achado["official_url"]),
               "--natureza", achado["nature"], "--fontes", fontes]
    opcoes = {
        "--numero": citacao.get("case_number"), "--relator": citacao.get("rapporteur"),
        "--trecho": achado.get("syllabus_literal"), "--identificador": citacao.get("identifier"),
        "--status": citacao.get("status"), "--tipo-norma": citacao.get("norm_type"),
        "--numero-norma": citacao.get("norm_number"), "--data-norma": citacao.get("norm_date"),
        "--dispositivo": citacao.get("provision"), "--vigencia": citacao.get("validity")
    }
    for opcao, valor in opcoes.items():
        if texto(valor):
            comando.extend([opcao, texto(valor)])
    try:
        processo = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", timeout=60)
        saida = json.loads((processo.stdout or "{}").strip().splitlines()[-1])
        return saida.get("outcome"), saida.get("motivo", "")
    except Exception as erro:
        return "blocked", f"falha ao executar verificador: {erro}"


def avisar_acentuacao(dados):
    'AVISOS (não bloqueiam) de acentuação — a Relação de Precedentes é lida pelo advogado.'






    avisos = []
    for indice, achado in enumerate(dados.get("achados", []) or []):
        if not isinstance(achado, dict):
            continue
        ref = texto(achado.get("reference")) or ""
        if ref and acentuacao_pt.reacentuar(ref) != ref:
            avisos.append(f"achado[{indice}]: reference sem acentuação — grave o rótulo em "
                          f"português acentuado (ex.: 'Apelação Cível', '2ª Câmara', 'Órgão Especial')")
        for campo in ("syllabus_literal", "full_text"):
            if acentuacao_pt.parece_sem_acento(texto(achado.get(campo)) or ""):
                avisos.append(f"achado[{indice}]: {campo} aparentemente sem acentuação — "
                              f"transcreva o literal como está na fonte oficial (literal não se reacentua)")
    return avisos






_RX_REF_ITEM = re.compile(
    r"\b(?:item|t[óo]pico|cap[íi]tulo|subitem)\s+[IVXLC]+(?:\.\d{1,2})?\b", re.I)


def avisar_referencia_de_item(dados):
    """AVISOS sobre referência a item da peça gravada no `estrategia_uso.como_usar`."""
    avisos = []
    for indice, achado in enumerate(dados.get("achados", []) or []):
        if not isinstance(achado, dict):
            continue
        uso = achado.get("estrategia_uso")
        como = texto(uso.get("como_usar")) if isinstance(uso, dict) else ""
        achadas = _RX_REF_ITEM.findall(como)
        if achadas:
            avisos.append(
                f"achado[{indice}]: `estrategia_uso.como_usar` aponta para "
                f"{', '.join(sorted(set(achadas)))} da peça — se a peça for renumerada, esta "
                f"referência fica obsoleta EM SILÊNCIO e o memorando passa a mandar o advogado "
                f"ao item errado. Prefira descrever o LUGAR pelo assunto ('no capítulo da via "
                f"eleita') em vez do número")
    return avisos


def validar_procedencia_literal(dados):
    '(erros, avisos) da PROCEDÊNCIA do teor transcrito: o elo que liga o teor ao documento.'















    erros, avisos = [], []
    try:
        import procedencia_literal as pl
    except Exception as erro:
        return [], [f"conferência de procedência indisponível: {erro}"]
    for indice, achado in enumerate(dados.get("achados") or []):
        if not isinstance(achado, dict):
            continue
        if not texto(achado.get("syllabus_literal")):
            continue
        nivel, motivo = pl.conferir_achado(achado)
        if nivel == "verbatim":
            continue
        selecionado = achado.get("selected_for_use") is True
        liberado = achado.get("use_status") == "allowed"
        alvo = erros if (nivel == "normalizado" or (liberado and selecionado)) else avisos
        alvo.append(
            f"achado[{indice}]: TEOR SEM PROCEDÊNCIA VERBATIM ({nivel}) — {motivo}. "
            f"Transcrição de julgado sai exatamente como o tribunal escreveu, inclusive os "
            f"erros dele. Ligue o teor ao documento com `python scripts/atestar_literal.py "
            f"achados.json --id {texto(achado.get('id')) or '<id>'} --documento <acórdão>.pdf "
            f"-o achados.json`")
    return erros, avisos


def validar_fonte(dados, fontes=FONTES_PADRAO):
    'A `official_url` FOI COPIADA de algum lugar, ou foi MONTADA de memória?'















    erros, avisos = [], []
    try:
        import diagnosticar_fontes as dfontes
    except Exception as erro:
        return [], [f"diagnóstico de fontes indisponível: {erro}"]
    usados, diag = dfontes.diagnosticar(dados, fontes)
    for d, a in zip(diag, usados):
        i, classe = d["i"], d["classe"]
        if classe == "ausente":



            if (a.get("pendencia_fonte") or {}).get("falta"):
                avisos.append(f"achado[{i}]: fonte oficial A OBTER — pendência declarada em "
                              f"`pendencia_fonte` desde "
                              f"{(a.get('pendencia_fonte') or {}).get('desde', '?')}")
            else:
                erros.append(f"achado[{i}]: sem official_url e SEM pendência declarada — "
                             f"registre `pendencia_fonte` (o que falta e como obter) ou a fonte")
            continue
        if classe == "nao_abre":
            erros.append(f"achado[{i}]: official_url NÃO ABRE o julgado — {d['motivo']}")
        elif classe == "efemera":
            erros.append(f"achado[{i}]: official_url com credencial de SESSÃO — {d['motivo']}. "
                         f"Registre a URL durável e guarde esta em `atalho_documento_sessao`")
        elif classe == "busca":
            avisos.append(f"achado[{i}]: official_url abre BUSCA, não o acórdão — serve de trilha, "
                          f"não de fonte clicável")
        elif classe == "agregador" and not (a.get("fonte_aceita_pelo_advogado") or {}).get("em"):
            avisos.append(f"achado[{i}]: {d['motivo']} — agregador não prova teor; registre a fonte "
                          f"oficial ou o aceite do advogado")

        url = texto(a.get("official_url"))
        origem_declarada = (texto((a.get("discovery") or {}).get("url"))
                            or texto(a.get("url_origem"))
                            or (a.get("fonte_corrigida") or {}).get("por")
                            or (a.get("conferencia") or {}).get("origem_do_codigo")
                            or (a.get("atalho_documento_sessao") or {}).get("fornecido_por"))
        if url and not origem_declarada:
            erros.append(f"achado[{i}]: official_url SEM PROCEDÊNCIA — não veio de `discovery.url` "
                         f"nem de origem declarada (`url_origem`). URL montada de memória é "
                         f"invenção, como número de processo inventado: copie a que a ferramenta "
                         f"devolveu, ou deixe o campo vazio e registre a pendência")
    return erros, avisos


def validar(dados, sem_rede=False, schema=None, fontes=FONTES_PADRAO):
    schema = schema or SCHEMA_PADRAO
    erros = validar_documento(dados, schema, fontes)
    if erros:
        return erros
    for indice, achado in enumerate(dados["achados"]):
        verificacao = achado["verification"]
        if verificacao["result"] == "confirmed" and verificacao["method"] == "automatic":
            if sem_rede:
                erros.append(f"achado[{indice}]: confirmação automática exige reverificação online")
                continue
            resultado, motivo = verificar_online(achado, fontes)
            if resultado != "confirmed":
                erros.append(f"achado[{indice}]: reverificação retornou {resultado}: {motivo[:160]}")
    return erros


def main():
    parser = argparse.ArgumentParser(description="Gate estrito dos achados Dissero v2/v3")
    parser.add_argument("arquivo", help="JSON v2/v3 ou '-' para stdin")
    parser.add_argument("--fontes", default=FONTES_PADRAO)
    parser.add_argument("--schema", default=None,
                        help="schema v2 alternativo; v3 sempre reaproveita o núcleo v2 + extensão estratégica")
    parser.add_argument("--sem-rede", action="store_true")
    args = parser.parse_args()
    try:
        bruto = sys.stdin.read() if args.arquivo == "-" else open(args.arquivo, encoding="utf-8").read()
        dados = json.loads(bruto)
    except Exception as erro:
        print(json.dumps({"ok": False, "codigo": "JSON_INVALIDO", "erro": str(erro)}, ensure_ascii=False))
        return 2
    if not isinstance(dados, dict):
        print(json.dumps({"ok": False, "codigo": "SCHEMA_INVALIDO", "violacoes": ["$: esperado objeto v2/v3"]}, ensure_ascii=False))
        return 2
    if dados.get("schema_version") not in ("dsr.achados.v2", "dsr.achados.v3"):
        _emitir_trace(1)
        print(json.dumps({"ok": False, "codigo": "VERSAO_NAO_SUPORTADA",
                          "erro": "o gate aceita só dsr.achados.v2 e dsr.achados.v3. Registro "
                                  "em outra versão não tem conversão: refaça a pesquisa e grave "
                                  "em dsr.achados.v3"}, ensure_ascii=False))
        return 2
    if dados.get("achados") == []:
        out = {"ok": False, "codigo": "RESULTADO_ZERO", "total": 0, "pendencias": 0,
               "violacoes": ["nenhum achado encontrado; interrompa o fluxo e peça orientação obrigatória ao advogado"],
               "resumo": "BLOQUEADO — RESULTADO_ZERO"}
        _emitir_trace(1)
        print(json.dumps(out, ensure_ascii=False))
        return 1

    erros = validar(dados, args.sem_rede, args.schema, args.fontes)


    erros_fonte, avisos_fonte = validar_fonte(dados, args.fontes)
    erros_proc, avisos_proc = validar_procedencia_literal(dados)
    erros = list(erros) + erros_fonte + erros_proc
    pendencias = sum(1 for achado in dados.get("achados", []) if achado.get("use_status") == "pending" and achado.get("selected_for_use"))
    out = {"ok": not erros, "codigo": "OK" if not erros else "CONTRATO_INVALIDO", "total": len(dados.get("achados", [])),
           "pendencias": pendencias, "violacoes": erros,
           "resumo": "APROVADO" if not erros else f"REPROVADO ({len(erros)} violação(ões)) — não entregar"}
    avisos = (avisar_acentuacao(dados) + avisar_referencia_de_item(dados)
              + avisos_fonte + avisos_proc)
    if avisos:
        out["avisos"] = avisos
    _emitir_trace(len(erros))
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not erros else 1


if __name__ == "__main__":
    raise SystemExit(main())
