#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'numero_cnj.py — Número Único de Processo (CNJ): validação, normalização e leitura.'






























import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass



RE_CNJ = re.compile(
    r"(?<!\d)(?:\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|\d{20})(?!\d)"
)


SEGMENTOS = {
    "1": "Supremo Tribunal Federal",
    "2": "Conselho Nacional de Justiça",
    "3": "Superior Tribunal de Justiça",
    "4": "Justiça Federal",
    "5": "Justiça do Trabalho",
    "6": "Justiça Eleitoral",
    "7": "Justiça Militar da União",
    "8": "Justiça Estadual",
    "9": "Justiça Militar Estadual",
}


def normalizar(valor):
    'Devolve os 20 dígitos do número, com ou sem máscara. None se não for CNJ.'



    if not isinstance(valor, str):
        return None
    digitos = re.sub(r"\D", "", valor)
    return digitos if len(digitos) == 20 else None


def _partes(digitos):
    """Fatia os 20 dígitos nos campos da Resolução 65/2008."""
    return (digitos[0:7], digitos[7:9], digitos[9:13],
            digitos[13:14], digitos[14:16], digitos[16:20])


def dv_correto(valor):
    'Dígito verificador que o número DEVERIA ter, como string de 2 caracteres.'



    digitos = normalizar(valor)
    if digitos is None:
        return None
    seq, _dv, ano, seg, trib, orig = _partes(digitos)
    resto = int(seq + ano + seg + trib + orig + "00") % 97
    return "%02d" % (98 - resto)


def validar(valor):
    'True somente se a forma for de CNJ E o dígito verificador fechar.'



    digitos = normalizar(valor)
    if digitos is None:
        return False
    seq, dv, ano, seg, trib, orig = _partes(digitos)
    return int(seq + ano + seg + trib + orig + dv) % 97 == 1


def formatar(valor):
    """Aplica a máscara NNNNNNN-DD.AAAA.J.TR.OOOO. None se a forma não for de CNJ."""
    digitos = normalizar(valor)
    if digitos is None:
        return None
    seq, dv, ano, seg, trib, orig = _partes(digitos)
    return f"{seq}-{dv}.{ano}.{seg}.{trib}.{orig}"


def componentes(valor):
    'Dicionário com os campos do número, o segmento por extenso e a validade.'





    digitos = normalizar(valor)
    if digitos is None:
        return None
    seq, dv, ano, seg, trib, orig = _partes(digitos)
    return {
        "numero": formatar(digitos),
        "digitos": digitos,
        "sequencial": seq,
        "dv": dv,
        "ano": ano,
        "segmento": seg,
        "segmento_nome": SEGMENTOS.get(seg, "segmento desconhecido"),
        "tribunal": trib,
        "origem": orig,
        "valido": validar(digitos),
        "dv_correto": dv_correto(digitos),

        "tribunal_origem": list(tribunal_de_origem(digitos)),
        "tribunal_origem_ambiguo": len(tribunal_de_origem(digitos)) > 1,
        "esfera": esfera(digitos),
    }





















