#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'varredura_documento.py — Varredura ESTRUTURAL de documento: entrada e saída (Dissero).'
























































import base64
import bisect
import hashlib
import html
import io
import json
import os
import re
import sys
import unicodedata
import zipfile
import zlib





try:
    import contraste_wcag as _cw
except ImportError:
    import importlib.util as _ilu
    _p_cw = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contraste_wcag.py")
    _s_cw = _ilu.spec_from_file_location("contraste_wcag", _p_cw)
    _cw = _ilu.module_from_spec(_s_cw)
    _s_cw.loader.exec_module(_cw)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass




TEM_CAMADA_PROFUNDA = False

AVISO_SEM_CAMADA_PROFUNDA = (
    "camada profunda AUSENTE (a página não é renderizada): não foram verificados a COR "
    "efetiva de cada trecho após máscaras, o TAMANHO efetivo de fonte após a matriz de texto "
    "nem o texto posto fora da página ou coberto por imagem ou desenho. A varredura estrutural "
    "rodou e vale; a cobertura é PARCIAL.")


AVISO_COM_CAMADA_PROFUNDA = (
    "camada profunda pelo poppler: posição e tamanho efetivo das palavras conferidos; a COR "
    "efetiva após máscaras e o texto coberto por imagem ou desenho continuam não verificados. A "
    "cobertura é PARCIAL nesses pontos.")
AVISO_SEM_DETECTOR = (
    " O texto de anotações, campos, camadas, metadados e arquivos embutidos foi lido, mas o "
    "detector de instrução dirigida à IA não está nesta cópia: o texto sai em `textos_nao_exibidos` para conferência.")

ZERO_WIDTH = ("​‌‍⁠﻿­"

              "⁡⁢⁣⁤")



BIDI = "‪‫‬‭‮⁦⁧⁨⁩"
_TAG_CHARS = re.compile(r"[\U000E0000-\U000E007F]")
_BANDEIRA_TAG = re.compile(r"\U0001F3F4[\U000E0030-\U000E0039\U000E0061-\U000E007A]{2,6}\U000E007F")


def revelar_tags(texto):
    """O texto escondido em Unicode Tag (U+E0020–E007E espelham o ASCII visível)."""
    return "".join(chr(ord(c) - 0xE0000) for c in texto if 0xE0020 <= ord(c) <= 0xE007E)
ORDEM_SEV = {"alta": 3, "media": 2, "baixa": 1}
_MAX_STREAM = 8_000_000









_INVISIVEIS_PDF = frozenset((0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x2061, 0x2062, 0x2063, 0x2064,
                             0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069))
_RE_BFCHAR = re.compile(rb"beginbfchar(.*?)endbfchar", re.S)
_RE_BFRANGE = re.compile(rb"beginbfrange(.*?)endbfrange", re.S)
_RE_HEX = re.compile(rb"<([0-9A-Fa-f\s]*)>")
_RE_LINHA_RANGE = re.compile(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f\s]*>)")


def _unidades_utf16(hexa):
    h = re.sub(rb"\s+", b"", hexa)
    try:
        return [int(h[i:i + 4], 16) for i in range(0, len(h) - len(h) % 4, 4)]
    except ValueError:
        return []


def _cmap_devolve_invisivel(dec):
    """True se o stream é uma tabela ToUnicode que devolve caractere de largura zero. Nunca levanta."""
    try:
        if b"beginbfchar" not in dec and b"beginbfrange" not in dec:
            return False
        for bloco in _RE_BFCHAR.findall(dec):
            pares = _RE_HEX.findall(bloco)
            for destino in pares[1::2]:
                if any(u in _INVISIVEIS_PDF for u in _unidades_utf16(destino)):
                    return True
        for bloco in _RE_BFRANGE.findall(dec):
            for ini, fim, dst in _RE_LINHA_RANGE.findall(bloco):
                if dst.startswith(b"["):
                    if any(u in _INVISIVEIS_PDF for d in _RE_HEX.findall(dst) for u in _unidades_utf16(d)):
                        return True
                    continue
                us = _unidades_utf16(dst[1:-1])
                if not us:
                    continue
                if any(u in _INVISIVEIS_PDF for u in us[:-1]):
                    return True
                n = min(max(int(fim, 16) - int(ini, 16), 0), 0xFFFF)
                if any(us[-1] <= alvo <= us[-1] + n for alvo in _INVISIVEIS_PDF):
                    return True
    except Exception:
        return False
    return False


def _achado(ident, severidade, descricao, trecho="", parte=""):
    '`parte` é ONDE, dentro do arquivo, o achado está: `""` para o corpo'


    return {"id": ident, "severidade": severidade, "descricao": descricao,
            "trecho": (trecho or "")[:200], "parte": parte}


def _invisiveis(texto, achados, onde, parte=""):
    """Caracteres que existem no arquivo e não existem na tela."""
    if any(c in texto for c in ZERO_WIDTH):
        achados.append(_achado(
            "caractere_invisivel", "media",
            f"caractere de largura zero em {onde} — some na tela, entra no texto extraído",
            "(caractere invisível removido da amostra)", parte))
    if any(c in texto for c in BIDI):
        achados.append(_achado(
            "controle_bidi", "media",
            f"controle de direção do texto em {onde} — a ordem mostrada na tela difere da "
            "ordem lida pela IA", "(controle de direção removido da amostra)", parte))


    texto = _BANDEIRA_TAG.sub("\U0001F3F4", texto)
    m = _TAG_CHARS.search(texto)
    if m:
        revelado = revelar_tags(texto)
        achados.append(_achado(
            "unicode_tag", "alta",
            f"Unicode Tag char (U+E0000–U+E007F) em {onde} — canal clássico de instrução "
            "oculta, sem nenhum uso legítimo em peça; o trecho mostra o texto escondido",
            ("texto escondido: " + revelado) if revelado else repr(m.group(0)), parte))












def _carregar_detector():
    """O módulo `detectar_injecao`, ou None. Nunca levanta."""
    aqui = os.path.dirname(os.path.abspath(__file__))
    for pasta in (aqui,
                  os.path.join(aqui, os.pardir, "skills", "dissero-ingestao", "scripts"),
                  os.path.join(aqui, os.pardir, os.pardir, "dissero-ingestao", "scripts")):
        alvo = os.path.join(pasta, "detectar_injecao.py")
        if not os.path.isfile(alvo):
            continue
        try:
            import importlib.util as _ilu2
            spec = _ilu2.spec_from_file_location("_dsr_detectar_injecao", alvo)
            mod = _ilu2.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "varrer"):
                return mod
        except Exception:
            continue
    return None


_DETECTOR = []


def _detector_padrao():
    if not _DETECTOR:
        _DETECTOR.append(_carregar_detector())
    return _DETECTOR[0]


_FONTE_ID = {"anotação": "injecao_em_anotacao", "campo de formulário": "injecao_em_campo",
             "metadados": "injecao_em_metadados", "comentário": "injecao_em_comentario",
             "camada desligada": "injecao_em_camada", "texto fora da página": "injecao_fora_da_pagina",
             "texto alternativo": "injecao_em_texto_alternativo",
             "texto excluído": "injecao_em_texto_excluido",
             "arquivo embutido": "injecao_em_arquivo_embutido"}


def _julgar_textos(textos, achados, detector):
    'Passa cada texto não exibido pelo detector. `textos`: [(fonte, onde, texto)].'

    if not textos:
        return True
    if detector is None:
        return False
    for fonte, onde, texto in textos:
        try:
            ach = detector.varrer(texto)
        except Exception:
            return False
        if not ach:
            continue
        ordem = {"alta": 3, "media": 2, "baixa": 1}
        pior = max(ach, key=lambda a: ordem.get(a.get("severidade"), 0))
        local = f" ({onde})" if onde and onde != fonte else ""
        achados.append(_achado(
            _FONTE_ID.get(fonte, "injecao_em_texto_nao_exibido"), pior["severidade"],
            f"texto de {fonte}{local}, que não aparece na página, com sinal de instrução "
            f"dirigida à IA: {pior.get('descricao', '')}",
            " ".join(texto.split()), onde))
    return True




_RE_RUN = re.compile(r"<w:r(?:\s[^>]*)?>(.*?)</w:r>", re.S)
_RE_TEXTO = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.S)
_RE_COR = re.compile(r'<w:color\b[^>]*w:val="([^"]+)"', re.I)
_RE_SZ = re.compile(r'<w:sz\b[^>]*w:val="(\d+)"', re.I)
_RE_VANISH = re.compile(r"<w:vanish\s*/?>", re.I)
_RE_INSTR = re.compile(r"<w:instrText[^>]*>(.*?)</w:instrText>", re.S | re.I)

_CAMPOS_EXTERNOS = re.compile(r"\b(INCLUDETEXT|INCLUDEPICTURE|DDE|DDEAUTO|LINK)\b", re.I)
_CORES_BRANCAS = {"ffffff", "fffffe", "fefefe", "white", "auto-white"}






























_RE_SHD = re.compile(r"<w:shd\b[^>]*/?>", re.I)
_RE_ATTR_FILL = re.compile(r'w:fill="([^"]*)"', re.I)
_RE_ATTR_VAL = re.compile(r'w:val="([^"]*)"', re.I)
_RE_HIGHLIGHT = re.compile(r'<w:highlight\b[^>]*w:val="([^"]*)"', re.I)
_RE_RPR_BLOCO = re.compile(r"<w:rPr\b[^>]*>.*?</w:rPr>|<w:rPr\b[^>]*/>", re.S | re.I)



_SHD_CHAPADO = {"clear", ""}

_HIGHLIGHT_RGB = {
    "black": "000000", "blue": "0000FF", "cyan": "00FFFF", "darkBlue": "000080",
    "darkCyan": "008080", "darkGray": "808080", "darkGreen": "008000",
    "darkMagenta": "800080", "darkRed": "800000", "darkYellow": "808000",
    "green": "00FF00", "lightGray": "C0C0C0", "magenta": "FF00FF", "red": "FF0000",
    "white": "FFFFFF", "yellow": "FFFF00",
}
_NOME_PARA_HEX = {"white": "FFFFFF", "auto-white": "FFFFFF"}
CONTRASTE_MINIMO_FUNDO = _cw.MINIMO_COMPONENTE



