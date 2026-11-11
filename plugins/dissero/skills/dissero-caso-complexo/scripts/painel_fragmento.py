#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'painel_fragmento.py — converte o painel do Conselho em FRAGMENTO pronto para o widget.'


































































import sys, os, re, json, stat, time, argparse, tempfile, contextlib
import html as _html
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass



try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import caso_raiz as _caso_raiz
except Exception:
    _caso_raiz = None


class CaminhoRecusado(ValueError):
    'Nome nu que nao se atribui a um arquivo da pasta do caso desta sessao; `resultado`'


    def __init__(self, resultado, motivo):
        super().__init__(motivo)
        self.resultado = resultado


def pasta_do_caso(session_id=None):
    '(pasta, origem) do caso DESTA sessao, ou (None, origem). So valem `DSR_CASO_RAIZ` e o'


    if _caso_raiz is None:
        return None, "sem_caso_raiz"
    try:
        raiz, origem = _caso_raiz.resolver(session_id=session_id)
    except Exception:
        return None, "falha"
    return (raiz, origem) if origem in ("env", "sessao") else (None, origem)


def no_caso(caminho, session_id=None, leitura=True, opcao="--state"):
    'Arquivo de nome NU -> o da pasta do caso desta sessao. Caminho com diretorio fica como'




    if not (isinstance(caminho, str) and caminho.strip()) or os.path.dirname(caminho):
        return caminho
    raiz, origem = pasta_do_caso(session_id)
    if raiz is None:
        motivo = ("«%s» veio sem pasta, e a pasta do caso desta sessão não foi identificada. "
                  % caminho)
        if origem == "sem_caso_raiz":
            motivo += "O caso_raiz.py não está ao lado deste script. "
        elif origem == "atual":
            motivo += ("A última pasta registrada pode ser de outra sessão ou de outro caso, e "
                       "não é usada. ")
        motivo += ("Passe o caminho completo em %s (\"<pasta do caso>/%s\"). Ou repita o "
                   "comando com --session-id <id da sessão>, depois de registrar a pasta com "
                   "`caso_raiz.py registrar --raiz \"<pasta do caso>\" --session-id <id da "
                   "sessão>`." % (opcao, caminho))
        raise CaminhoRecusado("caso_nao_resolvido", motivo)
    no_raiz = os.path.join(raiz, caminho)
    if leitura:
        try:
            dois = (os.path.isfile(no_raiz) and os.path.isfile(caminho)
                    and not os.path.samefile(no_raiz, caminho))
        except OSError:
            dois = True
        if dois:
            raise CaminhoRecusado("caminho_ambiguo", (
                "«%s» existe na pasta corrente (%s) e na pasta do caso (%s), como arquivos "
                "diferentes. Passe o caminho completo do estado desta sessão em %s."
                % (caminho, os.path.abspath(caminho), no_raiz, opcao)))
    return no_raiz


PLACEHOLDER = "/*ESTADO_INLINE*/ null"


PLACEHOLDER_CAMINHO = "/*STATE_PATH*/ null"
WRAPPER = "dsr-painel"





MODELO_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references",
                             "painel-conselho.html")


_SKILL = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL_DO_MODELO = _SKILL if _SKILL.startswith("dissero-") else "dissero-peticao"
MSG_MODELO_AUSENTE = (
    "modelo do plenario nao encontrado: %s. Busque-o pelo conector com carregar_recurso "
    "(caminho '" + SKILL_DO_MODELO + "/references/painel-conselho.html' e, para a mesma pasta, '"
    + SKILL_DO_MODELO + "/references/painel-conselho.js'), grave cada texto devolvido tal e qual "
    "no seu arquivo e rode de novo com --painel <arquivo .html>. Nao desenhe um painel proprio: o "
    "plenario do Conselho e este modelo, com os cinco julgadores e o brasao. Sem o modelo, "
    "declare ao advogado que o painel nao pode ser exibido.")






SCRIPT_DO_MODELO = "painel-conselho.js"
TAG_SCRIPT_DO_MODELO = '<script src="painel-conselho.js"></script>'


class ModeloIncompleto(ValueError):
    pass


def ler_modelo(caminho_html):
    """O documento completo do plenario: o .html com o script dele inline."""
    with open(caminho_html, encoding="utf-8") as f:
        html = f.read()
    if TAG_SCRIPT_DO_MODELO not in html:
        return html
    caminho_js = os.path.join(os.path.dirname(os.path.abspath(caminho_html)), SCRIPT_DO_MODELO)
    if not os.path.isfile(caminho_js):
        raise ModeloIncompleto(MSG_MODELO_AUSENTE % caminho_js)
    with open(caminho_js, encoding="utf-8") as f:
        js = f.read()
    return html.replace(TAG_SCRIPT_DO_MODELO, "<script>" + js + "</script>", 1)


COMO_EXIBIR = (
    "passe o CONTEUDO deste arquivo em `widget_code` (leia e cole o texto inteiro), nunca o "
    "caminho: caminho, URL ou placeholder renderizam como TEXTO CRU na tela e o painel nao "
    "aparece. AUTOTESTE: o argumento tem de comecar com '<style>'. Sem `--saida`, este script "
    "imprime o fragmento direto no stdout. Se a superficie recusar o tamanho, DECLARE a falha "
    "ao advogado e entregue o PAINEL_CONSELHO.html como download - nunca siga o rito como se o "
    "painel estivesse na tela."
)


def _erro(motivo):
    print(json.dumps({"ok": False, "erro": motivo}, ensure_ascii=False))
    return 1


def json_para_script(obj):
    'Serializa o estado para dentro de um bloco <script> SEM permitir marcacao.'












    s = json.dumps(obj, ensure_ascii=False)


    for bruto, seguro in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                          ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        s = s.replace(bruto, seguro)
    return s


















