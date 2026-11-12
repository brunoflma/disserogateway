#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'registro_falas.py — hook UserPromptSubmit: o LIVRO DE FALAS da superfície sem registro da conversa.'








































import hashlib
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
try:
    import caso_raiz as _caso_raiz
except Exception:
    _caso_raiz = None

PASTA_LIVRO = "livro_falas"

TETO_TEXTO = 20000
TETO_LIVRO = 4 * 1024 * 1024


def _superficie_remota_local(env=None):
    'Réplica da regra de `caso_raiz.superficie_remota`, para cópia instalada cujo `caso_raiz`'

    env = os.environ if env is None else env
    remoto = str(env.get("CLAUDE_CODE_REMOTE") or "").strip().lower() in ("true", "1")
    entrada = str(env.get("CLAUDE_CODE_ENTRYPOINT") or "").strip().lower().startswith("remote")
    return remoto or entrada


def superficie_remota(env=None):
    'O ambiente do processo diz que a sessão é remota (Cowork remoto do claude.ai)? A regra é a'

    f = getattr(_caso_raiz, "superficie_remota", None) if _caso_raiz is not None else None
    if callable(f):
        return f(env)
    return _superficie_remota_local(env)


def registro_ausente(evento, local=None):
    'O evento não traz o registro da conversa: sem `transcript_path`, ou o caminho não é arquivo.'

    tp = evento.get("transcript_path") if isinstance(evento, dict) else None
    if not (isinstance(tp, str) and tp.strip()):
        return True
    try:
        return not os.path.isfile(local(tp) if local else tp)
    except Exception:
        return True


def superficie_sem_registro(evento, local=None, env=None):
    """A superfície remota com o registro da conversa estruturalmente ausente."""
    return superficie_remota(env) and registro_ausente(evento, local)


def pasta_livro():
    """A pasta do livro de falas, ao lado da dos selos do gate."""
    if _caso_raiz is not None:
        base = _caso_raiz.base_dir()
    else:
        base = os.path.join(os.path.expanduser("~"), ".dissero")
    return os.path.join(base, PASTA_LIVRO)


def caminho_livro(session_id):
    chave = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
    return os.path.join(pasta_livro(), chave + ".jsonl")


def _sha(reg):
    """sha256 da linha sem o próprio `sha256`, em JSON canônico."""
    corpo = {k: v for k, v in reg.items() if k != "sha256"}
    return hashlib.sha256(json.dumps(corpo, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def ler_livro(session_id):
    '(estado, linhas) do livro da sessão. Estados: "ausente" (sem livro ou vazio), "ilegivel"'

    if not (isinstance(session_id, str) and session_id.strip()):
        return "ausente", []
    try:
        p = caminho_livro(session_id)
        if not os.path.isfile(p):
            return "ausente", []
        if os.path.getsize(p) > TETO_LIVRO + TETO_TEXTO * 8:
            return "ilegivel", []
        with open(p, "rb") as fh:
            dados = fh.read()



        brutas = [b.rstrip(b"\r").decode("utf-8") for b in dados.split(b"\n")]
    except Exception:
        return "ilegivel", []
    linhas, anterior = [], ""
    for i, bruta in enumerate(x for x in brutas if x.strip()):
        try:
            reg = json.loads(bruta)
        except Exception:
            return "ilegivel", []
        if not (isinstance(reg, dict) and reg.get("seq") == i + 1 and reg.get("sha_anterior") == anterior
                and isinstance(reg.get("sha256"), str) and reg["sha256"] == _sha(reg)):
            return "ilegivel", []
        if "texto" in reg and not isinstance(reg["texto"], str):
            return "ilegivel", []
        anterior = reg["sha256"]
        linhas.append(reg)
    return ("ok", linhas) if linhas else ("ausente", [])


def _sem_colado(texto):
    """A regra do gate (`gate_entrega._sem_colado`): só o digitado, ou None."""
    import gate_entrega
    return gate_entrega._sem_colado(texto)


ESPERA_TRAVA_S = 5.0
TRAVA_VELHA_S = 30.0


def _travar(p):
    'Trava do livro (`<livro>.trava`, criada com O_EXCL) em volta de ler, calcular e acrescentar.'



    trava = p + ".trava"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    limite = time.monotonic() + ESPERA_TRAVA_S
    while True:
        try:
            os.close(os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return trava
        except (FileExistsError, PermissionError):




            try:
                if time.time() - os.path.getmtime(trava) > TRAVA_VELHA_S:
                    os.remove(trava)
                    continue
            except OSError:
                pass
            if time.monotonic() >= limite:
                return None
            time.sleep(0.05)


def registrar(evento, env=None, agora=None):
    """Acrescenta a linha da mensagem ao livro da sessão. True quando gravou. Nunca levanta."""
    try:
        if not isinstance(evento, dict) or evento.get("hook_event_name") != "UserPromptSubmit":
            return False
        if not superficie_sem_registro(evento, env=env):
            return False
        sid = evento.get("session_id")
        if not (isinstance(sid, str) and sid.strip()):
            return False
        trava = _travar(caminho_livro(sid))
        if trava is None:
            return False
        try:
            return _registrar_travado(evento, sid, agora)
        finally:
            try:
                os.remove(trava)
            except OSError:
                pass
    except Exception:
        return False


def _registrar_travado(evento, sid, agora):
    try:
        estado, linhas = ler_livro(sid)
        if estado == "ilegivel":
            return False
        p = caminho_livro(sid)
        if os.path.isfile(p) and os.path.getsize(p) >= TETO_LIVRO:
            return False
        reg = {"seq": len(linhas) + 1,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(agora if agora is not None else time.time()))}
        prompt = evento.get("prompt")
        if isinstance(prompt, str):
            try:
                texto = _sem_colado(prompt)
            except Exception:
                texto = None
            if texto is None:
                reg.update(sem_texto=True, motivo="colado_indelimitavel")
            else:
                reg["texto"] = texto[:TETO_TEXTO]
        else:
            reg["sem_prompt"] = True
        reg["sha_anterior"] = linhas[-1]["sha256"] if linhas else ""
        reg["sha256"] = _sha(reg)
        os.makedirs(os.path.dirname(p), exist_ok=True)


        with open(p, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(reg, ensure_ascii=True) + "\n")
        return True
    except Exception:
        return False


def main():
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return 0
        raw = sys.stdin.read()
        evento = json.loads(raw) if raw and raw.strip() else {}
    except Exception:
        evento = {}
    registrar(evento)
    return 0


if __name__ == "__main__":
    sys.exit(main())
