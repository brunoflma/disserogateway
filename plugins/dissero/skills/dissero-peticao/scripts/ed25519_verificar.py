#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Verificação de assinatura Ed25519 em Python puro (RFC 8032, seção 5.1.7). Só verifica.'















from __future__ import annotations

import hashlib


_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _inv(x):
    return pow(x, _P - 2, _P)


def _somar(a, b):
    """Soma em coordenadas estendidas (X, Y, Z, T), fórmula da RFC 8032."""
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    pa = (y1 - x1) * (y2 - x2) % _P
    pb = (y1 + x1) * (y2 + x2) % _P
    pc = t1 * 2 * _D * t2 % _P
    pd = z1 * 2 * z2 % _P
    e, f, g, h = pb - pa, pd - pc, pd + pc, pb + pa
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _multiplicar(s, ponto):
    """[s]ponto por dobra-e-soma. Tempo variável não é problema: aqui só há dado público."""
    acc = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            acc = _somar(acc, ponto)
        ponto = _somar(ponto, ponto)
        s >>= 1
    return acc


def _iguais(a, b):
    x1, y1, z1, _ = a
    x2, y2, z2, _ = b
    return (x1 * z2 - x2 * z1) % _P == 0 and (y1 * z2 - y2 * z1) % _P == 0


def _recuperar_x(y, sinal):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1) % _P
    if x2 == 0:
        return None if sinal else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sinal:
        x = _P - x
    return x


def _descomprimir(b):
    'Ponto codificado em 32 bytes, ou None se a codificação for inválida (y >= p incluído:'

    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    sinal = y >> 255
    y &= (1 << 255) - 1
    x = _recuperar_x(y, sinal)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


_GY = 4 * _inv(5) % _P
_G = (_recuperar_x(_GY, 0), _GY, 1, _recuperar_x(_GY, 0) * _GY % _P)


def comprimir(ponto):
    """Codificação de 32 bytes de um ponto (usada pelo teste para derivar a chave pública)."""
    x, y, z, _ = ponto
    zi = _inv(z)
    x, y = x * zi % _P, y * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def ponto_base():
    return _G


def multiplicar_base(s):
    return _multiplicar(s, _G)


ORDEM = _Q


def verificar(chave_publica: bytes, mensagem: bytes, assinatura: bytes) -> bool:
    'True só se `assinatura` for a assinatura Ed25519 de `mensagem` pela `chave_publica`.'



    try:
        chave_publica, mensagem, assinatura = bytes(chave_publica), bytes(mensagem), bytes(assinatura)
    except (TypeError, ValueError):
        return False
    if len(chave_publica) != 32 or len(assinatura) != 64:
        return False
    a = _descomprimir(chave_publica)
    if a is None:
        return False
    r_bytes = assinatura[:32]
    r = _descomprimir(r_bytes)
    if r is None:
        return False
    s = int.from_bytes(assinatura[32:], "little")
    if s >= _Q:
        return False
    h = int.from_bytes(hashlib.sha512(r_bytes + chave_publica + mensagem).digest(), "little") % _Q
    return _iguais(_multiplicar(s, _G), _somar(r, _multiplicar(h, a)))
