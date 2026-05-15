"""Corpus primitives + registry.

A Corpus is a named collection of CorpusItems. A CorpusItem is a labeled
message sequence that a compressor can be applied to and scored against.
Corpora live separately from compressors so the same compressor can be
evaluated on synthetic, real-trace, and adversarial inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterator

from tokeless.compressors import Message


@dataclass
class CorpusItem:
    item_id: str
    messages: list[Message]
    description: str = ""


@dataclass
class Corpus:
    name: str
    description: str
    items: list[CorpusItem] = field(default_factory=list)

    def __iter__(self) -> Iterator[CorpusItem]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


CorpusFactory = Callable[[], Corpus]

_REGISTRY: dict[str, CorpusFactory] = {}


def register(name: str) -> Callable[[CorpusFactory], CorpusFactory]:
    def deco(fn: CorpusFactory) -> CorpusFactory:
        if name in _REGISTRY:
            raise ValueError(f"Corpus already registered: {name}")
        _REGISTRY[name] = fn
        return fn

    return deco


def get(name: str) -> Corpus:
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown corpus: {name!r}. Registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]()


def names() -> list[str]:
    return sorted(_REGISTRY)


# Side-effect registrations.
from tokeless.corpora import synthetic as _synthetic  # noqa: E402,F401
