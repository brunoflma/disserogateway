#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
transform_docx.py — modo TRANSFORMER do Visual Law: aplica o padrão a um .docx bruto
preservando 100% do conteúdo.

Uso (passo universal, determinístico):
  python transform_docx.py bruto.docx saida.docx                      # fragmento (remove cabeçalho/rodapé)
  python transform_docx.py bruto.docx saida.docx --identidade         # peça final (timbrado do perfil)
  python transform_docx.py bruto.docx saida.docx --manter-identidade  # conserva cabeçalho e rodapé
  python transform_docx.py bruto.docx saida.docx --minuta-pendencias  # MINUTA COM PENDÊNCIAS
  python transform_docx.py bruto.docx saida.docx --identidade --escritorio <id>  # outro escritório
  (`--fragmento` é aceito e é o padrão. Flag desconhecida é recusada, exit 1.)

MINUTA COM PENDÊNCIAS (`--minuta-pendencias`), só por ordem do advogado: a faixa constante
entra no topo do corpo, depois da conferência de preservação (que mede só o conteúdo do
advogado), e o carimbo `DSRMinutaPendencias` vai para o pacote; sem a marca gravada o arquivo
é apagado e sai 2. Combina com os três modos de identidade.

O passo universal NÃO cria banners, legendas nem caixas: isso exige leitura da peça. Para
converter elementos, o agente escreve um driver curto com a API de âncoras do core (ver
references/transformer-driver.md) e o passa em `transform(..., driver=fn)`, entre o unpack e o pack, ou roda este CLI
e depois reabre o resultado com o driver.

Proteções invioláveis:
  1. Parágrafos com <w:numPr> não são tocados.
  2. Drawings nunca são removidos (screenshots de prova têm descr="conteúdo gerado").
  3. Validação obrigatória ao final.
