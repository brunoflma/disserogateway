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
EV="$(cat 2>/dev/null)"
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
PY=""; for _v in 1 2; do for _c in python3 python "py -3" /opt/homebrew/bin/python3 /usr/local/bin/python3; do _PYW "${_c%% *}"; [ -n "$_W" ] || continue; case "$_W" in */WindowsApps/*) [ "$_v" = 2 ] || continue ;; *) [ "$_v" = 1 ] || continue ;; esac; $_c -c "import sys; sys.exit(sys.version_info < (3, 9))" </dev/null >/dev/null 2>&1 && { PY="$_c"; break 2; }; done; done
[ -n "$PY" ] || bloquear "o Python 3 não foi encontrado neste computador. Instale o Python 3 (python.org) e repita o comando."

OUT="$(printf '%s' "$EV" | $PY "$RAIZ/hooks/gate_entrega.py" 2>/dev/null)"; RC=$?
[ "$RC" -eq 0 ] || bloquear "o gate_entrega.py terminou com erro (saída $RC). Confira se o Python 3 roda (python --version), reinstale o plugin e repita o comando."
[ -n "$OUT" ] && printf '%s\n' "$OUT"
exit 0
