#!/usr/bin/env python3

import asyncio
from rpc_client import RPCClient

async def main():
    client = RPCClient("http://localhost:8000/rpc")

    value = await client.sensor.humidity()
    print("humidity:", value)

    await client.sensor.set_threshold(11)

if __name__ == "__main__":
    asyncio.run(main())
