#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Loader local e stdlib-only de credenciais do plugin Dissero.'





from __future__ import annotations

import json
import os
import sys
from pathlib import Path


_CHAVES = (
    "DATAJUD_API_KEY",
)


def _caminhos_padrao() -> list[Path]:
    caminhos = [Path(value) for value in (
        os.environ.get("DSR_CRED_FILE", ""),
    ) if value]


    try:
        caminhos.append(Path.home() / ".config" / "dissero" / "credenciais.env")
    except RuntimeError:
        pass
    return caminhos


def _parse(path: Path) -> dict[str, str]:
    pares: dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            chave = chave.strip()
            if chave in _CHAVES:
                pares[chave] = valor.strip().strip('"').strip("'")
    return pares


def carregar(extra_path: str | os.PathLike[str] | None = None) -> str | None:
    """Carrega o primeiro arquivo existente sem sobrescrever o ambiente."""
    caminhos = ([Path(extra_path)] if extra_path else []) + _caminhos_padrao()
    for path in caminhos:
        if path.is_file():
            for chave, valor in _parse(path).items():
                if valor and not os.environ.get(chave):
                    os.environ[chave] = valor
            return str(path)
    return None


def status() -> dict[str, str]:
    """Informa somente presença; nunca retorna valor de credencial."""
    return {chave: ("definida" if os.environ.get(chave) else "ausente") for chave in _CHAVES}


def main() -> int:
    usado = carregar()
    print(json.dumps(
        {"arquivo_carregado": bool(usado), "chaves": status()},
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
