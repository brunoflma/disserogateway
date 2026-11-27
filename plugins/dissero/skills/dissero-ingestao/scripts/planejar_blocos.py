#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'planejar_blocos.py — decide SE cabe mapa-síntese e, cabendo, PLANEJA os blocos (Passo 6).'



















































import sys, os, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))






try:
    from aval_subagentes import ler_aval
    import aval_subagentes as _aval
except Exception:
    ler_aval = None
    _aval = None






USO_LEITURA = "leitura_em_blocos"
MARCA_LEITOR = "[Dissero · leitor de bloco {k}/{n} · {doc}]"

TIPO_LEITOR = "dissero:leitor-de-bloco"


try:
    MAX_LEITORES_POR_DOCUMENTO = max(1, int(os.environ.get("DSR_LEITURA_MAX_LEITORES") or 120))
except ValueError:
    MAX_LEITORES_POR_DOCUMENTO = 120


MAX_LEITORES_POR_SESSAO = 2 * MAX_LEITORES_POR_DOCUMENTO


def contar_paginas_pdf(caminho):
    'Páginas do PDF lidas do PRÓPRIO arquivo (o número que o modelo declara não autoriza nada).'

    import re as _re
    try:
        with open(caminho, "rb") as fh:
            dados = fh.read()
    except OSError:
        return None
    if not dados.startswith(b"%PDF"):
        return None
    contagens = [int(m) for m in _re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", dados)]
    contagens += [int(m) for m in _re.findall(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", dados)]
    soltas = len(_re.findall(rb"/Type\s*/Page(?![a-zA-Z])", dados))
    n = max(contagens) if contagens else 0
    n = max(n, soltas)
    return n or None


def id_do_documento(caminho):
    """Identidade do documento: os 16 primeiros hexadecimais do SHA-256 do arquivo."""
    import hashlib as _h
    h = _h.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()[:16]


def registrar_leitura(session_id, raiz, blocos_n, documento, arquivo="", agora=None):
    'Autoriza, no aval da sessão, os leitores que FALTAM para este documento (id = hash do'


    import datetime as _dt
    if _aval is None or not _s(session_id):
        return False, "sem a sessão identificada (--session-id) não há aval a registrar"
    alvo, origem = _aval._caminho(_aval.NOME_AVAL, session_id, None, env=_aval.ENV_AVAL)
    if origem == "cwd":
        return False, ("a raiz do caso não está registrada: o gate procuraria o aval em outra pasta. "
                       "Rode `caso_raiz.py registrar --raiz <pasta do caso> --session-id <id>` e planeje de novo")
    if _s(raiz) and os.path.normcase(os.path.abspath(os.path.dirname(alvo))) != os.path.normcase(os.path.abspath(raiz)):
        return False, (f"--raiz {raiz} não é a raiz do caso que o gate enxerga ({os.path.dirname(alvo)}): "
                       "registre a raiz com `caso_raiz.py registrar` em vez de passá-la por argumento")
    agora = agora or _dt.datetime.now().isoformat(timespec="seconds")
    d = None
    if os.path.exists(alvo):
        try:
            with open(alvo, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            return False, f"o aval em {alvo} está ilegível e não é sobrescrito: confira o arquivo"
        if not isinstance(d, dict):
            return False, f"o aval em {alvo} não é um objeto e não é sobrescrito: confira o arquivo"
        if not _aval._vale_para_a_sessao(d, session_id):
            return False, (f"o aval em {alvo} é de outra sessão ({d.get('session_id')}) e não é sobrescrito: "
                           "peça o aval desta sessão com `autorizar_subagentes.py`")
    else:
        d = {"session_id": session_id.strip(), "max_simultaneos": _aval.PADRAO_SIMULTANEOS,
             "ondas": _aval.PADRAO_ONDAS, "concedido_em": agora,
             "escopo": "padrão sem aval expresso; a leitura em blocos foi acrescida pelo pedido de análise"}
    por_doc = _aval.leitura_por_documento(d)
    consumidos = _aval.ler_consumo_leitura(session_id, None).get(documento, 0)
    falta = blocos_n - (por_doc.get(documento, 0) - consumidos)
    if falta <= 0:
        return True, alvo
    if sum(por_doc.values()) + falta > MAX_LEITORES_POR_SESSAO:
        return False, (f"a sessão já autorizou {sum(por_doc.values())} leitores e o teto da sessão é "
                       f"{MAX_LEITORES_POR_SESSAO}: peça o aval expresso ao advogado para seguir")
    lista = d.get("acrescimos") if isinstance(d.get("acrescimos"), list) else []
    lista.append({"agentes": falta, "uso": USO_LEITURA, "documento": documento, "arquivo": arquivo,
                  "escopo": f"leitura em blocos de {arquivo or documento} ({blocos_n} blocos), pelo pedido de análise",
                  "concedido_em": agora})
    d["acrescimos"] = lista
    try:
        with open(alvo, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
    except OSError as e:
        return False, f"não foi possível gravar o aval em {alvo}: {e}"
    return True, alvo


def anotar_leitores(blocos, documento):
    """O pedido de cada leitor, com a marca que o gate reconhece e a instrução de leitura."""
    n = len(blocos)
    for k, b in enumerate(blocos, 1):
        ini, fim = b["paginas"]
        b["tipo_do_leitor"] = TIPO_LEITOR
        b["prompt_do_leitor"] = (
            MARCA_LEITOR.format(k=k, n=n, doc=documento)
            + f" Leia SOMENTE as páginas {ini} a {fim}, com {b['instrucao']}, e devolva a extração "
              "estruturada do contrato do agente de bloco (dissero-ingestao/references/mapa-sintese.md). "
              "Não leia o resto do documento, não conclua sobre o caso e marque como lacuna a página "
              "ilegível.")
    return blocos



LIMIAR_PAGINAS = 60

BLOCO_PAGINAS = 20



BLOCO_MAXIMO = 20
ROTAS = ("eluxi", "read")

OVERLAP_PAGINAS = 3






CHAVES_LISTA = ("pecas", "itens", "indice", "entradas", "capitulos", "secoes", "documentos")
CHAVES_PAGINA = ("pagina_inicial", "pagina_ini", "pagina", "inicio", "start", "from", "folha")
CHAVES_TITULO = ("titulo", "title", "tipo", "nome", "descricao", "resumo")


def _s(x):
    return isinstance(x, str) and bool(x.strip())


def _saida(payload, code=0):
    print(json.dumps(payload, ensure_ascii=False))
    return code


def _int(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, str) and x.strip().isdigit():
        return int(x.strip())
    return None


def _env_int(nome, padrao):
    v = _int(os.environ.get(nome))
    return v if (v is not None and v > 0) else padrao


def ler_indice(caminho):
    'Extrai do índice as (pagina, titulo) de início das unidades lógicas.'




    try:
        with open(caminho, encoding="utf-8") as fh:
            dados = json.load(fh)
    except OSError as e:
        return [], f"índice ilegível ({e}) — fronteiras por corte cego"
    except ValueError as e:
        return [], f"índice não é JSON válido ({e}) — fronteiras por corte cego"

    bruto = None
    if isinstance(dados, list):
        bruto = dados
    elif isinstance(dados, dict):
        for k in CHAVES_LISTA:
            if isinstance(dados.get(k), list):
                bruto = dados[k]
                break
    if not bruto:
        return [], "índice sem lista de unidades reconhecível — fronteiras por corte cego"

    vistas, ancoras = set(), []
    for item in bruto:
        pag = titulo = None
        if isinstance(item, dict):
            for k in CHAVES_PAGINA:
                pag = _int(item.get(k))
                if pag is not None:
                    break
            for k in CHAVES_TITULO:
                if _s(item.get(k)):
                    titulo = item[k].strip()
                    break
        else:
            pag = _int(item)
        if pag is None or pag < 1 or pag in vistas:
            continue
        vistas.add(pag)
        ancoras.append({"pagina": pag, "titulo": titulo or ""})

    ancoras.sort(key=lambda a: a["pagina"])
    if not ancoras:
        return [], "índice sem páginas de início utilizáveis — fronteiras por corte cego"
    return ancoras, ""


def _ancora_proxima(alvo, ancoras, tolerancia, minimo):
    'Âncora mais próxima de `alvo` dentro da tolerância, nunca antes de `minimo`.'


    melhor = None
    for a in ancoras:
        p = a["pagina"]
        if p < minimo or abs(p - alvo) > tolerancia:
            continue
        if melhor is None or abs(p - alvo) < abs(melhor["pagina"] - alvo):
            melhor = a
    return melhor


def montar_blocos(paginas, pagina_inicial=1, bloco=BLOCO_PAGINAS, overlap=OVERLAP_PAGINAS,
                  ancoras=None):
    'Fatia [pagina_inicial, pagina_inicial+paginas-1] em blocos com overlap.'








    ancoras = ancoras or []
    ultima = pagina_inicial + paginas - 1
    tolerancia = max(1, bloco // 4)

    maximo = min(bloco + tolerancia, BLOCO_MAXIMO)

    blocos, ini, anterior_fim, n = [], pagina_inicial, None, 0
    while ini <= ultima:
        n += 1
        fim_cego = min(ini + bloco - 1, ultima)
        fim, ancorado = fim_cego, ""
        if ancoras and fim_cego < ultima:

            alvo = _ancora_proxima(fim_cego + 1, ancoras, tolerancia, ini + 2)
            if alvo is not None and ini <= alvo["pagina"] - 1 <= min(ini + maximo - 1, ultima):
                fim = alvo["pagina"] - 1
                ancorado = alvo["titulo"] or f"início de unidade na p. {alvo['pagina']}"
        blocos.append({
            "bloco_id": f"{n:02d}",
            "paginas": [ini, fim],
            "total_paginas": fim - ini + 1,
            "overlap_com_anterior": 0 if anterior_fim is None else max(0, anterior_fim - ini + 1),
            "fronteira_ancorada": ancorado,
            "ler_markdown": {"pagina_inicio": ini, "pagina_fim": fim},
        })
        if fim >= ultima:
            break
        anterior_fim = fim

        ini = max(fim - overlap + 1, ini + 1)
    return blocos


def anotar_rota(blocos, rota, arquivo=None, processo=None):
    'Acrescenta a cada bloco a INSTRUÇÃO de leitura da rota escolhida.'




    alvo = arquivo.strip() if _s(arquivo) else "<caminho do arquivo>"



    proc = processo.strip() if _s(processo) else "<processo>"
    for b in blocos:
        ini, fim = b["paginas"]
        if rota == "read":
            b["instrucao"] = f'Read(file_path="{alvo}", pages="{ini}-{fim}")'
        else:
            b["instrucao"] = (f'ler_markdown(processo="{proc}", pagina_inicio={ini}, '
                              f'pagina_fim={fim})')
    return blocos


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="Planeja a extração distribuída (mapa-síntese) de documento único e extenso")
    ap.add_argument("--paginas", type=int, required=True,
                    help="total de páginas do documento (do índice/cobertura do eluxi)")
    ap.add_argument("--pagina-inicial", dest="pagina_inicial", type=int, default=1,
                    help="primeira página do intervalo a analisar (default: 1)")
    ap.add_argument("--limiar", type=int, default=None,
                    help=f"páginas a partir das quais aciona (default {LIMIAR_PAGINAS}; "
                         "env DSR_MAPA_LIMIAR_PAGINAS)")
    ap.add_argument("--bloco", type=int, default=None,
                    help=f"páginas por bloco (default {BLOCO_PAGINAS}; teto {BLOCO_MAXIMO} = cap "
                         "do ler_markdown; env DSR_MAPA_BLOCO)")
    ap.add_argument("--overlap", type=int, default=None,
                    help=f"páginas de sobreposição (default {OVERLAP_PAGINAS}; env DSR_MAPA_OVERLAP)")
    ap.add_argument("--rota", choices=ROTAS, default="eluxi",
                    help="quem lê cada bloco: eluxi (ler_markdown) · read (Read do host, PDF "
                         "com caminho no disco). PDF já injetado na conversa, sem caminho, não tem rota: "
                         "o documento já entrou inteiro")
    ap.add_argument("--arquivo", help="caminho/nome do documento, para compor a instrução de "
                                      "leitura da rota read")
    ap.add_argument("--processo", help="identificador do processo no eluxi (campo `processo` "
                                       "de consultar_catalogo/consultar_ingestao), para compor "
                                       "a instrução da rota eluxi: `processo` é argumento "
                                       "obrigatório do ler_markdown")
    ap.add_argument("--indice", help="JSON do índice (consultar_indice) para ancorar as fronteiras")
    ap.add_argument("--demanda", choices=["ampla", "pontual"], default="ampla",
                    help="ampla = percorrer o documento inteiro; pontual = dado localizável "
                         "(resolve por buscar_trechos, sem mapa)")
    ap.add_argument("--sintese-em-subagente", dest="sintese_subagente", action="store_true",
                    help="conta a síntese como +1 agente; por padrão ela roda no processo raiz")
    ap.add_argument("--session-id", dest="session_id",
                    help="id da sessão do harness — sem ele o aval §13 não é conferido")
    ap.add_argument("--raiz", help="força a pasta do caso (default: caso_raiz.py)")
    args = ap.parse_args(argv)

    limiar = args.limiar if args.limiar is not None else _env_int("DSR_MAPA_LIMIAR_PAGINAS",
                                                                  LIMIAR_PAGINAS)
    bloco = args.bloco if args.bloco is not None else _env_int("DSR_MAPA_BLOCO", BLOCO_PAGINAS)
    overlap = args.overlap if args.overlap is not None else _env_int("DSR_MAPA_OVERLAP",
                                                                     OVERLAP_PAGINAS)

    if args.paginas < 1:
        return _saida({"ok": False, "erro": "--paginas deve ser ≥ 1"}, 2)
    if args.pagina_inicial < 1:
        return _saida({"ok": False, "erro": "--pagina-inicial deve ser ≥ 1"}, 2)
    if limiar < 1:
        return _saida({"ok": False, "erro": "--limiar deve ser ≥ 1"}, 2)
    if bloco < 2:
        return _saida({"ok": False, "erro": "--bloco deve ser ≥ 2"}, 2)
    if bloco > BLOCO_MAXIMO:
        return _saida({"ok": False, "erro": f"--bloco {bloco} excede {BLOCO_MAXIMO}: é o cap de "
                                            "páginas consecutivas do `ler_markdown` "
                                            "(anti-truncamento). Bloco maior não pode ser lido."}, 2)
    if overlap < 0:
        return _saida({"ok": False, "erro": "--overlap deve ser ≥ 0"}, 2)
    if overlap >= bloco:
        return _saida({"ok": False, "erro": f"--overlap {overlap} deve ser MENOR que --bloco "
                                            f"{bloco}: sobreposição que iguala o bloco não avança"}, 2)

    base = {"ok": True, "paginas": args.paginas, "pagina_inicial": args.pagina_inicial,
            "limiar": limiar, "bloco": bloco, "overlap": overlap, "demanda": args.demanda,
            "rota": args.rota}

    if args.demanda == "pontual":
        base.update({"acao": "busca_pontual", "blocos": [], "total_blocos": 0,
                     "motivo": "dado localizável: `buscar_trechos` resolve com uma fração do "
                               "custo do mapa (Passo 6, 'quando NÃO usar')"})
        return _saida(base)

    if args.paginas < limiar:
        base.update({"acao": "leitura_direta", "blocos": [], "total_blocos": 0,
                     "motivo": f"{args.paginas} páginas abaixo do limiar de {limiar}: "
                               "`ler_markdown` sequencial é mais barato e não perde precisão"})
        return _saida(base)

    ancoras, aviso = ([], "")
    if _s(args.indice):
        ancoras, aviso = ler_indice(args.indice)
    if aviso:
        base["aviso_indice"] = aviso
    base["ancoras_no_indice"] = len(ancoras)

    blocos = anotar_rota(montar_blocos(args.paginas, args.pagina_inicial, bloco, overlap, ancoras),
                         args.rota, args.arquivo, args.processo)
    agentes = len(blocos) + (1 if args.sintese_subagente else 0)
    if ler_aval is None:



        base.update({
            "acao": "escalar",
            "erro": "módulo irmão `aval_subagentes.py` ausente: o aval do §13 não pôde ser lido",
            "nota": "rode `python sincronizar_shared.py --sync` na raiz do plugin para "
                    "reespelhar os módulos compartilhados",
        })
        return _saida(base, 1)
    teto, det_aval = ler_aval(args.session_id, args.raiz)

    base.update({
        "acao": "mapa_sintese",
        "blocos": blocos,
        "total_blocos": len(blocos),
        "sintese_em_subagente": bool(args.sintese_subagente),
        "agentes_previstos": agentes,
        "aval_subagentes": det_aval,
        "teto_autorizado": teto,
        "sintese_requer_confirmacao": True,
        "motivo": f"{args.paginas} páginas ≥ limiar {limiar} e demanda ampla: extração "
                  "distribuída evita a diluição de atenção da leitura acumulada",
    })

    documento = (args.arquivo or args.processo or "documento").strip()
    doc_id, motivo_auto = None, None
    if os.environ.get("DSR_LEITURA_PEDE_AVAL") == "1":
        motivo_auto = "DSR_LEITURA_PEDE_AVAL=1: o escritório pede o aval expresso para a leitura em blocos"
    elif not _s(args.arquivo) or not os.path.isfile(args.arquivo):
        motivo_auto = ("a autorização pelo pedido só vale para o arquivo no disco (--arquivo com o PDF "
                       "existente): sem ele, o número de páginas não é conferível; peça o aval expresso")
    elif bloco != BLOCO_PAGINAS or overlap != OVERLAP_PAGINAS:
        motivo_auto = (f"a autorização pelo pedido usa os blocos padrão ({BLOCO_PAGINAS} páginas, sobreposição "
                       f"de {OVERLAP_PAGINAS}); com outro tamanho, peça o aval expresso")
    else:
        reais = contar_paginas_pdf(args.arquivo)
        if not reais:
            motivo_auto = "não deu para contar as páginas do arquivo: peça o aval expresso"
        elif args.paginas > reais:
            motivo_auto = (f"o documento tem {reais} páginas, não {args.paginas}: planeje de novo com "
                           f"--paginas {reais}")
        else:
            doc_id = id_do_documento(args.arquivo)
    anotar_leitores(blocos, doc_id or "0" * 16)
    n = len(blocos)
    if doc_id:
        if n > MAX_LEITORES_POR_DOCUMENTO:
            base.update({"acao": "escalar",
                         "erro": (f"{n} blocos passam do teto de {MAX_LEITORES_POR_DOCUMENTO} leitores por documento: "
                                  "divida o documento (por volume ou por fase) ou peça o aval expresso ao advogado")})
            return _saida(base, 1)
        ok, info = registrar_leitura(args.session_id, args.raiz, n, doc_id, os.path.basename(args.arquivo))
        if ok:
            teto, det_aval = ler_aval(args.session_id, args.raiz)
            base.update({"aval_subagentes": det_aval, "teto_autorizado": teto, "aval_registrado_em": info,
                         "leitura_autorizada_pelo_pedido": True, "leitores_autorizados": n, "documento_id": doc_id,
                         "aviso_ao_advogado": (
                             f"Vou ler o documento em {n} partes de até {bloco} páginas, cada uma por um leitor "
                             f"independente, e juntar o resultado depois, para nada se perder no meio. São {n} "
                             f"leitores, e isso consome uso do seu plano. Se preferir uma leitura mais curta ou só "
                             f"de alguns trechos, diga.")})
            if args.sintese_subagente and det_aval.get("restante", 0) < 1:
                base.update({"acao": "escalar",
                             "erro": "a síntese em subagente usa o orçamento comum, que está esgotado nesta sessão: "
                                     "faça a síntese no processo raiz ou peça o aval expresso"})
                return _saida(base, 1)
            return _saida(base)
    else:
        info = motivo_auto
    base["leitura_nao_registrada"] = info
    if agentes > teto:
        base.update({
            "acao": "escalar",
            "erro": f"{agentes} agente(s) previsto(s) excede(m) o teto autorizado de {teto} (§13)",
            "comando_aval": (f'python scripts/autorizar_subagentes.py --session-id '
                             f'{args.session_id or "<id da sessão>"} --max-simultaneos 2 '
                             f'--ondas {(agentes + 1) // 2} '
                             f'--escopo "mapa-síntese — {len(blocos)} blocos de análise"'),
            "nota": "peça o aval expresso ANTES de disparar (§13: aprovação antes do efeito); "
                    "sem ele o hooks/gate_subagentes.py barra os disparos excedentes",
        })
        return _saida(base, 1)

    return _saida(base)


if __name__ == "__main__":
    sys.exit(main())
