#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'schema_mini.py — validador do subconjunto Draft-07 usado pelos contratos Dissero.'










from __future__ import annotations


def validar_schema(instancia, schema, raiz=None, caminho="$"):
    """Aplica o subconjunto Draft-07 usado pelos contratos, inclusive additionalProperties."""
    raiz = raiz or schema
    erros = []
    if "$ref" in schema:
        alvo = raiz
        for parte in schema["$ref"].removeprefix("#/").split("/"):
            alvo = alvo[parte]
        return validar_schema(instancia, alvo, raiz, caminho)
    if "const" in schema and instancia != schema["const"]:
        erros.append(f"{caminho}: valor deve ser {schema['const']!r}")
    if "enum" in schema and instancia not in schema["enum"]:
        erros.append(f"{caminho}: valor fora do enum {schema['enum']}")
    tipos = schema.get("type")
    if tipos:
        tipos = tipos if isinstance(tipos, list) else [tipos]
        mapa = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None), "number": (int, float), "integer": int}
        valido = any(isinstance(instancia, mapa[t]) and not (t in ("number", "integer") and isinstance(instancia, bool)) for t in tipos)
        if not valido:
            return [f"{caminho}: tipo inválido; esperado {tipos}"]
    if isinstance(instancia, str) and len(instancia) < schema.get("minLength", 0):
        erros.append(f"{caminho}: texto abaixo de minLength={schema['minLength']}")

    if ("minimum" in schema and isinstance(instancia, (int, float)) and not isinstance(instancia, bool)
            and instancia < schema["minimum"]):
        erros.append(f"{caminho}: valor abaixo de minimum={schema['minimum']}")
    if isinstance(instancia, dict):
        propriedades = schema.get("properties", {})
        for campo in schema.get("required", []):
            if campo not in instancia:
                erros.append(f"{caminho}: campo obrigatório ausente: {campo}")
        if schema.get("additionalProperties") is False:
            for campo in instancia:
                if campo not in propriedades:
                    erros.append(f"{caminho}: propriedade desconhecida: {campo}")
        for campo, valor in instancia.items():
            if campo in propriedades:
                erros.extend(validar_schema(valor, propriedades[campo], raiz, f"{caminho}.{campo}"))
    if isinstance(instancia, list) and "items" in schema:
        for indice, item in enumerate(instancia):
            erros.extend(validar_schema(item, schema["items"], raiz, f"{caminho}[{indice}]"))
    return erros
