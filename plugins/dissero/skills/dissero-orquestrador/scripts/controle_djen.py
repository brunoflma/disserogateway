#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'controle_djen.py - o que o escritório já fez com cada comunicação do DJEN.'







































import argparse
import json
import os
import sys
import tempfile
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numero_cnj

FORMATO = "dsr.djen.controle.v1"
VARIAVEL_ARQUIVO = "DSR_DJEN_CONTROLE"
ARQUIVO_PADRAO = os.path.join("~", ".config", "dissero", "djen", "controle.json")
SITUACOES = ("pendente", "visto", "delegado", "cumprido", "arquivado")
ENCERRADAS = frozenset({"cumprido", "arquivado"})


class RecusaControle(Exception):
    """Pedido recusado, com código estável (`codigo`) e explicação para o advogado."""

    def __init__(self, codigo, mensagem):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def onde_fica(arquivo=None):
    """Caminho absoluto do controle: o argumento, a variável de ambiente ou o padrão."""
    escolhido = arquivo or os.environ.get(VARIAVEL_ARQUIVO) or ARQUIVO_PADRAO
    return os.path.abspath(os.path.expanduser(escolhido))


def _vazio():
    return {"schema_version": FORMATO, "itens": {}}


def _abrir_controle(arquivo):
    """Conteúdo do controle. Arquivo ausente é controle vazio; ilegível é recusa."""
    if not os.path.exists(arquivo):
        return _vazio()
    try:
        with open(arquivo, encoding="utf-8") as fh:
            dados = json.load(fh)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise RecusaControle(
            "arquivo_ilegivel",
            "O controle em %s está ilegível (%s). Nada foi gravado por cima dele. Corrija ou "
            "mova o arquivo e repita." % (arquivo, exc.__class__.__name__))
    if (not isinstance(dados, dict) or not isinstance(dados.get("itens"), dict)
            or dados.get("schema_version", FORMATO) != FORMATO):
        raise RecusaControle(
            "formato_desconhecido",
            "O arquivo %s não está no formato %s. Nada foi gravado por cima dele." % (arquivo, FORMATO))
    return dados


def _salvar_controle(arquivo, dados):
    pasta = os.path.dirname(arquivo)
    try:
        os.makedirs(pasta, exist_ok=True)
        descritor, provisorio = tempfile.mkstemp(prefix=".controle-", suffix=".tmp", dir=pasta)
        with os.fdopen(descritor, "w", encoding="utf-8") as fh:
            json.dump(dados, fh, ensure_ascii=False, indent=2)
        os.replace(provisorio, arquivo)
    except OSError as exc:
        raise RecusaControle("gravacao_falhou",
                             "Não foi possível gravar o controle em %s (%s)." % (arquivo, exc))


def _chave(id_comunicacao):
    chave = str(id_comunicacao if id_comunicacao is not None else "").strip()
    if not chave:
        raise RecusaControle("id_vazio", "Informe o id da comunicação, como saiu do consultar_djen.py.")
    return chave


def registrar(id_comunicacao, situacao, para=None, nota=None, processo=None, arquivo=None,
              momento=None):
    'Grava a nova situação de uma comunicação e devolve o registro dela.'



    chave = _chave(id_comunicacao)
    if situacao not in SITUACOES:
        raise RecusaControle("situacao_desconhecida",
                             "Situação '%s' não existe. Use uma destas: %s." % (situacao, ", ".join(SITUACOES)))
    responsavel = (para or "").strip() or None
    if situacao == "delegado" and not responsavel:
        raise RecusaControle("delegacao_sem_responsavel",
                             "Para delegar, diga quem recebe a publicação com --para \"Nome\".")
    numero = None
    if processo:
        if not numero_cnj.validar(processo):
            raise RecusaControle("processo_invalido",
                                 "O número %s não fecha o dígito verificador do CNJ. Confira o "
                                 "número na comunicação e repita." % processo)
        numero = numero_cnj.formatar(processo)

    caminho = onde_fica(arquivo)
    dados = _abrir_controle(caminho)
    quando = momento or datetime.now().isoformat(timespec="seconds")
    texto_nota = (nota or "").strip() or None

    anterior = dados["itens"].get(chave) or {}
    passo = {"status": situacao, "em": quando}
    if responsavel and situacao == "delegado":
        passo["para"] = responsavel
    if texto_nota:
        passo["nota"] = texto_nota
    historico = list(anterior.get("historico") or []) + [passo]

    registro = {
        "id": chave,
        "status": situacao,
        "processo": numero or anterior.get("processo"),
        "delegado_para": responsavel if situacao == "delegado" else None,
        "nota": texto_nota or anterior.get("nota"),
        "atualizado_em": quando,
        "historico": historico,
    }
    dados["itens"][chave] = registro
    _salvar_controle(caminho, dados)
    return registro


