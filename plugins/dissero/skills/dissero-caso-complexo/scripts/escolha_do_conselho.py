#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'escolha_do_conselho.py — a ESCOLHA do advogado entre o Conselho completo e a Revisão Light.'
































import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import unicodedata

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import falas_do_advogado
except Exception:
    falas_do_advogado = None

NOME = "ESCOLHA_CONSELHO.json"
SCHEMA = "dsr.escolha_do_conselho.v1"
VARIANTES = ("completo", "light")
NOMES = {"completo": "Conselho completo", "light": "Revisão Light"}



PLANO_SUGERE = {"free": "light", "pro": "light", "max": "completo", "teams": "completo"}
PLANOS_ROTULO = {"free": "gratuito", "pro": "Pro", "max": "Max", "teams": "Teams"}

MARCA_DA_PERGUNTA = "como prefere a revisão final desta peça"
PERGUNTA = (
    "Como prefere a revisão final desta peça?\n"
    "1. Conselho completo. Cinco revisores independentes (um relator e quatro julgadores) leem a "
    "peça ao mesmo tempo, debatem e votam; havendo divergência, mais dois são chamados. É a revisão "
    "mais rigorosa e a que mais consome o limite de uso da sua conta.\n"
    "2. Revisão Light. Um único revisor confere a peça em quatro frentes, uma depois da outra "
    "(mérito, coerência, escrita e conformidade), por uma lista fixa de itens, e qualquer frente que "
    "encontre problema devolve a peça. Consome bem menos, mas não é deliberação colegiada.\n"
    "Responda 1 ou 2. Pode pedir o Conselho completo depois, sobre a mesma peça.")

AVISO_CONSUMO = ("o Conselho completo abre até sete revisores, cinco deles ao mesmo tempo, e num plano "
                 "{plano} costuma esgotar o limite de uso da conta antes do fim; a Revisão Light cabe "
                 "nesse limite")
AVISO_SOBRA = ("o plano {plano} comporta o Conselho completo; a Revisão Light foi escolha do advogado")


class Recusa(Exception):
    def __init__(self, motivo, codigo="escolha_recusada"):
        super().__init__(motivo)
        self.codigo = codigo


def _norm(texto):
    if falas_do_advogado is not None:
        return falas_do_advogado.normalizar(texto)
    t = unicodedata.normalize("NFKD", texto or "")
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split()).casefold()



def plano_do_perfil(caminho=None):
    """(plano normalizado ou None, origem). Perfil ausente ou torto não é erro: é sinal ausente."""
    cands = [caminho] if caminho else [os.environ.get("DSR_PERFIL") or "",
                                       os.path.join(os.path.expanduser("~"), ".config", "dissero", "perfil.json")]
    for c in cands:
        if c and os.path.isfile(c):
            try:
                with open(c, encoding="utf-8") as fh:
                    p = json.load(fh)
            except Exception:
                return None, os.path.abspath(c)
            plat = p.get("plataforma") if isinstance(p, dict) else None
            plano = plat.get("plano") if isinstance(plat, dict) else None
            plano = plano.strip().lower() if isinstance(plano, str) and plano.strip() else None
            return plano, os.path.abspath(c)
    return None, None


def sugestao(plano):
    """{"variante": "light"|"completo"|None, "motivo"}: a sugestão nunca decide sozinha."""
    v = PLANO_SUGERE.get((plano or "").strip().lower())
    if v is None:
        return {"variante": None, "motivo": "plano da conta não declarado no perfil: pergunte sem sugerir"}
    rot = PLANOS_ROTULO[plano.strip().lower()]
    return {"variante": v, "motivo": f"plano {rot} declarado no perfil sugere {'a' if v == 'light' else 'o'} {NOMES[v]}"}


def pergunta(plano=None):
    """O texto fixo, e, com plano declarado, a sugestão numa linha à parte."""
    s = sugestao(plano)
    if not s["variante"]:
        return PERGUNTA
    n = "2" if s["variante"] == "light" else "1"
    return (PERGUNTA + f"\nPelo plano {PLANOS_ROTULO[plano.strip().lower()]} informado no seu perfil, "
            f"sugiro a {n}; a escolha é sua.")



