"""
Unit and integration tests for KeywordSearcher — Phase 2 Task 1.

Test strategy:
- All unit tests mock psycopg2 to avoid requiring a live database.
- The integration fixture test uses Phase 1 DocumentChunk data shapes.
- RED phase: import from retrieval.py which does not yet exist — all tests fail.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from chatbot_kjri_dubai.rag.retrieval import KeywordSearcher, ResultChunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_connection():
    """Return a mock psycopg2 connection with cursor support."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = lambda s: cursor
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


@pytest.fixture
def sample_db_rows():
    """
    Simulate rows returned by PostgreSQL FTS query.

    Columns: id, document_id, chunk_number, chunk_text,
             start_char, end_char, chunk_tokens, relevance_score
    """
    return [
        ("chunk-001", "doc-abc", 0, "Paspor dan visa diperlukan untuk perjalanan ke luar negeri.", 0,   57,  12, 0.42),
        ("chunk-002", "doc-abc", 1, "Persyaratan paspor: foto terbaru, KTP, akta kelahiran.",      57, 109,  11, 0.31),
        ("chunk-003", "doc-xyz", 0, "Legalisasi dokumen membutuhkan paspor yang masih berlaku.",  0,   56,  10, 0.18),
    ]


@pytest.fixture
def searcher():
    """
    Return a KeywordSearcher whose psycopg2 connection is fully mocked.

    The connect call is patched so no real DB is contacted.
    """
    with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect") as mock_connect:
        mock_connect.return_value = MagicMock()
        ks = KeywordSearcher(db_connection_string="postgresql://user:pass@localhost/testdb")
    return ks


# ---------------------------------------------------------------------------
# ResultChunk dataclass
# ---------------------------------------------------------------------------

class TestResultChunk:
    """ResultChunk must carry all DocumentChunk fields plus relevance_score."""

    def test_result_chunk_creation(self):
        """ResultChunk instantiates with required fields and a relevance score."""
        rc = ResultChunk(
            id="chunk-001",
            document_id="doc-abc",
            chunk_number=0,
            chunk_text="Paspor diperlukan.",
            start_char=0,
            end_char=18,
            chunk_tokens=4,
            relevance_score=0.75,
        )
        assert rc.id == "chunk-001"
        assert rc.document_id == "doc-abc"
        assert rc.chunk_number == 0
        assert rc.chunk_text == "Paspor diperlukan."
        assert rc.start_char == 0
        assert rc.end_char == 18
        assert rc.chunk_tokens == 4
        assert rc.relevance_score == 0.75

    def test_result_chunk_relevance_score_is_float(self):
        """relevance_score field must accept float values."""
        rc = ResultChunk(
            id="c1", document_id="d1", chunk_number=0,
            chunk_text="text", start_char=0, end_char=4, chunk_tokens=1,
            relevance_score=0.0,
        )
        assert isinstance(rc.relevance_score, float)

    def test_result_chunk_default_score_zero(self):
        """relevance_score defaults to 0.0 when not supplied."""
        rc = ResultChunk(
            id="c1", document_id="d1", chunk_number=0,
            chunk_text="text", start_char=0, end_char=4, chunk_tokens=1,
        )
        assert rc.relevance_score == 0.0


# ---------------------------------------------------------------------------
# KeywordSearcher — initialisation
# ---------------------------------------------------------------------------

class TestKeywordSearcherInit:
    """KeywordSearcher must connect on construction and expose connection."""

    def test_init_calls_psycopg2_connect(self):
        """Constructor must call psycopg2.connect with the supplied DSN."""
        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            KeywordSearcher("postgresql://user:pass@localhost/testdb")
            mock_connect.assert_called_once_with("postgresql://user:pass@localhost/testdb")

    def test_init_stores_connection(self):
        """Constructor must store the connection on self.connection."""
        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect") as mock_connect:
            fake_conn = MagicMock()
            mock_connect.return_value = fake_conn
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")
            assert ks.connection is fake_conn

    def test_init_connection_failure_raises_connection_error(self):
        """If psycopg2.connect raises, KeywordSearcher must raise ConnectionError."""
        import psycopg2
        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect") as mock_connect:
            mock_connect.side_effect = psycopg2.OperationalError("Connection refused")
            with pytest.raises(ConnectionError, match="Cannot connect to database"):
                KeywordSearcher("postgresql://user:pass@badhost/testdb")


