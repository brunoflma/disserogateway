#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'perfil_advogado.py — separa o MOTOR do plugin da CONFIGURAÇÃO de quem o usa.'



















































import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import unicodedata
import zipfile






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



ESTILO_PADRAO = {"fonte": "Arial", "tamanho_meio_pt": 22, "cor": "1A1A1A"}

OBRIGATORIOS = [
    "advogado.nome",
    "advogado.nome_exibicao_cabecalho",
    "advogado.oab",
    "foro.cidade_assinatura",
]



PAGINA_PERFIL_URL = "https://dissero.bfldevlabs.studio/perfil"
MSG_SEM_PERFIL = ("[Dissero] Seus dados ainda não foram preenchidos. "
                  f"Abra {PAGINA_PERFIL_URL}, preencha uma vez e volte. "
                  "Enquanto isso, a peça pode ser preparada, mas não sai com o timbrado.")


PLACEHOLDERS = {
    "{{LINHA_ENDERECO}}": None,
    "{{LINHA_CONTATO}}": None,
    "{{ADVOGADO_NOME}}": "advogado.nome",


    "{{NOME_CABECALHO}}": None,
    "{{OAB}}": "advogado.oab",
    "{{LINHA_OAB}}": None,
    "{{ESCRITORIO}}": "advogado.banca",
    "{{EMAIL}}": "contato.email",
    "{{TELEFONE}}": "contato.telefone",
    "{{CIDADE_ASSINATURA}}": "foro.cidade_assinatura",





    "{{NOME_CABECALHO_SZ}}": None,
    "{{LINHA_ENDERECO_SZ}}": None,
    "{{LINHA_CONTATO_SZ}}": None,
    "{{LINHA_OAB_SZ}}": None,


    "{{TIMBRADO_FONTE}}": None,
    "{{TIMBRADO_TINTA}}": None,
    "{{TIMBRADO_ACENTO}}": None,
    "{{TIMBRADO_FILETE_SZ}}": None,
    "{{TIMBRADO_TRACKING}}": None,




    "{{TIMBRADO_ROTULO_SZ}}": None,
}

ASSETS_COM_PLACEHOLDER = ("header2.xml", "footer2.xml")
ASSETS_TODOS = ("header1.xml", "header2.xml", "header3.xml",
                "footer1.xml", "footer2.xml", "footer3.xml", "mapping.json")

RX_PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")


class PerfilError(Exception):
    """Perfil existe mas está inválido."""


class PerfilAusente(Exception):
    """Nenhum perfil resolvido. Fail-closed: quem produz PEÇA não pode seguir."""


class PerfilDoServidor(PerfilError):
    'O espelho do repositório tentou sobrescrever o perfil que o Dissero serviu.'


















MARCADORES_RAIZ = (".claude-plugin", ".codex-plugin")


def _raiz():
    'Raiz do plugin. Este módulo é vendorizado em skills/*/scripts/, então a busca sobe'

    aqui = os.path.dirname(os.path.abspath(__file__))
    cur = aqui
    for _ in range(5):
        if any(os.path.isdir(os.path.join(cur, m)) for m in MARCADORES_RAIZ):
            return cur
        pai = os.path.dirname(cur)
        if pai == cur:
            break
        cur = pai
    return os.path.dirname(aqui)


def _get(d, caminho, default=None):
    cur = d
    for parte in caminho.split("."):
        if not isinstance(cur, dict) or parte not in cur:
            return default
        cur = cur[parte]
    return cur


def resolver_caminho():
    """Caminho do perfil, ou None. Ver ordem no docstring do módulo."""
    env = (os.environ.get("DSR_PERFIL") or "").strip()
    if env and os.path.isfile(env):
        return env

    perfis = os.path.join(_raiz(), "perfis")
    ident = (os.environ.get("DSR_PERFIL_ID") or "").strip()
    if ident:
        p = os.path.join(perfis, ident, "perfil.json")
        if os.path.isfile(p):
            return p

    if os.path.isdir(perfis):

        candidatos = sorted(
            d for d in os.listdir(perfis)
            if d != "exemplo" and os.path.isfile(os.path.join(perfis, d, "perfil.json"))
        )

        if len(candidatos) == 1:
            return os.path.join(perfis, candidatos[0], "perfil.json")





    espelho = caminho_espelho()
    if os.path.isfile(espelho):
        return espelho

    return None


def carregar(caminho=None):
    """Perfil como dict, ou None se não houver. Não valida — ver validar()."""
    caminho = caminho or resolver_caminho()
    if not caminho or not os.path.isfile(caminho):
        return None



    try:
        with open(caminho, encoding="utf-8") as fh:
            perfil = json.load(fh)
    except json.JSONDecodeError as e:
        raise PerfilError(f"perfil.json malformado ({caminho}): {e}")
    except UnicodeDecodeError:
        raise PerfilError(f"perfil.json não está em UTF-8 ({caminho}); abra o arquivo e salve de novo como UTF-8")
    except OSError as e:
        raise PerfilError(f"perfil.json ilegível ({caminho}): {e.strerror or type(e).__name__}")
    if not isinstance(perfil, dict):
        raise PerfilError(f"perfil.json não é um objeto JSON ({caminho})")
    perfil["_caminho"] = os.path.abspath(caminho)
    return perfil















_RX_TOKEN = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:dsrr_[0-9a-f]{64}|(?:llx-|sk-|AIza|GOCSPX-|ya29\.|ghp_|xox[abp]-|1//)[A-Za-z0-9_\-]{8,})")



_RX_CHAVE_LICENCA = re.compile(
    r"\b(?:AMF|DSR)[\s-]?[A-HJ-KM-NP-Z2-9]{4}[\s-]?[A-HJ-KM-NP-Z2-9]{4}[\s-]?[A-HJ-KM-NP-Z2-9]{4}\b", re.I)


def _procurar_token(o, caminho=""):
    'Os caminhos do perfil onde ha algo com cara de token. PURA.'



    if isinstance(o, dict):
        for k, v in o.items():
            yield from _procurar_token(v, f"{caminho}.{k}" if caminho else str(k))
    elif isinstance(o, (list, tuple)):
        for i, v in enumerate(o):
            yield from _procurar_token(v, f"{caminho}[{i}]")
    elif isinstance(o, str) and (_RX_TOKEN.search(o) or _RX_CHAVE_LICENCA.search(o)):
        yield caminho or "(raiz)"











FAIXAS_LAYOUT = {
    "pagina": {"largura": (8000, 24000), "altura": (8000, 24000), "orientacao": ("retrato", "paisagem")},
    "margens": {"sup": (567, 2835), "inf": (567, 2835), "esq": (567, 2835), "dir": (567, 2835),
                "cabecalho": (0, 2835), "rodape": (0, 2835)},
    "paragrafo": {"entrelinha": (240, 480), "antes": (0, 720), "depois": (0, 720),
                  "recuo_primeira": (0, 2835), "alinhamento": ("left", "both", "center", "right")},
    "titulos": {"fonte": "fonte"},
}

_RX_FONTE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9 .\-]{1,64}")




LAYOUT_PADRAO = {
    "pagina": {"largura": 11906, "altura": 16838, "orientacao": "retrato"},
    "margens": {"sup": 1440, "inf": 1440, "esq": 1440, "dir": 1440, "cabecalho": 708, "rodape": 708},
}


def _inteiro(v):
    'Inteiro como o JavaScript o vê depois do JSON.parse: `1701` e `1701.0` são o mesmo número'

    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


def validar_layout(layout):
    """None se válido; senão o CAMPO recusado (mesma string que `validarLayout` devolve)."""
    if not isinstance(layout, dict):
        return "layout"
    for k in layout:
        if k != "versao" and k not in FAIXAS_LAYOUT:
            return k
    if _inteiro(layout.get("versao")) != 1:
        return "versao"
    for bloco, regras in FAIXAS_LAYOUT.items():
        if bloco not in layout:
            continue
        b = layout[bloco]
        if not isinstance(b, dict):
            return bloco
        for k in b:
            if k not in regras:
                return f"{bloco}.{k}"
        for k, regra in regras.items():
            if k not in b:
                continue
            v = b[k]
            campo = f"{bloco}.{k}"
            if regra == "fonte":
                if not isinstance(v, str) or not _RX_FONTE.fullmatch(v):
                    return campo
                continue
            if isinstance(regra[0], str):
                if not isinstance(v, str) or v not in regra:
                    return campo
                continue
            n = _inteiro(v)
            if n is None or not (regra[0] <= n <= regra[1]):
                return campo
    p = layout.get("pagina")
    if isinstance(p, dict) and p.get("orientacao"):
        larg, alt = _inteiro(p.get("largura")), _inteiro(p.get("altura"))
        if larg is not None and alt is not None and (p["orientacao"] == "retrato") != (larg <= alt):
            return "pagina.orientacao"
    return None







_HEX = re.compile(r"^[0-9A-Fa-f]{6}\Z")
_NOME_TEMA = re.compile(r"^[a-z][a-z0-9-]{1,31}\Z")
_VARIANTES = ("preenchido", "contornado", "filete")
FICHAS_TEMA = ("tinta", "legenda", "argumento_fundo", "argumento_barra",
               "juris_fundo", "juris_barra", "versalete", "capa_subtitulo", "acento")


_SZ_TIPOGRAFIA = (12, 96)



_SZ_ESPESSURA = (0, 96)
FAIXAS_TEMA = {
    "capitulo": {"variante": _VARIANTES, "filete_sup_sz": (0, 96), "filete_inf_sz": (0, 96),
                 "titulo_sz": (16, 72), "rotulo_sz": (12, 48), "rotulo_spacing": (0, 200),
                 "antes": (0, 720)},
    "capa": {"regua_sz": _SZ_ESPESSURA, "regua_fina_sz": _SZ_ESPESSURA},
    "contorno": {"sz": _SZ_ESPESSURA},
    "elementos": {"legenda": _VARIANTES, "capa": _VARIANTES, "argumento": _VARIANTES,
                  "jurisprudencia": _VARIANTES, "comparativa": _VARIANTES},
    "tipografia": {"fonte": "fonte", "corpo_sz": _SZ_TIPOGRAFIA, "capa_titulo_sz": _SZ_TIPOGRAFIA,
                   "capa_subtitulo_sz": _SZ_TIPOGRAFIA, "legenda_sz": _SZ_TIPOGRAFIA,
                   "versalete_sz": _SZ_TIPOGRAFIA},
}


def validar_tema(tema):
    """None se válido; senão o CAMPO recusado (mesma string que `validarTema` devolve)."""
    if not isinstance(tema, dict):
        return "tema"
    for k in tema:
        if k not in ("versao", "nome", "fichas") and k not in FAIXAS_TEMA:
            return k
    if _inteiro(tema.get("versao")) != 1:
        return "versao"
    nome = tema.get("nome")
    if not isinstance(nome, str) or not _NOME_TEMA.match(nome):
        return "nome"
    if "fichas" in tema:
        fichas = tema["fichas"]
        if not isinstance(fichas, dict):
            return "fichas"
        for k, v in fichas.items():
            if k not in FICHAS_TEMA or not isinstance(v, str) or not _HEX.match(v):
                return f"fichas.{k}"
    for bloco, regras in FAIXAS_TEMA.items():
        if bloco not in tema:
            continue
        b = tema[bloco]
        if not isinstance(b, dict):
            return bloco
        for k in b:
            if k not in regras:
                return f"{bloco}.{k}"
        for k, regra in regras.items():
            if k not in b:
                continue
            v = b[k]
            campo = f"{bloco}.{k}"
            if regra == "fonte":
                if not isinstance(v, str) or not _RX_FONTE.fullmatch(v):
                    return campo
                continue
            if isinstance(regra[0], str):
                if v not in regra:
                    return campo
                continue
            n = _inteiro(v)
            if n is None or not (regra[0] <= n <= regra[1]):
                return campo
    return tema_sem_contraste(tema)




_PAPEL = "FFFFFF"










_CHAPAS_COM_TEXTO = (
    (("capitulo", "variante"), "tinta", None, "fichas.tinta"),
    (("elementos", "legenda"), "legenda", "tinta", "fichas.legenda"),
    (("elementos", "capa"), "legenda", "tinta", "fichas.legenda"),
    (("elementos", "argumento"), "argumento_fundo", "tinta", "fichas.argumento_fundo"),
    (("elementos", "jurisprudencia"), "juris_fundo", "tinta", "fichas.juris_fundo"),
)


def tema_sem_contraste(tema):
    """O CAMPO recusado por contraste, ou None. Fina sobre `detalhe_contraste_do_tema`."""
    d = detalhe_contraste_do_tema(tema)
    return None if d is None else d["campo"]


def detalhe_contraste_do_tema(tema):
    'None se as cores do tema sustentam o contraste mínimo; senão um dicionário com'















    if not isinstance(tema, dict):
        return None
    fichas = tema.get("fichas")
    if not isinstance(fichas, dict):
        return None
    tinta = fichas.get("tinta")
    if isinstance(tinta, str) and _HEX.match(tinta):
        r = _cw.contraste_hex(tinta, _PAPEL)
        if r is not None and r < _cw.MINIMO_TEXTO:
            return {"campo": "fichas.tinta", "cor": tinta.upper(), "sobre": _PAPEL,
                    "razao": r, "minimo": _cw.MINIMO_TEXTO}
    for (bloco, chave), ficha_chapa, ficha_tinta, campo in _CHAPAS_COM_TEXTO:
        b = tema.get(bloco)
        if not isinstance(b, dict) or b.get(chave) != "preenchido":
            continue
        chapa = fichas.get(ficha_chapa)
        sobre = _PAPEL if ficha_tinta is None else fichas.get(ficha_tinta)
        if not (isinstance(chapa, str) and _HEX.match(chapa)):
            continue
        if not (isinstance(sobre, str) and _HEX.match(sobre)):
            continue
        r = _cw.contraste_hex(chapa, sobre)
        if r is not None and r < _cw.MINIMO_COMPONENTE:
            return {"campo": campo, "cor": chapa.upper(), "sobre": sobre.upper(),
                    "razao": r, "minimo": _cw.MINIMO_COMPONENTE}
    return None



















_MIGRACAO_TEMA = (
    ("capa", "regua_sz", None),
    ("capa", "regua_fina_sz", ("capitulo", "filete_inf_sz")),
    ("contorno", "sz", None),
)
_MIGRAVEIS = frozenset((bloco, chave) for bloco, chave, _ in _MIGRACAO_TEMA)


