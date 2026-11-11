#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Pseudonimização jurídica brasileira, local e experimental.'

















from __future__ import annotations

import argparse
import hashlib
import json
import time
import os
import re
import sys
import unicodedata
import datetime as _dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detectar_injecao
import numero_cnj

VERSAO = "dsr.pseudonimizacao.local.v1"
ENV_ENABLE = "DSR_PSEUDONIMIZACAO_EXPERIMENTAL"


VALORES_DESLIGA = ("0", "false", "nao", "não", "off")
ENV_LOCAL_ROOT = "DSR_PSEUDONIMIZACAO_LOCAL_ROOT"






CLOUD_SEGMENTS = {
    "onedrive", "dropbox", "google drive", "googledrive", "icloud", "box",
    "nextcloud", "owncloud", "pcloud", "mega", "syncthing", "sharepoint",
}
CLOUD_CURTOS = {"box", "mega"}


def _componente_em_nuvem(componente):
    """True quando o nome de UM componente do caminho indica pasta sincronizada com nuvem."""
    nome = str(componente).casefold()
    palavras = [p for p in re.split(r"[\W_]+", nome) if p]
    frase = " ".join(palavras)
    for marcador in CLOUD_SEGMENTS:
        if marcador in CLOUD_CURTOS:
            if any(p in (marcador, marcador + "sync", marcador + "drive") for p in palavras):
                return True
        elif marcador in nome or marcador in frase:
            return True
    return False


def capacidade_ligada(ambiente=None):
    """True salvo desligamento EXPLICITO por DSR_PSEUDONIMIZACAO_EXPERIMENTAL=0."""
    env = os.environ if ambiente is None else ambiente
    return str(env.get(ENV_ENABLE, "")).strip().lower() not in VALORES_DESLIGA







_ESP = r"(?:\r\n|\s)"
_SEP = r"(?:(?:\.|" + _ESP + r")" + _ESP + r"?)?"
_SEP_DV = r"(?:(?:-|" + _ESP + r")" + _ESP + r"?)?"
CPF_RX = re.compile(r"(?<!\d)\d{3}" + _SEP + r"\d{3}" + _SEP + r"\d{3}" + _SEP_DV + r"\d{2}(?!\d)")
CNPJ_RX = re.compile(r"(?<!\d)\d{2}" + _SEP + r"\d{3}" + _SEP + r"\d{3}(?:(?:/|" + _ESP + r")" + _ESP
                     + r"?)?\d{4}" + _SEP_DV + r"\d{2}(?!\d)")
PIS_RX = re.compile(r"(?<!\d)\d{3}" + _SEP + r"\d{5}" + _SEP + r"\d{2}" + _SEP_DV + r"\d(?!\d)")




OAB_RX = re.compile(
    r"\bOAB(?:\s*[/\-]\s*|\s+)(?:[A-Z]{2}\s*)?(?:\d{1,3}(?:\.\d{3})+|\d{3,8})(?:\s*[-/]\s*[A-Z])?\b",
    re.I)






EMAIL_RX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
TELEFONE_RX = re.compile(
    r"(?<![\d.\-/])(?:\+?55[\s.\-]?)?(?:\(\d{2}\)(?:\r\n|\s)?|\b\d{2}(?:\r\n|[\s.\-]))(?P<v9>9?\d{4})"
    r"(?:\r\n|[\s.\-])?\d{4}(?![\d\-/])")
_ANCORA_TELEFONE = re.compile(r"(?:tel(?:efone)?|cel(?:ular)?|fone|whatsapp|contato)\b\.?\s*[:\-]?\s*$", re.I)
CEP_RX = re.compile(r"(?<![\d\-])\d{5}-\d{3}(?![\d\-])")
CEP_ANCORADO_RX = re.compile(r"\bCEP\b\.?[:\s]*(?P<v>\d{5}\.?\d{3})(?![\d\-])", re.I)
RG_RX = re.compile(
    r"\b(?:RG|R\.G\.|identidade|carteira\s+de\s+identidade|c[eé]dula\s+de\s+identidade)\b\.?"
    r"\s*(?:n[º°.o]?\s*)?[:\s]*(?P<v>\d{1,2}\.?\d{3}\.?\d{3}-?[\dXx])(?![\dXx])", re.I)
CONTA_RX = re.compile(
    r"\b(?:ag(?:[eê]ncia)?\.?|conta(?:[\s-]+corrente)?|c/c|c\.c\.|cc)\b\.?\s*(?:n[º°.o]?\s*)?[:\s]*"
    r"(?P<v>(?!(?:19|20)\d{2}\b)\d{3,12}(?:-[\dXx])?)(?![\d\-])", re.I)
DATA_NASC_RX = re.compile(
    r"\b(?:nascid[oa]\s+em|data\s+de\s+nascimento|nascimento|nasc\.?)\b[:\s]*(?P<v>\d{2}/\d{2}/\d{4})\b", re.I)
ENDERECO_RX = re.compile(
    r"\b(?P<v>(?:Rua|R\.|Avenida|Av\.|Travessa|Tv\.|Alameda|Al\.|Pra[çc]a|P[çc]a\.|Rodovia|Rod\.|Estrada|Estr\.|"
    r"Largo|Quadra|Q\.|Lote|Sítio|S[íi]tio|Fazenda)\s+[^\n,;]{2,60}?"
    r"(?:,\s*(?:n[º°.o]?\s*)?\d+[A-Za-z]?|\s+n[º°.o]\s*\d+[A-Za-z]?|\s+s/n\b)"
    r"(?:,\s*(?:apto?\.?|apartamento|sala|bloco|casa|lote|quadra|km|conj\.?|conjunto)\s*[^\n,;]{1,25})?)")


def _telefone_ok(texto, m):
    'Telefone e o padrao mais parecido com outros numeros: exige DDD entre parenteses OU'

    if m.group(0).lstrip("+5 ").startswith("("):
        return True
    return bool(_ANCORA_TELEFONE.search(texto[max(0, m.start() - 24):m.start()]))



PADROES = (
    ("EMAIL", EMAIL_RX, 0.95, None),
    ("CEP", CEP_RX, 0.9, None),
    ("CEP", CEP_ANCORADO_RX, 0.9, None),
    ("TELEFONE", TELEFONE_RX, 0.85, _telefone_ok),
    ("RG", RG_RX, 0.85, None),
    ("CONTA", CONTA_RX, 0.8, None),
    ("DATA_NASC", DATA_NASC_RX, 0.85, None),
    ("ENDERECO", ENDERECO_RX, 0.8, None),
)


TIPOS = ("CPF", "CNPJ", "PIS", "CNJ", "OAB", "PESSOA", "LOCAL",
         "EMAIL", "TELEFONE", "CEP", "RG", "ENDERECO", "CONTA", "DATA_NASC")
ESTRATEGIAS = ("marcador", "parcial", "total")



TIPOS_OCORRENCIA = frozenset({"PESSOA", "LOCAL"})


ORIGEM_OCORRENCIA = "ner_opcional"


def _digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def validar_cpf(valor):
    d = _digitos(valor)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (soma * 10) % 11
        dv = 0 if dv == 10 else dv
        if dv != int(d[tamanho]):
            return False
    return True


def validar_cnpj(valor):
    d = _digitos(valor)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    pesos = ((5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
             (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    base = d[:12]
    for i, ps in enumerate(pesos):
        soma = sum(int(x) * p for x, p in zip(base, ps))
        dv = 0 if soma % 11 < 2 else 11 - soma % 11
        if dv != int(d[12 + i]):
            return False
        base += str(dv)
    return True


def validar_pis(valor):
    d = _digitos(valor)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    pesos = (3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    soma = sum(int(x) * p for x, p in zip(d[:10], pesos))
    resto = soma % 11
    dv = 0 if resto < 2 else 11 - resto
    return dv == int(d[-1])


def _sha(texto):
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()


def _norm(x):
    return re.sub(r"\s+", " ", str(x).strip()).casefold()


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))




TIPOS_DENYLIST = ("*", "PESSOA", "LOCAL")


def _denylist(caminho=None):
    'Termos que NUNCA viram marcador, por tipo: {"*": set, "PESSOA": set, "LOCAL": set}.'






    caminho = caminho or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "pseudonimizacao_denylist.json")
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    deny = {tipo: set() for tipo in TIPOS_DENYLIST}
    for categoria in dados.get("categorias") or []:
        if not isinstance(categoria, dict) or categoria.get("tipo") not in TIPOS_DENYLIST:
            continue
        for termo in categoria.get("termos") or []:
            deny[categoria["tipo"]].update({_norm(termo), _sem_acento(_norm(termo))})
    return deny


EXCECOES_SCHEMA = "dsr.pseudonimizacao.excecoes.v1"
NOME_EXCECOES = "pseudonimizacao_excecoes.json"


def carregar_excecoes(caminho):
    'Excecoes DO ADVOGADO ("nao e dado pessoal"): {"termos": [{"termo", "tipo", "liberado_em"}]}.'

    if not caminho or not os.path.isfile(caminho):
        return [], None
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, json.JSONDecodeError) as erro:
        return [], f"excecoes ilegiveis ({erro})"
    if not isinstance(dados, dict) or dados.get("schema_version") != EXCECOES_SCHEMA:
        return [], "excecoes com schema desconhecido"
    return [x for x in (dados.get("termos") or []) if isinstance(x, dict) and str(x.get("termo") or "").strip()], None


def liberar_termo(caminho, termo, tipo="*", por="advogado"):
    'Grava uma excecao do advogado: o termo deixa de ser mascarado em toda execucao'

    termos, erro = carregar_excecoes(caminho)
    if erro:
        raise ValueError(erro)
    chave = (_norm(termo), tipo)
    if not any((_norm(x.get("termo")), x.get("tipo", "*")) == chave for x in termos):
        termos.append({"termo": str(termo).strip(), "tipo": tipo, "por": por,
                       "liberado_em": time.strftime("%Y-%m-%dT%H:%M:%S")})
    os.makedirs(os.path.dirname(os.path.abspath(caminho)) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"schema_version": EXCECOES_SCHEMA, "termos": termos}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return len(termos)


def _deny_com_excecoes(deny, excecoes):
    for x in excecoes or []:
        tipo = str(x.get("tipo") or "*")
        deny.setdefault(tipo, set()).add(_norm(x.get("termo")))
    return deny





MINIMO_SEPARADORES = 2




ENV_DIGITO_INVALIDO = "DSR_PSEUDONIMIZACAO_SEM_DIGITO_INVALIDO"

_SEPARADORES = ".-/"