RX_CNJ_CANONICO = re.compile(r"(?<!\d)(?:\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|\d{20})(?!\d)")


RX_CNJ_FRAGMENTO = re.compile(r"(?<!\d)\d{7}-\d{2}(?!\d)")
RX_CPF = re.compile(r"(?<!\d)\d{3}[. ]?\d{3}[. ]?\d{3}[- ]?\d{2}(?!\d)")
RX_CNPJ = re.compile(r"(?<!\d)\d{2}[. ]?\d{3}[. ]?\d{3}[/ ]?\d{4}[- ]?\d{2}(?!\d)")
RX_OAB = re.compile(r"\bOAB(?:\s*[/\-]\s*|\s+)(?:[A-Z]{2}\s*)?\d{3,8}(?:\s*[-/]\s*[A-Z])?\b", re.I)

DETECTORES = (("CNJ", RX_CNJ_CANONICO), ("CNPJ", RX_CNPJ), ("CPF", RX_CPF),
              ("OAB", RX_OAB), ("CNJ-fragmento", RX_CNJ_FRAGMENTO))
MASCARA = {"CNJ": "[processo]", "CNJ-fragmento": "[processo]", "CNPJ": "[CNPJ]",
           "CPF": "[CPF]", "OAB": "[OAB]"}


def mascarar_texto(valor):
    """Substitui identificadores por rótulo. Só texto — quem percorre a árvore é `pseudonimizar`."""
    if not isinstance(valor, str):
        return valor
    for rotulo, rx in DETECTORES:
        valor = rx.sub(MASCARA[rotulo], valor)
    return valor


