#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'ativar_canal.py — liga o canal de atualizacao automatica do plugin Dissero nesta maquina, e e a'



























































from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import socket
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path



_PASTA = Path(__file__).resolve().parent
if str(_PASTA) not in sys.path:
    sys.path.insert(0, str(_PASTA))
import cofre_maquina as COFRE


def _nome_da_maquina() -> str:
    'Nome da máquina, o mesmo valor de `platform.node()`. Não se usa o `platform`: no Windows'



    try:
        return socket.gethostname()
    except Exception:
        return ""

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ORIGEM = os.environ.get("DSR_RELEASE_ORIGEM", "https://dissero.bfldevlabs.studio")
MERCADO = "dissero"
PLUGIN = f"dissero@{MERCADO}"
UA_CANAL = "dissero/1.0"
SETTINGS = COFRE.dir_config_claude() / "settings.json"



CREDENCIAIS = COFRE.dir_config_claude() / ".credentials.json"
TIMEOUT_LOGIN_S = 20
RC_SEM_LOGIN = 10
RC_COFRE = 12
ROTULO_COFRE = {"windows": "Gerenciador de Credenciais do Windows", "keychain": "Keychain do macOS",
                "chaveiro": "chaveiro do sistema (Secret Service)"}








CLAUDE_CODE_MINIMO = "2.1.295"
RC_CLAUDE_ANTIGO = 11
TIMEOUT_VERSAO_S = 15


def marca(segredo: str) -> str:
    """sha256 truncado: o unico jeito de uma credencial aparecer na saida."""
    return hashlib.sha256(segredo.encode("utf-8")).hexdigest()[:12] if segredo else "(ausente)"


def nome_da_maquina() -> str:
    return (_nome_da_maquina() or os.environ.get("COMPUTERNAME") or "maquina")[:80]


def _tupla_versao(v):
    """'2.1.295' -> (2, 1, 295); qualquer outra coisa -> None. PURA."""
    m = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)\s*", str(v or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def versao_na_saida(texto) -> str | None:
    """A versao X.Y.Z que `claude --version` imprime ('2.1.307 (Claude Code)'), ou None. PURA."""
    m = re.search(r"\b(\d+\.\d+\.\d+)\b", str(texto or ""))
    return m.group(1) if m else None


def abaixo_do_minimo(versao, minimo=CLAUDE_CODE_MINIMO) -> bool:
    'True so quando as DUAS versoes sao legiveis e a instalada e menor. Versao que nao se le nao'

    a, b = _tupla_versao(versao), _tupla_versao(minimo)
    return a is not None and b is not None and a < b


def versao_do_claude(exe, executar=subprocess.run) -> str | None:
    """A versao do Claude Code em `exe` (`<exe> --version`), ou None se nao se le. NUNCA levanta."""
    try:
        r = executar([str(exe), "--version"], capture_output=True, text=True, encoding="utf-8",
                     errors="replace", timeout=TIMEOUT_VERSAO_S)
        return versao_na_saida((r.stdout or "") + (r.stderr or "")) if r.returncode == 0 else None
    except Exception:
        return None


def msg_claude_antigo(versao, minimo=CLAUDE_CODE_MINIMO) -> str:
    return (f"o Claude Code desta maquina esta na versao {versao}, e o plugin Dissero exige a {minimo} ou "
            f"superior. Atualize o Claude Code (no terminal, `claude update`) e rode este comando de novo.")


def bloco_marketplace(origem: str, plataforma=None) -> dict:
    """A declaracao da loja SEM o token: o `headersHelper` le o cofre na hora (cofre_maquina)."""
    return COFRE.bloco_marketplace(origem, plataforma)


def mesclar_declaracao(settings: dict | None, bloco: dict) -> dict:
    'Devolve uma COPIA do settings com a declaracao do canal; tudo o mais fica intacto, outros'

    novo = copy.deepcopy(settings) if isinstance(settings, dict) else {}
    ekm = novo.get("extraKnownMarketplaces")
    if not isinstance(ekm, dict):
        ekm = {}
    ekm[MERCADO] = bloco
    novo["extraKnownMarketplaces"] = ekm
    return novo







def ler_login(credenciais=CREDENCIAIS, origem=ORIGEM, agora_ms=None) -> tuple[str, str]:
    "('valido', token), ('expirado', '') ou ('ausente', ''): o login do conector dissero no store"





    if Path(credenciais) == CREDENCIAIS:

        d = COFRE.ler_store_claude()
    else:
        try:
            d = json.loads(Path(credenciais).read_text(encoding="utf-8-sig"))
        except Exception:
            d = None
    d = d if isinstance(d, dict) else {}
    alvo = f"{str(origem).rstrip('/')}/mcp"
    agora_ms = agora_ms if agora_ms is not None else time.time() * 1000
    melhor, vencido = "", False
    for e in (d.get("mcpOAuth") or {}).values():
        if not isinstance(e, dict) or str(e.get("serverUrl") or "").rstrip("/") != alvo:
            continue
        tok = str(e.get("accessToken") or "").strip()
        if not tok:
            continue
        exp = e.get("expiresAt")
        if isinstance(exp, (int, float)) and exp <= agora_ms:
            vencido = True
            continue
        melhor = tok
    if melhor:
        return "valido", melhor
    return ("expirado" if vencido else "ausente"), ""


def _mensagem_jsonrpc(erro_http) -> str:
    "A frase de `error.message` no corpo JSON-RPC de uma resposta HTTP de erro, ou ''. Corpo que"


    try:
        corpo = json.loads(erro_http.read().decode("utf-8"))
        m = (corpo.get("error") or {}).get("message") if isinstance(corpo, dict) else None
        return m.strip()[:300] if isinstance(m, str) else ""
    except Exception:
        return ""


class CanalNaoConcluiu(Exception):
    'O canal RESPONDEU, mas nao concluiu a ativacao: o HTTP 503 da guarda de licenca (com a frase'







def _descrever_erro_jsonrpc(erro) -> str:
    '`JSON-RPC <code>: <message>` de um `error` JSON-RPC; sem codigo inteiro ou sem frase, a parte'

    codigo = erro.get("code") if isinstance(erro, dict) else None
    frase = str((erro.get("message") if isinstance(erro, dict) else "") or "").strip()[:300]
    return ("JSON-RPC" + (f" {codigo}" if isinstance(codigo, int) and not isinstance(codigo, bool) else "")
            + (f": {frase}" if frase else ""))


