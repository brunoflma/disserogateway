#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'calendario_camadas.py - Base de calendario forense em CAMADAS (Dissero). CONSULTIVO.'








































































import argparse
import json
import os
import sys
from datetime import date, timedelta



try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import pascoa as _pascoa

REFS = os.path.join(os.path.dirname(AQUI), "references")
CAMINHO_BASE_PADRAO = os.path.join(REFS, "calendario-forense.json")

EFEITOS = ("dia_nao_util", "suspensao_prazo", "prorrogacao_vencimento")





NIVEIS = ("brasil", "uf", "municipio", "esfera", "tribunal", "vara", "sistema")
TIPOS_ESPERADOS = (
    "feriado_nacional", "feriado_estadual", "feriado_municipal", "feriado_forense",
    "recesso_forense", "suspensao_expediente", "ponto_facultativo_com_suspensao",
    "indisponibilidade_sistema",
)
RECORRENCIAS = ("unica", "anual_fixa", "anual_movel")
ANCORAS = ("pascoa",)




MAX_ANOS_JANELA = 25

COBERTURA_DECLARADA = "declarada"
COBERTURA_PARCIAL = "parcial_declarada"


class BaseInvalida(Exception):
    """Base malformada -> exit 1."""


class Contrato(Exception):
    """Violacao de contrato/uso -> exit 2."""




def carregar(caminho=None):
    """Le a base JSON. Nao valida conteudo (use `validar`)."""
    alvo = caminho or CAMINHO_BASE_PADRAO
    if not os.path.isfile(alvo):
        raise Contrato("base nao encontrada: %s" % alvo)
    try:
        with open(alvo, "r", encoding="utf-8") as fh:
            base = json.load(fh)
    except ValueError as exc:
        raise BaseInvalida("JSON invalido em %s: %s" % (alvo, exc))
    if not isinstance(base, dict):
        raise BaseInvalida("a base deve ser um objeto JSON, veio %s" % type(base).__name__)
    return base


def _data(valor, rotulo, problemas=None):
    """Converte ISO em date. Com `problemas`, registra e devolve None."""
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        if problemas is None:
            raise Contrato("data invalida em %s: %r (use AAAA-MM-DD)" % (rotulo, valor))
        problemas.append("%s: data invalida %r (use AAAA-MM-DD)" % (rotulo, valor))
        return None


def _mes_dia(valor, rotulo, problemas):
    """Converte 'MM-DD' em (mes, dia). Registra problema e devolve None."""
    try:
        partes = str(valor).split("-")
        if len(partes) != 2:
            raise ValueError("formato")
        mes, dia = int(partes[0]), int(partes[1])
        date(2000, mes, dia)
        return (mes, dia)
    except (TypeError, ValueError):
        problemas.append("%s: mes-dia invalido %r (use MM-DD)" % (rotulo, valor))
        return None




def pascoa(ano):
    'Domingo de Pascoa pelo computo do calendario gregoriano, pela conta de `pascoa.py`.'





    if not isinstance(ano, int):
        raise Contrato("ano deve ser inteiro, veio %r" % (ano,))
    return _pascoa.pascoa(ano)


def _ancora(nome, ano):
    if nome == "pascoa":
        return pascoa(ano)
    raise Contrato("ancora desconhecida: %r" % (nome,))




def ocorrencias(registro, ano_ancora):
    """Spans (inicio, fim) do evento ancorados em `ano_ancora`. Lista, possivelmente vazia."""
    rec = registro.get("recorrencia")
    if rec == "unica":
        ini = _data(registro.get("data_inicio"), "data_inicio")
        fim_bruto = registro.get("data_fim")
        fim = _data(fim_bruto, "data_fim") if fim_bruto else ini

        if ini.year != ano_ancora:
            return []
        return [(ini, fim)]
    if rec == "anual_fixa":
        mdi = _mes_dia(registro.get("mes_dia_inicio"), "mes_dia_inicio", [])
        if mdi is None:
            return []
        try:
            ini = date(ano_ancora, mdi[0], mdi[1])
        except ValueError:
            return []
        bruto_fim = registro.get("mes_dia_fim")
        if not bruto_fim:
            return [(ini, ini)]
        mdf = _mes_dia(bruto_fim, "mes_dia_fim", [])
        if mdf is None:
            return []
        ano_fim = ano_ancora if mdf >= mdi else ano_ancora + 1
        try:
            fim = date(ano_fim, mdf[0], mdf[1])
        except ValueError:
            return []
        return [(ini, fim)]
    if rec == "anual_movel":
        base_dia = _ancora(registro.get("ancora"), ano_ancora)
        d_ini = registro.get("deslocamento_inicio")
        d_fim = registro.get("deslocamento_fim", d_ini)
        if not isinstance(d_ini, int) or not isinstance(d_fim, int):
            return []
        ini = base_dia + timedelta(days=d_ini)
        fim = base_dia + timedelta(days=d_fim)
        return [(ini, fim)]
    raise Contrato("recorrencia desconhecida: %r" % (rec,))


