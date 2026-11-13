#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'gate_entrega.py — hook PreToolUse: GATE DE ENTREGA da peça.'
















































import sys, os, json, re, tempfile, hashlib, glob, base64, zipfile
import html

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(AQUI)
ESTADO_PECA = os.path.join(_ROOT, "skills", "dissero-peticao", "scripts", "estado_peca.py")




_CMD_ENTREGAR = (f'{"python" if os.name == "nt" else "python3"} "{ESTADO_PECA}" entregar '
                 f'--state "<PECA_STATE.json do caso>" '
                 f'--destino "<pasta de destino>"')





_SITUACAO_ESCOLHA = '`escolha_do_metodo.py situacao --pasta "<pasta da peça>"`'
_OFERTA_PENDENCIAS = ("Se a peça não liberar, a minuta com as pendências marcadas segue a escolha "
                      f"que o advogado gravou no começo ({_SITUACAO_ESCOLHA} a mostra): na minuta "
                      "rápida, gere e entregue a minuta pelo comando da referência da minuta com "
                      "pendências; no método completo, faça ou tente (e registre) a etapa que o "
                      "gerador apontar como faltante, e gere de novo. Sem escolha gravada, em peça "
                      "com tese jurídica, pergunte a ele com o texto fixo antes.")
_MSG_OFICIAL = ("Não copie a peça à mão (`cp`, `Copy-Item` ou outro comando). Entregue pelo "
                "comando oficial, com o caminho literal do PECA_STATE.json do caso e da pasta de "
                f"destino: `{_CMD_ENTREGAR}`. Ele confere a peça aprovada e faz a cópia. "
                f"{_OFERTA_PENDENCIAS}")

PECA_STATE_NAME = "PECA_STATE.json"



MARCADORES_CASO = (PECA_STATE_NAME, "PROVENIENCIA.jsonl", "SQUAD_STATE.json",
                   "AUTORIZACAO_SUBAGENTES.json", "AUTORIZACAO_INGESTAO.json",
                   "AUTORIZACAO_CNPJA.json", "JUNTADA_TRACKER.json", "CONFERENCIA.json")



sys.path.insert(0, AQUI)
try:
    import caso_raiz as _caso_raiz
except Exception:
    _caso_raiz = None


_WINDOWS = os.name == "nt"
_GIT_BASH = re.compile(r'^/([A-Za-z])(?=/|$)')


def _caminho_local(p):
    'No Windows, `/d/pasta` vira `D:/pasta` e `/tmp/x` vira a pasta temporária do usuário'







    if not _WINDOWS and not _POSIX and isinstance(p, str):
        return p.replace("\\", "/")
    if not (_WINDOWS and _POSIX and isinstance(p, str)):
        return p
    if p == "/tmp" or p.startswith("/tmp/"):
        try:
            return os.path.join(tempfile.gettempdir(), *[x for x in p[5:].split("/") if x])
        except Exception:
            return p
    m = _GIT_BASH.match(p)
    if not m:
        return p
    return m.group(1).upper() + ":\\" + p[3:].replace("/", "\\")










_VERBOS_MECANISMO = (
    "cp", "copy", "copy-item", "cpi", "copyfile", "copyfileobj", "copy2", "copytree",
    "copyfilesync", "move", "mv", "move-item", "mi", "rename", "rename-item", "ren", "rni", "replace",
    "robocopy", "xcopy", "ditto", "rsync", "scp", "sftp", "dd", "tee", "install", "ln", "link",
    "mklink", "symlink", "out-file", "set-content", "sc", "add-content", "ac", "writeallbytes",
    "writealltext", "writefile", "writefilesync", "write_bytes", "write_text", "drive_upload",
    "rclone", "gdrive", "curl", "wget", "invoke-webrequest", "iwr", "invoke-restmethod", "irm",
    "start-bitstransfer", "uploadfile", "uploaddata", "uploadfileasync", "uploaddataasync")
_MECANISMO = re.compile(r'\b(' + "|".join(re.escape(v) for v in _VERBOS_MECANISMO) + r')\b', re.I)




_METODO_ARQUIVO = re.compile(r'(?:\.|::)\s*(?:(?i:copyto|moveto|replace|encrypt|decrypt)|'
                             r'Open[A-Z]\w*|Create\w*|AppendText)\s*\(')



_UPLOAD = re.compile(r'\b(drive_upload|rclone|gdrive|curl|wget|scp|sftp|'
                     r'invoke-webrequest|iwr|invoke-restmethod|irm|uploadfile|uploaddata|'
                     r'uploadfileasync|uploaddataasync)\b', re.I)


def _tem_mecanismo(sub):
    'O trecho tem verbo de cópia, movimento, escrita ou envio? Pela regex no texto (código'

    if _MECANISMO.search(sub or "") or _METODO_ARQUIVO.search(sub or ""):
        return True
    return any(_palavra(t) in _VERBOS_MECANISMO for t in _tokens(sub))


_LINK = re.compile(r'\b(ln|link|mklink|symlink)\b', re.I)



_SEP = re.compile(r'[\n;]|&&|\|\|')


def _quebra_em(cmd, i):
    """Tamanho da nova linha em `cmd[i]` (`\\n` ou `\\r\\n`), ou 0."""
    if cmd.startswith("\r\n", i):
        return 2
    return 1 if cmd.startswith("\n", i) else 0







_INTERP_HEREDOC = re.compile(r'^(?:python(?:\d+(?:\.\d+)?)?w?|py|node|nodejs|perl|ruby|php)$')
_HEREDOC_ABRE = re.compile(r'<<(-?)[ \t]*(?:\'([^\'\n]*)\'|"([^"\n]*)"|([^\s;&|<>()\'"]+))')


def _dono_heredoc(trecho):
    """Nome do programa que recebe o heredoc do trecho (sem atribuições nem prefixos), ou ''."""
    for t in trecho.split():
        if re.match(r'^[A-Za-z_]\w*=', t) or t.lower() in ("env", "command", "exec", "nohup", "time",
                                                          "sudo", "nice", "stdbuf"):
            continue
        return _palavra(t)
    return ""












_INICIALIZACAO_SHELL = re.compile(
    r'(?:^|[\\/])(?:\.(?:bashrc|bash_profile|bash_login|bash_logout|bash_aliases|profile|zshrc|zshenv|'
    r'zprofile|zlogin|zlogout|kshrc|mkshrc|cshrc|tcshrc|login|inputrc|envrc|pythonrc[^\\/]*)|'
    r'bash\.bashrc|profile|environment|config\.fish|[^\\/]+\.pth|sitecustomize\.py|usercustomize\.py)$|'
    r'(?:^|[\\/])\.ssh[\\/]rc$|'
    r'(?:^|[\\/])(?:profile\.d|fish[\\/]conf\.d|rc\.d|environment\.d)[\\/]', re.I)


def _heredoc_de_dado(dono, trecho, pendentes):
    """O heredoc do trecho é dado gravado por `cat`/`tee` (ver acima)?"""
    if dono not in ("cat", "tee") or not pendentes or not all(p[2] for p in pendentes):
        return False
    try:
        if len(_segmentos_pipe(trecho)) != 1:
            return False
        destinos = list(_alvos_redirecao(trecho))
        if dono == "tee":
            j, _t, _m = _programa(trecho)
            destinos += [x for x in _sem_redirecao(_tokens(trecho))[(j or 0) + 1:]
                         if not x.startswith("-") and not x.startswith("<<")]
    except Exception:
        return False
    for d in destinos:
        bruto = d if isinstance(d, str) else str(d)
        limpo = _desaspar(bruto)
        if (not limpo or re.search(r'[$`*?\[\]{}~]', bruto) or _INICIALIZACAO_SHELL.search(limpo)):
            return False
    return True


def _dividir(cmd, tipo=None, descartes=None, anomalias=None, heredocs=None):
    '[(trecho, separador que o encerra)] do comando, separado por nova linha, `;`, `&&`, `||` e'














    tipo = tipo or _TIPO
    partes, atual, aspa, i, n = [], [], None, 0, len(cmd)
    pendentes = []
    while i < n:
        c = cmd[i]
        if not aspa and tipo == "posix" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            m = _HEREDOC_ABRE.match(cmd, i)
            if m:
                pendentes.append((m.group(2) if m.group(2) is not None else
                                  m.group(3) if m.group(3) is not None else m.group(4), bool(m.group(1)),
                                  m.group(4) is None))
                atual.append(cmd[i:m.end()])
                i = m.end()
                continue
        if not aspa and pendentes and _quebra_em(cmd, i):
            dono = _dono_heredoc("".join(atual))
            codigo = bool(_INTERP_HEREDOC.match(dono))
            if codigo or _heredoc_de_dado(dono, "".join(atual), pendentes):
                j = i + _quebra_em(cmd, i)
                for delim, tira_tab, _citado in pendentes:
                    corpo = []
                    while j < n:
                        fim = cmd.find("\n", j)
                        fim = n if fim < 0 else fim
                        linha = cmd[j:fim].rstrip("\r")
                        j = fim + 1
                        if (linha.lstrip("\t") if tira_tab else linha) == delim:
                            break
                        corpo.append(linha)
                    if codigo and heredocs is not None:
                        heredocs.append((dono, "\n".join(corpo)))
                partes.append(("".join(atual), "\n"))
                atual, pendentes = [], []
                i = min(j, n)
                continue
            pendentes = []
        if aspa:
            if c == aspa:
                aspa = None
            elif tipo == "posix" and aspa == '"' and c == "\\":
                if _quebra_em(cmd, i + 1):
                    i += 1 + _quebra_em(cmd, i + 1)
                    continue
                if cmd[i + 1:i + 2] in ("\"", "\\", "$", "`"):
                    atual.append(cmd[i:i + 2])
                    i += 2
                    continue
            elif tipo == "ps" and aspa == '"' and c == "`" and i + 1 < n:
                atual.append(cmd[i:i + 2])
                i += 2
                continue
        elif tipo == "posix" and c == "\\" and _quebra_em(cmd, i + 1):
            i += 1 + _quebra_em(cmd, i + 1)
            continue
        elif tipo == "posix" and c == "\\" and cmd[i + 1:i + 2] in ("\"", "'"):
            if anomalias is not None:
                anomalias.append(cmd[i:i + 2])
            atual.append(cmd[i:i + 2])
            i += 2
            continue
        elif tipo == "ps" and c == "`" and _quebra_em(cmd, i + 1):
            atual.append(" ")
            i += 1 + _quebra_em(cmd, i + 1)
            continue
        elif c in "\"'":
            aspa = c
        elif tipo == "ps" and cmd.startswith("<#", i):
            fim = cmd.find("#>", i + 2)
            fim = n if fim < 0 else fim + 2
            if descartes is not None:
                descartes.append(cmd[i:fim])
            atual.append(" ")
            i = fim
            continue
        elif tipo != "cmd" and c == "#" and (i == 0 or cmd[i - 1].isspace()) and not (


                i >= 2 and cmd[i - 2] == ("`" if tipo == "ps" else "\\")
                and (len(cmd[:i - 1]) - len(cmd[:i - 1].rstrip(cmd[i - 2]))) % 2 == 1):
            fim = cmd.find("\n", i)
            fim = n if fim < 0 else fim
            if descartes is not None:
                descartes.append(cmd[i:fim])
            i = fim
            continue
        elif cmd.startswith(("&&", "||"), i) or c in "\n;" or (
                c == "&" and cmd[i - 1:i] not in (">", "|") and cmd[i + 1:i + 2] not in (">", "&")):
            sep = cmd[i:i + 2] if cmd.startswith(("&&", "||"), i) else c
            partes.append(("".join(atual), sep))
            atual = []
            i += len(sep)
            continue
        atual.append(c)
        i += 1
    if aspa:
        return None
    partes.append(("".join(atual), ""))
    return partes


def _fecho(s):
    """Posição do fecho do `(` ou `{` que abre `s`, fora de aspas, ou -1."""
    abre, fecha = s[0], ")" if s[0] == "(" else "}"
    prof, aspa = 0, None
    for i, c in enumerate(s):
        if aspa:
            if c == aspa:
                aspa = None
        elif c in "\"'":
            aspa = c
        elif c == abre:
            prof += 1
        elif c == fecha:
            prof -= 1
            if prof == 0:
                return i
    return -1


def _sem_agrupamento(s):
    '(trecho sem o `(`/`{` que o abre e o `)`/`}` que o fecha, subshells abertos, fechados).'





    abre = fecha = 0
    while s[:1] in ("(", "{") and s[:1]:
        fim = _fecho(s)
        sub = s[0] == "("
        if fim == len(s) - 1:
            s, abre, fecha = s[1:-1].strip(), abre + sub, fecha + sub
        elif fim < 0:
            s, abre = s[1:].strip(), abre + sub
        else:
            break
    while s[-1:] in (")", "}") and s[-1:] and (
            s.count(s[-1]) > s.count("(" if s[-1] == ")" else "{")):
        fecha += s[-1] == ")"
        s = s[:-1].strip()
    return s, abre, fecha


_SHELLS_POSIX = ("bash", "sh", "zsh", "dash", "ksh", "fish")
_SHELLS_PS = ("pwsh", "powershell")


def _desembrulhar(s):
    "(comando que `bash -c '…'`, `pwsh -Command …` ou `cmd /c …` executa, shell que o lê:"




    toks = _tokens(s)
    if len(toks) < 2:
        return None
    prog = _palavra(toks[0])

    def interno(resto):
        if len(resto) != 1:
            return " ".join(resto) or None
        t = resto[0]

        return _tirar_envelope(t).replace('\\"', '"') if t[:1] == '"' else _tirar_envelope(t)

    def com_tipo(texto, tipo):
        return (texto, tipo) if texto else None

    for k, bruto in enumerate(toks[1:], 1):
        t = bruto.lower()
        if prog in _SHELLS_POSIX:
            if re.match(r'^-[a-z]*c[a-z]*$', t):
                return com_tipo(interno(toks[k + 1:k + 2]), "posix")
            if not t.startswith("-"):
                return None
        elif prog in _SHELLS_PS:
            if t == "-wd" or (len(t) >= 4 and "-workingdirectory".startswith(t)):
                return None
            if len(t) >= 2 and "-command".startswith(t):
                return com_tipo(interno(toks[k + 1:]), "ps")
        elif prog == "cmd":
            if t in ("/c", "/k"):
                return com_tipo(interno(toks[k + 1:]), "cmd")
            if not _OPCAO_CMD.match(bruto):
                return None
        else:
            return None
    return None


def _partes(cmd, nivel=0, tipo=None, descartes=None, anomalias=None, heredocs=None):
    '[(sub-comando, subshells abertos antes dele, subshells fechados depois dele, em segundo'








    tipo = tipo or _TIPO
    pedacos = _dividir(cmd, tipo, descartes, anomalias, heredocs)
    if pedacos is None:
        pedacos = [(p, "") for p in _SEP.split(cmd)]
    out = []
    for p, sep in pedacos:
        s, abre, fecha = _sem_agrupamento(p.strip())
        fundo = sep == "&"
        dentro = _desembrulhar(s) if s and nivel < 3 else None
        filhos = _partes(dentro[0], nivel + 1, dentro[1], descartes, anomalias, heredocs) if dentro else []
        if filhos:
            s0, a0, f0, b0, t0 = filhos[0]
            filhos[0] = (s0, a0 + abre + 1, f0, b0, t0)
            s1, a1, f1, b1, t1 = filhos[-1]
            filhos[-1] = (s1, a1, f1 + fecha + 1, b1, t1)
            out += filhos
        elif s or abre or fecha:
            out.append((s, abre, fecha, fundo, tipo))
    return out


def _subcomandos(cmd):
    """Os sub-comandos de `cmd`, na ordem (ver `_partes`)."""
    return [s for s, _a, _f, _b, _t in _partes(cmd)] if isinstance(cmd, str) else []


