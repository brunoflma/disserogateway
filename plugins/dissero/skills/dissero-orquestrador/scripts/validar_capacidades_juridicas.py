#!/usr/bin/env python3
'Valida o registro de capacidades jurídicas (`capacidades_juridicas.json`), falha fechada.'









from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from urllib.parse import urlparse

VERSAO = "dsr.capacidades_juridicas.v1"
IDS = [
    "admissibilidade_recursal", "atualizacao_monetaria", "horas_extras",
    "salario_liquido_inss", "dosimetria_penal", "progressao_regime",
    "auditoria_pjecalc", "jurimetria_admissibilidade", "revisional_taxa_media",
]
SHA_RX = re.compile(r"^[0-9a-f]{64}$")






ESTADOS_DESABILITADOS = ("aguardando_revisao", "experimental_desabilitada")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SUFIXOS_OFICIAIS = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")


def _data(valor):
    try:
        return dt.date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return None


def validar(dados, hoje=None):
    erros = []
    if not isinstance(dados, dict) or dados.get("schema_version") != VERSAO:
        return ["schema_version inválida"]
    itens = dados.get("capacidades")
    if not isinstance(itens, list) or len(itens) != 9:
        return ["o catálogo deve conter exatamente nove capacidades"]
    if [x.get("id") for x in itens if isinstance(x, dict)] != IDS:
        erros.append("ordem/IDs das capacidades divergem do plano aprovado")
    hoje = hoje or dt.date.today()
    for i, item in enumerate(itens):
        if not isinstance(item, dict):
            erros.append(f"capacidades[{i}]: objeto obrigatório")
            continue
        if not item.get("enabled"):
            if item.get("estado") not in ESTADOS_DESABILITADOS:
                erros.append(f"{item.get('id')}: estado desabilitado inválido")
            continue
        faltam = [campo for campo in (
            "fonte_oficial", "valid_from", "valid_to", "extracted_at",
            "source_sha256", "reviewed_by", "entrypoint",
        ) if not item.get(campo)]
        if faltam:
            erros.append(f"{item.get('id')}: habilitação sem " + ", ".join(faltam))
            continue
        inicio, fim = _data(item.get("valid_from")), _data(item.get("valid_to"))
        if not inicio or not fim or inicio > hoje or fim < hoje:
            erros.append(f"{item.get('id')}: cobertura temporal ausente, futura ou vencida")
        if not SHA_RX.match(str(item.get("source_sha256", "")).lower()):
            erros.append(f"{item.get('id')}: source_sha256 inválido")
        fonte = str(item.get("fonte_oficial") or "")
        if not fonte.startswith("https://"):
            erros.append(f"{item.get('id')}: fonte oficial deve usar HTTPS")
        host = (urlparse(fonte).hostname or "").lower()
        if host and not any(host.endswith(sufixo) for sufixo in SUFIXOS_OFICIAIS):
            erros.append(f"{item.get('id')}: host da fonte não é oficial")
        extraido = _data(item.get("extracted_at"))
        if not extraido or extraido > hoje:
            erros.append(f"{item.get('id')}: extracted_at inválido ou futuro")
        if not isinstance(item.get("reviewed_by"), str) or len(item["reviewed_by"].strip()) < 3:
            erros.append(f"{item.get('id')}: revisor responsável inválido")
        entry = os.path.normpath(str(item.get("entrypoint") or ""))
        if entry.startswith("..") or os.path.isabs(entry):
            erros.append(f"{item.get('id')}: entrypoint deve ser caminho relativo seguro")
        elif not os.path.isfile(os.path.join(ROOT, entry)):
            erros.append(f"{item.get('id')}: entrypoint não existe")
    return erros


def main():
    p = argparse.ArgumentParser()
    p.add_argument("arquivo", nargs="?", default=os.path.join(os.path.dirname(__file__), "capacidades_juridicas.json"))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        with open(args.arquivo, encoding="utf-8") as f:
            dados = json.load(f)
        erros = validar(dados)
    except Exception as erro:
        erros = [str(erro)]
    out = {"ok": not erros, "violacoes": erros}
    print(json.dumps(out, ensure_ascii=False) if args.json else
          ("APROVADO" if not erros else "REPROVADO: " + "; ".join(erros)))
    return 0 if not erros else 1


if __name__ == "__main__":
    raise SystemExit(main())
