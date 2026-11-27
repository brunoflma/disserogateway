#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'o_que_o_dissero_sabe.py — responde ao advogado «o que o Dissero sabe de mim?».'

























import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

import perfil_advogado as pa



REGRAS_PERMANENTES = (
    "Só jurisprudência confirmada em fonte oficial entra na peça; o que não se confirma sai "
    "marcado para conferir, nunca inventado.",
    "Toda peça é minuta: a revisão final, a conferência da intimação e o protocolo são seus.",
    "Prazo, prescrição, verbas e honorários são calculados por código, não estimados pelo modelo.",
    "Documento sigiloso é lido só no seu computador; não sobe para a nuvem.",
    "Nada de autoridade nova sem o seu sim: consulta paga, leitura em nuvem e mais agentes "
    "dependem de aval seu, ato a ato.",
)

ROTULO_SECAO = {"trajetoria": "Trajetória", "mente": "Mente", "voz": "Voz", "repertorio": "Repertório"}
ROTULO_PREFERENCIA = {
    "auto": "usa se estiver conectado",
    "preferir": "preferir",
    "nao_usar": "não usar",
}


CORRIGIR = {
    "perfil": "Seus dados vêm do Dissero (página «Seus dados», " + pa.PAGINA_PERFIL_URL
              + "). Para mudar, corrija lá ou peça aqui «configurar meus dados».",
    "timbrado": "Para trocar ou reenviar o papel do escritório, peça «configurar meu timbrado».",
    "clone": "Para criar ou refazer o seu estilo (Mente, Voz, Repertório), peça «clonar meu estilo» "
             "ou «continuar configuração».",
    "conectores": "As preferências de conector ficam nos seus dados do Dissero; peça «configurar "
                  "meus dados» para mudá-las.",
}


def _texto(v):
    return str(v).strip() if v is not None else ""


def _perfil():
    """`(perfil|None, status_dict)`. Nunca levanta: perfil ilegível vira estado a reportar."""
    st = pa.status()
    if not st.get("resolvido"):
        return None, st
    try:
        return pa.carregar(st.get("caminho")), st
    except Exception:
        return None, st


def _bloco_perfil(perfil, st):
    if not st.get("resolvido"):
        return {"estado": "sem_perfil", "mensagem": "Ainda não há dados seus gravados nesta máquina."}
    if perfil is None:
        return {"estado": "ilegivel", "mensagem": "Os seus dados existem, mas não puderam ser lidos.",
                "erros": list(st.get("erros") or [])}
    areas = pa._get(perfil, "advogado.areas") or []
    if isinstance(areas, str):
        areas = [areas]
    dados = {
        "nome": _texto(pa._get(perfil, "advogado.nome")),
        "oab": _texto(pa._get(perfil, "advogado.oab")),
        "escritorio": _texto(pa._get(perfil, "advogado.banca")),
        "cidade_assinatura": _texto(pa.cidade_assinatura(perfil)),
        "areas": [_texto(a) for a in areas if _texto(a)] if isinstance(areas, (list, tuple)) else [],
    }
    bloco = {"estado": "completo" if st.get("valido") else "incompleto", "dados": dados,
             "origem": "servidor" if st.get("origem") == "servidor" else "local",
             "divergente": bool(st.get("divergente"))}
    if not st.get("valido"):
        bloco["erros"] = list(st.get("erros") or [])
    return bloco


def _bloco_timbrado(perfil):
    if not isinstance(perfil, dict):
        return {"tipo": None, "estado": "sem_perfil"}
    proprio = pa._get(perfil, "identidade_visual.timbrado") == "proprio"
    avulsas = [t for t in ("assinatura", "brasao") if pa._get(perfil, f"identidade_visual.{t}")]
    ident = pa.estado_da_identidade(perfil)
    bloco = {"tipo": "proprio" if proprio else "padrao", "assinatura_brasao": avulsas}
    if not proprio and not avulsas:
        bloco["estado"] = "padrao"
        return bloco
    if not ident.get("pendente"):
        bloco["estado"] = "integro"
        return bloco
    pacote, _ = pa.conferir_pacote_identidade()
    bloco["estado"] = "ausente" if pacote == "ausente" else "pendente"
    bloco["motivo"] = ident.get("motivo")
    return bloco


def _bloco_clone():
    try:
        reg = pa.clone_local()
    except pa.PerfilError as e:
        return {"estado": "inutilizavel", "motivo": str(e), "secoes": []}
    except Exception:
        return {"estado": "inutilizavel", "motivo": "a cópia local do clone não pôde ser lida", "secoes": []}
    if not reg:
        return {"estado": "ausente", "secoes": []}
    secoes = reg.get("secoes") or {}
    lista = [{"secao": k, "validada": bool((secoes.get(k) or {}).get("validada"))}
             for k in ("trajetoria", "mente", "voz", "repertorio") if k in secoes]
    return {"estado": "presente" if lista else "vazio", "secoes": lista}


