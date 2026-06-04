#!/usr/bin/env python3

from rpc_client import RPCClient

client = RPCClient("http://localhost:8000/rpc")

#value = client.Sensor.humidity()
#print("humidity:", value)

for i in range(1000):
   value = client.HvCore.getVoltage(1)
   print("CH1 getVoltage:" , value)
   value = client.HvCore.getCurrent(1)
   print("CH1 getCurrent:" , value)
   value = client.HvCore.getTemperature(1)
   print("CH1 getTemperature:" , value)

