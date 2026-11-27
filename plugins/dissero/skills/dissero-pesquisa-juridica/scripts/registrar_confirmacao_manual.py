#!/usr/bin/env python3
'Registra a conferência humana dos julgados: confirmação SÓ pelo recibo da tela; veto por qualquer via.'




















































from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from urllib.parse import urlparse

import recibo_conferencia as rc
from achado_contract import (FONTES_PADRAO, carregar_json, rebaixar_confirmacoes_sem_recibo,
                             sha256_texto, texto, validar_documento)

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


def _mesma_pessoa(a, b):
    return " ".join(texto(a).split()).casefold() == " ".join(texto(b).split()).casefold()


def _quem(ator, responsavel, recibo):
    '(sinais, campos extras da atestação) para quem conferiu e quem responde pela peça.'





    extras, sinais = {}, {}
    if texto(responsavel):
        extras["responsavel"] = texto(responsavel)
        proprio = _mesma_pessoa(ator, responsavel)
        sinais["attested_by_lawyer"] = proprio
        if not proprio:
            sinais["conferido_pela_equipe"] = True
    else:
        sinais["attested_by_lawyer"] = True
    if recibo:
        extras["recibo"] = recibo
        sinais["conferido_na_tela"] = True
    return sinais, extras





SEM_RECIBO = ("a confirmação de julgado só se registra pelo recibo da tela de conferência do "
              "Minha banca")


def _atestar(achado, ator, data, url, declaracao, sinais=None, responsavel=None, recibo=None):
    'Aplica a confirmação a UM achado, ancorada no endereço oficial. Devolve (ok, erro).'



    if not (isinstance(recibo, dict) and isinstance(recibo.get("envelope"), dict)):
        return False, SEM_RECIBO
    ementa = texto(achado.get("syllabus_literal"))
    if not ementa:
        return False, "ementa literal é obrigatória para confirmação"
    if urlparse(url).scheme != "https":
        return False, f"URL oficial deve usar HTTPS (recebida: {url or '(vazia)'})"
    base, extras = _quem(ator, responsavel, recibo)
    achado["official_url"] = url
    achado["verification"] = {
        "result": "confirmed", "method": "human", "checked_at": data,
        "final_url": url, "signals": {**base, **(sinais or {})},
        "human_attestation": {"actor": ator, "date": data, "official_url": url,
                              "declaration": declaracao, "syllabus_sha256": sha256_texto(ementa),
                              **extras}
    }
    achado["use_status"] = "allowed"
    return True, ""


def _atestar_documento(achado, ator, data, documento, declaracao, sinais=None,
                       responsavel=None, recibo=None):
    'Confirmação ancorada no INTEIRO TEOR DOS AUTOS, sem endereço oficial (o PDF do PJe não tem).'



    if not (isinstance(recibo, dict) and isinstance(recibo.get("envelope"), dict)):
        return False, SEM_RECIBO
    ementa = texto(achado.get("syllabus_literal"))
    if not ementa:
        return False, "ementa literal é obrigatória para confirmação"
    if len(texto((documento or {}).get("origem"))) < 3:
        return False, "a origem do documento (onde o advogado o baixou) é obrigatória"
    base, extras = _quem(ator, responsavel, recibo)
    achado["official_url"] = None
    achado["verification"] = {
        "result": "confirmed", "method": "human", "checked_at": data, "final_url": None,
        "signals": {**base, "documento_fornecido_pelo_advogado": True, **(sinais or {})},
        "human_attestation": {"actor": ator, "date": data, "official_url": None, "documento": documento,
                              "declaration": declaracao, "syllabus_sha256": sha256_texto(ementa),
                              **extras}
    }
    achado["use_status"] = "allowed"
    return True, ""


def _vetar(achado, ator, data, url, motivo, responsavel=None, recibo=None, tela=None):
    'NÃO CONFERE é veto: resultado `not_found`, método `none` (`human_attestation` registra'


    sinais = {"vetado_pelo_advogado": not texto(responsavel) or _mesma_pessoa(ator, responsavel)}
    if recibo:
        sinais["conferido_na_tela"] = True
    if tela:
        sinais["tela"] = tela
    achado["verification"] = {
        "result": "not_found", "method": "none", "checked_at": data,
        "final_url": url or texto(achado.get("official_url")),
        "signals": sinais, "human_attestation": None,
    }
    achado["use_status"] = "prohibited"
    achado["selected_for_use"] = False
    negada = {"por": ator, "em": data, "motivo": motivo}
    if texto(responsavel):
        negada["responsavel"] = texto(responsavel)
    if recibo:
        negada["recibo"] = recibo
    achado["conferencia_negada"] = negada


