#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'varredura_documento.py — Varredura ESTRUTURAL de documento: entrada e saída (Dissero).'





































import base64
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
    "efetiva de cada trecho após máscaras, o TAMANHO efetivo de fonte após a matriz de texto, "
    "nem o conteúdo de anotações. A varredura estrutural rodou e vale; a cobertura é PARCIAL.")

ZERO_WIDTH = "​‌‍⁠﻿­"
_TAG_CHARS = re.compile(r"[\U000E0000-\U000E007F]")
ORDEM_SEV = {"alta": 3, "media": 2, "baixa": 1}
_MAX_STREAM = 8_000_000


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
    m = _TAG_CHARS.search(texto)
    if m:
        achados.append(_achado(
            "unicode_tag", "alta",
            f"Unicode Tag char (U+E0000–U+E007F) em {onde} — canal clássico de instrução "
            "oculta, sem nenhum uso legítimo em peça",
            repr(m.group(0)), parte))




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


def _escopos_de_fundo(doc):
    '[(ini, fim, fill)] de cada elemento que DECLARA sombreamento, por posição no XML.'




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
    com_fundo = []
    for nome, ini, fim in escopos:
        fill = _fill_declarado(_props_proprias(doc[ini:fim], _PROPS_DE[nome]))
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
    rgb_fundo = _rgb(fundo)
    if rgb_fundo is None:
        return False
    return _cw.contraste(rgb_texto, rgb_fundo) >= CONTRASTE_MINIMO_FUNDO





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












_PARTES_EXTRA = re.compile(r"^word/(header\d+|footer\d+|footnotes|endnotes)\.xml$")
_NOME_DA_PARTE = {"header": "cabeçalho", "footer": "rodapé",
                  "footnotes": "nota de rodapé", "endnotes": "nota de fim"}


def _nome_da_parte(nome_do_arquivo):
    base = nome_do_arquivo[len("word/"):-len(".xml")].rstrip("0123456789")
    return _NOME_DA_PARTE.get(base, base)


def _varrer_runs(xml, achados, parte=""):
    'As regras de run — as MESMAS para o corpo e para as partes de fora dele.'





    escopos = _escopos_de_fundo(xml)
    for achado_run in _RE_RUN.finditer(xml):
        run_xml = achado_run.group(1)
        texto = _texto_do_run(run_xml).strip()
        if not texto:
            continue
        cor = _RE_COR.search(run_xml)



        if (cor and cor.group(1).strip().lower().lstrip("#") in _CORES_BRANCAS
                and not _fundo_sustenta(run_xml, achado_run.start(), escopos,
                                        cor.group(1))):
            achados.append(_achado(
                "texto_invisivel_cor", "alta",
                "texto em cor branca sobre fundo claro ou ausente — invisível na tela, "
                "legível pela IA processante",
                texto, parte))
        sz = _RE_SZ.search(run_xml)
        if sz and int(sz.group(1)) < 5:
            achados.append(_achado(
                "fonte_microscopica", "alta",
                f"fonte de {int(sz.group(1)) / 2:g}pt — abaixo do legível; nenhuma peça "
                "legítima usa esse corpo", texto, parte))
        if _RE_VANISH.search(run_xml):
            achados.append(_achado(
                "texto_oculto", "alta",
                "texto marcado como oculto (w:vanish) — não imprime, não aparece, e "
                "mesmo assim viaja no arquivo", texto, parte))

    for instr in _RE_INSTR.findall(xml):
        if _CAMPOS_EXTERNOS.search(instr):
            achados.append(_achado(
                "campo_externo", "alta",
                "campo que puxa conteúdo de fora ao abrir o documento — o que a peça "
                "mostra deixa de ser o que ela contém", instr.strip(), parte))

    _invisiveis(unicodedata.normalize("NFC", " ".join(_RE_TEXTO.findall(xml))), achados,
                f"{parte} da peça" if parte else "texto da peça", parte)


