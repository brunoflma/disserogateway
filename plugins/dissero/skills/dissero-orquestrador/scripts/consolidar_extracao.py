#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'consolidar_extracao.py — recebe o que os leitores devolveram e RECONCILIA contra o plano.'





























































import argparse
import json
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(os.path.dirname(AQUI), "references")
SCHEMA_EXTRACAO = os.path.join(REFS, "extracao_caso.schema.json")
NOME_EXTRACAO = "EXTRACAO_CASO.json"

if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass



try:
    import caso_raiz
except Exception:
    caso_raiz = None
try:
    from schema_mini import validar_schema
except Exception:
    validar_schema = None

SCHEMA_VERSION = "dsr.extracao_caso.v1"
TIPOS = ("fato", "data", "valor", "prova", "tese")



CAMPOS_ACHADO = ("tipo", "teor", "pagina", "chave", "detalhe", "estatuto", "fundamento", "plano",
                 "data")


ESTATUTOS = ("alegado", "provado", "incontroverso", "inferencia")
FUNDAMENTOS = ("admissao_expressa", "art341_filtrado_345", "art374",
               "art436_documento_nao_impugnado")
PLANOS = ("material", "processual")
CAMPOS_NOTA = ("nota", "teor", "descricao", "motivo")


class Contrato(Exception):
    """Uso/contrato inválido -> exit 2."""


def _s(x):
    return isinstance(x, str) and bool(x.strip())


def _int(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, str) and x.strip().lstrip("-").isdigit():
        return int(x.strip())
    return None


def _agora():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _saida(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False))
    return code


def _norm(texto):
    'Normalização MÍNIMA para comparar teores: espaço em branco e caixa, nada além.'




    return " ".join(str(texto).split()).casefold()





ACOES_PLANO = ("planejada", "escalar")


def _indexar_plano(plano, escalado_autorizado=False):
    'Indexa as fatias do `dsr.turma_plano.v1` por `fatia_id`, preservando a ordem do plano.'












    if not isinstance(plano, dict):
        raise Contrato(["plano não é objeto JSON"])
    acao = plano.get("acao")
    if acao not in ACOES_PLANO:
        raise Contrato(["plano com `acao` %r fora do enum publicado %s: o contrato "
                        "`dsr.turma_plano.v1` a exige e o valor diz se o leque foi autorizado"
                        % (acao, list(ACOES_PLANO))])
    if acao == "escalar" and not escalado_autorizado:
        raise Contrato(["plano com `acao: escalar`: o planejador já recusou esta turma — %s. "
                        "Replaneje com o aval corrigido, ou consolide com autorização expressa "
                        "(--plano-escalado-autorizado) se o advogado já liberou por outra via"
                        % (plano.get("erro") or "(sem `erro` declarado)")])
    fatias = plano.get("fatias")
    if not isinstance(fatias, list):
        raise Contrato(["plano sem `fatias`: sem o leque planejado não há o que reconciliar"])
    indice, ordem, erros = {}, [], []
    for posicao, fatia in enumerate(fatias):
        rotulo = "fatias[%d]" % posicao
        if not isinstance(fatia, dict):
            erros.append("%s não é objeto JSON" % rotulo)
            continue
        fatia_id = fatia.get("fatia_id")
        if not _s(fatia_id):
            erros.append("%s sem `fatia_id`" % rotulo)
            continue
        if fatia_id in indice:


            erros.append("`fatia_id` duplicado no plano: %s" % fatia_id)
            continue
        if not _s(fatia.get("doc_id")):
            erros.append("%s (%s) sem `doc_id`" % (rotulo, fatia_id))
        if not _s(fatia.get("sha256_arquivo")):
            erros.append("%s (%s) sem `sha256_arquivo`: o achado não teria como apontar o "
                         "documento de origem" % (rotulo, fatia_id))
        indice[fatia_id] = fatia
        ordem.append(fatia_id)
    if erros:
        raise Contrato(erros)
    if not ordem:



        raise Contrato(["plano com zero fatias: leque inexistente não é leque completo — "
                        "reconciliar sobre o conjunto vazio fecha sempre"])
    return indice, ordem


