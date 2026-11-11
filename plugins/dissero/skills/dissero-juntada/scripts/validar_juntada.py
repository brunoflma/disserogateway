#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'validar_juntada.py — gate da juntada: contrato do ledger e cruzamento com a conferência.'

























import sys, os, json, argparse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import conferencia_contract as conf
import juntada_contract as jc


def _saida(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False))
    return code


def _forma_invalida(tracker):
    """Descrição do defeito de forma que impede ler o tracker, ou "" quando a forma serve."""
    if not isinstance(tracker, dict):
        return f"o arquivo não é um objeto JSON (veio {type(tracker).__name__})"
    documentos = tracker.get("documentos")
    if documentos is not None and not isinstance(documentos, list):
        return f"`documentos` não é lista (veio {type(documentos).__name__})"
    for posicao, doc in enumerate(documentos or []):
        if not isinstance(doc, dict):
            return f"documentos[{posicao}] não é objeto (veio {type(doc).__name__})"

        status, ids = doc.get("status"), doc.get("evidence_ids")
        if isinstance(status, (list, dict)):
            return f"documentos[{posicao}].status não é texto (veio {type(status).__name__})"
        if ids is not None and not isinstance(ids, list):
            return f"documentos[{posicao}].evidence_ids não é lista (veio {type(ids).__name__})"
    return ""


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Valida o ledger da juntada e cruza com a conferência")
    ap.add_argument("tracker")
    ap.add_argument("--conferencia", help="CONFERENCIA.json (padrão: campo 'conferencia' do tracker; "
                                          "caminho relativo é procurado primeiro na pasta do tracker)")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.tracker):
        return _saida({"ok": False, "erro": f"tracker não encontrado: {args.tracker}"}, 2)
    try:
        tracker = json.loads(open(args.tracker, encoding="utf-8").read())
    except Exception as e:
        return _saida({"ok": False, "erro": f"tracker ilegível: {e}"}, 1)


    forma = _forma_invalida(tracker)
    if forma:
        return _saida({"ok": False, "erro": f"tracker fora do contrato dsr.juntada.v1: {forma}. "
                                            f"Corrija {os.path.basename(args.tracker)} e rode "
                                            "de novo."}, 1)

    violacoes = jc.validar_documento(tracker)
    avisos = []

    caminho_conf = args.conferencia or jc.texto(tracker.get("conferencia"))
    if caminho_conf and not os.path.isabs(caminho_conf):
        candidato = os.path.join(os.path.dirname(os.path.abspath(args.tracker)), caminho_conf)
        caminho_conf = candidato if os.path.isfile(candidato) else caminho_conf

    curados = [d for d in (tracker.get("documentos") or []) if d.get("status") == "curado"]


    cruzou = False
    if not caminho_conf:
        if curados:
            avisos.append(f"cruzamento NÃO executado (sem --conferencia): {len(curados)} documento(s) "
                          "curado(s) sem confronto contra a conferência de ingestão — sem ela, nada "
                          "prova que foram lidos")
    elif not os.path.isfile(caminho_conf):
        violacoes.append(f"conferência apontada não existe: {caminho_conf} — documento curado sem "
                         "conferência é documento sem prova de leitura (§2.8)")
    else:
        try:
            conferencia = json.loads(open(caminho_conf, encoding="utf-8").read())
        except Exception as e:
            violacoes.append(f"conferência ilegível ({caminho_conf}): {e}")
        else:
            erros_conf = conf.validar_documento(conferencia)
            if erros_conf:
                violacoes.append("conferência de ingestão NÃO está conforme o contrato "
                                 "dsr.conferencia.v1 — rode validar_conferencia.py antes: "
                                 + "; ".join(erros_conf[:3]))
            else:
                violacoes.extend(jc.cruzar_com_conferencia(tracker, conferencia))
                cruzou = True

    por_status = {}
    for d in tracker.get("documentos") or []:
        por_status[d.get("status")] = por_status.get(d.get("status"), 0) + 1

    payload = {"ok": not violacoes, "tracker": os.path.abspath(args.tracker),
               "conferencia": caminho_conf or "", "contador": tracker.get("contador"),
               "documentos": len(tracker.get("documentos") or []), "por_status": por_status,
               "cruzamento": "executado" if cruzou else "nao_executado",
               "violacoes": violacoes, "avisos": avisos}
    if violacoes:
        payload["nota"] = ("JUNTADA REPROVADA — conserte o tracker antes de citar (Doc. NN) na peça; "
                           "o `lint_peca.py --juntada` lê este mesmo ledger ao conferir o .docx")
        return _saida(payload, 1)
    payload["nota"] = ("juntada conforme — a peça pode citar os documentos curados e o linter pode "
                       "cruzar com `lint_peca.py <peca>.docx --juntada " + os.path.basename(args.tracker) + "`")
    return _saida(payload, 0)


if __name__ == "__main__":
    sys.exit(main())
