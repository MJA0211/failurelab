"""BM25 and exact identifier retrieval; optional real dense retrieval and cross-encoder."""

import re
from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

RETRIEVAL_VERSION = "retrieval-v1"


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_./-]+", text.lower())


@lru_cache(maxsize=2)
def models(embedding_model, reranker_model):
    from sentence_transformers import CrossEncoder, SentenceTransformer

    return SentenceTransformer(embedding_model), CrossEncoder(reranker_model)


def retrieve(query: str, evidence: list[dict], settings, limit=8) -> list[dict]:
    if not evidence:
        return []
    texts = [e["title"] + "\n" + e["content"] for e in evidence]
    corpus = [tokenize(t) or ["empty"] for t in texts]
    scores = BM25Okapi(corpus).get_scores(tokenize(query))
    identifiers = {w for w in tokenize(query) if any(c in w for c in "_./-")}
    scores += np.array([sum(2 for ident in identifiers if ident in t.lower()) for t in texts])
    lexical_order = np.argsort(-scores, kind="stable")
    fused = np.zeros(len(evidence))
    for rank, idx in enumerate(lexical_order):
        fused[idx] += 1 / (60 + rank + 1)
    if settings.retrieval_mode == "hybrid":
        encoder, reranker = models(settings.embedding_model, settings.reranker_model)
        vectors = encoder.encode(texts, normalize_embeddings=True)
        q = encoder.encode([query], normalize_embeddings=True)[0]
        for rank, idx in enumerate(np.argsort(-(vectors @ q))):
            fused[idx] += 1 / (60 + rank + 1)
        candidates = np.argsort(-fused)[: min(20, len(evidence))]
        rerank = reranker.predict([(query, texts[i]) for i in candidates])
        order = [candidates[i] for i in np.argsort(-rerank)]
    else:
        order = list(np.argsort(-fused, kind="stable"))
    return [
        {**evidence[i], "retrieval_score": round(float(fused[i]), 5), "rank": rank + 1}
        for rank, i in enumerate(order[:limit])
    ]
