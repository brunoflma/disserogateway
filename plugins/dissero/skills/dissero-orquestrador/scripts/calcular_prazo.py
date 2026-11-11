#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'calcular_prazo.py — Cálculo determinístico de prazos processuais (Dissero).'















































import argparse, calendar, json, os, sys
from datetime import date, timedelta



try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)
from pascoa import pascoa







COBERTURA = (
    "— COBERTURA DO CALENDÁRIO —\n"
    "  Cobre: feriados nacionais (1/1, 21/4, 1/5, 7/9, 12/10, 2/11, 15/11, 20/11 e\n"
    "         25/12); suspensão de 20/12 a 20/01 na contagem em dias úteis (CPC 220;\n"
    "         CLT 775-A).\n"
    "  NÃO cobre: feriado ESTADUAL, inclusive o 9/7 de SP; CARNAVAL (segunda e terça);\n"
    "         SEXTA-FEIRA SANTA; CORPUS CHRISTI; FERIADO MUNICIPAL, inclusive\n"
    "         o 25/1 da Capital (Lei mun. 14.485/2007, art. 10: vale 'no Município da\n"
    "         Capital'; em processo da Capital, informe com --feriado AAAA-01-25); ponto\n"
    "         facultativo do tribunal; portaria de SUSPENSÃO DE EXPEDIENTE;\n"
    "         INDISPONIBILIDADE do sistema (PJe, e-SAJ, eproc, Projudi); feriado municipal\n"
    "         de outra comarca.\n"
    "  Sem --feriado, cada um desses dias conta como ÚTIL no VENCIMENTO: se o tribunal\n"
    "         não teve expediente nele, o vencimento real nunca é ANTES do calculado, e\n"
    "         protocolar na data calculada nunca é chegar tarde.\n"
    "  A DATA-ALVO (D-N úteis) e os dias úteis restantes da triagem do DJEN usam o\n"
    "         CONJUNTO CONSERVADOR: o 9/7, a segunda e a terça de Carnaval, a Sexta-feira\n"
    "         Santa e o Corpus Christi contam sempre como NÃO úteis nessas duas contas,\n"
    "         informados por --feriado ou não. Contados como úteis, atrasariam a data-alvo\n"
    "         e diminuiriam a urgência onde o tribunal não teve expediente; onde teve, a\n"
    "         data-alvo só sai um pouco mais cedo.\n"
    "  Cada dia que o motor não cobre entra com --feriado AAAA-MM-DD, e vem desta fonte:\n"
    "         feriado, ponto facultativo e suspensão do calendário ANUAL: do ATO do tribunal\n"
    "         que o índice anual da AASP aponta (consultar_calendario_aasp.py --tribunal\n"
    "         <sigla> --ano AAAA devolve o ato e o link).\n"
    "         Leia o ato e informe cada dia com --feriado AAAA-MM-DD.\n"
    "         Ato posterior ao anual que acrescente ou mude data, inclusive portaria de\n"
    "         suspensão de expediente: do site do próprio tribunal.\n"
    "         Indisponibilidade do sistema: da certidão do tribunal, e só quando cai no dia\n"
    "         do começo ou do vencimento (CPC 224, § 1º).\n"
    "         Tribunal \"não divulgado\" no índice, ou ano sem página na AASP: não há fonte\n"
    "         para o calendário anual; declare a lacuna e escale ao advogado antes de\n"
    "         protocolar.\n"
    "  A contagem acima NÃO distingue esfera: aplica o mesmo conjunto a processo\n"
    "         federal, estadual e trabalhista. Os feriados forenses da Justiça Federal\n"
    "         (Lei 5.010/66, art. 62 — Semana Santa, da quarta-feira ao Domingo de Páscoa;\n"
    "         segunda e terça de Carnaval; 11/8, 1º/11, 2/11, 8/12 e o recesso 20/12–6/1)\n"
    "         estão na BASE DE CAMADAS, e não nesta contagem:\n"
    "         rode com --calendario --escopo esfera=federal e a conferência aponta\n"
    "         divergência dia a dia. A base é CONSULTIVA — relata, não recalcula.\n"
    "  Antes de protocolar, confira o ato e as portarias do TRIBUNAL competente."
)
























