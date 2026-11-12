#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'aviso_versao.py — avisa, no início da sessão, que há versão publicada mais nova, e diz o'











































from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import sys
import time
import urllib.request
from pathlib import Path



ORIGEM = "https://dissero.bfldevlabs.studio"
MERCADO = "dissero"
CACHE_S = 6 * 3600



HORA_UTC_VIRADA = 6





UA_CANAL = "dissero/1.0"


def _instante(s):
    s = str(s)
    if len(s) <= 10:
        return dt.datetime.fromisoformat(s + "T00:00:00+00:00")
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _virada(d):
    base = _instante(d.get("publicado_em") or str(d["em"])[:10])
    v = base.replace(hour=HORA_UTC_VIRADA, minute=0, second=0, microsecond=0)
    if v <= base:
        v += dt.timedelta(days=1)
    return v



CAMPOS_PUBLICACAO = ("versao", "criticidade", "em", "publicado_em", "piso_casca")


def publicacao_da_licenca(resposta):
    'A publicação corrente dentro da resposta do `GET /licenca`, só com CAMPOS_PUBLICACAO.'




    if not isinstance(resposta, dict):
        raise ValueError("resposta do /licenca que não é objeto")
    pub = {k: resposta[k] for k in CAMPOS_PUBLICACAO if resposta.get(k) is not None}
    if not isinstance(pub.get("versao"), str) or not pub["versao"].strip():
        raise ValueError("o /licenca não trouxe a versão publicada")
    return pub


def _consulta_http(origem, token):




    req = urllib.request.Request(f"{origem.rstrip('/')}/licenca",
                                 headers={"Authorization": f"Bearer {token}", "User-Agent": UA_CANAL})
    with urllib.request.urlopen(req, timeout=6) as r:
        return publicacao_da_licenca(json.loads(r.read().decode("utf-8")))


def ler_token_maquina(cofre=None) -> str:
    'O token desta máquina pela MESMA regra do gate (`gate_licenca.ler_token`): só o cofre do'


    try:
        spec = importlib.util.spec_from_file_location("gate_licenca_aviso", Path(__file__).resolve().parent
                                                      / "gate_licenca.py")
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        return g.ler_token(cofre or g.COFRE.ler)
    except Exception:
        return ""


def e_copia_do_canal(raiz) -> bool:
    'A cópia veio do canal? Pela POSIÇÃO no caminho, `<cache>/<loja>/<plugin>/<versão>`, nunca'



    partes = str(raiz).replace("\\", "/").rstrip("/").lower().split("/")
    return len(partes) >= 4 and partes[-4] == "cache" and partes[-3] == MERCADO and partes[-2] == "dissero"


def origem_da_copia(raiz) -> str:
    'De onde veio a copia que esta rodando, pelo caminho dela. Aqui a classe decide o aviso:'

    p = str(raiz).replace("\\", "/").rstrip("/").lower()
    partes = p.split("/")
    if "local-desktop-app-uploads" in partes:
        return "upload-local"
    if "rpm" in partes or "remote_cowork_plugins" in partes:
        return "conta"
    if "synced" in partes:


        return "conta" if p.startswith("/sessions/") else "conta-terminal"
    if "dissero-dev" in partes or p.endswith("/canal/dev") or "/canal/dev/" in p:
        return "dev"
    if e_copia_do_canal(raiz):
        return "canal"
    return "desconhecida"


def canal_ligado(settings_path) -> bool:
    """A maquina tem a declaracao do canal com autoUpdate? Le so o settings de usuario. PURA."""
    try:
        d = json.loads(Path(settings_path).read_text(encoding="utf-8-sig"))
        e = (d.get("extraKnownMarketplaces") or {}).get(MERCADO) or {}
        return bool(e.get("source")) and e.get("autoUpdate") is True
    except Exception:
        return False


