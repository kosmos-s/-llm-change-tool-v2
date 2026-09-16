from dataclasses import dataclass
from typing import Protocol


@dataclass
class ProviderResponse:
    raw: str
    input_tokens: int = 0
    output_tokens: int = 0


class ProviderFailure(RuntimeError):
    def __init__(self, code: str, retryable: bool = False):
        super().__init__(code)
        self.retryable = retryable


class Provider(Protocol):
    def predict(self, images, prompt: str, config) -> ProviderResponse: ...
