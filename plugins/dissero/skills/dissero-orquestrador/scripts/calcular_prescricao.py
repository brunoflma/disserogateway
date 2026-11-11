#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'calcular_prescricao.py — Cálculo determinístico da PRESCRIÇÃO PENAL (Dissero).'












































import argparse, sys
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass



MARCOS_INTERRUPTIVOS = {
    "recebimento-denuncia": "CP 117, I — recebimento da denúncia ou queixa",
    "recebimento-queixa": "CP 117, I — recebimento da denúncia ou queixa",
    "pronuncia": "CP 117, II — pronúncia",
    "confirmatoria-pronuncia": "CP 117, III — decisão confirmatória da pronúncia",
    "sentenca": "CP 117, IV — publicação da sentença condenatória recorrível",
    "acordao": "CP 117, IV — publicação do acórdão condenatório recorrível",
    "inicio-cumprimento": "CP 117, V — início ou continuação do cumprimento (só PPE)",
    "reincidencia": "CP 117, VI — reincidência (só PPE)",
}

MARCOS_INICIAIS = {
    "fato": "CP 111, I — data da consumação",
    "ultimo-ato": "CP 111, II — último ato de execução (tentativa)",
    "cessacao-permanencia": "CP 111, III — cessação da permanência",
    "conhecimento": "CP 111, IV — data em que o fato se tornou conhecido",
    "vitima-18": "CP 111, V — data em que a vítima completou 18 anos",
    "transito": "CP 112, I — trânsito em julgado (termo inicial da PPE)",
}
SO_PPE = ("inicio-cumprimento", "reincidencia")


def _data(s, rotulo):
    try:
        return date.fromisoformat(s)
    except ValueError:
        sys.exit(f"ERRO: data invalida em {rotulo}: '{s}' (use AAAA-MM-DD).")


def soma_meses(d, meses):
    """d + N meses, ancorando no último dia quando o mês de destino é mais curto."""
    total = (d.year * 12 + (d.month - 1)) + meses
    ano, mes = divmod(total, 12)
    mes += 1
    dia = d.day
    while True:
        try:
            return date(ano, mes, dia)
        except ValueError:
            dia -= 1


def fim_do_prazo(inicio, meses):
    'Consumação pela contagem PENAL (CP 10): inclui-se o dia do começo, logo o prazo de'


    return soma_meses(inicio, meses) - timedelta(days=1)


def faixa_109(anos, meses, dias, dois_anos_possivel=False):
    'Prazo do art. 109 em ANOS, pela pena de referência. Comparação por tupla porque a lei'

    t = (anos, meses, dias)
    if t < (1, 0, 0):
        if dois_anos_possivel:
            return 2, ("CP 109, VI (redação anterior à Lei 12.234/2010) — pena inferior a 1 ano; "
                       "2 anos por ser a lei mais benéfica ao fato anterior a 05/05/2010")
        return 3, "CP 109, VI — pena inferior a 1 ano"
    if t <= (2, 0, 0):
        return 4, "CP 109, V — pena igual a 1 ano ou, sendo superior, não excedente a 2"
    if t <= (4, 0, 0):
        return 8, "CP 109, IV — pena superior a 2, não excedente a 4"
    if t <= (8, 0, 0):
        return 12, "CP 109, III — pena superior a 4, não excedente a 8"
    if t <= (12, 0, 0):
        return 16, "CP 109, II — pena superior a 8, não excedente a 12"
    return 20, "CP 109, I — pena superior a 12"


def dias_suspensos(ini, fim, suspensoes):
    'Dias congelados dentro do intervalo [ini, fim] — o prazo retoma de onde parou, então'

    total = 0
    for s_ini, s_fim in suspensoes:
        a = max(ini, s_ini)
        b = min(fim, s_fim)
        if a <= b:
            total += (b - a).days + 1
    return total