MSG_SEM_UF = ("O motor não tem tabela de feriados estaduais e não aceita UF. O feriado estadual "
              "vem do ato do tribunal: rode consultar_calendario_aasp.py --tribunal <sigla> "
              "--ano AAAA, leia o ato que ele aponta e informe cada data com --feriado AAAA-MM-DD.")





UTEIS_PARA_URGENTE = 3






NOTA_AVISO_INDENIZADO = (
    "se esta é a prescrição trabalhista (CF, art. 7º, XXIX) e o contrato terminou com aviso "
    "prévio indenizado, o TST firmou no Tema 169 dos recursos repetitivos (RRAg "
    "0010195-61.2022.5.03.0035, julgado em 27/6/2025) que a prescrição bienal começa a fluir do "
    "término do aviso prévio, ainda que indenizado (CLT, art. 487, § 1º; OJs 82 e 83 da SDI-1). "
    "Contar do último dia trabalhado, sem a projeção, é o conservador: vence antes. Se o termo "
    "inicial informado já é o fim do aviso projetado, confira a data da projeção antes de "
    "contar com ela.")


def feriados(ano):
    'Dias não úteis do padrão: só os feriados nacionais por lei federal.'



    return {date(ano,1,1),date(ano,4,21),date(ano,5,1),date(ano,9,7),date(ano,10,12),
            date(ano,11,2),date(ano,11,15),date(ano,11,20),date(ano,12,25)}








def dias_conservadores(ano):
    'O 9/7, a segunda e a terça de Carnaval, a Sexta-feira Santa e o Corpus Christi do ano,'

    p = pascoa(ano)
    return {date(ano, 7, 9), p - timedelta(48), p - timedelta(47), p - timedelta(2),
            p + timedelta(60)}

def feriados_do_perfil(perfil):
    'As datas de `perfil.foro.feriados_locais`, como `date`. PURA.'








    if not isinstance(perfil, dict):
        return set()
    foro = perfil.get("foro")
    brutos = foro.get("feriados_locais") if isinstance(foro, dict) else None
    if not brutos:
        return set()
    fora = set()
    for bruto in brutos:
        try:
            fora.add(date.fromisoformat(str(bruto).strip()))
        except ValueError:
            raise ValueError(
                f"data invalida em foro.feriados_locais do perfil: '{bruto}' "
                f"(use AAAA-MM-DD). Corrija o perfil: ignorado, o feriado que voce declarou "
                f"contaria como dia util e o vencimento sairia de outro calendario."
            )
    return fora


def _perfil_do_ambiente():
    'O perfil resolvido, ou None. Nao e erro nao haver perfil: o CLI serve tambem a quem'

    try:
        import perfil_advogado as _pa
    except ImportError:
        return None
    try:
        caminho = _pa.resolver_caminho()
        return _pa.carregar(caminho) if caminho else None
    except Exception:
        return None


class Calendario:
    def __init__(self, extras=(), *, uf=None):

        if uf:
            raise ValueError(MSG_SEM_UF)
        self.extras=set(extras); self.conservador_ativo=False; self._cache={}
    def conservador(self):
        'Este calendário com os dias de `dias_conservadores` também como não úteis. Só a'


        derivado = Calendario(self.extras)
        derivado.conservador_ativo = True
        return derivado
    def fer(self, ano):
        if ano not in self._cache:
            dias = feriados(ano) | {e for e in self.extras if e.year == ano}
            if self.conservador_ativo:
                dias |= dias_conservadores(ano)
            self._cache[ano] = dias
        return self._cache[ano]
    def util(self, d):
        return d.weekday()<5 and d not in self.fer(d.year)
    def prox_util(self, d):
        while not self.util(d): d+=timedelta(1)
        return d
    def util_antes(self, d, n):
        while n>0:
            d-=timedelta(1)
            if self.util(d): n-=1
        return d