def migrar_tema(tema, embarcado):
    'Tema com os campos de `_MIGRACAO_TEMA` completados a partir de `embarcado` (o tema do'









    if not isinstance(tema, dict) or not isinstance(embarcado, dict):
        return tema
    novo = None
    for bloco, chave, origem in _MIGRACAO_TEMA:
        b = tema.get(bloco)
        if isinstance(b, dict) and chave in b:
            continue
        if origem is not None and isinstance(tema.get(origem[0]), dict) \
                and origem[1] in tema[origem[0]]:
            valor = tema[origem[0]][origem[1]]
        else:
            emb = embarcado.get(bloco)
            if not isinstance(emb, dict) or chave not in emb:
                continue
            valor = emb[chave]
        if novo is None:
            novo = dict(tema)
        atual = novo.get(bloco)
        novo[bloco] = dict(atual) if isinstance(atual, dict) else {}
        novo[bloco][chave] = valor
    return tema if novo is None else novo


def tema_sem_campos_novos(tema):
    'None se `tema` já traz os campos de `_MIGRACAO_TEMA`; senão o primeiro que falta'




    if not isinstance(tema, dict):
        return "tema"
    for bloco, chave, _origem in _MIGRACAO_TEMA:
        b = tema.get(bloco)
        if not isinstance(b, dict) or chave not in b:
            return f"{bloco}.{chave}"
    return None


def tema_incompleto(tema):
    'None se `tema` traz TODO campo que o construtor lê (fichas, capítulo, elementos e'















    if not isinstance(tema, dict):
        return "tema"
    fichas = tema.get("fichas")
    if not isinstance(fichas, dict):
        return "fichas"
    for k in FICHAS_TEMA:
        if k not in fichas:
            return f"fichas.{k}"
    for bloco, regras in FAIXAS_TEMA.items():
        exigidas = [k for k in regras if (bloco, k) not in _MIGRAVEIS]
        if not exigidas:
            continue
        b = tema.get(bloco)
        if not isinstance(b, dict):
            return bloco
        for k in exigidas:
            if k not in b:
                return f"{bloco}.{k}"
    return None


def layout(perfil=None):
    'Layout efetivo: o do perfil por cima do gabarito Dissero. Layout inválido é ignorado inteiro'

    efetivo = {k: dict(v) for k, v in LAYOUT_PADRAO.items()}
    lay = _get(perfil, "identidade_visual.layout") if isinstance(perfil, dict) else None
    if lay is None or validar_layout(lay) is not None:
        return efetivo
    for bloco in FAIXAS_LAYOUT:
        if isinstance(lay.get(bloco), dict):
            efetivo.setdefault(bloco, {}).update(
                {k: (_inteiro(v) if _inteiro(v) is not None else v) for k, v in lay[bloco].items()})
    return efetivo














_NOME_DO_CAMPO = {
    "advogado.nome": "o seu nome completo",
    "advogado.nome_exibicao_cabecalho": "o seu nome como sai no cabeçalho",
    "advogado.oab": "a sua inscrição na OAB",
    "foro.cidade_assinatura": "a cidade onde você assina",
    "preferencias_operacionais.margem_protocolo_dias_uteis":
        "a margem de dias úteis antes do protocolo",
    "identidade_visual.cor_texto_hex": "a cor do texto do escritório",
    "identidade_visual.tamanho_corpo_pt": "o tamanho da letra do corpo",
    "identidade_visual.layout": "as medidas de página do escritório",
    "identidade_visual.tema": "o tema visual do escritório",
}


def _nome_do_campo(caminho):
    'Nome em português do campo, ou o próprio caminho quando não houver — e não haver é'


    return _NOME_DO_CAMPO.get(caminho, caminho)


def validar(perfil):
    'Lista de erros (vazia = válido). As mensagens são para o ADVOGADO: nomeiam o campo'

    erros = []
    if not isinstance(perfil, dict):
        return ["perfil não é um objeto JSON"]
    for campo in OBRIGATORIOS:
        v = _get(perfil, campo)
        if v is None or (isinstance(v, str) and not v.strip()):
            erros.append(f"falta preencher: {_nome_do_campo(campo)}")


    def _tipo_em_portugues(v):
        if v is None:
            return "vazio"
        if isinstance(v, bool):
            return "verdadeiro/falso"
        if isinstance(v, (int, float)):
            return "número"
        if isinstance(v, list):
            return "lista"
        if isinstance(v, dict):
            return "bloco de campos"
        return "outro tipo de dado"

    def _descrever_campo_layout(campo):
        if "." in campo:
            bloco, folha = campo.split(".", 1)
            return f"«{folha}» em «{bloco}»"
        return f"«{campo}»"

    _oab_nome = _nome_do_campo("advogado.oab")
    oab = _get(perfil, "advogado.oab", "") or ""
    if not isinstance(oab, str):

        erros.append(f"{_oab_nome} deve ser texto (ex.: 'OAB/SP 000.000-X'), e veio como "
                     f"{_tipo_em_portugues(oab)}")
    elif oab and "OAB" not in oab.upper():
        erros.append(f"{_oab_nome} deveria conter 'OAB' (ex.: 'OAB/SP 000.000-X')")

    margem = _get(perfil, "preferencias_operacionais.margem_protocolo_dias_uteis")
    if margem is not None and (not isinstance(margem, bool)) and not (isinstance(margem, int) and margem >= 0):
        erros.append(f"{_nome_do_campo('preferencias_operacionais.margem_protocolo_dias_uteis')}"
                     f" deve ser um número inteiro de dias, zero ou mais")

    cor = _get(perfil, "identidade_visual.cor_texto_hex") or ""
    if not isinstance(cor, str) or (cor.lstrip("#")
                                    and not _HEX.match(cor.lstrip("#"))):
        erros.append(f"{_nome_do_campo('identidade_visual.cor_texto_hex')} deve ser hex de "
                     f"6 dígitos (ex.: '1A1A1A')")
    else:


        _r = _cw.contraste_hex(cor.lstrip("#"), _PAPEL) if cor else None
        if _r is not None and _r < _cw.MINIMO_TEXTO:
            erros.append(f"{_nome_do_campo('identidade_visual.cor_texto_hex')} está clara "
                         f"demais para o papel branco: '{cor.lstrip('#').upper()}' rende "
                         f"contraste de {_r:.1f} para 1, e o mínimo legível é "
                         f"{_cw.MINIMO_TEXTO:.1f} para 1. Escolha uma cor mais escura")

    tam = _get(perfil, "identidade_visual.tamanho_corpo_pt")
    if tam is not None and not (isinstance(tam, (int, float)) and 6 <= tam <= 24):
        erros.append(f"{_nome_do_campo('identidade_visual.tamanho_corpo_pt')} está fora da "
                     f"faixa razoável (6 a 24)")

    lay = _get(perfil, "identidade_visual.layout")
    if lay is not None:
        campo = validar_layout(lay)
        if campo is not None:


            erros.append(f"{_nome_do_campo('identidade_visual.layout')}: "
                         f"{_descrever_campo_layout(campo)} fora do esquema ou da faixa aceita")





    tema = _get(perfil, "identidade_visual.tema")
    if tema is not None:
        campo = validar_tema(tema)
        if campo is None:
            campo = tema_incompleto(tema)
        det = detalhe_contraste_do_tema(tema)
        if det is not None and det["campo"] == campo:


            erros.append(f"{_nome_do_campo('identidade_visual.tema')}: a cor "
                         f"'{det['cor']}' some sobre '{det['sobre']}' — rende contraste de "
                         f"{det['razao']:.1f} para 1, e o mínimo é {det['minimo']:.1f} para 1. "
                         f"Peça ao operador do escritório para escolher uma cor mais escura "
                         f"para o tema do seu perfil")
        elif campo is not None:



            erros.append(f"{_nome_do_campo('identidade_visual.tema')}: '{campo}' inválido ou "
                         f"incompleto — a peça não sai com o timbrado enquanto o tema estiver "
                         f"assim. Peça ao operador do escritório para reinstalar o tema no "
                         f"seu perfil")






    for caminho in _procurar_token(perfil):
        erros.append(f"SEGURANÇA: {caminho} parece conter um TOKEN — remova; chave vive "
                     f"no dsr_credenciais.env, nunca no perfil")
    return erros


def _remedio():
    'Uma resposta só, em qualquer superfície: o lugar onde o perfil se preenche. Mandar'


    return "  " + MSG_SEM_PERFIL


def exigir(caminho=None):
    """Perfil válido, ou levanta. Ponto fail-closed de quem produz PEÇA."""
    perfil = carregar(caminho)
    if perfil is None:
        raise PerfilAusente(
            "PERFIL DO ADVOGADO NÃO RESOLVIDO — a peça não sai.\n"
            "  Sem perfil, o timbrado sairia genérico e o defeito só apareceria depois de\n"
            "  protocolado.\n" + _remedio()
        )
    erros = validar(perfil)
    if erros:
        raise PerfilError("perfil inválido:\n  - " + "\n  - ".join(erros))
    if divergente(perfil):
        raise PerfilError("cópia divergente do servidor — chame perfil_do_advogado de novo e "
                          "grave com --gravar-do-servidor")
    return perfil








_RX_USO_PRIVADO = re.compile(r"[\ue000-\uf8ff\U000f0000-\U0010ffff]")


def _texto_do_perfil(valor):
    '`str()` + `strip()` + sem caractere de uso privado: a forma em que TODO campo do'

    return _RX_USO_PRIVADO.sub("", str(valor if valor is not None else "")).strip()





def montar_linha_oab(perfil):
    return f"Advogado(a) · {_texto_do_perfil(_get(perfil, 'advogado.oab', '') or '')}".strip()


def _juntar(partes, sep):
    'Junta só o que existe. É o coração da correção do rodapé: a pontuação vive ENTRE'

    return sep.join(p for p in (_texto_do_perfil(x or "") for x in partes) if p)


def montar_linha_endereco(perfil):
    '`<endereço> – <cidade/UF>, CEP <cep>`, montada só com o que o perfil tem.'



    lugar = _juntar([_get(perfil, "contato.endereco"), _get(perfil, "contato.cidade_uf")], " – ")
    cep = _texto_do_perfil(_get(perfil, "contato.cep") or "")
    return _juntar([lugar, f"CEP {cep}" if cep else ""], ", ")


def montar_linha_contato(perfil):
    '`e-mail: <email> – fone: <telefone>`, idem: sem e-mail, some o rótulo junto.'








    email = _texto_do_perfil(_get(perfil, "contato.email") or "")
    fone = _texto_do_perfil(_get(perfil, "contato.telefone") or "")
    return _juntar([f"{_ROTULO_EMAIL}{email}" if email else "",
                    f"{_ROTULO_FONE}{fone}" if fone else ""], " – ")




_ROTULO_EMAIL = "e-mail:\xa0"
_ROTULO_FONE = "fone:\xa0"


























_MARGEM_SEGURANCA = 1.03




_LARGURA_ARIAL_BOLD = {
    ' ': 0.2778, '!': 0.333, '"': 0.4741, '#': 0.5562, '%': 0.8892, '&': 0.7222, "'": 0.2378,
    '(': 0.333, ')': 0.333, '*': 0.3892, '+': 0.584, ',': 0.2778, '-': 0.333, '.': 0.2778,
    '/': 0.2778, '0': 0.5562, '1': 0.5562, '2': 0.5562, '3': 0.5562, '4': 0.5562, '5': 0.5562,
    '6': 0.5562, '7': 0.5562, '8': 0.5562, '9': 0.5562, ':': 0.333, ';': 0.333, '?': 0.6108,
    '@': 0.9751, 'A': 0.7222, 'B': 0.7222, 'C': 0.7222, 'D': 0.7222, 'E': 0.667, 'F': 0.6108,
    'G': 0.7778, 'H': 0.7222, 'I': 0.2778, 'J': 0.5562, 'K': 0.7222, 'L': 0.6108, 'M': 0.833,
    'N': 0.7222, 'O': 0.7778, 'P': 0.667, 'Q': 0.7778, 'R': 0.7222, 'S': 0.667, 'T': 0.6108,
    'U': 0.7222, 'V': 0.667, 'W': 0.9438, 'X': 0.667, 'Y': 0.667, 'Z': 0.6108, '[': 0.333,
    ']': 0.333, '_': 0.5562, 'a': 0.5562, 'b': 0.6108, 'c': 0.5562, 'd': 0.6108, 'e': 0.5562,
    'f': 0.333, 'g': 0.6108, 'h': 0.6108, 'i': 0.2778, 'j': 0.2778, 'k': 0.5562, 'l': 0.2778,
    'm': 0.8892, 'n': 0.6108, 'o': 0.6108, 'p': 0.6108, 'q': 0.6108, 'r': 0.3892, 's': 0.5562,
    't': 0.333, 'u': 0.6108, 'v': 0.5562, 'w': 0.7778, 'x': 0.5562, 'y': 0.5562, 'z': 0.5,
    '{': 0.3892, '}': 0.3892, '\xa0': 0.2778, 'ª': 0.3701, 'º': 0.3652, 'À': 0.7222,
    'Á': 0.7222, 'Â': 0.7222, 'Ã': 0.7222, 'Ä': 0.7222, 'Ç': 0.7222, 'È': 0.667, 'É': 0.667,
    'Ê': 0.667, 'Ë': 0.667, 'Ì': 0.2778, 'Í': 0.2778, 'Î': 0.2778, 'Ï': 0.2778, 'Ñ': 0.7222,
    'Ò': 0.7778, 'Ó': 0.7778, 'Ô': 0.7778, 'Õ': 0.7778, 'Ö': 0.7778, 'Ù': 0.7222, 'Ú': 0.7222,
    'Û': 0.7222, 'Ü': 0.7222, 'à': 0.5562, 'á': 0.5562, 'â': 0.5562, 'ã': 0.5562, 'ä': 0.5562,
    'ç': 0.5562, 'è': 0.5562, 'é': 0.5562, 'ê': 0.5562, 'ë': 0.5562, 'ì': 0.2778, 'í': 0.2778,
    'î': 0.2778, 'ï': 0.2778, 'ñ': 0.6108, 'ò': 0.6108, 'ó': 0.6108, 'ô': 0.6108, 'õ': 0.6108,
    'ö': 0.6108, 'ù': 0.6108, 'ú': 0.6108, 'û': 0.6108, 'ü': 0.6108, '–': 0.5562, '—': 1.0,
}
_FALLBACK_ARIAL_BOLD = max(_LARGURA_ARIAL_BOLD.values())






