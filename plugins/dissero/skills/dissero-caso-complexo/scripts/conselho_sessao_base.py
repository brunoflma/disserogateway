"""Módulo-base do conselho_sessao.py: constantes do rito e funções-folha do produtor.

Mora ao lado do conselho_sessao.py, que importa tudo daqui. Num arquivo só, o script encostava
no teto do conector, que recusa script servido maior que ele (truncado, ele não roda); os dois são
servidos e selados, e `conselho_sessao.py conferir` confere os dois selos. Nada aqui lê o estado do
disco nem resolve a pasta do caso: isso fica no principal, onde os testes o substituem."""
import sys, os, json, copy, time, tempfile  # noqa: F401
from datetime import datetime, timezone  # noqa: F401


CADEIRAS = ("merito", "coerencia", "escrita", "conformidade")


NOMES = {"merito": "Mérito", "coerencia": "Coerência", "escrita": "Escrita", "conformidade": "Conformidade"}


RISCOS = ("alto", "baixo")


MODOS = ("subagentes", "serial")


FASES = ("distribuicao", "debate", "votacao", "apreciacao")


RESULTADOS = ("aprovado", "devolvido")


VOTOS = ("aprovar", "devolver")


ST_CADEIRA = ("aguardando", "analisando", "debatendo", "votou")


ST_RELATOR = ("aguardando", "apreciando", "decidiu")


ST_ATA = {"analisando": "em análise", "debatendo": "em debate", "apreciando": "apreciando"}


ROTULOS = {"distribuicao": "Distribuição", "debate": "Debate", "votacao": "Votação",
           "apreciacao": "Apreciação"}


MODELOS = ("opus", "sonnet", "haiku", "herdado")


PERFIS = ("P-A", "P-O", "P-S", "P-H")


SUPERFICIES_EXIBICAO = ("widget", "artifact", "arquivo")


PASSOS = ("distribuicao", "debate", "votacao", "apreciacao", "fim")


LOTE = ("o voto anterior ainda não foi mostrado ao advogado: emita e mostre o painel depois de "
        "CADA voto, na ordem em que chegam (regimento §3 item 7)")


CONVERSOR = ("o conversor desta cópia é anterior à 3.0.1: mostre o plenário inteiro a cada "
             "movimento e atualize a cópia da conta")


def _painel(state):
    b = os.path.basename(state)
    cap = b[16:-5] if b.startswith("CONSELHO_STATUS_") and b.endswith(".json") else ""
    return f"PAINEL_CONSELHO_{cap}.html" if cap else "PAINEL_CONSELHO.html"


class Contrato(Exception):
    pass


def _is_int(x):   return isinstance(x, int) and not isinstance(x, bool)


def _full_str(x): return isinstance(x, str) and bool(x.strip())


def _d(o, k, t=dict):
    v = o.get(k)
    return v if isinstance(v, t) else t()


def _modelo(valor, rotulo="--modelo"):
    if valor is None:
        return None
    if not _full_str(valor):
        raise Contrato([f"{rotulo} não pode ser vazio (declare o tier ou omita a opção)"])
    return valor.strip()


def _tentar(f, *a):
    for i in range(80):
        try:
            return f(*a)
        except PermissionError:
            if i == 79:
                raise
            time.sleep(0.025)


def _stepkey(fase):
    return "fim" if fase in ("aprovado", "devolvido") else fase


def _snapshot(st):
    key = _stepkey(st.get("fase"))
    if not key:
        return
    st.setdefault("historico", {})[key] = {
        "atualizado": st.get("atualizado", ""),
        "fase": st.get("fase"),
        "cadeiras": [{"id": c.get("id"), "status": c.get("status"), "voto": c.get("voto"),
                      "fundamentacao": c.get("fundamentacao", ""),
                      "argumento_debate": c.get("argumento_debate", ""),
                      "modelo_pedido": c.get("modelo_pedido"), "voto_anterior": c.get("voto_anterior")}
                     for c in st.get("cadeiras", []) if isinstance(c, dict)],
        "relator": {k: st.get("relator", {}).get(k)
                    for k in ("status", "voto", "fundamentacao", "placar", "vencido", "modelo_pedido",
                              "voto_anterior")},
        "eventos_len": len(st.get("eventos", [])),
    }


def _lista(st, chave):
    return [e for e in _d(_d(st, "painel"), chave, list) if isinstance(e, dict)]


def _p(e):
    return _stepkey(str(e.get("fase", "")).strip())


def _fases(st, chave):
    return {_p(e) for e in _lista(st, chave)}


def _ult(st, t="proclamacao"):
    return max([i + 1 for i, e in enumerate(_d(st, "eventos", list))
                if isinstance(e, dict) and e.get("tipo") == t], default=0)


