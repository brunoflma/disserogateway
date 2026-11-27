#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'folha_atestacao.py — o que fecha o ciclo entre DESCOBERTA e CONFIRMAÇÃO.'

















































from __future__ import annotations

import argparse
import json
import os
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
    ("orgao_julgador", "Órgão julgador"),
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


def _sem_recibo(achado):
    'Confirmação humana que o recibo da tela não sustenta (a antiga, da conversa, da folha ou do'

    try:
        import recibo_conferencia
    except Exception:
        return (achado.get("verification") or {}).get("method") == "human"
    return recibo_conferencia.confirmacao_sem_recibo_valido(achado)


def _falta_ratificar(achado):
    """Teor conferido pela máquina sem a ratificação da tela gravada (D2): pendente."""
    v = achado.get("verification") or {}
    return (v.get("method") == "automatic" and v.get("result") == "confirmed"
            and not isinstance(v.get("ratificacao"), dict))


def da_maquina(achado):
    '(fonte, data) da verificação automática que confirmou o teor na fonte, ou None. Sem a data,'

    v = achado.get("verification") or {}
    if v.get("method") != "automatic" or v.get("result") != "confirmed":
        return None
    fonte = texto(v.get("final_url")) or texto(achado.get("official_url"))
    em = texto(v.get("checked_at"))
    if len(fonte) < 3 or len(em) < 10:
        return None
    return fonte, em


def _pendentes(dados, tudo=False):
    saida = []
    for achado in (dados.get("achados") or []):
        if not isinstance(achado, dict):
            continue
        status = achado.get("use_status")
        if status == "prohibited":
            continue


        if tudo or status == "pending" or (status == "allowed" and (_sem_recibo(achado)
                                                                    or _falta_ratificar(achado))):
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
        "A confirmação de cada julgado se faz no Minha banca, na tela de conferência: qualquer "
        "pessoa da banca, entrando com o próprio login, marca se confere e, quando estiver tudo "
        "certo, clica Encerrar e liberar; o nome dela fica gravado. Esta folha serve para conferir com calma e para apontar o que NÃO confere: "
        "devolvida, os julgados marcados como não confere saem da peça.",
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
            "**Resultado da conferência** (o que confere se confirma no Minha banca).", "",
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
    '(itens, fora_da_peca): os pendentes que sustentam a peça; sem nenhum selecionado, todos.'


    pend = _pendentes(dados)
    sel = [a for a in pend if a.get("selected_for_use")]
    return (sel, len(pend) - len(sel)) if sel else (pend, 0)


def _data_br(iso):
    t = texto(iso)[:10]
    return f"{t[8:10]}/{t[5:7]}/{t[0:4]}" if len(t) == 10 and t[4] == t[7] == "-" else t


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
        maquina = da_maquina(achado)
        if maquina:
            moldura = (f"teor conferido pela máquina na fonte em {_data_br(maquina[1])}; falta "
                       f"ratificar")
        elif conferida:
            moldura = f"moldura conferida na fonte em {conferida}"
        else:
            campos = [f"{rot.lower()} {texto(citation.get(c))}"
                      for c, rot in _ROTULOS_MOLDURA[:5] if texto(citation.get(c))]
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
                         "official_url": url, "origem": "maquina" if maquina else "pessoa",
                         "syllabus_sha256": sha256_texto(achado.get("syllabus_literal"))})
    linhas += MENSAGEM_CONFERENCIA
    if fora:
        linhas.append("")
        linhas.append(f"Outros {fora} julgado(s) pendente(s) não estão na minuta e ficaram fora "
                      f"desta conferência.")
    n_maquina = sum(1 for a in itens if da_maquina(a))
    cabeca = [f"Falta: conferir na fonte oficial {len(itens)} julgado(s) que sustentam a "
              f"minuta. Enquanto a conferência não for encerrada, a peça não é entregue.", ""]
    if n_maquina:
        cabeca += [f"{n_maquina} deles a máquina já conferiu na fonte: na tela, vêm marcados como "
                   f"confere, e basta ratificar (ou desmarcar, se não conferir).", ""]
    antigos = [a for a in itens if a.get("use_status") == "allowed" and not da_maquina(a)]
    if antigos:
        cabeca += [f"{len(antigos)} deles já tinha(m) sido conferido(s) pela conversa, pela folha "
                   f"ou pelo PDF, que não confirmam mais: só a conferência no Minha banca vale.",
                   ""]
    return "\n".join(cabeca + linhas), {"schema_version": "dsr.conferencia_pendente.v1",
                                        "tema": texto(dados.get("tema")), "fora_da_peca": fora,
                                        "itens": registro}