_LARGURA_CAMBRIA = {
    ' ': 0.2202, '!': 0.2856, '"': 0.3931, '#': 0.6191, '%': 0.8896, '&': 0.6875, "'": 0.2368,
    '(': 0.3818, ')': 0.3818, '*': 0.4272, '+': 0.5537, ',': 0.2051, '-': 0.332, '.': 0.2051,
    '/': 0.4902, '0': 0.5537, '1': 0.5537, '2': 0.5537, '3': 0.5537, '4': 0.5537, '5': 0.5537,
    '6': 0.5537, '7': 0.5537, '8': 0.5537, '9': 0.5537, ':': 0.2637, ';': 0.2637, '?': 0.4224,
    '@': 0.8853, 'A': 0.623, 'B': 0.6113, 'C': 0.5625, 'D': 0.6616, 'E': 0.5752, 'F': 0.5366,
    'G': 0.6108, 'H': 0.6865, 'I': 0.3242, 'J': 0.3066, 'K': 0.6294, 'L': 0.5366, 'M': 0.8154,
    'N': 0.6807, 'O': 0.6533, 'P': 0.5679, 'Q': 0.6533, 'R': 0.6211, 'S': 0.4961, 'T': 0.5928,
    'U': 0.6479, 'V': 0.6035, 'W': 0.9214, 'X': 0.5713, 'Y': 0.5703, 'Z': 0.5376, '[': 0.3501,
    ']': 0.3501, '_': 0.3706, 'a': 0.4883, 'b': 0.5474, 'c': 0.4409, 'd': 0.5547, 'e': 0.4878,
    'f': 0.3027, 'g': 0.4941, 'h': 0.5518, 'i': 0.2778, 'j': 0.2661, 'k': 0.5244, 'l': 0.2715,
    'm': 0.832, 'n': 0.5581, 'o': 0.5308, 'p': 0.5562, 'q': 0.5469, 'r': 0.4136, 's': 0.4297,
    't': 0.3384, 'u': 0.5522, 'v': 0.5039, 'w': 0.7744, 'x': 0.4834, 'y': 0.5039, 'z': 0.4546,
    '{': 0.3872, '}': 0.3872, '\xa0': 0.2202, 'ª': 0.417, 'º': 0.4277, 'À': 0.623, 'Á': 0.623,
    'Â': 0.623, 'Ã': 0.623, 'Ä': 0.623, 'Ç': 0.5625, 'È': 0.5752, 'É': 0.5752, 'Ê': 0.5752,
    'Ë': 0.5752, 'Ì': 0.3242, 'Í': 0.3242, 'Î': 0.3242, 'Ï': 0.3242, 'Ñ': 0.6807, 'Ò': 0.6533,
    'Ó': 0.6533, 'Ô': 0.6533, 'Õ': 0.6533, 'Ö': 0.6533, 'Ù': 0.6479, 'Ú': 0.6479, 'Û': 0.6479,
    'Ü': 0.6479, 'à': 0.4883, 'á': 0.4883, 'â': 0.4883, 'ã': 0.4883, 'ä': 0.4883, 'ç': 0.4409,
    'è': 0.4878, 'é': 0.4878, 'ê': 0.4878, 'ë': 0.4878, 'ì': 0.2778, 'í': 0.2778, 'î': 0.2778,
    'ï': 0.2778, 'ñ': 0.5581, 'ò': 0.5308, 'ó': 0.5308, 'ô': 0.5308, 'õ': 0.5308, 'ö': 0.5308,
    'ù': 0.5522, 'ú': 0.5522, 'û': 0.5522, 'ü': 0.5522, '–': 0.5, '—': 1.0, '·': 0.2822,
    '•': 0.4434,
}
_FALLBACK_CAMBRIA = max(_LARGURA_CAMBRIA.values())


_LARGURA_ARIAL = {
    ' ': 0.2778, '!': 0.2778, '"': 0.355, '#': 0.5562, '%': 0.8892, '&': 0.667, "'": 0.1909,
    '(': 0.333, ')': 0.333, '*': 0.3892, '+': 0.584, ',': 0.2778, '-': 0.333, '.': 0.2778,
    '/': 0.2778, '0': 0.5562, '1': 0.5562, '2': 0.5562, '3': 0.5562, '4': 0.5562, '5': 0.5562,
    '6': 0.5562, '7': 0.5562, '8': 0.5562, '9': 0.5562, ':': 0.2778, ';': 0.2778, '?': 0.5562,
    '@': 1.0151, 'A': 0.667, 'B': 0.667, 'C': 0.7222, 'D': 0.7222, 'E': 0.667, 'F': 0.6108,
    'G': 0.7778, 'H': 0.7222, 'I': 0.2778, 'J': 0.5, 'K': 0.667, 'L': 0.5562, 'M': 0.833,
    'N': 0.7222, 'O': 0.7778, 'P': 0.667, 'Q': 0.7778, 'R': 0.7222, 'S': 0.667, 'T': 0.6108,
    'U': 0.7222, 'V': 0.667, 'W': 0.9438, 'X': 0.667, 'Y': 0.667, 'Z': 0.6108, '[': 0.2778,
    ']': 0.2778, '_': 0.5562, 'a': 0.5562, 'b': 0.5562, 'c': 0.5, 'd': 0.5562, 'e': 0.5562,
    'f': 0.2778, 'g': 0.5562, 'h': 0.5562, 'i': 0.2222, 'j': 0.2222, 'k': 0.5, 'l': 0.2222,
    'm': 0.833, 'n': 0.5562, 'o': 0.5562, 'p': 0.5562, 'q': 0.5562, 'r': 0.333, 's': 0.5,
    't': 0.2778, 'u': 0.5562, 'v': 0.5, 'w': 0.7222, 'x': 0.5, 'y': 0.5, 'z': 0.5, '{': 0.334,
    '}': 0.334, '\xa0': 0.2778, 'ª': 0.3701, 'º': 0.3652, 'À': 0.667, 'Á': 0.667, 'Â': 0.667,
    'Ã': 0.667, 'Ä': 0.667, 'Ç': 0.7222, 'È': 0.667, 'É': 0.667, 'Ê': 0.667, 'Ë': 0.667,
    'Ì': 0.2778, 'Í': 0.2778, 'Î': 0.2778, 'Ï': 0.2778, 'Ñ': 0.7222, 'Ò': 0.7778, 'Ó': 0.7778,
    'Ô': 0.7778, 'Õ': 0.7778, 'Ö': 0.7778, 'Ù': 0.7222, 'Ú': 0.7222, 'Û': 0.7222, 'Ü': 0.7222,
    'à': 0.5562, 'á': 0.5562, 'â': 0.5562, 'ã': 0.5562, 'ä': 0.5562, 'ç': 0.5, 'è': 0.5562,
    'é': 0.5562, 'ê': 0.5562, 'ë': 0.5562, 'ì': 0.2778, 'í': 0.2778, 'î': 0.2778, 'ï': 0.2778,
    'ñ': 0.5562, 'ò': 0.5562, 'ó': 0.5562, 'ô': 0.5562, 'õ': 0.5562, 'ö': 0.5562, 'ù': 0.5562,
    'ú': 0.5562, 'û': 0.5562, 'ü': 0.5562, '–': 0.5562, '—': 1.0, '·': 0.333, '•': 0.3501,
}
_FALLBACK_ARIAL = max(_LARGURA_ARIAL.values())


_LARGURA_CALIBRI = {
    ' ': 0.2261, '!': 0.3257, '"': 0.4009, '#': 0.498, '%': 0.7148, '&': 0.6821, "'": 0.2207,
    '(': 0.3032, ')': 0.3032, '*': 0.498, '+': 0.498, ',': 0.2495, '-': 0.3062, '.': 0.2524,
    '/': 0.3862, '0': 0.5068, '1': 0.5068, '2': 0.5068, '3': 0.5068, '4': 0.5068, '5': 0.5068,
    '6': 0.5068, '7': 0.5068, '8': 0.5068, '9': 0.5068, ':': 0.2676, ';': 0.2676, '?': 0.4634,
    '@': 0.894, 'A': 0.5786, 'B': 0.5439, 'C': 0.5332, 'D': 0.6152, 'E': 0.4883, 'F': 0.4595,
    'G': 0.6309, 'H': 0.623, 'I': 0.252, 'J': 0.3188, 'K': 0.5195, 'L': 0.4204, 'M': 0.855,
    'N': 0.6455, 'O': 0.6621, 'P': 0.5166, 'Q': 0.6729, 'R': 0.543, 'S': 0.4595, 'T': 0.4873,
    'U': 0.6416, 'V': 0.5674, 'W': 0.8896, 'X': 0.519, 'Y': 0.4873, 'Z': 0.4683, '[': 0.3066,
    ']': 0.3066, '_': 0.498, 'a': 0.479, 'b': 0.5254, 'c': 0.4229, 'd': 0.5254, 'e': 0.4976,
    'f': 0.3052, 'g': 0.4707, 'h': 0.5254, 'i': 0.2295, 'j': 0.2393, 'k': 0.4546, 'l': 0.2295,
    'm': 0.7988, 'n': 0.5254, 'o': 0.5273, 'p': 0.5254, 'q': 0.5254, 'r': 0.3486, 's': 0.3911,
    't': 0.335, 'u': 0.5254, 'v': 0.4517, 'w': 0.7148, 'x': 0.4331, 'y': 0.4526, 'z': 0.395,
    '{': 0.3145, '}': 0.3145, '\xa0': 0.2261, 'ª': 0.4023, 'º': 0.4224, 'À': 0.5786,
    'Á': 0.5786, 'Â': 0.5786, 'Ã': 0.5786, 'Ä': 0.5786, 'Ç': 0.5332, 'È': 0.4883, 'É': 0.4883,
    'Ê': 0.4883, 'Ë': 0.4883, 'Ì': 0.252, 'Í': 0.252, 'Î': 0.252, 'Ï': 0.252, 'Ñ': 0.6455,
    'Ò': 0.6621, 'Ó': 0.6621, 'Ô': 0.6621, 'Õ': 0.6621, 'Ö': 0.6621, 'Ù': 0.6416, 'Ú': 0.6416,
    'Û': 0.6416, 'Ü': 0.6416, 'à': 0.479, 'á': 0.479, 'â': 0.479, 'ã': 0.479, 'ä': 0.479,
    'ç': 0.4229, 'è': 0.4976, 'é': 0.4976, 'ê': 0.4976, 'ë': 0.4976, 'ì': 0.2295, 'í': 0.2295,
    'î': 0.2295, 'ï': 0.2295, 'ñ': 0.5254, 'ò': 0.5273, 'ó': 0.5273, 'ô': 0.5273, 'õ': 0.5273,
    'ö': 0.5273, 'ù': 0.5254, 'ú': 0.5254, 'û': 0.5254, 'ü': 0.5254, '–': 0.498, '—': 0.9053,
    '·': 0.2524, '•': 0.498,
}
_FALLBACK_CALIBRI = max(_LARGURA_CALIBRI.values())









_PISO_SZ_RODAPE = 18
_DEGRAU_SZ = 2






_TRACKING_TIMBRADO = 20






_FILETE_SZ_MIN, _FILETE_SZ_MAX = 2, 12





_TIMBRADO_PADRAO = {"fonte": "Cambria", "nome_sz": 30, "rotulo_sz": 21, "corpo_sz": 24,
                    "filete_sz": 6, "tinta": "1A1A1A", "acento": "1F3864"}



_TABELAS_FONTE = {"cambria": (_LARGURA_CAMBRIA, _FALLBACK_CAMBRIA),
                  "arial": (_LARGURA_ARIAL, _FALLBACK_ARIAL),
                  "calibri": (_LARGURA_CALIBRI, _FALLBACK_CALIBRI)}


def _tabela_da_fonte(fonte):
    return _TABELAS_FONTE.get(str(fonte or "").strip().lower(),
                              (_LARGURA_ARIAL_BOLD, _FALLBACK_ARIAL_BOLD))


def _escada(topo, piso, degraus=4):
    'Os `degraus` corpos, do topo até o piso, de `_DEGRAU_SZ` em `_DEGRAU_SZ`, sem repetir'

    passos = []
    for i in range(degraus):
        sz = max(int(piso), int(topo) - i * _DEGRAU_SZ)
        if not passos or sz < passos[-1]:
            passos.append(sz)
    return tuple(passos)


def _tema_do_timbrado(perfil):
    'Os sete valores que o timbrado PADRÃO lê do tema do perfil -- ou, sem tema válido e'


    t = _get(perfil, "identidade_visual.tema")
    if (not isinstance(t, dict) or validar_tema(t) is not None
            or tema_incompleto(t) is not None):
        base = dict(_TIMBRADO_PADRAO)
    else:
        tip, cap, fic = t["tipografia"], t["capitulo"], t["fichas"]
        base = {"fonte": tip["fonte"], "nome_sz": cap["titulo_sz"],
                "rotulo_sz": tip["versalete_sz"], "corpo_sz": tip["corpo_sz"],
                "filete_sz": min(_FILETE_SZ_MAX, max(_FILETE_SZ_MIN, cap["filete_inf_sz"])),
                "tinta": fic["tinta"], "acento": fic["acento"]}



    fonte = _get(perfil, "identidade_visual.fonte_corpo")
    if isinstance(fonte, str) and fonte.strip():
        base["fonte"] = fonte.strip()
    cor = _get(perfil, "identidade_visual.cor_texto_hex")
    if isinstance(cor, str) and _HEX.match(cor.strip().lstrip("#")):
        base["tinta"] = cor.strip().lstrip("#").upper()
    return base


def _metrica(perfil, campo):
    "(tabela, reserva, passos, tracking) do campo do timbrado: 'nome', 'oab' ou 'rodape'."


    t = _tema_do_timbrado(perfil)
    tabela, reserva = _tabela_da_fonte(t["fonte"])
    if campo == "nome":
        return tabela, reserva, _escada(t["nome_sz"], t["corpo_sz"]), _TRACKING_TIMBRADO
    if campo == "oab":
        return tabela, reserva, _escada(t["rotulo_sz"], _PISO_SZ_RODAPE,
                                        degraus=3), _TRACKING_TIMBRADO
    return tabela, reserva, _escada(t["rotulo_sz"], _PISO_SZ_RODAPE, degraus=3), 0






_QUEBRA_MARCA = "\uE000"


def _largura_util_pt(perfil):
    'Largura útil da página (largura - margem esquerda - margem direita), em pontos,'



    lay = layout(perfil)
    pagina, margens = lay["pagina"], lay["margens"]
    return (pagina["largura"] - margens["esq"] - margens["dir"]) / 20.0


def _largura_glifos(texto, tabela, reserva, sz_meio_pt, tracking_tw=0):
    'Largura estimada de `texto` (pt), somando o avanço de cada glifo em `tabela`'







    pt = sz_meio_pt / 2.0
    largura = sum(tabela.get(ch, reserva) for ch in texto) * pt
    return (largura + len(texto) * (tracking_tw / 20.0)) * _MARGEM_SEGURANCA


def _melhor_sz(texto, tabela, reserva, passos, largura_util_pt, tracking_tw=0):
    'O primeiro `sz` (meio-ponto) de `passos`, em ORDEM DECRESCENTE de corpo, em que'


    for sz in passos:
        if _largura_glifos(texto, tabela, reserva, sz, tracking_tw) <= largura_util_pt:
            return sz
    return passos[-1]





















