#!/bin/bash
# PreToolUse: gate de entrega. Barra .docx levado a destino final ou enviado a upload sem
# `estado_peca pode-entregar` liberado (ver gate_entrega.py). A decisão vai no JSON
# (permissionDecision:"deny"); entrega liberada passa em silêncio.
#
# FALHA FECHADA: sem Python, ou com o .py saindo com erro, o evento que pode carregar peça
# (`.docx` ou tipo MIME de documento do Word no texto do evento) sai com exit 2, que no
# PreToolUse bloqueia a chamada da ferramenta, com o motivo no stderr. O evento sem peça possível
# passa (exit 0): o gate só julga peça, e bloquear todo comando deixaria a sessão sem shell.
# STDIN (evento) é lido uma vez e repassado ao .py; STDOUT (decisão) preservado; STDERR do .py
# suprimido, para traceback nunca virar contexto.
export PYTHONUTF8=1
# Lê o evento sem processo nem fork (read embutido; -d '' lê até o fim).
IFS= read -r -d '' EV || :
# RAIZ em cascata: CLAUDE_PLUGIN_ROOT, CODEX_PLUGIN_ROOT, pai do wrapper.
RAIZ="${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}}"

bloquear() {
  shopt -s nocasematch
  case "$EV" in
    *.docx*|*wordprocessingml*|*google-apps.document*|*excelent*ssim*) ;;
    *) exit 0 ;;
  esac
  printf '%s\n' "Gate de entrega do plugin Dissero: $1 Sem o gate, a peça não é conferida, e a entrega fica bloqueada. Comandos que não levam .docx seguem normalmente." >&2
  exit 2
}

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
[ -n "$PY" ] || bloquear "o Python 3 não foi encontrado neste computador. Instale o Python 3 (python.org) e repita o comando."

# O gate escreve direto na saída, sem pipe nem captura em subshell (cada fork custa caro no
# Windows). Saída != 0 continua bloqueando como antes.
$PY "$RAIZ/hooks/gate_entrega.py" <<<"$EV" 2>/dev/null; RC=$?
[ "$RC" -eq 0 ] || bloquear "o gate_entrega.py terminou com erro (saída $RC). Confira se o Python 3 roda (python --version), reinstale o plugin e repita o comando."
exit 0
