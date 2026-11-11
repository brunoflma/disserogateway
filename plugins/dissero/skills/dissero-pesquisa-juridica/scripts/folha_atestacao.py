#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'folha_atestacao.py — o que fecha o ciclo entre DESCOBERTA e CONFIRMAÇÃO.'










































from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

from achado_contract import FONTES_PADRAO, carregar_json, sha256_texto, texto


VERSOES_ACEITAS = ("dsr.achados.v2", "dsr.achados.v3")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass




NOTAS_DE_PORTAL = {
    "esaj": ("e-SAJ: a busca pública de jurisprudência responde no TJAL, TJMS, TJAC e TJSP, "
             "mas o PDF do inteiro teor não tem rota automática, e é ele que esta conferência "
             "cobre. No e-SAJ do TJCE a conferência é humana desde a busca"),
    "scon": ("SCON (STJ): a busca responde quando a consulta começa pela página inicial do "
             "portal; quem chega direto à pesquisa recebe HTTP 403, e isso não é bloqueio do "
             "portal. O PDF do inteiro teor não tem rota automática"),
    "jurisprudencia.stj": ("Busca de jurisprudência do STJ: mesma condição do SCON. A busca "
                           "responde; o PDF do inteiro teor exige conferência humana"),
}

_ROTULOS_MOLDURA = (
    ("case_number", "Número"),
    ("court", "Tribunal"),
    ("rapporteur", "Relator(a)"),
    ("judgment_date", "Julgamento"),
    ("identifier", "Identificador"),
    ("status", "Situação"),
    ("norm_type", "Tipo de norma"),
    ("norm_number", "Número da norma"),
    ("norm_date", "Data da norma"),
    ("provision", "Dispositivo"),
    ("validity", "Vigência"),
)


def barreira_conhecida(url):
    """Nota sobre o portal, quando o PDF do inteiro teor dele só se confere à mão."""
    u = (url or "").lower()
    for chave, nota in NOTAS_DE_PORTAL.items():
        if chave in u:
            return nota
    return ""


def aviso_host_travado(url, fontes):
    """Aviso ao advogado quando o host do endereço tem `confirmacao_teor` em `travas_locais`."""
    host = (urlparse(url or "").hostname or "").lower()
    ficha = ((fontes or {}).get("hosts") or {}).get(host)
    if not isinstance(ficha, dict) or "confirmacao_teor" not in ficha.get("travas_locais", []):
        return ""
    return (f"Este endereço não confirma o teor. {host} é do DataJud ou do LexML e serve "
            f"metadado ou índice, não o documento. Abra o julgado ou a norma no site do "
            f"tribunal ou do órgão que o publicou e confira lá. Anote esse endereço na linha "
            f"\"Endereço efetivamente aberto\". A atestação feita neste endereço é recusada no "
            f"registro")


def _pendentes(dados, tudo=False):
    saida = []
    for achado in (dados.get("achados") or []):
        if not isinstance(achado, dict):
            continue
        status = achado.get("use_status")
        if status == "prohibited":
            continue
        if tudo or status == "pending":
            saida.append(achado)
    return saida


def _trechos_para_conferir(achado, maximo=1200):
    'Ementa primeiro; o inteiro teor só se não houver ementa. A conferência do advogado é'

    ementa = texto(achado.get("syllabus_literal"))
    if ementa:
        return ementa[:maximo] + ("…" if len(ementa) > maximo else "")
    inteiro = texto(achado.get("full_text"))
    if inteiro:
        return inteiro[:maximo] + ("…" if len(inteiro) > maximo else "")
    return ""