def ativar_por_login_http(origem: str, token_oauth: str, maquina: str, timeout=TIMEOUT_LOGIN_S) -> dict:
    '`tools/call ativar_maquina` no /mcp, com o bearer do login. Devolve o `_meta` do Worker'






















    corpo = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "ativar_maquina", "arguments": {"maquina": str(maquina or "")[:80]}}}
    req = urllib.request.Request(f"{origem.rstrip('/')}/mcp", data=json.dumps(corpo).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {token_oauth}", "Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream", "User-Agent": UA_CANAL})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise PermissionError("401") from None
        frase = _mensagem_jsonrpc(e) if e.code in (403, 503) else ""
        if frase and e.code == 403:
            raise RuntimeError(frase) from None
        if frase:
            raise CanalNaoConcluiu(f"HTTP {e.code}: {frase}") from None
        raise OSError(f"HTTP {e.code}") from None
    except (OSError, ValueError) as e:
        raise OSError(f"{type(e).__name__}") from None
    if not isinstance(resp, dict):
        raise OSError("resposta JSON-RPC que nao e objeto")
    if resp.get("error") is not None:
        raise CanalNaoConcluiu(_descrever_erro_jsonrpc(resp["error"]))
    res = resp.get("result") or {}
    meta = res.get("_meta") or {}
    if res.get("isError") or not meta.get("token"):
        texto = " ".join(c.get("text", "") for c in (res.get("content") or []) if isinstance(c, dict)).strip()
        raise RuntimeError(texto or "o canal nao emitiu o token desta maquina")
    return meta

































COPIAS_MANTIDAS = 5
SUFIXO_COPIA = ".bak-dsr-"



MARCADOR_OMITIDO = "<omitido pelo plugin>"
NOMES_SIGILOSOS = ("token", "secret", "key", "password", "passphrase", "auth", "senha")


DICIONARIOS_SIGILOSOS = ("headers", "env")


SUFIXO_REMOVIDAS = ".dsr-removidas.json"
TENTATIVAS_TROCA = 40
ESPERA_TROCA_S = 0.025


TENTATIVAS_LEITURA = 4
ESPERA_LEITURA_S = 0.05
VOLTAS_CAS = 3


class ErroSettings(RuntimeError):
    """Erro NOMEADO da gravacao do settings. `codigo` diz qual conserto cabe."""
    codigo = "settings_erro"

    def __init__(self, mensagem, caminho=None, chaves=()):
        super().__init__(mensagem)
        self.caminho = str(caminho) if caminho is not None else None
        self.chaves = tuple(chaves)


class SettingsIlegivel(ErroSettings):
    """O arquivo existe e nao e um objeto JSON valido. Nada foi gravado."""
    codigo = "settings_ilegivel"


class GravacaoNaoConferida(ErroSettings):
    'A troca aconteceu, mas a releitura achou o arquivo ilegivel ou sem uma chave do advogado, e'



    codigo = "settings_nao_conferido"
    restauracao = "nada"


class SettingsOcupado(ErroSettings):
    'Nenhuma configuracao do advogado mudou, e a declaracao nao ficou. Tres causas: o sistema'





    codigo = "settings_ocupado"

    def __init__(self, mensagem, caminho=None, chaves=(), causa=None):
        super().__init__(mensagem, caminho, chaves)
        self.causa = causa


class SettingsNaoRelido(SettingsOcupado):
    'A troca ACONTECEU (passou pelo compare-and-swap), mas o sistema de arquivos recusou a'




    codigo = "settings_nao_relido"


def _e_sigiloso(nome) -> bool:
    n = str(nome).lower()
    return any(s in n for s in NOMES_SIGILOSOS)


def redigir_para_copia(obj, _dono=""):
    'COPIA de `obj` com os valores de credencial trocados por `MARCADOR_OMITIDO`. Redige por'


    if isinstance(obj, dict):
        saida = {}
        for k, v in obj.items():
            if _dono in DICIONARIOS_SIGILOSOS and isinstance(v, str) and _e_sigiloso(k):
                saida[k] = MARCADOR_OMITIDO
            else:
                saida[k] = redigir_para_copia(v, str(k).lower() if isinstance(k, str) else _dono)
        return saida
    if isinstance(obj, list):
        return [redigir_para_copia(x, _dono) for x in obj]
    return obj


def tem_marcador(obj) -> bool:
    'Se em algum ponto de `obj` ha um valor redigido. Quem restaura usa isto para nao recolocar'

    if isinstance(obj, dict):
        return any(tem_marcador(v) for v in obj.values())
    if isinstance(obj, list):
        return any(tem_marcador(x) for x in obj)
    return obj == MARCADOR_OMITIDO


def _caminhos_com_marcador(obj, prefixo: str) -> list:
    'Caminhos (`env.SENHA_X`) dos valores redigidos em `obj`. So nomes: o advogado precisa saber'

    if isinstance(obj, dict):
        return [c for k, v in obj.items() for c in _caminhos_com_marcador(v, f"{prefixo}.{k}")]
    if isinstance(obj, list):
        return [c for i, x in enumerate(obj) for c in _caminhos_com_marcador(x, f"{prefixo}[{i}]")]
    return [prefixo] if obj == MARCADOR_OMITIDO else []


def _sem_marcador(obj):
    'COPIA de `obj` sem as entradas redigidas. Melhor a ausencia da chave que o marcador: o'

    if isinstance(obj, dict):
        return {k: _sem_marcador(v) for k, v in obj.items() if v != MARCADOR_OMITIDO}
    if isinstance(obj, list):
        return [_sem_marcador(x) for x in obj]
    return obj


def _decodificar(bruto: bytes, caminho):
    try:
        d = json.loads(bruto.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise SettingsIlegivel(f"{caminho} existe e nao e JSON valido; nao foi substituido", caminho) from None
    if not isinstance(d, dict):
        raise SettingsIlegivel(f"{caminho} nao contem um objeto JSON; nao foi substituido", caminho)
    return d


def _ler_bruto(caminho, tentativas=TENTATIVAS_LEITURA, espera=ESPERA_LEITURA_S):
    'Os bytes do arquivo e o modo dele, ou (None, None) se ausente. Tenta de novo enquanto o'


    p = Path(caminho)
    ultimo = None
    for i in range(max(1, tentativas)):
        try:
            bruto = p.read_bytes()
            modo = p.stat().st_mode
            _decodificar(bruto, p)
            return bruto, modo
        except FileNotFoundError:
            return None, None
        except SettingsIlegivel as e:
            ultimo = e
        except OSError as e:
            ultimo = SettingsOcupado(f"{p} nao pode ser lido agora ({type(e).__name__}); nada foi gravado",
                                     p, causa=e)
        if i < tentativas - 1:
            time.sleep(espera)
    raise ultimo


def ler_settings(caminho, tentativas=TENTATIVAS_LEITURA, espera=ESPERA_LEITURA_S):
    'O settings como dict, None se ausente. Levanta SettingsIlegivel se existe e nao e objeto'


    bruto, _modo = _ler_bruto(caminho, tentativas, espera)
    return None if bruto is None else _decodificar(bruto, Path(caminho))


def copias_settings(caminho) -> list:
    """As copias guardadas pelo plugin, da mais antiga para a mais recente."""
    p = Path(caminho)
    return sorted(p.parent.glob(p.name + SUFIXO_COPIA + "*"), key=lambda x: x.name)


def _carimbo() -> str:
    t = time.time()


    return time.strftime("%Y%m%dT%H%M%S", time.gmtime(t)) + f"{int((t % 1) * 1_000_000):06d}"


def _abrir_privado(caminho, modo_origem=None):
    """Abre para escrita um arquivo NOVO. No POSIX nasce 0600 (ou com o modo do original)."""
    modo = 0o600 if modo_origem is None else (modo_origem & 0o777)
    if os.name == "nt":


        modo |= stat.S_IWRITE
    return os.open(str(caminho), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), modo)


def _guardar_copia(p: Path, bruto: bytes, modo_origem, atual=None) -> Path:
    'A copia do arquivo anterior, REDIGIDA: credencial nenhuma em texto puro. Quando nada ha a'

    if atual is not None:
        redigido = redigir_para_copia(atual)
        if redigido != atual:
            bruto = _serializar(redigido)
    base = p.name + SUFIXO_COPIA + _carimbo()
    destino, n = p.with_name(base), 0
    while True:
        try:
            fd = _abrir_privado(destino, modo_origem)
            break
        except FileExistsError:
            n += 1
            destino = p.with_name(f"{base}-{n}")
    with os.fdopen(fd, "wb") as f:
        f.write(bruto)
        f.flush()
        os.fsync(f.fileno())
    return destino


def _podar_copias(p: Path) -> None:
    'So as COPIAS_MANTIDAS mais recentes ficam. Roda depois da troca: a copia de uma volta que'

    for velha in copias_settings(p)[:-COPIAS_MANTIDAS]:
        _apagar(velha)


def _apagar(caminho) -> None:
    if caminho is None:
        return
    try:
        Path(caminho).unlink()
    except PermissionError:


        if os.name == "nt":
            try:
                os.chmod(str(caminho), stat.S_IWRITE)
                Path(caminho).unlink()
            except OSError:
                pass
    except OSError:
        pass


class _ArquivoMudou(Exception):
    """O arquivo nao e mais o que foi lido: o conteudo novo foi calculado sobre o que ja nao existe."""


_SEM_CAS = object()


def _ainda_e(p: Path, antes):
    'Se o arquivo ainda e `antes` (os bytes lidos; None = nao existia): True ou False. None'


    try:
        agora = p.read_bytes()
    except FileNotFoundError:
        return antes is None
    except OSError:
        return None
    return agora == antes


def _trocar_atomico(p: Path, bruto: bytes, modo_origem=None, antes=_SEM_CAS) -> None:
    'Grava `bruto` num irmao temporario, fsync, e troca por `os.replace`. Quem le o caminho ve'







    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.name}.", suffix=".tmp-dsr")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(bruto)
            f.flush()
            os.fsync(f.fileno())
        if modo_origem is not None and os.name != "nt":
            os.chmod(tmp, modo_origem & 0o777)
        for tentativa in range(TENTATIVAS_TROCA):
            if antes is not _SEM_CAS:
                igual = _ainda_e(p, antes)
                if igual is False:
                    raise _ArquivoMudou(str(p))
                if igual is None:
                    if tentativa == TENTATIVAS_TROCA - 1:
                        raise SettingsOcupado(f"{p} nao pode ser lido para conferir a troca; nada foi gravado", p)
                    time.sleep(ESPERA_TROCA_S)
                    continue
            try:
                os.replace(tmp, str(p))
                return
            except PermissionError:


                if tentativa == TENTATIVAS_TROCA - 1:
                    raise
                time.sleep(ESPERA_TROCA_S)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _serializar(obj) -> bytes:
    """UTF-8 SEM BOM: o Node, que le este arquivo, recusa BOM com 'Unexpected token'."""
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


