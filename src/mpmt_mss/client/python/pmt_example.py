from mssclient import MSSClient
from mpmt_mss.feb.devices import DeviceType

CHANNEL_TEST = 6

client = MSSClient("http://zynq:8000/rpc")

print(client.febmgr.getDefinedChannels())
print(client.febmgr.getStatus(DeviceType.PMT))
print(client.febmgr.getStatus(DeviceType.LED))
client.febmgr.enableChannel(3)
client.febmgr.enableChannels([1, 2, 3])

print(client.febmgr.getPMTStatus(CHANNEL_TEST))
print(client.febmgr.getPMTVoltage(CHANNEL_TEST))
print(client.febmgr.getPMTVoltageSet(CHANNEL_TEST))

try:
    print(client.febmgr.getPMTVoltageSet(8))
except Exception as e:
    print(e.code)

#client.febmgr.setPMTVoltageSet(CHANNEL_TEST, 689)
print(client.febmgr.getPMTVoltageSet(CHANNEL_TEST))
    
print(client.febmgr.getPMTCurrent(CHANNEL_TEST))
print(client.febmgr.getPMTTemperature(CHANNEL_TEST))
print(client.febmgr.getPMTRateRampup(CHANNEL_TEST))
print(client.febmgr.getPMTRateRampdown(CHANNEL_TEST))

#client.febmgr.setPMTRateRampup(CHANNEL_TEST,11)
#client.febmgr.setPMTRateRampdown(CHANNEL_TEST,12)

#client.febmgr.setPMTLimitVoltage(CHANNEL_TEST, 8)
#client.febmgr.setPMTLimitCurrent(CHANNEL_TEST, 1)
#client.febmgr.setPMTLimitTemperature(CHANNEL_TEST, 40)
#client.febmgr.setPMTLimitTriptime(CHANNEL_TEST, 8)

#client.febmgr.setPMTThreshold(CHANNEL_TEST, 1234.56)
print(client.febmgr.getPMTThreshold(CHANNEL_TEST))

print(client.febmgr.getPMTAlarm(CHANNEL_TEST))
print(client.febmgr.getPMTVref(CHANNEL_TEST))

#client.febmgr.powerPMTOn(CHANNEL_TEST)
#client.febmgr.powerPMTOff(CHANNEL_TEST)
#client.febmgr.resetPMT(CHANNEL_TEST)

print(client.febmgr.getPMTInfo(CHANNEL_TEST))

#client.febmgr.setPMTSerialNumber(CHANNEL_TEST, "0123456789AB")
#client.febmgr.setPMTHVSerialNumber(CHANNEL_TEST, "abcdefghi")
#client.febmgr.setPMTFEBSerialNumber(CHANNEL_TEST, "jklmnopq")

print(client.febmgr.readPMTMonRegisters(CHANNEL_TEST))
print(client.febmgr.readPMTCalibRegisters(CHANNEL_TEST))

#client.febmgr.writePMTCalibSlope(CHANNEL_TEST, 2.2)
#client.febmgr.writePMTCalibOffset(CHANNEL_TEST, 3.3)
#client.febmgr.writePMTCalibDiscr(CHANNEL_TEST, 1500)
