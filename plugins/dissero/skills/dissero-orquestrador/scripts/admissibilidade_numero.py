#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admissibilidade_numero.py - quando um NUMERO passa a ser dizivel numa tese.

O QUE ESTE MODULO NAO E. Ele nao calcula chance de ganhar. Nao existe, aqui nem em lugar
nenhum deste plugin, funcao que estime probabilidade de exito de uma tese - e ha teste ao
lado que le o proprio fonte para provar que nao existe.

POR QUE EXISTE. A casa nao usa porcentagem de exito (regra de `validar-tese.md`): sem dado
empirico de vara, tribunal e periodo, o numero e falsa precisao. A regra esta certa e nao
muda. Mas ela e uma PROIBICAO SEM PORTA: como na pratica nunca ha numero, a regra nunca e
exercitada, e no dia em que alguem tiver dado empirico de verdade nao havera criterio para
distinguir o numero legitimo do palpite com aparencia de medida. Este modulo e a porta -
estreita, e trancada por fora.

O QUE ELE MEDE, E O QUE SE RECUSA A MEDIR. Mede FREQUENCIA OBSERVADA sobre PROXY DE
MOVIMENTO: quantos processos de uma classe, num tribunal, num periodo, registraram
determinado movimento processual. Isso e contagem de fato publico, e o DataJud responde.
NAO mede merito. "Em 62% dos casos o pedido foi julgado procedente" e afirmacao sobre
merito, e este modulo a RECUSA - o codigo de movimento diz que houve sentenca, nao diz o
que ela decidiu, e tratar um pelo outro e o erro que a regra central existe para impedir.

TRES RECUSAS, cada uma com motivo proprio na saida:
  1. GRANDEZA DE MERITO -> recusa. O chamador declara o que contou; categoria de merito nao
     passa, por mais que a amostra seja grande.
  2. AMOSTRA RASA -> recusa abaixo de PISO_AMOSTRA. Numero sobre 12 casos nao e estatistica,
     e anedota com casas decimais.
  3. INTERVALO LARGO DEMAIS -> recusa acima de LARGURA_MAXIMA. Um intervalo de 20% a 80%
     nao informa nada, e publicar o ponto medio dele (50%) e mentir com aritmetica correta.

NUNCA SAI PONTO SOZINHO. Quando admite, a saida traz `n`, o intervalo de Wilson e o nivel de
confianca - os tres, sempre, na mesma estrutura. Nao ha caminho no codigo que devolva a
proporcao sem eles. Um numero solto e exatamente o que a regra central proibe, e um modulo
que o produzisse "so para uso interno" seria a fonte do vazamento.

INTERVALO DE WILSON, e nao o normal simples. O intervalo normal (p +- z*sqrt(p(1-p)/n))
degenera perto de 0 e de 1: com 0 sucesso em 30 ele devolve o intervalo [0, 0], que afirma
IMPOSSIBILIDADE a partir de uma amostra pequena. O de Wilson nao degenera, e por isso e o
usado. Stdlib pura - so `math`.

O TETO QUE O PROPRIO ENCANAMENTO IMPOE. A API publica do DataJud
devolve `hits.total` como {"value": 10000, "relation": "gte"} - ou seja, acima de dez mil ela
NAO diz quantos sao, diz "pelo menos". E o cliente somente-leitura da casa
(`datajud_client.py`) so aceita `query` e `_source` no topo, entao nao ha `aggs`,
`track_total_hits` nem contagem exata por agregacao. Consequencia: n acima de
TETO_CONTAGEM_EXATA e ESTIMATIVA POR PISO, e a confianca cai por isso - nao sobe. O chamador
declara `contagem_exata=False` nesse caso, e quem esquecer de declarar recebe a confianca
mais alta sobre um dado que nao a merece; por isso o campo e OBRIGATORIO e nao tem padrao.

FALHA FECHADA DUPLA, igual aos outros motores da casa: a funcao publica exige
`autorizado=True` explicito, e a CLI exige DSR_ADMISSIBILIDADE_NUMERO=1 no ambiente.
Desligar um nao liga o outro. Alem das duas, a ficha `jurimetria_admissibilidade` do registro
de capacidades e lida a cada avaliacao: desligada (`ficha_desligada`) ou vencida
(`ficha_vencida`), recusa, com o codigo no campo `ficha_recusada`.

Uso:
    DSR_ADMISSIBILIDADE_NUMERO=1 python admissibilidade_numero.py \\
        --sucessos 340 --total 1200 --grandeza movimento_processual \\
        --rotulo "baixa definitiva" --contagem-exata sim
Exit 0 numero ADMISSIVEL - 2 RECUSADO (falha fechada).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
from ficha_capacidade import FichaRecusada, exigir as exigir_ficha

