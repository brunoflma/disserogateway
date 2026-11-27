#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'aval_subagentes.py — ÚNICO leitor do aval de subagentes (§13) do lado das skills.'

































































import json
import os





try:
    import caso_raiz
except Exception:
    caso_raiz = None

NOME_AVAL = "AUTORIZACAO_SUBAGENTES.json"
NOME_LEDGER = "PROVENIENCIA.jsonl"




ENV_AVAL = "DSR_AUTORIZACAO"
ENV_LEDGER = "DSR_PROV_LEDGER"


PADRAO_SIMULTANEOS = 2
PADRAO_ONDAS = 1




USO_LEITURA = "leitura_em_blocos"
NOME_CONSUMO_LEITURA = "LEITURA_EM_BLOCOS.jsonl"


def leitura_por_documento(d):
    """{documento: agentes} dos acréscimos de leitura válidos — gêmeo do gate."""
    out = {}
    lista = d.get("acrescimos") if isinstance(d, dict) else None
    if isinstance(lista, list):
        for a in lista:
            if (isinstance(a, dict) and a.get("uso") == USO_LEITURA and _s(a.get("documento"))
                    and _int(a.get("agentes"))):
                doc = a["documento"].strip()
                out[doc] = out.get(doc, 0) + a["agentes"]
    return out


def soma_leitura_bruta(d):
    """Todo acréscimo marcado como leitura, válido ou não: nenhum é orçamento comum (gêmeo do gate)."""
    lista = d.get("acrescimos") if isinstance(d, dict) else None
    if not isinstance(lista, list):
        return 0
    return sum(a["agentes"] for a in lista if isinstance(a, dict) and _int(a.get("agentes")) and a.get("uso") == USO_LEITURA)


def ler_consumo_leitura(session_id, raiz=None):
    """{documento: leitores já liberados pelo gate} desta sessão — gêmeo do `ler_consumo`."""
    alvo, _ = _caminho(NOME_CONSUMO_LEITURA, session_id, raiz)
    out = {}
    try:
        with open(alvo, encoding="utf-8", errors="replace") as fh:
            for linha in fh:
                try:
                    d = json.loads(linha)
                except Exception:
                    continue
                if not isinstance(d, dict) or not _s(d.get("documento")):
                    continue
                if _s(session_id) and _s(d.get("session_id")) and d["session_id"].strip() != session_id.strip():
                    continue
                out[d["documento"].strip()] = out.get(d["documento"].strip(), 0) + 1
    except Exception:
        return {}
    return out


def _s(x):
    return isinstance(x, str) and bool(x.strip())


def _int(x):
    'Metade do aval em número USÁVEL, ou None (o chamador cai no padrão).'







    return x if (isinstance(x, int) and not isinstance(x, bool) and x > 0) else None


def soma_acrescimos(d):
    '(soma dos acréscimos válidos, itens recusados) — gêmeo do `soma_acrescimos` do gate.'





    if not isinstance(d, dict) or "acrescimos" not in d:
        return 0, []
    lista = d.get("acrescimos")
    if not isinstance(lista, list):
        return 0, [lista]
    soma, tortos = 0, []
    for a in lista:
        n = _int(a.get("agentes")) if isinstance(a, dict) else None
        if n is None:
            tortos.append(a)
        else:
            soma += n
    return soma, tortos


def contar_disparos(ledger_path, session_id):
    'Disparos de subagente JÁ registrados para a sessão, no `PROVENIENCIA.jsonl`.'








    if not _s(ledger_path) or not os.path.exists(ledger_path):
        return 0
    n = 0
    try:
        with open(ledger_path, encoding="utf-8", errors="replace") as fh:
            for linha in fh:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    d = json.loads(linha)
                except Exception:
                    continue
                if not isinstance(d, dict) or d.get("evento") != "SubagentStart":
                    continue



                if _s(session_id) and _s(d.get("session_id")):
                    if d.get("session_id").strip() != session_id.strip():
                        continue
                n += 1
    except Exception:
        return 0
    return n


def _caminho(nome, session_id, raiz, env=""):
    'Onde o arquivo de controle está — na MESMA ordem do gate.'





    if _s(env) and _s(os.environ.get(env)):
        return os.environ[env], "env"
    if _s(raiz):
        return os.path.join(os.path.abspath(raiz.strip()), nome), "raiz"
    if caso_raiz is not None:
        try:
            _, origem = caso_raiz.resolver(session_id=session_id)
            return caso_raiz.arquivo(nome, session_id=session_id), origem
        except Exception:
            pass
    return os.path.join(os.getcwd(), nome), "cwd"















