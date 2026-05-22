from mini_rpc import rpc_service, rpc_method

@rpc_service()
class Sensor:

    @rpc_method
    async def temperature(self) -> float:
        return 22.5

    @rpc_method
    async def humidity(self) -> float:
        return 48.5

    @rpc_method
    async def pressure(self) -> float:
        return 1000

    @rpc_method
    def set_threshold(self, value: float):
        self.threshold = value 

    @rpc_method
    def set_dual(self, p1: int, p2: str):
        self.threshold = 0