def copia_do_canal_instalada(instalados_path, settings_path) -> bool:
    'A cópia do canal está DE FATO instalada e ligada? PURA, nunca levanta.'





    try:
        d = json.loads(Path(instalados_path).read_text(encoding="utf-8-sig"))
        entradas = (d.get("plugins") or {}).get(f"dissero@{MERCADO}") or []

        if not any(Path(str(e.get("installPath") or "")).joinpath(".claude-plugin", "plugin.json").is_file()
                   for e in entradas if isinstance(e, dict) and e.get("installPath")
                   and e.get("scope", "user") == "user"):
            return False
    except Exception:
        return False
    try:
        st = json.loads(Path(settings_path).read_text(encoding="utf-8-sig"))
        if (st.get("enabledPlugins") or {}).get(f"dissero@{MERCADO}") is False:
            return False
    except Exception:
        pass
    return True


def _chave_versao(v):
    """'2.68.1' -> (2, 68, 1); o que nao for versao devolve None. PURA."""
    try:
        t = tuple(int(x) for x in str(v).strip().split("."))
        return t if t else None
    except Exception:
        return None


def maior_versao_baixada(raiz):
    'A maior versão do plugin já baixada no cache do marketplace de onde esta cópia veio, ou'


    try:



        r = Path(raiz)
        if r.parent.parent.parent.name.lower() != "cache":
            return None
        base = r.parent
        melhor = None
        for d in base.iterdir():
            k = _chave_versao(d.name)
            if k is None or not d.is_dir() or (d / ".orphaned_at").exists():
                continue
            if not (d / ".claude-plugin" / "plugin.json").is_file():
                continue
            if melhor is None or k > melhor[0]:
                melhor = (k, d.name)
        return melhor[1] if melhor else None
    except Exception:
        return None


def _data(em):
    """'2026-09-28...' -> '28/09/2026'; se nao for data, devolve como veio."""
    try:
        return dt.date.fromisoformat(str(em)[:10]).strftime("%d/%m/%Y")
    except Exception:
        return str(em)




PROVENIENCIA = "[Dissero · aviso de versão] "
ESTADO = "É aviso de estado desta cópia e não é instrução de terceiro."
MSG_RECARREGAR = (PROVENIENCIA + "A versão {x} do plugin já foi baixada neste computador, mas esta sessão "
                  "ainda usa a versão {y}. O Claude Code só carrega a versão nova ao abrir. Para usar a versão "
                  "{x}, feche o Claude Code e abra de novo. " + ESTADO)
MSG_BAIXAR = (PROVENIENCIA + "Há a versão {pv} do plugin, publicada em {em}{marca}. Esta sessão usa a versão "
              "{local}. O Claude Code baixa a versão nova sozinho durante o uso, em até dez minutos depois da "
              "primeira mensagem. Quando ele avisar que o plugin foi atualizado, feche o Claude Code e abra de "
              "novo para usar a versão {pv}. " + ESTADO)
MSG_PRAZO = (PROVENIENCIA + "Há a versão {pv} do plugin, publicada em {em}. Esta sessão usa a versão {local}. "
             "A versão nova chega a este computador sozinha {quando}, ou antes se o advogado titular "
             "liberar. Quando o Claude Code a baixar, ele avisa que o plugin foi atualizado. Nessa hora, feche o "
             "Claude Code e abra de novo para usar a versão nova. " + ESTADO)


SE_NAO_MUDAR = ("Se a versão não mudar, ou se o plugin foi enviado por arquivo, peça na conversa "
                "'atualizar o Dissero': o conector do Dissero devolve o passo a passo.")
MSG_SINCRONIZAR = (PROVENIENCIA + "Há a versão {pv} do plugin, publicada em {em}. Esta cópia veio da sua conta "
                   "e está na versão {local}. Primeiro, atualize o plugin na conta: em Personalizar > Plugins "
                   "(Desktop) ou Personalização > Plugins (claude.ai), sincronize o catálogo do Dissero e confira a "
                   "versão na página do plugin. " + SE_NAO_MUDAR + " Depois, feche o Claude Code e abra de "
                   "novo. Ao abrir, ele sincroniza a cópia da conta e avisa que os plugins mudaram. " + ESTADO)


