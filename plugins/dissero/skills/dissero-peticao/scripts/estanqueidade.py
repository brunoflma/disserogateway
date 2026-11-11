#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'estanqueidade.py - o material INTERNO nunca vai aos autos, ainda que bem escrito.'
























































































from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib
import importlib.util
import json
import os
import re
import sys
import unicodedata

SCHEMA_VERSION = "dsr.estanqueidade.v1"
CLASSES = ("interno_nunca_aos_autos", "interno_pode_ser_reescrito", "externo")


_SEVERIDADE = {"externo": 0, "interno_pode_ser_reescrito": 1, "interno_nunca_aos_autos": 2}


ATIVO_POR_PADRAO = False





LIMITE_EVIDENCIA = 80

AQUI = os.path.dirname(os.path.abspath(__file__))


class EstanqueidadeError(ValueError):
    """Contrato de entrada violado. Nunca e classificacao - e uso errado do modulo."""






PROCEDENCIAS = {
    "painel_conselho": {
        "selo": "lacrada", "artefato": "painel do Conselho Revisor (HTML da sessao)",
        "razao": "traz voto, fundamentacao e placar de cada cadeira sobre a propria peca"},
    "conselho_status": {
        "selo": "lacrada", "artefato": "estado da sessao do Conselho Revisor",
        "razao": "mesmo conteudo do painel em forma de registro: voto, devolucao, pendencia"},
    "squad_state": {
        "selo": "lacrada", "artefato": "estado do squad",
        "razao": "etapa, bloqueio, reprovacao e motivo de devolucao sao gestao interna"},
    "painel_squad": {
        "selo": "lacrada", "artefato": "painel de acompanhamento do squad",
        "razao": "apresentacao do estado do squad; mesma natureza do estado"},
    "avaliacao_fragilidade": {
        "selo": "lacrada", "artefato": "avaliacao de fragilidade da propria tese",
        "razao": "registra onde a propria tese cede, inclusive o resultado da etapa "
                 "adversarial; nas maos do adversario, aponta onde atacar"},
    "relatorio_estrategico_interno": {
        "selo": "lacrada", "artefato": "relatorio estrategico interno",
        "razao": "registra o objetivo do cliente, o prognostico, os pontos fracos conhecidos e "
                 "o uso de cada pedido na negociacao"},
    "dossie_redacao": {
        "selo": "aberta", "artefato": "dossie de redacao",
        "razao": "material ja separado para a peca; ainda assim passa pelas demais regras"},
    "minuta_advogado": {
        "selo": "aberta", "artefato": "minuta escrita pelo advogado",
        "razao": "texto destinado aos autos por construcao"},
    "autos": {
        "selo": "aberta", "artefato": "peca ou documento ja dos autos",
        "razao": "ja e publico no processo"},
    "documento_do_cliente": {
        "selo": "aberta", "artefato": "documento entregue pelo cliente",
        "razao": "prova destinada a instruir; sigilo e outra dimensao, tratada alhures"},
    "pesquisa_confirmada": {
        "selo": "aberta", "artefato": "precedente ou norma confirmada em fonte oficial",
        "razao": "conteudo publico de tribunal ou diario oficial"},
}

LACRADAS = tuple(sorted(k for k, v in PROCEDENCIAS.items() if v["selo"] == "lacrada"))
ABERTAS = tuple(sorted(k for k, v in PROCEDENCIAS.items() if v["selo"] == "aberta"))




















