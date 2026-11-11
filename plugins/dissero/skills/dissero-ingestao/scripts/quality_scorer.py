'quality_scorer.py — nota de qualidade do texto extraído de uma página.'








from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

LEGAL_PORTUGUESE_KEYWORDS = {
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "com", "nao", "uma", "os", "no", "se", "na",
    "por", "mais", "as", "dos", "como", "mas", "ao", "ele", "das", "seu", "sua", "ou", "quando", "muito",
    "nos", "ja", "eu", "tambem", "so", "pelo", "pela", "ate", "isso", "ela", "entre", "depois", "sem",
    "mesmo", "aos", "seus", "quem", "nas", "meu", "esse", "eles", "voce", "essa", "num", "nem", "suas",
    "meus", "minhas", "numa", "pelos", "pelas", "qual", "nossos", "nossa", "nossas", "dela", "deles",
    "processo", "autor", "reu", "juiz", "vara", "comarca", "tribunal", "justica", "peticao", "fls",
    "folhas", "sentenca", "decisao", "despacho", "artigo", "lei", "codigo", "direto", "recurso", "agravo",
    "apelacao", "embargos", "direito", "partes", "advogado", "oab", "requer", "pedi", "deferimento",
    "juntada", "termo", "autos", "valor", "causa", "real", "reais", "data", "juizo", "seja", "foram",
    "cumprimento", "execucao", "intimacao", "citacao", "manifestacao", "procuracao", "documento", "certidao"
}

_CID_PATTERN = re.compile(r"\(cid:\d+\)")
_UNMAPPED_UNICODE = re.compile(r"[\ue000-\uf8ff\ufffd]")


@dataclass(frozen=True)
class ItemQualityReport:
    score: float
    is_acceptable: bool
    alnum_density: float
    space_ratio: float
    symbol_noise_ratio: float
    dictionary_match_ratio: float
    cid_junk_ratio: float
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "is_acceptable": self.is_acceptable,
            "alnum_density": round(self.alnum_density, 4),
            "space_ratio": round(self.space_ratio, 4),
            "symbol_noise_ratio": round(self.symbol_noise_ratio, 4),
            "dictionary_match_ratio": round(self.dictionary_match_ratio, 4),
            "cid_junk_ratio": round(self.cid_junk_ratio, 4),
            "rejection_reasons": list(self.rejection_reasons),
        }


class QualityScorer:
    """Evaluates text quality (native PDF or OCR output) using multi-metric scoring."""

    def __init__(self, default_threshold: float = 0.70) -> None:
        self.default_threshold = default_threshold

    @staticmethod
    def _normalize(text: str) -> str:
        decomposed = unicodedata.normalize("NFKD", text)
        return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()

    def evaluate(self, text: str, threshold: float | None = None) -> ItemQualityReport:
        target_threshold = threshold if threshold is not None else self.default_threshold
        original = str(text or "")
        length = len(original)

        if length == 0:
            return ItemQualityReport(
                score=0.0,
                is_acceptable=False,
                alnum_density=0.0,
                space_ratio=0.0,
                symbol_noise_ratio=1.0,
                dictionary_match_ratio=0.0,
                cid_junk_ratio=0.0,
                rejection_reasons=("texto_vazio",),
            )

        rejection_reasons: list[str] = []


        cid_matches = len(_CID_PATTERN.findall(original))
        unmapped_matches = len(_UNMAPPED_UNICODE.findall(original))
        cid_junk_count = cid_matches * 6 + unmapped_matches
        cid_junk_ratio = cid_junk_count / max(length, 1)

        if cid_junk_ratio > 0.05 or cid_matches > 3:
            rejection_reasons.append("cid_font_unmapped_junk")


        alnum_chars = sum(char.isalnum() for char in original)
        alnum_density = alnum_chars / length

        spaces = sum(char.isspace() for char in original)
        space_ratio = spaces / length

        permitted_punct = set(".,;:()/%-$€R\n\r\t ")
        symbols = sum(
            not char.isalnum() and char not in permitted_punct for char in original
        )
        symbol_noise_ratio = symbols / length

        if alnum_chars < 20:
            rejection_reasons.append("poucos_caracteres_uteis")

        if alnum_density < 0.45:
            rejection_reasons.append("baixa_densidade_alfanumerica")

        if length > 30 and space_ratio < 0.04:
            rejection_reasons.append("baixa_proporcao_espacos")

        if symbol_noise_ratio > 0.15:
            rejection_reasons.append("proporcao_simbolos_alta")


        tokens = original.split()
        long_tokens = [t for t in tokens if len(t) >= 45]
        if sum(map(len, long_tokens)) / length > 0.3 or (long_tokens and alnum_chars < 200):
            rejection_reasons.append("sequencia_longa_sem_separacao")


        normalized_words = [
            re.sub(r"[^\w]", "", self._normalize(w)) for w in tokens if len(w) >= 2
        ]
        valid_words = [w for w in normalized_words if w in LEGAL_PORTUGUESE_KEYWORDS]

        dictionary_match_ratio = (
            len(valid_words) / len(normalized_words) if normalized_words else 0.0
        )


        clean_symbol_score = max(0.0, 1.0 - symbol_noise_ratio * 3.0)
        clean_cid_score = max(0.0, 1.0 - cid_junk_ratio * 5.0)
        dict_score = min(1.0, dictionary_match_ratio * 2.5)

        composite_score = (
            alnum_density * 0.30
            + clean_symbol_score * 0.25
            + dict_score * 0.25
            + clean_cid_score * 0.20
        )

        if rejection_reasons:
            composite_score = min(composite_score, 0.55)

        is_acceptable = composite_score >= target_threshold and not rejection_reasons

        return ItemQualityReport(
            score=composite_score,
            is_acceptable=is_acceptable,
            alnum_density=alnum_density,
            space_ratio=space_ratio,
            symbol_noise_ratio=symbol_noise_ratio,
            dictionary_match_ratio=dictionary_match_ratio,
            cid_junk_ratio=cid_junk_ratio,
            rejection_reasons=tuple(rejection_reasons),
        )
