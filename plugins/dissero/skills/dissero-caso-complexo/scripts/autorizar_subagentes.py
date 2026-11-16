#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'autorizar_subagentes.py — REGISTRA o aval do advogado para disparar subagentes (§13).'










































import sys, os, json, time, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import caso_raiz
except Exception:
    caso_raiz = None

NOME = "AUTORIZACAO_SUBAGENTES.json"
LEDGER = "PROVENIENCIA.jsonl"


PADRAO_SIMULTANEOS = 2
PADRAO_ONDAS = 1


DEFAULT_SIMULTANEOS = 5
DEFAULT_ONDAS = 1


def _s(x):
    return isinstance(x, str) and bool(x.strip())


def _saida(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False))
    return code


def destino(raiz=None, session_id=None):
    if _s(raiz):
        return os.path.join(os.path.abspath(raiz.strip()), NOME)
    if caso_raiz is not None:
        try:
            return caso_raiz.arquivo(NOME, session_id=session_id)
        except Exception:
            pass
    return os.path.join(os.getcwd(), NOME)


class AvalInvalido(ValueError):
    """Recusa do registro com código nomeado (`codigo`); `str()` é o texto para o modelo."""

    def __init__(self, codigo, detalhe):
        super().__init__(detalhe)
        self.codigo = codigo


def montar(session_id, max_simultaneos, ondas, escopo, ts=None):
    if not _s(session_id):
        raise AvalInvalido("session_id_obrigatorio",
                           "--session-id obrigatório: o aval é POR SESSÃO (id do harness, não inventado)")
    if not _s(escopo):
        raise AvalInvalido("escopo_obrigatorio",
                           "--escopo obrigatório: registre PARA QUE o advogado autorizou (ex.: "
                           "'Conselho Revisor — inicial de cobrança')")
    for rotulo, v in (("--max-simultaneos", max_simultaneos), ("--ondas", ondas)):
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise AvalInvalido("teto_invalido", f"{rotulo} deve ser inteiro ≥ 1")
    return {
        "session_id": session_id.strip(),
        "max_simultaneos": max_simultaneos,
        "ondas": ondas,
        "escopo": escopo.strip(),
        "concedido_em": ts.strip() if _s(ts) else time.strftime("%Y-%m-%dT%H:%M:%S"),
    }






def _inteiro(v, padrao):
    """Gêmeo do `_inteiro` do gate: inteiro > 0, nunca bool, string ou float."""
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else padrao


def soma_acrescimos(d):
    """Gêmeo do `soma_acrescimos` do gate: só item objeto com `agentes` inteiro > 0 soma."""
    lista = d.get("acrescimos") if isinstance(d, dict) else None
    if not isinstance(lista, list):
        return 0
    return sum(a["agentes"] for a in lista
               if isinstance(a, dict) and _inteiro(a.get("agentes"), 0) > 0)


def teto_do_aval(d):
    """Teto que o GATE concede para um aval já validado para a sessão."""
    s = _inteiro(d.get("max_simultaneos"), PADRAO_SIMULTANEOS)
    o = _inteiro(d.get("ondas"), PADRAO_ONDAS)
    return s * o + soma_acrescimos(d)


def caminho_ledger(alvo):
    'Ledger que o gate lê: `DSR_PROV_LEDGER`, senão o `PROVENIENCIA.jsonl` ao lado do aval'

    env = os.environ.get("DSR_PROV_LEDGER")
    if _s(env):
        return env
    return os.path.join(os.path.dirname(alvo) or ".", LEDGER)


def contar_disparos(ledger_path, session_id):
    'Disparos já registrados na sessão — mesma contagem do gate: cumulativa, só'

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




