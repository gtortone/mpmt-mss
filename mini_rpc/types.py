from pydantic import BaseModel
from typing import Any, Optional, Dict

class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Any = None
    id: Optional[Any] = None

class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Any = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None