NAO_COBERTO = (
    "nome de pessoa que NUNCA aparece qualificado nem rotulado como parte ou testemunha (o vizinho "
    "citado de passagem num depoimento): sem ocorrência marcada em --ner-json, nem o nome na lista "
    "de partes (--partes), ele fica inteiro no texto. Nome qualificado ou rotulado é achado pela heurística embarcada e propagado por busca exata; "
    "variante que o OCR corrompeu de outro jeito não é alcançada pela propagação",
    "nome de magistrado, promotor, defensor e advogado, e razão social de pessoa jurídica: ficam "
    "de propósito, por decisão do advogado — só partes e testemunhas viram [PESSOA_n]",
    "nome de perito e de servidor da justiça depois do cargo separado do nome ('Perito: Fulano', "
    "'o perito Fulano'): fica no texto, por decisão do advogado — quem atua no processo fica, quem "
    "é parte vira código. Colado ao cargo, sem dois-pontos, e seguido de qualificação de parte "
    "('Perito FULANO, brasileiro'), o nome vira [PESSOA_n]",
    "cidade e topônimo, salvo ocorrência LOCAL marcada em --ner-json com --mascarar-locais",
    "RG, conta bancária e data de nascimento SEM palavra-âncora (RG, identidade, agência, conta, "
    "nascido em): o número nu não se distingue de outro número",
    "telefone sem DDD entre parênteses e sem palavra-âncora (tel., celular, fone, contato)",
    "endereço sem logradouro reconhecível (Rua, Av., Travessa…) seguido de número ou s/n",
    "identificador com DÍGITO partido no meio de um grupo pela quebra de linha (separador na "
    "quebra é aceito; dígito na linha seguinte não é reconstituído)",
    "identificador SEM pontuação cujo dígito verificador não confere (sequência nua não se "
    "distingue de protocolo, conta ou matrícula)",
    "candidato FRACO (dígito inválido, nome por heurística ou ocorrência marcada) que caia dentro de zona "
    "protegida — citação de norma, dispositivo legal ou nome de tribunal: ele é preservado "
    "de propósito, e sai listado em `suprimidos_por_zona`. Identificador determinístico "
    "com dígito conferido NUNCA é suprimido por zona",
    "assinatura manuscrita, carimbo e conteúdo em imagem: o que o OCR não transformou em texto "
    "não existe para esta camada",
)


def _formatado(valor, minimo=MINIMO_SEPARADORES):
    'True quando o trecho traz a PONTUAÇÃO característica do identificador.'





    return sum(1 for c in str(valor or "") if c in _SEPARADORES) >= minimo


def _mascara_digito_invalido():
    return os.environ.get(ENV_DIGITO_INVALIDO, "").strip().lower() not in ("1", "true", "sim")


def _candidatos_deterministicos(texto, digito_invalido=None,
                                minimo_separadores=MINIMO_SEPARADORES):
    'Candidatos determinísticos. Dois graus, e a distinção vai para o registro.'

















    if digito_invalido is None:
        digito_invalido = _mascara_digito_invalido()
    saida = []
    specs = (
        ("CNPJ", CNPJ_RX, validar_cnpj),
        ("CPF", CPF_RX, validar_cpf),
        ("PIS", PIS_RX, validar_pis),
        ("CNJ", numero_cnj.RE_CNJ, numero_cnj.validar),
        ("OAB", OAB_RX, lambda _x: True),
    )
    for tipo, rx, validar in specs:
        for m in rx.finditer(texto or ""):
            bruto = m.group(0)
            if validar(bruto):
                saida.append({"inicio": m.start(), "fim": m.end(), "tipo": tipo,
                              "valor": bruto, "confianca": 1.0,
                              "origem": "deterministica"})
            elif digito_invalido and _formatado(bruto, minimo_separadores):



                saida.append({"inicio": m.start(), "fim": m.end(), "tipo": tipo,
                              "valor": bruto, "confianca": 0.5,
                              "origem": "deterministica_digito_invalido"})

    for tipo, rx, conf, cond in PADROES:
        for m in rx.finditer(texto or ""):
            if cond is not None and not cond(texto, m):
                continue
            if "v" in rx.groupindex and m.group("v"):
                ini, fim = m.start("v"), m.end("v")
            else:
                ini, fim = m.start(), m.end()
            valor = texto[ini:fim]
            if not valor.strip():
                continue
            saida.append({"inicio": ini, "fim": fim, "tipo": tipo, "valor": valor,
                          "confianca": conf, "origem": "deterministica_padrao"})
    return saida


def normalizar_entidade_ner(ent):
    'Ocorrencia no formato da casa {inicio, fim, tipo, confianca} -> (inicio, fim, tipo, confianca).'

    return ent.get("inicio"), ent.get("fim"), ent.get("tipo"), ent.get("confianca", 0.0)


def _candidatos_ner(texto, entidades, deny, tipos_aceitos=None):
    saida, descartados = [], []
    aceitos = set(tipos_aceitos or ("PESSOA",))
    if entidades is not None and not isinstance(entidades, list):
        return [], [{"indice": None, "motivo": "entidades NER deve ser lista"}]
    for indice, ent in enumerate(entidades or []):
        if not isinstance(ent, dict):
            descartados.append({"indice": indice, "motivo": "entidade não é objeto"})
            continue
        try:
            _i, _f, _rot, _conf = normalizar_entidade_ner(ent)
            inicio, fim = int(_i), int(_f)
        except (KeyError, TypeError, ValueError):
            descartados.append({"indice": indice, "motivo": "offset ausente ou inválido"})
            continue
        if inicio < 0 or fim <= inicio or fim > len(texto):
            descartados.append({"indice": indice, "motivo": "offset fora dos limites do texto"})
            continue
        valor = texto[inicio:fim]
        rotulo = str(_rot or "").upper()
        tipo_casa = rotulo if rotulo in TIPOS_OCORRENCIA else None






        if not valor.strip():
            descartados.append({"indice": indice, "motivo": "valor vazio no intervalo indicado"})
            continue
        if tipo_casa is None or tipo_casa not in aceitos:
            descartados.append({
                "indice": indice,
                "motivo": "tipo NER '%s' nao mascarado nesta execucao; aceitos: %s%s. Este "
                          "trecho segue NO TEXTO - mascare-o antes de subir, ou trate-o na "
                          "conferencia humana" % (rotulo or "(ausente)", ", ".join(sorted(aceitos)),
                                                  "" if "LOCAL" in aceitos else " (LOCAL so com --mascarar-locais)")})
            continue
        norm = _norm(valor)
        if norm in deny.get("*", set()) or norm in deny.get(tipo_casa, set()):
            continue
        try:
            confianca = float(_conf if _conf is not None else 0.0)
        except (TypeError, ValueError):
            descartados.append({"indice": indice, "motivo": "confiança NER inválida"})
            continue
        saida.append({"inicio": inicio, "fim": fim, "tipo": tipo_casa, "valor": valor,
                      "confianca": confianca, "origem": ORIGEM_OCORRENCIA})
    return saida, descartados


def _sem_sobreposicao(candidatos):
    ordenados = sorted(candidatos, key=lambda x: (x["inicio"], -(x["fim"] - x["inicio"])))
    saida, fim_atual = [], -1
    for item in ordenados:
        if item["inicio"] < fim_atual:
            continue
        saida.append(item)
        fim_atual = item["fim"]
    return saida

















ENV_HEURISTICA_NOME = "DSR_PSEUDONIMIZACAO_SEM_HEURISTICA_NOME"


_ROTULOS_PARTE = (
    r"requerentes?", r"requerid[oa]s?", r"autor(?:a|es|as)?", r"r[eé]us?", r"r[eé]s?", r"reclamantes?",
    r"reclamad[oa]s?", r"exequentes?", r"executad[oa]s?", r"embargantes?", r"embargad[oa]s?",
    r"agravantes?", r"agravad[oa]s?", r"apelantes?", r"apelad[oa]s?", r"recorrentes?", r"recorrid[oa]s?",
    r"impetrantes?", r"impugnantes?", r"impugnad[oa]s?", r"promoventes?", r"promovid[oa]s?",
    r"suscitantes?", r"suscitad[oa]s?", r"denunciad[oa]s?", r"acusad[oa]s?", r"indiciad[oa]s?",
    r"querelantes?", r"querelad[oa]s?", r"v[ií]timas?", r"ofendid[oa]s?", r"interessad[oa]s?",
    r"testemunhas?", r"declarantes?", r"depoentes?", r"informantes?", r"paciente", r"segurad[oa]",
    r"parte\s+autora", r"parte\s+r[eé]", r"parte\s+requerente", r"parte\s+requerida",
    r"pol[oa]\s+ativo", r"pol[oa]\s+passivo",
)

_ROTULOS_FORA = (
    r"advogad[oa]s?", r"procurador(?:a|es)?", r"defensor(?:a|es)?", r"juiz(?:a|es)?", r"ju[ií]z[oa]",
    r"desembargador(?:a|es)?", r"ministr[oa]s?", r"relator(?:a|es)?", r"promotor(?:a|es)?",
    r"perit[oa]s?", r"escriv[aã]o?", r"oficial", r"servidor(?:a)?", r"magistrad[oa]", r"dr\.?", r"dra\.?",
    r"mm\.?", r"exm[oa]\.?", r"excelent[ií]ssim[oa]",
)

_PJ_RX = re.compile(
    r"\b(?:ltda\.?|s\.?/?a\.?|s\.a\.|eireli|epp|me|cia\.?|companhia|sociedade|associa[çc][aã]o|funda[çc][aã]o|"
    r"instituto|cooperativa|sindicato|condom[ií]nio|banco|caixa|seguradora|hospital|cl[ií]nica|col[ée]gio|"
    r"escola|universidade|faculdade|ind[úu]stria|com[ée]rcio|transportes?|servi[çc]os|empreendimentos|"
    r"participa[çc][oõ]es|holding|incorporadora|construtora|imobili[áa]ria|munic[ií]pio|prefeitura|estado|"
    r"uni[aã]o|fazenda|inss|minist[ée]rio|defensoria|procuradoria|tribunal|c[âa]mara|secretaria|"
    r"departamento|autarquia|ag[êe]ncia|conselho|ordem|federa[çc][aã]o|confedera[çc][aã]o|igreja|"
    r"partido|empresa|grupo|rede|loja|supermercado|farm[áa]cia|posto|distribuidora|atacad[aã]o)\b", re.I)

_CONECTIVO = r"(?:d[aeo]s?|e|y|von|van|del|della|di|du|le|la)"
_PAL_NOME = r"(?:[A-ZÀ-Ý][a-zà-ÿ]{1,}|[A-ZÀ-Ý]{2,})"
NOME_RX = r"(?P<nome>" + _PAL_NOME + r"(?:[ \t]+(?:" + _CONECTIVO + r"[ \t]+)?" + _PAL_NOME + r"){1,6})"


ROTULADO_RX = re.compile(
    r"(?<![\wÀ-ÿ])(?:" + "|".join(_ROTULOS_PARTE) + r")\s*(?:\([^)]{0,30}\))?\s*[:\-–—]\s*" + NOME_RX, re.I)

QUALIFICADO_RX = re.compile(
    NOME_RX + r"\s*,\s*(?:(?:j[áa]\s+)?qualificad[oa]|brasileir[oa]|portugu[eê]s|estrangeir[oa]|nacionalidade|"
    r"natural\s+de|maior|menor|capaz|solteir[oa]|casad[oa]|divorciad[oa]|vi[úu]v[oa]|separad[oa]|"
    r"portador|inscrit[oa]\s+n[oa]\s+CPF|CPF|RG|nascid[oa]\s+em|residente|domiciliad[oa]|"
    r"aposentad[oa]|desempregad[oa]|autônom[oa]|autonom[oa])\b")

