#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'avaliar_pseudonimizacao.py — MEDE a pseudonimização contra um corpus gabaritado.'


























from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import pseudonimizar_local as pl

GABARITO_SCHEMA = "dsr.pseudonimizacao.gabarito.v1"
RELATORIO_SCHEMA = "dsr.pseudonimizacao.avaliacao.v1"
ENV_CORPUS = "DSR_PSEUDO_EVAL_CORPUS"


def _sha12(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]


def _coberto(ini, fim, mascarados):
    """Ocorrência coberta quando TODO o seu intervalo está dentro de trechos mascarados."""
    resto = [(ini, fim)]
    for a, b in mascarados:
        novo = []
        for x, y in resto:
            if b <= x or a >= y:
                novo.append((x, y))
                continue
            if a > x:
                novo.append((x, a))
            if b < y:
                novo.append((b, y))
        resto = novo
        if not resto:
            return True
    return not resto


def carregar_corpus(pasta):
    """Lista de (nome, texto, gabarito, entidades_ner|None). Gabarito inválido é erro dito."""
    itens, erros = [], []
    for txt in sorted(glob.glob(os.path.join(pasta, "*.txt"))):
        base = txt[:-4]
        gab = base + ".gabarito.json"
        if not os.path.isfile(gab):
            erros.append(f"{os.path.basename(txt)}: sem gabarito ({os.path.basename(gab)})")
            continue
        try:
            with open(txt, encoding="utf-8") as f:
                texto = f.read()
            with open(gab, encoding="utf-8") as f:
                g = json.load(f)
        except (OSError, json.JSONDecodeError) as erro:
            erros.append(f"{os.path.basename(txt)}: ilegível ({erro})")
            continue
        if not isinstance(g, dict) or g.get("schema_version") != GABARITO_SCHEMA \
                or not isinstance(g.get("ocorrencias"), list):
            erros.append(f"{os.path.basename(gab)}: schema inválido (esperado {GABARITO_SCHEMA})")
            continue
        ocorr = []
        for i, o in enumerate(g["ocorrencias"]):
            try:
                ini, fim = int(o["inicio"]), int(o["fim"])
                tipo = str(o["tipo"]).upper()
            except (KeyError, TypeError, ValueError):
                erros.append(f"{os.path.basename(gab)}: ocorrência {i} sem tipo/inicio/fim")
                continue
            if not (0 <= ini < fim <= len(texto)):
                erros.append(f"{os.path.basename(gab)}: ocorrência {i} fora do texto")
                continue
            ocorr.append({"tipo": tipo, "inicio": ini, "fim": fim})
        ner = None
        ner_path = base + ".ner.json"
        if os.path.isfile(ner_path):
            try:
                with open(ner_path, encoding="utf-8") as f:
                    bruto = json.load(f)
                ner = bruto.get("ocorrencias") if isinstance(bruto, dict) else bruto
            except (OSError, json.JSONDecodeError) as erro:
                erros.append(f"{os.path.basename(ner_path)}: ilegível ({erro})")
        itens.append((os.path.basename(base), texto, ocorr, ner))
    return itens, erros


