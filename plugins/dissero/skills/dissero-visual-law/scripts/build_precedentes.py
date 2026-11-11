#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Gera a Relação de Precedentes, memorando de pesquisa interno, a partir de achados v2 ou v3.'






























import os, sys, json, re, argparse, shutil, hashlib, zipfile, tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_docx
import visual_law_core as core
import acentuacao_pt
import vocabulario_interno
import estrategia_precedentes
import achado_contract
import docx_para_pdf


def precedentes_usados(achados):
    """Selecionados allowed ou pending; prohibited nunca entra."""
    return [a for a in achados
            if isinstance(a, dict) and a.get("selected_for_use") is True
            and a.get("use_status") in ("allowed", "pending")]


def registro_legado(a):
    'Achado de pasta antiga: `verification` na forma antiga, com `status` e `data` preenchidos'



    v = a.get("verification")
    if not isinstance(v, dict) or "result" in v or "method" in v:
        return False
    return all(isinstance(v.get(k), str) and v.get(k).strip() for k in ("status", "data"))


VERIFICACAO_AUSENTE = "verificacao_ausente"


def conferir_contrato(dados, usados):
    'Confere cada achado usado que não é de pasta antiga: o achado sem o bloco'





    achados = dados.get("achados", [])
    linhas, indices = [], []

    def nome(i):
        return str(achados[i].get("id") or "").strip() or f"achado nº {i + 1} (sem id)"

    for i, a in enumerate(achados):
        if not any(a is u for u in usados) or registro_legado(a):
            continue
        if not isinstance(a.get("verification"), dict):
            linhas.append(f"{nome(i)}: {VERIFICACAO_AUSENTE}: o achado não traz o bloco "
                          f"`verification` com o resultado e o método da conferência. Confira o "
                          f"julgado na pesquisa e registre a conferência antes de gerar a "
                          f"Relação.")
            continue
        indices.append(i)
    if not indices:
        return linhas, True
    r = achado_contract.violacoes_por_achado(dados, indices)
    linhas += ["registro: " + e for e in r["documento"]]
    for i, motivos in sorted(r["achados"].items()):
        linhas += [f"{nome(i)}: {m}" for m in motivos]
    return linhas, r["catalogo"]


def _esc(s):



    s = (s or "").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


def _paragrafos(s):
    'Inteiro teor em PARÁGRAFOS, um por linha física — a regra do plugin é "inteiro teor'








    if not (s or "").strip():
        return []
    out = []
    for p in re.split(r"\n\s*\n", s):
        p = _esc(p)
        if not p:
            continue
        if re.match(r"^(?::::|>>|#)", p) or LISTA_RX.match(p):
            p = "​" + p
        out.append(p)
    return out


LISTA_RX = re.compile(r"^\s*(?:\d{1,2}[.)]\s|[a-z][.)]\s|\([a-z0-9]{1,3}\)\s|[+•–-]\s)")


def _rotulo(s):
    'Texto NOSSO: aspas retas, uma linha, acentuação restaurada, vocabulário de advogado.'




    return vocabulario_interno.sanitizar(acentuacao_pt.reacentuar(_esc(s)))


def conferir_acentuacao(usados):
    'Relatório de acentuação: o que a tabela não resolveu no rótulo e que literal parece'

    residuos, literais = [], []
    for i, a in enumerate(usados, 1):
        for r in acentuacao_pt.residuos(_rotulo(a.get("reference", ""))):
            residuos.append(f"#{i}: {r}")
        for campo in ("syllabus_literal", "full_text"):
            if acentuacao_pt.parece_sem_acento(a.get(campo) or ""):
                literais.append(f"#{i}: {campo}")
    return residuos, literais


SELO_LEGADO = "CONFIRMADO — método não declarado"


def texto_url(a):
    u = a.get("official_url")
    return u.strip() if isinstance(u, str) else ""

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _data_br(v):
    'Data do registro em DD/MM/AAAA (convenção do padrão). Devolve "" se não houver data'

    for campo in ("checked_at", "data", "date"):
        s = v.get(campo)
        if isinstance(s, str) and _ISO.match(s.strip()):
            a, m, d = _ISO.match(s.strip()).groups()
            return f"{d}/{m}/{a}"
    return ""


