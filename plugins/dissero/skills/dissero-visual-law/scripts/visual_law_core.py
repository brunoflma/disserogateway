# -*- coding: utf-8 -*-
'visual_law_core.py — Núcleo do padrão Visual Law'



















import hashlib
import os
import tempfile
import re
import shutil
import zipfile



PEDIDO_ITEM_RX = re.compile(r"^(?:\d{1,2}[.)]\s|\+\s|[a-z][.)]\s|\([a-z0-9]{1,3}\)\s|[•–-]\s)")




INK         = "1A1A1A"
WHITE       = "FFFFFF"


W_FULL  = 9026
W_JURIS = 9018



BODY_PPR = ('<w:pPr><w:keepLines/><w:spacing w:after="140" w:line="276" w:lineRule="auto"/>'
            '<w:ind w:firstLine="708"/><w:jc w:val="both"/></w:pPr>')
BODY_PPR_NOIND = ('<w:pPr><w:keepLines/><w:spacing w:after="140" w:line="276" w:lineRule="auto"/>'
                  '<w:jc w:val="both"/></w:pPr>')















_LAYOUT = None


def definir_layout(perfil):
    """Liga o layout do perfil para a próxima montagem. Sem layout válido, desliga."""
    global _LAYOUT
    _LAYOUT = None
    try:
        import perfil_advogado as _pa
        bruto = _pa._get(perfil, "identidade_visual.layout") if isinstance(perfil, dict) else None
        if bruto is not None and _pa.validar_layout(bruto) is None:
            _LAYOUT = _pa.layout(perfil)
    except Exception:
        _LAYOUT = None
    return _LAYOUT




_TEMA = None


def definir_tema(perfil):
    """Liga o tema do perfil para a próxima montagem. Sem tema válido, usa o padrão."""
    global _TEMA
    import tema_visual as _tv
    _TEMA = _tv.tema_do_perfil(perfil)
    return _TEMA


def _tema():
    """O tema em vigor. Nunca devolve None — construtor não precisa saber se foi definido."""
    if _TEMA is not None:
        return _TEMA
    import tema_visual as _tv
    return _tv.PADRAO


def _casca_argumento(largura_barra=28):
    """Casca das caixas da família do argumento, conforme o tema em vigor."""
    t = _tema()
    fichas = t["fichas"]
    if t["elementos"]["argumento"] == "preenchido":
        return dict(fill=fichas["argumento_fundo"],
                    left_bar=(largura_barra, fichas["argumento_barra"]))

    return dict(fill=None, box_border=(t["contorno"]["sz"], fichas["argumento_barra"]))


def _body_ppr(indent=True):
    """pPr do parágrafo de corpo: o canônico Dissero, ou o do escritório quando houver."""
    par = (_LAYOUT or {}).get("paragrafo") or {}
    if not par:
        return BODY_PPR if indent else BODY_PPR_NOIND
    antes = par.get("antes")
    sp = ("<w:spacing" + (f' w:before="{antes}"' if antes is not None else "")
          + f' w:after="{par.get("depois", 140)}" w:line="{par.get("entrelinha", 276)}" w:lineRule="auto"/>')
    recuo = par.get("recuo_primeira", 708)
    ind = f'<w:ind w:firstLine="{recuo}"/>' if indent and recuo else ""
    return f'<w:pPr><w:keepLines/>{sp}{ind}<w:jc w:val="{par.get("alinhamento", "both")}"/></w:pPr>'


def _com_fonte_de_titulo(xml):
    """Põe a fonte dos títulos do escritório em todo run do componente de título."""
    fonte = ((_LAYOUT or {}).get("titulos") or {}).get("fonte")
    if not fonte:
        return xml
    rf = f'<w:rFonts w:ascii="{fonte}" w:hAnsi="{fonte}" w:cs="{fonte}"/>'
    return re.sub(r"<w:r>(<w:rPr>)?", lambda m: f"<w:r><w:rPr>{rf}" + ("" if m.group(1) else "</w:rPr>"), xml)


def _area_util():
    lay = _LAYOUT or {}
    pg, mg = lay.get("pagina") or {}, lay.get("margens") or {}
    return pg.get("largura", 11906) - mg.get("esq", 1440) - mg.get("dir", 1440)


def _pagina_no_sectpr(sect):
    """Troca pgSz e pgMar do sectPr pelos do layout, preservando o resto (refs, gutter)."""
    pg, mg = _LAYOUT["pagina"], _LAYOUT["margens"]
    orient = ' w:orient="landscape"' if pg.get("orientacao") == "paisagem" else ""
    sect = re.sub(r"<w:pgSz\b[^>]*/>", f'<w:pgSz w:w="{pg["largura"]}" w:h="{pg["altura"]}"{orient}/>', sect, count=1)

    def margens(m):
        attrs = dict(re.findall(r'w:(\w+)="([^"]*)"', m.group(0)))
        for de, para in (("top", "sup"), ("right", "dir"), ("bottom", "inf"), ("left", "esq"),
                         ("header", "cabecalho"), ("footer", "rodape")):
            attrs[de] = str(mg[para])
        attrs.setdefault("gutter", "0")
        ordem = ["top", "right", "bottom", "left", "header", "footer", "gutter"]
        return "<w:pgMar " + " ".join(f'w:{k}="{attrs[k]}"' for k in ordem + [k for k in attrs if k not in ordem]) + "/>"
    return re.sub(r"<w:pgMar\b[^>]*/>", margens, sect, count=1)


def _escalar_tabelas(doc, area):
    'Caixas Dissero (largura canônica W_FULL ou W_JURIS) passam a caber na área útil do'



    if area == W_FULL:
        return doc
    fator = area / W_FULL
    saida, i, n = [], 0, len(doc)
    while True:
        ini = doc.find("<w:tbl>", i)
        if ini < 0:
            saida.append(doc[i:])
            break
        prof, j = 0, ini
        while j < n:
            a, f = doc.find("<w:tbl>", j), doc.find("</w:tbl>", j)
            if a != -1 and a < f:
                prof, j = prof + 1, a + 7
            else:
                prof, j = prof - 1, f + 8
                if prof == 0:
                    break
        tabela = doc[ini:j]
        m = re.search(r'<w:tblW w:w="(\d+)" w:type="dxa"/>', tabela)
        if m and int(m.group(1)) in (W_FULL, W_JURIS):
            tabela = re.sub(r'(<w:(?:tblW|gridCol|tcW) w:w=")(\d+)(")',
                            lambda k: f"{k.group(1)}{round(int(k.group(2)) * fator)}{k.group(3)}", tabela)
        saida.append(doc[i:ini])
        saida.append(tabela)
        i = j
    return "".join(saida)


def _ajustar_documento_ao_layout(work_dir):
    """Página, margens e largura das caixas no document.xml. Só age com layout definido."""
    if _LAYOUT is None:
        return
    p = os.path.join(work_dir, "word", "document.xml")
    if not os.path.isfile(p):
        return
    with open(p, encoding="utf-8") as f:
        doc = f.read()
    doc = re.sub(r"<w:sectPr\b.*?</w:sectPr>", lambda m: _pagina_no_sectpr(m.group(0)), doc, flags=re.DOTALL)
    doc = _escalar_tabelas(doc, _area_util())
    with open(p, "w", encoding="utf-8") as f:
        f.write(doc)







_ESTILO_TEMPLATE_DSR = {"fonte": "Arial", "tamanho_meio_pt": 22, "cor": INK}


def aplicar_estilo_corpo(work_dir):
    'Fonte, tamanho e cor do texto do perfil (ou do tema em vigor) no rPrDefault do'





    est = _estilo_corpo()
    if est == _ESTILO_TEMPLATE_DSR:
        return
    p = os.path.join(work_dir, "word", "styles.xml")



    with open(p, encoding="utf-8", newline="") as f:
        st = f.read()
    novo = re.search(r"<w:rPrDefault>.*?</w:rPrDefault>", _docdefaults(est), re.DOTALL).group(0)
    if "<w:rPrDefault>" in st:
        st = re.sub(r"<w:rPrDefault>.*?</w:rPrDefault>", lambda _m: novo, st, count=1, flags=re.DOTALL)
    else:
        st = re.sub(r"(<w:styles[^>]*>)", lambda m: m.group(1) + _docdefaults(est), st, count=1)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(st)

















REL_IMAGEM = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
RID_ASSINATURA = "rIdDsrAssinatura"
RID_BRASAO = "rIdDsrBrasao"
LARGURA_ASSINATURA_EMU = 1800000
LARGURA_BRASAO_PT = 340
ALTURA_MAX_BRASAO_PT = 453
_ASSINATURA = None


def _normalizar_nome(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", re.sub(r"<[^>]+>|[*_]", "", str(s or "")))
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).casefold().split())


def _dimensoes(caminho):
    try:
        from extrair_papel import dimensoes_imagem
        with open(caminho, "rb") as fh:
            return dimensoes_imagem(fh.read(64 * 1024))
    except Exception:
        return None


def definir_assinatura(caminho, nome_subscritor):
    """Liga a assinatura para a próxima montagem, ou desliga (caminho None)."""
    global _ASSINATURA
    _ASSINATURA = None
    if not caminho or not nome_subscritor:
        return None
    dim = _dimensoes(caminho)
    if not dim or not dim[0] or not dim[1]:
        return None
    ext = caminho.rsplit(".", 1)[-1].lower()
    _ASSINATURA = {"caminho": caminho, "ext": "jpeg" if ext == "jpg" else ext,
                   "cx": LARGURA_ASSINATURA_EMU, "cy": round(LARGURA_ASSINATURA_EMU * dim[1] / dim[0]),
                   "nome": _normalizar_nome(nome_subscritor)}
    return _ASSINATURA


def _paragrafo_assinatura():
    a = _ASSINATURA
    desenho = (
        '<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{a["cx"]}" cy="{a["cy"]}"/><wp:docPr id="9001" name="Assinatura"/>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="9001" name="assinatura.{a["ext"]}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{RID_ASSINATURA}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{a["cx"]}" cy="{a["cy"]}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
        '</wp:inline></w:drawing></w:r>')
    return para([desenho], jc="center", keep_next=True)


def _garantir_default_de_imagem(work_dir, ext):
    ct_path = os.path.join(work_dir, "[Content_Types].xml")
    with open(ct_path, encoding="utf-8") as f:
        ct = f.read()
    tipo = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg"}[ext]
    if f'Extension="{ext}"' not in ct:
        ct = ct.replace("</Types>", f'<Default Extension="{ext}" ContentType="{tipo}"/></Types>')
        with open(ct_path, "w", encoding="utf-8") as f:
            f.write(ct)


def _acrescentar_relacao(rels_path, rid, alvo):
    if os.path.isfile(rels_path):
        with open(rels_path, encoding="utf-8") as f:
            rels = f.read()
    else:
        os.makedirs(os.path.dirname(rels_path), exist_ok=True)
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>')
    if f'Id="{rid}"' not in rels:
        rels = rels.replace("</Relationships>", f'<Relationship Id="{rid}" Type="{REL_IMAGEM}" Target="{alvo}"/></Relationships>')
        with open(rels_path, "w", encoding="utf-8") as f:
            f.write(rels)


def incorporar_assinatura(work_dir):
    """Copia a imagem e declara a relação -- só se o fecho de fato a usou."""
    if not _ASSINATURA:
        return False
    doc_path = os.path.join(work_dir, "word", "document.xml")
    with open(doc_path, encoding="utf-8") as f:
        if f'r:embed="{RID_ASSINATURA}"' not in f.read():
            return False
    alvo = f"media/dsr_assinatura.{_ASSINATURA['ext']}"
    os.makedirs(os.path.join(work_dir, "word", "media"), exist_ok=True)
    shutil.copy(_ASSINATURA["caminho"], os.path.join(work_dir, "word", alvo))
    _acrescentar_relacao(os.path.join(work_dir, "word", "_rels", "document.xml.rels"), RID_ASSINATURA, alvo)
    _garantir_default_de_imagem(work_dir, _ASSINATURA["ext"])
    return True


