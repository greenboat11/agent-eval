import json
from pathlib import Path
from typing import Callable
import structlog

from bus.message import Message

log = structlog.get_logger()


class MessageBus:
    def __init__(self, run_id: str, log_path: Path):
        self.run_id = run_id
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log: list[Message] = []
        self._subscribers: dict[str, list[Callable[[Message], None]]] = {}

    def publish(self, message: Message) -> None:
        self._log.append(message)
        self._write_to_disk(message)
        log.info("bus.publish", sender=message.sender, recipient=message.recipient,
                 type=message.message_type.value, hash=message.content_hash)
        for callback in self._subscribers.get(message.recipient, []):
            callback(message)

    def subscribe(self, recipient: str, callback: Callable[[Message], None]) -> None:
        self._subscribers.setdefault(recipient, []).append(callback)

    def get_log(self) -> list[Message]:
        return list(self._log)

    def _write_to_disk(self, message: Message) -> None:
        with self.log_path.open("a") as f:
            f.write(json.dumps(message.to_dict()) + "\n")
