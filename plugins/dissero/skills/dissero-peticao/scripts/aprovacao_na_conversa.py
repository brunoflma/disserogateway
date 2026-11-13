#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'aprovacao_na_conversa.py — a aprovação de estratégia e roteiro conferida na resposta do advogado.'



























import datetime
import hashlib
import json
import os
import re
import secrets
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
try:
    import falas_do_advogado
except Exception:
    falas_do_advogado = None

FASES = ("estrategia", "mapa")
PERGUNTAS = {
    "estrategia": "Aprova esta estratégia? Responda «aprovo» para seguir, ou diga o que mudar.",
    "mapa": "Aprova este roteiro de argumentos? Responda «aprovo» para seguir, ou diga o que mudar.",
}
TRECHOS = {
    "estrategia": ("Aprova esta estratégia", "diga o que mudar"),
    "mapa": ("Aprova este roteiro de argumentos", "diga o que mudar"),
}






_ABRE = re.compile(
    r'(?:(?:eu|entao|bom|tudo|ta|esta|e)\s+)*'
    r'(?:aprovo|aprovada|aprovado|aprovadissima|aprovadissimo|sim|ok|okay|okey|de acordo|concordo|perfeito|'
    r'perfeita|certo|correto|correta|isso mesmo|isso ai|e isso|fechado|beleza|blz|otimo|otima|excelente|'
    r'show|manda ver|bora|pode seguir|pode prosseguir|pode ir|pode mandar|pode sim|pode redigir|segue|siga|'
    r'prossiga|ta bom|ta otimo|ta perfeito|ta certo|esta bom|esta otimo|esta otima|esta perfeito|'
    r'esta perfeita|esta certo|esta correto|tudo certo|tudo bem|tudo ok|muito bom|muito boa)(?!\w)')

_PERMITIDAS = frozenset("""
aprovo aprovada aprovado aprovadissima aprovadissimo aprova sim ok okay okey de acordo concordo perfeito
perfeita certo certa correto correta isso mesmo ai e fechado beleza blz otimo otima excelente show manda ver
bora pode seguir prosseguir ir mandar redigir segue siga prossiga ta esta bom boa bem tudo muito ficou
obrigado obrigada valeu grato grata eu entao com a o as os para pra redacao estrategia roteiro
argumentos de do da assim como pode
""".split())

_SEM_MUDANCA = re.compile(
    r'(?<!\w)(?:(?:nao (?:precisa|e preciso|ha (?:nada )?(?:o )?(?:que|a|para|pra)|tenho(?: nada)?(?: a| para| pra)?) '
    r'(?:de )?(?:mudar|alterar|ajustar|corrigir|acrescentar|mexer|ressalvas?|reparos?|observac\w+)'
    r'(?: nada| em nada)?)'
    r'|(?:nada|sem nada|sem) (?:a |para |pra )?(?:mudar|alterar|ajustar|corrigir|acrescentar|mexer)'
    r'|(?:sem|nenhuma?) (?:ressalvas?|reparos?|alteracao|alteracoes|mudancas?|ajustes?|correcao|correcoes|'
    r'observacao|observacoes))(?!\w)')


def _norm(texto):
    if falas_do_advogado is not None:
        return falas_do_advogado.normalizar(texto)
    import unicodedata
    t = unicodedata.normalize("NFKD", texto or "")
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split()).casefold()


def aprova(texto):
    'True só quando a resposta inteira é aprovação: abre por uma fórmula de aprovação, não tem'


    n = _norm(texto)
    if not n.strip() or "?" in n:
        return False
    n = re.sub(r'[^\w\s]+', ' ', n.replace("tá", "ta").replace("tô", "to"))
    n = " ".join(n.split())
    n = " ".join(_SEM_MUDANCA.sub(" ok ", n).split())
    if not _ABRE.match(n):
        return False
    resto = n.split()
    return bool(resto) and all(w in _PERMITIDAS for w in resto)


REGISTRO = "APROVACAO_PERGUNTAS.json"
SCHEMA = "dsr.aprovacao_perguntas.v1"
ROTULO_CODIGO = "registro da pergunta:"


def _selo(reg):
    base = {k: v for k, v in reg.items() if k != "selo"}
    return hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def arquivo_da_fase(state, artefato):
    """O caminho do artefato como o `estado_peca` o resolve: absoluto, ou relativo à pasta do estado."""
    a = os.path.expanduser(str(artefato or "").strip())
    a = a if os.path.isabs(a) else os.path.join(os.path.dirname(os.path.abspath(state)), a)
    return os.path.normcase(os.path.normpath(a))


