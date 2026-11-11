#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auditar_calculo_alheio.py - confere o calculo do outro lado CONTRA ELE MESMO.

POR QUE NAO RECALCULA. Recalcular o valor exige indice oficial, tabela de INSS, fracao de
progressao e revisao humana, e cada uma dessas contas e capacidade propria, com ficha e chave
(`capacidades_juridicas.json`). Este modulo nao recalcula nada. Ele audita a COERENCIA
INTERNA do que a outra parte apresentou: soma que nao fecha, fator que nao bate com o
percentual declarado, mesma base saindo com dois valores, periodo fora do contrato, item
obrigatorio do laudo ausente. Nenhuma dessas conferencias precisa de fonte externa, porque a
referencia e o proprio documento auditado.

E ISSO NAO E UM CONSOLO. Aritmetica que nao fecha e o apontamento mais forte que existe numa
impugnacao: nao se discute tese, mostra-se a conta. O que este modulo NAO faz e dizer que o
valor esta juridicamente errado - para isso seria preciso recalcular, e recalcular sem fonte
oficial e o defeito que a politica das capacidades existe para impedir.

O QUE ELE NAO FAZ, e nao pode passar a fazer sem virar outra coisa:
  - nao recalcula, nao corrige e nao propoe valor;
  - nao aplica indice, aliquota, fracao nem correcao monetaria;
  - nao conclui que o laudo esta errado: todo apontamento sai `a_conferir`, e quem conclui e
    o advogado com o assistente tecnico contador;
  - nao substitui o assistente tecnico. O cenario 10 e marcado RISCO, e continua sendo.

AS SEIS CONFERENCIAS, e cada uma corresponde a um apontamento com dispositivo quando cabe:
  1. SOMA - a soma das parcelas bate com o total declarado, dentro da tolerancia?
  2. FATOR - valor declarado da parcela bate com base x fator, dentro da tolerancia?
  3. BASE DIVERGENTE - a MESMA base aparece com valores diferentes em parcelas distintas?
  4. PERIODO - o periodo da parcela cai dentro do periodo de apuracao declarado?
  5. SINAL - parcela declarada como desconto vem positiva, ou vice-versa?
  6. ESTRUTURA - os itens que o CPC art. 473 e a NBC TP 01 (R2) item 58 exigem estao presentes?

A TOLERANCIA E O UNICO NUMERO ARBITRARIO, e por isso e configuravel nos dois pontos de
entrada - com PISO. Centavo de arredondamento nao e inconsistencia: um laudo com trinta
parcelas acumula diferenca de arredondamento legitima. TOLERANCIA_PADRAO = 0.01 por parcela,
escalada pela raiz do numero de parcelas na conferencia da soma (erro de arredondamento
cresce com a raiz, nao linearmente). Tolerancia ZERO transformaria todo laudo em suspeito, e
apontamento que aparece sempre nao e lido.

TRES TRANCAS: a funcao publica exige `autorizado=True`, a CLI exige DSR_AUDITAR_CALCULO=1, e
as duas leem a ficha `auditoria_pjecalc` do registro de capacidades: ficha desligada
(`ficha_desligada`) ou vencida (`ficha_vencida`) recusa, e o motivo diz o que fazer. A recusa
pela ficha sai tambem no campo `ficha_recusada`.

SIGILO. A entrada e o calculo da outra parte, que traz valores e pode trazer nome. A SAIDA
carrega o rotulo da parcela como veio (e preciso, para o apontamento ser acionavel) e os
numeros - nao ha como apontar sem eles. Resultado deste modulo e SAIDA DE EXECUCAO, nunca
conteudo de repositorio.

Stdlib apenas. Uso:
    DSR_AUDITAR_CALCULO=1 python auditar_calculo_alheio.py --arquivo calculo.json
Exit 0 sem apontamento - 1 com apontamento - 2 RECUSADO (falha fechada).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import math
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
from ficha_capacidade import FichaRecusada, exigir as exigir_ficha

SCHEMA_VERSION = "dsr.auditoria_calculo.v1"
VARIAVEL_AMBIENTE = "DSR_AUDITAR_CALCULO"
CAPACIDADE = "auditoria_pjecalc"



TOLERANCIA_PADRAO = 0.01
PISO_TOLERANCIA = 0.0