def _cobertura_do_plano(plano):
    'A `cobertura` que o plano DECLARA, conferida como contrato antes de ser usada.'




    cobertura = plano.get("cobertura")
    if not isinstance(cobertura, dict):
        raise Contrato(["plano sem `cobertura` (ou com `cobertura` que não é objeto): sem ela "
                        "o gate de documento fora do leque não existe"])
    listas = {}
    for campo in ("nao_lidos", "sem_paginacao"):
        valor = cobertura.get(campo)
        if valor is None:
            listas[campo] = []
            continue
        if not isinstance(valor, list):
            raise Contrato(["`cobertura.%s` deve ser lista, veio %s"
                            % (campo, type(valor).__name__)])
        for posicao, item in enumerate(valor):
            if not _s(item):
                raise Contrato(["`cobertura.%s[%d]` não é `doc_id`: %r — descartar calado "
                                "sumiria com o documento" % (campo, posicao, item)])
        listas[campo] = [item.strip() for item in valor]
    autorizado = cobertura.get("sem_paginacao_autorizado") is True
    return cobertura, listas["nao_lidos"], listas["sem_paginacao"], autorizado


def _documentos_sem_fatia(nao_lidos, sem_paginacao, sem_paginacao_autorizado=False):
    'Documento do inventário que nunca virou fatia: reprova como fatia sem retorno.'












    saida = list(nao_lidos)
    if sem_paginacao_autorizado:
        return saida
    for doc_id in sem_paginacao:
        if doc_id not in saida:
            saida.append(doc_id)
    return saida


def cobertura_derivada(plano):
    'A cobertura RECALCULADA a partir das `fatias[]` — nunca a que o plano declara.'















    return _uniao_das_fatias(plano.get("fatias") or [], plano)


def _uniao_das_fatias(fatias, plano):
    'A conta de uniao, compartilhada por `cobertura_derivada` e `cobertura_lida`.'



    por_doc = {}
    for fatia in fatias:
        if not isinstance(fatia, dict):
            continue
        ini, fim = _int(fatia.get("pagina_inicial")), _int(fatia.get("pagina_final"))
        if ini is None or fim is None or fim < ini:
            continue
        por_doc.setdefault(str(fatia.get("doc_id") or "(sem doc_id)"), set()).update(
            range(ini, fim + 1))

    faltando, total = [], 0
    for doc_id in sorted(por_doc):
        paginas = por_doc[doc_id]
        total += len(paginas)
        buraco = sorted(set(range(min(paginas), max(paginas) + 1)) - paginas)
        if buraco:
            faltando.append({"doc_id": doc_id, "paginas": buraco[:50],
                             "total_faltando": len(buraco), "tipo": "interior"})

    planejadas = _int((plano.get("cobertura") or {}).get("paginas_planejadas"))
    derivada = {"paginas_cobertas": total, "paginas_planejadas": planejadas,
                "faltando": faltando, "documentos": sorted(por_doc)}
    if planejadas is not None and total < planejadas:
        derivada["faltando"] = faltando + [{
            "doc_id": "(total)", "paginas": [],
            "total_faltando": planejadas - total, "tipo": "borda_ou_documento_inteiro"}]
    derivada["completa"] = not derivada["faltando"]
    return derivada


def cobertura_lida(plano, respondidas):
    'A uniao das paginas que VOLTARAM LIDAS — o invariante de FIDELIDADE.'










    respondidas = set(respondidas or ())
    lidas = [f for f in (plano.get("fatias") or [])
             if isinstance(f, dict) and str(f.get("fatia_id") or "") in respondidas]
    return _uniao_das_fatias(lidas, plano)


