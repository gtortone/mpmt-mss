#include <iostream>

#include <mpmt_mss/mssclient.hpp>

// C++ port of client/python/sensors_example.py

using namespace mpmt_mss;

int main() {
  MSSClient client("http://zynq:8000/rpc");

  std::cout << client.sensors.read().dump() << std::endl;

  return 0;
}
