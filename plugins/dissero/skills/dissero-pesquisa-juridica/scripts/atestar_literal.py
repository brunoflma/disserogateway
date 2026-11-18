#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'atestar_literal.py — liga o teor do dataset ao DOCUMENTO do tribunal, com hash.'
































































from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

from urllib.parse import urlparse

import estrategia_precedentes as ep
import procedencia_literal as pl
from achado_contract import FONTES_PADRAO, carregar_json, texto, validar_documento
from verificar_citacao import _norm, confere_numero, confere_relator

try:
    import anatomia_acordao as anat
except ImportError:
    anat = None
ANATOMIA_INDISPONIVEL = "ANATOMIA_DO_ACORDAO_INDISPONIVEL"
ANATOMIA_FALHOU = "ANATOMIA_DO_ACORDAO_FALHOU"


def _aviso_anatomia(achado, texto_doc):
    'Aviso da anatomia para um achado; a falha do módulo vira aviso nomeado, nunca derruba a'

    if anat is None:
        return None
    try:
        return anat.aviso_do_achado(achado, texto_doc)
    except Exception as e:
        return {"codigo": ANATOMIA_FALHOU, "nivel": "aviso", "id": achado.get("id"),
                "mensagem": f"a anatomia do acórdão não pôde ser lida ({e}); confira o "
                            f"dispositivo à mão"}

AQUI = os.path.dirname(os.path.abspath(__file__))


VERSOES_ACEITAS = ("dsr.achados.v2", "dsr.achados.v3")


EXIT_OK = 0
EXIT_DIVERGENCIA = 1
EXIT_USO = 2
EXIT_GRAVOU_PARCIAL = 3


SEM_ENDERECO_OFICIAL = "SEM_ENDERECO_OFICIAL"


ATESTACAO_RECUSADA = "ATESTACAO_RECUSADA"

URL_OFICIAL_SEM_ACHADO = "URL_OFICIAL_SEM_ACHADO"
REMEDIO_ENDERECO = ("informe o endereço do documento no portal do tribunal com "
                    "--url-oficial {id}=https://<endereço oficial> e rode de novo")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

RX_CNJ = re.compile(r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}")


REMEDIO_POPPLER = ("Instale o poppler (Windows: `winget install oschwartz10612.Poppler`; "
                   "Debian/Ubuntu: `apt install poppler-utils`; macOS: `brew install poppler`) "
                   "e deixe o `pdftotext` no PATH, ou informe o binário por --pdftotext.")


def _pdftotext(informado=None):
    """Caminho do `pdftotext`: o informado, ou o do PATH. Nunca um caminho de máquina."""
    return shutil.which(informado or "pdftotext")