def montar(dados, tudo=False, ator="", fontes=None):
    itens = _pendentes(dados, tudo)
    if not itens:
        return None, 0
    tema = texto(dados.get("tema")) or "(tema não declarado)"
    linhas = [
        "# FOLHA DE CONFERÊNCIA NA FONTE OFICIAL",
        "",
        f"**Pesquisa:** {tema}",
        f"**Julgados a conferir:** {len(itens)}",
        "",
        "Cada julgado abaixo entrou na minuta assinalado como *a conferir*. Abra o endereço, "
        "confira primeiro a MOLDURA (número, órgão, relator e data) e depois o TRECHO, palavra "
        "a palavra, contra o que está na tela. Moldura certa com trecho de outro julgado é o "
        "erro que a leitura de conferência do julgador encontra — e é o que esta folha existe "
        "para impedir.",
        "",
        "Conferido, preencha a linha **ATESTO** do julgado. Depois devolva a folha preenchida: "
        "as conferências marcadas são registradas a partir dela, todas de uma vez, sem "
        "redigitar nada.",
        "",
        "Julgado que não se confirme na fonte **sai da peça** — não fica assinalado até o "
        "protocolo.",
        "",
        "---",
        "",
    ]
    for i, achado in enumerate(itens, 1):
        ref = texto(achado.get("reference")) or "(sem rótulo)"
        ident = texto(achado.get("id")) or f"(sem id — achado {i})"
        url = texto(achado.get("official_url"))
        citation = achado.get("citation") or {}
        linhas += [f"## {i}. {ref}", "", f"`id`: **{ident}**", "", "**Moldura a conferir**", ""]
        moldura = [(rot, texto(citation.get(campo)))
                   for campo, rot in _ROTULOS_MOLDURA if texto(citation.get(campo))]
        if moldura:
            linhas += ["| Campo | Valor registrado | Confere? |", "| --- | --- | --- |"]
            linhas += [f"| {rot} | {val} | ( ) sim  ( ) não |" for rot, val in moldura]
        else:
            linhas.append("_Nenhum campo de identificação registrado — o que já é um defeito "
                          "do achado: confira e complete antes de atestar._")
        linhas.append("")
        if url:
            linhas += ["**Endereço a abrir**", "", url, ""]
            travado = aviso_host_travado(url, fontes)
            if travado:
                linhas += [f"> {travado}.", ""]
            nota = barreira_conhecida(url)
            if nota:
                linhas += [f"> Sobre este portal: {nota}.", ""]
        else:
            pend = achado.get("pendencia_fonte") or {}
            falta = texto(pend.get("falta")) or "endereço oficial ainda não obtido"
            como = texto(pend.get("como_obter"))
            linhas += ["**Endereço a abrir**", "",
                       f"_Não há endereço registrado: {falta}._"
                       + (f" Como obter: {como}" if como else ""), ""]
        trecho = _trechos_para_conferir(achado)
        if trecho:
            linhas += ["**Trecho gravado — conferir palavra a palavra**", "",
                       "> " + trecho.replace("\n", "\n> "), ""]
        else:
            linhas += ["**Trecho gravado**", "",
                       "_Nenhum trecho literal foi extraído (é exatamente o caso dos portais "
                       "que só entregam PDF). Transcreva da tela o trecho que a peça usa._", ""]
        uso = achado.get("estrategia_uso")
        if isinstance(uso, dict) and texto(uso.get("como_usar")):
            linhas += [f"**Para que serve na peça:** {texto(uso['como_usar'])}", ""]
        linhas += [
            "**ATESTO** que abri o endereço acima e conferi moldura e trecho contra a fonte "
            "oficial.", "",
            f"- Quem atesta: {ator or '_______________________'}",
            "- Data (AAAA-MM-DD): _______________",
            "- Resultado: ( ) CONFERE  ( ) NÃO CONFERE — sai da peça",
            "- Endereço efetivamente aberto (se diferente do acima): _______________",
            "- Observação: _______________",
            "", "---", "",
        ]
    return "\n".join(linhas), len(itens)





_SINAIS_MOLDURA = {
    "acordao": ("numero", "relator"),
    "sumula": ("identificador",),
    "tema": ("identificador",),
    "norma": ("tipo_norma", "numero_norma"),
}
TRECHO_CURTO = 160


def moldura_conferida(achado):
    """Data em que a máquina conferiu a moldura na fonte, ou '' se não conferiu."""
    v = achado.get("verification") or {}
    sinais = v.get("signals") or {}
    exigidos = _SINAIS_MOLDURA.get(achado.get("nature"), ("identificador",))
    if not all(sinais.get(k) is True for k in exigidos):
        return ""
    return texto(v.get("checked_at"))[:10] or "data não registrada"


def _para_conferir(dados):
    """(itens, fora_da_peca): os pendentes que sustentam a peça; sem nenhum selecionado, todos."""
    pend = _pendentes(dados)
    sel = [a for a in pend if a.get("selected_for_use")]
    return (sel, len(pend) - len(sel)) if sel else (pend, 0)


def _uma_linha(valor, maximo=TRECHO_CURTO):
    t = " ".join(texto(valor).split())
    return t if len(t) <= maximo else t[:maximo].rstrip() + "…"