def em_recesso(d): return (d.month==12 and d.day>=20) or (d.month==1 and d.day<=20)


def somar_meses(dia, meses):
    'Vencimento do prazo de `meses` meses contado de `dia`, o dia do começo (CC, art. 132,'






    total = dia.month - 1 + meses
    ano, mes = dia.year + total // 12, total % 12 + 1
    ultimo = calendar.monthrange(ano, mes)[1]
    if dia.day <= ultimo:
        return date(ano, mes, dia.day), True
    return date(ano, mes, ultimo) + timedelta(1), False


def contar_corridos_com_suspensao(ini, dias):
    'Vencimento de `dias` dias CORRIDOS a partir de `ini` (contado), sem contar os dias de 20/12'

    d, rest = ini, dias
    while True:
        if not em_recesso(d):
            rest -= 1
            if rest == 0:
                return d
        d += timedelta(1)


def contar_uteis(ini, dias, cal, suspender_recesso):
    'Vencimento de `dias` dias ÚTEIS a partir do termo inicial `ini` (contado se for útil).'



    d = cal.prox_util(ini); rest = dias; pulou_recesso = False
    while True:
        if suspender_recesso and em_recesso(d):
            pulou_recesso = True
            d = cal.prox_util(d + timedelta(1)); continue
        if cal.util(d):
            rest -= 1
            if rest == 0:
                break
        d = cal.prox_util(d + timedelta(1))
    return d, pulou_recesso


def calcular_vencimento(disponibilizacao, dias, contagem, cal, suspender_recesso=None):
    'Rota da DISPONIBILIZAÇÃO no DJEN, reutilizável por outros scripts (a triagem do'






    if dias <= 0:
        raise ValueError("dias deve ser >= 1")
    disp = disponibilizacao if isinstance(disponibilizacao, date) else date.fromisoformat(str(disponibilizacao))
    pub = cal.prox_util(disp + timedelta(1))
    ini = cal.prox_util(pub + timedelta(1))
    if contagem == "uteis":
        susp = True if suspender_recesso is None else bool(suspender_recesso)
        venc, _ = contar_uteis(ini, dias, cal, susp)
    elif contagem == "corridos":
        venc = ini + timedelta(dias - 1)
        if not cal.util(venc):
            venc = cal.prox_util(venc)
    else:
        raise ValueError("contagem deve ser uteis ou corridos")
    return {"disponibilizacao": disp, "publicacao": pub, "termo_inicial": ini, "vencimento": venc,
            "dias": dias, "contagem": contagem}


def dias_uteis_entre(hoje, alvo, cal):
    """Dias úteis estritamente DEPOIS de `hoje` até `alvo` inclusive (negativo se já passou)."""
    if alvo >= hoje:
        n, d = 0, hoje
        while d < alvo:
            d += timedelta(1)
            if cal.util(d):
                n += 1
        return n
    n, d = 0, alvo
    while d < hoje:
        d += timedelta(1)
        if cal.util(d):
            n += 1
    return -n


def data_alvo(vencimento, margem, cal):
    'Data-alvo de protocolo: `margem` dias úteis antes do vencimento, contados no calendário'

    return cal.conservador().util_antes(vencimento, margem)


def dias_uteis_restantes(hoje, vencimento, cal):
    'Dias úteis depois de `hoje` até o vencimento, inclusive, no calendário conservador'




    n = dias_uteis_entre(hoje, vencimento, cal.conservador())
    return min(n, -1) if vencimento < hoje else n


def _datas_por_extenso(datas):
    """'a', 'a e b', 'a, b e c', em DD/MM/AAAA."""
    textos = [d.strftime("%d/%m/%Y") for d in datas]
    return textos[0] if len(textos) == 1 else ", ".join(textos[:-1]) + " e " + textos[-1]














