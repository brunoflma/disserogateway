#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'acentuacao_pt.py — reacentuação de RÓTULO DE CITAÇÃO (nunca de transcrição literal).'



























import re
import unicodedata


TERMOS = {

    "apelacao": "apelação", "apelacoes": "apelações", "civel": "cível",
    "acordao": "acórdão", "acordaos": "acórdãos", "sumula": "súmula", "sumulas": "súmulas",
    "decisao": "decisão", "decisoes": "decisões", "monocratica": "monocrática",
    "monocratico": "monocrático", "declaracao": "declaração", "declaratoria": "declaratória",
    "condenatoria": "condenatória", "rescisoria": "rescisória", "anulatoria": "anulatória",
    "monitoria": "monitória", "arguicao": "arguição", "reclamacao": "reclamação",
    "suspensao": "suspensão", "homologacao": "homologação", "execucao": "execução",
    "consignacao": "consignação", "impugnacao": "impugnação", "manifestacao": "manifestação",
    "peticao": "petição", "revisao": "revisão", "reintegracao": "reintegração",
    "antecipacao": "antecipação", "restituicao": "restituição", "compensacao": "compensação",
    "indenizacao": "indenização", "obrigacao": "obrigação", "obrigacoes": "obrigações",
    "prestacao": "prestação", "prestacoes": "prestações", "sub-rogacao": "sub-rogação",
    "subrogacao": "sub-rogação", "adjudicacao": "adjudicação", "arrematacao": "arrematação",
    "notificacao": "notificação", "intimacao": "intimação", "citacao": "citação",
    "instrucao": "instrução", "producao": "produção", "inversao": "inversão",
    "conversao": "conversão", "extincao": "extinção", "resolucao": "resolução",
    "rescisao": "rescisão", "inadimplencia": "inadimplência", "mora": "mora",

    "camara": "câmara", "camaras": "câmaras", "secao": "seção", "secoes": "seções",
    "orgao": "órgão", "orgaos": "órgãos", "competencia": "competência",
    "incompetencia": "incompetência", "instancia": "instância", "instancias": "instâncias",
    "juizo": "juízo", "regiao": "região", "justica": "justiça", "ministerio": "ministério",
    "previdencia": "previdência", "publico": "público", "publica": "pública",
    "publicos": "públicos", "publicas": "públicas", "uniao": "união", "sessao": "sessão",

    "seguranca": "segurança", "fianca": "fiança", "locacao": "locação",
    "familia": "família", "sucessoes": "sucessões", "heranca": "herança",
    "espolio": "espólio", "inventario": "inventário", "imovel": "imóvel",
    "imoveis": "imóveis", "avaliacao": "avaliação", "pericia": "perícia",
    "indagacao": "indagação", "honorarios": "honorários", "sucumbencia": "sucumbência",
    "prescricao": "prescrição", "decadencia": "decadência", "falencia": "falência",
    "recuperacao": "recuperação", "licitacao": "licitação", "tributaria": "tributária",
    "tributario": "tributário", "previdenciaria": "previdenciária", "servico": "serviço",
    "servicos": "serviços", "associacao": "associação", "fundacao": "fundação",
    "condominio": "condomínio", "usucapiao": "usucapião", "sentenca": "sentença",
    "inepcia": "inépcia", "litigancia": "litigância", "ma-fe": "má-fé",

    "jurisprudencia": "jurisprudência", "divergencia": "divergência",
    "controversia": "controvérsia", "transito": "trânsito", "oficio": "ofício",
    "relatoria": "relatoria", "vice-presidencia": "vice-presidência",



    "acao": "ação", "acoes": "ações", "nao": "não", "sao": "são", "ate": "até",
    "razao": "razão", "razoes": "razões", "onus": "ônus", "cobranca": "cobrança",
    "aluguel": "aluguel", "alugueis": "aluguéis", "civeis": "cíveis",
    "ausencia": "ausência", "existencia": "existência", "inexistencia": "inexistência",
    "ocorrencia": "ocorrência", "resistencia": "resistência", "subsistencia": "subsistência",
    "insuficiencia": "insuficiência", "inteligencia": "inteligência",
    "inobservancia": "inobservância", "denuncia": "denúncia",
    "deposito": "depósito", "depositos": "depósitos", "proposito": "propósito",
    "advocaticio": "advocatício", "advocaticios": "advocatícios",
    "advocaticia": "advocatícia", "advocaticias": "advocatícias",
    "consectarios": "consectários", "consectario": "consectário",
    "moratoria": "moratória", "moratorios": "moratórios", "moratorio": "moratório",
    "petitoria": "petitória", "probatoria": "probatória", "premonitoria": "premonitória",
    "indenizatoria": "indenizatória", "liberatoria": "liberatória",
    "contraditorio": "contraditório", "compulsorio": "compulsório",
    "necessario": "necessário", "necessarios": "necessários",
    "necessaria": "necessária", "necessarias": "necessárias",
    "desnecessaria": "desnecessária", "desnecessario": "desnecessário",
    "voluntaria": "voluntária", "voluntario": "voluntário", "bancaria": "bancária",
    "possivel": "possível", "impossivel": "impossível", "cabivel": "cabível",
    "aplicacao": "aplicação", "alteracao": "alteração", "afericao": "aferição",
    "apresentacao": "apresentação", "aquisicao": "aquisição", "assercao": "asserção",
    "autenticacao": "autenticação", "caracterizacao": "caracterização",
    "comprovacao": "comprovação", "condenacao": "condenação", "condicao": "condição",
    "condicoes": "condições", "conexao": "conexão", "concessao": "concessão",
    "consideracao": "consideração", "contestacao": "contestação",
    "contradicao": "contradição", "correcao": "correção", "declinacao": "declinação",
    "deducao": "dedução", "desocupacao": "desocupação", "dilacao": "dilação",
    "disponibilizacao": "disponibilização", "fixacao": "fixação",
    "fundamentacao": "fundamentação", "imissao": "imissão", "imposicao": "imposição",
    "inadequacao": "inadequação", "instauracao": "instauração",
    "liquidacao": "liquidação", "purgacao": "purgação", "prevencao": "prevenção",
    "pretensao": "pretensão", "reapreciacao": "reapreciação",
    "redistribuicao": "redistribuição", "relacao": "relação", "suscitacao": "suscitação",
    "usurpacao": "usurpação", "vedacao": "vedação", "violacao": "violação",
    "ocasiao": "ocasião", "aptidao": "aptidão", "afiancado": "afiançado",
    "afiancada": "afiançada", "locaticia": "locatícia", "locaticio": "locatício",
}