_NS_VML = {"v": "urn:schemas-microsoft-com:vml", "o": "urn:schemas-microsoft-com:office:office",
           "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def injetar_brasao(work_dir, caminho):
    "Marca-d'água do brasão em TODO cabeçalho presente (default, primeira página, par),"

    if not caminho:
        return 0
    dim = _dimensoes(caminho)
    if not dim or not dim[0] or not dim[1]:
        return 0
    larg, alt = LARGURA_BRASAO_PT, LARGURA_BRASAO_PT * dim[1] / dim[0]
    if alt > ALTURA_MAX_BRASAO_PT:
        larg, alt = larg * ALTURA_MAX_BRASAO_PT / alt, ALTURA_MAX_BRASAO_PT
    ext = caminho.rsplit(".", 1)[-1].lower()
    ext = "jpeg" if ext == "jpg" else ext
    word = os.path.join(work_dir, "word")
    cabecalhos = sorted(n for n in os.listdir(word) if re.fullmatch(r"header\d+\.xml", n))
    if not cabecalhos:
        return 0
    alvo = f"media/dsr_brasao.{ext}"
    os.makedirs(os.path.join(word, "media"), exist_ok=True)
    shutil.copy(caminho, os.path.join(word, alvo))
    _garantir_default_de_imagem(work_dir, ext)
    feitos = 0
    for i, nome in enumerate(cabecalhos, 1):
        p = os.path.join(word, nome)
        with open(p, encoding="utf-8") as f:
            xml = f.read()
        if f'r:id="{RID_BRASAO}"' in xml:
            continue
        raiz = re.search(r"<w:hdr\b[^>]*>", xml)
        if not raiz:
            continue
        faltam = "".join(f' xmlns:{k}="{v}"' for k, v in _NS_VML.items() if f"xmlns:{k}=" not in raiz.group(0))
        if faltam:
            xml = xml[:raiz.end() - 1] + faltam + xml[raiz.end() - 1:]
        forma = ('<w:r><w:rPr><w:noProof/></w:rPr><w:pict>'
                 f'<v:shape id="DsrBrasao{i}" o:spid="_x0000_s{2100 + i}" stroked="f" filled="f" '
                 f'style="position:absolute;margin-left:0;margin-top:0;width:{larg:.1f}pt;height:{alt:.1f}pt;'
                 'z-index:-251657216;mso-position-horizontal:center;mso-position-horizontal-relative:margin;'
                 'mso-position-vertical:center;mso-position-vertical-relative:margin" o:allowincell="f">'
                 f'<v:imagedata r:id="{RID_BRASAO}" o:title="brasao" gain="19661f" blacklevel="22938f"/>'
                 '</v:shape></w:pict></w:r>')
        fim = xml.find("</w:p>")
        if fim < 0:
            xml = xml.replace("</w:hdr>", f"<w:p>{forma}</w:p></w:hdr>", 1)
        else:
            xml = xml[:fim] + forma + xml[fim:]
        with open(p, "w", encoding="utf-8") as f:
            f.write(xml)
        _acrescentar_relacao(os.path.join(word, "_rels", f"{nome}.rels"), RID_BRASAO, alvo)
        feitos += 1
    return feitos


def dir_de_trabalho(prefixo="dsrvl_"):
    'Cria o diretorio de trabalho no temp DO SISTEMA (`tempfile`). Quem cria, remove.'





    return tempfile.mkdtemp(prefix=prefixo)


def _estilo_corpo():
    'Fonte, tamanho e cor do corpo: do perfil quando houver, do TEMA em vigor quando não.'






    tip = _tema().get("tipografia") or {}
    padrao = {"fonte": tip.get("fonte", "Arial"),
              "tamanho_meio_pt": tip.get("corpo_sz", 22),
              "cor": INK}
    try:
        import perfil_advogado as _pa
        perfil = _pa.carregar()
        if not perfil:
            return padrao
        fonte = _pa._get(perfil, "identidade_visual.fonte_corpo")
        if fonte:
            padrao["fonte"] = str(fonte)
        tam = _pa._get(perfil, "identidade_visual.tamanho_corpo_pt")
        if isinstance(tam, (int, float)) and 6 <= tam <= 24:
            padrao["tamanho_meio_pt"] = int(round(tam * 2))
        cor = (_pa._get(perfil, "identidade_visual.cor_texto_hex") or "").lstrip("#")
        if re.fullmatch(r"[0-9A-Fa-f]{6}", cor or ""):
            padrao["cor"] = cor.upper()
        return padrao
    except Exception:
        return padrao


def _docdefaults(est=None):
    est = est or _estilo_corpo()
    f, sz, cor = est["fonte"], est["tamanho_meio_pt"], est["cor"]
    return ('<w:docDefaults><w:rPrDefault><w:rPr>'
            f'<w:rFonts w:ascii="{f}" w:eastAsia="{f}" w:hAnsi="{f}" w:cs="{f}"/>'
            f'<w:color w:val="{cor}"/><w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
            '<w:lang w:val="pt-BR" w:eastAsia="pt-BR" w:bidi="ar-SA"/>'
            '</w:rPr></w:rPrDefault><w:pPrDefault/></w:docDefaults>')


SECTPR_CANON = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"'
                ' w:header="708" w:footer="708" w:gutter="0"/>'
                '<w:cols w:space="720"/><w:docGrid w:linePitch="360"/></w:sectPr>')

REL_HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
LINK_COLOR = "1155CC"

CT_HEADER = "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
CT_FOOTER = "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
REL_HEADER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
REL_FOOTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"

_HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.abspath(os.path.join(_HERE, "..", "assets"))





def xml_escape(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def straight_quotes(t):
    """Aspas sempre retas (regra transversal do padrão)."""
    return (t.replace("“", '"').replace("”", '"')
             .replace("‘", "'").replace("’", "'")
             .replace("«", '"').replace("»", '"'))


def attr_escape(t):
    'Escape para VALOR DE ATRIBUTO (Target de relationship). O `&` das URLs de'

    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))










LINKS_EXTERNOS = {}


URL_RX = re.compile(r"https?://[^\s<>\"'“”]+[^\s<>\"'“”.,;:!?)\]}]")



_SEP_URL = "/?&=._-#:;,+~%"




_MAX_SEM_QUEBRA = 14


def url_quebravel(url, cada=_MAX_SEM_QUEBRA):
    'URL com espaço de largura ZERO nos pontos de quebra — só no TEXTO EXIBIDO.'








    saida, desde = [], 0
    for ch in (url or ""):
        saida.append(ch)
        desde += 1
        if ch in _SEP_URL or desde >= cada:
            saida.append("​")
            desde = 0
    return "".join(saida)


def registrar_link(url):
    rid = "rIdDsrLink" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    LINKS_EXTERNOS[rid] = url
    return rid


def link_xml(url, runs_xml):
    """Envolve runs em <w:hyperlink> apontando para a URL (registrada no mapa)."""
    return (f'<w:hyperlink r:id="{registrar_link(url)}" w:history="1">'
            f'{"".join(runs_xml)}</w:hyperlink>')


def injetar_links(work_dir):
    'Grava em word/_rels/document.xml.rels os relationships externos registrados.'



    if not LINKS_EXTERNOS:
        return 0
    rels_path = os.path.join(work_dir, "word", "_rels", "document.xml.rels")
    with open(rels_path, encoding="utf-8") as f:
        rels = f.read()
    add = "".join(
        f'<Relationship Id="{rid}" Type="{REL_HYPERLINK}" '
        f'Target="{attr_escape(url)}" TargetMode="External"/>'
        for rid, url in sorted(LINKS_EXTERNOS.items()) if f'Id="{rid}"' not in rels)
    if not add:
        return 0
    rels = rels.replace("</Relationships>", add + "</Relationships>")
    with open(rels_path, "w", encoding="utf-8") as f:
        f.write(rels)
    return add.count("<Relationship ")





def run(text, b=False, i=False, color=None, sz=None, spacing=None,
        u=False, highlight=None, rstyle=None):
    '<w:r> com rPr mínimo (fonte/cor herdadas dos docDefaults).'



    rpr = ""
    if rstyle:
        rpr += f'<w:rStyle w:val="{rstyle}"/>'
    if b:
        rpr += "<w:b/><w:bCs/>"
    if i:
        rpr += "<w:i/><w:iCs/>"
    if color:
        rpr += f'<w:color w:val="{color}"/>'
    if spacing:
        rpr += f'<w:spacing w:val="{spacing}"/>'
    if sz:
        rpr += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    if highlight:
        rpr += f'<w:highlight w:val="{highlight}"/>'
    if u:
        rpr += '<w:u w:val="single"/>'
    rpr = f"<w:rPr>{rpr}</w:rPr>" if rpr else ""
    esc = xml_escape(text)
    ta = ' xml:space="preserve"' if text != text.strip() or not text else ""
    return f"<w:r>{rpr}<w:t{ta}>{esc}</w:t></w:r>"


def para(runs_xml, after=None, line=None, jc="both", first_line=None, rpr_mark=None, keep_next=False,
         before=None):
    '<w:p> genérico. rpr_mark: rPr de marca no pPr (parágrafos vazios).'







    sp = ""
    if after is not None or line is not None or before is not None:
        sp = "<w:spacing"
        if before is not None:
            sp += f' w:before="{before}"'
        if after is not None:
            sp += f' w:after="{after}"'
        if line is not None:
            sp += f' w:line="{line}" w:lineRule="auto"'
        sp += "/>"
    ind = f'<w:ind w:firstLine="{first_line}"/>' if first_line else ""
    mark = f"<w:rPr>{rpr_mark}</w:rPr>" if rpr_mark else ""
    kn = "<w:keepNext/>" if keep_next else ""
    return (f"<w:p><w:pPr>{kn}<w:keepLines/><w:widowControl/>{sp}{ind}"
            f"<w:jc w:val=\"{jc}\"/>{mark}</w:pPr>{''.join(runs_xml)}</w:p>")


def spacer(after=140, line=276, mark=4, keep_next=False):
    'Parágrafo separador do gabarito. Padrão: after=140, line=276,'










    sp = f'<w:spacing w:after="{after}"'
    if line:
        sp += f' w:line="{line}" w:lineRule="auto"'
    sp += "/>"
    rpr = (f'<w:rPr><w:sz w:val="{mark}"/><w:szCs w:val="{mark}"/></w:rPr>'
           if mark else "")
    kn = "<w:keepNext/>" if keep_next else ""
    return f'<w:p><w:pPr>{kn}{sp}<w:jc w:val="both"/>{rpr}</w:pPr></w:p>'





