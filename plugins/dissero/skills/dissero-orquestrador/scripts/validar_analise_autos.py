#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'validar_analise_autos.py — confere a análise de autos (cenário 6) como artefato com estado.'














































import argparse
import json
import os
import re
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(os.path.dirname(AQUI), "references", "analise_autos.schema.json")
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from schema_mini import validar_schema
except Exception:
    validar_schema = None
try:
    import numero_cnj
except Exception:
    numero_cnj = None

LACUNA = "não consta no material enviado"




FINALIDADES = {
    "assumir_causa": ("assumir a causa", "PRAZOS EM ABERTO e PROVIDÊNCIA",
                      "cenário 8 para o prazo; a peça, pela dissero-peticao"),
    "memoriais_ou_sustentacao": ("memoriais ou sustentação", "CONTROVÉRSIA",
                                 "preparacao-audiencias (cenário 9)"),
    "avaliar_risco": ("avaliar risco", "RISCOS", "analise-risco-processual"),
    "aceitar_caso": ("aceitar o caso", "MOLDURA e INTEGRIDADE",
                     "cenário 18 (conflito e entrada do cliente); pessoa jurídica, cenário 27"),
    "segunda_opiniao": ("segunda opinião", "CONTROVÉRSIA", "validar-tese"),
    "fichamento": ("só fichar", "MOLDURA e FATOS", "nenhuma; enquadramento só no bloco FORA DOS AUTOS"),
}


INTERDICOES = (
    ("certidao_intimacao", "tempestividade_e_prazo", "certidão de intimação"),
    ("contestacao", "art341_e_revelia", "contestação"),
    ("decisao_saneamento", "pontos_controvertidos_oficiais", "decisão de saneamento"),
)


_LACUNAS_TORTAS = {
    "", "-", "--", "?", "n/a", "na", "nd", "n/d", "null", "none", "[completar]", "completar",
    "nao informado", "nao informada", "desconhecido", "desconhecida", "sem informacao",
    "sem dado", "sem dados", "ignorado", "a definir", "nao identificado", "nao localizado",
    "nao encontrado", "nao disponivel",
}
_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PENDENCIA = re.compile(r"^==\[.+\]==$", re.S)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿]")


def _norm(texto):
    t = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c)).rstrip(".")


_LACUNA_N = _norm(LACUNA)



_SLOTS = {"cnj", "nome", "polo", "oab", "juizo", "magistrado", "classe", "rito", "valor_causa",
          "data_distribuicao", "ultimo_ato", "data", "certidao_intimacao", "contestacao",
          "decisao_saneamento", "citado_em", "alegado_em", "termo_final"}


_LOCALIZADOR = re.compile(r"(?<![a-z])(fls?|folhas?|pp?|pags?|paginas?|id|evento|ev|mov|seq)"
                          r"\.?\s*(n[o.]?\s*)?\d")
_AUSENCIA = re.compile(r"\bnao (foi |foram )?(junt|vei|consta|localiz|encontr|apresent)|\bausen"
                       r"|\bfalt|\binexist")
_DATA_LIVRE = r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2} de [a-z]+ de \d{4})"

_AFIRMA_TEMPESTIVO = re.compile(r"\b(é|foi|são|está|estão|seria|era|será)\s+(in)?tempestiv")

_AFIRMA_PRAZO = re.compile(
    r"tempestivamente|\btermo final\b"
    r"|\bultimo dia\b|\bate (o dia |dia )?" + _DATA_LIVRE +
    r"|\bprazo\b[^.;]{0,40}?\b(vence|venceu|vencera|termina|terminou|encerra|esgota|expira|fatal)")


def _e_lacuna(valor):
    """A fórmula fixa, sem caixa, com ou sem complemento depois de ';' ou '('."""
    if not isinstance(valor, str):
        return False
    n = _norm(valor)
    if n == _LACUNA_N:
        return True
    return n.startswith(_LACUNA_N) and n[len(_LACUNA_N):].lstrip()[:1] in (";", "(")


def lacuna_torta(valor, slot=True):
    'True se o valor é uma lacuna escrita fora da fórmula fixa. Fora de slot de dado, só'

    if not isinstance(valor, str) or _e_lacuna(valor):
        return False
    n = _norm(valor)
    return n in _LACUNAS_TORTAS or (slot and n.startswith("nao consta"))


def _e_slot(chave):
    return chave in _SLOTS or chave.startswith("folha")