TRIBUNAIS_POR_CODIGO = {
    ("1", "00"): ("STF",),
    ("2", "00"): ("CNJ",),
    ("3", "00"): ("STJ",),
    ("4", "01"): ("TRF1", "TRF6"),
    ("4", "02"): ("TRF2",),
    ("4", "03"): ("TRF3",),
    ("4", "04"): ("TRF4",),
    ("4", "05"): ("TRF5",),
    ("5", "00"): ("TST",),
    ("5", "01"): ("TRT1",),
    ("5", "02"): ("TRT2",),
    ("5", "03"): ("TRT3",),
    ("5", "04"): ("TRT4",),
    ("5", "05"): ("TRT5",),
    ("5", "06"): ("TRT6",),
    ("5", "07"): ("TRT7",),
    ("5", "08"): ("TRT8",),
    ("5", "09"): ("TRT9",),
    ("5", "10"): ("TRT10",),
    ("5", "11"): ("TRT11",),
    ("5", "12"): ("TRT12",),
    ("5", "13"): ("TRT13",),
    ("5", "14"): ("TRT14",),
    ("5", "15"): ("TRT15",),
    ("5", "16"): ("TRT16",),
    ("5", "17"): ("TRT17",),
    ("5", "18"): ("TRT18",),
    ("5", "19"): ("TRT19",),
    ("5", "20"): ("TRT20",),
    ("5", "21"): ("TRT21",),
    ("5", "22"): ("TRT22",),
    ("5", "23"): ("TRT23",),
    ("5", "24"): ("TRT24",),
    ("6", "00"): ("TSE",),
    ("6", "01"): ("TRE-AC",),
    ("6", "02"): ("TRE-AL",),
    ("6", "03"): ("TRE-AP",),
    ("6", "04"): ("TRE-AM",),
    ("6", "05"): ("TRE-BA",),
    ("6", "06"): ("TRE-CE",),
    ("6", "07"): ("TRE-DF",),
    ("6", "08"): ("TRE-ES",),
    ("6", "09"): ("TRE-GO",),
    ("6", "10"): ("TRE-MA",),
    ("6", "11"): ("TRE-MT",),
    ("6", "12"): ("TRE-MS",),
    ("6", "13"): ("TRE-MG",),
    ("6", "14"): ("TRE-PA",),
    ("6", "15"): ("TRE-PB",),
    ("6", "16"): ("TRE-PR",),
    ("6", "17"): ("TRE-PE",),
    ("6", "18"): ("TRE-PI",),
    ("6", "19"): ("TRE-RJ",),
    ("6", "20"): ("TRE-RN",),
    ("6", "21"): ("TRE-RS",),
    ("6", "22"): ("TRE-RO",),
    ("6", "23"): ("TRE-RR",),
    ("6", "24"): ("TRE-SC",),
    ("6", "25"): ("TRE-SE",),
    ("6", "26"): ("TRE-SP",),
    ("6", "27"): ("TRE-TO",),
    ("7", "00"): ("STM",),
    ("7", "01"): ("STM",),
    ("8", "01"): ("TJAC",),
    ("8", "02"): ("TJAL",),
    ("8", "03"): ("TJAP",),
    ("8", "04"): ("TJAM",),
    ("8", "05"): ("TJBA",),
    ("8", "06"): ("TJCE",),
    ("8", "07"): ("TJDFT",),
    ("8", "08"): ("TJES",),
    ("8", "09"): ("TJGO",),
    ("8", "10"): ("TJMA",),
    ("8", "11"): ("TJMT",),
    ("8", "12"): ("TJMS",),
    ("8", "13"): ("TJMG",),
    ("8", "14"): ("TJPA",),
    ("8", "15"): ("TJPB",),
    ("8", "16"): ("TJPR",),
    ("8", "17"): ("TJPE",),
    ("8", "18"): ("TJPI",),
    ("8", "19"): ("TJRJ",),
    ("8", "20"): ("TJRN",),
    ("8", "21"): ("TJRS",),
    ("8", "22"): ("TJRO",),
    ("8", "23"): ("TJRR",),
    ("8", "24"): ("TJSC",),
    ("8", "25"): ("TJSE",),
    ("8", "26"): ("TJSP",),
    ("8", "27"): ("TJTO",),
    ("9", "13"): ("TJMMG",),
    ("9", "21"): ("TJMRS",),
    ("9", "26"): ("TJMSP",),
}











ESFERA_POR_SEGMENTO = {
    "1": "federal", "2": "federal", "3": "federal", "4": "federal",
    "5": "trabalhista", "6": "eleitoral", "7": "federal", "8": "estadual",
    "9": "militar_estadual",
}
_SUPERIORES = {("5", "00"), ("6", "00"), ("7", "00"), ("7", "01")}


def tribunal_de_origem(valor):
    'Siglas do tribunal de ORIGEM do número. None se não for CNJ; () se código desconhecido.'




    digitos = normalizar(valor)
    if digitos is None:
        return None
    _, _, _, seg, trib, _ = _partes(digitos)
    return TRIBUNAIS_POR_CODIGO.get((seg, trib), ())


def esfera(valor):
    """Esfera do processo, no vocabulário da base de calendário. None se não for CNJ."""
    digitos = normalizar(valor)
    if digitos is None:
        return None
    _, _, _, seg, trib, _ = _partes(digitos)
    if (seg, trib) in _SUPERIORES:
        return "federal"
    return ESFERA_POR_SEGMENTO.get(seg)


def extrair(texto):
    'Lista os números com FORMA de CNJ encontrados no texto, na ordem de aparição.'




    if not isinstance(texto, str):
        return []
    return RE_CNJ.findall(texto)


def main(argv):
    if len(argv) != 2:
        print(json.dumps({
            "ok": False, "erro": "informe UM número de processo",
            "uso": 'python3 numero_cnj.py "0000001-17.0000.8.00.0000"',
            "exit_code": 2}, ensure_ascii=False))
        return 2

    comp = componentes(argv[1])
    if comp is None:
        print(json.dumps({
            "ok": False, "valido": False,
            "erro": "não tem a forma de um número CNJ (20 dígitos)",
            "entrada": argv[1][:60], "exit_code": 1}, ensure_ascii=False))
        return 1

    comp["ok"] = True
    comp["exit_code"] = 0 if comp["valido"] else 1
    if not comp["valido"]:
        comp["aviso"] = (
            f"FORMA de CNJ com dígito verificador INCORRETO: informado {comp['dv']}, "
            f"correto seria {comp['dv_correto']}. Provável erro de digitação — conferir "
            "na fonte antes de usar em peça, juntada ou consulta processual.")
    print(json.dumps(comp, ensure_ascii=False))
    return comp["exit_code"]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
