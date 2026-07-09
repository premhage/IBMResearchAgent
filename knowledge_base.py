"""
knowledge_base.py — PDF ingestion, chunking, embedding, and retrieval.

Maintains a persistent JSON index of all uploaded papers.  Uses watsonx
Granite Embedding for semantic search; falls back to TF-IDF cosine
similarity when embeddings are unavailable.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from typing import Any, Optional

import numpy as np

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

from config import KB_INDEX_FILE, UPLOAD_FOLDER


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _chunk_text(text: str, chunk_size: int = 600, overlap: int = 80) -> list[str]:
    """Split text into overlapping word-level chunks."""
    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += chunk_size - overlap
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
#  PDF text extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> str:
    """Try PyMuPDF first, fall back to pypdf."""
    text = ""
    if PYMUPDF_AVAILABLE:
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                text += page.get_text()
            doc.close()
            if len(text.strip()) > 100:
                return _clean_text(text)
        except Exception:
            pass

    if PYPDF_AVAILABLE:
        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                text += page.extract_text() or ""
            return _clean_text(text)
        except Exception:
            pass

    raise RuntimeError(f"Cannot extract text from {pdf_path}")


# ─────────────────────────────────────────────────────────────────────────────
#  Metadata extraction (heuristic)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_metadata(text: str, filename: str) -> dict[str, str]:
    """Heuristically pull title, authors, year from first 1 500 chars."""
    snippet = text[:1500]
    lines = [l.strip() for l in snippet.splitlines() if len(l.strip()) > 10]

    title = lines[0] if lines else os.path.splitext(filename)[0]

    year_m = re.search(r"\b(19|20)\d{2}\b", snippet)
    year = year_m.group(0) if year_m else "n.d."

    # Very rough author heuristic: line with commas and capitalised words
    authors = "Unknown Authors"
    for line in lines[1:6]:
        if re.search(r"[A-Z][a-z]+,?\s+[A-Z]", line) and len(line) < 200:
            authors = line
            break

    return {"title": title, "authors": authors, "year": year}


# ─────────────────────────────────────────────────────────────────────────────
#  Knowledge-base index (persistent JSON)
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeBase:
    """
    Stores paper metadata + text chunks.  Embeddings are computed lazily
    and cached in the index so they survive server restarts.
    """

    def __init__(self, index_path: str = KB_INDEX_FILE):
        self.index_path = index_path
        self._data: dict[str, Any] = self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self) -> None:
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def add_paper(
        self,
        pdf_path: str,
        filename: str,
        embed_fn=None,
        is_test_case: bool = False,
    ) -> dict[str, Any]:
        """
        Ingest a PDF.  Returns the paper record.
        embed_fn(texts: list[str]) -> list[list[float]]  (optional)
        """
        sha = _sha256(pdf_path)
        if sha in self._data:
            return self._data[sha]

        text = extract_text_from_pdf(pdf_path)
        meta = _extract_metadata(text, filename)
        chunks = _chunk_text(text)

        embeddings: list[list[float]] = []
        if embed_fn and chunks:
            try:
                embeddings = embed_fn(chunks)
            except Exception:
                embeddings = []

        record: dict[str, Any] = {
            "sha256": sha,
            "filename": filename,
            "title": meta["title"],
            "authors": meta["authors"],
            "year": meta["year"],
            "full_text": text,
            "chunks": chunks,
            "embeddings": embeddings,
            "is_test_case": is_test_case,
            "ingested_at": time.time(),
        }
        self._data[sha] = record
        self._save()
        return record

    def remove_paper(self, sha: str) -> bool:
        if sha in self._data:
            del self._data[sha]
            self._save()
            return True
        return False

    def list_papers(self) -> list[dict[str, Any]]:
        return [
            {k: v for k, v in p.items() if k not in ("chunks", "embeddings", "full_text")}
            for p in self._data.values()
        ]

    def get_paper(self, sha: str) -> Optional[dict[str, Any]]:
        return self._data.get(sha)

    def get_all_text(self) -> str:
        """Concatenate all paper full texts (for gap/contradiction analysis)."""
        return "\n\n".join(
            f"=== {p['title']} ({p['year']}) ===\n{p['full_text']}"
            for p in self._data.values()
        )

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int = 6,
        embed_fn=None,
    ) -> list[dict[str, Any]]:
        """
        Return top-k relevant chunks.  Uses cosine similarity over
        precomputed embeddings when available; otherwise TF-IDF fallback.
        """
        if not self._data:
            return []

        all_chunks: list[str] = []
        chunk_meta: list[dict[str, str]] = []
        all_embeddings: list[list[float]] = []

        for paper in self._data.values():
            for i, chunk in enumerate(paper["chunks"]):
                all_chunks.append(chunk)
                chunk_meta.append({
                    "sha256": paper["sha256"],
                    "title": paper["title"],
                    "authors": paper["authors"],
                    "year": paper["year"],
                    "chunk_index": i,
                })
                if paper["embeddings"] and i < len(paper["embeddings"]):
                    all_embeddings.append(paper["embeddings"][i])

        # ── semantic retrieval ─────────────────────────────────────────────
        if all_embeddings and embed_fn:
            try:
                q_emb = embed_fn([query])[0]
                scores = _cosine_scores(q_emb, all_embeddings)
                top_idx = np.argsort(scores)[::-1][:top_k]
                return [
                    {"chunk": all_chunks[i], "score": float(scores[i]), **chunk_meta[i]}
                    for i in top_idx
                ]
            except Exception:
                pass

        # ── TF-IDF fallback ────────────────────────────────────────────────
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as sk_cos

        try:
            corpus = all_chunks + [query]
            vec = TfidfVectorizer(stop_words="english", max_features=8000)
            tfidf = vec.fit_transform(corpus)
            scores = sk_cos(tfidf[-1], tfidf[:-1]).flatten()
            top_idx = np.argsort(scores)[::-1][:top_k]
            return [
                {"chunk": all_chunks[i], "score": float(scores[i]), **chunk_meta[i]}
                for i in top_idx
            ]
        except Exception:
            # Last resort: return first top_k chunks
            return [
                {"chunk": all_chunks[i], "score": 0.0, **chunk_meta[i]}
                for i in range(min(top_k, len(all_chunks)))
            ]


def _cosine_scores(
    query_vec: list[float], matrix: list[list[float]]
) -> np.ndarray:
    q = np.array(query_vec, dtype=np.float32)
    m = np.array(matrix, dtype=np.float32)
    q_norm = np.linalg.norm(q)
    m_norms = np.linalg.norm(m, axis=1, keepdims=True)
    if q_norm == 0:
        return np.zeros(len(matrix))
    m_norms = np.where(m_norms == 0, 1e-10, m_norms)
    return (m @ q) / (m_norms.flatten() * q_norm)


# ── Module-level singleton ────────────────────────────────────────────────────
kb = KnowledgeBase()
