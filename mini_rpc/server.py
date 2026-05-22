from fastapi import FastAPI
from mini_rpc.types import JSONRPCRequest, JSONRPCResponse
from mini_rpc.core import RPCRuntime, RPCError

def create_app(runtime: RPCRuntime):

    app = FastAPI(title="mPMT RPC Framework")

    @app.post("/rpc")
    async def rpc(req: JSONRPCRequest):

        try:
            result = await runtime.call(req.method, req.params)

            return JSONRPCResponse(
                result=result,
                id=req.id
            )

        except RPCError as e:
            return JSONRPCResponse(
                error={
                    "code": e.code,
                    "message": e.message
                },
                id=req.id
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