def _buracos_declarados(cobertura):
    'As folhas que o PRÓPRIO plano declara fora de fatia, saneadas para o contrato de saída.'




    declarada = {"completa": cobertura.get("completa")
                 if isinstance(cobertura.get("completa"), bool) else None,
                 "faltando": []}
    faltando = cobertura.get("faltando")
    if isinstance(faltando, list):
        for item in faltando:
            if not isinstance(item, dict):
                continue
            paginas = [p for p in (item.get("paginas") or [])
                       if isinstance(p, int) and not isinstance(p, bool)]
            declarada["faltando"].append({
                "doc_id": str(item.get("doc_id") or "(não declarado)"),
                "paginas": paginas,
                "total_faltando": _int(item.get("total_faltando")) or len(paginas)})
    return declarada





def _conferir_retorno(retorno):
    'Devolve a lista de motivos pelos quais este retorno NÃO conta como fatia lida.'



    problemas = []
    if not _s(retorno.get("agente")):
        problemas.append("sem `agente`: achado sem autor não se confere — é a mesma prova de "
                         "identidade que torna o voto do Conselho conferível")
    if "achados" not in retorno:



        problemas.append("retorno sem a chave `achados`: não distingue \"li e não achei nada\" "
                         "de \"não li\" — declare `achados: []` para a fatia estéril")
        return problemas
    achados = retorno.get("achados")
    if not isinstance(achados, list):
        problemas.append("`achados` deve ser lista, veio %s" % type(achados).__name__)
        return problemas
    for posicao, achado in enumerate(achados):
        rotulo = "achados[%d]" % posicao
        if not isinstance(achado, dict):
            problemas.append("%s não é objeto JSON" % rotulo)
            continue
        if achado.get("tipo") not in TIPOS:
            problemas.append("%s: `tipo` fora de %s (veio %r)"
                             % (rotulo, list(TIPOS), achado.get("tipo")))
        if not _s(achado.get("teor")):
            problemas.append("%s: `teor` vazio" % rotulo)
        pagina = _int(achado.get("pagina"))
        if pagina is None or pagina < 1:
            problemas.append("%s: `pagina` ausente ou inválida — sem a folha o L15 do LINT não "
                             "confere a citação contra a página lida" % rotulo)
        problemas.extend(_conferir_estatuto(achado, rotulo))
        if "plano" in achado and achado.get("plano") not in PLANOS:
            problemas.append("%s: `plano` fora de %s (veio %r)"
                             % (rotulo, list(PLANOS), achado.get("plano")))
    return problemas


def _conferir_estatuto(achado, rotulo):
    'Estatuto vale só no fato. Fora do fato, o campo segue preservado em `extras` (ver'



    if achado.get("tipo") != "fato" or "estatuto" not in achado:
        return []
    estatuto = achado.get("estatuto")
    if estatuto not in ESTATUTOS:
        return ["%s: `estatuto` fora de %s (veio %r)" % (rotulo, list(ESTATUTOS), estatuto)]
    if estatuto != "incontroverso":
        return []
    fundamento = achado.get("fundamento")
    if fundamento not in FUNDAMENTOS:
        return ["%s: incontroverso exige `fundamento` em %s (veio %r) — sem ele o fato "
                "continua alegado" % (rotulo, list(FUNDAMENTOS), fundamento)]
    return []


def _fora_da_faixa(retorno, fatia, agente):
    'Achado cuja folha a fatia NÃO cobre — o leitor devolveu página que não lhe foi pedida.'










    inicial = _int(fatia.get("pagina_inicial"))
    final = _int(fatia.get("pagina_final"))
    if inicial is None or final is None:
        return []
    saida = []
    for bruto in retorno.get("achados") or []:
        if not isinstance(bruto, dict):
            continue
        pagina = _int(bruto.get("pagina"))
        if pagina is None or inicial <= pagina <= final:
            continue
        saida.append({"fatia_id": fatia["fatia_id"], "agente": agente, "pagina": pagina,
                      "pagina_inicial": inicial, "pagina_final": final})
    return saida





