#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'pascoa.py — Domingo de Páscoa pelo cômputo gregoriano.'









from datetime import date


def pascoa(ano):
    """Domingo de Páscoa de `ano` pelo cômputo gregoriano."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    mes, dia = divmod(h + ll - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)
