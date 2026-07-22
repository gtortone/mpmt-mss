from mssclient import MSSClient
from mpmt_mss.feb.devices import DeviceType

CHANNEL_TEST = 6

client = MSSClient("http://zynq:8000/rpc")

print(client.getDefinedChannels())
print(client.getStatus(DeviceType.PMT))
print(client.getStatus(DeviceType.LED))
client.enableChannel(3)
client.enableChannels([1, 2, 3])

print(client.getPMTStatus(CHANNEL_TEST))
print(client.getPMTVoltage(CHANNEL_TEST))
print(client.getPMTVoltageSet(CHANNEL_TEST))

try:
    print(client.getPMTVoltageSet(8))
except Exception as e:
    print(e.code)

#client.setPMTVoltageSet(CHANNEL_TEST, 689)
print(client.getPMTVoltageSet(CHANNEL_TEST))
    
print(client.getPMTCurrent(CHANNEL_TEST))
print(client.getPMTTemperature(CHANNEL_TEST))
print(client.getPMTRateRampup(CHANNEL_TEST))
print(client.getPMTRateRampdown(CHANNEL_TEST))

#client.setPMTRateRampup(CHANNEL_TEST,11)
#client.setPMTRateRampdown(CHANNEL_TEST,12)

#client.setPMTLimitVoltage(CHANNEL_TEST, 8)
#client.setPMTLimitCurrent(CHANNEL_TEST, 1)
#client.setPMTLimitTemperature(CHANNEL_TEST, 40)
#client.setPMTLimitTriptime(CHANNEL_TEST, 8)

#client.setPMTThreshold(CHANNEL_TEST, 1234.56)
print(client.getPMTThreshold(CHANNEL_TEST))

print(client.getPMTAlarm(CHANNEL_TEST))
print(client.getPMTVref(CHANNEL_TEST))

#client.powerPMTOn(CHANNEL_TEST)
#client.powerPMTOff(CHANNEL_TEST)
#client.resetPMT(CHANNEL_TEST)

print(client.getPMTInfo(CHANNEL_TEST))

#client.setPMTSerialNumber(CHANNEL_TEST, "0123456789AB")
#client.setPMTHVSerialNumber(CHANNEL_TEST, "abcdefghi")
#client.setPMTFEBSerialNumber(CHANNEL_TEST, "jklmnopq")

print(client.readPMTMonRegisters(CHANNEL_TEST))
print(client.readPMTCalibRegisters(CHANNEL_TEST))

#client.writePMTCalibSlope(CHANNEL_TEST, 2.2)
#client.writePMTCalibOffset(CHANNEL_TEST, 3.3)
#client.writePMTCalibDiscr(CHANNEL_TEST, 1500)
