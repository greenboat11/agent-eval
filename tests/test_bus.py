import json
from pathlib import Path
from datetime import datetime
import pytest
from bus.message import Message, MessageType
from bus.message_bus import MessageBus


def test_message_computes_content_hash():
    msg = Message(
        sender="orchestrator",
        recipient="recon",
        message_type=MessageType.TASK_ASSIGN,
        content={"task": "scan localhost"},
        run_id="test-run-001",
    )
    assert msg.content_hash is not None
    assert len(msg.content_hash) == 64  # sha256 hex


def test_message_same_content_same_hash():
    content = {"task": "scan localhost"}
    msg1 = Message("a", "b", MessageType.TASK_ASSIGN, content, "run-1")
    msg2 = Message("a", "b", MessageType.TASK_ASSIGN, content, "run-1")
    assert msg1.content_hash == msg2.content_hash


def test_message_different_content_different_hash():
    msg1 = Message("a", "b", MessageType.TASK_ASSIGN, {"task": "foo"}, "run-1")
    msg2 = Message("a", "b", MessageType.TASK_ASSIGN, {"task": "bar"}, "run-1")
    assert msg1.content_hash != msg2.content_hash


def test_bus_publish_and_retrieve(tmp_path):
    bus = MessageBus(run_id="test-run-001", log_path=tmp_path / "bus.jsonl")
    msg = Message("orchestrator", "recon", MessageType.TASK_ASSIGN, {"task": "scan"}, "test-run-001")
    bus.publish(msg)
    log = bus.get_log()
    assert len(log) == 1
    assert log[0].sender == "orchestrator"


def test_bus_subscriber_called_on_publish(tmp_path):
    bus = MessageBus(run_id="test-run-001", log_path=tmp_path / "bus.jsonl")
    received = []
    bus.subscribe("recon", lambda m: received.append(m))
    msg = Message("orchestrator", "recon", MessageType.TASK_ASSIGN, {"task": "scan"}, "test-run-001")
    bus.publish(msg)
    assert len(received) == 1
    assert received[0].recipient == "recon"


def test_bus_subscriber_not_called_for_wrong_recipient(tmp_path):
    bus = MessageBus(run_id="test-run-001", log_path=tmp_path / "bus.jsonl")
    received = []
    bus.subscribe("web", lambda m: received.append(m))
    msg = Message("orchestrator", "recon", MessageType.TASK_ASSIGN, {"task": "scan"}, "test-run-001")
    bus.publish(msg)
    assert len(received) == 0


def test_bus_log_written_to_disk(tmp_path):
    log_path = tmp_path / "bus.jsonl"
    bus = MessageBus(run_id="test-run-001", log_path=log_path)
    msg = Message("orchestrator", "recon", MessageType.TASK_ASSIGN, {"task": "scan"}, "test-run-001")
    bus.publish(msg)
    assert log_path.exists()
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["sender"] == "orchestrator"
    assert record["content_hash"] == msg.content_hash