MARCADORES_LACRE = (
    ("conselho_revisor", "deliberacao do Conselho Revisor",
     r"\bconselho\s+revisor\b",
     "o Conselho Revisor e a revisao interna do escritorio; o que ele delibera nao e ato do "
     "processo"),
    ("conselho_placar", "placar ou divisao de votos do conselho interno",
     r"\bconselho\s+(?:se\s+)?(?:dividiu|votou|devolveu)\b"
     r"|\bplacar\s+(?:do|da)\s+(?:conselho|sessao|revisao)\b",
     "o painel do conselho registra o voto de cada cadeira; na peca, ele mostra onde a "
     "propria banca hesitou"),
    ("cadeira_conselho", "cadeira do conselho interno",
     r"\bcadeira\s+de\s+(?:merito|coerencia|escrita|conformidade)\b",
     "merito, coerencia, escrita e conformidade sao os mandatos da revisao interna, nao "
     "orgaos julgadores"),
    ("tese_propria_fraca", "avaliacao de fragilidade da propria tese",
     r"\bnoss[ao]\s+(?:tese|argumento|pedido|posicao)\s+(?:e|esta|seria|fica)\s+"
     r"(?:muito\s+|bastante\s+)?(?:fraca|fraco|fragil|vulneravel|insustentavel|arriscada|arriscado)\b"
     r"|\bnosso\s+ponto\s+fraco\b"
     r"|\bnossa\s+(?:maior\s+)?fragilidade\b",
     "e o registro da etapa adversarial na primeira pessoa da banca; na peca, indica ao "
     "adversario onde atacar"),
    ("prognostico_de_derrota", "prognostico interno de derrota",
     r"\b(?:perdemos|perderemos|vamos\s+perder|podemos\s+perder)\s+se\b"
     r"|\bchance\s+real\s+de\s+perder\b",
     "o pior cenario e exercicio da etapa adversarial e conversa com o cliente; nos autos, "
     "le-se como admissao"),
    ("pedido_de_barganha", "pedido incluido para negociar",
     r"\b(?:existe|serve|entrou|foi\s+incluid[ao])\s+(?:apenas\s+|so\s+|somente\s+)?para\s+negocia"
     r"|\bmoeda\s+de\s+troca\b",
     "o objetivo de negociar e escolha da estrategia; declarado na peca, tira do pedido o "
     "proprio fundamento"),
    ("estado_do_squad", "estado interno do squad",
     r"\bsquad\b|\bcheckpoint\b",
     "etapa e checkpoint sao o controle de producao do escritorio; nao existem nos autos"),
    ("painel_interno", "painel interno de acompanhamento",
     r"\bpainel\s+(?:do\s+squad|do\s+conselho|interno)\b",
     "o painel e instrumento de gestao do escritorio"),
    ("pendencia_interna", "pendencia interna de pesquisa ou conferencia",
     r"\bpendencia\s+(?:interna|do\s+escritorio)\b"
     r"|\bainda\s+nao\s+(?:pesquisamos|confirmamos|verificamos)\b"
     r"|\bnao\s+chegamos\s+a\s+pesquisar\b",
     "a pendencia de pesquisa barra o protocolo por outro gate; escrita na peca, anuncia "
     "que a fundamentacao esta incompleta"),
)




MARCADORES_AMBIGUOS = (
    ("fragilidade_sem_dono", "fragilidade sem dono declarado",
     r"\bfragil\b|\bfrageis\b|\bfragilidade\b",
     "a fragilidade pode ser da prova do adversario (peca legitima) ou da propria tese"),
    ("ponto_fraco_sem_dono", "ponto fraco sem dono declarado",
     r"\bponto\s+fraco\b",
     "o texto nao diz de qual lado e o ponto fraco"),
    ("risco_de_derrota", "risco de derrota sem dono declarado",
     r"\brisco\s+de\s+(?:perder|derrota|improcedencia|sucumbencia)\b",
     "pode ser o risco aceito pela banca ou argumento sobre o risco da parte contraria"),
    ("prognostico_de_exito", "prognostico de exito",
     r"\b(?:chance|chances|probabilidade)\s+de\s+exito\b",
     "pode ser prognostico interno ou citacao de jurimetria publica"),
    ("tese_fraca_sem_dono", "tese qualificada como fraca sem dono declarado",
     r"\btese\s+(?:fraca|arriscada|vulneravel|insustentavel)\b",
     "a tese fraca pode ser a da parte contraria"),
)

_LACRE_RX = tuple((i, r, re.compile(rx), e) for i, r, rx, e in MARCADORES_LACRE)
_AMBIGUO_RX = tuple((i, r, re.compile(rx), e) for i, r, rx, e in MARCADORES_AMBIGUOS)