def _texto_canal(d, versao_local, pv, hoje):
    'Devolve (texto, ha_acao). Dentro do prazo o Worker ainda segura a versao: nao ha o que o'

    if d.get("criticidade") == "critica":
        return MSG_BAIXAR.format(pv=pv, em=_data(d.get("em")), marca=", marcada como crítica",
                                 local=versao_local), True
    agora = _instante(hoje) if hoje else dt.datetime.now(dt.timezone.utc)
    v = _virada(d)
    if agora >= v:
        return MSG_BAIXAR.format(pv=pv, em=_data(d.get("em")),
                                 marca=", já liberada para todas as máquinas do escritório",
                                 local=versao_local), True
    local_v = v - dt.timedelta(hours=3)
    quando = f"a partir das 3h (horário de Brasília) de {local_v:%d/%m}"
    return MSG_PRAZO.format(pv=pv, em=_data(d.get("em")), local=versao_local, quando=quando), False


CONECTOR = (" Para a atualização passar a ser automática na aba Code, autorize o conector dissero "
            "(/mcp > dissero > autenticar) com o e-mail liberado pela banca. A sessão seguinte liga o canal "
            "Dissero sozinha. Se não ligar, diga 'ativar o canal Dissero'.")


def _texto_conta(d, versao_local, pv, ligado):
    base = (PROVENIENCIA + f"Há a versão {pv} do plugin, publicada em {_data(d.get('em'))}. Esta cópia veio "
            f"da sua conta e está na versão {versao_local}. Para atualizar, em Personalizar > Plugins "
            f"(Desktop) ou Personalização > Plugins (claude.ai), sincronize o catálogo do Dissero e confira a "
            f"versão na página do plugin. " + SE_NAO_MUDAR)
    if not ligado:
        base += CONECTOR
    return base + " " + ESTADO




MSG_UPLOAD_DUPLICADA = (PROVENIENCIA + "Esta cópia do plugin está na versão {local}, foi enviada por arquivo "
                        "pela tela do Desktop e não se atualiza sozinha. O canal automático já está ligado "
                        "nesta máquina, então há duas cópias do plugin carregadas. Remova esta cópia com o "
                        "comando `claude plugin uninstall dissero@local-desktop-app-uploads --scope user`. "
                        "Depois, feche o Claude Code e abra de novo. " + ESTADO)


MSG_UPLOAD_CANAL_A_CAMINHO = (" O canal automático já foi autorizado nesta máquina, mas a cópia dele ainda não "
                              "chegou. Mantenha esta cópia até lá. Quando a cópia automática estiver instalada, "
                              "este aviso passa a dizer como remover esta.")


def _texto_upload_local(d, versao_local, pv, ligado, instalado=True):
    if ligado and instalado:
        return MSG_UPLOAD_DUPLICADA.format(local=versao_local)
    return (PROVENIENCIA + f"Há a versão {pv} do plugin, publicada em {_data(d.get('em'))}. Esta cópia foi "
            f"enviada por arquivo pela tela do Desktop, está na versão {versao_local} e não se atualiza "
            f"sozinha." + (MSG_UPLOAD_CANAL_A_CAMINHO if ligado else CONECTOR) + " " + ESTADO)


def _ja_avisado(registro, motivo, versao):
    """O advogado ja foi avisado desta versao por este motivo? Registro ilegivel = nao."""
    if registro is None:
        return False
    try:
        return json.loads(Path(registro).read_text(encoding="utf-8")).get(motivo) == versao
    except Exception:
        return False