def peca_presente(valor):
    """True se a peça-chave aponta folha, página, Id ou evento, sem dizer que falta."""
    if not isinstance(valor, str):
        return False
    n = _norm(valor)
    return bool(_LOCALIZADOR.search(n)) and not _AUSENCIA.search(n)


def afirma_prazo(texto):
    if not isinstance(texto, str):
        return False
    return bool(_AFIRMA_PRAZO.search(_norm(texto)) or _AFIRMA_TEMPESTIVO.search(texto.lower()))


class _Coletor:
    def __init__(self):
        self.problemas = []

    def __call__(self, codigo, caminho, mensagem):
        self.problemas.append({"codigo": codigo, "caminho": caminho, "mensagem": mensagem})


def _lista(x):
    return x if isinstance(x, list) else []


def _dic(x):
    return x if isinstance(x, dict) else {}


def _texto(add, valor, caminho, slot=True):
    """Campo de texto: preenchido, ou com a fórmula exata."""
    if lacuna_torta(valor, slot):
        add("LACUNA_FORA_DA_FORMULA", caminho,
            "campo sem dado se escreve \"%s\", não %r" % (LACUNA, valor))
    elif isinstance(valor, str) and not valor.strip():
        add("CAMPO_AUSENTE", caminho, "campo vazio")


def _varrer_textos(add, no, caminho, slot=False):
    'Toda string do artefato passa pela régua da lacuna (exceto enums, que o schema cobre).'

    if isinstance(no, dict):
        for k, v in no.items():
            _varrer_textos(add, v, "%s.%s" % (caminho, k), _e_slot(k))
    elif isinstance(no, list):
        for i, v in enumerate(no):
            _varrer_textos(add, v, "%s[%d]" % (caminho, i), slot)
    elif isinstance(no, str):
        _texto(add, no, caminho, slot)


def _contrato(analise):
    if validar_schema is None:
        return ["schema_mini.py indisponível ao lado do validador: o contrato não foi aplicado"]
    try:
        with open(SCHEMA, encoding="utf-8") as fh:
            schema = json.load(fh)
    except Exception as exc:
        return ["analise_autos.schema.json ilegível: %s" % exc]
    return [str(p) for p in (validar_schema(analise, schema) or [])]


