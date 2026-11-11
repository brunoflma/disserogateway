#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'Memória experimental de dosimetria e progressão penal.'








from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
from ficha_capacidade import FichaRecusada, exigir as exigir_ficha

CAPACIDADES = ("dosimetria_penal", "progressao_regime")
ENGINE_VERSION = "dsr.dosimetria_progressao.engine.v1"
DECISION_VERSION = "dsr.dosimetria_progressao.decisao.v1"
REQUEST_VERSION = "dsr.dosimetria_progressao.pedido.v1"
AUTH_VERSION = "dsr.dosimetria_progressao.autorizacao.v1"
MEMORY_VERSION = "dsr.memoria_dosimetria_progressao.v1"
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")



HORA_FUSO = re.compile(r"(?P<hora>[0-9]{2}:[0-9]{2}(?P<seg>:[0-9]{2})?)"
                       r"(?(seg)(?:[.,](?P<fracao>[0-9]{1,6})[0-9]*)?)"
                       r"(?P<fuso>[+-][0-9]{2})(?::?(?P<min>[0-9]{2}))?\Z")
OFFICIAL_SUFFIXES = (".gov.br", ".jus.br", ".leg.br", ".mp.br", ".def.br")

class DosimetriaError(RuntimeError):
    def __init__(self, code: str, errors: list[str] | str):
        self.code = code; self.errors = [errors] if isinstance(errors, str) else list(errors); super().__init__("; ".join(self.errors))

