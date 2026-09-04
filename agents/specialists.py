from pathlib import Path

from openai import OpenAI

from bus.message import Message, MessageType
from bus.message_bus import MessageBus


class SpecialistAgent:
    def __init__(self, role: str, model: str, openrouter_key: str,
                 tools: list, bus: MessageBus, max_tokens: int = 2048):
        self.role = role
        self.model = model
        self.bus = bus
        self.max_tokens = max_tokens
        self._client = OpenAI(
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._system_prompt = self._load_prompt(role)

    def _load_prompt(self, role: str) -> str:
        prompt_path = Path(__file__).parent / "prompts" / f"{role}.md"
        if prompt_path.exists():
            return prompt_path.read_text()
        return f"You are the {role} specialist. Complete the assigned task and report findings."

    def handle_task(self, message: Message) -> None:
        task = message.content.get("task", "")
        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": f"Task: {task}"},
                ],
            )
            output = completion.choices[0].message.content or ""
            tokens = {
                "prompt": completion.usage.prompt_tokens,
                "completion": completion.usage.completion_tokens,
            }
        except Exception:
            output = ""
            tokens = {}

        if not output.strip():
            self.bus.publish(Message(
                sender=self.role,
                recipient="orchestrator",
                message_type=MessageType.ESCALATION,
                content={"reason": "empty_response", "task": task},
                run_id=message.run_id,
            ))
            return

        flag_candidate = None
        if "FLAG_CANDIDATE:" in output:
            parts = output.split("FLAG_CANDIDATE:")
            flag_candidate = parts[-1].strip().split()[0]

        result_content = {"output": output, "tokens": tokens, "task": task}
        if flag_candidate:
            result_content["flag_candidate"] = flag_candidate

        self.bus.publish(Message(
            sender=self.role,
            recipient="orchestrator",
            message_type=MessageType.TASK_RESULT,
            content=result_content,
            run_id=message.run_id,
        ))
