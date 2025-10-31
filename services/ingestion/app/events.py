from pydantic import BaseModel, HttpUrl
from datetime import datetime
from typing import Optional

EVENT_EXCHANGE = "events"           # topic exchange name
ROUTING_DISCOVERED = "doc.discovered"
ROUTING_FETCHED = "doc.fetched"
ROUTING_READY = "doc.ready"
'''''
class DocumentDiscovered(BaseModel):
    id: str
    title: str
    url: HttpUrl
    discovered_at: datetime

class DocumentFetched(BaseModel):
    id: str
    title: str
    url: HttpUrl
    stored_path: str
    fetched_at: datetime
    size_bytes: Optional[int] = None
    page_count: Optional[int] = None
'''''
class DocumentReady(BaseModel):
    id: str
    title: str
    url: HttpUrl
    discovered_at: datetime
    stored_path: str
    fetched_at: datetime
    ##size_bytes: Optional[int] = None
    page_count: Optional[int] = None