_PROPS_DE = {"tbl": "tblPr", "tr": "trPr", "tc": "tcPr", "p": "pPr"}
_RE_ELEMENTO = re.compile(r"<(/?)w:(tbl|tr|tc|p)(?=[\s/>])([^>]*)>")


def _rgb(valor):
    """(r, g, b) de um valor de cor OOXML, ou None se não der para saber."""
    if not valor:
        return None
    v = valor.strip().lstrip("#")
    if v.lower() in ("auto", "none"):
        return None
    if v in _NOME_PARA_HEX or v.lower() in _NOME_PARA_HEX:
        v = _NOME_PARA_HEX.get(v, _NOME_PARA_HEX.get(v.lower()))
    if len(v) != 6:
        return None
    try:
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _fill_declarado(props_xml, tirar_marca=True):
    '`w:fill` do sombreamento DECLARADO neste bloco de propriedades.'









    if not props_xml:
        return None


    limpo = _RE_RPR_BLOCO.sub("", props_xml) if tirar_marca else props_xml
    m = _RE_SHD.search(limpo)
    if not m:
        return None
    tag = m.group(0)
    val = _RE_ATTR_VAL.search(tag)
    if (val.group(1).strip().lower() if val else "") not in _SHD_CHAPADO:
        return None
    fill = _RE_ATTR_FILL.search(tag)
    return fill.group(1).strip() if fill else None


def _props_proprias(conteudo, nome_prop):
    'Bloco de propriedades PRÓPRIO do elemento — sempre o primeiro filho, pelo esquema'

    m = re.match(r"\s*<w:%s\b[^>]*(?:/>|>(.*?)</w:%s>)" % (nome_prop, nome_prop),
                 conteudo, re.S)
    return (m.group(1) or "") if m else ""


def _elementos(doc):
    '[(nome, ini, fim)] de cada tabela, linha, célula e parágrafo, por posição no XML.'




    pilha, escopos = [], []
    for m in _RE_ELEMENTO.finditer(doc):
        fecha, nome, attrs = m.group(1), m.group(2), m.group(3)
        if fecha:
            for i in range(len(pilha) - 1, -1, -1):
                if pilha[i][0] == nome:
                    ini = pilha[i][1]
                    del pilha[i:]
                    escopos.append((nome, ini, m.start()))
                    break
            continue
        if attrs.rstrip().endswith("/"):
            continue
        pilha.append((nome, m.end()))
    return escopos


def _escopos_de_fundo(doc, estilos=None, elementos=None):
    '[(ini, fim, fill)] de cada elemento que DECLARA sombreamento, por posição no XML.'




    com_fundo = []
    for nome, ini, fim in (_elementos(doc) if elementos is None else elementos):
        props = _props_proprias(doc[ini:fim], _PROPS_DE[nome])
        fill = _fill_declarado(props)
        if fill is None and nome == "p" and estilos is not None:
            fill = estilos.fundo_do_paragrafo(_estilo_de(props, _RE_PSTYLE))
        if fill is not None:
            com_fundo.append((ini, fim, fill))
    return com_fundo


def _fundo_em(pos, escopos):
    """Fundo efetivo na posição `pos`: o escopo MAIS INTERNO (o menor) que a contém."""
    melhor, menor = None, None
    for ini, fim, fill in escopos:
        if ini <= pos < fim:
            largura = fim - ini
            if menor is None or largura < menor:
                melhor, menor = fill, largura
    return melhor


def _fundo_sustenta(run_xml, pos, escopos, cor_texto):
    'True quando há fundo atrás do texto com contraste suficiente para torná-lo visível.'




    rgb_texto = _rgb(cor_texto)
    if rgb_texto is None:
        return False
    rgb_fundo = _rgb(_fundo_declarado(run_xml, pos, escopos))
    if rgb_fundo is None:
        return False
    return _cw.contraste(rgb_texto, rgb_fundo) >= CONTRASTE_MINIMO_FUNDO


def _fundo_declarado(run_xml, pos, escopos):
    """O valor cru do fundo atrás do run (run → realce → escopo mais interno), ou None."""
    fundo = _fill_declarado(run_xml, tirar_marca=False)
    if fundo is None:
        realce = _RE_HIGHLIGHT.search(run_xml)
        if realce:
            fundo = _HIGHLIGHT_RGB.get(realce.group(1).strip()) or \
                _HIGHLIGHT_RGB.get(realce.group(1).strip().lower())
            if fundo is None:
                fundo = "auto"
    if fundo is None:
        fundo = _fundo_em(pos, escopos)
    return fundo











CONTRASTE_INVISIVEL, CONTRASTE_APAGADO = 1.1, 1.5


def _contraste_com_fundo(run_xml, pos, escopos, cor_texto):
    rgb_texto = _rgb(cor_texto)
    if rgb_texto is None:
        return None
    rgb_fundo = _rgb(_fundo_declarado(run_xml, pos, escopos)) or (255, 255, 255)
    return _cw.contraste(rgb_texto, rgb_fundo)





_RE_TEXTO_OU_HIFEN = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>|<w:noBreakHyphen\s*/>", re.S)


def _texto_do_run(run_xml):
    return "".join(m.group(1) if m.group(1) is not None else "-"
                   for m in _RE_TEXTO_OU_HIFEN.finditer(run_xml))












































_RE_PARTE_TIMBRADO = re.compile(r"^word/((header|footer)\d+)\.xml$")
_RE_RPR = re.compile(r"<w:rPr>(.*?)</w:rPr>", re.S)
_RE_ID_REL = re.compile(r'\s(?:r:id|r:embed|r:link)="[^"]*"')
_RE_ESPACO = re.compile(r"\s+")




PARTE_CARIMBO = "docProps/custom.xml"
PROP_ORIGEM = "DSRTimbradoOrigem"
PROP_MANIFESTO = "DSRTimbradoManifesto"


def _prop_personalizada(xml, nome):
    m = re.search(r'name="' + re.escape(nome) + r'"[^>]*>\s*<[^>]*>([^<]*)<', xml)
    return m.group(1).strip() if m else ""


def ler_carimbo_timbrado(z):
    '`(origem, sha_do_manifesto)` carimbado pelo construtor, ou `None` quando não há.'





    try:
        xml = z.read(PARTE_CARIMBO).decode("utf-8", "replace")
    except Exception:
        return None
    origem = _prop_personalizada(xml, PROP_ORIGEM)
    if origem not in ("proprio", "padrao"):
        return None
    return origem, _prop_personalizada(xml, PROP_MANIFESTO)








PROP_MINUTA_PENDENCIAS = "DSRMinutaPendencias"




FAIXA_MINUTA_PENDENCIAS = ("MINUTA COM PENDÊNCIAS. Documento gerado por ordem do advogado antes "
                           "da conclusão da revisão. Os trechos realçados dependem de conferência "
                           "e não devem ser protocolados como estão.")
_RX_PARAGRAFO = re.compile(r"<w:p[ >].*?</w:p>", re.S)
_RX_TEXTO_RUN = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>")


