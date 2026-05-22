import inspect
from typing import Any, Callable, Dict


class RPCError(Exception):

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


class RPCRuntime:

    def __init__(self):
        self.services: Dict[str, object] = {}
        self.methods: Dict[str, Callable] = {}

    def register_service(self, name: str, instance: object):
        self.services[name] = instance

        for attr_name in dir(instance):
            method = getattr(instance, attr_name)

            if callable(method) and getattr(method, "_rpc_exposed", False):
                full_name = f"{name}.{attr_name}"
                self.methods[full_name] = method

    def list_methods(self):
        return list(self.methods.keys())

    async def call(self, method: str, params: Any):

        if method not in self.methods:
            raise RPCError(-32601, "Method not found")

        func = self.methods[method]

        try:
            # async function
            if inspect.iscoroutinefunction(func):
                return await self._invoke_async(func, params)

            # sync function
            return self._invoke_sync(func, params)

        except Exception as e:
            raise RPCError(-32603, str(e))

    async def _invoke_async(self, func, params):
        if isinstance(params, dict):
            return await func(**params)
        elif isinstance(params, list):
            return await func(*params)
        else:
            return await func(params)

    def _invoke_sync(self, func, params):
        if isinstance(params, dict):
            return func(**params)
        elif isinstance(params, list):
            return func(*params)
        else:
            return func(params)

    def get_schema(self):
        schema = {}

        for full_name, func in self.methods.items():
            sig = inspect.signature(func)

            params = []
            for name, p in sig.parameters.items():
                params.append({
                    "name": name,
                    "type": str(p.annotation) if p.annotation != inspect._empty else "any"
                })

            schema[full_name] = {
                "params": params,
                "returns": str(sig.return_annotation)
            }

        return schema
