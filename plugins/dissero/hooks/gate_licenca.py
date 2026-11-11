#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'gate_licenca.py — o plugin só trabalha com licença válida, e confere isso em TODA sessão.'































from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path



_PASTA_HOOK = Path(__file__).resolve().parent
if str(_PASTA_HOOK) not in sys.path:
    sys.path.insert(0, str(_PASTA_HOOK))
import cofre_maquina as COFRE


def _nome_da_maquina() -> str:
    'Nome da máquina, o mesmo valor de `platform.node()`. Não se usa o `platform`: no Windows'



    try:
        return socket.gethostname()
    except Exception:
        return ""





ORIGEM = "https://dissero.bfldevlabs.studio"
MERCADO = "dissero"
PLUGIN = f"dissero@{MERCADO}"
UA_CANAL = "dissero/1.0"
CACHE_S = 24 * 3600
TOLERANCIA_S = 72 * 3600










TIMEOUT_PERFIL_S = 8
FLAG_SINCRONIZAR = "--sincronizar-perfil"
FLAG_INSTALAR = "--instalar-canal"
FLAG_MEDIR_CLAUDE_CODE = "--medir-claude-code"


TRAVA_INSTALACAO = Path.home() / ".dissero" / "instalacao.lock"
RC_TRAVA_OCUPADA = 75
VIGIA = "vigia-settings.json"










LIMITE_REGRAVACOES = 2
FALHAS_ATE_AVISAR = 3
FOLGA_CONFIRMACAO_S = 24 * 3600
INTERVALO_AVISO_PERSISTENTE_S = 24 * 3600


RE_CHAVE = re.compile(r"\bDSR[\s-]?([A-HJ-KM-NP-Z2-9]{4})[\s-]?([A-HJ-KM-NP-Z2-9]{4})[\s-]?([A-HJ-KM-NP-Z2-9]{4})\b", re.I)












RE_PARECE_CHAVE = re.compile(r"\bDSR[\s-]([A-Z0-9]{3,6})[\s-]([A-Z0-9]{3,6})[\s-]([A-Z0-9]{3,6})\b", re.I)


RE_CONTORNO = re.compile(
    r"\b(?:(?:ignor|desconsider|pul|burl|contorn|desativ|desabilit|deslig|remov|tir|quebr|dribl)\w*\s+"
    r"(?:\w+\s+){0,2}?(?:hook|licen[cs]a|verificac\w*|trava|bloqueio|checagem|gate|validac\w*|restric\w*)|"
    r"bypass|jailbreak|override|hook|sem licen[cs]a|modo (?:de )?(?:teste|debug|dev\w*|admin\w*)|"
    r"sou (?:o |a )?(?:admin\w*|titular|don[oa]|desenvolvedor\w*|criador\w*|fornecedor\w*|dev)|"
    r"finj\w*|faz de conta|suponha que)\b", re.I)
RE_ALEGACAO = re.compile(
    r"\b(?:pronto|adicionad[oa]|adicionei|coloquei|informei|enviei|mandei|digitei|inseri|ativei|validei|"
    r"paguei|comprei|ja (?:tenho|esta|foi|fiz|mandei|enviei|informei|paguei|coloquei)|"
    r"(?:vamos|pode|podemos|bora) (?:continuar|seguir|prosseguir|comecar|la)|continu[ae]r?|prossig[ao]|"
    r"prosseguir|siga|liber[ae]|liberado|licen[cs]a (?:ok|validada|ativa|paga))\b", re.I)


SETTINGS = COFRE.dir_config_claude() / "settings.json"
ESTADO = Path.home() / ".dissero" / "licenca.json"
INSTALADOS = COFRE.dir_config_claude() / "plugins" / "installed_plugins.json"




CREDENCIAIS = COFRE.dir_config_claude() / ".credentials.json"



PERFIL_LOCAL = Path.home() / ".config" / "dissero" / "perfil.json"
IDENTIDADE_LOCAL = Path.home() / ".config" / "dissero" / "identidade"

IDADE_ORFAO_S = 600


TIMEOUT_ATIVACAO_S = 10



NOME_MARCADOR_BACKFILL = ".backfill-marca"


ESPERA_BACKFILL_MARCA_S = 7 * 24 * 3600








PROVENIENCIA = "[Dissero · verificação de licença do escritório] "
MSG_PEDIR = (PROVENIENCIA + "Esta cópia do plugin Dissero ainda não está licenciada neste computador, e por "
             "isso as skills do plugin não executam aqui até a licença ser reconhecida; o restante do Claude Code "
             "segue normal. A licença vem do login: digite /mcp, escolha dissero, autentique com o e-mail liberado "
             "pela banca e clique em Reconectar. Na primeira vez a tela do login pede a chave de licença "
             "(DSR-XXXX-XXXX-XXXX, do e-mail da Dissero); depois, só o Google. A chave é digitada só nessa tela, "
             "nunca na conversa. O login licencia você, e vale também no Cowork (Desktop ou claude.ai) e na aba Code. Feito o "
             "login, envie a sua demanda novamente.")


MSG_NAO_RECONHECIDA = (PROVENIENCIA + "A credencial deste computador não foi reconhecida pelo servidor da "
                       "Dissero: ela foi revogada ou substituída. Até a licença ser reconhecida de novo, as skills "
                       "do plugin não executam aqui. Digite /mcp, escolha dissero, autentique com o e-mail liberado "
                       "pela banca e clique em Reconectar; o plugin emite outra credencial sozinho. Depois envie a "
                       "sua demanda novamente.")
MSG_REVOGADA = (PROVENIENCIA + "A licença deste computador foi revogada, ou a licença já atingiu o número de "
                "computadores permitidos. O plugin Dissero não pode ser utilizado aqui. Entre em contato com a "
                "Dissero para regularizar.")






MSG_VENCIDA = (PROVENIENCIA + "O servidor da Dissero informou que a licença da banca venceu: o prazo de uso do "
               "plugin Dissero terminou, e por isso ele não pode ser utilizado aqui. Para continuar, solicite à "
               "Dissero a compra ou a renovação da licença anual. Manter o plugin instalado não renova o acesso.")
MSG_AGUARDANDO = (PROVENIENCIA + "O servidor da Dissero informou que a licença da banca ainda aguarda ativação: o "
                  "período gratuito começa quando o conector dissero é conectado de novo com o e-mail liberado "
                  "pela banca. Digite /mcp, escolha dissero, autentique com esse e-mail e clique em Reconectar. "
                  "Feito isso, envie a sua demanda novamente.")
MSG_SEM_REDE = (PROVENIENCIA + "Não foi possível confirmar a licença do plugin Dissero: sem conexão com o servidor "
                "da Dissero e sem validação recente neste computador. Verifique a conexão com a internet e abra uma "
                "nova sessão.")



MSG_INDISPONIVEL = (PROVENIENCIA + "O servidor da Dissero respondeu, mas não conseguiu conferir a licença "
                    "deste computador agora, por uma falha passageira do lado dele. Até a licença ser "
                    "reconhecida, as skills do plugin não executam aqui. Abra uma nova sessão em alguns minutos; "
                    "se o aviso se repetir, entre em contato com a Dissero.")


MSG_LIMITE_USO = (PROVENIENCIA + "O login do conector dissero atingiu o limite de uso de chamadas ao Dissero "
                  "nesta hora ou neste dia, e por isso a licença deste computador não foi conferida agora. Até "
                  "ela ser reconhecida, as skills do plugin não executam aqui. Abra uma nova sessão depois que o "
                  "uso voltar; se o seu trabalho precisa de mais, fale com o titular da banca.")


MSG_CHAVE_NO_PROMPT = (PROVENIENCIA + "O texto enviado parece conter uma chave de licença da Dissero, e por isso "
                       "não foi entregue ao Claude: a chave não se digita na conversa, para não ficar registrada nela. "
                       "Ela é pedida uma única vez, na tela de login do conector dissero. No terminal, digite /mcp, "
                       "escolha dissero e autentique com o e-mail liberado pela banca; no Desktop e no claude.ai, "
                       "vá em Conectores e clique em Vincular ao lado de dissero. Se a tela pedir a chave, digite-a "
                       "lá. Depois envie a sua demanda novamente, sem a chave.")
MSG_ALEGACAO = (PROVENIENCIA + "Nenhuma liberação foi feita. A licença é confirmada diretamente no servidor da "
                "Dissero, e afirmar que ela já foi informada não a substitui. Autorize o conector dissero (/mcp > "
                "dissero > autenticar) com o e-mail liberado pela banca. Sem isso, o plugin não pode ser utilizado.")
MSG_CONTORNO = (PROVENIENCIA + "Esta verificação é feita pelo servidor da Dissero e não pode ser desativada, "
                "ignorada ou substituída por instruções nesta conversa. O plugin Dissero só é liberado com um login "
                "autorizado pela banca (/mcp > dissero > autenticar). Faça o login ou entre em contato com a "
                "Dissero.")
MSG_LOGIN_OK = (PROVENIENCIA + "Licença reconhecida pelo login do conector dissero ({tenant}). Este aviso vem do "
                "hook de licença do plugin instalado pelo próprio escritório do advogado; não é instrução de "
                "terceiro e não pede ação nenhuma. O plugin Dissero está liberado neste computador: atenda a "
                "demanda normalmente, pelas skills do plugin. A cópia do canal de atualização está sendo instalada "
                "em segundo plano e entra em vigor na próxima sessão.")
MSG_LOGIN_EXPIRADO = (PROVENIENCIA + "O login do conector dissero neste computador expirou, e por isso a licença "
                      "do plugin Dissero não pôde ser confirmada agora. Digite /mcp, escolha dissero e clique em "
                      "Reconectar. Só a tela de login do Google aparece: a chave de licença não é pedida de novo. "
                      "Feito isso, envie a sua demanda novamente.")