def varrer(obj, _caminho="estado"):
    'Reexecuta os detectores sobre a árvore inteira e devolve o que sobreviveu.'




    achados = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            achados += varrer(k, "%s.%s" % (_caminho, k))
            achados += varrer(v, "%s.%s" % (_caminho, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            achados += varrer(v, "%s[%d]" % (_caminho, i))
    elif isinstance(obj, str):
        for rotulo, rx in DETECTORES:
            for m in rx.findall(obj):
                achados.append({"onde": _caminho, "tipo": rotulo, "trecho": m})
    return achados


RX_PECA_CITADA = re.compile(r"pe[çc]a\s+'([^']{4,200})'")








RX_MASCARA_CAMINHO = re.compile(
    r"(?<![\w.~/\\-])(?:[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/]|(?<!:)//[^\\/\s]+/|~[\\/]|/[A-Za-z]/"
    r"|/(?:sessions|mnt|home|Users|Volumes|media|tmp|var|srv|private|root|opt)/)(?:[^\\/\n]*[\\/])*"
    r"(?:[^\\/\n]*?\.(?:docx?|md|pdf|json|html?|txt|odt|rtf|xlsx?|zip|py)\b"
    r"|(?:[^\\/\n\"'«»()<>|]*[^\\/\n\"'«»()<>|\s])?)")









RX_CAMINHO_ABSOLUTO = re.compile(
    r"[A-Za-z]:\\|[A-Za-z]:/(?!/)|\\\\|\\Users\\|(?<!:)//[^/\s]|\b(?:file|computer):/"
    r"|~(?:[A-Za-z_][\w.-]*)?[\\/]|/[A-Za-z]/(?=[^/\s]*/)|^/"
    r"|/(?:sessions|mnt|home|Users|Volumes|media|tmp|var|srv|private|root|opt|workspace|data|run"
    r"|cygdrive|content)/")
RX_ENDERECO_WEB = re.compile(r"\bhttps?://\S+")


def caminhos_absolutos(obj, _caminho="estado"):
    """Onde, na árvore, há texto que parece caminho absoluto (chaves e valores)."""
    achados = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            achados += caminhos_absolutos(k, "%s.%s" % (_caminho, k))
            achados += caminhos_absolutos(v, "%s.%s" % (_caminho, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            achados += caminhos_absolutos(v, "%s[%d]" % (_caminho, i))
    elif isinstance(obj, str) and RX_CAMINHO_ABSOLUTO.search(RX_ENDERECO_WEB.sub("", obj)):
        achados.append(_caminho)
    return achados


def _sem_rastro_local(o):
    """Cópia sem o rastro que a sessão deixa na máquina: toda chave `caminho`, onde estiver."""
    if isinstance(o, dict):
        return {k: _sem_rastro_local(v) for k, v in o.items() if k != "caminho"}
    if isinstance(o, list):
        return [_sem_rastro_local(v) for v in o]
    return o


def pseudonimizar(estado, codigo_caso, termos_vedados=()):
    'Devolve uma CÓPIA do estado apta a sair da máquina, ou levanta ValueError.'

























    if not isinstance(codigo_caso, str) or not codigo_caso.strip():
        raise ValueError("--codigo-caso obrigatorio em --publico (rotulo opaco, ex.: 'A-17')")
    codigo = codigo_caso.strip()
    sobra_no_codigo = varrer(codigo, "codigo_caso")
    if sobra_no_codigo:
        raise ValueError("o proprio --codigo-caso carrega identificador (%s) — use rotulo opaco"
                         % ", ".join(sorted({a["tipo"] for a in sobra_no_codigo})))






    rotulo = "Caso " + codigo
    titulos = []
    for fonte in [estado] + list(estado.get("ciclos") or []):
        if isinstance(fonte, dict) and isinstance(fonte.get("peca"), str) and fonte["peca"].strip():
            titulos.append(fonte["peca"])

    for fonte in [estado] + list(estado.get("ciclos") or []):
        for ev in ((fonte or {}).get("eventos") or []):
            if isinstance(ev, dict) and isinstance(ev.get("texto"), str):
                titulos += RX_PECA_CITADA.findall(ev["texto"])
    vedados = [t.strip() for t in (termos_vedados or ()) if isinstance(t, str) and t.strip()]


    alvos = sorted(set(titulos), key=len, reverse=True)
    vedados = sorted(set(vedados), key=len, reverse=True)

    def caminhar(o):
        if isinstance(o, dict):
            return {k: caminhar(v) for k, v in o.items()}
        if isinstance(o, list):
            return [caminhar(v) for v in o]
        if isinstance(o, str):
            for t in alvos:
                o = o.replace(t, rotulo)
            for t in vedados:
                o = re.sub(re.escape(t), "[termo vedado]", o, flags=re.I)
            o = RX_MASCARA_CAMINHO.sub("[caminho]", o)
        return mascarar_texto(o)

    limpo = caminhar(json.loads(json.dumps(estado, ensure_ascii=False)))



    for bloco in [limpo] + [c for c in (limpo.get("ciclos") or []) if isinstance(c, dict)]:
        bloco.pop("painel", None)
        bloco.pop("lint", None)
    limpo = _sem_rastro_local(limpo)
    limpo["peca"] = rotulo
    for arquivado in (limpo.get("ciclos") or []):
        if isinstance(arquivado, dict):
            arquivado["peca"] = "Caso " + codigo
    limpo["publicado_pseudonimizado"] = True

    sobrou = varrer(limpo)
    bruto = json.dumps(limpo, ensure_ascii=False)
    for t in vedados:
        if re.search(re.escape(t), bruto, flags=re.I):
            sobrou.append({"onde": "estado", "tipo": "termo vedado", "trecho": t})
    if sobrou:
        detalhe = "; ".join("%s em %s" % (a["tipo"], a["onde"]) for a in sobrou[:5])
        raise ValueError("FALHA DE PSEUDONIMIZACAO: %d identificador(es) sobreviveram a mascara "
                         "(%s). A publicacao foi RECUSADA — corrija a origem antes de publicar."
                         % (len(sobrou), detalhe))
    caminhos = caminhos_absolutos(limpo)
    if caminhos:
        raise ValueError("FALHA DE PSEUDONIMIZACAO: caminho absoluto no estado a publicar (%s). A "
                         "pasta do caso e o usuario da maquina identificam o caso: tire o caminho "
                         "desse texto antes de publicar. A publicacao foi RECUSADA."
                         % "; ".join(caminhos[:5]))
    return limpo


def _injetar(texto, estado, state_path):
    'Estado no marcador do BOOT (obrigatorio quando ha estado) e caminho no do STATE_PATH.'


    if estado is not None and PLACEHOLDER not in texto:
        raise ValueError("painel sem o marcador de estado inline (%r)" % PLACEHOLDER)
    if state_path and PLACEHOLDER_CAMINHO in texto:
        texto = texto.replace(PLACEHOLDER_CAMINHO,
                              json_para_script(os.path.abspath(state_path)), 1)
    if estado is not None:
        texto = texto.replace(PLACEHOLDER, json_para_script(estado), 1)
    return texto


def montar(painel_html, estado=None, state_path=None):
    """painel completo (+ estado opcional) -> fragmento. Levanta ValueError se faltar peca."""
    m_style = re.search(r"<style>(.*?)</style>", painel_html, re.S)
    if not m_style:
        raise ValueError("painel sem bloco <style>")
    m_corpo = re.search(r"<body[^>]*>(.*?)<script", painel_html, re.S)
    if not m_corpo:
        raise ValueError("painel sem conteudo entre <body> e <script>")
    m_script = re.search(r"<script>(.*?)</script>", painel_html, re.S)
    if not m_script:
        raise ValueError("painel sem bloco <script>")


    estilo = re.sub(r"(?m)^(\s*)body\s*\{", r"\1.%s {" % WRAPPER, m_style.group(1))
    corpo = m_corpo.group(1)
    script = m_script.group(1)

    script = _injetar(script, estado, state_path)

    frag = "<style>%s</style>\n<div class=\"%s\">%s</div>\n<script>%s</script>\n" % (
        estilo, WRAPPER, corpo, script)


    for proibido in ("<!DOCTYPE", "<html", "<head", "<body"):
        if proibido.lower() in frag.lower():
            raise ValueError("fragmento ainda contem %r — conversao incompleta" % proibido)
    return frag


def montar_documento(painel_html, estado, state_path=None):
    """Painel COMPLETO com o estado embutido — superficie de reserva (abre no navegador)."""
    if estado is None:
        return painel_html
    return _injetar(painel_html, estado, state_path)










CORTE_WIDGET, CORTE_WIDGET_CICLO = 600, 300
TEXTOS_LONGOS = ("fundamentacao", "argumento_debate", "argumento", "fundamento", "texto")
SEM_RENDER = ("painel", "lint")




LIMITE_WIDGET = 150 * 1024
AVISO_WIDGET = (
    "o plenario tem %d bytes, acima de 150 KB: no widget, mostre o PLACAR (--placar) e entregue o "
    "PAINEL_CONSELHO.html (--documento) com o plenario inteiro, em vez de colar este fragmento.")


def _cortar(texto, corte):
    return texto if len(texto) <= corte else texto[:corte - 1].rstrip() + "…"


def _cortar_textos(o, corte):
    if isinstance(o, dict):
        return {k: (_cortar(v, corte) if k in TEXTOS_LONGOS and isinstance(v, str)
                    else _cortar_textos(v, corte)) for k, v in o.items()}
    if isinstance(o, list):
        return [_cortar_textos(v, corte) for v in o]
    return o


def projetar(estado):
    """Estado -> o que vai ao fragmento do widget (copia; o estado de origem nao muda)."""
    if not isinstance(estado, dict):
        return estado
    proj = _cortar_textos({k: v for k, v in estado.items() if k not in ("ciclos",) + SEM_RENDER},
                          CORTE_WIDGET)
    if isinstance(estado.get("ciclos"), list):
        proj["ciclos"] = [_cortar_textos({k: v for k, v in c.items() if k not in SEM_RENDER}
                                         if isinstance(c, dict) else c, CORTE_WIDGET_CICLO)
                          for c in estado["ciclos"]]
    return proj








PASSOS_PLACAR = (("distribuicao", "Distribuição"), ("debate", "Debate"), ("votacao", "Votação"),
                 ("apreciacao", "Proclamação"), ("fim", "Decisão"))
VOGAIS_PLACAR = (("merito", "Mérito"), ("coerencia", "Coerência"), ("escrita", "Escrita"),
                 ("conformidade", "Conformidade"))


STATUS_PLACAR = {"analisando": "em análise", "debatendo": "em debate", "decidiu": "votou"}
VOTOS_PLACAR = ("aprovar", "devolver")
CSS_PLACAR = (
    ".dsr-placar{font:13px/1.45 'Segoe UI',system-ui,sans-serif;color:#1d2433;background:#f6f7fb;"
    "border:1px solid #e3e6ef;border-radius:12px;padding:12px 14px}"
    ".dsr-placar .t{display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px}"
    ".dsr-placar .t b{color:#8c2f2f}.dsr-placar .m{color:#6b7385;font-size:12px}"
    ".dsr-placar .s{margin:6px 0;font-size:12px;color:#6b7385}"
    ".dsr-placar .s .on{color:#fff;background:#1d2433;border-radius:6px;padding:1px 6px}"
    ".dsr-placar .s .ok{background:#1f8a4c}.dsr-placar .s .no{background:#c23434}"
    ".dsr-placar table{border-collapse:collapse;width:100%;margin:4px 0 6px}"
    ".dsr-placar td{padding:3px 6px;border-top:1px solid #e3e6ef}"
    ".dsr-placar .v{border-radius:99px;padding:1px 9px;font-weight:650;font-size:11.5px}"
    ".dsr-placar .aprovar{background:#e6f6ec;color:#1f8a4c}"
    ".dsr-placar .devolver{background:#fbe9e9;color:#c23434}"
    ".dsr-placar .pend{background:#eef0f6;color:#6b7385}"
    ".dsr-placar .p{font-weight:650}.dsr-placar .p.pend{color:#a3561b}"
    ".dsr-placar ul{margin:4px 0 0 16px;padding:0;font-size:12px}"
    ".dsr-placar small{color:#6b7385}")


JS_PLACAR = (
    "(function(){var p=function(n){return(n<10?'0':'')+n};"
    "var t=document.querySelectorAll('.dsr-placar time[datetime]');"
    "for(var i=0;i<t.length;i++){var d=new Date(t[i].getAttribute('datetime'));"
    "if(isNaN(d.getTime()))continue;t[i].textContent=(t[i].className==='h'?'':"
    "p(d.getDate())+'/'+p(d.getMonth()+1)+' ')+p(d.getHours())+':'+p(d.getMinutes())}})();")
CORTE_PLACAR = 160


def _txt(valor, corte=CORTE_PLACAR):
    'Valor do estado como TEXTO no HTML do placar: escapado e cortado. O corte e em BYTES e'



    if isinstance(valor, (dict, list)) or valor is None:
        s = ""
    else:
        s = valor if isinstance(valor, str) else str(valor)

    def medida(t):
        return len(_html.escape(t, quote=True).encode("utf-8"))
    if medida(s) <= corte:
        return _html.escape(s, quote=True)

    lo, hi = 0, len(s)
    while lo < hi:
        meio = (lo + hi + 1) // 2
        if medida(s[:meio].rstrip()) + 3 <= corte:
            lo = meio
        else:
            hi = meio - 1
    return _html.escape(s[:lo].rstrip(), quote=True) + "…"


def _instante(iso):
    """datetime de um carimbo ISO (com ou sem fuso; o 'Z' do UTC tambem), ou None."""
    if not isinstance(iso, str) or not iso.strip():
        return None
    try:
        return datetime.fromisoformat(iso.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _tempo(iso, so_hora=False):
    """<time> com o carimbo no atributo e, no texto, a hora do relogio que gravou."""
    d = _instante(iso)
    if d is None:
        return ""
    return '<time %sdatetime="%s">%s</time>' % (
        'class="h" ' if so_hora else "", _html.escape(iso.strip(), quote=True),
        d.strftime("%H:%M" if so_hora else "%d/%m %H:%M"))


def _chip_voto(voto):
    if voto in ("aprovar", "devolver"):
        return '<span class="v %s">%s</span>' % (voto, "Aprovar" if voto == "aprovar" else "Devolver")
    return '<span class="v pend">aguardando voto</span>'


def _lista(v):
    """Lista de objetos do estado; o que nao e lista (estado fora do contrato) vira []."""
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _str(v):
    return v if isinstance(v, str) else ""


def _status_assento(v, padrao):
    'Status do assento no placar. Quem reviu o voto na apreciacao reaberta pelo art. 942 (§ 2º'



    if (v.get("voto_anterior") in VOTOS_PLACAR and v.get("voto") in VOTOS_PLACAR
            and v.get("voto_anterior") != v.get("voto")):
        return "revisou o voto"
    return _str(v.get("status")) or padrao


def _status_placar(st, fase):
    st = _str(st)
    if st == "apreciando":
        return "apurando os votos" if fase == "apreciacao" else "em análise"
    return STATUS_PLACAR.get(st, st)


def assentos_942(art):
    'Os assentos da ampliacao na ordem dos cartoes: (registro, status). Os que votaram'



    extras = _lista(art.get("votos_extra"))
    votados = {_str(v.get("assento")) for v in extras} - {""}
    conv = [c for c in _lista(art.get("convocados")) if _str(c.get("assento")) not in votados]
    todos = ([(v, "votou" if v.get("voto") in VOTOS_PLACAR else "aguardando") for v in extras]
             + [(c, "em debate" if c.get("status") == "debatendo" else "em análise") for c in conv])
    ordem = [s for s in art.get("novos") if isinstance(s, str)] if isinstance(art.get("novos"), list) else []

    def posicao(par):
        a = _str(par[0].get("assento"))
        return ordem.index(a) if a in ordem else len(ordem)
    return sorted(todos, key=posicao)


def _voto_valido(v):
    """Voto como o conselho_gate.py o conta: aprovar/devolver, com fundamentacao e agente_id."""
    fund = v.get("fundamentacao")
    return (v.get("voto") in VOTOS_PLACAR and bool(_str(v.get("agente_id")).strip())
            and isinstance(fund, (str, int, float)) and bool(str(fund).strip()))


def reaberta(estado):
    'A apreciacao foi reaberta pelo art. 942 (linha `tipo: reabertura` da ata): o julgamento'


    return any(e.get("tipo") == "reabertura" for e in _lista(estado.get("eventos")))


def contados(estado):
    '(aprovar, devolver) CONTADOS dos votos, a mesma conta do contagem() do plenario; o'





    cad = {c.get("id"): c for c in _lista(estado.get("cadeiras")) if isinstance(c.get("id"), str)}
    rel = estado.get("relator") if isinstance(estado.get("relator"), dict) else {}
    art = estado.get("art942") if isinstance(estado.get("art942"), dict) else {}
    base = [v if v in VOTOS_PLACAR else None
            for v in [cad.get(cid, {}).get("voto") for cid, _n in VOGAIS_PLACAR] + [rel.get("voto")]]
    if estado.get("fase") in ("aprovado", "devolvido"):
        extras = [] if len(set(base)) == 1 and not reaberta(estado) else [
            v.get("voto") for v in _lista(art.get("votos_extra")) if _voto_valido(v)][:2]
    else:
        extras = [v.get("voto") for v, st in assentos_942(art) if st == "votou"]
    votos = base + extras
    return votos.count("aprovar"), votos.count("devolver")


def pendencia(estado):
    'O que falta para a proclamacao valer, pela regra do conselho_gate.py, ou "". Turma'






    cad = {c.get("id"): c for c in _lista(estado.get("cadeiras")) if isinstance(c.get("id"), str)}
    rel = estado.get("relator") if isinstance(estado.get("relator"), dict) else {}
    faltam = [nome for cid, nome in VOGAIS_PLACAR if not _voto_valido(cad.get(cid, {}))]
    if not _voto_valido(rel):
        faltam.append("Relator")
    if faltam:
        return "Turma incompleta: falta o voto de " + ", ".join(faltam)
    base = [cad[cid] for cid, _n in VOGAIS_PLACAR] + [rel]
    unanime = len({v["voto"] for v in base}) == 1 and not reaberta(estado)
    art = estado.get("art942") if isinstance(estado.get("art942"), dict) else {}
    extras = [v for v in _lista(art.get("votos_extra")) if _voto_valido(v)]
    ids = [_str(v.get("agente_id")).strip() for v in base + ([] if unanime else extras[:2])]
    isolamento = estado.get("isolamento") if isinstance(estado.get("isolamento"), dict) else {}
    if _str(estado.get("autor_id")).strip() in ids:
        return "Turma inválida: autor entre os votantes"
    if len(set(ids)) < len(ids):
        return "Turma inválida: agente em dois assentos"
    if estado.get("risco") == "alto" and isolamento.get("modo") != "subagentes":
        return "Turma inválida: modo serial em risco alto"
    if not unanime and (not art.get("acionado") or len(extras) < 2):
        return "Ampliação do art. 942 pendente: votação não unânime sem os dois votos da ampliação"
    a, d = contados(estado)
    if estado.get("fase") in ("aprovado", "devolvido") and estado["fase"] != (
            "devolvido" if d >= a else "aprovado"):
        return "Resultado proclamado diverge dos votos: %d×%d" % (a, d)
    return ""


def _sem_nome(quem, texto):
    'A regra do semNome() do plenario, para as duas vias do mesmo instante dizerem o mesmo: o'


    if not (isinstance(quem, str) and quem and isinstance(texto, str) and texto.startswith(quem)):
        return texto
    resto = texto[len(quem):]
    return re.sub(r"^[:\s]+", "", resto) if re.match(r"[:\s]+\S", resto) else texto


def montar_placar(estado):
    """Estado -> fragmento compacto do placar (comeca com <style>, sem canvas e sem ciclos)."""
    if not isinstance(estado, dict):
        raise ValueError("estado ilegivel para o placar")
    fase = estado.get("fase")
    final = fase in ("aprovado", "devolvido")
    chaves = [p for p, _ in PASSOS_PLACAR]

    passo = 4 if final else (chaves.index(fase) if fase in chaves else 0)


    pend = pendencia(estado) if final else ""
    passos = []
    for i, (_chave, rotulo) in enumerate(PASSOS_PLACAR):
        if i == 4 and final:
            rotulo = "Aprovada" if fase == "aprovado" else "Devolvida"
        if i == passo:
            cls = "on" + ((" ok" if fase == "aprovado" else " no") if final and not pend else "")
            passos.append('<b class="%s">%s</b>' % (cls, rotulo))
        else:
            passos.append(rotulo + (" ✓" if i < passo else ""))


    cad = {c.get("id"): c for c in _lista(estado.get("cadeiras")) if isinstance(c.get("id"), str)}
    linhas = []
    for cid, nome in VOGAIS_PLACAR:
        c = cad.get(cid, {})
        linhas.append((_txt(nome), _status_assento(c, "votou" if c.get("voto") else "—"),
                       c.get("voto")))
    rel = estado.get("relator") if isinstance(estado.get("relator"), dict) else {}
    linhas.append(("Relator", _status_assento(rel, "decidiu" if rel.get("voto") else "aguardando"),
                   rel.get("voto")))
    art = estado.get("art942") if isinstance(estado.get("art942"), dict) else {}
    assentos = assentos_942(art)
    esperados = 5
    if art.get("acionado") or assentos:


        esperados = 7
        for i in range(2):
            v, st = assentos[i] if i < len(assentos) else ({}, "aguardando")
            nome = "Art. 942 (%d)" % (i + 1)
            if v.get("assento"):
                nome += " <small>%s</small>" % _txt(v["assento"], 40)
            linhas.append((nome, st, v.get("voto") if st == "votou" else None))
    tabela = "".join("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        nome, _txt(_status_placar(st, fase), 40), _chip_voto(voto)) for nome, st, voto in linhas)




    a, d = contados(estado)
    classe_placar = "p"
    if final:
        classe_placar += " pend" if pend else ""
        placar = "Placar: %d×%d — %s" % (
            a, d, _txt(pend[:1].lower() + pend[1:], 200) if pend
            else ("aprovada por maioria" if fase == "aprovado" else "devolvida por maioria"))
    elif a + d:
        placar = "Placar parcial: %d aprovar × %d devolver · %d de %d votos" % (a, d, a + d, esperados)
    else:
        placar = "Placar parcial: nenhum voto registrado · 0 de %d votos" % esperados

    eventos = _lista(estado.get("eventos"))[-3:]
    andamentos = "".join(
        "<li>%s <b>%s</b> — %s</li>" % (_tempo(e.get("em"), so_hora=True) or _txt(e.get("hora"), 8),
                                         _txt(e.get("quem"), 40),
                                         _txt(_sem_nome(e.get("quem"), e.get("texto"))))
        for e in reversed(eventos)) or "<li>Nenhum andamento registrado ainda.</li>"


    quando = estado.get("atualizado") if _instante(estado.get("atualizado")) else next(
        (e.get("em") for e in reversed(eventos) if _instante(e.get("em"))), "")
    momento = _tempo(quando)
    rotulo = ("instantâneo de " + momento) if momento else "instantâneo sem horário registrado"
    rotulo += " — decisão" if final else " — sessão em andamento"

    return (
        "<style>%s</style>\n<div class=\"dsr-placar\">"
        "<div class=\"t\"><span><b>Conselho Revisor</b> · Ciclo %s</span>"
        "<span class=\"m\">%s</span></div>"
        "<div><b>Peça:</b> %s</div>"
        "<div class=\"s\">%s</div>"
        "<table>%s</table>"
        "<div class=\"%s\">%s</div>"
        "<ul>%s</ul></div>\n<script>%s</script>\n" % (
            CSS_PLACAR, _txt(estado.get("ciclo") or "—", 12), rotulo,
            _txt(estado.get("peca") or "—"), " › ".join(passos), tabela, classe_placar, placar,
            andamentos, JS_PLACAR))




def agora_iso():
    'Instante corrente com FUSO (2026-10-27T10:33:59-03:00; na nuvem, +00:00). Carimbo sem'

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def contar_votos(estado):
    'Votos registrados: cadeiras com voto + relator com voto + votos extras do art. 942 (a'

    if not isinstance(estado, dict):
        return 0
    n = sum(1 for c in _lista(estado.get("cadeiras")) if c.get("voto"))
    if isinstance(estado.get("relator"), dict) and estado["relator"].get("voto"):
        n += 1
    art = estado.get("art942")
    if isinstance(art, dict):
        n += sum(1 for v in _lista(art.get("votos_extra")) if v.get("voto"))
    return n







TRAVA_ESPERA, TRAVA_PASSO, TRAVA_VELHA = 5.0, 0.025, 30.0


TROCA_TENTATIVAS, TROCA_PASSO = 40, 0.025


class EstadoOcupado(ValueError):
    """A trava do estado nao saiu na espera: outro comando grava a sessao agora."""
    resultado = "estado_ocupado"


def _ler_trava(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            d = json.loads(f.read())
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _trava_velha(caminho, info, agora):
    if info is None:

        try:
            return agora - os.stat(caminho).st_mtime > TRAVA_VELHA
        except OSError:
            return False
    try:
        return agora - float(info.get("em") or 0) > TRAVA_VELHA
    except (TypeError, ValueError):
        return True


def _tirar_trava_velha(caminho, info):
    'A trava julgada velha sai do lugar por RENOMEACAO para um nome unico, e so e descartada se'

    lixo = "%s.velha-%d-%d" % (caminho, os.getpid(), time.time_ns())
    try:
        os.rename(caminho, lixo)
    except OSError:
        return
    if _ler_trava(lixo) != info:
        try:
            os.rename(lixo, caminho)
        except OSError:
            pass
        return
    try:
        os.remove(lixo)
    except OSError:
        pass


@contextlib.contextmanager
def trava_do_estado(state_path):
    caminho = os.path.abspath(state_path) + ".lock"
    limite = time.monotonic() + TRAVA_ESPERA
    while True:
        try:
            fd = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            info = _ler_trava(caminho)
            if _trava_velha(caminho, info, time.time()):
                _tirar_trava_velha(caminho, info)
        except PermissionError:
            pass
        if time.monotonic() >= limite:
            raise EstadoOcupado(
                "o CONSELHO_STATUS.json esta em uso por outro comando (%s ha mais de %d s); nada "
                "foi gravado. Rode de novo este comando quando o outro terminar; se nenhum outro "
                "comando do Conselho estiver rodando, a trava e de um comando interrompido e vence "
                "sozinha em %d s: repita depois disso. Um comando do Conselho por vez, nunca em "
                "paralelo." % (os.path.basename(caminho), TRAVA_ESPERA, TRAVA_VELHA))
        time.sleep(TRAVA_PASSO)
    meu = {"pid": os.getpid(), "em": time.time()}
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(meu))
    except BaseException:


        _soltar_trava(caminho)
        raise
    try:
        yield
    finally:
        if _ler_trava(caminho) == meu:
            _soltar_trava(caminho)


def _soltar_trava(caminho):
    'Apaga a trava, repetindo no PermissionError: no Windows quem espera a abre para ler o'

    for tentativa in range(TROCA_TENTATIVAS):
        try:
            os.remove(caminho)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if tentativa == TROCA_TENTATIVAS - 1:
                return
            time.sleep(TROCA_PASSO)
        except OSError:
            return


def _ler_texto(caminho):
    """Texto do arquivo, repetindo a leitura que cruza a troca atomica de quem grava (Windows)."""
    for tentativa in range(TROCA_TENTATIVAS):
        try:
            with open(caminho, encoding="utf-8") as f:
                return f.read()
        except PermissionError:
            if tentativa == TROCA_TENTATIVAS - 1:
                raise
            time.sleep(TROCA_PASSO)


def _gravar_atomico(caminho, conteudo):
    'Temporario na MESMA pasta, flush+fsync e `os.replace`: quem le no meio ve o arquivo antigo'


    pasta = os.path.dirname(os.path.abspath(caminho))
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(caminho) + ".", suffix=".tmp",
                               dir=pasta)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(conteudo)
            f.flush()
            os.fsync(f.fileno())
        try:
            modo = stat.S_IMODE(os.stat(caminho).st_mode)
        except OSError:

            mascara = os.umask(0)
            os.umask(mascara)
            modo = 0o666 & ~mascara
        try:
            os.chmod(tmp, modo)
        except OSError:
            pass
        for tentativa in range(TROCA_TENTATIVAS):
            try:
                os.replace(tmp, caminho)
                break
            except PermissionError:
                if tentativa == TROCA_TENTATIVAS - 1:
                    raise
                time.sleep(TROCA_PASSO)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _anotar(state_path, estado, ts, via, emissao=None):
    'Acrescenta o movimento (e, com `emissao`, a emissao da fase) ao estado RELIDO do disco.'






    fase = estado.get("fase") if isinstance(estado, dict) else None
    if not (isinstance(fase, str) and fase.strip()):
        raise ValueError("estado sem 'fase' — nao ha o que registrar (rode `conselho_sessao.py fase` antes)")
    fase = fase.strip()
    em = ts.strip() if isinstance(ts, str) and ts.strip() else agora_iso()
    votos = contar_votos(estado)
    eventos_len = len(estado["eventos"]) if isinstance(estado.get("eventos"), list) else 0
    with trava_do_estado(state_path):
        try:
            disco = json.loads(_ler_texto(state_path))
        except ValueError as e:
            raise ValueError("CONSELHO_STATUS.json ilegivel no disco na hora de registrar (%s); "
                             "nada foi gravado" % e)
        if not isinstance(disco, dict):
            raise ValueError("CONSELHO_STATUS.json no disco nao e objeto; nada foi gravado")
        bloco = disco.get("painel") if isinstance(disco.get("painel"), dict) else {}
        disco["painel"] = bloco
        reg = None
        if emissao is not None:
            superficie, caminho = emissao
            emissoes = bloco.get("emissoes") if isinstance(bloco.get("emissoes"), list) else []
            reg = {"fase": fase, "superficie": superficie, "em": em, "votos": votos,
                   "eventos_len": eventos_len}
            if caminho:
                reg["caminho"] = caminho
            for i, e in enumerate(emissoes):
                if isinstance(e, dict) and e.get("fase") == fase and e.get("superficie") == superficie:
                    emissoes[i] = reg
                    break
            else:
                emissoes.append(reg)
            bloco["emissoes"] = emissoes
        movimentos = bloco.get("movimentos") if isinstance(bloco.get("movimentos"), list) else []
        mov = {"via": via, "fase": fase, "votos": votos, "eventos_len": eventos_len, "em": em}
        movimentos.append(mov)
        bloco["movimentos"] = movimentos
        _gravar_atomico(state_path, json.dumps(disco, ensure_ascii=False, indent=2))
    return reg, mov


def registrar_emissao(state_path, estado, superficie, caminho="", ts=None, via="fragmento"):
    'Anota a emissao do PLENARIO da fase corrente (`painel.emissoes`, idempotente por (fase,'


    return _anotar(state_path, estado, ts, via, (superficie, caminho))[0]


def registrar_movimento(state_path, estado, via, ts=None):
    """So o movimento (o placar): a emissao da fase e do plenario."""
    return _anotar(state_path, estado, ts, via)[1]


def main():
    ap = argparse.ArgumentParser(description="Fragmento do painel do Conselho (Dissero)")
    ap.add_argument("--painel", default=MODELO_PADRAO,
                    help="modelo do plenario; sem a opcao, o da propria skill "
                         "(references/painel-conselho.html)")
    ap.add_argument("--state")
    ap.add_argument("--saida")
    ap.add_argument("--documento", help="grava tambem o painel COMPLETO (superficie de reserva)")
    ap.add_argument("--registrar", action="store_true",
                    help="anota a emissao desta fase em painel.emissoes do CONSELHO_STATUS.json "
                         "(o conselho_gate.py --painel confere) e o movimento em painel.movimentos")
    ap.add_argument("--placar", action="store_true",
                    help="em vez do plenario, o PLACAR compacto para o widget a cada voto; com "
                         "--registrar anota so o movimento (via placar), nunca a emissao da fase")
    ap.add_argument("--ts")
    ap.add_argument("--publico", action="store_true",
                    help="prepara o estado para PUBLICACAO EXTERNA (Artifact): substitui a peca "
                         "pelo codigo do caso, mascara identificadores na ata e nos ciclos, e "
                         "RECUSA se algum sobreviver a mascara. Exige --codigo-caso.")
    ap.add_argument("--codigo-caso",
                    help="rotulo opaco do caso na versao publicada (ex.: 'A-17'). Nunca CNJ, "
                         "nome de parte ou numero de minuta.")
    ap.add_argument("--termos-vedados",
                    help="termos que NAO podem sair, separados por ';' (nome de parte, do "
                         "incidente, do programa). Regex reconhece identificador FORMATADO; "
                         "NOME nao tem forma, e so sai daqui se for NOMEADO aqui.")
    ap.add_argument("--session-id", dest="session_id",
                    help="id da sessao do harness: localiza a pasta do caso registrada para ela "
                         "quando --state, --saida ou --documento vem de nome nu")
    args = ap.parse_args()


    try:
        args.state = no_caso(args.state, args.session_id)
        args.saida = no_caso(args.saida, args.session_id, leitura=False, opcao="--saida")
        args.documento = no_caso(args.documento, args.session_id, leitura=False,
                                 opcao="--documento")
    except CaminhoRecusado as e:
        print(json.dumps({"ok": False, "resultado": e.resultado, "erro": str(e)},
                         ensure_ascii=False))
        return 2


    html = ""
    if not args.placar or args.documento:
        if not os.path.isfile(args.painel):
            return _erro(MSG_MODELO_AUSENTE % args.painel)
        try:
            html = ler_modelo(args.painel)
        except ModeloIncompleto as e:
            return _erro(str(e))
        except OSError as e:
            return _erro("falha ao ler o painel: %s" % e)

    estado = None
    if args.state:
        if not os.path.isfile(args.state):
            return _erro("estado nao encontrado: %s" % args.state)
        try:
            estado = json.loads(_ler_texto(args.state))
        except Exception as e:
            return _erro("CONSELHO_STATUS.json ilegivel: %s" % e)



    pseudonimizado = False
    if args.publico:
        if estado is None:
            return _erro("--publico exige --state (nao ha o que pseudonimizar sem estado)")
        try:
            _vedados = [t for t in (args.termos_vedados or "").split(";") if t.strip()]
            estado = pseudonimizar(estado, args.codigo_caso, _vedados)
            pseudonimizado = True
        except ValueError as e:
            return _erro(str(e))
    elif args.codigo_caso:
        return _erro("--codigo-caso so faz sentido com --publico")

    if args.placar and estado is None:
        return _erro("--placar exige --state (o placar e o da sessao)")
    if args.registrar and estado is None:
        return _erro("--registrar exige --state (a emissao e por FASE da sessao)")


    caminho_estado = None if pseudonimizado else args.state
    try:

        frag = (montar_placar(estado) if args.placar
                else montar(html, projetar(estado), caminho_estado))
    except ValueError as e:
        return _erro(str(e))
    except (TypeError, AttributeError) as e:
        return _erro("CONSELHO_STATUS.json fora do contrato (forma inesperada: %s); corrija o "
                     "estado pelo conselho_sessao.py" % e)
    tamanho = len(frag.encode("utf-8"))
    aviso = AVISO_WIDGET % tamanho if not args.placar and tamanho > LIMITE_WIDGET else ""




    documento = ""
    if args.documento:
        try:
            _gravar_atomico(args.documento, montar_documento(html, estado, caminho_estado))
            documento = args.documento
        except (ValueError, OSError) as e:
            return _erro("falha ao gravar o documento autonomo: %s" % e)
    if args.saida:
        try:
            _gravar_atomico(args.saida, frag)
        except OSError as e:
            return _erro("falha ao gravar a saida: %s" % e)

    emissao = movimento = None
    if args.registrar:
        try:
            if args.placar:
                movimento = registrar_movimento(args.state, estado, "placar", args.ts)
            else:
                emissao, movimento = _anotar(args.state, estado, args.ts,
                                             "documento" if documento else "fragmento",
                                             ("fragmento", documento))
        except EstadoOcupado as e:
            print(json.dumps({"ok": False, "resultado": e.resultado, "erro": str(e)},
                             ensure_ascii=False))
            return 2
        except (ValueError, OSError) as e:
            return _erro("falha ao registrar a emissao: %s" % e)

    if args.saida:




        resposta = {"ok": True, "saida": args.saida, "bytes": tamanho,
                    "com_estado": estado is not None, "placar": bool(args.placar),
                    "documento": documento, "emissao": emissao, "movimento": movimento,
                    "pseudonimizado": pseudonimizado,
                    "codigo_caso": (args.codigo_caso or "").strip() if pseudonimizado else "",
                    "como_exibir": COMO_EXIBIR}
        if aviso:
            resposta["aviso"] = aviso
        print(json.dumps(resposta, ensure_ascii=False))
    else:
        if aviso:

            sys.stderr.write(json.dumps({"aviso": aviso}, ensure_ascii=False) + "\n")
        sys.stdout.write(frag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
