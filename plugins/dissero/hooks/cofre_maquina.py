#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'cofre_maquina.py — o token de máquina do canal Dissero no cofre do sistema (24/10/2026).'












































from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

ALVO = "dissero-canal"





def _alvo(alvo=None) -> str:
    return alvo or os.environ.get("DSR_COFRE_ALVO") or ALVO


def _pasta(pasta=None) -> Path:
    'A pasta dos comandos e do arquivo de reserva: ~/.dissero, ou `DSR_COFRE_PASTA` (a suíte de'

    return Path(pasta or os.environ.get("DSR_COFRE_PASTA") or PASTA_PADRAO)
CONTA = "maquina"
AQUI = Path(__file__).resolve().parent
PASTA_PADRAO = Path.home() / ".dissero"
ARQUIVO_RESERVA = "maquina.token"
ARQUIVO_CIFRADO = "maquina.cofre"
SCRIPT_MODULO = "cofre_maquina.py"
SCRIPT_PS1 = "cabecalho.ps1"
SCRIPT_SH = "cabecalho.sh"


TOKEN_RX = re.compile(r"^[A-Za-z0-9_-]{20,200}$")
TIMEOUT_S = 10



COMANDO_WINDOWS = ('powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File '
                   '"%USERPROFILE%\\.dissero\\cabecalho.ps1"')
COMANDO_POSIX = 'sh "$HOME/.dissero/cabecalho.sh"'


class CofreIndisponivel(RuntimeError):
    """Nenhum cofre aceitou o token. A mensagem diz por quê, sem o token."""


def token_valido(token) -> bool:
    return bool(TOKEN_RX.match(str(token or "")))



def _win():
    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                    ("UserName", wintypes.LPWSTR)]

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    adv.CredWriteW.restype = wintypes.BOOL
    adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    adv.CredReadW.restype = wintypes.BOOL
    adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    adv.CredDeleteW.restype = wintypes.BOOL
    adv.CredFree.argtypes = [ctypes.c_void_p]
    return ctypes, CREDENTIALW, adv


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


def _win_gravar(alvo, token):
    ctypes, CREDENTIALW, adv = _win()
    blob = token.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    c = CREDENTIALW()
    c.Type = CRED_TYPE_GENERIC
    c.TargetName = alvo
    c.Comment = "Dissero: token de maquina do canal de atualizacao"
    c.CredentialBlobSize = len(blob)
    c.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    c.Persist = CRED_PERSIST_LOCAL_MACHINE
    c.UserName = CONTA
    if not adv.CredWriteW(ctypes.byref(c), 0):
        raise CofreIndisponivel(f"o Gerenciador de Credenciais recusou a gravacao (erro {ctypes.get_last_error()})")