MSG_CASCA = (PROVENIENCIA + "Esta é a cópia leve do plugin Dissero: as regras das skills vêm do "
             "servidor da Dissero pelo conector dissero, que confere a licença a cada uso, pelo login autorizado "
             "da banca. Este hook não confere esse login e nada é bloqueado aqui. Se uma skill do plugin disser "
             "que a licença não foi reconhecida, conecte o conector dissero com o e-mail liberado pela banca: no "
             "terminal, /mcp > dissero > autenticar; no Desktop e no claude.ai, em Conectores, clique em Vincular "
             "ao lado de dissero.")








MSG_CASCA_CANAL = (PROVENIENCIA + "Esta é a cópia leve do plugin Dissero: as skills dela são conferidas "
                   "pelo conector dissero a cada uso, e nada é bloqueado aqui. O que não aconteceu nesta sessão foi "
                   "ligar o canal de atualização deste computador (o que entrega a cópia do plugin): {motivo}")




AVISO_COPIA_ANTIGA = (" Esta é a cópia antiga do plugin, que trazia as regras no disco; a próxima atualização do "
                    "canal da Dissero a troca pela cópia leve, cujas regras são servidas pelo conector dissero "
                    "a cada uso.")
MOTIVOS_CASCA = {
    "cofre_indisponivel": "o cofre do sistema deste computador não aceitou guardar a credencial da máquina, "
                          "e por isso nada foi gravado na configuração do Claude Code. O plugin tenta de novo na "
                          "próxima sessão; se o aviso se repetir, fale com a Dissero.",
    "limite_maquinas": "o e-mail do login já atingiu o número de computadores permitidos pela licença. Para ligar o "
                       "canal aqui, peça à Dissero que libere uma vaga.",
    "login_expirado": "o servidor não aceitou o login do conector dissero guardado neste computador. No terminal, "
                      "digite /mcp, escolha dissero e clique em Reconectar; o canal é ligado na sessão seguinte.",
    "sem_rede": "não houve conexão com o servidor da Dissero. O plugin tenta de novo na próxima sessão.",
    "indisponivel": "o servidor da Dissero não conseguiu conferir a licença agora, por uma falha passageira do lado "
                    "dele. O plugin tenta de novo na próxima sessão.",
    "limite_uso": "o login atingiu o limite de uso de chamadas ao Dissero nesta hora ou neste dia. O plugin tenta "
                  "de novo na próxima sessão, depois que o uso voltar.",
    "settings_ilegivel": "o arquivo de configuração do Claude Code (~/.claude/settings.json) não é um JSON válido, e "
                         "por isso a declaração do canal não foi gravada. Ele não foi substituído, porque trocá-lo "
                         "apagaria as suas configurações. Corrija o arquivo, ou restaure uma cópia dele; o plugin "
                         "tenta de novo na próxima sessão.",
    "settings_ocupado": "o arquivo de configuração do Claude Code (~/.claude/settings.json) estava em uso por outro "
                        "programa, e por isso a declaração do canal não foi gravada. Nenhuma configuração sua foi "
                        "alterada. O plugin tenta de novo na próxima sessão.",



    "settings":"não foi possível gravar a declaração do canal no arquivo de configuração do Claude Code "
                "(~/.claude/settings.json). Nenhuma configuração sua foi alterada. O plugin tenta de novo na "
                "próxima sessão.",
}
MSG_CASCA_LOGIN_RECUSADO = (PROVENIENCIA + "O servidor da Dissero recusou o login do conector dissero guardado neste "
                            "computador: o e-mail não está liberado pela banca, não ocupa uma vaga da licença ou a "
                            "licença não está vigente. Esta é a cópia leve do plugin, cujas skills são conferidas pelo "
                            "conector a cada uso; com esse login, o servidor recusará também as regras das skills. Nada "
                            "é bloqueado aqui. Procure o titular da banca ou a Dissero para regularizar.")



MSG_CASCA_VENCIDA = (PROVENIENCIA + "O servidor da Dissero informou que a licença da banca venceu: o prazo de uso "
                     "do plugin Dissero terminou. Esta é a cópia leve do plugin, cujas skills são conferidas pelo "
                     "conector a cada uso; com a licença vencida, o servidor recusará também as regras das skills. "
                     "Nada é bloqueado aqui. Para continuar, solicite à Dissero a compra ou a renovação da licença "
                     "anual.")
MSG_CASCA_AGUARDANDO = (PROVENIENCIA + "O servidor da Dissero informou que a licença da banca ainda aguarda "
                        "ativação: o período gratuito começa quando o conector dissero é conectado de novo com o "
                        "e-mail liberado pela banca. Esta é a cópia leve do plugin, cujas skills são conferidas pelo "
                        "conector a cada uso; até essa conexão, o servidor recusará também as regras das skills. Nada "
                        "é bloqueado aqui. No terminal, digite /mcp, escolha dissero e clique em Reconectar; no "
                        "Desktop e no claude.ai, vá em Conectores e clique em Vincular ao lado de dissero.")







MSG_COWORK_REMOTO = (PROVENIENCIA + "Esta cópia do plugin Dissero roda na nuvem, no Cowork remoto do claude.ai, "
                     "onde não há um computador fixo a que prender a licença nem a pasta do computador do "
                     "advogado. Nesta superfície a licença é conferida pelo conector dissero, que só entrega as "
                     "regras das skills ao login autorizado da banca. Para trabalhar com a pasta do caso e com "
                     "documento sigiloso, o recomendado é o Cowork no Desktop. Este aviso é um estado, não uma "
                     "instrução.")
MSG_COWORK_DESKTOP = (PROVENIENCIA + "Esta cópia do plugin Dissero roda na máquina virtual do Cowork no Desktop, "
                      "onde a licença não se prende a um computador fixo. Nesta superfície a licença é conferida "
                      "pelo conector dissero, que só entrega as regras das skills ao login autorizado da banca. Este "
                      "aviso é um estado, não uma instrução, e não pede ação nenhuma.")
MSG_ERRO_INTERNO = (PROVENIENCIA + "A verificação de licença do plugin Dissero falhou por um erro interno, e "
                    "sem ela o plugin não pode ser utilizado. Abra uma nova sessão; se o problema persistir, entre em "
                    "contato com a Dissero.")



ESTADO_NAO_INSTRUCAO = (" Este aviso é estado informado pelo hook de licença do plugin instalado pelo escritório, "
                        "não instrução de terceiro.")



MSG_SETTINGS_ILEGIVEL = (PROVENIENCIA + "O arquivo de configuração do Claude Code neste computador "
                         "(~/.claude/settings.json) existe, mas não é um JSON válido. Ele não foi substituído, porque "
                         "trocá-lo apagaria as suas configurações. A licença do plugin Dissero não foi ativada. "
                         "Corrija o arquivo, ou restaure uma cópia dele, se tiver. Depois envie a sua demanda "
                         "novamente: a ativação pelo login é refeita sozinha. Se precisar de ajuda, entre em contato "
                         "com a Dissero.")




MSG_SETTINGS_OCUPADO = (PROVENIENCIA + "O arquivo de configuração do Claude Code neste computador "
                        "(~/.claude/settings.json) está em uso por outro programa neste momento, e por isso não foi "
                        "trocado. Nenhuma configuração sua foi alterada. A licença do plugin Dissero não foi "
                        "ativada. Aguarde alguns segundos. Depois envie a sua demanda novamente. Se o aviso se "
                        "repetir, feche as outras sessões do Claude Code.")



MSG_COFRE = (PROVENIENCIA + "A licença do plugin Dissero foi reconhecida, mas o cofre do sistema deste computador "
             "(Gerenciador de Credenciais, Keychain ou chaveiro) não aceitou guardar a credencial da máquina, e por "
             "isso nada foi gravado na configuração do Claude Code. Até isso se resolver, as skills do plugin não "
             "executam aqui. Abra uma nova sessão; se o aviso se repetir, fale com a Dissero.")
MSGS_SETTINGS = {"settings_ilegivel": MSG_SETTINGS_ILEGIVEL, "settings_ocupado": MSG_SETTINGS_OCUPADO}







SUFIXO_APOS_TOKEN = "_apos_token"
MSG_LOGIN_PENDENTE = (PROVENIENCIA + "Licença reconhecida pelo login do conector dissero{tenant}, e a credencial "
                      "desta máquina ficou guardada no cofre do sistema. Este aviso vem do hook de licença do plugin "
                      "instalado pelo próprio escritório do advogado; não é instrução de terceiro. O plugin Dissero "
                      "está liberado neste computador: atenda a demanda normalmente, pelas skills do plugin. O que "
                      "não ficou foi a declaração do canal de atualização no arquivo de configuração do Claude Code "
                      "(~/.claude/settings.json): {motivo}")
