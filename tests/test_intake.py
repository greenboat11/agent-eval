from unittest.mock import patch, MagicMock
import pytest
from intake.challenge_fetcher import ChallengeFetcher, ChallengeData


def test_fetcher_returns_challenge_data(tmp_path):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "id": 1,
            "name": "Hello Flags",
            "description": "Find the flag",
            "category": "web",
            "value": 100,
            "files": [],
            "flag_format": r"CTF\{[\w_]+\}",
        }
    }
    with patch("requests.get", return_value=mock_response):
        fetcher = ChallengeFetcher("http://localhost:8000", "token123", tmp_path)
        challenge = fetcher.fetch(1)
    assert isinstance(challenge, ChallengeData)
    assert challenge.id == 1
    assert challenge.title == "Hello Flags"
    assert challenge.category == "web"


def test_fetcher_raises_on_bad_status(tmp_path):
    mock_response = MagicMock()
    mock_response.status_code = 404
    with patch("requests.get", return_value=mock_response):
        fetcher = ChallengeFetcher("http://localhost:8000", "token123", tmp_path)
        with pytest.raises(RuntimeError, match="Failed to fetch"):
            fetcher.fetch(99)