# ---------------------------------------------------------------------------
# Test 1: Happy path — basic keyword search
# ---------------------------------------------------------------------------

class TestKeywordSearchBasic:

    def test_keyword_search_basic(self, mock_connection, sample_db_rows):
        """
        Happy path: search returns a list of ResultChunk objects
        ordered by relevance_score descending.
        """
        conn, cursor = mock_connection
        cursor.fetchall.return_value = sample_db_rows

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        results = ks.search("paspor")

        assert isinstance(results, list)
        assert len(results) == 3
        assert all(isinstance(r, ResultChunk) for r in results)
        # First result must have the highest relevance score
        assert results[0].relevance_score >= results[1].relevance_score >= results[2].relevance_score

    def test_keyword_search_maps_columns_correctly(self, mock_connection, sample_db_rows):
        """Each ResultChunk field must be mapped from the correct DB column."""
        conn, cursor = mock_connection
        cursor.fetchall.return_value = [sample_db_rows[0]]

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        results = ks.search("paspor")

        r = results[0]
        assert r.id == "chunk-001"
        assert r.document_id == "doc-abc"
        assert r.chunk_number == 0
        assert r.chunk_text == "Paspor dan visa diperlukan untuk perjalanan ke luar negeri."
        assert r.start_char == 0
        assert r.end_char == 57
        assert r.chunk_tokens == 12
        assert r.relevance_score == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# Test 2: Threshold filtering
# ---------------------------------------------------------------------------

class TestKeywordSearchThreshold:

    def test_keyword_search_threshold_filter(self, mock_connection, sample_db_rows):
        """
        Results with relevance_score below threshold must be excluded.

        sample_db_rows scores: 0.42, 0.31, 0.18
        With threshold=0.20, the last row (0.18) must be dropped.
        """
        conn, cursor = mock_connection
        cursor.fetchall.return_value = sample_db_rows

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        results = ks.search("paspor", threshold=0.20)

        assert len(results) == 2
        assert all(r.relevance_score >= 0.20 for r in results)

    def test_keyword_search_threshold_zero_returns_all(self, mock_connection, sample_db_rows):
        """threshold=0.0 must not filter any result."""
        conn, cursor = mock_connection
        cursor.fetchall.return_value = sample_db_rows

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        results = ks.search("paspor", threshold=0.0)

        assert len(results) == 3

    def test_keyword_search_threshold_above_all_returns_empty(self, mock_connection, sample_db_rows):
        """threshold higher than every score must return an empty list."""
        conn, cursor = mock_connection
        cursor.fetchall.return_value = sample_db_rows

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        results = ks.search("paspor", threshold=1.0)

        assert results == []


# ---------------------------------------------------------------------------
# Test 3: max_results limit
# ---------------------------------------------------------------------------

class TestKeywordSearchMaxResults:

    def test_keyword_search_max_results(self, mock_connection, sample_db_rows):
        """
        max_results must be passed to the SQL LIMIT clause so the DB
        never returns more rows than requested.
        """
        conn, cursor = mock_connection
        # DB honours LIMIT — returns only 2 rows
        cursor.fetchall.return_value = sample_db_rows[:2]

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        results = ks.search("paspor", max_results=2)

        assert len(results) == 2

    def test_keyword_search_max_results_passed_to_query(self, mock_connection):
        """max_results value must appear in the SQL execute parameters."""
        conn, cursor = mock_connection
        cursor.fetchall.return_value = []

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        ks.search("visa", max_results=5)

        # The execute call must include 5 somewhere in its args tuple
        call_args = cursor.execute.call_args
        sql_params = call_args[0][1]  # second positional arg to execute() is the params tuple
        assert 5 in sql_params

    def test_keyword_search_default_max_results_is_ten(self, mock_connection):
        """Default max_results must be 10."""
        conn, cursor = mock_connection
        cursor.fetchall.return_value = []

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        ks.search("visa")

        call_args = cursor.execute.call_args
        sql_params = call_args[0][1]
        assert 10 in sql_params


