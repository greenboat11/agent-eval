from unittest.mock import patch, MagicMock
import pytest
from submitter import FlagSubmitter


def test_validate_correct_flag():
    s = FlagSubmitter("http://localhost:8000", "token")
    assert s.validate("CTF{hello_world}", r"CTF\{[\w_]+\}") is True


def test_validate_wrong_flag():
    s = FlagSubmitter("http://localhost:8000", "token")
    assert s.validate("notaflag", r"CTF\{[\w_]+\}") is False


def test_submit_returns_correct_status():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"status": "correct"}}
    with patch("requests.post", return_value=mock_response):
        s = FlagSubmitter("http://localhost:8000", "token")
        result = s.submit(1, "CTF{flag}", "crypto_agent")
    assert result["status"] == "correct"
    assert result["flag"] == "CTF{flag}"
    assert result["submitting_agent"] == "crypto_agent"