def _particionar_otimo(unidades, juncoes, tabela, reserva, sz_meio_pt, largura_util_pt,
                        preferir_idxs=None, folga_preferencia=0.05, completas=None,
                        tracking_tw=0):
    '`unidades`: lista de N pedaços de texto que NUNCA são partidos por dentro.'






















    n = len(unidades)
    if n == 0:
        return [""]
    if n == 1:
        return [unidades[0]]
    preferir_idxs = set(preferir_idxs or ())
    completas = set(completas or ())



    escala = (sz_meio_pt / 2.0) * _MARGEM_SEGURANCA


    escala_tr = (tracking_tw / 20.0) * _MARGEM_SEGURANCA
    acum_u, acum_j, acum_nu, acum_nj = [0.0], [0.0], [0], [0]
    for u in unidades:
        acum_u.append(acum_u[-1] + sum(tabela.get(ch, reserva) for ch in u))
        acum_nu.append(acum_nu[-1] + len(u))
    for jc in juncoes:
        acum_j.append(acum_j[-1] + sum(tabela.get(ch, reserva) for ch in jc))
        acum_nj.append(acum_nj[-1] + len(jc))

    def largura(i, j):
        """Largura (pt) das unidades i..j-1 numa linha só, com as colas i..j-2."""
        return (((acum_u[j] - acum_u[i]) + (acum_j[j - 1] - acum_j[i])) * escala
                + ((acum_nu[j] - acum_nu[i]) + (acum_nj[j - 1] - acum_nj[i])) * escala_tr)

    def cabe(i, j):


        return (j - i == 1) or largura(i, j) <= largura_util_pt - 1e-9

    def texto_grupo(i, j):
        partes = [unidades[i]]
        for t in range(i + 1, j):
            partes.append(juncoes[t - 1])
            partes.append(unidades[t])
        return "".join(partes)




    alcancaveis, k = {0}, 0
    por_linha = [alcancaveis]
    while n not in alcancaveis:
        k += 1
        novos = set()
        for i in alcancaveis:
            for j in range(i + 1, n + 1):
                if not cabe(i, j):
                    break
                novos.add(j)
        alcancaveis = novos
        por_linha.append(alcancaveis)
    minK = k





    ini_min, i_ptr = [0] * (n + 1), 0
    for j in range(1, n + 1):
        while not cabe(i_ptr, j):
            i_ptr += 1
        ini_min[j] = i_ptr
    ate_o_fim = [set() for _ in range(minK + 1)]
    ate_o_fim[minK] = {n}
    for g in range(minK, 0, -1):
        ate_o_fim[g - 1] = {i for j in ate_o_fim[g] for i in range(ini_min[j], j)}
    fins = [sorted(por_linha[g] & ate_o_fim[g]) for g in range(minK + 1)]





    gigantes = {t for t in range(n) if largura(t, t + 1) > largura_util_pt}
    completas |= gigantes

    def peso(i, j):
        """Largura da linha (i, j) para o min-max: 0 para a unidade gigante sozinha."""
        return 0.0 if (j - i == 1 and i in gigantes) else largura(i, j)

    INF = float("inf")

    def resolver(k, exigir_dois, teto_largura, usar_preferencia, equilibrar):
        'DP: melhor partição das n unidades em k grupos, com todo grupo de 2+ unidades'





        pen = [[INF] * (n + 1) for _ in range(k + 1)]
        obj = [[INF] * (n + 1) for _ in range(k + 1)]
        parent = [[None] * (n + 1) for _ in range(k + 1)]
        pen[0][0], obj[0][0] = 0, 0.0
        for g in range(1, k + 1):
            for j in fins[g]:


                lo = max(ini_min[j], g - 1)
                while lo < j - 1 and largura(lo, j) > teto_largura + 1e-9:
                    lo += 1

                for i in range(lo, j):
                    if obj[g - 1][i] == INF:
                        continue
                    if exigir_dois and j - i == 1 and i not in completas:
                        continue
                    w = peso(i, j)
                    if w > teto_largura + 1e-9:
                        continue
                    if equilibrar:
                        novo = obj[g - 1][i] + max(0.0, largura_util_pt - largura(i, j)) ** 2
                    else:
                        novo = max(obj[g - 1][i], w)
                    penal = pen[g - 1][i]


                    if usar_preferencia and i > 0 and (i - 1) not in preferir_idxs:
                        penal += 1
                    if (penal, novo) < (pen[g][j], obj[g][j]):
                        pen[g][j], obj[g][j], parent[g][j] = penal, novo, i
        if obj[k][n] == INF:
            return None
        cortes, j = [], n
        for g in range(k, 0, -1):
            i = parent[g][j]
            cortes.append((i, j))
            j = i
        cortes.reverse()
        return cortes


    exigir_dois = n >= 2 * minK
    base = resolver(minK, True, INF, False, False) if exigir_dois else None
    if base is None:
        exigir_dois = False
        base = resolver(minK, False, INF, False, False)
    if base is None:



        base, i = [], 0
        while i < n:
            j = i + 1
            while j < n and cabe(i, j + 1):
                j += 1
            base.append((i, j))
            i = j
    largura_minmax = max(peso(i, j) for i, j in base)




    final = resolver(minK, exigir_dois, largura_minmax, False, True) or base


    if preferir_idxs:
        final = (resolver(minK, exigir_dois, largura_minmax * (1 + folga_preferencia), True,
                          True) or final)

    return [texto_grupo(i, j) for i, j in final]









_RX_ESPACOS = re.compile(r"[ \t\r\n\f\v]+")





_RX_PONTA_INVISIVEL = re.compile(r"^[\s\u200b-\u200d\u2060\ufeff]+|[\s\u200b-\u200d\u2060\ufeff]+$")


def _palavras(texto):
    return [q for q in (_RX_PONTA_INVISIVEL.sub("", p) for p in _RX_ESPACOS.split(texto)) if q]


def _unidades_palavras(texto, refinar=None):
    'Nome: cada palavra é uma unidade (nenhuma completa); colas são espaço comum, sem'

    unidades = _palavras(texto) or [""]
    return unidades, [" "] * (len(unidades) - 1), [], []







_ROTULOS_ENDERECO = frozenset((
    "nº", "n°", "n.º", "n.°", "n.", "no.", "nro", "nro.", "núm.", "num.", "número", "cep",
    "sala", "salas", "sl", "sl.", "conjunto", "conj.", "cj.", "cj", "cjto", "cjto.",
    "bloco", "bl", "bl.", "andar", "apto", "apto.", "apartamento", "ap", "ap.", "apt",
    "apt.", "lote", "lt", "lt.", "quadra", "qd.", "qd", "casa", "loja", "lj", "lj.", "km",
    "km.", "box", "torre", "unidade", "módulo", "modulo", "mód.", "ed.", "edifício",
    "edificio", "ala"))


_RX_ORDINAL = re.compile(r"\d+\.?[ºª°oa]\.?")


_RX_CODIGO_VIA = re.compile(r"[A-Za-z]{1,3}-?\d")

_RX_SIGLA_SETOR = re.compile(r"[A-ZÀ-Ü]{2,6}")


def _cola_na_anterior(anterior, palavra):
    'True quando `palavra` NÃO pode abrir uma linha depois de `anterior` (a última'






    if anterior.endswith((",", ";")):
        return False
    if anterior.lower() in _ROTULOS_ENDERECO or _RX_ORDINAL.fullmatch(anterior):
        return True



    if (_RX_SIGLA_SETOR.fullmatch(anterior)
            and palavra.lower().rstrip(",;") in _ROTULOS_ENDERECO):
        return True
    return palavra[:1].isdigit() or bool(_RX_CODIGO_VIA.match(palavra))




_SEPARADORES_ENDERECO = ("–", "-", "—", "•", "·", "|", "/")


def _unidades_endereco(texto, refinar=None, cidade=None):
    'Endereço: palavras, com o separador solto (" – ", o hífen ASCII " - " e os demais de'












    if cidade:
        marca = " – " + cidade
        pos = texto.rfind(marca)
        if pos >= 0:
            cabeca, cauda = texto[:pos], texto[pos + len(marca):]
            unidade_cidade = cidade
            if cauda.startswith(","):
                unidade_cidade, cauda = cidade + ",", cauda[1:]
            u1, j1, p1, _ = _unidades_endereco(cabeca)
            u2, j2, p2, _ = _unidades_endereco(cauda)
            unidades = [x for x in u1 if x] + [unidade_cidade]
            juncoes = j1[:len([x for x in u1 if x]) - 1]
            prefs = [i for i in p1 if i < len(juncoes)]
            if len(unidades) > 1:
                juncoes.append(" – ")
                prefs.append(len(juncoes) - 1)
            base = len(juncoes)
            resto = [x for x in u2 if x]
            if resto:
                juncoes.append(" ")
                unidades += resto
                juncoes += j2[:len(resto) - 1]
                prefs += [base + 1 + i for i in p2 if i < len(resto) - 1]


            palavras_cidade = [w for w in cidade.split() if w not in _SEPARADORES_ENDERECO]
            completas = [len(unidades) - len(resto) - 1] if len(palavras_cidade) >= 2 else []
            return unidades, juncoes, prefs, completas
    unidades, juncoes, prefs = [], [], []
    glue_pendente = " "
    for p in _palavras(texto):
        if p in _SEPARADORES_ENDERECO:
            glue_pendente = f" {p} "
            continue
        if (unidades and glue_pendente == " "
                and _cola_na_anterior(unidades[-1].rsplit(" ", 1)[-1], p)):
            unidades[-1] += " " + p
            continue
        if unidades:
            juncoes.append(glue_pendente)
            if glue_pendente != " ":
                prefs.append(len(juncoes) - 1)
            glue_pendente = " "
        unidades.append(p)
    return (unidades or [""]), juncoes, prefs, []









_RX_SEPARADOR_LISTA = re.compile(
    r"(?P<pont>\s*[,;])?(?P<esp1>\s*)"
    r"(?:(?P<barra>[/|–—•·]|(?<=\s)-(?=\s|$))|(?P<conj>e|ou|&)(?=\s|$))?(?P<esp2>\s*)", re.I)


def _compor_lista(texto, spans):
    '(unidades, junções) de um texto com os itens nas posições `spans` [(início, fim)].'



    if not spans:
        return [texto], []
    unidades, juncoes = [], []
    atual = texto[:spans[0][1]]
    for (_, fim_ant), (ini, fim) in zip(spans, spans[1:]):
        entre = texto[fim_ant:ini]
        m = _RX_SEPARADOR_LISTA.fullmatch(entre)
        if m is None:
            atual += entre + texto[ini:fim]
            continue
        if m.group("barra"):
            cola, prefixo = m.group("esp1") + m.group("barra") + m.group("esp2"), ""
        elif m.group("conj"):
            cola, prefixo = m.group("esp1"), m.group("conj") + m.group("esp2")
        else:
            cola, prefixo = m.group("esp1") + m.group("esp2"), ""
        unidades.append(atual + (m.group("pont") or ""))
        juncoes.append(cola)
        atual = prefixo + texto[ini:fim]
    unidades.append(atual + texto[spans[-1][1]:])
    return unidades, juncoes




_RX_CAUDA_SEPARADOR = re.compile(
    r"(?:\s*[,;])?(?:\s+(?:e|ou|&)(?=\s|$)|\s*[/|–—•·]|\s+-(?=\s|$))?\s*$", re.I)


def _fora_de_parenteses(texto):
    'fora[i] = True quando a posição i do texto não está dentro de um parêntese.'





    pares, pilha = [], []
    for i, ch in enumerate(texto):
        if ch == "(":
            pilha.append(i)
        elif ch == ")" and pilha:
            pares.append((pilha.pop(), i))
    fim = len(texto.rstrip()) - 1
    fora = [True] * len(texto)
    for a, b in pares:
        if b == fim and not any(ch.isdigit() for ch in texto[:a]):
            continue
        for i in range(a + 1, b + 1):
            fora[i] = False
    return fora


def _spans_por_inicio(texto, inicios, fim=None):
    'Cada item vai do seu início até o separador que precede o início seguinte (ou até'

    fim = len(texto) if fim is None else fim
    spans = []
    for k, ini in enumerate(inicios):
        fim_trecho = inicios[k + 1] if k + 1 < len(inicios) else fim
        cauda = _RX_CAUDA_SEPARADOR.search(texto, ini, fim_trecho)
        spans.append((ini, cauda.start() if cauda else fim_trecho))
    return spans







_RX_SEPARADOR_EXPLICITO = re.compile(r"\s*[,;]\s*|\s+(?:[/|–—•·-]|e|ou|&)\s+", re.I)


_SEPARADORES_DE_ROTULO = ("-", "–", "—")


def _spans_lista(texto, eh_item, inicios_internos, respeitar_parenteses=True,
                 rotulo_do_seguinte=None):
    'Spans dos itens de uma lista. `eh_item(trecho)`: o trecho entre dois separadores é'

















    fora = (_fora_de_parenteses(texto) if respeitar_parenteses else [True] * len(texto))
    cortes = [m.span() for m in _RX_SEPARADOR_EXPLICITO.finditer(texto)
              if m.end() > m.start() and fora[m.start()] and fora[m.end() - 1]]
    trechos, ini = [], 0
    for a, b in cortes:
        trechos.append((ini, a))
        ini = b
    trechos.append((ini, len(texto)))

    def sep_depois(k):
        return texto[cortes[k][0]:cortes[k][1]].strip() if k < len(cortes) else ""

    primeiro = next((k for k, (a, b) in enumerate(trechos) if eh_item(texto[a:b])), None)
    rotulo_antes = bool(primeiro) and sep_depois(primeiro - 1) in _SEPARADORES_DE_ROTULO

    itens, pendente = [], None
    for k, (a, b) in enumerate(trechos):
        if pendente is not None:
            a, pendente = pendente, None
        trecho = texto[a:b]




        vai_para_o_seguinte = (k + 1 < len(trechos) and rotulo_do_seguinte is not None
                               and rotulo_do_seguinte(trecho))
        if eh_item(trecho):
            itens.append((a, b))
        elif itens and not vai_para_o_seguinte and not (
                rotulo_antes and sep_depois(k) in _SEPARADORES_DE_ROTULO
                and not any(ch.isdigit() for ch in trecho)):
            itens[-1] = (itens[-1][0], b)
        else:
            pendente = a
    if pendente is not None:
        itens.append((pendente, len(texto)))

    spans = []
    for a, b in itens:
        dentro = [i for i in inicios_internos(texto, a, b, fora) if a < i < b]
        spans.extend(_spans_por_inicio(texto, [a] + dentro, b) if dentro else [(a, b)])
    return spans




_RX_INICIO_OAB = re.compile(r"\bOAB\b", re.I)






_UFS_BR = ("AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO")
_RX_INSCRICAO_UF = re.compile(
    r"(?<![Oo][Aa][Bb][/\- ])(?<![Oo][Aa][Bb])\b(?:" + _UFS_BR + r")\b"


    r"(?:,\s*(?:sob\s+o\s+)?n[º°o]?\.?º?\s*|\s*(?:[:\-–]\s*)?(?:sob\s+o\s+)?"
    r"(?:n[º°o]?\.?º?\s*)?)\(?\d")
