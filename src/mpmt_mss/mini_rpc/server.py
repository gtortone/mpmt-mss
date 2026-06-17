import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mpmt_mss.mini_rpc.types import *
from mpmt_mss.mini_rpc.core import RPCRuntime

def make_error_response(code: int, message: str, req_id: Optional[Union[str, int]] = None, data: Any = None) -> dict:
    response = {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
        "id": req_id,
    }
    if data is not None:
        response["error"]["data"] = data
    return response

def make_success_response(result: Any, req_id: Optional[Union[str, int]] = None) -> dict:
    return {"jsonrpc": "2.0", "result": result, "id": req_id}

def create_app(runtime: RPCRuntime):

    app = FastAPI(title="mPMT RPC Framework")

    @app.on_event("shutdown")
    def shutdown():
        for name,instance in runtime.services.items():
            if hasattr(instance, "close") and callable(getattr(instance, "close")):
                instance.close()

    @app.post("/rpc")
    async def rpc(request: Request):

        # body parsing
        try:
            body = await request.body()

            if not body:
                return JSONResponse(
                    status_code=200,
                    content=make_error_response(
                        code=RPCErrorCode.INVALID_REQUEST,
                        message="Invalid request",
                        data="empty body",
                    ),
                )

            raw = json.loads(body)

        except json.JSONDecodeError as exc:
            if exc.pos <= 1:
                return JSONResponse(
                    status_code=200,
                    content=make_error_response(
                        code=RPCErrorCode.INVALID_REQUEST,
                        message="Invalid request",
                        data=f"JSON object expected",
                    ),
                )
            else:
                return JSONResponse(
                    status_code=200,
                    content=make_error_response(
                        code=RPCErrorCode.PARSE_ERROR,
                        message="Parse error",
                        data=f"{exc.pos}: {exc.msg}",
                    ),
                )

        # batch request

        if isinstance(raw, list):
            if not raw:
                return JSONResponse(
                    status_code=200,
                    content=make_error_response(
                        code=RPCErrorCode.INVALID_REQUEST,
                        message="Invalid Request",
                        data="Batch array empty",
                    ),
                )
            results = [await _handle_single(item) for item in raw]
            responses = [r for r in results if r is not None]
            return JSONResponse(status_code=200, content=responses)

        # method dispatching

        result = await _handle_single(raw)
        if result is None:
            # È una notifica: nessuna risposta
            return JSONResponse(status_code=204, content=None)
        return JSONResponse(status_code=200, content=result)


    async def _handle_single(raw: Any) -> Optional[dict]:

        if not isinstance(raw, dict):
            return make_error_response(
                code=RPCErrorCode.INVALID_REQUEST,
                message="Invalid Request",
                data="JSON object expected",
            )
     
        req_id = raw.get("id")
     
        try:
            rpc_req = JSONRPCRequest(**raw)
        except Exception as exc:
            return make_error_response(
                code=RPCErrorCode.INVALID_REQUEST,
                message="Invalid request",
                req_id=req_id,
                data=str(exc),
            )
     
        is_notification = "id" not in raw
     
        try:
            result = await runtime.call(rpc_req.method, rpc_req.params)
     
            if is_notification:
                return None
     
            return make_success_response(result=result, req_id=rpc_req.id)

        except TypeError as exc:
            if is_notification:
                return None
            return make_error_response(
                code=RPCErrorCode.INVALID_PARAMS,
                message="Invalid params",
                req_id=rpc_req.id,
                data=str(exc)
            )
     
        except JSONRPCException as exc:
            if is_notification:
                return None
            return make_error_response(
                code=exc.code,
                message=exc.message,
                req_id=rpc_req.id,
                data=exc.data,
            )

        except Exception as exc:
            if is_notification:
                return None
            return make_error_response(
                code=RPCErrorCode.INTERNAL_ERROR,
                message="Internal error",
                req_id=rpc_req.id,
                data=str(exc),
            )


    @app.get("/rpc/methods")
    def methods():
        return {
            "methods": runtime.list_methods()
        }

    @app.get("/rpc/schema")
    def schema():
        return runtime.get_schema()

    return app
