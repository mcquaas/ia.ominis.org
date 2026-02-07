"""
API Key database model.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY

from app.database import Base


class APIKeyStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"
    expired = "expired"


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    key_prefix = Column(String(20), nullable=False, index=True)
    status = Column(Enum(APIKeyStatus), nullable=False, default=APIKeyStatus.active)
    permissions = Column(Text, nullable=True)  # JSON string of permissions
    ip_whitelist = Column(Text, nullable=True)  # JSON string of allowed IPs

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Usage tracking
    request_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="api_keys")

    def __repr__(self):
        return f"<APIKey {self.key_prefix}... user_id={self.user_id}>"