_RX_INSCRICAO_NUMERO_UF = re.compile(r"\b\d[\d.]*(?:-[A-Z])?\s*/\s*(?:" + _UFS_BR + r")\b")



_RX_NUMERO_NO_FIM = re.compile(r"\d[\d.]*(?:-[A-Z])?\s+$")
_RX_NUMERO_EM_SEGUIDA = re.compile(r"\S*\s+(?:sob\s+o\s+)?(?:n[º°o.]*\s*)?\d", re.I)


def _candidatos_inscricao(texto, a, b):
    '[(posição, tipo)] de cada começo de inscrição em texto[a:b]: "oab" (a palavra),'





    oabs = [m.start() for m in _RX_INICIO_OAB.finditer(texto, a, b)]
    cands = [(p, "oab") for p in oabs]

    def e_da_oab_anterior(pos):
        antes = [p for p in oabs if p < pos]
        return bool(antes) and not any(ch.isdigit() for ch in texto[max(antes):pos])

    for rx, tipo in ((_RX_INSCRICAO_UF, "uf"), (_RX_INSCRICAO_NUMERO_UF, "num")):
        for m in rx.finditer(texto, a, b):
            if not e_da_oab_anterior(m.start()):
                cands.append((m.start(), tipo))
    return sorted(set(cands))


def _eh_inscricao(trecho):
    'Trecho que tem inscrição COMPLETA: um começo de inscrição e um número ("OAB"'

    return (any(ch.isdigit() for ch in trecho)
            and bool(_candidatos_inscricao(trecho, 0, len(trecho))))


def _rotulo_oab_sem_numero(trecho):
    """O "OAB" (sem número) de "OAB / SP", "OAB – SP", "OAB — SP": rótulo do seguinte."""
    return bool(_RX_INICIO_OAB.search(trecho)) and not any(ch.isdigit() for ch in trecho)


def _inicios_oab(texto, a, b, fora):
    'Onde começa cada inscrição num trecho SEM separador entre elas: no "OAB" dela (ou'








    cands = [(p, t) for p, t in _candidatos_inscricao(texto, a, b) if fora[p]]
    if len(cands) < 2:
        return []
    ajustados, anterior = [], cands[0][0]
    for pos, tipo in cands[1:]:



        if not any(ch.isdigit() for ch in texto[anterior:pos]):
            continue
        ini = pos
        if tipo == "oab":
            m = _RX_NUMERO_NO_FIM.search(texto, anterior, pos)
            if m and not _RX_NUMERO_EM_SEGUIDA.match(texto, pos, b):
                ini = m.start()



        seps = [m.end() for m in _RX_SEPARADOR_REDE.finditer(texto, anterior, ini)]
        if seps:
            ini = seps[-1]
        abertos = []
        for k in range(seps[-1] if seps else anterior, ini):
            if texto[k] == "(":
                abertos.append(k)
            elif texto[k] == ")" and abertos:
                abertos.pop()
        if abertos:
            ini = abertos[0]
        if ini > anterior:
            ajustados.append(ini)
        anterior = pos
    return ajustados




_RX_SO_UF = re.compile(r"\(?(?:" + _UFS_BR + r")\)*[.;]?")
_RX_SEPARADOR_REDE = re.compile(r"\s*[,;]\s*|\s+(?:e|ou|&)\s+", re.I)


def _unidades_por_digito(texto):
    '(unidades, junções) de uma unidade de OAB que, depois de tudo, ainda não cabe na'









    cortes = [m.span() for m in _RX_SEPARADOR_REDE.finditer(texto) if m.end() > m.start()]
    trechos, ini = [], 0
    for x, y in cortes:
        trechos.append((ini, x))
        ini = y
    trechos.append((ini, len(texto)))
    spans, pendentes = [], []
    for x, y in trechos:
        if not texto[x:y].strip():
            continue


        if not pendentes and spans and _RX_SO_UF.fullmatch(texto[x:y].strip()):
            spans[-1] = (spans[-1][0], y)
            continue
        pendentes.append((x, y))
        if any(ch.isdigit() for ch in texto[x:y]):
            spans.append((pendentes[0][0], y))
            pendentes = []
    spans.extend(pendentes)
    if len(spans) < 2:
        return [texto], []
    return _compor_lista(texto, spans)


def _unidades_oab(texto, refinar=None):
    'OAB: cada INSCRIÇÃO é uma unidade COMPLETA, qualquer que seja o separador entre'












    spans = _spans_lista(texto, _eh_inscricao, _inicios_oab,
                         rotulo_do_seguinte=_rotulo_oab_sem_numero)
    unidades, juncoes = _compor_lista(texto, spans)
    if refinar is not None and any(refinar(u) for u in unidades):
        finas, colas = [], []
        for idx, u in enumerate(unidades):
            if idx:
                colas.append(juncoes[idx - 1])
            sub, sub_colas = [u], []
            if refinar(u):
                sub, sub_colas = _compor_lista(u, _spans_lista(
                    u, _eh_inscricao, _inicios_oab, respeitar_parenteses=False,
                    rotulo_do_seguinte=_rotulo_oab_sem_numero))
            for k, s in enumerate(sub):
                if k:
                    colas.append(sub_colas[k - 1])
                if refinar(s):
                    rede, rede_colas = _unidades_por_digito(s)
                    finas.extend(rede)
                    colas.extend(rede_colas)
                else:
                    finas.append(s)
        unidades, juncoes = finas, colas


    return unidades, juncoes, [], [i for i, u in enumerate(unidades)
                                   if any(ch.isdigit() for ch in u)]












_RX_TELEFONE = re.compile(
    r"(?<![\d+(])(?:0[3589]00[\s.-]?\d{3}[\s.-]?\d{4}"
    r"|(?:\+\d{1,3}[\s.-]?|55[\s.-]?)?"
    r"(?:\((?:0[xX]{2})?\d{2,3}\)[\s.-]?|0[xX]{2}\d{2}[\s.-]?|0\d{2}[\s.-]?|\d{2}[\s.-]?)?"
    r"(?:9[\s.])?\d{4,5}[\s.-]?\d{4})(?!\d|[.-]\d)")
_MIN_DIGITOS_TELEFONE = 8


def _eh_telefone(trecho):
    return sum(ch.isdigit() for ch in trecho) >= _MIN_DIGITOS_TELEFONE


def _inicios_telefone(texto, a, b, fora):
    inicios = [m.start() for m in _RX_TELEFONE.finditer(texto, a, b) if fora[m.start()]]
    return inicios[1:] if len(inicios) > 1 else []


def _campos_contato(texto):
    'Os CAMPOS de topo do contato -- o par "e-mail:\xa0X" e o par "fone:\xa0Y" --, na'

    sep = " – " + _ROTULO_FONE
    if texto.startswith(_ROTULO_EMAIL) and sep in texto:
        corte = texto.index(sep)
        return [texto[:corte], texto[corte + len(" – "):]]
    return [texto]


def _unidades_contato(texto, refinar=lambda campo: False):
    'Contato: cada CAMPO é uma unidade COMPLETA, coladas por " – " (preferido). O corte'







    unidades, juncoes, prefs, completas = [], [], [], []
    for idx, campo in enumerate(_campos_contato(texto)):
        if idx:
            juncoes.append(" – ")
            prefs.append(len(juncoes) - 1)
        partes, colas = [campo], []
        if campo.startswith(_ROTULO_FONE) and refinar(campo):
            partes, colas = _compor_lista(campo, _spans_lista(campo, _eh_telefone,
                                                              _inicios_telefone))
        completas.append(len(unidades))
        unidades.extend(partes)
        juncoes.extend(colas)
    return unidades, juncoes, prefs, completas


def _ajustar(texto, tabela, reserva, passos, largura_util_pt, tokenizar=_unidades_palavras,
             tracking_tw=0):
    '(sz, texto_final): o corpo escolhido e o texto, com `_QUEBRA_MARCA` entre as linhas'




    sz = _melhor_sz(texto, tabela, reserva, passos, largura_util_pt, tracking_tw)
    if sz == passos[-1] and _largura_glifos(texto, tabela, reserva, sz,
                                            tracking_tw) > largura_util_pt:
        unidades, juncoes, prefs, completas = tokenizar(
            texto, refinar=lambda u: _largura_glifos(u, tabela, reserva, sz,
                                                     tracking_tw) > largura_util_pt)
        linhas = _particionar_otimo(unidades, juncoes, tabela, reserva, sz, largura_util_pt,
                                     preferir_idxs=prefs, completas=completas,
                                     tracking_tw=tracking_tw)
        texto = _QUEBRA_MARCA.join(linhas)
    return sz, texto


def _texto_bruto(perfil, caminho):
    'O campo do perfil na forma em que entra na composição (`_texto_do_perfil`): a mesma de'


    return _texto_do_perfil(_get(perfil, caminho, "") or "")


def _sz_nome_cabecalho(perfil):
    tab, res, passos, tr = _metrica(perfil, "nome")
    nome = _texto_bruto(perfil, "advogado.nome_exibicao_cabecalho")
    sz, _ = _ajustar(nome, tab, res, passos, _largura_util_pt(perfil), tracking_tw=tr)
    return str(sz)


def _texto_nome_cabecalho(perfil):
    tab, res, passos, tr = _metrica(perfil, "nome")
    nome = _texto_bruto(perfil, "advogado.nome_exibicao_cabecalho")
    _, texto = _ajustar(nome, tab, res, passos, _largura_util_pt(perfil), tracking_tw=tr)
    return texto


def _sz_linha_oab(perfil):
    tab, res, passos, tr = _metrica(perfil, "oab")
    sz, _ = _ajustar(montar_linha_oab(perfil), tab, res, passos, _largura_util_pt(perfil),
                      tokenizar=_unidades_oab, tracking_tw=tr)
    return str(sz)


def _texto_linha_oab(perfil):
    tab, res, passos, tr = _metrica(perfil, "oab")
    _, texto = _ajustar(montar_linha_oab(perfil), tab, res, passos, _largura_util_pt(perfil),
                         tokenizar=_unidades_oab, tracking_tw=tr)
    return texto


def _sz_comum_rodape(perfil):
    'As duas linhas do rodapé (endereço e contato) saem SEMPRE no MESMO corpo -- o MENOR'



    largura = _largura_util_pt(perfil)
    tab, res, passos, tr = _metrica(perfil, "rodape")
    sz_e = _melhor_sz(montar_linha_endereco(perfil), tab, res, passos, largura, tr)
    sz_c = _melhor_sz(montar_linha_contato(perfil), tab, res, passos, largura, tr)
    return min(sz_e, sz_c)


def _sz_linha_endereco(perfil):
    """O corpo comum do rodapé, como texto: vale para as duas linhas."""
    return str(_sz_comum_rodape(perfil))


_sz_linha_contato = _sz_linha_endereco


def _texto_linha_endereco(perfil):
    sz = _sz_comum_rodape(perfil)
    texto = montar_linha_endereco(perfil)
    largura = _largura_util_pt(perfil)
    tab, res, _, tr = _metrica(perfil, "rodape")
    if _largura_glifos(texto, tab, res, sz, tr) > largura:
        unidades, juncoes, prefs, completas = _unidades_endereco(
            texto, cidade=_texto_do_perfil(_get(perfil, "contato.cidade_uf") or ""))
        linhas = _particionar_otimo(unidades, juncoes, tab, res, sz, largura,
                                     preferir_idxs=prefs, completas=completas, tracking_tw=tr)
        texto = _QUEBRA_MARCA.join(linhas)
    return texto


def _texto_linha_contato(perfil):
    'A linha de contato no corpo comum do rodapé. Quando não cabe numa linha só, a'




    sz = _sz_comum_rodape(perfil)
    texto = montar_linha_contato(perfil)
    largura = _largura_util_pt(perfil)
    tab, res, _, tr = _metrica(perfil, "rodape")

    def nao_cabe(s):
        return _largura_glifos(s, tab, res, sz, tr) > largura

    if nao_cabe(texto):
        linhas = []
        for campo in _campos_contato(texto):
            if not (campo.startswith(_ROTULO_FONE) and nao_cabe(campo)):
                linhas.append(campo)
                continue
            unidades, juncoes, prefs, completas = _unidades_contato(campo, refinar=nao_cabe)
            linhas.extend(_particionar_otimo(unidades, juncoes, tab, res, sz, largura,
                                             preferir_idxs=prefs, completas=completas,
                                             tracking_tw=tr))
        texto = _QUEBRA_MARCA.join(linhas)
    return texto


def _escapar_xml(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_COMPOSTOS = {



    "{{LINHA_OAB}}": _texto_linha_oab,
    "{{LINHA_ENDERECO}}": _texto_linha_endereco,
    "{{LINHA_CONTATO}}": _texto_linha_contato,
    "{{NOME_CABECALHO}}": _texto_nome_cabecalho,
    "{{NOME_CABECALHO_SZ}}": _sz_nome_cabecalho,
    "{{LINHA_OAB_SZ}}": _sz_linha_oab,
    "{{LINHA_ENDERECO_SZ}}": _sz_linha_endereco,
    "{{LINHA_CONTATO_SZ}}": _sz_linha_contato,
    "{{TIMBRADO_FONTE}}": lambda p: _tema_do_timbrado(p)["fonte"],
    "{{TIMBRADO_TINTA}}": lambda p: _tema_do_timbrado(p)["tinta"],
    "{{TIMBRADO_ACENTO}}": lambda p: _tema_do_timbrado(p)["acento"],
    "{{TIMBRADO_FILETE_SZ}}": lambda p: str(_tema_do_timbrado(p)["filete_sz"]),
    "{{TIMBRADO_TRACKING}}": lambda p: str(_TRACKING_TIMBRADO),
    "{{TIMBRADO_ROTULO_SZ}}": lambda p: str(_tema_do_timbrado(p)["rotulo_sz"]),
}


def _valor_para(placeholder, perfil):
    if placeholder in _COMPOSTOS:
        return _COMPOSTOS[placeholder](perfil)
    caminho = PLACEHOLDERS.get(placeholder)
    return "" if caminho is None else _texto_do_perfil(_get(perfil, caminho, "") or "")






_COMPOSTOS_TEXTO_PURO = {
    "{{LINHA_OAB}}": montar_linha_oab,
    "{{LINHA_ENDERECO}}": montar_linha_endereco,
    "{{LINHA_CONTATO}}": montar_linha_contato,
    "{{NOME_CABECALHO}}": lambda perfil: _texto_bruto(perfil, "advogado.nome_exibicao_cabecalho"),
}
















_RX_RUN_COM_MARCA = re.compile(
    r'<w:r(?P<attrs>\s[^>]*)?><w:rPr>(?P<rpr>(?:(?!</w:r>).)*?)</w:rPr>'
    r'<w:t[^>]*>(?P<texto>[^<]*' + re.escape(_QUEBRA_MARCA) + r'[^<]*)</w:t></w:r>', re.S)


def _expandir_quebras(conteudo):
    'Troca cada `<w:r>` cujo `<w:t>` contém uma ou mais `_QUEBRA_MARCA` por 2N+1 runs'






    def _sub(m):
        attrs = m.group("attrs") or ""
        rpr = m.group("rpr")
        pedacos = m.group("texto").split(_QUEBRA_MARCA)
        partes = []
        for i, pedaco in enumerate(pedacos):
            if i:
                partes.append(f'<w:r{attrs}><w:rPr>{rpr}</w:rPr><w:br/></w:r>')
            partes.append(f'<w:r{attrs}><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{pedaco}</w:t></w:r>')
        return "".join(partes)
    conteudo = _RX_RUN_COM_MARCA.sub(_sub, conteudo)
    if _QUEBRA_MARCA in conteudo:



        raise PerfilError(
            "_expandir_quebras: marca de quebra sobrou fora de um <w:t> reconhecível -- "
            "provável regressão na regex ou no gerador da marca")
    return conteudo
































_RX_HIFEN_TOKEN = re.compile(
    r"<w:t(?P<attrs>\s[^>]*)?>(?P<texto>[^<]*)</w:t>"
    r"|(?P<fronteira></?w:p(?:\s[^>]*)?/?>"
    r"|<w:(?:tab|br|cr|ptab|noBreakHyphen|softHyphen|sym|drawing|pict|object|fldChar)\b[^>]*>)")
_RX_ENTIDADE = re.compile(r"&(?:#[xX][0-9a-fA-F]+|#[0-9]+|amp|lt|gt|quot|apos);")
_ENTIDADES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}
NO_BREAK_HYPHEN = "<w:noBreakHyphen/>"