MARCA_CONFERENCIA = "(a declaracao nova)"
MARCA_ILEGIVEL = "(arquivo ilegivel na releitura)"


def _conferir(p: Path, esperadas, conferir):
    '(lido, faltam, bruto). `lido` e None quando o arquivo esta ilegivel agora; `faltam` lista'







    try:
        bruto, _modo = _ler_bruto(p, TENTATIVAS_TROCA, ESPERA_TROCA_S)
        lido = _decodificar(bruto, p) if bruto is not None else {}
    except SettingsIlegivel:
        return None, [MARCA_ILEGIVEL], None
    except SettingsOcupado as e:
        raise SettingsNaoRelido(f"{p} foi gravado, mas nao pode ser relido para conferir (o sistema de arquivos "
                                "recusou a leitura durante todo o prazo); nada foi desfeito", p,
                                causa=e.causa) from None
    faltam = sorted(set(esperadas) - set(lido))
    if not faltam and conferir is not None and not bool(conferir(lido)):
        faltam = [MARCA_CONFERENCIA]
    return lido, faltam, bruto


def gravar_settings(caminho, transformar, conferir=None, _apos_trocar=None) -> dict:
    'Le o settings, aplica `transformar(copia_do_atual_ou_None) -> dict` e grava com as'














    p = Path(caminho)
    try:
        return _gravar_settings(p, transformar, conferir, _apos_trocar)
    except ErroSettings:
        raise
    except OSError as e:
        raise SettingsOcupado(f"{p}: o sistema de arquivos recusou a gravacao ({type(e).__name__}); "
                              "o arquivo do advogado nao foi trocado", p, causa=e) from None


