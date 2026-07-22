from mssclient import MSSClient
from mpmt_mss.feb.devices import DeviceType

CHANNEL_TEST = 7

client = MSSClient("http://zynq:8000/rpc")

print(client.febmgr.getDefinedChannels())
print(client.febmgr.getStatus(DeviceType.PMT))
print(client.febmgr.getStatus(DeviceType.LED))

print(client.febmgr.getLEDStatus(CHANNEL_TEST))
print(client.febmgr.getLEDInfo(CHANNEL_TEST))

print(client.febmgr.getLEDTriggerStatus(CHANNEL_TEST))
print(client.febmgr.getLEDBiasStatus(CHANNEL_TEST))

print(client.febmgr.getLEDBiasVoltage(CHANNEL_TEST))
print(client.febmgr.readLEDBiasVoltage(CHANNEL_TEST))

print(client.febmgr.getLEDTriggerSource(CHANNEL_TEST))

print(client.febmgr.getLEDCurrent(CHANNEL_TEST))
print(client.febmgr.getLEDChannels(CHANNEL_TEST))

print(client.febmgr.readLEDMonRegisters(CHANNEL_TEST))

client.febmgr.powerLEDOn(CHANNEL_TEST)
client.febmgr.powerLEDOff(CHANNEL_TEST)

client.febmgr.setLEDTrigger(CHANNEL_TEST, 1)
client.febmgr.setLEDTriggerSource(CHANNEL_TEST, 2)

client.febmgr.setLEDBias(CHANNEL_TEST, 1)
client.febmgr.setLEDBiasVoltage(CHANNEL_TEST, 5.5)

client.febmgr.setLEDChannels(CHANNEL_TEST, channels=[1, 2])
client.febmgr.setLEDChannels(CHANNEL_TEST, channels=[3], append=True)





