#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'extrair_papel.py — tira do modelo Word do escritório só o que é do PAPEL, e envia ao servidor.'
























import argparse
import hashlib
import io
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perfil_advogado as PA

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"w": W, "a": A}



LIMITE_PACOTE = 800 * 1024
LIMITE_IMAGEM_AVULSA = 300 * 1024


LIMITE_DOCUMENTO = 64 * 1024 * 1024
LIMITE_PARTE = 2 * 1024 * 1024

FAIXA_TAMANHO_PT = (8, 16)

RX_PARTE = re.compile(r"^word/(header|footer)(\d+)\.xml$")
RX_ALVO_MIDIA = re.compile(r'Target="(?:/word/)?(media/[^"]+)"')
RX_TEXTO_P = re.compile(r"<w:p[ >][\s\S]*?</w:p>")
RX_TEXTO_T = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>|<w:noBreakHyphen\s*/>")


FAROS = (
    ("um número de processo", re.compile(r"(?<!\d)(?:\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|\d{20})(?!\d)")),
    ("um CPF", re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")),
    ("um CNPJ", re.compile(r"(?<!\d)\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}(?!\d)")),
)


class Recusa(Exception):
    """O arquivo não serve como está. A mensagem é a frase para o advogado."""




def tipo_imagem(b):
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:3] == b"\xff\xd8\xff":
        return "jpg"
    return None


def dimensoes_imagem(b):
    """(largura, altura) em pixels, lidas do cabeçalho do arquivo, ou None."""
    t = tipo_imagem(b)
    if t == "png" and len(b) >= 24 and b[12:16] == b"IHDR":
        return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")
    if t == "jpg":
        i = 2
        while i + 9 < len(b):
            if b[i] != 0xFF:
                i += 1
                continue
            marca = b[i + 1]
            if marca in (0xD8, 0x01) or 0xD0 <= marca <= 0xD7:
                i += 2
                continue
            tam = int.from_bytes(b[i + 2:i + 4], "big")
            if marca in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
            i += 2 + tam
    return None


def ler_imagem(caminho, papel):
    try:
        with open(caminho, "rb") as fh:
            b = fh.read(LIMITE_IMAGEM_AVULSA + 1)
    except OSError:
        raise Recusa(f"Não consegui abrir a imagem da {papel}. Confira o arquivo e tente de novo.")
    if len(b) > LIMITE_IMAGEM_AVULSA:
        raise Recusa(f"A imagem da {papel} passa de 300 KB. Reduza a imagem e tente de novo.")
    t = tipo_imagem(b)
    if not t:
        raise Recusa(f"A imagem da {papel} não é PNG nem JPEG. Salve como PNG e tente de novo.")
    return t, b




def _indexar(z):
    'nome -> ZipInfo, com o nome decodificado como o Worker e o navegador o leem, guardado'





    indice = dict(PA._entradas_zip(z))
    z.dsr_indice = indice
    return indice


def _ler(z, nome, teto):
    info = z.dsr_indice[nome]
    if info.file_size > teto:
        raise Recusa("Esse arquivo tem uma parte grande demais para ser um modelo. Envie o modelo em branco do escritório.")
    with z.open(info) as fh:
        dados = fh.read(teto + 1)
    if len(dados) > teto:
        raise Recusa("Esse arquivo tem uma parte grande demais para ser um modelo. Envie o modelo em branco do escritório.")
    return dados


def texto_de(xml):
    'Linhas de texto de cabeçalho/rodapé. `<w:noBreakHyphen/>` conta como "-": sem isso a'


    linhas = []
    for p in RX_TEXTO_P.findall(xml):
        t = "".join(m.group(1) if m.group(1) is not None else "-" for m in RX_TEXTO_T.finditer(p)).strip()
        if t:
            linhas.append(t)
    return linhas









































RX_TAG = re.compile(r"<[^>]*>")
RX_NOME_TAG = re.compile(r"</?([\w:.-]+)")
RX_ATRIB = re.compile(r"([\w:.-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")
TOGGLES = ("b", "bCs", "i", "iCs", "caps")
ORDEM_RPR = ("ins", "del", "moveFrom", "moveTo", "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps",
             "smallCaps", "strike", "dstrike", "outline", "shadow", "emboss", "imprint", "noProof",
             "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern", "position", "sz",
             "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs",
             "em", "lang", "eastAsianLayout", "specVanish", "oMath")
ORDEM_PPR = ("pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
             "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
             "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
             "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap",
             "jc", "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId",
             "cnfStyle", "rPr", "sectPr", "pPrChange")
COBERTOS_RPR = ("rFonts", "b", "bCs", "i", "iCs", "caps", "color", "spacing", "sz", "szCs")
COBERTOS_PPR = ("pBdr", "tabs", "spacing", "ind", "jc", "rPr")
RX_PALAVRA = re.compile(r"^[A-Za-z]+$")
RX_POS_TAB = re.compile(r"^-?\d{1,9}$")
LADOS_BORDA = ("top", "left", "bottom", "right", "between", "bar")
ATRIB_BORDA = ("val", "sz", "space", "color", "shadow", "frame")
ATRIB_ESPACO = ("before", "beforeLines", "beforeAutospacing", "after", "afterLines", "afterAutospacing", "line", "lineRule")
ATRIB_RECUO = ("left", "leftChars", "right", "rightChars", "hanging", "hangingChars", "firstLine", "firstLineChars")
SINONIMO_RECUO = {"start": "left", "end": "right", "startChars": "leftChars", "endChars": "rightChars"}
COR_DO_TEMA = {"dark1": "dk1", "light1": "lt1", "dark2": "dk2", "light2": "lt2", "text1": "dk1",
               "background1": "lt1", "text2": "dk2", "background2": "lt2", "accent1": "accent1",
               "accent2": "accent2", "accent3": "accent3", "accent4": "accent4", "accent5": "accent5",
               "accent6": "accent6", "hyperlink": "hlink", "followedHyperlink": "folHlink"}