def _gravar_settings(p: Path, transformar, conferir, _apos_trocar) -> dict:
    for _volta in range(VOLTAS_CAS):
        bruto, modo = _ler_bruto(p)
        atual = _decodificar(bruto, p) if bruto is not None else None
        novo = transformar(copy.deepcopy(atual))
        if not isinstance(novo, dict):
            raise TypeError("transformar deve devolver um dict")
        if atual is not None and novo == atual:
            return {"gravado": False, "copia": None, "restaurado": ()}
        copia = _guardar_copia(p, bruto, modo, atual) if bruto is not None else None



        try:
            _trocar_atomico(p, _serializar(novo), modo, antes=bruto)
        except _ArquivoMudou:
            _apagar(copia)
            continue
        except BaseException:


            _apagar(copia)
            raise
        break
    else:



        raise SettingsOcupado(f"{p} mudou durante a gravacao em {VOLTAS_CAS} tentativas seguidas (outro "
                              "programa gravando); nada foi gravado", p)
    _podar_copias(p)
    removidas = set(atual or {}) - set(novo)
    if copia is not None and removidas:
        _registrar_removidas(p, copia, sorted(removidas))
    if _apos_trocar:
        _apos_trocar(p)
    lido, faltam, bruto_lido = _conferir(p, set(novo), conferir)
    if not faltam:
        return {"gravado": True, "copia": str(copia) if copia else None, "restaurado": ()}

    proprias = (set(novo) - set(atual or {})) | {MARCA_CONFERENCIA}
    if lido is not None:
        reparo, faltam_reparo = _reparar(p, lido, bruto_lido, atual, removidas, modo, transformar, conferir)
        if reparo is not None:
            reparo["copia"] = str(copia) if copia else None
            return reparo




        if set(faltam) | set(faltam_reparo) <= proprias:
            raise SettingsOcupado(f"{p} foi regravado por outro programa logo depois da troca, e a gravacao "
                                  f"nao ficou (faltam: {', '.join(faltam)}); o arquivo ficou como o outro "
                                  "programa o deixou, sem nada do advogado a menos", p, faltam)



    if bruto is None:
        erro = GravacaoNaoConferida(f"{p}: a releitura nao conferiu (faltam: {', '.join(faltam)}); "
                                    "nao havia arquivo antes, nada a restaurar", p, faltam)
        erro.restauracao = "nada"
        raise erro
    try:
        _trocar_atomico(p, bruto, modo)
    except (OSError, ErroSettings) as e:
        erro = GravacaoNaoConferida(f"{p}: a releitura nao conferiu (faltam: {', '.join(faltam)}), e o sistema "
                                    f"de arquivos recusou a restauracao ({type(e).__name__}); o arquivo ficou "
                                    "como esta", p, faltam)
        erro.restauracao = "recusada"
        raise erro from None
    erro = GravacaoNaoConferida(f"{p}: a releitura nao conferiu (faltam: {', '.join(faltam)}); "
                                "o arquivo anterior foi restaurado inteiro", p, faltam)
    erro.restauracao = "integral"
    raise erro


def _reparar(p: Path, lido, bruto_lido, atual, removidas, modo, transformar, conferir):
    'Reaplica a transformacao ao conteudo ATUAL do arquivo e recoloca so as chaves de topo que'




    try:
        reparado = transformar(copy.deepcopy(lido))
    except Exception:
        return None, ()
    if not isinstance(reparado, dict):
        return None, ()
    recolocadas = sorted(k for k in (atual or {}) if k not in reparado and k not in removidas)
    for k in recolocadas:
        reparado[k] = atual[k]
    try:
        _trocar_atomico(p, _serializar(reparado), modo, antes=bruto_lido)
    except (_ArquivoMudou, ErroSettings, OSError):
        return None, ()
    _lido2, faltam2, _bruto2 = _conferir(p, set(reparado), conferir)
    if faltam2:
        return None, tuple(faltam2)
    return {"gravado": True, "restaurado": tuple(recolocadas)}, ()


def _registrar_removidas(p: Path, copia: Path, removidas) -> None:
    'Anota ao lado do arquivo quais chaves de topo ESTA escrita tirou de proposito, e contra'

    alvo = p.with_name(p.name + SUFIXO_REMOVIDAS)
    try:
        _trocar_atomico(alvo, json.dumps({"copia": copia.name, "chaves": list(removidas)}).encode("utf-8"))
    except OSError:
        pass


def chaves_removidas_de_proposito(caminho, copia) -> set:
    p = Path(caminho)
    try:
        d = json.loads(p.with_name(p.name + SUFIXO_REMOVIDAS).read_text(encoding="utf-8"))
    except Exception:
        return set()
    return set(d.get("chaves") or []) if d.get("copia") == Path(copia).name else set()


class CopiaAusente(FileNotFoundError):
    'A copia pedida (`--copia`, que o aviso do vigia fixa) nao existe mais: a poda guarda so as'




def restaurar_chaves_ausentes(caminho, copia=None) -> dict:
    'RESTAURACAO POR MESCLAGEM. Acrescenta ao settings de hoje as chaves de TOPO que existiam'










    p = Path(caminho)
    if copia and not Path(copia).is_file():
        raise CopiaAusente(f"{copia} nao existe mais; nada foi alterado")
    escolhidas = [Path(copia)] if copia else copias_settings(p)
    if not escolhidas:
        return {"copia": None, "restauradas": (), "redigidas": (), "entradas_redigidas": (),
                "gravado": False}
    de = escolhidas[-1]
    antes = ler_settings(de) or {}
    restauradas = []


    redigidas = []
    entradas = []

    def trocar(atual):
        d = dict(atual or {})
        restauradas.clear()
        redigidas.clear()
        entradas.clear()
        for chave, valor in antes.items():
            if chave in d:
                continue
            if chave == "extraKnownMarketplaces" and isinstance(valor, dict):

                fora = [m for m, ent in valor.items() if tem_marcador(ent)]
                valor = {m: ent for m, ent in valor.items() if m not in fora}
                if fora:
                    redigidas.append(chave)
                    entradas.extend(f"{chave}.{m}" for m in fora)
                if not valor:
                    continue
            elif tem_marcador(valor):
                entradas.extend(_caminhos_com_marcador(valor, chave))
                valor = _sem_marcador(valor)
                redigidas.append(chave)
                if valor in ({}, []):
                    continue
            d[chave] = valor
            restauradas.append(chave)
        return d

    r = gravar_settings(p, trocar)
    return {"copia": str(de), "restauradas": tuple(restauradas), "redigidas": tuple(redigidas),
            "entradas_redigidas": tuple(entradas), "gravado": bool(r.get("gravado"))}


def gravar_declaracao(caminho, bloco: dict, _apos_trocar=None) -> dict:
    'A declaracao do canal no settings de usuario, pela gravacao segura. A conferencia exige a'

    return gravar_settings(caminho, lambda d: mesclar_declaracao(d, bloco),
                           conferir=lambda lido: ((lido.get("extraKnownMarketplaces") or {}).get(MERCADO) == bloco),
                           _apos_trocar=_apos_trocar)





















PASTA_ESTADO = Path.home() / ".dissero"
PREFIXO_PENDENTE = "declaracao-pendente-"












CACHE_LICENCA = "licenca.json"
LINHA_CACHE_NAO_APAGADO = ("licenca: nao foi possivel apagar {arquivo}, o cache da ultima conferencia da licenca. "
                           "A ativacao vale; o gate de licenca volta a conferir no servidor em ate 24 h.")