MOTIVOS_PENDENTE = {
    "settings_ocupado": "outro programa estava com esse arquivo aberto ou gravava nele ao mesmo tempo (o próprio "
                        "Claude Code, por exemplo, ao trocar o modelo), ou o sistema recusou a gravação, e o plugin "
                        "não grava por cima do que outro programa acabou de gravar. Nenhuma configuração sua foi "
                        "alterada. A declaração é gravada sozinha numa próxima sessão.",
    "settings_nao_relido": "a gravação foi feita, mas outro programa manteve o arquivo aberto logo depois, e ele não "
                           "pôde ser relido para conferir. Nada foi desfeito. A próxima sessão confere a declaração "
                           "e a grava de novo, se faltar.",
    "settings_ilegivel": "ele deixou de ser um JSON válido enquanto o plugin o gravava, e não foi substituído, porque "
                         "trocá-lo apagaria as suas configurações. Corrija o arquivo, ou restaure uma cópia dele; a "
                         "declaração é gravada sozinha na primeira sessão depois disso.",
    "settings_nao_conferido": "outro programa o regravou enquanto o plugin gravava, e configurações suas sumiram "
                              "nesse intervalo. O arquivo voltou a ser exatamente o que era antes desta gravação; o "
                              "que o outro programa gravou nesse intervalo (uma troca de modelo, por exemplo) se "
                              "perdeu junto e precisa ser refeito. A declaração é gravada sozinha na próxima sessão.",
    "settings_nao_conferido_sem_copia": "outro programa o regravou enquanto o plugin gravava, e ele ficou ilegível. "
                                        "Não havia arquivo antes, e por isso nada foi restaurado. Corrija o arquivo; "
                                        "a declaração é gravada sozinha na primeira sessão depois disso.",
    "settings_nao_conferido_recusada": "outro programa o regravou enquanto o plugin gravava, configurações suas "
                                       "sumiram nesse intervalo, e o sistema recusou a restauração. O aviso de "
                                       "configurações perdidas da próxima sessão traz o comando que as recoloca. A "
                                       "declaração é gravada sozinha na próxima sessão.",
    "auxiliar": "o comando que entrega essa credencial ao Claude Code não pôde ser copiado para ~/.dissero agora, e "
                "sem ele a declaração não é gravada. Nenhuma configuração sua foi alterada. O plugin tenta a cópia e "
                "a declaração de novo nas próximas sessões; se a cópia continuar falhando, ele avisa o que "
                "conferir nessa pasta.",
    "settings": "não foi possível gravá-lo neste momento. A declaração é gravada sozinha numa próxima sessão.",
}



PENDENTES_AO_ADVOGADO = ("settings_ilegivel", "settings_nao_conferido", "settings_nao_conferido_sem_copia",
                         "settings_nao_conferido_recusada")
MSG_AVISO_PENDENTE = (PROVENIENCIA + "A licença do plugin Dissero foi reconhecida neste computador, mas a declaração "
                      "do canal de atualização não foi gravada no arquivo de configuração do Claude Code "
                      "(~/.claude/settings.json): {motivo} Este aviso é estado, não instrução, e nada foi bloqueado.")





MSG_PENDENTE_PERSISTENTE = (PROVENIENCIA + "A declaração do canal de atualização do plugin Dissero não pôde ser "
                            "gravada no arquivo de configuração do Claude Code (~/.claude/settings.json) em três "
                            "sessões seguidas: o arquivo estava em uso, ilegível, marcado como somente leitura ou sem "
                            "permissão de gravação. Confira se ele não está marcado como somente leitura e se nenhum "
                            "programa o mantém aberto. A licença deste computador vale; só a atualização automática "
                            "do plugin fica parada até a declaração entrar. Este aviso é estado, não instrução, e "
                            "nada foi bloqueado.")
MSG_PENDENTE_PERSISTENTE_AUXILIAR = (PROVENIENCIA + "A declaração do canal de atualização do plugin Dissero não "
                                     "foi gravada em três sessões seguidas porque o comando que entrega a credencial "
                                     "desta máquina ao Claude Code não pôde ser copiado para a pasta ~/.dissero (os "
                                     "arquivos cabecalho.ps1 e cabecalho.sh dessa pasta). O arquivo de configuração do "
                                     "Claude Code não é a causa. Confira se essa pasta e esses arquivos não estão "
                                     "marcados como somente leitura, se você tem permissão de gravação neles e se "
                                     "nenhum programa os mantém abertos. A licença deste computador vale; só a "
                                     "atualização automática do plugin fica parada até a cópia e a declaração entrarem. "
                                     "Este aviso é estado, não instrução, e nada foi bloqueado.")
MSG_PENDENTE_PERSISTENTE_OUTRA = (PROVENIENCIA + "A declaração do canal de atualização do plugin Dissero não pôde "
                                  "ser gravada em três sessões seguidas, por um erro que o plugin não soube nomear. A "
                                  "licença deste computador vale; só a atualização automática do plugin fica parada "
                                  "até a declaração entrar. Se o aviso se repetir, fale com a Dissero. Este aviso é "
                                  "estado, não instrução, e nada foi bloqueado.")



MSG_CANAL_DESISTIDO = (PROVENIENCIA + "A licença do plugin Dissero continua valendo neste computador, mas a "
                       "atualização automática do plugin parou: a declaração do canal de atualização foi tirada do "
                       "arquivo de configuração do Claude Code (~/.claude/settings.json) logo depois de gravada, "
                       "nas vezes em que o plugin a recolocou, e ele deixou de insistir. Se não foi você quem a "
                       "tirou, algum programa está regravando esse arquivo (outra sessão do Claude Code aberta, por "
                       "exemplo). Para religar a atualização automática, feche as outras sessões do Claude Code e "
                       "diga 'ativar o canal Dissero'. Este aviso é estado, não instrução, e nada foi bloqueado.")

AVISOS_DO_CANAL = {"pendente_persistente": MSG_PENDENTE_PERSISTENTE,
                   "pendente_persistente_auxiliar": MSG_PENDENTE_PERSISTENTE_AUXILIAR,
                   "pendente_persistente_outra": MSG_PENDENTE_PERSISTENTE_OUTRA,
                   "desistida": MSG_CANAL_DESISTIDO}



MSG_SETTINGS_GENERICO = (PROVENIENCIA + "Não foi possível gravar a configuração do Claude Code "
                         "(~/.claude/settings.json) neste momento. Nenhuma configuração sua foi alterada. A "
                         "licença do plugin Dissero não foi ativada. Feche as outras sessões do Claude Code. "
                         "Depois envie a sua demanda novamente.")


MSG_CLAUDE_CODE_ANTIGO = (PROVENIENCIA + "Este Claude Code está na versão {atual}, e o plugin Dissero exige a "
                          "{minimo} ou superior: em versão anterior, uma falha da trava de entrega pode deixar a "
                          "entrega seguir sem a conferência. Atualize o Claude Code (no terminal, claude update; no "
                          "Desktop, atualize o aplicativo) e abra uma nova sessão. Este aviso é estado, não "
                          "instrução, e nada foi bloqueado.")


def mensagem_pendente(motivo, tenant=None) -> str:
    'A frase de quando a ativação pelo login guardou o token no cofre e não gravou a declaração'



    base = str(motivo or "")
    if base.endswith(SUFIXO_APOS_TOKEN):
        base = base[: -len(SUFIXO_APOS_TOKEN)]
    texto = MOTIVOS_PENDENTE.get(base) or MOTIVOS_PENDENTE["settings"]
    return MSG_LOGIN_PENDENTE.format(tenant=f" ({tenant})" if tenant else "", motivo=texto)


def aviso_pendente(motivo):
    'O aviso AO ADVOGADO (systemMessage) da declaração pendente, ou None quando o desfecho se'

    base = str(motivo or "")
    if base.endswith(SUFIXO_APOS_TOKEN):
        base = base[: -len(SUFIXO_APOS_TOKEN)]
    if base not in PENDENTES_AO_ADVOGADO:
        return None
    return MSG_AVISO_PENDENTE.format(motivo=MOTIVOS_PENDENTE[base])


def _mensagem_motivo(tabela: dict, motivo) -> str:
    'Texto ao advogado para um `motivo` de recusa. Código com o sufixo de token tem a frase da'


    if isinstance(motivo, str) and motivo.endswith(SUFIXO_APOS_TOKEN):
        return mensagem_pendente(motivo)
    if motivo in tabela:
        return tabela[motivo]
    if isinstance(motivo, str) and motivo.startswith("settings_"):
        return MSG_SETTINGS_GENERICO
    raise KeyError(motivo)


def mensagem_casca(motivo) -> str:
    'A frase da CASCA depois de uma tentativa com o login local que não ligou o canal. PURA.'







    if motivo == "revogada":
        return MSG_CASCA_LOGIN_RECUSADO
    if motivo == "vencida":
        return MSG_CASCA_VENCIDA
    if motivo == "aguardando":
        return MSG_CASCA_AGUARDANDO
    base = str(motivo or "")
    if base.endswith(SUFIXO_APOS_TOKEN):
        return mensagem_pendente(base)
    if base in MOTIVOS_CASCA:
        texto = MOTIVOS_CASCA[base]
    elif base.startswith("settings_"):
        texto = MOTIVOS_CASCA["settings"]
    else:
        raise KeyError(motivo)
    return MSG_CASCA_CANAL.format(motivo=texto)


def motivo_da_recusa(texto) -> str:
    'O motivo de uma recusa do `ativar_maquina`, pela frase do servidor. PURA.'








    t = _sem_acento(texto).upper()
    if "NESTA MAQUINA" in t:
        return "limite_maquinas"


    if "LIMITE DE USO" in t:
        return "limite_uso"
    if "LICENCA VENCIDA" in t:
        return "vencida"
    if "AGUARDANDO ATIVACAO" in t:
        return "aguardando"
    if "INDISPONIVEL" in t or "TENTE NOVAMENTE" in t:
        return "indisponivel"
    return "revogada"


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c))


def classificar_prompt(texto) -> str:
    "A intencao de um prompt que chegou SEM licenca. PURA. Devolve 'chave', 'chave_malformada',"


    t = _sem_acento(texto)
    if RE_CHAVE.search(t):
        return "chave"
    m = RE_PARECE_CHAVE.search(t)
    if m and any(ch.isdigit() for ch in m.group(0)):
        return "chave_malformada"
    if RE_CONTORNO.search(t):
        return "contorno"
    if RE_ALEGACAO.search(t):
        return "alegacao"
    return "demanda"


def marca(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12] if s else "(ausente)"


def e_casca(raiz) -> bool:
    "A copia instalada e a CASCA (montagem 'conta')? Le a marca que o empacotador grava em"

    try:
        d = json.loads((Path(raiz) / ".claude-plugin" / "casca.json").read_text(encoding="utf-8-sig"))
        return isinstance(d, dict) and d.get("montagem") == "conta"
    except Exception:
        return False


