
from mini_rpc import RPCRuntime, create_app
from lib.sensor import Sensor
from highvoltage.hvmodbus import HVModbus
from highvoltage.hvcomposite import HVComposite
from runcontrol.fpga import FPGA
from sensors.housekeeping import HouseKeeping
from feb import ModbusManager, ModbusConfig
from argparse import Namespace

modbus = ModbusManager(ModbusConfig(mode="rtu", port="/dev/ttyPS1"))

# core objects
hv = HVModbus(modbus)
fpga = FPGA('/dev/uio0')
hk = HouseKeeping()

# composite objects
hvcomp = HVComposite(hv)
#hvcomp = HVComposite(hv, fpga)
#ledcomp = LEDComposite(led, fpga)

runtime = RPCRuntime()

# core layer
runtime.register_service("hv.core", hv)
#runtime.register_service("led.core", led)
runtime.register_service("fpga.core", fpga)
runtime.register_service("hk.core", hk)

# composite layer
runtime.register_service("hv", hvcomp)
#runtime.register_service("led", ledcomp)

app = create_app(runtime)
