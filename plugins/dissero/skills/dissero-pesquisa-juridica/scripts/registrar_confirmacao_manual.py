#!/usr/bin/env python3
'Registra atestação explícita do advogado vinculada à URL e ao SHA-256 da ementa.'


























from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

from achado_contract import FONTES_PADRAO, carregar_json, sha256_texto, texto, validar_documento

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MIN_DECLARACAO = 20




_RX_ID = re.compile(r"^`id`:\s*\*\*(.+?)\*\*\s*$", re.M)
_RX_QUEM = re.compile(r"^-\s*Quem atesta:\s*(.+?)\s*$", re.M)
_RX_DATA = re.compile(r"^-\s*Data \(AAAA-MM-DD\):\s*(.+?)\s*$", re.M)
_RX_RESULTADO = re.compile(r"^-\s*Resultado:\s*(.+?)\s*$", re.M)
_RX_URL_ABERTA = re.compile(r"^-\s*Endereço efetivamente aberto[^:]*:\s*(.+?)\s*$", re.M)
_RX_OBS = re.compile(r"^-\s*Observação:\s*(.+?)\s*$", re.M)
_RX_URL_SECAO = re.compile(r"^\*\*Endereço a abrir\*\*\s*\n\s*\n(\S+)\s*$", re.M)
_VAZIO = re.compile(r"^[_\s]*$")


def _limpo(valor):
    'Campo de formulário em branco continua em branco: a linha vem com sublinhados como'


    v = (valor or "").strip()
    return "" if _VAZIO.match(v) else v


def _marcado(linha, alvo):
    """`(x) CONFERE` / `(X) NÃO CONFERE` — aceita x, X e ✓ dentro dos parênteses."""
    for m in re.finditer(r"\(([^)]{0,3})\)\s*([^()]+)", linha):
        marca, rotulo = m.group(1).strip().lower(), m.group(2).strip().upper()
        if marca in ("x", "✓", "v") and rotulo.startswith(alvo):
            return True
    return False


def parse_folha(conteudo):
    '[{id, ator, data, confere, url, observacao}] — uma entrada por julgado ATESTADO.'




    blocos = re.split(r"^---\s*$", conteudo, flags=re.M)
    saida, ignorados = [], []
    for bloco in blocos:
        m_id = _RX_ID.search(bloco)
        if not m_id:
            continue
        ident = m_id.group(1).strip()
        m_res = _RX_RESULTADO.search(bloco)
        linha_res = m_res.group(1) if m_res else ""
        confere = _marcado(linha_res, "CONFERE")
        nao_confere = _marcado(linha_res, "NÃO CONFERE") or _marcado(linha_res, "NAO CONFERE")
        if not confere and not nao_confere:
            ignorados.append(ident)
            continue
        url = _limpo(_RX_URL_ABERTA.search(bloco).group(1) if _RX_URL_ABERTA.search(bloco) else "")
        if not url:
            m_sec = _RX_URL_SECAO.search(bloco)
            url = m_sec.group(1).strip() if m_sec else ""
        saida.append({
            "id": ident,
            "ator": _limpo(_RX_QUEM.search(bloco).group(1) if _RX_QUEM.search(bloco) else ""),
            "data": _limpo(_RX_DATA.search(bloco).group(1) if _RX_DATA.search(bloco) else ""),
            "confere": bool(confere) and not nao_confere,
            "url": url,
            "observacao": _limpo(_RX_OBS.search(bloco).group(1) if _RX_OBS.search(bloco) else ""),
        })
    return saida, ignorados


def ator_do_perfil():
    "Nome do advogado no perfil resolvido (`advogado.nome`), ou '' sem perfil."



    try:
        import perfil_advogado as pa
        perfil = pa.carregar()
    except Exception:
        return ""
    if not isinstance(perfil, dict):
        return ""
    return texto((perfil.get("advogado") or {}).get("nome"))


def hoje():
    return datetime.now().date().isoformat()