def selo(a):
    'Selo de estado do precedente: uma linha de leitura com o estado, a data da conferência'















    if a.get("use_status") == "pending":
        return "A CONFERIR NA FONTE OFICIAL ANTES DO PROTOCOLO"
    v = a.get("verification") or {}
    data = _data_br(v)
    sufixo = f" · {data}" if data else ""
    metodo = v.get("method")



    classe = (a.get("diagnostico_link") or {}).get("classe")
    if not texto_url(a) and (a.get("pendencia_fonte") or {}).get("falta"):

        return "CONFIRMADO" + sufixo + " · FONTE OFICIAL A OBTER (pendência registrada)"
    conf = a.get("conferencia") or {}
    aceite = a.get("fonte_aceita_pelo_advogado") or {}
    avisos = []



    if conf.get("processo") and conf.get("codigo"):
        avisos.append("conferir no e-SAJ com o código acima")
    elif classe == "nao_abre":
        avisos.append("ATENÇÃO: o link NÃO ABRE o julgado")
    elif classe == "efemera":
        avisos.append("ATENÇÃO: link EFÊMERO (sessão) — expira")
    elif classe == "busca":
        avisos.append("o link abre BUSCA, não o acórdão")
    elif classe == "processo":

        avisos.append("fonte é o processo no PJe (identidade confirmada)")
    elif classe == "agregador" and aceite.get("em"):

        avisos.append("fonte de agregador aceita pelo advogado")




    if not avisos and metodo not in ("human", "automatic"):
        res = (a.get("reconferencia") or {}).get("resultado")
        if res == "blocked":
            avisos.append("fonte recusa reconferência automática")
        elif res in ("not_found", "mismatch"):
            avisos.append("ATENÇÃO: reconferência NÃO confirmou pela fonte registrada")

    if metodo == "human":
        base = "CONFIRMADO PELO ADVOGADO"
    elif metodo == "automatic":
        base = "CONFIRMADO AUTOMATICAMENTE"
    else:


        base = "CONFIRMADO" if avisos else SELO_LEGADO
    return base + sufixo + "".join(" · " + x for x in avisos)


POSICOES = {

    "favoravel": "FAVORÁVEL — sustenta a tese",
    "contrario": "CONTRÁRIO — precisa ser ENFRENTADO na peça",
    "principiologico": "PRINCIPIOLÓGICO — base teórica, não precedente aplicável",
    "suporte_fatico": "SUPORTE FÁTICO — prova o fato, não a tese",
}


def montar_parecer(estrategia):
    'Abertura do memorando: tese central, distinguishing e enfrentamento dos contrários.'



    e = estrategia if isinstance(estrategia, dict) else {}
    tese = _rotulo(e.get("tese_central", ""))
    passos = [_rotulo(p) for p in (e.get("distinguishing") or []) if _rotulo(p)]
    contrarios = _rotulo(e.get("contrarios", ""))
    cobertura = e.get("cobertura_precedente")
    pesquisa = e.get("pesquisa_contraria") if isinstance(e.get("pesquisa_contraria"), dict) else {}
    if not (tese or passos or contrarios or cobertura or pesquisa):
        return []
    linhas = ["# MEMORANDO DE PESQUISA | PARECER DE ESTRATÉGIA", ""]
    rotulos_cobertura = {
        "confirmada": "confirmada por precedente aderente",
        "substituivel": "sustentada somente por autoridade alternativa indicada",
        "forcada": "apenas analógica — não serve como fundamento direto",
        "inexistente": "sem precedente aderente confirmado",
    }
    rotulos_pesquisa = {
        "nao_iniciada": "a busca de entendimento contrário ainda não foi feita",
        "concluida_sem_achado": "a busca de entendimento contrário foi concluída sem achado",
        "concluida_com_achado": "a busca localizou entendimento contrário, enfrentado abaixo",
        "bloqueada": "a busca de entendimento contrário ficou impedida e exige conferência",
    }
    situacoes = []
    if cobertura in rotulos_cobertura:
        situacoes.append("**Cobertura da tese:** " + rotulos_cobertura[cobertura] + ".")
    if pesquisa.get("estado") in rotulos_pesquisa:
        situacoes.append("**Pesquisa de entendimento contrário:** "
                         + rotulos_pesquisa[pesquisa["estado"]] + ".")



    if cobertura == "forcada":
        analogia = _rotulo(e.get("fundamentacao_analogica", ""))
        if analogia:
            situacoes.append("**A analogia invocada:** " + analogia)
        else:


            situacoes.append("**A analogia invocada:** não consta no registro — conferir antes "
                             "de usar o precedente como analógico.")
    if e.get("cobertura_valida_ate"):
        situacoes.append("**Revisar novamente até:** " + _rotulo(e["cobertura_valida_ate"]) + ".")
    if situacoes:
        linhas += ["::: caixa"] + situacoes + [":::", ""]
    if tese:
        linhas += ["::: sintese", tese, ":::", ""]
    if passos:
        linhas += ["## Distinguishing — os passos, na ordem em que a peça os usa", "",
                   "::: pedidos"]
        linhas += [f"{n}. {p}" for n, p in enumerate(passos, 1)]
        linhas += [":::", ""]
    if contrarios:
        linhas += ["## Enfrentamento dos precedentes contrários", "",
                   "::: caixa", contrarios, ":::", ""]
    return linhas