def extrair(caminho, pdftotext=None):
    'Texto do documento. PDF pelo poppler; .txt/.md lidos direto.'





    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".txt", ".md"):
        raw = open(caminho, "rb").read()
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return ""
    if ext != ".pdf":
        raise ValueError(f"tipo não suportado para conferência literal: {ext}")
    exe = _pdftotext(pdftotext)
    if not exe:
        onde = f"em {pdftotext}" if pdftotext else "no PATH"
        raise RuntimeError(
            f"pdftotext (poppler) não encontrado {onde} — sem extrator não há conferência "
            f"literal, e conferir de olho é o que este script existe para substituir. "
            f"{REMEDIO_POPPLER}")
    saida = caminho + ".conferencia.txt"
    r = subprocess.run([exe, "-layout", caminho, saida], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or not os.path.isfile(saida):
        raise RuntimeError(f"extração falhou: {(r.stderr or '').strip()[:200]}")
    raw = open(saida, "rb").read()
    os.remove(saida)
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def _casar_por_cnj(achados, pasta):
    """{id do achado: caminho do PDF} pelo número do processo no NOME do arquivo."""
    porq = {}
    for nome in os.listdir(pasta):
        if not nome.lower().endswith((".pdf", ".txt", ".md")):
            continue
        for m in RX_CNJ.finditer(nome):
            porq[re.sub(r"\D", "", m.group(0))] = os.path.join(pasta, nome)
    saida = {}
    for a in achados:
        if not isinstance(a, dict):
            continue
        ref = texto(a.get("reference")) + " " + texto((a.get("citation") or {}).get("case_number"))
        for m in RX_CNJ.finditer(ref):
            alvo = porq.get(re.sub(r"\D", "", m.group(0)))
            if alvo:
                saida[texto(a.get("id"))] = alvo
                break
    return saida


def _numero_de(achado):
    c = achado.get("citation") or {}
    return texto(c.get("case_number")) or texto(c.get("identifier"))


def faltas_de_identidade(achado, extraido):
    'O que da MOLDURA não aparece no documento: o número sempre; o relator, quando o registro'

    numero = _numero_de(achado)
    faltas = []
    if not numero or not confere_numero(numero, extraido):
        faltas.append(f"o número {numero or '(não registrado)'}")
    relator = texto((achado.get("citation") or {}).get("rapporteur"))
    if relator and confere_relator(relator, _norm(extraido)) is False:
        faltas.append(f"o relator {relator}")
    return faltas


def _casar_por_conteudo(achados, documentos, textos):
    '({id: documento}, [ids com trecho achado em documento de outro número]).'



    mapa, sem_numero_no_doc = {}, []
    for a in achados:
        ident, literal, numero = texto(a.get("id")), texto(a.get("syllabus_literal")), _numero_de(a)
        if not literal or a.get("use_status") == "prohibited":
            continue
        docs = [d for d in documentos if d in textos]
        por_numero = [d for d in docs if numero and confere_numero(numero, textos[d])]
        if por_numero:
            mapa[ident] = por_numero[0]
            continue
        com_trecho = [d for d in docs if pl.nivel(literal, textos[d]) == "verbatim"]
        if com_trecho and not numero:
            mapa[ident] = com_trecho[0]
        elif com_trecho:
            sem_numero_no_doc.append((ident, com_trecho[0], numero))
    return mapa, sem_numero_no_doc


def atestar(achado, documento, ts=None, pdftotext=None, extraido=None):
    """(ok, registro, motivo) para UM achado contra UM documento."""
    literal = texto(achado.get("syllabus_literal"))
    if not literal:
        return False, None, "achado sem `syllabus_literal` — não há teor a conferir"
    if extraido is None:
        extraido = extrair(documento, pdftotext)
    if not extraido.strip():
        return False, None, (f"o documento não devolveu texto ({os.path.basename(documento)}) "
                             f"— PDF só-imagem não serve para conferência literal: obtenha a "
                             f"versão pesquisável ou copie o trecho da tela")
    reg = pl.registrar(literal, extraido, origem=os.path.abspath(documento), em=ts)
    if reg["nivel"] == "verbatim":
        return True, reg, "verbatim"
    if reg["nivel"] == "normalizado":
        return False, reg, ("o teor só confere DEPOIS de apagar acento e pontuação — logo, "
                            "acento ou pontuação foram ALTERADOS em relação ao original. "
                            + str(reg.get("divergencia") or ""))
    return False, reg, ("o teor NÃO foi localizado no documento. " +
                        str(reg.get("divergencia") or ""))


def endereco_oficial(url, fontes, exigir_teor=False):
    '(ok, motivo) do endereço como ENDEREÇO OFICIAL de atestação.'







    url = texto(url)
    if not url:
        return False, "nenhum endereço registrado"
    partes = urlparse(url)
    if partes.scheme != "https":
        return False, f"o endereço não usa HTTPS ({url})"
    host = (partes.hostname or "").lower()
    hosts = (fontes or {}).get("hosts") or {}
    meta = hosts.get(host) or {}
    if "confirmacao_teor" in (meta.get("travas_locais") or []):
        return False, (f"{host} serve metadado ou índice (DataJud/LexML), não o documento do "
                       f"tribunal")
    no_catalogo = host in hosts
    sufixo = any(host.endswith(s) for s in (fontes or {}).get("sufixos_oficiais") or [])
    if no_catalogo and exigir_teor and "confirmacao_teor" not in (meta.get("capacidades") or []):
        return False, (f"o catálogo de fontes oficiais diz que {host} não serve o teor do "
                       f"julgado (índice ou banco de precedentes, não o documento do tribunal)")
    if no_catalogo or sufixo:
        return True, ""
    return False, f"{host} não é host oficial (agregador ou serviço de pesquisa)"


def escolher_endereco(achado, informadas, fontes):
    "(url, origem, motivo). origem: 'informada' | 'registro' | 'descoberta'; url '' = nenhum"

    ident = texto(achado.get("id"))
    if ident in informadas:
        ok, motivo = endereco_oficial(informadas[ident], fontes)
        return (informadas[ident], "informada", "") if ok else ("", "", f"--url-oficial: {motivo}")
    tentativas = []
    ok, motivo = endereco_oficial(achado.get("official_url"), fontes)
    if ok:
        return texto(achado.get("official_url")), "registro", ""
    tentativas.append(f"endereço oficial do registro: {motivo}")
    descoberta = texto((achado.get("discovery") or {}).get("url"))
    ok, motivo = endereco_oficial(descoberta, fontes, exigir_teor=True)
    if ok:
        return descoberta, "descoberta", ""
    tentativas.append(f"endereço da descoberta: {motivo}")
    return "", "", "; ".join(tentativas)


def violacoes_do_teor(dados, fontes_path):
    'Núcleo de TEOR do contrato (schema v2 + regras cruzadas), que bloqueia a gravação. No v3'

    base = ep.para_validacao_v2(dados) if dados.get("schema_version") == ep.VERSAO_V3 else dados
    return validar_documento(base, fontes_path=fontes_path)


def _o_que_fazer_estrategia(pendencia):
    if "pesquisa contrária" in pendencia or "pesquisa_contraria" in pendencia:
        return ("faça a busca de precedente CONTRÁRIO à tese (skill de pesquisa jurídica, com os "
                "termos da tese adversa) e registre no achados.json, em estrategia."
                "pesquisa_contraria, o estado (concluida_sem_achado ou concluida_com_achado), as "
                "consultas feitas (fonte, termos, data) e os IDs dos contrários achados; depois "
                "revise a cobertura_precedente com as datas e relinte. Até lá o linter acusa L25")
    if "cobertura" in pendencia:
        return ("revise a cobertura_precedente da estratégia (com cobertura_revisada_em e "
                "cobertura_valida_ate) conforme a seção «§1. Estratégia» do contrato-achados.md")
    return ("corrija a estratégia do registro conforme a seção «§1. Estratégia» do "
            "contrato-achados.md")


def pendencias_de_estrategia(dados):
    """Pendências de ESTRATÉGIA do v3, com o que fazer. Não bloqueiam a gravação do teor."""
    if dados.get("schema_version") != ep.VERSAO_V3:
        return []
    return [{"pendencia": p, "o_que_fazer": _o_que_fazer_estrategia(p)}
            for p in dict.fromkeys(ep.validar_v3(dados))]


NIVEIS_PESQUISA_TENTADA = 4


def _registro_que_lacra(saida):
    '(pasta, arquivo registrado) do PESQUISA_TENTADA.json que lacrou `saida`, procurando na'

    alvo_saida = os.path.normcase(os.path.abspath(saida))
    pasta = os.path.dirname(os.path.abspath(saida))
    for _ in range(NIVEIS_PESQUISA_TENTADA):
        try:
            with open(os.path.join(pasta, "PESQUISA_TENTADA.json"), encoding="utf-8") as fh:
                reg = json.load(fh)
        except (OSError, ValueError):
            reg = None
        arq = texto((((reg if isinstance(reg, dict) else {}).get("achados")) or {}).get("arquivo"))
        if arq:
            alvo = arq if os.path.isabs(arq) else os.path.join(pasta, arq)
            if os.path.normcase(os.path.abspath(alvo)) == alvo_saida:
                return pasta, arq
        mae = os.path.dirname(pasta)
        if mae == pasta:
            break
        pasta = mae
    return None, None


def aviso_pesquisa_tentada(saida):
    'Aviso quando a gravação caiu sobre o arquivo de achados que o registro de pesquisa'

    pasta, arq = _registro_que_lacra(saida)
    if not pasta:
        return None
    script = os.path.join(AQUI, "pesquisa_tentada.py")
    comando = f'python "{script}" registrar --pasta "{pasta}" --achados "{arq}"'
    return {"arquivo": os.path.abspath(saida), "comando": comando,
            "mensagem": ("o registro da pesquisa (PESQUISA_TENTADA.json) lacrou o arquivo de "
                         "achados pelo hash e ficou INVÁLIDO com esta gravação: registre a "
                         "pesquisa de novo antes de gerar ou entregar a peça")}


def _ler_urls_informadas(itens):
    """{id: url} de `--url-oficial ID=URL`; levanta ValueError no item mal formado."""
    saida = {}
    for item in itens or []:
        ident, sep, url = str(item).partition("=")
        if not sep or not ident.strip() or not url.strip():
            raise ValueError(f"--url-oficial espera ID=URL (recebido: {item})")
        saida[ident.strip()] = url.strip()
    return saida


def _veredito(out, gravou, parcial, atestando):
    conf = len(out.get("confirmados") or [])
    pend = len(out.get("pendentes_endereco") or [])
    div = len(out.get("divergentes") or [])
    contagem = (f"{conf} confirmado(s) · {pend} pendente(s) por endereço oficial · "
                f"{div} divergente(s)")
    if not gravou:
        motivo = "contrato do teor violado" if out.get("violacoes") else "divergência"
        return f"NADA GRAVADO ({motivo}): {contagem}"
    if not atestando:
        return (f"PROCEDÊNCIA GRAVADA: {len(out.get('atestados') or [])} achado(s) com teor "
                f"verbatim · {div} divergente(s)")
    return ("ATESTAÇÃO PARCIAL GRAVADA: " if parcial else "ATESTAÇÃO GRAVADA: ") + contagem


def _imprimir(out, primeira, extras=()):
    print(primeira)
    for linha in extras:
        print(linha)
    print(json.dumps(out, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(
        description="Liga o teor do dataset ao documento do tribunal, com hash")
    ap.add_argument("arquivo", help="achados.json (contrato dsr.achados.v2 ou v3)")
    ap.add_argument("--id", help="atestar UM achado")
    ap.add_argument("--documento", help="PDF/TXT do acórdão (com --id)")
    ap.add_argument("--todos", action="store_true", help="atestar todos, casando por CNJ")
    ap.add_argument("--pasta", help="pasta de documentos (com --todos)")
    ap.add_argument("--documentos", nargs="+",
                    help="PDFs soltos na conversa, casados pelo número no conteúdo")
    ap.add_argument("--atestar", action="store_true",
                    help="registra a conferência do pendente que bateu em número e trecho")
    ap.add_argument("--ator", help="quem atesta (padrão: o nome do perfil)")
    ap.add_argument("--data", help="data da atestação (padrão: hoje)")
    ap.add_argument("--fontes", default=FONTES_PADRAO)
    ap.add_argument("--ts", help="timestamp do chamador")
    ap.add_argument("--pdftotext", help="caminho do binário pdftotext (padrão: PATH)")
    ap.add_argument("--url-oficial", action="append", default=[], metavar="ID=URL",
                    help="endereço oficial do documento do achado ID (repetível)")
    ap.add_argument("--manter-v2", action="store_true",
                    help="não migra registro v2 para v3")
    ap.add_argument("-o", "--saida", required=True)
    a = ap.parse_args()

    def recusa_uso(erro):
        _imprimir({"ok": False, "erro": erro}, f"RECUSADO: {erro}")
        return EXIT_USO

    try:
        informadas = _ler_urls_informadas(a.url_oficial)
    except ValueError as e:
        return recusa_uso(str(e))
    try:
        dados = carregar_json(a.arquivo)
    except Exception as e:
        return recusa_uso(str(e))
    if not isinstance(dados, dict) or dados.get("schema_version") not in VERSOES_ACEITAS:
        return recusa_uso("contrato dsr.achados.v2 ou v3 obrigatório")
    migrado = None
    if dados.get("schema_version") == ep.VERSAO_V2 and not a.manter_v2:
        try:
            dados = ep.migrar_v2(dados)
        except ValueError as e:
            return recusa_uso(f"a migração para v3 falhou: {e}")
        migrado = {"de": ep.VERSAO_V2, "para": ep.VERSAO_V3,
                   "aviso": ("registro migrado para v3 no estado mais restritivo (pesquisa "
                             "contrária não iniciada, cobertura inexistente): o linter acusa L25 "
                             "até a pesquisa de precedente contrário ser registrada")}
        if ep.validar_v3(dados):



            migrado["lint_apos_migracao"] = "reprova"
            migrado["aviso"] = (
                "registro migrado para v3 no estado mais restritivo (pesquisa contrária não "
                "iniciada, cobertura inexistente). ATENÇÃO: a partir de agora o linter REPROVA a "
                "peça (L25 ESTRATÉGIA, erro, não mais pendência) até a pesquisa de precedente "
                "contrário ser concluída e a cobertura revisada; em v2 era só pendência e a peça "
                "saía como minuta. Para atestar o teor sem piorar o veredito enquanto a pesquisa "
                "contrária não é feita, rode de novo com --manter-v2")
        else:
            migrado["lint_apos_migracao"] = "sem_erro_de_estrategia"

    achados = [x for x in (dados.get("achados") or []) if isinstance(x, dict)]
    try:
        fontes = carregar_json(a.fontes)
    except Exception:
        fontes = {}

    ator = data = ""
    if a.atestar:
        import registrar_confirmacao_manual as rcm
        ator = texto(a.ator) or rcm.ator_do_perfil()
        data = texto(a.data) or rcm.hoje()
        if not ator:
            return recusa_uso("--atestar precisa de quem atesta: o nome vem do perfil do "
                              "advogado (advogado.nome), que não está configurado nesta "
                              "máquina; configure o perfil ou passe --ator")

    textos, ilegiveis, identidade = {}, [], []
    if a.documentos:
        for doc in a.documentos:
            try:
                textos[doc] = extrair(doc, a.pdftotext)
            except Exception as e:
                ilegiveis.append({"documento": os.path.basename(doc), "motivo": str(e)})
                continue
            if not textos[doc].strip():
                del textos[doc]
                ilegiveis.append({"documento": os.path.basename(doc), "motivo":
                                  "o documento não devolveu texto (PDF só-imagem): obtenha a "
                                  "versão pesquisável ou responda pela lista"})
        mapa, sem_numero = _casar_por_conteudo(achados, a.documentos, textos)
        identidade = [{"id": i, "documento": os.path.basename(d),
                       "motivo": f"o trecho está no documento, mas o número {n} não aparece "
                                 f"nele: confira se é o acórdão certo"}
                      for i, d, n in sem_numero]
    elif a.todos:
        if not a.pasta or not os.path.isdir(a.pasta):
            return recusa_uso("--todos exige --pasta válida")
        mapa = _casar_por_cnj(achados, a.pasta)
    else:
        if not a.id or not a.documento:
            return recusa_uso("informe --id e --documento, ou --todos")
        mapa = {a.id: a.documento}

    atestados, divergentes, sem_documento, confirmados = [], [], [], []
    pendentes_endereco, usadas, avisos_anatomia = [], set(), []
    for achado in achados:
        ident = texto(achado.get("id"))
        doc = mapa.get(ident)
        if not doc:
            if texto(achado.get("syllabus_literal")):
                sem_documento.append(ident)
            continue
        try:
            if doc not in textos:
                textos[doc] = extrair(doc, a.pdftotext)
            ok, reg, motivo = atestar(achado, doc, a.ts, a.pdftotext, textos[doc])
        except Exception as e:
            divergentes.append({"id": ident, "motivo": f"falha ao extrair: {e}"}); continue
        if not ok:
            divergentes.append({"id": ident, "motivo": motivo,
                                "documento": os.path.basename(doc)})
            continue
        regs = [r for r in (achado.get("procedencia_literal") or [])
                if isinstance(r, dict) and r.get("campo") != "syllabus_literal"]
        achado["procedencia_literal"] = regs + [reg]
        atestados.append(ident)
        aviso_anat = _aviso_anatomia(achado, textos[doc])
        if aviso_anat:
            avisos_anatomia.append(aviso_anat)
        if a.atestar and achado.get("use_status") == "pending":
            faltas = faltas_de_identidade(achado, textos[doc])
            if faltas:
                divergentes.append({"id": ident, "documento": os.path.basename(doc),
                                    "motivo": f"o trecho confere, mas {' e '.join(faltas)} não "
                                              f"aparece(m) no documento: confira se é o "
                                              f"acórdão certo"})
                continue


            usadas.add(ident)
            url, origem, motivo_url = escolher_endereco(achado, informadas, fontes)
            if not url:
                pendentes_endereco.append({
                    "id": ident, "codigo": SEM_ENDERECO_OFICIAL,
                    "documento": os.path.basename(doc),
                    "motivo": f"teor conferido verbatim, mas sem endereço oficial: {motivo_url}",
                    "o_que_fazer": REMEDIO_ENDERECO.format(id=ident)})
                continue
            declaracao = (f"PDF do inteiro teor obtido pelo advogado na fonte oficial "
                          f"({os.path.basename(doc)}); a máquina localizou no documento o "
                          f"número e o relator registrados e conferiu o trecho verbatim.")
            sinais = {"documento_conferido_por_maquina": True,
                      "documento_sha256_extracao": reg.get("sha256_extracao")}
            if origem in ("descoberta", "informada"):
                sinais["official_url_origem"] = origem
            ok_at, erro = rcm._atestar(achado, ator, data, url, declaracao, sinais)
            if ok_at:
                confirmados.append(ident)
            else:
                pendentes_endereco.append({
                    "id": ident, "codigo": ATESTACAO_RECUSADA,
                    "documento": os.path.basename(doc),
                    "motivo": f"o registro da atestação foi recusado: {erro}",
                    "o_que_fazer": ("corrija o que o erro aponta no achado e rode de novo; se o "
                                    "erro for do endereço, " + REMEDIO_ENDERECO.format(id=ident))})

    divergentes += identidade
    violacoes = violacoes_do_teor(dados, a.fontes) if confirmados else []
    out = {"ok": not divergentes and not violacoes, "atestados": atestados,
           "divergentes": divergentes, "sem_documento": sem_documento}
    if a.atestar:
        out.update({"confirmados": confirmados, "pendentes_endereco": pendentes_endereco,
                    "ator": ator, "data": data})
        sem_achado = [{"id": i, "url": u, "codigo": URL_OFICIAL_SEM_ACHADO,
                       "motivo": ("nenhum achado com este ID foi atestado nesta rodada (ID "
                                  "inexistente, sem documento casado ou já liberado): confira "
                                  "o ID no achados.json")}
                      for i, u in informadas.items() if i not in usadas]
        if sem_achado:
            out["urls_oficiais_sem_achado"] = sem_achado
    if a.documentos:
        usados = set(mapa.values())
        out["sem_correspondencia"] = [os.path.basename(d) for d in a.documentos
                                      if d in textos and d not in usados]
        out["ilegiveis"] = ilegiveis
    if violacoes:
        out["violacoes"] = violacoes
        out["codigo"] = "CONTRATO_DO_TEOR_VIOLADO"
        out["resumo"] = "a atestação violaria o contrato do dataset — nada foi gravado"
        _imprimir(out, _veredito(out, False, False, a.atestar)); return EXIT_DIVERGENCIA
    if divergentes:


        out["codigo"] = "DIVERGENCIA_DE_TEOR"
        out["resumo"] = (f"{len(divergentes)} divergência(s) — nada foi gravado. Cada uma é "
                         f"teor que NÃO corresponde ao documento do tribunal: corrija o "
                         f"`syllabus_literal` copiando do documento, sem adaptar nada")
        _imprimir(out, _veredito(out, False, False, a.atestar)); return EXIT_DIVERGENCIA
    with open(a.saida, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    out["saida"] = a.saida
    out["schema_version"] = dados.get("schema_version")
    extras = []
    if migrado:
        out["migrado"] = migrado
        extras.append(f"MIGRADO: {migrado['aviso']}")
    elif a.manter_v2 and dados.get("schema_version") == ep.VERSAO_V2:
        extras.append("MANTIDO EM v2 (--manter-v2): o linter segue pedindo a migração para v3 "
                      "(L25) antes do protocolo")
    pend_estr = pendencias_de_estrategia(dados)
    if pend_estr:
        out["pendencias_estrategia"] = pend_estr
        extras += [f"PENDÊNCIA DE ESTRATÉGIA (não bloqueia o teor): {p['pendencia']} — "
                   f"{p['o_que_fazer']}" for p in pend_estr]
    for u in out.get("urls_oficiais_sem_achado") or []:
        extras.append(f"AVISO {u['codigo']} ({u['id']}): {u['motivo']}")
    if avisos_anatomia:
        out["avisos_anatomia"] = avisos_anatomia
    elif anat is None and atestados:
        out["avisos_anatomia"] = [{"codigo": ANATOMIA_INDISPONIVEL, "nivel": "aviso"}]
    for v in out.get("avisos_anatomia") or []:
        extras.append(f"AVISO {v['codigo']} ({v.get('id', '-')}): "
                      f"{v.get('mensagem', 'anatomia do acórdão não conferida nesta cópia')}"
                      + (f" — {v['o_que_fazer']}" if v.get("o_que_fazer") else ""))
    for p in pendentes_endereco:
        extras.append(f"PENDENTE {p['codigo']} ({p['id']}): {p['motivo']} — {p['o_que_fazer']}")
    aviso = aviso_pesquisa_tentada(a.saida)
    if aviso:
        out["pesquisa_tentada"] = aviso
        extras.append(f"PESQUISA_TENTADA INVÁLIDA: {aviso['mensagem']}. Comando: "
                      f"{aviso['comando']}")
    parcial = bool(pendentes_endereco)
    if parcial:
        out["codigo"] = "GRAVOU_PARCIAL"
    out["resumo"] = (f"{len(atestados)} achado(s) com teor conferido VERBATIM contra o "
                     f"documento do tribunal"
                     + (f"; {len(confirmados)} registrado(s) como conferido(s) pelo advogado"
                        if a.atestar else "")
                     + (f"; {len(pendentes_endereco)} pendente(s) por falta de endereço oficial "
                        f"(teor conferido, sem liberação)" if pendentes_endereco else "")
                     + (f"; {len(sem_documento)} sem documento para conferir (seguem sem "
                        f"procedência)" if sem_documento else ""))
    primeira = _veredito(out, True, parcial, a.atestar)
    if migrado and migrado.get("lint_apos_migracao") == "reprova":
        primeira += (" · ATENÇÃO: migrado para v3, o linter passa a REPROVAR a peça (L25) até a "
                     "pesquisa de precedente contrário")
    _imprimir(out, primeira, extras)
    return EXIT_GRAVOU_PARCIAL if parcial else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
