#pragma once
#include <string>
#include <stdexcept>
#include <curl/curl.h>
#include <nlohmann/json.hpp>

using json = nlohmann::json;
using namespace std;

static size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    ((std::string*)userp)->append((char*)contents, size * nmemb);
    return size * nmemb;
}

class RPCClientBase {
public:
    string url;

    RPCClientBase(string u) : url(u) {}

    json call(string method, json params) {
        CURL* curl = curl_easy_init();
        string response;

        json payload = {
            {"jsonrpc", "2.0"},
            {"method", method},
            {"params", params},
            {"id", 1}
        };

        string body = payload.dump();

        if (curl) {
            struct curl_slist* headers = NULL;
            headers = curl_slist_append(headers, "Content-Type: application/json");

            curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
            curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
            curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);

            CURLcode res = curl_easy_perform(curl);

            curl_easy_cleanup(curl);
            curl_slist_free_all(headers);
        }

        json resp;

        try {
            resp = json::parse(response);
        } catch (...) {
            throw runtime_error("Invalid JSON response");
        }

        if (resp.contains("error") && !resp["error"].is_null()) {
            throw runtime_error(resp["error"]["message"].get<string>());
        }

        if (!resp.contains("result")) {
            throw runtime_error("Missing result field");
        }

        return resp["result"];
    }
};

class Sensor {
private:
    RPCClientBase* client;

public:
    Sensor(RPCClientBase* c) : client(c) {}

    float humidity() {
        json params = json::object();
        json res = client->call("sensor.humidity", params);
        if (res.is_number()) return res.get<float>();
        return 0.0;
    }

    float pressure() {
        json params = json::object();
        json res = client->call("sensor.pressure", params);
        if (res.is_number()) return res.get<float>();
        return 0.0;
    }

    void set_dual(int p1, std::string p2) {
        json params = json{{"p1", p1}, {"p2", p2}};
        json res = client->call("sensor.set_dual", params);
    }

    void set_threshold(float value) {
        json params = json{{"value", value}};
        json res = client->call("sensor.set_threshold", params);
    }

    float temperature() {
        json params = json::object();
        json res = client->call("sensor.temperature", params);
        if (res.is_number()) return res.get<float>();
        return 0.0;
    }

};

class RPCClient {
public:
    RPCClientBase base;
    Sensor sensor;

    RPCClient(string url)
        : base(url),
          sensor(&base) {}
};