_QUALIF_ADVOGADO_RX = re.compile(r"\bOAB\b|\badvogad[oa]s?\b|\bprocurador", re.I)
_ROTULO_FORA_RX = re.compile(r"(?:" + "|".join(_ROTULOS_FORA) + r")\s*[:\-–—]?\s*$", re.I)


_ROTULOS_SEM_NOME = (r"partes?", r"nome", r"qualifica[çc][aã]o", r"filia[çc][aã]o",
                     r"senhor(?:a|es|as)?", r"sr[as]?\.?", r"sras\.?", r"dona")
_ROTULO_INTEIRO_RX = re.compile(r"(?:" + "|".join(_ROTULOS_PARTE + _ROTULOS_FORA + _ROTULOS_SEM_NOME) + r")",
                                re.I)


def _heuristica_nome_ligada():
    return os.environ.get(ENV_HEURISTICA_NOME, "").strip().lower() not in ("1", "true", "sim")


def _resto_do_nome(palavras, i, negados):
    'As palavras da captura a partir de `i`, depois de cortar da frente, em laço, termo da deny'

    while i < len(palavras):
        norm = [_norm(p.group()) for p in palavras[i:]]
        corte = next((k for k in range(len(norm), 0, -1) if " ".join(norm[:k]) in negados), 0)
        if not corte:
            corte = next((k for k in (2, 1) if k <= len(norm)
                          and _ROTULO_INTEIRO_RX.fullmatch(" ".join(norm[:k]))), 0)
        if not corte and i and re.fullmatch(_CONECTIVO, norm[0], re.I):
            corte = 1
        if not corte:
            break
        i += corte
    return palavras[i:]


def _palavras_antes(texto, ini, teto):
    'As últimas `teto` palavras da linha antes de `ini`, como (palavra, início), lidas de trás'


    palavras, fim = [], ini
    while len(palavras) < teto:
        k = fim
        while k and texto[k - 1] != "\n" and texto[k - 1].isspace():
            k -= 1
        j = k
        while j and not texto[j - 1].isspace():
            j -= 1
        if j == k:
            break
        palavras.append((texto[j:k], j))
        fim = j
    palavras.reverse()
    return palavras


def _corte_do_termo_partido(palavras, texto, ini, negados, teto):
    'Quantas palavras do começo da captura completam um termo da deny list que começa ANTES dela,'








    if not teto or not ini or texto[ini - 1] == "\n" or not texto[ini - 1].isspace():
        return 0, ini
    antes = _palavras_antes(texto, ini, teto)
    norm_antes = [_norm(p) for p, _ in antes]
    norm = [_norm(p.group()) for p in palavras]
    for j in range(len(antes)):
        for k in range(len(norm) - 2, 0, -1):
            if " ".join(norm_antes[j:] + norm[:k]) in negados:
                return k, antes[j][1]
    return 0, ini


def _nome_da_captura(nome, texto, ini, negados, teto):
    'O nome de pessoa dentro da captura, como (nome, inicio, fim), ou None.'












    if _PJ_RX.search(nome):
        return None
    palavras = list(re.finditer(r"\S+", nome))
    corte, ini_termo = _corte_do_termo_partido(palavras, texto, ini, negados, teto)
    resto = _resto_do_nome(palavras, corte, negados)
    if len(resto) < 2:

        resto = _resto_do_nome(palavras, 0, negados)
        ini_termo = ini
    if len(resto) < 2:
        return None
    ini_nome, fim_nome = ini + resto[0].start(), ini + resto[-1].end()
    if _ROTULO_FORA_RX.search(texto[max(0, ini_termo - 40):ini_termo]):
        return None
    return texto[ini_nome:fim_nome], ini_nome, fim_nome


def _variantes(nome):
    """Formas pelas quais o mesmo nome reaparece: exato, caixa alta, primeiro+ultimo (≥3 palavras)."""
    v = {nome, nome.upper(), nome.title()}
    pal = [p for p in nome.split() if not re.fullmatch(_CONECTIVO, p, re.I)]
    if len(pal) >= 3:
        v.add(pal[0] + " " + pal[-1])
        v.add((pal[0] + " " + pal[-1]).upper())
    return {x for x in v if len(x) >= 5}


def _candidatos_heuristica_nome(texto, deny):
    """Nomes de PARTE e TESTEMUNHA achados por rotulo ou qualificacao, propagados por busca exata."""
    if not _heuristica_nome_ligada() or not texto:
        return []
    negados = deny.get("*", set()) | deny.get("PESSOA", set())
    teto = max((t.count(" ") + 1 for t in negados), default=0)
    achados = {}
    for m in ROTULADO_RX.finditer(texto):
        achado = _nome_da_captura(m.group("nome"), texto, m.start("nome"), negados, teto)
        if achado:
            achados.setdefault(_norm(achado[0]), achado)
    for m in QUALIFICADO_RX.finditer(texto):

        fim_q = texto.find(".", m.end())
        janela = texto[m.end():(fim_q if 0 < fim_q - m.end() <= 260 else m.end() + 260)]
        if _QUALIF_ADVOGADO_RX.search(janela):
            continue
        achado = _nome_da_captura(m.group("nome"), texto, m.start("nome"), negados, teto)
        if achado:
            achados.setdefault(_norm(achado[0]), achado)
    saida = []
    for chave_norm, (nome, ini, fim) in achados.items():
        chave = ("PESSOA", chave_norm)
        vistos = set()
        for var in _variantes(nome):
            for mm in re.finditer(r"(?<![\wÀ-ÿ])" + re.escape(var) + r"(?![\wÀ-ÿ])", texto):
                if (mm.start(), mm.end()) in vistos:
                    continue
                vistos.add((mm.start(), mm.end()))
                achado = mm.start() == ini and mm.end() == fim
                saida.append({"inicio": mm.start(), "fim": mm.end(), "tipo": "PESSOA",
                              "valor": texto[mm.start():mm.end()], "chave": chave,
                              "confianca": 0.6 if achado else 0.55,
                              "origem": "heuristica_qualificacao" if achado else "heuristica_propagacao"})
    return saida


















PARTES_SCHEMA = "dsr.pseudonimizacao.partes.v1"
ORIGEM_PARTES = "lista_de_partes"
MINIMO_LETRAS_FORMA = 2
CODIGO_PARTES_FORMATO = "PARTES_FORA_DO_FORMATO"
CODIGO_PARTES_AMBIGUAS = "PARTES_AMBIGUAS"


class PartesInvalidas(ValueError):
    """Lista de partes recusada, com código nomeado e violações sem o nome de ninguém."""

    def __init__(self, codigo, violacoes):
        super().__init__(codigo)
        self.codigo = codigo
        self.violacoes = list(violacoes)


def _forma_dobrada(texto):
    """Sem acento, sem caixa e com os espaços colapsados: a forma em que a lista casa."""
    return " ".join(_sem_acento(str(texto).casefold()).split())


def normalizar_partes(bruto):
    'Lista de partes do advogado -> [{"nome", "formas"}] (formas dobradas, sem repetição).'



    if bruto is None:
        return []
    if isinstance(bruto, dict):
        if bruto.get("schema_version") != PARTES_SCHEMA:
            raise PartesInvalidas(CODIGO_PARTES_FORMATO, ["schema_version deve ser " + PARTES_SCHEMA])
        lista = bruto.get("partes")
    else:
        lista = bruto
    if not isinstance(lista, list):
        raise PartesInvalidas(CODIGO_PARTES_FORMATO, ["'partes' deve ser lista"])
    partes, violacoes, ambiguas, dono = [], [], [], {}
    for i, item in enumerate(lista):
        if isinstance(item, str):
            item = {"nome": item}
        if not isinstance(item, dict):
            violacoes.append(f"parte {i}: deve ser objeto com 'nome' ou o nome em texto")
            continue
        extras = sorted(set(item) - {"nome", "variantes"})
        nome, variantes = item.get("nome"), item.get("variantes", [])
        if extras:
            violacoes.append(f"parte {i}: campo desconhecido ({', '.join(extras)})")
        if not isinstance(nome, str) or not nome.strip():
            violacoes.append(f"parte {i}: 'nome' ausente ou vazio")
            continue
        if not isinstance(variantes, list) or not all(isinstance(v, str) for v in variantes):
            violacoes.append(f"parte {i}: 'variantes' deve ser lista de textos")
            continue
        formas = []
        for j, crua in enumerate([nome] + variantes):
            forma = _forma_dobrada(crua)
            if sum(c.isalpha() for c in forma) < MINIMO_LETRAS_FORMA:
                violacoes.append(f"parte {i}: forma {j} com menos de {MINIMO_LETRAS_FORMA} letras")
                continue
            if forma in formas:
                continue
            if dono.get(forma, i) != i:
                ambiguas.append(f"partes {dono[forma]} e {i} declaram a mesma forma (forma {j})")
                continue
            dono[forma] = i
            formas.append(forma)
        if formas:
            partes.append({"nome": " ".join(nome.split()), "formas": formas})
    if violacoes:
        raise PartesInvalidas(CODIGO_PARTES_FORMATO, violacoes)
    if ambiguas:
        raise PartesInvalidas(CODIGO_PARTES_AMBIGUAS, ambiguas)
    return partes


def _chave_de_parte(parte):
    return ("PESSOA", "lista:" + parte["formas"][0])


def _indice_de_partes(partes):
    """forma dobrada -> (chave da pessoa, nome declarado)."""
    return {forma: (_chave_de_parte(p), p["nome"]) for p in partes or [] for forma in p["formas"]}









_PRECEDE_FORMA_DA_LISTA = re.compile(
    r"(?<!\w)(?:sao|santa|santo|lei|rua|r\.|avenida|av\.|travessa|tv\.|alameda|al\.|praca|pca\.|"
    r"rodovia|rod\.|min\.?|ministr[oa]|des\.?|desembargador(?:a)?|rel\.?|relator(?:a)?|juiz(?:a)?)"
    r"\s+$")
_PRECEDE_CARGO = re.compile(r"(?<!\w)(?:" + "|".join(_ROTULOS_FORA) + r")\s+$", re.I)
_ROTULO_DE_PARTE_RX = re.compile(r"(?:" + "|".join(_ROTULOS_PARTE + _ROTULOS_SEM_NOME) + r")", re.I)

_ABREVIATURAS = frozenset({"sr", "sra", "srs", "sras", "dr", "dra", "min", "des", "rel", "exmo", "exma",
                           "mm", "prof", "profa", "eng", "adv"})
_CONECTIVOS_DE_NOME = frozenset({"da", "de", "do", "das", "dos", "di", "del", "van", "von"})
_PALAVRA_DE_NOME_RX = re.compile(r"[A-ZÀ-Ý][A-Za-zÀ-ÿ'’\-]*")


def _fecha_frase(token):
    'O token (já sem espaço) termina frase: ponto final, interrogação ou exclamação, salvo'

    if not token or token[-1] not in ".!?…":
        return False
    return _forma_dobrada(token.rstrip(".!?…")) not in _ABREVIATURAS





