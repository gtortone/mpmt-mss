#!/usr/bin/env python3

import requests
import keyword


def safe(name: str):
    if keyword.iskeyword(name):
        return name + "_"
    return name


def split(full):
    parts = full.split(".")
    return parts[0], parts[1]


def generate(schema_url: str):

    schema = requests.get(schema_url).json()

    services = {}

    for full_name, meta in schema.items():
        service, method = full_name.rsplit(".", 1)

        service = full_name.rsplit(".", 1)[0]
        parts = []
        for p in service.split("."):
            parts.append(p.capitalize())
        service = "".join(parts)

        if service not in services:
            services[service] = []

        services[service].append((full_name, method, meta["params"]))

    code = []

    # ---------------- CLIENT BASE ----------------
    code.append("import httpx")
    code.append("")
    code.append("class BaseClient:")
    code.append("    def __init__(self, url):")
    code.append("        self.url = url")
    code.append("        self._id = 0")
    code.append("        self.client = httpx.Client(base_url=url)")
    code.append("")
    code.append("    def _call(self, method, params):")
    code.append("       self._id += 1")
    code.append("       resp = self.client.post(self.url, json={")
    code.append('            "jsonrpc": "2.0",')
    code.append('            "method": method,')
    code.append('            "params": params,')
    code.append('            "id": self._id')
    code.append("       })")
    code.append("       data = resp.json()")
    code.append("       if 'error' in data and data['error']:")
    code.append("           raise Exception(data['error'])")
    code.append("       return data.get('result')")
    code.append("")

    # ---------------- SERVICES ----------------
    for service, methods in services.items():

        class_name = service

        code.append(f"class {class_name}:")
        code.append("    def __init__(self, client):")
        code.append("        self._client = client")
        code.append("")

        for full_name, method, params in methods:

            method_name = safe(method)

            args = [p["name"] for p in params]

            args_str = ", ".join(args)

            dict_params = ", ".join([f'"{a}": {a}' for a in args])

            if args:
                code.append(f"    def {method_name}(self, {args_str}):")
                code.append(f"        return self._client._call('{full_name}', {{{dict_params}}})")
            else:
                code.append(f"    def {method_name}(self):")
                code.append(f"        return self._client._call('{full_name}', {{}})")

            code.append("")

    # ---------------- ROOT CLIENT ----------------
    code.append("class RPCClient(BaseClient):")
    code.append("    def __init__(self, url):")
    code.append("        super().__init__(url)")
    code.append("")

    for service in services.keys():
        code.append(f"        self.{service} = {service}(self)")
    code.append("")

    return "\n".join(code)


if __name__ == "__main__":
    out = generate("http://localhost:8000/rpc/schema")

    with open("rpc_client.py", "w") as f:
        f.write(out)

    print("Generated rpc_client.py")