def _alfanumerico(c):
    """Letra ou número Unicode — a MESMA classe de `[\\p{L}\\p{N}]` no JavaScript."""
    return bool(c) and unicodedata.category(c)[0] in "LN"


def _caracteres_de(texto_bruto):
    """[(caractere lógico, início bruto, fim bruto)] de um `<w:t>`, entidades decodificadas."""
    saida, i = [], 0
    while i < len(texto_bruto):
        if texto_bruto[i] == "&":
            m = _RX_ENTIDADE.match(texto_bruto, i)
            if m:
                ent = m.group(0)
                if ent in _ENTIDADES:
                    c = _ENTIDADES[ent]
                else:
                    try:
                        c = chr(int(ent[3:-1], 16) if ent[2] in "xX" else int(ent[2:-1]))
                    except (ValueError, OverflowError):
                        c = "&"
                saida.append((c, i, m.end()))
                i = m.end()
                continue
        saida.append((texto_bruto[i], i, i + 1))
        i += 1
    return saida


def normalizar_hifens_timbrado(xml):
    '`(xml_normalizado, n_convertidos)`. Aceita `str` ou `bytes` (UTF-8) e devolve o mesmo'



    if isinstance(xml, (bytes, bytearray)):
        try:
            texto = bytes(xml).decode("utf-8")
        except UnicodeDecodeError:
            return xml, 0
        saida, n = normalizar_hifens_timbrado(texto)
        return (saida.encode("utf-8") if n else xml), n
    tokens = list(_RX_HIFEN_TOKEN.finditer(xml))
    fluxo = []
    por_token = {}
    for k, m in enumerate(tokens):
        if m.group("fronteira") is not None:
            fluxo.append(("\n", None, None))
            continue
        chars = _caracteres_de(m.group("texto"))
        por_token[k] = chars
        fluxo.extend((c, k, j) for j, (c, _a, _b) in enumerate(chars))
    marcados = {}
    for i, (c, k, j) in enumerate(fluxo):
        if c == "-" and 0 < i < len(fluxo) - 1 and _alfanumerico(fluxo[i - 1][0]) \
                and _alfanumerico(fluxo[i + 1][0]):
            marcados.setdefault(k, []).append(j)
    if not marcados:
        return xml, 0
    pedacos, pos, n = [], 0, 0
    for k, js in sorted(marcados.items()):
        m = tokens[k]
        attrs = m.group("attrs") or ""
        bruto = m.group("texto")
        chars = por_token[k]
        pedacos.append(xml[pos:m.start()])
        novo, ini = [], 0
        for j in js:
            _c, a, b = chars[j]
            if a > ini:
                novo.append(f"<w:t{attrs}>{bruto[ini:a]}</w:t>")
            novo.append(NO_BREAK_HYPHEN)
            ini = b
            n += 1
        if ini < len(bruto):
            novo.append(f"<w:t{attrs}>{bruto[ini:]}</w:t>")
        pedacos.append("".join(novo))
        pos = m.end()
    pedacos.append(xml[pos:])
    return "".join(pedacos), n






_RX_BR_ENTRE_LINHAS = re.compile(
    r'<w:r\b[^>]*><w:rPr>(?:(?!</w:r>).)*?</w:rPr><w:br/></w:r>', re.S)


def _remover_quebra_condicional(conteudo, perfil):
    'A quebra entre endereço e contato só faz sentido quando OS DOIS têm conteúdo. Perfil'




    if montar_linha_endereco(perfil) and montar_linha_contato(perfil):
        return conteudo
    return _RX_BR_ENTRE_LINHAS.sub("", conteudo, count=1)


def resolver_texto(texto, perfil):
    'Expande os placeholders de identidade em texto comum (SKILL.md, referências, o'










    for ph in PLACEHOLDERS:
        if ph in texto:
            resolvedor_puro = _COMPOSTOS_TEXTO_PURO.get(ph)
            valor = resolvedor_puro(perfil) if resolvedor_puro else _valor_para(ph, perfil)
            texto = texto.replace(ph, valor)
    return texto


def rodape_vazio(perfil):
    'True quando o rodapé sairia sem informação NENHUMA de contato.'





    return not (montar_linha_endereco(perfil) or montar_linha_contato(perfil))


def gerar_identidade(perfil, dir_templates, dir_saida):
    'Escreve os 6 XML + mapping.json resolvidos em dir_saida. Devolve a lista.'



    erros = validar(perfil)
    if erros:
        raise PerfilError("perfil inválido:\n  - " + "\n  - ".join(erros))
    if rodape_vazio(perfil):
        raise PerfilError(
            "PERFIL SEM CONTATO — o rodapé sairia em branco em todas as páginas.\n"
            "  O timbrado imprime endereço, e-mail e telefone; sem nenhum deles a peça sai\n"
            "  com um traço e duas linhas vazias, e isso só se nota depois de protocolada.\n"
            "  Preencha endereço, e-mail ou telefone na página Seus dados, ou envie o seu timbrado.")
    os.makedirs(dir_saida, exist_ok=True)
    gerados = []
    for nome in ASSETS_TODOS:
        src = os.path.join(dir_templates, nome)
        dst = os.path.join(dir_saida, nome)
        if not os.path.isfile(src):
            raise PerfilError(f"template de identidade ausente: {src}")
        if nome in ASSETS_COM_PLACEHOLDER:
            conteudo = open(src, encoding="utf-8").read()
            for ph in PLACEHOLDERS:
                if ph in conteudo:
                    try:
                        valor = _valor_para(ph, perfil)
                    except PerfilError:
                        raise
                    except Exception as e:



                        raise PerfilError(
                            f"{nome}: não consegui compor {ph} ({type(e).__name__}: {e}). "
                            f"O perfil passou na validação; o defeito é do plugin, ao "
                            f"encaixar o texto no timbrado -- reporte com este erro") from e
                    conteudo = conteudo.replace(ph, _escapar_xml(valor))
            restantes = sorted(set(RX_PLACEHOLDER.findall(conteudo)))
            if restantes:
                raise PerfilError(
                    f"{nome}: placeholder não resolvido {restantes} — o perfil não tem o campo "
                    f"correspondente, e placeholder cru não vai para peça protocolada")







            if nome == "footer2.xml":
                conteudo = _remover_quebra_condicional(conteudo, perfil)
            conteudo = _expandir_quebras(conteudo)



            conteudo, _n = normalizar_hifens_timbrado(conteudo)
            open(dst, "w", encoding="utf-8", newline="").write(conteudo)
        else:
            shutil.copy2(src, dst)
        gerados.append(dst)
    return gerados




VERSAO_GERADOR_TIMBRADO = "2"


def _impressao(perfil, dir_templates):
    'Assinatura do par (perfil, templates), para invalidar o cache quando qualquer um'

    h = hashlib.sha256()



    h.update(VERSAO_GERADOR_TIMBRADO.encode("utf-8"))
    h.update(json.dumps({k: v for k, v in perfil.items() if k != "_caminho"},
                        sort_keys=True, ensure_ascii=False).encode("utf-8"))
    for nome in ASSETS_TODOS:
        p = os.path.join(dir_templates, nome)
        if os.path.isfile(p):
            h.update(nome.encode("utf-8"))
            h.update(open(p, "rb").read())
    return h.hexdigest()[:16]


def dir_templates_identidade():
    'Onde estão os XML-modelo do timbrado, nas três montagens que existem.'









    aqui = os.path.dirname(os.path.abspath(__file__))
    candidatos = [
        os.path.join(os.path.dirname(aqui), "assets", "identity"),
        os.path.join(_raiz(), "skills", "dissero-visual-law", "assets", "identity"),
    ]
    for c in candidatos:
        if os.path.isfile(os.path.join(c, "mapping.json")):
            return c
    return candidatos[-1]


def _verificar_marca_identidade(diretorio, perfil):
    'Recusa quando o timbrado em `diretorio` foi marcado para um advogado DIFERENTE do'






















    try:
        with open(os.path.join(diretorio, "mapping.json"), encoding="utf-8") as fh:
            _mapa = json.load(fh) or {}
        marca_disco = str(_mapa.get("marca") or "")
        marca_indeterminada = bool(_mapa.get("marca_indeterminada"))
    except (OSError, ValueError):
        marca_disco, marca_indeterminada = "", False
    marca_perfil = str(_get(perfil, "email_marca") or "")
    if marca_disco and marca_perfil and marca_disco != marca_perfil:
        raise PerfilError(
            "TIMBRADO DE OUTRO ADVOGADO — o pacote em identidade/ pertence a outra conta; "
            "chame perfil_do_advogado(parte=\"identidade\") de novo e grave com "
            "`perfil_advogado.py --gravar-identidade <zip>`; a peça não sai com o timbrado "
            "de outra pessoa.")



    if marca_indeterminada and marca_perfil:
        raise PerfilError(
            "TIMBRADO SEM DONO CONFERÍVEL — este pacote foi gravado quando o seu perfil "
            "estava ilegível, e por isso não ficou registrado de quem ele é. Chame "
            "perfil_do_advogado(parte=\"identidade\") de novo e grave com "
            "`perfil_advogado.py --gravar-identidade <zip>`; agora que o perfil abre, a "
            "gravação registra o dono e esta recusa não se repete.")


def dir_identidade(perfil, dir_templates=None):
    'Diretório com o timbrado do advogado, gerado sob demanda e cacheado ao lado do'

    if _get(perfil, "identidade_visual.timbrado") == "proprio":
        d = dir_identidade_propria()




        try:
            achados = os.listdir(d)
        except OSError:
            achados = []
        if not any(re.fullmatch(r"(header|footer)\d+\.xml", n) for n in achados):
            raise PerfilError(
                "TIMBRADO PRÓPRIO SEM PACOTE — chame perfil_do_advogado(parte=\"identidade\") e "
                "grave com `perfil_advogado.py --gravar-identidade <zip>`; a peça não sai com "
                "o timbrado errado. Cabeçalho e rodapé vêm só do pacote do Dissero ou do "
                "timbrado padrão do plugin: não escreva, não copie de outra peça e não ajuste "
                "nenhum dos dois à mão. Se o pacote não vier, entregue o trabalho em fragmento "
                "(sem --identidade) e diga ao advogado que ele precisa enviar o timbrado na "
                "página Seus dados do conector.")
        _verificar_marca_identidade(d, perfil)




        _exigir_pacote_integro(d)
        return d
    if dir_templates is None:
        dir_templates = dir_templates_identidade()
    base = os.path.dirname(perfil.get("_caminho") or os.path.join(_raiz(), "perfis", "sem-nome"))
    destino = os.path.join(base, ".identidade", _impressao(perfil, dir_templates))
    marca = os.path.join(destino, "mapping.json")
    if not os.path.isfile(marca):
        gerar_identidade(perfil, dir_templates, destino)


    _verificar_marca_identidade(destino, perfil)
    return destino




def estilo(perfil=None):
    '{"fonte","tamanho_meio_pt","cor"} — defaults Dissero quando ausente/sem perfil.'



    est = dict(ESTILO_PADRAO)
    if not perfil:
        return est
    fonte = _get(perfil, "identidade_visual.fonte_corpo")
    if fonte:
        est["fonte"] = str(fonte)
    tam = _get(perfil, "identidade_visual.tamanho_corpo_pt")
    if isinstance(tam, (int, float)) and 6 <= tam <= 24:
        est["tamanho_meio_pt"] = int(round(tam * 2))
    cor = _get(perfil, "identidade_visual.cor_texto_hex") or ""
    cor = cor.lstrip("#") if isinstance(cor, str) else ""
    if _HEX.match(cor):
        est["cor"] = cor.upper()
    return est


def descrever_estilo(perfil):
    'A linha "Estilo" do --status, dizendo DE ONDE vem cada valor.'










    est = estilo(perfil)
    fonte = _get(perfil, "identidade_visual.fonte_corpo") if perfil else None
    tam = _get(perfil, "identidade_visual.tamanho_corpo_pt") if perfil else None
    tam_valido = isinstance(tam, (int, float)) and 6 <= tam <= 24
    partes = [
        f"fonte {est['fonte']} (da banca)" if fonte else "fonte do tema",
        f"{est['tamanho_meio_pt'] / 2:g}pt (da banca)" if tam_valido else "tamanho do tema",
        f"cor #{est['cor']}",
    ]
    return " · ".join(partes)


def cidade_assinatura(perfil):
    return _get(perfil, "foro.cidade_assinatura", "")


def margem_protocolo(perfil):
    return _get(perfil, "preferencias_operacionais.margem_protocolo_dias_uteis", 2)


def tribunais_prioritarios(perfil):
    'A ordem de tribunais que a banca declarou para a pesquisa. Lista, possivelmente'












    v = _get(perfil, "preferencias_operacionais.tribunais_prioritarios", [])
    return list(v) if isinstance(v, (list, tuple)) else []


def estilo_overrides(perfil):
    return _get(perfil, "estilo_escrita.overrides", {}) or {}


