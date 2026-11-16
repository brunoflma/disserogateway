#!/bin/bash
# SubagentStop: rede de segurança do gate de entrega. Bloqueia o subagente que entregou peça
# sem liberação (decision:"block" no JSON), cobrindo a entrega feita dentro do subagente, onde
# o PreToolUse da sessão principal pode não disparar (ver gate_entrega_subagente.py).
#
# FALHA FECHADA: sem Python, ou com o .py saindo com erro, o subagente cujo transcript menciona
# `.docx` ou o tipo MIME de documento do Word sai com exit 2, que no SubagentStop impede o
# subagente de parar, com o motivo no stderr. Com `stop_hook_active` verdadeiro no evento (o
# subagente já foi devolvido por um hook de parada), a mensagem manda parar de tentar e avisar o
# advogado do que instalar ou consertar; a entrega continua sem liberação. Sem transcript
# legível, ou sem peça possível nele, passa (exit 0), como no .py. STDOUT (decisão) preservado;
# STDERR do .py suprimido.
export PYTHONUTF8=1
# Lê o evento sem processo nem fork (read embutido; -d '' lê até o fim).
IFS= read -r -d '' EV || :
# RAIZ em cascata: CLAUDE_PLUGIN_ROOT, CODEX_PLUGIN_ROOT, pai do wrapper.
RAIZ="${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}}"

# bloquear MOTIVO REMEDIO: o motivo começa em minúscula e o remédio é uma frase inteira.
bloquear() {
  # Caminho do transcript no JSON do evento; a barra invertida escapada do Windows vira barra.
  TR="$(printf '%s' "$EV" | sed -n 's/.*"agent_transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1 | tr -s '\\' '/')"
  [ -n "$TR" ] && [ -f "$TR" ] || exit 0
  grep -qiE '\.docx|wordprocessingml|google-apps\.document' "$TR" 2>/dev/null || exit 0
  if printf '%s' "$EV" | grep -qE '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    printf '%s\n' "Gate de entrega do plugin: Pare de tentar concluir a entrega. Avise o advogado que a peça não foi conferida porque $1 e diga o que instalar ou consertar: $2. A entrega não é liberada." >&2
  else
    printf '%s\n' "Gate de entrega do plugin Dissero: $1. $3. Sem o gate, a peça entregue por este subagente não é conferida. Diga ao advogado que a entrega não foi conferida e rode estado_peca.py pode-entregar --state <PECA_STATE do caso> --strict --docx <arquivo> em cada peça entregue." >&2
  fi
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
[ -n "$PY" ] || bloquear "o Python 3 não foi encontrado neste computador" "instale o Python 3 (python.org)" "Instale o Python 3 (python.org)"

# O gate escreve direto na saída, sem pipe nem captura em subshell (cada fork custa caro no
# Windows). Saída != 0 continua bloqueando como antes.
$PY "$RAIZ/hooks/gate_entrega_subagente.py" <<<"$EV" 2>/dev/null; RC=$?
[ "$RC" -eq 0 ] || bloquear "o gate_entrega_subagente.py terminou com erro (saída $RC)" "confira se o Python 3 roda (python --version) e reinstale o plugin" "Confira se o Python 3 roda (python --version) e reinstale o plugin"
exit 0
