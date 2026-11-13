#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_docx.py — modo BUILDER do Visual Law: gera o .docx já no padrão a partir do dialeto
markdown documentado no SKILL.md §4 e em references/dialeto-exemplo.md (blocos `:::` lidos por `visual_law_core.parse_blocks`).

Uso:
  python build_docx.py entrada.md saida.docx                # fragmento (sem cabeçalho e rodapé)
  python build_docx.py entrada.md saida.docx --identidade   # peça final (timbrado do perfil)
  python build_docx.py entrada.md --check                   # só valida, não gera
  python build_docx.py entrada.md saida.docx --force        # gera mesmo com AVISOS (nunca com ERROS)
  python build_docx.py entrada.md saida.docx --precedentes achados.json   # resolve `>> achado: <id>`
  python build_docx.py entrada.md saida.docx --minuta-pendencias   # MINUTA COM PENDÊNCIAS
  (`--fragmento` é aceito e é o padrão: sem `--identidade`. Flag desconhecida é recusada.)

MINUTA COM PENDÊNCIAS (`--minuta-pendencias`), sempre que a peça não libera: o documento sai com
a faixa constante logo depois da capa (no topo, sem capa) e o carimbo `DSRMinutaPendencias`,
sem como desligar. O que é rito ou estilo vira pendência listada em vez de parada: Jusmanizer
com ERRO, avisos de dialeto, `>> achado:` sem `--precedentes` (vira marcador de
jurisprudência a conferir), `{{CAMPO}}` sem perfil (vira ==[COMPLETAR: campo]==) e
`--identidade` sem perfil (sai em fragmento, com aviso). Marcador nu de prefixo fixo
(`[JURISPRUDÊNCIA A CONFERIR`, `[CONFERIR`, `[COMPLETAR`) sai realçado e listado. Continuam
travando: erro estrutural de dialeto, corpo que repete o timbrado, OOXML inválido,
jusmanizer.py ausente, e (exit 3) rastro de chat do Jusmanizer (J23) ou vocabulário interno
(`vocabulario_interno.residuos`) no corpo: encanamento nunca vai ao documento.

Antes de gerar, o builder valida o dialeto e aborta apontando linha e bloco, em vez de produzir
um .docx parcial que perde conteúdo em silêncio.
  Erros (abortam): bloco `:::` sem fechamento, de tipo desconhecido ou aberto dentro de outro;
  `>>` fora de `:::jurisprudencia`; papel de capa/fecho fora do bloco; dois papéis na mesma linha.
  Avisos (na geração abortam sem --force; no --check só aparecem): capa sem `titulo:`; fecho
  sem `ass:`; nada reconhecível.

