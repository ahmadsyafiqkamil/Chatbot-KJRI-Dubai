"""
Phase 2 RAG Retrieval Pipeline.

Task 1 — KeywordSearcher: PostgreSQL full-text search on document_chunks table.
Task 2 — SemanticSearcher: ChromaDB vector similarity search (not yet implemented).
Task 3 — HybridRetriever: Combines keyword + semantic results (not yet implemented).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class ResultChunk:
    """
    A document chunk returned by a retrieval operation.

    Extends the Phase 1 DocumentChunk shape with a relevance_score field
    that records how closely the chunk matched the search query.
    """

    id: str
    document_id: str
    chunk_number: int
    chunk_text: str
    start_char: int
    end_char: int
    chunk_tokens: int
    relevance_score: float = 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# PostgreSQL FTS query using the 'indonesian' text search configuration.
# Parameters (in order): query_text, query_text (repeated for WHERE clause), max_results.
_FTS_SQL = """
SELECT
    dc.id,
    dc.document_id,
    dc.chunk_number,
    dc.chunk_text,
    dc.start_char,
    dc.end_char,
    dc.chunk_tokens,
    ts_rank(
        to_tsvector('indonesian', dc.chunk_text),
        plainto_tsquery('indonesian', %s)
    ) AS relevance_score
FROM document_chunks dc
WHERE
    to_tsvector('indonesian', dc.chunk_text)
    @@ plainto_tsquery('indonesian', %s)
ORDER BY relevance_score DESC
LIMIT %s;
"""


def _validate_query(query: object) -> str:
    """
    Validate and normalise the search query.

    Args:
        query: Raw query value supplied by caller.

    Returns:
        Stripped query string.

    Raises:
        ValueError: If query is None, not a string, empty, or too short.
    """
    if query is None:
        raise ValueError("Query cannot be None")

    if not isinstance(query, str):
        raise ValueError(
            f"Query must be a string, got {type(query).__name__}"
        )

    stripped = query.strip()

    if not stripped:
        raise ValueError("Query cannot be empty")

    if len(stripped) < 3:
        raise ValueError(
            f"Query must be at least 3 characters, got {len(stripped)!r}"
        )

    return stripped


# ---------------------------------------------------------------------------
# KeywordSearcher
# ---------------------------------------------------------------------------

class KeywordSearcher:
    """
    Full-text keyword search over the document_chunks PostgreSQL table.

    Uses PostgreSQL's built-in FTS with the 'indonesian' text search
    configuration, which applies Bahasa Indonesia stemming rules.

    Usage::

        searcher = KeywordSearcher("postgresql://user:pass@localhost/db")
        results = searcher.search("pengurusan paspor", max_results=5)
        for chunk in results:
            print(chunk.relevance_score, chunk.chunk_text[:80])
    """

    def __init__(self, db_connection_string: str) -> None:
        """
        Establish a synchronous psycopg2 connection to PostgreSQL.

        Args:
            db_connection_string: libpq connection string or DSN URL.
                Example: "postgresql://user:pass@localhost:5432/mydb"

        Raises:
            ConnectionError: If the database is unreachable or credentials
                are invalid.
        """
        try:
            self.connection = psycopg2.connect(db_connection_string)
            logger.debug("KeywordSearcher connected to database.")
        except psycopg2.OperationalError as exc:
            raise ConnectionError(
                f"Cannot connect to database: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        query: object,
        max_results: int = 10,
        threshold: float = 0.1,
    ) -> List[ResultChunk]:
        """
        Search document_chunks using PostgreSQL full-text search.

        The query is matched against chunk_text using the 'indonesian'
        text search configuration. Results are filtered by threshold and
        ordered by relevance_score descending.

        Args:
            query: Search query string (Bahasa Indonesia or English).
                   Must be a non-empty string of at least 3 characters.
            max_results: Maximum number of rows to request from PostgreSQL
                         via the LIMIT clause. Defaults to 10.
            threshold: Minimum ts_rank score to include in the returned
                       list. Rows below this value are dropped after
                       retrieval. Defaults to 0.1.

        Returns:
            List of ResultChunk objects ordered by relevance_score
            descending. Empty list if no matches exceed the threshold.

        Raises:
            ValueError: If query is None, not a string, empty, or
                        shorter than 3 characters.
            RuntimeError: If the SQL query fails (wraps psycopg2
                          exceptions with context).
        """
        normalised = _validate_query(query)

        logger.debug(
            "KeywordSearcher.search query=%r max_results=%d threshold=%f",
            normalised, max_results, threshold,
        )

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    _FTS_SQL,
                    (normalised, normalised, max_results),
                )
                rows = cursor.fetchall()
        except psycopg2.Error as exc:
            raise RuntimeError(
                f"Keyword search failed for query {normalised!r}: {exc}"
            ) from exc

        results = [self._row_to_result_chunk(row) for row in rows]
        results = [r for r in results if r.relevance_score >= threshold]

        logger.debug(
            "KeywordSearcher.search returned %d results (threshold=%f)",
            len(results), threshold,
        )
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_result_chunk(row: tuple) -> ResultChunk:
        """
        Map a raw database row tuple to a ResultChunk dataclass.

        Expected column order (matches _FTS_SQL SELECT list):
            0  id
            1  document_id
            2  chunk_number
            3  chunk_text
            4  start_char
            5  end_char
            6  chunk_tokens
            7  relevance_score

        Args:
            row: Tuple returned by psycopg2 cursor.fetchall().

        Returns:
            Populated ResultChunk instance.
        """
        return ResultChunk(
            id=row[0],
            document_id=row[1],
            chunk_number=row[2],
            chunk_text=row[3],
            start_char=row[4],
            end_char=row[5],
            chunk_tokens=row[6],
            relevance_score=float(row[7]),
        )