CAMPOS_ECOADOS = ("sha256_arquivo", "doc_id", "fatia_id")


def _declaracoes_divergentes(bruto, fatia, agente):
    'O que o leitor ECOOU do ofício com valor diferente do que o plano diz.'






    saida = []
    for campo in CAMPOS_ECOADOS:
        declarado = bruto.get(campo)
        if not _s(declarado):
            continue
        do_plano = fatia.get(campo)
        if not _s(do_plano):
            continue
        if declarado.strip().casefold() == do_plano.strip().casefold():
            continue
        saida.append({"fatia_id": fatia["fatia_id"], "agente": agente, "campo": campo,
                      "declarado": declarado.strip(), "do_plano": do_plano.strip()})
    return saida


def _achado(bruto, fatia, agente):
    saida = {"fatia_id": fatia["fatia_id"], "doc_id": fatia["doc_id"],
             "sha256_arquivo": fatia["sha256_arquivo"], "pagina": _int(bruto.get("pagina")),
             "agente": agente, "tipo": bruto.get("tipo"), "teor": bruto["teor"].strip()}
    if _s(bruto.get("chave")):
        saida["chave"] = bruto["chave"].strip()
    if _s(bruto.get("detalhe")):
        saida["detalhe"] = bruto["detalhe"].strip()
    elevados = set(CAMPOS_ACHADO)
    if bruto.get("tipo") == "fato" and bruto.get("estatuto") in ESTATUTOS:
        saida["estatuto"] = bruto["estatuto"]
        if bruto["estatuto"] == "incontroverso":
            saida["fundamento"] = bruto["fundamento"]
        else:
            elevados.discard("fundamento")
    else:

        elevados.discard("estatuto")
        elevados.discard("fundamento")
    if bruto.get("plano") in PLANOS:
        saida["plano"] = bruto["plano"]
    if _s(bruto.get("data")):
        saida["data"] = bruto["data"].strip()
    else:
        elevados.discard("data")
    extras = {campo: valor for campo, valor in bruto.items() if campo not in elevados}
    if extras:
        saida["extras"] = extras
    return saida


def _notas_ilegiveis(retorno, fatia):
    'Recolhe o que o leitor declarou ilegível. Aceita string ou objeto; o que não couber em'


    bruto = retorno.get("ilegiveis")
    if bruto is None:
        bruto = retorno.get("ilegivel")
    if bruto is None:
        return []
    itens = bruto if isinstance(bruto, list) else [bruto]


    agente = retorno.get("agente")
    agente = agente.strip() if _s(agente) else "não declarado"
    saida = []
    for item in itens:
        pagina = None
        if isinstance(item, str):





            nota = item.strip() or ("ilegível declarado sem nota pelo agente %s" % agente)
        elif isinstance(item, dict):
            pagina = _int(item.get("pagina"))
            nota = ""
            for campo in CAMPOS_NOTA:
                if _s(item.get(campo)):
                    nota = item[campo].strip()
                    break
            if not nota:
                nota = json.dumps(item, ensure_ascii=False, sort_keys=True)
        else:
            nota = json.dumps(item, ensure_ascii=False)
        saida.append({"fatia_id": fatia["fatia_id"], "doc_id": fatia["doc_id"],
                      "sha256_arquivo": fatia["sha256_arquivo"], "pagina": pagina,
                      "nota": nota})
    return saida