Saída: 0 gerado (ou válido, no --check) · 1 uso · 2 OOXML inválido · 3 dialeto ou Jusmanizer
reprovado · 4 avisos sem --force · 5 --precedentes ilegível ou fora do contrato
dsr.achados.v2 ou v3, `achado:` sem dataset ou com id inexistente, saída em uso · 6 timbrado não
resolvido · 7 placeholder não resolvido ou timbrado colado no corpo · 8 jusmanizer.py ausente.
Na MINUTA COM PENDÊNCIAS, 2 também quando a marca não ficou gravada (o arquivo é apagado).
"""
import html
import json
import os
import re
import sys
import shutil



try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import visual_law_core as core
import carimbo_timbrado
try:
    import jusmanizer
except Exception as _e:
    print(f"ERRO: jusmanizer.py indisponível ao lado do builder ({_e}); o --check não pode medir "
          f"traços de IA no markdown")
    sys.exit(8)
try:
    import vocabulario_interno
except Exception as _e:
    print(f"ERRO: vocabulario_interno.py indisponível ao lado do builder ({_e})")
    sys.exit(8)
try:
    import perfil_advogado as _pa
except Exception:
    _pa = None
try:
    import escolha_do_metodo
except Exception:
    escolha_do_metodo = None



EXIT_FALTA_ESCOLHA_OU_ETAPA = 9



TIPOS_VALIDOS = ("capa", "caixa", "cita", "juris", "pedidos", "fecho", "quebra",
                 "tabela", "timeline", "sintese", "ancora")



PAPEIS_CAPA, PAPEIS_FECHO = core.PAPEIS_CAPA, core.PAPEIS_FECHO
_RX_PAPEL_CAPA = re.compile(r"^(%s):" % "|".join(PAPEIS_CAPA))
_RX_PAPEL_FECHO = re.compile(r"^(%s):" % "|".join(PAPEIS_FECHO))
_RX_PAPEL = re.compile(r"^(%s):\s" % "|".join(PAPEIS_CAPA + PAPEIS_FECHO))
_RX_PAPEIS_NA_LINHA = re.compile(r"(?:^|[\s,.;])(%s):\s" % "|".join(PAPEIS_CAPA + PAPEIS_FECHO))


def validar_dialeto(src):
    'Devolve (erros, avisos) como listas de strings. Não altera o conteúdo.'





    erros, avisos = [], []
    lines = src.splitlines()
    abertos = []
    tem_bloco = False
    capa_roles = fecho_roles = None

    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        s = ln.strip()
        n = i + 1

        if s.startswith(":::"):
            tipo = s[3:].strip().lower()
            if not abertos:

                if tipo == "":

                    erros.append(f"linha {n}: ':::' de fechamento sem bloco aberto correspondente")
                elif tipo.startswith("quebra"):
                    tem_bloco = True
                elif any(tipo.startswith(t) for t in TIPOS_VALIDOS):
                    abertos.append((n, tipo))
                    tem_bloco = True
                    if tipo.startswith("capa"):
                        capa_roles = []
                    elif tipo.startswith("fecho"):
                        fecho_roles = []
                else:
                    erros.append(f"linha {n}: tipo de bloco desconhecido ':::{tipo}' "
                                 f"(válidos: capa, caixa, citacao, jurisprudencia, pedidos, fecho, "
                                 f"quebra, tabela, timeline, sintese)")
                    abertos.append((n, "__ignorar__"))
            else:

                if tipo == "":
                    abertos.pop()
                else:
                    erros.append(f"linha {n}: novo bloco ':::{tipo}' aberto antes de fechar "
                                 f"o bloco da linha {abertos[-1][0]}")
            i += 1
            continue


        if abertos and abertos[-1][1].startswith("capa") and s:
            m = _RX_PAPEL_CAPA.match(s)
            if m and capa_roles is not None:
                capa_roles.append(m.group(1))
        if abertos and abertos[-1][1].startswith("fecho") and s:
            m = _RX_PAPEL_FECHO.match(s)
            if m and fecho_roles is not None:
                fecho_roles.append(m.group(1))






        papel = _RX_PAPEL.match(s)
        dentro_bloco_valido = bool(abertos) and abertos[-1][1] != "__ignorar__"
        dentro_capa_fecho = abertos and (abertos[-1][1].startswith("capa") or abertos[-1][1].startswith("fecho"))
        if papel and not dentro_bloco_valido:
            erros.append(f"linha {n}: papel '{papel.group(1)}:' fora do bloco :::capa/:::fecho — viraria texto do corpo")
        if dentro_capa_fecho and len(_RX_PAPEIS_NA_LINHA.findall(s)) > 1:
            erros.append(f"linha {n}: mais de um papel na mesma linha — um papel por linha (não junte as linhas do dialeto)")


        if s.startswith(">>") and not (abertos and abertos[-1][1].startswith("juris")):
            erros.append(f"linha {n}: '>>' (ementa) fora de um bloco ':::jurisprudencia'")




        if not abertos and s.startswith("#") and not (ln.startswith("# ") or ln.startswith("## ")):
            avisos.append(f"linha {n}: título fora do dialeto «{s[:40]}» (use '# ' para banner "
                          f"ou '## ' para legenda); sai como legenda ou como corpo")


        if s.startswith("#") or s.startswith("## ") or s.startswith("~ ") or (s and not s.startswith("&")):
            tem_bloco = True

        i += 1


    for (ln_n, tipo) in abertos:
        if tipo != "__ignorar__":
            erros.append(f"linha {ln_n}: bloco ':::{tipo}' aberto e nunca fechado com ':::' "
                         f"(isto descartaria todo o conteúdo seguinte)")


    if capa_roles is not None and "titulo" not in capa_roles:
        avisos.append("bloco ':::capa' sem campo 'titulo:' — a capa ficará sem caixa de título")
    if fecho_roles is not None and "ass" not in fecho_roles:
        avisos.append("bloco ':::fecho' sem campo 'ass:' — o fecho ficará sem assinatura")
    if not tem_bloco:
        avisos.append("nenhum bloco ou conteúdo reconhecível no arquivo — o .docx sairia vazio")

    return erros, avisos


def corpo_com_timbrado(src, perfil):
    'A linha do corpo que repete o cabeçalho ou o rodapé do perfil, ou None. É o sintoma da'








    if not perfil:
        return None
    cab = ((perfil.get("advogado") or {}).get("nome_exibicao_cabecalho") or "").strip()
    c = perfil.get("contato") or {}
    end = (c.get("endereco") or "").strip()
    cidade_uf = (c.get("cidade_uf") or "").strip()
    cep = (c.get("cep") or "").strip()
    partes_endereco = [p for p in (end, cidade_uf, cep) if p]
    exige_endereco = bool(end) and len(partes_endereco) >= 2
    limite_endereco = sum(len(p) for p in partes_endereco) + 40
    for linha in src.splitlines():
        t = linha.strip().strip("*_ ")
        if cab and t == cab:
            return linha
        if exige_endereco and len(t) <= limite_endereco and all(p in t for p in partes_endereco):
            return linha
    return None


def dispensas_do_perfil(perfil):
    'Padrões do Jusmanizer que `estilo_escrita.overrides` do perfil dispensa (`J01` com'



    if not perfil or _pa is None:
        return set()
    try:
        import lint_peca
        return set(lint_peca.dispensas_de_estilo(_pa.estilo_overrides(perfil))["excluir"])
    except (Exception, SystemExit):
        return set()





FLAGS_CONHECIDAS = ("--identidade", "--fragmento", "--force", "--check", "--precedentes",
                    "--minuta-pendencias")



_CAMPO_EM_PORTUGUES = {
    "ADVOGADO_NOME": "nome do advogado", "NOME_CABECALHO": "nome do advogado",
    "OAB": "inscrição na OAB", "LINHA_OAB": "inscrição na OAB",
    "ESCRITORIO": "nome do escritório", "EMAIL": "e-mail", "TELEFONE": "telefone",
    "CIDADE_ASSINATURA": "cidade da assinatura", "LINHA_ENDERECO": "endereço do escritório",
    "LINHA_CONTATO": "contato do escritório",
}


MARCADOR_EMENTA_A_CONFERIR = ("==[JURISPRUDÊNCIA A CONFERIR: transcrever a ementa da fonte "
                              "oficial]==")








RX_MARCADOR = re.compile(r"\[\s*" + core.PREFIXOS_MARCADOR_PENDENCIA + r"[^\]\n]*\](?!\()",
                         re.I)
RX_MARCADOR_NU = re.compile(r"(?<!==)\[\s*" + core.PREFIXOS_MARCADOR_PENDENCIA
                            + r"[^\]\n]*\](?!==)(?!\()", re.I)



PENDENCIA_ESTRUTURA = "há títulos ou blocos fora do padrão do escritório"


def realcar_marcadores(src):
    '(src com os marcadores nus realçados por `==`, lista de todos os marcadores do texto,'

    todos = [m.group(0) for m in RX_MARCADOR.finditer(src)]
    return RX_MARCADOR_NU.sub(lambda m: "==" + m.group(0) + "==", src), todos


def texto_do_corpo(body_xml):
    'O texto de cada parágrafo do corpo montado, para a conferência de vocabulário interno'

    paras = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", body_xml, re.S):
        t = "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", p))
        if t.strip():
            paras.append(html.unescape(t))
    return paras


def _marcador_de_campo(m):
    campo = m.group(0)[2:-2]
    return "==[COMPLETAR: " + _CAMPO_EM_PORTUGUES.get(campo, "dado do advogado") + "]=="


def build(md_path, out_docx, identidade=False, force=False, check_only=False,
          precedentes=None, jusmanizer_ativo=True, minuta_pendencias=False):
    '`minuta_pendencias=True` é a MINUTA COM PENDÊNCIAS (docstring do módulo): o que é rito'


    pendencias = []
    with open(md_path, encoding="utf-8") as f:
        src = f.read()

    src = core.normalizar_datas(src)

    if minuta_pendencias and escolha_do_metodo is not None:




        _pend_escolha, _parada = escolha_do_metodo.exigir_para_minuta(
            src, os.path.dirname(os.path.abspath(md_path)))
        if _parada:
            print(_parada)
            sys.exit(EXIT_FALTA_ESCOLHA_OU_ETAPA)
        pendencias.extend((p, None) for p in _pend_escolha)

    if minuta_pendencias:
        src, _marcadores = realcar_marcadores(src)
        if _marcadores:
            pendencias.append((f"{len(_marcadores)} trecho(s) marcado(s) para conferência, "
                               f"realçado(s) no documento: "
                               + "; ".join(m if len(m) <= 90 else m[:86] + "...]"
                                           for m in _marcadores), None))




    _perfil = None
    if _pa is not None:
        try:
            _perfil = _pa.carregar()
            if _perfil:
                src = _pa.resolver_texto(src, _perfil)
        except Exception:
            pass




    if identidade and _perfil:
        _linha_timbrada = corpo_com_timbrado(src, _perfil)
        if _linha_timbrada:
            print("ERRO: o corpo repete o timbrado do perfil:\n  " + _linha_timbrada.strip()
                  + "\n  Cabeçalho e rodapé entram pelo --identidade, não pelo texto. Remova essa linha (e as demais "
                  "do cabeçalho/rodapé coladas no corpo) e gere de novo.")
            sys.exit(7)




    _orfaos = sorted(set(re.findall(r"\{\{[A-Z_]{2,}\}\}", src)))
    if _orfaos and minuta_pendencias:
        src = re.sub(r"\{\{[A-Z_]{2,}\}\}", _marcador_de_campo, src)
        pendencias.append(("dados do advogado marcados para completar (perfil não configurado): "
                           + ", ".join(sorted({_CAMPO_EM_PORTUGUES.get(o[2:-2], "dado do advogado")
                                               for o in _orfaos})), None))
        _orfaos = []
    if _orfaos:
        print(f"ERRO: placeholder não resolvido no texto: {', '.join(_orfaos)}")
        print("  São campos do perfil que ninguém preencheu, ou nomes que não existem.")
        print("  Disponíveis: {{ADVOGADO_NOME}} {{NOME_CABECALHO}} {{OAB}} {{ESCRITORIO}}")
        print("               {{CIDADE_ASSINATURA}} {{EMAIL}} {{TELEFONE}}")
        print("  Confira o perfil: perfil_advogado.py --status")
        sys.exit(7)


    erros, avisos = validar_dialeto(src)
    if avisos:
        print("AVISOS de dialeto:")
        for a in avisos:
            print(" ⚠", a)
    if erros:
        print("ERROS de dialeto (geração abortada):")
        for e in erros:
            print(" ✗", e)
        print("Corrija a FONTE e gere de novo (nada foi escrito).")
        sys.exit(3)









    if jusmanizer_ativo:
        _dispensados = dispensas_do_perfil(_perfil)
        if _dispensados:
            print("Jusmanizer: dispensados pelo perfil (estilo_escrita.overrides): "
                  + ", ".join(sorted(_dispensados)))
        _paras, _titulos = jusmanizer.paragrafos_prosa_markdown(src)
        _jm = jusmanizer.analisar(_paras, titulos=_titulos, excluir=_dispensados)
        if _jm["ocorrencias"]:
            print(f"Jusmanizer: {_jm['veredito'].upper()} · {len(_jm['ocorrencias'])} ocorrência(s)")
            for o in _jm["ocorrencias"][:40]:
                print(f" {'✗' if o['severidade'] == 'erro' else '⚠'} {o['padrao']} {o['nome']}: "
                      f"«{o['contexto']}»")
            _rastro = [o for o in _jm["ocorrencias"]
                       if o["padrao"] == "J23" and o["severidade"] == "erro"]
            if _rastro and minuta_pendencias:


                print("ERRO: o texto traz rastro de conversa ou nome interno do sistema "
                      "(J23), que nunca vai ao documento, nem na MINUTA COM PENDÊNCIAS:")
                for o in _rastro[:10]:
                    print(f"  · «{o['contexto']}»")
                print("Reescreva esses trechos em português de advogado e gere de novo "
                      "(nada foi escrito).")
                sys.exit(3)
            if _jm["veredito"] == "erro" and minuta_pendencias:
                pendencias.append((f"estilo de escrita a revisar ({len(_jm['ocorrencias'])} "
                                   f"ocorrência(s) listadas acima)", None))
            elif _jm["veredito"] == "erro":
                print("Reescreva a FONTE pelo catálogo (estilo-escrita.md §2) e gere de novo.")
                sys.exit(3)
        else:
            print("Jusmanizer: limpo")




    for _aviso_l30 in core.l30_avisos_da_fonte(core.parse_blocks(src)):
        print(f"Estilo: AVISO {_aviso_l30}")



    for _aviso_l33 in core.l33_avisos_da_fonte(core.parse_blocks(src)):
        print(f"Estilo: AVISO {_aviso_l33} O linter reprova a peça enquanto o número ficar.")

    if check_only:
        print("Dialeto OK." if not avisos else "Dialeto válido, com avisos acima.")
        return
    if avisos and minuta_pendencias:
        pendencias.append((PENDENCIA_ESTRUTURA, "; ".join(avisos)))
    elif avisos and not force:
        print("Há avisos. Revise, ou use --force para gerar mesmo assim.")
        sys.exit(4)

    base_docx = os.path.join(core.ASSETS_DIR, "base_template.docx")
    blocks = core.parse_blocks(src)



    if identidade and _perfil:
        _adv = (_perfil.get("advogado") or {})
        _n = core.completar_oab_no_fecho(blocks, (_adv.get("oab") or "").strip(),
                                         _adv.get("nome"), _adv.get("nome_exibicao_cabecalho"))
        if _n:
            print(f"Assinatura: inscrição na OAB do perfil acrescentada em {_n} fecho(s).")




    n_injetados = 0
    if precedentes:
        try:
            dados = json.load(open(precedentes, encoding="utf-8"))
        except Exception as e:
            print(f"ERRO: --precedentes ilegível ({precedentes}): {e}")
            sys.exit(5)

        if (not isinstance(dados, dict)
                or dados.get("schema_version") not in ("dsr.achados.v2", "dsr.achados.v3")):
            print("ERRO: --precedentes fora do contrato dsr.achados.v2 ou dsr.achados.v3")
            sys.exit(5)
        try:
            blocks, n_injetados = core.injetar_achados(blocks, dados.get("achados") or [])
        except core.AchadoAusente as e:
            print(f"ERRO: {e}")
            sys.exit(5)
    else:
        pendentes = [l for _k, p in blocks if _k == "juris" for _c, em in p
                     for l in em if core.RX_REF_ACHADO.match(l or "")]
        if pendentes and minuta_pendencias:
            blocks = [(_k, [(_c, [MARCADOR_EMENTA_A_CONFERIR
                                  if core.RX_REF_ACHADO.match(l or "") else l for l in em])
                            for _c, em in p])
                      if _k == "juris" else (_k, p) for _k, p in blocks]
            pendencias.append((f"{len(pendentes)} ementa(s) sem o teor verificado, marcadas como "
                               f"jurisprudência a conferir", None))
            pendentes = []
        if pendentes:
            print("ERRO: a fonte referencia julgado por `>> achado: <id>` e o dataset não foi "
                  "apresentado (--precedentes achados.json). A referência existe para que a "
                  "ementa NÃO seja digitada: sem o dataset não há de onde copiá-la.")
            for l in pendentes[:5]:
                print("  ·", l)
            sys.exit(5)




    core.definir_layout(_perfil)
    core.definir_tema(_perfil)
    _ass = None
    if _pa is not None:
        try:
            _ass = _pa.imagem_avulsa(_perfil, "assinatura")
        except Exception:
            pass
    core.definir_assinatura(_ass, ((_perfil or {}).get("advogado") or {}).get("nome"))
    _faixa_esperada_em = None
    if minuta_pendencias:





        _pos_capa = next((i + 1 for i, (k, _p) in enumerate(blocks) if k == "capa"), 0)
        _faixa_esperada_em = (len(texto_do_corpo(core.blocks_to_xml(blocks[:_pos_capa])))
                              if _pos_capa else 0)


        blocks = core.inserir_faixa_minuta(blocks)
    body_xml = core.blocks_to_xml(blocks)

    if minuta_pendencias:


        _vazados = []
        for _t in texto_do_corpo(body_xml):
            for _r in vocabulario_interno.residuos(_t):
                if _r["termo"] not in _vazados:
                    _vazados.append(_r["termo"])
        if _vazados:
            print("ERRO: o texto traz nome interno do sistema, que nunca vai ao documento, nem "
                  "na MINUTA COM PENDÊNCIAS: " + ", ".join(f"«{t}»" for t in _vazados[:15]))
            print("Reescreva esses trechos em português de advogado e gere de novo "
                  "(nada foi escrito).")
            sys.exit(3)

    def _montar(work, com_identidade):
        'Monta o pacote em `work` e devolve (n_links, advogado). Timbrado que não resolve'


        core.unpack(base_docx, work)
        core.aplicar_estilo_corpo(work)
        doc_path = os.path.join(work, "word", "document.xml")
        with open(doc_path, encoding="utf-8") as f:
            base_doc = f.read()
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(core.build_document_xml(base_doc, body_xml))
        n_links = core.injetar_links(work)
        core.incorporar_assinatura(work)
        advogado = None
        if com_identidade:


            try:
                core.inject_header_footer(work)
                if _pa is not None:
                    try:
                        core.injetar_brasao(work, _pa.imagem_avulsa(_perfil, "brasao"))
                    except Exception:
                        pass
            except Exception as erro:
                if (type(erro).__name__ in ("PerfilAusente", "PerfilError")
                        or "TIMBRADO NÃO RESOLVIDO" in str(erro)
                        or "PACOTE DE IDENTIDADE SEM TIMBRADO" in str(erro)):
                    if minuta_pendencias:
                        print("AVISO: sai sem o timbrado do escritório (o perfil do advogado "
                              "não está configurado); a minuta segue sem cabeçalho e rodapé.")
                        print("  detalhe para o assistente: o timbrado não resolveu pelo perfil "
                              f"({type(erro).__name__}); a peça final pede o perfil configurado.")
                        return None
                    print(f"ERRO: {erro}")
                    sys.exit(6)
                raise


            carimbo_timbrado.carimbar_do_perfil(work, _perfil)
            advogado = ((_perfil or {}).get("advogado") or {}).get("nome")
        if minuta_pendencias:

            carimbo_timbrado.carimbar_minuta_pendencias(work)
        return n_links, advogado

    work = core.dir_de_trabalho("dsrvl_build_")
    try:
        montado = _montar(work, identidade)
        if montado is None:

            shutil.rmtree(work, ignore_errors=True)
            work = core.dir_de_trabalho("dsrvl_build_")
            identidade = False
            pendencias.append(("sem o timbrado do escritório (perfil não configurado): o "
                               "documento saiu sem cabeçalho e rodapé", None))
            montado = _montar(work, False)
        n_links, advogado = montado
        try:
            core.pack(work, out_docx)
        except core.ArquivoEmUso as erro:
            print(f"ERRO: {erro}")
            sys.exit(5)
        errs = core.validate_docx(out_docx)
        if errs:
            print("ERROS DE VALIDAÇÃO:")
            for e in errs:
                print(" -", e)
            sys.exit(2)
        _recusar_texto_oculto(out_docx)
        if minuta_pendencias and not _tem_marca(out_docx):


            try:
                os.remove(out_docx)
            except OSError:
                pass
            print("ERRO: a marca de MINUTA COM PENDÊNCIAS não ficou gravada no documento; "
                  "nada foi gerado. Gere de novo.")
            sys.exit(2)
        if minuta_pendencias and core.indice_da_faixa(out_docx) != _faixa_esperada_em:


            try:
                os.remove(out_docx)
            except OSError:
                pass
            print("ERRO: a faixa de MINUTA COM PENDÊNCIAS não ficou no primeiro parágrafo do "
                  "corpo (logo depois da capa, ou no topo sem capa); nada foi gerado.")
            sys.exit(2)
        n_tbl = body_xml.count("<w:tbl>")
        n_p = body_xml.count("<w:p>")
        print(f"OK → {out_docx} | {n_p} parágrafos, {n_tbl} elementos estruturais, "
              f"{n_links} hiperlink(s), "
              f"identidade={(advogado or 'do perfil') if identidade else 'nenhuma (fragmento)'}")
        if minuta_pendencias:
            print("MINUTA COM PENDÊNCIAS: faixa no corpo e marca gravadas. Não é a peça "
                  "liberada: não passou pela revisão completa e não se protocola como está.")
            print("Pendências apontadas pelo gerador:" if pendencias else
                  "Pendências apontadas pelo gerador: nenhuma; as da revisão continuam.")
            for frase, detalhe in pendencias:
                print(f"  · {frase}")
                if detalhe:
                    print(f"      detalhe para o assistente (não repassar): {detalhe}")
    finally:


        shutil.rmtree(work, ignore_errors=True)


def _texto_oculto_na_saida(caminho):
    "Os achados de severidade alta da varredura estrutural no .docx GERADO, numa linha, ou ''."





    try:
        import varredura_documento as _vd
        r = _vd.varrer_docx(caminho)
    except Exception:
        return ""
    if r.get("exit_code") != 1:
        return ""
    altas = [a for a in r.get("achados", []) if a.get("severidade") == "alta"]
    return "; ".join(str(a.get("id")) for a in altas[:5])


def _recusar_texto_oculto(out_docx):
    """Apaga a saída e encerra quando ela carrega elemento oculto. Sem achado, não faz nada."""
    achados = _texto_oculto_na_saida(out_docx)
    if not achados:
        return
    try:
        os.remove(out_docx)
    except OSError:
        pass
    print("ERRO: o documento gerado carrega elemento oculto (" + achados + "): texto que o leitor "
          "não vê, como letra branca, corpo mínimo ou trecho escondido. Nada foi gerado. Isso costuma "
          "vir do documento de origem ou do modelo do escritório; diga ao advogado onde está e gere "
          "de novo sem o trecho.")
    sys.exit(2)


def _tem_marca(caminho):
    'A marca da MINUTA COM PENDÊNCIAS no .docx gravado, pela mesma leitura que a entrega'

    try:
        import varredura_documento
        return varredura_documento.tem_marca_de_pendencias(caminho)
    except Exception:
        return False


if __name__ == "__main__":
    brutos = sys.argv[1:]
    args, prec, i = [], None, 0
    while i < len(brutos):
        a = brutos[i]
        if a == "--precedentes":
            if i + 1 < len(brutos):
                prec = brutos[i + 1]
            i += 2
            continue
        if not a.startswith("--"):
            args.append(a)
        i += 1
    flags = {a for a in brutos if a.startswith("--")}
    desconhecidas = sorted(flags - set(FLAGS_CONHECIDAS))
    if desconhecidas:
        print(f"ERRO: flag desconhecida: {', '.join(desconhecidas)}. Aceitas: "
              f"{', '.join(FLAGS_CONHECIDAS)}. Nada foi gerado.")
        sys.exit(1)
    check_only = "--check" in flags
    if (check_only and len(args) < 1) or (not check_only and len(args) != 2):
        print(__doc__)
        sys.exit(1)
    out = args[1] if len(args) > 1 else os.devnull
    build(args[0], out,
          identidade="--identidade" in flags,
          force="--force" in flags,
          check_only=check_only,
          precedentes=prec,
          minuta_pendencias="--minuta-pendencias" in flags)