def cobre_dia(registro, dia):
    """O evento do registro alcanca `dia`? (independente de vigencia e escopo)."""
    for ano in (dia.year - 1, dia.year, dia.year + 1):
        for ini, fim in ocorrencias(registro, ano):
            if ini <= dia <= fim:
                return True
    return False


def vigente_em(registro, dia):
    'A VIGENCIA DO REGISTRO (da norma) alcanca `dia`?'





    ini = _data(registro.get("vigencia_inicio"), "vigencia_inicio")
    if dia < ini:
        return False
    bruto = registro.get("vigencia_fim")
    if bruto:
        return dia <= _data(bruto, "vigencia_fim")
    return True


def escopo_casa(registro, escopo):
    'O escopo do registro corresponde ao escopo consultado?'




    esc = registro.get("escopo") or {}
    nivel = esc.get("nivel")
    if nivel == "brasil":
        return True
    alvo = (escopo or {}).get(nivel)
    if not alvo:
        return False
    return str(alvo).strip().casefold() == str(esc.get("valor", "")).strip().casefold()


def aplica(registro, dia, escopo):
    return vigente_em(registro, dia) and escopo_casa(registro, escopo) and cobre_dia(registro, dia)




def _validar_procedencia(proc, rotulo, sufixos, problemas):
    if not isinstance(proc, dict):
        problemas.append("%s: `procedencia` ausente ou nao e objeto - em discussao de "
                         "tempestividade vale a FONTE, nao a base" % rotulo)
        return
    for campo in ("ato", "numero", "data", "url_fonte_oficial", "data_coleta"):
        if not str(proc.get(campo) or "").strip():
            problemas.append("%s: procedencia.%s vazia" % (rotulo, campo))
    if proc.get("data"):
        _data(proc.get("data"), "%s: procedencia.data" % rotulo, problemas)
    if proc.get("data_coleta"):
        _data(proc.get("data_coleta"), "%s: procedencia.data_coleta" % rotulo, problemas)
    url = str(proc.get("url_fonte_oficial") or "")
    if url:
        resto = url.split("://", 1)[-1]
        host = resto.split("/", 1)[0].split("?", 1)[0].split("@")[-1].split(":", 1)[0].casefold()
        if not any(host.endswith(s) for s in sufixos):
            problemas.append("%s: procedencia.url_fonte_oficial com host %r fora dos sufixos "
                             "oficiais %s (sufixo IDENTIFICA candidato, nunca confirma)"
                             % (rotulo, host, list(sufixos)))


def _validar_recorrencia(reg, rotulo, problemas):
    rec = reg.get("recorrencia")
    if rec not in RECORRENCIAS:
        problemas.append("%s: recorrencia %r desconhecida (use %s)" % (rotulo, rec, list(RECORRENCIAS)))
        return
    if rec == "unica":
        ini = _data(reg.get("data_inicio"), "%s: data_inicio" % rotulo, problemas)
        if reg.get("data_fim"):
            fim = _data(reg.get("data_fim"), "%s: data_fim" % rotulo, problemas)
            if ini and fim and fim < ini:
                problemas.append("%s: data_fim anterior a data_inicio" % rotulo)
    elif rec == "anual_fixa":
        _mes_dia(reg.get("mes_dia_inicio"), "%s: mes_dia_inicio" % rotulo, problemas)
        if reg.get("mes_dia_fim"):
            _mes_dia(reg.get("mes_dia_fim"), "%s: mes_dia_fim" % rotulo, problemas)
    else:
        if reg.get("ancora") not in ANCORAS:
            problemas.append("%s: ancora %r desconhecida (use %s)"
                             % (rotulo, reg.get("ancora"), list(ANCORAS)))
        if not isinstance(reg.get("deslocamento_inicio"), int):
            problemas.append("%s: deslocamento_inicio deve ser inteiro de dias" % rotulo)
        if "deslocamento_fim" in reg and not isinstance(reg.get("deslocamento_fim"), int):
            problemas.append("%s: deslocamento_fim deve ser inteiro de dias" % rotulo)


