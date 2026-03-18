"""ConvictionScorer: LLM-basierte Conviction-Extraktion mit instructor + Pydantic."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from tradingagents.portfolio.scorer import BaseScorer, KeywordScorer


class ConvictionScore(BaseModel):
    """Strukturierter Float-Score zwischen -1.0 und +1.0."""

    value: float

    @field_validator("value")
    @classmethod
    def validate_range(cls, v: float) -> float:
        if not (-1.0 <= v <= 1.0):
            raise ValueError(f"Conviction score muss zwischen -1.0 und 1.0 liegen, erhalten: {v}")
        return v


_SYSTEM_PROMPT = (
    "Du bist ein Finanzanalyst. Analysiere das Trading-Signal und vergib einen "
    "Conviction-Score zwischen -1.0 (starkes SELL) und +1.0 (starkes BUY). "
    "Beispiele: 'Strong BUY' → 0.9, 'Cautious BUY' → 0.4, 'HOLD' → 0.0, "
    "'Cautious SELL' → -0.4, 'Strong SELL' → -0.9."
)


class ConvictionScorer(BaseScorer):
    """Nutzt instructor + Pydantic um einen Float-Conviction-Score zu extrahieren.

    Fallback bei LLM-Fehler: KeywordScorer (BUY=1.0, HOLD=0.0, SELL=-1.0).
    """

    def __init__(self, client, model: str = "gpt-4o-mini"):
        """
        Args:
            client: instructor-gepatchter OpenAI-Client.
            model: LLM-Modell für Conviction-Extraktion.
        """
        self._client = client
        self._model = model
        self._fallback = KeywordScorer()

    def score(self, signal: str) -> float:
        """Extrahiert Conviction-Score. Fällt bei Fehler auf KeywordScorer zurück."""
        try:
            result: ConvictionScore = self._client.chat.completions.create(
                model=self._model,
                response_model=ConvictionScore,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": signal},
                ],
            )
            return result.value
        except Exception:
            return self._fallback.score(signal)