_PALAVRAS_COMUNS_DE_ABERTURA = frozenset({
    "dias", "paz", "luz", "cruz", "rosa", "flores", "campos", "ramos", "fontes", "neves", "prado",
    "branco", "leal", "franco", "guerra", "porto", "vale", "serra", "monte", "costa", "lima", "rocha",
    "leite", "reis", "pena", "barros", "pinto", "nobre", "alegre", "rios", "pontes", "torres"})


def _minusculas(texto):
    """Palavras que o texto usa começando por minúscula, na forma dobrada."""
    return {_forma_dobrada(p) for p in re.findall(r"(?<![\wÀ-ÿ])[a-zà-ÿ][\wÀ-ÿ]*", texto)}


def _ocorrencia_da_lista_vale(texto, dobrado, ini_dobrado, ini, palavras, palavras_da_parte,
                              minusculas):
    """A ocorrência de uma forma da lista de partes é a parte (e se mascara)."""
    if _PRECEDE_FORMA_DA_LISTA.search(dobrado[max(0, ini_dobrado - 24):ini_dobrado]):
        return False
    if len(palavras) != 1:
        return True
    if not texto[ini].isupper() or _PRECEDE_CARGO.search(dobrado[max(0, ini_dobrado - 30):ini_dobrado]):
        return False
    tokens = texto[max(0, ini - 120):ini].split()
    if not tokens or _fecha_frase(tokens[-1]):
        return not (palavras[0] in _PALAVRAS_COMUNS_DE_ABERTURA or palavras[0] in minusculas)
    k = len(tokens) - 1
    if k and _forma_dobrada(tokens[k]) in _CONECTIVOS_DE_NOME:
        k -= 1
    vizinho = tokens[k]
    if (len(vizinho) >= 2 and _PALAVRA_DE_NOME_RX.fullmatch(vizinho)
            and _forma_dobrada(vizinho) not in palavras_da_parte
            and not _ROTULO_DE_PARTE_RX.fullmatch(_forma_dobrada(vizinho))
            and not (k == 0 or _fecha_frase(tokens[k - 1]))):
        return False
    return True


def _palavras_da_parte(parte):
    return frozenset(p for forma in parte["formas"] for p in forma.split())


def _candidatos_partes(texto, partes):
    """Toda aparição de toda forma de toda parte, no texto original, com a chave da PESSOA."""
    if not partes or not texto:
        return []
    dobrado, origem = _dobrar(texto)
    minusculas = _minusculas(texto)
    saida = []
    for parte in partes:
        chave = _chave_de_parte(parte)
        vizinhas = _palavras_da_parte(parte)
        for forma in parte["formas"]:
            palavras = forma.split()
            rx = re.compile(r"(?<!\w)" + r"\s+".join(re.escape(p) for p in palavras) + r"(?!\w)")
            for m in rx.finditer(dobrado):
                ini, fim = origem[m.start()], origem[m.end() - 1] + 1
                while fim < len(texto) and unicodedata.combining(texto[fim]):
                    fim += 1
                if not _ocorrencia_da_lista_vale(texto, dobrado, m.start(), ini, palavras,
                                                 vizinhas, minusculas):
                    continue
                saida.append({"inicio": ini, "fim": fim, "tipo": "PESSOA",
                              "valor": texto[ini:fim], "chave": chave, "canonico": parte["nome"],
                              "confianca": 1.0, "origem": ORIGEM_PARTES})
    return saida



























ZONAS_PROTEGIDAS = (
    ("citacao_de_norma", re.compile(
        r"\b(?:Lei(?:\s+Complementar)?|Decreto(?:-Lei)?|Medida\s+Provisória|"
        r"Emenda\s+Constitucional|Resolução|Portaria|Instrução\s+Normativa|Provimento|"
        r"Súmula(?:\s+Vinculante)?)\s*n?[.ºo°]*\s*[\d][\d./-]*",
        re.IGNORECASE)),




    ("dispositivo_legal", re.compile(
        r"\b(?:art(?:igo)?s?|inc(?:iso)?s?|§{1,2}|parágrafos?|alíneas?)\s*[.ºo°]*\s*"
        r"\d{1,3}(?:\.\d{3})?[ºo°]?", re.IGNORECASE)),
    ("tribunal_ou_orgao", re.compile(
        r"\b(?:STF|STJ|TST|TSE|STM|CNJ|TRF-?\d|TRT-?\d{1,2}|TJ[A-Z]{2}|TJDFT|"
        r"Supremo\s+Tribunal\s+Federal|Superior\s+Tribunal\s+de\s+Justiça|"
        r"Tribunal\s+Superior\s+do\s+Trabalho)\b")),
)


def zonas_protegidas(texto):
    """Intervalos [inicio, fim) que a deteccao deve ignorar. Lista de (inicio, fim, nome)."""
    achados = []
    for nome, rx in ZONAS_PROTEGIDAS:
        for m in rx.finditer(texto):
            achados.append((m.start(), m.end(), nome))
    return sorted(achados)


def _zona_de(item, zonas):
    'Nome da zona que cobre o candidato, ou None. Sobreposicao PARCIAL ja conta.'





    for inicio, fim, nome in zonas:
        if item["inicio"] < fim and inicio < item["fim"]:
            return nome
    return None


def _chave_de_entidade(tipo, valor):
    """Identidade da entidade, para o rotulo ser estavel entre ocorrencias."""
    texto = str(valor)
    if tipo in ("CPF", "CNPJ", "PIS", "CNJ", "OAB"):
        so_digitos = re.sub(r"\D", "", texto)
        if so_digitos:
            return (tipo, so_digitos)
    return (tipo, re.sub(r"\s+", " ", texto).strip().casefold())


def _mascara_parcial(tipo, valor):
    'Mascara PARCIAL: conferencia de relance ao custo de manter iniciais/digitos.'

    if tipo in ("PESSOA", "LOCAL", "ENDERECO", "EMAIL"):
        return " ".join((w[0] + "*" * (len(w) - 1)) if len(w) > 1 else w for w in valor.split())
    if len(valor) <= 5:
        return "*" * len(valor)
    return valor[:3] + "".join("*" if c.isalnum() else c for c in valor[3:-2]) + valor[-2:]


def _substituto(tipo, valor, marcador, estrategia):
    if estrategia == "marcador":
        return marcador
    if estrategia == "parcial":
        return _mascara_parcial(tipo, valor)
    return "*" * len(valor)


def _semear_mapping_base(mapping_base, partes=None):
    'Numeracao UNICA entre pecas: o mapping de uma peca'


    rotulos, contagem = {}, {}
    indice = _indice_de_partes(partes)
    for m in (mapping_base or {}).get("mapping") or []:
        if not isinstance(m, dict):
            continue
        tipo, valor, marcador = m.get("tipo"), m.get("valor"), m.get("marcador")
        if not (tipo and valor is not None and marcador):
            continue
        rotulos.setdefault(_chave_de_entidade(tipo, valor), marcador)
        if tipo == "PESSOA" and indice:
            for forma in (m.get("canonico"), valor):
                achado = indice.get(_forma_dobrada(forma)) if forma else None
                if achado:
                    rotulos.setdefault(achado[0], marcador)
        mm = re.fullmatch(r"\[%s_(\d+)\]" % re.escape(str(tipo)), str(marcador))
        if mm:
            contagem[tipo] = max(contagem.get(tipo, 0), int(mm.group(1)))
    return rotulos, contagem





































CODIGO_RESIDUO = "PSEUDONIMIZACAO_COM_RESIDUO"
CODIGO_AUDITORIA_FALHOU = "AUDITORIA_RESIDUAL_INDISPONIVEL"
TIPOS_IDENTIFICADOR = ("CPF", "CNPJ", "PIS", "CNJ", "OAB")
MINIMO_DIGITOS_RESIDUO = 5
TIPOS_NOME = ("PESSOA", "LOCAL")
ORIGEM_BASE = "mapping_base"
ORIGENS_FIRMES = ("deterministica", "deterministica_padrao", ORIGEM_BASE, ORIGEM_PARTES)

_PRECEDE_OUTRO_NOME = re.compile(r"(?<!\w)(?:sao|santa|santo|lei)\s+$")


def _dobrar(texto):
    """Texto sem caixa e sem acento, e para cada caractere dobrado a posição no texto de origem."""
    dobrado, origem = [], []
    for i, c in enumerate(texto):
        for d in _sem_acento(c.casefold()):
            dobrado.append(d)
            origem.append(i)
    return "".join(dobrado), origem


def _rx_valor_dobrado(valor):
    'Regex do valor mapeado sobre o texto dobrado: palavras separadas por qualquer espaço ou'

    palavras = _sem_acento(str(valor).casefold()).split()
    if not palavras:
        return None
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(p) for p in palavras) + r"(?!\w)")


def _rx_digitos(valor):
    'Regex dos dígitos do identificador com qualquer separador (ponto, hífen, barra, espaço,'

    d = _digitos(valor)
    if len(d) < MINIMO_DIGITOS_RESIDUO:
        return None
    return re.compile(r"(?<!\d)" + r"(?:\r\n|[\s./\-]){0,2}".join(d) + r"(?!\d)")


def _dentro(ini, fim, trechos):
    return any(a <= ini and fim <= b for a, b in trechos)


def _forma_de_nome_proprio(sanitizado, dobrado, inicio_dobrado, inicio):
    'A ocorrência de um nome de uma palavra só tem forma de nome próprio: começa por'

    if not sanitizado[inicio].isupper():
        return False
    return not _PRECEDE_OUTRO_NOME.search(dobrado[max(0, inicio_dobrado - 12):inicio_dobrado])


def _regras_por_valor(mapping, dobrado, origem, sanitizado):
    'Uma regra de busca por (tipo, padrão). O mesmo valor vindo do mapping desta execução e'

    regras = {}
    for m in mapping or []:
        tipo, valor = m.get("tipo"), m.get("valor")
        if not tipo or valor is None or not str(valor).strip():
            continue
        palpite = m.get("origem") not in ORIGENS_FIRMES
        uma_palavra = tipo in TIPOS_NOME and len(str(valor).split()) == 1
        lista = m.get("_lista_palavras")
        candidatas = [(_rx_valor_dobrado(valor), dobrado, origem, uma_palavra, lista)]
        if tipo in TIPOS_IDENTIFICADOR:
            candidatas.append((_rx_digitos(valor), sanitizado, None, False, None))
        for rx, alvo, mapa, curto, palavras_lista in candidatas:
            if rx is None:
                continue
            chave = (tipo, rx.pattern, mapa is None)
            if chave in regras:
                regras[chave]["palpite"] = regras[chave]["palpite"] and palpite
                if palavras_lista is not None:
                    regras[chave]["lista"] = (regras[chave]["lista"] or frozenset()) | palavras_lista
            else:
                regras[chave] = {"tipo": tipo, "rx": rx, "alvo": alvo, "mapa": mapa,
                                 "palpite": palpite, "uma_palavra": curto, "lista": palavras_lista,
                                 "palavras": _forma_dobrada(valor).split()}
    return list(regras.values())