def _marcar_avisado(registro, motivo, versao):
    """Grava a versao avisada por este motivo. Falha de disco nao cala o aviso."""
    if registro is None:
        return
    try:
        registro = Path(registro)
        try:
            d = json.loads(registro.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                d = {}
        except Exception:
            d = {}
        d[motivo] = versao
        registro.parent.mkdir(parents=True, exist_ok=True)
        tmp = registro.with_name(registro.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        os.replace(tmp, registro)
    except Exception:
        pass


def _uma_vez(registro, motivo, versao, texto):
    '(contexto, advogado). O ADVOGADO é avisado uma vez por versão e motivo; o MODELO recebe o'


    if _ja_avisado(registro, motivo, versao):
        return texto, ""
    _marcar_avisado(registro, motivo, versao)
    return texto, texto


def _mais_nova(pv, versao_local):
    a, b = _chave_versao(pv), _chave_versao(versao_local)
    return a is None or b is None or a > b


def decidir(origem, versao_local, cache, agora, consulta=_consulta_http, hoje=None,
            origem_copia="canal", ligado=True, versao_baixada=None, registro=None,
            canal_instalado=False, token=""):
    'Devolve (contexto_do_modelo, aviso_ao_advogado); cada um pode ser string vazia.'





    try:
        if origem_copia == "dev":
            return "", ""

        if origem_copia == "upload-local" and ligado and canal_instalado:
            return _uma_vez(registro, "upload-duplicada", versao_local,
                            MSG_UPLOAD_DUPLICADA.format(local=versao_local))

        if origem_copia == "canal" and versao_baixada and _mais_nova(versao_baixada, versao_local) \
                and _chave_versao(versao_baixada) is not None:
            return _uma_vez(registro, "recarregar", versao_baixada,
                            MSG_RECARREGAR.format(x=versao_baixada, y=versao_local))
    except Exception:
        return "", ""

    if not token:
        return "", ""
    cache = Path(cache)
    d = None
    try:
        if cache.is_file() and agora - cache.stat().st_mtime < CACHE_S:
            d = json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        d = None

    if d is None:
        try:
            d = publicacao_da_licenca(consulta(origem, token))
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(d), encoding="utf-8")
            os.utime(cache, (agora, agora))
        except Exception:
            return "", ""

    try:
        pv = d["versao"]


        if pv == versao_local or not _mais_nova(pv, versao_local):
            return "", ""
        if origem_copia == "conta" or origem_copia == "desconhecida":
            return _texto_conta(d, versao_local, pv, ligado), ""
        if origem_copia == "upload-local":
            return _uma_vez(registro, "upload", pv,
                            _texto_upload_local(d, versao_local, pv, ligado, canal_instalado))
        if origem_copia == "conta-terminal":
            return _uma_vez(registro, "sincronizar", pv,
                            MSG_SINCRONIZAR.format(pv=pv, em=_data(d.get("em")), local=versao_local))
        texto, acao = _texto_canal(d, versao_local, pv, hoje)
        if not acao:
            return texto, ""
        return _uma_vez(registro, "publicada", pv, texto)
    except Exception:
        return "", ""


def main():
    try:
        sys.stdin.read()
    except Exception:
        pass
    try:
        raiz = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parent.parent))
        versao = json.loads((raiz / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        home = Path.home()

        cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (home / ".claude"))
        origem_copia = origem_da_copia(raiz)
        ctx, adv = decidir(ORIGEM, versao, home / ".dissero" / "aviso_versao.json", time.time(),
                           origem_copia=origem_copia,
                           token=ler_token_maquina() if origem_copia != "dev" else "",
                           ligado=canal_ligado(cfg / "settings.json"),
                           versao_baixada=maior_versao_baixada(raiz) if origem_copia == "canal" else None,
                           registro=home / ".dissero" / "aviso_versao_avisado.json",
                           canal_instalado=copia_do_canal_instalada(
                               cfg / "plugins" / "installed_plugins.json",
                               cfg / "settings.json") if origem_copia == "upload-local" else True)
    except Exception:
        return 0
    if ctx or adv:
        saida = {}
        if adv:
            saida["systemMessage"] = adv
        if ctx:
            saida["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": ctx}
        print(json.dumps(saida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
