#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'estado_peca.py — máquina de estados da peça da skill dissero-peticao.'









































































import sys, os, re, json, argparse, subprocess, hashlib, math, shutil, tempfile, zipfile
import datetime
import xml.etree.ElementTree as ET

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
try:
    import caso_raiz
except Exception:
    caso_raiz = None
GATE_CONSELHO = os.path.join(AQUI, "conselho_gate.py")
_RE_CASO_ID = re.compile(r"^caso-[0-9a-f]{12}$")
LINT_PECA = os.path.join(AQUI, "..", "..", "dissero-visual-law", "scripts", "lint_peca.py")





LINT_TIMEOUT_S = 8


def _emitir_trace(fase, evento, dados):
    'Trace opcional: só escreve se env DSR_TRACE apontar um arquivo. Nunca levanta e nunca'

    destino = os.environ.get("DSR_TRACE")
    if not destino:
        return
    try:
        linha = json.dumps({"fase": fase, "evento": evento, "dados": dados}, ensure_ascii=False)
        with open(destino, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        return

ORDEM = ("briefing", "prazo", "estrategia", "adversarial", "mapa", "redacao",
         "verificacao", "visual_law", "lint", "conselho", "entrega")
RISCOS = ("alto", "baixo")



MODOS = ("cowork", "code", "chat")
GRAUS = ("primeiro", "segundo", "superior")
STATUS = ("pendente", "concluida", "bloqueada")












FASES_OPCIONAIS = ("adversarial",)


_BOOL_EV = ("briefing_forte", "ok_advogado", "aprovado", "ooxml_valido", "urgente", "liberado",
            "dispensa_por_urgencia", "sem_jurisprudencia", "honorarios")
_INT_EV = ("exit_code",)



_LIST_EV = ("pendencias_jurisprudencia", "trechos_lacrados", "contradicoes_sem_lastro",
            "pendencias_lint", "pedidos")



_STR_EV = ("autor_id",)



def _is_int(x):   return isinstance(x, int) and not isinstance(x, bool)
def _is_bool(x):  return isinstance(x, bool)
def _full_str(x): return isinstance(x, str) and bool(x.strip())



def _id(x):       return x.strip() if isinstance(x, str) and x.strip() else ""



_LIGADO = ("1", "true", "sim")


def _exige(st, args, chave):
    'A exigencia `chave` vale nesta peca? Le o que esta ESCRITO, nada mais.'













    if isinstance(st, dict) and st.get(chave) is True:
        return True
    if args is not None and getattr(args, chave, False):
        return True
    return os.environ.get("DSR_" + chave.upper(), "").strip().lower() in _LIGADO


def _exige_adversarial(st, args=None):
    'Etapa adversarial exigida? Chave `exigir_adversarial` (ver `_exige`). O `init` grava true'

    return _exige(st, args, "exigir_adversarial")


def _exige_estanqueidade(st, args=None):
    'Declaracao de estanqueidade exigida? Chave `exigir_estanqueidade` (ver `_exige`).'







    return _exige(st, args, "exigir_estanqueidade")


def _exige_squad(st, args=None):
    'Squad exigido? Chave `exigir_squad` (ver `_exige`). O `init` grava true por padrao;'

    return _exige(st, args, "exigir_squad")


def _leitura_pelo_squad(st):
    '(ok, motivo) — a leitura dos autos passou pelo squad?'











    caminho = None
    try:
        if caso_raiz is not None:
            caminho = caso_raiz.arquivo("SQUAD_STATE.json")
    except Exception:
        caminho = None
    if not caminho or not os.path.isfile(caminho):
        return False, ("o squad e obrigatorio nesta peca e nao ha SQUAD_STATE.json na raiz do "
                       "caso: a leitura dos autos precisa passar pela turma. Inicie com "
                       "`squad.py init --area <area do caso>` e conclua a etapa `memoria`, ou "
                       "declare a dispensa em "
                       "`init --sem-squad \"<motivo>\"`")
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            squad = json.load(arquivo)
    except Exception as exc:
        return False, ("SQUAD_STATE.json ilegivel em %s (%s): squad ilegivel nao e squad "
                       "cumprido" % (caminho, exc))
    etapas = squad.get("etapas") if isinstance(squad, dict) else None
    memoria = etapas.get("memoria") if isinstance(etapas, dict) else None
    if not isinstance(memoria, dict) or memoria.get("status") != "concluida":
        return False, ("o squad existe mas a etapa `memoria` nao esta concluida (status: %r): "
                       "e ela a leitura dos autos pela turma, que e o que a exigencia cobra"
                       % ((memoria or {}).get("status") if isinstance(memoria, dict) else None))
    return True, ""


def _fases_exigidas(st, args=None):
    'Fases que o rito EXIGE nesta peca. FASES_OPCIONAIS so entram quando declaradas.'




    if _exige_adversarial(st, args):
        return ORDEM
    return tuple(f for f in ORDEM if f not in FASES_OPCIONAIS)


class Contrato(Exception):
    """Violação de contrato/uso → exit 2 (resultado 'contrato_invalido')."""


def _saida(resultado, st, motivos, exit_code, extra=None):
    """Emite o envelope JSON na última linha e devolve o exit code."""
    payload = {"ok": True, "resultado": resultado,
               "fase_atual": (st.get("fase_atual") if isinstance(st, dict) else None),
               "motivos": list(motivos)}
    if extra:
        payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code



def _validar_evidencia(nome, ev):
    m = []
    if not isinstance(ev, dict):
        return [f"fases.{nome}.evidencia deve ser objeto"]
    for f in _BOOL_EV:
        if f in ev and not _is_bool(ev[f]):
            m.append(f"fases.{nome}.evidencia.{f} deve ser booleano (true/false), não string/int")
    for f in _INT_EV:
        if f in ev and not _is_int(ev[f]):
            m.append(f"fases.{nome}.evidencia.{f} deve ser inteiro (não bool/float/string)")
    for f in _LIST_EV:
        if f in ev and (not isinstance(ev[f], list) or any(not isinstance(item, str) for item in ev[f])):
            m.append(f"fases.{nome}.evidencia.{f} deve ser lista de strings")
    for f in _STR_EV:
        if f in ev and not _full_str(ev[f]):
            m.append(f"fases.{nome}.evidencia.{f} deve ser string nao-vazia (id do agente)")
    if "valor_causa" in ev and not _full_str(ev["valor_causa"]):
        m.append(f"fases.{nome}.evidencia.valor_causa deve ser texto com o valor (ex.: \"R$ 50.000,00\")")
    if isinstance(ev.get("pedidos"), list) and any(not _full_str(x) for x in ev["pedidos"]):
        m.append(f"fases.{nome}.evidencia.pedidos não pode ter item vazio")
    return m


def _validar_registro(nome, v):
    if not isinstance(v, dict):
        return [f"fases.{nome} deve ser objeto"]
    m = []
    if v.get("status") not in STATUS:
        m.append(f"fases.{nome}.status deve ser um de {STATUS}")
    if "artefato" in v and not isinstance(v["artefato"], str):
        m.append(f"fases.{nome}.artefato deve ser string")
    if "concluida_em" in v and v["concluida_em"] is not None and not isinstance(v["concluida_em"], str):
        m.append(f"fases.{nome}.concluida_em deve ser string ou null")
    if "entrega_por_download" in v and not _is_bool(v["entrega_por_download"]):
        m.append(f"fases.{nome}.entrega_por_download deve ser booleano (true/false)")
    if "evidencia" in v and v["evidencia"] is not None:
        m += _validar_evidencia(nome, v["evidencia"])
    return m



def _sha256(path):
    'SHA-256 do arquivo, ou None se ilegível. Lê em blocos: peça com imagens passa de 10 MB'

    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for bloco in iter(lambda: fh.read(1 << 20), b""):
                h.update(bloco)
        return h.hexdigest()
    except Exception:
        return None


def conferir_canonico(st):
    '(estado, detalhe, dados) do arquivo canônico.'




    caminho = st.get("arquivo_canonico")
    if not _full_str(caminho):
        return ("nao_registrado", "nenhum arquivo de trabalho registrado no PECA_STATE", {})
    registrado = st.get("hash_canonico")
    if not os.path.isfile(caminho):
        return ("ausente", f"o arquivo de trabalho registrado não existe: {_nome_arq(caminho)}",
                {"arquivo_canonico": caminho, "hash_registrado": registrado})
    atual = _sha256(caminho)
    dados = {"arquivo_canonico": caminho, "hash_registrado": registrado, "hash_atual": atual}
    if not _full_str(registrado):
        return ("divergente", "arquivo registrado SEM hash — recarimbe com `canonico`", dados)
    if atual != registrado:
        return ("divergente",
                f"o arquivo de trabalho MUDOU desde a última vez que o plugin o viu "
                f"({_nome_arq(caminho)}). Ou o advogado o editou à mão — e o trabalho desta sessão "
                f"precisa ser rebaseado sobre a versão dele —, ou voltou a haver duas cópias "
                f"vivas. Não decida sozinho: mostre a divergência e pergunte qual vale.", dados)
    return ("confere", f"arquivo de trabalho íntegro: {_nome_arq(caminho)}", dados)


def validar_contrato(st):
    """Valida o PECA_STATE inteiro. Levanta Contrato([motivos]) em qualquer violação."""
    if not isinstance(st, dict):
        raise Contrato(["raiz do PECA_STATE deve ser um objeto JSON"])
    m = []
    if not _full_str(st.get("peca")):
        m.append("peca: string não-vazia obrigatória")
    if st.get("risco") not in RISCOS:
        m.append(f"risco deve ser um de {RISCOS}")
    if st.get("modo_execucao") not in MODOS:
        m.append(f"modo_execucao deve ser um de {MODOS}")
    if st.get("fase_atual") not in ORDEM:
        m.append("fase_atual fora do enum de fases")
    if not _is_bool(st.get("is_minuta")):
        m.append("is_minuta deve ser booleano (true/false), não string/int")





    if "exigir_adversarial" in st and not _is_bool(st["exigir_adversarial"]):
        m.append("exigir_adversarial deve ser booleano (true/false), não string/int")
    if "exigir_estanqueidade" in st and not _is_bool(st["exigir_estanqueidade"]):
        m.append("exigir_estanqueidade deve ser booleano (true/false), não string/int")
    if "exigir_squad" in st and not _is_bool(st["exigir_squad"]):
        m.append("exigir_squad deve ser booleano (true/false), não string/int")



    for chave in ("dispensa_adversarial", "dispensa_squad"):
        if st.get(chave) is not None and not isinstance(st[chave], str):
            m.append(f"{chave} deve ser string (o motivo da dispensa) ou null")
    if st.get("grau_jurisdicao") is not None and st["grau_jurisdicao"] not in GRAUS:
        m.append(f"grau_jurisdicao deve ser um de {GRAUS} ou null")
    if "processos" in st and (not isinstance(st["processos"], list)
                              or any(not isinstance(x, str) for x in st["processos"])):
        m.append("processos deve ser lista de strings (números CNJ do caso)")
    if st.get("session_id") is not None and not _full_str(st["session_id"]):
        m.append("session_id deve ser string não-vazia (id da sessão do harness) ou null")
    pend = st.get("pendencias_jurisprudencia")
    if not isinstance(pend, list) or any(not isinstance(x, str) for x in pend):
        m.append("pendencias_jurisprudencia deve ser lista de strings (não tratada como vazia se tipo errado)")
    if "atualizado" in st and st["atualizado"] is not None and not isinstance(st["atualizado"], str):
        m.append("atualizado deve ser string (timestamp) ou null")
    if "ciclo" in st and (not _is_int(st["ciclo"]) or st["ciclo"] < 1):
        m.append("ciclo deve ser inteiro >= 1 (não bool/float/string/negativo)")
    if "reaberturas" in st and not isinstance(st["reaberturas"], list):
        m.append("reaberturas deve ser lista")
    if "arquivo_canonico" in st and not isinstance(st["arquivo_canonico"], str):
        m.append("arquivo_canonico deve ser string (caminho do arquivo de trabalho)")
    if st.get("caso_id") is not None and not (isinstance(st["caso_id"], str)
                                              and _RE_CASO_ID.match(st["caso_id"])):
        m.append("caso_id deve ser o código do caso (caso-<12 hex>) ou null")
    if "exame_mapa" in st and not _is_bool(st["exame_mapa"]):
        m.append("exame_mapa deve ser booleano (marca do estado criado com o exame do mapa)")
    if "hash_canonico" in st and st["hash_canonico"] is not None \
            and not isinstance(st["hash_canonico"], str):
        m.append("hash_canonico deve ser string (SHA-256) ou null")
    if "entregas" in st and (not isinstance(st["entregas"], list) or any(
            not isinstance(e, dict) or not all(_full_str(e.get(k)) for k in ("destino", "sha256", "data"))
            for e in st["entregas"])):
        m.append("entregas deve ser lista de recibos {destino, sha256, data} (gravada pelo `entregar`)")
    if "anexos" in st and (not isinstance(st["anexos"], list) or any(
            not isinstance(a, dict) or not all(_full_str(a.get(k)) for k in ("arquivo", "sha256"))
            for a in st["anexos"])):
        m.append("anexos deve ser lista de {arquivo, sha256} (gravada pelo `anexo`)")
    fases = st.get("fases")
    if not isinstance(fases, dict):
        m.append("fases deve ser objeto fase→registro")
    else:
        for k, v in fases.items():
            if k not in ORDEM:
                m.append(f"fases contém fase desconhecida fora do enum: {k}")
                continue
            m += _validar_registro(k, v)
    if m:
        raise Contrato(m)
    return st


def carregar(path):
    try:
        st = json.loads(open(path, encoding="utf-8").read())
    except Exception as e:
        raise Contrato([f"PECA_STATE.json ilegível/JSON inválido: {e}"])
    validar_contrato(st)



    for f in ORDEM:
        st["fases"].setdefault(f, {"status": "pendente", "artefato": "", "evidencia": {}})


    if _full_str(st.get("arquivo_canonico")):
        st["arquivo_canonico"] = _absoluto_do_estado(path, st["arquivo_canonico"])
    for a in _anexos(st):
        if isinstance(a, dict) and _full_str(a.get("arquivo")):
            a["arquivo"] = _absoluto_do_estado(path, a["arquivo"])
    return st


def _absoluto_do_estado(state_path, caminho):
    c = caminho.strip()
    if os.path.isabs(c):
        return c
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(state_path)), c))


def _relativo_ao_estado(state_path, caminho):
    'Caminho relativo à pasta do PECA_STATE, com `/`. Em outra unidade (Windows), não há'

    if not _full_str(caminho):
        return caminho
    try:
        rel = os.path.relpath(caminho.strip(), os.path.dirname(os.path.abspath(state_path)))
    except ValueError:
        return caminho
    return rel.replace(os.sep, "/")


def _gravar(path, st):
    disco = dict(st)
    if _full_str(disco.get("arquivo_canonico")):
        disco["arquivo_canonico"] = _relativo_ao_estado(path, disco["arquivo_canonico"])
    if isinstance(disco.get("anexos"), list):
        disco["anexos"] = [dict(a, arquivo=_relativo_ao_estado(path, a["arquivo"]))
                           if isinstance(a, dict) and _full_str(a.get("arquivo")) else a
                           for a in disco["anexos"]]
    open(path, "w", encoding="utf-8").write(json.dumps(disco, ensure_ascii=False, indent=2))








_EDICAO_NA_PECA = (
    (re.compile(r"L8\b", re.IGNORECASE),
     "substitua a jurisprudência assinalada pelo julgado real conferido na fonte oficial, ou "
     "retire o trecho (L8)"),

    (re.compile(r"L26\b(?!\s*CALIBRA)", re.IGNORECASE),
     "reescreva a expressão apontada no tom que a cobertura de precedentes da tese permite "
     "(L26 TOM)"),
    (re.compile(r"L34\b", re.IGNORECASE),
     "cite na frase a norma ou a base do percentual de juros, multa ou honorários apontado "
     "(L34 CONSECTÁRIO)"),
)
_SO_CONFERENCIA = (
    re.compile(r"julgado\s+n\.?\s*[º°]", re.IGNORECASE),
    re.compile(r"L11\b", re.IGNORECASE),
    re.compile(r"L25\s+PESQUISA\b", re.IGNORECASE),
    re.compile(r"L26\s*CALIBRA", re.IGNORECASE),
)

_PREFIXO_PENDENTE = re.compile(r"^\W*(?:PENDENTE\b\W*)?", re.IGNORECASE)
_CONFERIR_NA_FONTE = (
    "Julgado a conferir na fonte oficial: na raiz do caso, gere a lista de conferência com "
    "`folha_atestacao.py achados.json -o CONFERENCIA_PENDENTE.json` (skill "
    "dissero-pesquisa-juridica) e mostre ao advogado o `texto_conversa`. O PDF que ele soltar "
    "se confere com `atestar_literal.py achados.json --documentos <PDFs> --atestar -o "
    "achados.json`; a resposta dele numa linha se registra com `registrar_confirmacao_manual.py "
    "achados.json --lista CONFERENCIA_PENDENTE.json --confere <n> --nao-confere <n> --resposta "
    "\"<palavras dele>\" -o achados.json`. O `achados.json` da raiz do caso "
    "é o que o `pode-entregar` e a entrega leem sozinhos, e a conferência gravada com outro nome "
    "fica fora da reverificação. Nas outras linhas PENDENTE, siga o remédio que o linter dá. "
    "Depois relinte com `--precedentes achados.json`.")
_SEM_CODIGO = "Há linha PENDENTE sem código de regra reconhecido: leia-a na saída do linter."