def validar(base):
    'Devolve a lista de problemas ESTRUTURAIS. Lista vazia = base limpa.'




    problemas = []
    if not isinstance(base, dict):
        return ["a base deve ser um objeto JSON"]

    for chave in ("versao", "estado", "modo", "pendencia_juridica", "efeitos", "tipos",
                  "niveis_escopo", "precedencia_camadas", "sufixos_oficiais",
                  "cobertura_declarada", "registros"):
        if chave not in base:
            problemas.append("chave de topo ausente: %s" % chave)

    efeitos = base.get("efeitos") or {}
    for ef in EFEITOS:
        if ef not in efeitos:
            problemas.append("efeitos: falta %s - os tres efeitos nao podem colapsar em um" % ef)

    tipos = base.get("tipos") or {}
    for tp in TIPOS_ESPERADOS:
        if tp not in tipos:
            problemas.append("tipos: falta %s (sao sete tipos)" % tp)

    pend = base.get("pendencia_juridica") or {}
    perguntas = pend.get("perguntas") or []
    if len(perguntas) != 4:
        problemas.append("pendencia_juridica.perguntas: esperadas 4 perguntas, ha %d" % len(perguntas))
    for idx, p in enumerate(perguntas):
        rot = "pendencia_juridica.perguntas[%d]" % idx
        if not isinstance(p, dict):
            problemas.append("%s: nao e objeto" % rot)
            continue
        if not str(p.get("pergunta") or "").strip():
            problemas.append("%s: `pergunta` vazia" % rot)
        if "resposta" not in p:
            problemas.append("%s: falta o campo `resposta` (nasce null)" % rot)

    sufixos = tuple(base.get("sufixos_oficiais") or ())
    if not sufixos:
        problemas.append("sufixos_oficiais vazio - sem eles nao ha como triar a procedencia")

    registros = base.get("registros")
    cobertura = base.get("cobertura_declarada")
    if not isinstance(registros, list):
        problemas.append("registros deve ser lista")
        registros = []
    if not isinstance(cobertura, list):
        problemas.append("cobertura_declarada deve ser lista")
        cobertura = []

    estado = base.get("estado")
    if estado == "vazio" and (registros or cobertura):
        problemas.append("estado 'vazio' com registros/cobertura preenchidos - "
                         "declare estado 'preenchido'")
    if estado != "vazio" and not registros:
        problemas.append("estado %r sem registros - base vazia deve declarar estado 'vazio'" % estado)

    vistos = set()
    for idx, reg in enumerate(registros):
        rot = "registros[%d]" % idx
        if not isinstance(reg, dict):
            problemas.append("%s: nao e objeto" % rot)
            continue
        rid = str(reg.get("id") or "").strip()
        if not rid:
            problemas.append("%s: `id` vazio" % rot)
        elif rid in vistos:
            problemas.append("%s: id duplicado %r" % (rot, rid))
        else:
            vistos.add(rid)
        rot = "registros[%d](%s)" % (idx, rid or "sem-id")

        tipo = reg.get("tipo")
        spec = tipos.get(tipo) if isinstance(tipos.get(tipo), dict) else None
        if spec is None:
            problemas.append("%s: tipo %r desconhecido" % (rot, tipo))
        esc = reg.get("escopo")
        if not isinstance(esc, dict):
            problemas.append("%s: `escopo` ausente ou nao e objeto" % rot)
        else:
            nivel = esc.get("nivel")
            if nivel not in NIVEIS:
                problemas.append("%s: escopo.nivel %r fora de %s" % (rot, nivel, list(NIVEIS)))
            elif spec is not None:
                admitidos = spec.get("escopo_nivel_admitido") or []
                if nivel not in admitidos:
                    problemas.append("%s: tipo %s nao admite escopo.nivel %r (admitidos: %s)"
                                     % (rot, tipo, nivel, admitidos))
            if not str(esc.get("valor") or "").strip():
                problemas.append("%s: escopo.valor vazio" % rot)

        efeito = reg.get("efeito")
        if efeito not in EFEITOS:
            problemas.append("%s: efeito %r fora de %s" % (rot, efeito, list(EFEITOS)))
        elif spec is not None:
            tipico = spec.get("efeito_tipico")
            if efeito != tipico and not str(reg.get("justificativa_efeito") or "").strip():
                problemas.append("%s: efeito %r diverge do tipico %r sem `justificativa_efeito` - "
                                 "o codigo nao escolhe o efeito, quem diverge declara por que"
                                 % (rot, efeito, tipico))

        if not str(reg.get("vigencia_inicio") or "").strip():
            problemas.append("%s: `vigencia_inicio` ausente - sem periodo de validade a base "
                             "recalcula errado o passado" % rot)
        else:
            vi = _data(reg.get("vigencia_inicio"), "%s: vigencia_inicio" % rot, problemas)
            if reg.get("vigencia_fim"):
                vf = _data(reg.get("vigencia_fim"), "%s: vigencia_fim" % rot, problemas)
                if vi and vf and vf < vi:
                    problemas.append("%s: vigencia_fim anterior a vigencia_inicio" % rot)
        if "vigencia_fim" not in reg:
            problemas.append("%s: falta o campo `vigencia_fim` (use null se ainda vigente)" % rot)

        if not str(reg.get("base_normativa") or "").strip():
            problemas.append("%s: `base_normativa` vazia" % rot)

        _validar_recorrencia(reg, rot, problemas)
        _validar_procedencia(reg.get("procedencia"), rot, sufixos, problemas)

    for idx, cob in enumerate(cobertura):
        rot = "cobertura_declarada[%d]" % idx
        if not isinstance(cob, dict):
            problemas.append("%s: nao e objeto" % rot)
            continue
        if cob.get("nivel") not in NIVEIS:
            problemas.append("%s: nivel %r fora de %s" % (rot, cob.get("nivel"), list(NIVEIS)))
        if not str(cob.get("valor") or "").strip():
            problemas.append("%s: valor vazio" % rot)
        anos = cob.get("anos")
        if not isinstance(anos, list) or not anos or not all(isinstance(a, int) for a in anos):
            problemas.append("%s: `anos` deve ser lista nao vazia de inteiros" % rot)
        if not isinstance(cob.get("completo"), bool):
            problemas.append("%s: `completo` deve ser booleano" % rot)
        _validar_procedencia(cob.get("procedencia"), rot, sufixos, problemas)

    return problemas