def conferir_base(caminho, escopo, ini, venc, cal):
    'Confere o intervalo contra a base de camadas e devolve linhas de relato.'


    try:
        import calendario_camadas as cc
    except ImportError:
        return ["  base NAO consultada: `calendario_camadas.py` nao esta ao lado deste script "
                "(ele vive na skill dissero-orquestrador). O calculo acima nao depende dela."]
    try:
        base = cc.carregar(caminho)
    except Exception as erro:
        return ["  base NAO consultada: %s" % erro]
    problemas = cc.validar(base)
    if problemas:
        return ["  base INVALIDA, e por isso nao foi usada nem para avisar:"] + \
               ["    - %s" % p for p in list(problemas)[:5]]

    linhas = ["  base: %s" % (caminho or cc.CAMINHO_BASE_PADRAO),
              "  estado da base: %s | perguntas juridicas ainda em aberto: %s"
              % (base.get("estado"),
                 [p.get("id") for p in
                  ((base.get("pendencia_juridica") or {}).get("perguntas") or [])
                  if p.get("resposta") in (None, "")] or "nenhuma")]
    achou = False
    d = ini
    while d <= venc:
        try:
            res = cc.consultar(base, d, escopo or None)
        except Exception as erro:
            linhas.append("  %s: base nao respondeu (%s)" % (d.strftime("%d/%m/%Y"), erro))
            d += timedelta(1); continue
        nao_util_na_base = bool((res.get("efeitos") or {}).get("dia_nao_util"))
        rotulos = ", ".join(r.get("rotulo", "?") for r in
                            (res.get("efeitos") or {}).get("dia_nao_util", []))[:70]
        if nao_util_na_base and cal.util(d):
            achou = True
            linhas.append("  ! %s — a base diz DIA NAO UTIL (%s) e a contagem o tratou como util."
                          % (d.strftime("%d/%m/%Y"), rotulos))
            linhas.append("      o vencimento real não seria antes do calculado — erro conservador.")
        elif (d.weekday() < 5 and not cal.util(d) and not nao_util_na_base
              and d not in feriados(d.year)):
            achou = True
            linhas.append("  ! %s — a contagem o tratou como NAO UTIL e a base nao o registra."
                          % d.strftime("%d/%m/%Y"))
            linhas.append("      ATENCAO: o vencimento real seria ANTES do calculado — e assim "
                          "que se perde prazo. Confira o dia antes de protocolar.")
        d += timedelta(1)
    if not achou:
        linhas.append("  sem divergencia entre a contagem e a base, no intervalo conferido.")
    return linhas

