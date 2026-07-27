#include <iostream>

#include <mpmt_mss/mssclient.hpp>

// C++ port of client/python/led_example.py

using namespace mpmt_mss;

constexpr int kChannelTest = 7;

static void print_channels(const std::vector<int>& channels) {
  std::cout << "[";
  for (size_t i = 0; i < channels.size(); i++) std::cout << (i ? ", " : "") << channels[i];
  std::cout << "]" << std::endl;
}

int main() {
  MSSClient client("http://zynq:8000/rpc");

  print_channels(client.febmgr.getDefinedChannels());
  std::cout << client.febmgr.getStatus(DeviceType::PMT).dump() << std::endl;
  std::cout << client.febmgr.getStatus(DeviceType::LED).dump() << std::endl;

  std::cout << client.febmgr.getLEDStatus(kChannelTest).dump() << std::endl;
  std::cout << client.febmgr.getLEDInfo(kChannelTest).dump() << std::endl;

  std::cout << client.febmgr.getLEDTriggerStatus(kChannelTest).dump() << std::endl;
  std::cout << client.febmgr.getLEDBiasStatus(kChannelTest).dump() << std::endl;

  std::cout << client.febmgr.getLEDBiasVoltage(kChannelTest) << std::endl;
  std::cout << client.febmgr.readLEDBiasVoltage(kChannelTest) << std::endl;

  std::cout << client.febmgr.getLEDTriggerSource(kChannelTest).dump() << std::endl;

  std::cout << client.febmgr.getLEDCurrent(kChannelTest) << std::endl;
  print_channels(client.febmgr.getLEDChannels(kChannelTest));

  std::cout << client.febmgr.readLEDMonRegisters(kChannelTest).dump() << std::endl;

  client.febmgr.powerLEDOn(kChannelTest);
  client.febmgr.powerLEDOff(kChannelTest);

  client.febmgr.setLEDTrigger(kChannelTest, true);
  client.febmgr.setLEDTriggerSource(kChannelTest, TriggerSource::EXT);

  client.febmgr.setLEDBias(kChannelTest, true);
  client.febmgr.setLEDBiasVoltage(kChannelTest, 5.5);

  client.febmgr.setLEDChannels(kChannelTest, {1, 2});
  client.febmgr.setLEDChannels(kChannelTest, {3}, /*append=*/true);

  return 0;
}