def e_copia_do_canal(raiz) -> bool:
    'A cópia veio do canal? Pela POSIÇÃO no caminho, `<cache>/<loja>/<plugin>/<versão>`, nunca'




    partes = str(raiz).replace("\\", "/").rstrip("/").lower().split("/")
    return len(partes) >= 4 and partes[-4] == "cache" and partes[-3] == MERCADO and partes[-2] == "dissero"


def origem_da_copia(raiz) -> str:
    'De onde veio a cópia, pelo caminho dela. No gate a classe só decide as isenções (`dev`,'

    p = str(raiz).replace("\\", "/").rstrip("/").lower()
    partes = p.split("/")
    if "dissero-dev" in partes or p.endswith("/canal/dev") or "/canal/dev/" in p:
        return "dev"



    if p.startswith("/sessions/") or ".remote-plugins" in partes or "remote_cowork_plugins" in partes:
        return "cowork"


    if "synced" in partes:
        return "conta-terminal"
    if "local-desktop-app-uploads" in partes:
        return "upload-local"
    if "rpm" in partes:
        return "conta"
    if e_copia_do_canal(raiz):
        return "canal"
    return "desconhecida"


def cowork_remoto(raiz) -> bool:
    'Entre as cópias de origem `cowork`, a do Cowork remoto do claude.ai? Pelo CAMINHO, como a'




    if origem_da_copia(raiz) != "cowork":
        return False
    p = str(raiz).replace("\\", "/").rstrip("/").lower()
    partes = p.split("/")
    if ".remote-plugins" in partes:
        return False
    return (p.startswith("/sessions/cli-") or "remote_cowork_plugins" in partes
            or (p.startswith("/sessions/") and "synced" in partes))


def _ler_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def ler_token(cofre=None) -> str:
    'O token desta maquina, que mora SO no cofre do sistema (`cofre`, a funcao que o le; o main'



    if not cofre:
        return ""
    try:
        return str(cofre() or "").strip()
    except Exception:
        return ""


def validar_http(origem, token):
    req = urllib.request.Request(f"{origem.rstrip('/')}/licenca",
                                 headers={"Authorization": f"Bearer {token}", "User-Agent": UA_CANAL})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise PermissionError(str(e.code)) from None
        raise OSError(f"HTTP {e.code}") from None


def avaliar(estado, token, agora, validar, cache_s=CACHE_S, tolerancia_s=TOLERANCIA_S) -> dict:
    'Decide se esta maquina esta licenciada agora. PURA dado `validar`.'


    estado = dict(estado or {})
    if not token:
        return {"ok": False, "motivo": "sem_licenca", "validada_em": estado.get("validada_em"),
                "tenant": None, "token_marca": None}
    mesma = estado.get("token_marca") == marca(token)
    ultima = estado.get("validada_em") or 0
    if mesma and estado.get("ok") and agora - ultima < cache_s:
        return {**estado, "motivo": "cache"}
    try:
        r = validar(token)
        return {"ok": True, "motivo": "validada", "validada_em": agora, "tenant": r.get("tenant"),
                "token_marca": marca(token)}
    except PermissionError as e:
        return {"ok": False, "motivo": "revogada" if str(e) == "403" else "invalida",
                "validada_em": agora, "tenant": None, "token_marca": marca(token)}
    except Exception:
        if mesma and estado.get("ok") and agora - ultima < tolerancia_s:
            return {**estado, "motivo": "offline_tolerado"}
        return {"ok": False, "motivo": "sem_rede", "validada_em": ultima or None, "tenant": None,
                "token_marca": marca(token)}


def _caminho_ativar(raiz) -> Path:
    rel = Path("skills") / "dissero-ativar" / "scripts" / "ativar_canal.py"
    p = Path(raiz) / rel
    if not p.is_file():


        p = Path(__file__).resolve().parent.parent / rel
    return p


