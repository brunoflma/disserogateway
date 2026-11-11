#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'carimbo_timbrado.py — a origem do timbrado gravada DENTRO do .docx.'




















import os
import re

_FMTID_CARIMBO = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"

_RX_PROPRIEDADE = re.compile(r"<property\b[^>]*>.*?</property>", re.S)
_RX_NOME = re.compile(r'\bname="([^"]*)"')
_RX_PID = re.compile(r'\bpid="\d+"')
PARTE_CARIMBO = "docProps/custom.xml"
_TIPO_CARIMBO = "application/vnd.openxmlformats-officedocument.custom-properties+xml"
_REL_CARIMBO = ("http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
                "custom-properties")


PROP_MINUTA_PENDENCIAS = "DSRMinutaPendencias"


def _xml_escape(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def carimbar(work, origem, sha_manifesto):
    'Grava `docProps/custom.xml` no pacote DESEMPACOTADO, com o content-type e a'


    props = (("DSRTimbradoOrigem", origem), ("DSRTimbradoManifesto", sha_manifesto or ""))
    _gravar_propriedades(work, props, lambda nome: nome.startswith("DSRTimbrado"))


def carimbar_minuta_pendencias(work):
    'Carimba a MINUTA COM PENDÊNCIAS (`DSRMinutaPendencias` = "1") no pacote desempacotado.'





    _gravar_propriedades(work, ((PROP_MINUTA_PENDENCIAS, "1"),),
                         lambda nome: nome == PROP_MINUTA_PENDENCIAS)


def _gravar_propriedades(work, props, e_nossa):
    'Regrava `docProps/custom.xml` com `props` no fim; `e_nossa(nome)` diz quais'

    destino = os.path.join(work, *PARTE_CARIMBO.split("/"))





    alheias = []
    if os.path.isfile(destino):
        with open(destino, encoding="utf-8", errors="replace") as fh:
            antigo = fh.read()
        for bloco in _RX_PROPRIEDADE.findall(antigo):
            m = _RX_NOME.search(bloco)
            if m and not e_nossa(m.group(1)):
                alheias.append(bloco)
    partes = []
    pid = 2
    for bloco in alheias:
        partes.append(_RX_PID.sub(f'pid="{pid}"', bloco, count=1))
        pid += 1
    for nome, valor in props:
        partes.append(f'<property fmtid="{_FMTID_CARIMBO}" pid="{pid}" name="{nome}">'
                      f'<vt:lpwstr>{_xml_escape(valor)}</vt:lpwstr></property>')
        pid += 1
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
           'custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/'
           '2006/docPropsVTypes">' + "".join(partes) + '</Properties>')
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(xml)

    ct = os.path.join(work, "[Content_Types].xml")
    with open(ct, encoding="utf-8") as fh:
        texto = fh.read()
    if PARTE_CARIMBO not in texto:
        texto = texto.replace(
            "</Types>",
            f'<Override PartName="/{PARTE_CARIMBO}" ContentType="{_TIPO_CARIMBO}"/></Types>')
        with open(ct, "w", encoding="utf-8") as fh:
            fh.write(texto)

    rels = os.path.join(work, "_rels", ".rels")
    with open(rels, encoding="utf-8") as fh:
        texto = fh.read()
    if PARTE_CARIMBO not in texto:
        texto = texto.replace(
            "</Relationships>",
            f'<Relationship Id="rIdDsrTimbrado" Type="{_REL_CARIMBO}" '
            f'Target="{PARTE_CARIMBO}"/></Relationships>')
        with open(rels, "w", encoding="utf-8") as fh:
            fh.write(texto)


def carimbar_do_perfil(work, perfil=None):
    'Carimba a origem que o PERFIL declara. Devolve a origem carimbada, ou `None` quando'




    try:
        import perfil_advogado as _pa
        origem = _pa.origem_timbrado(perfil)
        carimbar(work, origem,
                 _pa.sha_manifesto_identidade() if origem == "proprio" else "")
        return origem
    except Exception:
        return None