MENSAGEM_CONFERENCIA = [
    "Quem resolve: confere qualquer pessoa da banca, entrando com o próprio login no Minha banca; "
    "o nome de quem conferiu fica gravado, e o responsável pela peça continua sendo o advogado que "
    "a assina. Encerra o titular da banca ou quem abriu a conferência: só eles veem o botão "
    "Encerrar e liberar.",
    "",
    "Como: vou abrir a conferência e mostrar o endereço. Abra a conferência no Minha banca e "
    "revise: cada julgado é comparado com a fonte oficial e marcado como confere, não confere (sai "
    "da peça) ou pendente, com o motivo; os que a máquina já conferiu vêm marcados como confere, "
    "para ratificar. Enquanto a conferência estiver aberta, dá para mudar tudo. Quando estiver "
    "tudo certo, o titular da banca ou quem abriu a conferência clica Encerrar e liberar: só o "
    "encerramento libera a peça. Depois me avise, e eu busco o resultado.",
    "",
    "Se algum julgado não confere e você já sabe, pode dizer aqui mesmo, por exemplo \"o 3 não "
    "confere\", que ele sai da peça. A confirmação, porém, só vale feita no Minha banca.",
]


def itens_da_tela(dados):
    'Itens no formato de entrada da tela de conferência: id, tipo e o CONTEÚDO que a tela'









    import registrar_confirmacao_manual as rcm
    itens, _ = _para_conferir(dados)
    saida = []
    for achado in itens:
        tipo_ancora, conteudo, sha, _ = rcm.conteudo_da_tela(achado)
        item = {"id": texto(achado.get("id")), "tipo": "julgado", **conteudo, "sha256": sha,
                "origem": "pessoa"}
        maquina = da_maquina(achado)
        if maquina and tipo_ancora == "endereco":


            item["origem"] = "maquina"
            item["maquina"] = {"fonte": maquina[0], "em": maquina[1]}
        if tipo_ancora == "nenhuma" or not conteudo["texto"]:
            item["so_veto"] = True
        saida.append(item)
    return saida


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
    parser.add_argument("--tela", default="",
                        help="(lista) onde gravar os itens da tela de conferência (padrão: "
                             "CONFERENCIA_TELA.json ao lado da lista)")
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
        tela_path = args.tela or os.path.join(os.path.dirname(os.path.abspath(args.saida)),
                                              "CONFERENCIA_TELA.json")
        import registrar_confirmacao_manual as rcm
        tela = {"schema_version": "dsr.conferencia_tela.v1", "tema": texto(dados.get("tema")),
                "responsavel": rcm.ator_do_perfil(), "itens": itens_da_tela(dados)}
        with open(tela_path, "w", encoding="utf-8") as arquivo:
            json.dump(tela, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")
        total = len(lista["itens"])
        print(json.dumps({"ok": True, "total": total, "fora_da_peca": lista["fora_da_peca"],
                          "saida": args.saida, "tela": tela_path, "texto_conversa": conversa,
                          "proximo_passo": (
                              "Mostre `texto_conversa` como está. Depois chame "
                              "`preparar_conferencia` do conector dissero com os itens de "
                              f"{os.path.basename(tela_path)} (e o responsável, se houver) e "
                              "mostre o endereço devolvido. Quando avisarem que clicaram "
                              "Encerrar e liberar, chame `recibo_da_conferencia`, grave o "
                              "envelope devolvido (só o do encerramento libera; o da conferência "
                              "aberta é andamento), sem "
                              "mexer em nada, num arquivo .json e registre com "
                              "`registrar_confirmacao_manual.py achados.json --recibo "
                              "<envelope.json> -o achados.json`. Veto dito na conversa: "
                              "`--lista` com `--nao-confere` (e `--quem-conferiu` se não foi o "
                              "advogado); confirmação por ali não é gravada."),
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
