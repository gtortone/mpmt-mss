from mssclient import MSSClient

client = MSSClient("http://zynq:8000/rpc")

reg = 1
value = client.fpga.readRegister(reg)
print(f'reg({reg}), {value}, {hex(value)}')

reg = 0
value = client.fpga.readRegister(reg)
print(f'reg({reg}), {value}, {hex(value)}')

value = client.fpga.writeRegister(0, 5)

value = client.fpga.readRegister(reg)
print(f'reg({reg}), {value}, {hex(value)}')

