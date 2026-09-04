import json
from datetime import datetime, timezone
from pathlib import Path

from bus.message import Message, MessageType
from intake.challenge_fetcher import ChallengeData


class CapabilityReport:
    def __init__(self, challenge: ChallengeData, bus_log: list[Message], result: dict):
        self.challenge = challenge
        self.bus_log = bus_log
        self.result = result

    def generate(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        start_ts = self.bus_log[0].timestamp if self.bus_log else datetime.now(timezone.utc)
        end_ts = self.bus_log[-1].timestamp if self.bus_log else datetime.now(timezone.utc)
        elapsed = (end_ts - start_ts).total_seconds()

        escalations = [m for m in self.bus_log if m.message_type == MessageType.ESCALATION]

        data = {
            "challenge": {
                "id": self.challenge.id,
                "title": self.challenge.title,
                "category": self.challenge.category,
                "points": self.challenge.points,
            },
            "result": {
                "solved": self.result.get("solved", False),
                "flag_candidate": self.result.get("flag_candidate"),
                "solving_agent": self.result.get("solving_agent"),
                "elapsed_seconds": round(elapsed, 2),
                "escalation_count": len(escalations),
                "control_state_at_end": self.result.get("control_state", "UNKNOWN"),
            },
            "token_usage": self.result.get("token_usage", {}),
            "message_log": [m.to_dict() for m in self.bus_log],
        }

        json_path = output_dir / "capability_report.json"
        json_path.write_text(json.dumps(data, indent=2, default=str))

        md = self._render_markdown(data, escalations)
        md_path = output_dir / "capability_report.md"
        md_path.write_text(md)
        return md_path

    def _render_markdown(self, data: dict, escalations: list) -> str:
        r = data["result"]
        c = data["challenge"]
        solved_str = "YES" if r["solved"] else "NO"
        return f"""# Capability Report — {c['title']}

**Challenge:** {c['title']} ({c['category']}, {c['points']} pts)
**Solved:** {solved_str}
**Flag:** `{r['flag_candidate'] or 'N/A'}`
**Solving Agent:** {r['solving_agent'] or 'N/A'}
**Time to Result:** {r['elapsed_seconds']}s
**Escalations:** {r['escalation_count']}
**Control State at End:** {r['control_state_at_end']}

## Token Usage
{json.dumps(data['token_usage'], indent=2)}

## Escalation Events
{'None' if not escalations else chr(10).join(f"- {e.sender} -> {e.content.get('reason', 'unknown')}" for e in escalations)}
"""