def _voltar_a_pendente(achado, data, tela):
    '"Pendente" numa versão nova do recibo: desfaz a decisão gravada antes (confere ou não'

    v = achado.get("verification") or {}
    achado["verification"] = {"result": "partial", "method": "none", "checked_at": data,
                              "final_url": texto(achado.get("official_url")) or None,
                              "signals": {"tela": tela, "reconferir_na_tela": True},
                              "human_attestation": None}
    achado["use_status"] = "pending"
    achado.pop("conferencia_negada", None)
    return v





CONFIRMAR_NA_TELA = (
    "A confirmação dos julgados se faz no Minha banca, na tela de conferência: qualquer pessoa da "
    "banca, entrando com o próprio login, revisa cada julgado (os que a máquina já conferiu na "
    "fonte vêm marcados como confere, para ratificar) e, quando estiver tudo certo, clica Encerrar "
    "e liberar; o nome dela fica gravado. A resposta na conversa e a folha servem só para tirar "
    "julgado da peça.")
CONFIRMAR_NA_TELA_ASSISTENTE = (
    "Nada foi confirmado por esta via. Gere a lista da tela com `folha_atestacao.py achados.json "
    "-o CONFERENCIA_PENDENTE.json`, chame `preparar_conferencia` do conector dissero com os itens "
    "de CONFERENCIA_TELA.json e mostre o endereço devolvido; avisado de que clicaram Encerrar e "
    "liberar, chame `recibo_da_conferencia`, grave o envelope num .json sem mexer e registre com "
    "`--recibo`. Recibo de conferência ainda aberta não libera nada.")