def _divergencias(achados):
    'Agrupa os achados por `chave` e NOMEIA os que não fecham entre si.'





















    por_chave = {}
    for achado in achados:
        chave = achado.get("chave")
        if not _s(chave):
            continue
        alvo = por_chave.setdefault(_norm(chave), {"grafia": chave, "itens": []})
        alvo["itens"].append(achado)
    saida = []
    for normalizada in sorted(por_chave):
        ocorrencias = por_chave[normalizada]["itens"]
        valores = {}
        for achado in ocorrencias:
            valores.setdefault(_norm(achado["teor"]), achado["teor"])
        if len(valores) < 2:
            continue
        entrada = {


            "chave": por_chave[normalizada]["grafia"],
            "tipos": sorted({achado["tipo"] for achado in ocorrencias}),
            "valores": [valores[k] for k in sorted(valores)],
            "ocorrencias": [{"fatia_id": a["fatia_id"], "doc_id": a["doc_id"],
                             "pagina": a["pagina"], "agente": a["agente"], "teor": a["teor"]}
                            for a in ocorrencias],
        }
        folhas = {(a["doc_id"], a["pagina"]) for a in ocorrencias}
        if len(folhas) == 1:
            entrada["mesma_folha"] = True


            entrada["origem"] = ("sobreposicao_do_plano"
                                 if len({a["fatia_id"] for a in ocorrencias}) > 1
                                 else "mesma_fatia")
        saida.append((bool(folhas and len(folhas) == 1), normalizada, entrada))
    return [entrada for _rotulada, _chave, entrada in sorted(saida, key=lambda t: t[:2])]


def _data_ordenavel(texto):
    '(ano, mês, dia) de AAAA-MM-DD ou DD/MM/AAAA; None para o resto. Só ORDENA: o texto cru'

    if not _s(texto):
        return None
    t = texto.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", t)
    if m:
        return int(m.group(3)), int(m.group(2)), int(m.group(1))
    return None


def _cronologia(achados, divergencias):
    'As duas cronologias, MATERIAL e PROCESSUAL, dos achados que declaram `plano`.'





    divergentes = {_norm(d["chave"]) for d in divergencias}
    listas = {"material": [], "processual": []}
    for posicao, achado in enumerate(achados):
        plano = achado.get("plano")
        if plano not in listas:
            continue
        data = achado.get("data") or (achado["teor"] if achado["tipo"] == "data" else None)
        item = {"fatia_id": achado["fatia_id"], "doc_id": achado["doc_id"],
                "pagina": achado["pagina"], "agente": achado["agente"], "tipo": achado["tipo"],
                "teor": achado["teor"], "data": data}
        if achado.get("chave"):
            item["chave"] = achado["chave"]
            if _norm(achado["chave"]) in divergentes:
                item["divergente"] = True
        if achado.get("estatuto"):
            item["estatuto"] = achado["estatuto"]
        ordem = _data_ordenavel(data)
        chave_ordem = (0, ordem) if ordem else (1, (0, 0, 0))
        listas[plano].append((chave_ordem, achado["doc_id"], achado["pagina"] or 0, posicao, item))
    return {nome: [t[-1] for t in sorted(itens, key=lambda t: t[:4])]
            for nome, itens in listas.items()}