def normalizar(texto):
    'Minuscula, sem acento, espaco em branco colapsado.'






    s = unicodedata.normalize("NFD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def sha256_texto(texto):
    return hashlib.sha256(str(texto or "").encode("utf-8")).hexdigest()



def _modulo_vizinho(nome):
    'O modulo `nome` deste diretorio (espelhado de `_shared/` pelo `sincronizar_shared.py`),'


    try:
        return importlib.import_module(nome)
    except Exception:
        pass
    caminho = os.path.join(AQUI, nome + ".py")
    if not os.path.isfile(caminho):
        return None
    try:
        spec = importlib.util.spec_from_file_location(nome, caminho)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo
    except Exception:
        return None


def carregar_vocabulario():
    'Devolve o modulo `vocabulario_interno` (o L16), ou None se ele nao estiver ao alcance.'




    return _modulo_vizinho("vocabulario_interno")



_CAMPOS_TRECHO = {"texto", "procedencia", "trecho_id", "declaracao_advogado"}
_CAMPOS_DECLARACAO = {"classe", "por", "em", "razao"}


def _validar_trecho(trecho):
    if not isinstance(trecho, dict):
        raise EstanqueidadeError("trecho deve ser objeto")
    desconhecidos = sorted(set(trecho) - _CAMPOS_TRECHO)
    if desconhecidos:
        raise EstanqueidadeError("campo nao permitido no trecho: %s" % ", ".join(desconhecidos))
    if not isinstance(trecho.get("texto"), str) or not trecho["texto"].strip():
        raise EstanqueidadeError("texto obrigatorio e nao vazio")
    if "trecho_id" in trecho and not isinstance(trecho["trecho_id"], str):
        raise EstanqueidadeError("trecho_id deve ser texto")
    dec = trecho.get("declaracao_advogado")
    if dec is not None:
        if not isinstance(dec, dict):
            raise EstanqueidadeError("declaracao_advogado deve ser objeto")
        sobra = sorted(set(dec) - _CAMPOS_DECLARACAO)
        if sobra:
            raise EstanqueidadeError("campo nao permitido na declaracao: %s" % ", ".join(sobra))
        if dec.get("classe") not in CLASSES:
            raise EstanqueidadeError("declaracao_advogado.classe deve ser uma de %s" % (CLASSES,))
        for campo in ("por", "em"):
            if not isinstance(dec.get(campo), str) or not dec[campo].strip():
                raise EstanqueidadeError("declaracao_advogado.%s obrigatorio" % campo)


def _validar_limite_evidencia(valor):
    'O limite e arbitrario, mas nao pode ser absurdo: corte de zero apagaria a evidencia.'



    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        raise EstanqueidadeError("limite_evidencia deve ser inteiro >= 1")


def _motivo(regra, rotulo, evidencia, explicacao, limite=LIMITE_EVIDENCIA):
    ev = str(evidencia or "")
    if len(ev) > limite:
        ev = ev[:limite] + "..."
    return {"regra": regra, "rotulo": rotulo, "evidencia": ev, "explicacao": explicacao}


def _achados(normalizado, tabela):
    saida = []
    for ident, rotulo, rx, explicacao in tabela:
        m = rx.search(normalizado)
        if m:
            saida.append((ident, rotulo, m.group(0), explicacao))
    return saida



def classificar(trecho, hoje=None, vocab=None, limite_evidencia=LIMITE_EVIDENCIA):
    'Classifica UM trecho candidato. Devolve o registro (`dsr.estanqueidade.v1`).'


















    _validar_limite_evidencia(limite_evidencia)
    _validar_trecho(trecho)
    texto = trecho["texto"]
    normalizado = normalizar(texto)
    proc = trecho.get("procedencia")
    dec = trecho.get("declaracao_advogado")

    registro = {
        "schema_version": SCHEMA_VERSION,
        "avaliado_em": (hoje or dt.date.today()).isoformat(),
        "trecho_id": trecho.get("trecho_id") or "",
        "trecho_sha256": sha256_texto(texto),
        "procedencia": proc if isinstance(proc, str) else "",
        "conclusivo": False,
        "classe": None,
        "pode_ir_aos_autos": False,
        "reescrita_permitida": False,
        "regra_decisoria": "",
        "motivos": [],
        "declaracao_advogado": dict(dec) if isinstance(dec, dict) else None,
        "registro_e_interno": True,
    }

    def mot(regra, rotulo, evidencia, explicacao):
        registro["motivos"].append(_motivo(regra, rotulo, evidencia, explicacao, limite_evidencia))

    def fechar(regra, classe):
        registro["regra_decisoria"] = regra
        registro["classe"] = classe
        registro["conclusivo"] = classe is not None
        registro["pode_ir_aos_autos"] = classe == "externo"
        registro["reescrita_permitida"] = classe == "interno_pode_ser_reescrito"
        return registro


    if not isinstance(proc, str) or proc not in PROCEDENCIAS:
        mot("P0", "procedencia nao declarada ou fora da tabela",
            proc if isinstance(proc, str) else "",
            "sem origem declarada o modulo nao classifica; declare uma de %s"
            % (tuple(sorted(PROCEDENCIAS)),))
        return fechar("P0", None)

    lacre = _achados(normalizado, _LACRE_RX)
    ficha = PROCEDENCIAS[proc]


    if ficha["selo"] == "lacrada":
        mot("P1", "procedencia lacrada: %s" % ficha["artefato"], proc, ficha["razao"])
        for _i, rotulo, termo, explicacao in lacre:
            mot("M1", rotulo, termo, explicacao)
        return _aplicar_declaracao(registro, fechar("P1", "interno_nunca_aos_autos"),
                                   dec, mot)


    if lacre:
        for _i, rotulo, termo, explicacao in lacre:
            mot("M1", rotulo, termo, explicacao)
        return _aplicar_declaracao(registro, fechar("M1", "interno_nunca_aos_autos"),
                                   dec, mot)





    ambiguos = _achados(normalizado, _AMBIGUO_RX)
    if ambiguos:
        for _i, rotulo, termo, explicacao in ambiguos:
            mot("M2", rotulo, termo, explicacao)
        if not dec:
            mot("M2", "declaracao do advogado necessaria", "",
                "o modulo nao adivinha de quem e a fragilidade; declare a classe do trecho")
            return fechar("M2", None)


    modulo = vocab if vocab is not None else carregar_vocabulario()
    if modulo is None:
        mot("V0", "vocabulario interno (L16) indisponivel", "",
            "sem a lista do L16 nao se pode afirmar que o trecho esta limpo de encanamento")
        return _aplicar_declaracao(registro, fechar("V0", None), dec, mot, bool(ambiguos))
    try:
        residuos = modulo.residuos(texto)
    except Exception as erro:
        mot("V0", "vocabulario interno (L16) falhou", erro.__class__.__name__,
            "a medida do L16 nao pode ser concluida; nao se afirma `externo` sem ela")
        return _aplicar_declaracao(registro, fechar("V0", None), dec, mot, bool(ambiguos))
    if residuos:
        for r in residuos:
            mot("V1", "residuo de vocabulario interno: %s" % r.get("classe", "?"),
                str(r.get("termo", "")),
                "defeito de forma: ha equivalente em portugues de advogado; o texto sobrevive "
                "a troca, que cabe ao autor fazer")
        return _aplicar_declaracao(registro, fechar("V1", "interno_pode_ser_reescrito"),
                                   dec, mot, bool(ambiguos))


    if ambiguos:
        mot("E1", "nenhum marcador de lacre, origem aberta, sem residuo do L16", proc,
            "so restava o marcador ambiguo, que a declaracao do advogado resolve")
    else:
        mot("E1", "nenhum marcador, origem aberta, sem residuo do L16", proc,
            "nada encontrado que impeca o trecho de ir aos autos")
    return _aplicar_declaracao(registro, fechar("E1", "externo"), dec, mot, bool(ambiguos))


def _aplicar_declaracao(registro, fechado, dec, mot, resolve_ambiguidade=False):
    'Declaracao do advogado sobre trecho JA classificado: restringe sempre, afrouxa nunca.'

















    if not isinstance(dec, dict):
        return fechado
    atual = fechado.get("classe")
    pedida = dec.get("classe")
    if pedida not in _SEVERIDADE:
        return fechado

    def selar(classe):
        registro["classe"] = classe
        registro["conclusivo"] = classe is not None
        registro["regra_decisoria"] = "D1"
        registro["pode_ir_aos_autos"] = classe == "externo"
        registro["reescrita_permitida"] = classe == "interno_pode_ser_reescrito"

    if atual is None:
        if pedida == "externo":
            mot("D2", "declaracao de `externo` recusada sobre apuracao inconclusiva",
                "%s pedido por %s em %s" % (pedida, dec.get("por"), dec.get("em")),
                "a apuracao nao se concluiu (o L16 nao pode ser medido); afirmar `externo` "
                "aqui seria afirmar o que nao se apurou. A recusa permanece e a tentativa "
                "fica registrada")
            return fechado
        mot("D1", "classe restringida pelo advogado sobre apuracao inconclusiva",
            "%s por %s em %s" % (pedida, dec.get("por"), dec.get("em")),
            "selar o trecho como interno restringe, e restringir e sempre permitido - mesmo "
            "sem a apuracao concluida")
        selar(pedida)
        return fechado

    if _SEVERIDADE[pedida] > _SEVERIDADE[atual]:
        mot("D1", "classe restringida pelo advogado",
            "%s -> %s por %s" % (atual, pedida, dec.get("por")),
            "rebaixar para classe mais restritiva e sempre permitido")
        selar(pedida)
    elif _SEVERIDADE[pedida] < _SEVERIDADE[atual]:
        mot("D2", "declaracao do advogado recusada",
            "%s pedido sobre %s por %s" % (pedida, atual, dec.get("por")),
            "afrouxar a classificacao nao esta a disposicao de quem redige; a classificacao "
            "apurada permanece e a tentativa fica registrada")
    elif resolve_ambiguidade:
        mot("D1", "classe declarada pelo advogado",
            "%s por %s em %s" % (pedida, dec.get("por"), dec.get("em")),
            "ambiguidade resolvida por pessoa identificada, nao por texto; a classe declarada "
            "coincide com a apurada, que e o teto")
        selar(pedida)
    return fechado



def avaliar_conjunto(trechos, ativado=None, hoje=None, vocab=None,
                     limite_evidencia=LIMITE_EVIDENCIA):
    'Classifica uma lista de trechos. So BARRA quando explicitamente ativada.'







    _validar_limite_evidencia(limite_evidencia)
    ligado = ATIVO_POR_PADRAO if ativado is None else bool(ativado)
    modulo = vocab if vocab is not None else carregar_vocabulario()
    registros, erros = [], []
    for indice, t in enumerate(trechos or []):
        try:
            registros.append(classificar(t, hoje=hoje, vocab=modulo,
                                         limite_evidencia=limite_evidencia))
        except EstanqueidadeError as erro:
            erros.append({"indice": indice, "erro": str(erro)})
    retidos = [r for r in registros if not r["pode_ir_aos_autos"]]
    if erros:
        veredito = "contrato_invalido"
    elif not ligado:
        veredito = "observado"
    elif retidos:
        veredito = "retido"
    else:
        veredito = "liberado"
    return {
        "schema_version": SCHEMA_VERSION,
        "ativo": ligado,
        "veredito": veredito,
        "total": len(registros),
        "retidos": [r["trecho_id"] or r["trecho_sha256"][:12] for r in retidos],
        "registros": registros,
        "erros": erros,
    }



def _schema_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "schema_estanqueidade.json")


