#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'conferencia_contract.py — contrato e regras cruzadas de `dsr.conferencia.v1`.'









































































from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema_mini import validar_schema

AQUI = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PADRAO = os.path.join(AQUI, "schema_conferencia.json")

SCHEMA_VERSION = "dsr.conferencia.v1"
NOME_ARTEFATO = "CONFERENCIA.json"
SENTINELAS = ("PDF_SEM_TEXTO_EXTRAIVEL", "TIPO_NAO_SUPORTADO")


ROTA_IMAGEM = "visual"
MOTOR_LEITURA_VISUAL = "leitura_visual"


MOTORES_IMAGEM = frozenset({MOTOR_LEITURA_VISUAL, "pdftoppm"})

PISO_TRECHO = 25


def motor_normalizado(valor):
    return str(valor or "").strip().lower()


def motor_de_imagem(valor):
    return motor_normalizado(valor) in MOTORES_IMAGEM





MOTORES_OCR = frozenset({"eluxi", "tesseract", "ocrmypdf", "paddleocr", "easyocr", "rapidocr"})

EXTENSOES_IMAGEM = (".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".pjpeg", ".pjp", ".tif",
                    ".tiff", ".bmp", ".dib", ".gif", ".webp", ".heic", ".heif", ".avif",
                    ".jp2", ".j2k", ".jpf", ".jpx", ".jxl")



_ASSINATURAS_IMAGEM = (
    b"\xff\xd8\xff",
    b"\x89PNG\r\n\x1a\n",
    b"GIF87a", b"GIF89a",
    b"II*\x00", b"MM\x00*",
    b"\x00\x00\x00\x0cjP  \r\n\x87\n",
    b"\xff\x4f\xff\x51",
    b"\xff\x0a",
    b"\x00\x00\x00\x0cJXL \r\n\x87\n",
)
_MARCAS_FTYP_IMAGEM = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1",
                       b"msf1", b"avif", b"avis")


def _bytes_de_imagem(cabeca):
    if not cabeca:
        return False
    if cabeca.startswith(b"BM"):

        return len(cabeca) >= 18 and cabeca[14:18] in (b"\x0c\x00\x00\x00", b"\x28\x00\x00\x00",
                                                        b"\x38\x00\x00\x00", b"\x40\x00\x00\x00",
                                                        b"\x6c\x00\x00\x00", b"\x7c\x00\x00\x00")
    if any(cabeca.startswith(a) for a in _ASSINATURAS_IMAGEM):
        return True
    if cabeca[:4] == b"RIFF" and cabeca[8:12] == b"WEBP":
        return True
    if cabeca[4:8] == b"ftyp" and cabeca[8:12] in _MARCAS_FTYP_IMAGEM:
        return True
    return False


def motor_ocr(valor):
    return motor_normalizado(valor) in MOTORES_OCR


def arquivo_de_imagem(caminho):
    """Foto ou digitalização avulsa: pela extensão OU pela assinatura dos bytes iniciais."""
    nome = str(caminho or "").strip()
    if nome.lower().endswith(EXTENSOES_IMAGEM):
        return True
    try:
        with open(nome, "rb") as fh:
            return _bytes_de_imagem(fh.read(32))
    except OSError:
        return False





_ASSINATURA_PDF = b"%PDF-"


def arquivo_pdf(caminho):
    """PDF: pela extensão `.pdf` OU pelo cabeçalho `%PDF-` no primeiro KB do arquivo."""
    nome = str(caminho or "").strip()
    if nome.lower().endswith(".pdf"):
        return True
    try:
        with open(nome, "rb") as fh:
            return _ASSINATURA_PDF in fh.read(1024)
    except OSError:
        return False


def texto(valor):
    return str(valor or "").strip()


def sha256_texto(valor):
    return hashlib.sha256(texto(valor).encode("utf-8")).hexdigest()


def sha256_arquivo(caminho):
    'SHA-256 do arquivo ORIGINAL. É o que prova que o arquivo foi aberto: quem não abre não'

    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def doc_id_de(sha_arquivo):
    """Identificador do documento = conteúdo dele (12 hex do sha do arquivo)."""
    return texto(sha_arquivo)[:12]


def evidence_id(sha_arquivo, pagina, offset, tamanho):
    'Identificador estável do TRECHO. Determinístico e sem estado: depende só do conteúdo'


    p = "" if pagina is None else str(int(pagina))
    semente = f"{texto(sha_arquivo)}:{p}:{int(offset)}:{int(tamanho)}"
    return hashlib.sha256(semente.encode("utf-8")).hexdigest()[:16]