def _win_ler(alvo) -> str:
    ctypes, CREDENTIALW, adv = _win()
    p = ctypes.POINTER(CREDENTIALW)()
    if not adv.CredReadW(alvo, CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
        return ""
    try:
        c = p.contents
        bruto = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
        return bruto.decode("utf-16-le", errors="replace").strip()
    finally:
        adv.CredFree(p)


def _win_apagar(alvo) -> bool:
    _ctypes, _c, adv = _win()
    return bool(adv.CredDeleteW(alvo, CRED_TYPE_GENERIC, 0))











VOLTAS_WINDOWS = 4
ESPERA_WINDOWS_S = 0.5


PREFIXO_ALVO_TESTE = "dissero-canal-teste"


def _espera_windows(alvo) -> float:
    v = os.environ.get("DSR_COFRE_ESPERA_MS", "")
    if str(alvo).startswith(PREFIXO_ALVO_TESTE) and v.isdigit():
        return int(v) / 1000
    return ESPERA_WINDOWS_S


def _win_gravar_conferido(alvo, token, dormir=None) -> int:
    'Grava, relê na hora e de novo depois de ESPERA_WINDOWS_S; o que não voltar igual é gravado'


    for volta in range(1, VOLTAS_WINDOWS + 1):
        _win_gravar(alvo, token)
        if _win_ler(alvo) != token:
            continue
        (dormir or time.sleep)(_espera_windows(alvo))
        if _win_ler(alvo) == token:
            return volta
    raise CofreIndisponivel(f"o cofre (windows) aceitou a gravação, mas não devolveu o token na releitura "
                            f"em {VOLTAS_WINDOWS} tentativas")



def _rodar(executar, cmd, entrada=None):
    try:
        return executar(cmd, input=entrada, capture_output=True, text=True, timeout=TIMEOUT_S)
    except Exception:
        return None


def _mac_gravar(alvo, token, executar):

    r = _rodar(executar, ["security", "-i"],
               f"add-generic-password -U -a {CONTA} -s {alvo} -l Dissero -w {token}\n")
    if r is None or r.returncode != 0:
        raise CofreIndisponivel("o Keychain recusou a gravacao (security add-generic-password)")


def _mac_ler(alvo, executar) -> str:
    r = _rodar(executar, ["security", "find-generic-password", "-a", CONTA, "-s", alvo, "-w"])
    return (r.stdout or "").strip() if r is not None and r.returncode == 0 else ""


def _mac_apagar(alvo, executar) -> bool:
    r = _rodar(executar, ["security", "delete-generic-password", "-a", CONTA, "-s", alvo])
    return r is not None and r.returncode == 0


def _linux_gravar_chaveiro(alvo, token, executar) -> bool:
    if not shutil.which("secret-tool"):
        return False
    r = _rodar(executar, ["secret-tool", "store", "--label=Dissero canal", "service", alvo, "account", CONTA],
               token)
    return r is not None and r.returncode == 0


def _linux_ler_chaveiro(alvo, executar) -> str:
    if not shutil.which("secret-tool"):
        return ""
    r = _rodar(executar, ["secret-tool", "lookup", "service", alvo, "account", CONTA])
    return (r.stdout or "").strip() if r is not None and r.returncode == 0 else ""


def _linux_apagar_chaveiro(alvo, executar) -> bool:
    if not shutil.which("secret-tool"):
        return False
    r = _rodar(executar, ["secret-tool", "clear", "service", alvo, "account", CONTA])
    return r is not None and r.returncode == 0


def _arquivo_apagar(pasta: Path) -> bool:
    """Apaga o arquivo de reserva em texto puro de versões anteriores, se existir."""
    try:
        (pasta / ARQUIVO_RESERVA).unlink()
        return True
    except OSError:
        return False



import hmac
import secrets


def _id_maquina(plataforma=None, executar=subprocess.run) -> bytes:
    'O identificador estável desta máquina: `/etc/machine-id` (systemd) ou o do D-Bus no Linux; o'




    if os.environ.get("DSR_COFRE_ID_MAQUINA"):
        return os.environ["DSR_COFRE_ID_MAQUINA"].encode()
    plataforma = plataforma or sys.platform
    if plataforma == "darwin":
        r = _rodar(executar, ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        m = re.search(r'"IOPlatformUUID"\s*=\s*"([0-9A-Fa-f-]{36})"', (r.stdout or "") if r is not None else "")
        return m.group(1).encode() if m else b""
    for caminho in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            v = Path(caminho).read_text(encoding="ascii").strip()
        except (OSError, UnicodeDecodeError):
            continue
        if re.fullmatch(r"[0-9a-f]{32}", v):
            return v.encode()
    return b""


def _uid() -> bytes:
    return str(os.getuid() if hasattr(os, "getuid") else 0).encode()


def _chaves(sal: bytes, id_maquina: bytes):
    base = hmac.new(id_maquina, b"dissero-canal|" + _uid() + b"|" + sal, hashlib.sha256).digest()
    return (hmac.new(base, b"cifra", hashlib.sha256).digest(),
            hmac.new(base, b"etiqueta", hashlib.sha256).digest())


def _fluxo(chave: bytes, nonce: bytes, n: int) -> bytes:
    saida = b""
    i = 0
    while len(saida) < n:
        saida += hmac.new(chave, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
        i += 1
    return saida[:n]


def cifrar(token: str, id_maquina: bytes) -> dict:
    sal, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    kc, ke = _chaves(sal, id_maquina)
    claro = token.encode("ascii")
    cifra = bytes(a ^ b for a, b in zip(claro, _fluxo(kc, nonce, len(claro))))
    etiqueta = hmac.new(ke, b"v1" + sal + nonce + cifra, hashlib.sha256).hexdigest()
    return {"v": 1, "sal": sal.hex(), "nonce": nonce.hex(), "cifra": cifra.hex(), "etiqueta": etiqueta}


def decifrar(registro, id_maquina: bytes) -> str:
    """O token, ou '' se o registro não é deste formato, foi alterado ou é de outra máquina."""
    try:
        sal, nonce = bytes.fromhex(registro["sal"]), bytes.fromhex(registro["nonce"])
        cifra = bytes.fromhex(registro["cifra"])
        if registro.get("v") != 1 or len(sal) != 16 or len(nonce) != 16 or not id_maquina:
            return ""
        kc, ke = _chaves(sal, id_maquina)
        esperada = hmac.new(ke, b"v1" + sal + nonce + cifra, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperada, str(registro.get("etiqueta", ""))):
            return ""
        return bytes(a ^ b for a, b in zip(cifra, _fluxo(kc, nonce, len(cifra)))).decode("ascii")
    except Exception:
        return ""


def _cifrado_gravar(pasta: Path, token, id_maquina: bytes):
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(pasta, 0o700)
    except OSError:
        pass
    destino, provisorio = pasta / ARQUIVO_CIFRADO, pasta / (ARQUIVO_CIFRADO + ".novo")
    fd = os.open(str(provisorio), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(cifrar(token, id_maquina)))
    os.replace(provisorio, destino)
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass


def _cifrado_ler(pasta: Path, id_maquina: bytes) -> str:
    try:
        return decifrar(json.loads((pasta / ARQUIVO_CIFRADO).read_text(encoding="utf-8")), id_maquina)
    except (OSError, ValueError):
        return ""


def _cifrado_apagar(pasta: Path) -> bool:
    try:
        (pasta / ARQUIVO_CIFRADO).unlink()
        return True
    except OSError:
        return False



MSG_SEM_COFRE = ("nem o cofre do sistema nem a reserva cifrada estão disponíveis nesta máquina: não há "
                 "Keychain desbloqueado ou chaveiro (Secret Service, secret-tool) na sessão, e o identificador da "
                 "máquina (/etc/machine-id no Linux, IOPlatformUUID no macOS) não pôde ser lido. O "
                 "plugin não guarda o token em arquivo de texto")


def gravar(token, *, alvo=None, pasta=None, plataforma=None, executar=subprocess.run) -> str:
    "Grava o token no cofre do sistema, confere relendo, e devolve onde: 'windows', 'keychain',"



    if not token_valido(token):
        raise CofreIndisponivel("token com formato inesperado; nada foi gravado")
    alvo = _alvo(alvo)
    pasta = _pasta(pasta)
    plataforma = plataforma or sys.platform
    if plataforma == "win32":
        _win_gravar_conferido(alvo, token)
        _arquivo_apagar(pasta)
        return "windows"
    else:
        try:
            if plataforma == "darwin":
                _mac_gravar(alvo, token, executar)
                onde = "keychain"
            elif _linux_gravar_chaveiro(alvo, token, executar):
                onde = "chaveiro"
            else:
                raise CofreIndisponivel("sem chaveiro")
            if ler(alvo=alvo, pasta=pasta, plataforma=plataforma, executar=executar) != token:
                raise CofreIndisponivel("releitura")
            _cifrado_apagar(pasta)
        except CofreIndisponivel:
            id_maq = _id_maquina(plataforma, executar)
            if not id_maq:
                raise CofreIndisponivel(MSG_SEM_COFRE) from None
            _cifrado_gravar(pasta, token, id_maq)
            onde = "cifrado"
    if ler(alvo=alvo, pasta=pasta, plataforma=plataforma, executar=executar) != token:
        raise CofreIndisponivel(f"o cofre ({onde}) aceitou a gravação, mas não devolveu o token na releitura")
    _arquivo_apagar(pasta)
    return onde


def ler(*, alvo=None, pasta=None, plataforma=None, executar=subprocess.run) -> str:
    """O token do cofre, ou ''. Só devolve token de formato válido. NUNCA levanta."""
    alvo = _alvo(alvo)
    plataforma = plataforma or sys.platform
    try:
        if plataforma == "win32":
            t = _win_ler(alvo)
        elif plataforma == "darwin":
            t = _mac_ler(alvo, executar)
        else:
            t = _linux_ler_chaveiro(alvo, executar)
        if not token_valido(t) and plataforma != "win32":
            t = _cifrado_ler(_pasta(pasta), _id_maquina(plataforma, executar))
    except Exception:
        t = ""
    return t if token_valido(t) else ""


def apagar(*, alvo=None, pasta=None, plataforma=None, executar=subprocess.run) -> bool:
    """Tira o token do cofre (revogação, limpeza). True se algo foi apagado. NUNCA levanta."""
    alvo = _alvo(alvo)
    plataforma = plataforma or sys.platform
    try:
        if plataforma == "win32":
            return _win_apagar(alvo)
        c = _cifrado_apagar(_pasta(pasta))
        a = _arquivo_apagar(_pasta(pasta))
        s = _mac_apagar(alvo, executar) if plataforma == "darwin" else _linux_apagar_chaveiro(alvo, executar)
        return s or c or a
    except Exception:
        return False


def comando(plataforma=None) -> str:
    """O comando do headersHelper para o settings desta plataforma."""
    return COMANDO_WINDOWS if (plataforma or sys.platform) == "win32" else COMANDO_POSIX


def instalar_auxiliares(pasta=None, origem=AQUI) -> list:
    'Copia cabecalho.ps1 e cabecalho.sh para `pasta` (~/.dissero), onde o comando os procura.'

    pasta = _pasta(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    feitos = []
    for nome in (SCRIPT_PS1, SCRIPT_SH, SCRIPT_MODULO):
        fonte = Path(origem) / nome
        if not fonte.is_file():
            continue
        destino = pasta / nome
        novo = fonte.read_bytes()
        if not destino.is_file() or destino.read_bytes() != novo:
            _gravar_por_cima(destino, novo)
            if nome == SCRIPT_SH:
                try:
                    os.chmod(destino, 0o755)
                except OSError:
                    pass
            feitos.append(destino)
    return feitos


def _gravar_por_cima(destino: Path, novo: bytes) -> None:
    'Grava `novo` em `destino`, também quando ele está SOMENTE LEITURA (rodada 4, 27/10/2026): o'




    try:
        destino.write_bytes(novo)
        return
    except PermissionError:
        if os.name == "nt":
            os.chmod(destino, stat.S_IWRITE | stat.S_IREAD)
        else:
            os.chmod(destino, stat.S_IMODE(destino.stat().st_mode) | stat.S_IWUSR)
    destino.write_bytes(novo)


def auxiliares_presentes(pasta=None, origem=AQUI) -> bool:
    """True quando o script do comando desta plataforma está em `pasta` e igual ao do plugin."""
    nomes = (SCRIPT_PS1,) if sys.platform == "win32" else (SCRIPT_SH, SCRIPT_MODULO)
    try:
        return all((_pasta(pasta) / n).read_bytes() == (Path(origem) / n).read_bytes() for n in nomes)
    except OSError:
        return False


def bloco_marketplace(origem: str, plataforma=None) -> dict:
    'A declaração da loja SEM o token: o cabeçalho sai do headersHelper, que lê o cofre.'

    return {"source": {"source": "url", "url": f"{origem.rstrip('/')}/marketplace.json",
                       "headersHelper": comando(plataforma)},
            "autoUpdate": True}



def dir_config_claude(ambiente=None) -> Path:
    """A pasta de configuração do Claude Code: `CLAUDE_CONFIG_DIR`, senão `~/.claude`."""
    amb = os.environ if ambiente is None else ambiente
    v = amb.get("CLAUDE_CONFIG_DIR")
    return Path(v) if v else Path.home() / ".claude"


def servicos_keychain_claude(ambiente=None) -> list:
    'Os nomes possíveis do item do login no Keychain, pela regra do Claude Code 2.1.310: sem'



    amb = os.environ if ambiente is None else ambiente
    base = "Claude Code-credentials"
    seguro = amb.get("CLAUDE_SECURESTORAGE_CONFIG_DIR")
    if seguro is not None:
        pastas = [seguro] if seguro else []
    elif amb.get("CLAUDE_CONFIG_DIR"):
        pastas = [amb["CLAUDE_CONFIG_DIR"]]
    else:
        return [base]
    nomes = []
    for p in pastas:
        for forma in (p, os.path.abspath(os.path.expanduser(p))):
            sufixo = hashlib.sha256(unicodedata.normalize("NFC", forma).encode("utf-8")).hexdigest()[:8]
            n = f"{base}-{sufixo}"
            if n not in nomes:
                nomes.append(n)
    return nomes or [base]


def _json_do_keychain(texto: str):
    """O `security -w` devolve o texto, ou hex quando o valor foi gravado como dado. Aceita os dois."""
    t = (texto or "").strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    if re.fullmatch(r"[0-9a-fA-F]+", t or "x") and len(t) % 2 == 0:
        try:
            return json.loads(bytes.fromhex(t).decode("utf-8"))
        except Exception:
            pass
    return None


def ler_store_claude(ambiente=None, plataforma=None, executar=subprocess.run):
    'O store de login do Claude Code (o JSON com `mcpOAuth`), ou None. No macOS lê o Keychain'


    plataforma = plataforma or sys.platform
    if plataforma == "darwin":
        for servico in servicos_keychain_claude(ambiente):
            r = _rodar(executar, ["security", "find-generic-password", "-a", "claude-code-user", "-w",
                                  "-s", servico])
            if r is not None and r.returncode == 0:
                d = _json_do_keychain(r.stdout)
                if isinstance(d, dict):
                    return d
    try:
        d = json.loads((dir_config_claude(ambiente) / ".credentials.json").read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None









if __name__ == "__main__":
    if sys.argv[1:] in (["-h"], ["--help"]):
        print("uso: cofre_maquina.py --token\n"
              "Imprime o token da reserva cifrada desta máquina (macOS e Linux sem Keychain ou chaveiro),\n"
              "para o cabecalho.sh. Sem reserva, ou no Windows, sai 1 calado. Não lê o cofre do sistema.")
        sys.exit(0)
    if sys.argv[1:] == ["--token"] and sys.platform != "win32":
        _t = _cifrado_ler(_pasta(), _id_maquina())
        _t = _t if token_valido(_t) else ""
        if _t:
            sys.stdout.write(_t)
            sys.exit(0)
    sys.exit(1)