# ---------------------------------------------------------------------------
# Test 4: No results
# ---------------------------------------------------------------------------

class TestKeywordSearchNoResults:

    def test_keyword_search_no_results(self, mock_connection):
        """When DB returns no rows, search must return an empty list (not raise)."""
        conn, cursor = mock_connection
        cursor.fetchall.return_value = []

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        results = ks.search("xyzzy_nonexistent_term")

        assert results == []
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Test 5: Invalid query — empty string
# ---------------------------------------------------------------------------

class TestKeywordSearchInvalidQueryEmpty:

    def test_keyword_search_invalid_query_empty(self, searcher):
        """Empty string query must raise ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            searcher.search("")

    def test_keyword_search_invalid_query_whitespace_only(self, searcher):
        """Whitespace-only query must be treated as empty and raise ValueError."""
        with pytest.raises(ValueError, match="Query cannot be empty"):
            searcher.search("   ")


# ---------------------------------------------------------------------------
# Test 6: Invalid query — too short
# ---------------------------------------------------------------------------

class TestKeywordSearchInvalidQueryTooShort:

    def test_keyword_search_invalid_query_too_short(self, searcher):
        """Query shorter than 3 characters must raise ValueError."""
        with pytest.raises(ValueError, match="Query must be at least 3 characters"):
            searcher.search("ab")

    def test_keyword_search_exactly_3_chars_is_valid(self, mock_connection):
        """A 3-character query must NOT raise — boundary value check."""
        conn, cursor = mock_connection
        cursor.fetchall.return_value = []

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        # Must not raise
        results = ks.search("abc")
        assert isinstance(results, list)

    def test_keyword_search_single_char_raises(self, searcher):
        """Single character query must raise ValueError."""
        with pytest.raises(ValueError, match="Query must be at least 3 characters"):
            searcher.search("a")


# ---------------------------------------------------------------------------
# Test 7: Invalid query — None
# ---------------------------------------------------------------------------

class TestKeywordSearchInvalidQueryNone:

    def test_keyword_search_invalid_query_none(self, searcher):
        """None query must raise ValueError."""
        with pytest.raises(ValueError, match="Query cannot be None"):
            searcher.search(None)

    def test_keyword_search_invalid_query_non_string(self, searcher):
        """Non-string query types must raise ValueError."""
        with pytest.raises(ValueError):
            searcher.search(42)

        with pytest.raises(ValueError):
            searcher.search(["paspor"])


# ---------------------------------------------------------------------------
# Test 8: Database connection failure during search
# ---------------------------------------------------------------------------

class TestKeywordSearchDbConnectionFailure:

    def test_keyword_search_db_connection_failure(self, mock_connection):
        """
        When cursor.execute raises OperationalError (e.g., DB went away),
        search must raise RuntimeError with context message.
        """
        import psycopg2
        conn, cursor = mock_connection
        cursor.execute.side_effect = psycopg2.OperationalError("server closed the connection unexpectedly")

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        with pytest.raises(RuntimeError, match="Keyword search failed"):
            ks.search("paspor")

    def test_keyword_search_unexpected_db_error(self, mock_connection):
        """
        Any unexpected exception from the DB layer must be wrapped
        in a RuntimeError (not propagate raw).
        """
        import psycopg2
        conn, cursor = mock_connection
        cursor.execute.side_effect = psycopg2.DatabaseError("syntax error")

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        with pytest.raises(RuntimeError, match="Keyword search failed"):
            ks.search("visa")


# ---------------------------------------------------------------------------
# Test 9: Integration with Phase 1 fixtures
# ---------------------------------------------------------------------------

class TestKeywordSearchIntegrationWithPhase1Fixtures:
    """
    Verify KeywordSearcher works with the same data shapes produced by
    Phase 1 DocumentManager (DocumentChunk fields).

    No live DB is required — we mock psycopg2 to return rows that mirror
    what the document_chunks table stores for Phase 1 processed documents.
    """

    @pytest.fixture
    def phase1_style_rows(self):
        """
        Rows shaped after Phase 1 DocumentChunk output stored in PostgreSQL.
        Mirrors: document_id, chunk_number, text, start_char, end_char, tokens.
        """
        return [
            (
                "chunk-p1-001",
                "doc-kjri-services",
                0,
                "Layanan konsuler KJRI Dubai mencakup pengurusan paspor, visa, dan legalisasi dokumen.",
                0,
                85,
                18,
                0.55,
            ),
            (
                "chunk-p1-002",
                "doc-kjri-services",
                1,
                "Biaya pengurusan paspor baru adalah AED 120 dengan waktu proses 5 hari kerja.",
                85,
                160,
                16,
                0.38,
            ),
        ]

    def test_keyword_search_integration_with_phase1_fixtures(self, mock_connection, phase1_style_rows):
        """
        search() must correctly map Phase 1 document_chunks table columns
        to ResultChunk objects, preserving document_id and chunk_number linkage.
        """
        conn, cursor = mock_connection
        cursor.fetchall.return_value = phase1_style_rows

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        results = ks.search("paspor layanan")

        assert len(results) == 2

        # Verify Phase 1 field mapping
        assert results[0].document_id == "doc-kjri-services"
        assert results[0].chunk_number == 0
        assert results[1].chunk_number == 1

        # Verify scores preserved
        assert results[0].relevance_score == pytest.approx(0.55)
        assert results[1].relevance_score == pytest.approx(0.38)

        # Verify both results share the same document_id (intra-doc chunking)
        assert results[0].document_id == results[1].document_id


# ---------------------------------------------------------------------------
# Test 10: Indonesian stemming / language awareness (optional boundary)
# ---------------------------------------------------------------------------

class TestKeywordSearchIndonesianStemming:
    """
    Verify the SQL uses 'indonesian' text search configuration.
    This is a behavioural contract test — we inspect the SQL sent to
    the DB cursor, not the linguistic output.
    """

    def test_keyword_search_uses_indonesian_language_config(self, mock_connection):
        """
        The SQL executed must reference 'indonesian' text search configuration
        to ensure language-aware stemming for Bahasa Indonesia queries.
        """
        conn, cursor = mock_connection
        cursor.fetchall.return_value = []

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        ks.search("layanan konsuler")

        call_args = cursor.execute.call_args
        sql = call_args[0][0]  # first positional arg to execute() is the SQL string
        assert "indonesian" in sql.lower(), (
            "SQL must use 'indonesian' text search config for Bahasa Indonesia stemming"
        )

    def test_keyword_search_query_passed_as_parameter_not_interpolated(self, mock_connection):
        """
        Query string must be passed as a parameter (not string-interpolated)
        to prevent SQL injection.
        """
        conn, cursor = mock_connection
        cursor.fetchall.return_value = []

        with patch("chatbot_kjri_dubai.rag.retrieval.psycopg2.connect", return_value=conn):
            ks = KeywordSearcher("postgresql://user:pass@localhost/testdb")

        malicious_query = "'; DROP TABLE document_chunks; --"
        # Must not raise — must be safely parameterised
        ks.search(malicious_query)

        call_args = cursor.execute.call_args
        sql = call_args[0][0]
        # The raw injection string must NOT appear in the SQL template
        assert "DROP TABLE" not in sql
