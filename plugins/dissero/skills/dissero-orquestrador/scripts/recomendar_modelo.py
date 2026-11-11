#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'recomendar_modelo.py — que tier a ANÁLISE INICIAL de um cenário deve pedir, e por quê (Dissero).'















































from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))




FAMILIAS = ("fable", "opus", "sonnet", "haiku")


CHAVE_LOOKUP = "analise_inicial_preferencial"

_RX_MODEL = re.compile(r'"model"\s*:\s*"([^"]+)"')


class Contrato(Exception):
    """Violação de contrato/uso → exit 2."""


def _s(x):
    return isinstance(x, str) and bool(x.strip())


def familia_do_id(model_id):
    """ID do modelo → família (fable/opus/sonnet/haiku) ou None."""
    if not _s(model_id):
        return None
    partes = model_id.strip().lower().split("-")
    for f in FAMILIAS:
        if f in partes:
            return f
    return None




def _candidatos_perfis():


    return [
        os.path.join(AQUI, "..", "references", "perfis_modelo.json"),
        os.path.join(AQUI, "..", "skills", "dissero-orquestrador", "references", "perfis_modelo.json"),
    ]


def carregar_perfis(caminho=None):
    candidatos = [caminho] if _s(caminho) else _candidatos_perfis()
    for c in candidatos:
        if c and os.path.isfile(c):
            try:
                with open(c, encoding="utf-8") as fh:
                    return json.load(fh), os.path.abspath(c)
            except Exception as e:
                raise Contrato(f"perfis_modelo.json ilegível em {c}: {e}")
    raise Contrato("perfis_modelo.json não encontrado (use --perfis)")


def carregar_perfil_advogado(caminho=None):
    """Perfil do advogado, ou None quando não há. Ausência NÃO é erro: é sinal ausente."""
    candidatos = []
    if _s(caminho):
        candidatos.append(caminho)
    else:
        env = os.environ.get("DSR_PERFIL", "")
        if _s(env):
            candidatos.append(env)
        candidatos.append(os.path.join(os.path.expanduser("~"), ".config", "dissero", "perfil.json"))
    for c in candidatos:
        if c and os.path.isfile(c):
            try:
                with open(c, encoding="utf-8") as fh:
                    return json.load(fh), os.path.abspath(c)
            except Exception:
                return None, os.path.abspath(c)
    return None, None




def _raiz_transcripts(override):
    if _s(override):
        return override.strip()
    env = os.environ.get("DSR_TRANSCRIPTS_MAIN_DIR", "")
    if _s(env):
        return env.strip()
    return os.path.join(os.path.expanduser("~"), ".claude", "projects")


def transcript_mais_recente(raiz):
    'O .jsonl de sessão principal mais recente sob a raiz (projects/<projeto>/<sessao>.jsonl).'

    if not (_s(raiz) and os.path.isdir(raiz)):
        return None
    padroes = [os.path.join(raiz, "*", "*.jsonl"), os.path.join(raiz, "*.jsonl")]
    arquivos = []
    for p in padroes:
        arquivos.extend(f for f in glob.glob(p) if os.sep + "subagents" + os.sep not in f)
    if not arquivos:
        return None
    return max(arquivos, key=lambda f: os.path.getmtime(f))


def modelo_no_transcript(caminho, cauda_bytes=262144):
    'Último ID de modelo gravado no transcript. Lê só a cauda: o arquivo pode ter dezenas'

    if not (_s(caminho) and os.path.isfile(caminho)):
        return None
    try:
        tam = os.path.getsize(caminho)
        with open(caminho, "rb") as fh:
            fh.seek(max(0, tam - cauda_bytes))
            texto = fh.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    achados = _RX_MODEL.findall(texto)
    return achados[-1] if achados else None




_RX_FAIXA = re.compile(r"^(\d+)-(\d+)$")


def _linha_do_cenario(cenarios, cenario):
    'A linha do catálogo para o cenário: a de chave exata ou, sem ela, a de faixa `a-b` que'

    c = cenarios.get(str(cenario))
    if isinstance(c, dict):
        return c
    texto = str(cenario).strip()
    if not texto.isdigit():
        return None
    n = int(texto)
    for chave, linha in cenarios.items():
        m = _RX_FAIXA.match(str(chave))
        if m and int(m.group(1)) <= n <= int(m.group(2)) and isinstance(linha, dict):
            return linha
    return None


