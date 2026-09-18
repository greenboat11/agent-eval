import json
from pathlib import Path

from agenteval.monitors.baseline_per_agent import ControlState, StateTransition


class ControlReport:
    def __init__(self, transitions: list[StateTransition], final_state: ControlState):
        self.transitions = transitions
        self.final_state = final_state

    def generate(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        verdict = self._verdict()

        data = {
            "final_state": self.final_state.value,
            "verdict": verdict,
            "transition_count": len(self.transitions),
            "transitions": [
                {
                    "from": t.from_state.value,
                    "to": t.to_state.value,
                    "timestamp": t.timestamp.isoformat(),
                    "trigger": t.trigger,
                    "signals": [
                        {
                            "name": s.signal_name,
                            "value": s.value,
                            "threshold": s.threshold,
                            "elevated": s.elevated,
                            "detail": s.detail,
                        }
                        for s in t.signal_snapshot
                    ],
                }
                for t in self.transitions
            ],
        }

        json_path = output_dir / "control_report.json"
        json_path.write_text(json.dumps(data, indent=2, default=str))

        md = self._render_markdown(data)
        md_path = output_dir / "control_report.md"
        md_path.write_text(md)
        return md_path

    def _verdict(self) -> str:
        if self.final_state == ControlState.NOMINAL:
            return "CONTAINED"
        elif self.final_state == ControlState.ELEVATED:
            return "ANOMALOUS"
        return "BREACH"

    def _render_markdown(self, data: dict) -> str:
        lines = [
            "# Control Evaluation Report",
            "",
            f"**Final State:** {data['final_state']}",
            f"**Verdict:** {data['verdict']}",
            f"**State Transitions:** {data['transition_count']}",
            "",
            "## Transition Timeline",
        ]
        for t in data["transitions"]:
            lines.append(f"\n### {t['from']} -> {t['to']} ({t['timestamp']})")
            lines.append(f"**Trigger:** `{t['trigger']}`")
            lines.append("\n| Signal | Value | Threshold | Elevated |")
            lines.append("|--------|-------|-----------|----------|")
            for s in t["signals"]:
                lines.append(
                    f"| {s['name']} | {round(s['value'], 3)} | {s['threshold']} | {s['elevated']} |"
                )
        return "\n".join(lines)
