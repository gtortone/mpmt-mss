#include <iostream>

#include <mpmt_mss/mssclient.hpp>

// C++ port of client/python/pmt_example.py

using namespace mpmt_mss;

constexpr int kChannelTest = 6;

int main() {
  MSSClient client("http://zynq:8000/rpc");

  auto print_channels = [](const std::vector<int>& channels) {
    std::cout << "[";
    for (size_t i = 0; i < channels.size(); i++) std::cout << (i ? ", " : "") << channels[i];
    std::cout << "]" << std::endl;
  };

  print_channels(client.febmgr.getDefinedChannels());
  std::cout << client.febmgr.getStatus(DeviceType::PMT).dump() << std::endl;
  std::cout << client.febmgr.getStatus(DeviceType::LED).dump() << std::endl;
  client.febmgr.enableChannel({1, 6});

  std::cout << client.febmgr.getPMTStatus(kChannelTest).dump() << std::endl;
  std::cout << client.febmgr.getPMTVoltage(kChannelTest) << std::endl;
  std::cout << client.febmgr.getPMTVoltageSet(kChannelTest) << std::endl;

  try {
    std::cout << client.febmgr.getPMTVoltageSet(8) << std::endl;
  } catch (const JsonRpcError& e) {
    std::cout << e.code << std::endl;
  }

  // client.febmgr.setPMTVoltageSet(kChannelTest, 689);
  std::cout << client.febmgr.getPMTVoltageSet(kChannelTest) << std::endl;

  std::cout << client.febmgr.getPMTCurrent(kChannelTest) << std::endl;
  std::cout << client.febmgr.getPMTTemperature(kChannelTest) << std::endl;
  std::cout << client.febmgr.getPMTRateRampup(kChannelTest) << std::endl;
  std::cout << client.febmgr.getPMTRateRampdown(kChannelTest) << std::endl;

  // client.febmgr.setPMTRateRampup(kChannelTest, 11);
  // client.febmgr.setPMTRateRampdown(kChannelTest, 12);

  // client.febmgr.setPMTLimitVoltage(kChannelTest, 8);
  // client.febmgr.setPMTLimitCurrent(kChannelTest, 1);
  // client.febmgr.setPMTLimitTemperature(kChannelTest, 40);
  // client.febmgr.setPMTLimitTriptime(kChannelTest, 8);

  // client.febmgr.setPMTThreshold(kChannelTest, 1234.56);
  std::cout << client.febmgr.getPMTThreshold(kChannelTest) << std::endl;

  std::cout << client.febmgr.getPMTAlarm(kChannelTest).dump() << std::endl;
  std::cout << client.febmgr.getPMTVref(kChannelTest) << std::endl;

  // client.febmgr.powerPMTOn(kChannelTest);
  // client.febmgr.powerPMTOff(kChannelTest);
  // client.febmgr.resetPMT(kChannelTest);

  std::cout << client.febmgr.getPMTInfo(kChannelTest).dump() << std::endl;

  // client.febmgr.setPMTSerialNumber(kChannelTest, "0123456789AB");
  // client.febmgr.setPMTHVSerialNumber(kChannelTest, "abcdefghi");
  // client.febmgr.setPMTFEBSerialNumber(kChannelTest, "jklmnopq");

  std::cout << client.febmgr.readPMTMonRegisters(kChannelTest).dump() << std::endl;
  std::cout << client.febmgr.readPMTCalibRegisters(kChannelTest).dump() << std::endl;

  // client.febmgr.writePMTCalibSlope(kChannelTest, 2.2);
  // client.febmgr.writePMTCalibOffset(kChannelTest, 3.3);
  // client.febmgr.writePMTCalibDiscr(kChannelTest, 1500);

  return 0;
}
