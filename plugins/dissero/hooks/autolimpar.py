#!/usr/bin/env python3
'autolimpar.py — poda de órfãos e AUTO-CURA de versão do plugin Dissero (SessionStart).'





























import json, os, sys, tempfile, shutil
from pathlib import Path

PROTEGE_PREFIXO = (".claude-plugin/",)
PROTEGE_EXATO = {"hooks/hooks.json", "hooks/autolimpar.sh", "hooks/autolimpar.py",
                 "hooks/detectar-demanda.sh", "hooks/detectar_demanda.py", "README.md"}
TIPOS = (".md", ".html", ".py", ".json", ".xml", ".docx", ".sh")
MIN_FILESET = 50


def _raiz():
    r = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(r) if r else Path(__file__).resolve().parent.parent


def _nome_plugin(base):
    try:
        return json.loads((base / ".claude-plugin" / "plugin.json").read_text("utf-8")).get("name")
    except Exception:
        return None


def _ler_versao(base):
    try:
        return json.loads((base / ".claude-plugin" / "plugin.json").read_text("utf-8")).get("version")
    except Exception:
        return None


def _ver_tuple(s):
    try:
        return tuple(int(x) for x in str(s).strip().split("."))
    except Exception:
        return None


def _ler_fileset(base):
    try:
        fs = set(json.loads((base / ".claude-plugin" / "fileset.json").read_text("utf-8")))
        return fs if len(fs) >= MIN_FILESET else None
    except Exception:
        return None


def _rpm_root():
    """Raiz das cópias de sessão ('rpm') do app desktop. Env DSR_RPM_ROOT para teste."""
    env = os.environ.get("DSR_RPM_ROOT")
    if env:
        return Path(env)
    appdata = os.environ.get("APPDATA")
    raiz = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return raiz / "Claude" / "local-agent-mode-sessions"


def _melhor_rpm(base):
    'ÚLTIMO RECURSO: a cópia dissero de MAIOR versão entre as `rpm` das OUTRAS sessões.'




    melhor, melhor_v = None, None
    try:
        cands = sorted(_rpm_root().glob("*/*/rpm/plugin_*"))
    except Exception:
        return None
    for c in cands:
        try:
            if not c.is_dir() or c.resolve() == base.resolve():
                continue
            if _nome_plugin(c) != "dissero":
                continue
            v = _ver_tuple(_ler_versao(c))
            if v is None:
                continue
            if melhor_v is None or v > melhor_v:
                melhor, melhor_v = c, v
        except Exception:
            continue
    return melhor


def _achar_fonte(base):
    'Fonte da verdade. Env DSR_MARKETPLACE_SRC tem prioridade e é EXCLUSIVO (usado sozinho,'



    env = os.environ.get("DSR_MARKETPLACE_SRC")
    if env:
        cands = [Path(env)]
    else:

        cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
        cands = [cfg / "plugins" / "marketplaces" / "local-desktop-app-uploads" / "dissero"]
    for c in cands:
        try:
            if c.resolve() == base.resolve():
                continue
            if _nome_plugin(c) == "dissero":
                return c
        except Exception:
            continue
    return None if env else _melhor_rpm(base)


def _copia_atomica(src, dst):
    'Copia src→dst com escrita atômica (temp no mesmo dir + os.replace) para nunca deixar'

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(dst.parent), prefix=".dsr_tmp_")
        os.close(fd)
        shutil.copy2(str(src), tmp)
        os.replace(tmp, str(dst))
        return True
    except OSError:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception:
            pass
        return False


def _podar_orfaos(base, manter):
    'Remove arquivos shipáveis de `base` que NÃO estão em `manter` (fileset) nem protegidos.'

    removidos = []
    for f in list(base.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(base).as_posix()
        if rel in manter or rel in PROTEGE_EXATO:
            continue
        if any(rel.startswith(p) for p in PROTEGE_PREFIXO):
            continue
        if "__pycache__" in rel or rel.endswith((".pyc", ".pyo")):
            continue
        if rel.startswith(".") or rel.endswith(".log"):
            continue
        if not rel.endswith(TIPOS):
            continue
        try:
            f.unlink()
            removidos.append(rel)
        except OSError:
            pass
    for d in sorted((p for p in base.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        try:
            next(d.iterdir())
        except StopIteration:
            try:
                d.rmdir()
            except OSError:
                pass
    return removidos


def _emitir(msg):
    """Aviso no formato oficial de SessionStart (additionalContext), como os hooks-irmãos."""
    try:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                  "additionalContext": msg}}))
    except Exception:
        pass


def _log(base, texto):
    try:
        (base / ".autolimpar.log").write_text(texto + "\n", encoding="utf-8")
    except OSError:
        pass


def _curar(base, fonte, fonte_fileset, v_base, v_fonte):
    'Espelha a fonte na sessão: copia (atômico) cada arquivo shipável do fileset da fonte que'

    copiados = 0
    for rel in fonte_fileset:
        if any(rel.startswith(p) for p in PROTEGE_PREFIXO):
            src = fonte / rel
        elif rel.endswith(TIPOS):
            src = fonte / rel
        else:
            continue
        if src.is_file() and _copia_atomica(src, base / rel):
            copiados += 1
    removidos = _podar_orfaos(base, fonte_fileset)
    v_agora = _ler_versao(base)
    if v_agora == v_fonte:
        _log(base, "auto-cura %s -> %s: %d arquivo(s) copiado(s), %d orfao(s) podado(s)."
             % (v_base, v_fonte, copiados, len(removidos)))


        _emitir("[dissero] Esta sessão carregou a versão %s, mas a fonte instalada é %s. "
                "Auto-curei a cópia no disco (espelhei a %s). REINICIE a sessão para carregar "
                "tudo — descrições/arquivos já lidos no início não se atualizam no meio da sessão. "
                "Se persistir, reinstale o plugin ou limpe o cache do 'rpm'."
                % (v_base, v_fonte, v_fonte))
    else:
        _log(base, "auto-cura INCOMPLETA %s -> %s (versao ainda %s; %d copiado(s))."
             % (v_base, v_fonte, v_agora, copiados))
        _emitir("[dissero] Sessão defasada: carregou %s, fonte é %s, e NÃO consegui curar a "
                "cópia (versão no disco ainda %s). Reinstale o plugin ou limpe o cache do 'rpm' "
                "e abra sessão nova." % (v_base, v_fonte, v_agora))


def main():
    base = _raiz()
    if _nome_plugin(base) != "dissero":
        return 0



    if (base / ".git").exists():
        return 0





    if (base / ".canal-dev").exists():
        return 0

    fonte = _achar_fonte(base)
    if fonte is not None:
        v_base, v_fonte = _ler_versao(base), _ler_versao(fonte)
        tb, tf = _ver_tuple(v_base), _ver_tuple(v_fonte)
        fonte_fileset = _ler_fileset(fonte)
        if tb is not None and tf is not None and tf > tb and fonte_fileset:
            _curar(base, fonte, fonte_fileset, v_base, v_fonte)
            return 0


    base_fileset = _ler_fileset(base)
    if not base_fileset:
        return 0
    removidos = _podar_orfaos(base, base_fileset)
    if removidos:
        _log(base, "residuo de versao anterior removido (%d arquivo(s)):\n%s"
             % (len(removidos), "\n".join(removidos)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
