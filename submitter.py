import re
from datetime import datetime
import requests


class FlagSubmitter:
    def __init__(self, ctfd_url: str, token: str):
        self.ctfd_url = ctfd_url.rstrip("/")
        self._headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
        self._attempts: list[dict] = []

    def validate(self, flag: str, flag_format: str) -> bool:
        return bool(re.fullmatch(flag_format, flag))

    def submit(self, challenge_id: int, flag: str, submitting_agent: str) -> dict:
        attempt_num = len(self._attempts) + 1
        resp = requests.post(
            f"{self.ctfd_url}/api/v1/challenges/attempt",
            headers=self._headers,
            json={"challenge_id": challenge_id, "submission": flag},
        )
        status = resp.json().get("data", {}).get("status", "unknown") if resp.status_code == 200 else "error"
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "challenge_id": challenge_id,
            "flag": flag,
            "submitting_agent": submitting_agent,
            "attempt": attempt_num,
            "status": status,
        }
        self._attempts.append(record)
        return record
