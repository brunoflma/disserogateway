#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'tarja_processual.py - os identificadores que o tribunal imprime em cada pagina, a prova de'




























import re



PRESERVAR_SEMPRE = (
    re.compile(r"Num\.\s*\S+\s*-\s*P[áa]g\.\s*\d+", re.I),
    re.compile(r"fls?\.\s*\d+", re.I),
    re.compile(r"P[áa]gina\s+\d+\s+de\s+\d+", re.I),
)

PADROES_TARJA = {


    "pje-tjce": {
        "deteccao": re.compile(r"pje[\w\-]*\.[\w.\-]+\.jus\.br", re.I),
        "tarja": (


            ("gerado_por", re.compile(
                r"Este documento foi gerado pelo usu[áa]rio\s+(?:.+?\s+em\s+"
                r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}|[\d.\*\-]{6,20})", re.I)),
            ("numero_documento", re.compile(
                r"N[úu]mero do documento:\s*(?P<valor>\d{20,40})", re.I)),



            ("url_validacao", re.compile(
                r"(?P<valor>https?://pje[\w\-]*\.[\w.\-]+\.jus\.br(?::\d+)?/pje\dgrau/"
                r"Processo/ConsultaDocumento/listView\.seam\?x=\d{20,40})", re.I)),


            ("assinatura", re.compile(
                r"Assinado eletronicamente por:\s*(?P<valor>.+?\s+-\s+"
                r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})", re.I)),
        ),


        "linhas_fracas": (
            ("qr_code", re.compile(r"^QR\s*Code\s*$", re.I)),
        ),
        "proveniencia": {"assinatura": {"valor": "assinantes"},
                         "numero_documento": {"valor": "numeros_documento"},
                         "url_validacao": {"valor": "urls_validacao"}},
    },




    "esaj": {
        "deteccao": re.compile(
            r"esaj[\w.\-]*\.jus\.br"
            r"|Este documento [ée] c[óo]pia do original,?\s*assinado digitalmente por",
            re.I),
        "tarja": (

            ("esaj_assinatura", re.compile(
                r"Este documento [ée] c[óo]pia do original,\s*assinado digitalmente por\s*"
                r"(?P<valor>.+?,\s*liberado nos autos em\s*\d{2}/\d{2}/\d{4}\s*[àa]s\s*"
                r"\d{2}:\d{2}(?::\d{2})?)\s*\.?", re.I)),

            ("esaj_protocolo", re.compile(
                r"Este documento [ée] c[óo]pia do original,\s*assinado digitalmente por\s*"
                r"(?P<valor>.+?,\s*protocolado em\s*\d{2}/\d{2}/\d{4}\s*[àa]s\s*"
                r"\d{2}:\d{2}(?::\d{2})?\s*,?\s*sob o n[úu]mero\s*[A-Za-z0-9]{6,30})", re.I)),





            ("esaj_conferencia", re.compile(
                r"Para conferir o original,\s*acesse o site\s*(?P<url>https?://\S+?),\s*"
                r"informe o processo\s+(?P<processo>[\d.\-]{20,25})\s+e\s+(?:o\s+)?"
                r"c[óo]digo\s+(?P<codigo>[A-Za-z0-9]{6,12})(?![0-9A-Za-zÀ-ÿ])\s*\.?", re.I)),




            ("esaj_ref", re.compile(
                r"(?:informe\s+o\s+processo\s+)?(?P<processo>[\d.\-]{20,25})\s+e\s+"
                r"(?:o\s+)?c[óo]digo\s+(?P<codigo>(?-i:[A-Z0-9]{6,12}))(?![0-9A-Za-zÀ-ÿ])\s*\.?",
                re.I)),

            ("esaj_frase", re.compile(
                r"Para conferir o original,?\s*acesse o site"
                r"(?:\s*(?P<url>https?://[\w.\-]*esaj[\w.\-]*\.jus\.br/\S*?),?)?(?=\s|$)",
                re.I)),
        ),
        "linhas_fracas": (),


        "proveniencia": {"esaj_assinatura": {"valor": "assinantes"},
                         "esaj_protocolo": {"valor": "assinantes"},
                         "esaj_conferencia": {"url": "urls_validacao",
                                              "processo": "processos",
                                              "codigo": "codigos_conferencia"},
                         "esaj_ref": {"processo": "processos",
                                      "codigo": "codigos_conferencia"},
                         "esaj_frase": {"url": "urls_validacao"}},
    },








    "stj": {
        "deteccao": re.compile(r"Documento eletr[ôo]nico\s+VDA\d+", re.I),
        "tarja": (
            ("stj_vda", re.compile(
                r"Documento eletr[ôo]nico\s+(?P<valor>VDA\d+)\s+assinado eletronicamente"
                r"[^\n]{0,80}?Lei\s*11\.419/\d{4}", re.I)),
            ("stj_signatario", re.compile(
                r"Signat[áa]rio\(a\):\s*(?P<valor>.+?\s+Assinado em:\s*"
                r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})", re.I)),
            ("stj_controle", re.compile(
                r"C[óo]digo de Controle do Documento:\s*"
                r"(?P<valor>[0-9A-Fa-f][0-9A-Fa-f\-]{15,})", re.I)),
        ),
        "linhas_fracas": (),
        "proveniencia": {"stj_vda": {"valor": "codigos_conferencia"},
                         "stj_signatario": {"valor": "assinantes"},
                         "stj_controle": {"valor": "codigos_conferencia"}},
    },
}