def _ler(alvo):
    """(aval, erro): o objeto JSON do arquivo, ou None com o motivo."""
    if not os.path.isfile(alvo):
        return None, "sem autorização registrada"
    try:
        with open(alvo, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception as e:
        return None, f"autorização ilegível: {e}"
    if not isinstance(d, dict):
        return None, "autorização ilegível: o arquivo não é um objeto JSON"
    return d, ""


def _gravar(alvo, reg):
    'Gravação atômica: temporário na mesma pasta + `os.replace`. Um aval meio escrito seria'

    pasta = os.path.dirname(alvo) or "."
    os.makedirs(pasta, exist_ok=True)
    tmp = os.path.join(pasta, f".{NOME}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(reg, ensure_ascii=False, indent=2))
        os.replace(tmp, alvo)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _comando_registro(session_id):
    return (f"python scripts/autorizar_subagentes.py --session-id {session_id} "
            f"--max-simultaneos N --ondas N --escopo \"<palavras do advogado>\"")


def somar(alvo, session_id, agentes, escopo, ts=None):
    """Anexa um acréscimo ao aval VIGENTE desta sessão. Devolve (payload, exit)."""
    if not isinstance(agentes, int) or isinstance(agentes, bool) or agentes < 1:
        return {"ok": False, "erro": "somar_invalido",
                "detalhe": "--somar deve ser inteiro ≥ 1 (os agentes do novo ciclo)"}, 2
    if not _s(escopo):
        return {"ok": False, "erro": "escopo_obrigatorio",
                "detalhe": "--escopo obrigatório: registre, com as palavras do advogado, o que "
                           "ele autorizou neste acréscimo"}, 2
    d, erro = _ler(alvo)
    vale = d is not None and _s(d.get("session_id")) and d["session_id"].strip() == session_id.strip()
    if not vale:
        if erro:
            motivo = erro
        elif _s(d.get("session_id")):
            motivo = f"o aval registrado é da sessão {d['session_id'].strip()}"
        else:
            motivo = "o aval registrado não traz session_id"
        return {"ok": False, "erro": "sem_aval_vigente", "caminho": alvo,
                "detalhe": f"--somar só acresce a um aval VIGENTE desta sessão ({motivo}). Com o "
                           "aval expresso do advogado, registre o aval pelo comando normal",
                "comando": _comando_registro(session_id.strip())}, 2
    ja = contar_disparos(caminho_ledger(alvo), session_id)
    anterior = teto_do_aval(d)
    acrescimo = {"agentes": agentes, "escopo": escopo.strip(),
                 "concedido_em": ts.strip() if _s(ts) else time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "ja_disparados_no_ato": ja}
    reg = dict(d)
    lista = d.get("acrescimos") if isinstance(d.get("acrescimos"), list) else []
    reg["acrescimos"] = list(lista) + [acrescimo]
    try:
        _gravar(alvo, reg)
    except OSError as e:
        return {"ok": False, "caminho": alvo, "erro": "falha_gravacao",
                "detalhe": f"falha ao gravar: {e}"}, 1
    novo = teto_do_aval(reg)
    return {"ok": True, "caminho": alvo, "ledger": caminho_ledger(alvo), "acrescimo": acrescimo,
            "teto_anterior": anterior, "teto_autorizado": novo,
            "ja_disparados": ja, "restante": max(0, novo - ja),
            "nota": "acréscimo REGISTRADO — só vale depois do 'pode' expresso do advogado; vale "
                    "só para esta sessão, e o aval original ficou preservado"}, 0


def mostrar(alvo, session_id):
    """Aval vigente, com o gasto da sessão contado como o gate conta. Devolve (payload, exit)."""
    padrao = PADRAO_SIMULTANEOS * PADRAO_ONDAS
    ledger = caminho_ledger(alvo)
    ja = contar_disparos(ledger, session_id)
    if not os.path.isfile(alvo):
        return {"ok": True, "existe": False, "caminho": alvo, "ledger": ledger, "teto_vigente": padrao,
                "ja_disparados": ja, "restante": max(0, padrao - ja),
                "nota": "sem autorização registrada — vale o padrão §13 (2 agentes, 1 onda)"}, 0
    d, erro = _ler(alvo)
    if d is None:
        return {"ok": False, "caminho": alvo, "erro": erro}, 1
    vale = _s(d.get("session_id")) and d["session_id"].strip() == session_id.strip()
    teto = teto_do_aval(d) if vale else padrao
    return {"ok": True, "existe": True, "caminho": alvo, "ledger": ledger, "autorizacao": d,
            "vale_para_esta_sessao": bool(vale), "teto_vigente": teto,
            "acrescimos": d.get("acrescimos") if isinstance(d.get("acrescimos"), list) else [],
            "ja_disparados": ja, "restante": max(0, teto - ja),
            "nota": ("contagem cumulativa na sessão: um novo ciclo, com aval expresso, entra por "
                     "--somar K" if vale else
                     "autorização de OUTRA sessão: o gate a ignora (vale o padrão §13)")}, 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Registra o aval de disparo de subagentes (Dissero §13)")
    ap.add_argument("--session-id", dest="session_id", required=True)


    ap.add_argument("--max-simultaneos", dest="max_simultaneos", type=int, default=None)
    ap.add_argument("--ondas", type=int, default=None)
    ap.add_argument("--somar", type=int, default=None,
                    help="acresce K agentes ao aval VIGENTE desta sessão (novo ciclo), "
                         "preservando o original")
    ap.add_argument("--escopo")
    ap.add_argument("--raiz")
    ap.add_argument("--ts")
    ap.add_argument("--mostrar", action="store_true",
                    help="não grava: mostra a autorização vigente, o já disparado e o restante")
    args = ap.parse_args(argv)

    alvo = destino(args.raiz, args.session_id)

    if args.mostrar:
        payload, code = mostrar(alvo, args.session_id)
        return _saida(payload, code)

    if args.somar is not None:
        if args.max_simultaneos is not None or args.ondas is not None:
            return _saida({"ok": False, "erro": "somar_com_teto_explicito",
                           "detalhe": "--somar acresce ao aval vigente e não convive com "
                                      "--max-simultaneos/--ondas: use um OU outro"}, 2)
        payload, code = somar(alvo, args.session_id, args.somar, args.escopo, args.ts)
        return _saida(payload, code)

    simult = DEFAULT_SIMULTANEOS if args.max_simultaneos is None else args.max_simultaneos
    ondas = DEFAULT_ONDAS if args.ondas is None else args.ondas
    try:
        reg = montar(args.session_id, simult, ondas, args.escopo, args.ts)
    except AvalInvalido as e:
        return _saida({"ok": False, "erro": e.codigo, "detalhe": str(e)}, 2)

    aviso = _aviso_descarte(alvo, reg)
    try:
        _gravar(alvo, reg)
    except OSError as e:
        return _saida({"ok": False, "caminho": alvo, "erro": "falha_gravacao",
                       "detalhe": f"falha ao gravar: {e}"}, 1)

    saida = {"ok": True, "caminho": alvo, "autorizacao": reg,
             "teto_autorizado": reg["max_simultaneos"] * reg["ondas"],
             "nota": "aval REGISTRADO — vale só para esta sessão; um novo ciclo, com novo "
                     "aval expresso, entra por --somar K"}
    if aviso:
        saida["aviso"] = aviso
    return _saida(saida)


def _aviso_descarte(alvo, reg):
    'Regravar o aval da MESMA sessão substitui o arquivo e leva os acréscimos junto. Não se'


    d, _ = _ler(alvo)
    if d is None or not soma_acrescimos(d):
        return None
    if not (_s(d.get("session_id")) and d["session_id"].strip() == reg["session_id"]):
        return None
    anterior, novo = teto_do_aval(d), teto_do_aval(reg)
    ja = contar_disparos(caminho_ledger(alvo), reg["session_id"])
    detalhe = (f"o aval anterior desta sessão tinha acréscimos (teto {anterior}) e foi "
               f"substituído: o teto agora é {novo}")
    if ja >= novo:
        detalhe += (f", abaixo do já disparado ({ja}) — o próximo disparo será bloqueado. Para "
                    f"um novo ciclo, com aval expresso do advogado, use --somar K")
    else:
        detalhe += f"; já disparados: {ja}. Para um novo ciclo, prefira --somar K"
    return {"codigo": "acrescimos_descartados", "teto_anterior": anterior, "teto_novo": novo,
            "ja_disparados": ja, "detalhe": detalhe}


if __name__ == "__main__":
    sys.exit(main())
