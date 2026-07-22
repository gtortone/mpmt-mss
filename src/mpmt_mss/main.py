
from mpmt_mss.rpc import RPCRuntime, create_app
from mpmt_mss.runcontrol.fpga import FPGA
from mpmt_mss.feb import FEBManager, ModbusConfig
from mpmt_mss.sensors import HouseKeeping

febmgr = FEBManager(ModbusConfig(mode="rtu", port="/dev/ttyPS1"))

# core objects
fpga = FPGA('/dev/uio0')
hk = HouseKeeping()

runtime = RPCRuntime()

# core layer
runtime.register_service("fpga", fpga)
runtime.register_service("sensors", hk)
runtime.register_service("febmgr", febmgr)

app = create_app(runtime)

def start():
    import uvicorn
    uvicorn.run("mpmt_mss.main:app", host="0.0.0.0", port=8000)
