from pydantic import BaseModel, HttpUrl
from datetime import datetime
from typing import Optional

class Document(BaseModel):
    id: str
    title: str
    url: HttpUrl
    discovered_at: datetime
    fetched_at: Optional[datetime] = None
    stored_path: Optional[str] = None
    size_bytes: Optional[int] = None
    page_count: Optional[int] = None