def _raizes_tmp():
    'Chaves (caminho real) das pastas de staging: a pasta temporária do usuário e, fora do'

    try:
        base = tempfile.gettempdir()
    except Exception:
        base = None
    if base in _CACHE_TMP:
        return _CACHE_TMP[base]
    raizes = [base] if base else []
    if not _WINDOWS:
        raizes.append("/tmp")
    out = []
    for r in raizes:
        try:
            out.append(_chave_caminho(os.path.realpath(r)).rstrip("\\/"))
        except (OSError, ValueError):
            continue
    _CACHE_TMP[base] = out
    return out


_CACHE_TMP = {}


def _is_tmp(path):
    'True SÓ para staging real: a pasta temporária do usuário (`tempfile.gettempdir()`) e o /tmp'






    if not isinstance(path, str):
        return False
    p = _caminho_local(path.strip().strip('"').strip("'"))
    if not isinstance(p, str) or not p.strip():
        return False
    p = os.path.expanduser(p.strip())
    if _WINDOWS:
        if not re.match(r'^(?:[A-Za-z]:[\\/]|[\\/]{2})', p):
            return False
    elif not os.path.isabs(p):
        return False
    try:
        real = _chave_caminho(os.path.realpath(p))
    except (OSError, ValueError):
        return False
    for r in _raizes_tmp():
        if real == r or real.startswith(r + os.sep):
            return not _caso_abaixo_do_tmp(os.path.realpath(p), r)
    return False


def _caso_abaixo_do_tmp(real, raiz_tmp):
    'True quando o caminho fica na árvore de um caso que mora DENTRO da pasta temporária: uma'





    d = real if os.path.isdir(real) else os.path.dirname(real)
    while True:
        k = _chave_caminho(d).rstrip("\\/")
        if k == raiz_tmp or not k.startswith(raiz_tmp + os.sep):
            break
        if any(os.path.exists(os.path.join(d, m)) for m in MARCADORES_CASO):
            return True
        acima = os.path.dirname(d)
        if acima == d:
            break
        d = acima
    try:
        raizes = _raizes_registradas() or []
    except Exception:
        raizes = []
    alvo = _chave_caminho(real)
    for raiz in raizes:
        try:
            k = _chave_caminho(os.path.realpath(raiz)).rstrip("\\/")
        except (OSError, ValueError):
            continue
        if k != raiz_tmp and k.startswith(raiz_tmp + os.sep) and (alvo == k or alvo.startswith(k + os.sep)):
            return True
    return False







_FORMAS_DOCX = frozenset()
_ARQUIVOS_DOCX = frozenset()






_FLUXO_DADOS = re.compile(r'^(.+?)((?::[^\\/:]*)?:\\?\$data)$', re.I)
_FLUXO_NOMEADO = re.compile(r'^(.+\.docx)\s*:[^\\/:]*$', re.I)


def _sem_fluxo(q):
    'O caminho sem o sufixo de fluxo do NTFS (`::$DATA`, `:nome:$DATA`, e `:nome` depois de'

    if not isinstance(q, str):
        return q
    m = _FLUXO_DADOS.match(q)
    if m and not re.fullmatch(r'[A-Za-z]', m.group(1)):
        q = m.group(1)
    m = _FLUXO_NOMEADO.match(q)
    return m.group(1) if m else q


def _eh_docx(p):
    '.docx? Normaliza aspas e REMOVE ponto/espaço final (o NTFS os descarta ao criar, e'



    if not isinstance(p, str):
        return False
    bruto = p.strip().strip('"').strip("'").rstrip(". ")
    q = _sem_fluxo(bruto).rstrip(". ")
    if q.lower().endswith(".docx"):
        return True
    if _FORMAS_DOCX and any(x in _FORMAS_DOCX or re.split(r'[=@]', x)[-1] in _FORMAS_DOCX
                            for x in (bruto, q)):
        return True
    if _ARQUIVOS_DOCX:
        try:
            a = _caminho_local(q)
            return os.path.isabs(a) and _chave_caminho(os.path.abspath(a)) in _ARQUIVOS_DOCX
        except (OSError, ValueError, TypeError):
            return False
    return False



_ESC_ANSI = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b",
             "f": "\f", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}
_ESC_PS = {"0": "\0", "a": "\a", "b": "\b", "e": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
           "v": "\v"}


def _escape_ansi(s, j):
    "(posição seguinte, caractere) do escape do `$'…'` do bash que começa em `s[j]` (depois da"

    c = s[j:j + 1]
    for letra, base, teto in (("x", 16, 2), ("u", 16, 4), ("U", 16, 8)):
        if c == letra:
            m = re.match(r'[0-9A-Fa-f]{1,%d}' % teto, s[j + 1:])
            if m:
                try:
                    return j + 1 + m.end(), chr(int(m.group(0), base))
                except (ValueError, OverflowError):
                    return j + 1 + m.end(), ""
            return j + 1, "\\" + c
    m = re.match(r'[0-7]{1,3}', s[j:])
    if m:
        return j + m.end(), chr(int(m.group(0), 8) & 0xFF)
    if c == "c" and j + 1 < len(s):
        return j + 2, chr(ord(s[j + 1]) & 0x1F)
    if c in _ESC_ANSI:
        return j + 1, _ESC_ANSI[c]
    return j + 1, "\\" + c


def _palavra_shell(t, tipo=None):
    'A palavra como o shell a entrega ao programa, numa aproximação que basta para o gate'





    tipo = tipo or _TIPO
    s = t or ""
    out, i, n = [], 0, len(s)
    if tipo == "cmd":
        aspa = False
        while i < n:
            c = s[i]
            if c == '"':
                aspa = not aspa
            elif c == "^" and not aspa and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            else:
                out.append(c)
            i += 1
        return "".join(out)
    if tipo == "ps":
        aspa = None
        while i < n:
            c = s[i]
            if aspa == "'":
                if c == "'" and s[i + 1:i + 2] == "'":
                    out.append("'")
                    i += 2
                    continue
                if c == "'":
                    aspa = None
                else:
                    out.append(c)
            elif c == "`" and i + 1 < n:
                out.append(_ESC_PS.get(s[i + 1], s[i + 1]))
                i += 2
                continue
            elif aspa == '"':
                if c == '"' and s[i + 1:i + 2] == '"':
                    out.append('"')
                    i += 2
                    continue
                if c == '"':
                    aspa = None
                else:
                    out.append(c)
            elif c in "'\"":
                aspa = c
            else:
                out.append(c)
            i += 1
        return "".join(out)
    modo = None
    while i < n:
        c = s[i]
        if modo == "'":
            if c == "'":
                modo = None
            else:
                out.append(c)
        elif modo == "$'":
            if c == "\\" and i + 1 < n:
                i, ch = _escape_ansi(s, i + 1)
                out.append(ch)
                continue
            if c == "'":
                modo = None
            else:
                out.append(c)
        elif modo == '"':
            if c == "\\" and s[i + 1:i + 2] in ('"', "\\", "$", "`", "\n"):
                if s[i + 1] != "\n":
                    out.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                modo = None
            else:
                out.append(c)
        elif c == "\\":
            if i + 1 < n and s[i + 1] != "\n":
                out.append(s[i + 1])
            i += 2
            continue
        elif c == "$" and s[i + 1:i + 2] in ("'", '"'):
            modo = "$'" if s[i + 1] == "'" else '"'
            i += 2
            continue
        elif c in "'\"":
            modo = c
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _tokens(cmd):
    'Tokeniza o comando RESPEITANDO AS ASPAS: caminho com ESPAÇO chega inteiro.'












    if not isinstance(cmd, str) or not cmd.strip():
        return []


    cmd = re.sub(r'(\d*>\|?)(?=["\'])', r'\1 ', cmd)
    out, atual, aspa = [], [], None
    for c in cmd:
        if aspa:
            atual.append(c)
            if c == aspa:
                aspa = None
        elif c in "\"'":
            aspa = c
            atual.append(c)
        elif c.isspace():
            if atual:
                out.append("".join(atual))
                atual = []
        else:
            atual.append(c)
    if aspa:
        return cmd.split()
    if atual:
        out.append("".join(atual))
    return [e for t in out for e in _expandir_chaves(t)]


def _tirar_envelope(t):
    """Remove só as aspas que envolvem o token inteiro (o comando de `bash -c "…"`)."""
    s = (t or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1]
    return s.strip('"').strip("'")


def _desaspar(t):
    'O token sem as aspas que delimitam trechos citados, onde quer que estejam'


    s = (t or "").strip()
    if '"' not in s and "'" not in s:
        return s
    out, aspa = [], None
    for c in s:
        if aspa:
            if c == aspa:
                aspa = None
            else:
                out.append(c)
        elif c in "\"'":
            aspa = c
        else:
            out.append(c)
    return "".join(out)






_LIMITE_CHAVES = 64


def _itens_chave(conteudo):
    'Palavras de um grupo `{…}` (lista com vírgula ou sequência `a..b`), ou None quando o bash'

    itens, atual, aspa = [], [], None
    for c in conteudo:
        if aspa:
            if c == aspa:
                aspa = None
        elif c in "\"'":
            aspa = c
        elif c == ",":
            itens.append("".join(atual))
            atual = []
            continue
        atual.append(c)
    itens.append("".join(atual))
    if len(itens) > 1:
        return itens
    m = re.fullmatch(r'(-?\d+)\.\.(-?\d+)(?:\.\.(-?\d+))?', conteudo)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        passo = abs(int(m.group(3) or 1)) or 1
        if abs(b - a) // passo + 1 > _LIMITE_CHAVES:
            return [conteudo] * (_LIMITE_CHAVES + 1)
        return [str(x) for x in range(a, b + (1 if b >= a else -1), passo if b >= a else -passo)]
    m = re.fullmatch(r'([A-Za-z])\.\.([A-Za-z])', conteudo)
    if m:
        a, b = ord(m.group(1)), ord(m.group(2))
        return [chr(x) for x in range(a, b + (1 if b >= a else -1), 1 if b >= a else -1)]
    return None


def _grupo_chaves(s):
    '(início, fim, palavras) do primeiro grupo de chaves que o bash abre em `s`, ou None. O grupo'

    aspa, abre = None, -1
    for i, c in enumerate(s):
        if aspa:
            if c == aspa:
                aspa = None
            continue
        if c in "\"'":
            aspa = c
        elif c == "{":
            abre = -1 if (i > 0 and s[i - 1] in "$@\\") else i
        elif c == "}" and abre >= 0:
            itens = _itens_chave(s[abre + 1:i])
            if itens is not None:
                return abre, i + 1, itens
            abre = -1
    return None


def _expandir_chaves(t):
    """As palavras em que o bash abre o token `t` (ele mesmo, sem grupo de chaves)."""
    pend, out = [t], []
    while pend:
        s = pend.pop(0)
        g = _grupo_chaves(s)
        if g is None:
            out.append(s)
        else:
            ini, fim, itens = g
            pend[0:0] = [s[:ini] + it + s[fim:] for it in itens]
        if len(out) + len(pend) > _LIMITE_CHAVES:
            return [t]
    return out


def _partes_virgula(t):
    'Os itens de uma lista do PowerShell (`"a.docx",b.docx`), separados pela vírgula fora de'

    if "," not in t:
        return [t]
    itens, atual, aspa, prof = [], [], None, 0
    for c in t:
        if aspa:
            if c == aspa:
                aspa = None
        elif c in "\"'":
            aspa = c
        elif c in "({[":
            prof += 1
        elif c in ")}]":
            prof = max(0, prof - 1)
        elif c == "," and prof == 0:
            itens.append("".join(atual))
            atual = []
            continue
        atual.append(c)
    itens.append("".join(atual))
    return [i for i in itens if i.strip()] or [t]







_REDIR_PREFIXO = re.compile(r'^(?:\d*|&|\*)>>?\|?&?')


_REDIR_ENTRADA = re.compile(r'^\d*<(?:<<|<|>)?(?!\()')
_ENTRADA_ARQUIVO = re.compile(r'^\d*<(?![<>(])')


def _sem_redirecao(toks):
    'Descarta tokens de redireção, de saída e de entrada, e o alvo que os segue, colado ou no'



    out, pular = [], False
    for t in toks:
        if pular:
            pular = False
            continue
        m = _REDIR_PREFIXO.match(t) or _REDIR_ENTRADA.match(t)
        if m:
            pular = not t[m.end():]
            continue
        out.append(t)
    return out


def _entradas_redirecionadas(toks):
    """Arquivos lidos por redireção de entrada (`< arquivo`, `0<arquivo`), sem aspas."""
    out = []
    for i, t in enumerate(toks):
        m = _ENTRADA_ARQUIVO.match(t)
        if m:
            alvo = t[m.end():] or (toks[i + 1] if i + 1 < len(toks) else "")
            if alvo:
                out.append(_desaspar(alvo))
    return out


def _docx_tokens(cmd, inteiros=False):
    'Todos os caminhos .docx nomeados no comando, na ordem em que aparecem. Com `inteiros`, só'







    if not isinstance(cmd, str):
        return []
    out = []
    for bruto in _tokens(cmd):
        t = _REDIR_PREFIXO.sub("", bruto)
        t = _ENTRADA_ARQUIVO.sub("", t)


        partes = _partes_virgula(t)
        if len(partes) > 1 and '"' not in t and "'" not in t:
            partes = [t] + partes
        for parte in partes:
            limpo = _desaspar(parte)
            if _eh_docx(limpo):


                out.append(re.split(r'[=@]', limpo)[-1].rstrip(". "))
                continue
            if inteiros:
                continue


            literais = [m.group(2) for m in re.finditer(r'(["\'])([^"\']*?\.docx)\1', parte, flags=re.I)]
            trechos = [re.split(r'[=@]', m)[-1]
                       for m in re.findall(r'["\']?([^\s"\']+\.docx)["\']?', parte, flags=re.I)]
            out += literais + [t for t in trechos if not any(lit.endswith(t) for lit in literais)]
    return out



_PY_PREFIXO = r'(?:[rR][bB]?|[bB][rR]?|[uU])?'

_PATS_DEST = (
    r'\bof=["\']?([^\s"\']+\.docx)',
    r'>\|?&?\s*["\']?([^\s"\'|>&]+\.docx)',
    r'(?:^|\s)(?:-o|--output|--upload-file|-T|--out-file|-FilePath|-Path)[=\s]+["\']?([^\s"\']+\.docx)',


    rf'open\s*\(\s*{_PY_PREFIXO}["\']([^"\']+\.docx)["\']\s*,\s*(?:mode\s*=\s*)?{_PY_PREFIXO}["\'][^"\']*[wax+][^"\']*["\']',
    r'writeall(?:bytes|text)\s*\(\s*["\']([^"\']+\.docx)',

    rf'\.\s*save\s*\(\s*{_PY_PREFIXO}["\']([^"\']+\.docx)["\']',

    rf'\b(?:ZipFile|PyZipFile|TarFile)\s*\(\s*{_PY_PREFIXO}["\']([^"\']+\.docx)["\']\s*,\s*(?:mode\s*=\s*)?{_PY_PREFIXO}["\'][wax]',
)


def _dests_redirecionados(cmd):
    'Alvos .docx de redireção (`>`, `1>`, `>|`), por TOKEN — inclusive citados com espaço.'




    out, toks = [], _tokens(cmd)
    for i, t in enumerate(toks):
        m = _REDIR_PREFIXO.match(t) or re.match(r'^\d*<>', t)
        if not m:
            continue
        alvo = t[m.end():] or (toks[i + 1] if i + 1 < len(toks) else "")
        alvo = _desaspar(alvo)
        if _eh_docx(alvo):
            out.append(alvo.rstrip(". "))
    return out





_REDIR_SAIDA = re.compile(r'^(?:(\d*|&|\*)(>>?\|?)|(\d*)(<>))')
_SAIDAS_NULAS = ("/dev/null", "nul", "$null", "/dev/stdout", "/dev/stderr", "/dev/tty", "con")




