#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'caso_raiz.py — resolve a RAIZ DO CASO de forma independente do `cwd` da sessão.'

























































import sys, os, re, json, time, tempfile, secrets

ENV_RAIZ = "DSR_CASO_RAIZ"
ENV_BASE = "DSR_CASO_BASE"
PONTEIRO_ATUAL = "caso_atual.json"
DIR_SESSOES = "sessoes"
ARQUIVO_CASO_ID = "CASO_ID.json"
DIR_CASOS = "casos"
_RE_CASO_ID = re.compile(r"^caso-[0-9a-f]{12}$")
_CHAVES_CASO_ID = {"caso_id", "criado_em"}


class CasoIdInvalido(ValueError):
    """`CASO_ID.json` existe mas não traz um código no formato opaco. Código: caso_id_invalido."""
    codigo = "caso_id_invalido"


class RegistroNaoGravado(OSError):
    'O registro não conseguiu gravar. `codigo` ∈ {pasta_nao_gravavel, ponteiro_nao_gravado};'


    def __init__(self, codigo, causa):
        self.codigo = codigo
        self.detalhe = (getattr(causa, "strerror", None) or type(causa).__name__)
        super().__init__(f"{codigo}: {self.detalhe}")





_SEGMENTOS_EFEMEROS = {"tmp", "temp", "scratchpad", "cache", "caches"}





















































ENV_AMBIENTE = "DSR_AMBIENTE"
MARCADOR_AMBIENTE = "ambiente.json"
_VERDADEIRO = ("1", "true", "yes", "on", "sim")
_SINAIS_EFEMEROS = (
    ("CLAUDE_CODE_ENTRYPOINT", lambda v: v.lower().startswith("remote")),
    ("CLAUDE_CODE_REMOTE", lambda v: v.lower() in _VERDADEIRO),
    ("CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE", lambda v: bool(v)),
)
_MONTAGENS_EFEMERAS = ("/mnt/user-data", "/mnt/skills")


def _s(x):
    return isinstance(x, str) and bool(x.strip())


def superficie_remota(env=None):
    'A sessão roda numa VM da plataforma (Cowork remoto do claude.ai, Claude Code na nuvem)?'




    env = os.environ if env is None else env
    try:
        remoto = str(env.get("CLAUDE_CODE_REMOTE") or "").strip().lower() in ("true", "1")
        entrada = str(env.get("CLAUDE_CODE_ENTRYPOINT") or "").strip().lower()
    except Exception:
        return False
    return remoto or entrada.startswith("remote")


def base_dir():
    """Pasta dos ponteiros. Fora do plugin (que é reinstalado) e fora do caso."""
    b = os.environ.get(ENV_BASE)
    if _s(b):
        return os.path.abspath(b.strip())
    return os.path.join(os.path.expanduser("~"), ".dissero")


def caminho_marcador_ambiente():
    return os.path.join(base_dir(), MARCADOR_AMBIENTE)


def ambiente(cwd=None):
    "{'efemero': bool, 'origem': str, 'motivo': str, 'sinais': [str]} — nunca levanta."





    d = (os.environ.get(ENV_AMBIENTE) or "").strip().lower()
    if d in ("efemero", "efêmero", "ephemeral"):
        return {"efemero": True, "origem": "declaracao", "sinais": [f"{ENV_AMBIENTE}={d}"],
                "motivo": "ambiente declarado EFÊMERO pelo advogado"}
    if d in ("duravel", "durável", "durable", "local"):
        return {"efemero": False, "origem": "declaracao", "sinais": [f"{ENV_AMBIENTE}={d}"],
                "motivo": "ambiente declarado DURÁVEL pelo advogado"}

    try:
        m = json.loads(open(caminho_marcador_ambiente(), encoding="utf-8").read())
        if isinstance(m, dict) and isinstance(m.get("efemero"), bool):
            return {"efemero": m["efemero"], "origem": "marcador",
                    "sinais": [caminho_marcador_ambiente()],
                    "motivo": m.get("motivo") or ("marcador diz EFÊMERO" if m["efemero"]
                                                  else "marcador diz DURÁVEL")}
    except Exception:
        pass

    sinais = []
    for nome, testa in _SINAIS_EFEMEROS:
        valor = (os.environ.get(nome) or "").strip()
        try:
            if valor and testa(valor):
                sinais.append(f"{nome}={valor}")
        except Exception:
            continue
    for m in _MONTAGENS_EFEMERAS:
        try:
            if os.path.isdir(m):
                sinais.append(f"montagem {m}")
        except Exception:
            continue
    if sinais:
        return {"efemero": True, "origem": "heuristica", "sinais": sinais,
                "motivo": "ambiente REMOTO/de sandbox (sessão não persiste; declare com "
                          f"{ENV_AMBIENTE}=duravel se este ambiente for persistente)"}
    return {"efemero": False, "origem": "padrao", "sinais": [],
            "motivo": "nenhum sinal de ambiente efêmero — tratado como durável"}


