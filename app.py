
from mini_rpc import RPCRuntime, create_app
from lib.sensor import Sensor
from highvoltage.hvmodbus import HVModbus
from runcontrol.fpga import FPGA
from sensors.housekeeping import HouseKeeping
from argparse import Namespace

runtime = RPCRuntime()

runtime.register_service("hv.core", HVModbus(Namespace(mode='rtu', port='/dev/ttyPS1')))
runtime.register_service("fpga.core", FPGA('/dev/uio0'))
runtime.register_service("hk.core", HouseKeeping())

app = create_app(runtime)