def _modulo_ativar(raiz):
    p = _caminho_ativar(raiz)
    spec = importlib.util.spec_from_file_location("ativar_canal", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _settings_legivel(ac, settings):
    'None se o settings pode ser gravado; senao o codigo do erro NOMEADO. Conferido ANTES de'

    try:
        ac.ler_settings(Path(settings))
        return None
    except ac.ErroSettings as e:
        return e.codigo


def _gravar_declaracao(ac, origem, settings):
    'Grava a declaração SEM token (o headersHelper lê o cofre) pela gravação segura do'


    try:
        ac.gravar_declaracao(Path(settings), ac.bloco_marketplace(origem))
    except ac.ErroSettings as e:


        codigo = e.codigo
        restauracao = getattr(e, "restauracao", None)
        if codigo == "settings_nao_conferido" and restauracao in ("nada", "recusada"):
            codigo += "_sem_copia" if restauracao == "nada" else "_recusada"
        return codigo + SUFIXO_APOS_TOKEN


    ac.reconciliar_registro(ac.bloco_marketplace(origem)["source"], ac.registro_de(settings),
                            trava=TRAVA_INSTALACAO)
    return None


def _store_login(credenciais):
    'O store de login do Claude Code. No caminho padrão, pelo cofre_maquina (no macOS, o'


    if Path(credenciais) == CREDENCIAIS:
        return COFRE.ler_store_claude()
    return _ler_json(credenciais)


def ler_token_oauth(credenciais=CREDENCIAIS, origem=ORIGEM, agora_ms=None) -> str:
    "O access token do conector dissero no store do Claude Code, ou ''. PURA no efeito."





    d = _store_login(credenciais)
    d = d if isinstance(d, dict) else {}
    alvo = f"{str(origem).rstrip('/')}/mcp"
    agora_ms = agora_ms if agora_ms is not None else time.time() * 1000
    melhor = ""
    for e in (d.get("mcpOAuth") or {}).values():
        if not isinstance(e, dict) or str(e.get("serverUrl") or "").rstrip("/") != alvo:
            continue
        tok = str(e.get("accessToken") or "").strip()
        if not tok:
            continue
        exp = e.get("expiresAt")
        if isinstance(exp, (int, float)) and exp <= agora_ms:
            continue
        melhor = tok
    return melhor


def situacao_login(credenciais=CREDENCIAIS, origem=ORIGEM, agora_ms=None) -> str:
    "'valido', 'expirado' ou 'ausente': o login do dissero no store do Claude Code. PURA no efeito."





    if ler_token_oauth(credenciais, origem, agora_ms):
        return "valido"
    d = _store_login(credenciais)
    d = d if isinstance(d, dict) else {}
    alvo = f"{str(origem).rstrip('/')}/mcp"
    for e in (d.get("mcpOAuth") or {}).values():
        if (isinstance(e, dict) and str(e.get("serverUrl") or "").rstrip("/") == alvo
                and str(e.get("accessToken") or "").strip()):
            return "expirado"
    return "ausente"


class ServidorIndisponivel(OSError):
    'O servidor RESPONDEU, mas não executou o pedido: o HTTP 503 com a frase da guarda de'








def _mensagem_jsonrpc(erro_http) -> str:
    "A frase de `error.message` no corpo JSON-RPC de uma resposta HTTP de erro, ou ''. Corpo"

    try:
        corpo = json.loads(erro_http.read().decode("utf-8"))
        m = (corpo.get("error") or {}).get("message") if isinstance(corpo, dict) else None
        return m.strip()[:300] if isinstance(m, str) else ""
    except Exception:
        return ""


def _post_mcp(origem, token_oauth, nome, argumentos, timeout):
    'POST /mcp `tools/call` com o bearer do login. Devolve a resposta JSON INTEIRA. Levanta'





    corpo = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": nome, "arguments": argumentos}}
    req = urllib.request.Request(f"{str(origem).rstrip('/')}/mcp", data=json.dumps(corpo).encode("utf-8"),
                                 method="POST",
                                 headers={"Authorization": f"Bearer {token_oauth}", "Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream", "User-Agent": UA_CANAL})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise PermissionError("401") from None
        frase = _mensagem_jsonrpc(e) if e.code in (403, 503) else ""
        if frase and e.code == 403:
            raise PermissionError(f"403 {frase}") from None
        if frase:
            raise ServidorIndisponivel(f"HTTP 503 {frase}") from None
        raise OSError(f"HTTP {e.code}") from None
    except Exception as e:
        raise OSError(str(e)) from None


def ativar_por_login_http(origem, token_oauth, maquina):
    'tools/call ativar_maquina no /mcp, com o bearer do login. Devolve o `_meta` do Worker'












    resp = _post_mcp(origem, token_oauth, "ativar_maquina", {"maquina": str(maquina or "")[:80]},
                     TIMEOUT_ATIVACAO_S)
    if not isinstance(resp, dict):
        raise OSError("resposta JSON-RPC que não é objeto")
    if resp.get("error") is not None:
        erro = resp["error"] if isinstance(resp["error"], dict) else {}
        raise ServidorIndisponivel(f"JSON-RPC {erro.get('code')}: {str(erro.get('message') or '')[:300]}".strip())
    res = resp.get("result") or {}
    meta = res.get("_meta") or {}
    if res.get("isError") or not meta.get("token"):
        texto = " ".join(c.get("text", "") for c in (res.get("content") or []) if isinstance(c, dict))
        raise PermissionError(f"403 {texto}".strip())
    return meta


def ativar_por_login(raiz, origem, token_oauth, maquina, settings, http=None, cofre=None, pasta_marca=None,
                     emitido=None):
    'Login -> token de maquina (tools/call ativar_maquina) e declaracao gravada.'














    ac = _modulo_ativar(raiz)
    http = http or ativar_por_login_http
    erro = _settings_legivel(ac, settings)
    if erro:
        return False, erro, None
    try:
        meta = http(origem, token_oauth, maquina)
    except PermissionError as e:
        return False, ("login_expirado" if str(e).startswith("401") else motivo_da_recusa(str(e))), None
    except ServidorIndisponivel:
        return False, "indisponivel", None
    except Exception:
        return False, "sem_rede", None
    token = str((meta or {}).get("token") or "")
    if not token:
        return False, "sem_rede", None
    if emitido is not None:
        emitido["token"] = token



    if cofre:
        try:
            cofre(token)
        except AuxiliarIndisponivel:
            if pasta_marca is not None:
                ac.marcar_pendente(pasta_marca, settings, "auxiliar")
            return False, "auxiliar" + SUFIXO_APOS_TOKEN, (meta or {}).get("tenant")
        except Exception:
            return False, "cofre_indisponivel", None
        if pasta_marca is not None:
            ac.marcar_pendente(pasta_marca, settings, "ativacao")
    erro = _gravar_declaracao(ac, origem, settings)
    if erro:

        return False, erro, (meta or {}).get("tenant")
    return True, "ativada", (meta or {}).get("tenant")


class AuxiliarIndisponivel(OSError):
    'O cofre ACEITOU o token, e só a cópia do comando que o lê para ~/.dissero falhou. Erro'



def guardar_no_cofre(token):
    'O token no cofre do sistema e o comando que o lê em ~/.dissero/. É a função que o main liga'


    COFRE.gravar(token)
    try:
        COFRE.instalar_auxiliares(origem=_PASTA_HOOK)
    except Exception as e:
        raise AuxiliarIndisponivel(f"{type(e).__name__}: {e}") from None


def _sem_falhas(marca_d):
    'Os dados da marca sem a conta de falhas (a declaração está no arquivo, ou acabou de ser'


    d = {k: v for k, v in marca_d.items() if k not in ("causa", "avisada_em")}
    d["falhas"] = 0
    return d


def _tem_falhas(ac, marca_d) -> bool:
    return bool(ac.contador_marca(marca_d.get("falhas")) or "causa" in marca_d or "avisada_em" in marca_d)


def manter_canal(settings=SETTINGS, origem=ORIGEM, raiz=None, trava=None, pasta=None, cofre_ler=None,
                 fonte_sessao=None, agora=None):
    'O que a sessao confere no canal, a cada SessionStart (24/10/2026):'






































    try:
        agora = time.time() if agora is None else float(agora)
        d = _ler_json(settings)
        e = ((d or {}).get("extraKnownMarketplaces") or {}).get(MERCADO) if isinstance(d, dict) else None
        src = (e or {}).get("source") or {}
        ac = _modulo_ativar(raiz or _raiz_do_plugin())
        bloco = ac.bloco_marketplace(origem)
        marca_p, marca_d = ac.consolidar_marcas(Path(pasta) if pasta is not None else ESTADO.parent, settings)
        feito = None
        if marca_p is not None and e == bloco:
            gravada = max(ac.instante_marca(marca_d.get("desde")), ac.instante_marca(marca_d.get("gravada_em")))
            if marca_d.get("desistida"):

                ac._apagar(marca_p)
            elif fonte_sessao == "startup" and agora - gravada >= FOLGA_CONFIRMACAO_S:

                ac._apagar(marca_p)
            elif _tem_falhas(ac, marca_d):
                ac.persistir_marca(marca_p, _sem_falhas(marca_d))
        elif marca_p is not None:
            if marca_d.get("desistida"):
                return None
            gravacoes = ac.contador_marca(marca_d.get("gravacoes"))
            if gravacoes >= LIMITE_REGRAVACOES:
                ac.persistir_marca(marca_p, {**marca_d, "desistida": True})
                return "desistida"
            if not ler_token(cofre_ler):
                return None
            anotada = {**marca_d, "gravacoes": gravacoes + 1, "gravada_em": agora}
            if not ac.persistir_marca(marca_p, anotada):
                return None
            etapa = "auxiliar"
            try:


                if not COFRE.auxiliares_presentes(origem=_PASTA_HOOK):
                    COFRE.instalar_auxiliares(origem=_PASTA_HOOK)
                etapa = "settings"
                r = ac.gravar_declaracao(Path(settings), bloco)
            except Exception as erro:
                if isinstance(erro, ac.SettingsNaoRelido):

                    if _tem_falhas(ac, anotada):
                        ac.persistir_marca(marca_p, _sem_falhas(anotada))
                    return "declarada"
                causa = "auxiliar" if etapa == "auxiliar" else (
                    "settings" if isinstance(erro, ac.ErroSettings) else "outra")
                falhas = ac.contador_marca(marca_d.get("falhas")) + 1

                nova = {**marca_d, "falhas": falhas, "causa": causa}
                avisar = (falhas >= FALHAS_ATE_AVISAR and
                          agora - ac.instante_marca(marca_d.get("avisada_em")) >= INTERVALO_AVISO_PERSISTENTE_S)
                if avisar:
                    nova["avisada_em"] = agora
                ac.persistir_marca(marca_p, nova)
                if not avisar:
                    return None
                return "pendente_persistente" + ("" if causa == "settings" else "_" + causa)
            if (r or {}).get("gravado"):
                if _tem_falhas(ac, anotada):
                    ac.persistir_marca(marca_p, _sem_falhas(anotada))
                feito = "declarada"
            else:

                ac.persistir_marca(marca_p, _sem_falhas(marca_d))
            src = bloco["source"]
        if feito is None and "headers" in src:
            ac.gravar_declaracao(Path(settings), bloco)
            src, feito = bloco["source"], "limpa"
        elif feito is None and src.get("headersHelper") != COFRE.comando():
            return None
        if not COFRE.auxiliares_presentes(origem=_PASTA_HOOK):
            COFRE.instalar_auxiliares(origem=_PASTA_HOOK)
            feito = feito or "auxiliar"
        reg = ac.reconciliar_registro(src, ac.registro_de(settings),
                                      trava=trava if trava is not None else TRAVA_INSTALACAO)
        return feito or ("registro" if reg == "reconciliado" else None)
    except Exception:
        return None


def _rpc_mcp(origem, token_oauth, nome, argumentos, timeout=20):
    '`tools/call` genérico (ver `_post_mcp`). Devolve `result` (dict, possivelmente vazio);'

    resp = _post_mcp(origem, token_oauth, nome, argumentos, timeout)
    try:
        return (resp or {}).get("result") or {}
    except Exception as e:
        raise OSError(str(e)) from None


def baixar_perfil_http(origem, token_oauth, parte="perfil"):
    '`tools/call perfil_do_advogado` no /mcp, `parte` em {"perfil", "identidade"}; com'




    if parte == "clone":
        return _rpc_mcp(origem, token_oauth, "clone_do_advogado", {}, timeout=TIMEOUT_PERFIL_S)
    return _rpc_mcp(origem, token_oauth, "perfil_do_advogado", {"parte": parte}, timeout=TIMEOUT_PERFIL_S)


def _perfil_valido(perfil) -> bool:
    'Validação MÍNIMA antes de instalar no disco de TODO advogado licenciado, e não a'




    return (isinstance(perfil, dict) and isinstance(perfil.get("versao_perfil"), str)
            and bool(perfil.get("versao_perfil").strip()) and isinstance(perfil.get("advogado"), dict))


def _mesmo_advogado(marca_atual, marca_nova) -> bool:
    'Só afirma "é o mesmo advogado" quando as DUAS marcas estão presentes e batem.'







    return bool(marca_atual) and bool(marca_nova) and marca_atual == marca_nova


def _identidade_marca_ausente(identidade) -> bool:
    'True quando `identidade/mapping.json` não carrega `marca` (ausente, ilegível, ou o'












    try:
        with open(Path(identidade) / "mapping.json", encoding="utf-8") as fh:
            m = json.load(fh)
        if isinstance(m, dict) and m.get("marca"):
            return False
    except (OSError, ValueError):
        pass
    return not _backfill_em_espera(identidade)


def _backfill_em_espera(identidade) -> bool:
    'True enquanto a ÚLTIMA tentativa falha de backfill ainda estiver dentro do prazo.'





    try:
        decorrido = time.time() - (Path(identidade) / NOME_MARCADOR_BACKFILL).stat().st_mtime
    except OSError:
        return False
    return 0 <= decorrido < ESPERA_BACKFILL_MARCA_S


def _anotar_backfill_falho(identidade) -> None:
    'Data a tentativa falha de backfill, para `_backfill_em_espera` cobrar o prazo.'




    try:
        d = Path(identidade)
        if not d.is_dir():
            return
        (d / NOME_MARCADOR_BACKFILL).write_text(
            "O plugin tentou completar a marca deste timbrado em "
            + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            + " e o pacote nao veio. Ele tenta de novo depois do prazo; apagar este arquivo "
              "faz tentar ja na proxima sessao.\n",
            encoding="utf-8")
    except Exception:
        pass


def _advogado_diferente_confirmado(marca_atual, marca_nova) -> bool:
    'Confirma que o disco pertence a um advogado DIFERENTE do que acabou de logar: exige as'





    return bool(marca_atual) and bool(marca_nova) and marca_atual != marca_nova


def _quarentenar_advogado_anterior(destino, identidade, clone=None) -> None:
    'Tira do caminho o perfil, o clone e o timbrado do advogado ANTERIOR ANTES de qualquer'













    try:
        destino = Path(destino)
        if destino.is_file():
            alvo = destino.with_name(destino.name + ".anterior")
            try:
                if alvo.exists():
                    alvo.unlink()
                destino.replace(alvo)
            except Exception:
                pass
    except Exception:
        pass



    try:
        if clone is not None and Path(clone).is_file():
            alvo_c = Path(clone).with_name(Path(clone).name + ".anterior")
            try:
                if alvo_c.exists():
                    alvo_c.unlink()
                Path(clone).replace(alvo_c)
            except Exception:
                pass
    except Exception:
        pass
    try:
        identidade = Path(identidade)

        extras = sorted(p.name[len(identidade.name):] for p in identidade.parent.glob(identidade.name + ".novo*")
                        if not p.name.endswith(".anterior"))
        for _sufixo in ["", ".velho"] + extras:
            try:
                origem = identidade.with_name(identidade.name + _sufixo)
                if not origem.is_dir():
                    continue
                alvo_id = origem.with_name(origem.name + ".anterior")
                try:
                    if alvo_id.exists():
                        shutil.rmtree(alvo_id, ignore_errors=True)
                    origem.replace(alvo_id)
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass


def gravar_perfil_local(resultado, destino=PERFIL_LOCAL) -> bool:
    'Grava ~/.config/dissero/perfil.json a partir do `content` (texto) da ferramenta MCP.'














    if not resultado or resultado.get("isError"):
        return False
    texto = " ".join(c.get("text", "") for c in (resultado.get("content") or []) if isinstance(c, dict))
    ini = texto.find("{")
    if ini < 0:
        return False
    corpo = texto[ini:].strip()
    try:
        perfil = json.loads(corpo)
    except Exception:
        return False
    if not _perfil_valido(perfil):
        return False
    em = str((resultado.get("_meta") or {}).get("em") or perfil.get("em") or "")
    atual = _ler_json(destino)
    atual = atual if isinstance(atual, dict) else {}
    marca_atual = str(atual.get("email_marca") or "")
    marca_nova = str((resultado.get("_meta") or {}).get("email_marca") or "")
    if (atual.get("_origem") == "servidor" and _mesmo_advogado(marca_atual, marca_nova)
            and str(atual.get("_em") or "") >= em):
        return False
    perfil = {k: v for k, v in perfil.items() if not str(k).startswith("_")}
    perfil.update({"_origem": "servidor", "_em": em, "_sha": hashlib.sha256(corpo.encode("utf-8")).hexdigest(),
                  "_texto_servidor": corpo})
    try:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.is_file():
            try:
                shutil.copy2(destino, str(destino) + ".anterior")
            except Exception:
                pass
        provisorio = destino.with_name(f"{destino.name}.tmp.{os.getpid()}")
        provisorio.write_text(json.dumps(perfil, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(provisorio, destino)
        return True
    except Exception:
        return False









RE_ENTRADA_IDENTIDADE = re.compile(
    r"word/(header\d+\.xml|footer\d+\.xml|_rels/(header|footer)\d+\.xml\.rels|"
    r"media/(?!\.{1,2}$)[^/\\]+)"
    r"|(assinatura|brasao)\.(png|jpe?g)")


def _entradas_zip(z):
    '[(nome, ZipInfo)] com o nome como o Worker o grava: UTF-8 SEM o bit 11 do zip, que o'


    saida = []
    for info in z.infolist():
        nome = info.filename
        if not info.flag_bits & 0x800:
            try:
                nome = nome.encode("cp437").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        saida.append((nome, info))
    return saida


TETO_IDENTIDADE_BYTES = 20 * 1024 * 1024


def _gravar_identidade_local(resultado, destino) -> bool:
    'Extrai o pacote de timbrado próprio (zip com header/footer/rels/media) em `destino`.'















    import base64
    import io
    import zipfile
    novo = None
    pode_limpar_novo = True
    try:
        if not resultado or resultado.get("isError"):
            return False
        texto = " ".join(c.get("text", "") for c in (resultado.get("content") or []) if isinstance(c, dict))
        dados = None
        if "base64:" in texto:
            dados = base64.b64decode(texto.split("base64:", 1)[1].strip())
        else:
            url = str((resultado.get("_meta") or {}).get("url") or "")
            if url and re.match(r"^https?://", url, re.I):
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA_CANAL}),
                                            timeout=20) as resp:
                    dados = resp.read(TETO_IDENTIDADE_BYTES + 1)
        if not dados or len(dados) > TETO_IDENTIDADE_BYTES:
            return False
        z = zipfile.ZipFile(io.BytesIO(dados))
        entradas = _entradas_zip(z)
        if not entradas:
            return False
        for nome, info in entradas:
            if not RE_ENTRADA_IDENTIDADE.fullmatch(nome):
                return False
            if info.file_size > TETO_IDENTIDADE_BYTES:
                return False

        destino = Path(destino)
        velho = destino.parent / f"{destino.name}.velho"




        if not destino.exists() and velho.exists():
            try:
                velho.replace(destino)
            except Exception:
                pass
        elif velho.exists():
            shutil.rmtree(velho, ignore_errors=True)





        agora_s = time.time()
        for orfao in destino.parent.glob(f"{destino.name}.novo*"):
            try:

                if (orfao.is_dir() and not orfao.name.endswith(".anterior")
                        and agora_s - orfao.stat().st_mtime > IDADE_ORFAO_S):
                    shutil.rmtree(orfao, ignore_errors=True)
            except Exception:
                pass
        novo = destino.parent / f"{destino.name}.novo.{os.getpid()}"
        if novo.exists():
            shutil.rmtree(novo)
        novo.mkdir(parents=True, exist_ok=True)
        for nome, info in entradas:
            alvo = novo / (nome[len("word/"):] if nome.startswith("word/") else nome)
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(z.read(info))


        mapping = {"origem": "servidor"}
        marca_identidade = str((resultado.get("_meta") or {}).get("email_marca") or "")
        if marca_identidade:
            mapping["marca"] = marca_identidade
        (novo / "mapping.json").write_text(json.dumps(mapping), encoding="utf-8")



        tinha_velho = destino.exists()
        if tinha_velho:
            destino.replace(velho)
        pode_limpar_novo = False
        try:
            novo.replace(destino)
        except Exception:
            if tinha_velho:
                try:
                    velho.replace(destino)
                except Exception:
                    pass
            raise
        if tinha_velho:
            shutil.rmtree(velho, ignore_errors=True)
        return True
    except Exception:
        if pode_limpar_novo and novo is not None:
            shutil.rmtree(novo, ignore_errors=True)
        elif novo is not None:



            try:
                if Path(destino).is_dir():
                    if novo.is_dir():
                        shutil.rmtree(novo, ignore_errors=True)



                    velho_corrida = Path(destino).parent / f"{Path(destino).name}.velho"
                    if velho_corrida.is_dir():
                        shutil.rmtree(velho_corrida, ignore_errors=True)
            except Exception:
                pass
        return False