Saída: 0 gerado · 1 uso · 2 OOXML inválido · 3 drawing perdido · 6 escritório da peça final não
escolhido, desconhecido ou removido (quem atua por vários: `escritorio_do_caso.py`) · 9 minuta de peça com tese
jurídica sem a escolha do advogado ou, no método completo, com etapa por fazer (`escolha_do_metodo.py`).
"""
import html
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
import vocabulario_interno
try:
    import escolha_do_metodo
except Exception:
    escolha_do_metodo = None



EXIT_FALTA_ESCOLHA_OU_ETAPA = 9


FLAGS_CONHECIDAS = ("--identidade", "--manter-identidade", "--fragmento", "--minuta-pendencias",
                    "--escritorio")


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



PENDENCIA_ESCRITORIO = ("falta escolher por qual escritório esta peça sai: o documento saiu sem "
                        "cabeçalho e rodapé")
PENDENCIA_PADRAO_INCOMPLETO = ("faltam dados do escritório para o papel padrão (nome, endereço e "
                               "cidade): o documento saiu sem cabeçalho e rodapé")


def _perfil_da_peca(escritorio):
    '`(visão do escritório da peça final, erro de escritório ou None)`. Visão None quando não há'



    try:
        import perfil_advogado as _pa
        if not _pa.carregar():
            return None, None
        return _pa.exigir(escritorio=escritorio), None
    except Exception as erro:
        if str(erro).startswith("ESCRITÓRIO"):
            return None, erro
        return None, None


def _perfil_do_fragmento(escritorio):
    'Perfil do corpo no fragmento e no `--manter-identidade`, sem recusar: o escritório que'


    try:
        import perfil_advogado as _pa
        import escritorio_do_caso
        perfil = _pa.carregar()
        visao, _eid = escritorio_do_caso.visao_sem_recusa(perfil, explicito=escritorio, modulo=_pa)
    except Exception:
        return None
    return None if visao is perfil else visao


def transform(src_docx, out_docx, identidade="fragmento", driver=None, minuta_pendencias=False,
              escritorio=None):
    perfil_peca, pend_escritorio = None, []
    if identidade == "final":
        perfil_peca, erro_escritorio = _perfil_da_peca(escritorio)
        if erro_escritorio is not None:

            if not minuta_pendencias or str(erro_escritorio).startswith(
                    ("ESCRITÓRIO DESCONHECIDO", "ESCRITÓRIO DIFERENTE")):
                print(f"ERRO: {erro_escritorio}")
                print("Nada foi gerado.")
                sys.exit(6)
            incompleto = str(erro_escritorio).startswith("ESCRITÓRIO SEM DADOS DO PAPEL PADRÃO")
            print("AVISO: sai sem o papel do escritório ("
                  + ("faltam dados do escritório para o papel padrão" if incompleto
                     else "falta escolher por qual escritório a peça sai")
                  + "); a minuta segue sem cabeçalho e rodapé.")
            print(f"  detalhe para o assistente: {erro_escritorio}")
            identidade = "fragmento"
            pend_escritorio.append(PENDENCIA_PADRAO_INCOMPLETO if incompleto else PENDENCIA_ESCRITORIO)
    if identidade != "final":
        perfil_peca = _perfil_do_fragmento(escritorio)
    work = core.dir_de_trabalho("dsrvl_tf_")
    try:
        core.unpack(src_docx, work)
        core.LINKS_EXTERNOS.clear()


        doc_path = os.path.join(work, "word", "document.xml")
        with open(doc_path, encoding="utf-8") as f:
            before = f.read()
        texts_before = [core.straight_quotes(t) for t in
                        re.findall(r"<w:t[^>]*>([^<]*)</w:t>", before)]
        n_drawings_before = before.count("<w:drawing")

        pend_pesquisa = []
        if minuta_pendencias and escolha_do_metodo is not None:



            _paras = [html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)))
                      for p in re.findall(r"<w:p[ >].*?</w:p>", before, re.S)]
            pend_pesquisa, _parada = escolha_do_metodo.exigir_para_minuta(
                "\n".join(_paras), os.path.dirname(os.path.abspath(src_docx)))
            if _parada:



                import build_docx
                build_docx.parar_por_parada(_parada, EXIT_FALTA_ESCOLHA_OU_ETAPA, out_docx)

        core.universal_pass(work, identidade=identidade, perfil=perfil_peca)

        if driver:
            with open(doc_path, encoding="utf-8") as f:
                doc = f.read()
            doc = driver(doc)
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write(doc)

        realcados_enc, realcados_marc = [], []
        if minuta_pendencias:




            with open(doc_path, encoding="utf-8") as f:
                doc = f.read()
            doc, realcados_enc = core.realcar_trechos_no_xml(doc, _spans_de_residuo)
            doc, realcados_marc = core.realcar_trechos_no_xml(
                doc, lambda t: [m.span() for m in core.RX_MARCADOR_PENDENCIA.finditer(t)])
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write(doc)


        with open(doc_path, encoding="utf-8") as f:
            after = f.read()
        joined_before = "".join(texts_before)
        joined_after = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", after))
        same = html.unescape(joined_before).replace(" ", "") == \
               html.unescape(joined_after).replace(" ", "")
        n_drawings_after = after.count("<w:drawing")
        print(f"Preservação: texto={'100%' if same else 'DIVERGÊNCIA — conferir!'} | "
              f"drawings {n_drawings_before}→{n_drawings_after}")
        if n_drawings_after < n_drawings_before:
            print("ERRO: drawings perdidos — abortando.")
            sys.exit(3)

        if minuta_pendencias:


            with open(doc_path, encoding="utf-8") as f:
                doc = f.read()
            doc = core.inserir_faixa_no_corpo(doc)
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write(doc)

        core.injetar_links(work)





        if identidade == "final":


            _perfil_tf = perfil_peca
            if _perfil_tf is None:
                try:
                    import perfil_advogado as _pa
                    _perfil_tf = _pa.carregar()
                except Exception:
                    _perfil_tf = None
            carimbo_timbrado.carimbar_do_perfil(work, _perfil_tf)
        if minuta_pendencias:
            carimbo_timbrado.carimbar_minuta_pendencias(work)

        core.pack(work, out_docx)
        errs = core.validate_docx(out_docx)
        if errs:
            print("ERROS DE VALIDAÇÃO:")
            for e in errs:
                print(" -", e)
            sys.exit(2)
        _recusar_texto_oculto(out_docx)
        if minuta_pendencias:
            try:
                import varredura_documento
                marcado = varredura_documento.tem_marca_de_pendencias(out_docx)
            except Exception:
                marcado = False
            if not marcado:
                try:
                    os.remove(out_docx)
                except OSError:
                    pass
                print("ERRO: a marca de MINUTA COM PENDÊNCIAS não ficou gravada no documento; "
                      "nada foi gerado. Gere de novo.")
                sys.exit(2)
            if core.indice_da_faixa(out_docx) != 0:


                try:
                    os.remove(out_docx)
                except OSError:
                    pass
                print("ERRO: a faixa de MINUTA COM PENDÊNCIAS não ficou no primeiro parágrafo "
                      "do corpo; nada foi gerado.")
                sys.exit(2)
        print(f"OK → {out_docx}")
        if minuta_pendencias:
            print("MINUTA COM PENDÊNCIAS: faixa no corpo e marca gravadas. Não é a peça "
                  "liberada: não passou pela revisão completa e não se protocola como está.")
            _imprimir_pendencias(realcados_enc, realcados_marc, pend_escritorio)
            for _frase in pend_pesquisa:
                print(f"  · {_frase}")
        return same
    finally:


        shutil.rmtree(work, ignore_errors=True)


def _spans_de_residuo(texto):
    '(início, fim) de cada ocorrência, no texto do parágrafo, de um termo que'

    spans = []
    for r in vocabulario_interno.residuos(texto):
        termo = r["termo"]
        ini = texto.find(termo)
        while termo and ini >= 0:
            spans.append((ini, ini + len(termo)))
            ini = texto.find(termo, ini + len(termo))
    return spans


def _resumo(trechos, limite=90):
    vistos = []
    for t in trechos:
        t = t if len(t) <= limite else t[:limite - 4] + "..."
        if t not in vistos:
            vistos.append(t)
    return vistos


def _imprimir_pendencias(encanamento, marcadores, frases=()):
    'As pendências do transformer no formato do builder: a linha «·» vai ao advogado, em'


    if not (encanamento or marcadores or frases):
        print("Pendências apontadas pelo transformador: nenhuma; as da revisão continuam.")
        return
    print("Pendências apontadas pelo transformador:")
    for frase in frases:
        print(f"  · {frase}")
    if marcadores:
        print(f"  · {len(marcadores)} trecho(s) marcado(s) para conferência, realçado(s) no "
              "documento: " + "; ".join(_resumo(marcadores)))
    if encanamento:
        print(f"  · {len(encanamento)} trecho(s) com termo técnico do sistema, realçado(s) no "
              "documento; precisam sair do texto antes de o documento ir a qualquer pessoa")
        print("      detalhe para o assistente (não repassar): nome de script, de campo ou de "
              "fase não vai ao documento, nem na MINUTA COM PENDÊNCIAS (L16): "
              + ", ".join(f"«{t}»" for t in _resumo(encanamento)[:15])
              + ". ANTES DE ENTREGAR, tire esses trechos do original (reescreva em português "
              "de advogado) e rode o transformador de novo; ele não apaga texto do advogado.")


if __name__ == "__main__":
    brutos, esc = list(sys.argv[1:]), None
    if "--escritorio" in brutos:
        _i = brutos.index("--escritorio")
        if _i + 1 >= len(brutos) or brutos[_i + 1].startswith("--"):
            print("ERRO: --escritorio pede o id do escritório (principal ou esc-xxxxxx). "
                  "Nada foi gerado.")
            sys.exit(1)
        esc = brutos[_i + 1]
        del brutos[_i:_i + 2]
    args = [a for a in brutos if not a.startswith("--")]
    flags = {a for a in brutos if a.startswith("--")} | ({"--escritorio"} if esc else set())
    desconhecidas = sorted(flags - set(FLAGS_CONHECIDAS))
    if desconhecidas:
        print(f"ERRO: flag desconhecida: {', '.join(desconhecidas)}. Aceitas: "
              f"{', '.join(FLAGS_CONHECIDAS)}. Nada foi gerado.")
        sys.exit(1)
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    mode = "fragmento"
    if "--identidade" in flags:
        mode = "final"
    if "--manter-identidade" in flags:
        mode = "manter"
    transform(args[0], args[1], identidade=mode,
              minuta_pendencias="--minuta-pendencias" in flags, escritorio=esc)