_PROG_NAO_DESPEJA = frozenset((
    "ls", "dir", "ll", "vdir", "stat", "file", "du", "wc", "tree", "test", "[", "[[", "realpath",
    "readlink", "basename", "dirname", "pwd", "echo", "printf", "true", "false", ":", "sha1sum",
    "sha224sum", "sha256sum", "sha384sum", "sha512sum", "md5sum", "cksum", "b2sum", "shasum",
    "rm", "del", "erase", "rmdir", "unlink", "remove-item", "ri", "mkdir", "md", "cd", "chdir",
    "pushd", "popd", "set-location", "sl", "push-location", "pop-location", "export", "unset",
    "declare", "local", "readonly", "typeset", "set", "rem", "::", "zipinfo", "find", "get-item",
    "gi", "get-childitem", "gci", "test-path", "resolve-path", "rvpa", "split-path", "join-path",
    "get-filehash", "get-acl", "measure-object", "measure", "get-itemproperty", "gp",
    "get-location", "gl", "get-date", "invoke-item", "ii", "explorer", "open", "xdg-open",
    "winword", "start", "start-process", "saps", "out-null"))



_PROG_SEM_SAIDA = frozenset((
    "cp", "mv", "copy", "move", "copy-item", "cpi", "move-item", "mi", "rename-item", "ren", "rni",
    "rename", "install", "ditto", "rsync", "scp", "sftp", "xcopy", "robocopy", "ln", "link",
    "mklink", "gcp", "gmv", "ginstall", "out-file", "set-content", "sc", "add-content", "ac",
    "drive_upload", "start-bitstransfer"))


_PROG_IDENTIDADE = ("cat", "type", "get-content", "gc")

_GC_PARAMS = {"-raw": 0, "-path": 1, "-literalpath": 1, "-encoding": 1, "-asbytestream": 0,
              "-readcount": 1, "-lp": 1, "-pspath": 1}

_LE_REFERENCIA = ("get-content", "gc", "cat", "type")


def _alvos_redirecao(sub):
    'Alvos da redireção da saída padrão do trecho, sem aspas e de qualquer extensão, sem o'

    out, toks = [], _tokens(sub)
    for i, t in enumerate(toks):
        m = _REDIR_SAIDA.match(t)
        if not m:
            continue
        fd = m.group(1) if m.group(2) else m.group(3)
        if fd not in (("", "1", "&", "*") if m.group(2) else ("1",)):
            continue
        resto = t[m.end():]
        if m.group(2) and resto.startswith("&"):

            alvo = _desaspar(resto[1:] or (toks[i + 1] if i + 1 < len(toks) else "")).strip()
            if re.fullmatch(r'\d+-?|-', alvo):
                continue
        else:
            alvo = _desaspar(resto or (toks[i + 1] if i + 1 < len(toks) else "")).strip()
        if alvo and not alvo.startswith("&") and alvo.lower() not in _SAIDAS_NULAS:
            out.append(alvo)


    fds = {}
    for i, t in enumerate(toks):
        m = re.match(r'^(\d*|&)(>>?\|?)(&?)(.*)$', t)
        if not m or t[:1] in "\"'":
            continue
        fd, dup, resto = m.group(1), m.group(3), m.group(4)
        alvo = _desaspar(resto or (toks[i + 1] if i + 1 < len(toks) else "")).strip()
        alvos = ("1", "2") if fd == "&" else (fd or "1",)
        if dup and re.fullmatch(r'\d+', alvo):
            for f in alvos:
                fds[f] = fds.get(alvo)
        elif dup and alvo == "-":
            for f in alvos:
                fds[f] = None
        elif alvo:
            for f in alvos:
                fds[f] = None if alvo.lower() in _SAIDAS_NULAS else alvo
    if fds.get("1") and fds["1"] not in out:
        out.append(fds["1"])
    return out


def _nao_despeja(p, resto):
    'O programa `p`, com os argumentos `resto` (sem aspas), nunca despeja o conteúdo do arquivo na'


    if p in _PROG_NAO_DESPEJA or p in _PROG_SEM_SAIDA:
        return True
    baixo = [x.lower() for x in resto]
    if p == "certutil":
        return "-hashfile" in baixo
    if p in ("unzip", "zipinfo"):
        opcoes = "".join(x[1:] for x in resto if re.fullmatch(r'-[A-Za-z]+', x or ""))
        return bool(set(opcoes) & set("lvtzZ")) and not set(opcoes) & set("pc")
    if p == "tar":
        letras = "".join(x.lstrip("-") for x in resto[:1] if re.fullmatch(r'-?[A-Za-z]+', x or ""))
        letras += "".join(x[1:] for x in resto[1:] if re.fullmatch(r'-[A-Za-z]+', x or ""))
        return ("t" in letras or "--list" in baixo) and not set(letras) & set("cruAxO")
    if p in ("7z", "7za"):
        pos = [x for x in baixo if x and not x.startswith("-")]
        return bool(pos) and pos[0] in ("l", "t", "h", "i")
    return False


def _identidade(p, resto, tipo=None):
    'O programa despeja o arquivo como está (`cat x`, `type x`, `Get-Content x -Raw`, e o `tee`, que'

    if p == "tee":
        return True
    if p not in _PROG_IDENTIDADE:
        return False
    if p in ("cat", "type") and (tipo or _TIPO) != "ps":
        return not any(x.startswith("-") and x != "-" for x in resto)
    k = 0
    while k < len(resto):
        x = resto[k].lower()
        if x.startswith("-"):
            nome = x.split(":", 1)[0]
            if nome not in _GC_PARAMS:
                return False
            k += 1 + (_GC_PARAMS[nome] if ":" not in x else 0)
            continue
        k += 1
    return True


def _roda_script_do_plugin(seg, tipo):
    """O trecho roda um script deste plugin pelo caminho absoluto (o relatório dele não é a peça)?"""
    try:
        classe, det, _i = _classe(seg, tipo)
        if classe != "script":
            return False
        nome = _expandir_raiz_plugin(_desaspar(det[1]))
        return not _relativo(nome) and _script_do_plugin(_destino_absoluto(nome, os.getcwd()))
    except Exception:
        return False


def _emissoes(sub, tipo=None):
    '[(alvo, idêntica)] das redireções de saída de trechos que despejam o conteúdo de um .docx: o'






    tipo = tipo or _TIPO
    out = []
    conteudo = transformado = referencia = False
    for seg in _segmentos_pipe(sub):
        toks = _tokens(seg)
        i, t, _m = _programa(seg)
        p = _palavra(t) if t else ""
        resto = [_desaspar(x) for x in _sem_redirecao(toks)[(i or 0) + 1:]] if t else []
        nomeia = (bool(_docx_tokens(" ".join(_sem_redirecao(toks))))
                  or any(_eh_docx(e) for e in _entradas_redirecionadas(toks)))
        if not t:
            c_out, tr_out, r_out = False, False, False
        elif _nao_despeja(p, resto) or _roda_script_do_plugin(seg, tipo):
            c_out, tr_out = False, False
            r_out = tipo == "ps" and (nomeia or referencia or conteudo)
        elif nomeia or conteudo or (tipo == "ps" and referencia and p in _LE_REFERENCIA):
            c_out = True
            tr_out = transformado or (nomeia and conteudo) or not _identidade(p, resto, tipo)
            r_out = False
        else:
            c_out, tr_out, r_out = False, False, tipo == "ps" and referencia
        if c_out:
            out += [(a, not tr_out) for a in _alvos_redirecao(seg)]
        conteudo, transformado, referencia = c_out, tr_out, r_out
    return out


def _saidas_emissor(sub):
    'Alvos da redireção de saída de um trecho que despeja o conteúdo de um .docx (`cat x.docx >'



    return [a for a, _identica in _emissoes(sub)]


def _dests_explicitos(cmd):
    'TODOS os destinos .docx explícitos (dd of=, redireção, flags de saída, open write, WriteAll).'


    if not isinstance(cmd, str):
        return []
    out = list(_dests_redirecionados(cmd))

    _i, prog, _m = _programa(cmd)
    unzip = bool(prog) and _palavra(prog) == "unzip"
    for pat in _PATS_DEST:
        if unzip and "--upload-file" in pat:
            continue
        out += re.findall(pat, cmd, flags=re.I)
    return out




_VERBOS_CMD = ("copy", "move", "xcopy", "robocopy", "replace", "mklink")
_OPCAO_CMD = re.compile(r'^/-?[A-Za-z?][A-Za-z0-9]{0,9}(?:[:+-].*)?$')




_PS_COM_VALOR = ("path", "literalpath", "destination", "filter", "include", "exclude",
                 "credential", "fromsession", "tosession", "erroraction", "warningaction",
                 "informationaction", "errorvariable", "warningvariable", "informationvariable",
                 "outvariable", "outbuffer", "pipelinevariable", "progressaction", "stream")
_PS_SEM_VALOR = ("force", "recurse", "container", "passthru", "whatif", "confirm", "verbose",
                 "debug")
_PS_APELIDOS = {"ea": "erroraction", "wa": "warningaction", "infa": "informationaction",
                "ev": "errorvariable", "wv": "warningvariable", "iv": "informationvariable",
                "ov": "outvariable", "ob": "outbuffer", "pv": "pipelinevariable",
                "proga": "progressaction", "lp": "literalpath", "pspath": "literalpath",
                "vb": "verbose", "db": "debug", "wi": "whatif", "cf": "confirm"}



_VERBOS_PS = ("copy-item", "cpi", "move-item", "mi")

_VERBOS_PASTA_CORRENTE = ("copy-item", "cpi", "move-item", "mi", "cp", "copy", "mv", "move",
                          "xcopy")


def _param_ps(t, curto=False):
    'Nome do parâmetro do PowerShell em `-Nome` ou `-Nome:valor`, ou None. Aceita o nome'


    m = re.match(r'^-([A-Za-z]+)(?::.*)?$', t or "")
    if not m:
        return None
    n = m.group(1).lower()
    if curto and n in _PS_APELIDOS:
        return _PS_APELIDOS[n]
    if len(n) < 3 and not curto:
        return None
    nomes = [p for p in _PS_COM_VALOR + _PS_SEM_VALOR if p.startswith(n)]
    return n if n in nomes else (nomes[0] if len(nomes) == 1 else None)


def _argumentos(seg):
    '(verbo, posicionais, destino nomeado, origem nomeada?) do primeiro verbo de cópia, movimento,'


    toks = [_desaspar(t) for t in _sem_redirecao(_tokens(seg))]
    verbos = [_palavra(t) for t in toks]
    i = next((k for k, v in enumerate(verbos)
              if v in _VERBOS_DESTINO_FINAL + ("robocopy", "mklink", "link")), None)
    if i is None:
        return None
    verbo = verbos[i]
    curto, cmd_win = verbo in _VERBOS_PS, verbo in _VERBOS_CMD
    pos, destino, origem_nomeada, j = [], None, False, i + 1
    while j < len(toks):
        t = toks[j]
        j += 1
        if not t or (cmd_win and _OPCAO_CMD.match(t) and not _is_tmp(t)):
            continue
        if t.startswith("-"):
            nome = _param_ps(t, curto)
            if nome in _PS_COM_VALOR:
                if ":" in t:
                    valor = t.split(":", 1)[1]
                else:
                    valor = toks[j] if j < len(toks) else ""
                    j += 1
                if nome == "destination":
                    destino = valor
                elif nome in ("path", "literalpath"):
                    origem_nomeada = True
            continue
        pos.append(t)


    if any(_desaspar(t).lower() in ("-exec", "-execdir", "-ok", "-okdir") for t in toks[:i]):
        while pos and pos[-1] in ("\\", "+", "\\;", ";"):
            pos.pop()
    return verbo, pos, destino, origem_nomeada


def _dest_cp(cmd):
    'Destino de cp/move/Copy-Item/etc.: o último posicional depois do verbo (no robocopy,'




    a = _argumentos(cmd)
    if a is None:
        toks = [t for t in (_desaspar(x) for x in _sem_redirecao(_tokens(cmd)))
                if t and not t.startswith("-")]
        return toks[-1] if toks else None
    verbo, pos, destino, origem_nomeada = a
    if destino:
        return destino
    if verbo == "robocopy":
        return pos[1] if len(pos) > 1 else None
    if verbo in _VERBOS_PASTA_CORRENTE:
        if origem_nomeada:
            return pos[0] if pos else "."
        if len(pos) == 1:
            return "."
    return pos[-1] if pos else None


def _entrega_sub(sub):
    """Analisa UM sub-comando: retorna o .docx entregue ou None."""
    if not sub or not sub.strip():
        return None
    for d in _dests_explicitos(sub):
        if not _is_tmp(d):
            return d
    docx = _docx_tokens(sub)
    if not docx:
        return None
    if not (_tem_mecanismo(sub) or _saidas_emissor(sub)) and not (_ARQUIVAMENTO.search(sub) and any(
            _saidas_arquivamento(seg) for seg in _segmentos_pipe(sub))):
        return None


    nao_tmp = [d for d in docx if not _is_tmp(d)] or docx
    if _remoto_do_sub(sub) or _LINK.search(sub):
        return nao_tmp[0]



    saidas = [s for s in _saidas_do_comando(sub) if isinstance(s, str) and s.strip()]
    if saidas and all(_is_tmp(s) for s in saidas):
        return None
    dest = None if saidas else _dest_cp(sub)
    if dest is not None and _is_tmp(dest):
        return None
    if not saidas and dest is None and all(_is_tmp(d) for d in docx):
        return None
    return nao_tmp[0]









_SHELL_NOMES = (r'bash|sh|shell|zsh|power_?shell|pwsh|cmd|terminal|run_?in_?terminal|'
                r'ctx_(?:batch_)?execute(?:_file)?|run_?command|exec(?:ute)?(?:_command)?|monitor')
_TOOLS_SHELL = re.compile(rf'^(?:{_SHELL_NOMES}|mcp__.*__(?:{_SHELL_NOMES}))$', re.I)


_TOOLS_POWERSHELL = re.compile(r'^(?:mcp__.*__)?(?:power_?shell|pwsh|run_?in_?terminal)$', re.I)

_TOOLS_CMD = re.compile(r'^(?:mcp__.*__)?cmd$', re.I)




_CAMPOS_COMANDO = ("command", "cmd", "script", "code", "command_line", "commands", "input")
_LINGUAGENS_SHELL = ("shell", "bash", "sh", "zsh", "powershell", "pwsh", "cmd", "bat")


def _eh_shell(tool_name):
    return isinstance(tool_name, str) and bool(_TOOLS_SHELL.match(tool_name.strip()))


def _comando_de(tool_input):
    'Extrai o comando do input de uma ferramenta de shell. Lista de linhas (ou de objetos com'


    if not isinstance(tool_input, dict):
        return None
    lang = tool_input.get("language")
    for k in _CAMPOS_COMANDO:
        if k == "code" and isinstance(lang, str) and lang.strip().lower() not in _LINGUAGENS_SHELL:
            continue
        v = tool_input.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, (list, tuple)):
            partes = [x if isinstance(x, str) else x.get("command") for x in v
                      if isinstance(x, str) or (isinstance(x, dict) and isinstance(x.get("command"), str))]
            if partes:
                return "\n".join(partes)
    return None


def _cwd_da_chamada(tool_name, tool_input, cwd):
    'A pasta em que o comando roda: o `cwd` do input da ferramenta de shell que o aceita'

    if _eh_shell(tool_name) and isinstance(tool_input, dict):
        p = tool_input.get("cwd")
        if isinstance(p, str) and p.strip():
            return _destino_absoluto(p, cwd)
    return cwd






_POSIX = True
_TIPO = "posix"


