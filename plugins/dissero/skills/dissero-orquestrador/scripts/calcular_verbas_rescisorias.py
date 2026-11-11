#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'calcular_verbas_rescisorias.py — cálculo determinístico de verbas rescisórias (Dissero).'


























import argparse, sys
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass



MOTIVOS = {
    "sem-justa-causa":    {"aviso": 1.0,  "ferias_prop": True,  "decimo_prop": True,
                           "multa": 0.40, "saque": "100%", "seguro": True},
    "rescisao-indireta":  {"aviso": 1.0,  "ferias_prop": True,  "decimo_prop": True,
                           "multa": 0.40, "saque": "100%", "seguro": True},

    "justa-causa":        {"aviso": 0.0,  "ferias_prop": False, "decimo_prop": False,
                           "multa": 0.0,  "saque": "não", "seguro": False},

    "pedido-demissao":    {"aviso": None, "ferias_prop": True,  "decimo_prop": True,
                           "multa": 0.0,  "saque": "não", "seguro": False},

    "acordo-484a":        {"aviso": 0.5,  "ferias_prop": True,  "decimo_prop": True,
                           "multa": 0.20, "saque": "80%", "seguro": False},
    "prazo-determinado":  {"aviso": 0.0,  "ferias_prop": True,  "decimo_prop": True,
                           "multa": 0.0,  "saque": "100%", "seguro": False},
    "aposentadoria":      {"aviso": 0.0,  "ferias_prop": True,  "decimo_prop": True,
                           "multa": 0.0,  "saque": "100%", "seguro": False},
    "falecimento":        {"aviso": 0.0,  "ferias_prop": True,  "decimo_prop": True,
                           "multa": 0.0,  "saque": "dependentes", "seguro": False},
}
FGTS_ALIQUOTA = 0.08


def _data(s, rotulo):
    'AAAA-MM-DD ou DD/MM/AAAA (B3 do teste do titular, 22/10/2026: o advogado copia a data do'


    texto = (s or "").strip()
    try:
        if "/" in texto:
            partes = texto.split("/")
            if len(partes) != 3 or len(partes[2]) != 4 or not all(p.isdigit() for p in partes):
                raise ValueError(texto)
            dia, mes, ano = (int(p) for p in partes)
            return date(ano, mes, dia)
        return date.fromisoformat(texto)
    except ValueError:
        sys.exit(f"ERRO: data inválida em {rotulo}: '{s}' (use DD/MM/AAAA ou AAAA-MM-DD).")


def anos_completos(adm, dem):
    return (dem.year - adm.year) - ((dem.month, dem.day) < (adm.month, adm.day))


def aviso_dias(adm, dem):
    """Lei 12.506/2011: 30 dias + 3 por ano COMPLETO de casa, teto de +60 (máximo 90)."""
    return 30 + min(anos_completos(adm, dem) * 3, 60)


def ultimo_aniversario(adm, dem):
    'Início do período aquisitivo em curso — a âncora das férias PROPORCIONAIS (nunca o'

    anos = anos_completos(adm, dem)
    if anos <= 0:
        return adm
    ano = adm.year + anos
    dia = adm.day
    while True:
        try:
            return date(ano, adm.month, dia)
        except ValueError:
            dia -= 1


