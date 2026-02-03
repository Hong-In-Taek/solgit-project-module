from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4


class MessageHeader:
    def __init__(
        self,
        message_id: str,
        message_type: str,
        version: str = "v1",
        timestamp: Optional[datetime] = None,
        correlation_id: Optional[str] = None,
        source: Optional[str] = None
    ):
        self.message_id = message_id
        self.message_type = message_type
        self.version = version
        self.timestamp = timestamp or datetime.utcnow()
        self.correlation_id = correlation_id
        self.source = source
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageHeader":
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif timestamp is None:
            timestamp = datetime.utcnow()
        
        return cls(
            message_id=data.get("messageId", ""),
            message_type=data.get("messageType", ""),
            version=data.get("version", "v1"),
            timestamp=timestamp,
            correlation_id=data.get("correlationId"),
            source=data.get("source")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "messageId": self.message_id,
            "messageType": self.message_type,
            "version": self.version,
            "timestamp": self.timestamp.isoformat() + "Z",
            "correlationId": self.correlation_id,
            "source": self.source
        }


class MessageBody:
    def __init__(self, payload: Any):
        self.payload = payload
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageBody":
        return cls(payload=data.get("payload"))
    
    def to_dict(self) -> Dict[str, Any]:
        return {"payload": self.payload}


class Message:
    def __init__(self, header: MessageHeader, body: MessageBody):
        self.header = header
        self.body = body
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            header=MessageHeader.from_dict(data.get("header", {})),
            body=MessageBody.from_dict(data.get("body", {}))
        )
    
    @classmethod
    def new_message(
        cls,
        message_type: str,
        payload: Any,
        source: str,
        correlation_id: Optional[str] = None
    ) -> "Message":
        return cls(
            header=MessageHeader(
                message_id=str(uuid4()),
                message_type=message_type,
                version="v1",
                timestamp=datetime.utcnow(),
                correlation_id=correlation_id,
                source=source
            ),
            body=MessageBody(payload=payload)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "header": self.header.to_dict(),
            "body": self.body.to_dict()
        }