def cobertura(base, dia, escopo):
    'Cobertura do escopo consultado no ano de `dia`. FAIL-CLOSED.'





    declaradas = base.get("cobertura_declarada") or []
    exigidos = [n for n in NIVEIS if n != "brasil"]
    cobertos, faltam = [], []
    for nivel in exigidos:
        valor = (escopo or {}).get(nivel)
        if not valor:
            faltam.append({"nivel": nivel, "valor": None, "motivo": "nao informado na consulta"})
            continue
        achou = False
        for cob in declaradas:
            if not isinstance(cob, dict):
                continue
            if cob.get("nivel") != nivel:
                continue
            if str(cob.get("valor", "")).strip().casefold() != str(valor).strip().casefold():
                continue
            if dia.year not in (cob.get("anos") or []):
                faltam.append({"nivel": nivel, "valor": valor,
                               "motivo": "sem calendario carregado para %d" % dia.year})
                achou = True
                break
            if not cob.get("completo"):
                faltam.append({"nivel": nivel, "valor": valor,
                               "motivo": "cobertura declarada INCOMPLETA para %d" % dia.year})
                achou = True
                break
            cobertos.append({"nivel": nivel, "valor": valor, "ano": dia.year})
            achou = True
            break
        if not achou:
            faltam.append({"nivel": nivel, "valor": valor, "motivo": "escopo sem calendario carregado"})

    situacao = COBERTURA_PARCIAL if faltam else COBERTURA_DECLARADA
    escal = []
    if faltam:
        escal.append("COBERTURA PARCIAL DECLARADA: a base não cobre %s."
                     % ", ".join("%s=%s (%s)" % (f["nivel"], f["valor"], f["motivo"]) for f in faltam))
        escal.append("O calendário do tribunal vem do ato oficial do ano que o índice anual da AASP "
                     "aponta: rode consultar_calendario_aasp.py --tribunal <sigla> --ano AAAA e leia "
                     "o ato. Informe cada dia sem expediente com --feriado AAAA-MM-DD no "
                     "calcular_prazo.py. Portaria posterior ao ato anual vem do site do próprio "
                     "tribunal. Tribunal \"não divulgado\" no índice, ou ano sem página na AASP, não "
                     "tem fonte: declare a lacuna e escale ao advogado antes de protocolar.")
        escal.append("Este módulo é CONSULTIVO e não devolve número: `resposta_numerica` é sempre nula.")
    return {"situacao": situacao, "cobertos": cobertos, "faltam": faltam, "escalonamento": escal}




