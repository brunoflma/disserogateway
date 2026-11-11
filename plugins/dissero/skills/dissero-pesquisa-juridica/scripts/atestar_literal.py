#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'atestar_literal.py — liga o teor do dataset ao DOCUMENTO do tribunal, com hash.'









































from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

import procedencia_literal as pl
from achado_contract import FONTES_PADRAO, carregar_json, texto, validar_documento
from verificar_citacao import _norm, confere_numero, confere_relator


VERSOES_ACEITAS = ("dsr.achados.v2", "dsr.achados.v3")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

RX_CNJ = re.compile(r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}")


REMEDIO_POPPLER = ("Instale o poppler (Windows: `winget install oschwartz10612.Poppler`; "
                   "Debian/Ubuntu: `apt install poppler-utils`; macOS: `brew install poppler`) "
                   "e deixe o `pdftotext` no PATH, ou informe o binário por --pdftotext.")


def _pdftotext(informado=None):
    """Caminho do `pdftotext`: o informado, ou o do PATH. Nunca um caminho de máquina."""
    return shutil.which(informado or "pdftotext")


def extrair(caminho, pdftotext=None):
    'Texto do documento. PDF pelo poppler; .txt/.md lidos direto.'





    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".txt", ".md"):
        raw = open(caminho, "rb").read()
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return ""
    if ext != ".pdf":
        raise ValueError(f"tipo não suportado para conferência literal: {ext}")
    exe = _pdftotext(pdftotext)
    if not exe:
        onde = f"em {pdftotext}" if pdftotext else "no PATH"
        raise RuntimeError(
            f"pdftotext (poppler) não encontrado {onde} — sem extrator não há conferência "
            f"literal, e conferir de olho é o que este script existe para substituir. "
            f"{REMEDIO_POPPLER}")
    saida = caminho + ".conferencia.txt"
    r = subprocess.run([exe, "-layout", caminho, saida], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or not os.path.isfile(saida):
        raise RuntimeError(f"extração falhou: {(r.stderr or '').strip()[:200]}")
    raw = open(saida, "rb").read()
    os.remove(saida)
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def _casar_por_cnj(achados, pasta):
    """{id do achado: caminho do PDF} pelo número do processo no NOME do arquivo."""
    porq = {}
    for nome in os.listdir(pasta):
        if not nome.lower().endswith((".pdf", ".txt", ".md")):
            continue
        for m in RX_CNJ.finditer(nome):
            porq[re.sub(r"\D", "", m.group(0))] = os.path.join(pasta, nome)
    saida = {}
    for a in achados:
        if not isinstance(a, dict):
            continue
        ref = texto(a.get("reference")) + " " + texto((a.get("citation") or {}).get("case_number"))
        for m in RX_CNJ.finditer(ref):
            alvo = porq.get(re.sub(r"\D", "", m.group(0)))
            if alvo:
                saida[texto(a.get("id"))] = alvo
                break
    return saida


def _numero_de(achado):
    c = achado.get("citation") or {}
    return texto(c.get("case_number")) or texto(c.get("identifier"))


def faltas_de_identidade(achado, extraido):
    'O que da MOLDURA não aparece no documento: o número sempre; o relator, quando o registro'

    numero = _numero_de(achado)
    faltas = []
    if not numero or not confere_numero(numero, extraido):
        faltas.append(f"o número {numero or '(não registrado)'}")
    relator = texto((achado.get("citation") or {}).get("rapporteur"))
    if relator and confere_relator(relator, _norm(extraido)) is False:
        faltas.append(f"o relator {relator}")
    return faltas


def _casar_por_conteudo(achados, documentos, textos):
    '({id: documento}, [ids com trecho achado em documento de outro número]).'



    mapa, sem_numero_no_doc = {}, []
    for a in achados:
        ident, literal, numero = texto(a.get("id")), texto(a.get("syllabus_literal")), _numero_de(a)
        if not literal or a.get("use_status") == "prohibited":
            continue
        docs = [d for d in documentos if d in textos]
        por_numero = [d for d in docs if numero and confere_numero(numero, textos[d])]
        if por_numero:
            mapa[ident] = por_numero[0]
            continue
        com_trecho = [d for d in docs if pl.nivel(literal, textos[d]) == "verbatim"]
        if com_trecho and not numero:
            mapa[ident] = com_trecho[0]
        elif com_trecho:
            sem_numero_no_doc.append((ident, com_trecho[0], numero))
    return mapa, sem_numero_no_doc


def atestar(achado, documento, ts=None, pdftotext=None, extraido=None):
    """(ok, registro, motivo) para UM achado contra UM documento."""
    literal = texto(achado.get("syllabus_literal"))
    if not literal:
        return False, None, "achado sem `syllabus_literal` — não há teor a conferir"
    if extraido is None:
        extraido = extrair(documento, pdftotext)
    if not extraido.strip():
        return False, None, (f"o documento não devolveu texto ({os.path.basename(documento)}) "
                             f"— PDF só-imagem não serve para conferência literal: obtenha a "
                             f"versão pesquisável ou copie o trecho da tela")
    reg = pl.registrar(literal, extraido, origem=os.path.abspath(documento), em=ts)
    if reg["nivel"] == "verbatim":
        return True, reg, "verbatim"
    if reg["nivel"] == "normalizado":
        return False, reg, ("o teor só confere DEPOIS de apagar acento e pontuação — logo, "
                            "acento ou pontuação foram ALTERADOS em relação ao original. "
                            + str(reg.get("divergencia") or ""))
    return False, reg, ("o teor NÃO foi localizado no documento. " +
                        str(reg.get("divergencia") or ""))


def main():
    ap = argparse.ArgumentParser(
        description="Liga o teor do dataset ao documento do tribunal, com hash")
    ap.add_argument("arquivo", help="achados.json (contrato dsr.achados.v2 ou v3)")
    ap.add_argument("--id", help="atestar UM achado")
    ap.add_argument("--documento", help="PDF/TXT do acórdão (com --id)")
    ap.add_argument("--todos", action="store_true", help="atestar todos, casando por CNJ")
    ap.add_argument("--pasta", help="pasta de documentos (com --todos)")
    ap.add_argument("--documentos", nargs="+",
                    help="PDFs soltos na conversa, casados pelo número no conteúdo")
    ap.add_argument("--atestar", action="store_true",
                    help="registra a conferência do pendente que bateu em número e trecho")
    ap.add_argument("--ator", help="quem atesta (padrão: o nome do perfil)")
    ap.add_argument("--data", help="data da atestação (padrão: hoje)")
    ap.add_argument("--fontes", default=FONTES_PADRAO)
    ap.add_argument("--ts", help="timestamp do chamador")
    ap.add_argument("--pdftotext", help="caminho do binário pdftotext (padrão: PATH)")
    ap.add_argument("-o", "--saida", required=True)
    a = ap.parse_args()

    try:
        dados = carregar_json(a.arquivo)
    except Exception as e:
        print(json.dumps({"ok": False, "erro": str(e)}, ensure_ascii=False)); return 2
    if not isinstance(dados, dict) or dados.get("schema_version") not in VERSOES_ACEITAS:
        print(json.dumps({"ok": False, "erro": "contrato dsr.achados.v2 ou v3 obrigatório"},
                         ensure_ascii=False)); return 2
    achados = [x for x in (dados.get("achados") or []) if isinstance(x, dict)]

    ator = data = ""
    if a.atestar:
        import registrar_confirmacao_manual as rcm
        ator = texto(a.ator) or rcm.ator_do_perfil()
        data = texto(a.data) or rcm.hoje()
        if not ator:
            print(json.dumps({"ok": False, "erro": "--atestar precisa de quem atesta: o nome vem "
                              "do perfil do advogado (advogado.nome), que não está configurado "
                              "nesta máquina; configure o perfil ou passe --ator"},
                             ensure_ascii=False)); return 2

    textos, ilegiveis, identidade = {}, [], []
    if a.documentos:
        for doc in a.documentos:
            try:
                textos[doc] = extrair(doc, a.pdftotext)
            except Exception as e:
                ilegiveis.append({"documento": os.path.basename(doc), "motivo": str(e)})
                continue
            if not textos[doc].strip():
                del textos[doc]
                ilegiveis.append({"documento": os.path.basename(doc), "motivo":
                                  "o documento não devolveu texto (PDF só-imagem): obtenha a "
                                  "versão pesquisável ou responda pela lista"})
        mapa, sem_numero = _casar_por_conteudo(achados, a.documentos, textos)
        identidade = [{"id": i, "documento": os.path.basename(d),
                       "motivo": f"o trecho está no documento, mas o número {n} não aparece "
                                 f"nele: confira se é o acórdão certo"}
                      for i, d, n in sem_numero]
    elif a.todos:
        if not a.pasta or not os.path.isdir(a.pasta):
            print(json.dumps({"ok": False, "erro": "--todos exige --pasta válida"},
                             ensure_ascii=False)); return 2
        mapa = _casar_por_cnj(achados, a.pasta)
    else:
        if not a.id or not a.documento:
            print(json.dumps({"ok": False, "erro": "informe --id e --documento, ou --todos"},
                             ensure_ascii=False)); return 2
        mapa = {a.id: a.documento}

    atestados, divergentes, sem_documento, confirmados = [], [], [], []
    for achado in achados:
        ident = texto(achado.get("id"))
        doc = mapa.get(ident)
        if not doc:
            if texto(achado.get("syllabus_literal")):
                sem_documento.append(ident)
            continue
        try:
            if doc not in textos:
                textos[doc] = extrair(doc, a.pdftotext)
            ok, reg, motivo = atestar(achado, doc, a.ts, a.pdftotext, textos[doc])
        except Exception as e:
            divergentes.append({"id": ident, "motivo": f"falha ao extrair: {e}"}); continue
        if not ok:
            divergentes.append({"id": ident, "motivo": motivo,
                                "documento": os.path.basename(doc)})
            continue
        regs = [r for r in (achado.get("procedencia_literal") or [])
                if isinstance(r, dict) and r.get("campo") != "syllabus_literal"]
        achado["procedencia_literal"] = regs + [reg]
        atestados.append(ident)
        if a.atestar and achado.get("use_status") == "pending":
            faltas = faltas_de_identidade(achado, textos[doc])
            if faltas:
                divergentes.append({"id": ident, "documento": os.path.basename(doc),
                                    "motivo": f"o trecho confere, mas {' e '.join(faltas)} não "
                                              f"aparece(m) no documento: confira se é o "
                                              f"acórdão certo"})
                continue
            url = texto(achado.get("official_url"))
            declaracao = (f"PDF do inteiro teor obtido pelo advogado na fonte oficial "
                          f"({os.path.basename(doc)}); a máquina localizou no documento o "
                          f"número e o relator registrados e conferiu o trecho verbatim.")
            ok_at, erro = rcm._atestar(achado, ator, data, url, declaracao,
                                       {"documento_conferido_por_maquina": True,
                                        "documento_sha256_extracao": reg.get("sha256_extracao")})
            if ok_at:
                confirmados.append(ident)
            else:
                divergentes.append({"id": ident, "motivo": erro,
                                    "documento": os.path.basename(doc)})

    divergentes += identidade
    violacoes = validar_documento(dados, fontes_path=a.fontes) if confirmados else []
    out = {"ok": not divergentes and not violacoes, "atestados": atestados,
           "divergentes": divergentes, "sem_documento": sem_documento}
    if a.atestar:
        out.update({"confirmados": confirmados, "ator": ator, "data": data})
    if a.documentos:
        usados = set(mapa.values())
        out["sem_correspondencia"] = [os.path.basename(d) for d in a.documentos
                                      if d in textos and d not in usados]
        out["ilegiveis"] = ilegiveis
    if violacoes:
        out["violacoes"] = violacoes
        out["resumo"] = "a atestação violaria o contrato do dataset — nada foi gravado"
        print(json.dumps(out, ensure_ascii=False)); return 1
    if divergentes:


        out["resumo"] = (f"{len(divergentes)} divergência(s) — nada foi gravado. Cada uma é "
                         f"teor que NÃO corresponde ao documento do tribunal: corrija o "
                         f"`syllabus_literal` copiando do documento, sem adaptar nada")
        print(json.dumps(out, ensure_ascii=False)); return 1
    with open(a.saida, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    out["saida"] = a.saida
    out["resumo"] = (f"{len(atestados)} achado(s) com teor conferido VERBATIM contra o "
                     f"documento do tribunal"
                     + (f"; {len(confirmados)} registrado(s) como conferido(s) pelo advogado"
                        if a.atestar else "")
                     + (f"; {len(sem_documento)} sem documento para conferir (seguem sem "
                        f"procedência)" if sem_documento else ""))
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
