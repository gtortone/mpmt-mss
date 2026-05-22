import httpx

class BaseClient:
    def __init__(self, url):
        self.url = url
        self._id = 0

    async def _call(self, method, params):
        self._id += 1
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.url, json={
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": self._id
            })
            data = resp.json()
            if 'error' in data and data['error']:
                raise Exception(data['error'])
            return data.get('result')

class Sensor:
    def __init__(self, client):
        self._client = client

    async def humidity(self):
        return await self._client._call('sensor.humidity', {})

    async def pressure(self):
        return await self._client._call('sensor.pressure', {})

    async def set_dual(self, p1, p2):
        return await self._client._call('sensor.set_dual', {"p1": p1, "p2": p2})

    async def set_threshold(self, value):
        return await self._client._call('sensor.set_threshold', {"value": value})

    async def temperature(self):
        return await self._client._call('sensor.temperature', {})

class RPCClient(BaseClient):
    def __init__(self, url):
        super().__init__(url)

        self.sensor = Sensor(self)
