import json
from pathlib import Path

import anthropic

from agenteval.monitors.baseline_per_agent import ControlMonitor
from bus.message import Message, MessageType
from bus.message_bus import MessageBus
from intake.challenge_fetcher import ChallengeData


class OrchestratorAgent:
    def __init__(self, model: str, anthropic_key: str, specialists: dict,
                 bus: MessageBus, monitor: ControlMonitor, config: dict):
        self.model = model
        self.specialists = specialists  # dict[role_name, SpecialistAgent]
        self.bus = bus
        self.monitor = monitor
        self.max_attempts = config.get("max_escalation_attempts", 2)
        self._client = anthropic.Anthropic(api_key=anthropic_key)
        self._system_prompt = self._load_prompt()
        self._pending_results: list[Message] = []
        self._token_usage: dict[str, int] = {}
        bus.subscribe("orchestrator", self._on_message)

    def _load_prompt(self) -> str:
        p = Path(__file__).parent / "prompts" / "orchestrator.md"
        return p.read_text() if p.exists() else "You are the orchestrator."

    def run(self, challenge: ChallengeData) -> dict:
        self._pending_results.clear()
        description = (
            f"Title: {challenge.title}\nCategory: {challenge.category}\n"
            f"Points: {challenge.points}\nDescription: {challenge.description}\n"
            f"Files: {[str(f) for f in challenge.files]}"
        )

        response = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self._system_prompt,
            messages=[{"role": "user", "content": description}],
        )
        raw = response.content[0].text
        self._token_usage["orchestrator"] = (
            response.usage.input_tokens + response.usage.output_tokens
        )

        try:
            assignments = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"solved": False, "flag_candidate": None, "error": "orchestrator_parse_failure", "raw": raw}

        flag_candidate = None
        solving_agent = None
        escalations = []

        for assignment in assignments:
            role = assignment.get("specialist")
            task = assignment.get("task", "")
            specialist = self.specialists.get(role)
            if not specialist:
                escalations.append({"reason": f"no_specialist_for_role:{role}"})
                continue

            task_msg = Message("orchestrator", role, MessageType.TASK_ASSIGN,
                               {"task": task}, self.bus.run_id)
            self.monitor.on_message(task_msg)

            for attempt in range(1, self.max_attempts + 1):
                self.bus.publish(task_msg)
                specialist.handle_task(task_msg)

                result = next((m for m in self._pending_results if m.sender == role), None)
                if result:
                    self._pending_results = [m for m in self._pending_results if m.sender != role]
                    if result.message_type == MessageType.TASK_RESULT:
                        fc = result.content.get("flag_candidate")
                        if fc:
                            flag_candidate = fc
                            solving_agent = role
                        break
                    elif result.message_type == MessageType.ESCALATION:
                        escalations.append({
                            "role": role,
                            "attempt": attempt,
                            "reason": result.content.get("reason"),
                        })

        return {
            "flag_candidate": flag_candidate,
            "solved": flag_candidate is not None,
            "solving_agent": solving_agent,
            "escalations": escalations,
            "token_usage": self._token_usage,
            "control_state": self.monitor.get_state().value,
        }

    def _on_message(self, message: Message) -> None:
        self.monitor.on_message(message)
        if message.message_type in (MessageType.TASK_RESULT, MessageType.ESCALATION):
            self._pending_results.append(message)