def _achados_residuais(sanitizado, mapping, trechos_substituidos):
    '(achados, possiveis): listas de (inicio, fim, tipo). Achado reprova; possível é nome de'


    achados, possiveis = [], []
    zonas = zonas_protegidas(sanitizado)
    for c in _candidatos_deterministicos(sanitizado):
        if _dentro(c["inicio"], c["fim"], trechos_substituidos):
            continue
        if c["origem"] not in ("deterministica", "deterministica_padrao") and _zona_de(c, zonas):
            continue
        achados.append((c["inicio"], c["fim"], c["tipo"]))
    dobrado, origem = _dobrar(sanitizado)
    minusculas = _minusculas(sanitizado)
    for regra in _regras_por_valor(mapping, dobrado, origem, sanitizado):
        mapa = regra["mapa"]
        for achado in regra["rx"].finditer(regra["alvo"]):
            ini, fim = achado.start(), achado.end()
            if mapa is not None:
                ini, fim = mapa[ini], mapa[fim - 1] + 1



            if _dentro(ini, fim, trechos_substituidos):
                continue
            if regra["palpite"] and _zona_de({"inicio": ini, "fim": fim}, zonas):
                continue
            if regra["lista"] is not None:


                if not _ocorrencia_da_lista_vale(sanitizado, dobrado, achado.start(), ini,
                                                 regra["palavras"], regra["lista"], minusculas):
                    possiveis.append((ini, fim, regra["tipo"]))
                    continue
            elif regra["uma_palavra"] and not _forma_de_nome_proprio(
                    sanitizado, dobrado, achado.start(), ini):
                possiveis.append((ini, fim, regra["tipo"]))
                continue
            achados.append((ini, fim, regra["tipo"]))
    return _unicos(achados), _unicos(possiveis)


def _unicos(lista):
    """Um resíduo achado por mais de uma via conta uma vez."""
    unicos, fim_atual = [], -1
    for ini, fim, tipo in sorted(lista, key=lambda x: (x[0], -(x[1] - x[0]))):
        if ini < fim_atual:
            continue
        unicos.append((ini, fim, tipo))
        fim_atual = fim
    return unicos


def _contar_por_tipo(lista):
    por_tipo = {}
    for _ini, _fim, tipo in lista:
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
    return dict(sorted(por_tipo.items()))


def _palavras_de_entrada(m):
    return frozenset(" ".join(_forma_dobrada(x) for x in (m.get("canonico"), m.get("valor"))
                              if isinstance(x, str)).split())


def _entradas_de_base(mapping_base):
    """Valores já mapeados nas peças anteriores do caso, como entradas firmes da auditoria."""
    entradas = []
    for m in (mapping_base or {}).get("mapping") or []:
        if isinstance(m, dict) and m.get("tipo") and m.get("valor") is not None:
            entrada = {"tipo": m["tipo"], "valor": m["valor"], "origem": ORIGEM_BASE}
            if m.get("origem") == ORIGEM_PARTES:
                entrada["_lista_palavras"] = _palavras_de_entrada(m)
            entradas.append(entrada)
    return entradas


def _entradas_da_lista(mapping, partes):
    'Toda forma da lista de partes entra na auditoria, mascarada ou não nesta peça, e o valor'

    palavras_por_forma = {f: _palavras_da_parte(p) for p in partes or [] for f in p["formas"]}
    entradas = []
    for m in mapping or []:
        if m.get("origem") == ORIGEM_PARTES:
            m = dict(m, _lista_palavras=palavras_por_forma.get(_forma_dobrada(m.get("valor") or ""),
                                                               _palavras_de_entrada(m)))
        entradas.append(m)
    for p in partes or []:
        for forma in p["formas"]:
            entradas.append({"tipo": "PESSOA", "valor": forma, "origem": ORIGEM_PARTES,
                             "_lista_palavras": _palavras_da_parte(p)})
    return entradas


def auditar_residuos(sanitizado, mapping, trechos_substituidos=(), mapping_base=None, partes=None):
    'Auditoria residual do texto mascarado. Devolve só tipo e contagem, nunca o valor:'



    try:
        conferir = _entradas_da_lista(mapping, partes) + _entradas_de_base(mapping_base)
        achados, possiveis = _achados_residuais(sanitizado or "", conferir,
                                                list(trechos_substituidos or ()))
    except Exception as erro:
        return {"aprovada": False, "codigo": CODIGO_AUDITORIA_FALHOU, "total_residuos": None,
                "por_tipo": {}, "valores_conferidos": len(mapping or []),
                "possiveis_por_tipo": {}, "erro": erro.__class__.__name__}
    return {"aprovada": not achados, "codigo": CODIGO_RESIDUO if achados else None,
            "total_residuos": len(achados), "por_tipo": _contar_por_tipo(achados),
            "valores_conferidos": len(conferir),
            "possiveis_por_tipo": _contar_por_tipo(possiveis)}


def pseudonimizar_texto(texto, entidades_ner=None, denylist_path=None, sigiloso=True,
                        estrategia="marcador", mascarar_locais=False, excecoes=None,
                        mapping_base=None, heuristica_nome=True, partes=None):
    if not isinstance(texto, str):
        raise ValueError("texto deve ser string")
    if sigiloso is not True:
        raise ValueError("pseudonimização nunca rebaixa a classificação de sigilo")
    if estrategia not in ESTRATEGIAS:
        raise ValueError("estrategia deve ser uma de: " + ", ".join(ESTRATEGIAS))
    lista_partes = normalizar_partes(partes)
    deny = _deny_com_excecoes(_denylist(denylist_path), excecoes)
    aceitos = {"PESSOA"} | ({"LOCAL"} if mascarar_locais else set())
    ner, ner_descartados = _candidatos_ner(texto, entidades_ner, deny, aceitos)
    heur = _candidatos_heuristica_nome(texto, deny) if heuristica_nome else []

    indice_partes = _indice_de_partes(lista_partes)
    for c in ner + heur:
        achado = indice_partes.get(_forma_dobrada(c["valor"])) if c["tipo"] == "PESSOA" else None
        if achado:
            c["chave"], c["canonico"] = achado


    candidatos = _sem_sobreposicao(
        _candidatos_deterministicos(texto) + _candidatos_partes(texto, lista_partes) + ner + heur)
    zonas = zonas_protegidas(texto)
    rotulo_por_entidade, contagem = _semear_mapping_base(mapping_base, lista_partes)
    chaves_partes = {_chave_de_parte(p) for p in lista_partes}
    partes_achadas = set()
    mapping, partes, cursor = [], [], 0
    suprimidos = []


    trechos_substituidos, tam_sanitizado = [], 0
    for item in candidatos:
        zona = _zona_de(item, zonas)









        if zona is not None and item.get("origem") in ("deterministica", "deterministica_padrao",
                                                       ORIGEM_PARTES):
            zona = None
        if zona is not None:


            suprimidos.append({
                "tipo": item["tipo"], "zona": zona,
                "inicio": item["inicio"], "fim": item["fim"],

                "valor_sha256_12": _sha(str(item["valor"]))[:12],
                "origem": item["origem"],
            })
            continue
        partes.append(texto[cursor:item["inicio"]])
        tam_sanitizado += item["inicio"] - cursor
        tipo = item["tipo"]
        chave = item.get("chave") or _chave_de_entidade(tipo, item["valor"])
        marcador = rotulo_por_entidade.get(chave)
        if marcador is None:
            contagem[tipo] = contagem.get(tipo, 0) + 1
            marcador = f"[{tipo}_{contagem[tipo]}]"
            rotulo_por_entidade[chave] = marcador
        substituto = _substituto(tipo, item["valor"], marcador, estrategia)
        partes.append(substituto)
        trechos_substituidos.append((tam_sanitizado, tam_sanitizado + len(substituto)))
        tam_sanitizado += len(substituto)
        entrada_mapping = {"marcador": marcador, "tipo": tipo, "valor": item["valor"],
                           "inicio": item["inicio"], "fim": item["fim"],
                           "confianca": item["confianca"], "origem": item["origem"]}
        if chave in chaves_partes:
            partes_achadas.add(chave)

            entrada_mapping["canonico"] = item.get("canonico")
        mapping.append(entrada_mapping)
        cursor = item["fim"]
    partes.append(texto[cursor:])
    sanitizado = "".join(partes)
    auditoria = auditar_residuos(sanitizado, mapping, trechos_substituidos, mapping_base, lista_partes)
    inj_entrada = detectar_injecao.varrer(texto)
    inj_saida = detectar_injecao.varrer(sanitizado)
    return {
        "schema_version": VERSAO,
        "experimental": True,
        "estrategia": estrategia,
        "mascarar_locais": bool(mascarar_locais),
        "excecoes_aplicadas": len(excecoes or []),
        "mapping_base_sha256": _sha(json.dumps(mapping_base, sort_keys=True, ensure_ascii=False)) if mapping_base else None,
        "ner_fonte": None,
        "ner_meta": None,
        "revisao": None,
        "sigiloso_entrada": bool(sigiloso),
        "sigiloso_saida": bool(sigiloso),
        "desclassifica_sigilo": False,
        "revisao_humana_obrigatoria": True,
        "cobertura_total_garantida": False,

        "nao_coberto": list(NAO_COBERTO),

        "aviso": ("MASCARADO NÃO É ANÔNIMO. Esta camada mascara identificador com forma "
                  "reconhecível; nome de pessoa só sai quando vem rotulado ou qualificado como "
                  "parte ou testemunha, ou marcado em --ner-json. Leia "
                  "`nao_coberto` antes de tratar este texto como despersonalizado, e a "
                  "revisão humana continua obrigatória."),
        "sha256_original": _sha(texto),
        "sha256_sanitizado": _sha(sanitizado),
        "texto_sanitizado": sanitizado,
        "mapping": mapping,
        "ner_descartados": ner_descartados,
        "incerteza": bool(ner_descartados),
        "total": len(mapping),

        "total_entidades_distintas": len(rotulo_por_entidade),
        "total_padrao_sem_dv": sum(1 for m in mapping if m.get("origem") == "deterministica_padrao"),
        "heuristica_nome": bool(heuristica_nome and _heuristica_nome_ligada()),
        "total_heuristica_nome": sum(1 for m in mapping if str(m.get("origem", "")).startswith("heuristica_")),


        "partes_informadas": len(lista_partes),
        "partes_sem_ocorrencia": len(chaves_partes - partes_achadas),
        "total_lista_de_partes": sum(1 for m in mapping if m.get("origem") == ORIGEM_PARTES),


        "suprimidos_por_zona": suprimidos,



        "total_digito_invalido": sum(
            1 for m in mapping if m.get("origem") == "deterministica_digito_invalido"),
        "mascara_digito_invalido": _mascara_digito_invalido(),
        "prompt_injection": {"entrada": inj_entrada, "saida": inj_saida},

        "auditoria_residual": auditoria,
    }


SCHEMA_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "pseudonimizacao_local.schema.json")

INDISPONIVEL_SCHEMA = ("schema_mini.py indisponivel ao lado do modulo - sem validador nada e "
                       "conferido, e artefato de sigilo nao sai por conferir (falha fechado)")