def _bloco_conectores(perfil):
    if not isinstance(perfil, dict):
        return {}
    c = pa._get(perfil, "conectores")
    if not isinstance(c, dict):
        return {}
    return {str(k): _texto(v) for k, v in c.items() if not str(k).startswith("_")}


def coletar():
    perfil, st = _perfil()
    return {
        "perfil": _bloco_perfil(perfil, st),
        "timbrado": _bloco_timbrado(perfil),
        "clone": _bloco_clone(),
        "conectores": _bloco_conectores(perfil),
        "regras_permanentes": list(REGRAS_PERMANENTES),
        "onde_corrigir": dict(CORRIGIR),
    }


def _linhas_texto(r):
    L = ["O QUE O DISSERO SABE DE VOCÊ", ""]
    p = r["perfil"]
    L.append("Seus dados")
    if p["estado"] == "sem_perfil":
        L.append("  " + p["mensagem"])
    elif p["estado"] == "ilegivel":
        L.append("  " + p["mensagem"])
    else:
        d = p["dados"]
        L.append("  Nome: " + (d["nome"] or "(não informado)"))
        L.append("  OAB: " + (d["oab"] or "(não informada)"))
        L.append("  Escritório: " + (d["escritorio"] or "(não informado)"))
        L.append("  Cidade de assinatura: " + (d["cidade_assinatura"] or "(não informada)"))
        L.append("  Áreas: " + (", ".join(d["areas"]) or "(não informadas)"))
        if p["estado"] == "incompleto":
            L.append("  Faltam dados obrigatórios; sem eles a peça final não sai com o seu timbrado.")
        if p.get("divergente"):
            L.append("  A cópia nesta máquina não bate com a do Dissero; vale a do Dissero.")
    L.append("  → " + r["onde_corrigir"]["perfil"])
    L.append("")

    t = r["timbrado"]
    L.append("Papel do escritório (timbrado)")
    if t["estado"] == "sem_perfil":
        L.append("  Sem dados seus, a peça sai sem timbrado.")
    else:
        tipo = "próprio (o modelo do seu escritório)" if t["tipo"] == "proprio" else "padrão do Dissero"
        L.append("  Tipo: " + tipo)
        if t.get("assinatura_brasao"):
            L.append("  Com " + " e ".join("brasão" if x == "brasao" else x for x in t["assinatura_brasao"]))
        estado = {"padrao": "em uso, nada a baixar",
                  "integro": "instalado e conferido nesta máquina",
                  "ausente": "ainda não baixado nesta máquina",
                  "pendente": "precisa ser baixado de novo"}[t["estado"]]
        L.append("  Situação: " + estado)
    L.append("  → " + r["onde_corrigir"]["timbrado"])
    L.append("")

    c = r["clone"]
    L.append("Seu estilo (clone)")
    if c["estado"] == "ausente":
        L.append("  Nenhum clone gravado nesta máquina.")
    elif c["estado"] == "inutilizavel":
        L.append("  Há uma cópia, mas ela não pode ser usada; peça para gravá-la de novo.")
    elif c["estado"] == "vazio":
        L.append("  O clone existe, mas ainda sem Mente nem Voz configuradas.")
    else:
        partes = [ROTULO_SECAO[s["secao"]] + (" (validada)" if s["validada"] else " (rascunho)")
                  for s in c["secoes"]]
        L.append("  Seções: " + ", ".join(partes))
    L.append("  → " + r["onde_corrigir"]["clone"])
    L.append("")

    L.append("Conectores")
    if not r["conectores"]:
        L.append("  Nenhuma preferência declarada; cada conector é usado se estiver conectado.")
    else:
        for k, v in sorted(r["conectores"].items()):
            L.append(f"  {k}: {ROTULO_PREFERENCIA.get(v, v or '(vazio)')}")
    L.append("  → " + r["onde_corrigir"]["conectores"])
    L.append("")

    L.append("Regras que valem sempre (não dependem dos seus dados)")
    for regra in r["regras_permanentes"]:
        L.append("  • " + regra)
    return L


def main(argv=None):
    ap = argparse.ArgumentParser(description="O que o Dissero sabe do advogado (só leitura).")
    ap.add_argument("--json", action="store_true", help="saída estruturada")
    a = ap.parse_args(argv)
    r = coletar()
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("\n".join(_linhas_texto(r)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