def consolidar(plano, retornos, escalado_autorizado=False):
    'Reconcilia os retornos dos leitores contra o plano da turma.'




    indice, ordem = _indexar_plano(plano, escalado_autorizado=escalado_autorizado)
    cobertura, nao_lidos, sem_paginacao, sem_pag_ok = _cobertura_do_plano(plano)
    if retornos is None:
        retornos = []
    if not isinstance(retornos, list):
        raise Contrato(["`retornos` deve ser lista"])

    achados, ilegiveis = [], []
    respondidas, invalidos, fora_do_plano = [], [], []
    duplicados, fora_da_faixa, declaracoes, sem_achado = [], [], [], []
    for posicao, retorno in enumerate(retornos):
        if not isinstance(retorno, dict):
            invalidos.append({"fatia_id": None, "posicao": posicao,
                              "motivos": ["retorno não é objeto JSON"]})
            continue
        fatia_id = retorno.get("fatia_id")
        if not _s(fatia_id):
            invalidos.append({"fatia_id": None, "posicao": posicao,
                              "motivos": ["retorno sem `fatia_id`: não dá para saber que "
                                          "parte dos autos ele diz ter lido"]})
            continue
        if fatia_id not in indice:


            fora_do_plano.append(fatia_id)
            continue
        fatia = indice[fatia_id]


        ilegiveis.extend(_notas_ilegiveis(retorno, fatia))
        problemas = _conferir_retorno(retorno)
        if problemas:
            invalidos.append({"fatia_id": fatia_id, "posicao": posicao, "motivos": problemas})
            continue
        agente = retorno["agente"].strip()
        if fatia_id in respondidas:






            duplicados.append({"fatia_id": fatia_id, "posicao": posicao, "agente": agente})
            continue
        respondidas.append(fatia_id)
        brutos = retorno.get("achados") or []
        if not brutos:



            sem_achado.append(fatia_id)
        fora_da_faixa.extend(_fora_da_faixa(retorno, fatia, agente))
        for bruto in brutos:
            declaracoes.extend(_declaracoes_divergentes(bruto, fatia, agente))
            achados.append(_achado(bruto, fatia, agente))

    sem_retorno = [fatia_id for fatia_id in ordem if fatia_id not in respondidas]
    sem_fatia = _documentos_sem_fatia(nao_lidos, sem_paginacao, sem_pag_ok)
    declarada = _buracos_declarados(cobertura)
    reconciliacao = {
        "ok": True,
        "fatias_planejadas": len(ordem),
        "fatias_respondidas": len(set(respondidas)),
        "fatias_sem_retorno": sem_retorno,
        "retornos_invalidos": invalidos,
        "retornos_fora_do_plano": fora_do_plano,
        "documentos_sem_fatia": sem_fatia,
        "documentos_sem_paginacao": list(sem_paginacao),
        "fatias_sem_achado": sem_achado,
        "retornos_duplicados": duplicados,
        "achados_fora_da_faixa": fora_da_faixa,
        "declaracoes_divergentes": declaracoes,
        "cobertura_do_plano": declarada,
        "cobertura_derivada": cobertura_derivada(plano),
        "cobertura_lida": cobertura_lida(plano, respondidas),
    }
    if sem_pag_ok and sem_paginacao:
        reconciliacao["sem_paginacao_autorizado"] = True
    if escalado_autorizado and plano.get("acao") == "escalar":



        reconciliacao["plano_escalado_autorizado"] = True
    if reconciliacao["fatias_sem_retorno"]:
        reconciliacao["ok"] = False
    if reconciliacao["retornos_fora_do_plano"]:
        reconciliacao["ok"] = False
    if reconciliacao["documentos_sem_fatia"]:
        reconciliacao["ok"] = False


    if not reconciliacao["cobertura_derivada"]["completa"]:
        reconciliacao["ok"] = False



    if not reconciliacao["cobertura_lida"]["completa"]:
        reconciliacao["ok"] = False

    if declarada["completa"] is False or declarada["faltando"]:
        reconciliacao["ok"] = False

    divergencias = _divergencias(achados)
    return {
        "schema_version": SCHEMA_VERSION,

        "caso": (plano.get("caso") if isinstance(plano.get("caso"), str)
                 and re.fullmatch(r"caso-[0-9a-f]{12}", plano["caso"]) else None),
        "gerado_em": _agora(),
        "achados": achados,
        "reconciliacao": reconciliacao,
        "divergencias": divergencias,
        "ilegiveis": ilegiveis,
        "cronologia": _cronologia(achados, divergencias),
    }


def validar_extracao(extracao):
    """O schema publicado É o contrato. Sem o validador ao lado, o módulo DIZ que está sem ele."""
    if validar_schema is None:
        return ["schema_mini.py indisponível ao lado do módulo — sem validador o contrato "
                "publicado não é conferido; corrija a instalação antes de confiar na extração"]
    try:
        with open(SCHEMA_EXTRACAO, encoding="utf-8") as arquivo:
            schema = json.load(arquivo)
    except Exception as exc:
        return ["extracao_caso.schema.json ilegível: %s" % exc]
    try:
        problemas = validar_schema(extracao, schema)
    except Exception as exc:
        return ["schema não pôde ser aplicado: %s" % exc]
    return [str(p) for p in (problemas or [])]