def avaliar(itens, mascarar_locais=True, estrategia="marcador"):
    """Roda a camada em cada documento e consolida as duas métricas + o inventário de vazamentos."""
    por_tipo = {}
    valores = {}
    docs = []
    for nome, texto, ocorr, ner in itens:
        r = pl.pseudonimizar_texto(texto, entidades_ner=ner, mascarar_locais=mascarar_locais,
                                   estrategia=estrategia)
        mascarados = [(m["inicio"], m["fim"]) for m in r["mapping"]]
        cob_doc = 0
        for o in ocorr:
            valor = texto[o["inicio"]:o["fim"]]
            chave = (o["tipo"], pl._chave_de_entidade(o["tipo"], valor))
            v = valores.setdefault(chave, {"tipo": o["tipo"], "sha12": _sha12(valor), "valor": valor,
                                           "ocorrencias": 0, "cobertas": 0, "vazamentos": []})
            pt = por_tipo.setdefault(o["tipo"], {"ocorrencias": 0, "cobertas": 0})
            v["ocorrencias"] += 1
            pt["ocorrencias"] += 1
            if _coberto(o["inicio"], o["fim"], mascarados):
                v["cobertas"] += 1
                pt["cobertas"] += 1
                cob_doc += 1
            else:
                v["vazamentos"].append({"documento": nome, "inicio": o["inicio"], "fim": o["fim"]})
        docs.append({"documento": nome, "ocorrencias_gabarito": len(ocorr), "cobertas": cob_doc,
                     "mascaradas_pela_camada": len(r["mapping"]), "com_ner": ner is not None,
                     "ner_descartados": len(r["ner_descartados"]),


                     "auditoria_aprovada": bool(r["auditoria_residual"].get("aprovada")),
                     "residuos_por_tipo": r["auditoria_residual"].get("por_tipo") or {}})
    total = sum(p["ocorrencias"] for p in por_tipo.values())
    cobertas = sum(p["cobertas"] for p in por_tipo.values())
    protegidos = sum(1 for v in valores.values() if not v["vazamentos"])
    vazamentos = sorted(
        ({"tipo": v["tipo"], "sha12": v["sha12"], "valor": v["valor"], "ocorrencias": v["ocorrencias"],
          "cobertas": v["cobertas"], "onde": v["vazamentos"]} for v in valores.values() if v["vazamentos"]),
        key=lambda x: (x["tipo"], x["sha12"]))
    for p in por_tipo.values():
        p["recall"] = round(p["cobertas"] / p["ocorrencias"], 4) if p["ocorrencias"] else None
    return {
        "schema_version": RELATORIO_SCHEMA,
        "documentos": len(itens),
        "ocorrencias": total, "ocorrencias_cobertas": cobertas,
        "recall_por_ocorrencia": round(cobertas / total, 4) if total else None,
        "valores_unicos": len(valores), "valores_protegidos": protegidos,
        "protecao_por_valor_unico": round(protegidos / len(valores), 4) if valores else None,
        "por_tipo": dict(sorted(por_tipo.items())),
        "vazamentos": vazamentos,
        "por_documento": docs,
        "documentos_reprovados_na_auditoria": sum(1 for d in docs if not d["auditoria_aprovada"]),
        "mascarar_locais": mascarar_locais, "estrategia": estrategia,
        "leitura": "recall diz quanto do texto foi tratado; proteção por valor único diz quantas pessoas/identificadores "
                   "ficaram SEM nenhuma exposição — é este o número do sigilo. Valor com uma ocorrência exposta conta "
                   "como vazado, ainda que as demais estejam cobertas.",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Mede recall por ocorrência e proteção por valor único da pseudonimização "
                                            "contra um corpus gabaritado (fora do repositório).")
    p.add_argument("--corpus", default=os.environ.get(ENV_CORPUS) or "",
                   help=f"diretório com <nome>.txt + <nome>.gabarito.json (padrão: ${ENV_CORPUS})")
    p.add_argument("--minimo-protecao", type=float, default=None,
                   help="reprova (exit 1) se a proteção por valor único ficar abaixo deste valor (0–1)")
    p.add_argument("--minimo-recall", type=float, default=None,
                   help="reprova (exit 1) se o recall por ocorrência ficar abaixo deste valor (0–1)")
    p.add_argument("--sem-locais", action="store_true", help="não mascara LOCAL vindo do NER")
    p.add_argument("--estrategia", choices=pl.ESTRATEGIAS, default="marcador")
    p.add_argument("--mostrar-valores", action="store_true",
                   help="imprime o valor vazado em claro (por padrão só tipo, posição e hash)")
    p.add_argument("-o", "--saida", help="grava o relatório JSON neste caminho")
    a = p.parse_args(argv)
    if not a.corpus or not os.path.isdir(a.corpus):
        print(json.dumps({"ok": True, "pulado": True, "schema_version": RELATORIO_SCHEMA,
                          "motivo": f"sem corpus gabaritado (--corpus ou ${ENV_CORPUS}); a medição foi PULADA, "
                                    f"não aprovada — nenhum número de cobertura pode ser declarado sem corpus"},
                         ensure_ascii=False))
        return 0
    itens, erros = carregar_corpus(a.corpus)
    if erros and not itens:
        print(json.dumps({"ok": False, "codigo": "CORPUS_INVALIDO", "erros": erros}, ensure_ascii=False))
        return 2
    rel = avaliar(itens, mascarar_locais=not a.sem_locais, estrategia=a.estrategia)
    rel["erros_corpus"] = erros
    if not a.mostrar_valores:
        for v in rel["vazamentos"]:
            v.pop("valor", None)
    reprovacoes = []
    if a.minimo_protecao is not None and (rel["protecao_por_valor_unico"] or 0) < a.minimo_protecao:
        reprovacoes.append(f"proteção por valor único {rel['protecao_por_valor_unico']} < mínimo {a.minimo_protecao}")
    if a.minimo_recall is not None and (rel["recall_por_ocorrencia"] or 0) < a.minimo_recall:
        reprovacoes.append(f"recall por ocorrência {rel['recall_por_ocorrencia']} < mínimo {a.minimo_recall}")
    rel["ok"] = not reprovacoes
    rel["reprovacoes"] = reprovacoes
    if a.saida:
        os.makedirs(os.path.dirname(os.path.abspath(a.saida)) or ".", exist_ok=True)
        with open(a.saida, "w", encoding="utf-8") as f:
            json.dump(rel, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(json.dumps(rel, ensure_ascii=False))
    return 1 if reprovacoes else 0


if __name__ == "__main__":
    sys.exit(main())