RX_HEX6 = re.compile(r"^[0-9A-Fa-f]{6}$")
RX_INT = re.compile(r"^-?\d+$")


def _nome_tag(tag):
    m = RX_NOME_TAG.match(tag)
    return m.group(1) if m else ""


def _atribs(tag):
    return {m.group(1): (m.group(2) if m.group(2) is not None else m.group(3)) for m in RX_ATRIB.finditer(tag)}


def _segmentos(s):
    """Filhos diretos de um conteúdo XML: [("t", texto) | ("e", nome, bruto)], sem perder byte."""
    segs, pos, prof, ini, nome = [], 0, 0, 0, ""
    for m in RX_TAG.finditer(s):
        tag = m.group(0)
        if tag.startswith("<?") or tag.startswith("<!"):
            continue
        fecha, auto = tag.startswith("</"), tag.endswith("/>")
        if prof == 0:
            if fecha:
                continue
            if m.start() > pos:
                segs.append(("t", s[pos:m.start()]))
            if auto:
                segs.append(("e", _nome_tag(tag), tag))
                pos = m.end()
                continue
            ini, nome, prof = m.start(), _nome_tag(tag), 1
        else:
            if fecha:
                prof -= 1
            elif not auto:
                prof += 1
            if prof == 0:
                segs.append(("e", nome, s[ini:m.end()]))
                pos = m.end()
    if prof:
        segs.append(("t", s[ini:]))
    elif pos < len(s):
        segs.append(("t", s[pos:]))
    return segs


def _partir(bruto):
    """(tag de abertura, miolo, tag de fechamento) de um elemento; miolo vazio se autofechado."""
    abre = RX_TAG.match(bruto).group(0)
    if abre.endswith("/>"):
        return abre, "", ""
    fecha = bruto.rfind("</")
    return abre, bruto[len(abre):fecha], bruto[fecha:]


def _filhos(bruto):
    return [] if bruto is None else _segmentos(_partir(bruto)[1])


def _local(nome):
    return nome[2:] if nome.startswith("w:") else None


def _primeiro(segs, nome):
    for k, sg in enumerate(segs):
        if sg[0] == "e" and sg[1] == nome:
            return k
    return None


def _q(v):
    'Valor de atributo pronto para ir entre aspas duplas: um `"` vindo de atributo com aspas'

    return str(v).replace('"', "&quot;")


def _ligado(a):
    return a.get("w:val", "true") not in ("0", "false", "off")