def _atestar(achado, ator, data, url, declaracao, sinais=None):
    'Aplica a atestação a UM achado. Devolve (ok, erro).'



    ementa = texto(achado.get("syllabus_literal"))
    if not ementa:
        return False, "ementa literal é obrigatória para confirmação"
    if urlparse(url).scheme != "https":
        return False, f"URL oficial deve usar HTTPS (recebida: {url or '(vazia)'})"
    achado["official_url"] = url
    achado["verification"] = {
        "result": "confirmed", "method": "human", "checked_at": data,
        "final_url": url, "signals": {"attested_by_lawyer": True, **(sinais or {})},
        "human_attestation": {"actor": ator, "date": data, "official_url": url,
                              "declaration": declaracao, "syllabus_sha256": sha256_texto(ementa)}
    }
    achado["use_status"] = "allowed"
    return True, ""


def _vetar(achado, ator, data, url, motivo):
    'NÃO CONFERE é veto: resultado `not_found`, método `none` (`human_attestation` registra'

    achado["verification"] = {
        "result": "not_found", "method": "none", "checked_at": data,
        "final_url": url or texto(achado.get("official_url")),
        "signals": {"vetado_pelo_advogado": True},
        "human_attestation": None,
    }
    achado["use_status"] = "prohibited"
    achado["selected_for_use"] = False
    achado["conferencia_negada"] = {"por": ator, "em": data, "motivo": motivo}