def contato_publico(perfil):
    'Linha de contato para User-Agent HTTP e afins. Sem perfil, nada de identidade —'

    if not perfil:
        return "dissero (assistente juridico; contato via advogado responsavel)"



    oab = _texto_do_perfil(_get(perfil, "advogado.oab", "") or "")
    oab = unicodedata.normalize("NFKD", oab.replace("–", "-").replace("—", "-"))
    oab = "".join(ch if 32 <= ord(ch) < 127 else " "
                  for ch in oab if not unicodedata.combining(ch))
    oab = " ".join(oab.split())
    if not oab:
        return "dissero (assistente juridico)"
    return f"dissero (assistente juridico; contato via {oab})".strip()













MARCA_ESPELHO = "_espelho"



RASTRO = ("_caminho", "_origem", "_em", "_sha", "_texto_servidor", MARCA_ESPELHO)


def caminho_espelho():
    """Onde o plugin INSTALADO procura o perfil."""
    return os.path.join(os.path.expanduser("~"), ".config", "dissero", "perfil.json")


def _essencia(perfil):
    """O perfil sem o que é meta — para comparar conteúdo, não carimbo."""
    return {k: v for k, v in (perfil or {}).items() if k not in RASTRO}


def resolver_fonte():
    'A fonte autorada, que NUNCA é o próprio espelho. Sem isto, `instalar()` num ambiente'

    espelho = os.path.abspath(caminho_espelho())
    caminho = resolver_caminho()
    if caminho and os.path.abspath(caminho) != espelho:
        return caminho
    return None


def conferir():
    """(estado, detalhe). Estados: `sincronizado`, `divergente`, `sem_espelho`, `sem_fonte`."""
    _espelho_atual = caminho_espelho()
    if os.path.isfile(_espelho_atual):
        try:
            _p = carregar(_espelho_atual)
        except PerfilError:
            _p = None
        if _p and _p.get("_origem") == "servidor":
            return "sincronizado", "perfil do servidor"
    fonte, espelho = resolver_fonte(), caminho_espelho()
    if not fonte:
        return "sem_fonte", "nenhum perfil autorado (só o espelho, ou nenhum)"
    if not os.path.isfile(espelho):
        return "sem_espelho", f"o plugin instalado não acharia perfil ({espelho})"
    try:
        a, b = _essencia(carregar(fonte)), _essencia(carregar(espelho))
    except PerfilError as e:
        return "divergente", f"espelho ilegível: {e}"
    if a == b:
        return "sincronizado", fonte
    campos = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    return "divergente", f"diferem em {campos} — a fonte é {fonte}"