def validar_relatorio(relatorio, schema_path=SCHEMA_PADRAO):
    '[] quando o relatorio bate com `pseudonimizacao_local.schema.json`.'








    try:
        from schema_mini import validar_schema
    except Exception:
        return [INDISPONIVEL_SCHEMA]
    try:
        with open(schema_path, encoding="utf-8") as arquivo:
            schema = json.load(arquivo)
    except Exception as erro:
        return [f"schema {schema_path} ilegivel: {erro.__class__.__name__}: {erro}"]
    return validar_schema(relatorio, schema)


def _dentro_de_git(caminho):
    atual = os.path.realpath(os.path.abspath(os.path.dirname(caminho)))
    while True:

        if os.path.exists(os.path.join(atual, ".git")):
            return True
        pai = os.path.dirname(atual)
        if pai == atual:
            return False
        atual = pai


def raiz_local_segura(override=None):
    if override:
        base = override
    elif os.environ.get(ENV_LOCAL_ROOT):
        base = os.environ[ENV_LOCAL_ROOT]
    elif os.environ.get("LOCALAPPDATA"):
        base = os.path.join(os.environ["LOCALAPPDATA"], "Dissero", "pseudonimizacao")
    else:
        base = os.path.join(os.path.expanduser("~"), ".local", "share", "dissero", "pseudonimizacao")
    return os.path.realpath(os.path.abspath(base))


def mapping_em_local_seguro(caminho, raiz_segura=None):
    if not isinstance(caminho, str) or not caminho.strip():
        return False
    absoluto = os.path.realpath(os.path.abspath(caminho))
    raiz = raiz_local_segura(raiz_segura)
    try:
        dentro_raiz = os.path.commonpath([absoluto, raiz]) == raiz and absoluto != raiz
    except ValueError:
        dentro_raiz = False
    partes = {p for p in absoluto.replace("/", os.sep).split(os.sep) if p}
    em_nuvem = any(_componente_em_nuvem(parte) for parte in partes)
    return dentro_raiz and not _dentro_de_git(absoluto) and not em_nuvem


_RE_CASO_ID = re.compile(r"^caso-[0-9a-f]{12}$")


def caso_da_sessao(session_id):
    '(código do caso, erro) do caso registrado para a sessão. Sem caso registrado → (None,'

    try:
        import caso_raiz
        cid, _origem, erro = caso_raiz.caso_id_vigente(session_id=session_id, criar=True)
    except Exception:
        return None, "caso_id_nao_gravado"
    if cid:
        return cid, None
    return None, (None if erro == "caso_nao_registrado" else erro)


def destino_no_caso(caminho, caso_id, raiz_segura=None):
    '(caminho, erro): o artefato com valor real vai para <raiz segura>/<código do caso>/,'


    raiz = raiz_local_segura(raiz_segura)
    absoluto = os.path.realpath(os.path.abspath(caminho))
    partes = [x for x in os.path.relpath(absoluto, raiz).split(os.sep) if x]
    if partes and partes[0] == caso_id:
        return absoluto, None
    if partes and _RE_CASO_ID.match(partes[0]):
        return None, "ARTEFATO_DE_OUTRO_CASO"
    return os.path.join(raiz, caso_id, *partes), None


def ao_lado_do_derivado(artefato, saida):
    'True quando o artefato com valor real (mapping, lista de partes, MD de revisão) ficaria na'


    pasta = os.path.normcase(os.path.realpath(os.path.dirname(os.path.abspath(saida))))
    alvo = os.path.normcase(os.path.realpath(os.path.abspath(artefato)))
    try:
        return os.path.commonpath([alvo, pasta]) == pasta
    except ValueError:
        return False


def _mesmo_arquivo(a, b):
    return (os.path.normcase(os.path.realpath(os.path.abspath(a)))
            == os.path.normcase(os.path.realpath(os.path.abspath(b))))




TETO_ARQUIVOS_PASTA_DERIVADO = 2000
TETO_BYTES_JSON_CONFERIDO = 50 * 1024 * 1024
CABECALHO_REVISAO = "# Revisão da pseudonimização"


def _parece_lista_de_partes(dados):
    if isinstance(dados, dict):
        return dados.get("schema_version") == PARTES_SCHEMA
    return (isinstance(dados, list) and bool(dados)
            and all(isinstance(x, str) or (isinstance(x, dict) and "nome" in x) for x in dados))


def artefato_com_valor_na_pasta(saida):
    'Artefato com valor real que JÁ está na pasta do derivado ou abaixo dela, de qualquer'


    pasta = os.path.dirname(os.path.abspath(saida))
    if not os.path.isdir(pasta):
        return None
    vistos = 0
    for raiz, _dirs, arquivos in os.walk(pasta):
        for nome in arquivos:
            vistos += 1
            if vistos > TETO_ARQUIVOS_PASTA_DERIVADO:
                return "nao_conferida"
            caminho = os.path.join(raiz, nome)
            if _mesmo_arquivo(caminho, saida):
                continue
            extensao = os.path.splitext(nome)[1].casefold()
            try:
                if extensao == ".json" and os.path.getsize(caminho) <= TETO_BYTES_JSON_CONFERIDO:
                    with open(caminho, encoding="utf-8") as f:
                        dados = json.load(f)
                    if isinstance(dados, dict) and dados.get("schema_version") == VERSAO:
                        return "mapping"
                    if _parece_lista_de_partes(dados):
                        return "partes"
                elif extensao == ".md":
                    with open(caminho, encoding="utf-8") as f:
                        if f.readline().startswith(CABECALHO_REVISAO):
                            return "revisao"
            except (OSError, ValueError):
                continue
    return None















CODIGO_MAPPING_ILEGIVEL = "MAPPING_ILEGIVEL"
CODIGO_REVERSAO_DIVERGENTE = "REVERSAO_DIVERGENTE"
CODIGO_REVERSAO_SEM_MARCADOR = "REVERSAO_SEM_MARCADOR"
CODIGO_MARCADOR_DESCONHECIDO = "MARCADOR_DESCONHECIDO"
CODIGO_REVERSAO_AO_LADO = "REVERSAO_AO_LADO_DO_DERIVADO"
CODIGO_REVERSAO_SOBRE_MAPPING = "REVERSAO_SOBRE_O_MAPPING"
MARCADOR_RX = re.compile(r"\[(?:" + "|".join(TIPOS) + r")_\d+\]")


class ReversaoRecusada(ValueError):
    """Reversão recusada, com código nomeado. O detalhe nunca traz valor real."""

    def __init__(self, codigo, detalhe=""):
        super().__init__(codigo)
        self.codigo = codigo
        self.detalhe = detalhe


def _mapping_legivel(relatorio):
    return (isinstance(relatorio, dict) and relatorio.get("schema_version") == VERSAO
            and isinstance(relatorio.get("mapping"), list)
            and all(isinstance(m, dict) and isinstance(m.get("marcador"), str)
                    and isinstance(m.get("valor"), str) for m in relatorio["mapping"]))


def _reverter_exato(texto, relatorio):
    estrategia = relatorio.get("estrategia") or "marcador"
    if estrategia not in ESTRATEGIAS:
        raise ReversaoRecusada(CODIGO_MAPPING_ILEGIVEL, "estratégia desconhecida no mapping")
    partes, pos, anterior = [], 0, 0
    for m in sorted(relatorio["mapping"], key=lambda x: x.get("inicio", -1)):
        try:
            lacuna = int(m["inicio"]) - anterior
            substituto = _substituto(m["tipo"], m["valor"], m["marcador"], estrategia)
        except (KeyError, TypeError, ValueError):
            raise ReversaoRecusada(CODIGO_MAPPING_ILEGIVEL, "ocorrência do mapping sem posição")
        if lacuna < 0 or texto[pos + lacuna:pos + lacuna + len(substituto)] != substituto:
            raise ReversaoRecusada(CODIGO_REVERSAO_DIVERGENTE,
                                   "o texto não bate com as posições do mapping")
        partes += [texto[pos:pos + lacuna], m["valor"]]
        pos += lacuna + len(substituto)
        anterior = int(m["fim"])
    partes.append(texto[pos:])
    return "".join(partes)


def _canonicos(relatorios):
    'marcador -> valor real. O nome declarado na lista de partes vence; sem ele, a primeira'

    canon = {}
    for relatorio in relatorios:
        for m in relatorio.get("mapping") or []:
            marcador, declarado = m["marcador"], m.get("canonico")
            atual = canon.get(marcador)
            if atual is None or (declarado and not atual[1]):
                canon[marcador] = (declarado or m["valor"], bool(declarado))
    return {k: v[0] for k, v in canon.items()}


def reverter_texto(texto, relatorio, bases=()):
    'Devolve {"modo", "texto", "marcadores_revertidos", "identico_ao_original"}.'



    if not isinstance(texto, str):
        raise ValueError("texto deve ser string")
    relatorios = [relatorio] + list(bases or ())
    if not all(_mapping_legivel(r) for r in relatorios):
        raise ReversaoRecusada(CODIGO_MAPPING_ILEGIVEL, "mapping fora do contrato " + VERSAO)
    if _sha(texto) == relatorio.get("sha256_sanitizado"):
        original = _reverter_exato(texto, relatorio)
        if _sha(original) != relatorio.get("sha256_original"):
            raise ReversaoRecusada(CODIGO_REVERSAO_DIVERGENTE,
                                   "a reversão não reproduz o original registrado")
        return {"modo": "exato", "texto": original,
                "marcadores_revertidos": len(relatorio["mapping"]), "identico_ao_original": True}
    if (relatorio.get("estrategia") or "marcador") != "marcador":
        raise ReversaoRecusada(CODIGO_REVERSAO_SEM_MARCADOR,
                               "texto novo só volta de mapping feito com a estratégia marcador")
    canon = _canonicos(relatorios)
    desconhecidos = sorted({m.group(0) for m in MARCADOR_RX.finditer(texto)} - set(canon))
    if desconhecidos:
        raise ReversaoRecusada(CODIGO_MARCADOR_DESCONHECIDO,
                               "marcadores sem dono nos mappings: " + ", ".join(desconhecidos))
    trocas = [0]

    def _troca(m):
        trocas[0] += 1
        return canon[m.group(0)]

    return {"modo": "minuta", "texto": MARCADOR_RX.sub(_troca, texto),
            "marcadores_revertidos": trocas[0], "identico_ao_original": None}


def validar_autorizacao(caminho, hoje=None):
    if not caminho or not os.path.isfile(caminho):
        return ["autorização local ausente"]
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, json.JSONDecodeError) as erro:
        return [f"autorização local ilegível: {erro}"]
    if not isinstance(dados, dict):
        return ["autorização local deve ser objeto JSON"]
    erros = []
    if dados.get("schema_version") != "dsr.pseudonimizacao.autorizacao.v1":
        erros.append("schema de autorização inválido")
    if dados.get("authorized_by_lawyer") is not True:
        erros.append("autorização expressa do advogado ausente")
    if not str(dados.get("scope") or "").strip():
        erros.append("escopo da autorização ausente")
    try:
        expira = _dt.date.fromisoformat(str(dados.get("expires_at") or "")[:10])
    except ValueError:
        expira = None
    if hoje is None:
        hoje = _dt.date.today()
    elif isinstance(hoje, _dt.datetime) or not isinstance(hoje, _dt.date):
        erros.append("parâmetro hoje deve ser date")
        hoje = _dt.date.today()
    if not expira or expira < hoje:
        erros.append("autorização ausente ou vencida")
    return erros


