from mssclient import MSSClient
from mpmt_mss.feb.devices import DeviceType

CHANNEL_TEST = 7

client = MSSClient("http://zynq:8000/rpc")

print(client.getDefinedChannels())
print(client.getStatus(DeviceType.PMT))
print(client.getStatus(DeviceType.LED))

print(client.getLEDStatus(CHANNEL_TEST))
print(client.getLEDInfo(CHANNEL_TEST))

print(client.getLEDTriggerStatus(CHANNEL_TEST))
print(client.getLEDBiasStatus(CHANNEL_TEST))

print(client.getLEDBiasVoltage(CHANNEL_TEST))
print(client.readLEDBiasVoltage(CHANNEL_TEST))

print(client.getLEDTriggerSource(CHANNEL_TEST))

print(client.getLEDCurrent(CHANNEL_TEST))
print(client.getLEDChannels(CHANNEL_TEST))

print(client.readLEDMonRegisters(CHANNEL_TEST))

client.powerLEDOn(CHANNEL_TEST)
client.powerLEDOff(CHANNEL_TEST)

client.setLEDTrigger(CHANNEL_TEST, 1)
client.setLEDTriggerSource(CHANNEL_TEST, 2)

client.setLEDBias(CHANNEL_TEST, 1)
client.setLEDBiasVoltage(CHANNEL_TEST, 5.5)

client.setLEDChannels(CHANNEL_TEST, channels=[1, 2])
client.setLEDChannels(CHANNEL_TEST, channels=[3], append=True)