ITENS_LAUDO = (
    ("objeto", "exposicao do objeto da pericia", "CPC, art. 473, I"),
    ("analise", "analise tecnica ou cientifica realizada", "CPC, art. 473, II"),
    ("metodo", "indicacao do metodo, esclarecido e demonstrado como predominantemente "
               "aceito", "CPC, art. 473, III"),
    ("respostas_quesitos", "resposta conclusiva a TODOS os quesitos",
     "CPC, art. 473, IV"),
    ("resumo_autos", "sintese do caso", "NBC TP 01 (R2), item 58, b"),
    ("relato_diligencias", "relato das diligencias realizadas", "NBC TP 01 (R2), item 58, e"),
    ("termo_encerramento", "termo de encerramento com relacao de anexos e apendices",
     "NBC TP 01 (R2), item 58, h"),
    ("assinatura_crc", "identificacao e assinatura com numero de registro no CRC e, se houver, "
                       "no CNPC", "NBC TP 01 (R2), item 58, i"),
)

MOTIVO_DESLIGADO = (
    "modulo nao autorizado: a funcao publica exige autorizado=True e a linha de comando exige "
    "%s=1 no ambiente. A ficha %s do registro de capacidades e outra tranca, conferida a "
    "parte" % (VARIAVEL_AMBIENTE, CAPACIDADE))

AVISO_NAO_RECALCULA = (
    "ESTE MODULO NAO RECALCULA. Ele confere o calculo apresentado CONTRA ELE MESMO - soma, "
    "fator, base, periodo, sinal e estrutura. Nao aplica indice, aliquota nem correcao, e "
    "portanto NAO diz que o valor esta juridicamente errado: diz que a conta nao fecha com a "
    "propria premissa declarada")

AVISO_A_CONFERIR = (
    "TODO APONTAMENTO E `a_conferir`, nunca conclusao. Quem conclui e o advogado com o "
    "assistente tecnico contador - a pericia contabil e competencia exclusiva de contador "
    "regular no CRC (NBC TP 01, item 4), e este modulo nao a substitui")




_INTEIRO = re.compile(r"[+-]?\d+")

_BRASILEIRO = re.compile(r"[+-]?(?:[1-9]\d{0,2}(?:\.\d{3})+|\d+)(?:,\d+)?")


_PONTO_DECIMAL = re.compile(r"[+-]?(?:\d+\.(?:\d{1,2}|\d{4,})|0\.\d+)")
_SO_NUMERAL = re.compile(r"[+-]?[\d.,]*\d[\d.,]*")


_FATOR_PONTO = re.compile(r"[+-]?\d+\.\d+")


def _ler(valor, fator=False):
    '(numero, None), ou (None, motivo) com motivo `ilegivel` ou `ambiguo`.'




    if isinstance(valor, bool) or valor is None:
        return None, "ilegivel"
    if isinstance(valor, (int, float)):
        return float(valor), None
    if not isinstance(valor, str):
        return None, "ilegivel"
    bruto = valor.strip().replace(" ", "")
    if not bruto:
        return None, "ilegivel"
    if _INTEIRO.fullmatch(bruto):
        return float(bruto), None
    if fator and _FATOR_PONTO.fullmatch(bruto):
        return float(bruto), None
    if _BRASILEIRO.fullmatch(bruto):
        return float(bruto.replace(".", "").replace(",", ".")), None
    if _PONTO_DECIMAL.fullmatch(bruto):
        return float(bruto), None
    if _SO_NUMERAL.fullmatch(bruto):
        return None, "ambiguo"
    return None, "ilegivel"


def _num(valor):
    """Numero, ou None (ilegivel ou ambiguo)."""
    return _ler(valor)[0]


def _ambiguo(campo, rotulo, valor):
    return _ap("valor_ambiguo" if campo != "total" else "total_ambiguo", rotulo, None, None,
               "o %s %r nao segue um formato de numero reconhecivel (por exemplo 1.000 ou "
               "1.234,56), e nao foi lido para nao ser lido errado: confira na planilha "
               "original. %s" % (campo, valor, {
                   "valor": "Esta parcela nao entra na soma, e a soma passa a nao poder ser "
                            "conferida",
                   "base": "A conferencia do fator desta parcela nao foi feita",
                   "fator": "A conferencia do fator desta parcela nao foi feita",
                   "total": "Sem o total nao ha como conferir a soma"}[campo]))


