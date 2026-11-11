#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'contraste_wcag.py — luminância relativa e razão de contraste (WCAG 2.1).'





















MINIMO_TEXTO = 4.5
MINIMO_COMPONENTE = 3.0


def luminancia(rgb):
    """Luminância relativa (WCAG 2.1, 0 = preto, 1 = branco). `rgb` é uma tripla 0-255."""
    canais = []
    for c in rgb:
        c = c / 255.0
        canais.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def contraste(rgb_a, rgb_b):
    """Razão de contraste entre duas triplas 0-255. Simétrica, de 1,0 a 21,0."""
    la, lb = luminancia(rgb_a), luminancia(rgb_b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def rgb_de_hex(valor):
    """Tripla 0-255 a partir de um hex de 6 dígitos (com ou sem `#`). None se não for um."""
    if not isinstance(valor, str):
        return None
    v = valor.strip().lstrip("#")
    if len(v) != 6:
        return None
    try:
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except ValueError:
        return None


def contraste_hex(a, b):
    'Razão de contraste entre dois hex de 6 dígitos. None quando um deles não é hex —'


    ra, rb = rgb_de_hex(a), rgb_de_hex(b)
    if ra is None or rb is None:
        return None
    return contraste(ra, rb)