def _motivo_minuta(pendencias):
    'Motivo do bloqueio da fase lint em MINUTA. `pendencias` são as linhas PENDENTE do linter'




    inicio = ("fase lint: linter devolveu MINUTA (exit 3) — a ESTRUTURA está limpa e há "
              "pendência que impede o protocolo. ")
    na_fonte = ". A correção é na fonte da peça: gere o .docx de novo e relinte."
    duas_saidas = ("Se o linter apontou L8, L26 TOM ou L34, edite a peça: "
                   + "; ".join(remedio for _, remedio in _EDICAO_NA_PECA) + na_fonte + " "
                   + _CONFERIR_NA_FONTE)
    if not (isinstance(pendencias, list) and pendencias):
        return inicio + duas_saidas
    edicoes, conferencia, duvida = set(), False, False
    for item in pendencias:
        texto = _PREFIXO_PENDENTE.sub("", str(item).strip(), count=1)
        regra = next((i for i, (rx, _) in enumerate(_EDICAO_NA_PECA) if rx.match(texto)), None)
        if regra is not None:
            edicoes.add(regra)
        elif any(rx.match(texto) for rx in _SO_CONFERENCIA):
            conferencia = True
        else:
            duvida = True
    if not edicoes:
        if duvida:
            return inicio + _SEM_CODIGO + " " + duas_saidas
        return inicio + _CONFERIR_NA_FONTE + " Nada a corrigir na peça."
    motivo = (inicio + "Edite a peça: "
              + "; ".join(r for i, (_, r) in enumerate(_EDICAO_NA_PECA) if i in edicoes)
              + na_fonte)
    if duvida:
        motivo += (" " + _SEM_CODIGO + " Se for L8, L26 TOM ou L34, ela também se resolve editando a "
                   "peça. " + _CONFERIR_NA_FONTE)
    elif conferencia:
        motivo += " As demais pendências não pedem edição. " + _CONFERIR_NA_FONTE
    return motivo



def _gate_fase(F, ev, modo, st):
    "Retorna (status_final, motivos). status_final 'concluida' libera; senão 'bloqueada'."

    if F == "briefing":
        if not _is_bool(ev.get("briefing_forte")):
            raise Contrato(["fase briefing: evidência briefing_forte (booleano) obrigatória"])
        if not ev["briefing_forte"]:
            return ("bloqueada", ["briefing fraco — não autoriza redação; continue o intake ou escale"])
        return ("concluida", [])

    if F in ("estrategia", "mapa"):



        prazo_ev = st.get("fases", {}).get("prazo", {}).get("evidencia", {}) or {}
        if ev.get("dispensa_por_urgencia") is True:
            if prazo_ev.get("urgente") is not True:
                return ("bloqueada", [f"fase {F}: dispensa_por_urgencia exige prazo URGENTE (fase prazo com urgente=true)"])
            return ("concluida", [f"fase {F}: OK do advogado DISPENSADO por urgência (prazo ≤3 dias úteis) — registrado"])
        if not _is_bool(ev.get("ok_advogado")):
            raise Contrato([f"fase {F}: evidência ok_advogado (booleano) obrigatória — ou dispensa_por_urgencia com prazo urgente"])
        if not ev["ok_advogado"]:
            return ("bloqueada", [f"fase {F}: requer OK expresso do advogado (ok_advogado=true)"])
        return ("concluida", [])

    if F == "adversarial":





        _fases = st.get("fases") if isinstance(st.get("fases"), dict) else {}
        _est = _fases.get("estrategia") if isinstance(_fases.get("estrategia"), dict) else {}
        _est_ev = _est.get("evidencia") if isinstance(_est.get("evidencia"), dict) else {}
        autor_estrategia = _id(_est_ev.get("autor_id"))
        atacante = _id(ev.get("autor_id"))
        if not atacante:
            raise Contrato(["fase adversarial: evidencia autor_id (string nao-vazia) obrigatoria "
                            "— e o id do agente que ATACA a tese, e tem de diferir do autor da "
                            "estrategia"])
        if not autor_estrategia:
            return ("bloqueada", [
                "fase adversarial: a fase estrategia nao declarou autor_id, logo nao ha como "
                "provar que o ataque veio de outro agente. Registre a estrategia com "
                "`avancar --fase estrategia ... --evidencia '{\"ok_advogado\": true, "
                "\"autor_id\": \"<id de quem desenhou a tese>\"}'` e repita o ataque"])
        if atacante == autor_estrategia:
            return ("bloqueada", [
                f"AUTO-ATAQUE: o agente que ataca (autor_id={atacante}) e o mesmo que desenhou a "
                f"estrategia. A etapa adversarial exige agente DIFERENTE — do contrario ela mede "
                f"a disposicao do autor de achar defeito em si mesmo, nao a solidez da tese"])
        return ("concluida", [])

    if F == "verificacao":






        if ev.get("sem_jurisprudencia") is True:
            pend = ev.get("pendencias_jurisprudencia", [])
            if not isinstance(pend, list):
                raise Contrato(["fase verificacao: pendencias_jurisprudencia (lista) obrigatória"])
            if pend:
                return ("bloqueada", ["fase verificacao: 'sem_jurisprudencia' declarado, mas há "
                                      f"{len(pend)} pendência(s) de precedente registrada(s)"])
            return ("concluida", [])
        ec = ev.get("exit_code")
        if not _is_int(ec):
            raise Contrato(["fase verificacao: evidência exit_code (inteiro) de validar_achados "
                            "obrigatória (peça que não cita julgado: declare sem_jurisprudencia=true)"])
        if ec != 0:
            return ("bloqueada", [f"fase verificacao: validar_achados retornou exit_code={ec} (≠0)"])
        pendencias = ev.get("pendencias_jurisprudencia")
        if not isinstance(pendencias, list):
            raise Contrato(["fase verificacao: evidência pendencias_jurisprudencia (lista) obrigatória"])
        if pendencias:
            return ("bloqueada", [f"fase verificacao: {len(pendencias)} precedente(s) pendente(s) impedem entrega"])










        lacrados = ev.get("trechos_lacrados")
        if lacrados is not None:


            if not isinstance(lacrados, list):
                raise Contrato(["fase verificacao: trechos_lacrados, quando declarado, "
                                "deve ser lista (tipo errado não é tratado como vazio)"])
            if lacrados:
                return ("bloqueada",
                        [f"fase verificacao: {len(lacrados)} trecho(s) de procedência LACRADA "
                         "na peça — material interno não vai aos autos. Reescreva a partir "
                         "de fonte aberta ou remova; a estanqueidade recusa e explica, "
                         "nunca reescreve por conta própria"])





        sem_lastro = ev.get("contradicoes_sem_lastro")
        if sem_lastro is not None:
            if not isinstance(sem_lastro, list):
                raise Contrato(["fase verificacao: contradicoes_sem_lastro, quando declarado, "
                                "deve ser lista (tipo errado não é tratado como vazio)"])
            if sem_lastro:
                return ("bloqueada",
                        [f"fase verificacao: {len(sem_lastro)} contradição(ões) AFIRMADA(S) "
                         "sem os dois lastros literais conferidos. Contradição se demonstra "
                         "citando as duas passagens verbatim; sem elas, a afirmação sai da "
                         "peça ou vira alegação, nunca acusação"])
        return ("concluida", [])

    if F == "visual_law":
        if not _is_bool(ev.get("ooxml_valido")):
            raise Contrato(["fase visual_law: evidência ooxml_valido (booleano) obrigatória"])
        if not ev["ooxml_valido"]:
            return ("bloqueada", ["fase visual_law: .docx inválido (ooxml_valido=false)"])
        return ("concluida", [])

    if F == "lint":
        ec = ev.get("exit_code")
        if not _is_int(ec):
            raise Contrato(["fase lint: evidência exit_code (inteiro) de lint_peca obrigatória"])
        if not _is_bool(ev.get("aprovado")):
            raise Contrato(["fase lint: evidência aprovado (booleano) obrigatória"])
        if modo == "chat":
            return ("bloqueada", ["modo chat: LINT fica PENDENTE, nunca APROVADO (peça sai como minuta)"])
        if ec == 3:


            return ("bloqueada", [_motivo_minuta(ev.get("pendencias_lint"))])
        if ec != 0 or not ev["aprovado"]:
            return ("bloqueada", [f"fase lint: lint_peca não APROVADO (exit_code={ec}, aprovado={ev.get('aprovado')})"])
        return ("concluida", [])


    return ("concluida", [])


def _parse_evidencia(args):
    raw = getattr(args, "evidencia", None)
    if raw is None:
        return {}
    if raw == "-":
        raw = sys.stdin.read()
    try:
        ev = json.loads(raw)
    except Exception as e:
        raise Contrato([f"--evidencia JSON inválido: {e}"])
    if not isinstance(ev, dict):
        raise Contrato(["--evidencia deve ser objeto JSON {campo: valor}"])
    return ev



def _str_ou_vazio(v):
    'Texto util, ou string vazia. O motivo da dispensa do squad e texto: `--sem-squad` sem'


    return v.strip() if isinstance(v, str) and v.strip() else ""


def _recomeco(args):
    '(anterior, motivos, saida) do `init` sobre um PECA_STATE que já existe.'





    if not os.path.exists(args.state):
        return None, [], None
    sem_squad = _str_ou_vazio(getattr(args, "sem_squad", None))
    sem_adv = _str_ou_vazio(getattr(args, "sem_adversarial", None))
    if not getattr(args, "recomecar", False) and (sem_squad or sem_adv):



        try:
            with open(args.state, encoding="utf-8-sig") as fh:
                atual = json.load(fh)
        except Exception:
            atual = None
        if not isinstance(atual, dict):
            return None, [], _saida("estado_ilegivel", None, [
                f"O PECA_STATE em {_nome_arq(args.state)} não se lê, e a dispensa não foi gravada."], 1)
        motivos = []
        if sem_squad:
            atual["exigir_squad"], atual["dispensa_squad"] = False, sem_squad
            motivos.append(f"DISPENSA DO SQUAD registrada no estado existente ({sem_squad}); fases intactas")
        if sem_adv:
            atual["exigir_adversarial"], atual["dispensa_adversarial"] = False, sem_adv
            motivos.append(f"DISPENSA DO ADVERSARIAL registrada no estado existente ({sem_adv}); "
                           "fases intactas")
        if args.ts:
            atual["atualizado"] = args.ts


        open(args.state, "w", encoding="utf-8").write(json.dumps(atual, ensure_ascii=False, indent=2))
        return None, [], _saida("dispensa_registrada", atual, motivos, 0)
    if not getattr(args, "recomecar", False):
        return None, [], _saida("estado_existente", None, [
            f"JÁ EXISTE um PECA_STATE em {_nome_arq(args.state)}, e o `init` não o grava por cima: "
            f"apagaria as fases concluídas, as reaberturas e o ciclo sem deixar rastro. Para refazer "
            f"uma etapa, use `estado_peca.py reabrir --fase <fase> --motivo \"<por quê>\"`. Para "
            f"recomeçar a peça do zero, `init --recomecar --motivo \"<por quê>\"`: o estado anterior "
            f"é arquivado em `_versoes/` e o reinício fica registrado no novo."], 1)
    motivo = _str_ou_vazio(getattr(args, "motivo", None))
    if not motivo:
        return None, [], _saida("recomeco_sem_motivo", None, [
            "`init --recomecar` exige `--motivo \"<por quê>\"`: recomeço sem razão registrada não se "
            "audita depois."], 1)
    with open(args.state, "rb") as fh:
        bruto = fh.read()
    try:
        anterior = json.loads(bruto.decode("utf-8-sig"))
    except Exception:
        anterior = {}
    anterior = anterior if isinstance(anterior, dict) else {}
    pasta = os.path.join(os.path.dirname(os.path.abspath(args.state)), "_versoes")
    os.makedirs(pasta, exist_ok=True)
    carimbo = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    copia = os.path.join(pasta, f"PECA_STATE.{carimbo}.json")
    with open(copia, "wb") as fh:
        fh.write(bruto)
    fases = anterior.get("fases") if isinstance(anterior.get("fases"), dict) else {}
    ciclo = anterior.get("ciclo") if isinstance(anterior.get("ciclo"), int) else 1
    registro = {"em": args.ts or _agora_iso(), "motivo": motivo,
                "sha256_anterior": hashlib.sha256(bruto).hexdigest(),
                "fases_concluidas_anteriores": sorted(
                    f for f, v in fases.items() if isinstance(v, dict) and v.get("status") == "concluida"),
                "ciclo_anterior": ciclo,
                "copia": os.path.relpath(copia, os.path.dirname(os.path.abspath(args.state)))}
    reinicios = anterior.get("reinicios") if isinstance(anterior.get("reinicios"), list) else []
    herdado = {"reinicios": reinicios + [registro], "ciclo": ciclo + 1}
    if isinstance(anterior.get("reaberturas"), list):
        herdado["reaberturas"] = anterior["reaberturas"]
    return herdado, [f"RECOMEÇO registrado ({motivo}): o estado anterior está em "
                     f"`_versoes/{os.path.basename(copia)}`, ciclo {ciclo + 1}"], None


def _agora_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_init(args):
    herdado, motivos_recomeco, recusa = _recomeco(args)
    if recusa is not None:
        return recusa
    st = {
        "peca": args.peca,
        "risco": args.risco,
        "modo_execucao": args.modo,
        "fase_atual": "briefing",
        "is_minuta": True,
        "ciclo": 1,





        "exigir_adversarial": not _str_ou_vazio(getattr(args, "sem_adversarial", None)),
        "dispensa_adversarial": _str_ou_vazio(getattr(args, "sem_adversarial", None)) or None,
        "exigir_estanqueidade": bool(getattr(args, "exigir_estanqueidade", False)),
        "exigir_squad": not _str_ou_vazio(getattr(args, "sem_squad", None)),
        "dispensa_squad": _str_ou_vazio(getattr(args, "sem_squad", None)) or None,
        "pendencias_jurisprudencia": [],


        "exame_mapa": True,
        "fases": {f: {"status": "pendente", "artefato": "", "evidencia": {}} for f in ORDEM},
    }
    if args.ts:
        st["atualizado"] = args.ts


    motivos = [f"PECA_STATE criado em {_nome_arq(args.state)}"] + motivos_recomeco
    if herdado:
        st.update(herdado)
    if args.grau:
        st["grau_jurisdicao"] = args.grau
    else:
        motivos.append(
            "GRAU DE JURISDIÇÃO não informado: derive-o da classe processual "
            "(`grau_jurisdicao.derivar(classe, tribunal)`) e grave com `--grau`. Sem ele o "
            "L20 do linter não confere as formas de tratamento (vocativo de 1º grau numa "
            "apelação, por exemplo)")
    if args.processo:
        st["processos"] = [p.strip() for p in args.processo if p and p.strip()]


    if args.session_id is not None:
        if not _full_str(args.session_id):
            raise Contrato(["--session-id não pode ser vazio"])
        st["session_id"] = args.session_id.strip()



    sem_codigo = "caso_raiz_indisponivel"
    if caso_raiz is not None:
        try:
            raiz, orig = caso_raiz.resolver(session_id=st.get("session_id"))
            dentro = os.path.normcase(os.path.abspath(args.state)).startswith(
                os.path.normcase(os.path.join(os.path.abspath(raiz), "")))
            if orig == "cwd":
                cid, sem_codigo = None, "caso_id_ausente"
            elif not dentro:
                cid, sem_codigo = None, "estado_fora_do_caso"
            else:
                cid, _o, erro = caso_raiz.caso_id_vigente(session_id=st.get("session_id"), criar=True)
                sem_codigo = erro or "caso_id_ausente"
        except Exception:
            cid = None
        if cid:
            st["caso_id"] = cid
    else:
        cid = None
    if not cid:
        motivos.append(f"CASO SEM CÓDIGO ({sem_codigo}): o PECA_STATE foi criado sem o código opaco "
                       "do caso (caso_id). " + {
                           "caso_id_ausente": "Nenhum caso registrado nesta sessão: registre a "
                                              "pasta do caso (`caso_raiz.py registrar`) e crie o "
                                              "estado dentro dela.",
                           "estado_fora_do_caso": "O PECA_STATE está fora da pasta do caso "
                                                  "registrado, e o código daquele caso não vale "
                                                  "para este.",
                           "caso_id_invalido": "O CASO_ID.json da pasta do caso é inválido (código "
                                               "fora do formato ou campo a mais): apague-o e "
                                               "registre a pasta de novo.",
                       }.get(sem_codigo, "O módulo do caso não respondeu; registre a pasta do caso "
                                         "e recrie o estado."))


    if caso_raiz is not None:
        try:
            amb = caso_raiz.ambiente()
        except Exception:
            amb = {}
        if amb.get("efemero"):
            motivos.append(
                f"AMBIENTE EFÊMERO ({amb.get('motivo', 'sandbox de nuvem')}): os arquivos desta sessão "
                f"são apagados ao fim dela. A peça sai por DOWNLOAD ao advogado, declarado na fase "
                f"visual_law (`avancar --fase visual_law --artefato <nome do .docx> "
                f"--entrega-por-download`); sem a declaração, o `pode-entregar` barra no fim.")
    validar_contrato(st)
    _gravar(args.state, st)
    return _saida("inicializado", st, motivos, 0)


def _avisos_de_dispensa(st, args=None):
    'Uma linha por dispensa EM VIGOR, com o motivo gravado no `init`. Gravar o motivo e nao'


    def frase(motivo):

        return motivo.strip().rstrip(" .") + "."

    linhas = []
    motivo = st.get("dispensa_squad")
    if _full_str(motivo) and not _exige_squad(st, args):
        linhas.append(f"Squad dispensado: {frase(motivo)}")
    motivo = st.get("dispensa_adversarial")
    if _full_str(motivo) and not _exige_adversarial(st, args):
        linhas.append(f"Etapa adversarial dispensada: {frase(motivo)}")
    return linhas


