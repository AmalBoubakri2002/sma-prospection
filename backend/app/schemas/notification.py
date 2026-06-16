import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    message: str
    is_read: bool
    related_user_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
