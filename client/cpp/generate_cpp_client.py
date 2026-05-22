#!/usr/bin/env python3

import requests


# -----------------------------
# TYPE MAPPING
# -----------------------------
def cpp_type(t):
    if not t:
        return "int"

    t = t.lower()

    if t == "<class 'int'>":
        return "int"
    if t == "<class 'float'>":
        return "float"
    if t == "<class 'bool'>":
        return "bool"
    if t == "<class 'str'>":
        return "std::string"

    return "void"


# -----------------------------
# SPLIT SERVICE.METHOD
# -----------------------------
def split(full):
    parts = full.split(".")
    if len(parts) == 1:
        return "default", parts[0]
    return parts[0], parts[1]


# -----------------------------
# GENERATOR
# -----------------------------
def generate(schema_url: str):

    schema = requests.get(schema_url).json()

    services = {}

    for full_name, meta in schema.items():
        service, method = split(full_name)

        services.setdefault(service, []).append(
            (full_name, method, meta.get("params", []), meta.get("returns", "int"))
        )

    code = []

    # =========================================================
    # HEADER
    # =========================================================
    code.append("#pragma once")
    code.append("#include <string>")
    code.append("#include <stdexcept>")
    code.append("#include <curl/curl.h>")
    code.append("#include <nlohmann/json.hpp>")
    code.append("")
    code.append("using json = nlohmann::json;")
    code.append("using namespace std;")
    code.append("")

    # =========================================================
    # CURL CALLBACK
    # =========================================================
    code.append("static size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {")
    code.append("    ((std::string*)userp)->append((char*)contents, size * nmemb);")
    code.append("    return size * nmemb;")
    code.append("}")
    code.append("")

    # =========================================================
    # BASE CLIENT
    # =========================================================
    code.append("class RPCClientBase {")
    code.append("public:")
    code.append("    string url;")
    code.append("")
    code.append("    RPCClientBase(string u) : url(u) {}")
    code.append("")
    code.append("    json call(string method, json params) {")
    code.append("        CURL* curl = curl_easy_init();")
    code.append("        string response;")
    code.append("")
    code.append("        json payload = {")
    code.append("            {\"jsonrpc\", \"2.0\"},")
    code.append("            {\"method\", method},")
    code.append("            {\"params\", params},")
    code.append("            {\"id\", 1}")
    code.append("        };")
    code.append("")
    code.append("        string body = payload.dump();")
    code.append("")
    code.append("        if (curl) {")
    code.append("            struct curl_slist* headers = NULL;")
    code.append("            headers = curl_slist_append(headers, \"Content-Type: application/json\");")
    code.append("")
    code.append("            curl_easy_setopt(curl, CURLOPT_URL, url.c_str());")
    code.append("            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());")
    code.append("            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);")
    code.append("            curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);")
    code.append("            curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);")
    code.append("")
    code.append("            CURLcode res = curl_easy_perform(curl);")
    code.append("")
    code.append("            curl_easy_cleanup(curl);")
    code.append("            curl_slist_free_all(headers);")
    code.append("        }")
    code.append("")
    code.append("        json resp;")
    code.append("")
    code.append("        try {")
    code.append("            resp = json::parse(response);")
    code.append("        } catch (...) {")
    code.append("            throw runtime_error(\"Invalid JSON response\");")
    code.append("        }")
    code.append("")
    code.append("        if (resp.contains(\"error\") && !resp[\"error\"].is_null()) {")
    code.append("            throw runtime_error(resp[\"error\"][\"message\"].get<string>());")
    code.append("        }")
    code.append("")
    code.append("        if (!resp.contains(\"result\")) {")
    code.append("            throw runtime_error(\"Missing result field\");")
    code.append("        }")
    code.append("")
    code.append("        return resp[\"result\"];")
    code.append("    }")
    code.append("};")
    code.append("")

    # =========================================================
    # SERVICES
    # =========================================================
    for service, methods in services.items():

        class_name = service.capitalize()

        code.append(f"class {class_name} {{")
        code.append("private:")
        code.append("    RPCClientBase* client;")
        code.append("")
        code.append("public:")
        code.append(f"    {class_name}(RPCClientBase* c) : client(c) {{}}")
        code.append("")

        for full_name, method, params, returns in methods:

            ret_type = cpp_type(returns)

            param_defs = []
            json_fields = []

            for p in params:
                name = p.get("name")
                ptype = cpp_type(p.get("type"))

                param_defs.append(f"{ptype} {name}")
                json_fields.append(f'{{"{name}", {name}}}')

            param_str = ", ".join(param_defs)

            code.append(f"    {ret_type} {method}({param_str}) {{")

            if json_fields:
                code.append(f"        json params = json{{{', '.join(json_fields)}}};")
            else:
                code.append("        json params = json::object();")

            code.append(f"        json res = client->call(\"{full_name}\", params);")

            # SAFE extraction (NO .value())
            if ret_type == "std::string":
                code.append('        if (res.is_string()) return res.get<string>();')
                code.append('        return res.dump();')
            elif ret_type == "bool":
                code.append('        if (res.is_boolean()) return res.get<bool>();')
                code.append('        return false;')
            elif ret_type == "float":
                code.append('        if (res.is_number()) return res.get<float>();')
                code.append('        return 0.0;')
            elif ret_type == "int":
                code.append('        if (res.is_number_integer()) return res.get<int>();')
                code.append('        return 0;')

            code.append("    }")
            code.append("")

        code.append("};")
        code.append("")

    # =========================================================
    # ROOT CLIENT
    # =========================================================
    code.append("class RPCClient {")
    code.append("public:")
    code.append("    RPCClientBase base;")

    for service in services.keys():
        code.append(f"    {service.capitalize()} {service};")

    code.append("")
    code.append("    RPCClient(string url)")
    code.append("        : base(url),")

    init = [f"{s}(&base)" for s in services.keys()]

    code.append("          " + ", ".join(init) + " {}")
    code.append("};")

    return "\n".join(code)


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    out = generate("http://localhost:8000/rpc/schema")

    with open("rpc_client.hpp", "w") as f:
        f.write(out)

    print("Generated rpc_client.hpp")