def _tipo_da_chamada(tool_name, tool_input=None):
    'Shell que lê o comando da chamada: "ps" (PowerShell), "cmd" ou "posix". A linguagem'

    lang = tool_input.get("language") if isinstance(tool_input, dict) else None
    if isinstance(lang, str) and lang.strip():
        lang = lang.strip().lower()
        if lang in ("powershell", "pwsh"):
            return "ps"
        if lang in ("cmd", "bat"):
            return "cmd"
        if lang in _LINGUAGENS_SHELL:
            return "posix"
    nome = tool_name.strip() if isinstance(tool_name, str) else ""
    if _TOOLS_POWERSHELL.match(nome):
        return "ps"
    if _TOOLS_CMD.match(nome):
        return "cmd"
    return "posix"


class _modo_caminho:
    'Contexto que acerta, para a chamada, a conversão do caminho do Git Bash e o shell que lê o'



    def __init__(self, tool_name, tool_input=None, cwd=None):
        self.tipo = _tipo_da_chamada(tool_name, tool_input)
        self.posix = self.tipo != "ps"
        self.tool_name, self.tool_input, self.cwd = tool_name, tool_input, cwd

    def __enter__(self):
        global _POSIX, _TIPO, _FORMAS_DOCX, _ARQUIVOS_DOCX
        self.antes = (_POSIX, _TIPO, _FORMAS_DOCX, _ARQUIVOS_DOCX)
        _POSIX, _TIPO = self.posix, self.tipo
        if self.cwd is not None:
            try:
                inp = self.tool_input if isinstance(self.tool_input, dict) else {}
                _FORMAS_DOCX, _ARQUIVOS_DOCX = frozenset(), frozenset()
                _FORMAS_DOCX, _ARQUIVOS_DOCX = _docx_por_conteudo(
                    self.tool_name, inp, _cwd_da_chamada(self.tool_name, inp, self.cwd))
            except BaseException:
                _POSIX, _TIPO, _FORMAS_DOCX, _ARQUIVOS_DOCX = self.antes
                raise
        return self

    def __exit__(self, *_exc):
        global _POSIX, _TIPO, _FORMAS_DOCX, _ARQUIVOS_DOCX
        _POSIX, _TIPO, _FORMAS_DOCX, _ARQUIVOS_DOCX = self.antes
        return False





_TETO_OPERANDOS_CONTEUDO = 64
_TETO_GLOB_CONTEUDO = 1000
_TETO_ZIP_CONTEUDO = 100




_DEFINE_NOME = re.compile(r'(?:^|[;&|\n({]|\bthen|\bdo|\belse)\s*[\w.:-]+\s*\(\s*\)|'
                          r'(?<![\w-])(?:function|filter|alias|set-alias|new-alias|sal|nal|doskey)\s',
                          re.I)


def _nome_docx(p):
    """O nome termina em .docx (sem olhar o conteúdo), também com o sufixo de fluxo do NTFS."""
    return (isinstance(p, str)
            and _sem_fluxo(p.strip().strip('"').strip("'").rstrip(". ")).rstrip(". ").lower().endswith(".docx"))


def _pacote_word(p, cont):
    'O arquivo é um pacote do Word: começa por `PK\\x03\\x04` e tem `word/document.xml` no'

    try:
        with open(p, "rb") as fh:
            if fh.read(4) != b"PK\x03\x04":
                return False
            cont[0] += 1
            if cont[0] > _TETO_ZIP_CONTEUDO:
                return True
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 8192))
            if b"word/document.xml" in fh.read():
                return True
    except OSError:
        return False
    try:
        with zipfile.ZipFile(p) as z:
            return any(n.lower() == "word/document.xml" for n in z.namelist())
    except Exception:
        return False


def _docx_por_conteudo(tool_name, tool_input, cwd):
    '(formas, chaves) dos operandos desta chamada que são .docx sem o nome terminar em .docx: o'





    formas, arquivos, vistos, cont = set(), set(), set(), [0]

    def conferir(caminho):
        try:
            k = _chave_caminho(caminho)
        except (TypeError, ValueError):
            return False
        if k in vistos:
            return k in arquivos
        if len(vistos) >= _TETO_OPERANDOS_CONTEUDO + _TETO_GLOB_CONTEUDO:
            return False
        vistos.add(k)
        try:
            if not os.path.isfile(caminho):
                return False
        except (OSError, ValueError):
            return False
        if _nome_docx(caminho) or _pacote_word(caminho, cont):
            arquivos.add(k)
            return True
        return False

    def candidatos(t, tipo):
        brutas = []
        for b in {_desaspar(t), _palavra_shell(t, tipo)}:
            b = _REDIR_PREFIXO.sub("", _ENTRADA_ARQUIVO.sub("", b))
            if b.startswith("-"):
                b = b.split(":", 1)[1] if ":" in b else (b.split("=", 1)[1] if "=" in b else "")
            for item in (_partes_virgula(b) if b else []):
                for x in (item, re.split(r'[=@]', item)[-1]):
                    brutas += [x, _sem_fluxo(x)]
        return [f for f in dict.fromkeys(brutas)
                if f and not f.startswith("-") and not _EXPANSAO.search(f) and not _destino_remoto(f)]

    if not isinstance(tool_input, dict):
        return frozenset(), frozenset()
    operandos = 0
    if _eh_shell(tool_name):
        p = tool_input.get("path")
        if isinstance(p, str) and p.strip() and not _nome_docx(p):
            try:
                if conferir(_destino_absoluto(p, cwd)):
                    formas.add(_desaspar(p).strip())
            except (OSError, ValueError):
                pass
        lang = tool_input.get("language")
        if "code" in tool_input and isinstance(lang, str) and lang.strip().lower() not in _LINGUAGENS_SHELL:
            return frozenset(formas), frozenset(arquivos)
        cmd = _comando_de(tool_input)


        define = isinstance(cmd, str) and bool(_DEFINE_NOME.search(cmd))
        for sub, pasta, _d, tipo in (_percorrer(cmd, cwd, com_tipo=True) if isinstance(cmd, str) else []):
            copia = (define or _tem_mecanismo(sub) or bool(_ARQUIVAMENTO.search(sub))
                     or bool(_alvos_redirecao(sub)) or len(_segmentos_pipe(sub)) > 1)
            bases = [pasta]
            a = _argumentos(sub)
            if a and a[0] == "robocopy" and a[1]:
                try:
                    bases.append(_destino_absoluto(a[1][0], pasta))
                except (OSError, ValueError):
                    pass
            for t in _tokens(sub):
                cands = candidatos(t, tipo)
                if not cands or all(_nome_docx(f) for f in cands):
                    continue
                achou = False
                for f in cands:
                    if _nome_docx(f):
                        continue
                    if _GLOB.search(f):
                        if not copia:
                            continue
                        for base in bases:
                            try:
                                padrao = os.path.join(base, os.path.expanduser(_caminho_local(f)))
                                if os.path.exists(padrao):
                                    achou = conferir(padrao) or achou
                                    continue
                                achados = glob.glob(padrao)
                            except Exception:
                                continue
                            if len(achados) > _TETO_GLOB_CONTEUDO:
                                achou = True
                                achados = achados[:_TETO_GLOB_CONTEUDO]
                            for x in achados:
                                if conferir(x):
                                    achou = True
                        continue
                    operandos += 1
                    if operandos > _TETO_OPERANDOS_CONTEUDO:
                        break
                    for base in bases:
                        try:
                            if conferir(_destino_absoluto(f, base)):
                                achou = True
                        except (OSError, ValueError):
                            continue
                if achou:
                    formas |= set(cands) | {_desaspar(t)}
    elif _eh_tool_arquivo(tool_name):
        for c in _valores_caminho(tool_input) + [_campo(tool_input, _CAMPOS_DESTINO)]:
            if isinstance(c, str) and c.strip() and not _nome_docx(c) and not _destino_remoto(c):
                try:
                    if conferir(_destino_absoluto(c, cwd)):
                        formas.add(_desaspar(c).strip())
                except (OSError, ValueError):
                    continue
    return frozenset(formas), frozenset(arquivos)







_TOOLS_ARQUIVO = re.compile(
    r'^mcp__.*__(?:file_?system|files?|file_?upload|'
    r'(?:copy|move|rename|write|create|upload|save|put|edit)_?file(?:_content)?)$', re.I)



_OPS_ESCRITA = ("copy", "move", "write", "create", "upload", "save", "append", "rename", "put")
_OPS_LEITURA = ("read", "list", "search", "info", "get", "download", "delete", "stat",
                "exists", "metadata", "permission")
_CAMPOS_OPERACAO = ("mode", "operation", "action", "op", "modo", "acao")


_CAMPOS_DESTINO = ("destination", "destination_path", "dest", "dest_path", "target", "target_path",
                   "to", "new_path", "output", "output_path", "destino", "caminho_destino")

_CAMPOS_CAMINHO = ("path", "file_path", "filepath", "caminho", "arquivo", "filename", "file_name",
                   "name", "source", "src", "origem")



_CAMPOS_CAMINHOS = ("paths", "filepaths", "file_paths", "files", "sources", "arquivos", "caminhos")


_MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MIME_GOOGLE_DOC = "application/vnd.google-apps.document"
_CAMPOS_MIME = ("contentMimeType", "mimeType", "content_mime_type", "mime_type", "mime",
                "contentType", "content_type")


_CAMPOS_CONTEUDO_BINARIO = ("base64Content", "base64_content", "content", "contentBase64")
_CAMPOS_TITULO = ("title", "titulo", "name", "filename", "file_name")





_TOOLS_ARQUIVO_NATIVAS = ("SendUserFile",)


_TOOLS_ENVIO_NATIVO = re.compile(r"^(?:mcp__.*__)?present_files$|^Artifact$")


def _eh_tool_arquivo(tool_name):
    return isinstance(tool_name, str) and (bool(_TOOLS_ARQUIVO.match(tool_name.strip()))
                                           or tool_name.strip() in _TOOLS_ARQUIVO_NATIVAS
                                           or bool(_TOOLS_ENVIO_NATIVO.match(tool_name.strip())))


def _envio_ao_advogado(tool_name):
    """A ferramenta manda o arquivo para fora do computador, a um destino que não é pasta de caso?"""
    return isinstance(tool_name, str) and (tool_name.strip() in _TOOLS_ARQUIVO_NATIVAS
                                           or bool(_TOOLS_ENVIO_NATIVO.match(tool_name.strip())))


def _campo(tool_input, nomes):
    'O valor do primeiro campo de `nomes` presente no input, sem diferenciar maiúsculas'

    if not isinstance(tool_input, dict):
        return None
    chaves = {k.lower(): k for k in tool_input if isinstance(k, str)}
    for n in nomes:
        k = chaves.get(n.lower())
        if k is not None:
            return tool_input[k]
    return None


def _valores_caminho(tool_input):
    'Os caminhos locais que o input nomeia, nos campos de caminho único e nos de lista, sem'

    if not isinstance(tool_input, dict):
        return []
    chaves = {k.lower(): k for k in tool_input if isinstance(k, str)}
    out = []
    for n in _CAMPOS_CAMINHO + _CAMPOS_CAMINHOS:
        k = chaves.get(n.lower())
        if k is None:
            continue
        v = tool_input[k]
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, (list, tuple)):
            for it in v:
                if isinstance(it, str):
                    out.append(it)
                elif isinstance(it, dict):
                    p = _campo(it, ("path", "file_path", "filepath"))
                    if isinstance(p, str):
                        out.append(p)
    return out


def _operacao(tool_name, tool_input):
    """'escrita' | 'leitura' | 'indefinida' — do campo `mode`/`operation` ou do nome da ferramenta."""
    for k in _CAMPOS_OPERACAO:
        v = tool_input.get(k)
        if isinstance(v, str) and v.strip():
            m = v.strip().lower()
            if any(m.startswith(o) for o in _OPS_ESCRITA):
                return "escrita"
            if any(m.startswith(o) for o in _OPS_LEITURA):
                return "leitura"
    nome = (tool_name or "").lower()
    if any(o in nome for o in _OPS_LEITURA):
        return "leitura"
    if any(o in nome for o in _OPS_ESCRITA):
        return "escrita"
    return "indefinida"


def _entrega_arquivo_estruturado(tool_name, tool_input):
    'Entrega por ferramenta de arquivo com PARÂMETROS (sem comando).'











    if _operacao(tool_name, tool_input) == "leitura":
        return None
    d = _campo(tool_input, _CAMPOS_DESTINO)
    if d is not None:
        if _is_tmp(d):
            return None
        if _eh_docx(d):
            return d


        for c in _valores_caminho(tool_input):
            if _eh_docx(c):
                return c
    upload = _eh_upload_estruturado(tool_name, tool_input)
    for c in _valores_caminho(tool_input):

        if _eh_docx(c) and (upload or not _is_tmp(c)):
            return c
    for v in tool_input.values():
        if _eh_docx(v) and not _is_tmp(v):
            return v
        if isinstance(v, (list, tuple)):
            for it in v:
                if isinstance(it, dict):


                    nome = _campo(it, ("path", "name", "filename", "title"))
                    mime = _campo(it, _CAMPOS_MIME)
                    if _eh_docx(nome) and not _is_tmp(nome):
                        return nome
                    if isinstance(mime, str) and mime.strip().lower().split(";")[0] == _MIME_DOCX:
                        return nome if isinstance(nome, str) and nome.strip() else "documento sem título"
                elif _eh_docx(it) and not _is_tmp(it):
                    return it
    return _entrega_por_mime(tool_input)


def _entrega_por_mime(tool_input):
    'Upload cujo tipo declarado é documento do Word (ou Google Doc com conteúdo binário), com'




    mimes = [tool_input.get(k) for k in _CAMPOS_MIME]
    mimes = [m.strip().lower().split(";")[0].strip() for m in mimes if isinstance(m, str)]
    binario = any(isinstance(tool_input.get(k), str) and tool_input.get(k).strip()
                  for k in _CAMPOS_CONTEUDO_BINARIO)
    if not (_MIME_DOCX in mimes or (_MIME_GOOGLE_DOC in mimes and binario)):
        return None
    for k in _CAMPOS_TITULO + _CAMPOS_CAMINHO:
        v = tool_input.get(k)
        if isinstance(v, str) and v.strip():
            return None if _is_tmp(v) else v.strip()
    return "documento sem título"


def _entrega_bash(cmd):
    'Retorna o .docx entregue por um comando shell, ou None. Avalia cada sub-comando (ver'

    if not isinstance(cmd, str):
        return None
    for sub in _subcomandos(cmd):
        alvo = _entrega_sub(sub)
        if alvo:
            return alvo
    return None


def _detectar_entrega(tool_name, tool_input):
    """Retorna o caminho do .docx sendo ENTREGUE (peça), ou None se não for entrega de peça."""
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool_name in ("Write", "Edit"):
        fp = tool_input.get("file_path") or ""
        return fp if (_eh_docx(fp) and not _is_tmp(fp)) else None
    if _eh_shell(tool_name):
        return _entrega_bash(_comando_de(tool_input))
    if _eh_tool_arquivo(tool_name):
        return _entrega_arquivo_estruturado(tool_name, tool_input)
    return None


def _localizar_state(alvo, cwd):
    'PECA_STATE.json acima de um caminho, ou None. Usado pelo `aviso_completude.py`.'



    alvo = _caminho_local(alvo)
    p = os.path.abspath(alvo if os.path.isabs(alvo) else os.path.join(cwd or os.getcwd(), alvo))
    d = p if os.path.isdir(p) else os.path.dirname(p)


    for _ in range(3):
        cand = os.path.join(d, PECA_STATE_NAME)
        if os.path.exists(cand):
            return cand
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def _candidatos_docx(evento, alvo, origens=()):
    '.docx legíveis EM DISCO relacionados a esta entrega, na ordem de preferência.'





    vistos, out = set(), []
    for cand in ([alvo] + _docx_tokens(_comando_de(evento.get("tool_input") or {}))
                 + list(origens)):
        if not isinstance(cand, str) or cand in vistos:
            continue
        vistos.add(cand)
        cand = _caminho_local(cand)
        try:
            if os.path.isfile(cand) and os.path.getsize(cand) > 0:
                out.append(cand)
        except OSError:
            continue
    return out