def carregar_json(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def derivar_leitura_status(documento):
    '`lido` | `parcial` | `nao_lido` | `indexado` — DERIVADO, nunca declarado.'










    if texto(documento.get("sentinela")):
        return "nao_lido"
    if not (documento.get("trechos") or []):
        if isinstance(documento.get("indice_eluxi"), dict) and documento.get("detector") != "escalar":
            return "indexado"
        return "nao_lido"
    if documento.get("detector") == "escalar":
        return "nao_lido"
    if lido_so_por_imagem(documento) and not any(
            len(normalizar_trecho(t.get("trecho_literal"))) >= PISO_TRECHO
            for t in (documento.get("trechos") or [])):

        return "nao_lido"
    cobertura = documento.get("cobertura") or {}
    if documento.get("confianca") == "baixa" or (cobertura.get("faltando") or []):
        return "parcial"
    return "lido"


def validar_regras(documento):
    erros = []
    rotulo = texto(documento.get("arquivo")) or texto(documento.get("doc_id"))
    prefixo = f"{rotulo}: "

    esperado = derivar_leitura_status(documento)
    if documento.get("leitura_status") != esperado:
        erros.append(prefixo + f"leitura_status deve ser derivado como {esperado}")

    sha_arq = texto(documento.get("sha256_arquivo"))
    if documento.get("doc_id") != doc_id_de(sha_arq):
        erros.append(prefixo + "doc_id deve ser os 12 primeiros hex do sha256_arquivo")

    sentinela = texto(documento.get("sentinela"))
    trechos = documento.get("trechos") or []
    if sentinela and trechos:
        erros.append(prefixo + f"sentinela {sentinela} com {len(trechos)} trecho(s): documento "
                               "não lido não tem teor — trecho aqui é teor improvisado")

    for indice, trecho in enumerate(trechos):
        marca = prefixo + f"trecho[{indice}]: "
        literal = trecho.get("trecho_literal")
        if trecho.get("sha256_trecho") != sha256_texto(literal):
            erros.append(marca + "sha256_trecho não corresponde ao trecho_literal (teor alterado "
                                 "depois do registro)")
        pagina = trecho.get("pagina")
        if documento.get("origem") == "eluxi" and pagina is None:
            erros.append(marca + "origem eluxi exige pagina (o conector devolve página e linhas)")
        if pagina is not None and pagina < 1:
            erros.append(marca + "pagina deve ser ≥ 1")


    numeracao = documento.get("numeracao")
    inicial = documento.get("pagina_inicial")
    if numeracao is not None and numeracao_de(documento) is None:
        erros.append(prefixo + f"numeracao {numeracao!r} inválida — use 'autos' ou 'arquivo'")
    elif numeracao_de(documento) == "autos":
        if not isinstance(inicial, int) or inicial < 1:
            erros.append(prefixo + "numeracao 'autos' exige pagina_inicial ≥ 1 (a folha da 1ª "
                                   "página): sem a base, dizer que `pagina` é folha dos autos "
                                   "não é conferível")
        else:
            fora = [t.get("pagina") for t in trechos
                    if isinstance(t.get("pagina"), int) and t["pagina"] < inicial]
            if fora:
                erros.append(prefixo + f"numeracao 'autos' com pagina_inicial {inicial}, mas "
                                       f"trecho(s) em página {sorted(set(fora))} — anterior à "
                                       "primeira folha do documento")
    elif numeracao_de(documento) == "arquivo" and isinstance(inicial, int) and inicial != 1:
        erros.append(prefixo + f"numeracao 'arquivo' com pagina_inicial {inicial}: posição no "
                               "arquivo conta de 1 — se a base é folha dos autos, declare "
                               "numeracao 'autos'")



    if (motor_de_imagem(documento.get("motor"))
            and motor_normalizado(documento.get("rota")) != ROTA_IMAGEM):
        erros.append(prefixo + f"motor de imagem {texto(documento.get('motor'))} declarado na rota "
                               f"{texto(documento.get('rota')) or '—'}: leitura por imagem é rota "
                               f"{ROTA_IMAGEM}")


    pst = documento.get("paginas_sem_texto")
    if pst is not None and (not isinstance(pst, list)
                            or any(not isinstance(p, int) or p < 1 for p in pst)
                            or pst != sorted(set(pst))):
        erros.append(prefixo + "paginas_sem_texto deve ser lista ordenada de inteiros ≥ 1, sem "
                               "repetição")

    if documento.get("indice_eluxi") is not None and documento.get("origem") != "eluxi":
        erros.append(prefixo + "indice_eluxi só cabe em documento de origem eluxi")
    if documento.get("paginas_lidas") is not None:
        pl = documento.get("paginas_lidas")
        if not isinstance(pl, list) or any(not isinstance(p, int) or p < 1 for p in pl) or pl != sorted(set(pl)):
            erros.append(prefixo + "paginas_lidas deve ser lista ordenada de inteiros ≥ 1, sem repetição")

    ids = [texto(t.get("evidence_id")) for t in trechos]
    if len(set(ids)) != len(ids):
        erros.append(prefixo + "evidence_id repetido no mesmo documento")

    cobertura = documento.get("cobertura") or {}
    total = documento.get("paginas_total")
    com_teor = cobertura.get("paginas_com_teor")
    if isinstance(total, int) and isinstance(com_teor, int) and com_teor > total:
        erros.append(prefixo + f"cobertura.paginas_com_teor ({com_teor}) maior que paginas_total ({total})")
    return erros


def validar_documento(dados, schema_path=SCHEMA_PADRAO):
    """[] quando o dataset está íntegro; lista de erros legíveis quando não."""
    erros = validar_schema(dados, carregar_json(schema_path))
    if erros:
        return erros
    vistos = {}
    for documento in dados["documentos"]:
        erros.extend(validar_regras(documento))
        chave = texto(documento.get("sha256_arquivo"))
        if chave in vistos:
            erros.append(f"{texto(documento.get('arquivo'))}: arquivo repetido no dataset "
                         f"(mesmo sha256 de {vistos[chave]})")
        else:
            vistos[chave] = texto(documento.get("arquivo"))
    return erros







_ELIPSES = ("[...]", "[…]", "(...)", "(…)", "…", "...")


def normalizar_trecho(valor, manter_acento=False):
    'Forma canônica de comparação: sem acento, minúscula, TODA pontuação virando espaço,'












    if manter_acento:
        texto_ = unicodedata.normalize("NFC", str(valor or ""))
    else:
        texto_ = unicodedata.normalize("NFKD", str(valor or ""))
        texto_ = "".join(c for c in texto_ if not unicodedata.combining(c))
    texto_ = "".join(c if (c.isalnum() or c.isspace()) else " " for c in texto_)
    return " ".join(texto_.casefold().split())


def _casa_em_ordem(partes, fonte):
    'Todas as partes aparecem na fonte, NA ORDEM em que foram transcritas. Ordem importa:'


    pos = 0
    for parte in partes:
        achou = fonte.find(parte, pos)
        if achou < 0:
            return False
        pos = achou + len(parte)
    return True


def confere_transcricao(trecho, armazenados, minimo=25, minimo_parte=12, manter_acento=False):
    'True se o `trecho` transcrito na peça confere com o teor lido do documento.'










    alvo = normalizar_trecho(trecho, manter_acento)
    if len(alvo) < minimo:
        return True


    partes_brutas = [str(trecho or "")]
    for marca in _ELIPSES:
        novas = []
        for p in partes_brutas:
            novas += p.split(marca)
        partes_brutas = novas
    partes = [normalizar_trecho(p, manter_acento) for p in partes_brutas]
    filtradas = [p for p in partes if len(p) >= minimo_parte]
    if not filtradas:








        filtradas = [p for p in partes if p]
    if not filtradas:
        return False
    partes = filtradas
    fontes = [normalizar_trecho(b, manter_acento) for b in armazenados]
    if len(fontes) > 1:
        fontes.append(" ".join(f for f in fontes if f))
    return any(f and _casa_em_ordem(partes, f) for f in fontes)


NUMERACOES = ("autos", "arquivo")


def numeracao_de(documento):
    """"autos" | "arquivo" | None (não declarada). Ver regra cruzada 7."""
    valor = texto((documento or {}).get("numeracao"))
    return valor if valor in NUMERACOES else None


def lido_so_por_imagem(documento):
    'True quando o teor registrado do documento veio só de leitura por IMAGEM (regra 8):'



    doc = documento or {}
    return (motor_normalizado(doc.get("rota")) == ROTA_IMAGEM
            or motor_de_imagem(doc.get("motor")))


def trechos_de_texto(documento):
    'Trechos do registro que servem de FONTE LITERAL (L14, prova de contradição): nenhum'


    doc = documento or {}
    if lido_so_por_imagem(doc):
        return []
    sem_texto = set(p for p in (doc.get("paginas_sem_texto") or []) if isinstance(p, int))
    if not sem_texto:
        return list(doc.get("trechos") or [])


    return [t for t in (doc.get("trechos") or [])
            if isinstance(t.get("pagina"), int) and t["pagina"] not in sem_texto]


def paginas_do_trecho(trecho, documento, minimo=25, minimo_parte=12):
    'Páginas dos trechos ARMAZENADOS que casam, cada um por si, com a transcrição.'










    if len(normalizar_trecho(trecho)) < minimo:
        return set()
    paginas = set()
    for armazenado in (documento or {}).get("trechos") or []:
        pagina = armazenado.get("pagina")
        if not isinstance(pagina, int):
            continue
        literal = armazenado.get("trecho_literal") or ""
        if confere_transcricao(trecho, [literal], minimo=minimo, minimo_parte=minimo_parte):
            paginas.add(pagina)
    return paginas








_CARIMBO_LINHA_RX = re.compile(
    r"^(?:documento\s+)?assinad[oa]\s+(?:eletronicamente|digitalmente)\s+por\b"
    r"|^este\s+documento\s+foi\s+(?:gerado|assinado|juntado|impresso)\b"
    r"|^num\s+\d+\s+pag\s+\d+(?:\s+de\s+\d+)?$"
    r"|^numero\s+do\s+documento\s+\d+$"
    r"|^id\s+[0-9a-z]+\s+pag\s+\d+(?:\s+de\s+\d+)?$"
    r"|^fls?\s+\d+$"
    r"|^pag(?:ina)?\s+\d+(?:\s+de\s+\d+)?$"
    r"|^https?\s"
    r"|^impresso\s+(?:por|em)\b"
    r"|\bcodigo\s+(?:de\s+)?(?:verificacao|autenticacao|autenticidade)\b"
    r"|^para\s+conferir\s+o\s+original\b"
    r"|^(?:valide|validar|confira|conferir)\s+(?:a\s+)?autenticidade\b")


def texto_sem_carimbo(texto_pagina):
    'O texto da página sem as linhas que são só carimbo de sistema (assinatura eletrônica,'

    linhas = []
    for linha in str(texto_pagina or "").splitlines():
        bruta = linha.strip()
        if bruta.lower().startswith(("http://", "https://", "www.")):
            continue
        if _CARIMBO_LINHA_RX.search(normalizar_trecho(bruta)):
            continue
        linhas.append(linha)
    return "\n".join(linhas)


def pagina_tem_texto(texto_pagina):
    'A página tem camada de texto DO DOCUMENTO? Não conta o que é só carimbo de sistema, nem'

    resto = normalizar_trecho(texto_sem_carimbo(texto_pagina))
    return any(sum(c.isalpha() for c in tok) >= 3 for tok in resto.split())







PISO_PALAVRAS_CAMADA = 0.6
PISO_PARES_CAMADA = 0.3


def _tokens(texto_):
    return normalizar_trecho(texto_sem_carimbo(texto_)).split()


def _sem_espacamento(toks):
    """Os tokens sem as sequências de 3 ou mais tokens de um só caractere (letra espaçada)."""
    saida, corrida = [], []
    for tok in toks:
        if len(tok) == 1:
            corrida.append(tok)
            continue
        if len(corrida) < 3:
            saida += corrida
        corrida = []
        saida.append(tok)
    if len(corrida) < 3:
        saida += corrida
    return saida


def camada_normalizada(paginas_texto):
    '(palavras, pares) da camada de texto inteira, para `teor_confere_com_camada`.'








    palavras, pares = set(), set()
    for pagina in paginas_texto or []:
        for toks in (_tokens(pagina), normalizar_trecho(pagina).split()):
            palavras.update(toks)
            pares.update(zip(toks, toks[1:]))
    return palavras, pares


def teor_confere_com_camada(trecho, camada):
    'True se o trecho do teor declarado vem da camada de texto (`camada_normalizada`). None'






    toks = _sem_espacamento(_tokens(trecho))
    if len(" ".join(toks)) < PISO_TRECHO or len(toks) < 2:
        return None
    palavras, pares = camada
    cob_palavras = sum(t in palavras for t in toks) / len(toks)
    seus_pares = list(zip(toks, toks[1:]))
    cob_pares = sum(p in pares for p in seus_pares) / len(seus_pares)
    return cob_palavras >= PISO_PALAVRAS_CAMADA and cob_pares >= PISO_PARES_CAMADA


def indexar(dados):
    """{sha256_arquivo: documento} — usado pelo cruzamento da juntada."""
    return {texto(d.get("sha256_arquivo")): d for d in (dados.get("documentos") or [])}


def evidence_ids(dados):
    """Todos os evidence_id do dataset (para cruzamento)."""
    return {texto(t.get("evidence_id"))
            for d in (dados.get("documentos") or [])
            for t in (d.get("trechos") or [])}