def instalar(origem=None, forcar=False):
    'Grava o espelho a partir da fonte. Devolve (acao, caminho).'





    fonte = origem or resolver_fonte()
    if not fonte:
        raise PerfilAusente(
            "nenhum perfil autorado para espelhar. Crie `perfis/<id>/perfil.json` "
            "(modelo em `perfis/exemplo/`) antes de instalar o espelho.")
    perfil = carregar(fonte)
    erros = validar(perfil)
    if erros:
        raise PerfilError("perfil inválido, não espelhado:\n  - " + "\n  - ".join(erros))

    destino = caminho_espelho()



    if not forcar:
        try:
            with open(destino, encoding="utf-8") as fh:
                _no_disco = json.load(fh)
        except (OSError, ValueError, UnicodeDecodeError):
            _no_disco = None
        if isinstance(_no_disco, dict) and _no_disco.get("_origem") == "servidor":
            raise PerfilDoServidor(
                "o perfil desta máquina vem do Dissero, e o espelho do repositório não o "
                f"substitui: {destino}. O servidor é a fonte desde o login — edite os seus dados "
                "pela conversa, não por arquivo. Para espelhar mesmo assim, rode "
                "`perfil_advogado.py --instalar --forcar` (a cópia atual vira .anterior).")
    novo = _essencia(perfil)
    novo[MARCA_ESPELHO] = {
        "_leia": "GERADO por perfil_advogado.py --instalar. Não edite este arquivo: edite a "
                 "origem abaixo e rode --instalar de novo. `--conferir` avisa se divergirem.",
        "origem": os.path.abspath(fonte).replace("\\", "/"),
    }

    if os.path.isfile(destino):
        if not forcar:
            try:
                if _essencia(carregar(destino)) == _essencia(perfil):
                    return "em_dia", destino
            except PerfilError:
                pass
        shutil.copy2(destino, destino + ".anterior")
        acao = "atualizado"
    else:
        acao = "criado"

    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(novo, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return acao, destino










def _sha_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def gravar_do_servidor(texto, destino=None):
    'Grava o perfil devolvido por `perfil_do_advogado`. Aceita o texto inteiro da ferramenta'


    if isinstance(texto, bytes):
        texto = texto.decode("utf-8")
    ini = texto.find("{")
    if ini < 0:
        raise PerfilError("o texto recebido do servidor não contém JSON")
    corpo = texto[ini:].strip()
    try:
        perfil = json.loads(corpo)
    except json.JSONDecodeError as e:
        raise PerfilError(f"JSON do servidor malformado: {e}")
    erros = validar(perfil)
    if erros:
        raise PerfilError("perfil do servidor inválido:\n  - " + "\n  - ".join(erros))
    perfil = {k: v for k, v in perfil.items() if not k.startswith("_")}
    perfil.update({"_origem": "servidor", "_em": perfil.get("em"),
                  "_sha": _sha_texto(corpo), "_texto_servidor": corpo})
    destino = destino or caminho_espelho()
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(perfil, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return destino


def divergente(perfil) -> bool:
    'True se a cópia local não bate com o que o servidor serviu (transcrição alterada).'



    if not perfil or perfil.get("_origem") != "servidor":
        return False
    t = perfil.get("_texto_servidor") or ""
    if _sha_texto(t) != perfil.get("_sha"):
        return True
    try:
        original = json.loads(t)
    except Exception:
        return True
    atual = {k: v for k, v in perfil.items() if not k.startswith("_")}
    original = {k: v for k, v in original.items() if not k.startswith("_")}
    return atual != original


def dir_identidade_propria():
    """Onde o timbrado PRÓPRIO (o pacote extraído por `--gravar-identidade`) vive."""
    return os.path.join(os.path.expanduser("~"), ".config", "dissero", "identidade")















_CHAVE_MANIFESTO = "hashes"
_ARQ_MAPEAMENTO = "mapping.json"



_AVISADOS_SEM_MANIFESTO = set()



_AVISADOS_IMAGEM_AVULSA = set()


def _sha_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def _partes_gravadas(diretorio):
    'Caminhos relativos (com barra normal) de tudo que há no pacote, menos o próprio'

    saida = []
    for raiz, _dirs, arquivos in os.walk(diretorio):
        for nome in arquivos:
            rel = os.path.relpath(os.path.join(raiz, nome), diretorio).replace(os.sep, "/")
            if rel != _ARQ_MAPEAMENTO:
                saida.append(rel)
    return sorted(saida)


def _manifesto_do_pacote(diretorio):
    '`{caminho_relativo: sha256}` gravado em `mapping.json`, ou `None` quando o pacote não'




    try:
        with open(os.path.join(diretorio, _ARQ_MAPEAMENTO), encoding="utf-8") as fh:
            mapa = json.load(fh) or {}
    except (OSError, ValueError, TypeError):
        return None
    hashes = mapa.get(_CHAVE_MANIFESTO)
    if not isinstance(hashes, dict) or not hashes:
        return None
    return {str(k): str(v) for k, v in hashes.items()}


def conferir_pacote_identidade(diretorio=None):
    '`(estado, detalhe)` do pacote de timbrado próprio em `diretorio`.'



















    diretorio = diretorio or dir_identidade_propria()
    if not os.path.isdir(diretorio):
        return "ausente", "não há pacote de timbrado próprio instalado"
    hashes = _manifesto_do_pacote(diretorio)
    if hashes is None:
        return "sem_manifesto", (
            "este pacote de timbrado foi gravado antes de o plugin registrar a impressão "
            "digital de cada arquivo, então não dá para conferir se ele continua sendo o "
            "que o Dissero serviu. Chame perfil_do_advogado(parte=\"identidade\") e grave "
            "com `perfil_advogado.py --gravar-identidade <zip>`. A peça sai normalmente; "
            "depois de regravar, esta conferência passa a valer.")
    em_disco = set(_partes_gravadas(diretorio))
    no_manifesto = set(hashes)
    faltando = sorted(no_manifesto - em_disco)
    sobrando = sorted(em_disco - no_manifesto)
    diferentes = []
    for rel in sorted(no_manifesto & em_disco):
        try:
            if _sha_arquivo(os.path.join(diretorio, rel)) != hashes[rel]:
                diferentes.append(rel)
        except OSError:
            faltando.append(rel)
    if faltando or sobrando or diferentes:
        partes = []
        if diferentes:
            partes.append("alterado(s): " + ", ".join(diferentes))
        if faltando:
            partes.append("faltando: " + ", ".join(sorted(set(faltando))))
        if sobrando:
            partes.append("a mais: " + ", ".join(sobrando))
        return "alterado", "; ".join(partes)
    return "integro", f"{len(no_manifesto)} arquivo(s) conferido(s)"


def _exigir_pacote_integro(diretorio):
    'Recusa NOMEADA quando o pacote em `diretorio` não é mais o que o servidor serviu.'




    estado, detalhe = conferir_pacote_identidade(diretorio)
    if estado == "alterado":
        raise PerfilError(
            "TIMBRADO ALTERADO FORA DO PACOTE — os arquivos do timbrado em identidade/ não "
            "são mais os que o Dissero serviu (" + detalhe + "). Cabeçalho e rodapé não se "
            "escrevem nem se ajustam à mão. Chame perfil_do_advogado(parte=\"identidade\") e "
            "grave com `perfil_advogado.py --gravar-identidade <zip>`; a peça não sai com um "
            "timbrado remendado.")
    if estado == "sem_manifesto" and diretorio not in _AVISADOS_SEM_MANIFESTO:
        _AVISADOS_SEM_MANIFESTO.add(diretorio)
        try:
            print("AVISO: " + detalhe, file=sys.stderr)
        except Exception:
            pass

















def origem_timbrado(perfil):
    '`"proprio"` quando a peça vai usar o pacote do Dissero, `"padrao"` no resto.'



    return "proprio" if _get(perfil, "identidade_visual.timbrado") == "proprio" else "padrao"


def sha_manifesto_identidade(diretorio=None):
    'sha256 do MANIFESTO do pacote de timbrado próprio, ou `""` quando não há manifesto.'




    hashes = _manifesto_do_pacote(diretorio or dir_identidade_propria())
    if not hashes:
        return ""
    return _sha_texto(json.dumps(hashes, sort_keys=True, separators=(",", ":")))












_RX_ENTRADA_IDENTIDADE = re.compile(
    r"word/(header\d+\.xml|footer\d+\.xml|_rels/(header|footer)\d+\.xml\.rels|"
    r"media/(?!\.{1,2}$)[^/\\]+)"
    r"|(assinatura|brasao)\.(png|jpe?g)")


def _entradas_zip(z):
    '[(nome, ZipInfo)] com o nome como o Worker e o navegador o gravam.'






    saida = []
    for info in z.infolist():
        nome = info.filename
        if not info.flag_bits & 0x800:
            try:
                nome = nome.encode("cp437").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        saida.append((nome, info))
    return saida


def _marca_do_perfil_resolvido():
    '`email_marca` do perfil que resolve AGORA, ou `""`.'





    return _marca_e_legibilidade()[0]


def _marca_e_legibilidade():
    '`(marca, ilegível)` do perfil que resolveria AGORA. São estados DIFERENTES:'











    try:
        perfil = carregar()
    except (PerfilError, OSError, UnicodeDecodeError, TypeError):
        return "", True
    if not perfil:
        return "", False
    return str(_get(perfil, "email_marca") or ""), False





TETO_PACOTE_BAIXADO = 1024 * 1024


def _baixar_pacote(url):
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dsr-perfil/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            dados = r.read(TETO_PACOTE_BAIXADO + 1)
    except urllib.error.HTTPError as e:
        raise PerfilError(f"o endereço do timbrado não serviu (HTTP {e.code}); ele vale 15 minutos: chame "
                          "perfil_do_advogado(parte=\"identidade\") de novo")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise PerfilError(f"não foi possível baixar o timbrado ({type(e).__name__}); tente de novo")
    if len(dados) > TETO_PACOTE_BAIXADO:
        raise PerfilError("o pacote de timbrado baixado é maior que o permitido")
    return dados


def marca_do_pacote_no_disco(destino=None):
    '`marca` gravada no `mapping.json` do pacote que está em `destino`, ou `""`.'



    destino = destino or dir_identidade_propria()
    try:
        with open(os.path.join(destino, "mapping.json"), encoding="utf-8") as fh:
            return str((json.load(fh) or {}).get("marca") or "")
    except (OSError, ValueError, TypeError):
        return ""


def troca_de_dono_do_timbrado(destino=None):
    '`(marca_no_disco, marca_do_perfil)` quando `--gravar-identidade` vai APAGAR um pacote'














    disco = marca_do_pacote_no_disco(destino)
    perfil_marca, _ilegivel = _marca_e_legibilidade()
    if disco and perfil_marca and disco != perfil_marca:
        return disco, perfil_marca
    return None


def gravar_identidade(pacote, destino=None):
    'Extrai o zip do timbrado próprio (header*/footer*/rels/media, assinatura e brasão) em'












    destino = destino or dir_identidade_propria()
    if isinstance(pacote, str) and re.match(r"^https?://", pacote, re.I):
        dados = _baixar_pacote(pacote)
    else:
        dados = open(pacote, "rb").read() if isinstance(pacote, str) else pacote
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
        entradas = _entradas_zip(z)
    except zipfile.BadZipFile:
        raise PerfilError(
            "o pacote de timbrado não é um zip válido; chame "
            "perfil_do_advogado(parte=\"identidade\") de novo")


    for nome, _info in entradas:
        if not _RX_ENTRADA_IDENTIDADE.fullmatch(nome):
            raise PerfilError(f"o pacote de timbrado tem um arquivo inesperado: {nome}")
    if os.path.isdir(destino):
        shutil.rmtree(destino)
    n = 0
    avulsas = []
    for nome, info in entradas:
        rel = nome[len("word/"):] if nome.startswith("word/") else nome
        if rel == nome:
            avulsas.append(nome)
        alvo = os.path.join(destino, rel)
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        with open(alvo, "wb") as fh:
            fh.write(z.read(info))
        n += 1
    mapping = {"origem": "servidor", "arquivos": n}
    if avulsas:
        mapping["avulsas"] = sorted(avulsas)



    mapping[_CHAVE_MANIFESTO] = {rel: _sha_arquivo(os.path.join(destino, rel))
                                 for rel in _partes_gravadas(destino)}
    _AVISADOS_SEM_MANIFESTO.discard(destino)
    marca, perfil_ilegivel = _marca_e_legibilidade()
    if marca:
        mapping["marca"] = marca
    elif perfil_ilegivel:



        mapping["marca_indeterminada"] = True
    with open(os.path.join(destino, "mapping.json"), "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, ensure_ascii=False)
    return n










def imagem_avulsa(perfil, tipo):
    """Caminho da imagem (`assinatura` ou `brasao`) do advogado do perfil, ou None."""
    if tipo not in ("assinatura", "brasao") or not isinstance(perfil, dict):
        return None
    if not _get(perfil, f"identidade_visual.{tipo}"):
        return None
    d = dir_identidade_propria()
    caminho = next((os.path.join(d, f"{tipo}.{ext}") for ext in ("png", "jpg", "jpeg")
                    if os.path.isfile(os.path.join(d, f"{tipo}.{ext}"))), None)
    if not caminho:
        return None
    try:
        _verificar_marca_identidade(d, perfil)





        _exigir_pacote_integro(d)
    except PerfilError as erro:




        if d not in _AVISADOS_IMAGEM_AVULSA:
            _AVISADOS_IMAGEM_AVULSA.add(d)
            try:
                print(f"AVISO: a peça sai SEM assinatura e SEM brasão porque o pacote de "
                      f"identidade não pôde ser usado. {erro}", file=sys.stderr)
            except Exception:
                pass
        return None
    return caminho











def caminho_clone():
    return os.path.join(os.path.expanduser("~"), ".config", "dissero", "clone.json")


_CABECALHO_CLONE = "[Dissero]"



_RX_SECAO_CLONE = re.compile(r"^=== (TRAJETÓRIA|MENTE|VOZ|REPERTÓRIO) · (.+?) ===$", re.M)
_CHAVE_SECAO = {"TRAJETÓRIA": "trajetoria", "MENTE": "mente", "VOZ": "voz", "REPERTÓRIO": "repertorio"}


def _secoes_clone(texto):
    marcas = list(_RX_SECAO_CLONE.finditer(texto))
    secoes = {}
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        secoes[_CHAVE_SECAO[m.group(1)]] = {
            "texto": texto[m.end():fim].strip(),
            "validada": m.group(2).startswith("validada em"),
        }
    return secoes


def gravar_clone_do_servidor(texto, destino=None):
    """Grava o que `clone_do_advogado` devolveu. Devolve o caminho gravado."""
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8")
    texto = texto.strip()
    if not texto.startswith(_CABECALHO_CLONE) or not ("Clone do advogado" in texto or "não configurou Mente nem Voz" in texto):
        raise PerfilError("o texto recebido não veio de clone_do_advogado; chame a ferramenta de novo e grave a resposta inteira")
    registro = {"_origem": "servidor", "_sha": _sha_texto(texto), "_texto_servidor": texto, "secoes": _secoes_clone(texto)}
    marca = _marca_do_perfil_resolvido()
    if marca:
        registro["email_marca"] = marca
    destino = destino or caminho_clone()
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    provisorio = destino + ".tmp"
    with open(provisorio, "w", encoding="utf-8") as fh:
        json.dump(registro, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(provisorio, destino)
    return destino


def clone_local(caminho=None):
    'Registro do clone gravado nesta máquina, ou None se não houver. Levanta PerfilError se'

    caminho = caminho or caminho_clone()
    if not os.path.isfile(caminho):
        return None
    try:
        with open(caminho, encoding="utf-8") as fh:
            registro = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise PerfilError("a cópia local do clone está ilegível; chame clone_do_advogado e grave de novo")
    if not isinstance(registro, dict) or registro.get("_origem") != "servidor":
        raise PerfilError("a cópia local do clone não veio do servidor; chame clone_do_advogado e grave de novo")
    if _sha_texto(registro.get("_texto_servidor") or "") != registro.get("_sha"):
        raise PerfilError("a cópia local do clone foi alterada depois de gravada; chame clone_do_advogado e grave de novo")
    marca, atual = registro.get("email_marca") or "", _marca_do_perfil_resolvido()
    if marca and atual and marca != atual:
        raise PerfilError("o clone gravado nesta máquina é de outro advogado; chame clone_do_advogado e grave de novo")
    return registro







_RX_MARCAS = re.compile(r"(?im)^[\W\d]*marcas proibidas\W*?[:\-–—]\s*(.+)$")
_RX_GENERICO = re.compile(r"(?i)^(qualquer|todo|toda|todos|todas|nenhum|nenhuma|outros?|outras?|etc)\b")


def marcas_proibidas_da_voz(texto):
    """Termos da linha "Marcas proibidas" da Voz, na ordem, sem repetição. PURA."""
    m = _RX_MARCAS.search(str(texto or ""))
    if not m:
        return []
    termos = []
    for parte in re.split(r"[,.;]|\s+e\s+", m.group(1)):
        t = parte.strip().strip("«»\"'*`").strip()
        if not t or len(t.split()) > 4 or _RX_GENERICO.match(t):
            continue
        if t.casefold() not in {x.casefold() for x in termos}:
            termos.append(t)
    return termos


def marcas_proibidas():
    'Termos proibidos pela Voz da cópia local do clone; [] sem clone, sem Voz ou clone'

    try:
        registro = clone_local()
    except PerfilError:
        return []
    voz = (((registro or {}).get("secoes") or {}).get("voz") or {}).get("texto") or ""
    return marcas_proibidas_da_voz(voz)


def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()


def achar_marcas(texto, termos):
    '[(termo, ocorrências)] dos termos presentes no texto, como palavra inteira, sem'

    base = _sem_acento(str(texto or ""))
    achados = []
    for t in termos:
        padrao = r"(?<!\w)" + r"\s+".join(re.escape(p) for p in _sem_acento(t).split()) + r"(?!\w)"
        n = len(re.findall(padrao, base))
        if n:
            achados.append((t, n))
    return achados










CONECTORES_DO_INVENTARIO = ("eluxi", "zetema", "cnpja")
_RX_FONTE_RUN = re.compile(r'<w:rFonts\b[^>]*\bw:ascii="([^"]+)"')


def _fontes_do_pacote(diretorio):
    """{arquivo: [fontes]} dos cabeçalhos e rodapés do pacote de timbrado."""
    out = {}
    try:
        nomes = sorted(os.listdir(diretorio))
    except OSError:
        return out
    for nome in nomes:
        if not re.fullmatch(r"(?:header|footer)\d*\.xml", nome):
            continue
        try:
            with open(os.path.join(diretorio, nome), encoding="utf-8") as fh:
                fontes = sorted(set(_RX_FONTE_RUN.findall(fh.read())))
        except (OSError, UnicodeDecodeError):
            continue
        if fontes:
            out[nome] = fontes
    return out


def pontos_a_conferir(perfil, dir_pacote=None):
    """Lista de frases, uma por ponto do perfil a confirmar com o advogado; vazia quando nada."""
    pontos = []
    if not _get(perfil, "advogado.areas"):
        pontos.append("advogado.areas vazio: as áreas de atuação não constam do perfil")
    if not _get(perfil, "foro.feriados_locais"):
        pontos.append("foro.feriados_locais vazio: o prazo sai sem feriado estadual e municipal "
                      "(a calculadora avisa a cada cálculo)")
    conectores = _get(perfil, "conectores")
    if isinstance(conectores, dict):
        ids = [c for c in conectores if not str(c).startswith("_")]
        fora = [c for c in ids if c not in CONECTORES_DO_INVENTARIO]
        faltam = [c for c in CONECTORES_DO_INVENTARIO if c not in conectores]
        if fora:
            pontos.append("conectores fora do inventário, ignorados: " + ", ".join(fora))
        if faltam:
            pontos.append("conectores da casa sem preferência no perfil (valem como auto): "
                          + ", ".join(faltam))
    corpo = str(_get(perfil, "identidade_visual.fonte_corpo") or "").strip()
    if corpo and _get(perfil, "identidade_visual.timbrado") == "proprio":
        diretorio = dir_pacote or dir_identidade_propria()
        for arquivo, fontes in _fontes_do_pacote(diretorio).items():
            outras = [f for f in fontes if f.lower() != corpo.lower()]
            if outras:
                parte = "rodapé" if arquivo.startswith("footer") else "cabeçalho"
                pontos.append(f"timbrado próprio: {parte} ({arquivo}) em {', '.join(outras)}, "
                              f"corpo em {corpo}")
    return pontos


def status():
    """Diagnóstico sem expor o conteúdo do perfil."""
    caminho = resolver_caminho()
    if not caminho:
        return {"resolvido": False, "caminho": None, "valido": False, "erros": ["nenhum perfil encontrado"]}
    try:
        perfil = carregar(caminho)
    except (PerfilError, OSError, UnicodeDecodeError, TypeError) as e:




        return {"resolvido": True, "caminho": caminho, "valido": False, "erros": [str(e)]}
    erros = validar(perfil)
    estado, detalhe = conferir()





    pacote = None
    if _get(perfil, "identidade_visual.timbrado") == "proprio":
        est_p, det_p = conferir_pacote_identidade()
        pacote = {"estado": est_p, "detalhe": det_p}
    return {"resolvido": True, "caminho": caminho, "valido": not erros, "erros": erros,
            "timbrado_proprio": pacote,
            "pontos_a_conferir": pontos_a_conferir(perfil),
            "advogado": _get(perfil, "advogado.nome") if not erros else None,
            "origem": perfil.get("_origem") or "local", "em": perfil.get("_em"),
            "divergente": divergente(perfil),
            "espelho": {"caminho": caminho_espelho(), "estado": estado, "detalhe": detalhe}}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Perfil do advogado (motor × configuração).")
    ap.add_argument("--perfil", help="caminho explícito do perfil.json")
    ap.add_argument("--status", action="store_true", help="diagnóstico da resolução")
    ap.add_argument("--tribunais", action="store_true",
                    help="imprime, em JSON, a ordem de tribunais que a banca declarou para "
                         "a pesquisa (lista vazia = sem preferência)")
    ap.add_argument("--gerar-identidade", nargs=2, metavar=("DIR_TEMPLATES", "DIR_SAIDA"))
    ap.add_argument("--instalar", action="store_true",
                    help="espelha a fonte em ~/.config/dissero/perfil.json (o plugin instalado)")
    ap.add_argument("--forcar", action="store_true",
                    help="com --instalar, grava também por cima do perfil que o Dissero serviu "
                         "(a cópia atual vira .anterior)")
    ap.add_argument("--conferir", action="store_true",
                    help="fonte e espelho batem? exit !=0 se divergirem")
    ap.add_argument("--gravar-do-servidor", metavar="ARQUIVO",
                    help="grava o perfil que `perfil_do_advogado` devolveu ('-' lê stdin)")
    ap.add_argument("--gravar-identidade", metavar="ZIP_OU_ENDERECO",
                    help="extrai o pacote de timbrado próprio de um .zip ou do endereço que o servidor devolveu")
    ap.add_argument("--clone", action="store_true",
                    help="imprime o clone do advogado gravado nesta máquina (Mente, Voz, Repertório)")
    ap.add_argument("--gravar-clone-do-servidor", metavar="ARQUIVO",
                    help="grava o texto que `clone_do_advogado` devolveu ('-' lê stdin)")
    a = ap.parse_args(argv)

    if a.clone:
        try:
            registro = clone_local()
        except PerfilError as e:
            print(f"ERRO: {e}")
            return 1
        if not registro or not registro.get("secoes"):
            print("Sem clone configurado nesta máquina. Chame clone_do_advogado; sem clone, use o estilo Dissero padrão.")
            return 0
        print(registro["_texto_servidor"])
        return 0

    if a.gravar_clone_do_servidor:
        try:
            texto = (sys.stdin.buffer.read().decode("utf-8") if a.gravar_clone_do_servidor == "-"
                     else open(a.gravar_clone_do_servidor, encoding="utf-8").read())
            destino = gravar_clone_do_servidor(texto)
        except (PerfilError, OSError, UnicodeDecodeError) as e:
            print(f"ERRO: {e}")
            return 1
        print(f"clone gravado: {destino}")
        return 0

    if a.tribunais:


        try:
            caminho = a.perfil or resolver_caminho()
            perfil = carregar(caminho) if caminho else None
        except PerfilError:
            perfil = None
        print(json.dumps({"tribunais_prioritarios": tribunais_prioritarios(perfil)},
                         ensure_ascii=False))
        return 0

    if a.gravar_do_servidor:


        try:
            texto = (sys.stdin.buffer.read().decode("utf-8") if a.gravar_do_servidor == "-"
                     else open(a.gravar_do_servidor, encoding="utf-8").read())
            gravar_do_servidor(texto)
        except (PerfilError, OSError, UnicodeDecodeError) as e:
            print(f"ERRO: {e}")
            return 1
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0

    if a.gravar_identidade:




        _troca = troca_de_dono_do_timbrado()
        try:
            gravar_identidade(a.gravar_identidade)
        except (PerfilError, OSError, UnicodeDecodeError) as e:
            print(f"ERRO: {e}")
            return 1
        if _troca:
            print(f"AVISO: o timbrado que estava aqui era da marca {_troca[0]} e foi "
                  f"substituído pelo da marca {_troca[1]}, que é a do perfil que resolve "
                  f"agora. Se isso não era o esperado, chame "
                  f"perfil_do_advogado(parte=\"identidade\") com o login certo e grave de novo.")
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0

    if a.status:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0

    if a.conferir:
        estado, detalhe = conferir()
        print(f"{estado}: {detalhe}")
        return 0 if estado == "sincronizado" else 1

    if a.instalar:
        try:
            acao, destino = instalar(a.perfil, forcar=a.forcar)
        except (PerfilAusente, PerfilError) as e:
            print(f"ERRO: {e}")
            return 1
        print(f"espelho {acao}: {destino}")
        return 0

    try:
        perfil = carregar(a.perfil)
    except PerfilError as e:
        print(f"ERRO: {e}")
        return 2
    if perfil is None:
        print(MSG_SEM_PERFIL)
        return 1

    erros = validar(perfil)
    if erros:
        print("PERFIL INVÁLIDO:")
        for e in erros:
            print("  x", e)
        return 1

    if a.gerar_identidade:
        dir_t, dir_s = a.gerar_identidade
        try:
            gerados = gerar_identidade(perfil, dir_t, dir_s)
        except PerfilError as e:
            print(f"ERRO: {e}")
            return 3
        print(f"Identidade gerada ({len(gerados)} arquivos) em {dir_s}:")
        for g in gerados:
            print("  -", os.path.basename(g))
        return 0

    print("Perfil VÁLIDO.")
    print(f"  Arquivo:    {perfil['_caminho']}")
    print(f"  Advogado:   {_get(perfil, 'advogado.nome')} ({_get(perfil, 'advogado.oab')})")
    print(f"  Assinatura: {cidade_assinatura(perfil)} - margem D-{margem_protocolo(perfil)}")
    print(f"  Estilo:     {descrever_estilo(perfil)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