_PREFIXO = (r'(?:(?:quero|prefiro|escolho|pode ser|vai|vamos|fica|fico|com|de|faz|faca|manda|e|eh|'
            r'ok|sim|certo|beleza|entao|bom|a|o|na|no|pela|pelo|opcao|alternativa|numero|n|resposta)[\s,:-]+)*')
_OPCOES = (
    ("completo", r'1(?:a|o)?|primeira(?: opcao| alternativa)?|conselho completo|o completo|completo|completa'),
    ("light", r'2(?:a|o)?|segunda(?![ -]?feira)(?: opcao| alternativa)?|revisao light|revisao leve|light|leve'),
)
_SOZINHOS = {"um": "completo", "dois": "light"}
_DEPOIS_NEGA = re.compile(r'\s*,?\s*(?:nao|nunca|jamais|nem)(?!\w)(?!\s+(?:tenho|tem|ha|precisa|preciso|e|eh)\b)')
_FATO_DEPOIS = re.compile(r'\s*(?:dias?|horas?|anos?|meses|vara|turma|camara|reais|%|mil)\b')


def escolha_da_resposta(texto):
    '"completo", "light" ou None: a opção com que a resposta ABRE. Pergunta dele não escolhe;'

    n = re.sub(r'^[\W_]+', '', _norm(texto).replace("º", "o").replace("°", "o"))
    primeira = re.match(r'[^.!?\n]*[.!?\n]?', n).group(0)
    if primeira.rstrip().endswith("?"):
        return None
    inteira = re.sub(r'[\W_]+', ' ', n).strip()
    if inteira in _SOZINHOS:
        return _SOZINHOS[inteira]
    for variante, rx in _OPCOES:
        m = re.match(_PREFIXO + r'(?:' + rx + r')(?![\w])', n)
        if not m or _DEPOIS_NEGA.match(n, m.end()) or _FATO_DEPOIS.match(n, m.end()):
            continue
        if re.match(r'\s*,?\s*ou(?!\w)', n[m.end():]):
            return None
        return variante
    return None


def _ancora_registrar(entrada):
    cmd = entrada.get("command") if isinstance(entrada, dict) else None
    return isinstance(cmd, str) and "escolha_do_conselho" in cmd and "registrar" in cmd


def _nao_conferida(motivo, fonte=None):
    return {"estado": "nao_conferida", "fonte": fonte, "resposta": None, "motivo": motivo}


TRECHOS_DA_PERGUNTA = (MARCA_DA_PERGUNTA, "Conselho completo", "Revisão Light")


def conferir_palavras(variante, palavras, env=None, livro=None):
    '{"estado": "conferida"|"nao_conferida", ...}; levanta Recusa quando a escolha não se sustenta.'



    dita = escolha_da_resposta(palavras)
    if dita is None:
        raise Recusa("as palavras não abrem por uma das duas opções («1», «2», «o completo», «a light»); "
                     "grave a resposta dele à pergunta, como ele a escreveu")
    if dita != variante:
        raise Recusa(f"as palavras dizem «{NOMES[dita]}», e a variante gravada é «{NOMES[variante]}»")
    if falas_do_advogado is None:
        return _nao_conferida("o leitor das mensagens do advogado não está nesta cópia do plugin")
    falas, fonte, motivo = falas_do_advogado.falas_da_sessao(env, TRECHOS_DA_PERGUNTA, _ancora_registrar, livro)
    if falas is None:
        return _nao_conferida(motivo or "sem registro legível da conversa")
    if fonte == "livro_de_falas":
        ultima = escolha_da_resposta(falas[-1]) if falas else None
        if ultima and ultima != variante:
            raise Recusa(f"a última mensagem do advogado diz «{NOMES[ultima]}», e a variante gravada é «{NOMES[variante]}»")
        return _nao_conferida("no Cowork remoto o registro guarda as mensagens dele, mas não a pergunta", fonte)
    resp, porque = falas_do_advogado.resposta_a_pergunta(falas, lambda f: escolha_da_resposta(f) is not None)
    if resp is None:
        raise Recusa(f"{porque}. Faça a pergunta com o texto fixo e grave a resposta dele")
    if escolha_da_resposta(resp) != variante:
        raise Recusa("a resposta do advogado à pergunta diz a outra opção. Não escolha por ele: pergunte "
                     "de novo, se preciso, e grave a resposta")
    if _norm(palavras).strip(" .,;!") not in _norm(resp):
        raise Recusa("as palavras gravadas não saem da resposta dele à pergunta; grave a resposta como ele a escreveu")
    return {"estado": "conferida", "fonte": fonte, "motivo": None, "resposta": " ".join(resp.split())[:300]}