def _data(valor):
    if not isinstance(valor, str) or len(valor.strip()) < 10:
        return None
    b = valor.strip()
    try:
        return _dt.date(int(b[0:4]), int(b[5:7]), int(b[8:10]))
    except (ValueError, TypeError):
        return None


def _ap(tipo, parcela, medido, declarado, texto, dispositivo=None):
    ap = {"tipo": tipo, "estado": "a_conferir", "parcela": parcela, "o_que_diz": texto}
    if medido is not None:
        ap["medido"] = round(medido, 4)
    if declarado is not None:
        ap["declarado"] = round(declarado, 4)
    if medido is not None and declarado is not None:
        ap["diferenca"] = round(medido - declarado, 4)
    if dispositivo:
        ap["dispositivo"] = dispositivo
    return ap


def auditar(calculo, autorizado=False, tolerancia=TOLERANCIA_PADRAO, hoje=None,
            registro_capacidades=None):
    'Apontamentos de coerencia interna. Nunca conclui, nunca recalcula.'



    motivos = []
    ficha_recusada = None
    if autorizado is not True:
        motivos.append(MOTIVO_DESLIGADO)
    try:
        exigir_ficha(CAPACIDADE, hoje=hoje, registro=registro_capacidades)
    except FichaRecusada as exc:
        ficha_recusada = exc.codigo
        motivos.append(exc.mensagem)
    if not isinstance(calculo, dict):
        motivos.append("calculo deve ser objeto")
    if not isinstance(tolerancia, (int, float)) or isinstance(tolerancia, bool):
        motivos.append("tolerancia deve ser numero")
    elif tolerancia < PISO_TOLERANCIA:
        motivos.append("tolerancia negativa: %r" % tolerancia)
    if motivos:
        recusa = {"schema_version": SCHEMA_VERSION, "estado": "recusado", "motivos": motivos}
        if ficha_recusada:
            recusa["ficha_recusada"] = ficha_recusada
        return recusa

    parcelas = calculo.get("parcelas")
    if not isinstance(parcelas, list) or not parcelas:
        return {"schema_version": SCHEMA_VERSION, "estado": "recusado",
                "motivos": ["`parcelas` deve ser lista nao vazia: sem parcela nao ha o que "
                            "conferir, e devolver 'nenhum apontamento' aqui seria dizer que "
                            "a conta fecha"]}

    aps = []
    soma = 0.0
    bases = {}
    ini_ap = _data(calculo.get("periodo_inicio"))
    fim_ap = _data(calculo.get("periodo_fim"))

    for i, p in enumerate(parcelas):
        rot = str((p or {}).get("rotulo") or "parcela[%d]" % i).strip() or "parcela[%d]" % i
        if not isinstance(p, dict):
            aps.append(_ap("parcela_ilegivel", rot, None, None,
                           "item da lista nao e objeto: nao ha como conferir"))
            continue
        valor, problema = _ler(p.get("valor"))
        if problema == "ambiguo":
            aps.append(_ambiguo("valor", rot, p.get("valor")))
            continue
        if valor is None:
            aps.append(_ap("valor_ilegivel", rot, None, None,
                           "valor ausente ou ilegivel: parcela sem valor nao entra na soma, "
                           "e a soma passa a nao poder ser conferida"))
            continue
        soma += valor


        base, prob_base = _ler(p.get("base"))
        fator, prob_fator = _ler(p.get("fator"), fator=True)
        for campo, prob in (("base", prob_base), ("fator", prob_fator)):
            if prob == "ambiguo":
                aps.append(_ambiguo(campo, rot, p.get(campo)))
        if base is not None and fator is not None:
            esperado = base * fator
            if abs(esperado - valor) > tolerancia:
                aps.append(_ap("fator_nao_bate", rot, esperado, valor,
                               "base x fator nao chega ao valor declarado da parcela"))


        nome_base = str(p.get("base_nome") or "").strip()
        if nome_base and base is not None:
            visto = bases.setdefault(nome_base, base)
            if abs(visto - base) > tolerancia:
                aps.append(_ap("base_divergente", rot, base, visto,
                               "a base '%s' aparece com dois valores diferentes no mesmo "
                               "calculo" % nome_base))


        pi, pf = _data(p.get("periodo_inicio")), _data(p.get("periodo_fim"))
        if pi and pf and pi > pf:
            aps.append(_ap("periodo_invertido", rot, None, None,
                           "o periodo da parcela comeca depois de terminar"))
        for rotulo_data, d in (("inicio", pi), ("fim", pf)):
            if d and ini_ap and d < ini_ap:
                aps.append(_ap("periodo_fora_da_apuracao", rot, None, None,
                               "o %s da parcela e anterior ao periodo de apuracao declarado "
                               "(%s)" % (rotulo_data, ini_ap.isoformat())))
            if d and fim_ap and d > fim_ap:
                aps.append(_ap("periodo_fora_da_apuracao", rot, None, None,
                               "o %s da parcela e posterior ao periodo de apuracao declarado "
                               "(%s)" % (rotulo_data, fim_ap.isoformat())))


        if p.get("desconto") is True and valor > 0:
            aps.append(_ap("sinal_contrario", rot, valor, None,
                           "declarada como DESCONTO e vem com valor positivo: somada assim, "
                           "ela aumenta o total em vez de reduzir"))
        if p.get("desconto") is False and valor < 0:
            aps.append(_ap("sinal_contrario", rot, valor, None,
                           "declarada como credito e vem com valor negativo"))



    total, prob_total = _ler(calculo.get("total"))
    if prob_total == "ambiguo":
        aps.append(_ambiguo("total", None, calculo.get("total")))
    elif total is None:
        aps.append(_ap("total_ausente", None, soma, None,
                       "o calculo nao declara total: sem ele nao ha como conferir a soma, e "
                       "a soma e a conferencia mais forte que existe"))
    else:
        folga = tolerancia * math.sqrt(max(len(parcelas), 1))
        if abs(soma - total) > folga:
            aps.append(_ap("soma_nao_fecha", None, soma, total,
                           "a soma das parcelas nao chega ao total declarado (folga de "
                           "arredondamento admitida: %.4f)" % folga))


    laudo = calculo.get("laudo")
    estrutura = []
    if isinstance(laudo, dict):
        for chave, descricao, dispositivo in ITENS_LAUDO:
            if not laudo.get(chave):
                estrutura.append({"item": chave, "estado": "a_conferir",
                                  "falta": descricao, "dispositivo": dispositivo})
    else:
        estrutura.append({"item": "(bloco `laudo` ausente)", "estado": "a_conferir",
                          "falta": "a conferencia estrutural nao foi pedida: sem o bloco "
                                   "`laudo`, os oito itens do CPC art. 473 e da NBC TP 01 "
                                   "(R2) item 58 nao foram verificados",
                          "dispositivo": "CPC, art. 473; NBC TP 01 (R2), item 58"})

    return {
        "schema_version": SCHEMA_VERSION,
        "estado": "auditado",
        "parcelas_conferidas": len(parcelas),
        "soma_das_parcelas": round(soma, 4),
        "total_declarado": total,
        "tolerancia_por_parcela": tolerancia,
        "apontamentos": aps,
        "estrutura_do_laudo": estrutura,
        "avisos": [AVISO_NAO_RECALCULA, AVISO_A_CONFERIR],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arquivo", required=True, help="JSON com o calculo da outra parte")
    ap.add_argument("--tolerancia", type=float, default=TOLERANCIA_PADRAO)
    args = ap.parse_args(argv)
    try:
        dado = json.load(io.open(args.arquivo, encoding="utf-8"))
    except (OSError, ValueError) as erro:
        print(json.dumps({"schema_version": SCHEMA_VERSION, "estado": "recusado",
                          "motivos": ["arquivo ilegivel: %s" % erro]}, ensure_ascii=False))
        return 2
    r = auditar(dado, autorizado=os.environ.get(VARIAVEL_AMBIENTE) == "1",
                tolerancia=args.tolerancia)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if r["estado"] != "auditado":
        return 2
    return 1 if (r["apontamentos"] or r["estrutura_do_laudo"]) else 0


if __name__ == "__main__":
    sys.exit(main())