def _load_json(path: Any) -> tuple[dict[str, Any], str]:
    if not isinstance(path, (str, os.PathLike)): raise DosimetriaError("arquivo_invalido", "caminho local obrigatório")
    original = os.path.abspath(os.fspath(path)); resolved = os.path.realpath(original)
    if os.path.islink(original) or not os.path.isfile(resolved): raise DosimetriaError("arquivo_invalido", "arquivo ausente ou inseguro")
    current = resolved
    while True:
        if os.path.exists(os.path.join(current, ".git")): raise DosimetriaError("arquivo_invalido", "decisão e autorização não podem estar dentro de Git")
        parent = os.path.dirname(current)
        if parent == current: break
        current = parent
    try:
        raw = Path(resolved).read_bytes(); value = json.loads(raw.decode("utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc: raise DosimetriaError("arquivo_invalido", "JSON local ilegível") from exc
    if not isinstance(value, dict): raise DosimetriaError("arquivo_invalido", "JSON deve conter objeto")
    return value, hashlib.sha256(raw).hexdigest()

def _date(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not DATE.fullmatch(value): return None
    try: return dt.date.fromisoformat(value)
    except ValueError: return None

def _datetime(value: Any) -> dt.datetime | None:
    if not isinstance(value, str): return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    hora = HORA_FUSO.search(candidate)
    if hora:
        fracao = dt.datetime.strptime(hora["fracao"], "%f").strftime(".%f") if hora["fracao"] else ""
        candidate = candidate[:hora.start()] + hora["hora"] + fracao + hora["fuso"] + ":%02d" % int(hora["min"] or 0)
    try: parsed = dt.datetime.fromisoformat(candidate)
    except ValueError: return None
    return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo and parsed.utcoffset() is not None else None

def _official_url(value: Any) -> bool:
    if not isinstance(value, str): return False
    parsed = urlparse(value); host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and bool(host) and any(host.endswith(x) for x in OFFICIAL_SUFFIXES) and not parsed.username and not parsed.password and not parsed.fragment

def _int(value: Any, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0): raise DosimetriaError("entrada_invalida", f"{field} deve ser inteiro {'positivo' if positive else 'não negativo'}")
    return value

def _unknown(value: Mapping[str, Any], allowed: set[str], prefix: str) -> list[str]: return [f"{prefix} contém campo não permitido: {key}" for key in value if key not in allowed]

def validar_decisao(decision: Any, *, hoje: dt.date | None = None) -> list[str]:
    if not isinstance(decision, Mapping): return ["decisão deve ser objeto"]
    allowed = {"schema_version", "decision_id", "name", "legal_source_url", "legal_source_sha256", "valid_from", "valid_to", "extracted_at", "reviewed_by", "reviewed_role", "reviewed_at", "segregation_attested", "dosimetria", "progressao"}
    errors = _unknown(decision, allowed, "decisão")
    if decision.get("schema_version") != DECISION_VERSION: errors.append(f"schema_version deve ser {DECISION_VERSION}")
    if not isinstance(decision.get("decision_id"), str) or not ID.fullmatch(str(decision.get("decision_id"))): errors.append("decision_id inválido")
    for field in ("name", "reviewed_by"):
        if not isinstance(decision.get(field), str) or not decision[field].strip(): errors.append(f"{field} obrigatório")
    if not _official_url(decision.get("legal_source_url")): errors.append("legal_source_url deve ser HTTPS oficial")
    if not isinstance(decision.get("legal_source_sha256"), str) or not SHA256.fullmatch(decision["legal_source_sha256"]): errors.append("legal_source_sha256 inválido")
    if decision.get("reviewed_role") != "advogado": errors.append("reviewed_role deve ser advogado")
    if decision.get("segregation_attested") is not True: errors.append("segregation_attested=true é obrigatório")
    today = hoje or dt.date.today(); start, end, extracted, reviewed = (_date(decision.get(k)) for k in ("valid_from", "valid_to", "extracted_at", "reviewed_at"))
    if start is None or end is None or start > end or not start <= today <= end: errors.append("vigência da decisão inválida, ausente ou vencida")
    if extracted is None or extracted > today: errors.append("extracted_at inválido ou futuro")
    if reviewed is None or reviewed > today: errors.append("reviewed_at inválido ou futuro")
    dos = decision.get("dosimetria")
    if not isinstance(dos, Mapping) or set(dos) != {"pena_base_dias", "fase_1", "fase_2", "fase_3"}: errors.append("dosimetria deve declarar pena_base_dias e três fases")
    else:
        try: _int(dos["pena_base_dias"], "dosimetria.pena_base_dias", positive=True)
        except DosimetriaError as exc: errors.extend(exc.errors)
        for phase in ("fase_1", "fase_2", "fase_3"):
            factors = dos.get(phase)
            if not isinstance(factors, list): errors.append(f"dosimetria.{phase} deve ser lista"); continue
            for i, factor in enumerate(factors):
                p = f"dosimetria.{phase}[{i}]"
                if not isinstance(factor, Mapping) or set(factor) != {"id", "efeito", "dias", "fundamento"}: errors.append(f"{p} inválido"); continue
                if not isinstance(factor.get("id"), str) or not ID.fullmatch(factor["id"]): errors.append(f"{p}.id inválido")
                if factor.get("efeito") not in {"acrescimo", "decrescimo"}: errors.append(f"{p}.efeito inválido")
                try: _int(factor.get("dias"), f"{p}.dias", positive=True)
                except DosimetriaError as exc: errors.extend(exc.errors)
                if not isinstance(factor.get("fundamento"), str) or not factor["fundamento"].strip(): errors.append(f"{p}.fundamento obrigatório")
    prog = decision.get("progressao")
    if not isinstance(prog, Mapping) or set(prog) != {"fracao_numerador", "fracao_denominador", "arredondamento_dias", "base"}: errors.append("progressao deve declarar fração, arredondamento e base")
    else:
        for field in ("fracao_numerador", "fracao_denominador"):
            try: _int(prog.get(field), f"progressao.{field}", positive=True)
            except DosimetriaError as exc: errors.extend(exc.errors)



        if isinstance(prog.get("fracao_numerador"), int) and isinstance(prog.get("fracao_denominador"), int) and prog["fracao_numerador"] and prog["fracao_denominador"] and prog["fracao_numerador"] > prog["fracao_denominador"]: errors.append("fração de progressão não pode superar 1")
        if prog.get("arredondamento_dias") not in {"ceil", "floor", "reject"}: errors.append("arredondamento_dias inválido")
        if prog.get("base") not in {"pena_total", "pena_remanescente"}: errors.append("base de progressão inválida")
    return errors

def validar_pedido(request: Any) -> list[str]:
    if not isinstance(request, Mapping): return ["pedido deve ser objeto"]
    errors = _unknown(request, {"schema_version", "decision_path", "decision_sha256", "authorization_path", "data_referencia", "dias_cumpridos", "dias_detraidos", "dias_remidos"}, "pedido")
    if request.get("schema_version") != REQUEST_VERSION: errors.append(f"schema_version deve ser {REQUEST_VERSION}")
    if not isinstance(request.get("decision_path"), str) or not request["decision_path"].strip(): errors.append("decision_path obrigatório")
    if not isinstance(request.get("authorization_path"), str) or not request["authorization_path"].strip(): errors.append("authorization_path obrigatório")
    if not isinstance(request.get("decision_sha256"), str) or not SHA256.fullmatch(request["decision_sha256"]): errors.append("decision_sha256 inválido")
    if _date(request.get("data_referencia")) is None: errors.append("data_referencia inválida")
    for field in ("dias_cumpridos", "dias_detraidos", "dias_remidos"):
        try: _int(request.get(field), field)
        except DosimetriaError as exc: errors.extend(exc.errors)
    return errors

def _authorize(path: Any, decision_hash: str, now: dt.datetime) -> None:
    auth, _ = _load_json(path); errors = []
    if set(auth) != {"schema_version", "authorized_by_lawyer", "scope", "decision_sha256", "expires_at", "authorized_by"}: errors.append("autorização contém campos não permitidos")
    if auth.get("schema_version") != AUTH_VERSION: errors.append(f"schema_version deve ser {AUTH_VERSION}")
    if auth.get("authorized_by_lawyer") is not True or auth.get("scope") != "calculo_experimental": errors.append("autorização jurídica experimental inválida")
    if auth.get("decision_sha256", "").casefold() != decision_hash.casefold(): errors.append("autorização não corresponde à decisão")
    expires = _datetime(auth.get("expires_at"))
    if expires is None or expires <= now: errors.append("autorização ausente, inválida ou vencida")
    if not isinstance(auth.get("authorized_by"), str) or len(auth["authorized_by"].strip()) < 3: errors.append("authorized_by inválido")
    if errors: raise DosimetriaError("autorizacao_invalida", errors)

def calcular(request: Any, *, hoje: dt.date | None = None, agora: dt.datetime | None = None, experimental_authorized: bool = False, registro_capacidades: Any = None) -> dict[str, Any]:
    'Memória de dosimetria e progressão. `registro_capacidades` (dict ou caminho) substitui'

    if experimental_authorized is not True: raise DosimetriaError("capacidade_desabilitada", "dosimetria e progressão experimental exigem autorização explícita")
    now = agora or dt.datetime.combine(hoje or dt.date.today(), dt.time(12), tzinfo=dt.timezone.utc); today = hoje or now.date()
    for capacidade in CAPACIDADES:
        try:
            exigir_ficha(capacidade, hoje=today, registro=registro_capacidades)
        except FichaRecusada as exc:
            raise DosimetriaError(exc.codigo, exc.mensagem) from None
    errors = validar_pedido(request)
    if errors: raise DosimetriaError("pedido_invalido", errors)
    decision, decision_hash = _load_json(request["decision_path"])
    if decision_hash.casefold() != request["decision_sha256"].casefold(): raise DosimetriaError("hash_divergente", "decision_sha256 diverge do arquivo")
    _authorize(request["authorization_path"], decision_hash, now)
    errors = validar_decisao(decision, hoje=today)
    if errors: raise DosimetriaError("decisao_invalida", errors)
    dos, prog = decision["dosimetria"], decision["progressao"]; penalty = _int(dos["pena_base_dias"], "pena_base_dias", positive=True); phases = []
    for phase in ("fase_1", "fase_2", "fase_3"):
        before = penalty
        for factor in dos[phase]: penalty += factor["dias"] if factor["efeito"] == "acrescimo" else -factor["dias"]
        if penalty <= 0: raise DosimetriaError("decisao_invalida", f"{phase} produz pena não positiva")
        phases.append({"fase": phase, "pena_antes_dias": before, "pena_depois_dias": penalty, "fatores": dos[phase]})



    parcelas = {x: _int(request[x], x) for x in ("dias_cumpridos", "dias_detraidos", "dias_remidos")}
    served = sum(parcelas.values()); remaining = max(0, penalty - served)
    denominator = _int(prog["fracao_denominador"], "fracao_denominador", positive=True); numerator = _int(prog["fracao_numerador"], "fracao_numerador", positive=True); base = penalty if prog["base"] == "pena_total" else remaining; raw = Fraction(base * numerator, denominator)
    if raw.denominator != 1:
        if prog["arredondamento_dias"] == "reject": raise DosimetriaError("arredondamento_ausente", "frações produziram dia fracionário e decisão exige reject")
        threshold = raw.numerator // raw.denominator + (1 if prog["arredondamento_dias"] == "ceil" else 0)
    else: threshold = raw.numerator
    eligible = served >= threshold
    return {"schema_version": MEMORY_VERSION, "status": "MINUTA_PARA_REVISAO", "engine_version": ENGINE_VERSION, "decision": {"decision_id": decision["decision_id"], "decision_sha256": decision_hash, "legal_source_url": decision["legal_source_url"], "legal_source_sha256": decision["legal_source_sha256"], "reviewed_by": decision["reviewed_by"]}, "dosimetria": {"pena_final_dias": penalty, "fases": phases}, "progressao": {"dias_considerados_total": served, "dias_cumpridos": parcelas["dias_cumpridos"], "dias_detraidos": parcelas["dias_detraidos"], "dias_remidos": parcelas["dias_remidos"], "dias_remanescentes": remaining, "fracao": f"{numerator}/{denominator}", "dias_exigidos": threshold, "elegibilidade": "elegivel" if eligible else "nao_elegivel", "base": prog["base"]}, "warnings": ["MINUTA_PARA_REVISAO: conferência obrigatória do advogado.", "O motor não escolhe pena, circunstâncias, frações, crime ou regime.", "Datas de cumprimento, detração e remição devem ser conferidas nos autos e na execução penal.", "`dias_considerados_total` SOMA as três parcelas (cumpridos + detraídos + remidos) para aferir a fração do art. 112 da LEP. Somar a REMIÇÃO nessa base é TESE JURÍDICA, não aritmética — ela depende de homologação judicial (LEP art. 126) e a detração (CP art. 42) é etapa própria. O motor não decide isso: mostra as três parcelas separadas para que o advogado confirme ou recuse a base antes de usar a minuta."]}

def main(argv: list[str] | None = None) -> int:
    try:
        parser = argparse.ArgumentParser(); parser.add_argument("--request", required=True); args = parser.parse_args(argv)
        request, _ = _load_json(args.request)
        if os.environ.get("DSR_DOSIMETRIA_PROGRESSAO_EXPERIMENTAL") != "1": raise DosimetriaError("capacidade_desabilitada", "DSR_DOSIMETRIA_PROGRESSAO_EXPERIMENTAL=1 é obrigatório")
        result = calcular(request, experimental_authorized=True)
    except (DosimetriaError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "status": "INCONCLUSIVO", "error_code": getattr(exc, "code", "falha"), "errors": getattr(exc, "errors", [str(exc)])}, ensure_ascii=False, sort_keys=True)); return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