def main():
    ap=argparse.ArgumentParser(add_help=True)
    g=ap.add_mutually_exclusive_group(required=True)
    for k in ("disponibilizacao","publicacao","intimacao","inicio"): g.add_argument(f"--{k}")
    u=ap.add_mutually_exclusive_group(required=True)
    u.add_argument("--dias",type=int,help="prazo em dias, contado pela --contagem")
    u.add_argument("--meses",type=int,
                   help="prazo em meses, de data a data (CC, art. 132, § 3º): vence no dia de "
                        "igual número ao do dia do começo; sem ele, no dia seguinte")
    u.add_argument("--anos",type=int,help="prazo em anos, de data a data, como --meses")
    ap.add_argument("--contagem",choices=("uteis","corridos"),help="obrigatória com --dias")
    ap.add_argument("--dobro",action="store_true"); ap.add_argument("--sem-suspensao",action="store_true")
    ap.add_argument("--suspende-recesso",action="store_true",
                    help="no processo penal, suspende a contagem corrida de 20/12 a 20/01 (CPP, "
                         "art. 798-A), depois de o advogado confirmar que não há exceção (réu "
                         "preso, Lei Maria da Penha, medida urgente)")
    ap.add_argument("--decadencial",action="store_true")
    ap.add_argument("--prescricional",action="store_true",
                    help="prazo prescricional (material), em --meses ou --anos, sem margem D-2")
    ap.add_argument("--feriado",action="append",default=[])
    ap.add_argument("--margem",type=int,default=2)
    ap.add_argument("--registrar",metavar="ARQUIVO",
                    help="grava o resultado em JSON (gerado_por calcular_prazo.py): é o artefato que a "
                         "fase `prazo` do estado_peca.py exige")
    ap.add_argument("--hoje",metavar="AAAA-MM-DD",
                    help="data de referência dos dias úteis restantes (padrão: a data do sistema)")

    ap.add_argument("--uf",help=argparse.SUPPRESS)
    ap.add_argument("--calendario",nargs="?",const="",
                    help="MODO AVISO: confere o resultado contra a base de camadas e RELATA "
                         "divergencia; NAO muda o calculo. Sem valor, usa a base padrao do "
                         "plugin, que traz o art. 62 da Lei 5.010/66 para a esfera federal só "
                         "para conferência: essa camada é consultiva e não muda a conta, e o dia "
                         "sem expediente entra por --feriado, lido no ato do tribunal que o "
                         "índice da AASP aponta. Com valor, usa o arquivo indicado.")
    ap.add_argument("--escopo",action="append",default=[],metavar="NIVEL=VALOR",
                    help="escopo da consulta a base, ex.: tribunal=TRT-15 (repetivel)")
    ap.add_argument("--processo",metavar="CNJ",
                    help="numero CNJ do processo: preenche `esfera` e `tribunal` do escopo a "
                         "partir do proprio numero (Res. CNJ 65/2008). NAO substitui --escopo "
                         "informado a mao, que sempre vence. Nao altera a contagem.")
    a=ap.parse_args()
    if a.uf is not None: sys.exit(f"ERRO: {MSG_SEM_UF}")
    if a.prescricional and a.decadencial:
        sys.exit("ERRO: --prescricional e --decadencial são regimes diferentes; use um só.")
    if a.prescricional and a.dias is not None:
        sys.exit("ERRO: --prescricional conta de data a data, em --meses ou --anos, e não em --dias.")
    if a.dias is not None:
        if a.dias<=0: sys.exit(f"ERRO: --dias deve ser >= 1 (recebido: {a.dias}).")
        if a.contagem is None: sys.exit("ERRO: --contagem uteis|corridos é obrigatória com --dias.")
        em_meses=None
    else:

        opcao,valor=("--meses",a.meses) if a.meses is not None else ("--anos",a.anos)
        if valor<=0: sys.exit(f"ERRO: {opcao} deve ser >= 1 (recebido: {valor}).")
        if a.contagem=="uteis":
            sys.exit(f"ERRO: prazo em meses ou anos conta de data a data (CC, art. 132, § 3º), "
                     f"e não em dias úteis. Tire --contagem uteis.")
        if a.dobro:
            sys.exit("ERRO: --dobro vale para prazo em dias. Confira na lei se o prazo em meses "
                     "ou anos é dobrado e informe-o já dobrado.")
        if a.suspende_recesso:
            sys.exit("ERRO: --suspende-recesso vale para prazo em dias corridos. Prazo em meses "
                     "ou anos corre de data a data.")
        em_meses=a.meses if a.meses is not None else 12*a.anos
    def _data(s,rotulo):
        try: return date.fromisoformat(s)
        except ValueError: sys.exit(f"ERRO: data invalida em {rotulo}: '{s}' (use AAAA-MM-DD).")
    hoje=_data(a.hoje,"--hoje") if a.hoje else date.today()



    try:
        do_perfil = feriados_do_perfil(_perfil_do_ambiente())
    except ValueError as erro:
        sys.exit(f"ERRO: {erro}")
    try:
        cal=Calendario(set(_data(f,"--feriado") for f in a.feriado)|do_perfil)
    except ValueError as erro:
        sys.exit(f"ERRO: {erro}")
    dias=(a.dias*2 if a.dobro else a.dias) if em_meses is None else None
    cadeia=[]


    if a.disponibilizacao:
        disp=_data(a.disponibilizacao,"--disponibilizacao")
        pub=cal.prox_util(disp+timedelta(1)); cadeia.append(f"Disponibilização DJEN/DJe: {disp:%d/%m/%Y}")
        cadeia.append(f"Considerado PUBLICADO no 1º dia útil seguinte: {pub:%d/%m/%Y} (Lei 11.419, art. 4º, §3º)")
        ini=cal.prox_util(pub+timedelta(1)); cadeia.append(f"Termo inicial (1º dia útil após a publicação): {ini:%d/%m/%Y} (CPC art. 224, §§2º-3º)")
        comeco=pub
    elif a.publicacao:
        pub=_data(a.publicacao,"--publicacao"); cadeia.append(f"Publicação: {pub:%d/%m/%Y}")
        ini=cal.prox_util(pub+timedelta(1)); cadeia.append(f"Termo inicial (1º dia útil seguinte): {ini:%d/%m/%Y}")
        comeco=pub
    elif a.intimacao:
        itm=_data(a.intimacao,"--intimacao"); cadeia.append(f"Intimação/ciência: {itm:%d/%m/%Y} (exclui-se o dia do começo)")
        if a.decadencial:
            ini=itm+timedelta(1); cadeia.append(f"Termo inicial: {ini:%d/%m/%Y} (decadência corre mesmo em dia não útil)")
        else:
            ini=cal.prox_util(itm+timedelta(1)); cadeia.append(f"Termo inicial: {ini:%d/%m/%Y} (CPC 224 §1º / Súmula 310-STF)")
        comeco=itm
    else:
        ini=_data(a.inicio,"--inicio"); cadeia.append(f"Termo inicial informado: {ini:%d/%m/%Y}")
        comeco=ini-timedelta(1)
    if a.dobro: cadeia.append(f"Prazo em DOBRO: {a.dias} → {dias} dias")

    susp_uteis = (a.contagem=="uteis") and not a.sem_suspensao and not a.decadencial
    susp_corr  = (a.contagem=="corridos") and a.suspende_recesso and not a.decadencial
    avisos=[]



    if not a.feriado and not do_perfil:
        avisos.append("feriados ESTADUAIS e MUNICIPAIS NÃO foram verificados: o perfil não tem "
                      "foro.feriados_locais e nenhum --feriado foi informado. Se a comarca ou o "
                      "estado teve feriado no período, o vencimento real nunca é antes do calculado "
                      "e protocolar na data acima nunca é chegar tarde, mas a conta não é a do "
                      "tribunal. Leia o ato do tribunal (consultar_calendario_aasp.py) e "
                      "recalcule com --feriado.")
    if em_meses is not None:
        unidade=(f"{a.meses} {'MÊS' if a.meses==1 else 'MESES'}" if a.meses is not None
                 else f"{a.anos} {'ANO' if a.anos==1 else 'ANOS'}")
        venc,igual=somar_meses(comeco,em_meses)
        cadeia.append(f"Contagem: {unidade} de data a data a partir de {comeco:%d/%m/%Y} (CC art. 132, § 3º)")
        if igual:
            cadeia.append(f"Vence no dia de igual número: {venc:%d/%m/%Y}")
        else:
            cadeia.append(f"Sem o dia {comeco.day} no mês do vencimento: vence no dia seguinte, {venc:%d/%m/%Y}")
        if a.decadencial:
            avisos.append("prazo DECADENCIAL: sem prorrogação garantida do vencimento — protocolar ANTES")
        elif not cal.util(venc):
            v2=cal.prox_util(venc); cadeia.append(f"Vencimento em dia sem expediente ({venc:%d/%m/%Y}) → prorrogado: {v2:%d/%m/%Y} (CC art. 132, § 1º; na rescisória, CPC art. 975, § 1º)"); venc=v2
    elif a.contagem=="uteis":
        venc, pulou_recesso = contar_uteis(ini, dias, cal, susp_uteis)
        cadeia.append(f"Contagem: {dias} dias ÚTEIS"+(" (suspensão 20/12–20/01 aplicada — CPC 220/CLT 775-A)" if pulou_recesso else ""))
    else:
        if susp_corr:
            venc=contar_corridos_com_suspensao(ini, dias)
            cadeia.append(f"Contagem: {dias} dias CORRIDOS com suspensão 20/12–20/01 (CPP art. 798-A; sem exceção, confirmado pelo advogado)")
        else:
            venc=ini+timedelta(dias-1)
            rotulo = "decadencial — Lei/CC" if a.decadencial else "CPP art. 798"
            cadeia.append(f"Contagem: {dias} dias CORRIDOS ({rotulo})")




            if not a.decadencial and any(em_recesso(ini+timedelta(i)) for i in range(dias)):
                ref=contar_corridos_com_suspensao(ini, dias)
                if not cal.util(ref): ref=cal.prox_util(ref)
                avisos.append("a contagem corrida atravessa 20/12–20/01. Se o prazo é do processo "
                              "penal, o CPP, art. 798-A (Lei 14.365/2022), suspende o prazo de "
                              "20/12 a 20/01, salvo nos processos de réu preso vinculados à prisão, "
                              "nos procedimentos da Lei Maria da Penha (Lei 11.340/2006) e nas "
                              "medidas urgentes por despacho fundamentado do juízo. O vencimento "
                              "acima, sem a suspensão, é o que vale até o advogado confirmar que não "
                              "há exceção. Confirmado, recalcule com --suspende-recesso. Vencimento "
                              f"com a suspensão, só como referência: {ref:%d/%m/%Y}.")
        if a.decadencial:
            avisos.append("prazo DECADENCIAL: sem suspensão e sem prorrogação garantida do vencimento — protocolar ANTES")
        elif not cal.util(venc):
            v2=cal.prox_util(venc); cadeia.append(f"Vencimento em dia sem expediente ({venc:%d/%m/%Y}) → prorrogado: {v2:%d/%m/%Y} (CPP 798 §3º / CPC 224 §1º)"); venc=v2
    cadeia.append(f"VENCIMENTO LEGAL: {venc:%d/%m/%Y} ({['seg','ter','qua','qui','sex','sáb','dom'][venc.weekday()]})")
    alvo_reg=None
    if a.prescricional:
        avisos.append("prazo PRESCRICIONAL (material): sem margem de protocolo D-2. Vence no dia "
                      "legal acima; distribua antes dele.")



        avisos.append(NOTA_AVISO_INDENIZADO)
    elif a.decadencial:
        avisos.append("prescrição não é decadência: prazo prescricional vai com --prescricional "
                      "(em --meses ou --anos), e não com --decadencial. Este cálculo saiu como "
                      "DECADENCIAL.")
    if a.margem>0 and not a.decadencial and not a.prescricional:
        alvo=data_alvo(venc,a.margem,cal)
        if alvo < ini:

            cadeia.append(f"DATA-ALVO DE PROTOCOLO: prazo curto ({f'{dias}d' if em_meses is None else unidade.lower()}) — margem D-{a.margem} cairia antes do início ({ini:%d/%m/%Y}); proteja o vencimento {venc:%d/%m/%Y} e protocole o quanto antes")
        else:
            cadeia.append(f"DATA-ALVO DE PROTOCOLO (D-{a.margem} úteis): {alvo:%d/%m/%Y}")
            alvo_reg=alvo

            conservador=cal.conservador()
            tirados=[d for d in (alvo+timedelta(i) for i in range(1,(venc-alvo).days))
                     if cal.util(d) and not conservador.util(d)]
            if tirados:
                cadeia.append(f"  Na margem, {_datas_por_extenso(tirados)} não "
                              f"{'conta' if len(tirados)==1 else 'contam'} como "
                              f"{'útil' if len(tirados)==1 else 'úteis'} (conjunto conservador, "
                              f"ver a cobertura).")


    restam=dias_uteis_restantes(hoje, venc, cal)
    cadeia.append(f"Dias úteis restantes (calendário conservador): {restam} (de {hoje:%d/%m/%Y} ao vencimento)")
    if restam < 0:
        cadeia.append("VENCIDO: o vencimento é anterior à data de referência. Leve ao advogado antes de qualquer outra etapa.")
    elif restam <= UTEIS_PARA_URGENTE:
        cadeia.append(f"URGENTE: faltam {UTEIS_PARA_URGENTE} dias úteis ou menos. Priorize a peça sobre qualquer outra etapa.")
    for c in cadeia: print(c)
    for w in avisos: print(f"⚠ AVISO: {w}")
    if a.registrar:


        reg={"gerado_por":"calcular_prazo.py","formato":1,"termo_inicial":ini.isoformat(),
             "vencimento_legal":venc.isoformat(),"data_alvo_D2":alvo_reg.isoformat() if alvo_reg else None,
             "margem_uteis":0 if a.prescricional else a.margem,"decadencial":bool(a.decadencial),
             "prescricional":bool(a.prescricional),
             "natureza":"prescricional" if a.prescricional else ("decadencial" if a.decadencial else "processual"),
             "dias_uteis_restantes":restam,
             "urgente":0<=restam<=UTEIS_PARA_URGENTE,"vencido":restam<0,"referencia":hoje.isoformat(),
             "cadeia":cadeia,"avisos":avisos,"argumentos":sys.argv[1:]}
        with open(a.registrar,"w",encoding="utf-8") as fh:
            fh.write(json.dumps(reg,ensure_ascii=False,indent=2))
        print(f"Resultado registrado em {a.registrar} (artefato da fase prazo).")
    if a.calendario is not None:


        escopo={}



        if a.processo:
            try:
                import numero_cnj as ncnj
                comp = ncnj.componentes(a.processo)
            except ImportError:
                comp = None
                print("  aviso: `numero_cnj.py` nao esta ao lado deste script; "
                      "--processo ignorado.")
            if comp is None:
                print(f"  aviso: '{a.processo}' nao tem forma de numero CNJ; "
                      f"--processo ignorado.")
            else:
                if comp.get("esfera"):
                    escopo["esfera"]=comp["esfera"]
                origem=comp.get("tribunal_origem") or []
                if len(origem)==1:
                    escopo["tribunal"]=origem[0]
                elif len(origem)>1:
                    print(f"  aviso: o codigo do tribunal e AMBIGUO ({', '.join(origem)}); "
                          f"informe --escopo tribunal=... para desempatar.")
                if not comp.get("valido"):
                    print(f"  aviso: o digito verificador do numero NAO fecha "
                          f"(seria {comp.get('dv_correto')}) — escopo derivado assim mesmo, "
                          f"mas confira o numero.")
        for par in a.escopo:
            if "=" not in par: sys.exit(f"ERRO: --escopo espera NIVEL=VALOR (recebido: '{par}').")
            nivel,valor=par.split("=",1); escopo[nivel.strip()]=valor.strip()
        print("\n— CONFERÊNCIA CONTRA A BASE DE CALENDÁRIO (modo AVISO) —")
        print("  O cálculo acima NÃO foi alterado por esta conferência.")
        for linha in conferir_base(a.calendario or None,escopo,ini,venc,cal): print(linha)
    print(COBERTURA)
    print("Conferência final da intimação no DJEN e responsabilidade pelo protocolo: do advogado.")
if __name__=="__main__": main()
