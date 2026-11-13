#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'pesquisa_tentada.py — o registro de que a pesquisa de jurisprudência foi TENTADA.'


































import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import unicodedata

NOME = "PESQUISA_TENTADA.json"
SCHEMA = "dsr.pesquisa_tentada.v1"
MOTIVOS = ("conector_ausente", "conector_falhou", "sigilo")
ACHADOS_SCHEMAS = ("dsr.achados.v2", "dsr.achados.v3")





_RX_CAIXA = re.compile(r"\[\s*JURISPRUD[ÊE]NCIA\s+A\s+CONFERIR", re.I)
_RX_ACHADO = re.compile(r"^\s*>>\s*achado\s*:", re.I | re.M)
_RX_SUMULA = re.compile(
    r"\bS[úu]mulas?\s+(?:Vinculantes?\s+)?(?:n\.?[ºo°]?\s*)?(\d{1,4})(?:-([A-Za-z])\b)?"
    r"(?:\s*,?\s*(?:d[oa]s?\s+)?(STF|STJ|TST|TSE|STM|TNU|TRF\s*\d|TRT\s*\d{1,2}|TJ[A-Z]{2}))?", re.I)
_RX_OJ = re.compile(
    r"\b(?:OJ|Orienta[çc][ãa]o\s+Jurisprudencial)\s+(?:Transit[óo]ria\s+)?(?:n\.?[ºo°]?\s*)?(\d{1,4})"
    r"(?:\s*,?\s*d[ao]\s+(SB?DI[-\s]?[12I]{1,2}|SDC|Tribunal\s+Pleno))?", re.I)
_RX_TEMA = re.compile(r"\bTema\s+(?:n\.?[ºo°]?\s*)?(\d{1,2}\.?\d{1,3})\b(?=[^\n]{0,60}"
                      r"(?:STF|STJ|TST|repercuss[ãa]o|repetitiv))", re.I)
_RX_JULGADO = re.compile(
    r"\b(?:REsp|AREsp|AgInt|AgRg|EREsp|EDcl|RE|ARE|ADI|ADC|ADPF|HC|RHC|MS|RMS|RR|AIRR|RO|ROT|AP|"
    r"E-RR|E-ED-RR|IRDR|IAC|IRR)\s*-?\s*(?:n\.?[ºo°]?\s*)?\d[\d.\-/]{2,}", re.I)
_RX_TITULO = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[IVXLC\d]+\s*[.)\-–—]\s*)?(?:D[OA]S?\s+)?(DIREITO|FUNDAMENTOS?(?:\s+JUR[ÍI]DICOS?)?|"
    r"FUNDAMENTA[ÇC][ÃA]O|RAZ[ÕO]ES(?:\s+D[OE]\s+\w+)?|M[ÉE]RITO|PRELIMINAR(?:ES)?|CABIMENTO|"
    r"TESES?|PREJUDICIAL(?:\s+DE\s+M[ÉE]RITO)?)\b[^\n]{0,60}$", re.M)


def _titulos_de_fundamentacao(texto):
    """Linhas que são título de fundamentação: título do markdown, ou linha curta em maiúsculas."""
    out = []
    for m in _RX_TITULO.finditer(texto or ""):
        linha = m.group(0).strip()
        nu = linha.lstrip("#").strip()
        if linha.startswith("#") or (nu == nu.upper() and len(nu) <= 80):
            out.append(nu)
    return out


def sumulas_citadas(texto):
    """Súmulas e orientações jurisprudenciais citadas, normalizadas e sem repetir, na ordem."""
    out = []
    for m in _RX_SUMULA.finditer(texto or ""):
        vinc = " Vinculante" if re.search(r"vinculante", m.group(0), re.I) else ""
        letra = f"-{m.group(2).upper()}" if m.group(2) else ""
        trib = (" do " + re.sub(r"\s+", "", m.group(3)).upper()) if m.group(3) else ""
        out.append(f"Súmula{vinc} {m.group(1)}{letra}{trib}")
    for m in _RX_OJ.finditer(texto or ""):
        orgao = (" da " + re.sub(r"\s+", " ", m.group(2)).upper()) if m.group(2) else ""
        out.append(f"OJ {m.group(1)}{orgao}")
    return list(dict.fromkeys(out))


