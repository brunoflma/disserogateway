#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'metricas_pecas.py — o ganho do uso, medido peça a peça e semana a semana.'


































import argparse
import datetime
import json
import os
import statistics
import sys

NOME_ESTADO = "PECA_STATE.json"
NOME_METRICAS = "METRICAS.jsonl"
PASTA_VERSOES = "_versoes"
TIPO_ERRO = "erro_pos_protocolo"



PULAR = {PASTA_VERSOES, ".git", "__pycache__", "node_modules"}




def _data_hora(valor):
    'Converte o texto de uma marca de tempo em datetime com fuso (UTC se vier sem fuso).'


    if not isinstance(valor, str) or not valor.strip():
        return None
    t = valor.strip()
    if t.endswith(("Z", "z")):
        t = t[:-1] + "+00:00"
    try:
        d = datetime.datetime.fromisoformat(t)
    except ValueError:
        try:
            d = datetime.datetime.combine(datetime.date.fromisoformat(t[:10]), datetime.time())
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d


def _semana(d):
    """Semana ISO no formato AAAA-Www (a semana começa na segunda)."""
    ano, sem, _ = d.isocalendar()
    return f"{ano}-W{sem:02d}"


def _lista(v):
    return v if isinstance(v, list) else []


def _dic(v):
    return v if isinstance(v, dict) else {}