def ler_registro(state):
    """(registro, None) ou (None, motivo). Registro editado à mão não vale."""
    caminho = os.path.join(os.path.dirname(os.path.abspath(state)), REGISTRO)
    if not os.path.isfile(caminho):
        return None, None
    try:
        with open(caminho, encoding="utf-8") as fh:
            reg = json.load(fh)
    except Exception:
        return None, "o registro das perguntas de aprovação está ilegível"
    if (not isinstance(reg, dict) or reg.get("schema_version") != SCHEMA
            or not isinstance(reg.get("fases"), dict) or reg.get("selo") != _selo(reg)):
        return None, "o registro das perguntas de aprovação não foi gravado pelo script (ou foi alterado depois)"
    return reg, None


def registrar_pergunta(fase, state, artefato, agora=None):
    """Grava o hash do arquivo da fase no instante da pergunta e devolve o código de uso único."""
    if fase not in FASES:
        raise ValueError(f"fase fora de {FASES}")
    if not os.path.isfile(state):
        raise ValueError("o --state não é o PECA_STATE.json da peça")
    arquivo = arquivo_da_fase(state, artefato)
    if not os.path.isfile(arquivo):
        raise ValueError(f"o arquivo da fase («{artefato}») não existe: grave-o antes de perguntar")
    anterior, _ = ler_registro(state)
    fases = dict((anterior or {}).get("fases") or {})
    codigo = secrets.token_hex(8)
    em = (agora or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fases[fase] = {"arquivo": arquivo, "sha256": _sha_arquivo(arquivo), "codigo": codigo, "em": em}
    reg = {"schema_version": SCHEMA, "gerado_por": "aprovacao_na_conversa.py", "fases": fases}
    reg["selo"] = _selo(reg)
    caminho = os.path.join(os.path.dirname(os.path.abspath(state)), REGISTRO)
    tmp = caminho + ".parcial"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, caminho)
    return codigo


def _pergunta_do_arquivo(fase, falas, state, artefato):
    'None quando a pergunta registrada para esta peça é a última feita antes da resposta e o'

    reg, motivo = ler_registro(state)
    if motivo:
        return motivo
    p = (reg or {}).get("fases", {}).get(fase)
    if not isinstance(p, dict) or not p.get("codigo"):
        return ("a pergunta de aprovação não foi feita pelo script com o arquivo desta peça "
                f"(`aprovacao_na_conversa.py pergunta {fase} --state ... --artefato ...`), então não há "
                "como saber que texto ele aprovou")
    saida = getattr(falas, "saida_corte", None) or ""
    if f"{ROTULO_CODIGO} {p['codigo']}" not in saida or saida.count(ROTULO_CODIGO) != 1:
        return ("a última pergunta de aprovação feita antes da resposta dele não é a registrada para esta "
                "peça (a de outra peça, ou a pergunta refeita depois da resposta)")
    arquivo = arquivo_da_fase(state, artefato)
    if arquivo != p.get("arquivo"):
        return "o arquivo registrado na fase não é o que foi mostrado na pergunta de aprovação"
    if not os.path.isfile(arquivo) or _sha_arquivo(arquivo) != p.get("sha256"):
        return ("o arquivo mudou entre a pergunta de aprovação e o registro da fase; a resposta dele "
                "não alcança o texto de agora: mostre-o e pergunte de novo")
    return None


def _cortesia(texto):
    n = " ".join(re.sub(r'[^\w\s]+', ' ', _norm(texto)).split())
    return bool(n) and all(w in {"obrigado", "obrigada", "valeu", "grato", "grata", "ok", "beleza", "blz"}
                           for w in n.split())


def _ancora(fase):
    def casa(entrada):
        cmd = entrada.get("command") if isinstance(entrada, dict) else None
        return (isinstance(cmd, str) and "estado_peca" in cmd and "avancar" in cmd
                and re.search(r'--fase[\s=]+["\']?' + fase + r'(?!\w)', cmd) is not None)
    return casa


