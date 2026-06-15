
from mini_rpc import RPCRuntime, create_app
from runcontrol.fpga import FPGA
from sensors.housekeeping import HouseKeeping
from feb import ModbusManager, ModbusConfig, FEBManager, DeviceChannel, DeviceType, PMTChannel, LEDChannel

febmgr = FEBManager(ModbusConfig(mode="rtu", port="/dev/ttyPS1"))

#pmt_channels = [2, 3, 5, 6, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18]
#led_channels = [1, 4, 7, 10, 19]

# test
pmt_channels = range(1,20)
led_channels = []

for ch in pmt_channels:
    febmgr.configure(DeviceType.PMT, channel=ch, address=ch)

for ch in led_channels:
    febmgr.configure(DeviceType.LED, channel=ch, address=20+ch)

# core objects
fpga = FPGA('/dev/uio0')

runtime = RPCRuntime()

# core layer
runtime.register_service("fpga.core", fpga)
runtime.register_service("febmgr", febmgr)

app = create_app(runtime)