CONTADORES_MARCA = ("gravacoes", "falhas")


def contador_marca(v) -> int:
    'Um contador da marca: inteiro finito e >= 0. Qualquer outra coisa (texto, lista, nulo,'


    if isinstance(v, bool):
        return 0
    if isinstance(v, int):
        return v if v >= 0 else 0
    if isinstance(v, float) and math.isfinite(v) and v >= 0:
        return int(v)
    return 0


def instante_marca(v) -> float:
    'Um instante da marca (`desde`, `gravada_em`, `avisada_em`): numero finito, senao 0 (o mais'

    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0.0
    return float(v) if math.isfinite(v) else 0.0


def _chave_settings(settings) -> str:
    return os.path.normcase(os.path.abspath(str(Path(settings).expanduser())))


def marca_pendente(pasta, settings) -> Path:
    """O caminho da marca de pendencia deste settings em `pasta`."""
    h = hashlib.sha256(_chave_settings(settings).encode("utf-8")).hexdigest()[:12]
    return Path(pasta) / f"{PREFIXO_PENDENTE}{h}.json"


def _ler_marca(caminho):
    'Os dados da marca, com os contadores NORMALIZADOS (`contador_marca`), ou None se ela nao e'

    try:
        d = json.loads(Path(caminho).read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    if not (isinstance(d, dict) and isinstance(d.get("settings"), str)):
        return None
    d = dict(d)
    for k in CONTADORES_MARCA:
        d[k] = contador_marca(d.get(k))
    return d


def _gravar_marca(caminho, dados) -> bool:
    try:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        _trocar_atomico(Path(caminho), json.dumps(dados).encode("utf-8"))
        return True
    except Exception:
        return False


def apagar_cache_licenca(pasta) -> bool:
    'Apaga o cache da licenca do gate em `pasta` (ver CACHE_LICENCA). True se ele nao existe mais'


    try:
        p = Path(pasta) / CACHE_LICENCA
        if p.is_file() or p.is_symlink():
            _apagar(p)
        return not os.path.lexists(str(p))
    except Exception:
        return False


def marcar_pendente(pasta, settings, motivo="ativacao", agora=None) -> bool:
    'Marca a declaracao deste settings como pendente, com os contadores zerados (uma ativacao'

    return _gravar_marca(marca_pendente(pasta, settings),
                         {"settings": os.path.abspath(str(Path(settings).expanduser())),
                          "desde": time.time() if agora is None else agora, "motivo": str(motivo),
                          "gravacoes": 0, "falhas": 0})


def consolidar_marcas(pasta, settings):
    '(caminho, dados) da marca deste settings, ou (None, None). As que outro gerador gravou com'





    try:
        alvo = _chave_settings(settings)
        canonica = marca_pendente(pasta, settings)
        achadas, fora_da_forma = [], False
        for m in sorted(Path(pasta).glob(PREFIXO_PENDENTE + "*.json")):
            d = _ler_marca(m)
            if d is not None and _chave_settings(d["settings"]) == alvo:
                achadas.append((m, d))
            elif d is None and m == canonica:
                fora_da_forma = True
        if not achadas and fora_da_forma:
            achadas = [(canonica, {"settings": os.path.abspath(str(Path(settings).expanduser())), "desde": 0,
                                   "motivo": "marca_fora_da_forma", "gravacoes": 0, "falhas": 0})]
        if not achadas:
            return None, None

        achadas.sort(key=lambda x: x[0] != canonica)
        dados = dict(achadas[0][1])
        for _m, d in achadas[1:]:
            for k in CONTADORES_MARCA:
                dados[k] = max(contador_marca(dados.get(k)), contador_marca(d.get(k)))
        if len(achadas) > 1 or achadas[0][0] != canonica:
            if not _gravar_marca(canonica, dados):
                return achadas[0]
            for m, _d in achadas:
                if m != canonica:
                    _apagar(m)
        return canonica, dados
    except Exception:
        return None, None


def atualizar_marca(caminho, dados) -> bool:
    return _gravar_marca(caminho, dados)


def persistir_marca(caminho, dados) -> bool:
    '`atualizar_marca` que nao desiste por um arquivo SOMENTE LEITURA: se a troca e recusada, a'




    if _gravar_marca(caminho, dados):
        return True
    _apagar(caminho)
    return _gravar_marca(caminho, dados)












REGISTRO = COFRE.dir_config_claude() / "plugins" / "known_marketplaces.json"


def registro_de(settings) -> Path:
    'O registro que acompanha um settings de usuario: os dois moram na pasta de configuracao do'


    return Path(settings).parent / "plugins" / "known_marketplaces.json"


def reconciliar_registro(fonte: dict, registro=None, trava=None) -> str:
    'Iguala a `source` da entrada do canal no registro do Claude Code a `fonte` (a declarada).'





    if not isinstance(fonte, dict) or "headers" in fonte or not fonte.get("headersHelper"):
        return "recusado"
    p = Path(registro or REGISTRO)




    try:
        d0 = json.loads(p.read_bytes().decode("utf-8-sig"))
    except FileNotFoundError:
        return "ausente"
    except Exception:
        return "falhou"
    e0 = d0.get(MERCADO) if isinstance(d0, dict) else None
    if not isinstance(e0, dict):
        return "ausente"
    if e0.get("source") == fonte:
        return "em_dia"
    if trava is not None and not adquirir_trava(trava):
        return "ocupado"
    try:
        try:
            d = json.loads(p.read_bytes().decode("utf-8-sig"))
        except FileNotFoundError:
            return "ausente"
        e = d.get(MERCADO) if isinstance(d, dict) else None
        if not isinstance(e, dict):
            return "ausente"
        if e.get("source") == fonte:
            return "em_dia"
        novo = dict(d)
        novo[MERCADO] = {**e, "source": copy.deepcopy(fonte)}
        _trocar_atomico(p, (json.dumps(novo, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        lido = json.loads(p.read_text(encoding="utf-8"))
        return "reconciliado" if (lido.get(MERCADO) or {}).get("source") == fonte else "falhou"
    except Exception:
        return "falhou"
    finally:
        if trava is not None:
            liberar_trava(trava)







TRAVA_INSTALACAO = Path.home() / ".dissero" / "instalacao.lock"


TRAVA_IDADE_S = 15 * 60
TIMEOUT_CLAUDE_S = 300
RC_TRAVA_OCUPADA = 75

RC_SO_REDIGIDAS = 7

RC_COPIA_AUSENTE = 13


def processo_vivo(pid) -> bool:
    'Se o PID esta vivo. NUNCA usa `os.kill(pid, 0)` no Windows: la ele chama TerminateProcess'

    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            return ctypes.get_last_error() == 5
        try:
            codigo = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(codigo)):
                return True
            return codigo.value == 259
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _ler_trava(p: Path):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and "pid" in d else None
    except Exception:
        return None


def _trava_velha(p: Path, info, agora, idade_max, vivo) -> bool:
    if info is None:

        try:
            return agora - p.stat().st_mtime > idade_max
        except OSError:
            return True
    try:
        em = float(info.get("em") or 0)
    except (TypeError, ValueError):
        em = 0
    return agora - em > idade_max or not vivo(info.get("pid"))


def trava_ativa(caminho=None, agora=None, idade_max=TRAVA_IDADE_S, vivo=processo_vivo) -> bool:
    p = Path(caminho or TRAVA_INSTALACAO)
    if not p.exists():
        return False
    return not _trava_velha(p, _ler_trava(p), time.time() if agora is None else agora, idade_max, vivo)


def adquirir_trava(caminho=None, pid=None, agora=None, idade_max=TRAVA_IDADE_S, vivo=processo_vivo) -> bool:
    'Cria a trava com O_EXCL. Trava velha (processo morto, idade acima do teto, ilegivel e'



    p = Path(caminho or TRAVA_INSTALACAO)
    pid = os.getpid() if pid is None else pid
    p.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        agora_ = time.time() if agora is None else agora
        try:
            fd = _abrir_privado(p)
        except FileExistsError:
            info = _ler_trava(p)
            if not _trava_velha(p, info, agora_, idade_max, vivo):
                return False
            lixo = p.with_name(f"{p.name}.velha-{pid}-{time.time_ns()}")
            try:
                os.rename(str(p), str(lixo))
            except FileNotFoundError:
                continue
            except OSError:
                return False
            if _ler_trava(lixo) != info:
                try:
                    os.rename(str(lixo), str(p))
                except OSError:
                    pass
                return False
            try:
                os.unlink(str(lixo))
            except OSError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"pid": pid, "em": agora_}))
        return True
    return False


