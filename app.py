
from mini_rpc import RPCRuntime, create_app
from lib.sensor import Sensor
from highvoltage.hvmodbus import HVModbus
from highvoltage.hvcomposite import HVComposite
from runcontrol.fpga import FPGA
from sensors.housekeeping import HouseKeeping
from argparse import Namespace

runtime = RPCRuntime()

hv = HVModbus(Namespace(mode='rtu', port='/dev/ttyPS1'))
fpga = FPGA('/dev/uio0')
hk = HouseKeeping()
hvcomp = HVComposite(hv)

# core layer
runtime.register_service("hv.core", hv)
runtime.register_service("fpga.core", fpga)
runtime.register_service("hk.core", hk)

# composite layer
runtime.register_service("hv.composite", hvcomp)

app = create_app(runtime)