_FLAGS_SAIDA = ("-o", "--output", "--out-file", "-outfile", "-filepath")



_CMDLETS_ESCRITA = re.compile(r'^(?:set-content|sc|add-content|ac|out-file)$', re.I)
_FLAGS_CAMINHO_PS = ("-path", "-literalpath")


_VERBOS_ALVO_T = ("cp", "mv", "install", "ln", "gcp", "gmv", "ginstall")

_FLAG_T = re.compile(r'^-[abdfHilLnPpRrsuvxZCcDT]*t(.*)$')



_VERBOS_DESTINO_FINAL = ("cp", "mv", "copy", "move", "copy-item", "cpi", "move-item", "mi",
                         "rename-item", "ren", "rni", "rename", "install", "ditto", "rsync", "scp",
                         "sftp", "xcopy", "tee", "ln", "gcp", "gmv", "ginstall", "rclone")

_EXPANSAO = re.compile(r'\$(?:\{|\(|[A-Za-z_0-9@*#?!$])|%[A-Za-z_][A-Za-z0-9_]*%')
_GLOB = re.compile(r'[*?\[]')


_VERBOS_CD = ("cd", "chdir", "pushd", "set-location", "sl", "push-location")
_VERBOS_POPD = ("popd", "pop-location")
_PREFIXOS_CD = ("builtin", "command", "then", "do", "else", "elif", "if", "while", "until", "!",
                "time", "{", "(")

_PS_CD_COM_VALOR = ("path", "literalpath", "stackname", "erroraction", "warningaction",
                    "informationaction", "errorvariable", "warningvariable", "informationvariable",
                    "outvariable", "outbuffer", "pipelinevariable", "progressaction")
_PS_CD_SEM_VALOR = ("passthru", "verbose", "debug", "whatif", "confirm")




_CD_EMBUTIDO = re.compile(r'\bchdir\s*\(|\bSetCurrentDirectory\b|\bCurrentDirectory\s*=|'
                          r'\bcwd\s*[=:]|-WorkingDirectory\b|--chdir\b|--directory\b|'
                          r'(?-i:(?:^|\s)-C(?=[\s=]))', re.I)


_DOTNET = re.compile(r'\[(?:System\.)?IO\.(?:File|Directory|FileInfo|DirectoryInfo|Path)\]\s*::', re.I)
_PATS_SAIDA_API = (
    rf'open\s*\(\s*{_PY_PREFIXO}["\']([^"\']+\.docx)["\']\s*,\s*(?:mode\s*=\s*)?{_PY_PREFIXO}["\'][^"\']*[wax+][^"\']*["\']',
    r'writeall(?:bytes|text)\s*\(\s*["\']([^"\']+\.docx)',
    r'writefile(?:sync)?\s*\(\s*["\']([^"\']+\.docx)',

    rf'\.\s*save\s*\(\s*{_PY_PREFIXO}["\']([^"\']+\.docx)["\']',

    rf'\b(?:ZipFile|PyZipFile|TarFile)\s*\(\s*{_PY_PREFIXO}["\']([^"\']+\.docx)["\']\s*,\s*(?:mode\s*=\s*)?{_PY_PREFIXO}["\'][wax]',
    rf'path\s*\(\s*{_PY_PREFIXO}["\']([^"\']+\.docx)["\']\s*\)\s*\.\s*write_(?:bytes|text)',

    rf'\)\s*\.\s*(?:rename|replace)\s*\(\s*{_PY_PREFIXO}["\']([^"\']+\.docx)',

    rf'(?:copy\w*|move|rename|replace|symlink|link)\s*\(\s*{_PY_PREFIXO}["\'][^"\']+["\']\s*,\s*{_PY_PREFIXO}["\']([^"\']+\.docx)',

    rf'(?:copy\w*|move|rename|replace|symlink|link)\s*\(\s*{_PY_PREFIXO}["\'][^"\']+\.docx["\']\s*,\s*{_PY_PREFIXO}["\']([^"\']+)["\']',
)


def _palavra(t):
    """Nome de programa no token: sem aspas, sem pasta, sem `.exe`, em minúsculas."""
    b = re.split(r'[\\/]', _desaspar(t))[-1].lower()
    return b[:-4] if b.endswith(".exe") else b


def _tem_verbo(toks, verbos):
    return any(_palavra(t) in verbos for t in toks)


def _segmentos_pipe(sub):
    """Trechos de um sub-comando separados por `|` fora de aspas (`>|` não separa)."""
    segs, atual, aspa = [], [], None
    for i, c in enumerate(sub or ""):
        if aspa:
            if c == aspa:
                aspa = None
        elif c in "\"'":
            aspa = c
        elif c == "|" and not (i > 0 and sub[i - 1] == ">"):
            segs.append("".join(atual))
            atual = []
            continue
        atual.append(c)
    segs.append("".join(atual))
    return segs


def _destinos_por_flag(toks):
    'Destino declarado por flag: `-t DIR`/`--target-directory=DIR` depois de cp, mv, install'


    out, verbo = [], False
    for i, bruto in enumerate(toks):
        t = _desaspar(bruto)
        prox = _desaspar(toks[i + 1]) if i + 1 < len(toks) else ""
        baixo = t.lower()
        if baixo == "-destination":
            if prox:
                out.append(prox)
            continue
        if baixo.startswith(("-destination:", "-destination=")):
            out.append(t[len("-destination") + 1:])
            continue
        if not verbo:
            verbo = _palavra(t) in _VERBOS_ALVO_T
            continue



        longa = re.match(r'^(--t[a-z-]*)(?:=(.*))?$', t)
        if longa and "--target-directory".startswith(longa.group(1)):
            valor = longa.group(2) if longa.group(2) is not None else prox
            if valor:
                out.append(_desaspar(valor))
        elif not t.startswith("--"):
            m = _FLAG_T.match(t)
            if m:
                valor = _desaspar(m.group(1)) or prox
                if valor:
                    out.append(valor)
    return out


def _caminhos_escritos_ps(seg):
    'Arquivo escrito por Set-Content, Add-Content ou Out-File no trecho de pipe: valor de'


    out, escrita, prof = [], False, 0
    toks = _tokens(seg)
    for i, bruto in enumerate(toks):
        if prof == 0 and not bruto.startswith(("(", "$(", "@(")):
            t = _desaspar(bruto)
            baixo = t.lower()
            if _CMDLETS_ESCRITA.match(t):
                escrita = True
                prox = toks[i + 1] if i + 1 < len(toks) else ""
                if prox and not prox.startswith(("-", "(", "$(", "@(")):
                    out.append(_desaspar(prox))
            elif escrita:
                for f in _FLAGS_CAMINHO_PS:
                    if baixo == f and i + 1 < len(toks):
                        out.append(_desaspar(toks[i + 1]))
                    elif baixo.startswith((f + ":", f + "=")):
                        out.append(t[len(f) + 1:])
        if bruto[:1] not in "\"'":
            prof = max(0, prof + bruto.count("(") - bruto.count(")"))
    return out





_ARQUIVAMENTO = re.compile(r'\b(tar|zip|7z|7za|compress-archive)\b', re.I)


def _saidas_arquivamento(seg):
    'O pacote que o trecho de pipe CRIA (`tar -cf X`, `tar cf X`, `--file=X`, `zip X …`,'

    st = [_desaspar(t) for t in _sem_redirecao(_tokens(seg))]
    verbos = [_palavra(t) for t in st]
    for i, verbo in enumerate(verbos):
        args = st[i + 1:]
        if verbo == "tar":
            criar, arquivo = False, None
            for k, a in enumerate(args):
                prox = args[k + 1] if k + 1 < len(args) else None
                if a.startswith("--file="):
                    arquivo = a[len("--file="):]
                elif a == "--file":
                    arquivo = prox
                elif a in ("--create", "--append", "--update", "--concatenate"):
                    criar = True
                elif re.fullmatch(r'-[A-Za-z]+', a) or (k == 0 and re.fullmatch(r'[A-Za-z]+', a)):
                    letras = a.lstrip("-")
                    criar = criar or bool(set(letras) & set("cruA"))
                    if "f" in letras:
                        arquivo = prox
            return [arquivo] if criar and arquivo else []
        if verbo == "zip":
            pos = [a for a in args if not a.startswith("-")]
            return pos[:1]
        if verbo in ("7z", "7za"):
            pos = [a for a in args if not a.startswith("-")]
            return [pos[1]] if len(pos) > 1 and pos[0].lower() in ("a", "u") else []
        if verbo == "compress-archive":
            for k, a in enumerate(args):
                m = re.match(r'^-(dest[a-z]*)(?::(.*))?$', a, re.I)
                if m and "destinationpath".startswith(m.group(1).lower()):
                    v = m.group(2) if m.group(2) is not None else (args[k + 1] if k + 1 < len(args) else "")
                    return [v] if v else []
            pos = [a for k, a in enumerate(args) if not a.startswith("-")
                   and not (k > 0 and args[k - 1].lower().startswith(("-path", "-literalpath")))]
            return pos[-1:] if len(pos) > 1 else []
    return []


def _saidas_do_comando(sub):
    """Arquivos que o sub-comando ESCREVE, na forma em que aparecem no comando."""
    out = list(_dests_redirecionados(sub))
    out += [a for a in _saidas_emissor(sub) if a not in out]
    toks = _tokens(sub)
    for i, bruto in enumerate(toks):
        t = _desaspar(bruto)
        baixo = t.lower()
        if baixo.startswith("of="):
            out.append(t[3:])
            continue
        for f in _FLAGS_SAIDA:
            if baixo == f and i + 1 < len(toks):
                out.append(_desaspar(toks[i + 1]))
            elif baixo.startswith(f + "=") or (len(f) > 2 and not f.startswith("--")
                                               and baixo.startswith(f + ":")):
                out.append(t[len(f) + 1:])
    destinos = _destinos_por_flag(toks)
    out += destinos
    for seg in _segmentos_pipe(sub):
        out += _caminhos_escritos_ps(seg)
        out += _saidas_arquivamento(seg)
    for pat in _PATS_SAIDA_API:
        out += re.findall(pat, sub, flags=re.I)




    if not (destinos or _remoto_do_sub(sub) or _LINK.search(sub)):
        for seg in _segmentos_pipe(sub):
            st = [_desaspar(t) for t in _sem_redirecao(_tokens(seg))]
            verbos = [_palavra(t) for t in st]
            if "tee" in verbos:
                out += [t for t in st[verbos.index("tee") + 1:] if t and not t.startswith("-")]
            elif _tem_verbo(st, _VERBOS_DESTINO_FINAL + ("robocopy",)):
                dest = _dest_cp(seg)
                if dest:
                    out.append(dest)
    return out


def _absoluto(p, cwd):
    p = os.path.expanduser(_caminho_local(p.strip().strip('"').strip("'").rstrip(". ")))
    return os.path.abspath(p if os.path.isabs(p) else os.path.join(cwd, p))


def _chave_caminho(p):
    return os.path.normcase(os.path.normpath(p))


