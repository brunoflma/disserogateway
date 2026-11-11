#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'mapa_argumentativo.py — exame do mapa argumentativo da peça (fase `mapa` da dissero-peticao).'































import json
import os
import re
import sys
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass




DEGRAUS = (
    (1, "questões processuais",
     re.compile(r"\bquest\w* processua|\bpreliminar(?!\w*\s+de\s+merito)|\bart\.? ?337\b")),
    (2, "prejudiciais de mérito", re.compile(r"\bprejudicia|\bpreliminar\w*\s+de\s+merito")),
    (3, "mérito principal", re.compile(r"\bmerito principal\b|\ban debeatur\b")),
    (4, "mérito secundário", re.compile(r"\bmerito secundario\b|\bquantum debeatur\b")),
    (5, "consectários e sucumbência", re.compile(r"\bconsectario|\bsucumbencia")),
)
NOME_DEGRAU = {n: nome for n, nome, _ in DEGRAUS}

_ITEM = r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?"
_RX_TITULO = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_RX_TESE = re.compile(_ITEM + r"(?:#{1,6}\s*)?tese(?:\s+\(?\d+\)?)?\s*:\s*(.*)$")
_RX_QUESTAO = re.compile(_ITEM + r"questao(?:\s+\(?\d+\)?)?\s*:\s*(.*)$")
_RX_QUADRO = re.compile(_ITEM + r"(?:(tese)\s+)?(principal|central|subsidiari[ao]s?|descartad[ao]s?)"
                        r"\b[^:\n]*:\s*(.*)$")
_RX_MOTIVO = re.compile(r"\bmotivo\s*:\s*(.*)$")
_RX_MOTIVO_LINHA = re.compile(_ITEM + r"motivo\s*:\s*(.*)$")
_RX_LISTA = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+\S")

_RX_ROTULO = re.compile(r"^\s*(?:#|(?:[-*+]|\d+[.)])\s|[^\s:]+(?:\s+[^\s:]+){0,3}\s*:(?:\s|$))")



_RX_SECAO_FORA = re.compile(
    r"^(?:d[oa]s?\s+)?(?:fatos?|pedidos?|requerimentos?|documentos?|provas?|anexos?|testemunhas?"
    r"|rol|conclus(?:ao|oes)|sintese|encerramento|fecho)\b")

_RX_NUMERACAO = re.compile(r"^(?:\d+(?:\.\d+)*[.)]?|[ivx]{1,6}\s*[.)\-–—])\s*")
_RX_SECAO_QUADRO = re.compile(r"\bquadro\b|^(?:d[oa]s?\s+)?teses\b")
_PALAVRA = re.compile(r"[a-z]{3,}")


def _norm(linha):
    """Minúsculas, sem acento e sem a marcação de ênfase do Markdown."""
    sem = "".join(c for c in unicodedata.normalize("NFD", linha.lower())
                  if unicodedata.category(c) != "Mn")
    return sem.replace("**", "").replace("__", "")


def _degrau(titulo_norm):
    achados = [n for n, _, rx in DEGRAUS if rx.search(titulo_norm)]
    return achados[0] if len(achados) == 1 else None


def _tem_palavra(texto):
    """Ao menos uma palavra de três letras que não seja uma letra só repetida («aaa»)."""
    return any(len(set(p)) > 1 for p in _PALAVRA.findall(texto or ""))


def _indent(linha):
    return len(linha) - len(linha.lstrip())