_RX_SECAO_CLONE = re.compile(r"^=== (TRAJETÓRIA|MENTE|VOZ|REPERTÓRIO) · (.+?) ===$", re.M)
_CHAVE_SECAO_CLONE = {"TRAJETÓRIA": "trajetoria", "MENTE": "mente", "VOZ": "voz", "REPERTÓRIO": "repertorio"}


def gravar_clone_local(resultado, destino) -> bool:
    """Grava o que `clone_do_advogado` devolveu. True se gravou algo novo. NUNCA levanta."""
    try:
        if not resultado or resultado.get("isError"):
            return False
        textos = [c.get("text", "") for c in (resultado.get("content") or []) if isinstance(c, dict)]
        texto = (textos[0] if textos else "").strip()
        if not texto.startswith("[Dissero]") or not (
                "Clone do advogado" in texto or "não configurou Mente nem Voz" in texto):
            return False
        destino = Path(destino)
        sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        marca = str((resultado.get("_meta") or {}).get("email_marca") or "")
        atual = _ler_json(destino)
        if isinstance(atual, dict) and atual.get("_sha") == sha and str(atual.get("email_marca") or "") == marca:
            return False
        marcas = list(_RX_SECAO_CLONE.finditer(texto))
        secoes = {}
        for i, m in enumerate(marcas):
            fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
            secoes[_CHAVE_SECAO_CLONE[m.group(1)]] = {"texto": texto[m.end():fim].strip(),
                                                     "validada": m.group(2).startswith("validada em")}
        registro = {"_origem": "servidor", "_sha": sha, "_texto_servidor": texto, "secoes": secoes}
        if marca:
            registro["email_marca"] = marca
        destino.parent.mkdir(parents=True, exist_ok=True)
        provisorio = destino.with_name(f"{destino.name}.tmp.{os.getpid()}")
        provisorio.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(provisorio, destino)
        return True
    except Exception:
        return False


def sincronizar_perfil(origem, token_oauth, http=baixar_perfil_http, destino=PERFIL_LOCAL,
                       identidade=IDENTIDADE_LOCAL, clone=None) -> bool:
    'Perfil do servidor -> arquivo local, logo depois do login. NUNCA levanta e nunca bloqueia: é'














    if not token_oauth:
        return False
    try:
        r = http(origem, token_oauth, "perfil")
        atual = _ler_json(destino)
        atual = atual if isinstance(atual, dict) else {}
        marca_atual = str(atual.get("email_marca") or "")
        marca_nova = str((r.get("_meta") or {}).get("email_marca") or "")



        clone = Path(clone) if clone is not None else Path(destino).with_name("clone.json")
        if _advogado_diferente_confirmado(marca_atual, marca_nova):
            _quarentenar_advogado_anterior(destino, identidade, clone)
        troca_de_advogado = not _mesmo_advogado(marca_atual, marca_nova)
        gravou = gravar_perfil_local(r, destino)


        meta_perfil = r.get("_meta") or {}
        if meta_perfil.get("timbrado") == "proprio" or meta_perfil.get("pacote"):



            motivos = gravou or troca_de_advogado or not Path(identidade).is_dir()
            backfill = not motivos and _identidade_marca_ausente(identidade)
            if motivos or backfill:
                baixou = False
                try:
                    baixou = _gravar_identidade_local(http(origem, token_oauth, "identidade"),
                                                      identidade)
                except Exception:
                    baixou = False
                if backfill and not baixou:
                    _anotar_backfill_falho(identidade)

        try:
            gravar_clone_local(http(origem, token_oauth, "clone"), clone)
        except Exception:
            pass
        return gravou
    except Exception:
        return False


