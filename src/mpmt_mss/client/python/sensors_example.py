from mssclient import MSSClient

client = MSSClient("http://zynq:8000/rpc")

print(client.sensors.read())