def liberar_trava(caminho=None, pid=None) -> None:
    """Apaga a trava, mas so se ela for DESTE processo."""
    p = Path(caminho or TRAVA_INSTALACAO)
    pid = os.getpid() if pid is None else pid
    info = _ler_trava(p)
    if info is not None and info.get("pid") == pid:
        try:
            p.unlink()
        except OSError:
            pass


def instalar_sequencial(exe, plugin, trava=None, executar=subprocess.run, versao=None) -> tuple[int, str]:
    'Com a trava tomada: `claude plugin install <plugin>`, ESPERANDO o fim dele. Devolve (rc do'








    if not adquirir_trava(trava):
        return RC_TRAVA_OCUPADA, "outra instalacao do plugin Dissero esta em andamento nesta maquina"
    try:
        v = versao if versao is not None else versao_do_claude(exe)
        if abaixo_do_minimo(v):
            return RC_CLAUDE_ANTIGO, msg_claude_antigo(v)
        kw = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace",
              "timeout": TIMEOUT_CLAUDE_S}
        try:
            r = executar([exe, "plugin", "install", plugin, "--scope", "user"], **kw)
        except Exception as e:
            return 1, f"{type(e).__name__}: {e}"
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    finally:
        liberar_trava(trava)


def instalar(executar=subprocess.run) -> tuple[int, str]:
    exe = shutil.which("claude")
    if not exe:
        return 127, "o comando `claude` nao esta no PATH desta maquina"
    return instalar_sequencial(exe, PLUGIN, TRAVA_INSTALACAO, executar=executar)


def _main_restaurar(settings: Path, copia):
    'O comando que o vigia do gate indica ao advogado. Mensagens em portugues, uma instrucao'


    try:
        r = restaurar_chaves_ausentes(settings, copia)
    except CopiaAusente:
        print(f"ativar_canal: a cópia {copia} não existe mais (o plugin guarda só as {COPIAS_MANTIDAS} mais "
              "recentes, e as mais antigas saem), e por isso nada foi recolocado. Nada foi alterado. As cópias que "
              f"ainda existem ficam ao lado de {settings}, com o nome {Path(settings).name}{SUFIXO_COPIA}<data>. "
              "Rode o comando de novo com --copia apontando para uma delas, ou sem --copia para usar a mais "
              "recente.", file=sys.stderr)
        return RC_COPIA_AUSENTE
    except SettingsIlegivel:
        print(f"ativar_canal: {settings} não é um JSON válido neste momento. Nada foi alterado. "
              "Corrija o arquivo e rode de novo.", file=sys.stderr)
        return 8
    except SettingsNaoRelido:
        print(f"ativar_canal: {settings} foi gravado, mas outro programa o manteve aberto logo depois, e ele não "
              "pôde ser relido para conferir. Nada foi desfeito. Feche o Claude Code. Depois rode este comando "
              "de novo: ele confere o que ainda falta.", file=sys.stderr)
        return 5
    except SettingsOcupado:
        print(f"ativar_canal: {settings} está em uso ou sendo gravado por outro programa neste momento. "
              "Nada foi alterado. Feche o Claude Code. Depois rode este comando de novo.", file=sys.stderr)
        return 5
    except GravacaoNaoConferida as e:
        if e.restauracao == "integral":


            desfecho = ("Nada foi recolocado: o arquivo voltou a ser exatamente o que era antes deste comando; o "
                        "que o outro programa gravou nesse intervalo se perdeu junto.")
        else:
            desfecho = _desfecho_nao_conferido(e)
        print(f"ativar_canal: outro programa regravou {settings} enquanto as configurações eram recolocadas. "
              f"{desfecho} Feche o Claude Code. Depois rode este comando de novo.", file=sys.stderr)
        return 5
    except ErroSettings:
        print(f"ativar_canal: não foi possível restaurar {settings} agora. Feche o Claude Code. Depois rode "
              "este comando de novo.", file=sys.stderr)
        return 5
    if not r["copia"]:
        print("ativar_canal: não há cópia guardada pelo plugin ao lado deste arquivo; nada a restaurar.")
        return 0
    entradas = ", ".join(r.get("entradas_redigidas") or r.get("redigidas") or ())
    if not r["restauradas"]:
        if r.get("redigidas"):
            print(f"ativar_canal: nada foi recolocado em {settings}. A cópia {r['copia']} guardava estas "
                  f"entradas com a credencial redigida, e elas NÃO voltaram: {entradas}. "
                  "Reponha cada uma pelo programa que a criou. "
                  "A credencial do canal é reemitida na próxima ativação.", file=sys.stderr)
            return RC_SO_REDIGIDAS
        print(f"ativar_canal: nenhuma configuração de topo está faltando em {settings}; nada foi alterado.")
        return 0
    print(f"ativar_canal: recolocadas em {settings}, da cópia {r['copia']}: {', '.join(r['restauradas'])}.")
    if r.get("redigidas"):
        print(f"Atenção: em {', '.join(r['redigidas'])} a cópia guardava credenciais redigidas, e essas "
              f"entradas NÃO voltaram: {entradas}. Reponha cada uma pelo programa que a criou.")
    print("O resto do arquivo ficou como estava.")
    print("A credencial do canal não vem da cópia; ela é reemitida na próxima ativação.")
    return 0


