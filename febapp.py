
from mini_rpc import RPCRuntime, create_app
from runcontrol.fpga import FPGA
from sensors.housekeeping import HouseKeeping
from feb import ModbusManager, ModbusConfig, FEBManager, DeviceChannel, DeviceType, PMTChannel, LEDChannel

febmgr = FEBManager(ModbusConfig(mode="rtu", port="/dev/ttyPS1"))

# core objects
fpga = FPGA('/dev/uio0')

runtime = RPCRuntime()

# core layer
runtime.register_service("fpga.core", fpga)
runtime.register_service("febmgr", febmgr)

app = create_app(runtime)
