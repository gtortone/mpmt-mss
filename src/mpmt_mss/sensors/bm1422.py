import smbus2
import time


class BM1422:
    REG_CNTL1 = 0x1B
    REG_CNTL2 = 0x1C
    REG_CNTL3 = 0x1D
    REG_CNTL4_1 = 0x5C
    REG_CNTL4_2 = 0x15D
    REG_DATA = 0x10
    SCALE = 0.0042 # µT/LSB

    def __init__(self, bus, address):
        self.bus = bus
        self.address = address
        try:
            self.i2cbus = smbus2.SMBus(bus)
        except IOError:
            print(f"E: I2C bus {bus} not found")
            sys.exit(-1)
        try:
            self.init_sensor()
        except IOError:
            print(f"E: BM1422 initialization error")

    def init_sensor(self):
        self.i2cbus.write_byte_data(self.address, self.REG_CNTL1, 0x80)
        time.sleep(0.05)

        self.i2cbus.write_byte_data(self.address, self.REG_CNTL4_1, 0x0)
        time.sleep(0.05)

        self.i2cbus.write_byte_data(self.address, self.REG_CNTL4_2, 0x00)
        time.sleep(0.05)

        self.i2cbus.write_byte_data(self.address, self.REG_CNTL2, 0xC)
        time.sleep(0.05)

        self.i2cbus.write_byte_data(self.address, self.REG_CNTL3, 0x40)
        time.sleep(0.05)

    @staticmethod
    def _int16(lo: int, hi: int) -> int:
        v = (hi << 8) | lo
        return v - 65536 if v & 0x8000 else v

    def _read_block(self, addr: int, start_reg: int, n: int) -> bytes:
        data = self.i2cbus.read_i2c_block_data(addr, start_reg, n)
        return bytes(data)

    def readAll(self):
        output = []
        d = self._read_block(self.address, self.REG_DATA, 6)
        output.append(self._int16(d[0], d[1]) * self.SCALE)  # X
        output.append(self._int16(d[2], d[3]) * self.SCALE)  # Y
        output.append(self._int16(d[4], d[5]) * self.SCALE)  # Z
        return output