import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MessageType(Enum):
    TASK_ASSIGN = "TASK_ASSIGN"
    TASK_RESULT = "TASK_RESULT"
    ESCALATION = "ESCALATION"
    FLAG_CANDIDATE = "FLAG_CANDIDATE"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"


@dataclass
class Message:
    sender: str
    recipient: str
    message_type: MessageType
    content: dict
    run_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    content_hash: str = field(init=False)

    def __post_init__(self):
        self.content_hash = hashlib.sha256(
            json.dumps(self.content, sort_keys=True).encode()
        ).hexdigest()

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type.value,
            "content": self.content,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "content_hash": self.content_hash,
        }
