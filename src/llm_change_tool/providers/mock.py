from llm_change_tool.core.labels import KEYS, canonical
from llm_change_tool.providers.base import ProviderResponse


class MockProvider:
    """Deterministic pilot response; deliberately requires human review."""

    def predict(self, images, prompt, config):
        return ProviderResponse(
            canonical(
                {
                    "labels": dict.fromkeys(KEYS, 0),
                    "confidence": 0.5,
                    "reason": "합성 Mock 판정 — 실제 AI 결과가 아닙니다.",
                    "review_required": True,
                }
            )
        )