def _disparar_destacado(iniciar, flag) -> bool:
    'Roda ESTE MESMO arquivo com `flag` num processo destacado: stdin/stdout/stderr no vazio,'



    try:
        alvo = str(Path(__file__).resolve())
    except Exception:
        return False
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200
    else:
        kw["start_new_session"] = True
    try:
        iniciar([sys.executable, alvo, flag], **kw)
        return True
    except Exception:
        return False


def sincronizar_em_segundo_plano(iniciar=subprocess.Popen) -> bool:
    'Dispara a sincronização do perfil sem esperar por ela (`--sincronizar-perfil`). O filho'

    return _disparar_destacado(iniciar, FLAG_SINCRONIZAR)


def copia_do_canal_instalada(instalados=INSTALADOS) -> bool:
    d = _ler_json(instalados) or {}
    return PLUGIN in (d.get("plugins") or {})


def _raiz_do_plugin():
    return Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)


def instalar_em_segundo_plano(iniciar=subprocess.Popen, achar=shutil.which, trava=None):
    'Dispara a instalação da cópia do canal sem esperar: hook tem teto de segundos, o install'






    if not achar("claude"):
        return False
    try:
        if _modulo_ativar(_raiz_do_plugin()).trava_ativa(trava or TRAVA_INSTALACAO):
            return False
    except Exception:
        return False
    return _disparar_destacado(iniciar, FLAG_INSTALAR)


def executor_de_instalacao() -> int:
    """O filho destacado de `instalar_em_segundo_plano`. Sequencial e sob trava."""
    exe = shutil.which("claude")
    if not exe:
        return 127
    rc, _saida = _modulo_ativar(_raiz_do_plugin()).instalar_sequencial(exe, PLUGIN, TRAVA_INSTALACAO)
    return 0 if rc in (0, RC_TRAVA_OCUPADA) else rc


def vigiar_settings(settings=SETTINGS, estado=ESTADO, a_confirmar=None):
    'O VIGIA. Compara as chaves de topo do settings com as da cópia que o próprio plugin guardou ao'


















    try:
        ac = _modulo_ativar(_raiz_do_plugin())
        copias = ac.copias_settings(settings)
        if not copias:
            return None
        vigia_p = Path(estado).with_name(VIGIA)
        registro = _ler_json(vigia_p)
        registro = registro if isinstance(registro, dict) else {}
        pendente = registro.get("pendente") if isinstance(registro.get("pendente"), dict) else {}
        ultima = copias[-1]
        if pendente.get("copia"):
            ultima = next((c for c in copias if c.name == str(pendente.get("copia"))), ultima)
        try:
            antes = ac.ler_settings(ultima) or {}
        except ac.ErroSettings:
            return None
        ilegivel = False
        try:
            atual = ac.ler_settings(settings) or {}
        except ac.SettingsOcupado:
            return None
        except ac.ErroSettings:
            atual, ilegivel = {}, True
        faltam = sorted(set(antes) - set(atual) - ac.chaves_removidas_de_proposito(settings, ultima))
        if not faltam and not ilegivel:
            if registro:
                _apagar(vigia_p)
            return None
        assinatura = hashlib.sha256(f"{ultima.name}|{ilegivel}|{','.join(faltam)}".encode("utf-8")).hexdigest()[:16]
        if registro.get("avisado") == assinatura:
            return None
        _gravar_estado(vigia_p, {"pendente": {"copia": ultima.name, "assinatura": assinatura}})
        confirmacao = (vigia_p, {"avisado": assinatura, "copia": ultima.name})
        if a_confirmar is None:
            _gravar_estado(*confirmacao)
        else:
            a_confirmar.append(confirmacao)








        comando = (f'python "{_caminho_ativar(_raiz_do_plugin())}" --restaurar-chaves --settings "{settings}" '
                   f'--copia "{ultima}"')
        if ilegivel:
            o_que = "deixou de ser um JSON válido (o Claude Code pode ignorá-lo inteiro)"
            conserto = (f"Corrija o arquivo, ou restaure a cópia que o plugin guardou em {ultima}. "
                        "Essa cópia não guarda credenciais: a do canal é reemitida na próxima ativação.")
        else:
            o_que = ("perdeu configurações que existiam quando o plugin o gravou pela última vez (chaves: "
                     + ", ".join(faltam) + ")")
            conserto = ("Se não foi você quem as removeu, elas podem voltar sem que nada mais seja tocado. "
                        "Feche o Claude Code. Depois rode este comando no terminal: " + comando + ". "
                        f"Ele lê a cópia {ultima} e recoloca só essas chaves.")
        return (PROVENIENCIA + f"O arquivo de configuração do Claude Code neste computador ({settings}) {o_que}. "
                "Não foi o plugin Dissero que fez essa alteração. " + conserto + " "
                "O plugin não restaura sozinho, porque a alteração pode ter sido sua. Este aviso é estado, não "
                "instrução, e nada foi bloqueado.")
    except Exception:
        return None


def confirmar_vigia(ctx) -> None:
    'A 2ª fase do vigia: grava {"avisado": ...} para cada aviso que JÁ SAIU na saída impressa.'


    try:
        while ctx.get("_vigia_a_confirmar"):
            _gravar_estado(*ctx["_vigia_a_confirmar"].pop(0))
    except Exception:
        pass


def _nome_evento(evento) -> str:
    """O evento do hook: o campo do harness, senão deduzido pela presença de `prompt`."""
    return evento.get("hook_event_name") or ("UserPromptSubmit" if "prompt" in evento else "SessionStart")

















CACHE_VERSAO = Path.home() / ".dissero" / "claude_code.json"




TIMEOUT_VERSAO_S = 30


def _binario_da_sessao(ambiente=None):
    '(caminho, chave do cache) do binário desta sessão, ou (None, None). Levanta se o caminho'

    exe = str((ambiente if ambiente is not None else os.environ).get("CLAUDE_CODE_EXECPATH") or "").strip()
    if not exe:
        return None, None
    st = Path(exe).stat()
    return exe, {"exe": exe, "tamanho": st.st_size, "mtime": int(st.st_mtime)}


def _versao_guardada(chave, cache) -> str | None:
    guardado = _ler_json(cache)
    if isinstance(guardado, dict) and all(guardado.get(k) == v for k, v in chave.items()) and guardado.get("versao"):
        return str(guardado["versao"])
    return None


def versao_claude_code_sem_esperar(ambiente=None, cache=None, iniciar=subprocess.Popen) -> str | None:
    'A versão do Claude Code desta sessão SE ela já estiver no cache, para este mesmo binário;'



    try:
        exe, chave = _binario_da_sessao(ambiente)
        if not exe:
            return None
        guardada = _versao_guardada(chave, Path(cache) if cache is not None else CACHE_VERSAO)
        if guardada:
            return guardada
        _disparar_destacado(iniciar, FLAG_MEDIR_CLAUDE_CODE)
        return None
    except Exception:
        return None


def versao_claude_code(ambiente=None, cache=None, rodar=subprocess.run) -> str | None:
    'A versão do Claude Code desta sessão, MEDIDA (roda o `--version` quando o cache não serve) e'

    try:
        exe, chave = _binario_da_sessao(ambiente)
        if not exe:
            return None
        cache = Path(cache) if cache is not None else CACHE_VERSAO
        guardada = _versao_guardada(chave, cache)
        if guardada:
            return guardada
        r = rodar([exe, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                  timeout=TIMEOUT_VERSAO_S)
        m = re.search(r"\b(\d+\.\d+\.\d+)\b", (r.stdout or "") + (r.stderr or "")) if r.returncode == 0 else None
        if not m:
            return None
        _gravar_estado(cache, {**chave, "versao": m.group(1)})
        return m.group(1)
    except Exception:
        return None


def aviso_claude_code(versao, minimo) -> str | None:
    'A frase ao advogado quando `versao` está abaixo de `minimo`, ou None. Versão que não se lê'

    def _t(v):
        m = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)\s*", str(v or ""))
        return tuple(int(x) for x in m.groups()) if m else None
    a, b = _t(versao), _t(minimo)
    if a is None or b is None or a >= b:
        return None
    return MSG_CLAUDE_CODE_ANTIGO.format(atual=versao, minimo=minimo)


def _claude_code_minimo(raiz) -> str | None:
    try:
        return str(_modulo_ativar(raiz).CLAUDE_CODE_MINIMO)
    except Exception:
        return None


def _acrescentar_aviso(saida, aviso):
    'Soma `aviso` à saída da SessionStart: ao modelo (additionalContext) e ao advogado'

    saida = dict(saida or {})
    hso = dict(saida.get("hookSpecificOutput") or {"hookEventName": "SessionStart"})
    hso["additionalContext"] = ((hso.get("additionalContext") or "") + "\n\n" + aviso).strip()
    saida["hookSpecificOutput"] = hso
    saida["systemMessage"] = ((saida.get("systemMessage") or "") + "\n\n" + aviso).strip()
    return saida


def executar(evento, ctx) -> dict | None:
    'O nucleo, testavel. `ctx`: raiz, origem, settings, estado (Path), agora, cofre_ler(), cofre_gravar(token),'












    avisos = ctx["_avisos_da_sessao"] = []
    ctx["_vigia_a_confirmar"] = []
    nome = _nome_evento(evento)
    sessao = nome == "SessionStart" and origem_da_copia(ctx["raiz"]) not in ("dev", "cowork")
    if sessao:



        try:
            if ctx.get("vigia"):
                aviso = ctx["vigia"](ctx["settings"], ctx["estado"])
            else:
                aviso = vigiar_settings(ctx["settings"], ctx["estado"], ctx["_vigia_a_confirmar"])
        except Exception:
            aviso = None
        if aviso:
            avisos.append(aviso)
    if sessao and ctx.get("migrar"):




        try:
            migrado = ctx["migrar"](evento.get("source"))
        except Exception:
            migrado = None
        if migrado in AVISOS_DO_CANAL:
            avisos.append(AVISOS_DO_CANAL[migrado])
    saida = _executar(evento, ctx)
    if not sessao:
        return saida
    for aviso in avisos:
        saida = _acrescentar_aviso(saida, aviso)
    try:
        versao = (ctx.get("versao_claude_code") or versao_claude_code_sem_esperar)()
        minimo = (ctx.get("claude_code_minimo") or (lambda: _claude_code_minimo(ctx["raiz"])))()
        aviso_v = aviso_claude_code(versao, minimo)
    except Exception:
        aviso_v = None
    if aviso_v:
        saida = _acrescentar_aviso(saida, aviso_v)
    return saida


