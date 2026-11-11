#!/bin/sh
# cabecalho.sh - headersHelper do canal Dissero no macOS e no Linux (24/10/2026).
#
# O Claude Code roda este script antes de cada consulta a loja do plugin e de cada download
# (`headersHelper` em extraKnownMarketplaces.dissero.source, Claude Code 2.1.238 ou superior). Ele
# le o token desta maquina no cofre do sistema e imprime UM objeto JSON com o cabecalho
# Authorization. O token nunca fica no settings.json.
#   macOS  Keychain (servico dissero-canal, conta maquina);
#   Linux  chaveiro do sistema (secret-tool).
#   Sem os dois: ~/.dissero/maquina.cofre, cifrado e preso a esta maquina (cofre_maquina.py).
#
# Sai com erro, sem imprimir nada, quando nao ha token ou o formato e inesperado: o Claude Code
# entao nao faz a consulta, e a copia instalada segue como esta.
# Copiado para ~/.dissero/ (caminho estavel); a fonte e _shared/cabecalho.sh.
alvo="${DSR_COFRE_ALVO:-dissero-canal}"
t=""
if [ "$(uname -s)" = "Darwin" ] && command -v security >/dev/null 2>&1; then
  t=$(security find-generic-password -a maquina -s "$alvo" -w 2>/dev/null) || t=""
fi
if [ -z "$t" ] && command -v secret-tool >/dev/null 2>&1; then
  t=$(secret-tool lookup service "$alvo" account maquina 2>/dev/null) || t=""
fi
# Reserva cifrada (sem Keychain ou chaveiro): so o Python do proprio plugin a abre.
if [ -z "$t" ] && [ -f "$HOME/.dissero/maquina.cofre" ]; then
  for py in python3 python /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if "$py" -c "import sys; sys.exit(sys.version_info < (3, 9))" </dev/null >/dev/null 2>&1; then
      t=$("$py" "$HOME/.dissero/cofre_maquina.py" --token 2>/dev/null </dev/null) && break || t=""
    fi
  done
fi
case "$t" in
  "" | *[!A-Za-z0-9_-]*) exit 1 ;;
esac
n=${#t}
if [ "$n" -lt 20 ] || [ "$n" -gt 200 ]; then exit 1; fi
printf '{"Authorization":"Bearer %s"}' "$t"
exit 0