def cmd_status(args):
    st = carregar(args.state)
    resumo = {f: st["fases"].get(f, {}).get("status", "pendente") for f in ORDEM}

    aprovacoes = _aprovacoes(st, args.state)
    linhas = _avisos_de_dispensa(st) + [_frase_aprovacao(F, a) for F, a in aprovacoes.items()]

    return _saida("status", st, linhas, 0,
                  extra={"is_minuta": st["is_minuta"], "fases": resumo, "aprovacoes": aprovacoes,
                         "exigir_adversarial": _exige_adversarial(st),
                         "exigir_estanqueidade": _exige_estanqueidade(st),
                         "exigir_squad": _exige_squad(st),
                         "dispensa_squad": st.get("dispensa_squad"),
                         "dispensa_adversarial": st.get("dispensa_adversarial")})


def cmd_canonico(args):
    'Registra (ou reaponta) o arquivo DE TRABALHO da peça e carimba o hash.'





    st = carregar(args.state)
    if not _full_str(args.arquivo):
        raise Contrato(["canonico exige --arquivo (caminho do .docx de trabalho)"])
    caminho = os.path.abspath(os.path.expanduser(args.arquivo.strip()))
    if not os.path.isfile(caminho):
        return _saida("bloqueado", st,
                      [f"canonico: arquivo inexistente ({_nome_arq(caminho)}) — registre o arquivo que "
                       f"existe, não o que se pretende gravar"], 1)
    h = _sha256(caminho)
    if h is None:
        return _saida("bloqueado", st, [f"canonico: arquivo ilegível ({_nome_arq(caminho)})"], 1)
    anterior = st.get("arquivo_canonico")
    st["arquivo_canonico"] = caminho
    st["hash_canonico"] = h
    if args.ts:
        st["canonico_em"] = args.ts
        st["atualizado"] = args.ts
    _gravar(args.state, st)
    rel = _no_relato(args.state, caminho)
    motivos = [f"arquivo de trabalho registrado: {rel}"]
    if _full_str(anterior) and os.path.abspath(anterior) != caminho:


        motivos.append(f"o arquivo de trabalho ANTERIOR era {_no_relato(args.state, anterior)} — se ele continua na "
                       f"pasta, mova-o para `_versoes/` para que não haja duas cópias vivas")
    return _saida("canonico_registrado", st, motivos, 0,
                  extra={"arquivo_canonico": rel, "hash_canonico": h})


def cmd_qual_arquivo(args):
    'Qual é o arquivo de trabalho, e ele mudou desde que o plugin o viu?'




    st = carregar(args.state)
    estado, detalhe, dados = conferir_canonico(st)
    codigo = {"confere": 0, "divergente": 1, "ausente": 1, "nao_registrado": 2}[estado]
    if dados.get("arquivo_canonico"):
        dados = dict(dados, arquivo_canonico=_no_relato(args.state, dados["arquivo_canonico"]))
    return _saida(estado, st, [detalhe], codigo,
                  extra={"pode_abrir": estado == "confere", **dados})


def _anexos(st):
    """Anexos registrados no PECA_STATE: [{arquivo, sha256}]."""
    a = st.get("anexos")
    return list(a) if isinstance(a, list) else []


def _anexos_relato(state_path, anexos):
    return [dict(a, arquivo=_no_relato(state_path, a["arquivo"])) for a in anexos]


def _no_relato(state_path, caminho):
    'O caminho como o relato de máquina o cita: relativo à pasta do PECA_STATE quando fica'



    rel = _relativo_ao_estado(state_path, caminho)
    if not _full_str(rel) or rel.startswith("..") or os.path.isabs(rel):
        return _nome_arq(caminho)
    return rel


def _nome_arq(caminho):
    return os.path.basename(str(caminho).rstrip("\\/")) or str(caminho)


def _mesmo_arquivo(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _anexo_e_peca(gate, caminho, canon, state_path):
    'O arquivo traz o texto de uma peça, pelos mesmos critérios do gate de entrega? Sem os'

    try:
        ext = os.path.splitext(caminho.lower())[1]
        texto = (gate._texto_do_docx(caminho) if ext == ".docx"
                 else gate._ler_texto_enviado(caminho, ext))
        if not texto or not texto.strip():
            return False
        if gate._abre_com(gate._VOCATIVO_PECA, texto) and gate._FECHO_PECA.search(texto):
            return True
        if _full_str(canon):
            c = canon.strip()
            if not os.path.isabs(c):
                c = os.path.join(os.path.dirname(os.path.abspath(state_path)), c)
            if os.path.isfile(c):
                enviado = gate._shingles(texto)
                comum = enviado & gate._shingles(gate._texto_do_docx(c))
                return (len(comum) >= gate._SHINGLES_MINIMOS
                        and len(comum) / max(1, len(enviado)) >= gate._SOBREPOSICAO_PECA)
    except AttributeError:
        return False
    except Exception:
        return False
    return False


def cmd_anexo(args):
    'Registra o arquivo que acompanha a peça na entrega (a guia de juntada, por exemplo), com o'



    st = carregar(args.state)
    if not _full_str(args.arquivo):
        raise Contrato(["anexo exige --arquivo (caminho do arquivo que acompanha a peça)"])
    caminho = os.path.abspath(os.path.expanduser(args.arquivo.strip()))
    outros = [a for a in _anexos(st) if not _mesmo_arquivo(a["arquivo"], caminho)]
    if args.remover:
        if len(outros) == len(_anexos(st)):
            return _saida("bloqueado", st, [f"anexo: {_nome_arq(caminho)} não está registrado como anexo"], 1)
        st["anexos"] = outros
        if args.ts:
            st["atualizado"] = args.ts
        _gravar(args.state, st)
        return _saida("anexo_removido", st, [f"anexo retirado do registro: {_nome_arq(caminho)}"], 0,
                      extra={"anexos": _anexos_relato(args.state, outros)})
    if not os.path.isfile(caminho):
        return _saida("bloqueado", st,
                      [f"anexo: arquivo inexistente ({_nome_arq(caminho)}). Registre o arquivo que existe, "
                       f"não o que se pretende gravar."], 1)
    gate = _gate_entrega()
    if gate is None:
        return _saida("conferencia_indisponivel", st,
                      [f"anexo: a regra de pasta de caso do plugin ({GATE_ENTREGA}) não carregou, e "
                       f"sem ela não se sabe de que caso o arquivo é. Atualize ou reinstale o plugin "
                       f"e registre o anexo de novo."], 1)
    raiz_alheia = _caso_alheio(gate, args.state, st, caminho)
    if raiz_alheia:
        return _saida("anexo_outro_caso", st, [_msg_anexo_outro_caso(caminho, raiz_alheia)], 1)
    h = _sha256(caminho)
    if h is None:
        return _saida("bloqueado", st, [f"anexo: arquivo ilegível ({_nome_arq(caminho)})"], 1)
    canon = st.get("arquivo_canonico")
    if _full_str(canon) and _mesmo_arquivo(canon, caminho):
        return _saida("bloqueado", st,
                      [f"anexo: {_nome_arq(caminho)} é a própria peça canônica, que o `entregar` já copia. "
                       f"Registre como anexo só o arquivo que acompanha a peça."], 1)



    if _anexo_e_peca(gate, caminho, canon, args.state):
        return _saida("anexo_e_peca", st,
                      [f"anexo: {_nome_arq(caminho)} traz o texto de uma peça (o vocativo ao juízo e o "
                       f"fecho, ou a repetição da peça canônica). A peça sai como .docx pelo rito; "
                       f"anexo é só o que a acompanha (guia, memória de cálculo, Relação)."], 1)


    nome = os.path.basename(caminho)
    nomes = [os.path.basename(a["arquivo"]) for a in outros]
    if _full_str(canon):
        nomes.append(os.path.basename(canon.strip()))
    if nome.lower() in {n.lower() for n in nomes}:
        return _saida("bloqueado", st,
                      [f"anexo: já há na entrega um arquivo com o nome {nome}, e no destino um "
                       f"substituiria o outro. Renomeie o anexo e registre-o de novo."], 1)
    registro = {"arquivo": caminho, "sha256": h}
    if args.ts:
        registro["registrado_em"] = args.ts
        st["atualizado"] = args.ts
    st["anexos"] = outros + [registro]
    _gravar(args.state, st)
    return _saida("anexo_registrado", st, [f"anexo registrado: {_nome_arq(caminho)}"], 0,
                  extra={"anexos": _anexos_relato(args.state, st["anexos"])})






FASES_COM_ARQUIVO = ("prazo", "estrategia", "adversarial", "mapa", "redacao", "verificacao",
                     "visual_law", "lint")
_EXT_ARQUIVO = re.compile(r"^\S+\.(?:md|docx|json|txt|pdf|html|jsonl)$", re.I)


def _parece_arquivo(artefato):
    return bool(_EXT_ARQUIVO.match(artefato or ""))
_CHAVES_PRAZO = ("vencimento_legal", "data_alvo_D2", "urgente")


def _arquivo_do_artefato(state_path, artefato):
    """Caminho do artefato: absoluto como veio, ou relativo à pasta do PECA_STATE.json."""
    a = os.path.expanduser(artefato)
    return a if os.path.isabs(a) else os.path.join(os.path.dirname(os.path.abspath(state_path)), a)


def _sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _evidencia_do_prazo(arquivo, ev):
    '(evidência, recusa). O artefato do prazo é o registro do `calcular_prazo.py --registrar`;'

    remedio = ("rode `calcular_prazo.py ... --registrar PRAZO.json` e registre esse arquivo como artefato "
               "da fase prazo")
    try:
        reg = json.loads(open(arquivo, encoding="utf-8").read())
    except Exception:
        return ev, f"fase prazo: o artefato não é o registro da calculadora (JSON ilegível): {remedio}"
    if not isinstance(reg, dict) or reg.get("gerado_por") != "calcular_prazo.py":
        return ev, f"fase prazo: o artefato não foi gerado pela calculadora: {remedio}"
    novo = dict(ev)
    for k in _CHAVES_PRAZO:
        if k in ev and ev[k] != reg.get(k):
            return ev, (f"fase prazo: a evidência diz {k}={ev[k]!r}, e o registro da calculadora diz "
                        f"{reg.get(k)!r}. Vale o registro: tire o valor digitado ou recalcule.")
        if reg.get(k) is not None:
            novo[k] = reg[k]
    return novo, None









FASES_COM_APROVACAO = ("estrategia", "mapa")


def _squad_do_caso(state_path):
    """(caminho, estado) do SQUAD_STATE.json: o da pasta do PECA_STATE, senão o da raiz do caso."""
    candidatos = [os.path.join(os.path.dirname(os.path.abspath(state_path)), "SQUAD_STATE.json")]
    try:
        if caso_raiz is not None:
            candidatos.append(caso_raiz.arquivo("SQUAD_STATE.json"))
    except Exception:
        pass
    for caminho in candidatos:
        if caminho and os.path.isfile(caminho):
            try:
                with open(caminho, encoding="utf-8") as fh:
                    squad = json.load(fh)
            except Exception:
                return caminho, None
            return caminho, squad if isinstance(squad, dict) else None
    return None, None


def _aprovacao_da_fase(st, state_path, F):
    'Rótulo da aprovação do advogado na fase F, RE-DERIVADO do estado do mundo (arquivo e'


    reg = st["fases"].get(F) if isinstance(st["fases"].get(F), dict) else {}
    if reg.get("status") != "concluida":
        return None
    ev = reg.get("evidencia") if isinstance(reg.get("evidencia"), dict) else {}
    if ev.get("dispensa_por_urgencia") is True:
        return {"origem": "dispensada_por_urgencia"}
    sha = reg.get("artefato_sha256")
    art = reg.get("artefato") if _full_str(reg.get("artefato")) else ""
    if not (_full_str(sha) and _parece_arquivo(art.strip())):
        return {"origem": "declarada", "detalhe": "o artefato da fase não é um arquivo com hash "
                "registrado, então nenhum checkpoint pode confirmar que foi ele o aprovado"}
    arquivo = _arquivo_do_artefato(state_path, art.strip())
    if not os.path.isfile(arquivo) or _sha256(arquivo) != sha:
        return {"origem": "declarada", "detalhe": f"o arquivo «{art.strip()}» mudou ou sumiu "
                "depois do registro da fase; a aprovação registrada não alcança o texto de agora"}
    squad_path, squad = _squad_do_caso(state_path)
    if not squad:
        return {"origem": "declarada", "detalhe": "não há squad com checkpoint aprovado neste caso "
                "(`squad.py aprovar --aprovado --por \"<advogado>\"` no checkpoint que tem o arquivo "
                "entre as evidências)"}
    pasta = os.path.dirname(squad_path)
    etapas = squad.get("etapas") if isinstance(squad.get("etapas"), dict) else {}
    editado_depois = None
    for etapa in (squad.get("checkpoints") or []):
        e = etapas.get(etapa) if isinstance(etapas.get(etapa), dict) else {}
        apr = e.get("aprovacao") if isinstance(e.get("aprovacao"), dict) else {}
        if not (_full_str(apr.get("por")) and _full_str(apr.get("em"))):
            continue
        for item in (e.get("evidencias") or []):
            ref = item.get("ref") if isinstance(item, dict) else None
            if not _full_str(ref):
                continue
            alvo = ref if os.path.isabs(ref) else os.path.join(pasta, ref)
            if not (os.path.isfile(alvo) and _sha256(alvo) == sha):
                continue



            try:
                quando = datetime.datetime.fromisoformat(apr["em"].strip()).timestamp()
            except (ValueError, OSError, OverflowError):
                quando = None
            if quando is None or int(os.path.getmtime(alvo)) > quando:
                editado_depois = (etapa, apr["em"].strip())
                continue
            return {"origem": "checkpoint", "etapa": etapa, "por": apr["por"].strip(),
                    "em": apr["em"].strip(), "squad": squad_path}
    if editado_depois:
        return {"origem": "declarada", "detalhe": f"«{art.strip()}» foi modificado depois da "
                f"aprovação do checkpoint «{editado_depois[0]}» ({editado_depois[1]}), então o "
                f"advogado aprovou outro texto. Submeta a versão atual ao checkpoint de novo"}
    return {"origem": "declarada", "detalhe": f"nenhum checkpoint aprovado do squad ({squad_path}) "
            f"tem «{art.strip()}», com este conteúdo, entre as evidências"}


_NOME_FASE = {"estrategia": "estratégia", "mapa": "mapa"}


def _frase_aprovacao(F, apr):
    nome = _NOME_FASE.get(F, F)
    if apr["origem"] == "checkpoint":
        return (f"Aprovação do advogado ({nome}): conferida no checkpoint «{apr['etapa']}» do squad, "
                f"por {apr['por']} em {apr['em']}.")
    if apr["origem"] == "dispensada_por_urgencia":
        return f"Aprovação do advogado ({nome}): dispensada por urgência do prazo."
    return f"Aprovação do advogado ({nome}): declarada, sem registro que a confirme — {apr['detalhe']}."


def _aprovacoes(st, state_path):
    return {F: a for F in FASES_COM_APROVACAO if (a := _aprovacao_da_fase(st, state_path, F))}






_PALAVRA_VAZIA = {"de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "em", "no", "na",
                  "nos", "nas", "por", "para", "com", "ao", "aos", "art", "arts", "lei", "que"}
_DINHEIRO = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+,\d{2}|\d+")


def _sem_acento(texto):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(c) != "Mn")


def _palavras(texto):
    return [p for p in re.findall(r"[a-z0-9]+", _sem_acento(texto)) if p not in _PALAVRA_VAZIA]


