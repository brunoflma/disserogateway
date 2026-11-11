#!/usr/bin/env python3
"""Verificação oficial segura, com critérios próprios por natureza jurídica."""
from __future__ import annotations

import argparse
import hashlib
import html
import http.client
import io
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
FONTES_PADRAO = os.path.join(AQUI, "fontes_oficiais.json")
TIMEOUT = 20
MAX_BYTES = 5_000_000
MAX_REDIRECTS = 3
MIN_TEXTO_VISIVEL = 120
HEADERS = {"User-Agent": "Dissero/1.0 (+verificacao juridica)", "Accept": "text/html,application/json,text/plain,application/pdf"}


class AcessoInseguro(Exception):
    pass


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port=port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        bruto = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(bruto, server_hostname=self.host)


def _norm(valor):
    valor = unicodedata.normalize("NFKD", str(valor or ""))
    valor = "".join(char for char in valor if not unicodedata.combining(char)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", valor)).strip()


def _digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def carregar_fontes(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    if not isinstance(dados.get("hosts"), dict) or not isinstance(dados.get("sufixos_oficiais"), list):
        raise ValueError("estrutura inválida")
    return dados


def motivo_host_travado(host, fontes):
    'Motivo nomeado quando o catálogo trava `confirmacao_teor` no host (DataJud e LexML, em'


    host = (host or "").lower()
    if "confirmacao_teor" not in fontes["hosts"].get(host, {}).get("travas_locais", []):
        return ""
    return (f"DataJud/LexML não confirmam o teor: {host} serve metadado ou índice; confirme no "
            f"documento do tribunal ou do órgão que o publicou")


def classificar_host(host, fontes):
    host = (host or "").lower()
    if host in fontes["hosts"]:
        return "catalogado"
    if any(host.endswith(sufixo.lower()) for sufixo in fontes["sufixos_oficiais"]):
        return "sufixo_oficial"
    return "nao_oficial"


def _resolver_publico(host, permitir_privado=False):
    try:
        enderecos = {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except socket.gaierror as erro:
        raise AcessoInseguro(f"dns: {erro}") from erro
    if not enderecos:
        raise AcessoInseguro("dns sem endereço")
    if not permitir_privado:
        for endereco in enderecos:
            ip = ipaddress.ip_address(endereco)
            if not ip.is_global:
                raise AcessoInseguro(f"IP não público bloqueado: {ip}")
    return sorted(enderecos)[0]


def _validar_url(url, permitir_http=False, permitir_privado=False):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise AcessoInseguro("somente URL HTTP(S) sem credenciais")
    if parsed.scheme != "https" and not permitir_http:
        raise AcessoInseguro("HTTPS obrigatório")
    try:
        ipaddress.ip_address(parsed.hostname)
        if not permitir_privado:
            raise AcessoInseguro("IP literal não permitido")
    except ValueError:
        pass
    ip = _resolver_publico(parsed.hostname, permitir_privado)
    return parsed, ip


def baixar(url, permitir_http=False, permitir_privado=False):
    atual = url
    for salto in range(MAX_REDIRECTS + 1):
        parsed, ip = _validar_url(atual, permitir_http, permitir_privado)
        porta = parsed.port or (443 if parsed.scheme == "https" else 80)
        conexao_cls = _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
        conexao = conexao_cls(parsed.hostname, ip, porta, TIMEOUT)
        caminho = parsed.path or "/"
        if parsed.query:
            caminho += "?" + parsed.query
        try:
            conexao.request("GET", caminho, headers={**HEADERS, "Host": parsed.netloc})
            resposta = conexao.getresponse()
            if resposta.status in (301, 302, 303, 307, 308):
                destino = resposta.getheader("Location")
                resposta.read(1024)
                if not destino or salto >= MAX_REDIRECTS:
                    return None, atual, resposta.status, "redirecionamentos", "limite/Location inválido"
                atual = urljoin(atual, destino)
                continue
            bruto = resposta.read(MAX_BYTES + 1)
            if len(bruto) > MAX_BYTES:
                return None, atual, resposta.status, "limite_bytes", "documento excede limite de bytes"
            return bruto, atual, resposta.status, resposta.getheader("Content-Type", "application/octet-stream"), None
        except (OSError, ssl.SSLError, http.client.HTTPException) as erro:
            return None, atual, 0, "rede", str(erro)
        finally:
            conexao.close()
    return None, atual, 0, "redirecionamentos", "limite excedido"


def _charset(content_type):
    casamento = re.search(r"charset\s*=\s*[\"']?([^;\"']+)", content_type, re.I)
    return casamento.group(1).strip() if casamento else "utf-8"


def _texto_json(valor):
    if isinstance(valor, dict):
        return " ".join(_texto_json(item) for item in valor.values())
    if isinstance(valor, list):
        return " ".join(_texto_json(item) for item in valor)
    return str(valor) if valor is not None else ""


def _extrair_pdf(bruto):
    caminho = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as arquivo:
            arquivo.write(bruto)
            caminho = arquivo.name
        processo = subprocess.run(["pdftotext", "-layout", caminho, "-"], capture_output=True, timeout=30)
        if processo.returncode == 0:
            texto = processo.stdout.decode("utf-8", errors="replace").strip()
            if texto:
                return texto, "pdftotext"
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    finally:
        if caminho:
            try: os.unlink(caminho)
            except OSError: pass
    try:
        from pypdf import PdfReader
        texto = "\n".join(pagina.extract_text() or "" for pagina in PdfReader(io.BytesIO(bruto)).pages).strip()
        if texto:
            return texto, "pypdf"
    except Exception:
        pass
    return "", None


def extrair_texto(bruto, content_type):
    tipo = content_type.split(";", 1)[0].strip().lower()
    if tipo == "application/pdf" or bruto.startswith(b"%PDF"):
        texto, extrator = _extrair_pdf(bruto)
        return texto, extrator, "pdf"
    try:
        texto = bruto.decode(_charset(content_type), errors="replace")
    except LookupError:
        texto = bruto.decode("utf-8", errors="replace")
    if tipo.endswith("/json") or tipo.endswith("+json"):
        try: texto = _texto_json(json.loads(texto))
        except json.JSONDecodeError: pass
    elif "html" in tipo or "xml" in tipo:
        texto = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", texto)
        texto = html.unescape(re.sub(r"(?s)<[^>]+>", " ", texto))
    return re.sub(r"\s+", " ", texto).strip(), None, tipo


def confere(valor, pagina):
    esperado = _norm(valor)
    return None if not esperado else esperado in pagina


def confere_numero(valor, texto):
    numero = _digitos(valor)
    if not numero:
        return None
    tokens = {_digitos(item) for item in re.findall(r"\d[\d.\-/]*\d|\d", texto)}
    return numero in tokens


def confere_relator(valor, pagina):
    esperado = [token for token in _norm(valor).split() if len(token) >= 3 and token not in ("min", "des", "rel", "relator", "relatora", "ministro", "ministra")]
    return None if not esperado else sum(token in pagina for token in esperado) >= max(1, len(esperado) - 1)


def resultado(out, outcome, motivo, codigo=1):
    mapa = {"confirmed": "CONFIRMADO", "blocked": "BLOQUEIO_DE_ACESSO", "partial": "PARCIAL", "not_found": "NAO_CONFIRMADO", "mismatch": "NAO_CONFIRMADO"}
    uso = "allowed" if outcome == "confirmed" else "pending" if outcome in ("blocked", "partial") else "prohibited"
    out.update({"outcome": outcome, "method": "automatic", "use_status": uso, "selo": mapa[outcome], "motivo": motivo})
    print(json.dumps(out, ensure_ascii=False))
    return codigo


def main():
    parser = argparse.ArgumentParser(description="Verificador oficial Dissero")
    parser.add_argument("--url", required=True)
    parser.add_argument("--natureza", choices=["acordao", "sumula", "tema", "norma", "decisao_administrativa"], default="acordao")
    parser.add_argument("--numero")
    parser.add_argument("--relator")
    parser.add_argument("--trecho")
    parser.add_argument("--identificador")
    parser.add_argument("--status")
    parser.add_argument("--tipo-norma")
    parser.add_argument("--numero-norma")
    parser.add_argument("--data-norma")
    parser.add_argument("--dispositivo")
    parser.add_argument("--vigencia")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--fontes", default=FONTES_PADRAO)
    parser.add_argument("--permitir-http-teste", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--permitir-ip-privado-teste", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        fontes = carregar_fontes(args.fontes)
    except Exception as erro:
        print(json.dumps({"ok": False, "erro": f"fontes_oficiais.json: {erro}"}, ensure_ascii=False)); return 2
    host = (urlparse(args.url).hostname or "").lower()
    classe = classificar_host(host, fontes)
    out = {"ok": True, "url": args.url, "final_url": None, "host": host, "host_classe": classe,
           "host_oficial": classe != "nao_oficial", "host_catalogado": classe == "catalogado",
           "checked_at": datetime.now(timezone.utc).isoformat(), "verificacoes": {}}
    if classe == "nao_oficial":
        return resultado(out, "not_found", "host fora do catálogo e dos sufixos candidatos")
    if args.offline:
        return resultado(out, "blocked", "fonte não acessada em modo offline")


    try:
        bruto, final_url, status_http, content_type, erro = baixar(
            args.url, args.permitir_http_teste, args.permitir_ip_privado_teste)
    except AcessoInseguro as erro_seguranca:
        return resultado(out, "blocked", f"acesso seguro bloqueado: {erro_seguranca}")
    out["final_url"] = final_url
    final_host = (urlparse(final_url).hostname or "").lower()
    final_classe = classificar_host(final_host, fontes)
    if status_http in (404, 410): return resultado(out, "not_found", f"HTTP {status_http} na fonte oficial")
    if bruto is None: return resultado(out, "blocked", f"acesso indisponível ({content_type}: {erro})")
    if status_http in (401, 403, 407, 429, 451) or status_http >= 500:
        return resultado(out, "blocked", f"HTTP {status_http}: acesso automatizado impedido")
    if status_http < 200 or status_http >= 300:
        return resultado(out, "partial", f"HTTP {status_http} não conclusivo")
    texto_limpo, extrator, tipo = extrair_texto(bruto, content_type)
    out.update({"content_type": content_type, "sha256": hashlib.sha256(bruto).hexdigest(), "pdf_extractor": extrator})
    if tipo == "pdf" and not extrator:
        return resultado(out, "blocked", "PDF sem extrator confiável; confirmação manual necessária")
    if len(texto_limpo) < MIN_TEXTO_VISIVEL:
        return resultado(out, "blocked", "texto visível insuficiente (SPA/anti-bot ou documento vazio)")
    pagina = _norm(texto_limpo)
    verificacoes = {
        "numero": confere_numero(args.numero, texto_limpo), "relator": confere_relator(args.relator, pagina),
        "trecho": confere(args.trecho, pagina), "identificador": confere(args.identificador, pagina),
        "status": confere(args.status, pagina), "tipo_norma": confere(args.tipo_norma, pagina),
        "numero_norma": confere_numero(args.numero_norma, texto_limpo), "data_norma": confere(args.data_norma, pagina),
        "dispositivo": confere(args.dispositivo, pagina), "vigencia": confere(args.vigencia, pagina)
    }
    out["verificacoes"] = {chave: valor for chave, valor in verificacoes.items() if valor is not None}
    if any(valor is False for valor in out["verificacoes"].values()):
        return resultado(out, "mismatch", "um ou mais sinais divergem do documento oficial")


    travado = motivo_host_travado(final_host, fontes)
    if travado:
        return resultado(out, "partial", travado)
    if args.natureza == "acordao": obrigatorios = ("numero", "relator", "trecho")
    elif args.natureza in ("sumula", "tema"): obrigatorios = ("identificador", "trecho", "status")
    elif args.natureza == "norma": obrigatorios = ("tipo_norma", "numero_norma", "data_norma", "dispositivo", "trecho", "vigencia")
    else: obrigatorios = ("identificador", "trecho")
    if not all(verificacoes[chave] is True for chave in obrigatorios):
        return resultado(out, "partial", "sinais obrigatórios insuficientes para esta natureza")
    capacidades = fontes["hosts"].get(final_host, {}).get("capacidades", [])
    if final_classe != "catalogado" or "confirmacao_teor" not in capacidades:


        return resultado(out, "partial",
                         "host final não possui capacidade catalogada de confirmação do teor")
    return resultado(out, "confirmed", "identidade e teor confrontados em host oficial catalogado", 0)


if __name__ == "__main__":
    raise SystemExit(main())