def tem_tese_juridica(texto):
    '(tem?, por quê em português) da peça em texto. Falso: mero requerimento, sem fundamento'

    texto = texto or ""
    if _RX_CAIXA.search(texto):
        return True, "a peça traz trecho marcado como jurisprudência a conferir"
    if _RX_ACHADO.search(texto) or _RX_JULGADO.search(texto):
        return True, "a peça cita julgado"
    citadas = sumulas_citadas(texto)
    if citadas:
        return True, "a peça cita " + ", ".join(citadas[:3]) + (" e outras" if len(citadas) > 3 else "")
    if _RX_TEMA.search(texto):
        return True, "a peça cita tema de repercussão geral ou de recurso repetitivo"
    titulos = _titulos_de_fundamentacao(texto)
    if titulos:
        return True, f"a peça tem fundamentação jurídica («{titulos[0][:60]}»)"
    return False, ""



def _selo(reg):
    base = {k: v for k, v in reg.items() if k != "selo"}
    return hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


_VAZIAS = {"a", "o", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "que", "nao", "foi",
           "por", "para", "com", "sem", "um", "uma", "ao", "as", "os", "se", "esta", "estava", "esta", "ser",
           "possivel", "pesquisa", "pesquisar", "jurisprudencia", "indisponivel", "erro", "falha", "falhou",
           "conector", "conectores", "ferramenta", "ferramentas", "motivo", "generico", "disponivel", "ha",
           "tem", "tinha", "houve", "nenhum", "nenhuma", "rodar", "concluir", "pode", "pude", "conseguiu"}


def _palavras_proprias(texto):
    return {p for p in re.findall(r"[a-z0-9_]{3,}", _sem_acento(texto)) if p not in _VAZIAS}


def _detalhe_generico(detalhe):
    'Motivo pelo qual o detalhe não serve, ou None. Detalhe que só repete «não foi possível'

    d = (detalhe or "").strip()
    if len(d) < 40:
        return "o detalhe tem menos de 40 caracteres: diga o que aconteceu (o que foi procurado ou chamado, e o que veio)"
    if len(_palavras_proprias(d)) < 4:
        return ("o detalhe é genérico: nomeie o conector ou a ferramenta, o que foi tentado e o que "
                "voltou, em vez de repetir que a pesquisa não foi possível")
    return None


def _consulta(texto):
    """{fonte, termos} de "<fonte>: <termos>", ou None."""
    if ":" not in (texto or ""):
        return None
    fonte, termos = (x.strip() for x in texto.split(":", 1))
    if len(fonte) < 3 or len(termos) < 8 or len(re.findall(r"\w{3,}", termos)) < 2:
        return None
    if _sem_acento(fonte) in ("memoria", "conhecimento", "conhecimento proprio", "modelo", "nenhuma", "nenhum"):
        return None
    return {"fonte": fonte, "termos": termos}


def _ler_achados(caminho):
    """(total de achados, erro) do conjunto de achados."""
    try:
        with open(caminho, encoding="utf-8") as fh:
            dados = json.load(fh)
    except Exception:
        return 0, "o arquivo de achados não é JSON legível"
    if not isinstance(dados, dict) or dados.get("schema_version") not in ACHADOS_SCHEMAS:
        return 0, "o arquivo de achados está fora do contrato dsr.achados.v2 ou dsr.achados.v3"
    achados = dados.get("achados")
    if not isinstance(achados, list) or not achados or not all(isinstance(a, dict) and a for a in achados):
        return 0, ("o conjunto de achados está vazio: pesquisa que rodou e não achou nada se registra "
                   "com --sem-resultado e as consultas feitas")
    return len(achados), None


