#!/bin/bash
# PreToolUse, só aviso: lembra o intake e o medir_completude quando se começa a redigir prosa
# (.md) com o briefing da peça incompleto, e o squad quando a peça o exige (ver
# aviso_completude.py). Nunca bloqueia. Fail-safe: exit 0 sempre; STDOUT (aviso) preservado.
export PYTHONUTF8=1
# Probe de execução real, e não `command -v`: o atalho python3 da Microsoft Store existe no
# PATH e sai sem rodar. Stdin isolado para o probe não consumir o evento.
# Python 3.9 ou superior (o /usr/bin/python3 do macOS é o 3.9); aberto pelo macOS sem o PATH do
# Homebrew (o Claude Code lançado pela interface), tenta também os dois lugares dele.
# Duas voltas: na primeira, todo candidato que NÃO mora em WindowsApps; na segunda, só os de lá.
# No Windows, python3/python de WindowsApps é o atalho da Microsoft Store, lançado por um stub que
# custa de 1 a 2 s por chamada (medido em 09/11/2026: 1,7 s contra 0,5 s do Python instalado), e o
# hook paga duas vezes, na sonda e na execução. Ele fica como último recurso, nunca excluído.
# A pasta de cada candidato sai de um laço sobre o PATH só com builtins: `$(command -v ...)` abriria
# um subshell por candidato, e numa máquina com criação de processo lenta cada um custa meio segundo.
_PYW() { _W=""; case "$1" in */*) _W="$1"; return ;; esac; local IFS=:; for _d in $PATH; do if [ -x "$_d/$1" ] || [ -x "$_d/$1.exe" ]; then _W="$_d/$1"; return; fi; done; }
# Sonda com memória (16/11/2026): o interpretador que passou na sonda e o executável real dele
# (sys.executable) ficam em ~/.dissero/python_ok; enquanto o atalho for o mesmo e o registro for mais
# novo que ele, o hook roda direto no executável real, sem sonda e sem o lançador do atalho.
# Cada subida do Python custa ~0,5 s nesta máquina, e sob carga o hook estourava o tempo-limite.
_PYOK="${HOME:-/tmp}/.dissero/python_ok"
PY=""; for _v in 1 2; do for _c in python3 python "py -3" /opt/homebrew/bin/python3 /usr/local/bin/python3; do _PYW "${_c%% *}"; [ -n "$_W" ] || continue; case "$_W" in */WindowsApps/*) [ "$_v" = 2 ] || continue ;; *) [ "$_v" = 1 ] || continue ;; esac; _M=""; [ -f "$_PYOK" ] && { IFS= read -r _M < "$_PYOK" || :; }; _X="${_M##*|}"; if [ -n "$_PYOK" ] && [ "$_PYOK" -nt "$_W" ] && [ "${_M%|*}" = "$_c|$_W" ]; then case "$_X" in *" "*|"") PY="$_c" ;; *) if [ -x "$_X" ]; then PY="$_X"; else PY="$_c"; fi ;; esac; break 2; fi; $_c -c "import sys; sys.exit(sys.version_info < (3, 9))" </dev/null >/dev/null 2>&1 && { PY="$_c"; _X="$($_c -c "import sys; print(sys.executable)" </dev/null 2>/dev/null)"; _X="${_X%$'\r'}"; _X="${_X//\\/\/}"; case "$_X" in *" "*|"") ;; *) [ -x "$_X" ] && PY="$_X" ;; esac; [ -n "$_PYOK" ] && mkdir -p "${_PYOK%/*}" 2>/dev/null && printf '%s' "$_c|$_W|$_X" > "$_PYOK.$$" 2>/dev/null && mv -f "$_PYOK.$$" "$_PYOK" 2>/dev/null; break 2; }; done; done
[ -z "$PY" ] && exit 0
# RAIZ em cascata: CLAUDE_PLUGIN_ROOT, CODEX_PLUGIN_ROOT, pai do wrapper.
RAIZ="${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}}"
$PY "$RAIZ/hooks/aviso_completude.py" 2>/dev/null
exit 0