def _tbl(paras_xml, w=W_FULL, fill=None, left_bar=None,
         tcmar=(150, 200, 150, 200), borderless=False, can_split=False,
         top_bar=None, bottom_bar=None, box_border=None):
    "left_bar=(sz, color) → top/bottom/right 'none' FFFFFF; sem left_bar,"

















    borders = "".join(
        f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
    tblpr = (f'<w:tblPr><w:tblW w:w="{w}" w:type="dxa"/>'
             f"<w:tblBorders>{borders}</w:tblBorders>"
             '<w:tblCellMar><w:left w:w="10" w:type="dxa"/>'
             '<w:right w:w="10" w:type="dxa"/></w:tblCellMar>'
             '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1"'
             ' w:lastColumn="0" w:noHBand="0" w:noVBand="1"/></w:tblPr>')
    tcb = ""
    if borderless or box_border or left_bar or top_bar or bottom_bar:





        edges = {"top": None, "left": None, "bottom": None, "right": None}
        if box_border:
            edges["top"] = edges["left"] = edges["bottom"] = edges["right"] = box_border
        if left_bar:
            edges["left"] = left_bar
        if top_bar:
            edges["top"] = top_bar
        if bottom_bar:
            edges["bottom"] = bottom_bar

        def _edge_xml(side, bar):
            if bar:
                sz, color = bar
                return f'<w:{side} w:val="single" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            return f'<w:{side} w:val="none" w:sz="0" w:space="0" w:color="FFFFFF"/>'

        tcb = ('<w:tcBorders>'
               + "".join(_edge_xml(side, edges[side])
                         for side in ("top", "left", "bottom", "right"))
               + '</w:tcBorders>')
    shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
    t, l, b_, r = tcmar
    mar = (f'<w:tcMar><w:top w:w="{t}" w:type="dxa"/><w:left w:w="{l}" w:type="dxa"/>'
           f'<w:bottom w:w="{b_}" w:type="dxa"/><w:right w:w="{r}" w:type="dxa"/></w:tcMar>')

    trpr = "<w:trPr></w:trPr>" if can_split else "<w:trPr><w:cantSplit/></w:trPr>"
    return (f"<w:tbl>{tblpr}<w:tblGrid><w:gridCol w:w=\"{w}\"/></w:tblGrid>"
            f"<w:tr>{trpr}<w:tc><w:tcPr><w:tcW w:w=\"{w}\" w:type=\"dxa\"/>{tcb}{shd}{mar}</w:tcPr>"
            f"{''.join(paras_xml)}</w:tc></w:tr></w:tbl>")













MAX_CAIXA_ATOMICA = 1000

_T_RX = re.compile(r"<w:t[^>]*>([^<]*)</w:t>")


def _texto_visivel(paras_xml):
    'Caracteres de texto que a caixa realmente imprime — a medida de altura que temos'

    return sum(len(t) for p in paras_xml for t in _T_RX.findall(p))


def _pode_quebrar(paras_xml):
    return _texto_visivel(paras_xml) > MAX_CAIXA_ATOMICA




















_ROMANO_CAP = r"(?=[IVXL])L?X{0,3}(?:IX|IV|V?I{0,3})"
_ROMANO_CAP_QQ_CAIXA = r"(?=[IVXLivxl])[Ll]?[Xx]{0,3}(?:[Ii][Xx]|[Ii][Vv]|[Vv]?[Ii]{0,3})"
_ROTULO_SO_NUMERAL = re.compile(rf"^({_ROMANO_CAP}|\d+)\.?$")
_ROTULO_CAPITULO_NUMERAL = re.compile(
    rf"^(cap[íi]tulo )((?={_ROMANO_CAP_QQ_CAIXA}\.?$)[IVXLivxl]{{2,}}|\d{{2,}})\.?$", re.I)


def _normalizar_rotulo(eyebrow):
    m = _ROTULO_SO_NUMERAL.match(eyebrow.strip())
    return f"CAPÍTULO {m.group(1).upper()}" if m else eyebrow


def _runs_do_rotulo(eyebrow, cor, sz, spacing):
    rotulo = _normalizar_rotulo(eyebrow)
    m = _ROTULO_CAPITULO_NUMERAL.match(rotulo.strip())
    if not m:
        return [run(rotulo, b=True, color=cor, sz=sz, spacing=spacing)]
    return [run(m.group(1), b=True, color=cor, sz=sz, spacing=spacing),
            run(m.group(2).upper(), b=True, color=cor, sz=sz)]


def banner(title_runs, eyebrow=None):
    'Banner de capítulo/seção. eyebrow=None → só o título (peças não'

    tema = _tema()
    cap = tema["capitulo"]
    fichas = tema["fichas"]
    paras = []
    if eyebrow:
        mark = (f'<w:b/><w:bCs/><w:color w:val="{fichas["versalete"]}"/>'
                f'<w:spacing w:val="{cap["rotulo_spacing"]}"/>'
                f'<w:sz w:val="{cap["rotulo_sz"]}"/><w:szCs w:val="{cap["rotulo_sz"]}"/>')
        paras.append(para(_runs_do_rotulo(eyebrow, fichas["versalete"], cap["rotulo_sz"],
                                          cap["rotulo_spacing"]), after=40, rpr_mark=mark))
        paras.append('<w:p><w:pPr><w:spacing w:after="40"/><w:jc w:val="both"/>'
                     '<w:rPr><w:sz w:val="4"/><w:szCs w:val="4"/></w:rPr></w:pPr></w:p>')




    cor_titulo = WHITE if cap["variante"] == "preenchido" else fichas["tinta"]
    title = [run(t, b=True, i=i_, color=cor_titulo, sz=cap["titulo_sz"]) for t, _b, i_ in title_runs] \
        if isinstance(title_runs, list) else [run(title_runs, b=True, color=cor_titulo, sz=cap["titulo_sz"])]
    paras.append(para(title, keep_next=True))
    if cap["variante"] == "preenchido":
        return _com_fonte_de_titulo(_tbl(paras, w=W_FULL, fill=fichas["tinta"],
                                         tcmar=(200, 240, 200, 240)))


    return _com_fonte_de_titulo(_tbl(paras, w=W_FULL, fill=None,
                                     top_bar=(cap["filete_sup_sz"], fichas["acento"]),
                                     bottom_bar=(cap["filete_inf_sz"], fichas["acento"]),
                                     tcmar=(200, 240, 200, 240)))


def legend(label):
    """Legenda de subseção: 'N.x · Título'."""
    tema = _tema()
    fichas = tema["fichas"]
    runs_xml = [_seg_run(t, f | frozenset(("b",)), sz=tema["tipografia"]["legenda_sz"])
                for t, f in md_segments(label)]
    p = para(runs_xml, keep_next=True)
    if tema["elementos"]["legenda"] == "preenchido":
        casca = dict(fill=fichas["legenda"], left_bar=(30, fichas["tinta"]))
    else:




        casca = dict(fill=None, bottom_bar=(tema["capitulo"]["filete_inf_sz"], fichas["acento"]))
    return _com_fonte_de_titulo(_tbl([p], w=W_FULL, tcmar=(110, 200, 110, 200), **casca))


def title_box(title, subtitle=None):
    'Caixa de título da capa (peça/ação): célula com fundo fichas["legenda"] sob'



    tema = _tema()
    fichas = tema["fichas"]
    tip = tema["tipografia"]
    paras = []
    t_runs = []
    for t, f in md_segments(title):
        t_runs.append(run(t, b=True, i="i" in f, sz=tip["capa_titulo_sz"], spacing="20"))
    paras.append(para(t_runs, after=60 if subtitle else None, jc="center"))
    if subtitle:
        s_runs = [run(t, b="b" in f, i=True, color=fichas["capa_subtitulo"], sz=tip["capa_subtitulo_sz"])
                  for t, f in md_segments(subtitle)]
        paras.append(para(s_runs, jc="center"))
    if tema["elementos"]["capa"] == "preenchido":
        casca = dict(fill=fichas["legenda"], borderless=True)
    else:


        casca = dict(fill=None,
                     top_bar=(tema["capa"]["regua_sz"], fichas["acento"]),
                     bottom_bar=(tema["capa"]["regua_fina_sz"], fichas["acento"]))
    return _com_fonte_de_titulo(_tbl(paras, w=W_FULL, tcmar=(160, 200, 160, 200), **casca))


def _jc_de(runs_xml):
    'Parágrafo com URL NÃO é justificado.'




    return "left" if any("<w:hyperlink" in r for r in runs_xml) else "both"


def arg_box(paragraphs_runs):
    'Caixa de destaque/argumento. paragraphs_runs: lista de listas de'


    paras = []
    n = len(paragraphs_runs)
    for k, runs_xml in enumerate(paragraphs_runs):
        last = (k == n - 1)
        paras.append(para(runs_xml, after=None if last else 140, line=276,
                          jc=_jc_de(runs_xml)))
        if not last:
            paras.append('<w:p><w:pPr><w:spacing w:after="140" w:line="276"'
                         ' w:lineRule="auto"/><w:jc w:val="both"/>'
                         '<w:rPr><w:sz w:val="4"/><w:szCs w:val="4"/></w:rPr>'
                         '</w:pPr></w:p>')
    return _tbl(paras, w=W_FULL, can_split=_pode_quebrar(paras), **_casca_argumento())


def quote_box(items):
    'Caixa de transcrição literal. items: lista de tuplas:'







    paras = []
    n = len(items)
    for k, item in enumerate(items):
        kind = item[0]
        last = (k == n - 1)
        if kind == "sep":
            paras.append('<w:p><w:pPr><w:spacing w:after="60" w:line="276"'
                         ' w:lineRule="auto"/><w:jc w:val="both"/>'
                         '<w:rPr><w:i/><w:iCs/><w:sz w:val="4"/>'
                         '<w:szCs w:val="4"/></w:rPr></w:pPr></w:p>')
            continue
        text = item[1]
        if kind == "attr":
            runs_xml = [_seg_run(t, f | frozenset(("b",)), sz="21")
                        for t, f in md_segments(text)]
            if last:
                paras.append(para(runs_xml, after=140, line=276,
                                  rpr_mark="<w:b/><w:bCs/>"))
            else:
                paras.append(para(runs_xml, after=180,
                                  rpr_mark="<w:b/><w:bCs/><w:sz w:val=\"21\"/>"
                                           "<w:szCs w:val=\"21\"/>"))
                paras.append('<w:p><w:pPr><w:spacing w:after="180"/>'
                             '<w:jc w:val="both"/><w:rPr><w:sz w:val="4"/>'
                             '<w:szCs w:val="4"/></w:rPr></w:pPr></w:p>')
        else:
            paras.append(para(quote_para_runs(text), after=60, line=276,
                              rpr_mark="<w:i/><w:iCs/>"))
    return _tbl(paras, w=W_FULL, can_split=_pode_quebrar(paras), **_casca_argumento())





_CAB_SUJEIRA = ("confirmado", "parcial", "fonte:", "http")

def sanitizar_cab(linha):
    'Remove da identificação do julgado os segmentos de verificação interna'



    partes = [p.strip() for p in (linha or "").split("·")]
    ident = partes[0] if partes else ""
    ident = re.sub(r"\s+https?://\S+", "", ident).strip()
    resto = [p for p in partes[1:] if p and not any(s in p.lower() for s in _CAB_SUJEIRA)]
    juntos = [x for x in [ident] + resto if x]
    return " · ".join(juntos).strip()


def juris_box(items):
    'Caixa de jurisprudência. items: [(julgado, ementa), ...] onde ementa é'


    t = _tema()
    fichas = t["fichas"]
    paras = [para([run("JURISPRUDÊNCIA", b=True, color=fichas["juris_barra"],
                       sz=t["tipografia"]["versalete_sz"], spacing="80")], after=100)]

    seq = []
    for julgado, ementa in items:
        seq.append(("cab", julgado))
        if isinstance(ementa, str):
            ementa = [ementa] if ementa.strip() else []
        for em in ementa:
            if em and em.strip():
                seq.append(("em", em))
    for k, (tipo, texto) in enumerate(seq):
        last = (k == len(seq) - 1)
        prox_cab = (not last and seq[k + 1][0] == "cab")
        if tipo == "cab":


            texto = sanitizar_cab(texto)
            paras.append(para([_seg_run(t, f | {"b"}, sz="21")
                               for t, f in md_segments(texto)], after=30))
        else:



            em_runs = "".join(_seg_run(t, f, sz="21")
                              for t, f in md_segments(texto, autobold=False))
            if last:
                paras.append(f'<w:p><w:pPr><w:jc w:val="both"/></w:pPr>'
                             f'{em_runs}</w:p>')
            else:


                aft = 120 if prox_cab else 70
                mark = ('<w:i/><w:iCs/><w:sz w:val="21"/><w:szCs w:val="21"/>')
                paras.append(f'<w:p><w:pPr><w:spacing w:after="{aft}"/><w:jc w:val="both"/>'
                             f'<w:rPr>{mark}</w:rPr></w:pPr>{em_runs}</w:p>')
                if prox_cab:
                    paras.append('<w:p><w:pPr><w:spacing w:after="120"/><w:jc w:val="both"/>'
                                 '<w:rPr><w:sz w:val="4"/><w:szCs w:val="4"/></w:rPr></w:pPr></w:p>')
    if t["elementos"]["jurisprudencia"] == "preenchido":
        casca = dict(fill=fichas["juris_fundo"], left_bar=(24, fichas["juris_barra"]))
    else:
        casca = dict(fill=None, box_border=(t["contorno"]["sz"], fichas["juris_barra"]))
    return _tbl(paras, w=W_JURIS, **casca, can_split=_pode_quebrar(paras))





def _grid_tbl(rows, widths, header=False, header_fill=None,
              body_fill=None, left_bar=None, tcmar=(90, 140, 90, 140),
              box_border=None):
    'Tabela de grade (N colunas × M linhas). `rows`: lista de linhas; cada'






    t = _tema()
    if header_fill is None and header:
        header_fill = t["fichas"]["legenda"] if t["elementos"]["comparativa"] == "preenchido" else None
    total = sum(widths)
    borders = "".join(
        f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
    tblpr = (f'<w:tblPr><w:tblW w:w="{total}" w:type="dxa"/>'
             f"<w:tblBorders>{borders}</w:tblBorders>"
             '<w:tblCellMar><w:left w:w="80" w:type="dxa"/>'
             '<w:right w:w="80" w:type="dxa"/></w:tblCellMar>'
             '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1"'
             ' w:lastColumn="0" w:noHBand="0" w:noVBand="1"/></w:tblPr>')
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    t, l, b_, r = tcmar
    mar = (f'<w:tcMar><w:top w:w="{t}" w:type="dxa"/><w:left w:w="{l}" w:type="dxa"/>'
           f'<w:bottom w:w="{b_}" w:type="dxa"/><w:right w:w="{r}" w:type="dxa"/></w:tcMar>')
    trs = []
    for ri, row in enumerate(rows):
        is_head = header and ri == 0
        fill = header_fill if is_head else body_fill
        cells = []
        for ci, cell_xml in enumerate(row):
            w = widths[ci] if ci < len(widths) else widths[-1]
            shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
            tcb = ""
            if box_border:
                bsz, bcolor = box_border
                tcb = ('<w:tcBorders>'
                       + "".join(f'<w:{side} w:val="single" w:sz="{bsz}" w:space="0" w:color="{bcolor}"/>'
                                 for side in ("top", "left", "bottom", "right"))
                       + '</w:tcBorders>')
            if left_bar and ci == 0:
                bsz, bcolor = left_bar
                tcb = ('<w:tcBorders>'
                       f'<w:left w:val="single" w:sz="{bsz}" w:space="0" w:color="{bcolor}"/>'
                       '</w:tcBorders>')
            cells.append(f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{tcb}{shd}{mar}'
                         f'<w:vAlign w:val="center"/></w:tcPr>{cell_xml}</w:tc>')
        trs.append(f'<w:tr><w:trPr><w:cantSplit/>'
                   f'{"<w:tblHeader/>" if is_head else ""}</w:trPr>{"".join(cells)}</w:tr>')
    return f'<w:tbl>{tblpr}<w:tblGrid>{grid}</w:tblGrid>{"".join(trs)}</w:tbl>'


def _cell_para(runs_xml, jc="both", bold=False):
    'Parágrafo de célula: entrelinha 276, sem recuo. bold marca o pPr para'

    return para(runs_xml, line=276, jc=jc,
                rpr_mark="<w:b/><w:bCs/>" if bold else None)


def data_table(header, rows):
    'Tabela comparativa/relacional (Visual Law). `header`: lista de títulos de'



    ncol = len(header)
    if ncol == 0:
        return ""
    w = W_FULL // ncol
    widths = [w] * (ncol - 1) + [W_FULL - w * (ncol - 1)]
    grid_rows = [[_cell_para([_seg_run(t, f | {"b"}) for t, f in md_segments(h)], bold=True)
                  for h in header]]
    for row in rows:
        grid_rows.append([_cell_para(md_runs(row[ci] if ci < len(row) else ""))
                          for ci in range(ncol)])
    t = _tema(); fichas = t["fichas"]
    if t["elementos"]["comparativa"] == "preenchido":
        casca = dict(left_bar=(24, fichas["argumento_barra"]))
    else:
        casca = dict(box_border=(t["contorno"]["sz"], fichas["argumento_barra"]))
    return _grid_tbl(grid_rows, widths, header=True, **casca)


def timeline_box(entries):
    'Linha do tempo (Visual Law). `entries`: lista de (data, evento). Duas'


    if not entries:
        return ""
    w_data = 1800
    widths = [w_data, W_FULL - w_data]
    rows = [[_cell_para([_seg_run(t, f | {"b"}) for t, f in md_segments(d)], bold=True),
             _cell_para(md_runs(ev))] for d, ev in entries]
    t = _tema(); fichas = t["fichas"]
    if t["elementos"]["comparativa"] == "preenchido":
        casca = dict(body_fill=fichas["argumento_fundo"], left_bar=(24, fichas["argumento_barra"]))
    else:
        casca = dict(body_fill=None, box_border=(t["contorno"]["sz"], fichas["argumento_barra"]))
    return _grid_tbl(rows, widths, **casca)


def sintese_box(paragraphs_runs):
    'Caixa de síntese/âncora de abertura. Como a caixa de argumento, com um'


    t = _tema()
    cor = t["fichas"]["argumento_barra"]
    vsz = t["tipografia"]["versalete_sz"]
    eyebrow = para([run("EM SÍNTESE", b=True, color=cor, sz=vsz, spacing="60")],
                   after=60,
                   rpr_mark=f'<w:b/><w:bCs/><w:color w:val="{cor}"/>'
                            f'<w:spacing w:val="60"/><w:sz w:val="{vsz}"/><w:szCs w:val="{vsz}"/>')
    paras = [eyebrow]
    n = len(paragraphs_runs)
    for k, runs_xml in enumerate(paragraphs_runs):
        last = (k == n - 1)
        paras.append(para(runs_xml, after=None if last else 140, line=276))
        if not last:
            paras.append('<w:p><w:pPr><w:spacing w:after="140" w:line="276"'
                         ' w:lineRule="auto"/><w:jc w:val="both"/>'
                         '<w:rPr><w:sz w:val="4"/><w:szCs w:val="4"/></w:rPr>'
                         '</w:pPr></w:p>')
    return _tbl(paras, w=W_FULL, can_split=_pode_quebrar(paras), **_casca_argumento())





















_MESES_RX = ("janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|"
             "setembro|outubro|novembro|dezembro")



AUTOBOLD_CLASSES = (
    ("doc",   r"\((?:Docs?\.)\s?[^()]{1,40}\)"),
    ("valor", r"R\$\s?\d+(?:\.\d{3})*(?:,\d{1,2})?"),
    ("proc",  r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b"),
    ("fls",   r"\bfls?\.\s?\d{1,5}(?:\s?[/\-–]\s?\d{1,5})*"),
    ("item",  r"\bite(?:m|ns)\s+\d{1,3}(?:(?:\s*,\s*|\s+e\s+)\d{1,3})*"),
    ("num",   r"\bn(?:[º°]|\.º|\.)\s?\d(?:[\d.\-/]*\d)?(?:-[A-Za-z])?"),
    ("data",  r"\b\d{1,2}º?\s+de\s+(?:%s)\s+de\s+\d{4}\b"
              r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
              r"|\b\d{1,2}/\d{4}\b"
              r"|\b(?:%s)\s+de\s+\d{4}\b" % (_MESES_RX, _MESES_RX)),
)
AUTOBOLD_RE = re.compile(
    "|".join(f"(?P<{nome}>{pat})" for nome, pat in AUTOBOLD_CLASSES),
    re.IGNORECASE)





_VETO_NUM_RX = re.compile(
    r"\b(?:leis?|lc|complementar|decreto|decretos|s[úu]mulas?|enunciados?|"
    r"temas?|resolu[çc][ãa]o|portarias?|provimento|instru[çc][ãa]o|emenda|"
    r"medida provis[óo]ria|artigos?|arts?|incisos?|al[íi]neas?|par[áa]grafos?|"
    r"c[óo]digo|adi|adpf|adc|resp|are|rext?|cpf|cnpj|rg|oab|cep|pis|nit|"
    r"ctps|cnh|matr[íi]cula)"
    r"(?:[\s/][A-Za-zÀ-ÿ]{1,12}){0,2}[\s,;:.\-/]*$", re.IGNORECASE)


def _autobold_vetado(m, text):
    """True = o trecho casado NÃO recebe negrito automático."""
    if m.lastgroup != "num":
        return False
    return bool(_VETO_NUM_RX.search(text[max(0, m.start() - 48):m.start()]))


def autobold_matches(text):
    '[(início, fim, trecho, classe)] dos dados objetivos que DEVEM sair em'


    out = []
    for m in AUTOBOLD_RE.finditer(text):
        if _autobold_vetado(m, text):
            continue
        out.append((m.start(), m.end(), m.group(0), m.lastgroup))
    return out









_DOC_RE = re.compile(r"\((?:Docs?\.|DOC\.)\s?[^()]{1,40}\)")
_MARKERS = (("***", frozenset(("b", "i"))),
            ("**",  frozenset(("b",))),
            ("__",  frozenset(("u",))),
            ("==",  frozenset(("hl",))),
            ("!!",  frozenset(("red",))),
            ("{{",  frozenset(("gray",))),
            ("*",   frozenset(("i",))))
RED = "7A1F1F"


def _parse_inline(text, flags):
    segs = []
    pos = 0
    n = len(text)
    while pos < n:
        best = None
        for mk, fl in _MARKERS:
            close = "}}" if mk == "{{" else mk
            i = text.find(mk, pos)
            if i == -1:
                continue
            j = text.find(close, i + len(mk))
            if j == -1:
                continue
            if best is None or i < best[0]:
                best = (i, j, mk, close, fl)
        if best is None:
            segs.append((text[pos:], flags))
            break
        i, j, mk, close, fl = best
        if i > pos:
            segs.append((text[pos:i], flags))
        segs.extend(_parse_inline(text[i + len(mk):j], flags | fl))
        pos = j + len(close)
    return [s for s in segs if s[0]]


def _autolink(segments):
    "Separa URLs em segmentos próprios com a flag 'link'."




    out = []
    for text, flags in segments:
        pos = 0
        for m in URL_RX.finditer(text):
            if m.start() > pos:
                out.append((text[pos:m.start()], flags))
            out.append((m.group(0), flags | frozenset(("link",))))
            pos = m.end()
        if pos < len(text):
            out.append((text[pos:], flags))
    return [s for s in out if s[0]]


def _autodoc(segments, extras=True):
    'Põe em negrito os dados objetivos (data, valor, fls./item/(Doc. XX),'



    rx = AUTOBOLD_RE if extras else _DOC_RE
    out = []
    for text, flags in segments:
        if "b" in flags or "link" in flags:
            out.append((text, flags))
            continue
        pos = 0
        for m in rx.finditer(text):
            if _autobold_vetado(m, text):
                continue
            if m.start() > pos:
                out.append((text[pos:m.start()], flags))
            out.append((m.group(0), flags | frozenset(("b",))))
            pos = m.end()
        if pos < len(text):
            out.append((text[pos:], flags))
    return [s for s in out if s[0]]


def md_segments(text, base_italic=False, autobold=True):
    'Texto inline-markdown → [(texto, flags)] com flags ⊆'


    base = frozenset(("i",)) if base_italic else frozenset()
    return _autodoc(_autolink(_parse_inline(straight_quotes(text), base)),
                    extras=autobold)


def _seg_run(text, flags, sz=None):
    gray = "gray" in flags
    color = "404040" if gray else (RED if "red" in flags else None)
    if "link" in flags:




        return link_xml(text, [run(url_quebravel(text), b="b" in flags, i="i" in flags, u=True,
                                   color=LINK_COLOR, sz=sz, rstyle="Hyperlink")])
    return run(text,
               b="b" in flags, i="i" in flags, u="u" in flags,
               highlight="yellow" if "hl" in flags else None,
               color=color,
               sz="21" if gray else sz)


def md_runs(text, base_italic=False, sz=None, autobold=True):
    """Converte texto inline-markdown em runs XML."""
    return [_seg_run(t, f, sz=sz) for t, f in
            md_segments(text, base_italic=base_italic, autobold=autobold)]


def quote_para_runs(text):
    'Parágrafo de citação: aspas retas inicial/final ampliadas'



    segs = md_segments(text, base_italic=True, autobold=False)
    out, closing = [], None
    if segs and segs[0][0].startswith('"'):
        out.append(run('"', b=True, i=True, sz="28"))
        segs[0] = (segs[0][0][1:], segs[0][1])
    if segs and segs[-1][0].endswith('"'):
        closing = run('"', b=True, i=True, sz="28")
        segs[-1] = (segs[-1][0][:-1], segs[-1][1])
    out += [_seg_run(t, f) for t, f in segs if t]
    if closing:
        out.append(closing)
    return out


def body_para(text, indent=True, left=None, bold=False):
    'Parágrafo de corpo canônico (recuo 708 por padrão). left=360 para'


    if left:
        ppr = _body_ppr(False).replace(
            '<w:jc', f'<w:ind w:left="{left}"/><w:jc')
    else:
        ppr = _body_ppr(indent)
    if bold:
        runs = [_seg_run(t, f | frozenset(("b",))) for t, f in md_segments(text)]
        ppr = ppr.replace("</w:pPr>", "<w:rPr><w:b/><w:bCs/></w:rPr></w:pPr>")
    else:
        runs = md_runs(text)
    return f"<w:p>{ppr}{''.join(runs)}</w:p>"


def pedido_para(text, left=None):
    'Item/subitem de pedido: SÓ o marcador (1.  2)  a.  (a)  +) em'

    if left:
        ppr = _body_ppr(False).replace('<w:jc', f'<w:ind w:left="{left}"/><w:jc')
    else:
        ppr = _body_ppr(False)
    m = PEDIDO_ITEM_RX.match(text)
    if m:
        token = text[:m.end()].rstrip()
        rest = text[len(token):]
        runs = [_seg_run(token, frozenset(("b",)))] + md_runs(rest)
    else:
        runs = md_runs(text)
    return f"<w:p>{ppr}{''.join(runs)}</w:p>"





_DATA_HIFEN_RX = re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b")

def normalizar_datas(src):
    'Converte datas autorais DD-MM-AAAA → DD/MM/AAAA. Preserva o teor LITERAL'


    out, literal = [], False
    for ln in src.splitlines(keepends=True):
        s = ln.strip().lower()
        if s.startswith(":::"):
            tipo = s[3:].strip()
            if literal and tipo == "":
                literal = False
            elif not literal and (tipo.startswith("juris") or tipo.startswith("cita")):
                literal = True
            out.append(ln)
            continue
        out.append(ln if literal else _DATA_HIFEN_RX.sub(r"\1/\2/\3", ln))
    return "".join(out)







L30_MAX_CHARS = 160


_L30_ABREV = {"art", "arts", "fl", "fls", "n", "nº", "inc", "incs", "al", "p", "pp", "sr", "sra",
              "dr", "dra", "min", "rel", "des", "doc", "docs", "cf", "v", "ex", "ob", "cit", "op",
              "id", "ib", "ibid", "etc", "ltda", "sec", "cap", "par", "prof", "profa", "exmo",
              "exma", "ilmo", "ilma", "dj", "dje", "j", "t"}
_L30_FIM_FRASE = re.compile(r"([.!?…])\s+(?=[\"«(]?[A-ZÁÉÍÓÚÂÊÔÃÕÀÇ])")
MSG_L30 = ("L30 parágrafo de corpo sem recuo de primeira linha, com {n} caracteres e {f} "
           "frase(s): o marcador ~ serve só para a abertura curta; tire o ~ ou encurte a "
           "abertura: «{inicio}»")


def l30_frases(texto):
    """Quantas frases o texto tem (abreviatura forense não fecha frase)."""
    t = " ".join(str(texto).split())
    n = 1
    for m in _L30_FIM_FRASE.finditer(t):
        antes = t[:m.start()].rsplit(" ", 1)[-1].lstrip("(«\"").lower()
        if m.group(1) == "." and antes in _L30_ABREV:
            continue
        n += 1
    return n


def l30_lead_in_longo(texto):
    """True se um parágrafo SEM recuo passa de lead-in: mais de 160 caracteres OU mais de uma frase."""
    t = " ".join(str(texto).split())
    return bool(t) and (len(t) > L30_MAX_CHARS or l30_frases(t) > 1)


def l30_mensagem(texto):
    t = " ".join(str(texto).split())
    inicio = t if len(t) <= 70 else t[:70].rstrip() + "…"
    return MSG_L30.format(n=len(t), f=l30_frases(t), inicio=inicio)


def l30_avisos_da_fonte(blocks):
    'Avisos L30 sobre os blocos do dialeto: todo parágrafo de corpo marcado com `~`'


    out = []



    visto_banner = False
    for kind, payload in blocks:
        if kind == "banner":
            visto_banner = True
            continue
        if kind != "body" or not visto_banner:
            continue
        texto, com_recuo = payload
        if com_recuo:
            continue
        plano = re.sub(r"\*\*|\*|==", "", texto)
        if l30_lead_in_longo(plano):
            out.append(l30_mensagem(plano))
    return out











RX_L33_NUMERO = re.compile(
    r"^\(?(?:\d{1,3}[.)]|\d{1,3}(?:\.\d{1,2})+[.)]?)\s+(?=[\"«(A-Za-zÀ-ÖØ-öø-ÿ])")
L33_ENUMERACAO_MAX = 200
MSG_L33 = ("L33 {n} parágrafos de corpo começam por número ({exemplos}): a minuta não numera "
           "parágrafos. Seção vai em banner ('# ') ou legenda ('## '), pedido em '::: pedidos'; "
           "tire o número do início do parágrafo.")


def _l33_plano(texto):
    return " ".join(re.sub(r"\*\*|\*|==", "", str(texto)).split())


def l33_paragrafos_numerados(itens):
    '`itens`: sequência de (texto, papel), papel `corpo` para parágrafo de corpo e qualquer'




    planos = [(_l33_plano(t), papel) for t, papel in itens]
    achados, k = [], 0
    while k < len(planos):
        t, papel = planos[k]
        if papel != "corpo" or not RX_L33_NUMERO.match(t):
            k += 1
            continue
        fim = k
        while (fim < len(planos) and planos[fim][1] == "corpo"
               and RX_L33_NUMERO.match(planos[fim][0])):
            fim += 1
        corrida = [x for x, _p in planos[k:fim]]
        anterior = planos[k - 1] if k > 0 else ("", "")
        enumeracao = (anterior[1] == "corpo" and anterior[0].rstrip().endswith(":")
                      and all(len(x) <= L33_ENUMERACAO_MAX for x in corrida))
        if not enumeracao:
            achados.extend(corrida)
        k = fim
    return achados if len(achados) >= 2 else []


def l33_mensagem(achados):
    ex = ", ".join("«" + (a if len(a) <= 50 else a[:50].rstrip() + "…") + "»" for a in achados[:3])
    return MSG_L33.format(n=len(achados), exemplos=ex)


def l33_avisos_da_fonte(blocks):
    """Aviso L33 sobre os blocos do dialeto (no máximo um, com a contagem)."""
    itens = [(payload[0], "corpo") if kind == "body" else ("", kind) for kind, payload in blocks]
    achados = l33_paragrafos_numerados(itens)
    return [l33_mensagem(achados)] if achados else []





PAPEIS_CAPA = ("end", "autor", "titulo", "sub", "vs", "reu", "autos", "campo", "saud")
PAPEIS_FECHO = ("data", "ass")
_RX_LINHA_CAPA = re.compile(r"^(%s):\s*(.*)$" % "|".join(PAPEIS_CAPA))
_RX_LINHA_FECHO = re.compile(r"^(%s):\s*(.*)$" % "|".join(PAPEIS_FECHO))


def parse_blocks(src):
    'Dialeto de blocos → [(kind, payload)]. Uma peça/capítulo por arquivo; a referência'




















    blocks = []
    lines = src.splitlines()
    k = 0
    while k < len(lines):
        ln = lines[k].rstrip()
        if not ln.strip():
            k += 1
            continue
        if ln.startswith(":::"):
            kind = ln[3:].strip().lower()
            if kind.startswith("quebra"):
                blocks.append(("quebra", None))
                k += 1
                continue
            inner = []
            k += 1
            while k < len(lines) and lines[k].strip() != ":::":
                inner.append(lines[k].rstrip())
                k += 1
            k += 1
            if kind.startswith("capa"):
                roles = []
                for l2 in inner:
                    s2 = l2.strip()
                    if not s2:
                        continue
                    m2 = _RX_LINHA_CAPA.match(s2)
                    if m2:
                        roles.append((m2.group(1), m2.group(2)))
                    elif parte_reconhecida(s2):



                        roles.append(("parte", s2))
                    else:
                        roles.append(("autor", s2))
                blocks.append(("capa", roles))
                continue
            if kind.startswith("fecho"):
                roles = []
                free = 0
                for l2 in inner:
                    s2 = l2.strip()
                    if not s2:
                        continue
                    m2 = _RX_LINHA_FECHO.match(s2)
                    if m2:
                        roles.append((m2.group(1), m2.group(2)))
                    else:
                        free += 1
                        roles.append(("t1" if free == 1 else "t2", s2))
                blocks.append(("fecho", roles))
                continue
            if kind.startswith("pedidos"):




                paras, cur = [], []
                for l2 in inner + [""]:
                    s2 = l2.strip()
                    if not s2:
                        if cur:
                            paras.append(" ".join(cur)); cur = []
                    elif PEDIDO_ITEM_RX.match(s2) and cur:
                        paras.append(" ".join(cur)); cur = [s2]
                    else:
                        cur.append(s2)
                if cur:
                    paras.append(" ".join(cur))
                blocks.append(("pedidos", paras))
                continue
            if kind.startswith("juris"):








                items = []
                cab, em = None, []
                for l2 in inner + [""]:
                    if l2.startswith(">>"):
                        trecho = l2[2:].strip()
                        if trecho:
                            em.append(trecho)
                    elif l2.strip():
                        if cab is not None:
                            items.append((cab, em))
                        cab, em = l2.strip(), []
                if cab is not None:
                    items.append((cab, em))
                elif em:
                    items.append(("", em))
                blocks.append(("juris", items))



            elif kind.startswith("tabela"):


                rows = [[c.strip() for c in l2.split("|")]
                        for l2 in inner if l2.strip()]
                blocks.append(("tabela", rows))
            elif kind.startswith("timeline"):

                ents = []
                for l2 in inner:
                    if not l2.strip():
                        continue
                    if "|" in l2:
                        d, ev = l2.split("|", 1)
                        ents.append((d.strip(), ev.strip()))
                    else:
                        ents.append(("", l2.strip()))
                blocks.append(("timeline", ents))
            elif kind.startswith("sintese") or kind.startswith("ancora"):


                paras, cur = [], []
                for l2 in inner + [""]:
                    s2 = l2.strip()
                    if s2:
                        cur.append(s2)
                    elif cur:
                        paras.append(" ".join(cur)); cur = []


                if paras:
                    paras[0] = re.sub(r"^\*\*\s*Em\s+s[íi]ntese\s*[.:]?\s*\*\*\s*[.:]?\s*", "",
                                      paras[0], count=1, flags=re.I)
                    if not paras[0]:
                        paras = paras[1:]
                blocks.append(("sintese", paras))
            else:
                is_quote = kind.startswith("cita")
                paras, cur = [], []

                def flush():
                    if cur:
                        paras.append(" ".join(cur))
                        del cur[:]
                for l2 in inner + [""]:
                    s2 = l2.strip()
                    if s2 == "---" and is_quote:
                        flush()
                        paras.append(("sep",))
                    elif s2.startswith("-- ") and is_quote:
                        flush()
                        paras.append(("attr", s2[3:].strip()))
                    elif s2:
                        cur.append(s2)
                    else:
                        flush()
                flush()
                if is_quote:
                    items = [p if isinstance(p, tuple) else ("q", p)
                             for p in paras]
                    blocks.append(("citacao", items))
                else:
                    blocks.append(("caixa", paras))
            continue
        if ln.startswith("&"):
            blocks.append(("ctl", ln[1:].strip().lower()))
            k += 1
            continue
        if ln.startswith("## "):
            blocks.append(("legenda", ln[3:].strip()))
            k += 1
            continue
        if ln.startswith("# "):
            t = ln[2:].strip()
            if "|" in t:
                eyebrow, title = [x.strip() for x in t.split("|", 1)]
            else:
                eyebrow, title = None, t
            blocks.append(("banner", (eyebrow, title)))
            k += 1
            continue

        cur = []
        noind = False
        while k < len(lines) and lines[k].strip() and not re.match(
                r"^(#|::|:::|&)", lines[k].strip()):
            piece = lines[k].rstrip()
            if not cur and piece.startswith("~ "):
                noind = True
                piece = piece[2:]









            if parte_reconhecida(piece.strip()) and not _tem_continuacao(lines, k):
                if cur:
                    break
                cur.append(linha_de_parte(piece.strip()))
                k += 1
                break
            cur.append(piece.strip())
            k += 1
        if not cur and k < len(lines):





            s_k = lines[k].strip()
            m_k = re.match(r"^#{3,}\s+(.*)$", s_k)
            if m_k:
                blocks.append(("legenda", m_k.group(1).strip()))
            else:
                blocks.append(("body", (s_k, True)))
            k += 1
            continue
        blocks.append(("body", (" ".join(cur), not noind)))
    return blocks





















RX_REF_ACHADO = re.compile(r"^achado\s*:\s*(\S+)\s*$", re.I)


class AchadoAusente(Exception):
    'Referência `>> achado: <id>` que o dataset não contém. Falha FECHADA: gerar a peça'



def injetar_achados(blocks, achados, quebrar=True):
    'Resolve `>> achado: <id>` nos blocos de jurisprudência, do dataset verificado.'





    por_id = {}
    for a in (achados or []):
        if isinstance(a, dict) and str(a.get("id") or "").strip():
            por_id[str(a["id"]).strip()] = a
    faltando, injetados = [], 0
    saida = []
    for kind, payload in blocks:
        if kind != "juris":
            saida.append((kind, payload))
            continue
        novos = []
        for cab, ementa in payload:
            ids = [m.group(1) for m in (RX_REF_ACHADO.match(l or "") for l in ementa) if m]
            if not ids:
                novos.append((cab, ementa))
                continue
            for ident in ids:
                achado = por_id.get(ident)
                if achado is None:
                    faltando.append(ident)
                    continue
                literal = str(achado.get("syllabus_literal") or "").strip()
                if not literal:
                    literal = str(achado.get("full_text") or "").strip()
                if not literal:
                    faltando.append(f"{ident} (sem teor gravado)")
                    continue



                partes = [p.strip() for p in literal.splitlines() if p.strip()] if quebrar \
                    else [literal]
                novos.append((str(achado.get("reference") or "").strip(), partes or [literal]))
                injetados += 1
        saida.append((kind, novos))
    if faltando:
        raise AchadoAusente(
            "referência a achado inexistente no dataset: " + ", ".join(sorted(set(faltando)))
            + ". Confira o `id` no achados.json — o builder NÃO inventa julgado, e caixa de "
              "jurisprudência muda não sai daqui")
    return saida, injetados











_ROTULOS_PARTE = (
    "agravante", "agravado", "recorrente", "recorrido", "apelante", "apelado",
    "embargante", "embargado", "impetrante", "impetrado", "requerente", "requerido",
    "reclamante", "reclamado", "exequente", "executado", "paciente", "autor",
    "réu", "reu", "ré",
)





RX_LINHA_PARTE = re.compile(
    r"^(?P<rot>(?:" + "|".join(_ROTULOS_PARTE) + r")(?:a|s|as|es|oras|ora)?)\s*:\s*"
    r"(?P<nome>\S.*?)\s*$", re.IGNORECASE)














LIMITE_NOME_PARTE = 120
_RX_NOME_MINUSCULO = re.compile(r"^[a-zà-öø-ÿ]")
_RX_FRASE_INTERNA = re.compile(r"[.!?;][  ]+\S")









_RX_MARCA_SOCIETARIA = re.compile(
    r"&|\b(?:Ltda|Cia|Companhia|Associados|Sociedade|Limitada|Eireli)\b"
    r"|(?<![\w.])(?:S\.\s?A\.?|S/A|SA|ME|EPP|MEI|SLU)(?!\w)", re.IGNORECASE)

_SIGLAS_SOCIETARIAS_CAIXA = {"SA", "ME", "EPP", "MEI", "SLU"}
_CONECTIVOS_DE_NOME = {"de", "da", "do", "das", "dos", "e", "d'", "del", "la", "y"}
_RX_TERMO_QUALIFICACAO = re.compile(
    r"(?i)\b(?:brasileir|estrangeir|solteir|casad|divorciad|vi[uú]v|separad|convivente"
    r"|inscrit|portador|resident|domiciliad|cpf|cnpj|rg|oab|pessoa|sede|sediad"
    r"|representad|nacionalidade|profiss|menor|nascid|natural|filh|estabelecid"
    r"|matriz|filial|endere[cç]|rua|avenida)")


def _tem_forma_de_nome(trecho):
    'Trecho de nome: palavras capitalizadas, `&` ou conectivo, sem algarismo, sem termo'


    t = (trecho or "").strip()
    if not t or len(t) > 80 or re.search(r"\d", t) or _RX_TERMO_QUALIFICACAO.search(t):
        return False
    for palavra in t.split():
        if palavra == "&" or palavra.lower() in _CONECTIVOS_DE_NOME:
            continue
        if not palavra[0].isupper():
            return False
    return True


def _tem_marca_societaria(trecho):
    for m in _RX_MARCA_SOCIETARIA.finditer(trecho or ""):
        sig = m.group(0).replace(".", "").replace(" ", "").replace("/", "")
        if sig.upper() in _SIGLAS_SOCIETARIAS_CAIXA and sig != sig.upper():
            continue
        return True
    return False


def fim_do_nome(texto):
    'Índice em que o NOME termina num texto `Nome, qualificação…`: a vírgula que abre a'


    texto = texto or ""
    virgulas = [i for i, c in enumerate(texto) if c == ","]
    if not virgulas:
        return len(texto)
    limites = virgulas + [len(texto)]
    fim = virgulas[0]
    for k, v in enumerate(virgulas):
        trecho = texto[v + 1:limites[k + 1]]
        if not _tem_forma_de_nome(trecho):
            break
        if _tem_marca_societaria(trecho):
            fim = limites[k + 1]
    return fim


def nome_parece_de_parte(nome):
    """O texto depois de `Rótulo:` parece NOME de parte (e não frase nem qualificação)?"""
    nome = (nome or "").strip()
    if not nome or len(nome) > LIMITE_NOME_PARTE:
        return False
    if _RX_NOME_MINUSCULO.match(nome):
        return False
    if "," in nome and fim_do_nome(nome) < len(nome):
        return False
    if _RX_FRASE_INTERNA.search(nome):
        return False
    return True


def _tem_continuacao(lines, k):
    'A linha `k+1` continua o parágrafo da linha `k`? Linha em branco, diretiva do'

    nxt = lines[k + 1].strip() if k + 1 < len(lines) else ""
    if not nxt or re.match(r"^(#|::|:::|&)", nxt):
        return False
    return parte_reconhecida(nxt) is None


def parte_reconhecida(texto):
    'O match da linha de parte, ou None. É o ÚNICO lugar que decide — capa e corpo'

    m = RX_LINHA_PARTE.match(str(texto or "").strip())
    if m is None or not nome_parece_de_parte(m.group("nome")):
        return None
    return m


def linha_de_parte(texto):
    '`"Agravante: Fulano de Tal"` → `"Agravante: **FULANO DE TAL**"`; qualquer outra'






    m = parte_reconhecida(texto)
    if not m:
        return texto
    nome = m.group("nome")
    if "*" in nome or "==" in nome:
        return texto
    return f"{m.group('rot')}: **{nome.upper()}**"


def _negrito_ate_virgula(segs):
    'Negrito no nome da parte até o fim do NOME (convenção forense Dissero),'








    def atomico(f):


        return "hl" in f or "link" in f


    corrido = "".join("x" * len(t) if atomico(f) else t for t, f in segs)
    corte = fim_do_nome(corrido)
    out, pos = [], 0
    for t, f in segs:
        ini, pos = pos, pos + len(t)
        if ini >= corte:
            out.append((t, f))
        elif pos <= corte or atomico(f):
            out.append((t, f | frozenset(("b",))))
        else:
            out.append((t[:corte - ini], f | frozenset(("b",))))
            out.append((t[corte - ini:], f))
    return out


def capa_xml(roles):
    'Capa canônica: endereçamento (negrito, after=320 + espaçador 320),'



    out = []
    sub = None
    for role, text in roles:
        if role == "sub":
            sub = text
    seq = [(r, t) for r, t in roles if r != "sub"]
    ppr_map = {
        "end":   dict(after=320, line=None, b=True),
        "autor": dict(after=200, line=276, b=False),
        "vs":    dict(after=160, line=276, b=False),
        "reu":   dict(after=120, line=276, b=False),
        "autos": dict(after=200, line=None, b=True),
        "campo": dict(after=120, line=276, b=False),
        "saud":  dict(after=320, line=None, b=True),
        "parte": dict(after=120, line=276, b=False),
    }
    for i, (role, text) in enumerate(seq):
        if role == "titulo":
            out.append(title_box(text, sub))





            if i + 1 < len(seq):
                out.append(spacer(140, line=276, mark=4))
            continue
        if role == "parte":
            text = linha_de_parte(text)
        cfg = ppr_map.get(role, ppr_map["autor"])
        segs = md_segments(text)
        if cfg["b"]:
            segs = [(t, f | frozenset(("b",))) for t, f in segs]
        elif role in ("autor", "reu"):



            segs = _negrito_ate_virgula(segs)
        runs_xml = [_seg_run(t, f) for t, f in segs]
        out.append(para(runs_xml, after=cfg["after"], line=cfg["line"],
                        rpr_mark="<w:b/><w:bCs/>" if cfg["b"] else None))
        if role == "end":
            out.append(spacer(320, line=None, mark=4))
        elif role == "autos":

            out.append(spacer(160, line=None, mark=4))





    out.append(spacer(_tema()["capitulo"]["antes"], line=None, mark=20))
    return "".join(out)


_RX_P_ABRE = re.compile(r"<w:p(?:\s[^>]*)?>")


_ANTES_DA_QUEBRA = ("</w:pStyle>", "<w:keepNext/>", "<w:keepLines/>")


def sem_espacadores_finais(xml):
    'Tira os parágrafos VAZIOS do fim do trecho. Os blocos chegam a `blocks_to_xml` como'


    while xml.endswith("</w:p>"):
        k = max(xml.rfind("<w:p>"), xml.rfind("<w:p "))
        if k < 0:
            break
        ultimo = xml[k:]



        if "</w:tbl>" in ultimo or "<w:br" in ultimo or re.search(r"<w:t[^>]*>[^<]", ultimo):
            break
        xml = xml[:k]
    return xml


def com_quebra_de_pagina(trecho_xml):
    'Põe `<w:pageBreakBefore/>` no PRIMEIRO parágrafo do trecho, respeitando a ordem do'


    m = _RX_P_ABRE.search(trecho_xml)
    if not m:
        return trecho_xml
    ini = m.end()
    if trecho_xml.startswith("<w:pPr>", ini):
        corte = ini + len("<w:pPr>")
        for marca in _ANTES_DA_QUEBRA:
            pos = trecho_xml.find(marca, ini, trecho_xml.find("</w:pPr>", ini))
            if pos >= 0:
                corte = max(corte, pos + len(marca))
        return trecho_xml[:corte] + "<w:pageBreakBefore/>" + trecho_xml[corte:]
    return trecho_xml[:ini] + "<w:pPr><w:pageBreakBefore/></w:pPr>" + trecho_xml[ini:]


def fecho_xml(roles):
    "Fecho canônico: 'Termos em que,' (before=160/after=60), 'Pede e"


    out = []
    assinada = False
    for role, text in roles:


        if (role == "ass" and not assinada and _ASSINATURA
                and _ASSINATURA["nome"] and _ASSINATURA["nome"] in _normalizar_nome(text)):
            out.append(_paragrafo_assinatura())
        if role == "ass":
            assinada = True


        bold = role in ("data", "ass")
        runs_xml = [_seg_run(t, (f | frozenset(("b",))) if bold else f)
                    for t, f in md_segments(text)]
        if role == "t1":


            out.append(para(runs_xml, before=160, after=60, line=None))
        elif role == "t2":
            out.append(para(runs_xml, after=220, line=None))
            out.append(spacer(220, line=None, mark=None))
        elif role == "data":
            out.append(para(runs_xml, after=320, line=None,
                            rpr_mark="<w:b/><w:bCs/>"))
            out.append(spacer(320, line=None, mark=None))
        elif role == "ass":
            out.append(para(runs_xml, jc="center", rpr_mark="<w:b/><w:bCs/>"))
    out.append(spacer(140, line=276, mark=None))
    out.append(spacer(140, line=276, mark=None))
    return "".join(out)


_RX_TEM_OAB = re.compile(r"\bOAB\b", re.IGNORECASE)


def completar_oab_no_fecho(blocks, oab, *nomes):
    'Peça final: o fecho assinado com o NOME e sem a inscrição na OAB ganha a inscrição'












    if not oab:
        return 0
    alvos = {a for a in (_normalizar_nome(n) for n in nomes) if a}
    postos = 0
    for kind, payload in blocks:
        if kind != "fecho" or not payload:
            continue
        pos = next((j for j, (r, t) in enumerate(payload)
                    if r == "ass" and any(a in _normalizar_nome(t) for a in alvos)), None)
        if pos is None:
            continue




        if _RX_TEM_OAB.search(payload[pos][1] or ""):
            continue
        seguinte = next(((r, t) for r, t in payload[pos + 1:] if r == "ass"), None)
        if seguinte is not None and _RX_TEM_OAB.search(seguinte[1] or ""):
            continue
        payload.insert(pos + 1, ("ass", oab))
        postos += 1
    return postos




_RX_PAPEL_NO_FECHO = re.compile(
    r"(?i)^(?:advogad[oa]s?|procurador[a]?|defensor[a]?|estagi[aá]ri[oa]|s[oó]ci[oa]"
    r"|p\.\s?p\.|assinad[oa]|assinatura|subscritor[a]?|representante)\b")
_RX_ESCRITORIO = re.compile(r"(?i)\badvoca(?:cia|dos)\b")


def signatarios_sem_inscricao(linhas):
    'Os NOMES de signatário de um bloco de assinatura que ficaram sem a inscrição na OAB.'





    faltam, pendente = [], None
    for linha in linhas:
        s = (linha or "").strip()
        if _RX_TEM_OAB.search(s):
            pendente = None
            continue
        palavras = [p for p in s.split() if p != "&"]
        if (len(palavras) < 2 or _RX_PAPEL_NO_FECHO.match(s) or _RX_ESCRITORIO.search(s)
                or _tem_marca_societaria(s) or not _tem_forma_de_nome(s)):
            continue
        if pendente:
            faltam.append(pendente)
        pendente = s
    if pendente:
        faltam.append(pendente)
    return faltam


def blocks_to_xml(blocks):
    'Monta o XML do corpo com as regras canônicas de espaçamento do'







    LINKS_EXTERNOS.clear()
    out = []
    prev = None
    prev_kind = None

    suppress = False
    quebra_pendente = False
    blocos_apos_quebra = 0
    for kind, payload in blocks:
        if kind == "ctl":
            if payload == "glue":
                suppress = True
            elif payload.startswith("sp") and quebra_pendente:




                suppress = True
            elif payload.startswith("sp"):
                spec = payload[2:]
                plain_line = spec.endswith("p")
                if plain_line:
                    spec = spec[:-1]
                parts = spec.split(".")
                after = int(parts[0])
                mark = (int(parts[1]) if len(parts) > 1 else 4) or None
                out.append(spacer(after, line=None if plain_line else 276,
                                  mark=mark))
                suppress = True
            continue
        is_tbl = kind in ("banner", "legenda", "caixa", "citacao", "juris",
                          "tabela", "timeline", "sintese")




        gap = None
        if prev is not None and prev != "fixo":
            if kind == "banner":



                gap = (_tema()["capitulo"]["antes"], None, 4)
            elif kind == "pedidos" and prev_kind in ("banner", "legenda"):



                gap = ("280", 276, 4)
            elif prev == "tbl":
                gap = ("140", 276, 4)
        if suppress or quebra_pendente:


            gap = None
            suppress = False
        if gap:





            out.append(spacer(int(gap[0]), line=gap[1], mark=gap[2],
                              keep_next=prev_kind in ("banner", "legenda")))
        prev_kind = kind
        marca = len(out)

        if kind == "banner":
            eyebrow, title = payload
            out.append(banner(title, eyebrow=eyebrow))
            prev = "tbl"
        elif kind == "legenda":
            out.append(legend(straight_quotes(payload)))
            prev = "tbl"
        elif kind == "caixa":
            out.append(arg_box([md_runs(p) for p in payload]))
            prev = "tbl"
        elif kind == "citacao":
            out.append(quote_box(payload))
            prev = "tbl"
        elif kind == "juris":
            items = [(straight_quotes(c), [straight_quotes(e) for e in ems])
                     for c, ems in payload]
            out.append(juris_box(items))
            prev = "tbl"
        elif kind == "tabela":
            out.append(data_table(payload[0] if payload else [],
                                  payload[1:] if payload else []))
            prev = "tbl"
        elif kind == "timeline":
            out.append(timeline_box(payload))
            prev = "tbl"
        elif kind == "sintese":
            out.append(sintese_box([md_runs(p) for p in payload]))
            prev = "tbl"
        elif kind == "body":
            text, indent = payload
            out.append(body_para(text, indent=indent))
            prev = "body"
        elif kind == "pedidos":







            for k, p in enumerate(payload):
                ultimo = k == len(payload) - 1
                if p.startswith("+ "):
                    out.append(pedido_para(p[2:], left=360))
                    if not ultimo:
                        out.append(spacer(140, line=276, mark=4).replace(
                            "<w:jc", '<w:ind w:left="360"/><w:jc'))
                else:
                    out.append(pedido_para(p))
                    if not ultimo:
                        out.append(spacer(140, line=276, mark=4))
            prev = "body"
        elif kind == "capa":
            out.append(capa_xml(payload))
            prev = "fixo"
        elif kind == "quebra":







            while out:
                podado = sem_espacadores_finais(out[-1])
                if podado == out[-1]:
                    break
                if podado:
                    out[-1] = podado
                    break
                out.pop()
            if quebra_pendente:




                out.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
            quebra_pendente = True
            blocos_apos_quebra = 0
            prev = "fixo"
        elif kind == "fecho":
            out.append(fecho_xml(payload))
            prev = "fixo"

        if quebra_pendente and kind != "quebra":
            blocos_apos_quebra += 1
        if quebra_pendente and len(out) > marca and kind != "quebra":
            trecho = "".join(out[marca:])
            del out[marca:]
            out.append(com_quebra_de_pagina(trecho))
            quebra_pendente = False
    if quebra_pendente and not blocos_apos_quebra:








        out.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
    return "".join(out)


def build_document_xml(base_document_xml, body_content_xml):
    'Substitui o conteúdo do corpo do document.xml base, preservando'

    m = re.search(r"<w:body>(.*)</w:body>", base_document_xml, re.DOTALL)
    inner = m.group(1)
    sect = re.search(r"<w:sectPr.*?</w:sectPr>", inner, re.DOTALL)
    sect_xml = sect.group(0) if sect else SECTPR_CANON
    new_inner = body_content_xml + sect_xml
    return (base_document_xml[:m.start(1)] + new_inner +
            base_document_xml[m.end(1):])











FAIXA_MINUTA_TITULO = "MINUTA COM PENDÊNCIAS."
FAIXA_MINUTA_CORPO = ("Documento gerado por ordem do advogado antes da conclusão da revisão. "
                      "Os trechos realçados dependem de conferência e não devem ser "
                      "protocolados como estão.")
FAIXA_MINUTA_PENDENCIAS = FAIXA_MINUTA_TITULO + " " + FAIXA_MINUTA_CORPO

_FAIXA_MINUTA_MD = "!!**" + FAIXA_MINUTA_TITULO + "**!! " + FAIXA_MINUTA_CORPO


def _so_espaco(t):
    return re.sub(r"\s+", " ", t or "").strip()


def tem_faixa_minuta(texto):
    'True quando o texto (de um parágrafo, ou do documento inteiro) traz a faixa da minuta'

    return _so_espaco(FAIXA_MINUTA_PENDENCIAS) in _so_espaco(texto)


def bloco_faixa_minuta():
    """O bloco `caixa` da faixa, para entrar na lista de `parse_blocks`."""
    return ("caixa", [_FAIXA_MINUTA_MD])


def inserir_faixa_minuta(blocks):
    'A lista de blocos com a faixa logo DEPOIS da capa, ou no topo quando não há capa'



    blocks = list(blocks)
    pos = next((i + 1 for i, (k, _p) in enumerate(blocks) if k == "capa"), 0)
    blocks.insert(pos, bloco_faixa_minuta())
    return blocks


def faixa_minuta_xml():
    'O XML da faixa (caixa e o espaçador abaixo), para o transformer, que recebe o'

    return arg_box([md_runs(_FAIXA_MINUTA_MD, autobold=False)]) + spacer(140)


def inserir_faixa_no_corpo(doc_xml):
    'O `document.xml` com a faixa no topo do corpo, logo depois de `<w:body>` (o'

    return re.sub(r"(<w:body(?:\s[^>]*)?>)", lambda m: m.group(1) + faixa_minuta_xml(),
                  doc_xml, count=1)


_RX_P_DOC = re.compile(r"<w:p[ >].*?</w:p>", re.S)
_RX_T_DOC = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>")


def textos_dos_paragrafos(doc_xml):
    """O texto de cada parágrafo (`w:p`) com texto, na ordem do XML."""
    import html as _html
    saida = []
    for p in _RX_P_DOC.findall(doc_xml):
        t = "".join(_html.unescape(x) for x in _RX_T_DOC.findall(p))
        if t.strip():
            saida.append(t)
    return saida


def indice_da_faixa(docx_path):
    'A posição da faixa entre os parágrafos com texto de `word/document.xml` (0 = o'




    try:
        with zipfile.ZipFile(docx_path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return None
    alvo = _so_espaco(FAIXA_MINUTA_PENDENCIAS)
    for i, t in enumerate(textos_dos_paragrafos(xml)):
        if _so_espaco(t) == alvo:
            return i
    return None








PREFIXOS_MARCADOR_PENDENCIA = (r"(?:jurisprud\w*\s+a\s+(?:conferir|inserir)|a\s+conferir|"
                               r"conferir|completar|verificar|pendente|inserir)\b")
RX_MARCADOR_PENDENCIA = re.compile(r"\[\s*" + PREFIXOS_MARCADOR_PENDENCIA + r"[^\]\n]*\]",
                                   re.I)




_DEPOIS_DO_REALCE = ("u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl", "cs", "em",
                     "lang", "eastAsianLayout", "specVanish", "oMath", "rPrChange")
_RX_RUN_DOC = re.compile(r"<w:r(?:\s[^>]*)?>(?:(?!</w:r>).)*</w:r>", re.S)
_RX_RUN_SO_TEXTO = re.compile(
    r"<w:r((?:\s[^>]*)?)>(<w:rPr>(?:(?!</w:rPr>).)*</w:rPr>)?(<w:t(?:\s[^>]*)?>)([^<]*)</w:t></w:r>",
    re.S)


def _rpr_com_realce(rpr):
    'O rPr (string, possivelmente vazia) com `<w:highlight w:val="yellow"/>` na posição do'

    if not rpr:
        return '<w:rPr><w:highlight w:val="yellow"/></w:rPr>'
    if "<w:highlight" in rpr:
        return rpr
    m = re.search(r"<w:(?:" + "|".join(_DEPOIS_DO_REALCE) + r")[\s/>]", rpr)
    pos = m.start() if m else rpr.rindex("</w:rPr>")
    return rpr[:pos] + '<w:highlight w:val="yellow"/>' + rpr[pos:]


def realcar_trechos_no_xml(doc_xml, achar):
    'Realça (amarelo, `w:highlight`) os trechos que `achar(texto_do_paragrafo)` aponta, sem'







    import html as _html
    trechos = []

    def no_paragrafo(mp):
        p = mp.group(0)
        if "<w:txbxContent" in p:
            return p
        runs = list(_RX_RUN_DOC.finditer(p))
        if not runs:
            return p
        pedacos, pos = [], 0
        for r in runs:
            t = "".join(_html.unescape(x) for x in _RX_T_DOC.findall(r.group(0)))
            pedacos.append((r, pos, pos + len(t)))
            pos += len(t)
        texto = "".join("".join(_html.unescape(x) for x in _RX_T_DOC.findall(r.group(0)))
                        for r, _a, _b in pedacos)
        spans = sorted(set((a, b) for a, b in achar(texto) if 0 <= a < b <= len(texto)))
        if not spans:
            return p
        trechos.extend(texto[a:b] for a, b in spans)
        saida, cursor = [], 0
        for r, ini, fim in pedacos:
            saida.append(p[cursor:r.start()])
            cursor = r.end()
            run_xml = r.group(0)
            toca = [(max(a, ini), min(b, fim)) for a, b in spans if a < fim and b > ini]
            if not toca:
                saida.append(run_xml)
                continue
            simples = _RX_RUN_SO_TEXTO.fullmatch(run_xml)
            if not simples:
                rpr_m = re.search(r"<w:rPr>(?:(?!</w:rPr>).)*</w:rPr>", run_xml, re.S)
                if rpr_m:
                    run_xml = (run_xml[:rpr_m.start()] + _rpr_com_realce(rpr_m.group(0))
                               + run_xml[rpr_m.end():])
                else:
                    run_xml = re.sub(r"^(<w:r(?:\s[^>]*)?>)",
                                     lambda m: m.group(1) + _rpr_com_realce(""), run_xml)
                saida.append(run_xml)
                continue
            attrs, rpr, _abre_t = simples.group(1), simples.group(2) or "", simples.group(3)
            t_run = _html.unescape(simples.group(4))
            cortes = sorted({0, len(t_run)} | {x - ini for a, b in toca for x in (a, b)})
            for c0, c1 in zip(cortes, cortes[1:]):
                pedaco = t_run[c0:c1]
                if not pedaco:
                    continue
                dentro = any(a - ini <= c0 and c1 <= b - ini for a, b in toca)
                rpr_p = _rpr_com_realce(rpr) if dentro else rpr
                saida.append(f'<w:r{attrs}>{rpr_p}<w:t xml:space="preserve">'
                             f'{_html.escape(pedaco, quote=False)}</w:t></w:r>')
        saida.append(p[cursor:])
        return "".join(saida)

    return _RX_P_DOC.sub(no_paragrafo, doc_xml), trechos





def unpack(docx_path, work_dir):
    if os.path.isdir(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)
    with zipfile.ZipFile(docx_path) as z:
        z.extractall(work_dir)
    return work_dir








def _autor_do_perfil():
    try:
        import perfil_advogado as _pa
        perfil = _pa.carregar()
    except Exception:
        return ""
    if not isinstance(perfil, dict):
        return ""
    return str((perfil.get("advogado") or {}).get("nome") or "").strip()


def _definir_campo(xml, tag, valor, fecho):
    'Troca o conteúdo de <tag ...>...</tag> (ou a forma vazia <tag/>), ou o insere antes de'

    rx = re.compile(r"<%s(\s[^>]*)?(?:/>|>.*?</%s>)" % (re.escape(tag), re.escape(tag)), re.S)
    m = rx.search(xml)
    attrs = (m.group(1) or "") if m else ""
    novo = "<%s%s>%s</%s>" % (tag, attrs, valor, tag)
    if m:
        return xml[:m.start()] + novo + xml[m.end():]
    return xml.replace(fecho, novo + fecho)


def propriedades_do_documento(work_dir, autor=None, agora=None):
    """Regrava docProps/core.xml e docProps/app.xml sem dado de quem não assina a peça."""
    import datetime as _dt
    import html as _h
    autor = _h.escape(_autor_do_perfil() if autor is None else autor, quote=False)
    agora = agora or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = os.path.join(work_dir, "docProps", "core.xml")
    if os.path.isfile(core):
        with open(core, encoding="utf-8") as f:
            xml = f.read()
        fecho = "</cp:coreProperties>"
        for tag, valor in (("dc:creator", autor), ("cp:lastModifiedBy", autor),
                           ("cp:revision", "1")):
            xml = _definir_campo(xml, tag, valor, fecho)
        for tag in ("dcterms:created", "dcterms:modified"):
            xml = re.sub(r"<%s(\s[^>]*)?>.*?</%s>" % (tag, tag),
                         lambda m, t=tag: '<%s xsi:type="dcterms:W3CDTF">%s</%s>' % (t, agora, t),
                         xml, flags=re.S)
        xml = re.sub(r"<cp:lastPrinted(\s[^>]*)?(?:/>|>.*?</cp:lastPrinted>)", "", xml, flags=re.S)
        with open(core, "w", encoding="utf-8") as f:
            f.write(xml)
    app = os.path.join(work_dir, "docProps", "app.xml")
    if os.path.isfile(app):
        with open(app, encoding="utf-8") as f:
            xml = f.read()
        for tag, valor in (("Company", ""), ("Manager", ""), ("TotalTime", "0")):
            if re.search(r"<%s[\s/>]" % tag, xml):
                xml = _definir_campo(xml, tag, valor, "</Properties>")
        with open(app, "w", encoding="utf-8") as f:
            f.write(xml)


class ArquivoEmUso(Exception):
    """Destino aberto em outro programa (Word/LibreOffice). Não é defeito de geração."""


def pack(work_dir, out_docx):



    try:
        if os.path.exists(out_docx):
            os.remove(out_docx)
    except PermissionError:
        raise ArquivoEmUso(
            f"o destino está ABERTO em outro programa e o Windows bloqueia a escrita:\n"
            f"  {out_docx}\n"
            f"Feche o arquivo no Word/LibreOffice e rode de novo (nada foi alterado).")



    _ajustar_documento_ao_layout(work_dir)
    propriedades_do_documento(work_dir)
    names = []
    for root, _dirs, files in os.walk(work_dir):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, work_dir).replace(os.sep, "/")
            names.append(rel)
    names.sort(key=lambda n: (n != "[Content_Types].xml", n))
    with zipfile.ZipFile(out_docx, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in names:
            z.write(os.path.join(work_dir, rel), rel)
    return out_docx


def validate_docx(docx_path):
    'Validação leve: zip íntegro, XML bem formado, partes essenciais,'

    import xml.etree.ElementTree as ET
    errors = []
    with zipfile.ZipFile(docx_path) as z:
        bad = z.testzip()
        if bad:
            errors.append(f"zip corrompido em {bad}")
        names = set(z.namelist())
        for req in ("[Content_Types].xml", "word/document.xml",
                    "_rels/.rels", "word/_rels/document.xml.rels"):
            if req not in names:
                errors.append(f"parte essencial ausente: {req}")
        for n in names:
            if n.endswith((".xml", ".rels")):
                try:
                    ET.fromstring(z.read(n))
                except ET.ParseError as e:
                    errors.append(f"XML malformado {n}: {e}")




        rels_parts = sorted(n for n in names
                             if n == "word/_rels/document.xml.rels"
                             or re.fullmatch(r"word/_rels/(header|footer)\d+\.xml\.rels", n))
        for rels_part in rels_parts:
            rels = z.read(rels_part).decode("utf-8")
            for m in re.finditer(r'Target="([^"]+)"', rels):
                t = m.group(1)
                if t.startswith(("http", "/")) or "TargetMode=\"External\"" in rels[max(0, m.start()-200):m.end()+200]:
                    continue
                import posixpath
                resolved = posixpath.normpath(posixpath.join("word", t))
                if resolved not in names:
                    errors.append(f"relationship sem alvo: {resolved} (declarado em {rels_part})")

        if "[Content_Types].xml" in names:
            ct = z.read("[Content_Types].xml").decode("utf-8")
            for part, ctype in (("word/header1.xml", CT_HEADER),
                                ("word/footer1.xml", CT_FOOTER)):
                if part in names and f'PartName="/{part}"' not in ct:
                    errors.append(f"content-type ausente para {part}")
    return errors





IDENTITY_PARTS = ("header1.xml", "header2.xml", "header3.xml",
                  "footer1.xml", "footer2.xml", "footer3.xml")
IDENTITY_MAP = (("header", "even", "header1.xml", "rIdDsrH1"),
                ("header", "default", "header2.xml", "rIdDsrH2"),
                ("header", "first", "header3.xml", "rIdDsrH3"),
                ("footer", "even", "footer1.xml", "rIdDsrF1"),
                ("footer", "default", "footer2.xml", "rIdDsrF2"),
                ("footer", "first", "footer3.xml", "rIdDsrF3"))












IDENTITY_EXTRA_RE = re.compile(r"^(_rels/(header|footer)\d+\.xml\.rels|media/(?!\.{1,2}$)[^/\\]+)$")
CT_IMAGENS = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
              "gif": "image/gif", "emf": "image/x-emf", "wmf": "image/x-wmf",
              "svg": "image/svg+xml", "bmp": "image/bmp", "tif": "image/tiff",
              "tiff": "image/tiff"}

RX_PARTE_IDENTIDADE = re.compile(r"(header|footer)(\d+)\.xml")


def _peso_parte(caminho):
    'Quanto CONTEÚDO visível uma parte de cabeçalho/rodapé carrega. Usado para escolher'






    try:
        with open(caminho, encoding="utf-8", errors="replace") as fh:
            xml = fh.read()
    except OSError:
        return -1
    texto = sum(len(m.group(1).strip()) for m in re.finditer(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", xml))
    imagens = len(re.findall(r"<w:(?:drawing|pict)\b", xml))
    return texto + 200 * imagens


def planejar_identidade(ident_dir):
    'Qual arquivo de `ident_dir` preenche cada um dos seis slots Dissero. `{alvo: origem}`.'




























    plano = {}
    for especie in ("header", "footer"):
        alvos = [p for (k, _t, p, _r) in IDENTITY_MAP if k == especie]
        if all(os.path.isfile(os.path.join(ident_dir, a)) for a in alvos):
            plano.update({a: a for a in alvos})
            continue
        try:
            nomes = os.listdir(ident_dir)
        except OSError:
            nomes = []
        achados = []
        for n in nomes:
            m = RX_PARTE_IDENTIDADE.fullmatch(n)
            if m and m.group(1) == especie:
                achados.append((-_peso_parte(os.path.join(ident_dir, n)), int(m.group(2)), n))
        if not achados:
            continue
        fonte = sorted(achados)[0][2]
        plano.update({a: fonte for a in alvos})
    return plano


def timbrado_em_toda_pagina(plano, ident_dir):
    'O plano com o timbrado em toda página: o slot `even` ou `first` cuja parte não tem'







    novo = dict(plano)
    padrao = {k: p for (k, t, p, _r) in IDENTITY_MAP if t == "default"}
    for kind, typ, parte, _rid in IDENTITY_MAP:
        fonte_padrao = plano.get(padrao[kind])
        if typ == "default" or not fonte_padrao:
            continue
        fonte = plano.get(parte)
        if fonte is None or _peso_parte(os.path.join(ident_dir, fonte)) <= 0:
            novo[parte] = fonte_padrao
    return novo


def copiar_identidade(ident_dir, word_dir, plano=None):
    'Copia o timbrado de `ident_dir` para `word_dir` (a árvore `word/` descompactada):'




    plano = planejar_identidade(ident_dir) if plano is None else plano
    copiados = []
    for alvo in IDENTITY_PARTS:
        fonte = plano.get(alvo)
        if not fonte:
            continue
        shutil.copy(os.path.join(ident_dir, fonte), os.path.join(word_dir, alvo))
        copiados.append(alvo)
        rels = os.path.join(ident_dir, "_rels", f"{fonte}.rels")
        if os.path.isfile(rels):
            os.makedirs(os.path.join(word_dir, "_rels"), exist_ok=True)
            shutil.copy(rels, os.path.join(word_dir, "_rels", f"{alvo}.rels"))
            copiados.append(f"_rels/{alvo}.rels")
    pasta = os.path.join(ident_dir, "media")
    if os.path.isdir(pasta):
        for nome in sorted(os.listdir(pasta)):
            rel = f"media/{nome}"
            if IDENTITY_EXTRA_RE.match(rel):
                os.makedirs(os.path.join(word_dir, "media"), exist_ok=True)
                shutil.copy(os.path.join(pasta, nome), os.path.join(word_dir, "media", nome))
                copiados.append(rel)
    return copiados


def ensure_content_types(work_dir):
    ct_path = os.path.join(work_dir, "[Content_Types].xml")
    with open(ct_path, encoding="utf-8") as f:
        ct = f.read()
    changed = False
    word_dir = os.path.join(work_dir, "word")
    for part in IDENTITY_PARTS:
        if not os.path.exists(os.path.join(word_dir, part)):
            continue
        ctype = CT_HEADER if part.startswith("header") else CT_FOOTER
        if f'PartName="/word/{part}"' not in ct:
            ct = ct.replace("</Types>",
                            f'<Override PartName="/word/{part}" '
                            f'ContentType="{ctype}"/></Types>')
            changed = True




    media_dir = os.path.join(word_dir, "media")
    if os.path.isdir(media_dir):
        for nome in os.listdir(media_dir):
            ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
            ctype = CT_IMAGENS.get(ext)
            if ctype and f'Extension="{ext}"' not in ct:
                ct = ct.replace("</Types>",
                                f'<Default Extension="{ext}" ContentType="{ctype}"/></Types>')
                changed = True
    if changed:
        with open(ct_path, "w", encoding="utf-8") as f:
            f.write(ct)


def _remover_partes_orfas(work_dir, copiados):
    'Tira do pacote as partes de cabeçalho e rodapé que o timbrado do perfil não trouxe'




    word_dir = os.path.join(work_dir, "word")
    manter = {c for c in copiados if re.fullmatch(r"(?:header|footer)\d+\.xml", c)}
    removidas = []
    for nome in sorted(os.listdir(word_dir)):
        if re.fullmatch(r"(?:header|footer)\d+\.xml", nome) and nome not in manter:
            os.remove(os.path.join(word_dir, nome))
            removidas.append(nome)
            rels = os.path.join(word_dir, "_rels", f"{nome}.rels")
            if os.path.isfile(rels):
                os.remove(rels)
    if not removidas:
        return
    ct_path = os.path.join(work_dir, "[Content_Types].xml")
    with open(ct_path, encoding="utf-8") as f:
        ct = f.read()
    for nome in removidas:
        ct = re.sub(r'<Override PartName="/word/' + re.escape(nome) + r'"[^>]*/>', "", ct)
    with open(ct_path, "w", encoding="utf-8") as f:
        f.write(ct)


def inject_header_footer(work_dir, ident_dir=None):
    'Injeta o timbrado completo (cabeçalho e rodapé even/default/first) no docx'









    if ident_dir is None:
        try:
            import perfil_advogado as _pa
        except ImportError:
            raise RuntimeError(
                "TIMBRADO NÃO RESOLVIDO: perfil_advogado.py não está ao lado do núcleo.\n"
                "  A peça NÃO sai sem o timbrado do perfil. Reinstale o plugin para restaurar "
                "os scripts da skill."
            ) from None
        ident_dir = _pa.dir_identidade(_pa.exigir())

    plano = timbrado_em_toda_pagina(planejar_identidade(ident_dir), ident_dir)



    for _p in sorted(set(plano.values())):
        _f = os.path.join(ident_dir, _p)
        if os.path.isfile(_f) and "{{" in open(_f, encoding="utf-8").read():
            raise RuntimeError(
                f"TIMBRADO NÃO RESOLVIDO: {_p} ainda tem placeholder.\n"
                "  A peça NÃO sai com `{{...}}` impresso no rodapé. Configure o perfil do\n"
                "  advogado (modelo em `perfis/exemplo/perfil.json`) ou aponte $DSR_PERFIL."
            )

    word_dir = os.path.join(work_dir, "word")






    copiados = copiar_identidade(ident_dir, word_dir, plano)
    presentes = [(k, t, p, r) for (k, t, p, r) in IDENTITY_MAP if p in copiados]
    if not presentes:
        raise RuntimeError(
            f"PACOTE DE IDENTIDADE SEM TIMBRADO: não há cabeçalho nem rodapé em {ident_dir}.\n"
            "  Envie de novo o timbrado na página Seus dados do conector, a partir de uma "
            "petição que já saiu com o seu cabeçalho ou rodapé."
        )
    _remover_partes_orfas(work_dir, copiados)

    rels_path = os.path.join(word_dir, "_rels", "document.xml.rels")
    with open(rels_path, encoding="utf-8") as f:
        rels = f.read()
    rels = re.sub(r'<Relationship [^>]*Target="(?:header|footer)\d+\.xml"[^>]*/>',
                  "", rels)
    add = ""
    rids = {}
    for kind, typ, part, rid in presentes:
        rel_type = REL_HEADER if kind == "header" else REL_FOOTER
        add += f'<Relationship Id="{rid}" Type="{rel_type}" Target="{part}"/>'
        rids[(kind, typ)] = rid
    rels = rels.replace("</Relationships>", add + "</Relationships>")
    with open(rels_path, "w", encoding="utf-8") as f:
        f.write(rels)

    doc_path = os.path.join(word_dir, "document.xml")
    with open(doc_path, encoding="utf-8") as f:
        doc = f.read()
    doc = re.sub(r"<w:headerReference[^/]*/>", "", doc)
    doc = re.sub(r"<w:footerReference[^/]*/>", "", doc)
    refs = "".join(
        f'<w:{kind}Reference w:type="{typ}" r:id="{rids[(kind, typ)]}"/>'
        for kind, typ, _part, _rid in presentes)
    if "<w:pgSz" in doc:
        doc = doc.replace("<w:pgSz", refs + "<w:pgSz", 1)
    else:
        doc = doc.replace("</w:sectPr>", refs + "</w:sectPr>", 1)
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(doc)
    ensure_content_types(work_dir)
    tem = {k for (k, _t, _p, _r) in presentes}
    print("Timbrado do perfil aplicado ("
          + " e ".join(r for e, r in (("header", "cabeçalho"), ("footer", "rodapé")) if e in tem)
          + " even/default/first).")


def strip_header_footer(work_dir):
    'Remove identidade por completo: referências, partes, relationships'

    doc_path = os.path.join(work_dir, "word", "document.xml")
    with open(doc_path, encoding="utf-8") as f:
        doc = f.read()
    n = len(re.findall(r"<w:(?:header|footer)Reference[^/]*/>", doc))
    doc = re.sub(r"<w:headerReference[^/]*/>", "", doc)
    doc = re.sub(r"<w:footerReference[^/]*/>", "", doc)
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(doc)
    word_dir = os.path.join(work_dir, "word")
    removed = 0
    for f_ in list(os.listdir(word_dir)):
        if re.fullmatch(r"(?:header|footer)\d+\.xml", f_):
            os.remove(os.path.join(word_dir, f_))
            removed += 1
    rels_path = os.path.join(word_dir, "_rels", "document.xml.rels")
    with open(rels_path, encoding="utf-8") as f:
        rels = f.read()
    rels = re.sub(r'<Relationship [^>]*Target="(?:header|footer)\d+\.xml"[^>]*/>',
                  "", rels)
    with open(rels_path, "w", encoding="utf-8") as f:
        f.write(rels)
    ct_path = os.path.join(work_dir, "[Content_Types].xml")
    with open(ct_path, encoding="utf-8") as f:
        ct = f.read()
    ct = re.sub(r'<Override PartName="/word/(?:header|footer)\d+\.xml"[^>]*/>',
                "", ct)
    with open(ct_path, "w", encoding="utf-8") as f:
        f.write(ct)
    if n or removed:
        print(f"Identidade removida: {n} referências, {removed} partes "
              "(modo fragmento).")





def _norm_sectpr(doc):
    """A4 + margens 1440, preservando referências de header/footer."""
    def fix(m):
        s = m.group(0)
        refs = "".join(re.findall(r"<w:(?:header|footer)Reference[^/]*/>", s))
        attrs = re.search(r"<w:sectPr([^>]*)>", s).group(1)
        return (f"<w:sectPr{attrs}>{refs}"
                '<w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"'
                ' w:header="708" w:footer="708" w:gutter="0"/>'
                '<w:cols w:space="720"/><w:docGrid w:linePitch="360"/></w:sectPr>')
    return re.sub(r"<w:sectPr[^>]*>.*?</w:sectPr>", fix, doc, flags=re.DOTALL)


def _norm_styles(work_dir):
    'docDefaults do estilo de corpo resolvido (`_estilo_corpo`: tema em vigor ou perfil;'

    p = os.path.join(work_dir, "word", "styles.xml")
    with open(p, encoding="utf-8") as f:
        st = f.read()
    docdefaults = _docdefaults()


    if "<w:docDefaults>" in st:
        st = re.sub(r"<w:docDefaults>.*?</w:docDefaults>", lambda _m: docdefaults, st,
                    flags=re.DOTALL)
    else:
        st = re.sub(r"(<w:styles[^>]*>)", lambda m: m.group(1) + docdefaults, st, count=1)

    def clean_normal(m):
        s = m.group(0)
        s = re.sub(r"<w:rFonts[^/]*/>", "", s)
        s = re.sub(r'<w:sz\s+w:val="[^"]+"/>', "", s)
        s = re.sub(r'<w:szCs\s+w:val="[^"]+"/>', "", s)
        s = re.sub(r'<w:color\s+w:val="[^"]+"[^/]*/>', "", s)
        return s
    st = re.sub(r'<w:style w:type="paragraph" w:default="1".*?</w:style>',
                clean_normal, st, count=1, flags=re.DOTALL)
    with open(p, "w", encoding="utf-8") as f:
        f.write(st)


def _strip_run_format_overrides(p_xml):
    'Remove rFonts/sz/cor-de-tema dos runs do corpo (herdam docDefaults),'

    def fix(m):
        rpr = m.group(0)
        rpr = re.sub(r"<w:rFonts[^/]*/>", "", rpr)
        rpr = re.sub(r'<w:sz\s+w:val="[^"]+"/>', "", rpr)
        rpr = re.sub(r'<w:szCs\s+w:val="[^"]+"/>', "", rpr)
        rpr = re.sub(r'<w:color\s+w:val="(?:000000|auto|1A1A1A)"[^/]*/>', "", rpr)
        rpr = re.sub(r'<w:lang[^/]*/>', "", rpr)
        return rpr
    return re.sub(r"<w:rPr>.*?</w:rPr>", fix, p_xml, flags=re.DOTALL)


def restyle_body(doc):
    'Aplica o pPr canônico de corpo a todos os parágrafos de texto de'



    tables = []
    def stash(m):
        tables.append(m.group(0))
        return f"\x00TBL{len(tables)-1}\x00"
    doc = re.sub(r"<w:tbl>.*?</w:tbl>", stash, doc, flags=re.DOTALL)

    changed = [0]
    LIST_STYLE = re.compile(r'<w:pStyle w:val="[^"]*(?:List|Lista|PargrafodaLista)[^"]*"', re.I)
    def fix_p(m):
        p = m.group(0)
        if "<w:numPr>" in p or LIST_STYLE.search(p):
            return p
        txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).strip()
        if not txt:
            return p
        pbb = "<w:pageBreakBefore/>" if "<w:pageBreakBefore" in p else ""

        ppr = _body_ppr(True).replace("<w:keepLines/>", "<w:keepLines/>" + pbb)
        new = re.sub(r"<w:pPr>.*?</w:pPr>", "", p, count=1, flags=re.DOTALL)
        new = re.sub(r"(<w:p\b[^>]*>)", r"\1" + ppr, new, count=1)
        new = _strip_run_format_overrides(new)
        changed[0] += 1
        return new
    doc = re.sub(r"<w:p\b[^>]*>.*?</w:p>", fix_p, doc, flags=re.DOTALL)

    for k, t in enumerate(tables):
        doc = doc.replace(f"\x00TBL{k}\x00", t)
    print(f"restyle_body: {changed[0]} parágrafos de corpo normalizados")
    return doc


def fix_quotes_in_text(doc):
    """Aspas retas em todos os nós de texto."""
    def fix(m):
        return m.group(1) + straight_quotes(m.group(2)) + m.group(3)
    return re.sub(r"(<w:t[^>]*>)([^<]*)(</w:t>)", fix, doc)


_RUN_SIMPLES_RX = re.compile(
    r"<w:r>(?:(<w:rPr>.*?</w:rPr>))?<w:t(?:\s[^>]*)?>([^<]*)</w:t></w:r>", re.DOTALL)


def merge_runs_iguais(doc):
    'Junta runs ADJACENTES de formatação IDÊNTICA (mesmo `rPr`, byte a byte) que'







    n = [0]

    def junta(m):
        bloco = m.group(0)
        runs = list(_RUN_SIMPLES_RX.finditer(bloco))
        if len(runs) < 2:
            return bloco
        saida, k = [], 0
        pos = 0
        while k < len(runs):
            r = runs[k]

            if r.start() > pos:
                saida.append(bloco[pos:r.start()])
            rpr = r.group(1) or ""
            texto = r.group(2)
            j = k + 1
            while (j < len(runs) and (runs[j - 1].end() == runs[j].start())
                   and (runs[j].group(1) or "") == rpr):
                texto += runs[j].group(2)
                j += 1
            if j > k + 1:
                n[0] += (j - k - 1)
            saida.append(f'<w:r>{rpr}<w:t xml:space="preserve">{texto}</w:t></w:r>')
            pos = runs[j - 1].end()
            k = j
        saida.append(bloco[pos:])
        return "".join(saida)

    doc = re.sub(r"<w:p\b[^>]*>.*?</w:p>", junta, doc, flags=re.DOTALL)
    if n[0]:
        print(f"merge_runs_iguais: {n[0]} run(s) adjacente(s) de formatação idêntica "
              "unidos (o dado objetivo partido pelo Word volta a ser um trecho só)")
    return doc


def bold_dados_objetivos(doc):
    'Auto-negrito dos dados objetivos (data, valor, fls./item/(Doc. XX), nº de'




    n_fixed = [0]
    def fix_run(m):
        r = m.group(0)
        rpr_m = re.search(r"<w:rPr>.*?</w:rPr>", r, re.DOTALL)
        rpr = rpr_m.group(0) if rpr_m else "<w:rPr></w:rPr>"
        if "<w:b/>" in rpr or "<w:i/>" in rpr:
            return r
        t_m = re.search(r"(<w:t[^>]*>)([^<]*)(</w:t>)", r)
        if not t_m:
            return r
        text = t_m.group(2)
        achados = autobold_matches(text)
        if not achados:
            return r
        rpr_clean = re.sub(r'<w:bC?s?\s+w:val="(?:0|false|none)"\s*/>', "", rpr)
        rpr_b = rpr_clean.replace("<w:rPr>", "<w:rPr><w:b/><w:bCs/>", 1)
        parts, pos = [], 0
        for ini, fim, trecho, _classe in achados:
            pre = text[pos:ini]
            if pre:
                parts.append(f'<w:r>{rpr if rpr_m else ""}<w:t xml:space="preserve">{pre}</w:t></w:r>')
            parts.append(f'<w:r>{rpr_b}<w:t xml:space="preserve">{trecho}</w:t></w:r>')
            pos = fim
        tail = text[pos:]
        if tail:
            parts.append(f'<w:r>{rpr if rpr_m else ""}<w:t xml:space="preserve">{tail}</w:t></w:r>')
        n_fixed[0] += 1
        return "".join(parts)
    doc = re.sub(r"<w:r\b[^>]*>(?:(?!</w:r>).)*?</w:r>", fix_run, doc,
                 flags=re.DOTALL)
    if n_fixed[0]:
        print(f"bold_dados_objetivos: {n_fixed[0]} runs com dado objetivo "
              "(data/valor/fls./item/nº/Doc.) reforçados em negrito")
    return doc


def universal_pass(work_dir, identidade="fragmento"):
    'Normalização determinística do transformer:'





    perfil_up = None
    try:
        import perfil_advogado as _pa
        perfil_up = _pa.carregar()
    except Exception:
        perfil_up = None
    definir_layout(perfil_up)



    definir_tema(perfil_up)
    doc_path = os.path.join(work_dir, "word", "document.xml")
    with open(doc_path, encoding="utf-8") as f:
        doc = f.read()

    doc = _norm_sectpr(doc)
    doc = restyle_body(doc)
    doc = fix_quotes_in_text(doc)
    doc = merge_runs_iguais(doc)
    doc = bold_dados_objetivos(doc)
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(doc)
    _norm_styles(work_dir)
    if identidade == "fragmento":
        strip_header_footer(work_dir)
    elif identidade == "final":
        inject_header_footer(work_dir)

        try:
            import perfil_advogado as _pa
            injetar_brasao(work_dir, _pa.imagem_avulsa(perfil_up, "brasao"))
        except Exception:
            pass
    print(f"universal_pass concluído (identidade: {identidade}).")



def find_paragraph(doc, anchor):
    esc = re.escape(straight_quotes(anchor))
    pat = re.compile(r"<w:p\b[^>]*>(?:(?!</w:p>).)*?" + esc +
                     r"(?:(?!</w:p>).)*?</w:p>", re.DOTALL)
    return pat


def paragraph_text(p_xml):
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p_xml))


def replace_paragraph(doc, anchor, new_xml, count=1):
    """Substitui o(s) parágrafo(s) que contêm a âncora pelo XML dado."""
    pat = find_paragraph(doc, anchor)
    out, n = pat.subn(new_xml.replace("\\", "\\\\"), doc, count)
    if n == 0:
        print(f"AVISO: âncora não encontrada: {anchor[:60]!r}")
    return out


def convert_to_banner(doc, anchor, title, eyebrow=None, trailing_spacer=140):
    return replace_paragraph(doc, anchor, banner(title, eyebrow=eyebrow) +
                             spacer(trailing_spacer))


def convert_to_legend(doc, anchor, label, trailing_spacer=140):
    return replace_paragraph(doc, anchor, legend(label) +
                             spacer(trailing_spacer))


def convert_range_to_box(doc, first_anchor, last_anchor, kind="caixa",
                         trailing_spacer=140):
    'Converte a sequência de parágrafos [first..last] numa caixa.'

    pa = find_paragraph(doc, first_anchor).search(doc)
    pb = find_paragraph(doc, last_anchor).search(doc)
    if not pa or not pb or pb.end() < pa.start():
        print(f"AVISO: intervalo não encontrado: {first_anchor[:40]!r} → "
              f"{last_anchor[:40]!r}")
        return doc
    chunk = doc[pa.start():pb.end()]
    paras_txt = [paragraph_text(p) for p in
                 re.findall(r"<w:p\b[^>]*>.*?</w:p>", chunk, re.DOTALL)]
    paras_txt = [straight_quotes(t).strip() for t in paras_txt if t.strip()]
    if kind == "citacao":
        box = quote_box([("q", t) for t in paras_txt])
    else:
        box = arg_box([md_runs(t) for t in paras_txt])
    return doc[:pa.start()] + box + spacer(trailing_spacer) + doc[pb.end():]


def convert_to_juris(doc, anchor_of_first, items, trailing_spacer=140,
                     consume=1):
    "Substitui o parágrafo âncora (e os 'consume-1' seguintes) pela"

    pat = find_paragraph(doc, anchor_of_first)
    m = pat.search(doc)
    if not m:
        print(f"AVISO: âncora não encontrada: {anchor_of_first[:60]!r}")
        return doc
    start, end = m.start(), m.end()
    for _ in range(consume - 1):
        nxt = re.compile(r"\s*<w:p\b[^>]*>.*?</w:p>", re.DOTALL).match(doc, end)
        if not nxt:
            break
        end = nxt.end()
    return (doc[:start] + juris_box(items) + spacer(trailing_spacer) +
            doc[end:])
