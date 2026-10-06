"""Small-corpus hybrid retrieval without an external vector service."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Iterable


def tokenize(text: str) -> list[str]:
    """Return English tokens plus CJK unigrams/bigrams for useful Chinese recall."""
    lowered = (text or "").lower()
    tokens = re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", lowered)
    expanded: list[str] = []
    for token in tokens:
        if re.fullmatch(r"[\u3400-\u9fff]+", token):
            expanded.extend(token)
            expanded.extend(token[index:index + 2] for index in range(len(token) - 1))
        else:
            expanded.append(token)
    return expanded


def _hashed_vector(tokens: Iterable[str], dimensions: int = 256) -> Counter[int]:
    vector: Counter[int] = Counter()
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:4], "big") % dimensions] += 1
    return vector


def cosine_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_vector = _hashed_vector(left)
    right_vector = _hashed_vector(right)
    if not left_vector or not right_vector:
        return 0.0
    dot = sum(value * right_vector.get(key, 0) for key, value in left_vector.items())
    left_norm = math.sqrt(sum(value * value for value in left_vector.values()))
    right_norm = math.sqrt(sum(value * value for value in right_vector.values()))
    return dot / max(left_norm * right_norm, 1e-9)


def hybrid_scores(query: str, documents: list[str]) -> list[float]:
    """Blend BM25 lexical relevance with hashed n-gram cosine similarity."""
    if not documents:
        return []
    query_terms = tokenize(query)
    if not query_terms:
        return [0.0] * len(documents)

    tokenized = [tokenize(document) for document in documents]
    doc_count = len(tokenized)
    avg_length = sum(len(tokens) for tokens in tokenized) / max(doc_count, 1)
    doc_frequency = Counter(term for tokens in tokenized for term in set(tokens))
    query_counts = Counter(query_terms)
    k1, b = 1.5, 0.75
    raw_bm25: list[float] = []
    for tokens in tokenized:
        counts = Counter(tokens)
        score = 0.0
        for term, query_weight in query_counts.items():
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            inverse_frequency = math.log(
                1 + (doc_count - doc_frequency[term] + 0.5) / (doc_frequency[term] + 0.5)
            )
            denominator = frequency + k1 * (
                1 - b + b * len(tokens) / max(avg_length, 1.0)
            )
            score += inverse_frequency * frequency * (k1 + 1) / denominator * query_weight
        raw_bm25.append(score)

    max_bm25 = max(raw_bm25, default=0.0)
    return [
        round(
            0.65 * (bm25 / max_bm25 if max_bm25 else 0.0)
            + 0.35 * cosine_similarity(query_terms, tokens),
            6,
        )
        for bm25, tokens in zip(raw_bm25, tokenized)
    ]