NOMES = {
    "antonio": "Antônio", "fatima": "Fátima", "joao": "João", "jose": "José",
    "otavio": "Otávio", "araujo": "Araújo", "inacio": "Inácio",
    "patrocinio": "Patrocínio", "lucidio": "Lucídio", "junior": "Júnior",
    "cesar": "César", "ines": "Inês", "vitoria": "Vitória", "barbara": "Bárbara",
    "angela": "Ângela", "andre": "André", "marcio": "Márcio", "mauricio": "Maurício",
    "fabio": "Fábio", "flavio": "Flávio", "lucia": "Lúcia", "genesio": "Genésio",
    "tarcisio": "Tarcísio", "aurelio": "Aurélio", "rogerio": "Rogério",
    "valerio": "Valério", "helio": "Hélio", "sergio": "Sérgio", "fabricio": "Fabrício",
    "getulio": "Getúlio", "romulo": "Rômulo", "silverio": "Silvério",
    "goncalves": "Gonçalves", "assuncao": "Assunção", "conceicao": "Conceição",
    "nobrega": "Nóbrega", "franca": "França", "gloria": "Glória", "otilia": "Otília",
}



COMPOSTOS = {"villas boas": "Villas Bôas"}



COMPOSTOS["denuncia vazia"] = "denúncia vazia"


_ORD_F = re.compile(r"\b(\d{1,3})[ªa]\s+(?=(?:C[âa]mara|Turma|Vara|Se[çc][ãa]o|Regi[ãa]o|"
                    r"Inst[âa]ncia|Vice))")
