import uuid
import time
from dataclasses import dataclass, field

@dataclass
class HistoryItem:
    task_type: str
    file_name: str
    file_path: str
    status: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self):
        return {
            "id": self.id,
            "task_type": self.task_type,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "timestamp": self.timestamp,
            "status": self.status
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            task_type=data.get("task_type", ""),
            file_name=data.get("file_name", ""),
            file_path=data.get("file_path", ""),
            timestamp=data.get("timestamp", time.time()),
            status=data.get("status", "")
        )