def _sha256_arquivo(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _eh_upload_estruturado(tool_name, tool_input):
    if "upload" in (tool_name or "").lower() or _envio_ao_advogado(tool_name):
        return True
    return any(isinstance(tool_input.get(k), str) and tool_input[k].strip().lower().startswith("upload")
               for k in _CAMPOS_OPERACAO)


def _mudanca_de_pasta(sub):
    '("cd" | "push" | "pop", pasta pedida ou None) quando o sub-comando muda a pasta do shell, ou'




    toks = _tokens(sub)
    i = 0
    while i < len(toks) and (_desaspar(toks[i]).lower() in _PREFIXOS_CD
                             or re.match(r'^[A-Za-z_]\w*=', toks[i])):
        i += 1
    if i >= len(toks):
        return None
    verbo = _palavra(toks[i])
    if verbo in _VERBOS_POPD:
        return ("pop", None)
    if verbo not in _VERBOS_CD:
        return None
    tipo = "push" if verbo in ("pushd", "push-location") else "cd"
    if len(_segmentos_pipe(sub)) > 1:
        return (tipo, None)
    resto = _sem_redirecao(toks[i + 1:])
    pos, j = [], 0
    while j < len(resto):
        bruto = resto[j]
        t = _desaspar(bruto)
        j += 1
        if not t or t.lower() == "/d":
            continue
        if t in ("-", "+"):
            return (tipo, None)
        if t == "--":
            continue
        if t.startswith("--"):
            return (tipo, None)
        if t.startswith("-"):
            nome = t[1:].split(":", 1)[0].lower()
            if len(nome) == 1 and nome in "lpe@":
                continue
            nome = _PS_APELIDOS.get(nome, nome)
            cands = [p for p in _PS_CD_COM_VALOR + _PS_CD_SEM_VALOR if p.startswith(nome)]
            cands = [nome] if nome in cands else cands
            if len(cands) != 1:
                return (tipo, None)
            if cands[0] in _PS_CD_SEM_VALOR:
                continue
            if ":" in t:
                valor = t.split(":", 1)[1]
            else:
                valor = _desaspar(resto[j]) if j < len(resto) else ""
                j += 1
            if cands[0] in ("path", "literalpath"):
                pos.append(valor)
            continue
        pos.append(t)
    pos = [p for p in pos if p]
    return (tipo, pos[0] if len(pos) == 1 else None)


def _pasta_existente(arg, base):
    """A pasta `arg` resolvida em `base`, quando existe; senão None."""
    destino = os.path.abspath(os.path.join(base, os.path.expanduser(_caminho_local(arg))))
    return destino if os.path.isdir(destino) else None


def _relativo(p):
    """Caminho que depende da pasta corrente (sem raiz, unidade nem `~`)?"""
    return not os.path.isabs(os.path.expanduser(_caminho_local(_desaspar(p))))


def _cd_no_meio(sub):
    'O sub-comando tem um verbo de mudança de pasta fora da primeira posição (`x | Set-Location`,'

    return any(_palavra(t) in _VERBOS_CD + _VERBOS_POPD for t in _tokens(sub)[1:]
               if t[:1] not in "\"'")


def _percorrer(cmd, cwd, com_tipo=False):
    '[(sub-comando, pasta em que roda, pasta desconhecida ou None)] de `cmd`, sem os `cd`.'











    out, pasta, cd_var, subshells, pilha = [], cwd, None, [], []
    for sub, abre, fecha, fundo, shell in (_partes(cmd) if isinstance(cmd, str) else []):
        subshells += [(pasta, cd_var, list(pilha))] * abre
        mud = _mudanca_de_pasta(sub) if sub else None
        if mud is not None:
            tipo, alvo = mud
            if fundo:
                cd_var = sub.strip()
            elif tipo == "pop":
                if pilha:
                    pasta, cd_var = pilha.pop()
                else:
                    cd_var = sub.strip()
            elif alvo is not None and cd_var and _relativo(alvo) and not _EXPANSAO.search(alvo):
                pass
            else:
                nova = (_pasta_existente(alvo, pasta)
                        if alvo is not None and not _EXPANSAO.search(alvo) else None)
                if nova:
                    if tipo == "push":
                        pilha.append((pasta, cd_var))
                    pasta, cd_var = nova, None
                else:
                    cd_var = sub.strip()
        elif sub:
            proprio = cd_var
            if not proprio and _CD_EMBUTIDO.search(sub):
                proprio = sub.strip()
            elif not proprio and _DOTNET.search(sub) and _chave_caminho(pasta) != _chave_caminho(cwd):
                proprio = sub.strip()
            out.append((sub, pasta, proprio, shell) if com_tipo else (sub, pasta, proprio))
            if _cd_no_meio(sub):
                cd_var = cd_var or sub.strip()
        for _ in range(fecha):
            if subshells:
                pasta, cd_var, pilha = subshells.pop()
    return out


def _globs_docx(sub, base, toks=None):
    '.docx que um glob do sub-comando alcança (`cp *.docx entrega/`), resolvidos em `base`.'


    out = []
    if toks is None:
        toks = [_desaspar(t) for t in _sem_redirecao(_tokens(sub))]
    for t in toks:
        if not t or t.startswith("-") or not _GLOB.search(t) or _EXPANSAO.search(t):
            continue
        padrao = os.path.join(base, os.path.expanduser(_caminho_local(t)))
        try:
            if os.path.exists(padrao):
                continue
            achados = sorted(glob.glob(padrao))
        except Exception:
            continue
        out += [a for a in achados if _eh_docx(a) and os.path.isfile(a)]
    return out


def _nomeados_do_sub(sub, pasta):
    '[(caminho, pasta em que se resolve)] dos .docx que o sub-comando nomeia ou alcança por'


    a = _argumentos(sub)
    if a and a[0] == "robocopy" and a[1]:
        origem = _destino_absoluto(a[1][0], pasta)
        filtros = a[1][2:]
        return [(f, origem) for f in filtros + _globs_docx(sub, origem, filtros)]
    return [(n, pasta) for n in _docx_tokens(sub) + _globs_docx(sub, pasta)]


def _pares_da_entrega(tool_name, tool_input, cwd):
    '[(nomeados, saídas)] desta entrega: um par por sub-comando de entrega no shell, na ordem,'




    if not isinstance(tool_input, dict):
        return []
    cwd = cwd or os.getcwd()
    if tool_name in ("Write", "Edit"):
        fp = (tool_input.get("file_path"), cwd)
        return [([], [fp])]
    if _eh_shell(tool_name):
        return [(_nomeados_do_sub(sub, pasta), [(s, pasta) for s in _saidas_do_comando(sub)])
                for sub, pasta, _cd_var in _percorrer(_comando_de(tool_input), cwd)
                if _entrega_sub(sub)]
    if _eh_tool_arquivo(tool_name):
        caminhos = [(c, cwd) for c in _valores_caminho(tool_input)]
        destino = _campo(tool_input, _CAMPOS_DESTINO)
        if destino is not None:
            return [(caminhos + [(destino, cwd)], [(destino, cwd)])]
        if _eh_upload_estruturado(tool_name, tool_input):
            return [(caminhos, [])]
        return [([], caminhos)]
    return []


def _excluidos(pares):
    """Chaves dos caminhos escritos pela entrega (todas as saídas de todos os pares)."""
    excluir = set()
    for _nomeados, saidas in pares:
        for s, pasta in saidas:
            if isinstance(s, str) and s.strip():
                for forma in (s, re.split(r'[=@]', s)[-1]):
                    excluir.add(_chave_caminho(_absoluto(forma, pasta)))
    return excluir


def _docx_nomeados(nomeados, excluir):
    """Caminhos absolutos dos .docx de `nomeados` que não estão em `excluir`, existam ou não."""
    return [p for p in (_absoluto(n, pasta) for n, pasta in nomeados if _eh_docx(n))
            if _chave_caminho(p) not in excluir]


def _em_disco(caminhos):
    """Os caminhos que são arquivo não vazio em disco, sem repetir caminho."""
    out, vistos = [], set()
    for p in caminhos:
        k = _chave_caminho(p)
        if k in vistos:
            continue
        vistos.add(k)
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                out.append(p)
        except OSError:
            continue
    return out


def _origens_da_entrega(tool_name, tool_input, cwd):
    '.docx em disco que carregam o conteúdo desta entrega: caminho absoluto, um por conteúdo'





    pares = _pares_da_entrega(tool_name, tool_input, cwd or os.getcwd())
    excluir = _excluidos(pares)
    origens, vistos = [], set()
    for nomeados, _saidas in pares:
        for p in _em_disco(_docx_nomeados(nomeados, excluir)):
            try:
                h = _sha256_arquivo(p)
            except OSError:
                continue
            if h not in vistos:
                vistos.add(h)
                origens.append(p)
    return origens





def _destino_absoluto(d, pasta):
    'Caminho absoluto de um destino. O ponto e o espaço finais que o NTFS descarta saem só do'

    s = os.path.expanduser(_caminho_local(_desaspar(d).strip()))
    if re.split(r'[\\/]', s.rstrip("\\/"))[-1] not in (".", ".."):
        s = s.rstrip(". ")
    return os.path.abspath(s if os.path.isabs(s) else os.path.join(pasta, s))




_REMOTO = re.compile(r'^(?:[A-Za-z][\w+.-]*://|(?:[^\s@/\\:]+@)?[^\s@/\\:]{2,}:)')

_VERBOS_ORIGEM_DESTINO = ("rclone", "scp", "sftp", "rsync")


def _destino_remoto(d):
    return isinstance(d, str) and bool(_REMOTO.match(_desaspar(d).strip()))


def _remoto_do_sub(sub):
    'O sub-comando envia a destino remoto? A ferramenta de upload, sempre; rclone, scp, sftp e'

    a = _argumentos(sub)
    if a and a[0] in _VERBOS_ORIGEM_DESTINO:
        return any(_destino_remoto(p) for p in a[1])
    return bool(_UPLOAD.search(sub or ""))


def _raizes_registradas():
    'Raízes de caso registradas pelo `caso_raiz.py` que existem em disco: `DSR_CASO_RAIZ`, o'


    if _caso_raiz is None:
        return None
    raizes = []
    env = os.environ.get(_caso_raiz.ENV_RAIZ)
    if isinstance(env, str) and env.strip():
        raizes.append(env.strip())
    base = _caso_raiz.base_dir()
    ponteiros = [os.path.join(base, _caso_raiz.PONTEIRO_ATUAL)]
    try:
        ponteiros += glob.glob(os.path.join(glob.escape(base), _caso_raiz.DIR_SESSOES, "*.json"))
    except Exception:
        pass
    for p in ponteiros:
        try:
            with open(p, encoding="utf-8") as fh:
                raiz = json.load(fh).get("raiz")
        except Exception:
            continue
        if isinstance(raiz, str) and raiz.strip():
            raizes.append(raiz.strip())
    return [os.path.abspath(r) for r in raizes if os.path.isdir(r)]




_PASTAS_CONHECIDAS_WINDOWS = ("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
                              "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
                              "{374DE290-123F-4565-9164-39C4925E467B}")

_PASTAS_CONHECIDAS_XDG = ("XDG_DESKTOP_DIR", "XDG_DOCUMENTS_DIR", "XDG_DOWNLOAD_DIR")
_PASTAS_CONHECIDAS_PADRAO = ("Desktop", "Documents", "Downloads")

_VARIAVEIS_ONEDRIVE = ("OneDrive", "OneDriveCommercial", "OneDriveConsumer")
_CACHE_PASTAS_SISTEMA = []


def _pasta_conhecida_windows(folderid):
    """Caminho de uma pasta conhecida do Windows pelo FOLDERID, ou None."""
    import ctypes
    import uuid
    from ctypes import wintypes

    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    u = uuid.UUID(folderid)
    guid = _GUID(u.fields[0], u.fields[1], u.fields[2],
                 (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
    obter = ctypes.windll.shell32.SHGetKnownFolderPath
    obter.argtypes = (ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE,
                      ctypes.POINTER(ctypes.c_void_p))
    obter.restype = ctypes.c_long
    liberar = ctypes.windll.ole32.CoTaskMemFree
    liberar.argtypes = (ctypes.c_void_p,)
    ponteiro = ctypes.c_void_p()
    try:
        if obter(ctypes.byref(guid), 0, None, ctypes.byref(ponteiro)) != 0 or not ponteiro.value:
            return None
        return ctypes.wstring_at(ponteiro.value)
    finally:
        if ponteiro.value:
            liberar(ponteiro)


def _pastas_xdg(casa):
    """Área de Trabalho, Documentos e Downloads declaradas no `user-dirs.dirs` do XDG (Linux)."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(casa, ".config")
    out = []
    try:
        with open(os.path.join(base, "user-dirs.dirs"), encoding="utf-8") as fh:
            linhas = fh.read().splitlines()
    except (OSError, ValueError):
        return out
    for linha in linhas:
        nome, _, valor = linha.strip().partition("=")
        if nome in _PASTAS_CONHECIDAS_XDG and valor:
            valor = valor.strip().strip('"').replace("$HOME", casa)
            if valor and valor.rstrip("/") != casa.rstrip("/"):
                out.append(valor)
    return out


def _pastas_conhecidas():
    'Área de Trabalho, Documentos e Downloads do usuário onde estiverem: no Windows, pela API'


    if _CACHE_PASTAS_SISTEMA:
        return list(_CACHE_PASTAS_SISTEMA[0])
    pastas = []
    try:
        casa = os.path.expanduser("~")
    except Exception:
        casa = ""
    if _WINDOWS:
        for folderid in _PASTAS_CONHECIDAS_WINDOWS:
            try:
                p = _pasta_conhecida_windows(folderid)
            except Exception:
                p = None
            if p:
                pastas.append(p)
    elif casa and casa != "~":
        pastas += _pastas_xdg(casa)
    if casa and casa != "~":
        pastas += [os.path.join(casa, n) for n in _PASTAS_CONHECIDAS_PADRAO]
    _CACHE_PASTAS_SISTEMA.append(tuple(pastas))
    return pastas


def _pastas_sem_caso():
    'Chaves das pastas cujos arquivos de controle não marcam caso: a pasta pessoal, a Área de'




    pastas = []
    try:
        casa = os.path.expanduser("~")
    except Exception:
        casa = ""
    if casa and casa != "~":
        pastas.append(casa)
    pastas += _pastas_conhecidas()
    for var in _VARIAVEIS_ONEDRIVE:
        v = os.environ.get(var)
        if isinstance(v, str) and v.strip():
            pastas.append(v.strip())
    out = set()
    for p in pastas:
        out |= _chaves_da_pasta(p)
    out.discard("")
    return out


_CACHE_CHAVES_PASTA = {}


def _chaves_da_pasta(p):
    'Chaves do caminho escrito e do real (a pasta pode ser junção ou link), uma vez por'

    if p not in _CACHE_CHAVES_PASTA:
        chaves = set()
        for forma in (p, _real(p)):
            try:
                if forma:
                    chaves.add(_chave_caminho(os.path.abspath(forma)).rstrip("\\/"))
            except (OSError, ValueError, TypeError):
                continue
        _CACHE_CHAVES_PASTA[p] = chaves
    return _CACHE_CHAVES_PASTA[p]


def _marcador_de_caso(caminho):
    '(pasta, arquivo de controle) do caso em cuja árvore o caminho fica, ou None. Sobe da'

    d = caminho if os.path.isdir(caminho) else os.path.dirname(caminho)
    ignorar = _pastas_sem_caso()
    while True:
        acima = os.path.dirname(d)
        if acima == d:
            return None
        if _chave_caminho(d) not in ignorar:
            for marcador in MARCADORES_CASO:
                if os.path.exists(os.path.join(d, marcador)):
                    return d, marcador
        d = acima


def _varredura_bloqueia(evento, alvo, origens=()):
    'Motivo do deny quando a peça carrega elemento oculto, ou None.'






    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import varredura_documento as vd
    except Exception:
        return None
    caminhos = _candidatos_docx(evento, alvo, origens)
    for caminho in caminhos:
        try:
            r = vd.varrer_docx(caminho)
        except Exception:
            continue
        if r.get("exit_code") == 1:
            altas = [a for a in r.get("achados", []) if a.get("severidade") == "alta"]



            def _onde(p):
                return (" na " if p.startswith("nota") else " no ") + p if p else ""
            itens = "; ".join(
                f"{a['id']} ({a['severidade']})"
                f"{_onde(a.get('parte', ''))}: "
                f"{a.get('trecho', '')[:90]}" for a in altas)





            if all(a.get("id") == "timbrado_pacote_trocado" for a in altas):
                return (f"Entrega de PEÇA BLOQUEADA: PACOTE DE TIMBRADO TROCADO em "
                        f"{os.path.basename(caminho)} — {itens}. Esta peça foi gerada com um "
                        f"pacote de timbrado diferente do que está instalado agora. Gere a "
                        f"peça de novo com `build_docx.py --identidade` e entregue a nova.")
            if all(a.get("id") == "timbrado_fora_do_pacote" for a in altas):
                return (f"Entrega de PEÇA BLOQUEADA: TIMBRADO FORA DO PACOTE em "
                        f"{os.path.basename(caminho)} — {itens}. O cabeçalho e o rodapé de "
                        f"uma peça vêm só do pacote que o Dissero serviu ou do timbrado "
                        f"padrão do plugin. Nunca se escreve, copia de outra peça nem ajusta "
                        f"cabeçalho ou rodapé à mão. Gere a peça de novo com `build_docx.py "
                        f"--identidade`; se a recusa continuar, chame "
                        f"perfil_do_advogado(parte=\"identidade\") e grave com "
                        f"`perfil_advogado.py --gravar-identidade <zip>`.")
            return (f"Entrega de PEÇA BLOQUEADA: ELEMENTO OCULTO em "
                    f"{os.path.basename(caminho)} — {itens}. Texto invisível em peça é ato "
                    f"atentatório à dignidade da justiça (CPC, arts. 5º e 77, § 2º). Remova antes "
                    f"de protocolar; a responsabilidade é de quem subscreve.")
    return None















_PROG_LEITURA = frozenset((
    "ls", "dir", "ll", "vdir", "stat", "file", "du", "wc", "tree", "test", "[", "[[", "realpath",
    "readlink", "basename", "dirname", "pwd", "echo", "printf", "true", "false", ":", "sha1sum",
    "sha224sum", "sha256sum", "sha384sum", "sha512sum", "md5sum", "cksum", "b2sum", "shasum",
    "grep", "egrep", "fgrep", "rg", "ag", "cat", "tac", "type", "more", "head", "tail", "tr",


    "cut", "nl", "fold",
    "rm", "del", "erase",
    "rmdir", "unlink", "remove-item", "ri", "mkdir", "md", "cd", "chdir", "pushd", "popd",
    "set-location", "sl", "push-location", "pop-location", "export", "unset", "declare", "local",
    "readonly", "typeset", "set", "rem", "::", "zipinfo", "find", "get-item", "gi",
    "get-childitem", "gci", "test-path", "resolve-path", "rvpa", "split-path", "join-path",
    "get-filehash", "select-string", "sls", "get-acl", "measure-object", "measure", "write-host",
    "write-output", "write", "out-host", "out-null", "select-object", "select", "sort-object",
    "format-list", "fl", "format-table", "ft", "format-wide", "fw", "out-string",
    "convertto-json", "get-itemproperty", "gp", "get-content", "gc", "get-location", "gl",
    "get-date", "write-verbose", "write-warning", "invoke-item", "ii", "explorer", "open",
    "xdg-open", "winword"))

_PROG_COPIA = frozenset(v for v in _VERBOS_MECANISMO if not re.search(r'_|file|copy[0-9a-z]|write', v)) | frozenset((
    "cp", "copy", "mv", "move", "copy-item", "move-item", "rename-item", "install", "ditto",
    "rsync", "scp", "sftp", "tee", "gcp", "gmv", "ginstall", "drive_upload", "out-file",
    "set-content", "add-content", "start-bitstransfer"))
_PROG_PACOTE = ("tar", "zip", "7z", "7za", "compress-archive", "unzip")

_PROG_DINAMICO = ("eval", "invoke-expression", "iex", "invoke-command", "icm", "start-job",
                  "sajb", "start-threadjob", "xargs", "parallel", "watch", "runas", "wsl",
                  "schtasks", "at", "crontab", "su")
_PROG_DEFINICAO = ("function", "filter", "workflow", "alias", "unalias", "set-alias", "new-alias",
                   "sal", "nal")

_PREFIXOS_PROGRAMA = ("env", "command", "builtin", "time", "sudo", "doas", "exec", "nice", "nohup", "setsid",
                      "ionice", "stdbuf", "timeout", "then", "do", "else", "elif", "if", "while",
                      "until", "!", "{", "(", "$(", "@(", "&", "call", "noglob")
_PREFIXO_VALOR = {"sudo": ("-u", "-g", "-h", "-p", "-C", "-r", "-t", "-U", "-D", "-R"),
                  "doas": ("-u", "-C"), "env": ("-u", "-C", "--unset", "--chdir"),
                  "nice": ("-n",), "ionice": ("-c", "-n", "-p"),
                  "timeout": ("-s", "-k", "--signal", "--kill-after"), "time": ("-f", "-o"),
                  "exec": ("-a",), "stdbuf": (), "command": ()}

_DOTNET_LIDO = re.compile(r'^\[(?:System\.)?IO\.(?:File|Path|Directory)\]::(?:Copy|Move|Replace|'
                          r'WriteAll(?:Bytes|Text|Lines)|ReadAll(?:Bytes|Text|Lines)|Exists|'
                          r'GetFileName\w*|GetDirectoryName|GetExtension|GetFullPath|Combine|'
                          r'GetLastWriteTime|GetAttributes)\b', re.I)

_EXT_SCRIPT = {".sh": "posix", ".bash": "posix", ".zsh": "posix", ".ksh": "posix", ".fish": "posix",
               ".ps1": "ps", ".psm1": "ps", ".bat": "cmd", ".cmd": "cmd", ".py": "python",
               ".pyw": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
               ".ts": "javascript", ".vbs": "vbscript", ".vbe": "vbscript", ".wsf": "vbscript",
               ".hta": "vbscript", ".pl": "perl", ".rb": "ruby", ".php": "php", ".r": "r"}
_RE_PYTHON = re.compile(r'^(?:python[\d.]*w?|py|pyw)$')

_PWSH_COM_VALOR = ("-executionpolicy", "-windowstyle", "-workingdirectory", "-configurationname",
                   "-settingsfile", "-inputformat", "-outputformat", "-version", "-psconsolefile",
                   "-custompipename")


def _programa(seg):
    '(posição, token do programa, motivo) do trecho de pipe, depois das atribuições (`X=1`), dos'



    toks = _sem_redirecao(_tokens(seg))
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r'^[A-Za-z_]\w*\+?=', t):
            i += 1
            continue
        b = t.lower()



        if b not in _PREFIXOS_PROGRAMA and re.match(r'^(?:/usr)?(?:/local)?/s?bin/[\w.-]+$', b):
            if _palavra(t) in ("env", "sudo", "doas", "nice", "nohup", "setsid", "ionice", "stdbuf",
                               "timeout", "time"):
                b = _palavra(t)
        if b in _PREFIXOS_PROGRAMA:
            i += 1
            if b in _PREFIXO_VALOR:
                while i < len(toks) and toks[i].startswith("-") and toks[i] not in ("-", "--"):
                    o = toks[i]
                    if b == "env" and (re.match(r'^-[A-Za-z]*S', o) or o.startswith("--split-string")):
                        return i, o, "o `env -S` monta o comando a partir de um texto"
                    i += 2 if o in _PREFIXO_VALOR[b] else 1
                if b == "timeout" and i < len(toks) and re.match(r'^\d', toks[i]):
                    i += 1
            continue
        m = re.match(r'^[$@]?\(+', t)
        if m and len(t) > m.end():
            t = t[m.end():]
        return i, t, None
    return None, None, None


def _nome_escondido(t, tipo):
    'Por que o token do programa não é um nome que o gate lê, ou None: aspas ou escape no meio'


    s = t or ""
    if (len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'" and s[0] not in s[1:-1]
            and re.match(r'^(?:[A-Za-z]:[\\/]|/|\\\\)', s[1:-1])):
        s = s[1:-1]
        if any(c in s for c in "\"'`^") or _EXPANSAO.search(s):
            return "aspas"
        return None
    if any(c in s for c in "\"'"):
        return "aspas"
    if "`" in s or "^" in s or (tipo == "posix" and "\\" in s):
        return "escape"
    if _EXPANSAO.search(s):
        return "variavel"
    return None


def _decodificar_ps(b64):
    """O texto de `-EncodedCommand` (base64 de UTF-16LE), ou None."""
    try:
        return base64.b64decode(_desaspar(b64 or "").strip(), validate=True).decode("utf-16-le")
    except Exception:
        return None


def _script_de(seg, toks, i, p, tipo, t=None):
    'O que o interpretador do trecho roda: ("script", token do arquivo, linguagem, argumentos),'




    resto = toks[i + 1:]
    st = [_desaspar(x) for x in resto]
    entrada = [e for e in _entradas_redirecionadas(_tokens(seg)) if e]

    def arquivo(k, ling):
        return ("script", resto[k], ling, st[k + 1:])

    def da_entrada(ling, motivo):
        return ("script", entrada[0], ling, []) if entrada else ("interp_nao_lido", motivo)

    def com_codigo(k, ling, flags, ate_valor=(), agrupado=None):
        while k < len(st):
            o = st[k]

            if o in flags or (agrupado and re.fullmatch(agrupado, o)):
                return ("codigo", st[k + 1] if k + 1 < len(st) else "", ling)
            pre = next((f for f in flags if f.startswith("--") and o.startswith(f + "=")), None)
            if pre:
                return ("codigo", o[len(pre) + 1:], ling)
            if o == "-":
                return da_entrada(ling, f"`{p} -` lê o programa da entrada")
            if o in ate_valor:
                k += 2
                continue
            if o.startswith("-"):
                k += 1
                continue
            return arquivo(k, ling)
        return da_entrada(ling, f"`{p}` sem arquivo lê o programa da entrada")

    if p in ("source", "."):
        return arquivo(0, tipo) if st else ("interp_nao_lido", f"`{p}` sem arquivo")
    if p in _SHELLS_POSIX:
        k = 0
        while k < len(st) and st[k][:1] in ("-", "+") and st[k] not in ("-", "--"):
            o = st[k]
            if re.match(r'^-[A-Za-z]*c[A-Za-z]*$', o):
                return ("interp_nao_lido", f"o comando de `{p} -c` não foi aberto pelo gate")
            if re.match(r'^-[A-Za-z]*s[A-Za-z]*$', o):
                return da_entrada("posix", f"`{p} -s` lê o script da entrada")
            k += 2 if o in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file") else 1
        if k < len(st) and st[k] == "--":
            k += 1
        if k >= len(st) or st[k] == "-":
            return da_entrada("posix", f"`{p}` sem arquivo lê o script da entrada")
        return arquivo(k, "posix")
    if p in _SHELLS_PS:
        k, wd = 0, False
        while k < len(st):
            o = st[k].lower()
            if o == "-f" or (len(o) >= 3 and "-file".startswith(o)):
                if k + 1 >= len(st):
                    return ("interp_nao_lido", "`-File` sem arquivo")
                if wd and _relativo(st[k + 1]):
                    return ("interp_nao_lido", "o script relativo roda em outra pasta (`-WorkingDirectory`)")
                return arquivo(k + 1, "ps")
            if o in ("-e", "-ec") or (len(o) >= 3 and "-encodedcommand".startswith(o)):
                texto = _decodificar_ps(st[k + 1] if k + 1 < len(st) else "")
                if texto is None:
                    return ("interp_nao_lido", "o comando codificado (`-EncodedCommand`) não se decodifica")
                return ("codificado", texto)
            if len(o) >= 2 and "-command".startswith(o):
                return ("interp_nao_lido", f"o comando de `{p} -Command` não foi aberto pelo gate")
            if o.startswith("-"):
                com_valor = o in ("-ex", "-ep", "-w", "-wd", "-v", "-if", "-of") or (
                    len(o) >= 3 and any(n.startswith(o) for n in _PWSH_COM_VALOR))
                wd = wd or o == "-wd" or (len(o) >= 4 and "-workingdirectory".startswith(o))
                k += 2 if com_valor else 1
                continue
            if wd and _relativo(st[k]):
                return ("interp_nao_lido", "o script relativo roda em outra pasta (`-WorkingDirectory`)")
            return arquivo(k, "ps")
        return da_entrada("ps", f"`{p}` sem arquivo lê o script da entrada")
    if _RE_PYTHON.match(p):
        k = 0
        while k < len(st):
            o = st[k]
            if o == "-":
                return da_entrada("python", f"`{p} -` lê o programa da entrada")
            if o == "--check-hash-based-pycs":
                k += 2
                continue
            if o.startswith("-") and not o.startswith("--"):




                fim = next((j for j, ch in enumerate(o[1:], 1) if ch in "cmXW"), None)
                if fim is not None:
                    ch, colado = o[fim], o[fim + 1:]
                    if ch == "c":
                        return ("codigo", colado or (st[k + 1] if k + 1 < len(st) else ""), "python")
                    if ch == "m":
                        return ("interp_nao_lido", f"`{p} -m` roda um módulo que o gate não lê")
                    k += 1 if colado else 2
                    continue
            if o.startswith("-"):
                k += 1
                continue
            return arquivo(k, "python")
        return da_entrada("python", f"`{p}` sem arquivo lê o programa da entrada")
    if p in ("node", "nodejs"):
        return com_codigo(0, "javascript", ("-e", "--eval", "-p", "--print", "-pe"),
                          ("-r", "--require", "--import", "--loader", "--experimental-loader", "-C"))
    if p in ("deno", "bun", "tsx", "ts-node"):
        if st[:1] == ["eval"]:
            return ("codigo", st[1] if len(st) > 1 else "", "javascript")
        return com_codigo(1 if st[:1] in (["run"], ["x"]) else 0, "javascript",
                          ("-e", "--eval", "-p", "--print"))
    if p in ("perl", "ruby"):
        return com_codigo(0, p, ("-e", "-E"), ("-I", "-M", "-r"), agrupado=r'-[A-Za-z]*[eE]')
    if p == "php":
        return com_codigo(0, "php", ("-r",), ("-f", "-c", "-d"))
    if p == "rscript":
        return com_codigo(0, "r", ("-e",))
    if p in ("wscript", "cscript", "mshta"):
        k = next((n for n, o in enumerate(st) if not o.startswith("//")), None)
        if k is None:
            return ("interp_nao_lido", f"`{p}` sem script")
        return arquivo(k, _EXT_SCRIPT.get(os.path.splitext(st[k])[1].lower(), "vbscript"))
    t = t if t is not None else toks[i]
    nome = _desaspar(t)
    ext = os.path.splitext(nome)[1].lower()
    if ext in _EXT_SCRIPT:
        return ("script", t, _EXT_SCRIPT[ext], st)
    if re.match(r'^\.{1,2}[\\/]', nome) and ext != ".exe":
        return ("script", t, tipo, st)
    return None


def _texto_executavel_ps(s):
    'O texto do PowerShell que roda como código: sem o conteúdo das aspas simples, e das aspas'


    out, aspa, prof, i, n = [], None, 0, 0, len(s or "")
    while i < n:
        c = s[i]
        if aspa == "'":
            out.append("'" if c == "'" else " ")
            if c == "'":
                aspa = None
        elif aspa == '"' and prof == 0:
            if c == "`" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if s.startswith("$(", i):
                out.append("$(")
                prof = 1
                i += 2
                continue
            out.append('"' if c == '"' else " ")
            if c == '"':
                aspa = None
        elif aspa == '"':
            prof += c == "("
            prof -= c == ")"
            out.append(c)
        elif c in "'\"":
            aspa = c
            out.append(c)
        else:
            out.append(c)
        i += 1
    return "".join(out)




_METODO_PS = re.compile(r'(?:[)\]]|\$[\w:]+)(?:\s*\.\s*\w+)*\s*\.\s*\w+\s*\(')


def _chamada_metodo_ps(seg, i=None):
    'O nome do método que o trecho do PowerShell chama fora de aspas, ou None: método sobre o'


    texto = _texto_executavel_ps(seg)
    m = _METODO_PS.search(texto)
    if m:
        return re.search(r'(\w+)\s*\($', m.group(0)).group(1)
    toks = _sem_redirecao(_tokens(seg))
    for t in toks[(i or 0) + 1:]:
        m = re.search(r'::\s*(\w+)\s*\(', _texto_executavel_ps(t))
        if m:
            return m.group(1)
    return None


def _classe(seg, tipo):
    '(classe, detalhe) do trecho de pipe pelo programa que ele roda. Classes: "atribuicao",'




    i, t, motivo = _programa(seg)
    if motivo:
        return "nao_lido", motivo, i
    if t is None:
        return "atribuicao", None, None
    toks = _sem_redirecao(_tokens(seg))
    if t.startswith("$") and tipo == "ps":

        m = re.match(r'^\$[\w:]+\s*[+\-*/]?=', t)
        prox = toks[i + 1] if i + 1 < len(toks) else ""
        if m or re.match(r'^[+\-*/]?=', prox):
            resto = seg.split("=", 1)[1].strip() if "=" in seg else ""
            if not resto or resto[:1] in "\"'0123456789" or resto.startswith(("@{", "@(", "$true",
                                                                                "$false", "$null")):
                metodo = _chamada_metodo_ps(resto) if resto[:1] not in "\"'0123456789" else None
                return ("metodo", metodo, i) if metodo else ("atribuicao", None, i)
            return _classe(resto, tipo)
    if tipo == "ps":

        metodo = _chamada_metodo_ps(seg, i)
        if metodo:
            return "metodo", metodo, i
    if t.startswith("$") and tipo == "ps":
        return "expressao", t, i
    if re.match(r'^\[[\w.]+\]::', t):
        if _DOTNET_LIDO.match(t):
            return ("copia" if re.search(r'::(?:Copy|Move|Replace|WriteAll)', t, re.I) else "leitura"), t, i
        return "expressao", t, i
    esc = _nome_escondido(t, tipo)
    if esc:
        return "escondido", t, i
    p = _palavra(t)
    if p in _PROG_DINAMICO:
        return "dinamico", p, i
    if (p in _PROG_DEFINICAO or re.match(r'^[\w.:-]+\(\)$', p)
            or (i + 1 < len(toks) and toks[i + 1] == "()")):
        return "definicao", p, i
    info = _script_de(seg, toks, i, p, tipo, t)
    if info:
        return info[0], info, i
    resto = [_desaspar(x) for x in toks[i + 1:]]
    baixo = [x.lower() for x in resto]
    if p in _PROG_PACOTE:
        return _classe_pacote(p, resto) + (i,)
    if p == "certutil":
        return ("leitura", p, i) if "-hashfile" in baixo else ("desconhecido", p, i)
    if p in ("start", "start-process", "saps"):




        ops = [x for x in resto if x and not x.startswith("-")
               and not (x.startswith("/") and "/" not in x[1:])]
        if ops and all(_eh_docx(o) for o in ops):
            return "leitura", p, i
        return "nao_lido", f"o `{p}` roda outro programa, que o gate não lê", i
    if p == "find" and any(x in ("-exec", "-execdir", "-ok", "-okdir") for x in baixo):
        return "nao_lido", "o `find -exec` roda outro programa em cada arquivo", i
    if p in _PROG_COPIA:
        return "copia", p, i
    if p in _PROG_LEITURA:
        return "leitura", p, i
    return "desconhecido", p, i


def _classe_pacote(p, args):
    'Classe do tar, zip, 7z, Compress-Archive e unzip pelo modo: criar ou acrescentar é cópia'



    pos = [a for a in args if a and not a.startswith("-")]
    if p in ("zip", "compress-archive"):
        return "copia", p
    if p == "tar":
        letras = "".join(a.lstrip("-") for a in args[:1] if re.fullmatch(r'-?[A-Za-z]+', a or ""))
        letras += "".join(a[1:] for a in args[1:] if re.fullmatch(r'-[A-Za-z]+', a or ""))
        longas = {a for a in args if a.startswith("--")}
        if set(letras) & set("cruA") or longas & {"--create", "--append", "--update", "--concatenate"}:
            return "copia", p
        if "t" in letras or "--list" in longas:
            return "leitura", p
        destino = next((args[k + 1] for k, a in enumerate(args[:-1]) if a in ("-C", "--directory")), None)
        if any(_eh_docx(a) for a in pos[1:]) or not (destino and _is_tmp(destino)):
            return "nao_lido", "o `tar` extrai arquivos fora da pasta temporária"
        return "leitura", p
    if p in ("7z", "7za"):
        modo = pos[0].lower() if pos else ""
        if modo in ("a", "u"):
            return "copia", p
        if modo in ("l", "t", "h", "i"):
            return "leitura", p
        if modo in ("x", "e"):
            saida = next((a[2:] for a in args if a.startswith("-o")), "")
            if any(_eh_docx(a) for a in pos[2:]) or not (saida and _is_tmp(saida)):
                return "nao_lido", "o `7z` extrai arquivos fora da pasta temporária"
            return "leitura", p
        return "nao_lido", f"o `7z {modo}` altera o pacote por dentro"

    opcoes = "".join(a[1:] for a in args if re.fullmatch(r'-[A-Za-z]+', a or ""))
    if set(opcoes) & set("lvtzZpc"):
        return "leitura", p
    destino = next((args[k + 1] for k, a in enumerate(args[:-1]) if a == "-d"), None)
    if any(_eh_docx(a) for a in pos[1:]) or not (destino and _is_tmp(destino)):
        return "nao_lido", "o `unzip` extrai arquivos fora da pasta temporária"
    return "leitura", p







_NOME_VAR = r'[A-Za-z_][A-Za-z0-9_]*'
_ATRIBUICAO = re.compile(r'(?:export[ \t]+)?(' + _NOME_VAR + r')=(?:\'([^\']*)\'|"([^"$`\\]*)"|'
                         r'([^\s\'"$`\\;&|<>(){}*?\[\]~#]*))(?=[ \t]*(?:;|&&|\|\||\n|$))')
_LIGA_NOME = (r'\b(?:read|for|local|declare|typeset|unset|readonly|let|mapfile|readarray|getopts|'
              r'select)\b[^;\n&|]*\b{}\b')


def _estado_posix(cmd):
    """Para cada posição do comando, (aspas abertas, profundidade de parênteses e chaves)."""
    est, q, prof, i = [], "", 0, 0
    while i < len(cmd):
        c = cmd[i]
        est.append((q, prof))
        if q == "'":
            q = "" if c == "'" else q
        elif c == "\\" and i + 1 < len(cmd):
            est.append((q, prof))
            i += 2
            continue
        elif q == '"':
            q = "" if c == '"' else q
        elif c == "$" and cmd[i + 1:i + 2] == "{":
            fim = cmd.find("}", i)
            fim = len(cmd) - 1 if fim < 0 else fim
            est.extend([(q, prof)] * (fim - i))
            i = fim + 1
            continue
        elif c in "'\"":
            q = c
        elif c in "({":
            prof += 1
        elif c in ")}":
            prof = max(0, prof - 1)
        i += 1
    return est


def _resolver_variaveis(cmd):
    'O comando com cada `$NOME`/`${NOME}` trocado pelo valor da atribuição literal do mesmo'

    if not (isinstance(cmd, str) and "=" in cmd and "$" in cmd) or "<<" in cmd or "$'" in cmd:
        return cmd
    est = _estado_posix(cmd)
    valores = {}
    for m in _ATRIBUICAO.finditer(cmd):
        ini = m.start()
        if ini >= len(est) or est[ini] != ("", 0):
            continue
        antes = cmd[:ini].rstrip(" \t")
        if antes and not (antes.endswith(("\n", ";")) and not antes.endswith(";;")):
            continue
        nome = m.group(1)
        v = next(g for g in (m.group(2), m.group(3), m.group(4)) if g is not None)
        if m.group(2) is not None and re.search(r'["\\$`]', v):
            continue
        valores.setdefault(nome, []).append((m.end(), v))
    trocas = []
    for nome, lst in valores.items():
        if (len(lst) != 1 or len(re.findall(r'(?<![\w$])' + nome + r'\+?=', cmd)) != 1
                or re.search(_LIGA_NOME.format(nome), cmd)):
            continue
        fim, v = lst[0]
        livre = not re.search(r'[\s*?\[\]{}~\'"]', v)
        for m in re.finditer(r'\$(?:\{' + nome + r'\}|' + nome + r'(?![A-Za-z0-9_]))', cmd):
            if m.start() < fim or m.start() >= len(est) or (m.start() and cmd[m.start() - 1] == "\\"):
                continue
            q = est[m.start()][0]
            if q == "'" or (q == "" and not livre):
                continue
            trocas.append((m.start(), m.end(), v))
    for a, b, v in sorted(trocas, reverse=True):
        cmd = cmd[:a] + v + cmd[b:]
    return cmd


def _resolver_variaveis_evento(evento, tool_name):
    """O evento com o comando de shell POSIX resolvido por `_resolver_variaveis`."""
    ti = evento.get("tool_input")
    if not (_eh_shell(tool_name) and isinstance(ti, dict) and isinstance(ti.get("command"), str)
            and _tipo_da_chamada(tool_name, ti) == "posix"):
        return evento
    novo = _resolver_variaveis(ti["command"])
    if novo == ti["command"]:
        return evento
    return dict(evento, tool_input=dict(ti, command=novo))


_SUBPASTAS_PLUGIN = ("skills", "hooks", "_shared", "build", "scripts")


def _expandir_raiz_plugin(s):
    '`${CLAUDE_PLUGIN_ROOT}` (e as formas do PowerShell e do cmd) vira a raiz deste plugin, e a'

    casa = os.path.expanduser("~")
    for v, real in (("${CLAUDE_PLUGIN_ROOT}", _ROOT), ("$CLAUDE_PLUGIN_ROOT", _ROOT),
                    ("$env:CLAUDE_PLUGIN_ROOT", _ROOT), ("%CLAUDE_PLUGIN_ROOT%", _ROOT),
                    ("${HOME}", casa), ("$HOME", casa), ("$env:USERPROFILE", casa),
                    ("$env:HOME", casa), ("%USERPROFILE%", casa)):
        if v.lower() in s.lower():
            s = re.sub(re.escape(v), lambda _m, r=real: r.replace("\\", "/"), s, flags=re.I)
    return s


def _script_do_plugin(caminho):
    """O script fica numa pasta de código deste plugin?"""
    try:
        real = _chave_caminho(os.path.realpath(caminho))
        raiz = os.path.realpath(_ROOT)
    except (OSError, ValueError):
        return False
    return any(real.startswith(_chave_caminho(os.path.join(raiz, sp)) + os.sep)
               for sp in _SUBPASTAS_PLUGIN)



def _real(p):
    """Caminho real (junções e links resolvidos, sobre o maior trecho que existe), ou None."""
    try:
        return os.path.realpath(p)
    except (OSError, ValueError):
        return None


def _raiz_do_caso(p):
    'A pasta raiz do caso em cuja árvore o caminho fica (a do arquivo de controle, ou a raiz'

    achado = _marcador_de_caso(p)
    if achado:
        return achado[0]
    k = _chave_caminho(p)
    for r in _raizes_registradas() or []:
        kr = _chave_caminho(r).rstrip("\\/")
        if k == kr or k.startswith(kr + os.sep):
            return r
    return None


def _mesmo_caso(a, b):
    """As duas raízes de caso são o mesmo caso (uma dentro da outra conta)?"""
    ka, kb = (_chave_caminho(_real(x) or x).rstrip("\\/") for x in (a, b))
    return ka == kb or ka.startswith(kb + os.sep) or kb.startswith(ka + os.sep)


_LEMBRETE = re.compile(r'<system-reminder>.*?(?:</system-reminder>|\Z)', re.S)
_ABRE_COLADO = re.compile(r'<pasted_content\b([^>]*)>', re.I)
_FECHA_COLADO = re.compile(r'</pasted_content\b([^>]*)>', re.I)
_ID_COLADO = re.compile(r'(?<![\w-])id\s*=\s*(?:"([^"]*)"|' + r"'([^']*)')", re.I)


def _sem_colado(texto):
    'A mensagem sem o texto colado e sem lembrete do sistema: só o que o advogado digitou, ou'





    s = texto or ""
    ids = []
    for m in _ABRE_COLADO.finditer(s):
        mid = _ID_COLADO.search(m.group(1))
        if not mid:
            return None
        ids.append(mid.group(1) if mid.group(1) is not None else mid.group(2))
    if len(ids) != len(set(ids)):
        return None



    fechos = []
    for m in _FECHA_COLADO.finditer(s):
        mid = _ID_COLADO.search(m.group(1))
        fechos.append(None if not mid else (mid.group(1) if mid.group(1) is not None else mid.group(2)))
    if len(fechos) != len(set(fechos)) or any(f not in ids for f in fechos):
        return None
    out, i = [], 0
    while True:
        m = _ABRE_COLADO.search(s, i)
        if not m:
            out.append(s[i:])
            break
        out.append(s[i:m.start()] + " ")
        mid = _ID_COLADO.search(m.group(1))
        x = re.escape(mid.group(1) if mid.group(1) is not None else mid.group(2))
        fecho = re.compile(r'</pasted_content\s+id\s*=\s*(?:"' + x + r'"|' + "'" + x + "'" + r')\s*>', re.I)
        f = fecho.search(s, m.end())
        if not f:
            break
        i = f.end()
    return _LEMBRETE.sub(" ", "".join(out))


_GLOB = re.compile(r'[*?\[]')



_EXT_ODF_ENVIO = (".odt", ".ott")
_TETO_TEXTO_ENVIO = 2_000_000


_VOCATIVO_PECA = re.compile(r"\bEXCELENT[ÍI]SSIM[OA]S?\b|\bEXM[OA]\.?\s+SRA?\b|(?i:\bexcelent[íi]ssim[oa]s?"
                            r"\s+(?:senhora?|sra?\.?|doutora?|ju[íi]za?|desembargadora?|ministr[oa])\b)"
                            r"|(?i:\b[AÀ]O?\s+(?:(?:MM\.?|meritíssim[oa]|d[ou]uto|egrégi[oa]|colend[oa])\s+)?"
                            r"(?:ju[íi]zo|tribunal|turma|câmara|vara)\s+(?:d[aeo]s?|regional|superior|federal)\b)")



_LINHAS_DE_ABERTURA = 15
_FECHO_PECA = re.compile(r"\bTermos\s+em\s+que\b|\bNestes\s+termos\b|\bN\.\s*termos\b"
                         r"|\bpede(?:m)?(?:\s+e\s+espera(?:m)?)?\s+deferimento\b", re.I)
_SHINGLE = 8
_SOBREPOSICAO_PECA = 0.3
_SHINGLES_MINIMOS = 20


def _ler_texto_enviado(p, ext):
    'Texto do arquivo enviado: o content.xml do ODF, ou os bytes como UTF-8. Arquivo sem extensão'

    try:
        if ext in _EXT_ODF_ENVIO and zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                xml = z.read("content.xml")[:_TETO_TEXTO_ENVIO].decode("utf-8", "replace")
            xml = re.sub(r"</text:(?:p|h)>", "\n", xml)
            return html.unescape(re.sub(r"<[^>]+>", "", xml))

        with open(p, "rb") as fh:
            dados = fh.read(_TETO_TEXTO_ENVIO)
    except Exception:
        return None
    if ext == "" and b"\x00" in dados[:4096]:
        return None
    return dados.decode("utf-8", "replace")


def _abre_com(rx, texto):
    '`rx` casa no começo de uma das primeiras linhas não vazias do texto (marcação de Markdown e'

    linhas = 0
    for linha in (texto or "").splitlines():
        limpa = re.sub(r"<[^>]+>", "", linha)
        limpa = re.sub(r"^[\s#>*_|\-–—=`~]+", "", limpa)
        if not limpa.strip():
            continue
        if rx.match(limpa):
            return True
        linhas += 1
        if linhas >= _LINHAS_DE_ABERTURA:
            break
    return False


def _texto_do_docx(caminho):
    """Texto corrido do word/document.xml, sem depender do python-docx; "" se não se lê."""
    try:
        if os.path.getsize(caminho) > 50_000_000:
            return ""
        with zipfile.ZipFile(caminho) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return ""
    xml = re.sub(r"</w:p>", "\n", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def _shingles(texto):
    palavras = re.findall(r"\w+", (texto or "").lower())
    return {" ".join(palavras[i:i + _SHINGLE]) for i in range(max(0, len(palavras) - _SHINGLE + 1))}


def _deny(reason):
    if _CMD_ENTREGAR not in reason:
        reason = f"{reason} {_MSG_OFICIAL}"
    return _deny_sem_oficial(reason)


def _deny_sem_oficial(reason):
    """Deny sem o remédio da entrega da peça: para a recusa que não envolve peça."""
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


























def _decidir_minuta(evento, tool_name, cwd):
    """O deny por texto oculto no .docx que sai, ou None. Nunca levanta."""
    try:
        resolvido = _resolver_variaveis_evento(evento, tool_name)
    except Exception:
        resolvido = evento
    tool_input = resolvido.get("tool_input") or {}
    try:
        with _modo_caminho(tool_name, tool_input, cwd):
            alvo = _detectar_entrega(tool_name, tool_input)
            if not alvo:
                return None
            try:
                origens = _origens_da_entrega(tool_name, tool_input, _cwd_da_chamada(tool_name, tool_input, cwd))
            except Exception:
                origens = []
            oculto = _varredura_bloqueia(resolvido, alvo, origens)
    except Exception:
        return None
    return _deny(oculto) if oculto else None


def decidir(evento):
    """Núcleo: dado o evento PreToolUse, retorna o dict de deny OU None (sem decisão/allow)."""
    if not isinstance(evento, dict):
        return None
    tool_name = evento.get("tool_name")
    if not (isinstance(tool_name, str) and tool_name):
        return None
    cwd = evento.get("cwd") if (isinstance(evento.get("cwd"), str) and evento.get("cwd").strip()) else os.getcwd()
    return _decidir_minuta(evento, tool_name, cwd)







_PODE_SER_PECA = re.compile(r'\.docx|\.d[\\`^\'"]*o[\\`^\'"]*c[\\`^\'"]*[x?*\[]|wordprocessingml|'
                            r'google-apps\.document', re.I)

_RODA_SCRIPT = re.compile(r'\.(?:sh|bash|ps1|psm1|bat|cmd|py|pyw|js|mjs|cjs|ts|vbs|pl|rb|php)\b|'
                          r'\b(?:source|bash|zsh|pwsh|powershell)\b|-EncodedCommand|\s-e(?:nc|c)?\s', re.I)


def pode_ser_peca(texto):
    return isinstance(texto, str) and bool(_PODE_SER_PECA.search(texto))


def _roda_script(raw):
    """O comando do evento (ou o texto inteiro, se o evento não se lê) roda script?"""
    try:
        ev = json.loads(raw)
        texto = _comando_de(ev.get("tool_input")) if isinstance(ev, dict) else None
    except Exception:
        texto = raw
    return isinstance(texto, str) and bool(_RODA_SCRIPT.search(texto))


def _deny_falha(erro):
    'Deny da falha do próprio gate. Nomeia só o tipo do erro: a mensagem dele pode trazer o'

    return _deny(f"Entrega de PEÇA BLOQUEADA: o gate de entrega falhou ao analisar esta chamada "
                 f"({erro}) e não libera a peça sem a análise. {_MSG_OFICIAL} Se a falha "
                 f"continuar também no comando oficial, avise o advogado de que a peça não foi "
                 f"entregue.")


def main():
    'Lê o evento do stdin e imprime o deny, quando há. A falha do gate (evento ilegível ou'


    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        ev = json.loads(raw) if raw and raw.strip() else {}
        saida = decidir(ev)
    except Exception as e:
        saida = _deny_falha(type(e).__name__) if (pode_ser_peca(raw) or _roda_script(raw)
                                                  or _VOCATIVO_PECA.search(raw or "")) else None
    if saida:
        print(json.dumps(saida, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