def _desfecho_nao_conferido(e) -> str:
    """O que GravacaoNaoConferida deixou no arquivo, numa frase ao advogado."""
    if e.restauracao == "integral":

        return ("O arquivo voltou a ser exatamente o que era antes desta gravação; o que o outro programa "
                "gravou nesse intervalo se perdeu junto.")
    if e.restauracao == "recusada":
        return ("O sistema de arquivos recusou a restauração, e o arquivo ficou como está: confira as suas "
                "configurações nele.")
    return "Não havia arquivo antes, e nada foi restaurado."


def _avisar_ilegivel(settings) -> int:
    print(f"ativar_canal: {settings} existe mas não é um JSON válido, e por isso não foi substituído "
          "(trocá-lo apagaria as suas configurações). Corrija o arquivo e rode de novo.", file=sys.stderr)
    return 8


def _avisar_ocupado(settings) -> int:
    print(f"ativar_canal: {settings} está em uso por outro programa neste momento, e por isso não foi "
          "trocado. Feche o Claude Code. Depois rode este comando de novo.", file=sys.stderr)
    return 9






PROMESSA_PENDENTE = "Se não rodar, a próxima sessão do Claude Code grava a declaração sozinha."
PROMESSA_NAO_RELIDO = ", e a próxima sessão do Claude Code confere a declaração e a grava de novo, se faltar."
PROMESSA_AUXILIAR = "A próxima sessão do Claude Code tenta a cópia e a declaração de novo, sozinha."
LINHA_DECLARACAO_PENDENTE = (
    "ativar_canal: {settings} está em uso ou sendo gravado por outro programa neste momento, e por isso a "
    "declaração do canal não ficou. Nenhuma configuração sua foi alterada. O token desta máquina já está no "
    "cofre: a licença vale, e só a declaração falta. Feche as outras sessões do Claude Code. Depois rode este "
    "comando de novo. " + PROMESSA_PENDENTE)
LINHA_NAO_RELIDO = (
    "ativar_canal: a declaração do canal foi gravada em {settings}, mas outro programa manteve o arquivo aberto "
    "logo depois, e ele não pôde ser relido para conferir. Nada foi desfeito. O token desta máquina já está no "
    "cofre: a licença vale" + PROMESSA_NAO_RELIDO)
LINHA_AUXILIAR = (
    "ativar_canal: o token desta máquina ficou no cofre, mas não foi possível copiar o comando que o lê para "
    "~/.dissero ({erro}). Nada foi gravado no settings; nao siga. " + PROMESSA_AUXILIAR)
SEM_MARCA_PENDENTE = (
    "A pendência também não pôde ser anotada em {pasta} (a pasta não aceitou a gravação), e por isso nenhuma "
    "sessão do Claude Code grava a declaração sozinha: rode este comando de novo.")
SEM_MARCA_NAO_RELIDO = (
    ". A pendência não pôde ser anotada em {pasta} (a pasta não aceitou a gravação), e por isso nenhuma sessão "
    "do Claude Code confere a declaração sozinha: feche as outras sessões do Claude Code e rode este comando de "
    "novo; ele confere a declaração e a grava, se faltar.")
SEM_MARCA_AUXILIAR = (
    "A pendência também não pôde ser anotada em {pasta} (a pasta não aceitou a gravação), e por isso nenhuma "
    "sessão do Claude Code tenta a cópia sozinha: corrija a permissão de gravação dessa pasta e rode este "
    "comando de novo.")


def linha_sem_promessa(linha: str, promessa: str, sem_marca: str, marcou: bool, pasta) -> str:
    'A linha tal e qual com a marca gravada; sem ela, a promessa da sessao seguinte (falsa sem a'

    if marcou:
        return linha
    return linha.replace(promessa, sem_marca.format(pasta=pasta))


def _settings_impede(settings) -> int:
    '0 se o settings pode ser gravado; senao a saida do erro NOMEADO (8 ilegivel, 9 em uso), ja'


    try:
        ler_settings(Path(settings))
        return 0
    except SettingsIlegivel:
        return _avisar_ilegivel(settings)
    except SettingsOcupado:
        return _avisar_ocupado(settings)