def carregar_schema():
    with open(_schema_path(), encoding="utf-8") as f:
        return json.load(f)


def _validador_mini():
    """`schema_mini.validar_schema`, ou None se o validador nao estiver ao alcance."""
    modulo = _modulo_vizinho("schema_mini")
    return getattr(modulo, "validar_schema", None) if modulo is not None else None


_SHA_RX = re.compile(r"^[0-9a-f]{64}$")


def validar_registro(registro, schema=None, validar_schema=None):
    'Erros do registro: os do schema (validador da casa) mais os que ele nao alcanca.'





    erros = []
    validador = validar_schema if validar_schema is not None else _validador_mini()
    if validador is None:
        erros.append("schema_mini indisponivel: o registro nao pode ser validado contra o schema")
    else:
        erros.extend(validador(registro, schema if schema is not None else carregar_schema()))
    if not isinstance(registro, dict):
        return erros
    sha = registro.get("trecho_sha256")
    if not isinstance(sha, str) or not _SHA_RX.match(sha):
        erros.append("trecho_sha256 deve ser sha-256 em minusculas")
    classe = registro.get("classe")
    if registro.get("conclusivo") is not (classe is not None):
        erros.append("conclusivo tem de casar com a presenca de classe")
    if registro.get("pode_ir_aos_autos") is not (classe == "externo"):
        erros.append("pode_ir_aos_autos so e verdadeiro com classe=externo")
    if registro.get("reescrita_permitida") is not (classe == "interno_pode_ser_reescrito"):
        erros.append("reescrita_permitida so e verdadeiro com classe=interno_pode_ser_reescrito")
    if not registro.get("motivos"):
        erros.append("registro sem motivo declarado")
    return erros