def _corte(fase):
    'O registro anterior da mesma fase (de outra peça ou de outro ciclo), a reabertura do rito e'


    casa = _ancora(fase)

    def corta(entrada):
        cmd = entrada.get("command") if isinstance(entrada, dict) else None
        if not isinstance(cmd, str):
            return False
        if casa(entrada):
            return True
        if "estado_peca" in cmd and re.search(r'(?<![\w-])reabrir(?!\w)', cmd):
            return True
        return bool("aprovacao_na_conversa" in cmd and re.search(r'(?<![\w-])pergunta(?!\w)', cmd)
                    and re.search(r'(?<![\w-])' + fase + r'(?![\w-])', cmd))
    return corta


def _nao(motivo, fonte=None):
    return {"estado": "nao_conferida", "fonte": fonte, "motivo": motivo, "resposta": None}


def conferir(fase, env=None, livro=None, ancora=None, state=None, artefato=None):
    '{"estado": "conferida"|"nao_conferida", "fonte", "motivo", "resposta"}. Nunca levanta e nunca'



    if fase not in FASES:
        return _nao(f"a fase «{fase}» não tem pergunta de aprovação")
    if falas_do_advogado is None:
        return _nao("o leitor das mensagens do advogado não está nesta cópia do plugin")
    try:
        falas, fonte, motivo = falas_do_advogado.falas_da_sessao(
            env, TRECHOS[fase], ancora or _ancora(fase), livro, _corte(fase))
        if falas is None:
            return _nao(motivo or "sem registro legível da conversa")
        if fonte == "livro_de_falas":
            return _nao("no Cowork remoto o registro guarda as mensagens dele, mas não a pergunta de "
                        "aprovação nem a caixa de perguntas", fonte)
        if not falas.marcas:
            return _nao("a pergunta de aprovação não foi feita com o texto fixo nesta sessão (ou não foi "
                        "feita de novo depois do registro anterior desta fase)", fonte)
        resp, _porque = falas_do_advogado.resposta_a_pergunta(falas)
        if resp is None:
            return _nao("a pergunta de aprovação foi feita e o advogado ainda não respondeu a ela", fonte)
        curta = " ".join(resp.split())[:300]
        if not aprova(resp):
            return dict(_nao("a resposta dele à pergunta de aprovação não aprova sem ressalva", fonte),
                        resposta=curta)


        i = next(k for k, f in enumerate(falas) if f is resp)
        depois = falas[i + 1:]
        if any(f.origem in ("digitada", "enfileirada", "caixa") and not aprova(f) and not _cortesia(f)
               for f in depois):
            return dict(_nao("depois de aprovar, o advogado escreveu de novo sem a pergunta ser refeita; "
                             "mostre o texto atual e pergunte outra vez", fonte), resposta=curta)
        if state is not None:
            falta = _pergunta_do_arquivo(fase, falas, state, artefato)
            if falta:
                return dict(_nao(falta, fonte), resposta=curta)
        return {"estado": "conferida", "fonte": fonte, "motivo": None, "resposta": curta}
    except Exception as e:
        return _nao(f"a leitura do registro da conversa falhou ({type(e).__name__})")


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    uso = ("uso: aprovacao_na_conversa.py pergunta estrategia|mapa --state <PECA_STATE.json> --artefato <arquivo>\n"
           "     aprovacao_na_conversa.py conferir estrategia|mapa")
    if len(a) >= 2 and a[0] == "pergunta" and a[1] in FASES:
        opts = dict(zip(a[2::2], a[3::2]))
        if len(a) % 2 or set(opts) - {"--state", "--artefato"}:
            print(uso, file=sys.stderr)
            return 2
        if not (opts.get("--state") and opts.get("--artefato")):
            print(PERGUNTAS[a[1]])
            print("aviso: sem --state e --artefato, a resposta do advogado não poderá ser conferida e a "
                  "aprovação sairá declarada.", file=sys.stderr)
            return 0
        try:
            codigo = registrar_pergunta(a[1], opts["--state"], opts["--artefato"])
        except (ValueError, OSError) as e:
            print(f"pergunta não registrada: {e}", file=sys.stderr)
            return 1
        print(PERGUNTAS[a[1]])
        print(f"({ROTULO_CODIGO} {codigo}. Mostre ao advogado só a pergunta acima, depois do texto do "
              "arquivo; se mudar o arquivo, rode este comando de novo e pergunte outra vez.)")
        return 0
    if len(a) == 2 and a[0] == "conferir" and a[1] in FASES:
        print(json.dumps(conferir(a[1]), ensure_ascii=False))
        return 0
    print(uso, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