def registro_de(id_comunicacao, arquivo=None):
    """O registro de uma comunicação, ou None quando ela nunca foi marcada."""
    return _abrir_controle(onde_fica(arquivo))["itens"].get(_chave(id_comunicacao))


def registros_dos_ids(ids, arquivo=None):
    """{id: registro} só das comunicações de `ids` que têm registro."""
    itens = _abrir_controle(onde_fica(arquivo))["itens"]
    pedidos = {str(i).strip() for i in ids if str(i).strip()}
    return {chave: itens[chave] for chave in pedidos if chave in itens}


def registros(situacao=None, arquivo=None):
    """Registros do controle, do mais antigo para o mais recente; filtra por situação."""
    if situacao is not None and situacao not in SITUACOES:
        raise RecusaControle("situacao_desconhecida",
                             "Situação '%s' não existe. Use uma destas: %s." % (situacao, ", ".join(SITUACOES)))
    itens = _abrir_controle(onde_fica(arquivo))["itens"].values()
    escolhidos = [r for r in itens if situacao is None or r.get("status") == situacao]
    return sorted(escolhidos, key=lambda r: (str(r.get("atualizado_em") or ""), str(r.get("id"))))


def _imprimir(dados):
    print(json.dumps(dados, ensure_ascii=False))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Situação de trabalho das comunicações do DJEN no escritório (arquivo local, "
                    "fora do repositório).")
    ap.add_argument("--marcar", metavar="ID",
                    help="id da comunicação na saída do consultar_djen.py (o hash também serve)")
    ap.add_argument("--status", choices=SITUACOES,
                    help="situação a gravar com --marcar, ou filtro de --listar")
    ap.add_argument("--para", help="nome de quem fica com a comunicação; exigido com --status delegado")
    ap.add_argument("--nota", help="anotação livre, guardada no histórico")
    ap.add_argument("--processo", help="número CNJ da comunicação, para identificar a linha na lista")
    ap.add_argument("--listar", action="store_true", help="lista os registros (todos, ou os de --status)")
    ap.add_argument("--caminho", action="store_true", help="imprime o caminho do arquivo do controle")
    ap.add_argument("--arquivo", help="arquivo do controle (padrão: $%s ou %s)"
                    % (VARIAVEL_ARQUIVO, ARQUIVO_PADRAO.replace(os.sep, "/")))
    args = ap.parse_args(argv)

    caminho = onde_fica(args.arquivo)
    try:
        if args.caminho:
            _imprimir({"ok": True, "caminho": caminho, "existe": os.path.isfile(caminho)})
            return 0
        if args.marcar is not None:
            if not args.status:
                _imprimir({"ok": False, "erro": "situacao_ausente",
                           "mensagem": "Com --marcar, diga a situação com --status."})
                return 2
            registro = registrar(args.marcar, args.status, para=args.para, nota=args.nota,
                                 processo=args.processo, arquivo=args.arquivo)
            _imprimir({"ok": True, "item": registro, "caminho": caminho})
            return 0
        if args.listar:
            lista = registros(args.status, arquivo=args.arquivo)
            _imprimir({"ok": True, "total": len(lista), "itens": lista, "caminho": caminho})
            return 0
    except RecusaControle as recusa:
        _imprimir({"ok": False, "erro": recusa.codigo, "mensagem": recusa.mensagem})
        return 2
    _imprimir({"ok": False, "erro": "uso_incorreto",
               "mensagem": "Use --marcar <id> --status <situação>, --listar ou --caminho."})
    return 2


if __name__ == "__main__":
    sys.exit(main())
