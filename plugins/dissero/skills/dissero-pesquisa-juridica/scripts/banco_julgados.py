#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'banco_julgados.py — o banco de julgados CONFERIDOS por tese, da banca (25/11/2026).'



















from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CHAVES_CITACAO = ("court", "case_number", "rapporteur", "judgment_date", "identifier", "status",
                  "norm_type", "norm_number", "norm_date", "provision", "validity")


def _t(v):
    return v.strip() if isinstance(v, str) else ""


def _sem_recibo_valido(achado, fontes):
    'True quando o achado gravado como liberado não é liberado pelo contrato: o mesmo critério do'





    try:
        import achado_contract
    except Exception:
        return True
    try:
        return (achado_contract.derivar_use_status(achado) != "allowed"
                or bool(achado_contract.motivos_das_regras(achado, fontes)))
    except Exception:
        return True


def _fontes():
    try:
        import achado_contract
        return achado_contract.carregar_json(achado_contract.FONTES_PADRAO)
    except Exception:
        return None


def exportar(dados):
    julgados, fora = [], []
    fontes = _fontes()
    for a in dados.get("achados") or []:
        if not isinstance(a, dict) or a.get("use_status") != "allowed":
            continue
        v = a.get("verification") or {}
        at = v.get("human_attestation") if isinstance(v.get("human_attestation"), dict) else {}
        ref = _t(a.get("reference"))



        if _sem_recibo_valido(a, fontes):
            fora.append(f"{ref or a.get('id')}: confirmação sem o recibo de encerramento da "
                        f"conferência")
            continue
        item = {"referencia": ref, "natureza": _t(a.get("nature")), "autoridade": _t(str(a.get("authority") or "")),
                "trecho": _t(a.get("syllabus_literal")), "conferido_em": _t(v.get("checked_at"))[:10],
                "citacao": {k: _t(str((a.get("citation") or {}).get(k) or "")) for k in CHAVES_CITACAO
                            if (a.get("citation") or {}).get(k)}}
        uso = a.get("estrategia_uso")
        if isinstance(uso, dict) and _t(uso.get("como_usar")):
            item["tese_em_uma_frase"] = _t(uso.get("como_usar"))
        if _t(a.get("official_url")):
            item["url_oficial"] = _t(a.get("official_url"))
        elif isinstance(at.get("documento"), dict):
            d = at["documento"]
            item["documento"] = {"sha256": _t(d.get("sha256")), "origem": _t(d.get("origem")),
                                 "arquivo": _t(d.get("arquivo"))}
        else:
            fora.append(f"{ref or a.get('id')}: sem fonte conferida")
            continue
        if not item["trecho"] or not re.match(r"\d{4}-\d{2}-\d{2}$", item["conferido_em"]):
            fora.append(f"{ref or a.get('id')}: sem trecho ou sem data da conferência")
            continue
        julgados.append(item)
    return julgados, fora


def _slug(t):
    import unicodedata
    s = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40]


def importar(texto_resposta, hoje):
    ini = texto_resposta.find("{")
    if ini < 0:
        raise ValueError("o texto não traz o JSON do banco: grave a resposta de julgados_conferidos inteira")
    corpo = json.loads(texto_resposta[ini:])
    tese = _t(corpo.get("tese"))
    achados, fora = [], []
    for n, j in enumerate(corpo.get("julgados") or [], 1):
        if not isinstance(j, dict) or not _t(j.get("trecho")):
            continue
        if _t(j.get("autoridade")) not in ("A", "B", "C", "D", "E"):

            fora.append(f"{_t(j.get('referencia')) or n}: sem a força do precedente (A a E) no banco")
            continue
        fonte = j.get("fonte") or {}
        url = _t(fonte.get("url_oficial"))
        cit = {k: (_t((j.get("citacao") or {}).get(k)) or None) for k in CHAVES_CITACAO}
        conferido = _t(j.get("conferido_em"))
        try:
            dias = (hoje - date.fromisoformat(conferido)).days
        except ValueError:
            dias = None
        achado = {
            "id": f"banco-{_slug(tese)}-{n}", "reference": _t(j.get("referencia")),
            "nature": _t(j.get("natureza")) or "acordao", "authority": _t(j.get("autoridade")),
            "citation": cit, "discovery": {"provider": "banco_da_banca", "url": url or None},
            "official_url": url or None, "syllabus_literal": _t(j.get("trecho")), "full_text": None,
            "verification": {"result": "partial", "method": "none", "checked_at": None, "final_url": url or None,
                             "signals": {"banco_da_banca": True, "ultima_conferencia": conferido,
                                         "dias_desde_a_conferencia": dias, "tese_do_banco": tese,
                                         "fonte_do_banco": fonte},
                             "human_attestation": None},
            "selected_for_use": False, "use_status": "pending",
        }
        if len(_t(j.get("tese_em_uma_frase"))) >= 20:
            achado["estrategia_uso"] = {"posicao": "favoravel", "como_usar": _t(j.get("tese_em_uma_frase"))}
        achados.append(achado)
    return tese, achados, fora


def main():
    ap = argparse.ArgumentParser(description="Banco de julgados conferidos da banca (exportar/importar)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("exportar")
    pe.add_argument("achados")
    pe.add_argument("--tese", required=True)
    pe.add_argument("-o", "--saida", required=True)
    pi = sub.add_parser("importar")
    pi.add_argument("resposta")
    pi.add_argument("-o", "--saida", required=True)
    pi.add_argument("--hoje", help="AAAA-MM-DD (padrão: hoje)")
    a = ap.parse_args()
    try:
        if a.cmd == "exportar":
            dados = json.load(open(a.achados, encoding="utf-8"))
            julgados, fora = exportar(dados)
            if not julgados:
                print(json.dumps({"ok": False, "erro": "nenhum achado confirmado com fonte conferida", "fora": fora},
                                 ensure_ascii=False))
                return 1
            json.dump({"tese": a.tese, "julgados": julgados}, open(a.saida, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            print(json.dumps({"ok": True, "saida": a.saida, "julgados": len(julgados), "fora": fora}, ensure_ascii=False))
            return 0
        hoje = date.fromisoformat(a.hoje) if a.hoje else date.today()
        tese, achados, fora = importar(open(a.resposta, encoding="utf-8").read(), hoje)
        if not achados:
            print(json.dumps({"ok": False, "erro": "o banco não trouxe julgado aproveitável", "fora": fora},
                             ensure_ascii=False))
            return 1
        json.dump({"schema_version": "dsr.achados.v2", "tema": tese, "achados": achados},
                  open(a.saida, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(json.dumps({"ok": True, "saida": a.saida, "tese": tese, "pendentes": len(achados), "fora": fora,
                          "o_que_fazer": "todos entram PENDENTES: mostre a lista curta (folha_atestacao.py) e "
                                         "registre a resposta do advogado; a data da última conferência vai em "
                                         "cada item"}, ensure_ascii=False))
        return 0
    except (OSError, ValueError) as e:
        print(json.dumps({"ok": False, "erro": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