def _executar(evento, ctx) -> dict | None:
    origem = origem_da_copia(ctx["raiz"])
    if origem == "dev":
        return None
    nome = _nome_evento(evento)




    if origem == "cowork":
        if nome == "SessionStart":
            msg = MSG_COWORK_REMOTO if cowork_remoto(ctx["raiz"]) else MSG_COWORK_DESKTOP
            return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}
        return None





    if nome == "UserPromptSubmit" and classificar_prompt(evento.get("prompt", "")) == "chave":
        return {"decision": "block", "reason": MSG_CHAVE_NO_PROMPT}
    estado_p = Path(ctx["estado"])
    estado = _ler_json(estado_p) or {}
    token = ler_token(ctx.get("cofre_ler"))
    novo = avaliar(estado, token, ctx["agora"], ctx["validar"])
    _gravar_estado(estado_p, novo)







    msg_login = None
    motivo_login = None
    login_tentado = False
    if not novo["ok"] and novo["motivo"] in ("sem_licenca", "invalida", "revogada"):
        tok_oauth = (ctx.get("oauth") or (lambda: ""))()
        if tok_oauth:
            emitido = {}
            ok_l, motivo_l, tenant_l = ativar_por_login(ctx["raiz"], ctx["origem"], tok_oauth, ctx["maquina"],
                                                        ctx["settings"], http=ctx.get("ativar_oauth"),
                                                        cofre=ctx.get("cofre_gravar"), pasta_marca=estado_p.parent,
                                                        emitido=emitido)



            pendente = not ok_l and str(motivo_l or "").endswith(SUFIXO_APOS_TOKEN)
            if ok_l or pendente:

                estado_login = {"ok": True, "motivo": "ativada_login", "validada_em": ctx["agora"],
                                "tenant": tenant_l, "token_marca": marca(emitido.get("token") or "")}


                if nome == "SessionStart":
                    (ctx.get("perfil") or (lambda: False))()
                _gravar_estado(estado_p, estado_login)
                if pendente:


                    saida = {"hookSpecificOutput": {"hookEventName": nome,
                                                    "additionalContext": mensagem_pendente(motivo_l, tenant_l)}}
                    aviso = aviso_pendente(motivo_l)
                    if aviso:
                        saida["systemMessage"] = aviso
                    return saida
                ctx["instalar"]()

                return {"hookSpecificOutput": {"hookEventName": nome,
                                               "additionalContext": MSG_LOGIN_OK.format(tenant=tenant_l)}}
            login_tentado = True
            motivo_login = motivo_l


            msg_login = _mensagem_motivo({"login_expirado": MSG_LOGIN_EXPIRADO, "revogada": MSG_REVOGADA,
                                          "limite_maquinas": MSG_REVOGADA, "vencida": MSG_VENCIDA,
                                          "aguardando": MSG_AGUARDANDO, "indisponivel": MSG_INDISPONIVEL,
                                          "limite_uso": MSG_LIMITE_USO,
                                          "sem_rede": MSG_SEM_REDE, "cofre_indisponivel": MSG_COFRE,
                                          **MSGS_SETTINGS}, motivo_l)
        elif (novo["motivo"] in ("sem_licenca", "invalida")
              and (ctx.get("login_situacao") or (lambda: "ausente"))() == "expirado"):


            msg_login = MSG_LOGIN_EXPIRADO









    casca = e_casca(ctx["raiz"])

    if nome == "SessionStart":





        if (ctx.get("oauth") or (lambda: ""))():
            (ctx.get("perfil") or (lambda: False))()
        if novo["ok"]:
            if not ctx["instalada"]() and _pode_instalar(ctx):
                ctx["instalar"]()
            return None
        if casca:






            if login_tentado and motivo_login:
                return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                               "additionalContext": mensagem_casca(motivo_login)
                                               + ESTADO_NAO_INSTRUCAO}}
            return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                           "additionalContext": MSG_CASCA + ESTADO_NAO_INSTRUCAO}}
        msg = msg_login or {"sem_licenca": MSG_PEDIR, "invalida": MSG_NAO_RECONHECIDA, "revogada": MSG_REVOGADA,
                            "sem_rede": MSG_SEM_REDE}[novo["motivo"]]

        return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                       "additionalContext": msg + ESTADO_NAO_INSTRUCAO + " Até a licença ser "
                                       "reconhecida, as skills do plugin Dissero não executam; o restante segue normal."
                                       + AVISO_COPIA_ANTIGA}}


    if novo["ok"]:
        return None
    prompt = evento.get("prompt", "")
    intencao = classificar_prompt(prompt)
    if casca:

        return None
    if intencao in ("chave", "chave_malformada"):
        return {"decision": "block", "reason": MSG_CHAVE_NO_PROMPT}
    if novo["motivo"] == "sem_rede":
        return {"decision": "block", "reason": MSG_SEM_REDE}
    if intencao == "contorno":
        return {"decision": "block", "reason": MSG_CONTORNO}
    if intencao == "alegacao":
        return {"decision": "block", "reason": MSG_ALEGACAO}
    msg = msg_login or {"sem_licenca": MSG_PEDIR, "invalida": MSG_NAO_RECONHECIDA, "revogada": MSG_REVOGADA}[novo["motivo"]]
    return {"decision": "block", "reason": msg}


def _pode_instalar(ctx) -> bool:
    'Se a SessionStart pode disparar a instalação da cópia do canal. Não com o settings ilegível'



    try:
        ac = _modulo_ativar(ctx["raiz"])
        d = ac.ler_settings(Path(ctx["settings"]))
        e = ((d or {}).get("extraKnownMarketplaces") or {}).get(MERCADO)
        if e == ac.bloco_marketplace(ctx["origem"]):
            return True
        marca_p, _dados = ac.consolidar_marcas(Path(ctx["estado"]).parent, ctx["settings"])
        return marca_p is None
    except Exception:
        return False


def _gravar_estado(p, estado):
    try:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(json.dumps(estado), encoding="utf-8")
    except Exception:
        pass


def _apagar(p):
    try:
        Path(p).unlink()
    except OSError:
        pass


def main():




    if FLAG_INSTALAR in sys.argv[1:]:
        try:
            return executor_de_instalacao()
        except Exception:
            return 1
    if FLAG_SINCRONIZAR in sys.argv[1:]:
        try:
            sincronizar_perfil(ORIGEM, ler_token_oauth(CREDENCIAIS, ORIGEM))
        except Exception:
            pass
        return 0
    if FLAG_MEDIR_CLAUDE_CODE in sys.argv[1:]:
        versao_claude_code()
        return 0
    try:
        evento = json.loads(sys.stdin.read() or "{}")
    except Exception:
        evento = {}
    raiz = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parent.parent))
    ctx = {
        "raiz": raiz, "origem": ORIGEM, "settings": SETTINGS,
        "estado": ESTADO, "agora": time.time(),
        "maquina": (_nome_da_maquina() or os.environ.get("COMPUTERNAME") or "maquina")[:80],
        "validar": lambda tok: validar_http(ORIGEM, tok),
        "instalar": instalar_em_segundo_plano, "instalada": copia_do_canal_instalada,
        "oauth": lambda: ler_token_oauth(CREDENCIAIS, ORIGEM), "ativar_oauth": None,

        "cofre_ler": COFRE.ler, "cofre_gravar": guardar_no_cofre,
        "migrar": lambda fonte=None: manter_canal(SETTINGS, ORIGEM, raiz, cofre_ler=COFRE.ler, fonte_sessao=fonte),
        "login_situacao": lambda: situacao_login(CREDENCIAIS, ORIGEM),

        "perfil": sincronizar_em_segundo_plano,

        "versao_claude_code": versao_claude_code_sem_esperar,
        "claude_code_minimo": lambda: _claude_code_minimo(raiz),
    }
    saida = executar_fechado(evento, ctx)
    if saida:


        print(json.dumps(saida, ensure_ascii=True))
        sys.stdout.flush()

        confirmar_vigia(ctx)
    return 0


def executar_fechado(evento, ctx) -> dict | None:
    '`executar` com FALHA FECHADA: defeito do próprio hook bloqueia em vez de liberar. A'



    try:
        return executar(evento, ctx)
    except Exception:
        if origem_da_copia(ctx["raiz"]) in ("dev", "cowork"):
            return None
        nome = _nome_evento(evento)



        try:
            avisos = list(ctx.get("_avisos_da_sessao") or []) if nome == "SessionStart" else []
        except Exception:
            avisos = []



        if e_casca(ctx["raiz"]):
            if nome == "UserPromptSubmit":
                return None
            saida = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                            "additionalContext": MSG_CASCA + ESTADO_NAO_INSTRUCAO}}
        elif nome == "UserPromptSubmit":
            return {"decision": "block", "reason": MSG_ERRO_INTERNO}
        else:
            saida = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                            "additionalContext": MSG_ERRO_INTERNO + ESTADO_NAO_INSTRUCAO + " Até a "
                                            "licença ser validada, as skills do plugin Dissero não executam; o restante "
                                            "segue normal."}}
        for aviso in avisos:
            saida = _acrescentar_aviso(saida, aviso)
        return saida


if __name__ == "__main__":
    raise SystemExit(main())