class Recusa(Exception):
    pass


def montar(pasta, resultado, achados=None, consultas=(), motivo=None, detalhe=None, procurados=None,
           ferramenta=None, erro=None, agora=None):
    """O registro pronto para gravar; levanta Recusa com a frase do que falta."""
    reg = {"schema_version": SCHEMA, "gerado_por": "pesquisa_tentada.py", "resultado": resultado,
           "em": (agora or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if resultado == "achados":
        if not achados:
            raise Recusa("--achados <arquivo> é obrigatório")
        caminho = achados if os.path.isabs(achados) else os.path.join(pasta, achados)
        if not os.path.isfile(caminho):
            raise Recusa(f"o arquivo de achados não existe: {caminho}")
        total, problema = _ler_achados(caminho)
        if problema:
            raise Recusa(problema)
        reg["achados"] = {"arquivo": os.path.relpath(caminho, pasta) if os.path.commonpath(
            [os.path.abspath(caminho), os.path.abspath(pasta)]) == os.path.abspath(pasta) else os.path.abspath(caminho),
            "sha256": _sha_arquivo(caminho), "total": total}
    elif resultado == "sem_resultado":
        lidas = [_consulta(c) for c in consultas]
        if not lidas or not all(lidas):
            raise Recusa('cada --consulta tem a forma "<fonte consultada>: <termos buscados>", com a fonte '
                         "nomeada e ao menos duas palavras de busca; memória do modelo não é fonte")
        reg["consultas"] = lidas
    elif resultado == "impossivel":
        if motivo not in MOTIVOS:
            raise Recusa("--motivo é um de: " + ", ".join(MOTIVOS))
        generico = _detalhe_generico(detalhe)
        if generico:
            raise Recusa(generico)
        imp = {"motivo": motivo, "detalhe": detalhe.strip()}
        if motivo == "conector_ausente":
            nomes = [p.strip() for p in re.split(r"[,;]", procurados or "") if len(p.strip()) >= 3]
            if not nomes:
                raise Recusa("--procurados é obrigatório no conector ausente: os conectores de pesquisa "
                             "procurados na sessão, pelo nome")
            imp["procurados"] = nomes
        if motivo == "conector_falhou":
            if not (ferramenta or "").strip() or len((erro or "").strip()) < 8:
                raise Recusa("--ferramenta (a ferramenta chamada) e --erro (o erro que ela devolveu) são "
                             "obrigatórios no conector que falhou")
            imp["ferramenta"], imp["erro"] = ferramenta.strip(), erro.strip()[:400]
        reg["impedimento"] = imp
    else:
        raise Recusa("resultado fora de: achados, sem_resultado, impossivel")
    reg["selo"] = _selo(reg)
    return reg


def gravar(pasta, reg):
    caminho = os.path.join(pasta, NOME)
    tmp = caminho + ".parcial"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, caminho)
    return caminho


def ler(pasta):
    '(registro, None) quando há registro válido na pasta; (None, motivo em português) quando não'


    caminho = os.path.join(pasta or ".", NOME)
    if not os.path.isfile(caminho):
        return None, "não há registro de pesquisa na pasta da peça"
    try:
        with open(caminho, encoding="utf-8") as fh:
            reg = json.load(fh)
    except Exception:
        return None, "o registro de pesquisa está ilegível"
    if (not isinstance(reg, dict) or reg.get("schema_version") != SCHEMA
            or reg.get("gerado_por") != "pesquisa_tentada.py" or reg.get("selo") != _selo(reg)):
        return None, "o registro de pesquisa não foi gravado pelo script (ou foi alterado depois)"
    r = reg.get("resultado")
    if r == "achados":
        a = reg.get("achados") if isinstance(reg.get("achados"), dict) else {}
        arq = a.get("arquivo") or ""
        arq = arq if os.path.isabs(arq) else os.path.join(pasta, arq)
        if not os.path.isfile(arq) or _sha_arquivo(arq) != a.get("sha256"):
            return None, "o arquivo de achados do registro mudou ou sumiu: registre a pesquisa de novo"
        if _ler_achados(arq)[1]:
            return None, "o arquivo de achados do registro não vale mais: registre a pesquisa de novo"
    elif r == "sem_resultado":
        cs = reg.get("consultas")
        if not isinstance(cs, list) or not cs or not all(
                isinstance(c, dict) and _consulta(f"{c.get('fonte', '')}: {c.get('termos', '')}") for c in cs):
            return None, "o registro de pesquisa sem resultado não traz as consultas feitas"
    elif r == "impossivel":
        imp = reg.get("impedimento") if isinstance(reg.get("impedimento"), dict) else {}
        if imp.get("motivo") not in MOTIVOS or _detalhe_generico(imp.get("detalhe")):
            return None, "o registro de impossibilidade não diz o motivo"
    else:
        return None, "o registro de pesquisa não diz o resultado"
    return reg, None


_MOTIVO_PT = {"conector_ausente": "não havia conector de pesquisa de jurisprudência ligado nesta sessão",
              "conector_falhou": "o conector de pesquisa de jurisprudência não respondeu",
              "sigilo": "o caso é sigiloso e a pesquisa em serviço externo não foi feita"}


def pendencia(reg):
    'A frase da pendência para a lista da minuta, em português de advogado, ou None quando a'

    r = (reg or {}).get("resultado")
    if r == "sem_resultado":
        fontes = ", ".join(dict.fromkeys(c["fonte"] for c in reg["consultas"]))
        return (f"pesquisa de jurisprudência feita sem resultado aproveitável ({fontes}): as teses seguem sem "
                f"precedente conferido, e os trechos marcados dependem de pesquisa do advogado")
    if r == "impossivel":
        return (f"pesquisa de jurisprudência não realizada: {_MOTIVO_PT[reg['impedimento']['motivo']]}. "
                f"Nenhum precedente desta minuta foi conferido; a pesquisa fica por fazer antes do protocolo")
    return None


def recusa(porque, problema):
    """O texto da parada do gerador: o remédio é rodar a pesquisa, não entregar assim."""
    return (
        "PARADA: a minuta com pendências ainda não sai, porque a pesquisa de jurisprudência não foi tentada.\n"
        f"  Por quê: {porque}, e {problema}.\n"
        "  O que fazer AGORA, nesta mesma resposta, sem perguntar ao advogado:\n"
        "  1. Abra a skill dissero-pesquisa-juridica e rode a pesquisa das teses da peça pelos conectores\n"
        "     de jurisprudência da sessão. Confirmado o que der, use na peça só o confirmado.\n"
        "  2. Registre o resultado na pasta da peça, com o `pesquisa_tentada.py registrar` da própria\n"
        "     skill de pesquisa: `--achados <achados.json>` se achou; `--sem-resultado --consulta\n"
        "     \"<fonte>: <termos>\"` se buscou e não achou; `--impossivel --motivo <conector_ausente|\n"
        "     conector_falhou|sigilo> --detalhe \"<o que aconteceu>\"` se não pôde pesquisar.\n"
        "  3. Gere a minuta de novo, com o mesmo comando.\n"
        "  A pesquisa que não pôde ser feita NÃO segura o arquivo: registrada a impossibilidade, a\n"
        "  minuta sai, com a pendência escrita para o advogado. Não entregue a peça por outro caminho.")


def exigir(texto, pasta):
    'Para o gerador da minuta: (registro ou None, pendências a listar, texto da parada ou None).'




    tem, porque = tem_tese_juridica(texto)
    if not tem:
        return None, [], None
    reg, problema = ler(pasta)
    if reg is None:
        return None, [], recusa(porque, problema)
    pend = []
    frase = pendencia(reg)
    if frase:
        pend.append(frase)
    frase = pendencia_das_sumulas(texto, reg, pasta)
    if frase:
        pend.append(frase)
    return reg, pend, None


def pendencia_das_sumulas(texto, reg, pasta):
    'A pendência das súmulas e orientações jurisprudenciais citadas sem constar dos achados do'

    citadas = sumulas_citadas(texto)
    conferidas = _texto_dos_achados(reg, pasta)
    soltas = [c for c in citadas if not _sumula_conferida(c, conferidas)]
    if not soltas:
        return None
    return ("súmula ou orientação jurisprudencial citada sem conferência do texto: "
            + "; ".join(soltas[:12]) + ("; e outras" if len(soltas) > 12 else "")
            + ". Vale a regra dos julgados: confira o enunciado na fonte oficial antes do protocolo")


def _texto_dos_achados(reg, pasta):
    if (reg or {}).get("resultado") != "achados":
        return ""
    arq = reg["achados"]["arquivo"]
    arq = arq if os.path.isabs(arq) else os.path.join(pasta, arq)
    try:
        with open(arq, encoding="utf-8") as fh:
            return _sem_acento(json.dumps(json.load(fh), ensure_ascii=False))
    except Exception:
        return ""


def _sumula_conferida(citada, texto_achados):
    """A súmula ou OJ citada aparece, pelo número, no conjunto de achados?"""
    m = re.match(r"(Súmula(?: Vinculante)?|OJ) (\d+)", citada)
    if not m or not texto_achados:
        return False
    tipo = "sumula" if m.group(1).startswith("S") else r"(?:oj|orientacao jurisprudencial)"
    return re.search(rf"{tipo}[^\d\n]{{0,25}}{m.group(2)}\b", texto_achados) is not None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pesquisa_tentada.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("registrar")
    r.add_argument("--pasta", required=True)
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--achados")
    g.add_argument("--sem-resultado", action="store_true")
    g.add_argument("--impossivel", action="store_true")
    r.add_argument("--consulta", action="append", default=[])
    r.add_argument("--motivo")
    r.add_argument("--detalhe")
    r.add_argument("--procurados")
    r.add_argument("--ferramenta")
    r.add_argument("--erro")
    c = sub.add_parser("conferir")
    c.add_argument("--pasta", required=True)
    c.add_argument("--peca")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if not os.path.isdir(a.pasta):
        print(json.dumps({"ok": False, "codigo": "contrato_invalido", "mensagem": "a pasta não existe"},
                         ensure_ascii=False))
        return 2
    if a.cmd == "registrar":
        resultado = "achados" if a.achados else ("sem_resultado" if a.sem_resultado else "impossivel")
        try:
            reg = montar(a.pasta, resultado, achados=a.achados, consultas=a.consulta, motivo=a.motivo,
                         detalhe=a.detalhe, procurados=a.procurados, ferramenta=a.ferramenta, erro=a.erro)
        except Recusa as e:
            print(json.dumps({"ok": False, "codigo": "registro_recusado", "mensagem": str(e)}, ensure_ascii=False))
            return 1
        caminho = gravar(a.pasta, reg)
        print(json.dumps({"ok": True, "resultado": resultado, "arquivo": caminho,
                          "pendencia_na_minuta": pendencia(reg)}, ensure_ascii=False))
        return 0
    texto = ""
    if a.peca:
        try:
            with open(a.peca, encoding="utf-8") as fh:
                texto = fh.read()
        except OSError:
            print(json.dumps({"ok": False, "codigo": "contrato_invalido", "mensagem": "a peça não foi lida"},
                             ensure_ascii=False))
            return 2
        tem, porque = tem_tese_juridica(texto)
        if not tem:
            print(json.dumps({"ok": True, "exige_pesquisa": False}, ensure_ascii=False))
            return 0
    reg, problema = ler(a.pasta)
    if reg is None:
        print(json.dumps({"ok": False, "codigo": "pesquisa_nao_tentada", "mensagem": problema}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "exige_pesquisa": True, "resultado": reg["resultado"],
                      "pendencia_na_minuta": pendencia(reg)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