def montar_lista(dados, fontes=None):
    """(texto para a conversa, lista para gravar) ou (None, None) sem nada a conferir."""
    itens, fora = _para_conferir(dados)
    if not itens:
        return None, None
    linhas = [f"Julgados a conferir na fonte oficial ({len(itens)}):", ""]
    registro = []
    for n, achado in enumerate(itens, 1):
        citation = achado.get("citation") or {}
        ref = texto(achado.get("reference")) or "(sem rótulo)"
        url = texto(achado.get("official_url"))
        conferida = moldura_conferida(achado)
        if conferida:
            moldura = f"moldura conferida na fonte em {conferida}"
        else:
            campos = [f"{rot.lower()} {texto(citation.get(c))}"
                      for c, rot in _ROTULOS_MOLDURA[:4] if texto(citation.get(c))]
            moldura = "confira " + (", ".join(campos) if campos else "número, relator e data")
        linhas.append(f"{n}. {ref} · {moldura}")
        if url:
            linhas.append(f"   Abrir: {url}")
            if aviso_host_travado(url, fontes):
                linhas.append("   Este endereço não confirma o teor (DataJud ou LexML): abra o "
                              "julgado no site do tribunal que o publicou.")
        else:
            pend = achado.get("pendencia_fonte") or {}
            linhas.append(f"   Sem endereço registrado: "
                          f"{texto(pend.get('falta')) or 'endereço oficial ainda não obtido'}.")
        trecho = _uma_linha(achado.get("syllabus_literal") or achado.get("full_text"))
        linhas.append(f"   Trecho: «{trecho}»" if trecho else
                      "   Trecho: nenhum gravado; copie da tela o trecho que a peça usa.")
        linhas.append("")
        registro.append({"numero": n, "id": texto(achado.get("id")), "referencia": ref,
                         "official_url": url,
                         "syllabus_sha256": sha256_texto(achado.get("syllabus_literal"))})
    linhas.append("Para cada um, baixe o PDF do inteiro teor no endereço e solte aqui: a "
                  "máquina confere o trecho palavra por palavra. Sem o PDF, responda numa "
                  "linha, por exemplo: \"conferem 1 e 2; o 3 não confere\". O que não "
                  "conferir sai da peça.")
    if fora:
        linhas.append("")
        linhas.append(f"Outros {fora} julgado(s) pendente(s) não estão na minuta e ficaram fora "
                      f"desta conferência.")
    return "\n".join(linhas), {"schema_version": "dsr.conferencia_pendente.v1",
                               "tema": texto(dados.get("tema")), "fora_da_peca": fora,
                               "itens": registro}


def main():
    parser = argparse.ArgumentParser(
        description="Conferência na fonte oficial, a partir dos achados pendentes")
    parser.add_argument("arquivo", help="achados.json (contrato dsr.achados.v2 ou v3)")
    parser.add_argument("-o", "--saida", required=True,
                        help="lista .json (padrão) ou folha .md (--formato folha)")
    parser.add_argument("--formato", choices=("lista", "folha"),
                        help="lista curta para a conversa (padrão) ou a folha de formulário; "
                             "-o terminado em .md implica folha")
    parser.add_argument("--tudo", action="store_true",
                        help="inclui os já liberados (reconferência), não só os pendentes")
    parser.add_argument("--ator", default="", help="pré-preenche quem vai atestar")
    parser.add_argument("--fontes", default=FONTES_PADRAO,
                        help="catálogo de fontes oficiais (padrão: o da skill)")
    args = parser.parse_args()

    try:
        dados = carregar_json(args.arquivo)
    except Exception as erro:
        print(json.dumps({"ok": False, "erro": str(erro)}, ensure_ascii=False))
        return 2
    if not isinstance(dados, dict) or dados.get("schema_version") not in VERSOES_ACEITAS:
        print(json.dumps({"ok": False, "erro": "contrato dsr.achados.v2 ou v3 obrigatório"},
                         ensure_ascii=False))
        return 2
    try:
        fontes = carregar_json(args.fontes)
        if not isinstance(fontes, dict) or not isinstance(fontes.get("hosts"), dict):
            raise ValueError("estrutura inválida")
    except Exception as erro:
        print(json.dumps({"ok": False, "erro": f"fontes_oficiais.json: {erro}"},
                         ensure_ascii=False))
        return 2

    formato = args.formato or ("folha" if args.saida.lower().endswith(".md") else "lista")
    if formato == "lista":
        conversa, lista = montar_lista(dados, fontes)
        if not conversa:
            print(json.dumps({"ok": True, "total": 0,
                              "resumo": "nenhum julgado pendente — nada a conferir"},
                             ensure_ascii=False))
            return 1
        with open(args.saida, "w", encoding="utf-8") as arquivo:
            json.dump(lista, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")
        total = len(lista["itens"])
        print(json.dumps({"ok": True, "total": total, "fora_da_peca": lista["fora_da_peca"],
                          "saida": args.saida, "texto_conversa": conversa,
                          "resumo": f"{total} julgado(s) a conferir: mostre `texto_conversa` "
                                    f"ao advogado como está"}, ensure_ascii=False))
        return 0

    texto_folha, total = montar(dados, args.tudo, args.ator, fontes)
    if not texto_folha:
        print(json.dumps({"ok": True, "total": 0,
                          "resumo": "nenhum julgado pendente — nada a conferir"},
                         ensure_ascii=False))
        return 1
    with open(args.saida, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto_folha)
        arquivo.write("\n")
    out = {"ok": True, "total": total, "saida": args.saida,
           "resumo": f"folha de conferência com {total} julgado(s) — abra, confira "
                     f"e devolva com `registrar_confirmacao_manual.py --folha`"}
    travados = [texto(a.get("id")) for a in _pendentes(dados, args.tudo)
                if aviso_host_travado(texto(a.get("official_url")), fontes)]
    if travados:
        out["enderecos_travados"] = travados
        out["resumo"] += (f"; {len(travados)} endereço(s) do DataJud ou do LexML não "
                          f"confirmam o teor, e a folha manda conferir no tribunal ou no órgão "
                          f"que publicou")
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