def main(argv=None):
    'Os literais que a skill cita ficam sem acento, como no .ps1 (ASCII puro): as linhas de'


    ap = argparse.ArgumentParser(description="Liga o canal de atualização automática do plugin Dissero nesta máquina.")
    portador = ap.add_mutually_exclusive_group()
    portador.add_argument("--login", action="store_true",
                          help="usa o login do conector dissero (/mcp > dissero > autenticar); o login nunca é impresso")
    portador.add_argument("--token", help=argparse.SUPPRESS)
    ap.add_argument("--maquina", default=nome_da_maquina(), help="nome desta máquina no registro da licença")
    ap.add_argument("--origem", default=ORIGEM)
    ap.add_argument("--settings", default=str(SETTINGS), help=argparse.SUPPRESS)
    ap.add_argument("--credenciais", default=str(CREDENCIAIS), help=argparse.SUPPRESS)
    ap.add_argument("--sem-instalar", action="store_true", help="grava a declaração e não roda o install")
    ap.add_argument("--so-mostrar", action="store_true", help="não escreve nada; diz o que faria")
    ap.add_argument("--restaurar-chaves", action="store_true",
                    help="recoloca no settings as configurações de topo que sumiram, lidas da cópia "
                         "guardada pelo plugin; não toca em mais nada")
    ap.add_argument("--copia", help="a cópia a usar no --restaurar-chaves (padrão: a mais recente)")
    ap.add_argument("--pasta-estado", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    settings = Path(a.settings)
    if a.restaurar_chaves:
        return _main_restaurar(settings, a.copia)
    if a.so_mostrar:
        print(f"1. tools/call ativar_maquina em {a.origem.rstrip('/')}/mcp  (login do conector dissero -> "
              f"token desta máquina: {a.maquina})")
        print(f"2. guardar o token no cofre do sistema e copiar o comando para ~/.dissero/")
        print(f"3. mesclar extraKnownMarketplaces.{MERCADO} (headersHelper, autoUpdate: true) em {settings}")
        print(f"4. claude plugin install {PLUGIN} --scope user  (com o Claude Code {CLAUDE_CODE_MINIMO} ou superior)")
        return 0

    if a.token:
        token = a.token
        print(f"canal: token informado ({marca(token)}); o /mcp nao foi chamado")
    elif a.login:
        situacao, tok_login = ler_login(Path(a.credenciais), a.origem)
        if situacao == "ausente":
            print("ativar_canal: não há login do conector dissero neste computador. Digite /mcp, escolha dissero "
                  "e autentique com o e-mail liberado pela banca. Depois rode este comando de novo.", file=sys.stderr)
            return RC_SEM_LOGIN
        if situacao == "expirado":
            print("ativar_canal: o login do conector dissero neste computador expirou. Digite /mcp, escolha "
                  "dissero e clique em Reconectar. Depois rode este comando de novo.", file=sys.stderr)
            return RC_SEM_LOGIN


        rc_settings = _settings_impede(settings)
        if rc_settings:
            return rc_settings
        try:
            meta = ativar_por_login_http(a.origem, tok_login, a.maquina)
        except PermissionError:
            print("ativar_canal: o canal não aceitou o login do conector dissero (HTTP 401). Digite /mcp, "
                  "escolha dissero e clique em Reconectar. Depois rode este comando de novo.", file=sys.stderr)
            return RC_SEM_LOGIN
        except RuntimeError as e:
            print(f"ativar_canal: o canal recusou a ativacao: {e}", file=sys.stderr)
            return 3
        except CanalNaoConcluiu as e:
            print(f"ativar_canal: o canal respondeu, mas nao concluiu a ativacao ({e}). A falha e do lado do "
                  "servidor, e nao da internet: rode este comando de novo mais tarde; se repetir, fale com a "
                  "Dissero.", file=sys.stderr)
            return 4
        except Exception as e:
            print(f"ativar_canal: nao foi possivel falar com o canal ({e}).", file=sys.stderr)
            return 4
        token = str(meta.get("token") or "")
        if not token:
            print("ativar_canal: resposta do canal sem token.", file=sys.stderr)
            return 4
        m = meta.get("maquinas") or {}
        print(f"canal: login aceito para o tenant {meta.get('tenant')} "
              f"({m.get('usadas', '?')}/{m.get('permitidas', '?')} maquina(s)); token {marca(token)}")
    else:
        print("ativar_canal: informe --login. A licença vem do login do conector dissero (/mcp > dissero > "
              "autenticar); não há ativação por chave digitada.", file=sys.stderr)
        return 2



    try:
        onde = COFRE.gravar(token)
    except (COFRE.CofreIndisponivel, OSError) as e:
        print(f"ativar_canal: o cofre do sistema nao aceitou o token desta maquina ({e}). Nada foi "
              "gravado no settings; nao siga.", file=sys.stderr)
        return RC_COFRE



    pasta_estado = Path(a.pasta_estado) if a.pasta_estado else PASTA_ESTADO
    marcou = marcar_pendente(pasta_estado, settings, "ativar_canal")

    cache_fora = apagar_cache_licenca(pasta_estado)
    print(f"cofre: token {marca(token)} guardado no {ROTULO_COFRE.get(onde, onde)}")
    if not cache_fora:
        print(LINHA_CACHE_NAO_APAGADO.format(arquivo=pasta_estado / CACHE_LICENCA), file=sys.stderr)
    try:
        COFRE.instalar_auxiliares()
    except (COFRE.CofreIndisponivel, OSError) as e:
        print(linha_sem_promessa(LINHA_AUXILIAR.format(erro=e), PROMESSA_AUXILIAR, SEM_MARCA_AUXILIAR, marcou,
                                 pasta_estado), file=sys.stderr)
        return RC_COFRE
    try:
        r = gravar_declaracao(settings, bloco_marketplace(a.origem))
    except SettingsIlegivel:
        return _avisar_ilegivel(settings)
    except SettingsNaoRelido:
        print(linha_sem_promessa(LINHA_NAO_RELIDO.format(settings=settings), PROMESSA_NAO_RELIDO,
                                 SEM_MARCA_NAO_RELIDO, marcou, pasta_estado), file=sys.stderr)
        return 9
    except SettingsOcupado:

        print(linha_sem_promessa(LINHA_DECLARACAO_PENDENTE.format(settings=settings), PROMESSA_PENDENTE,
                                 SEM_MARCA_PENDENTE, marcou, pasta_estado), file=sys.stderr)
        return 9
    except GravacaoNaoConferida as e:
        print(f"ativar_canal: a gravação de {settings} não conferiu na releitura "
              f"(faltam: {', '.join(e.chaves)}). {_desfecho_nao_conferido(e)} Por isso, nao siga.",
              file=sys.stderr)
        return 5

    if r.get("copia"):
        print(f"settings: copia do arquivo anterior em {r['copia']}")
    print(f"settings: declaracao {MERCADO} gravada em {settings} (headersHelper, autoUpdate: true; sem token)")


    registro = registro_de(settings)
    reg = reconciliar_registro(bloco_marketplace(a.origem)["source"], registro, trava=TRAVA_INSTALACAO)
    if reg == "reconciliado":
        print(f"registro: a loja {MERCADO} do Claude Code passou a usar o headersHelper (o token saiu de {registro})")
    elif reg in ("ocupado", "falhou"):
        print(f"registro: a loja {MERCADO} do Claude Code nao foi posta em dia agora ({reg}); o gate de "
              "licenca tenta de novo na proxima sessao.", file=sys.stderr)

    if a.sem_instalar:
        print("instalacao pulada (--sem-instalar).")
        return 0
    rc, saida = instalar()
    if rc == RC_TRAVA_OCUPADA:


        print("plugin: outra instalacao do plugin Dissero ja esta em andamento neste computador; ela conclui "
              "sozinha e a copia entra em vigor na proxima sessao.")
        return 0
    if rc == RC_CLAUDE_ANTIGO:
        print(f"ativar_canal: {saida} A declaracao ja ficou gravada; so a instalacao falta.", file=sys.stderr)
        return RC_CLAUDE_ANTIGO
    if rc != 0:
        print(f"ativar_canal: `claude plugin install` falhou ({rc}): {saida.strip()[-300:]}", file=sys.stderr)
        return 6
    print(f"plugin: {PLUGIN} instalado no escopo de usuario. A partir da proxima sessao, a "
          "atualizacao e automatica.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