def e_ambiente_efemero(cwd=None):
    return bool(ambiente(cwd=cwd).get("efemero"))


def marcar_ambiente(efemero, motivo=""):
    """Grava `<base>/ambiente.json`. Quem sabe que está num sandbox registra para o gate saber."""
    if not isinstance(efemero, bool):
        raise ValueError("efemero deve ser booleano")
    alvo = caminho_marcador_ambiente()
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    d = {"efemero": efemero, "motivo": (motivo or "").strip(),
         "registrado_em": time.strftime("%Y-%m-%dT%H:%M:%S")}
    open(alvo, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))
    return alvo


def _slug(session_id):
    """Nome de arquivo seguro para o id da sessão (ids do harness são UUID, mas não confie)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", (session_id or "").strip())[:120] or "sem-sessao"


def caminho_ponteiro_sessao(session_id):
    return os.path.join(base_dir(), DIR_SESSOES, _slug(session_id) + ".json")


def caminho_ponteiro_atual():
    return os.path.join(base_dir(), PONTEIRO_ATUAL)


def _ler_ponteiro(path):
    """dict do ponteiro, ou None. Ausente/ilegível/malformado → None (fail-open)."""
    try:
        if not os.path.isfile(path):
            return None
        d = json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return None
    if not isinstance(d, dict) or not _s(d.get("raiz")):
        return None
    return d


def _raiz_util(d):
    """Raiz do ponteiro, se a pasta ainda existir. Pasta apagada → None (o ponteiro venceu)."""
    if not d:
        return None
    raiz = d["raiz"].strip()
    return raiz if os.path.isdir(raiz) else None


def resolver(cwd=None, session_id=None):
    """(raiz, origem) — origem ∈ {'env', 'sessao', 'atual', 'cwd'}. Nunca levanta."""
    env = os.environ.get(ENV_RAIZ)
    if _s(env):
        return os.path.abspath(env.strip()), "env"

    if _s(session_id):
        r = _raiz_util(_ler_ponteiro(caminho_ponteiro_sessao(session_id)))
        if r:
            return r, "sessao"

    d = _ler_ponteiro(caminho_ponteiro_atual())
    if d:
        dono = d.get("session_id")


        if not (_s(dono) and _s(session_id) and dono.strip() != session_id.strip()):
            r = _raiz_util(d)
            if r:
                return r, "atual"

    return (cwd.strip() if _s(cwd) else os.getcwd()), "cwd"


def e_caso_id(valor):
    """True quando o valor tem o formato do código opaco (`caso-` + 12 hexadecimais)."""
    return isinstance(valor, str) and bool(_RE_CASO_ID.match(valor))


def ler_caso_id(raiz):
    'Código do caso gravado em `<raiz>/CASO_ID.json`, ou None se o arquivo não existe.'


    p = os.path.join(raiz, ARQUIVO_CASO_ID)
    if not os.path.isfile(p):
        return None
    try:
        d = json.loads(open(p, encoding="utf-8").read())
    except Exception:
        raise CasoIdInvalido(f"caso_id_invalido: {ARQUIVO_CASO_ID} ilegível")
    cid = d.get("caso_id") if isinstance(d, dict) else None
    if not e_caso_id(cid):
        raise CasoIdInvalido(f"caso_id_invalido: {ARQUIVO_CASO_ID} sem código no formato caso-<12 hex>")

    if not set(d) <= _CHAVES_CASO_ID:
        raise CasoIdInvalido(f"caso_id_invalido: {ARQUIVO_CASO_ID} com campo além de caso_id e criado_em")
    return cid


def _caminho_dono(caso_id):
    return os.path.join(base_dir(), DIR_CASOS, caso_id + ".json")


def caso_conhecido(caso_id):
    'True quando o código tem o formato e há registro dele nesta máquina'

    try:
        return e_caso_id(caso_id) and os.path.isfile(_caminho_dono(caso_id))
    except (OSError, ValueError):
        return False


def _dono_vivo(caso_id, raiz):
    'Outra pasta VIVA que já é dona deste código (cópia), ou None. Pasta dona apagada ou'

    d = _ler_ponteiro(_caminho_dono(caso_id))
    outra = _raiz_util(d)
    if not outra:
        return None
    try:
        if os.path.samefile(outra, raiz):
            return None
        return outra if ler_caso_id(outra) == caso_id else None
    except (OSError, CasoIdInvalido):
        return None


def _gravar_caso_id(raiz, cid, ts=None):
    """Regrava o `CASO_ID.json` (troca atômica), para a cópia ganhar código próprio."""
    p = os.path.join(raiz, ARQUIVO_CASO_ID)
    d = {"caso_id": cid, "criado_em": ts if _s(ts) else time.strftime("%Y-%m-%dT%H:%M:%S")}
    tmp = p + ".novo"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(d, ensure_ascii=False, indent=2))
    os.replace(tmp, p)


def garantir_caso_id(raiz, ts=None):
    'Lê o código do caso; se não houver, cria um aleatório e grava. Estável: quem chega'


    cid = ler_caso_id(raiz)
    if cid:
        return cid
    novo = "caso-" + secrets.token_hex(6)
    d = {"caso_id": novo, "criado_em": ts if _s(ts) else time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        with open(os.path.join(raiz, ARQUIVO_CASO_ID), "x", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False, indent=2))
    except FileExistsError:
        return ler_caso_id(raiz)
    return novo


def caso_id_vigente(cwd=None, session_id=None, criar=False):
    '(caso_id, origem, erro) do caso resolvido. Nunca levanta. Sem caso registrado (origem'


    raiz, origem = resolver(cwd=cwd, session_id=session_id)
    if origem == "cwd":
        return None, origem, "caso_nao_registrado"
    try:
        cid = garantir_caso_id(raiz) if criar else ler_caso_id(raiz)
    except CasoIdInvalido:
        return None, origem, "caso_id_invalido"
    except OSError:
        return None, origem, "caso_id_nao_gravado"
    return cid, origem, (None if cid else "caso_id_ausente")


def registrar(raiz, session_id=None, ts=None, criar=True):
    'Vincula a sessão corrente à pasta do caso. Grava o ponteiro da sessão e o corrente.'


    if not _s(raiz):
        raise ValueError("raiz do caso vazia")
    raiz = os.path.abspath(raiz.strip())
    if criar:
        try:
            os.makedirs(raiz, exist_ok=True)
        except (OSError, ValueError) as e:
            raise RegistroNaoGravado("pasta_nao_gravavel", e)



    caso_id, erro_id, aviso = None, None, None
    if os.path.isdir(raiz):
        try:
            caso_id = garantir_caso_id(raiz, ts)
            if _dono_vivo(caso_id, raiz):
                caso_id = "caso-" + secrets.token_hex(6)
                _gravar_caso_id(raiz, caso_id, ts)
                aviso = "caso_id_copiado"
        except OSError:
            caso_id, erro_id = None, "caso_id_nao_gravado"
    else:
        erro_id = "pasta_inexistente"
    reg = {"raiz": raiz, "caso_id": caso_id,
           "session_id": session_id.strip() if _s(session_id) else None,
           "registrado_em": ts if _s(ts) else time.strftime("%Y-%m-%dT%H:%M:%S")}

    escritos = []
    texto = json.dumps(reg, ensure_ascii=False, indent=2)
    alvos = ([caminho_ponteiro_sessao(session_id)] if _s(session_id) else []) + [caminho_ponteiro_atual()]
    if caso_id:
        alvos.append(_caminho_dono(caso_id))
    try:
        for p in alvos:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(texto)
            escritos.append(p)
    except OSError as e:
        raise RegistroNaoGravado("ponteiro_nao_gravado", e)

    reg["ponteiros"] = escritos[:2] if _s(session_id) else escritos[:1]
    if erro_id:
        reg["caso_id_erro"] = erro_id
    if aviso:
        reg["caso_id_aviso"] = aviso
    return reg


def relato_registro(reg):
    'O que o registro relata à máquina: o código do caso, sem o caminho da pasta, que'

    out = {"caso_id": reg.get("caso_id"), "session_id": reg.get("session_id"),
           "registrado_em": reg.get("registrado_em"), "ponteiros": len(reg.get("ponteiros") or [])}
    if reg.get("caso_id_erro"):
        out["caso_id_erro"] = reg["caso_id_erro"]
    if reg.get("caso_id_aviso"):
        out["caso_id_aviso"] = reg["caso_id_aviso"]
    return out


def arquivo(nome, cwd=None, session_id=None):
    """Caminho de um arquivo de controle NA RAIZ DO CASO (PROVENIENCIA.jsonl, PECA_STATE.json…)."""
    raiz, _ = resolver(cwd=cwd, session_id=session_id)
    return os.path.join(raiz, nome)


def e_efemero(caminho):
    'True quando o caminho não sobrevive à sessão — lugar de STAGING, nunca de artefato'



    if not _s(caminho):
        return False
    if e_ambiente_efemero():
        return True
    p = os.path.abspath(caminho.strip()).replace("\\", "/")
    segs = [s.lower() for s in p.split("/") if s]
    if any(s in _SEGMENTOS_EFEMEROS for s in segs):
        return True
    try:
        tmp = os.path.abspath(tempfile.gettempdir()).replace("\\", "/").lower().rstrip("/")
    except Exception:
        return False
    pl = p.lower()
    return bool(tmp) and (pl == tmp or pl.startswith(tmp + "/"))



def _print(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False))
    return code


def main(argv=None):
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Raiz do caso (Dissero) — independente do cwd da sessão")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("registrar", help="vincula a sessão corrente à pasta do caso")
    pr.add_argument("--raiz", required=True)
    pr.add_argument("--session-id", dest="session_id")
    pr.add_argument("--ts")
    pr.add_argument("--nao-criar", dest="nao_criar", action="store_true")

    pi = sub.add_parser("id", help="código opaco do caso vigente (cria o de caso antigo)")
    pi.add_argument("--session-id", dest="session_id")
    pi.add_argument("--cwd")

    ps = sub.add_parser("resolver", help="mostra a raiz vigente e de onde ela veio")
    ps.add_argument("--session-id", dest="session_id")
    ps.add_argument("--cwd")
    ps.add_argument("--nome", help="devolve também o caminho deste arquivo na raiz do caso")

    pe = sub.add_parser("efemero", help="o caminho é temporário/scratchpad?")
    pe.add_argument("--caminho", required=True)

    pam = sub.add_parser("ambiente", help="este ambiente sobrevive à sessão? (sandbox de nuvem?)")
    pam.add_argument("--marcar", choices=("efemero", "duravel"),
                     help="grava <base>/ambiente.json com a resposta (para o gate saber)")
    pam.add_argument("--motivo", default="")

    args = ap.parse_args(argv)

    if args.cmd == "ambiente":
        if args.marcar:
            try:
                alvo = marcar_ambiente(args.marcar == "efemero", args.motivo)
            except Exception as e:
                return _print({"ok": False, "erro": str(e)}, 1)
            return _print({"ok": True, "marcador": alvo, **ambiente()})
        return _print({"ok": True, **ambiente()})

    if args.cmd == "registrar":
        try:
            reg = registrar(args.raiz, args.session_id, args.ts, criar=not args.nao_criar)
        except CasoIdInvalido:
            return _print({"ok": False, "erro": CasoIdInvalido.codigo,
                           "orientacao": f"o {ARQUIVO_CASO_ID} da pasta do caso foi alterado; "
                                         "apague-o para que um código novo seja gerado"}, 1)
        except RegistroNaoGravado as e:
            return _print({"ok": False, "erro": e.codigo, "detalhe": e.detalhe}, 1)
        except OSError as e:

            return _print({"ok": False, "erro": "registro_nao_gravado",
                           "detalhe": e.strerror or type(e).__name__}, 1)
        except ValueError as e:
            return _print({"ok": False, "erro": "raiz_vazia", "detalhe": str(e)}, 1)
        except Exception as e:
            return _print({"ok": False, "erro": "registro_nao_gravado", "detalhe": type(e).__name__}, 1)
        return _print({"ok": True, **relato_registro(reg)})

    if args.cmd == "id":
        cid, origem, erro = caso_id_vigente(cwd=args.cwd, session_id=args.session_id, criar=True)
        if not cid:
            return _print({"ok": False, "erro": erro, "origem": origem}, 1)
        return _print({"ok": True, "caso_id": cid, "origem": origem})

    if args.cmd == "resolver":
        raiz, origem = resolver(cwd=args.cwd, session_id=args.session_id)
        out = {"ok": True, "raiz": raiz, "origem": origem, "existe": os.path.isdir(raiz)}
        if origem != "cwd":
            cid, _, _ = caso_id_vigente(cwd=args.cwd, session_id=args.session_id)
            out["caso_id"] = cid
        if _s(args.nome):
            out["caminho"] = os.path.join(raiz, args.nome.strip())
        return _print(out)

    return _print({"ok": True, "caminho": args.caminho, "efemero": e_efemero(args.caminho)})


if __name__ == "__main__":
    sys.exit(main())