def montar_fonte(usados, caso="", estrategia=None):
    'Fonte do dialeto Dissero: banner + parecer de estratégia + uma ::: caixa por precedente.'



    caso = acentuacao_pt.reacentuar(caso or "")
    titulo = f"RELAÇÃO DE PRECEDENTES — {caso}".rstrip(" —") if caso else "RELAÇÃO DE PRECEDENTES"
    bloqueados = [a for a in usados if a.get("use_status") == "pending"]
    linhas = [f"# DOCUMENTO INTERNO — NÃO PROTOCOLAR | {titulo}", ""]
    if bloqueados:


        quantos = (f"{len(bloqueados)} dos {len(usados)} precedentes"
                   if len(bloqueados) != len(usados)
                   else (f"Os {len(usados)} precedentes" if len(usados) > 1 else "O precedente"))
        linhas += ["::: caixa",
                   f"**A CONFERIR ANTES DO PROTOCOLO.** {quantos} desta Relação ainda não "
                   "foram conferidos na fonte oficial do tribunal. Podem ficar assinalados na "
                   "minuta enquanto ela se escreve, mas ou se confere cada um na fonte, ou ele "
                   "sai da peça antes do protocolo. A conferência é do advogado.",
                   ":::", ""]
    linhas += montar_parecer(estrategia)
    if any(a.get("estrategia_uso") for a in usados) or estrategia:
        linhas += ["# PRECEDENTES | UM A UM", ""]
    for i, a in enumerate(usados, 1):
        ref = _rotulo(a.get("reference", ""))
        ementa = _esc(a.get("syllabus_literal", ""))
        link = _esc(a.get("official_url", ""))
        pendente = a.get("use_status") == "pending"
        estado = selo(a)
        linhas += [f"## {i} · {ref}" + ("  [A CONFERIR]" if pendente else ""), "", "::: caixa"]




        uso = a.get("estrategia_uso") or {}
        if isinstance(uso, str):
            uso = {"posicao": None, "como_usar": uso}
        elif not isinstance(uso, dict):
            uso = {}
        como_usar = _rotulo(uso.get("como_usar", ""))
        if como_usar:
            rotulo_pos = POSICOES.get(uso.get("posicao"), "")
            cabeca = f"**Como usar ({rotulo_pos}):** " if rotulo_pos else "**Como usar:** "
            linhas.append(cabeca + como_usar)
            linhas.append("")
        if ementa:
            linhas.append(f"**Ementa:** {ementa}")
            linhas.append("")
        integral = _paragrafos(a.get("full_text"))
        if integral:
            linhas.append("**Inteiro teor:**")
            for p in integral:
                linhas.append(p)
            linhas.append("")

        pend = a.get("pendencia_fonte") or {}
        if link:
            linhas.append(f"**Fonte:** {link}")
        elif pend.get("falta"):

            linhas.append("**Fonte:** ==[A OBTER — ver Pendência abaixo]==")
        else:
            linhas.append("**Fonte:** ==[URL OFICIAL AUSENTE]==")
        linhas.append("")
        if not link and pend.get("falta"):

            linhas.append(f"**Pendência:** {_rotulo(pend['falta'])} — {_rotulo(pend.get('como_obter', ''))}")
            linhas.append("")


        conf = a.get("conferencia") or {}
        if conf.get("processo") and conf.get("codigo"):
            linhas.append(f"**Conferência:** processo {_esc(conf['processo'])} · código "
                          f"{_esc(conf['codigo'])}")
            linhas.append("")
        linhas.append(f"**Situação:** {estado}")
        linhas += [":::", ""]
    return "\n".join(linhas)







MARCA_RELACAO = "relacao-precedentes:sha256="


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