AVISO_CWD = ("o aval foi resolvido pelo `cwd` DESTE processo: sem ponteiro de caso registrado, "
             "o gate pode ler OUTRO arquivo e conceder um teto diferente. O plano não obriga o "
             "gate. Registre o caso com `caso_raiz.py registrar --raiz <pasta> --session-id <id>` "
             "antes de confiar neste número")


def _vale_para_a_sessao(d, session_id):
    'Espelho literal do `ler_autorizacao` do gate, ramo a ramo.'





    if not isinstance(d, dict):
        return False
    if _s(session_id) and _s(d.get("session_id")):
        return d["session_id"].strip() == session_id.strip()
    if not _s(d.get("session_id")):
        return False
    return True


def _com_o_gasto(teto, det, session_id, raiz):
    'Fecha o detalhe com o orçamento JÁ CONSUMIDO na sessão.'




    ledger, origem_ledger = _caminho(NOME_LEDGER, session_id, raiz, env=ENV_LEDGER)
    consumo = ler_consumo_leitura(session_id, raiz)
    ja = max(0, contar_disparos(ledger, session_id) - sum(consumo.values()))
    if consumo:
        det["leitura_consumida"] = consumo
    det["ledger"] = ledger
    det["origem_ledger"] = origem_ledger
    det["ja_disparados"] = ja
    det["restante"] = max(0, teto - ja)
    return teto, det


def ler_aval(session_id, raiz=None):
    """Aval de subagentes vigente (§13). Devolve (teto_autorizado, detalhe)."""
    alvo, origem = _caminho(NOME_AVAL, session_id, raiz, env=ENV_AVAL)

    padrao = PADRAO_SIMULTANEOS * PADRAO_ONDAS
    det = {"caminho": alvo, "origem": origem, "existe": False,
           "vale_para_esta_sessao": False, "teto_padrao_sem_aval": padrao}

    if origem == "cwd":
        det["aviso_paridade"] = AVISO_CWD
    if not os.path.isfile(alvo):
        return _com_o_gasto(padrao, det, session_id, raiz)
    try:
        with open(alvo, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception as e:


        det["erro"] = f"aval ilegível: {e}"
        return _com_o_gasto(padrao, det, session_id, raiz)
    if not isinstance(d, dict):


        det["erro"] = "aval ilegível: o arquivo não é um objeto JSON (veio %s)" % type(d).__name__
        return _com_o_gasto(padrao, det, session_id, raiz)
    det["existe"] = True
    vale = _vale_para_a_sessao(d, session_id)
    det["vale_para_esta_sessao"] = bool(vale)
    if not vale:
        det["nota"] = ("aval de OUTRA sessão (ou aval sem `session_id`, que não é rastreável): "
                       "o gate o ignora")
        return _com_o_gasto(padrao, det, session_id, raiz)
    simult = _int(d.get("max_simultaneos")) or PADRAO_SIMULTANEOS
    ondas = _int(d.get("ondas")) or PADRAO_ONDAS
    det.update({"max_simultaneos": simult, "ondas": ondas, "escopo": d.get("escopo", ""),
                "concedido_em": d.get("concedido_em", "")})



    tortos = [(c, d[c]) for c in ("max_simultaneos", "ondas")
              if c in d and _int(d[c]) is None]
    extra, acr_tortos = soma_acrescimos(d)
    det["acrescimo_total"] = extra - soma_leitura_bruta(d)
    notas = ["%s %r ignorado: o gate só aceita inteiro > 0" % (c, v) for c, v in tortos]
    if acr_tortos:
        notas.append("acrescimos %r ignorado(s): o gate só soma item com `agentes` inteiro > 0"
                     % (acr_tortos,))
    if notas:
        det["nota_tipo"] = ("; ".join(notas)
                            + " — regrave o aval com `autorizar_subagentes.py`")


    leitura = leitura_por_documento(d)
    if leitura:
        det["leitura_por_documento"] = leitura
    return _com_o_gasto(simult * ondas + extra - soma_leitura_bruta(d), det, session_id, raiz)
