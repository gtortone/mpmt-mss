from pydantic import BaseModel
from typing import Any, Optional, Union

class RPCErrorCode:
    INVALID_REQUEST  = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS   = -32602
    INTERNAL_ERROR   = -32603
    PARSE_ERROR      = -32700

class JSONRPCRequest(BaseModel):
    jsonrpc: str
    method: str
    params: Optional[Union[dict, list]] = None
    id: Optional[Union[str, int]] = None

class JSONRPCErrorBody(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None

class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[JSONRPCErrorBody] = None
    id: Optional[Union[str, int]] = None

class JSONRPCException(Exception):
    code: int = RPCErrorCode.INTERNAL_ERROR
    message: str = "Internal error"
 
    def __init__(self, data: Any = None):
        self.data = data
        super().__init__(self.message)
 
class ParseError(JSONRPCException):
    code = RPCErrorCode.PARSE_ERROR
    message = "Parse error"
 
class InvalidRequestError(JSONRPCException):
    code = RPCErrorCode.INVALID_REQUEST
    message = "Invalid Request"
 
class MethodNotFoundError(JSONRPCException):
    code = RPCErrorCode.METHOD_NOT_FOUND
    message = "Method not found"
 
class InvalidParamsError(JSONRPCException):
    code = RPCErrorCode.INVALID_PARAMS
    message = "Invalid params"
 
class InternalError(JSONRPCException):
    code = RPCErrorCode.INTERNAL_ERROR
    message = "Internal error"