def _ler_json(caminho, rotulo):
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except Exception as exc:
        raise Contrato(["%s ilegível/JSON inválido: %s" % (rotulo, exc)])


def _ler_retornos(caminho):
    'Aceita ARQUIVO (lista, ou objeto com `retornos`) ou PASTA com um `.json` por leitor.'




    if os.path.isdir(caminho):
        saida = []
        for nome in sorted(os.listdir(caminho)):
            if not nome.lower().endswith(".json"):
                continue
            valor = _ler_json(os.path.join(caminho, nome), nome)
            saida.extend(valor if isinstance(valor, list) else [valor])
        return saida
    valor = _ler_json(caminho, os.path.basename(caminho))
    if isinstance(valor, dict) and isinstance(valor.get("retornos"), list):
        return valor["retornos"]
    if not isinstance(valor, list):
        raise Contrato(["--retornos deve apontar para lista de retornos, objeto com `retornos` "
                        "ou pasta com um .json por leitor"])
    return valor


def _destino(args):
    if _s(args.saida):
        return os.path.abspath(args.saida)
    if _s(args.raiz):
        return os.path.join(os.path.abspath(args.raiz), NOME_EXTRACAO)


    if caso_raiz is not None:
        try:
            return caso_raiz.arquivo(NOME_EXTRACAO)
        except Exception:
            pass
    return os.path.abspath(NOME_EXTRACAO)


