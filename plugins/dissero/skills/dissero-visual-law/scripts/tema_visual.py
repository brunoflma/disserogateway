#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'tema_visual.py — a gramatica da peca como DADO. Casa unica de ficha e variante.'



















TEMA_FILETE = {
    "versao": 1, "nome": "filete",
    "fichas": {"tinta": "1A1A1A", "legenda": "FFFFFF", "argumento_fundo": "FFFFFF",
               "argumento_barra": "1F3864", "juris_fundo": "FFFFFF", "juris_barra": "1F3864",
               "versalete": "1F3864", "capa_subtitulo": "1F3864", "acento": "1F3864"},
    "capitulo": {"variante": "filete", "filete_sup_sz": 36, "filete_inf_sz": 6,
                 "titulo_sz": 30, "rotulo_sz": 21, "rotulo_spacing": 80, "antes": 200},


    "capa": {"regua_sz": 12, "regua_fina_sz": 6},
    "contorno": {"sz": 6},
    "elementos": {"legenda": "filete", "capa": "filete", "argumento": "contornado",
                  "jurisprudencia": "contornado", "comparativa": "contornado"},

    "tipografia": {"fonte": "Cambria", "corpo_sz": 24, "capa_titulo_sz": 34,
                   "capa_subtitulo_sz": 22, "legenda_sz": 26, "versalete_sz": 21},
}

PADRAO = TEMA_FILETE


def tema_do_perfil(perfil):
    'O tema da banca (`perfil.identidade_visual.tema`), ou o PADRAO.'




    if not isinstance(perfil, dict):
        return PADRAO
    iv = perfil.get("identidade_visual") or {}
    t = iv.get("tema")
    if not isinstance(t, dict):
        return PADRAO
    try:
        import perfil_advogado as pa
        if pa.validar_tema(t) is not None:
            return PADRAO




        t = pa.migrar_tema(t, PADRAO)
        if pa.tema_incompleto(t) is not None:
            return PADRAO
    except Exception:
        return PADRAO
    return t