_ORD_M = re.compile(r"\b(\d{1,3})[ºo]\s+(?=(?:Grupo|Juizado|Cart[óo]rio|Of[íi]cio|Tribunal))")


_NUMERO = re.compile(r"\b(Informativo|Tema|S[úu]mula|Enunciado|Processo|Boletim|Verbete|"
                     r"Precedente|Provimento|Resolu[çc][ãa]o|Portaria|Decreto|Lei|Item)\s+n[oº°]\.?\s+(?=\d)")

_DESA = re.compile(r"\bDes(?:\.a|a\.)\s+")











_SUSPEITA = re.compile(r"^[A-Za-z][A-Za-z-]*(?:cao|coes|ncia|ncias|nsao|nsoes|"
                       r"orio|oria|avel|ivel|ssao|ssoes|ao|oes|ueis|aticio|aticios|"
                       r"osito|ositos|onus)$", re.I)
_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ-]*")
_DIACRITICO = re.compile(r"[À-ÿ]")



SEM_ACENTO = frozenset("""
teoria categoria diretoria auditoria assessoria procuradoria corregedoria ouvidoria
secretaria relatoria banca franca manca vitoria-regia acao-nao
""".split())


def _sem_acento(p):
    return "".join(c for c in unicodedata.normalize("NFD", p)
                   if unicodedata.category(c) != "Mn").lower()


def _casar_caixa(original, alvo):
    """Aplica ao alvo a CAIXA do original: TODO MAIÚSCULO, Inicial ou minúsculo."""
    if original.isupper():
        return alvo.upper()
    if original[:1].isupper():
        return alvo[:1].upper() + alvo[1:]
    return alvo[:1].lower() + alvo[1:]


def _trocar_palavras(texto, tabela):
    def sub(m):
        p = m.group(0)
        alvo = tabela.get(p.lower())
        return _casar_caixa(p, alvo) if alvo else p
    return _PALAVRA.sub(sub, texto)


def reacentuar(texto):
    'Reacentua RÓTULO DE CITAÇÃO pelo dicionário fechado. Idempotente.'



    if not texto:
        return texto
    for chave, alvo in COMPOSTOS.items():
        texto = re.sub(re.escape(chave).replace(r"\ ", r"\s+"), alvo, texto, flags=re.I)
    texto = _trocar_palavras(texto, TERMOS)
    texto = _trocar_palavras(texto, NOMES)
    texto = _ORD_F.sub(r"\1ª ", texto)
    texto = _ORD_M.sub(r"\1º ", texto)
    texto = _NUMERO.sub(r"\1 nº ", texto)
    texto = _DESA.sub("Desª. ", texto)
    return texto


def reacentuar_literal(texto):
    'Reacentuação de TRANSCRIÇÃO LITERAL, com invariante conferida em runtime.'







    if not texto:
        return texto
    novo = texto
    for chave, alvo in COMPOSTOS.items():
        novo = re.sub(re.escape(chave).replace(r"\ ", r"\s+"), alvo, novo, flags=re.I)
    novo = _trocar_palavras(novo, TERMOS)
    novo = _trocar_palavras(novo, NOMES)
    return novo if _sem_acento(novo) == _sem_acento(texto) else texto


def residuos(texto):
    'Palavras que ainda parecem sem acento e que a tabela NÃO resolve.'




    fora, vistos = [], set()
    for m in _PALAVRA.finditer(texto or ""):
        p = m.group(0)
        if _DIACRITICO.search(p):
            continue
        base = _sem_acento(p)
        if base in TERMOS or base in NOMES or base in SEM_ACENTO:
            continue
        if _SUSPEITA.match(p) and base not in vistos:
            vistos.add(base)
            fora.append(p)
    return fora


def parece_sem_acento(texto):
    'Heurística para TRANSCRIÇÃO LITERAL: texto longo, zero diacrítico e ao menos um'


    t = texto or ""
    if len(t) < 60 or _DIACRITICO.search(t):
        return False
    return bool(residuos(t)) or bool(re.search(r"\b\w*(?:cao|coes)\b", t, re.I))