def _modo_folha(dados, args):
    try:
        conteudo = open(args.folha, encoding="utf-8").read()
    except Exception as erro:
        print(json.dumps({"ok": False, "erro": f"folha ilegível: {erro}"}, ensure_ascii=False))
        return 2
    entradas, sem_marca = parse_folha(conteudo)
    if not entradas:
        print(json.dumps({"ok": False, "codigo": "FOLHA_VAZIA",
                          "erro": "nenhum julgado ATESTADO na folha — marque (x) CONFERE ou "
                                  "(x) NÃO CONFERE em cada bloco antes de devolvê-la",
                          "sem_marca": sem_marca}, ensure_ascii=False))
        return 1
    por_id = {texto(a.get("id")): a for a in (dados.get("achados") or []) if isinstance(a, dict)}
    confirmados, recusados, falhas = [], [], []
    for e in entradas:
        achado = por_id.get(e["id"])
        if achado is None:
            falhas.append(f"{e['id']}: achado não localizado no dataset")
            continue
        if not e["confere"]:
            _vetar(achado, e["ator"] or args.ator, e["data"] or args.data, e["url"],
                   e["observacao"] or "não confere com a fonte oficial (folha de conferência)")
            recusados.append(e["id"])
            continue
        ator = e["ator"] or args.ator
        data = e["data"] or args.data or datetime.now(timezone.utc).isoformat()
        if not ator:
            falhas.append(f"{e['id']}: 'Quem atesta' em branco — atestação é ato de pessoa "
                          f"identificada (preencha na folha ou passe --ator)")
            continue
        declaracao = (f"Conferido na fonte oficial pela folha de conferência: moldura "
                      f"(número, órgão, relator e data) e trecho literal conferidos contra a "
                      f"tela do tribunal em {data}."
                      + (f" Observação: {e['observacao']}" if e["observacao"] else ""))
        ok, erro = _atestar(achado, ator, data, e["url"], declaracao)
        (confirmados if ok else falhas).append(e["id"] if ok else f"{e['id']}: {erro}")

    erros = validar_documento(dados, fontes_path=args.fontes)
    saida = {"ok": not erros and not falhas, "confirmados": confirmados,
             "recusados": recusados, "falhas": falhas, "sem_marca": sem_marca}
    if erros:
        saida["violacoes"] = erros
    if not saida["ok"]:
        print(json.dumps(saida, ensure_ascii=False))
        return 1
    with open(args.saida, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
    saida["saida"] = args.saida
    saida["resumo"] = (f"{len(confirmados)} confirmado(s), {len(recusados)} recusado(s) "
                       f"(saem da peça)"
                       + (f", {len(sem_marca)} sem marca na folha (seguem pendentes)"
                          if sem_marca else ""))
    print(json.dumps(saida, ensure_ascii=False))
    return 0


def _numeros(valor):
    "'1, 2 e 5' / '1,2,5' / '1 2 5' -> {1, 2, 5}. Outra coisa que não número é recusada:"

    v = texto(valor)
    if not v:
        return set()
    partes = [p for p in re.split(r"[\s,;]+|\be\b", v) if p]
    if not all(p.isdigit() for p in partes):
        raise ValueError(f"esperado número de item da lista, recebido {v!r}")
    return {int(p) for p in partes}


def _motivos(valores):
    """['3: o relator é outro'] -> {3: 'o relator é outro'}."""
    saida = {}
    for v in valores or []:
        m = re.match(r"^\s*(\d+)\s*[:=\-–]\s*(.+?)\s*$", texto(v))
        if not m:
            raise ValueError(f"--motivo deve ser 'N: motivo', recebido {v!r}")
        saida[int(m.group(1))] = m.group(2)
    return saida


def _modo_lista(dados, args):
    def recusa(erro, rc=2):
        print(json.dumps({"ok": False, "erro": erro}, ensure_ascii=False))
        return rc
    try:
        lista = carregar_json(args.lista)
        itens = {int(i["numero"]): i for i in lista.get("itens") or []}
    except Exception as erro:
        return recusa(f"lista ilegível ({args.lista}): {erro}")
    try:
        confere, nao = _numeros(args.confere), _numeros(args.nao_confere)
        motivos = _motivos(args.motivo)
    except ValueError as erro:
        return recusa(str(erro))
    if not confere and not nao:
        return recusa("informe --confere e/ou --nao-confere com os números que o advogado deu")
    if confere & nao:
        return recusa(f"item(ns) {sorted(confere & nao)} em --confere e em --nao-confere ao "
                      f"mesmo tempo: pergunte de novo ao advogado")
    fora = sorted((confere | nao) - set(itens))
    if fora:
        return recusa(f"item(ns) {fora} não estão na lista mostrada ao advogado "
                      f"(itens: {sorted(itens)})")
    resposta = texto(args.resposta)
    if not resposta:
        return recusa("--resposta é obrigatória: as palavras do advogado são a declaração que "
                      "fica gravada na atestação")
    ator = texto(args.ator) or ator_do_perfil()
    if not ator:
        return recusa("quem atesta não foi identificado: o nome vem do perfil do advogado "
                      "(advogado.nome), que não está configurado nesta máquina; configure o "
                      "perfil ou passe --ator")
    data = texto(args.data) or hoje()
    por_id = {texto(a.get("id")): a for a in (dados.get("achados") or []) if isinstance(a, dict)}
    confirmados, recusados, falhas = [], [], []
    for n in sorted(confere | nao):
        item = itens[n]
        achado = por_id.get(texto(item.get("id")))
        if achado is None:
            falhas.append(f"item {n} ({item.get('id')}): achado não localizado no dataset")
            continue
        if (sha256_texto(achado.get("syllabus_literal")) != item.get("syllabus_sha256")
                or texto(achado.get("official_url")) != texto(item.get("official_url"))):
            falhas.append(f"item {n} ({item.get('id')}): o julgado mudou depois que a lista "
                          f"foi mostrada (trecho ou endereço); gere a lista de novo e mostre-a "
                          f"ao advogado, porque a resposta dele foi sobre outro texto")
            continue
        url = texto(item.get("official_url"))
        if n in nao:
            _vetar(achado, ator, data, url,
                   motivos.get(n) or f"não confere com a fonte oficial (resposta do advogado: "
                                     f"«{resposta}»)")
            recusados.append(item["id"])
            continue
        declaracao = (f"Conferido pelo advogado na fonte oficial ({url}), item {n} da lista de "
                      f"conferência, em resposta na conversa: «{resposta}».")
        ok, erro = _atestar(achado, ator, data, url, declaracao,
                            {"resposta_na_conversa": True})
        (confirmados if ok else falhas).append(item["id"] if ok else f"item {n}: {erro}")

    erros = validar_documento(dados, fontes_path=args.fontes)
    sem_resposta = sorted(set(itens) - confere - nao)
    saida = {"ok": not erros and not falhas, "confirmados": confirmados,
             "recusados": recusados, "falhas": falhas, "sem_resposta": sem_resposta,
             "ator": ator, "data": data}
    if erros:
        saida["violacoes"] = erros
    if not saida["ok"]:
        print(json.dumps(saida, ensure_ascii=False))
        return 1
    with open(args.saida, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
    saida["saida"] = args.saida
    saida["resumo"] = (f"{len(confirmados)} confirmado(s), {len(recusados)} recusado(s) "
                       f"(saem da peça)"
                       + (f", item(ns) {sem_resposta} sem resposta (seguem pendentes)"
                          if sem_resposta else ""))
    print(json.dumps(saida, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Registrar confirmação humana Dissero")
    parser.add_argument("arquivo")
    parser.add_argument("--lista", help="CONFERENCIA_PENDENTE.json que o folha_atestacao.py "
                                        "gravou ao mostrar a lista (modo RESPOSTA NA CONVERSA)")
    parser.add_argument("--confere", help="números dos itens que o advogado disse conferir")
    parser.add_argument("--nao-confere", help="números dos itens que ele disse não conferir")
    parser.add_argument("--resposta", help="as palavras do advogado, como ele escreveu")
    parser.add_argument("--motivo", action="append",
                        help="'N: motivo' de um item que não confere (repetível)")
    parser.add_argument("--folha", help="folha de conferência preenchida (modo em BLOCO)")
    parser.add_argument("--id")
    parser.add_argument("--ator")
    parser.add_argument("--url-oficial")
    parser.add_argument("--declaracao")
    parser.add_argument("--data")
    parser.add_argument("-o", "--saida", required=True)
    parser.add_argument("--fontes", default=FONTES_PADRAO)
    args = parser.parse_args()

    try:
        dados = carregar_json(args.arquivo)
    except Exception as erro:
        print(json.dumps({"ok": False, "erro": str(erro)}, ensure_ascii=False)); return 2

    if args.lista:
        return _modo_lista(dados, args)
    if args.folha:
        return _modo_folha(dados, args)

    for obrigatorio in ("id", "ator", "url_oficial", "declaracao"):
        if not texto(getattr(args, obrigatorio, None)):
            print(json.dumps({"ok": False, "erro": f"--{obrigatorio.replace('_', '-')} é "
                                                   f"obrigatório fora do modo --folha"},
                             ensure_ascii=False)); return 2
    if len(texto(args.declaracao)) < MIN_DECLARACAO:
        print(json.dumps({"ok": False,
                          "erro": f"declaração deve ter ao menos {MIN_DECLARACAO} caracteres"},
                         ensure_ascii=False)); return 2
    achado = next((item for item in dados.get("achados", []) if item.get("id") == args.id), None)
    if not achado:
        print(json.dumps({"ok": False, "erro": "achado não localizado"}, ensure_ascii=False)); return 2
    data = args.data or datetime.now(timezone.utc).isoformat()
    ok, erro = _atestar(achado, args.ator, data, args.url_oficial, args.declaracao)
    if not ok:
        print(json.dumps({"ok": False, "erro": erro}, ensure_ascii=False)); return 2
    erros = validar_documento(dados, fontes_path=args.fontes)
    if erros:
        print(json.dumps({"ok": False, "violacoes": erros}, ensure_ascii=False)); return 1
    with open(args.saida, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
    print(json.dumps({"ok": True, "id": args.id, "saida": args.saida,
                      "syllabus_sha256": achado["verification"]["human_attestation"]["syllabus_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