def _so_espaco(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def tem_carimbo_de_pendencias(caminho):
    'True quando o pacote traz a propriedade `DSRMinutaPendencias` = "1" (só o carimbo; a'

    try:
        with zipfile.ZipFile(caminho) as z:
            xml = z.read(PARTE_CARIMBO).decode("utf-8", "replace")
    except Exception:
        return False
    return _prop_personalizada(xml, PROP_MINUTA_PENDENCIAS) == "1"


def tem_faixa_de_pendencias(caminho):
    'True quando um parágrafo (`w:p`) do corpo é exatamente a faixa constante (espaços'

    try:
        with zipfile.ZipFile(caminho) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return False
    alvo = _so_espaco(FAIXA_MINUTA_PENDENCIAS)
    for p in _RX_PARAGRAFO.findall(xml):
        texto = "".join(html.unescape(t) for t in _RX_TEXTO_RUN.findall(p))
        if _so_espaco(texto) == alvo:
            return True
    return False


def tem_marca_de_pendencias(caminho):
    'True quando o `.docx` em `caminho` saiu da MINUTA COM PENDÊNCIAS: o carimbo'





    return tem_carimbo_de_pendencias(caminho) and tem_faixa_de_pendencias(caminho)


def _sha_manifesto(hashes):
    'O mesmo cálculo de `perfil_advogado.sha_manifesto_identidade`, repetido aqui porque'


    return hashlib.sha256(json.dumps(
        {str(k): str(v) for k, v in hashes.items()},
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def dir_pacote_timbrado():
    '`~/.config/dissero/identidade` — o mesmo caminho de `perfil_advogado.dir_identidade_propria()`.'



    return os.path.join(os.path.expanduser("~"), ".config", "dissero", "identidade")


def _runs_do_timbrado(xml):
    """Sequência `(texto, formatação)` dos runs COM texto, normalizada."""
    saida = []
    for run in _RE_RUN.finditer(xml):
        corpo = run.group(1)
        texto = _texto_do_run(corpo)
        if not texto.strip():
            continue
        rpr = _RE_RPR.search(corpo)
        forma = _RE_ID_REL.sub("", rpr.group(1)) if rpr else ""
        saida.append((_RE_ESPACO.sub(" ", texto), _RE_ESPACO.sub(" ", forma).strip()))
    return saida


def conferir_timbrado(z, nomes, dir_pacote=None):
    'Achados de cabeçalho/rodapé que não vieram do pacote do Dissero.'






    carimbo = ler_carimbo_timbrado(z)
    if not carimbo or carimbo[0] != "proprio":
        return []
    sha_da_peca = carimbo[1]
    if not sha_da_peca:



        return []
    dir_pacote = dir_pacote or dir_pacote_timbrado()
    try:
        with open(os.path.join(dir_pacote, "mapping.json"), encoding="utf-8") as fh:
            hashes = (json.load(fh) or {}).get("hashes")
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(hashes, dict) or not hashes:
        return []
    if _sha_manifesto(hashes) != sha_da_peca:




        return [_achado(
            "timbrado_pacote_trocado", "alta",
            "esta peça foi gerada com um pacote de timbrado diferente do que está instalado "
            "agora — o pacote do Dissero foi regravado depois que ela saiu, e não dá para "
            "conferir o cabeçalho e o rodapé dela contra o de hoje. Gere a peça de novo com "
            "`build_docx.py --identidade` e entregue a nova.",
            os.path.basename(dir_pacote))]
    esperado = {"header": [], "footer": []}
    for nome, sha in sorted(hashes.items()):
        m = re.fullmatch(r"(header|footer)\d+\.xml", str(nome))
        if not m:
            continue
        caminho = os.path.join(dir_pacote, str(nome))
        try:
            with open(caminho, "rb") as fh:
                bruto = fh.read()
        except OSError:
            continue



        if hashlib.sha256(bruto).hexdigest() != str(sha):
            continue
        esperado[m.group(1)].append(_runs_do_timbrado(bruto.decode("utf-8", "replace")))
    if not esperado["header"] and not esperado["footer"]:
        return []
    achados = []
    for nome in sorted(nomes):
        m = _RE_PARTE_TIMBRADO.match(nome)
        if not m:
            continue
        especie = m.group(2)
        try:
            runs = _runs_do_timbrado(z.read(nome).decode("utf-8", "replace"))
        except Exception:
            continue


        if not runs or not esperado[especie]:
            continue
        if runs in esperado[especie]:
            continue
        achados.append(_achado(
            "timbrado_fora_do_pacote", "alta",
            "o cabeçalho ou o rodapé desta peça não é o que o Dissero serviu — ele foi "
            "escrito, copiado de outra peça ou ajustado à mão. Cabeçalho e rodapé vêm só do "
            "pacote do servidor ou do timbrado padrão do plugin. Gere a peça de novo com "
            "`build_docx.py --identidade`; se a recusa continuar, chame "
            "perfil_do_advogado(parte=\"identidade\") e grave com "
            "`perfil_advogado.py --gravar-identidade <zip>`",
            m.group(1) + ": " + " | ".join(t for t, _f in runs[:4])))
    return achados






















_RE_ESTILO = re.compile(r"<w:style\b([^>]*)>(.*?)</w:style>", re.S)
_RE_ATTR_TIPO = re.compile(r'w:type="([^"]*)"')
_RE_ATTR_ID = re.compile(r'w:styleId="([^"]*)"')
_RE_ATTR_PADRAO = re.compile(r'w:default="(?:1|true|on)"')
_RE_BASEDON = re.compile(r'<w:basedOn\b[^>]*w:val="([^"]*)"')
_RE_PSTYLE = re.compile(r'<w:pStyle\b[^>]*w:val="([^"]*)"')
_RE_RSTYLE = re.compile(r'<w:rStyle\b[^>]*w:val="([^"]*)"')
_RE_ALTERACAO = re.compile(r"<w:(rPrChange|pPrChange)\b.*?</w:\1>|<w:(?:rPrChange|pPrChange)\b[^>]*/>", re.S)
_RE_BLOCO_RPR = re.compile(r"<w:rPr\b[^>]*>(.*?)</w:rPr>", re.S)
_RE_BLOCO_PPR = re.compile(r"<w:pPr\b[^>]*>(.*?)</w:pPr>", re.S)
_RE_COND_TABELA = re.compile(r"<w:tblStylePr\b.*?</w:tblStylePr>", re.S)
_RE_RPR_DEFAULT = re.compile(r"<w:rPrDefault\b[^>]*>(.*?)</w:rPrDefault>", re.S)
_RE_PPR_DEFAULT = re.compile(r"<w:pPrDefault\b[^>]*>(.*?)</w:pPrDefault>", re.S)
_RX_PROP = {}
_DESLIGADO = {"0", "false", "off", "none"}


def _rx_prop(nome):
    """`<w:nome .../>` exato: `w` não casa com `webHidden`, nem `sz` com `szCs`."""
    rx = _RX_PROP.get(nome)
    if rx is None:
        rx = _RX_PROP[nome] = re.compile(r"<w:%s(?=[\s/>])[^>]*>" % nome)
    return rx


def _attr(tag, nome):
    m = re.search(r'\bw:%s="([^"]*)"' % nome, tag or "")
    return m.group(1).strip() if m else None


def _ligado(tag):
    """Propriedade liga/desliga: presente e sem `w:val` falso."""
    return bool(tag) and (_attr(tag, "val") or "1").lower() not in _DESLIGADO


def _inteiro(tag, nome="val"):
    v = _attr(tag, nome)
    try:
        return int(float(v)) if v not in (None, "") else None
    except ValueError:
        return None


def _estilo_de(props_xml, rx):
    m = rx.search(props_xml or "")
    return m.group(1) if m else None


def _prop_efetiva(nome, run_limpo, cadeia):
    """A declaração vencedora de `nome`: a do run, senão a última da cadeia de estilos."""
    m = _rx_prop(nome).search(run_limpo)
    if m:
        return m.group(0)
    for rpr in reversed(cadeia):
        achadas = _rx_prop(nome).findall(rpr)
        if achadas:
            return achadas[-1]
    return None




_SLOTS_TEMA = {"dark1": "dk1", "light1": "lt1", "dark2": "dk2", "light2": "lt2",
               "accent1": "accent1", "accent2": "accent2", "accent3": "accent3",
               "accent4": "accent4", "accent5": "accent5", "accent6": "accent6",
               "hyperlink": "hlink", "followedHyperlink": "folHlink"}
_MAPA_TEMA_PADRAO = {"background1": "light1", "text1": "dark1", "background2": "light2", "text2": "dark2"}
_ATTR_MAPA = {"background1": "bg1", "text1": "t1", "background2": "bg2", "text2": "t2"}
_TEMA_SEM_PARTE = {"dk1": "000000", "lt1": "FFFFFF"}
_RE_SLOT_TEMA = re.compile(r"<a:(dk1|lt1|dk2|lt2|accent[1-6]|hlink|folHlink)\b[^>]*>(.*?)</a:\1>", re.S)
_RE_SRGB = re.compile(r'<a:srgbClr\b[^>]*\bval="([0-9A-Fa-f]{6})"')
_RE_SYSCLR = re.compile(r'<a:sysClr\b[^>]*\blastClr="([0-9A-Fa-f]{6})"')
_RE_MAPA_CORES = re.compile(r"<w:clrSchemeMapping\b[^>]*>")


def _matiz(hexa, tint=None, shade=None):
    '`w:themeTint`/`w:themeShade` (00–FF) aplicados em RGB. O Word faz a conta em HSL; em'

    rgb = [int(hexa[i:i + 2], 16) for i in (0, 2, 4)]
    try:
        if shade:
            f = int(shade, 16) / 255
            rgb = [round(c * f) for c in rgb]
        if tint:
            f = int(tint, 16) / 255
            rgb = [round(c * f + 255 * (1 - f)) for c in rgb]
    except ValueError:
        pass
    return "".join(f"{max(0, min(255, c)):02X}" for c in rgb)


class _Estilos:
    'Estilos, `docDefaults`, tema e mapa de cores de um .docx. Nunca levanta: parte ausente'


    def __init__(self, styles_xml="", tema_xml="", settings_xml=""):
        self._por_id, self._padrao_p, self._cadeias, self._ppr = {}, None, {}, {}
        sem_tabela = _RE_COND_TABELA.sub("", styles_xml or "")
        m = _RE_RPR_DEFAULT.search(sem_tabela)
        self.defaults_rpr = "".join(_RE_BLOCO_RPR.findall(m.group(1))) if m else ""
        m = _RE_PPR_DEFAULT.search(sem_tabela)
        self.defaults_ppr = "".join(_RE_BLOCO_PPR.findall(m.group(1))) if m else ""
        for m in _RE_ESTILO.finditer(sem_tabela):
            attrs, corpo = m.group(1), _RE_ALTERACAO.sub("", m.group(2))
            ident = _RE_ATTR_ID.search(attrs)
            if not ident:
                continue
            tipo = (_RE_ATTR_TIPO.search(attrs) or [None, ""])[1]
            ppr = "".join(_RE_BLOCO_PPR.findall(corpo))
            rpr = "".join(_RE_BLOCO_RPR.findall(_RE_BLOCO_PPR.sub("", corpo)))
            base = _RE_BASEDON.search(corpo)
            self._por_id[ident.group(1)] = (tipo, base.group(1) if base else None, rpr, ppr)
            if tipo == "paragraph" and _RE_ATTR_PADRAO.search(attrs) and self._padrao_p is None:
                self._padrao_p = ident.group(1)
        self._tema = {}
        for m in _RE_SLOT_TEMA.finditer(tema_xml or ""):
            c = _RE_SRGB.search(m.group(2)) or _RE_SYSCLR.search(m.group(2))
            if c:
                self._tema[m.group(1)] = c.group(1).upper()
        if not self._tema:
            self._tema = dict(_TEMA_SEM_PARTE)
        self._mapa = dict(_MAPA_TEMA_PADRAO)
        m = _RE_MAPA_CORES.search(settings_xml or "")
        if m:
            for nome, attr in _ATTR_MAPA.items():
                v = _attr(m.group(0), attr)
                if v:
                    self._mapa[nome] = v

    def _cadeia(self, ident, tipo):
        """[estilo base, ..., estilo] de um id, com guarda de ciclo."""
        saida, vistos = [], set()
        while ident and ident not in vistos and len(vistos) < 32:
            vistos.add(ident)
            dados = self._por_id.get(ident)
            if dados is None or (tipo and dados[0] and dados[0] != tipo):
                break
            saida.append(dados)
            ident = dados[1]
        return list(reversed(saida))

    def cadeia_rpr(self, pstyle, rstyle):
        chave = (pstyle, rstyle)
        if chave not in self._cadeias:
            cad = [self.defaults_rpr] if self.defaults_rpr else []
            cad += [d[2] for d in self._cadeia(pstyle or self._padrao_p, "paragraph") if d[2]]
            cad += [d[2] for d in self._cadeia(rstyle, "character") if d[2]]
            self._cadeias[chave] = cad
        return self._cadeias[chave]

    def cadeia_ppr(self, pstyle):
        chave = pstyle or self._padrao_p
        if chave not in self._ppr:
            cad = [self.defaults_ppr] if self.defaults_ppr else []
            self._ppr[chave] = cad + [d[3] for d in self._cadeia(chave, "paragraph") if d[3]]
        return self._ppr[chave]

    def fundo_do_paragrafo(self, pstyle):
        for ppr in reversed(self.cadeia_ppr(pstyle)):
            fill = _fill_declarado(ppr)
            if fill is not None:
                return fill
        return None

    def cor(self, tag):
        'O valor de cor que a tela mostra: a do tema, quando há `w:themeColor` que se resolva;'

        if not tag:
            return None
        tema = _attr(tag, "themeColor")
        if tema:
            slot = _SLOTS_TEMA.get(self._mapa.get(tema, tema))
            hexa = self._tema.get(slot) if slot else None
            if hexa:
                return _matiz(hexa, _attr(tag, "themeTint"), _attr(tag, "themeShade"))
        return _attr(tag, "val")


_SEM_ESTILOS = _Estilos()




SZ_MINUSCULA = 7


ESCALA_MINIMA = 20


_RE_SO_NUMERO = re.compile(r"[\s\d.\-–—ivxlcdmIVXLCDM]*")
_RE_PGSZ = re.compile(r"<w:pgSz\b[^>]*>")
PAGINA_PADRAO = (11906, 16838)


def _pagina(doc):
    """(largura, altura) em twips: a maior seção declarada, ou A4."""
    w = h = 0
    for tag in _RE_PGSZ.findall(doc or ""):
        w, h = max(w, _inteiro(tag, "w") or 0), max(h, _inteiro(tag, "h") or 0)
    return (w or PAGINA_PADRAO[0], h or PAGINA_PADRAO[1])


def _moldura_fora(tag, pagina):
    'True quando a moldura (`w:framePr`) fica INTEIRA fora do papel.'





    if not tag:
        return False
    larg, alt = pagina
    def eixo(pos, tam, ancora, alinhado, limite):
        if alinhado or pos is None:
            return False
        folga = 0 if ancora == "page" else limite
        return pos + (tam if tam else limite) <= -folga or pos >= limite
    return (eixo(_inteiro(tag, "x"), _inteiro(tag, "w"), _attr(tag, "hAnchor"), _attr(tag, "xAlign"), larg)
            or eixo(_inteiro(tag, "y"), _inteiro(tag, "h"), _attr(tag, "vAnchor"), _attr(tag, "yAlign"), alt))


def _paragrafo_em(pos, paragrafos, inicios):
    """O parágrafo mais interno que contém `pos` (bisseção, e volta atrás no aninhado)."""
    i = bisect.bisect_right(inicios, pos) - 1
    passos = 0
    while i >= 0 and passos < 64:
        ini, fim, props = paragrafos[i]
        if ini <= pos < fim:
            return i
        i, passos = i - 1, passos + 1
    return None




_RE_ALT = re.compile(r"<(?:wp|pic|a):(?:docPr|cNvPr)\b[^>]*>")
_RE_ALT_ATTR = re.compile(r'\b(?:descr|title)="([^"]*)"')
_RE_DELTEXT = re.compile(r"<w:delText\b[^>]*>(.*?)</w:delText>", re.S)


def _texto_alternativo(xml):
    vistos, saida = set(), []
    for tag in _RE_ALT.findall(xml):
        for v in _RE_ALT_ATTR.findall(tag):
            t = " ".join(html.unescape(v).split())
            if t and t not in vistos:
                vistos.add(t)
                saida.append(t)
    return " | ".join(saida)


def _texto_excluido(xml):
    return " ".join(" ".join(html.unescape(t) for t in _RE_DELTEXT.findall(xml)).split())















_PARTES_EXTRA = re.compile(r"^word/(header\d+|footer\d+|footnotes|endnotes|comments)\.xml$")
_NOME_DA_PARTE = {"header": "cabeçalho", "footer": "rodapé",
                  "footnotes": "nota de rodapé", "endnotes": "nota de fim",
                  "comments": "comentário"}
_RE_TAG_XML = re.compile(r"<[^>]+>")


def _texto_xml(xml):
    return html.unescape(" ".join(_RE_TAG_XML.sub(" ", xml).split()))


def _nome_da_parte(nome_do_arquivo):
    base = nome_do_arquivo[len("word/"):-len(".xml")].rstrip("0123456789")
    return _NOME_DA_PARTE.get(base, base)


def _varrer_runs(xml, achados, parte="", estilos=None, pagina=PAGINA_PADRAO):
    'As regras de run — as MESMAS para o corpo e para as partes de fora dele.'






    estilos = estilos or _SEM_ESTILOS
    elementos = _elementos(xml)
    escopos = _escopos_de_fundo(xml, estilos, elementos)
    paragrafos = sorted((i, f, _props_proprias(xml[i:f], "pPr")) for n, i, f in elementos if n == "p")
    inicios = [p[0] for p in paragrafos]
    molduras = {}
    for achado_run in _RE_RUN.finditer(xml):
        run_xml = achado_run.group(1)
        texto = _texto_do_run(run_xml).strip()
        if not texto:
            continue
        run_limpo = _RE_ALTERACAO.sub("", run_xml)
        i_par = _paragrafo_em(achado_run.start(), paragrafos, inicios)
        ppr = _RE_ALTERACAO.sub("", paragrafos[i_par][2]) if i_par is not None else ""
        pstyle = _estilo_de(ppr, _RE_PSTYLE)
        cadeia = estilos.cadeia_rpr(pstyle, _estilo_de(run_limpo, _RE_RSTYLE))
        prop = lambda nome: _prop_efetiva(nome, run_limpo, cadeia)

        fundo_run = (prop("shd") or "") + (prop("highlight") or "")
        valor_cor = estilos.cor(prop("color"))
        branco = bool(valor_cor) and valor_cor.strip().lower().lstrip("#") in _CORES_BRANCAS



        if branco and not _fundo_sustenta(fundo_run, achado_run.start(), escopos, valor_cor):
            achados.append(_achado(
                "texto_invisivel_cor", "alta",
                "texto em cor branca sobre fundo claro ou ausente — invisível na tela, "
                "legível pela IA processante",
                texto, parte))
        elif valor_cor and not branco:
            k = _contraste_com_fundo(fundo_run, achado_run.start(), escopos, valor_cor)
            if k is not None and k < CONTRASTE_INVISIVEL:
                achados.append(_achado(
                    "texto_invisivel_cor", "alta",
                    f"texto da cor do fundo (contraste {k:.2f}:1) — invisível na tela, "
                    "legível pela IA processante", texto, parte))
            elif k is not None and k < CONTRASTE_APAGADO:
                achados.append(_achado(
                    "texto_quase_invisivel", "media",
                    f"texto muito claro para o fundo (contraste {k:.2f}:1) — quase invisível na "
                    "tela; confira se é enfeite do timbrado ou texto escondido", texto, parte))
        sz = _inteiro(prop("sz"))
        if sz is not None and sz < 5:
            achados.append(_achado(
                "fonte_microscopica", "alta",
                f"fonte de {sz / 2:g}pt — abaixo do legível; nenhuma peça "
                "legítima usa esse corpo", texto, parte))
        elif sz is not None and sz <= SZ_MINUSCULA:
            achados.append(_achado(
                "fonte_minuscula", "media",
                f"fonte de {sz / 2:g}pt — difícil de ler na tela e no papel; confira se é "
                "texto escondido", texto, parte))
        if _ligado(prop("vanish")):
            achados.append(_achado(
                "texto_oculto", "alta",
                "texto marcado como oculto (w:vanish) — não imprime, não aparece, e "
                "mesmo assim viaja no arquivo", texto, parte))
        escala = _inteiro(prop("w"))
        if escala is not None and 0 < escala < ESCALA_MINIMA:
            espaco = _inteiro(prop("spacing"))
            comprimido = espaco is not None and espaco < 0
            achados.append(_achado(
                "texto_comprimido", "alta" if comprimido else "media",
                f"texto comprimido a {escala}% da largura"
                + (" e com letras sobrepostas (espaçamento negativo)" if comprimido else "")
                + " — vira um traço na tela, e a IA o lê inteiro", texto, parte))
        if _ligado(prop("webHidden")) and not _RE_SO_NUMERO.fullmatch(texto):
            achados.append(_achado(
                "texto_oculto_web", "media",
                "texto marcado para não aparecer na visualização web (w:webHidden) — confira "
                "se é texto escondido", texto, parte))
        if i_par is not None:
            moldura = _rx_prop("framePr").search(ppr)
            tag = moldura.group(0) if moldura else None
            if tag is None:
                for p_estilo in reversed(estilos.cadeia_ppr(pstyle)):
                    achadas = _rx_prop("framePr").findall(p_estilo)
                    if achadas:
                        tag = achadas[-1]
                        break
            if _moldura_fora(tag, pagina):
                molduras.setdefault(i_par, []).append(texto)
    for textos in molduras.values():
        achados.append(_achado(
            "texto_fora_da_pagina", "alta",
            "texto numa moldura (w:framePr) posta fora da página — não aparece, e a IA o lê",
            " ".join(textos), parte))

    for instr in _RE_INSTR.findall(xml):
        if _CAMPOS_EXTERNOS.search(instr):
            achados.append(_achado(
                "campo_externo", "alta",
                "campo que puxa conteúdo de fora ao abrir o documento — o que a peça "
                "mostra deixa de ser o que ela contém", instr.strip(), parte))

    _invisiveis(unicodedata.normalize("NFC", " ".join(_RE_TEXTO.findall(xml))), achados,
                f"{parte} da peça" if parte else "texto da peça", parte)


def varrer_docx(dados, linguistico=False, detector=None):
    'Varre um .docx (bytes ou caminho). É a peça que o plugin ENTREGA.'




    achados = []
    try:
        if isinstance(dados, (str, os.PathLike)):
            with open(dados, "rb") as fh:
                dados = fh.read()
        z = zipfile.ZipFile(io.BytesIO(dados))
        nomes = z.namelist()
        doc = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception as e:
        return {"ok": False, "suspeito": None, "exit_code": 2,
                "erro": f"não foi possível ler como .docx: {type(e).__name__}: {e}",
                "aviso": "arquivo ilegível NÃO é arquivo limpo — conferir antes de entregar",
                "achados": [], "camada_profunda": TEM_CAMADA_PROFUNDA}

    def _parte(nome):
        try:
            return z.read(nome).decode("utf-8", "replace") if nome in nomes else ""
        except Exception:
            return ""
    estilos = _Estilos(_parte("word/styles.xml"),
                       _parte(next((n for n in sorted(nomes) if re.match(r"^word/theme/theme\d*\.xml$", n)), "")),
                       _parte("word/settings.xml"))
    pagina = _pagina(doc)
    _varrer_runs(doc, achados, estilos=estilos, pagina=pagina)




    for nome in sorted(n for n in nomes if _PARTES_EXTRA.match(n)):
        try:
            xml_parte = z.read(nome).decode("utf-8", "replace")
        except Exception:
            continue
        _varrer_runs(xml_parte, achados, _nome_da_parte(nome), estilos, pagina)

    if any(n.endswith("vbaProject.bin") for n in nomes):
        achados.append(_achado("macro_embutida", "alta",
                               "macro (VBA) embutida no documento", "word/vbaProject.bin"))

    achados.extend(conferir_timbrado(z, nomes))

    extra = {}
    if linguistico:
        textos = []
        for nome in sorted(n for n in nomes if n == "word/comments.xml"):
            try:
                t = _texto_xml(z.read(nome).decode("utf-8", "replace"))
            except Exception:
                t = ""
            if t:
                textos.append(("comentário", "comentário", t))


        for nome_prop in ("docProps/core.xml", "docProps/custom.xml", "docProps/app.xml"):
            t = _texto_xml(_parte(nome_prop))
            if t:
                _invisiveis(t, achados, "propriedades do documento", "propriedades do documento")
                textos.append(("metadados", "propriedades do documento", t))

        for nome in ["word/document.xml"] + sorted(n for n in nomes if _PARTES_EXTRA.match(n)):
            xml_parte = doc if nome == "word/document.xml" else _parte(nome)
            onde = "corpo da peça" if nome == "word/document.xml" else _nome_da_parte(nome)
            for fonte, t in (("texto alternativo", _texto_alternativo(xml_parte)),
                             ("texto excluído", _texto_excluido(xml_parte))):
                if t:
                    _invisiveis(t, achados, f"{fonte} ({onde})", onde)
                    textos.append((fonte, onde, t))
        det = _detector_padrao() if detector is None else (detector or None)
        if not _julgar_textos(textos, achados, det):
            extra = _sem_detector(textos)
        else:
            extra = {"detector_linguistico": True}
    return _resultado(achados, "docx", extra)




_TOKENS_PDF = [
    ("javascript", "alta", rb"/JavaScript\b|/JS\s*[(<]",
     "JavaScript embutido — PDF de peça não executa código"),
    ("launch", "alta", rb"/Launch\b",
     "ação de execução de programa (/Launch) ao abrir o documento"),
    ("arquivo_embutido", "media", rb"/EmbeddedFiles?\b",
     "arquivo embutido dentro do PDF — conteúdo que a leitura da página não mostra"),
    ("acao_automatica", "media", rb"/AA\b",
     "ação automática (/AA) disparada por evento de página ou campo"),
    ("formulario_xfa", "media", rb"/XFA\b",
     "formulário XFA — o conteúdo do campo não aparece na extração de texto"),
    ("midia_rica", "media", rb"/RichMedia\b",
     "mídia rica embutida (Flash/3D) — superfície de execução"),
]


RE_STREAM = re.compile(rb"stream\r?\n(.*?)(?:\r?\n)?endstream", re.S)
_RE_STREAM = RE_STREAM
_RE_BT_ET = re.compile(rb"BT\b(.*?)\bET\b", re.S)
_RE_TR3 = re.compile(rb"(?:^|[\s])3\s+Tr\b")


_RE_TR7 = re.compile(rb"(?:^|[\s])7\s+Tr\b")

_ZERO_PDF = rb"-?(?:0+\.?0*|\.0+)"
_RE_RECORTE_VAZIO = re.compile(rb"(?:^|\s)-?[\d.]+\s+-?[\d.]+\s+" + _ZERO_PDF + rb"\s+" + _ZERO_PDF
                               + rb"\s+re\s+W\*?\s+n\b")
_RE_Q_FECHA = re.compile(rb"(?:^|\s)Q\b")
_RE_MOSTRA_TEXTO = re.compile(rb"\b(?:Tj|TJ|'|\")\B|\bTj\b|\bTJ\b")
_RE_LITERAL = re.compile(rb"\(([^)\\]{4,200})\)")


def decodificar_stream(bruto):
    'O conteúdo do stream, decodificado o bastante para ler os operadores.'




    try:
        return zlib.decompress(bruto)
    except Exception:
        pass



    if bruto[:1] == b"x":
        try:
            parcial = zlib.decompressobj().decompress(bruto)
            if parcial:
                return parcial
        except Exception:
            pass
    limpo = bruto.strip()
    if limpo.endswith(b"~>"):
        try:
            a85 = base64.a85decode(limpo.removeprefix(b"<~")[:-2])
        except Exception:
            return bruto
        try:
            return zlib.decompress(a85)
        except Exception:
            return a85
    return bruto


def _streams(dados):
    total = 0
    for m in RE_STREAM.finditer(dados):
        if total > _MAX_STREAM:
            break
        dec = decodificar_stream(m.group(1))
        total += len(dec)
        yield m.start(), dec













_RE_OBJ_INICIO = re.compile(rb"(?<![0-9])(\d{1,10})\s+\d{1,5}\s+obj\b")
_RE_REF = re.compile(rb"(\d{1,10})\s+\d{1,5}\s+R\b")
_RE_E_PAGINA = re.compile(rb"/Type\s*/Page(?![A-Za-z])")
_RE_E_PAGES = re.compile(rb"/Type\s*/Pages\b")
_RE_E_CATALOGO = re.compile(rb"/Type\s*/Catalog\b")




_RE_E_OBJSTM = re.compile(rb"/Type\s*/ObjStm\b")
_MAX_PAGINAS_NO_AVISO = 8
SEM_PAGINA = "página não identificada"


def _valor_de(corpo, chave):
    'O que vem depois de `/Chave` num dicionário de objeto: a lista `[...]` inteira, ou a'

    m = re.search(rb"/" + chave + rb"\s*(\[[^\]]*\]|\d{1,10}\s+\d{1,5}\s+R)", corpo)
    return [int(n) for n in _RE_REF.findall(m.group(1))] if m else []


class _MapaDePaginas:
    """Objeto do PDF → número da página (1 = primeira), lido da estrutura, sem renderizar."""

    def __init__(self, dados):
        self.inicios, self.numeros, corpos = [], [], {}
        marcas = [(m.start(), int(m.group(1))) for m in _RE_OBJ_INICIO.finditer(dados)]
        for i, (pos, num) in enumerate(marcas):
            fim = marcas[i + 1][0] if i + 1 < len(marcas) else len(dados)
            self.inicios.append(pos)
            self.numeros.append(num)



            corte = dados.find(b"stream", pos, fim)
            corpos[num] = bytes(dados[pos:fim if corte < 0 else corte])
        self.corpos = corpos
        paginas = [n for n, c in corpos.items() if _RE_E_PAGINA.search(c)]
        self.catalogos = {n for n, c in corpos.items() if _RE_E_CATALOGO.search(c)}
        self.comprimidos = {n for n, c in corpos.items() if _RE_E_OBJSTM.search(c)}
        ordem = self._ordem_da_arvore(corpos, set(paginas))


        self.confiavel = bool(paginas) and len(ordem) == len(paginas)
        self.pagina_de = {}
        self.conteudos = {}
        if self.confiavel:
            for indice, num in enumerate(ordem, 1):
                self.pagina_de[num] = indice
                for ref in _valor_de(corpos[num], rb"Contents"):
                    self.conteudos.setdefault(ref, indice)
                for chave in (rb"Contents", rb"Annots"):
                    for ref in _valor_de(corpos[num], chave):
                        self.pagina_de.setdefault(ref, indice)

    @staticmethod
    def _ordem_da_arvore(corpos, paginas):
        raizes = [n for n, c in corpos.items() if _RE_E_PAGES.search(c) and b"/Parent" not in c]
        if len(raizes) != 1:
            return []
        ordem, vistos, pilha = [], set(), [raizes[0]]
        while pilha:
            num = pilha.pop()
            if num in vistos or num not in corpos:
                continue
            vistos.add(num)
            if num in paginas:
                ordem.append(num)
            else:
                pilha.extend(reversed(_valor_de(corpos[num], rb"Kids")))
        return ordem

    def objeto_em(self, pos):
        """O número do objeto que contém o byte `pos`, ou None."""
        lo, hi = 0, len(self.inicios)
        while lo < hi:
            meio = (lo + hi) // 2
            if self.inicios[meio] <= pos:
                lo = meio + 1
            else:
                hi = meio
        return self.numeros[lo - 1] if lo else None

    def lugar_em(self, pos):
        """'catálogo', um número de página, ou None quando a estrutura não diz."""
        num = self.objeto_em(pos)
        if num is None:
            return None
        if num in self.catalogos:
            return "catálogo"
        return self.pagina_de.get(num)


def _texto_do_lugar(lugares):
    "De um conjunto de lugares (números de página, 'catálogo', None) para o português do"

    paginas = sorted(l for l in lugares if isinstance(l, int))
    partes = []
    if "catálogo" in lugares:
        partes.append("configuração geral do documento (vale para todas as páginas)")
    if paginas:
        mostradas = ", ".join(str(p) for p in paginas[:_MAX_PAGINAS_NO_AVISO])
        resto = len(paginas) - _MAX_PAGINAS_NO_AVISO
        rotulo = "página" if len(paginas) == 1 else "páginas"
        partes.append(f"{rotulo} {mostradas}" + (f" e mais {resto}" if resto > 0 else ""))
    if None in lugares:
        partes.append(SEM_PAGINA if not partes else "outros pontos de página não identificada")
    return "; ".join(partes)



_ESCAPES_PDF = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}


def _decodificar_texto_pdf(b):
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be", "replace")
    if b.startswith(b"\xff\xfe"):
        return b[2:].decode("utf-16-le", "replace")
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8", "replace")

    return b.decode("latin-1").replace("­", "")


def _ler_string_pdf(buf, i):
    '(texto, fim) da string PDF em buf[i] — literal `(...)` ou hexadecimal `<...>`.'

    try:
        if buf[i:i + 1] == b"(":
            out, prof, j, n = bytearray(), 0, i, min(len(buf), i + 20000)
            while j < n:
                c = buf[j]
                if c == 0x5C:
                    j += 1
                    if j >= n:
                        break
                    e = buf[j]
                    if e in _ESCAPES_PDF:
                        out.append(_ESCAPES_PDF[e])
                    elif 0x30 <= e <= 0x37:
                        k, v = j, 0
                        while k < j + 3 and k < n and 0x30 <= buf[k] <= 0x37:
                            v, k = v * 8 + buf[k] - 0x30, k + 1
                        out.append(v & 0xFF)
                        j = k
                        continue
                    elif e not in (10, 13):
                        out.append(e)
                elif c == 0x28:
                    prof += 1
                    if prof > 1:
                        out.append(c)
                elif c == 0x29:
                    prof -= 1
                    if prof == 0:
                        return _decodificar_texto_pdf(bytes(out)), j + 1
                    out.append(c)
                else:
                    out.append(c)
                j += 1
            return None, i
        if buf[i:i + 1] == b"<" and buf[i + 1:i + 2] != b"<":
            fim = buf.find(b">", i)
            if fim < 0:
                return None, i
            h = re.sub(rb"[^0-9A-Fa-f]", b"", buf[i + 1:fim])
            if len(h) % 2:
                h += b"0"
            return _decodificar_texto_pdf(bytes.fromhex(h.decode("ascii"))), fim + 1
    except Exception:
        pass
    return None, i


def _strings_da_chave(corpo, chave):
    """Os valores-string de `/Chave` num dicionário (nunca um `<<` aninhado nem referência)."""
    saida = []
    for m in re.finditer(rb"/" + chave + rb"\s*(?=[(<])", corpo):
        if corpo[m.end():m.end() + 2] == b"<<":
            continue
        t, _ = _ler_string_pdf(corpo, m.end())
        if t and t.strip() and _legivel(t):
            saida.append(t[:5000])
    return saida


_RE_E_EMBUTIDO = re.compile(rb"/Type\s*/EmbeddedFile\b")


def _texto_embutido(dec):
    'O texto de um arquivo embutido, quando ele é texto (UTF-8, UTF-16 com BOM ou Latin-1'

    amostra = dec[:200_000]
    if amostra[:2] in (b"\xff\xfe", b"\xfe\xff"):
        t = amostra.decode("utf-16", "replace")
    else:
        try:
            t = amostra.decode("utf-8")
        except UnicodeDecodeError:
            t = amostra.decode("latin-1")
    t = t.lstrip("\ufeff")
    return t[:20_000] if t.strip() and _legivel(t) else None


def _legivel(t):
    'Texto, e não bytes: o `/Contents` de uma ASSINATURA digital é o PKCS#7 em hexadecimal, e'

    amostra = t[:2000]
    bons = sum(ch.isprintable() or ch in "\n\r\t" for ch in amostra)
    return bons >= 0.85 * len(amostra)












LIMIAR_QUASE_BRANCO = 0.92
_RE_TOK = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>|[-+]?(?:\d+\.?\d*|\.\d+)"
                     rb"|/[^\s/\[\]()<>{}%]*|[A-Za-z'\"][A-Za-z0-9*'\"]*|[\[\]]", re.S)
_OPS_COR = {b"g": 1, b"rg": 3, b"k": 4, b"sc": 0, b"scn": 0}
_OPS_PINTA = {b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
_OPS_MOSTRA = {b"Tj", b"TJ", b"'", b'"'}


def _luz(cor):
    """Claridade média (0 preto, 1 branco) de (n, valores), ou None."""
    if not cor:
        return None
    n, v = cor
    if n == 1:
        return v[0]
    if n == 3:
        return sum(v) / 3
    if n == 4:
        return sum((1 - x) * (1 - v[3]) for x in v[:3]) / 3
    return None


def _quase_branco(cor):
    if not cor:
        return False
    n, v = cor
    if n in (1, 3):
        return all(x >= LIMIAR_QUASE_BRANCO for x in v)
    if n == 4:
        return all(x <= 1 - LIMIAR_QUASE_BRANCO for x in v)
    return False


def _amostra_de(strings):
    partes = []
    for s in strings:
        t, _ = _ler_string_pdf(s, 0)
        if t:
            partes.append(t)
    return " ".join(" ".join(partes).split())[:200]


def _parece_conteudo(dec):
    'Content stream é texto de operadores; fonte embutida, perfil ICC e imagem não são. MEDIDO em'

    cabeca = dec[:2048]
    if cabeca.lstrip()[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"%!PS", b"%!Fo", b"\x01\x00\x04\x02"):
        return False
    return bool(cabeca) and sum(32 <= b < 127 or b in (9, 10, 13) for b in cabeca) >= 0.6 * len(cabeca)











LIMIAR_OPACIDADE = 0.05
_RE_GS_EM_LINHA = re.compile(rb"/([^\s/<>\[\]()]+)\s*<<([^<>]*)>>")
_RE_CA = re.compile(rb"/ca\s+([-+]?(?:\d+\.?\d*|\.\d+))")


def _opacidades(blobs, corpos):
    """{nome do ExtGState: opacidade de preenchimento}, de dicionários em linha e por referência."""
    def ca(corpo):
        m = _RE_CA.search(corpo)
        try:
            return float(m.group(1)) if m else None
        except ValueError:
            return None
    saida = {}
    def guardar(nome, valor):
        saida[nome] = min(valor, saida.get(nome, valor))
    por_numero = {}
    for num, corpo in corpos.items():
        v = ca(corpo)
        if v is not None:
            por_numero[num] = v
    for b in blobs:
        for m in _RE_GS_EM_LINHA.finditer(b):
            v = ca(m.group(2))
            if v is not None:
                guardar(m.group(1), v)
        if por_numero:
            for m in _RE_NOME_REF.finditer(b):
                v = por_numero.get(int(m.group(2)))
                if v is not None:
                    guardar(m.group(1), v)
    return saida


def _texto_claro(dec, tem_imagem=False, estado=None, opacidades=None):
    '[(severidade, amostra, tipo)] de texto mostrado com preenchimento quase branco (`cor`) ou'









    estado = {} if estado is None else estado
    achados, nums, strs = [], [], []
    fill, pilha = estado.get("fill", (1, (0.0,))), list(estado.get("pilha", ()))
    desenho_escuro = estado.get("escuro", False)
    alfa, pilha_alfa = estado.get("alfa", 1.0), list(estado.get("pilha_alfa", ()))
    opacidades = opacidades or {}
    em_texto = cor_no_bloco = False
    nome = None
    transparentes = 0
    for m in _RE_TOK.finditer(dec):
        t = m.group(0)
        c = t[:1]
        if c in b"(<":
            strs.append(t)
            continue
        if c in b"[]":
            continue
        if c == b"/":
            nums, nome = [], t[1:]
            continue
        if c in b"+-.0123456789":
            try:
                nums.append(float(t))
            except ValueError:
                nums = []
            continue
        if t == b"q":
            pilha.append(fill)
            pilha_alfa.append(alfa)
        elif t == b"Q":
            fill = pilha.pop() if pilha else fill
            alfa = pilha_alfa.pop() if pilha_alfa else alfa
        elif t == b"gs":

            if nome is not None and nome in opacidades:
                alfa = opacidades[nome]
        elif t in _OPS_COR:
            precisa = _OPS_COR[t]
            if precisa and len(nums) >= precisa:
                fill = (precisa, tuple(nums[-precisa:]))
            elif not precisa and len(nums) in (1, 3, 4):
                fill = (len(nums), tuple(nums))
            else:
                fill = None
            cor_no_bloco = em_texto
        elif t == b"cs":
            fill = (1, (0.0,))
        elif t in _OPS_PINTA:
            luz = _luz(fill)
            if luz is not None and luz < 0.5:
                desenho_escuro = True
        elif t == b"Do":
            desenho_escuro = True
        elif t == b"BT":
            em_texto, cor_no_bloco = True, False
        elif t == b"ET":
            em_texto = False
        elif t in _OPS_MOSTRA and em_texto:
            if alfa < LIMIAR_OPACIDADE and transparentes < 5:
                transparentes += 1
                achados.append(("media" if tem_imagem else "alta", _amostra_de(strs), "opacidade"))
            elif _quase_branco(fill) and len(achados) - transparentes < 5:
                branco_exato = cor_no_bloco and all(x == (0.0 if fill[0] == 4 else 1.0) for x in fill[1])
                alta = branco_exato or not (desenho_escuro or tem_imagem)
                achados.append(("alta" if alta else "media", _amostra_de(strs), "cor"))
        nums, strs, nome = [], [], None
    estado.update(fill=fill, pilha=tuple(pilha), escuro=desenho_escuro, alfa=alfa,
                  pilha_alfa=tuple(pilha_alfa))
    return achados



_RE_OFF = re.compile(rb"/OFF\s*\[([^\]]*)\]")
_RE_PROPRIEDADES = re.compile(rb"/Properties\s*<<(.*?)>>", re.S)
_RE_NOME_REF = re.compile(rb"/([^\s/<>\[\]()]+)\s+(\d{1,10})\s+\d{1,5}\s+R")
_RE_OC_BDC = re.compile(rb"/OC\s*/([^\s/<>\[\]()]+)\s*BDC(.*?)EMC", re.S)
_RE_OC_REF = re.compile(rb"/OC\s+(\d{1,10})\s+\d{1,5}\s+R")
_RE_IMAGEM = re.compile(rb"/Subtype\s*/Image\b")
_RE_TOK_STR = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>", re.S)
_RE_INFO = re.compile(rb"/Info\s+(\d{1,10})\s+\d{1,5}\s+R")
_CHAVES_INFO = (b"Title", b"Subject", b"Keywords", b"Author", b"Creator", b"Producer")


def _camadas_off(blobs):
    refs = set()
    for b in blobs:
        for m in _RE_OFF.finditer(b):
            refs.update(int(x) for x in _RE_REF.findall(m.group(1)))
    nomes = set()
    if refs:
        for b in blobs:
            for m in _RE_PROPRIEDADES.finditer(b):
                for nome, ref in _RE_NOME_REF.findall(m.group(1)):
                    if int(ref) in refs:
                        nomes.add(nome)
    return refs, nomes








ALTURA_MINIMA_PT = 3.0
_MIN_MICRO_ALTA = 5
_MAX_PAGINAS_PROFUNDA = 300
_RE_PAGINA_BBOX = re.compile(r'<page\s+width="([\d.]+)"\s+height="([\d.]+)"\s*>(.*?)</page>', re.S)
_RE_PALAVRA_BBOX = re.compile(r'<word\s+xMin="([-\d.]+)"\s+yMin="([-\d.]+)"\s+xMax="([-\d.]+)"\s+'
                              r'yMax="([-\d.]+)"\s*>(.*?)</word>', re.S)


def analisar_bbox(xhtml):
    """Achados da saída de `pdftotext -bbox-layout`: palavra fora da página e corpo < 3 pt."""
    fora, micro = [], []
    for n, m in enumerate(_RE_PAGINA_BBOX.finditer(xhtml), 1):
        w, h = float(m.group(1)), float(m.group(2))
        for p in _RE_PALAVRA_BBOX.finditer(m.group(3)):
            x0, y0, x1, y1 = (float(p.group(i)) for i in range(1, 5))
            palavra = html.unescape(p.group(5)).strip()
            letras = sum(ch.isalnum() for ch in palavra)
            if not letras:
                continue
            if x1 <= 0 or y1 <= 0 or x0 >= w or y0 >= h:
                fora.append((n, palavra))
            elif (y1 - y0) < ALTURA_MINIMA_PT and letras >= 3:
                micro.append((n, palavra))
    achados = []
    if fora:
        onde = _texto_do_lugar({n for n, _ in fora})
        achados.append(_achado(
            "texto_fora_da_pagina", "alta",
            f"texto posto fora da área da página — não aparece, e a extração o lê; onde: {onde}",
            " ".join(p for _, p in fora[:40]), onde))
    if micro:
        onde = _texto_do_lugar({n for n, _ in micro})
        sev = "alta" if len(micro) >= _MIN_MICRO_ALTA else "media"
        achados.append(_achado(
            "fonte_microscopica", sev,
            f"{len(micro)} palavra(s) com corpo efetivo abaixo de {ALTURA_MINIMA_PT:g} pt — "
            f"ilegível na página, lida pela IA; onde: {onde}",
            " ".join(p for _, p in micro[:40]), onde))
    return achados










_MIN_CMP = 8


def _normalizar_cmp(t):
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t.lower() if ch.isalnum() and not unicodedata.combining(ch))


def _literais_legiveis(dec):
    saida = []
    for s in re.findall(rb"\((?:\\.|[^\\()])*\)", dec):
        t, _ = _ler_string_pdf(s, 0)
        if t and _legivel(t) and sum(ch.isalpha() for ch in t) >= 0.7 * max(len(t.strip()), 1):
            saida.append(t)
    return saida


def _texto_fora_da_pagina(por_pagina, texto_poppler, max_paginas):
    """[(página, trecho)] do texto literal da página que o poppler não devolveu."""
    faltas = []
    for pagina, literais in sorted(por_pagina.items()):
        if pagina > max_paginas:
            continue



        cands = [(t, _normalizar_cmp(t)) for t in literais if t.isascii()]
        cands = [(t, n) for t, n in cands if len(n) >= _MIN_CMP]
        faltam = [(t, n) for t, n in cands if n not in texto_poppler]


        if not cands or len(faltam) > len(cands) - len(faltam):
            continue
        faltas.extend((pagina, " ".join(t.split())) for t, _ in faltam)
    return faltas


def _candidatos_pdftotext(exe=None):
    if exe:
        return [exe]
    vistos, saida = set(), []
    for c in [os.environ.get("DSR_PDFTOTEXT", "")] + [
            os.path.join(d, nome) for d in os.environ.get("PATH", "").split(os.pathsep) if d
            for nome in ("pdftotext.exe", "pdftotext")]:
        if c and os.path.isfile(c):
            chave = os.path.normcase(os.path.abspath(c))
            if chave not in vistos:
                vistos.add(chave)
                saida.append(c)
    return saida


def camada_profunda_pdf(caminho, exe=None, timeout=180, max_paginas=_MAX_PAGINAS_PROFUNDA):
    """{'rodou': bool, 'motivo'?, 'achados': [...], 'exe'?}. Nunca levanta."""
    import subprocess
    if not caminho or not os.path.isfile(str(caminho)):
        return {"rodou": False, "achados": [], "motivo": "sem arquivo em disco para o poppler ler"}
    candidatos = _candidatos_pdftotext(exe)
    if not candidatos:
        return {"rodou": False, "achados": [], "motivo": "pdftotext (poppler) fora do PATH"}
    motivos = []
    for c in candidatos:
        try:
            proc = subprocess.run([c, "-bbox-layout", "-enc", "UTF-8", "-l", str(max_paginas),
                                   str(caminho), "-"], capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            motivos.append(f"{c}: não terminou em {timeout} s")
            continue
        except OSError as e:
            motivos.append(f"{c}: não executa ({e.__class__.__name__})")
            continue
        saida = proc.stdout.decode("utf-8", "replace")
        if proc.returncode != 0 or "<page" not in saida:
            erro = proc.stderr.decode("utf-8", "replace")
            motivos.append(f"{c}: sem saída -bbox-layout"
                           + (" (é o pdftotext do xpdf, não o do poppler)" if "xpdf" in erro.lower()
                              or "-bbox" in erro else f" (exit {proc.returncode})"))
            continue
        return {"rodou": True, "achados": analisar_bbox(saida), "exe": c,
                "texto": _normalizar_cmp(" ".join(html.unescape(p.group(5))
                                                  for p in _RE_PALAVRA_BBOX.finditer(saida))),
                "max_paginas": max_paginas}
    return {"rodou": False, "achados": [], "motivo": "; ".join(motivos)[:400]}


def varrer_pdf(dados, profunda=False, caminho=None, detector=None, timeout_profunda=180):
    'Varre um PDF (bytes ou caminho). Estrutura e content streams — não renderiza.'




    if caminho is None and isinstance(dados, (str, os.PathLike)):
        caminho = dados
    achados = []
    try:
        if isinstance(dados, (str, os.PathLike)):
            with open(dados, "rb") as fh:
                dados = fh.read()
        if not isinstance(dados, (bytes, bytearray)) or b"%PDF" not in dados[:1024]:
            raise ValueError("não começa por %PDF")
    except Exception as e:
        return {"ok": False, "suspeito": None, "exit_code": 2,
                "erro": f"não foi possível ler como PDF: {e}",
                "aviso": "arquivo ilegível NÃO é arquivo limpo",
                "achados": [], "camada_profunda": TEM_CAMADA_PROFUNDA}

    mapa = _MapaDePaginas(dados)
    for ident, sev, rx, desc in _TOKENS_PDF:
        m = re.search(rx, dados)
        if not m:
            continue
        if ident == "acao_automatica":

            onde = _texto_do_lugar({mapa.lugar_em(x.start()) for x in re.finditer(rx, dados)})
            achados.append(_achado(ident, sev, f"{desc}; onde: {onde}", m.group(0).decode("latin-1"), onde))
            continue
        achados.append(_achado(ident, sev, desc, m.group(0).decode("latin-1")))


    eofs = dados.count(b"%%EOF")
    if eofs > 1:
        achados.append(_achado(
            "atualizacao_incremental", "baixa",
            f"{eofs} atualizações incrementais — esperado em documento assinado "
            "digitalmente; só interessa se houver outro achado junto", f"%%EOF x{eofs}"))

    tem_imagem = bool(re.search(rb"/Subtype\s*/Image|/DCTDecode|/JPXDecode|/CCITTFaxDecode",
                                dados))


    invisiveis = {}
    ja_acusados = {a["id"] for a in achados}
    comprimidos, textos, xmp, camada_txt, literais_pagina, estados_pagina = [], [], [], [], {}, {}

    pre = [decodificar_stream(m.group(1)) for m in RE_STREAM.finditer(dados)
           if mapa.objeto_em(m.start()) in mapa.comprimidos][:200]
    refs_off, nomes_off = _camadas_off([dados] + pre)
    opacidades = _opacidades([dados] + pre, mapa.corpos)
    for pos, dec in _streams(dados):
        if mapa.objeto_em(pos) in mapa.comprimidos:
            comprimidos.append(dec)


            for ident, sev, rx, desc in _TOKENS_PDF:
                m = re.search(rx, dec)
                if m and ident not in ja_acusados:
                    ja_acusados.add(ident)
                    achados.append(_achado(ident, sev, f"{desc}; onde: {SEM_PAGINA} (o arquivo guarda a "
                                           "estrutura comprimida)", m.group(0).decode("latin-1"), SEM_PAGINA))
            continue


        if _RE_E_EMBUTIDO.search(mapa.corpos.get(mapa.objeto_em(pos), b"")):
            t = _texto_embutido(dec)
            if t:
                textos.append(("arquivo embutido", "", t))
            continue
        if _cmap_devolve_invisivel(dec):
            invisiveis.setdefault("caractere_invisivel", (_achado(
                "caractere_invisivel", "media",
                "caractere de largura zero no texto de uma fonte do documento — some na tela, "
                "entra no texto extraído", "(caractere invisível removido da amostra)"), set()))[1].add(None)
        if b"xmpmeta" in dec[:4096] or b"<rdf:RDF" in dec[:4096]:
            t = _texto_xml(dec.decode("utf-8", "replace"))
            if t:
                xmp.append(t)
            continue
        corpo = mapa.corpos.get(mapa.objeto_em(pos), b"")

        pag = mapa.conteudos.get(mapa.objeto_em(pos))
        estado = estados_pagina.setdefault(pag, {}) if pag is not None else None
        if _RE_IMAGEM.search(corpo) or not _parece_conteudo(dec):
            continue
        if b"BT" not in dec:
            if estado is not None:
                _texto_claro(dec, tem_imagem, estado, opacidades)
            continue
        lugar = mapa.lugar_em(pos)
        onde = _texto_do_lugar({lugar}) if lugar is not None else ""
        if profunda and mapa.objeto_em(pos) in mapa.conteudos:
            literais_pagina.setdefault(mapa.conteudos[mapa.objeto_em(pos)], []).extend(
                _literais_legiveis(dec))
        if _RE_MOSTRA_TEXTO.search(dec):
            for sev, amostra, tipo in _texto_claro(dec, tem_imagem, estado, opacidades):
                if tipo == "opacidade":
                    achados.append(_achado(
                        "texto_transparente", sev,
                        "texto desenhado com opacidade zero (ou quase) — invisível na página, "
                        "legível na extração" + ("" if sev == "alta" else
                                                 "; com imagem no arquivo, pode ser a camada de "
                                                 "reconhecimento de texto de um escaneado"),
                        amostra, onde))
                elif sev == "alta":
                    achados.append(_achado(
                        "texto_invisivel_cor", "alta",
                        "texto desenhado com preenchimento branco ou quase branco — invisível "
                        "na página, legível na extração", amostra, onde))
                else:
                    achados.append(_achado(
                        "texto_claro_sobre_desenho", "media",
                        "texto em branco ou quase branco depois de um desenho escuro ou imagem — "
                        "pode ser título sobre faixa; confira se aparece na página", amostra, onde))

            if nomes_off:
                for m_oc in _RE_OC_BDC.finditer(dec):
                    if m_oc.group(1) in nomes_off and _RE_MOSTRA_TEXTO.search(m_oc.group(2)):
                        camada_txt.append((onde, _amostra_de(_RE_TOK_STR.findall(m_oc.group(2)))))
            m_ref = _RE_OC_REF.search(corpo)
            if m_ref and int(m_ref.group(1)) in refs_off:
                camada_txt.append((onde, _amostra_de(_RE_TOK_STR.findall(dec))))
        for m_rv in _RE_RECORTE_VAZIO.finditer(dec):
            m_q = _RE_Q_FECHA.search(dec, m_rv.end())
            trecho_rv = dec[m_rv.end():m_q.start() if m_q else len(dec)]
            blocos_rv = [b for b in _RE_BT_ET.findall(trecho_rv) if _RE_MOSTRA_TEXTO.search(b)]
            if blocos_rv:
                achados.append(_achado(
                    "texto_em_recorte_vazio", "alta",
                    "texto desenhado dentro de um recorte de área zero (re W n com largura e altura "
                    "zero) — não aparece na página, e a extração o lê",
                    b" ".join(_RE_LITERAL.findall(b" ".join(blocos_rv)))[:200]
                    .decode("latin-1", "replace")))
                break
        for bloco in _RE_BT_ET.findall(dec):
            if not _RE_MOSTRA_TEXTO.search(bloco):
                continue
            amostra = b" ".join(_RE_LITERAL.findall(bloco))[:200].decode("latin-1", "replace")
            if _RE_TR7.search(bloco):
                achados.append(_achado(
                    "texto_recorte_render", "media" if tem_imagem else "alta",
                    "texto em modo de recorte (7 Tr): entra só no recorte e não é pintado"
                    + (" — com imagem no arquivo pode ser texto preenchido por imagem; confira na "
                       "página" if tem_imagem else " — sem imagem no arquivo, nada o mostra"),
                    amostra))
            if _RE_TR3.search(bloco):
                if tem_imagem:
                    achados.append(_achado(
                        "camada_ocr", "baixa",
                        "texto em modo invisível (3 Tr) com imagem no arquivo — é a camada "
                        "de OCR de documento escaneado, comportamento esperado", amostra))
                else:
                    achados.append(_achado(
                        "texto_invisivel_render", "alta",
                        "texto em modo de renderização invisível (3 Tr) SEM nenhuma imagem "
                        "no arquivo — não há camada de OCR que justifique", amostra))
    for a, lugares in invisiveis.values():
        onde = _texto_do_lugar(lugares)
        achados.append(_achado(a["id"], a["severidade"], f"{a['descricao']}; onde: {onde}", a["trecho"], onde))


    for onde, amostra in camada_txt:
        achados.append(_achado(
            "camada_desligada", "alta",
            "texto numa camada que o documento declara DESLIGADA — não aparece na página, e a "
            "extração o lê" + (f"; onde: {onde}" if onde else ""), amostra, onde))
        if amostra:
            textos.append(("camada desligada", onde, amostra))
    if refs_off and not camada_txt:
        achados.append(_achado(
            "camada_desligada", "baixa",
            "o documento declara camada desligada, sem texto achado nela pela leitura da "
            "estrutura — informativo", "/OCProperties /OFF"))
    for num, corpo in mapa.corpos.items():
        if b"/ByteRange" in corpo or re.search(rb"/Type\s*/Sig\b", corpo):
            continue
        lugar = mapa.pagina_de.get(num)
        onde = _texto_do_lugar({lugar}) if lugar is not None else ""
        for t in _strings_da_chave(corpo, b"Contents"):
            textos.append(("anotação", onde, t))
        if b"/FT" in corpo or re.search(rb"/T\s*[(<]", corpo):
            for t in _strings_da_chave(corpo, b"V"):
                textos.append(("campo de formulário", onde, t))
    for blob in pre:

        for t in _strings_da_chave(blob, b"Contents"):
            textos.append(("anotação", SEM_PAGINA, t))
        for m_v in re.finditer(rb"/FT\s*/\w+", blob):
            for t in _strings_da_chave(blob[m_v.start():m_v.start() + 600], b"V")[:1]:
                textos.append(("campo de formulário", SEM_PAGINA, t))
    for num in {int(n) for n in _RE_INFO.findall(dados)}:
        corpo = mapa.corpos.get(num, b"")
        partes = [t for chave in _CHAVES_INFO for t in _strings_da_chave(corpo, chave)]
        if partes:
            textos.append(("metadados", "propriedades do documento", " | ".join(partes)))
    for t in xmp:
        textos.append(("metadados", "propriedades do documento", t))
    for fonte, onde, t in textos:
        if fonte != "camada desligada":
            _invisiveis(t, achados, f"texto de {fonte}", onde)

    extra_prof = {}
    if profunda:
        prof = camada_profunda_pdf(caminho, timeout=timeout_profunda)
        if prof["rodou"]:
            achados.extend(prof["achados"])
            extra_prof["camada_profunda"] = True
            faltas = _texto_fora_da_pagina(literais_pagina, prof["texto"], prof["max_paginas"])
            if faltas and not any(a["id"] == "texto_fora_da_pagina" for a in prof["achados"]):
                onde = _texto_do_lugar({p for p, _ in faltas})
                achados.append(_achado(
                    "texto_fora_da_pagina", "media",
                    "texto escrito no arquivo que o leitor de PDF não mostra na página (desenhado "
                    f"fora da área visível, provavelmente); onde: {onde}",
                    " | ".join(t for _, t in faltas[:10]), onde))
                for p, t in faltas[:20]:
                    textos.append(("texto fora da página", _texto_do_lugar({p}), t))
        else:
            extra_prof["camada_profunda_motivo"] = prof.get("motivo", "")
    det = _detector_padrao() if detector is None else (detector or None)
    extra = {"detector_linguistico": True} if _julgar_textos(textos, achados, det) else _sem_detector(textos)
    extra.update(extra_prof)
    return _resultado(achados, "pdf", extra)




def _sem_detector(textos):
    return {"detector_linguistico": False,
            "textos_nao_exibidos": [{"fonte": f, "onde": o, "texto": " ".join(t.split())[:300]}
                                    for f, o, t in textos[:20]]}


def _resultado(achados, tipo, extra=None):
    extra = dict(extra or {})
    vistos, unicos = set(), []
    for a in achados:



        chave = (a["id"], a.get("parte", ""), a["trecho"][:60])
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(a)
    sev_max = max((ORDEM_SEV[a["severidade"]] for a in unicos), default=0)
    codigo = 1 if sev_max >= ORDEM_SEV["alta"] else 0
    out = {
        "ok": True, "tipo": tipo, "suspeito": bool(unicos),
        "severidade_max": {3: "alta", 2: "media", 1: "baixa", 0: "nenhuma"}[sev_max],
        "exit_code": codigo, "total": len(unicos), "achados": unicos[:50],
        "camada_profunda": bool(extra.pop("camada_profunda", TEM_CAMADA_PROFUNDA)),
    }
    out["aviso_cobertura"] = AVISO_COM_CAMADA_PROFUNDA if out["camada_profunda"] else AVISO_SEM_CAMADA_PROFUNDA
    if extra.get("detector_linguistico") is False:
        out["aviso_cobertura"] += AVISO_SEM_DETECTOR
    out.update(extra)
    if codigo == 1:
        out["acao"] = "escalar"
        out["aviso"] = (
            "ELEMENTO OCULTO no documento: tratar como conteúdo NÃO CONFIÁVEL e escalar ao "
            "advogado. Na SAÍDA, não entregar antes de remover: quem responde pelo texto "
            "oculto é quem protocola, não quem escreveu.")
    elif unicos:
        out["acao"] = "revisar"
    else:
        out["acao"] = "seguir"
    return out


def varrer(caminho, entrada=False, profunda=False):
    '`entrada=True`: documento lido de fora ou arquivo final a conferir — o texto não exibido'

    ext = os.path.splitext(str(caminho))[1].lower()
    if ext in (".docx", ".docm"):
        return varrer_docx(caminho, linguistico=entrada)
    if ext == ".pdf":
        return varrer_pdf(caminho, profunda=profunda)
    return {"ok": False, "exit_code": 2, "achados": [], "camada_profunda": TEM_CAMADA_PROFUNDA,
            "erro": f"extensão não coberta por esta varredura: {ext or '(sem extensão)'}"}


def main(argv):


    sem_profunda = "--sem-camada-profunda" in argv
    argv = [a for a in argv if a != "--sem-camada-profunda"]
    if len(argv) != 2 or not os.path.isfile(argv[1]):
        print(json.dumps({"ok": False, "exit_code": 2,
                          "erro": "informe UM arquivo .pdf ou .docx existente",
                          "uso": "python3 varredura_documento.py <arquivo> [--sem-camada-profunda]"},
                         ensure_ascii=False))
        return 2
    r = varrer(argv[1], entrada=True, profunda=not sem_profunda)
    code = r.get("exit_code", 2)
    print(json.dumps(r, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