def validar(analise):
    """Devolve a lista de problemas (cada um com `codigo`, `caminho`, `mensagem`)."""
    add = _Coletor()
    if not isinstance(analise, dict):
        add("CONTRATO_INVALIDO", "$", "a análise deve ser um objeto JSON")
        return add.problemas
    for p in _contrato(analise):
        add("CONTRATO_INVALIDO", "$", p)
    _varrer_textos(add, analise, "$")

    escopo = analise.get("escopo")
    if escopo in ("copia_parcial", "pecas_avulsas", "so_decisao") and analise.get("completa") is True:
        add("ESCOPO_PARCIAL_COMPLETO", "$.completa",
            "escopo %s não se declara completo: a análise sai PARCIAL" % escopo)
    if not _lista(analise.get("lido")):
        add("NADA_LIDO", "$.lido", "a entrega abre com o que foi efetivamente lido")


    pecas = _dic(analise.get("pecas_chave"))
    vedadas = {c.get("conclusao") for c in map(_dic, _lista(analise.get("conclusoes_interditadas")))}
    ausentes = set()
    for campo, conclusao, nome in INTERDICOES:
        valor = pecas.get(campo)
        if isinstance(valor, str) and not _e_lacuna(valor) and not peca_presente(valor):
            add("PECA_CHAVE_INDEFINIDA", "$.pecas_chave.%s" % campo,
                "a %s é a folha onde está (fl., Id ou evento e o número) ou \"%s\"; %r conta "
                "como ausente" % (nome, LACUNA, valor))
        if not peca_presente(valor):
            ausentes.add(campo)
            if conclusao not in vedadas:
                add("INTERDICAO_FALTANTE", "$.conclusoes_interditadas",
                    "sem %s, a conclusão %s tem de sair interditada" % (nome, conclusao))
    tempest_vedada = "certidao_intimacao" in ausentes or "tempestividade_e_prazo" in vedadas


    for i, prazo in enumerate(map(_dic, _lista(analise.get("prazos")))):
        cam = "$.prazos[%d]" % i
        if tempest_vedada:
            add("PRAZO_INTERDITADO", cam, "sem certidão de intimação, nada de prazo nem de "
                "tempestividade: o prazo vai para as conclusões interditadas")
        if prazo.get("origem") != "calcular_prazo.py":
            add("PRAZO_SEM_CALCULADORA", cam, "o termo final sai do calcular_prazo.py")
        if not _DATA_ISO.match(str(prazo.get("termo_final") or "")):
            add("TERMO_FINAL_INVALIDO", cam, "termo final em AAAA-MM-DD, como a calculadora devolve")
    prov = _dic(analise.get("providencia"))
    ate = prov.get("ate_quando")
    if isinstance(ate, dict):
        if tempest_vedada:
            add("PRAZO_INTERDITADO", "$.providencia.ate_quando",
                "com a tempestividade interditada, a providência não afirma prazo")
        if ate.get("origem") != "calcular_prazo.py":
            add("PRAZO_SEM_CALCULADORA", "$.providencia.ate_quando",
                "todo \"até quando\" processual sai do calcular_prazo.py")
        if not _DATA_ISO.match(str(ate.get("termo_final") or "")):
            add("TERMO_FINAL_INVALIDO", "$.providencia.ate_quando", "termo final em AAAA-MM-DD")
    if tempest_vedada:
        livres = [("$.providencia.proximo_ato", prov.get("proximo_ato"))]
        livres += [("$.respostas[%d].resposta" % i, r.get("resposta"))
                   for i, r in enumerate(map(_dic, _lista(analise.get("respostas"))))]
        for cam, texto in livres:
            if afirma_prazo(texto):
                add("PRAZO_INTERDITADO", cam, "com a tempestividade interditada, nada de prazo nem "
                    "de tempestividade afirmados em texto livre")
    for i, item in enumerate(_lista(prov.get("antes_de_protocolar"))):
        if not isinstance(item, str) or not _PENDENCIA.match(item.strip()) or _EMOJI.search(item):
            add("PENDENCIA_FORA_DO_FORMATO", "$.providencia.antes_de_protocolar[%d]" % i,
                "cada pendência no formato ==[...]==, sem emoji")


    ficha = _dic(analise.get("ficha"))
    cnj = ficha.get("cnj")
    if isinstance(cnj, str) and cnj.strip() and not _e_lacuna(cnj) and not lacuna_torta(cnj):
        if numero_cnj is None:
            add("CNJ_INVALIDO", "$.ficha.cnj", "numero_cnj.py indisponível: o CNJ não foi conferido")
        elif not numero_cnj.validar(cnj):
            add("CNJ_INVALIDO", "$.ficha.cnj",
                "o dígito verificador de %r não fecha (numero_cnj.py)" % cnj)


    fatos = [_dic(f) for f in _lista(analise.get("fatos"))]
    ids = {f.get("id") for f in fatos if isinstance(f.get("id"), str)}
    for i, fato in enumerate(fatos):
        cam = "$.fatos[%d]" % i
        est = fato.get("estatuto")
        fonte = _dic(fato.get("fonte"))
        fundamento = fato.get("fundamento")
        if est in ("alegado", "provado") and not (fonte.get("descricao") and fonte.get("folha")):
            add("FATO_SEM_FONTE", cam, "%s pede a peça ou o documento e a folha" % est)
        if est == "provado" and fonte and fonte.get("tipo") not in ("documento", "prova_produzida"):
            add("PROVADO_SEM_PROVA", cam, "fato só narrado em peça continua alegado: provado "
                "exige documento ou prova produzida")
        if est == "incontroverso" and not fundamento:
            add("INCONTROVERSO_SEM_FUNDAMENTO", cam, "incontroverso leva o fundamento: admissão "
                "expressa, art. 341 filtrado pelo 345, art. 374 ou documento não impugnado (art. 436)")
        if fundamento and est != "incontroverso":
            add("FUNDAMENTO_FORA_DO_INCONTROVERSO", cam,
                "fundamento de incontroverso em fato %s" % est)
        if fundamento == "art341_filtrado_345" and "contestacao" in ausentes:
            add("ART341_INTERDITADO", cam, "sem a contestação, nada de art. 341 nem de revelia")
        if est == "inferencia":
            base = [b for b in _lista(fato.get("deduzido_de")) if b in ids and b != fato.get("id")]
            if not base:
                add("INFERENCIA_SEM_BASE", cam, "inferência nomeia os fatos de que parte")


    pontos = [_dic(p) for p in _lista(analise.get("pontos_controvertidos"))]
    for i, ponto in enumerate(pontos):
        cam = "$.pontos_controvertidos[%d]" % i
        if ponto.get("origem") == "saneamento":
            if "decisao_saneamento" in ausentes or "pontos_controvertidos_oficiais" in vedadas:
                add("SANEAMENTO_INTERDITADO", cam, "sem a decisão de saneamento, o ponto nasce do "
                    "confronto das defesas e não é ponto controvertido oficial")
            elif not ponto.get("folha_saneamento"):
                add("PONTO_SEM_ORIGEM", cam, "ponto fixado no saneamento leva a folha da decisão")
        if ponto.get("estado_prova") in ("produzida", "indeferida") and not ponto.get("folha_prova"):
            add("PROVA_SEM_FOLHA", cam, "prova %s leva a folha" % ponto.get("estado_prova"))
    ids_pontos = [p.get("id") for p in pontos]
    respondidos = set()
    for i, resp in enumerate(map(_dic, _lista(analise.get("respostas")))):
        alvo = resp.get("ponto")
        if alvo not in ids_pontos:
            add("RESPOSTA_SEM_PONTO", "$.respostas[%d]" % i,
                "resposta a ponto %r que o quadro não tem" % alvo)
        elif isinstance(resp.get("resposta"), str) and resp["resposta"].strip():
            texto = resp["resposta"]
            if _e_lacuna(texto) or lacuna_torta(texto, slot=False) or _norm(texto) == "nao consta":
                add("RESPOSTA_LACUNA", "$.respostas[%d].resposta" % i,
                    "a fórmula de lacuna não responde ao ponto %r: diga o que os autos permitem "
                    "concluir sobre ele, ainda que seja a falta de prova" % alvo)
            else:
                respondidos.add(alvo)
    for i, pid in enumerate(ids_pontos):
        if pid not in respondidos:
            add("PONTO_SEM_RESPOSTA", "$.pontos_controvertidos[%d]" % i,
                "o ponto %r não tem resposta na conclusão" % pid)

    questao = analise.get("questao_central")
    if isinstance(questao, str) and questao.strip():
        if _e_lacuna(questao):
            if pontos:
                add("QUESTAO_CENTRAL_ABERTA", "$.questao_central",
                    "com ponto controvertido, a questão central é obrigatória")
        elif not questao.strip().endswith("?"):
            add("QUESTAO_CENTRAL_ABERTA", "$.questao_central",
                "a questão central é pergunta fechada, de resposta sim ou não")



    if analise.get("finalidade") == "avaliar_risco" and not isinstance(analise.get("riscos"), list):
        add("BLOCO_DA_FINALIDADE_AUSENTE", "$.riscos",
            "com a finalidade avaliar risco, a entrega abre pelo bloco RISCOS: grave `riscos` "
            "(lista vazia se não houver)")


    if analise.get("finalidade") == "fichamento":
        for i, d in enumerate(map(_dic, _lista(analise.get("direito")))):
            citado = d.get("citado_em")
            if not isinstance(citado, str) or not citado.strip() or _e_lacuna(citado):
                add("DIREITO_FORA_DOS_AUTOS", "$.direito[%d]" % i,
                    "no fichamento, direito que os autos não citam vai para fora_dos_autos")
    return add.problemas