def main():


    p = argparse.ArgumentParser(description="Pseudonimização local; não desclassifica sigilo.",
                                allow_abbrev=False)
    p.add_argument("entrada", nargs="?")
    p.add_argument("-o", "--saida")
    p.add_argument("--mapping")
    p.add_argument("--autorizacao",
                   help="JSON local com aval expresso, escopo e vencimento")
    p.add_argument("--ner-json", dest="ner_json",
                   help="JSON com ocorrências marcadas {inicio, fim, tipo: PESSOA|LOCAL, confianca}, "
                        "em lista ou sob a chave 'ocorrencias'")
    p.add_argument("--mascarar-locais", dest="mascarar_locais", action="store_true",
                   help="também mascara LOCAL vindo das ocorrências marcadas (cidades, topônimos)")
    p.add_argument("--estrategia", choices=ESTRATEGIAS, default="marcador",
                   help="marcador [TIPO_n] (padrão) · parcial (J*** d* S****) · total (****)")
    p.add_argument("--excecoes", help="JSON de exceções do advogado (padrão: %s na raiz local segura)" % NOME_EXCECOES)
    p.add_argument("--liberar", metavar="TERMO",
                   help="grava TERMO como 'não é dado pessoal' nas exceções e sai")
    p.add_argument("--tipo", default="*", help="tipo da exceção de --liberar: * (padrão), PESSOA ou LOCAL")
    p.add_argument("--mapping-base", dest="mapping_base",
                   help="mapping de peça anterior do mesmo caso: numeração única entre peças ([PESSOA_1] é a mesma pessoa)")
    p.add_argument("--revisao", help="grava um MD de revisão (tipo, confiança, origem, valor, contexto) na raiz local segura")
    p.add_argument("--sem-heuristica-nome", dest="sem_heuristica_nome", action="store_true",
                   help="desliga o detector embarcado de nome por qualificação/rótulo de parte e testemunha")
    p.add_argument("--partes",
                   help="JSON da lista de partes (%s): {nome, variantes}; uma pessoa, um rótulo, "
                        "qualquer grafia. Só na raiz local segura" % PARTES_SCHEMA)
    p.add_argument("--session-id", dest="session_id",
                   help="sessão do caso registrado (caso_raiz.py): mapping e MD de revisão vão para "
                        "<raiz local segura>/<código do caso>/")
    p.add_argument("--reverter", metavar="MINUTA",
                   help="devolve os nomes reais à MINUTA pelo --mapping; grava -o na raiz local segura e sai")
    args = p.parse_args()
    if not capacidade_ligada():
        print(json.dumps({"ok": False, "codigo": "CAPACIDADE_DESABILITADA",
                          "orientacao": f"{ENV_ENABLE}=0 desligou a pseudonimização nesta sessão"}, ensure_ascii=False))
        return 2
    if args.reverter:
        return _cli_reverter(args)
    caminho_excecoes = args.excecoes or os.path.join(raiz_local_segura(), NOME_EXCECOES)
    if args.liberar:
        if not mapping_em_local_seguro(caminho_excecoes):
            print(json.dumps({"ok": False, "codigo": "ARTEFATO_EM_LOCAL_INSEGURO",
                              "orientacao": "as exceções ficam na raiz local segura",
                              "raiz_local_segura": raiz_local_segura()}, ensure_ascii=False))
            return 2
        try:
            n = liberar_termo(caminho_excecoes, args.liberar, args.tipo)
        except ValueError as erro:
            print(json.dumps({"ok": False, "codigo": "EXCECOES_ILEGIVEIS", "erro": str(erro)}, ensure_ascii=False))
            return 2
        print(json.dumps({"ok": True, "liberado": args.liberar, "tipo": args.tipo,
                          "excecoes": caminho_excecoes, "total_excecoes": n,
                          "nota": "vale para toda execução seguinte que use este arquivo de exceções"}, ensure_ascii=False))
        return 0
    if not (args.entrada and args.saida and args.mapping):
        print(json.dumps({"ok": False, "codigo": "USO_INVALIDO",
                          "orientacao": "informe entrada, -o/--saida e --mapping (ou --liberar TERMO)"}, ensure_ascii=False))
        return 2
    erros_autorizacao = validar_autorizacao(args.autorizacao)
    if erros_autorizacao:
        print(json.dumps({"ok": False, "codigo": "AUTORIZACAO_INVALIDA",
                          "violacoes": erros_autorizacao}, ensure_ascii=False))
        return 2
    if not mapping_em_local_seguro(args.mapping) or not mapping_em_local_seguro(args.saida):
        print(json.dumps({"ok": False, "codigo": "ARTEFATO_EM_LOCAL_INSEGURO",
                          "orientacao": "grave saída e mapping dentro da raiz local segura",
                          "raiz_local_segura": raiz_local_segura()}, ensure_ascii=False))
        return 2
    if args.revisao and not mapping_em_local_seguro(args.revisao):
        print(json.dumps({"ok": False, "codigo": "ARTEFATO_EM_LOCAL_INSEGURO",
                          "orientacao": "o MD de revisão traz os valores originais: só na raiz local segura",
                          "raiz_local_segura": raiz_local_segura()}, ensure_ascii=False))
        return 2
    if args.partes and not mapping_em_local_seguro(args.partes):
        print(json.dumps({"ok": False, "codigo": "ARTEFATO_EM_LOCAL_INSEGURO",
                          "orientacao": "a lista de partes traz os nomes reais: só na raiz local segura",
                          "raiz_local_segura": raiz_local_segura()}, ensure_ascii=False))
        return 2


    caso_id = None
    if args.session_id:
        caso_id, erro_caso = caso_da_sessao(args.session_id)
        if erro_caso:
            print(json.dumps({"ok": False, "codigo": "CODIGO_DO_CASO_ILEGIVEL",
                              "orientacao": "o caso desta sessão está registrado, mas o código dele "
                                            "não pôde ser lido nem gravado; confira com caso_raiz.py id. "
                                            "Nada foi gravado"}, ensure_ascii=False))
            return 2
    if caso_id:
        for atributo in ("mapping", "revisao"):
            caminho = getattr(args, atributo)
            if not caminho:
                continue
            novo, erro_destino = destino_no_caso(caminho, caso_id)
            if erro_destino:
                print(json.dumps({"ok": False, "codigo": erro_destino, "artefato": atributo,
                                  "orientacao": "o %s está apontado para a pasta de outro caso na raiz "
                                                "segura; grave-o na pasta deste caso. Nada foi gravado"
                                                % atributo}, ensure_ascii=False))
                return 2
            setattr(args, atributo, novo)


    for rotulo, caminho in (("mapping", args.mapping), ("revisao", args.revisao), ("partes", args.partes),
                            ("mapping_base", args.mapping_base)):
        if caminho and ao_lado_do_derivado(caminho, args.saida):
            print(json.dumps({"ok": False, "codigo": "MAPPING_AO_LADO_DO_DERIVADO", "artefato": rotulo,
                              "orientacao": "grave o texto mascarado numa pasta só dele (por exemplo "
                                            "<raiz>/derivados/) e o %s fora dela (por exemplo "
                                            "<raiz>/mapas/); nada foi gravado" % rotulo},
                             ensure_ascii=False))
            return 2

    ja_na_pasta = artefato_com_valor_na_pasta(args.saida)
    if ja_na_pasta == "nao_conferida":
        print(json.dumps({"ok": False, "codigo": "PASTA_DO_DERIVADO_NAO_CONFERIDA",
                          "orientacao": "a pasta do texto mascarado tem arquivos demais para conferir; "
                                        "grave-o numa pasta só dele (por exemplo <raiz>/derivados/). "
                                        "Nada foi gravado"}, ensure_ascii=False))
        return 2
    if ja_na_pasta:
        print(json.dumps({"ok": False, "codigo": "MAPPING_AO_LADO_DO_DERIVADO", "artefato": ja_na_pasta,
                          "orientacao": "a pasta do texto mascarado já guarda um arquivo com os dados "
                                        "reais (%s de outra peça); quem subir a pasta o levaria junto. "
                                        "Grave o texto mascarado numa pasta só dele (por exemplo "
                                        "<raiz>/derivados/) e tire de lá esse arquivo; nada foi gravado"
                                        % ja_na_pasta}, ensure_ascii=False))
        return 2
    partes = None
    if args.partes:
        try:
            with open(args.partes, encoding="utf-8") as f:
                partes = json.load(f)
            normalizar_partes(partes)
        except (OSError, json.JSONDecodeError) as erro:
            print(json.dumps({"ok": False, "codigo": "PARTES_ILEGIVEIS",
                              "erro": erro.__class__.__name__}, ensure_ascii=False))
            return 2
        except PartesInvalidas as erro:
            print(json.dumps({"ok": False, "codigo": erro.codigo, "violacoes": erro.violacoes,
                              "orientacao": "corrija a lista de partes; nada foi gravado"},
                             ensure_ascii=False))
            return 2




    try:
        with open(args.entrada, encoding="utf-8", newline="") as f:
            texto = f.read()
    except UnicodeDecodeError:
        print(json.dumps({"ok": False, "codigo": "ENTRADA_FORA_DE_UTF8",
                          "orientacao": "o texto não está em UTF-8; salve-o em UTF-8 (por exemplo, "
                                        "\"Salvar como\" com a codificação UTF-8) e rode de novo. "
                                        "Nada foi gravado"}, ensure_ascii=False))
        return 2
    except OSError as erro:
        print(json.dumps({"ok": False, "codigo": "ENTRADA_ILEGIVEL",
                          "erro": erro.__class__.__name__}, ensure_ascii=False))
        return 2
    excecoes, erro_exc = carregar_excecoes(caminho_excecoes)
    if erro_exc:
        print(json.dumps({"ok": False, "codigo": "EXCECOES_ILEGIVEIS", "erro": erro_exc,
                          "excecoes": caminho_excecoes}, ensure_ascii=False))
        return 2
    mapping_base = None
    if args.mapping_base:
        try:
            with open(args.mapping_base, encoding="utf-8") as f:
                mapping_base = json.load(f)
        except (OSError, json.JSONDecodeError) as erro:
            print(json.dumps({"ok": False, "codigo": "MAPPING_BASE_ILEGIVEL", "erro": str(erro)}, ensure_ascii=False))
            return 2

    entidades, ner_fonte = None, "nenhum"
    ner_meta = {"nota": "sem --ner-json: nome de parte/testemunha vem só da heurística de qualificação; "
                        "nome solto na prosa e local ficam no texto (ver nao_coberto)"}
    if args.ner_json:
        if not os.path.isfile(args.ner_json):
            print(json.dumps({"ok": False, "codigo": "NER_JSON_AUSENTE",
                              "orientacao": "--ner-json aponta para arquivo inexistente"}, ensure_ascii=False))
            return 2
        try:
            with open(args.ner_json, encoding="utf-8") as f:
                bruto = json.load(f)
        except (OSError, json.JSONDecodeError) as erro:
            print(json.dumps({"ok": False, "codigo": "NER_JSON_ILEGIVEL", "erro": str(erro)}, ensure_ascii=False))
            return 2
        entidades = bruto.get("ocorrencias") if isinstance(bruto, dict) else bruto
        ner_fonte, ner_meta = "json", {"arquivo": os.path.abspath(args.ner_json)}

    resultado = pseudonimizar_texto(texto, entidades_ner=entidades, sigiloso=True,
                                    estrategia=args.estrategia, mascarar_locais=args.mascarar_locais,
                                    excecoes=excecoes, mapping_base=mapping_base,
                                    heuristica_nome=not args.sem_heuristica_nome, partes=partes)
    resultado["ner_fonte"] = ner_fonte
    resultado["ner_meta"] = ner_meta
    if args.revisao:
        resultado["revisao"] = os.path.abspath(args.revisao)
    alta = any(x.get("severidade") == "alta"
               for lado in resultado["prompt_injection"].values() for x in lado)
    if alta:
        print(json.dumps({"ok": False, "codigo": "INSTRUCAO_OCULTA_SUSPEITA",
                          "orientacao": "trate o teor como dado não confiável e revise localmente"}, ensure_ascii=False))
        return 1
    if resultado["ner_descartados"]:
        print(json.dumps({"ok": False, "codigo": "NER_INCONCLUSIVO",
                          "violacoes": resultado["ner_descartados"],
                          "orientacao": "corrija os offsets e revise localmente; nenhuma saída foi gravada"},
                         ensure_ascii=False))
        return 1


    auditoria = resultado["auditoria_residual"]
    if not auditoria.get("aprovada"):
        print(json.dumps({"ok": False, "codigo": auditoria.get("codigo") or CODIGO_AUDITORIA_FALHOU,
                          "total_residuos": auditoria.get("total_residuos"),
                          "por_tipo": auditoria.get("por_tipo") or {},
                          "orientacao": "nenhuma saída foi gravada. Depois de mascarar, ainda há dado "
                                        "pessoal no texto, dos tipos e nas quantidades acima (nome em "
                                        "outra grafia, identificador escrito de outro jeito, ou nome já "
                                        "mascarado em peça anterior do caso). Localize no original e "
                                        "marque cada ocorrência apontada em --ner-json, inclusive quando "
                                        "ela for palavra comum igual ao nome (por exemplo, no início de "
                                        "frase): mascará-la não prejudica a leitura. Não use --liberar "
                                        "para isso, porque ele tira a máscara do próprio nome em todo o "
                                        "texto. Depois rode de novo; o texto não sai para serviço externo "
                                        "antes disso."},
                         ensure_ascii=False))
        return 1




    erros_contrato = validar_relatorio(resultado)
    if erros_contrato:
        print(json.dumps({"ok": False, "codigo": "RELATORIO_FORA_DO_CONTRATO",
                          "violacoes": erros_contrato,
                          "orientacao": "nenhuma saída foi gravada; o relatório da camada não "
                                        "bate com pseudonimizacao_local.schema.json"},
                         ensure_ascii=False))
        return 2
    os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.mapping)), exist_ok=True)
    with open(args.saida, "w", encoding="utf-8", newline="") as f:
        f.write(resultado["texto_sanitizado"])
    if args.revisao:
        os.makedirs(os.path.dirname(os.path.abspath(args.revisao)), exist_ok=True)
        with open(args.revisao, "w", encoding="utf-8") as f:
            f.write(md_revisao(texto, resultado, caminho_excecoes))
    mapa = {k: v for k, v in resultado.items() if k != "texto_sanitizado"}
    with open(args.mapping, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"ok": True, "saida": os.path.abspath(args.saida),
                      "mapping": os.path.abspath(args.mapping), "caso_id": caso_id,
                      "total": resultado["total"],
                      "total_entidades_distintas": resultado["total_entidades_distintas"],
                      "estrategia": args.estrategia, "ner_fonte": ner_fonte,
                      "revisao": resultado.get("revisao"),
                      "partes_informadas": resultado["partes_informadas"],
                      "partes_sem_ocorrencia": resultado["partes_sem_ocorrencia"],
                      "nao_coberto": resultado["nao_coberto"][:2],
                      "sigiloso_saida": resultado["sigiloso_saida"],
                      "auditoria_residual": {"aprovada": True, "total_residuos": 0},
                      "revisao_humana_obrigatoria": True}, ensure_ascii=False))
    return 0


