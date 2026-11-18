#!/bin/bash
# PreToolUse, em TODA ferramenta: com a marca de sondagem da sessão de pé, nega a ferramenta; com ou sem
# marca, nega a ferramenta que mexe na própria proteção (ver gate_sigilo.py). O hooks.json invoca por bash.
#
# CAMINHO RÁPIDO. Este hook roda a cada chamada de ferramenta. Sem nenhuma marca de sondagem
# gravada, que é o caso de quase toda chamada, não procura nem abre o Python: lê só o começo da entrada
# (8 KB, pelo próprio bash, sem subir processo) e sai aqui mesmo, a menos que ela cite um alvo da
# proteção (hooks, settings, a pasta do Dissero, a data e a hora do sistema, o desligamento do plugin).
# Só então, ou com marca na pasta, abre o Python, que decide (o mesmo corpo do gate_sigilo.sh). A janela
# e o contador da sessão não terminam em .json e não desligam o caminho rápido.
_B="${DSR_CASO_BASE:-$HOME/.dissero}/sigilo"
_LIDO=""
# Sem processo: o glob sem correspondência fica literal, e o -e falha.
for _f in "$_B"/*.json; do break; done
if [ ! -e "$_f" ]; then
  _IN=""
  IFS= read -r -N 8192 _IN || :
  _LIDO=1
  # Só a entrada da ferramenta conta: a pasta de trabalho e a transcrição, que vêm antes, podem ter
  # qualquer nome («Sigilo», «settings»). Expansão do próprio bash, sem processo.
  _T="${_IN#*\"tool_input\"}"
  _ALVO=""
  shopt -s nocasematch
  # Comando que não coube nos 8 KB lidos: o alvo pode estar depois do enchimento, e o Python confere a
  # entrada inteira. Ferramenta de arquivo traz o caminho antes do conteúdo e fica no caminho rápido.
  if [ "${#_IN}" -ge 8192 ]; then
    case "$_IN" in
      *'"tool_name":"Write"'*|*'"tool_name": "Write"'*|*'"tool_name":"Edit"'*|*'"tool_name": "Edit"'*|*'"tool_name":"MultiEdit"'*|*'"tool_name": "MultiEdit"'*|*'"tool_name":"Read"'*|*'"tool_name": "Read"'*|*'"tool_name":"NotebookEdit"'*|*'"tool_name": "NotebookEdit"'*) ;;
      *) _ALVO=1 ;;
    esac
  fi
  # Base própria dos marcadores (DSR_CASO_BASE): o nome da pasta dela também é alvo. Sem ela, «.dissero» basta,
  # e a pasta de um caso chamada «Sigilo» não sobe o Python a cada leitura.
  if [ -n "$DSR_CASO_BASE" ]; then
    _U="${DSR_CASO_BASE%[/\\]}"; _U="${_U##*[/\\]}"
    [ -n "$_U" ] && case "$_T" in *"$_U"*) _ALVO=1 ;; esac
  fi
  if [ -z "$_ALVO" ]; then
    case "$_T" in
      *hooks*|*settings*|*.dissero*|*disableallhooks*|*'claude plugin'*|*claude-plugin*|*installed_plugins*|*known_marketplaces*) ;;
      *publicar.py*|*wrangler.jsonc*|*'/python"'*|*'/python3"'*|*'/python.exe"'*|*'\\python"'*|*'\\python3"'*|*'\\python.exe"'*) ;;
      *'plugins/cache/dissero '*|*'plugins/cache/dissero"'*|*'plugins/cache/dissero/ '*|*'.claude/plugins '*|*'.claude/plugins"'*|*'.claude/plugins/ '*|*'.claude '*|*'.claude"'*|*'.claude/ '*) ;;
      *'date -s'*|*'date --set'*|*'date '[0-9]*|*'time '[0-9]*|*set-date*|*timedatectl*|*w32tm*|*hwclock*|*faketime*|*setsystemtime*|*setlocaltime*) ;;
      *) exit 0 ;;
    esac
  fi
  shopt -u nocasematch
fi
export PYTHONUTF8=1
_PYW() { _W=""; case "$1" in */*) _W="$1"; return ;; esac; local IFS=:; for _d in $PATH; do if [ -x "$_d/$1" ] || [ -x "$_d/$1.exe" ]; then _W="$_d/$1"; return; fi; done; }
# Sonda com memória (16/11/2026): o interpretador que passou na sonda e o executável real dele
# (sys.executable) ficam em ~/.dissero/python_ok; enquanto o atalho for o mesmo e o registro for mais
# novo que ele, o hook roda direto no executável real, sem sonda e sem o lançador do atalho.
# Cada subida do Python custa ~0,5 s nesta máquina, e sob carga o hook estourava o tempo-limite.
# A memória só vale com um executável de nome Python (ataque de sondagem à rodada 3: «/usr/bin/true» no
# terceiro campo desligava os hooks). Fora disso a sonda roda e regrava a memória, o que conserta os outros hooks.
_PYOK="${HOME:-/tmp}/.dissero/python_ok"
PY=""; for _v in 1 2; do for _c in python3 python "py -3" /opt/homebrew/bin/python3 /usr/local/bin/python3; do _PYW "${_c%% *}"; [ -n "$_W" ] || continue; case "$_W" in */WindowsApps/*) [ "$_v" = 2 ] || continue ;; *) [ "$_v" = 1 ] || continue ;; esac; _M=""; [ -f "$_PYOK" ] && { IFS= read -r _M < "$_PYOK" || :; }; _X="${_M##*|}"; if [ -n "$_PYOK" ] && [ "$_PYOK" -nt "$_W" ] && [ "${_M%|*}" = "$_c|$_W" ] && case "${_X##*/}" in ""|python*|Python*) true ;; *) false ;; esac; then case "$_X" in *" "*|"") PY="$_c" ;; *) if [ -x "$_X" ]; then PY="$_X"; else PY="$_c"; fi ;; esac; break 2; fi; $_c -c "import sys; sys.exit(sys.version_info < (3, 9))" </dev/null >/dev/null 2>&1 && { PY="$_c"; _X="$($_c -c "import sys; print(sys.executable)" </dev/null 2>/dev/null)"; _X="${_X%$'\r'}"; _X="${_X//\\/\/}"; case "$_X" in *" "*|"") ;; *) [ -x "$_X" ] && PY="$_X" ;; esac; [ -n "$_PYOK" ] && mkdir -p "${_PYOK%/*}" 2>/dev/null && printf '%s' "$_c|$_W|$_X" > "$_PYOK.$$" 2>/dev/null && mv -f "$_PYOK.$$" "$_PYOK" 2>/dev/null; break 2; }; done; done
[ -z "$PY" ] && exit 0
RAIZ="${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}}"
# A entrada já lida volta inteira ao Python: o começo guardado e o resto ainda no tubo.
if [ -n "$_LIDO" ]; then
  { printf '%s' "$_IN"; cat; } | $PY "$RAIZ/hooks/gate_sigilo.py" 2>/dev/null
else
  $PY "$RAIZ/hooks/gate_sigilo.py" 2>/dev/null
fi
exit 0