def avos(inicio, fim):
    'Avos por mês com 15 dias ou mais trabalhados no mês (regra de avos da CLT), no'

    if fim < inicio:
        return 0, []
    detalhe, total = [], 0
    ano, mes = inicio.year, inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        prim = date(ano, mes, 1)
        prox = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
        ult = prox - timedelta(days=1)
        a = max(prim, inicio)
        b = min(ult, fim)
        dias = (b - a).days + 1 if a <= b else 0
        if dias >= 15:
            total += 1
            detalhe.append(f"{mes:02d}/{ano} ({dias}d)")
        else:
            detalhe.append(f"{mes:02d}/{ano} ({dias}d — não conta, <15)")
        if mes == 12:
            ano, mes = ano + 1, 1
        else:
            mes += 1
    return min(total, 12), detalhe


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    ap = argparse.ArgumentParser(description="Verbas rescisórias determinísticas (Dissero)")
    ap.add_argument("--admissao", required=True)
    ap.add_argument("--demissao", required=True)
    ap.add_argument("--motivo", required=True, choices=sorted(MOTIVOS))
    ap.add_argument("--salario", type=float, required=True, help="salário BASE mensal")
    ap.add_argument("--media-variaveis", dest="media", type=float, default=0.0,
                    help="média de HE/comissões dos últimos 12 meses (integra a base)")
    ap.add_argument("--aviso", choices=("indenizado", "trabalhado", "dispensado"),
                    default="indenizado",
                    help="indenizado projeta tempo (CLT, art. 487, § 1º); trabalhado já está no "
                         "saldo; dispensado não projeta nem indeniza")
    ap.add_argument("--saldo-fgts", dest="saldo_fgts", type=float, default=0.0)
    ap.add_argument("--ferias-vencidas", dest="ferias_vencidas", type=int, default=0,
                    help="períodos aquisitivos COMPLETOS não gozados")
    ap.add_argument("--dias-saldo", dest="dias_saldo", type=int,
                    help="dias trabalhados no mês da rescisão (padrão: dia da demissão)")
    a = ap.parse_args()

    adm, dem = _data(a.admissao, "--admissao"), _data(a.demissao, "--demissao")
    if dem < adm:
        sys.exit(f"ERRO: demissão ({dem}) anterior à admissão ({adm}).")
    if a.salario <= 0:
        sys.exit("ERRO: --salario deve ser maior que zero.")
    if a.ferias_vencidas < 0:
        sys.exit("ERRO: --ferias-vencidas não pode ser negativo.")
    regra = MOTIVOS[a.motivo]

    linhas, avisos = [], []
    base = a.salario + a.media
    anos = anos_completos(adm, dem)
    linhas.append(f"Admissão {adm:%d/%m/%Y} · Demissão {dem:%d/%m/%Y} · Motivo: {a.motivo}")
    linhas.append(f"Tempo de casa: {anos} ano(s) completo(s)")
    linhas.append(f"Base de cálculo: salário {brl(a.salario)}"
                  + (f" + médias variáveis {brl(a.media)} = {brl(base)}" if a.media else ""))


    dias_av = aviso_dias(adm, dem)
    fracao = regra["aviso"]
    projeta = False
    valor_aviso = 0.0
    if fracao is None:
        linhas.append(f"Aviso prévio: devido PELO EMPREGADO ({dias_av} dias seriam do "
                      f"empregador na dispensa) — nada a pagar; se não cumprido, o empregador "
                      f"pode descontar (CLT 487, §2º)")
        avisos.append("pedido de demissão: aviso não cumprido gera DESCONTO, que este script não "
                      "aplica — informe-o à parte se for o caso")
    elif fracao == 0.0:
        linhas.append("Aviso prévio: NÃO devido neste motivo")
    else:
        dias_pagos = dias_av * fracao
        if a.aviso == "trabalhado":
            linhas.append(f"Aviso prévio TRABALHADO ({dias_av} dias) — remunerado como salário "
                          f"no período, sem indenização própria; NÃO projeta avos")
        elif a.aviso == "dispensado":
            linhas.append("Aviso prévio DISPENSADO — sem indenização e sem projeção")
            avisos.append("aviso dispensado sem indenização é hipótese restrita; confira se não "
                          "se trata de aviso INDENIZADO (que projeta tempo — CLT, art. 487, § 1º)")
        else:
            valor_aviso = base * dias_pagos / 30
            projeta = True
            comp = (f"Lei 12.506/2011: 30 + {anos}×3, teto +60" if dias_av > 30
                    else "Lei 12.506/2011: 30 dias")
            meia = " × 50% (CLT 484-A)" if fracao == 0.5 else ""
            linhas.append(f"Aviso prévio INDENIZADO: {dias_pagos:g} dias ({comp}{meia}) = "
                          f"{brl(valor_aviso)}")

    fim_projetado = dem + timedelta(days=int(round(dias_av * (fracao or 0)))) if projeta else dem
    if projeta:
        linhas.append(f"Projeção do aviso (CLT, art. 487, § 1º): avos contados até "
                      f"{fim_projetado:%d/%m/%Y}")


    dias_saldo = a.dias_saldo if a.dias_saldo is not None else dem.day
    if dias_saldo < 0 or dias_saldo > 31:
        sys.exit("ERRO: --dias-saldo deve estar entre 0 e 31.")
    saldo = base * dias_saldo / 30
    linhas.append(f"Saldo de salário ({dias_saldo} dias ÷ 30): {brl(saldo)}")


    ferias_venc = 0.0
    if a.ferias_vencidas:
        ferias_venc = base * a.ferias_vencidas * (4 / 3)
        linhas.append(f"Férias VENCIDAS + 1/3 ({a.ferias_vencidas} período(s)): "
                      f"{brl(ferias_venc)}")


    ferias_prop = 0.0
    if regra["ferias_prop"]:
        ini_aq = ultimo_aniversario(adm, dem)
        n_fp, det_fp = avos(ini_aq, fim_projetado)
        ferias_prop = base * n_fp / 12 * (4 / 3)
        linhas.append(f"Férias PROPORCIONAIS + 1/3: {n_fp}/12 — período aquisitivo desde "
                      f"{ini_aq:%d/%m/%Y} = {brl(ferias_prop)}")
        linhas.append(f"    avos de férias: {', '.join(det_fp)}")
    else:
        linhas.append("Férias PROPORCIONAIS: NÃO devidas neste motivo (justa causa — "
                      "Súmula 171-TST; as VENCIDAS subsistem)")


    decimo = 0.0
    if regra["decimo_prop"]:
        ini_13 = max(adm, date(dem.year, 1, 1))
        n_13, det_13 = avos(ini_13, fim_projetado)
        decimo = base * n_13 / 12
        linhas.append(f"13º PROPORCIONAL: {n_13}/12 — ano civil desde {ini_13:%d/%m/%Y} = "
                      f"{brl(decimo)}")
        linhas.append(f"    avos de 13º: {', '.join(det_13)}")
    else:
        linhas.append("13º PROPORCIONAL: NÃO devido neste motivo (justa causa)")

    bruto = saldo + valor_aviso + ferias_venc + ferias_prop + decimo
    linhas.append(f"BRUTO (antes de INSS/IRRF): {brl(bruto)}")


    dep_aviso = valor_aviso * FGTS_ALIQUOTA
    dep_13 = decimo * FGTS_ALIQUOTA
    dep_saldo = saldo * FGTS_ALIQUOTA
    dep_rescis = dep_aviso + dep_13 + dep_saldo
    multa = (a.saldo_fgts + dep_rescis) * regra["multa"]
    linhas.append(f"FGTS — saldo informado na conta vinculada: {brl(a.saldo_fgts)}")
    linhas.append(f"FGTS — depósitos rescisórios 8% (saldo {brl(dep_saldo)} + aviso "
                  f"{brl(dep_aviso)} + 13º {brl(dep_13)}): {brl(dep_rescis)}")
    if regra["multa"]:
        linhas.append(f"Multa do FGTS {regra['multa']:.0%} sobre {brl(a.saldo_fgts + dep_rescis)}"
                      f": {brl(multa)}")
    else:
        linhas.append("Multa do FGTS: NÃO devida neste motivo (alíquota 0)")
    linhas.append(f"GRRF a recolher (depósitos rescisórios + multa): {brl(dep_rescis + multa)}")


    linhas.append(f"Saque do FGTS: {regra['saque']} · Seguro-desemprego: "
                  f"{'em tese, sujeito à carência e aos demais requisitos da Lei 7.998/1990' if regra['seguro'] else 'não'}")


    linhas.append("")
    linhas.append("MAPA DE INCIDÊNCIA — os VALORES saem da tabela vigente, conferida pelo "
                  "advogado (este script não embute tabela que envelhece):")
    linhas.append("  IRRF INCIDE em: saldo de salário, 13º (em DARF separada) e médias")
    linhas.append("  IRRF NÃO incide em: aviso prévio INDENIZADO e indenização por despedida, "
                  "inclusive a multa do FGTS (Lei 7.713/1988, art. 6º, V), e férias INDENIZADAS "
                  "— vencidas e proporcionais, com o 1/3 (Súmulas 386 e 125 do STJ)")
    linhas.append("  INSS INCIDE em: saldo de salário e 13º · NÃO incide em férias indenizadas")





    linhas.append("  INSS sobre aviso INDENIZADO: o STJ firmou, no Tema 478 dos recursos "
                  "repetitivos (REsp 1.230.957/RS), que não incide a contribuição a cargo da "
                  "EMPRESA, por não ser verba salarial. A cota do EMPREGADO não é o objeto do "
                  "tema: a conferir pelo advogado")

    if a.motivo == "acordo-484a":
        avisos.append("acordo do art. 484-A: multa de 20% (NÃO 40%), aviso pela metade, saque de "
                      "80% e SEM seguro-desemprego — o erro de aplicar 40% aqui é o mais comum")
    if a.motivo == "justa-causa":
        avisos.append("justa causa exige documentação prévia e proporcionalidade; sem isso a "
                      "reversão em juízo transforma o cálculo no de dispensa SEM justa causa")
    if not a.media:
        avisos.append("sem --media-variaveis: se houve hora extra, comissão, adicional ou "
                      "gratificação habitual nos 12 meses, a média INTEGRA a base de todas as "
                      "verbas e o cálculo está subestimado")
    if a.ferias_vencidas == 0 and anos >= 1:
        avisos.append(f"{anos} ano(s) de casa e --ferias-vencidas 0: confira se não há período "
                      "aquisitivo completo não gozado (e se há, se é em dobro — CLT 137)")
    if a.saldo_fgts == 0 and regra["multa"]:
        avisos.append("saldo do FGTS informado como zero: a multa incidiu só sobre os depósitos "
                      "rescisórios — junte o extrato da conta vinculada")
    avisos.append("prazo de pagamento: 10 dias corridos da rescisão (CLT 477, §6º); atraso gera "
                  "multa de um salário (CLT 477, §8º) — calcule o prazo pelo calcular_prazo.py")
    avisos.append("avos contados por mês com 15 dias ou mais; não se aplicam suspensões do "
                  "contrato (afastamento previdenciário, estabilidade) — se houve, o cálculo "
                  "precisa de ajuste manual")

    for l in linhas:
        print(l)
    for w in avisos:
        print(f"⚠ AVISO: {w}")
    print("Cálculo de apoio: valores de INSS/IRRF pela tabela vigente, extrato do FGTS e "
          "conferência final são do advogado. Não substitui o TRCT nem o eSocial.")


if __name__ == "__main__":
    main()
