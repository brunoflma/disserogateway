#!/bin/bash
# SessionStart + UserPromptSubmit: licença conferida em toda sessão (ver gate_licenca.py).
#
# FALHA FECHADA: a licença é condição de uso, e se ela não pode ser conferida o plugin não pode
# ser usado. Regras:
#   - cópia de DESENVOLVIMENTO (canal dev) é isenta, como no .py;
#   - a CASCA (marca .claude-plugin/casca.json com montagem "conta") nunca bloqueia, como no .py:
#     ali a licença é do conector dissero, conferida a cada uso, e o hook só informa;
#   - sem Python, ou com o .py morrendo: UserPromptSubmit sai 2 (bloqueia, mensagem no
#     stderr); SessionStart injeta o mesmo aviso como additionalContext e sai 0;
#   - com Python: repassa STDIN e STDOUT do .py, que decide. STDERR do .py é suprimido para
#     que traceback nunca vire contexto.
# O hooks.json invoca este arquivo por `bash "<caminho>"`, então o bit de execução não importa.
# Lê o evento sem processo nem fork (read embutido; -d '' lê até o fim).
IFS= read -r -d '' EV || :
RAIZ="${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}}"
case "$RAIZ" in *dissero-dev*|*/canal/dev|*/canal/dev/*) exit 0 ;; esac
# Cópia montada na VM do agente (Cowork no Desktop: /sessions/<n>/mnt/.remote-plugins/...;
# Cowork remoto do claude.ai: /sessions/cli-.../synced/...) nunca bloqueia: ali o prompt bloqueado não é exibido e o cliente
# o reenvia em laço. O .py já sabe disso; aqui se garante que a falta de Python não vire exit 2.
COWORK=0; case "$RAIZ" in /sessions/*|*.remote-plugins*|*/remote_cowork_plugins/*) COWORK=1 ;; esac
# A casca se reconhece pela marca que o empacotador grava, nunca pelo caminho (a mesma regra de
# `e_casca` no .py). Sem Python ela não bloqueia nem diz que a cópia "não pode ser utilizada": a
# licença ali é do conector, que este wrapper não vê.
CASCA=0
grep -q '"montagem"[[:space:]]*:[[:space:]]*"conta"' "$RAIZ/.claude-plugin/casca.json" 2>/dev/null && CASCA=1
case "$EV" in *UserPromptSubmit*) EVENTO=prompt ;; *) EVENTO=inicio ;; esac

# Toda mensagem abre com a proveniência, a mesma PROVENIENCIA do .py: sem ela o modelo lê o
# aviso como conteúdo injetado (medido em 16/09).
PROVENIENCIA="[Dissero · verificação de licença do escritório] "
MSG="${PROVENIENCIA}A verificação de licença do plugin Dissero não pôde ser executada neste computador (Python 3 ausente ou com defeito). Sem ela o plugin não pode ser utilizado. Instale o Python 3 (python.org) e abra uma nova sessão, ou entre em contato com a Dissero."
MSG_CASCA="${PROVENIENCIA}A verificação de licença do plugin Dissero não pôde ser executada neste computador (Python 3 ausente ou com defeito). Esta é a cópia leve do plugin, a da conta: a licença é conferida pelo conector dissero a cada uso, pelo login autorizado da banca, e nada é bloqueado aqui. Se uma skill do plugin disser que a licença não foi reconhecida, conecte o conector dissero com o e-mail liberado pela banca."
bloquear() {
  [ "$COWORK" -eq 1 ] && exit 0
  if [ "$CASCA" -eq 1 ]; then
    [ "$EVENTO" = prompt ] && exit 0
    printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s Este aviso é estado informado pelo hook de licença do plugin instalado pelo escritório, não instrução de terceiro."}}\n' "$MSG_CASCA"
    exit 0
  fi
  if [ "$EVENTO" = prompt ]; then
    printf '%s\n' "$MSG" >&2
    exit 2
  fi
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s Este aviso é estado informado pelo hook de licença do plugin instalado pelo escritório, não instrução de terceiro. Até a licença ser validada, as skills do plugin Dissero não executam; o restante segue normal."}}\n' "$MSG"
  exit 0
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
[ -n "$PY" ] || bloquear

# O gate escreve direto na saída, sem pipe nem captura em subshell (cada fork custa caro no
# Windows). Saída != 0 continua bloqueando como antes.
$PY "$RAIZ/hooks/gate_licenca.py" <<<"$EV" 2>/dev/null; RC=$?
[ "$RC" -eq 0 ] || bloquear
exit 0