def main(argv=None):
    ap = argparse.ArgumentParser(description="Prescrição penal determinística (Dissero)")
    ap.add_argument("--especie", required=True,
                    choices=("ppp-abstrato", "ppp-retroativa", "ppp-intercorrente", "ppe"))
    ap.add_argument("--pena-anos", type=int, default=0)
    ap.add_argument("--pena-meses", type=int, default=0)
    ap.add_argument("--pena-dias", type=int, default=0)
    ap.add_argument("--multa-isolada", action="store_true")
    ap.add_argument("--marco", action="append", default=[], metavar="NOME:AAAA-MM-DD")
    ap.add_argument("--suspensao", action="append", default=[], metavar="INI:FIM")
    ap.add_argument("--reincidente", action="store_true")
    ap.add_argument("--nascimento")
    ap.add_argument("--data-sentenca", dest="data_sentenca")
    ap.add_argument("--hoje")
    a = ap.parse_args(argv)

    cadeia, avisos = [], []
    ppe = a.especie == "ppe"


    if not a.marco:
        sys.exit("ERRO: informe ao menos um --marco NOME:AAAA-MM-DD (ex.: fato:2015-03-10).")
    marcos = []
    for item in a.marco:
        if ":" not in item:
            sys.exit(f"ERRO: --marco malformado: '{item}' (use NOME:AAAA-MM-DD).")
        nome, _, ds = item.partition(":")
        nome = nome.strip().lower()
        if nome not in MARCOS_INTERRUPTIVOS and nome not in MARCOS_INICIAIS:
            validos = ", ".join(sorted(set(MARCOS_INTERRUPTIVOS) | set(MARCOS_INICIAIS)))
            sys.exit(f"ERRO: marco desconhecido '{nome}'. Válidos: {validos}")
        if nome in SO_PPE and not ppe:
            sys.exit(f"ERRO: marco '{nome}' só existe na PPE (CP 117, V-VI) — espécie "
                     f"informada: {a.especie}.")
        marcos.append((_data(ds, f"--marco {nome}"), nome))
    marcos.sort()

    suspensoes = []
    for item in a.suspensao:
        if ":" not in item:
            sys.exit(f"ERRO: --suspensao malformada: '{item}' (use INI:FIM).")
        i, _, f = item.partition(":")
        d_i, d_f = _data(i, "--suspensao (início)"), _data(f, "--suspensao (fim)")
        if d_f < d_i:
            sys.exit(f"ERRO: suspensão com fim antes do início: {d_i} → {d_f}.")
        suspensoes.append((d_i, d_f))


    if a.multa_isolada:
        prazo_meses = 24
        cadeia.append("Pena: MULTA como única cominada/aplicada → prazo de 2 anos (CP 114, I)")
    else:
        if (a.pena_anos, a.pena_meses, a.pena_dias) == (0, 0, 0):
            sys.exit("ERRO: informe a pena de referência (--pena-anos/--pena-meses/--pena-dias) "
                     "ou --multa-isolada. O script NÃO calcula pena e NÃO trabalha com pena "
                     "hipotética (Súmula 438-STJ veda a prescrição virtual).")
        for nome, v in (("--pena-anos", a.pena_anos), ("--pena-meses", a.pena_meses),
                        ("--pena-dias", a.pena_dias)):
            if v < 0:
                sys.exit(f"ERRO: {nome} não pode ser negativo.")
        data_fato = next((d for d, n in marcos if n in MARCOS_INICIAIS), None)
        dois = bool(data_fato and data_fato < date(2010, 5, 5))
        anos_109, fundamento = faixa_109(a.pena_anos, a.pena_meses, a.pena_dias, dois)
        prazo_meses = anos_109 * 12
        base = "máxima cominada" if a.especie == "ppp-abstrato" else "concreta aplicada"
        cadeia.append(f"Pena de referência ({base}): {a.pena_anos}a {a.pena_meses}m "
                      f"{a.pena_dias}d")
        cadeia.append(f"Prazo do art. 109: {anos_109} anos — {fundamento}")
        if a.especie == "ppp-abstrato":
            avisos.append("em ABSTRATO a pena de referência é a MÁXIMA com majorantes (no maior "
                          "aumento) e minorantes (na maior redução); agravantes e atenuantes "
                          "genéricas NÃO entram — confira se a pena informada já está ajustada")


    if a.reincidente:
        if not ppe:
            sys.exit("ERRO: --reincidente só incide na PPE (CP 110, caput). A Súmula 220 do STJ "
                     "veda o acréscimo de 1/3 na prescrição da pretensão PUNITIVA.")
        antes = prazo_meses
        prazo_meses = prazo_meses * 4 // 3
        cadeia.append(f"Reincidência (PPE): +1/3 → {antes // 12}a {antes % 12}m passa a "
                      f"{prazo_meses // 12}a {prazo_meses % 12}m (CP 110, caput)")

    reduz, motivos = False, []
    if a.nascimento:
        nasc = _data(a.nascimento, "--nascimento")
        d_fato = next((d for d, n in marcos if n in MARCOS_INICIAIS), None)
        if d_fato is None:
            avisos.append("--nascimento informado sem marco inicial (fato/consumação): não foi "
                          "possível apurar a idade na data do fato para o art. 115")
        else:
            idade = (d_fato.year - nasc.year) - ((d_fato.month, d_fato.day) < (nasc.month, nasc.day))
            if idade < 21:
                reduz = True
                motivos.append(f"menor de 21 na data do fato (idade {idade})")
            else:
                cadeia.append(f"Art. 115 (menor de 21): NÃO incide — idade na data do fato: "
                              f"{idade}")
    if a.data_sentenca:
        d_sent = _data(a.data_sentenca, "--data-sentenca")
        if not a.nascimento:
            avisos.append("--data-sentenca informada sem --nascimento: o art. 115 (maior de 70 "
                          "na sentença) não pôde ser apurado")
        else:
            nasc = _data(a.nascimento, "--nascimento")
            idade_s = (d_sent.year - nasc.year) - ((d_sent.month, d_sent.day) < (nasc.month, nasc.day))
            if idade_s > 70:
                reduz = True
                motivos.append(f"maior de 70 na data da sentença (idade {idade_s})")
    if reduz:
        antes = prazo_meses
        prazo_meses = prazo_meses // 2
        cadeia.append(f"Art. 115 (metade): {antes // 12}a {antes % 12}m → {prazo_meses // 12}a "
                      f"{prazo_meses % 12}m — {'; '.join(motivos)}")
        if a.reincidente:
            avisos.append("incidem ao mesmo tempo o acréscimo de 1/3 (CP 110) e a redução pela "
                          "metade (CP 115); aqui somou-se PRIMEIRO e reduziu-se DEPOIS — a ordem "
                          "é controvertida e altera o resultado, confira a tese adotada")
        avisos.append("a extensão do marco dos 70 anos à data do ACÓRDÃO é construção "
                      "jurisprudencial — confirme pela dissero-pesquisa-juridica antes de sustentar")

    cadeia.append(f"PRAZO PRESCRICIONAL APLICADO: {prazo_meses // 12} ano(s)"
                  + (f" e {prazo_meses % 12} mês(es)" if prazo_meses % 12 else ""))


    cadeia.append("")
    cadeia.append("LINHA DO TEMPO E INTERVALOS (basta UM intervalo alcançar o prazo — CP 107, IV):")
    hoje = _data(a.hoje, "--hoje") if a.hoje else None
    prescrito = []
    for i, (d, nome) in enumerate(marcos):
        rotulo = MARCOS_INTERRUPTIVOS.get(nome) or MARCOS_INICIAIS.get(nome)
        cadeia.append(f"  · {d:%d/%m/%Y} — {nome} ({rotulo})")
        prox = marcos[i + 1] if i + 1 < len(marcos) else None
        fim = fim_do_prazo(d, prazo_meses)
        susp = dias_suspensos(d, fim, suspensoes)
        if susp:
            fim = fim + timedelta(days=susp)
        alvo, tipo = (prox[0], f"até {prox[1]}") if prox else (hoje, "até hoje (intervalo ABERTO)")
        nota = f" (+{susp}d de suspensão)" if susp else ""
        if alvo is None:


            cadeia.append(f"    ↳ intervalo ABERTO (sem --hoje, não avaliado): consumação em "
                          f"{fim:%d/%m/%Y}{nota}")
        elif alvo > fim:
            prescrito.append((d, nome, alvo, tipo, fim, susp))
            cadeia.append(f"    ↳ {tipo}: PRESCRITO — prazo esgotado em {fim:%d/%m/%Y}, marco "
                          f"seguinte em {alvo:%d/%m/%Y}{nota}")
        else:
            cadeia.append(f"    ↳ {tipo}: dentro do prazo (limite era {fim:%d/%m/%Y}){nota}")


    cadeia.append("")
    if prescrito:
        d, nome, alvo, _t, fim, _s = prescrito[0]
        cadeia.append(f"RESULTADO: PRESCRIÇÃO CONSUMADA em {fim:%d/%m/%Y} — intervalo entre "
                      f"{nome} ({d:%d/%m/%Y}) e o marco seguinte ({alvo:%d/%m/%Y}) superou o "
                      f"prazo aplicado")
        cadeia.append(f"Fundamento: art. 107, IV, do CP ({a.especie}); matéria de ordem pública, "
                      f"cognoscível de ofício em qualquer fase e grau (CPP art. 61)")
        if len(prescrito) > 1:
            cadeia.append(f"({len(prescrito)} intervalos alcançaram o prazo — o primeiro basta)")
    elif hoje is None and len(marcos) >= 1:
        cadeia.append("RESULTADO: nenhum intervalo FECHADO alcançou o prazo. O intervalo aberto "
                      "não foi avaliado — informe --hoje para medi-lo.")
    else:
        cadeia.append("RESULTADO: prescrição NÃO consumada nos intervalos avaliados.")

    if ppe:
        avisos.append("termo inicial da PPE: o CP 112, I fala em trânsito para a ACUSAÇÃO, e o "
                      "STF assentou em repercussão geral o trânsito para AMBAS as partes, com "
                      "modulação — o enquadramento na modulação decide o caso; confirme pela "
                      "dissero-pesquisa-juridica")
    if a.especie == "ppp-retroativa":
        d_fato = next((d for d, n in marcos if n in MARCOS_INICIAIS), None)
        if d_fato and d_fato >= date(2010, 5, 5):
            avisos.append("retroativa em fato POSTERIOR a 05/05/2010: vedado contar período "
                          "anterior ao recebimento da denúncia (CP 110, §1º, Lei 12.234/2010) — "
                          "confira se o intervalo apontado não é o do fato→denúncia")
        elif d_fato:
            avisos.append("fato ANTERIOR a 05/05/2010: teste também o intervalo fato→denúncia, "
                          "porque a Lei 12.234/2010 não retroage em prejuízo")
    if len(marcos) == 1:
        avisos.append("apenas UM marco informado: sem os marcos do art. 117 dos autos (com "
                      "certidão), o cálculo não sustenta pedido — peça de prescrição sem tabela "
                      "de datas documentada é indeferida")
    avisos.append("contagem PENAL (CP 10): incluído o dia do começo, sem prorrogação por sábado, "
                  "domingo ou feriado — não confundir com o prazo processual do calcular_prazo.py")
    avisos.append("em concurso de crimes a prescrição corre por crime, ISOLADAMENTE (CP 119); na "
                  "continuidade delitiva, sem o acréscimo da continuação (Súmula 497-STF) — "
                  "rode uma vez por crime")

    for c in cadeia:
        print(c)
    for w in avisos:
        print(f"⚠ AVISO: {w}")
    print("Datas provadas por certidão nos autos e conferência final: do advogado. Prescrição "
          "VIRTUAL (pena hipotética) é vedada pela Súmula 438 do STJ e não é calculada aqui.")


if __name__ == "__main__":
    main()
