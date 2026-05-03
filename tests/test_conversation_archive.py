"""Tests for conversation_archive module."""
import pytest
from chatbot_kjri_dubai.conversation_archive import detect_gratitude_closure


# ---------------------------------------------------------------------------
# Positive cases — should return "gratitude"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "terima kasih",
    "Terima Kasih banyak",
    "makasih ya!",
    "Thanks!",
    "thank you so much",
    "bye",
    "Bye!",
    "sampai jumpa",
    "selamat tinggal",
    "ok makasih, sudah cukup",
    "sudah selesai, terima kasih",
    "oke bye",
    "thanks, goodbye",
    "dadah",
    "terima kasih banyak, sudah sangat membantu",
])
def test_detect_gratitude_closure_positive(text):
    result = detect_gratitude_closure(text)
    assert result == "gratitude", f"Expected 'gratitude' for: {text!r}"


# ---------------------------------------------------------------------------
# Negative cases — should return None
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "halo, saya ingin tanya",
    "paspor saya hilang",
    "bagaimana cara memperbarui paspor?",
    "mantap",
    "oke",
    "baik",
    "ya",
])
def test_detect_gratitude_closure_negative(text):
    result = detect_gratitude_closure(text)
    assert result is None, f"Expected None for: {text!r}"


# ---------------------------------------------------------------------------
# Anti-false-positive: "terima kasih tapi ..." — continuation signals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "terima kasih tapi saya mau tanya satu lagi",
    "makasih, tapi gimana kalau dokumen saya berbeda?",
    "ok makasih, ada yang perlu saya siapkan?",
    "terima kasih, bagaimana jika paspor saya sudah expired?",
    "thanks, tapi namun saya masih bingung",
    "terima kasih! satu lagi pertanyaan: apakah perlu membawa foto?",
    "makasih, mau tanya soal biaya juga dong",
    "terima kasih, apakah prosesnya bisa dipercepat?",
])
def test_detect_gratitude_closure_continuation(text):
    result = detect_gratitude_closure(text)
    assert result is None, f"Expected None (continuation signal) for: {text!r}"


# ---------------------------------------------------------------------------
# Anti-false-positive: message with '?' should not trigger closure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "terima kasih, ada informasi lain?",
    "makasih, berapa harganya?",
    "thanks, bisa tolong jelaskan lagi?",
])
def test_detect_gratitude_closure_question_mark(text):
    result = detect_gratitude_closure(text)
    assert result is None, f"Expected None (has '?') for: {text!r}"