def recomendar(cenario, perfis, perfil_advogado=None, modelo_sessao=None):
    """Núcleo puro: (cenário, lookup, perfil, modelo da sessão) → dict da recomendação."""
    cenarios = perfis.get("cenarios") or {}
    c = _linha_do_cenario(cenarios, cenario)
    if not isinstance(c, dict):
        raise Contrato(f"cenário {cenario!r} não existe no catálogo ({len(cenarios)} cenários)")
    pid = c.get("perfil")
    perfil = (perfis.get("perfis") or {}).get(pid)
    if not isinstance(perfil, dict):
        raise Contrato(f"perfil {pid!r} do cenário {cenario} não existe em perfis_modelo.json")
    cfg = perfis.get(CHAVE_LOOKUP)
    if not isinstance(cfg, dict):
        raise Contrato(f"perfis_modelo.json sem o bloco '{CHAVE_LOOKUP}'")
    tier_pref = cfg.get("tier")
    substitui = tuple(cfg.get("substitui") or ())
    planos = tuple(str(p).strip().lower() for p in (cfg.get("planos") or ()))
    if not (_s(tier_pref) and substitui and planos):
        raise Contrato(f"bloco '{CHAVE_LOOKUP}' incompleto (tier, substitui, planos)")

    analise = perfil.get("analise")
    execucao = perfil.get("execucao")

    sinais = []
    plano = None
    if isinstance(perfil_advogado, dict):
        plat = perfil_advogado.get("plataforma")
        if isinstance(plat, dict) and _s(plat.get("plano")):
            plano = plat["plano"].strip().lower()
            if plano in planos:
                sinais.append({"sinal": "perfil", "detalhe": f"plataforma.plano = {plano}"})
    fam_sessao = familia_do_id(modelo_sessao)
    if fam_sessao == tier_pref:
        sinais.append({"sinal": "sessao", "detalhe": f"modelo da sessão = {modelo_sessao}"})

    disponivel = bool(sinais)
    if disponivel and analise in substitui:
        analise_rec = tier_pref
        motivo = (f"{tier_pref} disponível ({', '.join(s['sinal'] for s in sinais)}): a análise "
                  f"inicial sobe de {analise} para {tier_pref}; execução segue em {execucao}")
    elif disponivel:
        analise_rec = analise
        motivo = (f"{tier_pref} disponível, mas o perfil {pid} analisa em {analise}, que não é "
                  f"substituído — só {', '.join(substitui)} sobe")
    else:
        analise_rec = analise
        motivo = (f"nenhum sinal de {tier_pref}: plano não se presume — análise em {analise}, "
                  f"como no catálogo")

    checkpoint = bool(fam_sessao) and fam_sessao != analise_rec



    esforco = ((perfis.get("esforco") or {}).get("por_perfil_analise") or {}).get(pid)
    return {
        "cenario": str(cenario),
        "nome": c.get("cenario"),
        "perfil": pid,
        "analise_catalogo": analise,
        "analise_recomendada": analise_rec,
        "execucao": execucao,
        "fable_disponivel": disponivel,
        "sinais": sinais,
        "plano_declarado": plano,
        "modelo_sessao": modelo_sessao if _s(modelo_sessao) else None,
        "familia_sessao": fam_sessao,
        "checkpoint_sugerido": checkpoint,
        "esforco_recomendado": esforco if _s(esforco) else None,
        "motivo": motivo + (f"; esforço recomendado para a análise em {analise_rec}: {esforco} (ajuste do advogado na sessão)" if _s(esforco) else ""),
        "nao_muda": ["execucao", "conselho_por_assento"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tier recomendado para a análise inicial de um cenário — sobe a Fable só por sinal (perfil ou sessão).")
    ap.add_argument("--cenario", required=True, help="número do cenário no catálogo (1–31)")
    ap.add_argument("--perfil", default=None, help="perfil.json do advogado (default: $DSR_PERFIL ou ~/.config/dissero/perfil.json)")
    ap.add_argument("--modelo-sessao", default=None, help="ID do modelo da sessão, se já conhecido (dispensa o transcript)")
    ap.add_argument("--transcripts", default=None, help="raiz dos transcripts da sessão principal (default: $DSR_TRANSCRIPTS_MAIN_DIR ou ~/.claude/projects)")
    ap.add_argument("--perfis", default=None, help="perfis_modelo.json (default: o da skill dissero-orquestrador)")
    ap.add_argument("--sem-transcript", action="store_true", help="não ler transcript nenhum (só perfil e --modelo-sessao)")
    a = ap.parse_args(argv)

    try:
        perfis, origem_perfis = carregar_perfis(a.perfis)
        perfil_adv, origem_perfil = carregar_perfil_advogado(a.perfil)
        modelo = a.modelo_sessao
        origem_modelo = "argumento" if _s(modelo) else None
        if not _s(modelo) and not a.sem_transcript:
            tr = transcript_mais_recente(_raiz_transcripts(a.transcripts))
            modelo = modelo_no_transcript(tr)
            origem_modelo = tr if _s(modelo) else None
        saida = recomendar(a.cenario, perfis, perfil_adv, modelo)
        saida.update({"ok": True, "origem": {"perfis_modelo": origem_perfis,
                                             "perfil_advogado": origem_perfil,
                                             "modelo_sessao": origem_modelo}})
        print(json.dumps(saida, ensure_ascii=False))
        return 0
    except Contrato as e:
        print(json.dumps({"ok": False, "erro": "contrato", "motivo": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
