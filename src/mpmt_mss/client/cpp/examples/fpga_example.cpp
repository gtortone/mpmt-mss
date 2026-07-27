#include <iostream>

#include <mpmt_mss/mssclient.hpp>

// C++ port of client/python/fpga_example.py

using namespace mpmt_mss;

int main() {
  MSSClient client("http://zynq:8000/rpc");

  int64_t reg = 1;
  int64_t value = client.fpga.readRegister(reg);
  std::cout << "reg(" << reg << "), " << value << ", 0x" << std::hex << value << std::dec
            << std::endl;

  reg = 0;
  value = client.fpga.readRegister(reg);
  std::cout << "reg(" << reg << "), " << value << ", 0x" << std::hex << value << std::dec
            << std::endl;

  client.fpga.writeRegister(0, 5);

  value = client.fpga.readRegister(reg);
  std::cout << "reg(" << reg << "), " << value << ", 0x" << std::hex << value << std::dec
            << std::endl;

  return 0;
}