def tabela_finalidade():
    return [{"finalidade": k, "rotulo": v[0], "primeiro_bloco": v[1], "rota_complementar": v[2]}
            for k, v in FINALIDADES.items()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Confere a análise de autos contra o contrato.")
    ap.add_argument("analise", nargs="?", help="arquivo JSON da análise")
    ap.add_argument("--tabela-finalidade", action="store_true",
                    help="imprime a tabela fixa da finalidade da leitura")
    args = ap.parse_args(argv)
    if args.tabela_finalidade:
        print(json.dumps({"ok": True, "finalidades": tabela_finalidade()}, ensure_ascii=False))
        return 0
    if not args.analise:
        print(json.dumps({"ok": False, "erro": "uso_invalido",
                          "mensagem": "informe o arquivo JSON da análise"}, ensure_ascii=False))
        return 2
    try:
        with open(args.analise, encoding="utf-8") as fh:
            analise = json.load(fh)
    except Exception as exc:
        print(json.dumps({"ok": False, "erro": "arquivo_ilegivel", "mensagem": str(exc)},
                         ensure_ascii=False))
        return 2
    problemas = validar(analise)
    print(json.dumps({"ok": not problemas, "problemas": problemas,
                      "codigos": sorted({p["codigo"] for p in problemas})}, ensure_ascii=False))
    return 0 if not problemas else 1


if __name__ == "__main__":
    sys.exit(main())
