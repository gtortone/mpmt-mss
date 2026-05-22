
from mini_rpc import RPCRuntime, create_app
from lib.sensor import Sensor

runtime = RPCRuntime()

runtime.register_service("sensor", Sensor())

app = create_app(runtime)