def _selo(reg):
    base = {k: v for k, v in reg.items() if k != "selo"}
    return hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def montar(variante, palavras, agora=None, anterior=None, conferencia=None, plano=None):
    if variante not in VARIANTES:
        raise Recusa("--variante é completo ou light", "contrato_invalido")
    p = " ".join((palavras or "").split())
    if not p:
        raise Recusa("--palavras é obrigatório: o que o advogado escreveu ao escolher, como ele escreveu",
                     "contrato_invalido")
    if len(p) > 600:
        raise Recusa("--palavras leva só a frase da escolha (até 600 caracteres), não a conversa", "contrato_invalido")
    reg = {"schema_version": SCHEMA, "gerado_por": "escolha_do_conselho.py", "variante": variante,
           "palavras": p, "plano_declarado": plano, "sugestao": sugestao(plano)["variante"],
           "em": (agora or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if isinstance(conferencia, dict):
        reg["conferencia"] = conferencia
    if isinstance(anterior, dict) and anterior.get("variante") in VARIANTES:
        hist = list(anterior.get("historico") or [])
        hist.append({k: anterior.get(k) for k in ("variante", "palavras", "em")})
        reg["historico"] = hist[-10:]
    reg["selo"] = _selo(reg)
    return reg


def gravar(pasta, reg):
    caminho = os.path.join(pasta, NOME)
    tmp = caminho + ".parcial"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, caminho)
    return caminho


def ler(pasta):
    """(registro, None), ou (None, motivo). Registro escrito ou alterado à mão não vale."""
    caminho = os.path.join(pasta or ".", NOME)
    if not os.path.isfile(caminho):
        return None, "o advogado ainda não escolheu entre o Conselho completo e a Revisão Light"
    try:
        with open(caminho, encoding="utf-8") as fh:
            reg = json.load(fh)
    except Exception:
        return None, "o registro da escolha do Conselho está ilegível"
    if (not isinstance(reg, dict) or reg.get("schema_version") != SCHEMA or reg.get("variante") not in VARIANTES
            or reg.get("gerado_por") != "escolha_do_conselho.py" or not str(reg.get("palavras") or "").strip()
            or reg.get("selo") != _selo(reg)):
        return None, "o registro da escolha do Conselho não foi gravado pelo script (ou foi alterado depois)"
    return reg, None


def nota_conferencia(reg):
    """A frase para o acórdão: conferida, ou NÃO CONFERIDO, em português de advogado."""
    c = (reg or {}).get("conferencia")
    if isinstance(c, dict) and c.get("estado") == "conferida":
        return "escolha conferida nas mensagens dele"
    return "escolha NÃO CONFERIDA nas mensagens dele"


def _deliberou(c):
    cad = c.get("cadeiras") if isinstance(c.get("cadeiras"), list) else []
    art = c.get("art942") if isinstance(c.get("art942"), dict) else {}
    ext = art.get("votos_extra") if isinstance(art.get("votos_extra"), list) else []
    if "devolvido" in (c.get("fase"), c.get("resultado")) or any(
            isinstance(v, dict) and v.get("voto") == "devolver" for v in [*cad, c.get("relator"), *ext]):
        return "light_apos_devolucao"
    if any(isinstance(v, dict) and v.get("voto") in ("aprovar", "devolver") for v in [*cad, c.get("relator"), *ext]):
        return "light_apos_voto"
    return None


def completo_deliberado(st):
    '(código, ciclo) do primeiro ciclo do Conselho COMPLETO que votou ou devolveu a peça nesta'

    if not isinstance(st, dict):
        return None
    for c in [*(st.get("ciclos") if isinstance(st.get("ciclos"), list) else []), st]:
        if not isinstance(c, dict) or c.get("variante") == "light":
            continue
        cod = _deliberou(c)
        if cod:
            return cod, c.get("ciclo")
    return None


def _sessoes_da_pasta(pasta):
    '[(arquivo, sessão)] de TODO .json da pasta com forma de sessão do Conselho (cadeiras em lista),'


    out = []
    try:
        nomes = sorted(n for n in os.listdir(pasta or ".") if n.lower().endswith(".json"))
    except OSError:
        return out
    for n in nomes:
        p = os.path.join(pasta or ".", n)
        try:
            if os.path.getsize(p) > 4_000_000:
                continue
            with open(p, encoding="utf-8") as fh:
                st = json.load(fh)
        except Exception:
            continue
        if isinstance(st, dict) and isinstance(st.get("cadeiras"), list):
            out.append((p, st))
    return out


def completo_na_pasta(pasta):
    '(código, ciclo, arquivo) do primeiro Conselho COMPLETO que votou ou devolveu a peça em qualquer'

    for p, st in _sessoes_da_pasta(pasta):
        d = completo_deliberado(st)
        if d:
            return d[0], d[1], p
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="escolha_do_conselho.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("pergunta", "sugestao"):
        sub.add_parser(n).add_argument("--perfil")
    r = sub.add_parser("registrar")
    r.add_argument("--pasta", required=True)
    r.add_argument("--variante", required=True)
    r.add_argument("--palavras", required=True)
    r.add_argument("--perfil")
    sub.add_parser("conferir").add_argument("--pasta", required=True)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if a.cmd in ("pergunta", "sugestao"):
        plano, origem = plano_do_perfil(a.perfil)
        if a.cmd == "pergunta":
            print(pergunta(plano))
        else:
            print(json.dumps(dict(sugestao(plano), ok=True, plano=plano, perfil=origem), ensure_ascii=False))
        return 0
    if not os.path.isdir(a.pasta):
        print(json.dumps({"ok": False, "codigo": "contrato_invalido", "mensagem": "a pasta não existe"},
                         ensure_ascii=False))
        return 2
    if a.cmd == "conferir":
        reg, problema = ler(a.pasta)
        if reg is None:
            print(json.dumps({"ok": False, "codigo": "sem_escolha", "mensagem": problema}, ensure_ascii=False))
            return 1
        print(json.dumps({"ok": True, "variante": reg["variante"], "palavras": reg["palavras"],
                          "conferencia": nota_conferencia(reg)}, ensure_ascii=False))
        return 0
    plano, _origem = plano_do_perfil(a.perfil)
    anterior, _ = ler(a.pasta)
    try:
        montar(a.variante, a.palavras)
        if a.variante == "light":
            d = completo_na_pasta(a.pasta)
            if d:
                raise Recusa(f"o Conselho completo já {'devolveu a peça' if d[0] == 'light_apos_devolucao' else 'votou'} "
                             f"no ciclo {d[1]} ({d[2]}); a Revisão Light não toma o lugar dele. A ressubmissão "
                             f"volta ao completo (`conselho_sessao.py novo-ciclo`).", d[0])
        conf = conferir_palavras(a.variante, a.palavras)
        reg = montar(a.variante, a.palavras, anterior=anterior, conferencia=conf, plano=plano)
    except Recusa as e:
        print(json.dumps({"ok": False, "codigo": e.codigo, "mensagem": str(e)}, ensure_ascii=False))
        return 2 if e.codigo == "contrato_invalido" else 1
    gravar(a.pasta, reg)
    out = {"ok": True, "variante": reg["variante"], "conferencia": conf["estado"],
           "sugestao": reg["sugestao"], "trocou": bool(anterior and anterior["variante"] != reg["variante"])}
    avisos = []
    if plano in ("free", "pro") and reg["variante"] == "completo":
        avisos.append(AVISO_CONSUMO.format(plano=PLANOS_ROTULO[plano]))
    if plano in ("max", "teams") and reg["variante"] == "light":
        avisos.append(AVISO_SOBRA.format(plano=PLANOS_ROTULO[plano]))
    if conf["estado"] != "conferida":
        avisos.append("escolha gravada SEM conferência nas mensagens do advogado (" + (conf.get("motivo") or "")
                      + "); o acórdão dirá isso")
    if avisos:
        out["avisos"] = avisos
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