def vocabulario_esfera(base):
    'Valores de esfera que a base declara em `valores_esfera` (as chaves sem `_`, que sao'

    valores = base.get("valores_esfera") if isinstance(base, dict) else None
    if not isinstance(valores, dict):
        return ()
    return tuple(k for k in valores if not str(k).startswith("_"))


def eventos_do_dia(base, dia, escopo):
    """Registros da base que se aplicam a `dia` no `escopo`. Lista (pode ser vazia)."""
    saida = []
    for reg in (base.get("registros") or []):
        if not isinstance(reg, dict):
            continue
        try:
            if aplica(reg, dia, escopo):
                saida.append(reg)
        except Contrato:
            continue
    return saida


def _resumo(reg, camada):
    esc = reg.get("escopo") or {}
    return {
        "id": reg.get("id"),
        "tipo": reg.get("tipo"),
        "rotulo": reg.get("rotulo"),
        "efeito": reg.get("efeito"),
        "camada": camada,
        "escopo": {"nivel": esc.get("nivel"), "valor": esc.get("valor")},
        "vigencia": {"inicio": reg.get("vigencia_inicio"), "fim": reg.get("vigencia_fim")},
        "base_normativa": reg.get("base_normativa"),
        "procedencia": reg.get("procedencia"),
        "justificativa_efeito": reg.get("justificativa_efeito"),
    }


def classificar(base, dia, escopo):
    """Os TRES efeitos em baldes SEPARADOS. Nunca colapsa um no outro."""
    baldes = dict((ef, []) for ef in EFEITOS)
    for reg in eventos_do_dia(base, dia, escopo):
        ef = reg.get("efeito")
        if ef in baldes:
            baldes[ef].append(_resumo(reg, "base"))
    return baldes