def carimbar_origem(docx, sha):
    """Grava `MARCA_RELACAO<sha>` em `cp:keywords` do docProps/core.xml do .docx."""
    marca = MARCA_RELACAO + sha
    with zipfile.ZipFile(docx) as z:
        itens = [(i, z.read(i.filename)) for i in z.infolist()]
    saida = []
    for info, dados in itens:
        if info.filename == "docProps/core.xml":
            xml = dados.decode("utf-8")
            if re.search(r"<cp:keywords>.*?</cp:keywords>", xml, re.S):
                xml = re.sub(r"<cp:keywords>.*?</cp:keywords>",
                             f"<cp:keywords>{marca}</cp:keywords>", xml, flags=re.S)
            else:
                xml = xml.replace("</cp:coreProperties>",
                                  f"<cp:keywords>{marca}</cp:keywords></cp:coreProperties>")
            dados = xml.encode("utf-8")
        saida.append((info, dados))
    fd, tmp = tempfile.mkstemp(suffix=".docx", dir=os.path.dirname(os.path.abspath(docx)))
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for info, dados in saida:
                z.writestr(info, dados)
        os.replace(tmp, docx)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def build_precedentes(achados_json, out_docx, caso="", pdf=False):
    with open(achados_json, encoding="utf-8") as f:
        dados = json.load(f)
    if (not isinstance(dados, dict)
            or dados.get("schema_version") not in ("dsr.achados.v2", "dsr.achados.v3")):
        print("ERRO: contrato dsr.achados.v2 ou dsr.achados.v3 obrigatório.")
        sys.exit(2)
    if dados.get("schema_version") == "dsr.achados.v3":
        falhas = estrategia_precedentes.validar_v3(dados)
        if falhas:
            print("ERRO: estratégia jurisprudencial v3 incompleta — a Relação não pode "
                  "apresentar uma certeza que o registro não sustenta:")
            for falha in falhas:
                print("  ·", falha)
            sys.exit(2)
    achados = dados.get("achados", [])
    usados = precedentes_usados(achados)
    if not usados:
        print("ERRO: nenhum precedente selecionado com estado allowed ou pending — "
              "nada a gerar (a Relação de Precedentes não é criada vazia).")
        sys.exit(2)
    fora, catalogo = conferir_contrato(dados, usados)
    if fora:
        print("ERRO: achado fora do contrato do achado — a Relação de Precedentes não é gerada. "
              "Corrija o registro na pesquisa e gere de novo:")
        for linha in fora:
            print("  ·", linha)
        sys.exit(2)
    if not catalogo:
        print("AVISO: o catálogo de fontes oficiais não acompanha esta skill. O host de cada "
              "confirmação, automática ou do advogado, é conferido na pesquisa, pelo validador "
              "de achados; aqui o contrato do achado rodou sem essa parte.")
    estrategia = dados.get("estrategia") if isinstance(dados, dict) else None
    fonte = montar_fonte(usados, caso, estrategia)




    sobras = vocabulario_interno.residuos(fonte)
    if sobras:
        print("ERRO: vocabulário interno no texto da Relação — o advogado lê este documento, "
              "e nome de script, campo de registro e diagnóstico de sessão não podem sair "
              "impressos. Reescreva o campo de origem em linguagem de advogado "
              "(transcrição literal contaminada se conserta na EXTRAÇÃO, não aqui):")
        for r in sobras:
            print(f"  · {r['classe']}: «{r['termo']}»")
        sys.exit(3)




    work = core.dir_de_trabalho("dsrvl_precedentes_")
    try:
        tmp_md = os.path.join(work, "relacao.md")
        with open(tmp_md, "w", encoding="utf-8") as f:
            f.write(fonte)



        build_docx.build(tmp_md, out_docx, identidade=False, force=True, jusmanizer_ativo=False)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    carimbar_origem(out_docx, sha256_arquivo(achados_json))

    legados = [i for i, x in enumerate(usados, 1) if selo(x).startswith(SELO_LEGADO)]
    if legados:
        print(f"AVISO: {len(legados)} de {len(usados)} precedente(s) sem `verification.method` do "
              f"contrato v2 — selados como método NÃO DECLARADO (nunca como automático). "
              f"Rode validar_achados.py para regularizar: "
              f"#{', #'.join(str(i) for i in legados[:20])}" + (" …" if len(legados) > 20 else ""))

    residuos, literais = conferir_acentuacao(usados)
    if residuos:
        print("AVISO de acentuação (rótulo — conferir à mão; a tabela não cobre nome próprio):")
        print("  ·", ", ".join(residuos[:20]) + (" …" if len(residuos) > 20 else ""))
    if literais:
        print("AVISO: transcrição literal aparentemente SEM acentuação — não foi alterada "
              "(literal não se reacentua; reextraia da fonte oficial):")
        for l in literais[:10]:
            print("  ·", l)

    if pdf:
        caminho, rota = docx_para_pdf.converter(out_docx)
        if caminho:
            print(f"PDF → {caminho} | rota: {rota}")
        else:
            print("AVISO: PDF não gerado (sem Word/COM nem LibreOffice); o .docx está pronto.")
            for d in docx_para_pdf.DIAGNOSTICO:
                print("  ·", d)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Relação de Precedentes (uso interno).")
    ap.add_argument("achados_json")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--caso", default="")
    ap.add_argument("--pdf", action="store_true",
                    help="gerar também o PDF ao lado do .docx (padrão: NÃO gera)")
    a = ap.parse_args()
    build_precedentes(a.achados_json, a.out, a.caso, pdf=a.pdf)