def _luz(hexa, fator, clarear):
    'Tint/shade do Word: luminância em HSL, canal truncado (com folga de 1e-9 contra o erro'



    r, g, b = (int(hexa[k:k + 2], 16) / 255 for k in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    luz = (mx + mn) / 2
    if mx == mn:
        mat = sat = 0.0
    else:
        d = mx - mn
        sat = d / (1 - abs(2 * luz - 1))
        if mx == r:
            mat = (g - b) / d
            if mat < 0:
                mat += 6
        elif mx == g:
            mat = (b - r) / d + 2
        else:
            mat = (r - g) / d + 4
    f = fator / 255
    luz = luz * f + (1 - f) if clarear else luz * f
    c = (1 - abs(2 * luz - 1)) * sat
    x = c * (1 - abs(mat % 2 - 1))
    m = luz - c / 2
    setor = int(mat) % 6
    rgb = ((c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x))[setor]
    return "".join("%02X" % min(255, max(0, math.floor((v + m) * 255 + 1e-9))) for v in rgb)


def _cor(a, tema, chave="w:val"):
    """Cor efetiva de um w:color / lado de borda: tema resolvido para hex, ou o val, ou None."""
    ref = COR_DO_TEMA.get(a.get("w:themeColor", ""))
    base = tema["cores"].get(ref) if ref else None
    if base:
        for atr, clarear in (("w:themeTint", True), ("w:themeShade", False)):
            v = a.get(atr, "")
            if re.fullmatch(r"[0-9A-Fa-f]{1,2}", v):
                base = _luz(base, int(v, 16), clarear)
        return base
    v = a.get(chave, "")
    if RX_HEX6.match(v):
        return v.upper()
    return "auto" if v == "auto" else None


def _fonte_do_tema(tema, ref):
    m = re.fullmatch(r"(major|minor)(Ascii|HAnsi|EastAsia|Bidi)", ref or "")
    if not m:
        return None
    slot = {"Ascii": "latin", "HAnsi": "latin", "EastAsia": "ea", "Bidi": "cs"}[m.group(2)]
    return tema["fontes"].get(m.group(1) + "_" + slot) or None


def _props_r(segs, tema):
    p = {}
    for sg in segs:
        if sg[0] != "e":
            continue
        nome = _local(sg[1])
        if nome not in COBERTOS_RPR:
            continue
        a = _atribs(RX_TAG.match(sg[2]).group(0))
        if nome == "rFonts":
            fontes = {}
            for slot, tslot in (("ascii", "asciiTheme"), ("hAnsi", "hAnsiTheme"), ("eastAsia", "eastAsiaTheme"), ("cs", "cstheme")):
                v = _fonte_do_tema(tema, a.get("w:" + tslot)) if ("w:" + tslot) in a else None
                if not v and a.get("w:" + slot):
                    v = a["w:" + slot]
                if v:
                    fontes[slot] = v
            if fontes:
                p["fontes"] = {**p.get("fontes", {}), **fontes}
        elif nome in TOGGLES:
            p[nome] = _ligado(a)
        elif nome == "color":
            c = _cor(a, tema)
            if c:
                p["cor"] = c
        elif nome in ("sz", "szCs", "spacing"):
            v = a.get("w:val", "")
            if RX_INT.match(v):
                p["espaco" if nome == "spacing" else nome] = int(v)
    return p


def _props_p(segs, tema):
    p = {}
    for sg in segs:
        if sg[0] != "e":
            continue
        nome = _local(sg[1])
        a = _atribs(RX_TAG.match(sg[2]).group(0))
        if nome == "jc" and a.get("w:val"):
            p["jc"] = a["w:val"]
        elif nome == "spacing":
            p["espaco"] = {k: a["w:" + k] for k in ATRIB_ESPACO if ("w:" + k) in a}
        elif nome == "ind":
            recuo = {}
            for k, v in a.items():
                k = SINONIMO_RECUO.get(k[2:], k[2:]) if k.startswith("w:") else None
                if k in ATRIB_RECUO:
                    recuo[k] = v
            p["recuo"] = recuo
        elif nome == "tabs":
            tabs = []
            for t in _filhos(sg[2]):
                if t[0] != "e" or t[1] != "w:tab":
                    continue
                at = _atribs(RX_TAG.match(t[2]).group(0))
                pos, val, lid = at.get("w:pos", ""), at.get("w:val", ""), at.get("w:leader", "")
                if RX_POS_TAB.match(pos) and RX_PALAVRA.match(val) and (not lid or RX_PALAVRA.match(lid)):
                    tabs.append((str(int(pos)), val, lid))
            p["tabs"] = tabs
        elif nome == "pBdr":
            bordas = {}
            for lado in _filhos(sg[2]):
                if lado[0] != "e":
                    continue
                ln = {"start": "left", "end": "right"}.get(_local(lado[1]) or "", _local(lado[1]))
                if ln not in LADOS_BORDA:
                    continue
                al = _atribs(RX_TAG.match(lado[2]).group(0))
                b = {k: al["w:" + k] for k in ATRIB_BORDA if k != "color" and ("w:" + k) in al}
                c = _cor(al, tema, "w:color")
                if c:
                    b["color"] = c
                bordas[ln] = b
            p["bordas"] = bordas
    return p


def _sobrepor_r(base, nivel):
    out = dict(base)
    for k, v in nivel.items():
        out[k] = {**base.get("fontes", {}), **v} if k == "fontes" else v
    return out


def _sobrepor_p(base, nivel):
    out = dict(base)
    if "jc" in nivel:
        out["jc"] = nivel["jc"]
    if "espaco" in nivel:
        out["espaco"] = {**base.get("espaco", {}), **nivel["espaco"]}
    if "recuo" in nivel:
        r = dict(base.get("recuo", {}))
        n = nivel["recuo"]
        if "firstLine" in n or "firstLineChars" in n:
            r.pop("hanging", None)
            r.pop("hangingChars", None)
        if "hanging" in n or "hangingChars" in n:
            r.pop("firstLine", None)
            r.pop("firstLineChars", None)
        r.update(n)
        out["recuo"] = r
    if "bordas" in nivel:
        out["bordas"] = {**base.get("bordas", {}), **nivel["bordas"]}
    if "tabs" in nivel:
        m = {pos: (val, lid) for pos, val, lid in base.get("tabs", [])}
        for pos, val, lid in nivel["tabs"]:


            m[pos] = ("clear", "") if val == "clear" else (val, lid)
        out["tabs"] = [(pos, m[pos][0], m[pos][1]) for pos in sorted(m, key=int)]
    return out


def ler_estilos_do_modelo(xml_estilos, xml_tema):
    """Estrutura da cascata: docDefaults, estilos por id e os estilos padrão."""
    tema = {"fontes": {}, "cores": {}}
    if xml_tema:
        for tipo in ("major", "minor"):
            m = re.search(rf"<a:{tipo}Font>([\s\S]*?)</a:{tipo}Font>", xml_tema)
            if m:
                for slot in ("latin", "ea", "cs"):
                    mm = re.search(rf"<a:{slot}\b[^>]*\btypeface=\"([^\"]*)\"", m.group(1))
                    if mm and mm.group(1):
                        tema["fontes"][f"{tipo}_{slot}"] = mm.group(1)
        m = re.search(r"<a:clrScheme\b[^>]*>([\s\S]*?)</a:clrScheme>", xml_tema)
        if m:
            for nome in set(COR_DO_TEMA.values()):
                mm = re.search(rf"<a:{nome}>([\s\S]*?)</a:{nome}>", m.group(1))
                if not mm:
                    continue
                c = (re.search(r"<a:srgbClr\b[^>]*\bval=\"([0-9A-Fa-f]{6})\"", mm.group(1))
                     or re.search(r"<a:sysClr\b[^>]*\blastClr=\"([0-9A-Fa-f]{6})\"", mm.group(1)))
                if c:
                    tema["cores"][nome] = c.group(1).upper()
    est = {"tema": tema, "estilos": {}, "dd_r": {}, "dd_p": {}, "padrao": {}}
    raiz = _segmentos(xml_estilos)
    k = _primeiro(raiz, "w:styles")
    if k is None:
        return est
    for sg in _filhos(raiz[k][2]):
        if sg[0] != "e":
            continue
        if sg[1] == "w:docDefaults":
            for d in _filhos(sg[2]):
                if d[0] == "e" and d[1] == "w:rPrDefault":
                    f = _filhos(d[2])
                    j = _primeiro(f, "w:rPr")
                    if j is not None:
                        est["dd_r"] = _props_r(_filhos(f[j][2]), tema)
                elif d[0] == "e" and d[1] == "w:pPrDefault":
                    f = _filhos(d[2])
                    j = _primeiro(f, "w:pPr")
                    if j is not None:
                        est["dd_p"] = _props_p(_filhos(f[j][2]), tema)
        elif sg[1] == "w:style":
            a = _atribs(RX_TAG.match(sg[2]).group(0))
            sid, tipo = a.get("w:styleId"), a.get("w:type", "paragraph")
            if not sid:
                continue
            f = _filhos(sg[2])
            j = _primeiro(f, "w:basedOn")
            base = _atribs(RX_TAG.match(f[j][2]).group(0)).get("w:val") if j is not None else None
            jr, jp = _primeiro(f, "w:rPr"), _primeiro(f, "w:pPr")
            est["estilos"][sid] = {
                "tipo": tipo, "base": base,
                "r": _props_r(_filhos(f[jr][2]), tema) if jr is not None else {},
                "p": _props_p(_filhos(f[jp][2]), tema) if jp is not None else {},
            }
            if a.get("w:default") in ("1", "true", "on") and tipo not in est["padrao"]:
                est["padrao"][tipo] = sid
    if "paragraph" not in est["padrao"] and est["estilos"].get("Normal", {}).get("tipo") == "paragraph":
        est["padrao"]["paragraph"] = "Normal"
    return est


def _cadeia(est, sid, tipo):
    if sid not in est["estilos"] or est["estilos"][sid]["tipo"] != tipo:
        sid = est["padrao"].get(tipo)
    ids = []
    while sid and sid in est["estilos"] and est["estilos"][sid]["tipo"] == tipo and sid not in ids and len(ids) < 20:
        ids.append(sid)
        sid = est["estilos"][sid]["base"]
    return [est["estilos"][s] for s in reversed(ids)]


def _efetivo_r(est, pstyle, rstyle, direto):
    ps, cs = {}, {}
    for st in _cadeia(est, pstyle, "paragraph"):
        ps = _sobrepor_r(ps, st["r"])
    for st in _cadeia(est, rstyle, "character"):
        cs = _sobrepor_r(cs, st["r"])
    ef = _sobrepor_r(_sobrepor_r(est["dd_r"], ps), cs)
    for t in TOGGLES:


        if t in est["dd_r"] or t in ps or t in cs:
            v = bool(est["dd_r"].get(t))
            if ps.get(t):
                v = not v
            if cs.get(t):
                v = not v
            ef[t] = v
    return _sobrepor_r(ef, direto)


def _efetivo_p(est, pstyle, direto):
    ef = dict(est["dd_p"])
    for st in _cadeia(est, pstyle, "paragraph"):
        ef = _sobrepor_p(ef, st["p"])
    return _sobrepor_p(ef, direto)


def _indice(nome, ordem):
    local = _local(nome)
    if local in ordem:
        return ordem.index(local)
    return 999 if local in ("rPrChange", "pPrChange") else 998


def _inserir(segs, novos, ordem):
    """Filhos mantidos + novos na posição do esquema (CT_RPr / CT_PPr exigem ordem)."""
    out = list(segs)
    for nome, bruto in novos:
        i = _indice("w:" + nome, ordem)
        j = next((k for k, sg in enumerate(out) if sg[0] == "e" and _indice(sg[1], ordem) > i), len(out))
        out.insert(j, ("e", "w:" + nome, bruto))
    return "".join(sg[1] if sg[0] == "t" else sg[2] for sg in out)


def _xml_rpr(filhos, ef):
    novos = []
    f = ef.get("fontes", {})
    at = "".join(f' w:{s}="{_q(f[s])}"' for s in ("ascii", "hAnsi", "eastAsia", "cs") if f.get(s))
    if at:
        novos.append(("rFonts", f"<w:rFonts{at}/>"))
    novos.extend((t, f"<w:{t}/>") for t in TOGGLES if ef.get(t))
    novos.append(("color", f'<w:color w:val="{ef.get("cor", "auto")}"/>'))
    if ef.get("espaco"):
        novos.append(("spacing", f'<w:spacing w:val="{ef["espaco"]}"/>'))
    novos.append(("sz", f'<w:sz w:val="{ef.get("sz", 20)}"/>'))
    if "szCs" in ef:
        novos.append(("szCs", f'<w:szCs w:val="{ef["szCs"]}"/>'))
    mantidos = [sg for sg in filhos if not (sg[0] == "e" and _local(sg[1]) in COBERTOS_RPR)]
    return "<w:rPr>" + _inserir(mantidos, novos, ORDEM_RPR) + "</w:rPr>"


def _xml_ppr(filhos, ef, marca):
    novos = []
    bordas = ef.get("bordas", {})
    lados = ""
    for lado in LADOS_BORDA:
        b = bordas.get(lado)
        if b and b.get("val") not in (None, "nil", "none"):
            lados += f"<w:{lado}" + "".join(f' w:{k}="{_q(b[k])}"' for k in ATRIB_BORDA if k in b) + "/>"
    if lados:
        novos.append(("pBdr", f"<w:pBdr>{lados}</w:pBdr>"))
    tabs = ef.get("tabs", [])
    if tabs:
        novos.append(("tabs", "<w:tabs>" + "".join(
            f'<w:tab w:val="{val}"' + (f' w:leader="{lid}"' if lid else "") + f' w:pos="{pos}"/>'
            for pos, val, lid in tabs) + "</w:tabs>"))
    esp = {"before": "0", "after": "0", "line": "240", "lineRule": "auto", **ef.get("espaco", {})}
    novos.append(("spacing", "<w:spacing" + "".join(f' w:{k}="{_q(esp[k])}"' for k in ATRIB_ESPACO if k in esp) + "/>"))
    rec = {"left": "0", "right": "0", **ef.get("recuo", {})}
    if not any(k in rec for k in ("hanging", "hangingChars", "firstLine", "firstLineChars")):
        rec["firstLine"] = "0"
    novos.append(("ind", "<w:ind" + "".join(f' w:{k}="{_q(rec[k])}"' for k in ATRIB_RECUO if k in rec) + "/>"))
    novos.append(("jc", f'<w:jc w:val="{_q(ef.get("jc", "left"))}"/>'))
    novos.append(("rPr", marca))
    mantidos = [sg for sg in filhos if not (sg[0] == "e" and _local(sg[1]) in COBERTOS_PPR)]
    return "<w:pPr>" + _inserir(mantidos, novos, ORDEM_PPR) + "</w:pPr>"


def _val_filho(segs, nome):
    k = _primeiro(segs, nome)
    return _atribs(RX_TAG.match(segs[k][2]).group(0)).get("w:val") if k is not None else None


def _reescrever(s, est, pstyle=None):
    out = []
    for sg in _segmentos(s):
        if sg[0] == "t":
            out.append(sg[1])
        elif sg[1] == "w:p":
            out.append(_reescrever_p(sg[2], est))
        elif sg[2].endswith("/>") and RX_TAG.match(sg[2]).end() == len(sg[2]):
            out.append(sg[2])
        elif sg[1] == "w:r":
            out.append(_reescrever_r(sg[2], est, pstyle))
        else:
            abre, miolo, fecha = _partir(sg[2])
            out.append(abre + _reescrever(miolo, est, pstyle) + fecha)
    return "".join(out)


def _reescrever_p(bruto, est):
    abre, miolo, fecha = _partir(bruto)
    if not fecha:
        abre, fecha = abre[:-2].rstrip() + ">", "</w:p>"
    segs = _segmentos(miolo)
    k = _primeiro(segs, "w:pPr")
    filhos = _filhos(segs[k][2]) if k is not None else []
    pstyle = _val_filho(filhos, "w:pStyle")
    km = _primeiro(filhos, "w:rPr")
    fm = _filhos(filhos[km][2]) if km is not None else []
    marca = _xml_rpr(fm, _efetivo_r(est, pstyle, _val_filho(fm, "w:rStyle"), _props_r(fm, est["tema"])))
    ppr = _xml_ppr(filhos, _efetivo_p(est, pstyle, _props_p(filhos, est["tema"])), marca)
    resto = "".join(sg[1] if sg[0] == "t" else (ppr if i == k else _reescrever(sg[2], est, pstyle))
                    for i, sg in enumerate(segs))
    return abre + (resto if k is not None else ppr + resto) + fecha


def _reescrever_r(bruto, est, pstyle):
    abre, miolo, fecha = _partir(bruto)
    segs = _segmentos(miolo)
    k = _primeiro(segs, "w:rPr")
    filhos = _filhos(segs[k][2]) if k is not None else []
    rpr = _xml_rpr(filhos, _efetivo_r(est, pstyle, _val_filho(filhos, "w:rStyle"), _props_r(filhos, est["tema"])))
    resto = "".join(sg[1] if sg[0] == "t" else (rpr if i == k else _reescrever(sg[2], est, pstyle))
                    for i, sg in enumerate(segs))
    return abre + (resto if k is not None else rpr + resto) + fecha


def materializar_timbrado(xml, est):
    """Cabeçalho/rodapé com a formatação efetiva gravada em cada parágrafo e run."""
    return _reescrever(xml, est)


def _estilos_do_modelo(z):
    """A cascata do modelo, ou None quando ele não tem `styles.xml` (nada a materializar)."""
    if "word/styles.xml" not in z.dsr_indice:
        return None
    try:
        estilos = _ler(z, "word/styles.xml", LIMITE_PARTE).decode("utf-8", errors="replace")
        tema = (_ler(z, "word/theme/theme1.xml", LIMITE_PARTE).decode("utf-8", errors="replace")
                if "word/theme/theme1.xml" in z.dsr_indice else "")
    except Recusa:


        return None
    return ler_estilos_do_modelo(estilos, tema)


def extrair_timbrado(z):
    """(partes: dict nome -> bytes, previa: dict). Mesma seleção do cliente_perfil.js."""
    nomes = list(z.dsr_indice)
    partes = {}
    previa = {"cabecalho": [], "rodape": [], "imagens": 0}
    midias = set()
    est = _estilos_do_modelo(z)
    for nome in nomes:
        m = RX_PARTE.match(nome)
        if not m:
            continue
        dados = _ler(z, nome, LIMITE_PARTE)
        if est is not None:

            bruto = dados.decode("utf-8", errors="replace")
            novo = materializar_timbrado(bruto, est)
            if novo != bruto:
                dados = novo.encode("utf-8")




        dados, _n = PA.normalizar_hifens_timbrado(dados)
        xml = dados.decode("utf-8", errors="replace")
        partes[nome] = dados
        previa["cabecalho" if m.group(1) == "header" else "rodape"].extend(texto_de(xml))
        rels = f"word/_rels/{m.group(1)}{m.group(2)}.xml.rels"
        if rels in nomes:
            rx = _ler(z, rels, LIMITE_PARTE)
            partes[rels] = rx
            for alvo in RX_ALVO_MIDIA.findall(rx.decode("utf-8", errors="replace")):
                midias.add(f"word/{alvo}")
    for nome in nomes:
        if nome in midias:
            partes[nome] = _ler(z, nome, LIMITE_PACOTE)
            previa["imagens"] += 1
    for linha in previa["cabecalho"] + previa["rodape"]:
        for rotulo, rx in FAROS:
            if rx.search(linha):
                raise Recusa(f"O cabeçalho ou o rodapé desse arquivo tem {rotulo}. Ele não pode sair do computador. "
                             "Envie o modelo em branco do escritório, sem dados de caso.")
    return partes, previa




def _w(el, attr):
    return None if el is None else el.get(f"{{{W}}}{attr}")


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _fontes_do_tema(z):
    if "word/theme/theme1.xml" not in z.dsr_indice:
        return {}
    try:
        raiz = ET.fromstring(_ler(z, "word/theme/theme1.xml", LIMITE_PARTE))
    except ET.ParseError:
        return {}
    out = {}
    for tipo, chave in (("minorFont", "minor"), ("majorFont", "major")):
        latin = raiz.find(f".//a:{tipo}/a:latin", NS)
        if latin is not None and latin.get("typeface"):
            out[chave] = latin.get("typeface")
    return out


def _fonte(rfonts, tema):
    if rfonts is None:
        return None
    nome = _w(rfonts, "ascii") or _w(rfonts, "hAnsi")
    if nome:
        return nome
    ref = _w(rfonts, "asciiTheme") or _w(rfonts, "hAnsiTheme") or ""
    if ref.startswith("minor"):
        return tema.get("minor")
    if ref.startswith("major"):
        return tema.get("major")
    return None


def _aplicar(ppr, rpr, alvo, tema):
    """Sobrepõe em `alvo` o que ppr/rpr dizem (docDefaults primeiro, depois o estilo)."""
    if rpr is not None:
        f = _fonte(rpr.find("w:rFonts", NS), tema)
        if f:
            alvo["fonte"] = f
        sz = _int(_w(rpr.find("w:sz", NS), "val"))
        if sz:
            alvo["meio_pt"] = sz
        cor = _w(rpr.find("w:color", NS), "val")
        if cor and re.fullmatch(r"[0-9A-Fa-f]{6}", cor):
            alvo["cor"] = cor.upper()
    if ppr is not None:
        esp = ppr.find("w:spacing", NS)
        if esp is not None:
            regra = _w(esp, "lineRule") or "auto"
            if _w(esp, "line") and regra == "auto":
                alvo["entrelinha"] = _int(_w(esp, "line"))
            for k in ("before", "after"):
                if _w(esp, k) is not None:
                    alvo["antes" if k == "before" else "depois"] = _int(_w(esp, k))
        ind = ppr.find("w:ind", NS)
        if ind is not None and _w(ind, "firstLine") is not None:
            alvo["recuo_primeira"] = _int(_w(ind, "firstLine"))
        jc = _w(ppr.find("w:jc", NS), "val")
        if jc:
            alvo["alinhamento"] = {"start": "left", "end": "right"}.get(jc, jc)


def _estilos(z, tema):
    if "word/styles.xml" not in z.dsr_indice:
        return {}, None
    try:
        raiz = ET.fromstring(_ler(z, "word/styles.xml", LIMITE_PARTE))
    except ET.ParseError:
        return {}, None
    corpo = {}
    dd = raiz.find("w:docDefaults", NS)
    if dd is not None:
        _aplicar(dd.find("w:pPrDefault/w:pPr", NS), dd.find("w:rPrDefault/w:rPr", NS), corpo, tema)
    normal = titulo = None
    for st in raiz.findall("w:style", NS):
        if _w(st, "type") != "paragraph":
            continue
        nome = (_w(st.find("w:name", NS), "val") or "").lower()
        sid = _w(st, "styleId") or ""
        if (_w(st, "default") in ("1", "true") or sid == "Normal") and normal is None:
            normal = st
        if nome == "heading 1" or sid in ("Heading1", "Ttulo1"):
            titulo = st
    if normal is not None:
        _aplicar(normal.find("w:pPr", NS), normal.find("w:rPr", NS), corpo, tema)
    fonte_titulo = _fonte(titulo.find("w:rPr/w:rFonts", NS), tema) if titulo is not None else None
    return corpo, fonte_titulo


def _sectpr(z):
    """Página e margens do ÚLTIMO w:sectPr. O document.xml é lido e descartado aqui."""
    if "word/document.xml" not in z.dsr_indice:
        return {}, {}
    doc = _ler(z, "word/document.xml", LIMITE_DOCUMENTO).decode("utf-8", errors="replace")
    blocos = re.findall(r"<w:sectPr\b[\s\S]*?</w:sectPr>", doc)
    del doc
    if not blocos:
        return {}, {}
    s = blocos[-1]
    attrs = lambda tag: dict(re.findall(r'w:(\w+)="([^"]*)"', (re.search(rf"<w:{tag}\b([^>]*)>", s) or [None, ""])[1]))
    pg, mg = attrs("pgSz"), attrs("pgMar")
    pagina = {}
    if _int(pg.get("w")) is not None:
        pagina["largura"] = _int(pg.get("w"))
    if _int(pg.get("h")) is not None:
        pagina["altura"] = _int(pg.get("h"))
    if pagina:
        pagina["orientacao"] = "paisagem" if pg.get("orient") == "landscape" else "retrato"
    margens = {}
    for de, para in (("top", "sup"), ("bottom", "inf"), ("left", "esq"), ("right", "dir"), ("header", "cabecalho"), ("footer", "rodape")):
        if _int(mg.get(de)) is not None:
            margens[para] = abs(_int(mg.get(de))) if de in ("top", "bottom") else _int(mg.get(de))
    return pagina, margens


def extrair_layout(z):
    '(layout: dict pronto para layout.json, fora: list de (campo, valor)).'



    tema = _fontes_do_tema(z)
    corpo_lido, fonte_titulo = _estilos(z, tema)
    pagina, margens = _sectpr(z)
    bruto = {
        "pagina": pagina,
        "margens": margens,
        "paragrafo": {k: corpo_lido[k] for k in ("entrelinha", "antes", "depois", "recuo_primeira", "alinhamento") if corpo_lido.get(k) is not None},
        "titulos": {"fonte": fonte_titulo} if fonte_titulo else {},
    }
    layout, fora = {"versao": 1}, []
    for bloco, campos in bruto.items():
        aceitos = {}
        for k, v in campos.items():
            if PA.validar_layout({"versao": 1, bloco: {k: v}}) is None:
                aceitos[k] = v
            else:
                fora.append((f"{bloco}.{k}", v))
        if aceitos:
            layout[bloco] = aceitos
    if "pagina" in layout and PA.validar_layout({"versao": 1, "pagina": layout["pagina"]}) is not None:
        fora.append(("pagina.orientacao", layout.pop("pagina")))
    corpo = {}
    if corpo_lido.get("fonte"):
        if PA._RX_FONTE.fullmatch(corpo_lido["fonte"]):
            corpo["fonte"] = corpo_lido["fonte"]
        else:
            fora.append(("corpo.fonte", corpo_lido["fonte"]))
    if corpo_lido.get("meio_pt"):
        pt = int(round(corpo_lido["meio_pt"] / 2))
        if FAIXA_TAMANHO_PT[0] <= pt <= FAIXA_TAMANHO_PT[1]:
            corpo["tamanho_pt"] = pt
        else:
            fora.append(("corpo.tamanho_pt", pt))
    if corpo_lido.get("cor"):
        corpo["cor_hex"] = corpo_lido["cor"]
    if corpo:
        layout["corpo"] = corpo
    return layout, fora




def montar(docx, assinatura=None, brasao=None):
    'Lê tudo e devolve (dados, partes, previa): o zip pronto para enviar, as partes por nome'

    try:
        z = zipfile.ZipFile(docx)
    except (OSError, zipfile.BadZipFile):
        raise Recusa("Não foi possível ler esse arquivo. Confira se é um documento Word (.docx) e tente de novo.")
    with z:
        _indexar(z)
        if any(n.endswith("vbaProject.bin") for n in z.dsr_indice):
            raise Recusa("Esse arquivo tem programação embutida e não pode ser usado. Salve como .docx comum e tente de novo.")
        partes, previa = extrair_timbrado(z)
        layout, fora = extrair_layout(z)
    previa["layout"], previa["fora"] = layout, fora
    for rotulo, caminho in (("assinatura", assinatura), ("brasao", brasao)):
        if caminho:
            tipo, b = ler_imagem(caminho, "assinatura" if rotulo == "assinatura" else "brasão")
            partes[f"{rotulo}.{tipo}"] = b
            previa[rotulo] = {"tipo": tipo, "pixels": dimensoes_imagem(b)}
    if len(layout) > 1:
        partes["layout.json"] = json.dumps(layout, ensure_ascii=False, sort_keys=True).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as saida:
        for nome in sorted(partes):
            saida.writestr(nome, partes[nome])
    dados = buf.getvalue()
    if len(dados) > LIMITE_PACOTE:
        raise Recusa("O timbrado desse arquivo é grande demais. Use imagens menores no cabeçalho e no rodapé.")
    if not partes:
        raise Recusa("Esse arquivo não tem cabeçalho, rodapé nem medidas de página aproveitáveis. Envie o modelo que o escritório usa.")
    return dados, partes, previa


def _cm(twips):
    return f"{twips / 567:.1f}".replace(".", ",") + " cm"


ROTULO_CAMPO = {
    "margens.sup": "margem superior", "margens.inf": "margem inferior", "margens.esq": "margem esquerda",
    "margens.dir": "margem direita", "margens.cabecalho": "distância do cabeçalho", "margens.rodape": "distância do rodapé",
    "pagina.largura": "largura da página", "pagina.altura": "altura da página", "pagina.orientacao": "orientação da página",
    "paragrafo.entrelinha": "entrelinha", "paragrafo.antes": "espaço antes do parágrafo",
    "paragrafo.depois": "espaço depois do parágrafo", "paragrafo.recuo_primeira": "recuo da primeira linha",
    "paragrafo.alinhamento": "alinhamento", "titulos.fonte": "fonte dos títulos",
    "corpo.fonte": "fonte do texto", "corpo.tamanho_pt": "tamanho da letra",
}
ALINHAMENTO = {"left": "à esquerda", "both": "justificado", "center": "centralizado", "right": "à direita"}


def texto_previa(previa):
    lay = previa["layout"]
    l = ["Prévia do papel do escritório (nada foi enviado ainda)."]
    l.append(f"- Cabeçalho · {' / '.join(previa['cabecalho']) or 'sem texto'}")
    l.append(f"- Rodapé · {' / '.join(previa['rodape']) or 'sem texto'}")
    l.append(f"- Imagens no cabeçalho e no rodapé · {previa['imagens']}")
    for chave, nome in (("assinatura", "Assinatura"), ("brasao", "Brasão")):
        info = previa.get(chave)
        l.append(f"- {nome} · " + (f"{info['tipo'].upper()}" + (f", {info['pixels'][0]} x {info['pixels'][1]} pixels" if info["pixels"] else "") if info else "não enviada"))
    c = lay.get("corpo", {})
    if c:
        l.append("- Texto · " + ", ".join(x for x in (c.get("fonte"), f"{c['tamanho_pt']} pt" if c.get("tamanho_pt") else None,
                                                     f"cor {c['cor_hex']}" if c.get("cor_hex") else None) if x))
    m = lay.get("margens", {})
    if m:
        partes = [f"{ROTULO_CAMPO['margens.' + k].replace('margem ', '')} {_cm(v)}" for k, v in m.items() if k in ("sup", "inf", "esq", "dir")]
        if partes:
            l.append("- Margens · " + ", ".join(partes))
    p = lay.get("pagina")
    if p:
        l.append(f"- Página · {_cm(p['largura'])} x {_cm(p['altura'])}, {p['orientacao']}")
    pa = lay.get("paragrafo", {})
    if pa:
        itens = []
        if pa.get("entrelinha"):
            itens.append(f"entrelinha {pa['entrelinha'] / 240:.2f}".rstrip("0").rstrip(".").replace(".", ","))
        if pa.get("recuo_primeira"):
            itens.append(f"recuo da primeira linha {_cm(pa['recuo_primeira'])}")
        if pa.get("alinhamento"):
            itens.append(ALINHAMENTO.get(pa["alinhamento"], pa["alinhamento"]))
        if itens:
            l.append("- Parágrafo · " + ", ".join(itens))
    if lay.get("titulos"):
        l.append(f"- Fonte dos títulos · {lay['titulos']['fonte']}")
    if previa["fora"]:
        l.append("Fora do comum, confirme com o advogado antes de enviar · "
                 + "; ".join(f"{ROTULO_CAMPO.get(c, c)} {v}" for c, v in previa["fora"]))
    return "\n".join(l)


def enviar(url, dados):
    req = urllib.request.Request(url, data=dados, method="POST",
                                 headers={"content-type": "application/zip", "user-agent": "dsr-extrator/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "mensagem": f"O envio foi recusado (código {e.code}). Peça um novo endereço e tente de novo."}
    except (urllib.error.URLError, OSError, TimeoutError):
        return {"ok": False, "mensagem": "Não foi possível falar com o servidor agora. Tente de novo em instantes."}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Extrai do modelo Word só o papel do escritório e envia ao servidor.")
    ap.add_argument("--docx", required=True)
    ap.add_argument("--assinatura")
    ap.add_argument("--brasao")
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--previa", action="store_true")
    modo.add_argument("--enviar", metavar="ENDERECO")
    modo.add_argument("--listar-partes", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--ignorar-fora-da-faixa", action="store_true",
                    help="envia sem as medidas fora do comum (o advogado confirmou)")
    a = ap.parse_args(argv)
    try:
        dados, partes, previa = montar(a.docx, a.assinatura, a.brasao)
    except Recusa as e:
        print(f"ERRO: {e}")
        return 1
    if a.listar_partes:

        print(json.dumps({"partes": {n: hashlib.sha256(b).hexdigest() for n, b in partes.items()},
                          "layout": previa["layout"], "fora": [c for c, _ in previa["fora"]]}, ensure_ascii=False))
        return 0
    print(texto_previa(previa))
    if a.previa:
        return 0
    if previa["fora"] and not a.ignorar_fora_da_faixa:
        print("ERRO: Há medidas fora do comum. Confirme com o advogado; se ele concordar em seguir sem elas, "
              "rode de novo com --ignorar-fora-da-faixa.")
        return 1
    r = enviar(a.enviar, dados)
    if not r.get("ok"):
        campo = f" ({ROTULO_CAMPO.get(r.get('campo'), r.get('campo'))})" if r.get("campo") else ""
        print(f"ERRO: {r.get('mensagem') or 'O envio foi recusado.'}{campo}")
        return 1
    pv = r.get("previa", {})
    papel = "o timbrado do próprio escritório" if pv.get("timbrado") == "proprio" else "o timbrado gerado pelo plugin, com as medidas do escritório"
    print(f"Enviado e gravado. As próximas peças saem com {papel}"
          + (", com a assinatura" if pv.get("assinatura") else "") + (" e o brasão" if pv.get("brasao") else "") + ".")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERRO: falha inesperada ao ler o arquivo ({type(e).__name__}). Tente de novo; se repetir, siga sem o modelo.")
        sys.exit(1)
