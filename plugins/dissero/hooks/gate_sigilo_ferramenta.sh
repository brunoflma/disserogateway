#!/bin/bash
# PreToolUse, em TODA ferramenta: com a marca de sondagem da sessão de pé, nega a ferramenta
# (ver gate_sigilo.py). O hooks.json invoca por bash.
#
# CAMINHO RÁPIDO. Este hook roda a cada chamada de ferramenta. Sem nenhuma marca de sondagem
# gravada, que é o caso de quase toda chamada, sai aqui mesmo: não lê a entrada, não procura nem
# abre o Python. Só com marca na pasta abre o Python, que decide (o mesmo corpo do gate_sigilo.sh).
_B="${DSR_CASO_BASE:-$HOME/.dissero}/sigilo"
ls "$_B"/*.json >/dev/null 2>&1 || exit 0
export PYTHONUTF8=1
_PYW() { _W=""; case "$1" in */*) _W="$1"; return ;; esac; local IFS=:; for _d in $PATH; do if [ -x "$_d/$1" ] || [ -x "$_d/$1.exe" ]; then _W="$_d/$1"; return; fi; done; }
PY=""; for _v in 1 2; do for _c in python3 python "py -3" /opt/homebrew/bin/python3 /usr/local/bin/python3; do _PYW "${_c%% *}"; [ -n "$_W" ] || continue; case "$_W" in */WindowsApps/*) [ "$_v" = 2 ] || continue ;; *) [ "$_v" = 1 ] || continue ;; esac; $_c -c "import sys; sys.exit(sys.version_info < (3, 9))" </dev/null >/dev/null 2>&1 && { PY="$_c"; break 2; }; done; done
[ -z "$PY" ] && exit 0
RAIZ="${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}}"
$PY "$RAIZ/hooks/gate_sigilo.py" 2>/dev/null
exit 0