def _cli_reverter(args):
    """--reverter MINUTA -o SAÍDA --mapping MAPPING [--mapping-base ...]: só na raiz segura."""
    def _recusa(codigo, retorno=2, **extra):
        print(json.dumps({"ok": False, "codigo": codigo, **extra}, ensure_ascii=False))
        return retorno
    if not (args.saida and args.mapping):
        return _recusa("USO_INVALIDO", orientacao="informe --reverter <minuta>, -o/--saida e --mapping")
    for caminho in (args.mapping, args.mapping_base):
        if caminho and not mapping_em_local_seguro(caminho):
            return _recusa("MAPPING_FORA_DA_RAIZ_SEGURA", raiz_local_segura=raiz_local_segura(),
                           orientacao="a reversão só lê o mapping onde ele vive, na raiz local segura")
    if not mapping_em_local_seguro(args.saida):
        return _recusa("REVERSAO_FORA_DA_RAIZ_SEGURA", raiz_local_segura=raiz_local_segura(),
                       orientacao="o texto revertido traz os nomes reais: grave-o na raiz local segura")




    pasta_minuta = os.path.dirname(os.path.abspath(args.reverter))
    if (_mesmo_arquivo(os.path.dirname(os.path.abspath(args.saida)), pasta_minuta)
            or (ao_lado_do_derivado(args.saida, args.reverter)
                and mapping_em_local_seguro(os.path.join(pasta_minuta, "x")))):
        return _recusa(CODIGO_REVERSAO_AO_LADO, orientacao=(
            "o texto revertido traz os nomes reais e não pode ficar na pasta do texto mascarado, "
            "nem substituí-lo: grave-o numa pasta só de revertidos (por exemplo <raiz>/revertidos/). "
            "Nada foi gravado"))
    if any(c and _mesmo_arquivo(args.saida, c) for c in (args.mapping, args.mapping_base)):
        return _recusa(CODIGO_REVERSAO_SOBRE_MAPPING, orientacao=(
            "a saída apontaria para o próprio mapping e o apagaria; escolha outro arquivo. "
            "Nada foi gravado"))
    relatorios = []
    for caminho in (args.mapping, args.mapping_base):
        if not caminho:
            continue
        try:
            with open(caminho, encoding="utf-8") as f:
                relatorios.append(json.load(f))
        except (OSError, json.JSONDecodeError) as erro:
            return _recusa(CODIGO_MAPPING_ILEGIVEL, erro=erro.__class__.__name__)
    try:
        with open(args.reverter, encoding="utf-8", newline="") as f:
            minuta = f.read()
    except (OSError, UnicodeDecodeError) as erro:
        return _recusa("MINUTA_ILEGIVEL", erro=erro.__class__.__name__)
    try:
        r = reverter_texto(minuta, relatorios[0], relatorios[1:])
    except ReversaoRecusada as erro:
        return _recusa(erro.codigo, 1, detalhe=erro.detalhe,
                       orientacao="nada foi gravado; confira se a minuta e o mapping são da mesma peça")
    os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
    with open(args.saida, "w", encoding="utf-8", newline="") as f:
        f.write(r["texto"])
    print(json.dumps({"ok": True, "saida": os.path.abspath(args.saida), "modo": r["modo"],
                      "marcadores_revertidos": r["marcadores_revertidos"],
                      "identico_ao_original": r["identico_ao_original"],

                      "sigiloso_saida": True, "desclassifica_sigilo": False,
                      "aviso": "o texto revertido traz os nomes reais e continua sigiloso: "
                               "trate-o como o original"}, ensure_ascii=False))
    return 0


def md_revisao(texto, resultado, caminho_excecoes):
    'MD de REVISAO: cada ocorrencia com tipo,'


    linhas = ["# Revisão da pseudonimização — CONFIRA ANTES DE USAR O TEXTO MASCARADO", "",
              f"sha256 do original: {resultado['sha256_original']} · estratégia: {resultado['estrategia']} · "
              f"ocorrências: {resultado['total']} · entidades: {resultado['total_entidades_distintas']} · "
              f"NER: {resultado.get('ner_fonte') or 'nenhum'}", "",
              "Auditoria residual do texto mascarado: "
              + ("aprovada, nada sobrou" if (resultado.get("auditoria_residual") or {}).get("aprovada")
                 else "NÃO aprovada"), "",
              "Palavra igual a um nome de uma palavra só, deixada sem máscara por estar em minúscula "
              "ou fazer parte de outro nome (\"15 dias\", \"São Paulo\"); confira se nenhuma é a "
              "pessoa: " + (", ".join(f"{t} {n}" for t, n in sorted(
                  ((resultado.get("auditoria_residual") or {}).get("possiveis_por_tipo") or {}).items()))
                  or "nenhuma"), "",
              "Falso positivo? Libere o termo e ele deixa de ser mascarado nas execuções seguintes:", "",
              f"    python3 pseudonimizar_local.py --liberar \"<termo>\" [--tipo PESSOA|LOCAL] --excecoes \"{caminho_excecoes}\"", ""]
    por_tipo = {}
    for m in resultado["mapping"]:
        por_tipo.setdefault(m["tipo"], []).append(m)
    for tipo in sorted(por_tipo):
        itens = por_tipo[tipo]
        linhas += [f"## {tipo} — {len(itens)} ocorrência(s)", "", "| marcador | confiança | origem | valor | contexto |", "|---|---|---|---|---|"]
        for m in sorted(itens, key=lambda x: x["confianca"]):
            a, b = max(0, m["inicio"] - 40), min(len(texto), m["fim"] + 40)
            ctx = texto[a:b].replace("\n", " ").replace("|", "\\|")
            linhas.append(f"| {m['marcador']} | {m['confianca']:.2f} | {m['origem']} | {str(m['valor']).replace('|', '/')} | …{ctx}… |")
        linhas.append("")
    if resultado.get("suprimidos_por_zona"):
        linhas += ["## Suprimidos por zona protegida (conferir se a supressão foi legítima)", ""]
        for s in resultado["suprimidos_por_zona"]:
            linhas.append(f"- {s['tipo']} em zona `{s['zona']}` (posição {s['inicio']}–{s['fim']}, sha {s['valor_sha256_12']})")
        linhas.append("")
    linhas += ["## O que esta camada NÃO cobre", ""] + [f"- {x}" for x in resultado["nao_coberto"]] + [""]
    return "\n".join(linhas)


if __name__ == "__main__":
    raise SystemExit(main())