def varrer_docx(dados):
    """Varre um .docx (bytes ou caminho). É a peça que o plugin ENTREGA."""
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

    _varrer_runs(doc, achados)




    for nome in sorted(n for n in nomes if _PARTES_EXTRA.match(n)):
        try:
            xml_parte = z.read(nome).decode("utf-8", "replace")
        except Exception:
            continue
        _varrer_runs(xml_parte, achados, _nome_da_parte(nome))

    if any(n.endswith("vbaProject.bin") for n in nomes):
        achados.append(_achado("macro_embutida", "alta",
                               "macro (VBA) embutida no documento", "word/vbaProject.bin"))

    achados.extend(conferir_timbrado(z, nomes))

    return _resultado(achados, "docx")




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

_RE_BRANCO = re.compile(rb"(?:^|[\s])(?:1(?:\.0+)?\s+1(?:\.0+)?\s+1(?:\.0+)?\s+rg|1(?:\.0+)?\s+g)\b")
_RE_TR3 = re.compile(rb"(?:^|[\s])3\s+Tr\b")
_RE_MOSTRA_TEXTO = re.compile(rb"\b(?:Tj|TJ|'|\")\B|\bTj\b|\bTJ\b")
_RE_LITERAL = re.compile(rb"\(([^)\\]{4,200})\)")


def decodificar_stream(bruto):
    'O conteúdo do stream, decodificado o bastante para ler os operadores.'




    try:
        return zlib.decompress(bruto)
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
        yield dec


def varrer_pdf(dados):
    """Varre um PDF (bytes ou caminho). Estrutura e content streams — não renderiza."""
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

    for ident, sev, rx, desc in _TOKENS_PDF:
        m = re.search(rx, dados)
        if m:
            achados.append(_achado(ident, sev, desc, m.group(0).decode("latin-1")))


    eofs = dados.count(b"%%EOF")
    if eofs > 1:
        achados.append(_achado(
            "atualizacao_incremental", "baixa",
            f"{eofs} atualizações incrementais — esperado em documento assinado "
            "digitalmente; só interessa se houver outro achado junto", f"%%EOF x{eofs}"))

    tem_imagem = bool(re.search(rb"/Subtype\s*/Image|/DCTDecode|/JPXDecode|/CCITTFaxDecode",
                                dados))
    for dec in _streams(dados):
        for bloco in _RE_BT_ET.findall(dec):
            if not _RE_MOSTRA_TEXTO.search(bloco):
                continue
            amostra = b" ".join(_RE_LITERAL.findall(bloco))[:200].decode("latin-1", "replace")
            if _RE_BRANCO.search(bloco):
                achados.append(_achado(
                    "texto_invisivel_cor", "alta",
                    "texto desenhado com preenchimento branco — invisível na página, "
                    "legível na extração", amostra))
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
        _invisiveis(dec.decode("latin-1", "replace"), achados, "content stream")

    return _resultado(achados, "pdf")




def _resultado(achados, tipo):
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
        "camada_profunda": TEM_CAMADA_PROFUNDA,
    }
    if not TEM_CAMADA_PROFUNDA:
        out["aviso_cobertura"] = AVISO_SEM_CAMADA_PROFUNDA
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


def varrer(caminho):
    ext = os.path.splitext(str(caminho))[1].lower()
    if ext in (".docx", ".docm"):
        return varrer_docx(caminho)
    if ext == ".pdf":
        return varrer_pdf(caminho)
    return {"ok": False, "exit_code": 2, "achados": [], "camada_profunda": TEM_CAMADA_PROFUNDA,
            "erro": f"extensão não coberta por esta varredura: {ext or '(sem extensão)'}"}


def main(argv):
    if len(argv) != 2 or not os.path.isfile(argv[1]):
        print(json.dumps({"ok": False, "exit_code": 2,
                          "erro": "informe UM arquivo .pdf ou .docx existente",
                          "uso": "python3 varredura_documento.py <arquivo>"}, ensure_ascii=False))
        return 2
    r = varrer(argv[1])
    code = r.get("exit_code", 2)
    print(json.dumps(r, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
