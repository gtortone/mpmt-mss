#include "rpc_client.hpp"

int main() {

    RPCClient client("http://localhost:8000/rpc");

    for(int i=0; i<1000; i++) {
       float v = client.hv.getVoltage(1);
    }


    //client.sensor.set_threshold(11);

    //printf("humidity: %f\n", hum);
}