def _ler_json(caminho):
    try:
        with open(caminho, "rb") as fh:
            dado = json.loads(fh.read().decode("utf-8-sig"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return dado if isinstance(dado, dict) else None


def _marcas(st):
    'As marcas de tempo de um estado que podem marcar o início. Ficam de fora as da própria'


    vals = [st.get("atualizado"), st.get("canonico_em")]
    for nome, reg in _dic(st.get("fases")).items():
        if nome != "entrega":
            vals.append(_dic(reg).get("concluida_em"))
    for chave in ("reaberturas", "reinicios", "correcoes_modo"):
        vals.extend(_dic(e).get("em") for e in _lista(st.get(chave)))
    return [d for d in (_data_hora(v) for v in vals) if d is not None]


def _versoes(pasta_estado):
    """Estados guardados em `_versoes/` ao lado do PECA_STATE (recomeços do zero)."""
    pasta = os.path.join(pasta_estado, PASTA_VERSOES)
    try:
        nomes = sorted(os.listdir(pasta))
    except OSError:
        return []
    out = []
    for n in nomes:
        if n.startswith("PECA_STATE") and n.endswith(".json"):
            st = _ler_json(os.path.join(pasta, n))
            if st is not None:
                out.append(st)
    return out


def _fim(st):
    """(datetime do fim, situação). Situação: final, minuta_com_pendencias ou em_andamento."""
    recibos = [_dic(e) for e in _lista(st.get("entregas")) if not _dic(e).get("anexo")]
    liberadas = [_data_hora(e.get("data")) for e in recibos if not e.get("com_pendencias")]
    liberadas = [d for d in liberadas if d is not None]
    entrega = _dic(_dic(st.get("fases")).get("entrega"))
    if liberadas or (st.get("is_minuta") is False and entrega.get("status") == "concluida"):
        fim = min(liberadas) if liberadas else _data_hora(entrega.get("concluida_em"))
        return fim, "final"
    pend = [_data_hora(e.get("data")) for e in recibos if e.get("com_pendencias")]
    pend = [d for d in pend if d is not None]
    if pend:
        return min(pend), "minuta_com_pendencias"
    return None, "em_andamento"


def _pendencias_jur(st):
    topo = [p for p in _lista(st.get("pendencias_jurisprudencia")) if isinstance(p, str) and p.strip()]
    ver = _dic(_dic(_dic(st.get("fases")).get("verificacao")).get("evidencia"))
    fase = [p for p in _lista(ver.get("pendencias_jurisprudencia")) if isinstance(p, str) and p.strip()]
    return sorted(set(p.strip() for p in topo + fase))


def medir_peca(caminho, raiz):
    """Métrica de uma peça, ou None se o arquivo não for um PECA_STATE legível."""
    st = _ler_json(caminho)
    if st is None:
        return None
    pasta = os.path.dirname(caminho)
    marcas = _marcas(st)
    for v in _versoes(pasta):
        marcas.extend(_marcas(v))
    inicio = min(marcas) if marcas else None
    fim, situacao = _fim(st)
    horas, aviso = None, None
    if inicio is None:
        aviso = "sem_marca_de_inicio"
    elif fim is not None:
        if fim < inicio:
            aviso = "fim_antes_do_inicio"
        else:
            horas = round((fim - inicio).total_seconds() / 3600, 1)
    reab = [_dic(e) for e in _lista(st.get("reaberturas"))]
    por_fase = {}
    for e in reab:
        f = e.get("fase") if isinstance(e.get("fase"), str) else "?"
        por_fase[f] = por_fase.get(f, 0) + 1
    ciclo = st.get("ciclo") if isinstance(st.get("ciclo"), int) and not isinstance(st.get("ciclo"), bool) else 1
    return {
        "peca": st.get("peca") if isinstance(st.get("peca"), str) else "",
        "estado": os.path.relpath(caminho, raiz).replace(os.sep, "/"),
        "modo_execucao": st.get("modo_execucao") if isinstance(st.get("modo_execucao"), str) else None,
        "risco": st.get("risco") if isinstance(st.get("risco"), str) else None,
        "situacao": situacao,
        "is_minuta": st.get("is_minuta") is not False,
        "inicio": inicio.isoformat() if inicio else None,
        "fim": fim.isoformat() if fim else None,
        "semana": _semana(fim) if fim else None,
        "horas_ate_entrega": horas,
        "aviso_tempo": aviso,
        "ciclo": ciclo,
        "reaberturas": len(reab),
        "reaberturas_por_fase": por_fase,
        "recomecos": len(_lista(st.get("reinicios"))),
        "pendencias_jurisprudencia": len(_pendencias_jur(st)),
    }


def _arquivos(raiz, nome):
    for dirpath, dirnames, filenames in os.walk(raiz):
        dirnames[:] = sorted(d for d in dirnames if d not in PULAR)
        if nome in filenames:
            yield os.path.join(dirpath, nome)


def ler_erros(caminho, raiz):
    """Erros pós-protocolo de um METRICAS.jsonl. Linha ilegível é contada, não interrompe."""
    erros, ruins = [], 0
    try:
        with open(caminho, encoding="utf-8-sig") as fh:
            linhas = fh.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return [], 1
    for ln in linhas:
        if not ln.strip():
            continue
        try:
            e = json.loads(ln)
        except ValueError:
            ruins += 1
            continue
        if not isinstance(e, dict) or e.get("tipo") != TIPO_ERRO:
            continue
        d = _data_hora(e.get("data"))
        if d is None:
            ruins += 1
            continue
        erros.append({"data": d.date().isoformat(), "semana": _semana(d),
                      "peca": e.get("peca") if isinstance(e.get("peca"), str) else None,
                      "descricao": e.get("descricao") if isinstance(e.get("descricao"), str) else "",
                      "arquivo": os.path.relpath(caminho, raiz).replace(os.sep, "/")})
    return erros, ruins




def _taxa(erros, pecas):
    return round(erros / pecas, 2) if pecas else None


def agregar(pecas, erros):
    semanas = {}

    def sem(chave):
        return semanas.setdefault(chave, {"semana": chave, "pecas_entregues": 0, "finais": 0,
                                          "minutas_com_pendencias": 0, "_horas": [],
                                          "_reab": [], "pendencias_jurisprudencia": 0,
                                          "erros_pos_protocolo": 0})

    for p in pecas:
        if p["semana"] is None:
            continue
        s = sem(p["semana"])
        s["pecas_entregues"] += 1
        s["finais" if p["situacao"] == "final" else "minutas_com_pendencias"] += 1
        if p["horas_ate_entrega"] is not None:
            s["_horas"].append(p["horas_ate_entrega"])
        s["_reab"].append(p["reaberturas"] + p["recomecos"])
        s["pendencias_jurisprudencia"] += p["pendencias_jurisprudencia"]
    for e in erros:
        sem(e["semana"])["erros_pos_protocolo"] += 1
    lista = []
    for chave in sorted(semanas):
        s = semanas[chave]
        h, r = s.pop("_horas"), s.pop("_reab")
        s["horas_mediana"] = round(statistics.median(h), 1) if h else None
        s["correcoes_por_peca"] = round(sum(r) / len(r), 2) if r else None
        s["erros_por_peca"] = _taxa(s["erros_pos_protocolo"], s["pecas_entregues"])
        lista.append(s)
    return lista


def alerta(semanas):
    'O sinal de alerta: os erros que passaram subiram da penúltima para a última semana com'


    if len(semanas) < 2:
        return None
    ant, ult = semanas[-2], semanas[-1]
    if ult["erros_pos_protocolo"] == 0:
        return None
    if ant["pecas_entregues"] and ult["pecas_entregues"]:
        subiu = ult["erros_por_peca"] > ant["erros_por_peca"]
    else:
        subiu = ult["erros_pos_protocolo"] > ant["erros_pos_protocolo"]
    if not subiu:
        return None
    return (f"Os erros achados depois do protocolo subiram na semana {ult['semana']} "
            f"(eram {ant['erros_pos_protocolo']} em {ant['semana']}, agora "
            f"{ult['erros_pos_protocolo']}). Reduza o ritmo e reforce a conferência antes do "
            f"protocolo.")


def relatorio(raiz):
    raiz = os.path.abspath(raiz)
    pecas, ilegiveis = [], []
    for c in _arquivos(raiz, NOME_ESTADO):
        m = medir_peca(c, raiz)
        if m is None:
            ilegiveis.append(os.path.relpath(c, raiz).replace(os.sep, "/"))
        else:
            pecas.append(m)
    erros, ruins = [], 0
    for c in _arquivos(raiz, NOME_METRICAS):
        e, r = ler_erros(c, raiz)
        erros.extend(e)
        ruins += r
    semanas = agregar(pecas, erros)
    entregues = [p for p in pecas if p["situacao"] != "em_andamento"]
    horas = [p["horas_ate_entrega"] for p in entregues if p["horas_ate_entrega"] is not None]
    modos = {}
    for p in pecas:
        k = p["modo_execucao"] or "?"
        modos[k] = modos.get(k, 0) + 1
    total = {
        "pecas": len(pecas),
        "entregues": len(entregues),
        "finais": sum(1 for p in pecas if p["situacao"] == "final"),
        "minutas_com_pendencias": sum(1 for p in pecas if p["situacao"] == "minuta_com_pendencias"),
        "em_andamento": sum(1 for p in pecas if p["situacao"] == "em_andamento"),
        "horas_mediana": round(statistics.median(horas), 1) if horas else None,
        "correcoes_por_peca": (round(sum(p["reaberturas"] + p["recomecos"] for p in entregues)
                                     / len(entregues), 2) if entregues else None),
        "pendencias_jurisprudencia_abertas": sum(p["pendencias_jurisprudencia"] for p in pecas),
        "erros_pos_protocolo": len(erros),
        "erros_por_peca": _taxa(len(erros), len(entregues)),
        "por_modo": dict(sorted(modos.items())),
    }
    return {"ok": True, "pasta": raiz, "total": total, "semanas": semanas,
            "alerta": alerta(semanas), "pecas": pecas, "erros": erros,
            "estados_ilegiveis": ilegiveis, "linhas_de_metricas_ilegiveis": ruins}


def _fmt(v, suf=""):
    return "—" if v is None else f"{v}{suf}"


def texto(rel, detalhe=False):
    t = rel["total"]
    linhas = [f"Peças: {t['pecas']} ({t['finais']} finais, {t['minutas_com_pendencias']} minutas "
              f"com pendências, {t['em_andamento']} em andamento).",
              f"Tempo até a entrega (mediana): {_fmt(t['horas_mediana'], ' h')}. "
              f"Correções por peça: {_fmt(t['correcoes_por_peca'])}. "
              f"Erros depois do protocolo: {t['erros_pos_protocolo']} "
              f"({_fmt(t['erros_por_peca'])} por peça entregue).",
              f"Pendências de jurisprudência abertas: {t['pendencias_jurisprudencia_abertas']}. "
              "Modo: " + ", ".join(f"{k} {v}" for k, v in t["por_modo"].items()) + "."]
    if rel["semanas"]:
        linhas.append("Por semana (peças · mediana h · correções/peça · erros):")
        for s in rel["semanas"]:
            linhas.append(f"  {s['semana']}: {s['pecas_entregues']} · {_fmt(s['horas_mediana'])} · "
                          f"{_fmt(s['correcoes_por_peca'])} · {s['erros_pos_protocolo']}")
    if detalhe:
        for p in rel["pecas"]:
            linhas.append(f"  - {p['peca'] or p['estado']}: {p['situacao']}, "
                          f"{_fmt(p['horas_ate_entrega'], ' h')}, ciclo {p['ciclo']}, "
                          f"{p['reaberturas']} reabertura(s), {p['recomecos']} recomeço(s), "
                          f"{p['pendencias_jurisprudencia']} pendência(s) de jurisprudência")
    if rel["estados_ilegiveis"] or rel["linhas_de_metricas_ilegiveis"]:
        linhas.append(f"Ignorados: {len(rel['estados_ilegiveis'])} estado(s) ilegível(is), "
                      f"{rel['linhas_de_metricas_ilegiveis']} linha(s) de erro ilegível(is).")
    if rel["alerta"]:
        linhas.append("ALERTA: " + rel["alerta"])
    return "\n".join(linhas)




def registrar_erro(caso, descricao, peca=None, data=None, hoje=None):
    """Grava um erro pós-protocolo em <caso>/METRICAS.jsonl. Devolve (resultado, código)."""
    if not os.path.isdir(caso):
        return {"ok": False, "motivo": "caso_inexistente",
                "mensagem": f"A pasta do caso não existe: {caso}"}, 1
    if not isinstance(descricao, str) or not descricao.strip():
        return {"ok": False, "motivo": "descricao_vazia",
                "mensagem": "Descreva o erro achado depois do protocolo (--descricao)."}, 1
    if data:
        try:
            dia = datetime.date.fromisoformat(data.strip())
        except ValueError:
            return {"ok": False, "motivo": "data_invalida",
                    "mensagem": "Data no formato AAAA-MM-DD (--data)."}, 1
    else:
        dia = hoje or datetime.date.today()
    if not (isinstance(peca, str) and peca.strip()):
        nomes = []
        for c in _arquivos(caso, NOME_ESTADO):
            st = _ler_json(c)
            if st is not None and isinstance(st.get("peca"), str) and st["peca"].strip():
                nomes.append(st["peca"].strip())
        nomes = sorted(set(nomes))
        if len(nomes) != 1:
            return {"ok": False, "motivo": "peca_ambigua" if nomes else "peca_nao_encontrada",
                    "mensagem": ("Diga a qual peça o erro pertence (--peca)."
                                 + (" Peças do caso: " + "; ".join(nomes) if nomes else
                                    " Nenhuma peça registrada nesta pasta."))}, 1
        peca = nomes[0]
    linha = {"tipo": TIPO_ERRO, "data": dia.isoformat(), "descricao": descricao.strip(),
             "peca": peca.strip()}
    destino = os.path.join(caso, NOME_METRICAS)
    with open(destino, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return {"ok": True, "resultado": "erro_registrado", "arquivo": destino, **linha}, 0




def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Métricas do uso: tempo, correções e erros por peça.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("relatorio", help="mede as peças de uma pasta de casos")
    pr.add_argument("--pasta", required=True)
    pr.add_argument("--json", action="store_true")
    pr.add_argument("--detalhe", action="store_true", help="lista peça a peça no texto")
    pe = sub.add_parser("registrar-erro", help="registra erro achado depois do protocolo")
    pe.add_argument("--caso", required=True)
    pe.add_argument("--descricao", required=True)
    pe.add_argument("--peca")
    pe.add_argument("--data", help="AAAA-MM-DD; padrão, hoje")
    pe.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "relatorio":
        if not os.path.isdir(args.pasta):
            msg = {"ok": False, "motivo": "pasta_inexistente",
                   "mensagem": f"A pasta não existe: {args.pasta}"}
            print(json.dumps(msg, ensure_ascii=False) if args.json else msg["mensagem"])
            return 1
        rel = relatorio(args.pasta)
        print(json.dumps(rel, ensure_ascii=False, indent=1) if args.json else texto(rel, args.detalhe))
        return 0
    res, cod = registrar_erro(args.caso, args.descricao, args.peca, args.data)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    elif res["ok"]:
        print(f"Erro registrado em {res['arquivo']} ({res['data']}, peça: {res['peca']}).")
    else:
        print(res["mensagem"])
    return cod


if __name__ == "__main__":
    sys.exit(main())