SCHEMA_VERSION = "dsr.admissibilidade_numero.v1"
VARIAVEL_AMBIENTE = "DSR_ADMISSIBILIDADE_NUMERO"
CAPACIDADE = "jurimetria_admissibilidade"










PISO_AMOSTRA = 30
LARGURA_MAXIMA = 0.30
TETO_CONTAGEM_EXATA = 10000

Z_95 = 1.959963985



GRANDEZAS_ADMITIDAS = {
    "movimento_processual": (
        "contagem de processos que registraram determinado MOVIMENTO na tabela do CNJ. "
        "Fato publico e verificavel; nao diz o conteudo da decisao"),
    "tempo_ate_movimento": (
        "tempo decorrido entre o ajuizamento e determinado movimento. Fato de calendario"),
    "distribuicao_por_orgao": (
        "como os processos de uma classe se distribuem entre orgaos julgadores"),
    "distribuicao_por_classe": (
        "como os processos se distribuem entre classes processuais"),
}



GRANDEZAS_DE_MERITO = {
    "procedencia", "improcedencia", "exito", "sucesso", "ganho", "vitoria", "derrota",
    "provimento", "desprovimento", "condenacao", "absolvicao", "acolhimento",
    "chance_de_exito", "probabilidade_de_exito", "merito",
}

MOTIVO_MERITO = (
    "GRANDEZA DE MERITO: '%s' mede o que a decisao DECIDIU, e nao um fato processual "
    "contavel. Codigo de movimento diz que houve sentenca; nao diz o que ela julgou. "
    "Estimar merito por proxy de movimento e falsa precisao com aparencia de dado - "
    "exatamente o que a regra central de validar-tese proibe. Nenhum tamanho de amostra "
    "conserta isso: o defeito e da GRANDEZA, nao do n.")

MOTIVO_GRANDEZA_DESCONHECIDA = (
    "grandeza '%s' nao esta na lista fechada de grandezas admitidas (%s). Grandeza nova e "
    "decisao de quem responde pela tese, e nao literal novo num chamador")

MOTIVO_AMOSTRA_RASA = (
    "AMOSTRA RASA: n=%d esta abaixo do piso de %d. Numero sobre amostra assim nao e "
    "estatistica, e anedota com casas decimais")

MOTIVO_INTERVALO_LARGO = (
    "INTERVALO LARGO DEMAIS: de %.1f%% a %.1f%% (largura %.1f pontos, maximo %.1f). Um "
    "intervalo assim nao informa, e publicar o ponto medio dele seria mentir com "
    "aritmetica correta")

MOTIVO_DESLIGADO = (
    "modulo nao autorizado: a funcao publica exige autorizado=True e a linha de comando "
    "exige %s=1 no ambiente. Numero em tese nasce PROIBIDO por validar-tese.md; este "
    "modulo e a excecao estreita, e excecao nao se aplica sozinha" % VARIAVEL_AMBIENTE)

AVISO_PROXY = (
    "PROXY, NAO MERITO: este numero descreve movimentacao processual observada, e NAO a "
    "chance de exito da tese. Ao levar para o cliente ou para a peca, diga o que foi "
    "contado - nunca 'chance de ganhar'")

AVISO_CONTAGEM_POR_PISO = (
    "CONTAGEM POR PISO: a API publica do DataJud devolve no maximo %d com relacao 'gte', e "
    "o cliente somente-leitura da casa nao aceita agregacao. O n usado e PISO, nao total, e "
    "a confianca foi rebaixada por isso" % TETO_CONTAGEM_EXATA)


def _wilson(sucessos, total, z=Z_95):
    'Intervalo de Wilson. Nao degenera em 0 nem em 1, que e a razao de nao usar o normal:'


    if total <= 0:
        return (0.0, 1.0)
    p = sucessos / total
    z2 = z * z
    denom = 1.0 + z2 / total
    centro = (p + z2 / (2.0 * total)) / denom
    meia = (z / denom) * math.sqrt(p * (1.0 - p) / total + z2 / (4.0 * total * total))
    return (max(0.0, centro - meia), min(1.0, centro + meia))


def _nivel_confianca(total, largura, contagem_exata):
    'BAIXA e o padrao, e sobe com dificuldade. Amostra rasa e contagem por piso NUNCA'


    if not contagem_exata:
        return "baixa"
    if total < 100 or largura > 0.20:
        return "baixa"
    if total < 400 or largura > 0.10:
        return "media"
    return "alta"