def _falta(st, passo):
    """'' em dia; senão 'não EMITIDO' ou 'defasado' (menos votos, ou antes da última revisão ou,
    no fim, da proclamação)."""
    es = [e for e in _lista(st, "emissoes") if _p(e) == passo]
    n, p = sum(_contar_placar(st)), _ult(st, "proclamacao" if passo == "fim" else "revisao_de_voto")
    if any(not (_is_int(e.get("votos")) and e["votos"] < n) and not (
            _is_int(e.get("eventos_len")) and e["eventos_len"] < p) for e in es):
        return ""
    return "defasado (emitido antes do último voto, revisão ou proclamação)" if es else "não EMITIDO"


def _lote(st):
    """Anti-lote (aviso), ANTES do voto; sem `painel.movimentos`, o do conversor."""
    b = _d(st, "painel")
    if "movimentos" not in b:
        if _lista(st, "emissoes") and not b.get("aviso_conversor"):
            b["aviso_conversor"] = True
            return [CONVERSOR]
        return []
    m = (_lista(st, "movimentos") or [{}])[-1]
    v, e = m.get("votos"), m.get("eventos_len")
    return [LOTE] if sum(_contar_placar(st)) > (v if _is_int(v) else 0) or (
        _is_int(e) and e < _ult(st, "revisao_de_voto")) else []


def _arquivar_ciclo(st):
    anteriores = _d(st, "ciclos", list)
    f = st.get("fase")
    anteriores.append({
        "ciclo": st.get("ciclo"), "peca": st.get("peca"), "fase": f,
        "resultado": f if f in RESULTADOS else None,
        "placar": (st.get("relator") or {}).get("placar", ""),
        "encerrado_em": st.get("atualizado", ""), "session_id": st.get("session_id", ""),
        **{k: copy.deepcopy(st.get(k, [] if k in ("cadeiras", "eventos") else {}))
           for k in ("cadeiras", "relator", "art942", "historico", "eventos", "painel")}})
    return anteriores


def _estado_inicial(peca, risco, ciclo, autor_id, isolamento):
    return {
        "peca": peca, "risco": risco, "fase": "distribuicao", "ciclo": ciclo,
        "autor_id": autor_id, "isolamento": isolamento,
        "relator": {"agente_id": "", "status": "aguardando", "voto": None,
                    "fundamentacao": "", "placar": "", "vencido": False},
        "cadeiras": [{"id": c, "papel": "Vogal — " + NOMES[c], "agente_id": "",
                      "status": "aguardando", "voto": None, "fundamentacao": ""} for c in CADEIRAS],
        "pendencias_jurisprudencia": [], "eventos": [],
    }


def _deliberou(c):
    votos = _d(c, "cadeiras", list) + [c.get("relator")] + _d(_d(c, "art942"), "votos_extra", list)
    return "devolvido" in (c.get("fase"), c.get("resultado")) or any(
        isinstance(v, dict) and v.get("voto") in VOTOS for v in votos)


def _acha_cadeira(st, cid):
    for c in st.get("cadeiras", []):
        if isinstance(c, dict) and c.get("id") == cid:
            return c
    raise Contrato([f"cadeira '{cid}' não existe na sessão (rode 'abrir')"])


def _livre(st, aid, s=None):
    """O autor e o agente de OUTRO assento (cadeiras, relator, ampliação) não ocupam `s`."""
    art = _d(st, "art942")
    if aid == str(st.get("autor_id") or "").strip():
        raise Contrato(["AUTO-CERTIFICAÇÃO: o autor da peça não vota"])
    if aid in [str(x.get("agente_id")).strip() for x in [*st.get("cadeiras", []), st.get("relator"),
               *(art.get("votos_extra") or []), *(art.get("convocados") or [])]
               if isinstance(x, dict) and x is not s]:
        raise Contrato([f"agente_id '{aid}' já ocupa outro assento: um agente, um voto"])


def _ata(nome, args, rev={}):
    v = args.voto and nome + (f" revisou o voto, de {rev['voto_anterior'].upper()} para " if rev.get("tipo")
                              else " votou ") + args.voto.upper()
    if _full_str(args.evento):
        return f"{v}: {args.evento.strip()}" if v else args.evento
    return v or (f"{nome}: {ST_ATA[args.status]}" if args.status in ST_ATA else "")


def _movimento(args):
    return args.voto is not None or args.status not in (None, "aguardando")


def _status_final(args):
    if args.status in ("votou", "decidiu") and args.voto is None:
        raise Contrato([f"--status {args.status} só com --voto: é o voto que o grava"])


def _contar_placar(st):
    vs = [v.get("voto") for v in [*st.get("cadeiras", []), st.get("relator"),
                                  *((st.get("art942") or {}).get("votos_extra") or [])] if isinstance(v, dict)]
    return vs.count("aprovar"), vs.count("devolver")


def _votou(v):
    return (isinstance(v, dict) and v.get("voto") in VOTOS and _full_str(v.get("fundamentacao"))
            and _full_str(v.get("agente_id")))

# Tudo o que o principal usa, inclusive os nomes com sublinhado (o `import *` os pularia).
__all__ = [_n for _n, _v in list(globals().items())
           if not _n.startswith("__") and type(_v) is not type(sys)]
# selo dsr: sha256=44c13b9dcd25e7bcca5f9822e745a8cbe2be638297cbf42e8c2856e387fa291f
