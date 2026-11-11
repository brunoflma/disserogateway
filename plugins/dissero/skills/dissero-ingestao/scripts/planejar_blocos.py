#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'planejar_blocos.py — decide SE cabe mapa-síntese e, cabendo, PLANEJA os blocos (Passo 6).'



















































import sys, os, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))






try:
    from aval_subagentes import ler_aval
except Exception:
    ler_aval = None



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