def avaliar(sucessos, total, grandeza, rotulo, contagem_exata, autorizado=False,
            piso_amostra=PISO_AMOSTRA, largura_maxima=LARGURA_MAXIMA, hoje=None,
            registro_capacidades=None):
    'Diz se o numero pode ser dito, e nunca devolve a proporcao sozinha.'






    motivos = []
    ficha_recusada = None

    if autorizado is not True:
        motivos.append(MOTIVO_DESLIGADO)
    try:
        exigir_ficha(CAPACIDADE, hoje=hoje, registro=registro_capacidades)
    except FichaRecusada as exc:
        ficha_recusada = exc.codigo
        motivos.append(exc.mensagem)

    if not isinstance(sucessos, int) or isinstance(sucessos, bool) or sucessos < 0:
        motivos.append("sucessos deve ser inteiro nao negativo")
    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
        motivos.append("total deve ser inteiro positivo")
    if not motivos and sucessos > total:
        motivos.append("sucessos (%d) maior que o total (%d)" % (sucessos, total))

    chave = str(grandeza or "").strip().lower()
    if chave in GRANDEZAS_DE_MERITO:
        motivos.append(MOTIVO_MERITO % chave)
    elif chave not in GRANDEZAS_ADMITIDAS:
        motivos.append(MOTIVO_GRANDEZA_DESCONHECIDA
                       % (chave or "(vazia)", ", ".join(sorted(GRANDEZAS_ADMITIDAS))))

    if not str(rotulo or "").strip():
        motivos.append("rotulo ausente: sem dizer O QUE foi contado, o numero nao e "
                       "conferivel por quem le")

    if not isinstance(contagem_exata, bool):
        motivos.append("contagem_exata deve ser booleano declarado: sem ele nao se sabe se "
                       "o n e total ou piso, e a confianca seria calculada sobre suposicao")

    if piso_amostra < PISO_AMOSTRA:
        motivos.append("piso_amostra=%d abaixo do piso da casa (%d): afrouxar o piso de "
                       "amostra e afrouxar a unica trava que separa numero de anedota"
                       % (piso_amostra, PISO_AMOSTRA))
    if largura_maxima > LARGURA_MAXIMA:
        motivos.append("largura_maxima=%.2f acima do teto da casa (%.2f)"
                       % (largura_maxima, LARGURA_MAXIMA))

    if motivos:
        recusa = {"schema_version": SCHEMA_VERSION, "estado": "recusado", "motivos": motivos}
        if ficha_recusada:
            recusa["ficha_recusada"] = ficha_recusada
        return recusa

    if total < piso_amostra:
        motivos.append(MOTIVO_AMOSTRA_RASA % (total, piso_amostra))

    baixo, alto = _wilson(sucessos, total)
    largura = alto - baixo
    if largura > largura_maxima:
        motivos.append(MOTIVO_INTERVALO_LARGO
                       % (baixo * 100, alto * 100, largura * 100, largura_maxima * 100))

    if motivos:
        return {"schema_version": SCHEMA_VERSION, "estado": "recusado", "motivos": motivos}

    avisos = [AVISO_PROXY]
    if not contagem_exata:
        avisos.append(AVISO_CONTAGEM_POR_PISO)

    return {
        "schema_version": SCHEMA_VERSION,
        "estado": "admissivel",
        "grandeza": chave,
        "rotulo": str(rotulo).strip(),
        "n": total,
        "ocorrencias": sucessos,
        "proporcao": sucessos / total,
        "intervalo_95": [baixo, alto],
        "largura_intervalo": largura,
        "contagem_exata": contagem_exata,
        "confianca": _nivel_confianca(total, largura, contagem_exata),
        "frase_sugerida": (
            "%s em %d de %d processos observados (%.1f%%, intervalo de 95%%: %.1f%% a "
            "%.1f%%; %s)"
            % (str(rotulo).strip(), sucessos, total, 100.0 * sucessos / total,
               baixo * 100, alto * 100,
               "contagem exata" if contagem_exata else "n como PISO, nao total")),
        "avisos": avisos,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sucessos", type=int, required=True)
    ap.add_argument("--total", type=int, required=True)
    ap.add_argument("--grandeza", required=True,
                    help="uma de: " + ", ".join(sorted(GRANDEZAS_ADMITIDAS)))
    ap.add_argument("--rotulo", required=True, help="o que foi contado, em portugues")
    ap.add_argument("--contagem-exata", required=True, choices=("sim", "nao"),
                    help="'nao' quando o n veio de hits.total com relacao 'gte'")
    ap.add_argument("--piso-amostra", type=int, default=PISO_AMOSTRA)
    ap.add_argument("--largura-maxima", type=float, default=LARGURA_MAXIMA)
    args = ap.parse_args(argv)

    autorizado = os.environ.get(VARIAVEL_AMBIENTE) == "1"
    r = avaliar(args.sucessos, args.total, args.grandeza, args.rotulo,
                args.contagem_exata == "sim", autorizado=autorizado,
                piso_amostra=args.piso_amostra, largura_maxima=args.largura_maxima)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["estado"] == "admissivel" else 2


if __name__ == "__main__":
    sys.exit(main())