def conflitos(base, dia, escopo):
    'Mesmo dia, MESMO (nivel, valor), efeitos DIFERENTES -> conflito declarado.'




    por_escopo = {}
    for reg in eventos_do_dia(base, dia, escopo):
        esc = reg.get("escopo") or {}
        chave = (esc.get("nivel"), str(esc.get("valor", "")).strip().casefold())
        por_escopo.setdefault(chave, []).append(reg)
    saida = []
    for (nivel, valor), regs in sorted(por_escopo.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        efs = sorted(set(r.get("efeito") for r in regs))
        if len(efs) > 1:
            saida.append({
                "escopo": {"nivel": nivel, "valor": regs[0].get("escopo", {}).get("valor")},
                "efeitos_em_disputa": efs,
                "registros": [_resumo(r, "base") for r in regs],
                "quem_decide": "o advogado",
                "remissao": "pendencia_juridica.perguntas[id=4]",
            })
    return saida


def consultar(base, dia, escopo=None, feriados_do_caso=()):
    'Resposta CONSULTIVA para um dia. `resposta_numerica` e sempre None.'





    if not isinstance(dia, date):
        raise Contrato("dia deve ser datetime.date, veio %r" % (dia,))
    escopo = dict(escopo or {})
    for k in escopo:
        if k not in NIVEIS:
            raise Contrato("nivel de escopo desconhecido: %r (use %s)" % (k, list(NIVEIS)))
    caso = set(feriados_do_caso or ())
    for d in caso:
        if not isinstance(d, date):
            raise Contrato("feriados_do_caso deve conter datetime.date, veio %r" % (d,))

    cob = cobertura(base, dia, escopo)
    baldes = classificar(base, dia, escopo)
    confl = conflitos(base, dia, escopo)
    venceu = None
    sobrestados = []

    if dia in caso:
        venceu = "caso"
        for ef in EFEITOS:
            sobrestados.extend(baldes[ef])
            baldes[ef] = []
        baldes["dia_nao_util"] = [{
            "id": "caso:%s" % dia.isoformat(),
            "tipo": "camada_do_caso",
            "rotulo": "feriado/suspensao informado pelo advogado",
            "efeito": "dia_nao_util",
            "camada": "caso",
            "escopo": {"nivel": "caso", "valor": "processo em maos"},
            "base_normativa": "palavra do advogado (--feriado AAAA-MM-DD do calcular_prazo.py)",
            "procedencia": {"ato": "informacao do advogado no caso concreto"},
        }]
        confl = []
    elif any(baldes[ef] for ef in EFEITOS):
        venceu = "base"

    return {
        "modo": base.get("modo", "consultivo"),
        "dia": dia.isoformat(),
        "escopo": escopo,
        "cobertura": cob["situacao"],
        "cobertos": cob["cobertos"],
        "faltam": cob["faltam"],
        "escalonamento": cob["escalonamento"],
        "resposta_numerica": None,
        "por_que_sem_numero": ("Módulo CONSULTIVO: o calcular_prazo.py só confere esta base, em "
                               "modo aviso, e o relato vem POSTERIOR ao resultado. O dia sem "
                               "expediente do tribunal vem do ato oficial que o índice anual da "
                               "AASP aponta e entra no cálculo por --feriado."),
        "camada_vencedora": venceu,
        "efeitos": baldes,
        "sobrestados_pela_camada_do_caso": sobrestados,
        "conflitos": confl,
        "precedencia_declarada": base.get("precedencia_camadas") or [],
        "estado_da_base": base.get("estado"),
        "pendencia_aberta": [p.get("id") for p in
                             ((base.get("pendencia_juridica") or {}).get("perguntas") or [])
                             if p.get("resposta") in (None, "")],
    }


def janela(base, inicio, fim, escopo=None, feriados_do_caso=(), max_anos=MAX_ANOS_JANELA):
    """Consulta dia a dia num intervalo fechado. `max_anos` e guarda de trabalho."""
    if not isinstance(inicio, date) or not isinstance(fim, date):
        raise Contrato("inicio e fim devem ser datetime.date")
    if fim < inicio:
        raise Contrato("fim anterior a inicio")
    if (fim - inicio).days > int(max_anos) * 366:
        raise Contrato("janela maior que max_anos=%s (guarda arbitraria e configuravel)" % max_anos)
    saida, d = [], inicio
    while d <= fim:
        saida.append(consultar(base, d, escopo, feriados_do_caso))
        d += timedelta(days=1)
    return saida




def formatar_pendencia(base):
    pend = base.get("pendencia_juridica") or {}
    linhas = ["=" * 72,
              "PENDENCIA JURIDICA - o que falta o ADVOGADO decidir",
              "=" * 72,
              "Fonte: %s" % pend.get("fonte", "-"),
              "Quem decide: %s" % pend.get("quem_decide", "-"),
              "Enquanto pendente: %s" % pend.get("enquanto_pendente", "-"),
              ""]
    for p in (pend.get("perguntas") or []):
        marca = "ABERTA" if p.get("resposta") in (None, "") else "RESPONDIDA"
        linhas.append("[%s] %s. %s" % (marca, p.get("id"), p.get("tema")))
        linhas.append("      %s" % p.get("pergunta"))
        for item in (p.get("o_que_preenche") or []):
            linhas.append("      -> preenche: %s" % item)
        linhas.append("")
    linhas.append("Ligacao ao calculo: %s" % base.get("ligacao_ao_calculo", "-"))
    linhas.append("=" * 72)
    return "\n".join(linhas)


def formatar(res):
    linhas = ["=" * 72,
              "CALENDARIO EM CAMADAS - CONSULTA CONSULTIVA (nao altera calculo de prazo)",
              "=" * 72,
              "Dia: %s   Escopo: %s" % (res["dia"], res["escopo"] or "(nenhum nivel informado)"),
              "Cobertura: %s" % res["cobertura"].upper(),
              "Estado da base: %s" % res["estado_da_base"],
              "Camada vencedora: %s" % (res["camada_vencedora"] or "(nenhuma)"),
              ""]
    linhas.append("-- OS TRES EFEITOS, SEPARADOS --")
    for ef in EFEITOS:
        itens = res["efeitos"][ef]
        linhas.append("  %s: %d" % (ef, len(itens)))
        for it in itens:
            linhas.append("      - [%s] %s (%s=%s) %s" % (it.get("camada"), it.get("rotulo"),
                                                          it.get("escopo", {}).get("nivel"),
                                                          it.get("escopo", {}).get("valor"),
                                                          it.get("base_normativa") or ""))
    if res["sobrestados_pela_camada_do_caso"]:
        linhas.append("")
        linhas.append("-- SOBRESTADOS pela camada do caso (a palavra do advogado vence) --")
        for it in res["sobrestados_pela_camada_do_caso"]:
            linhas.append("      - %s (%s)" % (it.get("rotulo"), it.get("efeito")))
    if res["conflitos"]:
        linhas.append("")
        linhas.append("-- CONFLITO DE EFEITO: o codigo NAO escolhe --")
        for c in res["conflitos"]:
            linhas.append("      escopo %s=%s em disputa: %s (ver %s)"
                          % (c["escopo"]["nivel"], c["escopo"]["valor"],
                             ", ".join(c["efeitos_em_disputa"]), c["remissao"]))
    if res["escalonamento"]:
        linhas.append("")
        linhas.append("-- ESCALONAMENTO --")
        for e in res["escalonamento"]:
            linhas.append("      %s" % e)
    linhas.append("")
    linhas.append("resposta_numerica: %s" % res["resposta_numerica"])
    linhas.append("motivo: %s" % res["por_que_sem_numero"])
    if res["pendencia_aberta"]:
        linhas.append("Perguntas de pendencia ABERTAS: %s" % res["pendencia_aberta"])
    linhas.append("=" * 72)
    return "\n".join(linhas)




def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description="Base de calendario forense em "
                                                            "camadas (consultivo; nao altera calculo de prazo).")
    ap.add_argument("--base", default=None, help="caminho da base JSON")
    ap.add_argument("--validar", action="store_true", help="valida a estrutura da base")
    ap.add_argument("--pendencia", action="store_true", help="imprime o bloco de pendencia juridica")
    ap.add_argument("--consultar", metavar="AAAA-MM-DD", default=None)
    ap.add_argument("--uf", default=None)
    ap.add_argument("--municipio", default=None)
    ap.add_argument("--esfera", default=None,
                    help="ramo do processo, no vocabulário de `valores_esfera` da base "
                         "(ex.: federal)")
    ap.add_argument("--tribunal", default=None)
    ap.add_argument("--vara", default=None)
    ap.add_argument("--sistema", default=None)
    ap.add_argument("--feriado", action="append", default=[],
                    help="camada do caso: a palavra do advogado, vence sempre (repetivel)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if not (a.validar or a.pendencia or a.consultar):
        print("ERRO: use --validar, --pendencia ou --consultar AAAA-MM-DD.", file=sys.stderr)
        return 2
    try:
        base = carregar(a.base)
    except Contrato as exc:
        print("ERRO DE CONTRATO: %s" % exc, file=sys.stderr)
        return 2
    except BaseInvalida as exc:
        print("BASE INVALIDA: %s" % exc, file=sys.stderr)
        return 1

    if a.validar:
        problemas = validar(base)
        if a.json:
            print(json.dumps({"ok": not problemas, "problemas": problemas},
                             ensure_ascii=False, indent=2))
        elif problemas:
            print("BASE INVALIDA - %d problema(s):" % len(problemas))
            for p in problemas:
                print("  - %s" % p)
        else:
            print("BASE VALIDA - estado=%s, registros=%d, cobertura_declarada=%d"
                  % (base.get("estado"), len(base.get("registros") or []),
                     len(base.get("cobertura_declarada") or [])))
        if problemas:
            return 1

    if a.pendencia:
        if a.json:
            print(json.dumps(base.get("pendencia_juridica") or {}, ensure_ascii=False, indent=2))
        else:
            print(formatar_pendencia(base))

    if a.consultar:
        try:
            dia = _data(a.consultar, "--consultar")
            caso = [_data(f, "--feriado") for f in a.feriado]
            escopo = {}
            for nivel in NIVEIS:
                valor = getattr(a, nivel, None)
                if valor:
                    escopo[nivel] = valor
            vocab = vocabulario_esfera(base)
            if (a.esfera and vocab
                    and a.esfera.strip().casefold() not in [v.casefold() for v in vocab]):
                raise Contrato("--esfera %r fora do vocabulário da base (use %s)"
                               % (a.esfera, list(vocab)))
            res = consultar(base, dia, escopo, caso)
        except Contrato as exc:
            print("ERRO DE CONTRATO: %s" % exc, file=sys.stderr)
            return 2
        print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else formatar(res))
        if res["conflitos"]:
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