def _gravar(caminho, valor):
    'Gravação ATÔMICA: escreve ao lado e substitui. Interrupção no meio deixaria um'

    destino = os.path.abspath(caminho)
    pasta = os.path.dirname(destino) or "."
    try:
        os.makedirs(pasta, exist_ok=True)
        temporario = destino + ".parcial"
        with open(temporario, "w", encoding="utf-8") as arquivo:
            json.dump(valor, arquivo, ensure_ascii=False, indent=2)
        os.replace(temporario, destino)
    except OSError as exc:
        raise Contrato(["não foi possível gravar %s: %s" % (destino, exc)])
    return destino


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Reconcilia os retornos dos leitores contra o plano da turma (dissero-orquestrador)")
    parser.add_argument("--plano", required=True, help="caminho do plano `dsr.turma_plano.v1`")
    parser.add_argument("--retornos", required=True,
                        help="arquivo com a lista de retornos, ou PASTA com um .json por leitor")
    parser.add_argument("--saida", default=None,
                        help="caminho do EXTRACAO_CASO.json (default: raiz do caso)")
    parser.add_argument("--raiz", default=None, help="força a pasta do caso")
    parser.add_argument("--plano-escalado-autorizado", action="store_true",
                        dest="escalado_autorizado",
                        help="consolida um plano com `acao: escalar` que o advogado liberou "
                             "por outra via; a autorização fica registrada na extração")
    parser.add_argument("--json", action="store_true", dest="json_completo",
                        help="imprime a extração INTEIRA em vez do resumo")
    args = parser.parse_args(argv)

    try:
        plano = _ler_json(args.plano, os.path.basename(args.plano))
        retornos = _ler_retornos(args.retornos)
        extracao = consolidar(plano, retornos,
                              escalado_autorizado=bool(args.escalado_autorizado))
    except Contrato as exc:
        return _saida({"ok": False, "resultado": "contrato_invalido",
                       "motivos": list(exc.args[0])}, 2)

    problemas = validar_extracao(extracao)
    if problemas:


        return _saida({"ok": False, "resultado": "extracao_fora_do_contrato",
                       "motivos": problemas[:8]}, 2)

    try:
        destino = _gravar(_destino(args), extracao)
    except Contrato as exc:
        return _saida({"ok": False, "resultado": "contrato_invalido",
                       "motivos": list(exc.args[0])}, 2)

    reconciliacao = extracao["reconciliacao"]
    payload = {
        "ok": bool(reconciliacao["ok"]),
        "resultado": "extracao_consolidada" if reconciliacao["ok"] else "reconciliacao_reprovada",
        "caso": extracao["caso"],
        "saida": os.path.basename(destino),
        "total_achados": len(extracao["achados"]),
        "total_divergencias": len(extracao["divergencias"]),
        "total_ilegiveis": len(extracao["ilegiveis"]),
        "reconciliacao": reconciliacao,
        "motivos": [],



        "avisos": [],
    }
    sem_paginacao = set(reconciliacao.get("documentos_sem_paginacao") or [])
    if not reconciliacao["ok"]:



        for fatia_id in reconciliacao["fatias_sem_retorno"]:
            payload["motivos"].append("fatia sem retorno: %s" % fatia_id)
        for fatia_id in reconciliacao["retornos_fora_do_plano"]:
            payload["motivos"].append("retorno de fatia fora do plano: %s" % fatia_id)
        for doc_id in reconciliacao["documentos_sem_fatia"]:
            if doc_id in sem_paginacao:
                payload["motivos"].append(
                    "documento sem paginação nunca virou fatia: %s — ninguém leu uma folha "
                    "dele" % doc_id)
            else:
                payload["motivos"].append("documento sem fatia no plano: %s" % doc_id)
        declarada = reconciliacao.get("cobertura_do_plano") or {}
        for buraco in declarada.get("faltando") or []:
            payload["motivos"].append(
                "página fora de fatia declarada pelo próprio plano: %s, %d folha(s) %s"
                % (buraco["doc_id"], buraco["total_faltando"], buraco["paginas"][:10]))
        if declarada.get("completa") is False and not (declarada.get("faltando") or []):
            payload["motivos"].append("o plano declara a cobertura INCOMPLETA (`completa: "
                                      "false`) sem nomear as folhas: replaneje a turma")
    for fatia_id in reconciliacao.get("fatias_sem_achado") or []:
        payload["avisos"].append("fatia lida e ESTÉRIL (`achados: []`): %s" % fatia_id)
    for item in reconciliacao.get("retornos_duplicados") or []:
        payload["avisos"].append("segunda leitura da fatia %s por %s: os achados dela foram "
                                 "gravados UMA vez" % (item["fatia_id"], item["agente"]))
    for item in reconciliacao.get("achados_fora_da_faixa") or []:
        payload["avisos"].append("achado com folha %d fora da faixa %d-%d da fatia %s (%s): a "
                                 "procedência não bate com o que o plano pediu"
                                 % (item["pagina"], item["pagina_inicial"],
                                    item["pagina_final"], item["fatia_id"], item["agente"]))
    for item in reconciliacao.get("declaracoes_divergentes") or []:
        payload["avisos"].append("%s declarou `%s` = %r contra %r do plano na fatia %s: o "
                                 "carimbo do plano prevalece"
                                 % (item["agente"], item["campo"], item["declarado"],
                                    item["do_plano"], item["fatia_id"]))
    if reconciliacao.get("sem_paginacao_autorizado"):
        payload["avisos"].append(
            "documento(s) sem paginação NÃO lido(s) por autorização expressa do advogado: %s"
            % ", ".join(reconciliacao.get("documentos_sem_paginacao") or []))
    if reconciliacao.get("plano_escalado_autorizado"):
        payload["avisos"].append("plano com `acao: escalar` consolidado por AUTORIZAÇÃO "
                                 "EXPRESSA: o planejador havia recusado esta turma")
    if args.json_completo:
        payload["extracao"] = extracao
    return _saida(payload, 0 if reconciliacao["ok"] else 1)


if __name__ == "__main__":
    sys.exit(main())
