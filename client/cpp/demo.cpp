#include "rpc_client.hpp"

int main() {

    RPCClient client("http://localhost:8000/rpc");

    float hum = client.sensor.humidity();
    client.sensor.set_threshold(11);

    printf("humidity: %f\n", hum);
}
