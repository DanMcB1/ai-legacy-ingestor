"""Local vector store: SQLite for chunks and provenance, TF-IDF (or optional SBERT) for search."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .models import Chunk, QualityReport, ScoredChunk
from .paths import INDEX_DB, INDEX_DIR

DEFAULT_TOP_K = 5
MIN_SHOW_SCORE = 0.08


def _embedding_choice() -> str:
    return os.environ.get("LEGACY_INGESTOR_EMBEDDINGS", "tfidf").strip().lower()


class TfidfBackend:
    """Sparse TF-IDF vectors. Default: no model download, runs offline."""

    name = "tfidf"

    def __init__(self, texts: list[str]) -> None:
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,
        )
        self.matrix = self.vectorizer.fit_transform(texts)

    def similarities(self, query: str) -> np.ndarray:
        query_vec = self.vectorizer.transform([query])
        return cosine_similarity(query_vec, self.matrix).ravel()


class SbertBackend:
    """Optional dense embeddings. Only used when explicitly requested."""

    name = "sbert"

    def __init__(self, texts: list[str]) -> None:
        from sentence_transformers import SentenceTransformer

        model_name = os.environ.get(
            "LEGACY_INGESTOR_SBERT_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        self.model = SentenceTransformer(model_name)
        vectors = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        self.matrix = np.asarray(vectors, dtype=np.float32)

    def similarities(self, query: str) -> np.ndarray:
        vector = self.model.encode([query], normalize_embeddings=True, show_progress_bar=False)
        return (self.matrix @ np.asarray(vector, dtype=np.float32).ravel())


def _open_backend(texts: list[str]):
    choice = _embedding_choice()
    if choice in {"sbert", "sentence-transformers", "minilm"}:
        try:
            return SbertBackend(texts)
        except Exception:
            return TfidfBackend(texts)
    return TfidfBackend(texts)


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_type TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            page INTEGER,
            record_number INTEGER,
            line_start INTEGER,
            line_end INTEGER,
            ocr_confidence REAL,
            record_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    return conn


def _row_to_chunk(row: sqlite3.Row) -> Chunk:
    metadata = json.loads(row["metadata_json"] or "{}")
    return Chunk(
        id=row["id"],
        text=row["text"],
        source_file=row["source_file"],
        source_type=row["source_type"],
        chunk_index=int(row["chunk_index"]),
        page=row["page"],
        record_number=row["record_number"],
        line_start=row["line_start"],
        line_end=row["line_end"],
        ocr_confidence=row["ocr_confidence"],
        record_id=row["record_id"],
        metadata=metadata,
    )


class VectorStore:
    """SQLite-backed chunk store plus an in-memory TF-IDF (or SBERT) index."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else INDEX_DB
        self.chunks: list[Chunk] = []
        self.backend = None
        self.backend_name = "tfidf"
        self.report: QualityReport | None = None

    def clear(self) -> None:
        self.chunks = []
        self.backend = None
        self.report = None
        if self.db_path.is_file():
            self.db_path.unlink()

    def add_chunks(self, chunks: list[Chunk]) -> None:
        self.chunks.extend(chunks)

    def build(self) -> None:
        texts = [c.text for c in self.chunks]
        if not texts:
            self.backend = None
            return
        self.backend = _open_backend(texts)
        self.backend_name = self.backend.name

    def save(self, report: QualityReport | None = None) -> Path:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        if self.db_path.is_file():
            self.db_path.unlink()
        conn = _connect(self.db_path)
        try:
            conn.execute("DELETE FROM chunks")
            for chunk in self.chunks:
                conn.execute(
                    """
                    INSERT INTO chunks (
                        id, text, source_file, source_type, chunk_index, page,
                        record_number, line_start, line_end, ocr_confidence,
                        record_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.id,
                        chunk.text,
                        chunk.source_file,
                        chunk.source_type,
                        chunk.chunk_index,
                        chunk.page,
                        chunk.record_number,
                        chunk.line_start,
                        chunk.line_end,
                        chunk.ocr_confidence,
                        chunk.record_id,
                        json.dumps(chunk.metadata),
                    ),
                )
            payload = {
                "backend": self.backend_name,
                "chunk_count": len(self.chunks),
            }
            if report is not None:
                payload["report"] = report.to_dict()
                self.report = report
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("info", json.dumps(payload)),
            )
            conn.commit()
        finally:
            conn.close()
        return self.db_path

    def load(self) -> None:
        if not self.db_path.is_file():
            self.chunks = []
            self.backend = None
            return
        conn = _connect(self.db_path)
        try:
            rows = conn.execute("SELECT * FROM chunks ORDER BY source_file, chunk_index").fetchall()
            self.chunks = [_row_to_chunk(row) for row in rows]
            info = conn.execute("SELECT value FROM meta WHERE key = 'info'").fetchone()
            if info:
                payload = json.loads(info["value"])
                report_data = payload.get("report")
                if report_data:
                    self.report = QualityReport(**report_data)
        finally:
            conn.close()
        self.build()

    def search(self, query: str, k: int = DEFAULT_TOP_K) -> list[ScoredChunk]:
        if not query.strip() or not self.chunks:
            return []
        if self.backend is None:
            self.build()
        if self.backend is None:
            return []
        scores = self.backend.similarities(query)
        if scores.size == 0:
            return []
        order = np.argsort(-scores)
        hits: list[ScoredChunk] = []
        for index in order:
            score = float(scores[index])
            if score < MIN_SHOW_SCORE:
                break
            hits.append(ScoredChunk(chunk=self.chunks[int(index)], score=score))
            if len(hits) >= k:
                break
        return hits
