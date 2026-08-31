from dataclasses import dataclass
from pathlib import Path
import requests


@dataclass
class ChallengeData:
    id: int
    title: str
    description: str
    category: str
    points: int
    files: list[Path]
    flag_format: str


class ChallengeFetcher:
    def __init__(self, ctfd_url: str, token: str, workspace_root: Path):
        self.ctfd_url = ctfd_url.rstrip("/")
        self.token = token
        self.workspace_root = Path(workspace_root)
        self._headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}

    def fetch(self, challenge_id: int) -> ChallengeData:
        resp = requests.get(
            f"{self.ctfd_url}/api/v1/challenges/{challenge_id}",
            headers=self._headers,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch challenge {challenge_id}: HTTP {resp.status_code}")
        data = resp.json()["data"]
        workspace = self.workspace_root / str(challenge_id)
        workspace.mkdir(parents=True, exist_ok=True)
        files = self._download_files(data.get("files", []), workspace)
        return ChallengeData(
            id=data["id"],
            title=data["name"],
            description=data["description"],
            category=data["category"],
            points=data["value"],
            files=files,
            flag_format=data.get("flag_format", r"CTF\{[\w_]+\}"),
        )

    def _download_files(self, file_urls: list[str], dest: Path) -> list[Path]:
        paths = []
        for url in file_urls:
            full_url = url if url.startswith("http") else f"{self.ctfd_url}/{url.lstrip('/')}"
            resp = requests.get(full_url, headers=self._headers)
            filename = Path(url).name
            path = dest / filename
            path.write_bytes(resp.content)
            paths.append(path)
        return paths