def examinar(texto):
    """{aprovado, estruturado, teses, quadro, motivos:[{codigo, mensagem}], avisos:[...]}"""
    linhas = texto.splitlines()
    norm = [_norm(l) for l in linhas]
    teses, quadro = [], {"principal": 0, "subsidiaria": 0, "descartada": 0}
    motivos, avisos = [], []
    degrau_atual, tese, questao_aberta = None, None, None
    secao_fora, secao_degrau, itens_em_degrau = False, False, 0

    def reprova(codigo, mensagem):
        motivos.append({"codigo": codigo, "mensagem": mensagem})

    def motivo_de(i, texto_linha):
        """Motivo na própria linha ou na próxima linha não vazia."""
        mot = _RX_MOTIVO.search(texto_linha)
        if mot:
            return mot.group(1)
        for j in range(i + 1, len(norm)):
            if norm[j].strip():
                seguinte = _RX_MOTIVO_LINHA.match(norm[j])
                return seguinte.group(1) if seguinte else ""
        return ""

    def confere_descarte(i, texto_linha, original):
        if not _tem_palavra(motivo_de(i, texto_linha)):
            reprova("descarte_sem_motivo",
                    f"linha {i + 1}: tese descartada sem o motivo do descarte («{original}»). "
                    "Escreva na mesma linha, ou na seguinte, «Motivo: <por que ficou de fora>».")

    for i, n in enumerate(norm):
        original = linhas[i].strip()
        if questao_aberta is not None:

            if n.strip() and not _RX_ROTULO.match(n):
                questao_aberta[1] = (questao_aberta[1] + " " + n.strip()).strip()
                if questao_aberta[1].rstrip(" *_").endswith("?"):
                    questao_aberta = None
                continue
            questao_aberta = None
        m = _RX_TITULO.match(n)
        if m and not _RX_TESE.match(n):
            titulo = _RX_NUMERACAO.sub("", m.group(1).strip(" *_:"), count=1)
            d = _degrau(titulo)
            secao_fora = bool(_RX_SECAO_FORA.match(titulo))
            if d is not None:
                degrau_atual, secao_degrau = d, True
            elif secao_fora or _RX_SECAO_QUADRO.search(titulo):
                secao_degrau = False
            tese = None
            continue
        if not _RX_LISTA.match(n) and not _indent(n) and ":" in n:
            rotulo = _RX_NUMERACAO.sub("", n.strip(" *_"), count=1)
            if _RX_SECAO_FORA.match(rotulo):
                secao_fora, secao_degrau = True, False
            elif _RX_SECAO_QUADRO.search(rotulo.split(":")[0]):
                secao_fora, secao_degrau = False, False
        m = _RX_TESE.match(n)
        if m:
            tese = {"linha": i + 1, "texto": original, "degrau": degrau_atual, "questoes": []}
            teses.append(tese)
            continue
        m = _RX_QUESTAO.match(n)
        if m:
            if tese is not None:
                q = [i + 1, m.group(1).strip()]
                tese["questoes"].append(q)
                if not q[1].rstrip(" *_").endswith("?"):
                    questao_aberta = q
            continue
        m = _RX_QUADRO.match(n)
        if m and not secao_fora and not (m.group(2) == "central" and not m.group(1)):
            tipo = m.group(2)
            chave = ("principal" if tipo in ("principal", "central")
                     else "subsidiaria" if tipo.startswith("subsidiari") else "descartada")
            if chave != "descartada":
                quadro[chave] += 1
                continue
            if m.group(3).strip(" *_"):
                quadro["descartada"] += 1
                confere_descarte(i, m.group(3), original)
                continue

            subitens = []
            for j in range(i + 1, len(norm)):
                if not norm[j].strip():
                    continue
                if _indent(norm[j]) <= _indent(n) or _RX_TITULO.match(norm[j]):
                    break
                if _RX_LISTA.match(norm[j]) and not _RX_MOTIVO_LINHA.match(norm[j]):
                    subitens.append(j)
            if not subitens:
                quadro["descartada"] += 1
                confere_descarte(i, "", original)
            for j in subitens:
                quadro["descartada"] += 1
                confere_descarte(j, norm[j], linhas[j].strip())
            continue
        if secao_degrau and not secao_fora and _RX_LISTA.match(n):
            itens_em_degrau += 1

    estruturado = bool(teses) or any(quadro.values()) or bool(itens_em_degrau)
    if not estruturado:
        avisos.append({"codigo": "mapa_sem_estrutura", "mensagem":
                       "MAPA SEM QUADRO DE TESES NEM ESCADA DE EXAME: nada foi conferido. Monte o mapa "
                       "no formato de references/mapa-argumentativo.md (quadro de teses e, por degrau, "
                       "«Tese:» seguida de «Questão: ...?»)."})

    for t in teses:
        if not t["questoes"]:
            reprova("tese_sem_questao",
                    f"linha {t['linha']}: tese sem a linha «Questão:» («{t['texto']}»). Formule a "
                    "pergunta fechada que o juiz terá de responder para acolher a tese.")
            continue
        if len(t["questoes"]) > 1:
            avisos.append({"codigo": "questao_repetida", "mensagem":
                           f"linha {t['linha']}: a tese tem {len(t['questoes'])} linhas «Questão:»; "
                           "pergunta diferente costuma ser tese diferente."})
        for linha, q in t["questoes"]:
            q = q.rstrip(" *_")
            if not q.endswith("?"):
                reprova("questao_sem_interrogacao",
                        f"linha {linha}: a Questão não termina em ponto de interrogação. Escreva-a "
                        "como pergunta fechada, a que se responde com sim ou não.")
            elif not _tem_palavra(q):
                reprova("questao_vazia",
                        f"linha {linha}: a Questão não traz pergunta nenhuma. Escreva a pergunta "
                        "fechada que o juiz terá de responder para acolher a tese.")
        if t["degrau"] is None:
            avisos.append({"codigo": "tese_sem_degrau", "mensagem":
                           f"linha {t['linha']}: tese fora de um degrau reconhecido da escada "
                           "(questões processuais, prejudiciais, mérito principal, mérito "
                           "secundário, consectários e sucumbência)."})

    if not teses and (any(quadro.values()) or itens_em_degrau):
        reprova("mapa_sem_questao", "o mapa tem quadro de teses ou degraus da escada, mas nenhuma "
                "linha «Tese:» com a sua «Questão:». Sob cada degrau, escreva «Tese:» e, logo "
                "abaixo, «Questão: ...?».")
    if teses and not quadro["principal"]:
        reprova("quadro_sem_principal", "falta no quadro de teses a linha «Principal:» (a tese "
                "principal, com as subsidiárias e as descartadas abaixo dela).")
    if quadro["subsidiaria"] and not quadro["principal"]:
        reprova("subsidiaria_sem_principal", "há tese subsidiária sem tese principal: o pedido "
                "subsidiário só é conhecido se o anterior não for acolhido (CPC, art. 326).")

    maior = None
    for t in teses:
        d = t["degrau"]
        if d is None:
            continue
        if maior is not None and d < maior:
            reprova("escada_fora_de_ordem",
                    f"linha {t['linha']}: tese de {NOME_DEGRAU[d]} depois de tese de "
                    f"{NOME_DEGRAU[maior]}. A ordem de exame é: questões processuais (art. 337), "
                    "prejudiciais de mérito, mérito principal, mérito secundário, consectários e "
                    "sucumbência.")
        maior = d if maior is None else max(maior, d)

    return {"aprovado": not motivos, "estruturado": estruturado, "teses": len(teses),
            "quadro": quadro, "motivos": motivos, "avisos": avisos}


def examinar_arquivo(caminho):
    with open(caminho, encoding="utf-8") as fh:
        return examinar(fh.read())


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(json.dumps({"ok": False, "codigo": "uso_invalido",
                          "mensagem": "uso: mapa_argumentativo.py MAPA.md"}, ensure_ascii=False))
        return 2
    try:
        res = examinar_arquivo(argv[0])
    except (OSError, UnicodeDecodeError) as e:
        print(json.dumps({"ok": False, "codigo": "mapa_ilegivel",
                          "mensagem": f"não foi possível ler o mapa: {e}"}, ensure_ascii=False))
        return 2
    print(json.dumps(dict(ok=res["aprovado"], **res), ensure_ascii=False))
    return 0 if res["aprovado"] else 1


if __name__ == "__main__":
    sys.exit(main())