def _centavos(texto):
    t = texto.replace("R$", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(".", "")
    try:
        return round(float(t) * 100)
    except ValueError:
        return None


def _texto_da_peca(caminho):
    if not caminho or not os.path.isfile(caminho):
        return None
    if caminho.lower().endswith(".docx"):
        return _texto_docx(caminho)
    try:
        with open(caminho, encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None


def _coerencia_pedidos(st, texto):
    """(resultado, avisos). `texto` é o da peça; None quando ela não pôde ser lida."""
    fonte = {}



    pedidos = []
    for F in ("briefing", "estrategia", "mapa"):
        ev = (st["fases"].get(F) or {}).get("evidencia") or {}
        if isinstance(ev, dict):
            fonte.update({k: ev[k] for k in ("pedidos", "valor_causa", "honorarios") if k in ev})
            pedidos += [p for p in (ev.get("pedidos") if isinstance(ev.get("pedidos"), list) else [])
                        if p not in pedidos]
    if "pedidos" in fonte:
        fonte["pedidos"] = pedidos
    if "pedidos" not in fonte:
        return ({"conferida": False}, [
            "COERÊNCIA DOS PEDIDOS não conferida: nem o briefing, nem a estratégia, nem o mapa aprovados "
            "declararam os pedidos. Declare-os "
            "na evidência do mapa (`\"pedidos\": [\"...\"]`, e `\"valor_causa\"`/`\"honorarios\"` quando "
            "houver) para a peça ser confrontada com eles antes da versão final."])
    if texto is None:
        return ({"conferida": False}, [
            "COERÊNCIA DOS PEDIDOS não conferida: o texto da peça não pôde ser lido (registre a redação "
            "como arquivo .md, .txt ou .docx)."])
    peca = set(_palavras(texto))
    ausentes = [p for p in fonte["pedidos"] if not set(_palavras(p)) <= peca]
    avisos = [f"COERÊNCIA DOS PEDIDOS: o pedido «{p}», aprovado antes da redação, não aparece na peça."
              for p in ausentes]
    res = {"conferida": True, "ausentes": ausentes}
    if _full_str(fonte.get("valor_causa")):
        alvo = _centavos(fonte["valor_causa"])
        achados = {_centavos(v) for v in _DINHEIRO.findall(texto)}
        res["valor_causa_confere"] = alvo is not None and alvo in achados
        if not res["valor_causa_confere"]:
            avisos.append(f"COERÊNCIA DOS PEDIDOS: o valor da causa aprovado antes da redação é "
                          f"{fonte['valor_causa'].strip()}, e a peça não traz esse valor.")
    if fonte.get("honorarios") is True:
        res["honorarios_confere"] = "honorarios" in peca
        if not res["honorarios_confere"]:
            avisos.append("COERÊNCIA DOS PEDIDOS: os honorários foram pedidos antes da redação, e a peça não "
                          "os menciona.")
    return res, avisos


_EXT_MAPA = (".md", ".markdown", ".txt")


def _examinar_mapa(arquivo):
    'Exame do mapa (escada de exame e quadro de teses). Sem o módulo ou com o arquivo ilegível,'

    try:
        import mapa_argumentativo
        return mapa_argumentativo.examinar_arquivo(arquivo)
    except (ImportError, OSError, UnicodeDecodeError) as e:
        return {"motivos": [], "avisos": [{"codigo": "mapa_nao_conferido", "mensagem":
                f"o exame do mapa não rodou ({type(e).__name__}); confira a escada e o quadro "
                f"de teses à mão."}]}


_REFAZER_MAPA = ("Reescrito o mapa, o OK do advogado tem de ser pedido de novo: o OK dado ao mapa "
                 "anterior não cobre o texto novo (`avancar --fase mapa` com `ok_advogado` do mapa "
                 "reescrito).")


def _exame_do_mapa_so_avisa(st, ev):
    'Motivo pelo qual o exame do mapa avisa em vez de reprovar, ou None (reprova).'






    if st.get("exame_mapa") is not True:
        return "o estado da peça é de versão anterior ao exame do mapa (caso em andamento)"
    prazo_ev = (st.get("fases", {}).get("prazo", {}) or {}).get("evidencia", {}) or {}
    if ev.get("dispensa_por_urgencia") is True and prazo_ev.get("urgente") is True:
        return "o prazo é urgente e o mapa saiu com a dispensa por urgência"
    return None


def cmd_avancar(args):
    st = carregar(args.state)
    F = args.fase
    if F not in ORDEM:
        raise Contrato([f"--fase '{F}' fora do enum de fases {ORDEM}"])
    idx = ORDEM.index(F)
    if F == "entrega":
        _emitir_trace(F, "avancar", {"resultado": "bloqueado"})
        return _saida("bloqueado", st, ["fase 'entrega' só é atingível via 'pode-entregar'"], 1)




    exigidas = _fases_exigidas(st)
    faltam = [p for p in ORDEM[:idx]
              if p in exigidas
              and (st["fases"].get(p, {}).get("status") != "concluida"
                   or not _full_str(st["fases"].get(p, {}).get("artefato")))]
    if faltam:
        _emitir_trace(F, "avancar", {"resultado": "bloqueado", "faltam": faltam})
        return _saida("bloqueado", st, [f"fase anterior não concluída / sem artefato: {p}" for p in faltam], 1)

    if not _full_str(args.artefato):
        _emitir_trace(F, "avancar", {"resultado": "bloqueado"})
        return _saida("bloqueado", st, [f"fase {F}: artefato obrigatório (string não-vazia)"], 1)

    ev = _parse_evidencia(args)
    erros_tipo = _validar_evidencia(F, ev)
    if erros_tipo:
        raise Contrato(erros_tipo)




    arquivo = None
    if F in FASES_COM_ARQUIVO and (F == "prazo" or _parece_arquivo(args.artefato.strip())):
        arquivo = _arquivo_do_artefato(args.state, args.artefato.strip())
        if not os.path.isfile(arquivo) and F == "prazo":
            _emitir_trace(F, "avancar", {"resultado": "bloqueado"})
            return _saida("bloqueado", st, [f"fase prazo: o artefato «{args.artefato.strip()}» não é o registro "
                                            f"da calculadora (arquivo não encontrado): rode `calcular_prazo.py ... "
                                            f"--registrar PRAZO.json` e registre esse arquivo como artefato"], 1)
        if not os.path.isfile(arquivo):
            _emitir_trace(F, "avancar", {"resultado": "bloqueado"})
            return _saida("bloqueado", st, [f"fase {F}: o artefato «{args.artefato.strip()}» não existe "
                                            f"({arquivo}). Registre o arquivo que a fase produziu, pelo "
                                            f"caminho completo ou relativo à pasta do PECA_STATE.json."], 1)
        if F == "prazo":
            ev, recusa = _evidencia_do_prazo(arquivo, ev)
            if recusa:
                _emitir_trace(F, "avancar", {"resultado": "bloqueado"})
                return _saida("bloqueado", st, [recusa], 1)





    avisos_mapa = []
    caminho_mapa = arquivo
    if F == "mapa" and caminho_mapa is None and args.artefato.strip().lower().endswith(_EXT_MAPA):
        candidato = _arquivo_do_artefato(args.state, args.artefato.strip())
        caminho_mapa = candidato if os.path.isfile(candidato) else None
    if F == "mapa" and not (caminho_mapa and caminho_mapa.lower().endswith(_EXT_MAPA)):
        avisos_mapa = [f"MAPA (mapa_nao_conferido): o mapa registrado («{args.artefato.strip()}») "
                       "não é arquivo de texto .md ou .txt, e a escada de exame e o quadro de teses "
                       "não foram conferidos. Registre o mapa em .md para o exame rodar."]
    elif F == "mapa":
        exame_mapa = _examinar_mapa(caminho_mapa)
        rebaixar = _exame_do_mapa_so_avisa(st, ev)
        if exame_mapa["motivos"] and not rebaixar:
            _emitir_trace(F, "avancar", {"resultado": "bloqueado",
                                         "codigos": [m["codigo"] for m in exame_mapa["motivos"]]})
            return _saida("bloqueado", st, [f"MAPA REPROVADO ({m['codigo']}): {m['mensagem']}"
                                            for m in exame_mapa["motivos"]] + [_REFAZER_MAPA], 1)
        avisos_mapa = [f"MAPA NÃO CONFORME ({m['codigo']}), registrado sem bloquear porque "
                       f"{rebaixar}: {m['mensagem']}" for m in exame_mapa["motivos"]]
        avisos_mapa += [f"MAPA ({a['codigo']}): {a['mensagem']}" for a in exame_mapa["avisos"]]

    novo_status, motivos = _gate_fase(F, ev, st["modo_execucao"], st)



    if F == "conselho" and novo_status == "concluida":
        conselho_ok, _acordao, conselho_motivos = _reverificar_conselho(
            args.artefato.strip(), st["risco"], None, session_id=st.get("session_id"))
        if not conselho_ok:
            novo_status, motivos = "bloqueada", conselho_motivos
        else:
            _st_canon = conferir_canonico(st)[2]
            outra = _versao_julgada(st, args.artefato.strip(), (_st_canon or {}).get("arquivo_canonico"))
            if outra:
                novo_status, motivos = "bloqueada", outra
    if F == "verificacao":
        st["pendencias_jurisprudencia"] = list(ev.get("pendencias_jurisprudencia", []))
    reg = st["fases"].setdefault(F, {})
    reg["status"] = novo_status
    reg["artefato"] = args.artefato.strip()
    reg["evidencia"] = ev
    if arquivo:
        reg["artefato_sha256"] = _sha256_arquivo(arquivo)
    else:
        reg.pop("artefato_sha256", None)



    if getattr(args, "entrega_por_download", False):
        if F != "visual_law":
            raise Contrato(["--entrega-por-download só se aplica à fase visual_law "
                            "(é o .docx protocolável que o advogado baixa)"])
        reg["entrega_por_download"] = True
    if args.ts:
        reg["concluida_em"] = args.ts
        st["atualizado"] = args.ts
    avisos = []
    reg.pop("aprovacao", None)
    reg.pop("coerencia_pedidos", None)
    if novo_status == "concluida":
        st["fase_atual"] = F
        avisos += avisos_mapa

        if F in FASES_COM_APROVACAO:
            apr = _aprovacao_da_fase(st, args.state, F)
            reg["aprovacao"] = apr
            avisos.append(_frase_aprovacao(F, apr))

        if F == "verificacao":
            red = st["fases"].get("redacao") or {}
            art_red = red.get("artefato") if _full_str(red.get("artefato")) else ""
            texto = (_texto_da_peca(_arquivo_do_artefato(args.state, art_red.strip()))
                     if _parece_arquivo(art_red.strip()) else None)
            reg["coerencia_pedidos"], avisos_e8 = _coerencia_pedidos(st, texto)
            avisos += avisos_e8

        if F == "visual_law" and not reg.get("entrega_por_download") and caso_raiz is not None:
            try:
                amb = caso_raiz.ambiente()
            except Exception:
                amb = {}
            if amb.get("efemero"):
                avisos.append(
                    f"AMBIENTE EFÊMERO ({amb.get('motivo', 'sandbox de nuvem')}): o .docx desta sessão "
                    f"é apagado ao fim dela. Entregue-o por download ao advogado e declare "
                    f"(`avancar --fase visual_law --artefato <nome do .docx> --entrega-por-download`); "
                    f"sem a declaração, o `pode-entregar` barra no fim.")
    _gravar(args.state, st)
    if novo_status == "concluida":
        _emitir_trace(F, "avancar", {"resultado": "fase_concluida", "novo_status": novo_status})
        return _saida("fase_concluida", st, [f"fase {F} concluída"] + avisos, 0)
    _emitir_trace(F, "avancar", {"resultado": "bloqueado", "novo_status": novo_status, "motivos": motivos})
    return _saida("bloqueado", st, motivos, 1)


def cmd_reabrir(args):
    'Devolução do conselho (SKILL.md §8): reabre uma fase e TODAS as posteriores para um'

    st = carregar(args.state)
    F = args.fase
    if F not in ORDEM:
        raise Contrato([f"--fase '{F}' fora do enum de fases {ORDEM}"])
    if F == "entrega":
        return _saida("bloqueado", st, ["não se reabre 'entrega'; reabra a fase a corrigir (ex.: redacao)"], 1)
    if not _full_str(args.motivo):
        return _saida("bloqueado", st, ["reabrir exige --motivo não-vazio (justificativa do novo ciclo)"], 1)
    idx = ORDEM.index(F)
    for p in ORDEM[idx:]:
        st["fases"][p] = {"status": "pendente", "artefato": "", "evidencia": {}}
    st["fase_atual"] = ORDEM[idx - 1] if idx > 0 else "briefing"
    st["is_minuta"] = True
    st["ciclo"] = (st["ciclo"] if _is_int(st.get("ciclo")) else 1) + 1
    entrada = {"fase": F, "motivo": args.motivo.strip()}
    if args.ts:
        entrada["em"] = args.ts
        st["atualizado"] = args.ts
    st.setdefault("reaberturas", []).append(entrada)
    _gravar(args.state, st)
    return _saida("reaberta", st,
                  [f"fase '{F}' e posteriores reabertas (ciclo {st['ciclo']}); motivo registrado"], 0)


def _status_do_conselho(cs_path, session_id=None):
    'Caminho absoluto do CONSELHO_STATUS.json que o `pode-entregar` lê e entrega ao gate.'





    try:
        import conselho_gate
    except Exception as e:
        return None, f"conselho: conselho_gate.py não carregou para localizar o status ({e})"
    try:
        return os.path.abspath(conselho_gate.no_caso(cs_path, session_id)), None
    except conselho_gate.CaminhoRecusado as e:
        if e.resultado != "caso_nao_resolvido":
            return None, f"conselho NÃO liberou ({e.resultado}): {e}"
        return None, (
            f"conselho NÃO liberou (caso_nao_resolvido): o status «{cs_path}» veio sem pasta, e "
            f"a pasta do caso desta sessão não foi identificada. A pasta corrente e o último "
            f"caso registrado não identificam o caso em curso. Registre o status pelo caminho "
            f"completo (`estado_peca.py avancar --fase conselho --artefato "
            f"\"<pasta do caso>/{cs_path}\"`) ou passe "
            f"`--conselho-status \"<pasta do caso>/{cs_path}\"` ao `pode-entregar`.")


NOME_LEDGER = "PROVENIENCIA.jsonl"


def _ledger_do_caso(session_id=None):
    'Confere, antes de chamar o gate, que o registro de trabalho (`PROVENIENCIA.jsonl`) de'


    try:
        import conselho_gate
    except Exception as e:
        return f"conselho: conselho_gate.py não carregou para localizar o {NOME_LEDGER} ({e})"
    try:
        conselho_gate.no_caso(NOME_LEDGER, session_id)
    except conselho_gate.CaminhoRecusado as e:
        if e.resultado != "caso_nao_resolvido":
            return f"conselho NÃO liberou ({e.resultado}): {e}"
        return (
            f"conselho NÃO liberou (caso_nao_resolvido): na peça de risco alto, o registro de "
            f"trabalho {NOME_LEDGER} é lido só na pasta do caso desta sessão, e ela não foi "
            f"identificada. A pasta corrente e o último caso registrado não identificam o caso "
            f"em curso. Registre a pasta com `caso_raiz.py registrar --raiz \"<pasta do caso>\" "
            f"--session-id <id da sessão>` e abra o Conselho com o mesmo `--session-id`, ou "
            f"aponte o registro com DSR_PROV_LEDGER=\"<pasta do caso>/{NOME_LEDGER}\".")
    return None


def _reverificar_conselho(cs_path, peca_risco, transcritos=None, session_id=None):
    'Anti-autocertificação: RE-INVOCA conselho_gate.py sobre o CONSELHO_STATUS.json apontado.'




    if not _full_str(cs_path):
        return (False, "", ["conselho: caminho do CONSELHO_STATUS.json ausente (fase conselho sem artefato)"])
    cs_path, recusa = _status_do_conselho(cs_path.strip(), _str_ou_vazio(session_id) or None)
    if recusa:
        return (False, "", [recusa])
    if not os.path.exists(cs_path):
        return (False, "", [f"conselho: CONSELHO_STATUS.json não encontrado: {cs_path}"])
    try:
        raw = open(cs_path, encoding="utf-8").read()


        try:
            _cs = json.loads(raw)
            sessao_do_status = _cs.get("session_id") if isinstance(_cs, dict) else None
        except Exception:
            _cs, sessao_do_status = None, None


        if isinstance(_cs, dict) and _cs.get("fase") == "devolvido":
            placar = ((_cs.get("relator") or {}).get("placar") if isinstance(_cs.get("relator"), dict) else None)
            return (False, "", [f"o Conselho DEVOLVEU a peça{f' (placar {placar})' if placar else ''}: "
                                f"corrija os achados do acórdão e abra novo ciclo — `estado_peca.py reabrir "
                                f"--fase <fase a corrigir> --motivo \"<o que o Conselho apontou>\"` e "
                                f"`conselho_sessao.py novo-ciclo`"])
        cmd = [sys.executable, GATE_CONSELHO, cs_path]





        if peca_risco == "alto":




            ledger = os.environ.get("DSR_PROV_LEDGER")
            if _full_str(ledger):
                cmd += ["--proveniencia", ledger.strip()]
            else:
                sessao = (_str_ou_vazio(sessao_do_status) or _str_ou_vazio(session_id)
                          or None)
                recusa = _ledger_do_caso(sessao)
                if recusa:
                    return (False, "", [recusa])
                cmd += ["--proveniencia", NOME_LEDGER]
                if sessao:
                    cmd += ["--session-id", sessao]





            _transc = _str_ou_vazio(transcritos) or os.environ.get("DSR_TRANSCRIPTS_DIR", "")
            if _full_str(_transc):
                cmd += ["--transcritos", _transc.strip()]


            cmd += ["--painel"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        o = json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception as e:
        return (False, "", [f"conselho: falha ao reverificar via conselho_gate.py: {e}"])
    liberado = (r.returncode == 0 and o.get("liberado") is True
                and o.get("resultado") in ("aprovado", "liberado_optin"))
    if not liberado:
        gate_motivos = o.get("motivos") if isinstance(o.get("motivos"), list) else []
        detalhe = "; ".join(str(m) for m in gate_motivos if str(m).strip())
        return (False, "", [f"conselho NÃO liberou (resultado={o.get('resultado')}, exit={r.returncode}) "
                            f"— re-verificado pelo conselho_gate, 'concluida' no JSON não basta"
                            + (f". Motivos: {detalhe}" if detalhe else "")])


    try:
        cs_risco = json.loads(raw).get("risco")
    except Exception:
        cs_risco = None
    if cs_risco != peca_risco:
        return (False, "", [f"conselho: risco do CONSELHO_STATUS ({cs_risco}) diverge do risco da peça "
                            f"({peca_risco}) — peça {peca_risco} não se libera por conselho {cs_risco}"])
    return (True, o.get("acordao", ""), [])


_REMEDIO_PECA = ("Registre o .docx de trabalho com `estado_peca.py canonico --arquivo "
                 "\"<caminho do .docx>\"` ou passe `--docx \"<caminho do .docx>\"` ao "
                 "`pode-entregar`, e reexecute o `pode-entregar`.")


def _peca_do_estado(st):
    'A peça sobre a qual o `pode-entregar` sem `--docx` reexecuta o linter.'






    canon = st.get("arquivo_canonico")
    if _full_str(canon):
        origem, cand = "`arquivo_canonico`", canon.strip()
    else:
        reg = st["fases"].get("visual_law")
        art = reg.get("artefato") if isinstance(reg, dict) else None
        if not _full_str(art):
            return None, ("LINT FAIL-CLOSED: o PECA_STATE não aponta a peça (sem "
                          "`arquivo_canonico` e sem artefato na fase `visual_law`), e sem ela o "
                          "linter não é reexecutado. " + _REMEDIO_PECA)
        origem, cand = "artefato da fase `visual_law`", art.strip()
    cand = os.path.expanduser(cand)
    if not os.path.isabs(cand):
        forma = "veio com caminho relativo" if os.path.dirname(cand) else "veio sem pasta"
        sessao = _str_ou_vazio(st.get("session_id")) or None
        try:
            import conselho_gate
        except Exception as e:
            return None, (f"LINT FAIL-CLOSED: a peça «{cand}» ({origem}) {forma}, e o "
                          f"conselho_gate.py, que localiza a pasta do caso, não carregou ({e}). "
                          + _REMEDIO_PECA)
        try:
            if os.path.dirname(cand):
                raiz, _origem = conselho_gate.pasta_do_caso(sessao)
                if raiz is None:
                    raise conselho_gate.CaminhoRecusado("caso_nao_resolvido", "")
                cand = os.path.join(raiz, cand)
            else:
                cand = conselho_gate.no_caso(cand, sessao)
        except conselho_gate.CaminhoRecusado as e:
            if e.resultado != "caso_nao_resolvido":
                return None, f"LINT FAIL-CLOSED ({e.resultado}): {e} " + _REMEDIO_PECA
            return None, (f"LINT FAIL-CLOSED (caso_nao_resolvido): a peça «{cand}» ({origem}) "
                          f"{forma}, e a pasta do caso desta sessão não foi identificada. "
                          f"A pasta corrente e o último caso registrado não identificam o caso "
                          f"em curso. " + _REMEDIO_PECA)
    cand = os.path.abspath(cand)
    if not os.path.isfile(cand):
        return None, (f"LINT FAIL-CLOSED: a peça que o PECA_STATE aponta ({origem}) não foi "
                      f"encontrada em {cand}, e sem ela o linter não é reexecutado. "
                      + _REMEDIO_PECA)
    return cand, None














_SIGLAS_CLASSE = (r"R[Ee][Ss][Pp]|AR[Ee][Ss][Pp]|ER[Ee][Ss][Pp]|RE|ARE|RMS|RHC|HC|MS|AI|Ag[Ii][Nn][Tt]|"
                  r"Ag[Rr][Gg]|AgR|ED[Cc][Ll]|ED|ADI|ADC|ADPF|ADO|Rcl|RO|ROT|RR|AIRR|ARR|AIRO|RORSum|"
                  r"IRDR|IAC|Pet|Ap\.\s*C[íi]v(?:el)?\.?|Ap\.\s*Crim\.?")

_NUM_SINAL = r"(?:[Nn]\.?\s*[º°o]\.?)"
_CLASSE_NUM_RX = re.compile(
    rf"(?<![\w/])(?:{_SIGLAS_CLASSE})(?![\w])\s*(?:-|\.|{_NUM_SINAL})?\s*(\d[\d.\-/]*\d)")
_CEP_RX = re.compile(r"^\d{2}\.?\d{3}-?\d{3}$")
_EXTENSO_RX = re.compile(
    r"\b(?:Recurso\s+(?:Especial|Extraordin[áa]rio|Ordin[áa]rio|de\s+Revista)|Agravo\s+(?:de\s+"
    r"Instrumento|Interno|Regimental|em\s+Recurso)|Embargos\s+de\s+(?:Declara[çc][ãa]o|Diverg[êe]ncia)"
    r"|Habeas\s+Corpus|Mandado\s+de\s+Seguran[çc]a|Apela[çc][ãa]o(?:\s+C[íi]vel|\s+Criminal)?"
    r"|Conflito\s+de\s+Compet[êe]ncia|A[çc][ãa]o\s+Direta\s+de\s+Inconstitucionalidade"
    r"|Reclama[çc][ãa]o)\s*(?:n\.?\s*[º°o]\.?\s*)?(\d[\d.\-/]*\d)", re.I)
_SUM_TEMA_RX = re.compile(r"\b(?:S[úu]mula|Tema|OJ|Orienta[çc][ãa]o\s+Jurisprudencial|Precedente\s+"
                          r"Normativo|Informativo)\s+(?:Vinculante\s+)?(?:n\.?\s*[º°o]\.?\s*)?\d", re.I)
_TRIB_RX = re.compile(r"\b(?:STF|STJ|TST|TSE|STM|TNU|TRF\d?|TRT\d{0,2}|TJ[A-Z]{2})\b")
_IND_JULGAMENTO_RX = re.compile(r"\bRel\.|\brelatora?\b|\bj\.\s*\d|julgad[oa]\s+em|\bDJe?\b"
                                r"|\bInformativo\s+\d", re.I)


_DOC_HINT_RE = re.compile(r"\bDoc\.\s*\d+|\bDoc\b\s*\d+", re.IGNORECASE)





_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TEXTO_DO_RUN = {_W + "tab": "\t", _W + "ptab": "\t", _W + "cr": "\n", _W + "noBreakHyphen": "-"}


def _texto_run(r):
    partes = []
    for e in r:
        if e.tag == _W + "t":
            partes.append(e.text or "")
        elif e.tag == _W + "br":
            partes.append("\n" if e.get(_W + "type", "textWrapping") == "textWrapping" else "")
        else:
            partes.append(_TEXTO_DO_RUN.get(e.tag, ""))
    return "".join(partes)


def _texto_docx(docx_path, tabelas=False):
    'Texto dos parágrafos não vazios do .docx, ou "" se não houver o que ler. Com `tabelas`,'

    if not docx_path or not os.path.isfile(docx_path):
        return ""
    try:
        with zipfile.ZipFile(docx_path) as z:
            corpo = ET.fromstring(z.read("word/document.xml")).find(_W + "body")
    except Exception:
        return ""
    if corpo is None:
        return ""
    textos = []
    for p in (corpo.iter(_W + "p") if tabelas else corpo.findall(_W + "p")):
        runs = []
        for filho in p:
            if filho.tag == _W + "r":
                runs.append(filho)
            elif filho.tag == _W + "hyperlink":
                runs.extend(filho.findall(_W + "r"))
        textos.append("".join(_texto_run(r) for r in runs).strip())
    return "\n".join(t for t in textos if t)


def _so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def _cita_julgado_no_texto(blob, processos=()):
    'Forma de citação de julgado no texto. Número do próprio caso (`processos` do'


    proprios = {d for d in (_so_digitos(p) for p in processos or ()) if d}

    def _numero_de_julgado(numero):
        return not _CEP_RX.match(numero) and _so_digitos(numero) not in proprios

    if any(_numero_de_julgado(m.group(1)) for m in _CLASSE_NUM_RX.finditer(blob)):
        return True
    if any(_numero_de_julgado(m.group(1)) for m in _EXTENSO_RX.finditer(blob)):
        return True
    if _SUM_TEMA_RX.search(blob):
        return True


    return any(_TRIB_RX.search(p) and _IND_JULGAMENTO_RX.search(p) for p in blob.split("\n"))


def _peca_cita_julgado(docx_path, processos=()):
    'Se a peça cita julgado, o `achados.json` é OBRIGATÓRIO no `pode-entregar` (como no L11).'







    if "JURISPRUDÊNCIA" in _texto_docx(docx_path, tabelas=True).upper():
        return True
    blob = _texto_docx(docx_path)
    return bool(blob) and _cita_julgado_no_texto(blob, processos)




MARCA_RELACAO = "relacao-precedentes:sha256="


def _origem_da_relacao(docx_path):
    """Hash do `achados.json` carimbado na Relação, ou None se o .docx não é uma Relação."""
    try:
        with zipfile.ZipFile(docx_path) as z:
            xml = z.read("docProps/core.xml").decode("utf-8", "replace")
    except Exception:
        return None
    m = re.search(re.escape(MARCA_RELACAO) + r"([0-9a-f]{64})", xml)
    return m.group(1) if m else None


def _conferir_relacao(st, achados_path):
    'Motivos de bloqueio quando a peça cita julgado e a Relação de Precedentes não sai junto,'


    h = _sha256(achados_path)
    origens = [_origem_da_relacao(a["arquivo"]) for a in _anexos(st)
               if str(a.get("arquivo", "")).lower().endswith(".docx") and os.path.isfile(a["arquivo"])]
    origens = [o for o in origens if o]
    comando = (f"gere-a com `build_precedentes.py \"{achados_path}\" -o \"Relação de Precedentes — "
               f"<caso>.docx\" --caso \"<caso>\"` (skill dissero-visual-law) e registre-a com "
               f"`estado_peca.py anexo --arquivo \"<a Relação>\"`")
    if not origens:
        return [f"RELAÇÃO DE PRECEDENTES AUSENTE: a peça cita julgado e a Relação de Precedentes "
                f"não está registrada para sair com ela. Ela acompanha a minuta sempre que houver "
                f"julgado citado: {comando}."]
    if h not in origens:
        return [f"RELAÇÃO DE PRECEDENTES DESATUALIZADA: a Relação registrada saiu de outra versão "
                f"do `achados.json` (algum julgado foi conferido, vetado ou alterado depois). Gere "
                f"de novo sobre o de agora: {comando}."]
    return []


def _peca_cita_doc(docx_path):
    'Se a peça cita (Doc. NN), o `JUNTADA_TRACKER.json` é OBRIGATÓRIO (como no L13). Folha'

    blob = _texto_docx(docx_path)
    return bool(blob) and _DOC_HINT_RE.search(blob) is not None


def _ledger_declara_conferencia(jnt_path):
    'True quando o ledger da juntada aponta o próprio dataset da conferência (campo'

    try:
        with open(jnt_path, encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        return False
    return isinstance(dados, dict) and bool(str(dados.get("conferencia") or "").strip())


_PREFIXOS_DO_LINTER = ("ERRO:", "REPROVADO:", "PENDENTE:")


def _apontado_pelo_linter(saida, limite=3):
    'As primeiras linhas de erro/pendência da saída do lint_peca.py, com o remédio que cada'

    linhas = [l.strip() for l in (saida or "").splitlines()
              if l.strip().startswith(_PREFIXOS_DO_LINTER)]
    if not linhas:
        return ""
    texto = " | ".join(l if len(l) <= 400 else l[:397] + "..." for l in linhas[:limite])
    if len(linhas) > limite:
        texto += f" | (+{len(linhas) - limite} na saída do linter)"
    return texto


def _reverificar_lint(st, args, docx_path, ev, motivos, avisos_entrega):
    'Reexecuta o lint_peca.py sobre `docx_path` e acrescenta a `motivos` o que bloqueia.'







    if not os.path.exists(LINT_PECA):
        motivos.append(f"LINT FAIL-CLOSED: lint_peca.py não encontrado ({LINT_PECA}) para "
                       f"reexecutar o linter sobre a peça")
        return
    prec_arg, jnt_arg, conf_arg = args.precedentes, args.juntada, args.conferencia


    if caso_raiz is not None and (not prec_arg or not jnt_arg or not conf_arg):
        try:
            raiz_st, _ = caso_raiz.resolver(session_id=st.get("session_id"))
        except Exception:
            raiz_st = None
        if raiz_st and not prec_arg:
            cand = os.path.join(raiz_st, "achados.json")
            if os.path.isfile(cand):
                prec_arg = cand
        if raiz_st and not jnt_arg:
            cand = os.path.join(raiz_st, "JUNTADA_TRACKER.json")
            if os.path.isfile(cand):
                jnt_arg = cand


        if raiz_st and not conf_arg and not (jnt_arg and _ledger_declara_conferencia(jnt_arg)):
            cand = os.path.join(raiz_st, "CONFERENCIA.json")
            if os.path.isfile(cand):
                conf_arg = cand

    cita_julgado = _peca_cita_julgado(docx_path, st.get("processos") or ())
    cita_doc = _peca_cita_doc(docx_path)


    if cita_julgado and not prec_arg:
        motivos.append(
            "LINT FAIL-CLOSED: peça cita julgado e o `achados.json` NÃO foi "
            "localizado — nem via CLI (`--precedentes`), nem auto-localizado na raiz "
            "do caso. Sem ele o linter reprova a Relação de Precedentes, e a evidência "
            "autodeclarada não substitui a reverificação: a entrega não pode ser "
            "liberada. Localize o `achados.json` na raiz do caso (ou passe via CLI) e "
            "reexecute `pode-entregar`.")
    if cita_julgado and prec_arg:
        motivos.extend(_conferir_relacao(st, prec_arg))
    if cita_doc and not jnt_arg:
        motivos.append(
            "LINT FAIL-CLOSED: peça cita (Doc. NN) e o "
            "`JUNTADA_TRACKER.json` NÃO foi localizado — nem via CLI (`--juntada`), "
            "nem auto-localizado na raiz do caso. O linter REPROVA sem o ledger "
            "(L13 FAIL-CLOSED). A entrega não pode ser liberada sem o ledger curado.")
    cmd = [sys.executable, LINT_PECA, docx_path]
    cruzamento = (("--precedentes", prec_arg), ("--juntada", jnt_arg),
                  ("--conferencia", conf_arg))
    for flag, valor in cruzamento:
        if valor:
            if not os.path.exists(valor):
                motivos.append(f"LINT: artefato de cruzamento não encontrado ({flag} {valor})")
            else:
                cmd += [flag, valor]



    grau_st = args.grau or st.get("grau_jurisdicao")
    if grau_st:
        cmd += ["--grau", str(grau_st)]
    else:
        avisos_entrega.append(
            "LINT: grau de jurisdição não consta do PECA_STATE — o L20 (formas de "
            "tratamento por instância) roda por inferência da capa, ou não roda. "
            "Derive-o da classe processual no briefing (`grau_jurisdicao.derivar`) e "
            "grave-o no estado")
    for numero in (st.get("processos") or []):
        if isinstance(numero, str) and numero.strip():
            cmd += ["--processo", numero.strip()]
    teto = args.lint_timeout if args.lint_timeout is not None else LINT_TIMEOUT_S
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           timeout=teto)
    except subprocess.TimeoutExpired:
        motivos.append(f"LINT FAIL-CLOSED: o linter não terminou em {teto:g} s sobre "
                       f"{docx_path}, e a entrega não é liberada sem a reexecução. Rode "
                       f"`lint_peca.py` sobre a peça para ver onde ele para e reexecute o "
                       f"`pode-entregar`.")
        return
    except Exception as e:
        motivos.append(f"LINT FAIL-CLOSED: o linter não pôde ser executado sobre {docx_path} "
                       f"({e}), e a entrega não é liberada sem a reexecução.")
        return
    if r.returncode != 0:
        cruz = " ".join(f"{f} {v}" for f, v in cruzamento if v) or "sem cruzamento"
        apontado = _apontado_pelo_linter(r.stdout)
        motivos.append(f"LINT reprovado na reverificação da peça {docx_path} "
                       f"(exit={r.returncode}; {cruz}). "
                       + (f"O linter apontou: {apontado}. Siga o remédio de cada linha e "
                          f"reexecute o `pode-entregar`." if apontado else
                          f"Rode `lint_peca.py` sobre ela com os mesmos argumentos para ver "
                          f"os erros."))


    if ev.get("exit_code") != r.returncode:
        motivos.append(
            f"LINT PROVA CRUZADA: a evidência registrada declara exit_code="
            f"{ev.get('exit_code')}, mas a reexecução devolveu exit_code="
            f"{r.returncode}. A evidência só vale se casar com a reexecução. "
            f"Reprocesse a fase `lint` com `estado_peca.py avancar "
            f"--fase lint --artefato \"{docx_path}\" --evidencia '{{\"exit_code\":"
            f"{r.returncode}, \"aprovado\":{str(r.returncode == 0).lower()}}}'`.")


def _montar_acordao(st, conselho_acordao, args=None):
    prazo_ev = st["fases"].get("prazo", {}).get("evidencia", {}) or {}
    partes = [f"Peça '{st['peca']}' (risco {st['risco']}, modo {st['modo_execucao']}) LIBERADA para entrega."]
    if conselho_acordao:
        partes.append(f"Conselho: {conselho_acordao}")
    if isinstance(prazo_ev.get("data_alvo_D2"), str) and prazo_ev["data_alvo_D2"].strip():
        partes.append(f"Prazo-alvo (D-2): {prazo_ev['data_alvo_D2']}.")
    if (st["fases"].get("verificacao", {}).get("evidencia") or {}).get("sem_jurisprudencia") is True:
        partes.append("VERIFICAÇÃO: peça sem julgado citado — ausência DECLARADA "
                      "(`sem_jurisprudencia`), não verificação omitida.")
    if st["fases"].get("visual_law", {}).get("entrega_por_download") is True:
        partes.append("ENTREGA POR DOWNLOAD (ambiente efêmero): o .docx NÃO está em pasta durável "
                      "— confirme o download antes de encerrar a sessão, ou a peça se perde.")

    for _r in (st.get("reinicios") if isinstance(st.get("reinicios"), list) else []):
        if isinstance(_r, dict):
            partes.append(f"RECOMEÇO DO RITO em {_r.get('em', '?')}: {_r.get('motivo', 'sem motivo')} "
                          f"(estado anterior arquivado, com {len(_r.get('fases_concluidas_anteriores') or [])} "
                          f"fase(s) concluída(s), ciclo {_r.get('ciclo_anterior', '?')}).")

    partes.extend(_avisos_de_dispensa(st, args))

    _sp = getattr(args, "state", None)
    if _full_str(_sp):
        for _F, _a in _aprovacoes(st, _sp).items():
            partes.append(_frase_aprovacao(_F, _a).replace("Aprovação do advogado",
                                                           "APROVAÇÃO DO ADVOGADO", 1))



    _adv = st["fases"].get("adversarial")
    _adv = _adv if isinstance(_adv, dict) else {}
    _adv_ev = _adv.get("evidencia") if isinstance(_adv.get("evidencia"), dict) else {}
    if _adv.get("status") == "concluida":





        _atk = _id(_adv_ev.get("autor_id"))
        _est_a = st["fases"].get("estrategia")
        _est_a = _est_a if isinstance(_est_a, dict) else {}
        _est_ev_a = _est_a.get("evidencia") if isinstance(_est_a.get("evidencia"), dict) else {}
        _aut = _id(_est_ev_a.get("autor_id"))
        if not _atk:
            partes.append("ETAPA ADVERSARIAL registrada SEM autor_id declarado: nao ha como "
                          "dizer que o ataque partiu de outro agente. Trate como nao atacada.")
        elif _aut and _atk == _aut:
            partes.append(f"ETAPA ADVERSARIAL registrada pelo MESMO autor_id da estrategia "
                          f"({_atk}): auto-ataque nao e ataque, e a tese NAO foi confrontada "
                          f"por outro agente.")
        elif not _aut:
            partes.append(f"ETAPA ADVERSARIAL cumprida: ataque registrado por autor_id={_atk} "
                          f"(declarado). A fase estrategia nao declarou autor_id, entao a "
                          f"distincao entre os dois NAO pode ser afirmada.")
        else:
            partes.append(f"ETAPA ADVERSARIAL cumprida: ataque registrado por autor_id={_atk} "
                          f"(declarado), distinto do autor_id da estrategia ({_aut}).")
    else:


        partes.append("ETAPA ADVERSARIAL nao exigida nesta peca (dispensada ou estado sem a "
                      "exigencia): a tese NAO passou por simulacao da contraparte. Para "
                      "exigi-la, nao dispense no `init` (`--sem-adversarial`) ou grave "
                      "exigir_adversarial:true no PECA_STATE.")


    _est_ver = st["fases"].get("verificacao")
    _est_ev = (_est_ver.get("evidencia") if isinstance(_est_ver, dict)
               and isinstance(_est_ver.get("evidencia"), dict) else {})
    _est_decl = _est_ev.get("trechos_lacrados")
    if _est_decl is None:
        partes.append("ESTANQUEIDADE nao declarada nesta peca: nao consta se o material "
                      "interno (painel do conselho, estado do squad, avaliacao de fragilidade) "
                      "foi separado do que vai aos autos. Para exigi-la, `init "
                      "--exigir-estanqueidade` (ou exigir_estanqueidade:true no PECA_STATE).")
    elif _est_decl:
        partes.append(f"ESTANQUEIDADE conferida e com {len(_est_decl)} trecho(s) LACRADO(S) "
                      f"declarado(s) - a entrega nao teria sido liberada com eles na peca.")
    else:
        partes.append("ESTANQUEIDADE conferida: nenhum trecho de procedencia lacrada na peca "
                      "(declaracao explicita, nao ausencia de declaracao).")

    _concluidas = sum(1 for f in ORDEM[:-1]
                      if (st["fases"].get(f) or {}).get("status") == "concluida")
    partes.append(f"{_concluidas} fases concluídas · LINT APROVADO · sem pendências de jurisprudência · is_minuta=false.")
    return " ".join(partes)


def _validar_lint_timeout(args):
    if args.lint_timeout is not None and not (math.isfinite(args.lint_timeout)
                                              and args.lint_timeout > 0):
        raise Contrato(["--lint-timeout: segundos, número finito maior que zero"])


def _conferir_entrega(st, args):
    'As conferências da porta de entrega, sem gravar nada: (motivos, avisos, acórdão do'


    motivos = []
    avisos_entrega = []




    exigidas = _fases_exigidas(st, args)


    if _exige_squad(st, args):
        _ok_squad, _motivo_squad = _leitura_pelo_squad(st)
        if not _ok_squad:
            motivos.append("squad: %s" % _motivo_squad)




    if _exige_estanqueidade(st, args):
        _ver = st["fases"].get("verificacao")
        _ver_ev = (_ver.get("evidencia") if isinstance(_ver, dict)
                   and isinstance(_ver.get("evidencia"), dict) else {})
        _lacr = _ver_ev.get("trechos_lacrados")
        if isinstance(_lacr, list) and _lacr:



            motivos.append(
                "estanqueidade: %d trecho(s) de procedencia LACRADA declarado(s) na evidencia "
                "da fase verificacao. Material interno nao vai aos autos, ainda que bem escrito "
                "- reescreva a partir de fonte aberta ou remova. A estanqueidade recusa e "
                "explica; nunca reescreve por conta propria" % len(_lacr))
        elif "trechos_lacrados" not in _ver_ev:
            motivos.append(
                "estanqueidade EXIGIDA nesta peca e NAO declarada: a evidencia da fase "
                "verificacao nao traz `trechos_lacrados`. Sem a chave, nao ha diferenca entre "
                "conferir e nao achar nada e nao ter conferido. Rode `estanqueidade.py` sobre "
                "os trechos com a procedencia declarada e registre o resultado - lista vazia e "
                "resposta valida")



    for p in ORDEM[:-1]:
        reg = st["fases"].get(p, {})
        if p not in exigidas:


            if reg.get("status") == "bloqueada":
                avisos_entrega.append(
                    f"fase OPCIONAL '{p}' registrada como BLOQUEADA e nao exigida nesta peca: a "
                    f"entrega segue liberada, mas o resultado dela ficou em aberto no PECA_STATE")
            continue
        if reg.get("status") != "concluida" or not _full_str(reg.get("artefato")):
            motivos.append(f"fase {p} não concluída / sem artefato")









    if caso_raiz is not None:
        amb = {"efemero": False}
        try:
            amb = caso_raiz.ambiente()
        except Exception:
            pass
        for p in ("visual_law",):
            reg_p = st["fases"].get(p, {})
            art = reg_p.get("artefato")
            try:
                efemero = caso_raiz.e_efemero(art)
            except Exception:
                efemero = False
            if not efemero:
                continue
            if amb.get("efemero"):
                if reg_p.get("entrega_por_download") is True:
                    continue
                motivos.append(
                    f"fase {p}: AMBIENTE EFÊMERO ({amb.get('motivo', 'sandbox de nuvem')}) — todo "
                    f"caminho aqui é apagado ao fim da sessão, inclusive {art}. Entregue o .docx "
                    f"por DOWNLOAD ao advogado e declare "
                    f"(`avancar --fase {p} --artefato <nome do arquivo> --entrega-por-download`). "
                    f"Se este ambiente for persistente, declare com DSR_AMBIENTE=duravel")
            else:
                motivos.append(
                    f"fase {p}: artefato em diretório TEMPORÁRIO ({art}) — o .docx da peça seria "
                    f"apagado com a sessão. Copie-o para a raiz do caso e reaponte o artefato "
                    f"(`avancar --fase {p} --artefato <caminho na pasta do caso>`)")




    estado_canon, detalhe_canon, _dados = conferir_canonico(st)
    if estado_canon in ("divergente", "ausente"):
        motivos.append(f"ARQUIVO CANÔNICO: {detalhe_canon}")
    elif estado_canon == "nao_registrado":


        avisos_entrega.append(
            "ARQUIVO CANÔNICO não registrado — este gate não pode conferir que a peça "
            "entregue é a mesma que o linter aprovou. Registre com `estado_peca.py canonico "
            "--arquivo <caminho do .docx>`")




    marcados = []
    for cand in (getattr(args, "docx", None), (_dados or {}).get("arquivo_canonico")):
        if cand and cand not in marcados and os.path.isfile(cand) and _sinal_de_pendencias(cand):
            marcados.append(cand)
    if marcados:
        motivos.append(
            "MINUTA COM PENDÊNCIAS: a peça (%s) foi gerada com a marca de minuta com pendências e "
            "nunca sai como peça liberada. Para a entrega normal, gere o documento de novo sem "
            "--minuta-pendencias, passe-o pelo rito e registre-o com `estado_peca.py canonico`"
            % ", ".join(os.path.basename(c) for c in marcados))


    if st["pendencias_jurisprudencia"]:
        motivos.append(f"pendências de jurisprudência em aberto: {len(st['pendencias_jurisprudencia'])}")











    if st["modo_execucao"] == "chat":
        motivos.append("modo chat: sem a ferramenta de subagente do ambiente não há assentos "
                       "dedicados — o Conselho não delibera validamente e a peça sai como "
                       "MINUTA, entrega não liberada (o linter roda nesse modo; o que falta são "
                       "os assentos)")
    else:
        ev_lint = st["fases"].get("lint", {}).get("evidencia", {}) or {}
        if not _is_int(ev_lint.get("exit_code")):
            motivos.append(
                "LINT FAIL-CLOSED: a evidência registrada da fase `lint` não traz exit_code "
                "(inteiro) do lint_peca.py. Sem o resultado registrado não há o que cruzar com "
                "a reexecução do linter, e nenhuma outra anotação da evidência o substitui. "
                "Rode `lint_peca.py` sobre a peça, registre o resultado com `estado_peca.py "
                "avancar --fase lint --artefato \"<caminho do .docx>\" --evidencia "
                "'{\"exit_code\": <exit do linter>, \"aprovado\": <true|false>}'` e "
                "reexecute o `pode-entregar`.")
        else:
            docx_alvo, recusa = ((args.docx, None) if args.docx else _peca_do_estado(st))
            if recusa:
                motivos.append(recusa)
            else:
                _reverificar_lint(st, args, docx_alvo, ev_lint, motivos, avisos_entrega)

                avisos_entrega += _coerencia_pedidos(st, _texto_da_peca(docx_alvo))[1]


    cs_path = args.conselho_status or st["fases"].get("conselho", {}).get("artefato")
    conselho_ok, conselho_acordao, conselho_motivos = _reverificar_conselho(
        cs_path, st["risco"], _str_ou_vazio(getattr(args, "transcritos", None)),
        session_id=st.get("session_id"))
    motivos += conselho_motivos
    motivos += _versao_julgada(st, cs_path, (_dados or {}).get("arquivo_canonico"))

    return motivos, avisos_entrega, conselho_acordao


def _versao_julgada(st, cs_path, canonico):
    'E2: o lint e os votos do Conselho gravam o hash do .docx julgado. O gate do Conselho só'



    if not _full_str(cs_path):
        return []
    caminho, recusa = _status_do_conselho(cs_path.strip(), _str_ou_vazio(st.get("session_id")) or None)
    if recusa or not os.path.isfile(caminho):
        return []
    try:
        with open(caminho, encoding="utf-8") as fh:
            cs = json.load(fh)
        julgado = cs["lint"].get("docx_sha256")
    except Exception:
        return []
    if not _full_str(julgado):
        return []
    if _full_str(st.get("hash_canonico")):
        peca_hash, peca = st["hash_canonico"], canonico or st.get("arquivo_canonico")
    else:
        alvo, falta = _peca_do_estado(st)
        if falta or not alvo or not os.path.isfile(alvo):
            return []
        peca_hash, peca = _sha256(alvo), alvo
    if peca_hash == julgado:
        return []
    return [f"o Conselho julgou outra versão da peça: o lint e os votos são de "
            f"«{cs['lint'].get('docx') or 'outro arquivo'}», e a peça registrada para entrega "
            f"(«{peca}») tem outro conteúdo. Submeta a versão atual à turma "
            f"(`conselho_sessao.py novo-ciclo`, depois `lint` e os votos) antes de entregar"]









PROP_MINUTA_PENDENCIAS = "DSRMinutaPendencias"
BUILD_DOCX = os.path.join(AQUI, "..", "..", "dissero-visual-law", "scripts", "build_docx.py")
ORDEM_MIN_CHARS = 8

TERCEIRA_VIA_O_QUE = (
    "Primeiro proponha cumprir as pendências; é o recomendado antes da entrega. Se o advogado "
    "ordenar, nas palavras dele, o documento pode sair agora como MINUTA COM PENDÊNCIAS: leva a "
    "marca permanente de minuta, os trechos em aberto ficam realçados, a lista do que falta "
    "acompanha a entrega e a revisão fica sob a responsabilidade dele. Também pode não gerar "
    "nada agora. A escolha é dele.")


def _entrega_do_caso(state):
    'A pasta `entrega` dentro do caso do PECA_STATE: o destino da minuta com pendências (R2).'

    gate = _gate_entrega()
    casa = (_pasta_do_caso(gate, state) if gate is not None
            else os.path.dirname(os.path.abspath(state)))
    return os.path.join(casa, "entrega")


def _comando_terceira_via(state):
    return (f'python "{os.path.abspath(os.path.join(AQUI, "estado_peca.py"))}" entregar '
            f'--state "{os.path.abspath(state)}" --destino "{_entrega_do_caso(state)}" '
            f'--minuta-com-pendencias --ordem-do-advogado "<palavras literais do advogado>"')


def _terceira_via(state):
    """Campo aditivo das saídas bloqueadas: a oferta, para o modelo apresentar ao advogado."""
    return {"o_que": TERCEIRA_VIA_O_QUE, "como": _comando_terceira_via(state)}





FAIXA_MINUTA_PENDENCIAS = (
    "MINUTA COM PENDÊNCIAS. Documento gerado por ordem do advogado antes da conclusão da revisão. "
    "Os trechos realçados dependem de conferência e não devem ser protocolados como estão.")


def _so_espaco(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def _partes_do_docx(caminho):
    """(custom.xml, document.xml) do pacote, cada um bytes ou None; None se o zip é ilegível."""
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = set(z.namelist())
            return tuple(z.read(n) if n in nomes else None
                         for n in ("docProps/custom.xml", "word/document.xml"))
    except Exception:
        return None


def _tem_carimbo(custom):
    'O carimbo DSRMinutaPendencias com valor exatamente "1" (a leitura da varredura e do'

    if not custom:
        return False
    try:
        raiz = ET.fromstring(custom)
    except Exception:
        return False
    for prop in raiz.iter():
        if prop.tag.rsplit("}", 1)[-1] != "property" or prop.get("name") != PROP_MINUTA_PENDENCIAS:
            continue
        for valor in prop:
            if (valor.text or "").strip() == "1":
                return True
    return False


def _tem_faixa(documento):
    'A faixa constante, inteira, num parágrafo (w:p) do corpo. Os runs do parágrafo se juntam'

    if not documento:
        return False
    try:
        raiz = ET.fromstring(documento)
    except Exception:
        return False
    alvo = _so_espaco(FAIXA_MINUTA_PENDENCIAS)
    for par in raiz.iter():
        if par.tag.rsplit("}", 1)[-1] != "p":
            continue
        texto = "".join(t.text or "" for t in par.iter() if t.tag.rsplit("}", 1)[-1] == "t")
        if alvo in _so_espaco(texto):
            return True
    return False


def _local(el):
    return el.tag.rsplit("}", 1)[-1]


def _texto_de(el):
    return "".join(t.text or "" for t in el.iter() if _local(t) == "t")




_TETO_LINHAS_DA_CAPA = 12


def _fecha_a_capa(el):
    """O espaçador que fecha a capa: parágrafo vazio com a marca de corpo 20 (só a capa usa)."""
    if _local(el) != "p" or _so_espaco(_texto_de(el)):
        return False
    return any(_local(sz) == "sz" and any(k.rsplit("}", 1)[-1] == "val" and v == "20"
                                          for k, v in sz.attrib.items())
               for sz in el.iter())


def _faixa_abre_o_corpo(documento):
    'A faixa é o 1º elemento do corpo, ou o 1º depois da capa. O gerador a põe no topo (sem'




    if not documento:
        return False
    try:
        raiz = ET.fromstring(documento)
    except Exception:
        return False
    corpo = next((el for el in raiz.iter() if _local(el) == "body"), None)
    if corpo is None:
        return False
    alvo = _so_espaco(FAIXA_MINUTA_PENDENCIAS)
    filhos = list(corpo)
    for i, el in enumerate(filhos):
        if _local(el) not in ("p", "tbl"):
            return False
        pars = [el] if _local(el) == "p" else [p for p in el.iter() if _local(p) == "p"]
        if not any(alvo in _so_espaco(_texto_de(p)) for p in pars):
            continue
        antes = filhos[:i]
        com_texto = [a for a in antes if _so_espaco(_texto_de(a))]
        if not com_texto:
            return True
        return len(com_texto) <= _TETO_LINHAS_DA_CAPA and _fecha_a_capa(antes[-1])
    return False


def tem_marca_de_pendencias(caminho):
    'True quando o .docx traz o carimbo DSRMinutaPendencias="1" em docProps/custom.xml E a'




    partes = _partes_do_docx(caminho)
    return bool(partes) and _tem_carimbo(partes[0]) and _faixa_abre_o_corpo(partes[1])


def _sinal_de_pendencias(caminho):
    'True quando o .docx traz o carimbo OU a faixa. Para a peça nunca sair LIBERADA basta um'

    partes = _partes_do_docx(caminho)
    return bool(partes) and (_tem_carimbo(partes[0]) or _tem_faixa(partes[1]))


_VOCABULARIO_CARREGADO = []


def _vocabulario_interno():
    """O vocabulario_interno.py ao lado deste script, como módulo, ou None se não carrega."""
    if _VOCABULARIO_CARREGADO:
        return _VOCABULARIO_CARREGADO[0]
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_dsr_vocabulario_interno", os.path.join(AQUI, "vocabulario_interno.py"))
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        if not callable(getattr(modulo, "residuos", None)):
            modulo = None
    except Exception:
        modulo = None
    _VOCABULARIO_CARREGADO.append(modulo)
    return modulo



_PARTES_DE_TEXTO = ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml")


def residuos_no_docx(caminho, vocabulario):
    'Os termos do vocabulário interno no texto do .docx (corpo e notas), parágrafo a'

    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = set(z.namelist())
            xmls = [z.read(n) for n in _PARTES_DE_TEXTO if n in nomes]
    except Exception:
        return None
    achados, vistos = [], set()
    for xml in xmls:
        try:
            raiz = ET.fromstring(xml)
        except Exception:
            return None
        for par in raiz.iter():
            if _local(par) != "p":
                continue
            texto = _texto_de(par)
            for a in vocabulario.residuos(texto, contexto=_so_espaco(texto)[:120]):
                if a["termo"].lower() not in vistos:
                    vistos.add(a["termo"].lower())
                    achados.append(a)
    return achados


def _ordem_normalizada(texto):
    return " ".join(texto.split()) if isinstance(texto, str) else ""





_PENDENCIA_FASE = {
    "briefing": "O levantamento inicial dos fatos e dos pedidos não foi concluído.",
    "prazo": "O prazo não foi calculado e registrado.",
    "estrategia": "A estratégia da peça não foi aprovada pelo advogado.",
    "adversarial": "Os argumentos prováveis da parte contrária não foram simulados.",
    "mapa": "O roteiro da peça não foi aprovado pelo advogado.",
    "redacao": "A redação não foi registrada como concluída.",
    "verificacao": "A conferência das citações, dos fatos e dos precedentes não foi concluída.",
    "visual_law": "A formatação final no padrão do escritório não foi concluída.",
    "lint": "A revisão automática de forma e estilo não aprovou a peça.",
    "conselho": "A peça não foi revista nem aprovada pelo Conselho Revisor.",
}
_PENDENCIA_GENERICA = "Há conferência do rito de revisão ainda não concluída."


def _pendencia_do_motivo(motivo):
    'A frase ao advogado para um motivo de bloqueio, ou None para o que não é pendência da'

    m = str(motivo)
    baixo = m.lower()
    if m.startswith("MINUTA COM PENDÊNCIAS:"):
        return None
    if m.startswith("squad:"):
        return "A leitura dos autos pela equipe de conferência não foi concluída."
    if baixo.startswith("estanqueidade"):
        if "lacrada" in baixo:
            return "Há trecho de origem interna sigilosa que não pode ir aos autos."
        return "Não foi declarada a conferência de que nenhum trecho vem de material interno sigiloso."
    achado = re.match(r"fase (\w+) não concluída / sem artefato$", m)
    if achado:
        return _PENDENCIA_FASE.get(achado.group(1), _PENDENCIA_GENERICA)
    if m.startswith("fase visual_law:"):
        return "O arquivo da peça estava em pasta temporária, que é apagada ao fim da sessão."
    if m.startswith("ARQUIVO CANÔNICO:"):
        return "O arquivo da peça mudou depois da última conferência."
    achado = re.match(r"pendências de jurisprudência em aberto: (\d+)", m)
    if achado:
        n = int(achado.group(1))
        return ("Há %d precedente%s citado%s sem confirmação na fonte oficial."
                % (n, "s" if n != 1 else "", "s" if n != 1 else ""))
    if m.startswith("modo chat:"):
        return ("Neste ambiente o Conselho Revisor não pode deliberar, e a peça não passou pela "
                "revisão colegiada.")
    if "cita julgado" in baixo:
        return "Os precedentes citados não têm a relação de confirmação que os acompanha."
    if "cita (doc. nn)" in baixo:
        return "Os documentos citados não têm a relação de juntada conferida."
    if baixo.startswith("lint"):
        return _PENDENCIA_FASE["lint"]
    if "conselho devolveu" in baixo:
        return "O Conselho Revisor devolveu a peça com pontos a corrigir."
    if baixo.startswith("conselho"):
        return _PENDENCIA_FASE["conselho"]
    return _PENDENCIA_GENERICA


def pendencias_do_advogado(motivos):
    """A lista de pendências em português de advogado, sem repetição, na ordem dos motivos."""
    saida = []
    for motivo in motivos:
        frase = _pendencia_do_motivo(motivo)
        if frase and frase not in saida:
            saida.append(frase)
    return saida


def _docx_do_caso(st, state_path):
    'O .docx que o artefato da fase visual_law aponta, se existir (relativo à pasta do'

    reg = st["fases"].get("visual_law")
    art = reg.get("artefato") if isinstance(reg, dict) else None
    if not _full_str(art) or not art.strip().lower().endswith(".docx"):
        return None
    cand = os.path.expanduser(art.strip())
    if not os.path.isabs(cand):
        cand = os.path.join(os.path.dirname(os.path.abspath(state_path)), cand)
    return os.path.abspath(cand) if os.path.isfile(cand) else None


def _registrar_liberacao(st, args, conselho_acordao):
    """Marca no estado (em memória) a fase `entrega` concluída e a peça fora de minuta."""
    st["fases"]["entrega"]["status"] = "concluida"
    st["fases"]["entrega"]["artefato"] = conselho_acordao or "acórdão do conselho"
    st["fases"]["entrega"]["evidencia"] = {"liberado": True}
    st["is_minuta"] = False
    st["fase_atual"] = "entrega"
    if args.ts:
        st["fases"]["entrega"]["concluida_em"] = args.ts
        st["atualizado"] = args.ts


def cmd_pode_entregar(args):
    _validar_lint_timeout(args)
    st = carregar(args.state)
    motivos, avisos_entrega, conselho_acordao = _conferir_entrega(st, args)
    if not motivos:
        _registrar_liberacao(st, args, conselho_acordao)
        _gravar(args.state, st)
        _emitir_trace(st.get("fase_atual"), "pode_entregar", {"resultado": "liberado", "strict": bool(args.strict)})
        return _saida("liberado", st, avisos_entrega, 0,
                      extra={"pode_entregar": True, "avisos": avisos_entrega,
                             "acordao": _montar_acordao(st, conselho_acordao, args)})

    resultado = "minuta_chat" if st["modo_execucao"] == "chat" else "bloqueado"
    exit_code = 0 if (getattr(args, "informativo", False) and not args.strict) else 1
    _emitir_trace(st.get("fase_atual"), "pode_entregar", {"resultado": resultado, "strict": bool(args.strict)})
    return _saida(resultado, st, motivos, exit_code,
                  extra={"pode_entregar": False, "avisos": avisos_entrega, "acordao": "",
                         "terceira_via": _terceira_via(args.state)})





GATE_ENTREGA = os.path.join(AQUI, "..", "..", "..", "hooks", "gate_entrega.py")
_GATE_CARREGADO = []


def _gate_entrega():
    'O hooks/gate_entrega.py como módulo, ou None se não carrega. O sys.path volta como'

    if _GATE_CARREGADO:
        return _GATE_CARREGADO[0]
    antes = list(sys.path)
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_dsr_gate_entrega", GATE_ENTREGA)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    except Exception:
        modulo = None
    finally:
        sys.path[:] = antes
    _GATE_CARREGADO.append(modulo)
    return modulo





SAIDAS_DA_CONVERSA = "/mnt/user-data/outputs"
_MONTAGENS_DO_CHAT = ("/mnt/user-data", "/mnt/skills")
_POSIX = os.name == "posix"


def _sessao_remota():
    f = getattr(caso_raiz, "superficie_remota", None) if caso_raiz is not None else None
    try:
        return bool(f()) if f else False
    except Exception:
        return False


def _saida_da_conversa(destino):
    'O destino é a pasta de saídas da sandbox do claude.ai (ou fica dentro dela)? Só num sistema'



    if not _POSIX:
        return False
    if not all(os.path.isdir(m) for m in _MONTAGENS_DO_CHAT) and not (
            _sessao_remota() and os.path.isdir(SAIDAS_DA_CONVERSA)):
        return False
    real = os.path.normcase(os.path.realpath(destino)).rstrip("\\/")
    base = os.path.normcase(os.path.realpath(SAIDAS_DA_CONVERSA)).rstrip("\\/")
    return real == base or real.startswith(base + os.sep)


def _pasta_do_caso(gate, state_path):
    """A raiz do caso do PECA_STATE, pelo caminho real; sem raiz, a pasta do PECA_STATE."""
    estado_abs = os.path.abspath(state_path)
    return (gate._raiz_do_caso(gate._real(estado_abs) or estado_abs)
            or gate._real(os.path.dirname(estado_abs)) or os.path.dirname(estado_abs))


def _destino_da_minuta_vale(gate, state_path, destino):
    'Na terceira via, o destino fica dentro da pasta do caso da peça, pelo caminho real, ou é'

    if _saida_da_conversa(destino):
        return True
    estado_abs = os.path.abspath(state_path)
    real_d = gate._real(destino) or destino
    if gate._raiz_do_caso(gate._real(estado_abs) or estado_abs):
        raiz_d = gate._raiz_do_caso(real_d)
        return bool(raiz_d) and gate._mesmo_caso(_pasta_do_caso(gate, state_path), raiz_d)
    casa = os.path.normcase(_pasta_do_caso(gate, state_path)).rstrip("\\/")
    alvo = os.path.normcase(real_d).rstrip("\\/")
    return alvo == casa or alvo.startswith(casa + os.sep)


def _raiz_de(gate, caminho):
    c = os.path.abspath(caminho)
    return gate._raiz_do_caso(gate._real(c) or c)


def _caso_alheio(gate, state_path, st, arquivo):
    'A raiz do caso do `arquivo` quando ele fica na árvore de um caso que não é o da peça (o do'


    raiz_a = _raiz_de(gate, arquivo)
    if not raiz_a:
        return None
    raiz_peca = _raiz_de(gate, state_path)
    canon = st.get("arquivo_canonico")
    if not raiz_peca and _full_str(canon):
        raiz_peca = _raiz_de(gate, canon.strip())
    if raiz_peca and gate._mesmo_caso(raiz_peca, raiz_a):
        return None
    return raiz_a


def _msg_anexo_outro_caso(arquivo, raiz, na_entrega=False):
    retirar = (f"Retire o registro com `estado_peca.py anexo --arquivo \"{arquivo}\" --remover`. "
               if na_entrega else "")
    return (f"O anexo {os.path.basename(arquivo)} fica na pasta de outro caso ({raiz}), e o documento "
            f"de um caso não sai com a peça de outro. {retirar}Registre como anexo só arquivo deste "
            f"caso. Se o advogado quer o documento nesta entrega, peça a ele que o salve na pasta "
            f"deste caso, e registre essa cópia com `estado_peca.py anexo --arquivo <arquivo>`.")


def _recusa_entrega(st, codigo, mensagem, motivos=None, exit_code=1, terceira_via=None):
    """Envelope da recusa do `entregar`: {ok:false, codigo, mensagem[, motivos][, terceira_via]}."""
    payload = {"ok": False, "codigo": codigo, "mensagem": mensagem}
    if motivos:
        payload["motivos"] = list(motivos)
    if terceira_via:
        payload["terceira_via"] = terceira_via
    _emitir_trace(st.get("fase_atual") if isinstance(st, dict) else None, "entregar",
                  {"resultado": codigo})
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def _agora():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _remover(caminho):
    try:
        if caminho and os.path.exists(caminho):
            os.remove(caminho)
    except OSError:
        pass


def _desfazer_troca(gravados, anteriores):
    'Desfaz a troca do `entregar`: tira do destino o que esta entrega gravou e devolve cada'


    for final_c in gravados:
        if final_c not in anteriores:
            _remover(final_c)
    presos = []
    for final_c, guarda in anteriores.items():
        try:
            os.replace(guarda, final_c)
        except OSError:
            presos.append((final_c, guarda))
    return presos


def _msg_desfeita(anteriores, presos):
    """A frase que diz como o destino ficou depois de desfeita a troca."""
    if presos:
        return " ".join(f"O arquivo que estava em {final_c} ficou em {guarda}. Feche o que prende "
                        f"{os.path.basename(final_c)} e dê ao arquivo provisório esse nome."
                        for final_c, guarda in presos) + " "
    if anteriores:
        return ("Nenhum arquivo desta entrega ficou na pasta, e os que já estavam lá continuam "
                "como antes. ")
    return "Nenhum arquivo desta entrega ficou na pasta. "


def cmd_entregar(args):
    'Entrega oficial: confere a peça canônica aprovada e a copia para `--destino`.'








    _validar_lint_timeout(args)
    via = bool(getattr(args, "minuta_com_pendencias", False))
    ordem_crua = getattr(args, "ordem_do_advogado", None)
    ordem = _ordem_normalizada(ordem_crua)
    if via and len(ordem) < ORDEM_MIN_CHARS:
        return _recusa_entrega(None, "contrato_invalido",
                               f"A minuta com pendências só sai por ordem do advogado: passe "
                               f"--ordem-do-advogado com as palavras dele, literais, tiradas da "
                               f"mensagem em que ele ordenou (pelo menos {ORDEM_MIN_CHARS} "
                               f"caracteres). Sem a ordem dele, ofereça a escolha e espere a "
                               f"resposta.", exit_code=2)
    if not via and ordem_crua is not None:
        return _recusa_entrega(None, "contrato_invalido",
                               "--ordem-do-advogado só vale com --minuta-com-pendencias.",
                               exit_code=2)
    st = carregar(args.state)
    if not _full_str(args.destino):
        return _recusa_entrega(st, "contrato_invalido",
                               "Falta a pasta de destino. Rode de novo com --destino <pasta>.",
                               exit_code=2)
    destino = os.path.abspath(os.path.expanduser(args.destino.strip()))
    criar_destino = False
    if not os.path.exists(destino):


        gate = _gate_entrega()
        if gate is not None and _destino_da_minuta_vale(gate, args.state, destino):
            if via:
                try:
                    os.makedirs(destino, exist_ok=True)
                except OSError:
                    pass
            else:



                criar_destino = True
    if not os.path.isdir(destino) and not criar_destino:
        return _recusa_entrega(st, "destino_inexistente",
                               f"A pasta de destino não existe: {destino}. Crie a pasta ou escolha "
                               f"uma que exista e rode a entrega de novo.")

    estado_canon, _detalhe, dados = conferir_canonico(st)
    canonico = dados.get("arquivo_canonico")
    if estado_canon == "nao_registrado":
        if via:


            ep = os.path.abspath(os.path.join(AQUI, "estado_peca.py"))
            achado = _docx_do_caso(st, args.state)
            gerar = ""
            if achado and tem_marca_de_pendencias(achado):
                alvo = achado
            else:
                pasta = (os.path.dirname(achado) if achado
                         else os.path.dirname(os.path.abspath(args.state)))
                base = (os.path.splitext(os.path.basename(achado))[0] if achado else "<peça>")


                alvo = os.path.join(pasta, f"{base} - com pendências.docx")
                gerar = (f'Gere o .docx com a marca: `python "{os.path.abspath(BUILD_DOCX)}" '
                         f'"<o .md da peça>" "{alvo}" --identidade --minuta-pendencias`. ')
            return _recusa_entrega(st, "canonico_ausente",
                                   f"O PECA_STATE não registra a peça canônica. {gerar}Registre o "
                                   f'documento com `python "{ep}" canonico --state '
                                   f'"{os.path.abspath(args.state)}" --arquivo "{alvo}"` e rode '
                                   f"de novo o mesmo `entregar --minuta-com-pendencias`.")
        return _recusa_entrega(st, "canonico_ausente",
                               "O PECA_STATE não registra a peça canônica. Registre a peça aprovada "
                               "com `estado_peca.py canonico --arquivo <peça>.docx` e rode a "
                               "entrega de novo.", terceira_via=_terceira_via(args.state))
    if estado_canon == "ausente":
        return _recusa_entrega(st, "canonico_ausente",
                               f"A peça canônica registrada não está em disco: {canonico}. "
                               f"Localize o arquivo e registre-o de novo com `estado_peca.py "
                               f"canonico --arquivo <peça>.docx`.")
    hash_canonico = dados.get("hash_registrado")
    if not _full_str(hash_canonico):
        return _recusa_entrega(st, "canonico_ausente",
                               f"A peça canônica ({canonico}) está registrada sem hash. Registre-a "
                               f"de novo com `estado_peca.py canonico --arquivo <peça>.docx`.")
    if estado_canon != "confere":
        return _recusa_entrega(st, "hash_divergente",
                               f"A peça canônica mudou depois de registrada ({canonico}). Pergunte "
                               f"ao advogado qual versão vale. A versão nova passa de novo pelo "
                               f"lint e pelo conselho e é registrada com `estado_peca.py canonico` "
                               f"antes da entrega.")
    if via and not tem_marca_de_pendencias(canonico):
        return _recusa_entrega(st, "sem_marca_de_pendencias",
                               f"A peça canônica ({canonico}) não traz a marca de MINUTA COM "
                               f"PENDÊNCIAS, e a minuta com pendências só sai marcada. Gere o "
                               f'documento com a marca (`python "{os.path.abspath(BUILD_DOCX)}" '
                               f'"<o .md da peça>" "<pasta do caso>/<peça> - com '
                               f'pendências.docx" --identidade --minuta-pendencias`), registre-o com '
                               f'`python "{os.path.abspath(os.path.join(AQUI, "estado_peca.py"))}" '
                               f'canonico --state "{os.path.abspath(args.state)}" --arquivo '
                               f'"<o .docx gerado>"` e rode de novo o mesmo `entregar '
                               f'--minuta-com-pendencias`. A faixa de minuta tem de abrir o '
                               f'corpo (logo depois da capa, se houver), como o gerador a põe.')
    if via:


        vocab = _vocabulario_interno()
        achados = residuos_no_docx(canonico, vocab) if vocab else None
        if achados is None:
            return _recusa_entrega(st, "conferencia_indisponivel",
                                   f"O detector de vocabulário interno do plugin "
                                   f"({os.path.join(AQUI, 'vocabulario_interno.py')}) não carregou "
                                   f"ou a peça canônica ({canonico}) não se lê, e sem ele a minuta "
                                   f"não é conferida. Atualize ou reinstale o plugin e rode a "
                                   f"entrega de novo.")
        if achados:
            termos = "; ".join(f"«{a['termo']}» ({a['classe']}) em «{a['contexto']}»"
                               for a in achados[:8])
            return _recusa_entrega(st, "vocabulario_interno_na_minuta",
                                   f"A peça canônica ({canonico}) traz vocabulário interno do "
                                   f"plugin no texto, e nada disso sai ao advogado, nem na minuta: "
                                   f"{termos}. Tire esses termos do texto (no .md da peça, ou no "
                                   f".docx dado pelo advogado, perguntando a ele se o termo é dele), "
                                   f"gere de novo o .docx com a marca, registre-o com "
                                   f"`estado_peca.py canonico` e rode de novo o mesmo `entregar "
                                   f"--minuta-com-pendencias`.",
                                   [a["termo"] for a in achados])

    gate = _gate_entrega()
    if gate is None:
        return _recusa_entrega(st, "conferencia_indisponivel",
                               f"A regra de pasta de caso do plugin ({GATE_ENTREGA}) não carregou, "
                               f"e sem ela o destino não é conferido. Atualize ou reinstale o "
                               f"plugin e rode a entrega de novo.")
    raiz_destino = gate._raiz_do_caso(gate._real(destino) or destino)
    if raiz_destino:
        estado_abs = os.path.abspath(args.state)
        raiz_peca = gate._raiz_do_caso(gate._real(estado_abs) or estado_abs)
        if not (raiz_peca and gate._mesmo_caso(raiz_peca, raiz_destino)):
            return _recusa_entrega(st, "destino_outro_caso",
                                   f"A pasta de destino fica no caso em {raiz_destino}, e a peça é "
                                   f"do caso em {raiz_peca or os.path.dirname(estado_abs)}. A peça "
                                   f"só é entregue no caso dela ou fora de qualquer caso (área de "
                                   f"trabalho, pendrive). Escolha outra pasta.")
    if via and not _destino_da_minuta_vale(gate, args.state, destino):



        casa = _pasta_do_caso(gate, args.state)
        sugerida = os.path.join(casa, "entrega")
        return _recusa_entrega(st, "destino_fora_do_caso",
                               f"A minuta com pendências é gravada só dentro da pasta do caso "
                               f"({casa}), e a pasta de destino ({destino}) fica fora dele. Rode "
                               f'de novo com --destino "{sugerida}" (a pasta é criada se não '
                               f"existir) e depois mande ao advogado o .docx entregue lá pelo envio "
                               f"de arquivo da conversa, ou copie-o para a pasta que ele pediu: "
                               f"nesse passo a ordem dele é conferida de novo. No Cowork remoto, se "
                               f"existir a pasta de saídas da conversa ({SAIDAS_DA_CONVERSA}), ela "
                               f"também vale.")



    anexos = []
    for a in _anexos(st):
        origem_a = a["arquivo"]
        if not os.path.isfile(origem_a):
            return _recusa_entrega(st, "anexo_ausente",
                                   f"O anexo registrado não está em disco: {origem_a}. Localize o "
                                   f"arquivo e registre-o de novo com `estado_peca.py anexo "
                                   f"--arquivo <arquivo>`, ou retire o registro com `estado_peca.py "
                                   f"anexo --arquivo <arquivo> --remover`, e rode a entrega de novo.")

        raiz_alheia = _caso_alheio(gate, args.state, st, origem_a)
        if raiz_alheia:
            return _recusa_entrega(st, "anexo_outro_caso",
                                   _msg_anexo_outro_caso(origem_a, raiz_alheia, na_entrega=True))
        if _sha256(origem_a) != a["sha256"]:
            return _recusa_entrega(st, "anexo_divergente",
                                   f"O anexo {os.path.basename(origem_a)} mudou depois de registrado "
                                   f"({origem_a}). Pergunte ao advogado se a versão nova vale. Se "
                                   f"vale, registre-a de novo com `estado_peca.py anexo --arquivo "
                                   f"<arquivo>` e rode a entrega de novo.")
        anexos.append((origem_a, a["sha256"]))
    copias = [(canonico, hash_canonico)] + anexos
    nomes = [os.path.basename(o).lower() for o, _h in copias]
    if len(set(nomes)) != len(nomes):
        repetido = next(n for n in nomes if nomes.count(n) > 1)
        return _recusa_entrega(st, "anexo_nome_repetido",
                               f"A peça e os anexos registrados têm dois arquivos com o nome "
                               f"{repetido}, e no destino um substituiria o outro. Renomeie o anexo "
                               f"e registre-o de novo com `estado_peca.py anexo --arquivo <arquivo>`.")

    finais = []
    for origem_c, _h in copias:
        nome_c = os.path.basename(origem_c)
        final_c = os.path.join(destino, nome_c)
        if os.path.exists(final_c):
            if os.path.normcase(os.path.realpath(final_c)) == os.path.normcase(os.path.realpath(origem_c)):
                return _recusa_entrega(st, "ja_existe",
                                       f"O destino é a pasta do próprio arquivo ({final_c}). "
                                       f"Escolha a pasta para onde a peça vai.")
            if os.path.isdir(final_c) or not args.substituir:
                return _recusa_entrega(st, "ja_existe",
                                       f"Já existe {nome_c} em {destino}. Para substituir o arquivo, "
                                       f"rode de novo com --substituir. Para manter os dois, escolha "
                                       f"outra pasta.")
        finais.append(final_c)
    final = finais[0]

    motivos, avisos, conselho_acordao = _conferir_entrega(st, args)
    pendencias = []
    if motivos and via:



        pendencias = pendencias_do_advogado(motivos) or [
            "Nenhuma pendência do rito foi apontada. O documento foi gerado com a marca de minuta "
            "e pode ser gerado de novo sem ela para a entrega normal."]
    elif motivos:
        return _recusa_entrega(st, "nao_liberado",
                               "A peça não está liberada para entrega. Resolva os motivos e rode a "
                               "entrega de novo.", motivos,
                               terceira_via=_terceira_via(args.state))
    docx_da_entrega = [o for o, _h in copias if o.lower().endswith(".docx")]
    oculto = gate._varredura_bloqueia({"tool_input": {}}, canonico, docx_da_entrega)
    if oculto:
        return _recusa_entrega(st, "varredura_reprovada", oculto)
    if criar_destino:
        try:
            os.makedirs(destino, exist_ok=True)
        except OSError:
            return _recusa_entrega(st, "destino_inexistente",
                                   f"A pasta de destino não existe e não pôde ser criada: {destino}. "
                                   f"Crie a pasta ou escolha uma que exista e rode a entrega de novo.")





    provisorios, anteriores, gravados = [], {}, []
    try:
        for (origem_c, h_c), final_c in zip(copias, finais):
            fd, provisorio = tempfile.mkstemp(prefix=".entrega-", suffix=".parcial", dir=destino)
            os.close(fd)
            provisorios.append(provisorio)
            shutil.copyfile(origem_c, provisorio)
            if _sha256(provisorio) != h_c:
                for p in provisorios:
                    _remover(p)
                return _recusa_entrega(st, "hash_divergente",
                                       f"A cópia de {os.path.basename(origem_c)} não tem o conteúdo "
                                       f"registrado (o arquivo mudou durante a entrega ou a gravação "
                                       f"em {destino} falhou). Rode `estado_peca.py qual-arquivo` e, "
                                       f"se a peça confere, rode a entrega de novo.")
        for final_c in finais:
            if os.path.exists(final_c) and not args.substituir:
                for p in provisorios:
                    _remover(p)
                return _recusa_entrega(st, "ja_existe",
                                       f"Já existe {os.path.basename(final_c)} em {destino}. Para "
                                       f"substituir o arquivo, rode de novo com --substituir.")
        for final_c in finais:
            if os.path.exists(final_c):
                fd, guarda = tempfile.mkstemp(prefix=".entrega-", suffix=".anterior", dir=destino)
                os.close(fd)
                try:
                    os.replace(final_c, guarda)
                except OSError:
                    _remover(guarda)
                    raise
                anteriores[final_c] = guarda
        for provisorio, final_c in zip(list(provisorios), finais):
            os.replace(provisorio, final_c)
            provisorios.remove(provisorio)
            gravados.append(final_c)
    except OSError as e:
        for p in provisorios:
            _remover(p)
        presos = _desfazer_troca(gravados, anteriores)
        return _recusa_entrega(st, "falha_na_copia",
                               f"A cópia para {destino} falhou ({type(e).__name__}). "
                               f"{_msg_desfeita(anteriores, presos)}Se um arquivo de destino "
                               f"estiver aberto no Word, feche-o. Confira se a pasta aceita gravação "
                               f"e rode a entrega de novo.")
    copiados = [_sha256(f) for f in finais]
    if any(c != h for c, (_o, h) in zip(copiados, copias)):
        presos = _desfazer_troca(finais, anteriores)
        return _recusa_entrega(st, "hash_divergente",
                               f"Um arquivo gravado em {destino} não tem o conteúdo registrado. "
                               f"{_msg_desfeita(anteriores, presos)}Rode a entrega de novo.")
    for guarda in anteriores.values():
        _remover(guarda)
    copiado = copiados[0]

    if via:



        data = args.ts or _agora()
        recibos = st.setdefault("entregas", [])
        extra = {"com_pendencias": True, "ordem_do_advogado": ordem, "pendencias": pendencias}
        recibos.append(dict({"destino": final, "sha256": copiado, "data": data}, **extra))
        for final_c, h_c in zip(finais[1:], copiados[1:]):
            recibos.append(dict({"destino": final_c, "sha256": h_c, "data": data, "anexo": True},
                                **extra))
        if args.ts:
            st["atualizado"] = args.ts
        _gravar(args.state, st)
        _emitir_trace(st.get("fase_atual"), "entregar", {"resultado": "minuta_com_pendencias"})
        print(json.dumps({"ok": True, "resultado": "minuta_com_pendencias",
                          "arquivo": final, "sha256": copiado,
                          "anexos": [{"arquivo": f, "sha256": h}
                                     for f, h in zip(finais[1:], copiados[1:])],
                          "pendencias": pendencias, "ordem_do_advogado": ordem,
                          "termo": ("MINUTA COM PENDÊNCIAS, entregue por ordem do advogado em "
                                    f"{data[:10]}. Não foi liberada pelo rito de revisão; a "
                                    "revisão e o protocolo são do advogado."),
                          "avisos": avisos}, ensure_ascii=False))
        return 0

    _registrar_liberacao(st, args, conselho_acordao)
    data = args.ts or _agora()
    recibos = st.setdefault("entregas", [])
    recibos.append({"destino": final, "sha256": copiado, "data": data})
    for final_c, h_c in zip(finais[1:], copiados[1:]):
        recibos.append({"destino": final_c, "sha256": h_c, "data": data, "anexo": True})
    _gravar(args.state, st)
    _emitir_trace(st.get("fase_atual"), "entregar", {"resultado": "entregue"})
    print(json.dumps({"ok": True, "arquivo": final, "sha256": copiado,
                      "anexos": [{"arquivo": f, "sha256": h}
                                 for f, h in zip(finais[1:], copiados[1:])],
                      "avisos": avisos,
                      "acordao": _montar_acordao(st, conselho_acordao, args)}, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Máquina de estados da peça (dissero-peticao)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init")
    pi.add_argument("--state", default="PECA_STATE.json")
    pi.add_argument("--peca", required=True)
    pi.add_argument("--risco", choices=RISCOS, required=True)
    pi.add_argument("--modo", choices=MODOS, required=True)
    pi.add_argument("--grau", choices=GRAUS,
                    help="grau de jurisdição derivado da classe processual (governa o L20)")
    pi.add_argument("--processo", action="append", default=[],
                    help="CNJ do próprio caso e dos recursos derivados (repetível)")
    pi.add_argument("--session-id", dest="session_id", default=None,
                    help="id da sessão do harness, o mesmo de `caso_raiz.py registrar`")
    pi.add_argument("--ts")
    pi.add_argument("--recomecar", action="store_true",
                    help="recomeça a peça sobre um PECA_STATE existente: arquiva o anterior em "
                         "_versoes/ e registra o reinício (exige --motivo)")
    pi.add_argument("--motivo", default=None, help="por que recomeçar (com --recomecar)")



    pi.add_argument("--sem-squad", dest="sem_squad", default=None, metavar="MOTIVO",
                    help="dispensa o squad NESTA peca, com o motivo gravado no estado. O squad "
                         "e obrigatorio em peca nova; dispensar exige dizer por que")
    pi.add_argument("--sem-adversarial", dest="sem_adversarial", default=None, metavar="MOTIVO",
                    help="dispensa a etapa adversarial NESTA peca, com o motivo gravado no estado. "
                         "A etapa e obrigatoria em peca nova; dispensar exige dizer por que")

    pi.add_argument("--exigir-estanqueidade", dest="exigir_estanqueidade", action="store_true",
                    help="exige que a fase verificacao DECLARE `trechos_lacrados` (lista, "
                         "podendo ser vazia) antes de liberar a entrega desta peca")

    ps = sub.add_parser("status")
    ps.add_argument("--state", default="PECA_STATE.json")

    pa = sub.add_parser("avancar")
    pa.add_argument("--state", default="PECA_STATE.json")
    pa.add_argument("--fase", required=True)
    pa.add_argument("--artefato", default="")
    pa.add_argument("--evidencia")
    pa.add_argument("--entrega-por-download", dest="entrega_por_download", action="store_true",
                    help="ambiente efêmero (Cowork remoto do claude.ai): o .docx é entregue por download, "
                         "não por caminho na pasta do caso")
    pa.add_argument("--ts")

    def opcoes_da_conferencia(p):
        """Opções das conferências da entrega, comuns ao `pode-entregar` e ao `entregar`."""
        p.add_argument("--state", default="PECA_STATE.json")
        p.add_argument("--conselho-status", dest="conselho_status")


        p.add_argument("--precedentes")
        p.add_argument("--juntada")


        p.add_argument("--conferencia")

        p.add_argument("--lint-timeout", dest="lint_timeout", type=float, default=None)

        p.add_argument("--grau", choices=GRAUS)
        p.add_argument("--ts")


        p.add_argument("--exigir-adversarial", dest="exigir_adversarial", action="store_true",
                       help="cobra a etapa adversarial nesta verificacao, mesmo que o PECA_STATE "
                            "nao a exija")
        p.add_argument("--exigir-estanqueidade", dest="exigir_estanqueidade", action="store_true",
                       help="cobra a declaracao de estanqueidade nesta verificacao, mesmo que o "
                            "PECA_STATE nao a exija")
        p.add_argument("--exigir-squad", dest="exigir_squad", action="store_true",
                       help="cobra o squad nesta verificacao, mesmo que o PECA_STATE nao o exija")
        p.add_argument("--transcritos", dest="transcritos", default=None,
                       help="diretorio de transcripts de subagente, repassado ao conselho_gate "
                            "(2a via de proveniencia). Tambem aceita DSR_TRANSCRIPTS_DIR")

    pe = sub.add_parser("pode-entregar")
    opcoes_da_conferencia(pe)
    pe.add_argument("--docx")



    pe.add_argument("--strict", action="store_true")
    pe.add_argument("--informativo", action="store_true",
                    help="consulta: sai 0 mesmo bloqueado (os motivos são os mesmos)")




    pg = sub.add_parser("entregar", help="confere a peça canônica aprovada e a copia ao destino",
                        allow_abbrev=False)
    opcoes_da_conferencia(pg)
    pg.add_argument("--destino", default="", help="pasta que recebe a peça (tem de existir)")
    pg.add_argument("--substituir", action="store_true",
                    help="substitui o arquivo de mesmo nome que já estiver no destino")


    pg.add_argument("--minuta-com-pendencias", dest="minuta_com_pendencias", action="store_true",
                    help="entrega a canônica marcada como MINUTA COM PENDÊNCIAS, sem liberá-la; "
                         "exige --ordem-do-advogado")
    pg.add_argument("--ordem-do-advogado", dest="ordem_do_advogado", default=None,
                    help="as palavras literais do advogado que ordenou a minuta com pendências")
    pg.set_defaults(docx=None, strict=True)

    pr = sub.add_parser("reabrir")
    pr.add_argument("--state", default="PECA_STATE.json")
    pr.add_argument("--fase", required=True)
    pr.add_argument("--motivo", default="")
    pr.add_argument("--ts")

    pc = sub.add_parser("canonico", help="registra/reaponta o .docx de trabalho e carimba o hash")
    pc.add_argument("--state", default="PECA_STATE.json")
    pc.add_argument("--arquivo", default="")
    pc.add_argument("--ts")

    pq = sub.add_parser("qual-arquivo", help="qual é o .docx de trabalho, e ele mudou?")
    pq.add_argument("--state", default="PECA_STATE.json")

    px = sub.add_parser("anexo", help="registra o arquivo que sai com a peça no `entregar`")
    px.add_argument("--state", default="PECA_STATE.json")
    px.add_argument("--arquivo", default="")
    px.add_argument("--remover", action="store_true", help="retira o registro do anexo")
    px.add_argument("--ts")

    args = ap.parse_args()
    try:
        if args.cmd == "init":
            return cmd_init(args)
        if args.cmd == "status":
            return cmd_status(args)
        if args.cmd == "avancar":
            return cmd_avancar(args)
        if args.cmd == "pode-entregar":
            return cmd_pode_entregar(args)
        if args.cmd == "reabrir":
            return cmd_reabrir(args)
        if args.cmd == "canonico":
            return cmd_canonico(args)
        if args.cmd == "qual-arquivo":
            return cmd_qual_arquivo(args)
        if args.cmd == "anexo":
            return cmd_anexo(args)
        if args.cmd == "entregar":
            try:
                return cmd_entregar(args)
            except Contrato as e:
                return _recusa_entrega(None, "contrato_invalido",
                                       "O comando ou o PECA_STATE.json é inválido. Corrija o que "
                                       "os motivos apontam e rode a entrega de novo.", e.args[0], 2)
    except Contrato as e:
        return _saida("contrato_invalido", None, e.args[0], 2)
    return _saida("contrato_invalido", None, ["subcomando desconhecido"], 2)


if __name__ == "__main__":
    sys.exit(main())