def _gravar(dados, saida):
    with open(saida, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


def _so_pela_tela(nao_registrados):
    return {"nao_registrados": nao_registrados, "codigo": "CONFIRMACAO_SO_PELA_TELA",
            "mensagem_ao_advogado": CONFIRMAR_NA_TELA,
            "para_o_assistente": CONFIRMAR_NA_TELA_ASSISTENTE}


def _modo_folha(dados, args):
    try:
        conteudo = open(args.folha, encoding="utf-8").read()
    except Exception as erro:
        print(json.dumps({"ok": False, "erro": f"folha ilegível: {erro}"}, ensure_ascii=False))
        return 2
    entradas, sem_marca = parse_folha(conteudo)
    if not entradas:
        print(json.dumps({"ok": False, "codigo": "FOLHA_VAZIA",
                          "erro": "nenhum julgado marcado na folha: marque (x) NÃO CONFERE no "
                                  "julgado que sai da peça; a confirmação se faz na tela",
                          "sem_marca": sem_marca}, ensure_ascii=False))
        return 1
    por_id = {texto(a.get("id")): a for a in (dados.get("achados") or []) if isinstance(a, dict)}
    quem_conferiu = texto(args.quem_conferiu)
    responsavel = (texto(args.ator) or ator_do_perfil()) if quem_conferiu else None
    if quem_conferiu and not responsavel:
        print(json.dumps({"ok": False, "codigo": "RESPONSAVEL_NAO_IDENTIFICADO",
                          "erro": RESPONSAVEL_AUSENTE}, ensure_ascii=False))
        return 2
    recusados, falhas, nao_registrados = [], [], []
    for e in entradas:
        achado = por_id.get(e["id"])
        if achado is None:
            falhas.append(f"{e['id']}: achado não localizado no dataset")
            continue
        if e["confere"]:
            nao_registrados.append(e["id"])
            continue
        ator = e["ator"] or quem_conferiu or args.ator or ator_do_perfil()
        if not ator:
            falhas.append(f"{e['id']}: 'Quem atesta' em branco: o veto é ato de pessoa "
                          f"identificada (preencha na folha ou passe --ator)")
            continue
        _vetar(achado, ator, e["data"] or args.data or hoje(), e["url"],
               e["observacao"] or "não confere com a fonte oficial (folha de conferência)",
               responsavel=responsavel)
        recusados.append(e["id"])
    return _fechar_veto(dados, args, recusados, falhas, nao_registrados,
                        {"sem_marca": sem_marca})


def _fechar_veto(dados, args, recusados, falhas, nao_registrados, extra):
    """Valida, grava (se houver veto) e imprime a saída dos modos que só vetam."""
    erros = validar_documento(dados, fontes_path=args.fontes)
    saida = {"ok": not erros and not falhas and not nao_registrados, "confirmados": [],
             "recusados": recusados, "falhas": falhas, **extra}
    if nao_registrados:
        saida.update(_so_pela_tela(nao_registrados))
    if erros:
        saida["violacoes"] = erros
    if erros or falhas or not recusados:
        saida["gravado"] = False
        print(json.dumps(saida, ensure_ascii=False))
        return 1
    _gravar(dados, args.saida)
    saida["saida"] = args.saida
    saida["resumo"] = (f"{len(recusados)} julgado(s) vetado(s) (saem da peça)"
                       + (f"; {len(nao_registrados)} marcado(s) como confere não foram gravados: "
                          f"a confirmação se faz na tela" if nao_registrados else ""))
    print(json.dumps(saida, ensure_ascii=False))
    return 3 if nao_registrados else 0


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
    def recusa(erro, rc_=2, **extra):
        print(json.dumps({"ok": False, "erro": erro, **extra}, ensure_ascii=False))
        return rc_
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
        return recusa("informe --nao-confere com os números que saem da peça; a confirmação "
                      "se faz na tela")
    if confere & nao:
        return recusa(f"item(ns) {sorted(confere & nao)} em --confere e em --nao-confere ao "
                      f"mesmo tempo: pergunte de novo ao advogado")
    fora = sorted((confere | nao) - set(itens))
    if fora:
        return recusa(f"item(ns) {fora} não estão na lista mostrada ao advogado "
                      f"(itens: {sorted(itens)})")
    nao_registrados = [texto(itens[n].get("id")) for n in sorted(confere)]
    if not nao:


        print(json.dumps({"ok": False, "gravado": False, "confirmados": [],
                          **_so_pela_tela(nao_registrados),
                          "erro": "a confirmação de julgado só se registra pelo recibo da tela"},
                         ensure_ascii=False))
        return 1
    resposta = texto(args.resposta)
    if not resposta:
        return recusa("--resposta é obrigatória: as palavras de quem vetou ficam gravadas no "
                      "motivo do veto")
    advogado = texto(args.ator) or ator_do_perfil()
    if not advogado:
        return recusa("quem veta não foi identificado: o nome vem do perfil do advogado "
                      "(advogado.nome), que não está configurado nesta máquina; configure o "
                      "perfil ou passe --ator")
    quem_conferiu = texto(args.quem_conferiu)
    ator = quem_conferiu or advogado
    responsavel = advogado if quem_conferiu else None
    data = texto(args.data) or hoje()
    por_id = {texto(a.get("id")): a for a in (dados.get("achados") or []) if isinstance(a, dict)}
    recusados, falhas = [], []
    for n in sorted(nao):
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
        _vetar(achado, ator, data, texto(item.get("official_url")),
               motivos.get(n) or f"não confere com a fonte oficial (resposta na conversa: "
                                 f"«{resposta}»)", responsavel=responsavel)
        recusados.append(item["id"])
    extra = {"sem_resposta": sorted(set(itens) - confere - nao), "ator": ator, "data": data}
    if responsavel:
        extra["responsavel"] = responsavel
    return _fechar_veto(dados, args, recusados, falhas, nao_registrados, extra)






VARIAVEL_CHAVE_TESTE = rc.VARIAVEL_CHAVE_TESTE
TIPO_RECIBO = rc.TIPO_RECIBO
RESULTADOS_RECIBO = rc.RESULTADOS_RECIBO
ErroRecibo = rc.ErroRecibo
canonico = rc.canonico
_de_b64url = rc.de_b64url
carregar_chave = rc.carregar_chave
verificar_envelope = rc.verificar_envelope
_instante = rc.instante

RESPONSAVEL_AUSENTE = ("o advogado responsável não foi identificado: ele vem do perfil do "
                       "advogado (advogado.nome), que não está configurado nesta máquina; "
                       "configure o perfil ou informe o nome dele")


def _arquivo_da_procedencia(achado):
    """(registro, caminho) da procedência verbatim do trecho num ARQUIVO local, ou (None, '')."""
    import procedencia_literal as pl
    nivel, _ = pl.conferir_achado(achado)
    if nivel != "verbatim":
        return None, ""
    for reg in achado.get("procedencia_literal") or []:
        if (isinstance(reg, dict) and reg.get("campo", "syllabus_literal") == "syllabus_literal"
                and reg.get("nivel") == "verbatim" and os.path.isfile(texto(reg.get("origem")))):
            return reg, texto(reg.get("origem"))
    return None, ""


def _sha256_arquivo(caminho):
    with open(caminho, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def ancora(achado):
    'Em que se ancora a conferência de um julgado, e o hash que a tela mostra e o recibo leva.'







    url = texto(achado.get("official_url"))
    if urlparse(url).scheme == "https":
        return "endereco", sha256_texto(achado.get("syllabus_literal")), url
    reg, caminho = _arquivo_da_procedencia(achado)
    if reg:
        return "documento", _sha256_arquivo(caminho), {"registro": reg, "caminho": caminho}
    return "nenhuma", sha256_texto(achado.get("syllabus_literal")), None


def conteudo_da_tela(achado):
    '(tipo_ancora, conteudo, sha256, alvo) do julgado como a tela de conferência o mostra.'








    tipo_ancora, sha_ancora, alvo = ancora(achado)
    rotulo = texto(achado.get("reference")) or texto(achado.get("id"))
    documento = ""
    if tipo_ancora == "documento":
        documento = sha_ancora
        alvo = {**alvo, "sha256": documento}
        rotulo = rc.rotulo_do_documento(rotulo, os.path.basename(alvo["caminho"]))
    corpo, sha = rc.conteudo(rotulo, achado.get("citation"), achado.get("syllabus_literal"),
                             alvo if tipo_ancora == "endereco" else "", documento,
                             rc.sha256_inteiro_teor(achado))
    return tipo_ancora, corpo, sha, alvo


def _data_br(iso):
    t = texto(iso)[:10]
    return f"{t[8:10]}/{t[5:7]}/{t[0:4]}" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t) else t


def _decisao_da_tela(achado):
    '(conferencia, versao, instante) da última decisão pela tela já gravada no julgado'

    v = achado.get("verification") or {}
    candidatos = []
    for selo in (((v.get("human_attestation") or {}).get("recibo")), v.get("ratificacao"),
                 ((achado.get("conferencia_negada") or {}).get("recibo"))):
        if isinstance(selo, dict):
            recibo = (selo.get("envelope") or {}).get("recibo") or {}
            candidatos.append((texto(selo.get("conferencia")), rc.versao_do_recibo(recibo),
                               rc.instante(selo.get("em"))))
    tela = (v.get("signals") or {}).get("tela")
    if isinstance(tela, dict):
        candidatos.append((texto(tela.get("conferencia")), int(tela.get("versao") or 1),
                           rc.instante(tela.get("em"))))
    candidatos = [c for c in candidatos if c[2] is not None]
    if not candidatos:
        return None, 0, None
    return max(candidatos, key=lambda c: (c[2], c[1]))




PENDENCIA_ITEM = {
    "ITEM_DESCONHECIDO": (
        "o recibo traz um julgado que não está nesta pesquisa",
        "Falta: nada neste caso; o julgado não é desta pesquisa. Quem resolve: ninguém. Como: o "
        "recibo provavelmente é de outra pesquisa; confira se o arquivo certo foi registrado."),
    "ITEM_ALTERADO": (
        "o julgado mudou depois de conferido na tela (texto, citação, endereço ou documento); a "
        "conferência foi sobre outro conteúdo",
        "Falta: conferir de novo este julgado, que mudou depois da conferência. Quem resolve: "
        "qualquer pessoa da banca. Como: uma nova conferência no Minha banca, que já mostra o "
        "conteúdo atual."),
    "SEM_ENDERECO_NEM_DOCUMENTO": (
        "não há endereço oficial nem o inteiro teor dos autos conferido para ancorar a "
        "confirmação",
        "Falta: o endereço oficial do julgado ou o PDF do inteiro teor. Quem resolve: quem "
        "pesquisa o caso (advogado ou equipe). Como: indicar o endereço oficial ou soltar o PDF do "
        "inteiro teor na conversa; depois, uma nova conferência no Minha banca."),
    "SEM_EMENTA": (
        "não há texto gravado do julgado para comparar com a fonte",
        "Falta: o texto do julgado que vai para a peça. Quem resolve: quem pesquisa o caso. Como: "
        "gravar a ementa ou o trecho a partir da fonte oficial; depois, uma nova conferência no "
        "Minha banca."),
    "RECIBO_ANTIGO": (
        "o julgado já tem uma decisão mais nova pela tela; o recibo antigo não a desfaz",
        "Falta: nada; vale a decisão mais nova. Quem resolve: ninguém. Como: se a decisão mais "
        "nova estiver errada, mude-a na conferência do Minha banca."),
    "ORIGEM_DIVERGENTE": (
        "o recibo traz o julgado como conferido pela máquina, mas a verificação automática dele não "
        "está gravada (ou deixou de valer); não há o que ratificar",
        "Falta: conferir este julgado de novo. Quem resolve: qualquer pessoa da banca confere; "
        "encerra o titular da banca ou quem abriu a conferência. Como: uma nova conferência no "
        "Minha banca, que o mostra como está agora; ao terminar, Encerrar e liberar."),
    "VERSAO_JA_APLICADA": (
        "esta versão da conferência já foi registrada, ou é anterior à registrada; vale só a "
        "mais nova",
        "Falta: nada; vale a versão mais nova da conferência. Quem resolve: ninguém. Como: para "
        "mudar a decisão, mude-a na conferência do Minha banca enquanto ela estiver aberta."),
}


def _da_maquina(achado):
    """O julgado tem a verificação automática gravada (a máquina confirmou o teor na fonte)."""
    v = achado.get("verification") or {}
    return v.get("method") == "automatic" and v.get("result") == "confirmed"


def _ratificar(achado, autor, selo, marca):
    '"Confere" de origem "maquina" no recibo final (D2): grava a ratificação da pessoa sobre a'

    v = achado["verification"]
    sinais = dict(v.get("signals") or {})
    sinais.pop("reconferir_na_tela", None)
    sinais.update({"tela": marca, "ratificado_na_tela": True})
    v["signals"] = sinais
    v["ratificacao"] = {**selo, "por": autor}
    achado["use_status"] = "allowed"
    achado.pop("conferencia_negada", None)


def _maquina_volta_a_pendente(achado, marca):
    '"Pendente" sobre julgado da máquina: desfaz só a ratificação; a verificação automática fica,'

    v = achado["verification"]
    v.pop("ratificacao", None)
    sinais = dict(v.get("signals") or {})
    sinais.pop("ratificado_na_tela", None)
    sinais.update({"tela": marca, "reconferir_na_tela": True})
    v["signals"] = sinais
    achado["use_status"] = "pending"
    achado.pop("conferencia_negada", None)



EM_ANDAMENTO_ADVOGADO = (
    "A conferência ainda está aberta no Minha banca, e nada foi liberado: enquanto ela estiver "
    "aberta, a banca pode ajustar à vontade. Falta: encerrar a conferência. Quem resolve: o "
    "titular da banca ou quem abriu a conferência (só eles veem o botão; qualquer pessoa da banca "
    "pode conferir e salvar antes). Como: no Minha banca, revise os julgados e, quando estiver tudo "
    "certo, clique Encerrar e liberar; só então os julgados que conferem saem liberados.")
EM_ANDAMENTO_ASSISTENTE = (
    "Nada foi gravado: o recibo é de versão intermediária (final false). Mostre o andamento, peça "
    "que encerrem na tela e, avisado de que clicaram Encerrar e liberar, chame "
    "`recibo_da_conferencia` de novo e registre o recibo do encerramento com `--recibo`.")


def _andamento(recibo):
    contagem = {"confere": 0, "nao_confere": 0, "pendente": 0}
    da_maquina = 0
    for e in rc.entradas_do_recibo(recibo):
        contagem[e["resultado"]] = contagem.get(e["resultado"], 0) + 1
        da_maquina += e["origem"] == "maquina"
    return {"conferencia": texto(recibo.get("conferencia")), "versao": rc.versao_do_recibo(recibo),
            "em": texto(recibo.get("em")),
            "por": texto((recibo.get("conferido_por") or {}).get("nome")),
            **contagem, "conferidos_pela_maquina": da_maquina}


def _modo_recibo(dados, args):
    def recusa(codigo, erro, rc_=1, **extra):
        print(json.dumps({"ok": False, "codigo": codigo, "erro": erro, "gravado": False, **extra},
                         ensure_ascii=False))
        return rc_
    try:
        envelope = carregar_json(args.recibo)
    except Exception as erro:
        return recusa("RECIBO_ILEGIVEL", f"recibo ilegível ({erro})", rc_=2)
    try:
        recibo = verificar_envelope(envelope, carregar_chave())
    except ErroRecibo as erro:
        return recusa(erro.codigo, erro.mensagem)

    if not rc.recibo_final(recibo):
        return recusa("CONFERENCIA_EM_ANDAMENTO",
                      "nada foi registrado: a conferência ainda está aberta; só o recibo de "
                      "Encerrar e liberar confirma julgado",
                      andamento=_andamento(recibo), mensagem_ao_advogado=EM_ANDAMENTO_ADVOGADO,
                      para_o_assistente=EM_ANDAMENTO_ASSISTENTE)

    nome = texto(recibo["conferido_por"]["nome"])
    responsavel = texto(recibo["responsavel"])
    em = texto(recibo["em"])
    conferencia = texto(recibo["conferencia"])
    versao = rc.versao_do_recibo(recibo)
    instante = rc.instante(em)


    selo = {"conferencia": conferencia, "chave": texto(recibo["chave"]), "em": em,
            "assinatura_sha256": hashlib.sha256(
                texto(envelope["assinatura"]).encode("ascii")).hexdigest(),
            "envelope": {"recibo": recibo, "assinatura": texto(envelope["assinatura"])}}
    tela = {"conferencia": conferencia, "versao": versao, "em": em}
    por_id = {texto(a.get("id")): a for a in (dados.get("achados") or []) if isinstance(a, dict)}




    pendencias, plano, outros_tipos, deixados = [], [], [], []

    def pendente(ident, codigo):
        motivo, mensagem = PENDENCIA_ITEM[codigo]
        pendencias.append({"id": ident, "codigo": codigo, "motivo": motivo,
                           "mensagem_ao_advogado": mensagem})


    for item in rc.entradas_do_recibo(recibo):
        ident = texto(item["id"])
        if texto(item.get("tipo")) not in ("", "julgado"):
            outros_tipos.append(ident)
            continue
        achado = por_id.get(ident)
        if achado is None:
            pendente(ident, "ITEM_DESCONHECIDO")
            continue
        tipo_ancora, conteudo, sha, alvo = conteudo_da_tela(achado)
        if sha != texto(item["sha256"]):
            pendente(ident, "ITEM_ALTERADO")
            continue




        anterior, versao_anterior, quando = _decisao_da_tela(achado)
        if anterior == conferencia:
            if versao <= versao_anterior:
                pendente(ident, "VERSAO_JA_APLICADA")
                continue
        elif quando and (instante is None or quando >= instante):
            pendente(ident, "RECIBO_ANTIGO")
            continue
        if item["resultado"] == "pendente":
            if anterior is None:
                deixados.append(ident)
                continue
        elif item["resultado"] == "confere":
            if item["origem"] == "maquina" and not _da_maquina(achado):
                pendente(ident, "ORIGEM_DIVERGENTE")
                continue
            if not conteudo["texto"]:
                pendente(ident, "SEM_EMENTA")
                continue
            if tipo_ancora == "nenhuma":
                pendente(ident, "SEM_ENDERECO_NEM_DOCUMENTO")
                continue
        plano.append((item, achado, tipo_ancora, alvo))
    if not plano:
        if not pendencias:
            return recusa("RECIBO_VAZIO", "nada foi registrado: o recibo não traz decisão a "
                                          "registrar (os julgados ficaram pendentes na tela)",
                          deixados_pendentes=deixados)
        return recusa(pendencias[0]["codigo"], "nada foi registrado: " + "; ".join(
            f"{p['id']}: {p['motivo']}" for p in pendencias),
            pendencias=pendencias,
            mensagem_ao_advogado=" ".join(dict.fromkeys(p["mensagem_ao_advogado"]
                                                        for p in pendencias)))

    confirmados, recusados, reabertos, ratificados = [], [], [], []
    for item, achado, tipo_ancora, alvo in plano:
        ident = texto(item["id"])


        autor = texto(item.get("por")) or nome
        em_item = texto(item.get("em")) or em
        declaracao = (f"Conferido por {autor} na tela de conferência do Minha banca em "
                      f"{_data_br(em_item)}, sob responsabilidade de {responsavel}"
                      + (f" (versão {versao} da conferência)." if versao > 1 else "."))
        marca = {**tela, "resultado": item["resultado"]}
        if item["resultado"] == "pendente":
            if _da_maquina(achado):
                _maquina_volta_a_pendente(achado, marca)
            else:
                _voltar_a_pendente(achado, em, marca)
            reabertos.append(ident)
            continue
        if item["resultado"] == "nao_confere":
            _vetar(achado, autor, em_item, alvo if tipo_ancora == "endereco" else "",
                   texto(item.get("motivo")) or "não confere com a fonte (tela de conferência)",
                   responsavel=responsavel, recibo=selo, tela=marca)
            recusados.append(ident)
            continue
        if item["origem"] == "maquina":
            _ratificar(achado, autor, selo, marca)
            confirmados.append(ident)
            ratificados.append(ident)
            continue
        if tipo_ancora == "endereco":
            ok, erro = _atestar(achado, autor, em_item, alvo, declaracao + f" Fonte oficial: {alvo}.",
                                {"tela": marca}, responsavel=responsavel, recibo=selo)
        else:
            reg = alvo["registro"]
            arquivo = os.path.basename(alvo["caminho"])
            documento = {"sha256": alvo["sha256"],
                         "sha256_extracao": texto(reg.get("sha256_extracao")),
                         "origem": f"inteiro teor fornecido à banca ({arquivo}), conferido na "
                                   f"tela de conferência por {autor}",
                         "arquivo": arquivo}
            ok, erro = _atestar_documento(
                achado, autor, em_item, documento,
                declaracao + f" Inteiro teor conferido: {arquivo}, trecho conferido verbatim "
                             f"pela máquina no mesmo documento.",
                {"documento_conferido_por_maquina": True, "tela": marca},
                responsavel=responsavel, recibo=selo)
        if not ok:
            return recusa("ATESTACAO_RECUSADA", f"nada foi registrado: {ident}: {erro}")


        achado.pop("conferencia_negada", None)
        confirmados.append(ident)

    erros = validar_documento(dados, fontes_path=args.fontes)
    desselecionados = []
    if erros:




        desselecionados = _desselecionar_por_estrategia(dados, erros, confirmados, args.fontes)
        if desselecionados is None:
            return recusa("CONTRATO_VIOLADO", "nada foi registrado: a atestação violaria o "
                                              "contrato do dataset", violacoes=erros)
    _gravar(dados, args.saida)
    saida = {"ok": True, "confirmados": confirmados, "recusados": recusados,
             "voltaram_a_pendente": reabertos, "conferido_por": nome,
             "responsavel": responsavel, "em": em, "conferencia": conferencia,
             "versao": versao, "saida": args.saida, "ratificados_da_maquina": ratificados,
             "resumo": (f"{len(confirmados)} confirmado(s) e {len(recusados)} recusado(s) (saem "
                        f"da peça), conferidos por {nome} na tela, sob responsabilidade de "
                        f"{responsavel}"
                        + (f"; {len(ratificados)} deles conferido(s) pela máquina e ratificado(s)"
                           if ratificados else "")
                        + (f"; {len(reabertos)} voltaram a pendente" if reabertos else ""))}
    if deixados:
        saida["deixados_pendentes"] = deixados
    if pendencias:
        saida["pendencias"] = pendencias
        saida["mensagem_ao_advogado"] = " ".join(dict.fromkeys(p["mensagem_ao_advogado"]
                                                              for p in pendencias))
        saida["resumo"] += f"; {len(pendencias)} julgado(s) continuam pendentes"
    if desselecionados:
        bloco = _pendencia_estrategia(desselecionados, confirmados, args.saida)
        saida["estrategia_pendente"] = bloco
        saida["pendencias"] = saida.get("pendencias", []) + [
            {"id": ident, "codigo": "ESTRATEGIA_INCOMPLETA", "motivo": bloco["motivo"],
             "mensagem_ao_advogado": bloco["mensagem_ao_advogado"]} for ident in desselecionados]
        saida["mensagem_ao_advogado"] = " ".join(
            m for m in (saida.get("mensagem_ao_advogado"), bloco["mensagem_ao_advogado"]) if m)
        saida["para_o_assistente"] = bloco["para_o_assistente"]
        saida["resumo"] += (f"; {len(desselecionados)} julgado(s) fora da peça até concluir a "
                            f"estratégia de precedentes")
    if outros_tipos:
        saida["outros_tipos"] = outros_tipos
    print(json.dumps(saida, ensure_ascii=False))

    return 3 if (pendencias or desselecionados) else 0




_SO_SELECAO = (
    "precedente selecionado exige pesquisa contrária concluída",
    "cobertura inexistente não pode manter precedente favorável selecionado",
)


def _desselecionar_por_estrategia(dados, erros, confirmados, fontes):
    'Tira da seleção o mínimo para o registro caber no contrato; devolve os IDs tirados.'




    if dados.get("schema_version") != "dsr.achados.v3" or not erros:
        return None
    if any(e not in _SO_SELECAO for e in erros):
        return None
    import copy as _copy
    tentativa = _copy.deepcopy(dados)
    achados = [a for a in tentativa.get("achados") or [] if isinstance(a, dict)]
    tirados = []
    for a in achados:
        if texto(a.get("id")) in confirmados and a.get("selected_for_use") is True:
            a["selected_for_use"] = False
            tirados.append(texto(a.get("id")))
    restantes = validar_documento(tentativa, fontes_path=fontes)
    if restantes and all(e in _SO_SELECAO for e in restantes):
        est = tentativa.get("estrategia") or {}
        pesquisa = est.get("pesquisa_contraria") or {}
        concluida = pesquisa.get("estado") in ("concluida_sem_achado", "concluida_com_achado")
        for a in achados:
            if a.get("selected_for_use") is not True:
                continue
            favoravel_liberado = ((a.get("estrategia_uso") or {}).get("posicao") == "favoravel"
                                  and a.get("use_status") == "allowed")
            if not concluida or (est.get("cobertura_precedente") == "inexistente"
                                 and favoravel_liberado):
                a["selected_for_use"] = False
                tirados.append(texto(a.get("id")))
        restantes = validar_documento(tentativa, fontes_path=fontes)
    if restantes or not tirados:
        return None
    dados.clear()
    dados.update(tentativa)
    return tirados


def _pendencia_estrategia(desselecionados, confirmados, saida):
    agora = [i for i in desselecionados if i in confirmados]
    outros = [i for i in desselecionados if i not in confirmados]
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estrategia_precedentes.py")
    selecionar = " ".join(f"--selecionar {i}" for i in desselecionados)
    comando = (f'python "{script}" definir --achados "{saida}" '
               f"--pesquisa-contraria concluida_sem_achado "
               f'--consulta "<fonte>" "<termos>" AAAA-MM-DD '
               f"--cobertura confirmada --revisada-em AAAA-MM-DD --valida-ate AAAA-MM-DD "
               f"{selecionar}")
    partes = []
    if agora:
        partes.append(f"{len(agora)} julgado(s) conferido(s) na tela estão confirmados, mas ficam "
                      f"fora da peça por enquanto")
    if outros:
        partes.append(f"{len(outros)} outro(s) julgado(s) já escolhido(s) para a peça também "
                      f"saíram dela pelo mesmo motivo")
    mensagem = ("; ".join(partes) + ". Falta: concluir a pesquisa de julgados em sentido contrário "
                "e avaliar quanto os precedentes sustentam a tese. Quem resolve: o assistente, "
                "com a sua revisão. Como: feita essa etapa, os julgados voltam à peça sem nova "
                "conferência; a conferência que a banca fez continua valendo.")
    assistente = (
        "A confirmação foi gravada (selo do recibo, liberado), mas o julgado saiu da seleção "
        "porque a estratégia do registro não admite precedente selecionado: pesquisa contrária "
        "não concluída e/ou cobertura inexistente. Faça a pesquisa contrária de verdade, registre "
        "as consultas e a cobertura e devolva os julgados à peça pelo comando abaixo, que valida "
        "o registro inteiro e só grava se passar (não edite o arquivo à mão). Ajuste o estado "
        "(concluida_com_achado exige --achado-contrario com julgado classificado como contrário) "
        "e a cobertura (substituivel exige --autoridade-substituta; forcada exige "
        "--fundamentacao-analogica) ao que a pesquisa mostrar. Comando: " + comando)
    return {"codigo": "ESTRATEGIA_INCOMPLETA",
            "motivo": "confirmado pela tela, fora da peça até concluir a estratégia de precedentes",
            "confirmados_fora_da_peca": agora, "outros_fora_da_peca": outros,
            "mensagem_ao_advogado": mensagem, "para_o_assistente": assistente,
            "comando": comando}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Registrar a conferência humana dos julgados")
    parser.add_argument("arquivo")
    parser.add_argument("--recibo", help="recibo assinado da tela de conferência (envelope "
                                         "JSON com recibo e assinatura): o único que confirma")
    parser.add_argument("--lista", help="CONFERENCIA_PENDENTE.json que o folha_atestacao.py "
                                        "gravou ao mostrar a lista (só veto)")
    parser.add_argument("--confere", help="números que disseram conferir: não grava; a "
                                          "confirmação se faz na tela")
    parser.add_argument("--nao-confere", help="números dos itens que saem da peça")
    parser.add_argument("--resposta", help="as palavras de quem vetou, como escreveu")
    parser.add_argument("--motivo", action="append",
                        help="'N: motivo' de um item que não confere (repetível)")
    parser.add_argument("--folha", help="folha de conferência preenchida (só veto)")
    parser.add_argument("--quem-conferiu",
                        help="nome de quem de fato conferiu (lista e folha); o advogado do "
                             "perfil fica como responsável")
    parser.add_argument("--id")
    parser.add_argument("--ator")
    parser.add_argument("--url-oficial")
    parser.add_argument("--declaracao")
    parser.add_argument("--data")
    parser.add_argument("-o", "--saida", required=True)
    parser.add_argument("--fontes", default=FONTES_PADRAO)
    args = parser.parse_args(argv)

    try:
        dados = carregar_json(args.arquivo)
    except Exception as erro:
        print(json.dumps({"ok": False, "erro": str(erro)}, ensure_ascii=False)); return 2

    if not (args.recibo or args.lista or args.folha):

        print(json.dumps({"ok": False, "gravado": False, **_so_pela_tela([texto(args.id)] if args.id else []),
                          "erro": "a confirmação de julgado só se registra pelo recibo da tela"},
                         ensure_ascii=False))
        return 2


    rebaixados = rebaixar_confirmacoes_sem_recibo(dados)
    if rebaixados:
        print(json.dumps({"aviso": "confirmação sem recibo da tela voltou a pendente",
                          "rebaixados": rebaixados}, ensure_ascii=False), file=sys.stderr)
    if args.recibo:
        return _modo_recibo(dados, args)
    if args.lista:
        return _modo_lista(dados, args)
    return _modo_folha(dados, args)


if __name__ == "__main__":
    raise SystemExit(main())