def _ler_lote(caminho):
    trechos = []
    with open(caminho, encoding="utf-8") as f:
        for numero, linha in enumerate(f, 1):
            if not linha.strip():
                continue
            try:
                trechos.append(json.loads(linha))
            except ValueError as erro:
                raise EstanqueidadeError("linha %d do lote nao e JSON: %s" % (numero, erro))
    return trechos


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Estanqueidade: o trecho candidato pode ir aos autos?")
    p.add_argument("--procedencia", help="origem declarada (ver --listar-procedencias)")
    p.add_argument("--texto")
    p.add_argument("--texto-arquivo")
    p.add_argument("--trecho-id", default="")
    p.add_argument("--lote", help="JSONL, um trecho por linha")
    p.add_argument("--ativar", action="store_true",
                   help="liga o veredito de barra (desligado por padrao)")
    p.add_argument("--limite-evidencia", type=int, default=LIMITE_EVIDENCIA,
                   help="corte do trecho de evidencia no registro (padrao %d, arbitrario e "
                        "configuravel; nao ha o que medir aqui)" % LIMITE_EVIDENCIA)
    p.add_argument("--listar-procedencias", action="store_true")
    args = p.parse_args(argv)

    if args.listar_procedencias:
        print(json.dumps({"lacradas": list(LACRADAS), "abertas": list(ABERTAS),
                          "tabela": PROCEDENCIAS}, ensure_ascii=False, indent=2))
        return 0
    try:
        if args.lote:
            trechos = _ler_lote(args.lote)
        else:
            texto = args.texto
            if args.texto_arquivo:
                with open(args.texto_arquivo, encoding="utf-8") as f:
                    texto = f.read()
            if texto is None or not args.procedencia:
                raise EstanqueidadeError("informe --lote, ou --procedencia com --texto/--texto-arquivo")
            trechos = [{"texto": texto, "procedencia": args.procedencia,
                        "trecho_id": args.trecho_id}]
        saida = avaliar_conjunto(trechos, ativado=args.ativar,
                                 limite_evidencia=args.limite_evidencia)
    except EstanqueidadeError as erro:
        print(json.dumps({"ok": False, "erro": str(erro)}, ensure_ascii=False))
        return 2
    except OSError as erro:
        print(json.dumps({"ok": False, "erro": "arquivo ilegivel: %s" % erro}, ensure_ascii=False))
        return 2
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    if saida["veredito"] == "contrato_invalido":
        return 2
    return 1 if saida["veredito"] == "retido" else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
