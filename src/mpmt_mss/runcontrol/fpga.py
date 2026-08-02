import sys
import mmap
import json
import os
from mpmt_mss.rpc import rpc_service, rpc_method
import subprocess
import signal

@rpc_service()
class FPGA:
    def __init__(self, uiodev):
        try:
            self.fid = open(uiodev, 'r+b', 0)
        except FileNotFoundError:
            self.perror("UIO device not found")
            sys.exit(-1)
        self.regs = mmap.mmap(self.fid.fileno(), 0x10000)
        self.acqprocess = None

    REG_STATUS = 3
    REG_CONTROL = 4
    REG_PULSER_PERIOD = 7

    REG_DEADTIME = 27
    REG_FIFO_WORD_COUNT = 43
    REG_TRIGGER_WINDOW = 44
    REG_TR32_COUNT = 45
    REG_HOUSEKEEPING = 56
    REG_PULSER_SUBHITS = 60
    REG_FW_DATE_AND_FAULTS = 61
    REG_FW_TIME = 62
    REG_FW_SHA = 63
    REG_FW_VERSION = 104

    # REG_CONTROL bit fields
    CTRL_TIMEOUT_MASK = 0x000001FF
    CTRL_FIFO_RESET = 0x00000200
    CTRL_CLOCK_INTERNAL = 0x00000400
    CTRL_CLOCK_CABLE_2 = 0x00000800
    CTRL_TR32_ENABLE = 0x00004000
    CTRL_ADC_CALIBRATION = 0x00010000
    CTRL_SPI_CLOCK_MASK = 0x00180000

    # REG_STATUS bit fields
    STATUS_FIFO_FULL = 0x00000001
    STATUS_PLL_LOCKED = 0x00000002
    STATUS_CABLE_2_FOUND = 0x00000004
    STATUS_CABLE_2_LOST = 0x00000008
    STATUS_CABLE_2_OK = 0x00000010
    STATUS_CABLE_1_FOUND = 0x00000020
    STATUS_CABLE_1_LOST = 0x00000040
    STATUS_CABLE_1_OK = 0x00000080
    STATUS_ACTIVE_CABLE_2 = 0x00000100
    STATUS_ACTIVE_CLOCK_INTERNAL = 0x00000200
    STATUS_TR32_NOT_ALIGNED = 0x00000400
    STATUS_TR32_NOT_RECEIVED = 0x00000800
    STATUS_TR32_EARLY = 0x00001000
    STATUS_TAGT_NOT_RECEIVED = 0x00002000
    STATUS_TAGT_PARITY_ERROR = 0x00004000
    STATUS_CLOCK_UNSTABLE = 0x00008000

    UINT32_MASK = 0xFFFFFFFF
    ALLCHANNELMASK = 0x7FFFF

    @rpc_method
    def readRegister(self, address:int):
        return int.from_bytes(self.regs[address*4:(address*4)+4], byteorder='little')

    @rpc_method
    def writeRegister(self, address:int, value:int):
        self.regs[address*4:(address*4)+4] = int.to_bytes(value, 4, byteorder='little')

    @staticmethod
    def _validateChannel(channel: int) -> None:
        if isinstance(channel, bool) or not isinstance(channel, int):
            raise TypeError("channel must be an integer")
        if channel < 1 or channel > 19:
            raise IndexError(
                f"Invalid channel index {channel}; "
                "expected 1..19"
            )

    @staticmethod
    def _validateRange(value: int, minimum: int, maximum: int, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < minimum or value > maximum:
            raise ValueError(
                f"Invalid {name} {value}; expected {minimum}..{maximum}"
            )

    def _channelMask(self, channel: int) -> int:
        self._validateChannel(channel)
        return 1 << (channel - 1)

    def _setRegisterBits(self, register: int, mask: int):
        value = self.readRegister(register)
        value = (value | mask) & self.UINT32_MASK
        self.writeRegister(register, value)

    def _clearRegisterBits(self, register: int, mask: int):
        value = self.readRegister(register)
        value = value & ~mask & self.UINT32_MASK
        self.writeRegister(register, value)

    def _updateRegisterField(self, register: int, mask: int, fieldValue: int):
        value = self.readRegister(register)
        value = (value & ~mask) | (fieldValue & mask)
        value &= self.UINT32_MASK
        self.writeRegister(register, value)

    # ------------------------------------------------------------------
    # Pulser configuration, registers 7 and 60
    # ------------------------------------------------------------------

    @rpc_method
    def setPulserFrequency(self, frequencyHz: int):
        """
        Configure the internal pulser.

        A frequency of zero disables the pulser. Valid enabled frequencies are
        1..999999 Hz. The FPGA register contains int(1_000_000/frequency).
        """
        self._validateRange(frequencyHz, 0, 999_999, "frequencyHz")

        period = 0 if frequencyHz == 0 else int(1_000_000 / frequencyHz)
        self.writeRegister(self.REG_PULSER_PERIOD, period)

    @rpc_method
    def getPulserFrequency(self) -> dict[str, int]:
        period = self.readRegister(self.REG_PULSER_PERIOD)
        frequency = 0 if period == 0 else int(1_000_000 / period)
        return {
            "frequencyHz": frequency,
            "registerValue": period,
        }

    @rpc_method
    def setPulserSubhits(self, subhits: int):
        self._validateRange(subhits, 0, 2**5-1, "subhits")
        self.writeRegister(self.REG_PULSER_SUBHITS, subhits)

    @rpc_method
    def getPulserSubhits(self) -> int:
        return self.readRegister(self.REG_PULSER_SUBHITS)

    # ------------------------------------------------------------------
    # Clock configuration and status, registers 3 and 4
    # ------------------------------------------------------------------

    @rpc_method
    def setClockSource(self, source: str):
        """Select ``external``/``cable`` or ``internal``/``quartz``."""
        sourceNormalised = source.strip().lower()
        if sourceNormalised in ("external", "cable", "e"):
            self._clearRegisterBits(self.REG_CONTROL, self.CTRL_CLOCK_INTERNAL)
        elif sourceNormalised in ("internal", "quartz", "i"):
            self._setRegisterBits(self.REG_CONTROL,self.CTRL_CLOCK_INTERNAL)
        else:
            raise ValueError("Invalid clock source; use external/cable/E or internal/quartz/I")

    @rpc_method
    def setClockCable(self, cable: int):
        self._validateRange(cable, 1, 2, "cable")
        if cable == 1:
            self._clearRegisterBits(self.REG_CONTROL, self.CTRL_CLOCK_CABLE_2)
        else:
            self._setRegisterBits(self.REG_CONTROL, self.CTRL_CLOCK_CABLE_2)

    @rpc_method
    def getClockStatus(self):
        status = self.readRegister(self.REG_STATUS)
        control = self.readRegister(self.REG_CONTROL)

        return {
            "pllLocked": bool(status & self.STATUS_PLL_LOCKED),
            "clockUnstable": bool(status & self.STATUS_CLOCK_UNSTABLE),
            "activeSource": bool(status & self.STATUS_ACTIVE_CLOCK_INTERNAL),
            "configuredSource": bool(control & self.CTRL_CLOCK_INTERNAL),
            "activeCable": (2 if status & self.STATUS_ACTIVE_CABLE_2 else 1),
            "configuredCable": (2 if control & self.CTRL_CLOCK_CABLE_2 else 1),
            "cable1": {
                "ok": bool(status & self.STATUS_CABLE_1_OK),
                "lost": bool(status & self.STATUS_CABLE_1_LOST),
                "found": bool(status & self.STATUS_CABLE_1_FOUND),
            },
            "cable2": {
                "ok": bool(status & self.STATUS_CABLE_2_OK),
                "lost": bool(status & self.STATUS_CABLE_2_LOST),
                "found": bool(status & self.STATUS_CABLE_2_FOUND),
            },
        }

    @rpc_method
    def getTr32Status(self):
        status = self.readRegister(self.REG_STATUS)
        count = self.readRegister(self.REG_TR32_COUNT)

        return {
            "received": not bool(status & self.STATUS_TR32_NOT_RECEIVED),
            "aligned": not bool(status & self.STATUS_TR32_NOT_ALIGNED),
            "arrivedEarly": bool(status & self.STATUS_TR32_EARLY),
            "count": count,
            "tagTReceived": not bool(
                status & self.STATUS_TAGT_NOT_RECEIVED
            ),
            "tagTParityOk": not bool(
                status & self.STATUS_TAGT_PARITY_ERROR
            ),
        }

    # ------------------------------------------------------------------
    # Tr32 and TagT
    # ------------------------------------------------------------------

    @rpc_method
    def enableTr32Channel(self):
        self._setRegisterBits(self.REG_CONTROL, self.CTRL_TR32_ENABLE)

    @rpc_method
    def disableTr32Channel(self):
        self._clearRegisterBits(self.REG_CONTROL, self.CTRL_TR32_ENABLE)

    # ------------------------------------------------------------------
    # ADC calibration
    # ------------------------------------------------------------------

    @rpc_method
    def requestAdcCalibration(self):
        """
        Pulse the ADC-calibration bit.

        Unlike the original CLI, only bit 16 is cleared afterwards; unrelated
        upper control-register bits are preserved.
        """
        self._setRegisterBits(self.REG_CONTROL, self.CTRL_ADC_CALIBRATION)
        time.sleep(pulseSeconds)
        self._clearRegisterBits(self.REG_CONTROL, self.CTRL_ADC_CALIBRATION)

    # ------------------------------------------------------------------
    # SPI clock
    # ------------------------------------------------------------------

    @rpc_method
    def setSpiClock(self, selection: int) -> str:
        """
        Set SPI clock selection:
        0=10.42 MHz, 1=12.5 MHz, 2=15.625 MHz, 3=20.83 MHz.
        """
        self._validateRange(selection, 0, 3, "selection")
        field = selection << 19

        self._updateRegisterField(self.REG_CONTROL, self.CTRL_SPI_CLOCK_MASK, field)

    @rpc_method
    def getSpiClock(self) -> float:
        control = self.readRegister(self.REG_CONTROL)
        selection = (control & self.CTRL_SPI_CLOCK_MASK) >> 19
        frequenciesMHz = {
            0: 10.42,
            1: 12.5,
            2: 15.625,
            3: 20.83,
        }
        return frequenciesMHz[selection]

    # ------------------------------------------------------------------
    # FIFO reset
    # ------------------------------------------------------------------

    @rpc_method
    def setFifoReset(self, reset: bool) -> str:
        """
        Set AXI FIFO reset state.

        FPGA convention inherited from rc.py:
        - bit 9 = 1: FIFO reset
        - bit 9 = 0: FIFO free
        """
        if reset:
            self._setRegisterBits(self.REG_CONTROL, self.CTRL_FIFO_RESET)
        else:
            self._clearRegisterBits(self.REG_CONTROL, self.CTRL_FIFO_RESET)

        return f"reset {reset}"

    # ------------------------------------------------------------------
    # Data-shifter timeout, REG_CONTROL bits 0..8
    # ------------------------------------------------------------------

    @rpc_method
    def setDataShifterTimeout(self, ticks: int):
        """Set timeout in 8 ns ticks. Accepted logical range: 1..512."""
        self._validateRange(ticks, 1, 512, "ticks")
        self._updateRegisterField(self.REG_CONTROL, self.CTRL_TIMEOUT_MASK, ticks - 1)

    @rpc_method
    def getDataShifterTimeout(self) -> int:
        control = self.readRegister(self.REG_CONTROL)
        encoded = control & self.CTRL_TIMEOUT_MASK
        ticks = encoded + 1
        return ticks * 8

    # ------------------------------------------------------------------
    # External trigger window, register 44
    # ------------------------------------------------------------------

    @rpc_method
    def setTriggerWindow(self, ticks: int):
        """Set trigger-window width in 8 ns ticks; zero disables it."""
        self._validateRange(
            ticks,
            0,
            self.UINT32_MASK,
            "ticks",
        )
        self.writeRegister(self.REG_TRIGGER_WINDOW, ticks)

    @rpc_method
    def getTriggerWindow(self) -> int:
        ticks = self.readRegister(self.REG_TRIGGER_WINDOW)
        return  ticks * 8

    # ------------------------------------------------------------------
    # Monitoring methods
    # ------------------------------------------------------------------

    @rpc_method
    def getDeadtime(self) -> dict[str, float | int]:
        counter = self.readRegister(self.REG_DEADTIME)
        deadtimePercent = (65535 - counter) / 65535 * 100.0
        return {
            "counter": counter,
            "percent": deadtimePercent,
        }

    @rpc_method
    def getHousekeeping(self):
        housekeeping = self.readRegister(self.REG_HOUSEKEEPING)
        status = self.readRegister(self.REG_FW_DATE_AND_FAULTS)

        return {
            "temperatureC": (housekeeping >> 12) / 100.0,
            "relativeHumidityPercent": (housekeeping & 0xFFF) / 100.0,
            "powerOk": not bool(status & 0x2),
            "voltageOk": not bool(status & 0x1),
        }

    @rpc_method
    def getFifoStatus(self):
        words = self.readRegister(self.REG_FIFO_WORD_COUNT)
        status = self.readRegister(self.REG_STATUS)
        return {
            "words": words,
            "full": bool(status & self.STATUS_FIFO_FULL),
        }

    # ------------------------------------------------------------------
    # Firmware/bitstream information
    # ------------------------------------------------------------------

    @rpc_method
    def getFirmwareInfo(self) -> dict[str, str]:
        dateValue = self.readRegister(self.REG_FW_DATE_AND_FAULTS)
        timeValue = self.readRegister(self.REG_FW_TIME)
        shaValue = self.readRegister(self.REG_FW_SHA)
        versionValue = self.readRegister(self.REG_FW_VERSION)

        dateHex = f"{dateValue:08x}"
        timeHex = f"{timeValue:08x}"
        versionHex = f"{versionValue:x}"

        major = versionHex[0]
        minorText = versionHex[1:3]
        patchText = versionHex[3:] or "0"
        minor = int(minorText, 16)
        patch = int(patchText, 16)
        version = f"v{major}.{minor}.{patch}"

        return {
            "version": version,
            "bitstreamDate": f"{dateHex[6:8]}-{dateHex[4:6]}-{dateHex[0:4]}",
            "bitstreamTime": f"{timeHex[0:2]}:{timeHex[2:4]}:{timeHex[4:6]}",
            "commitSha": f"{shaValue:08x}"
        }

    # ------------------------------------------------------------------
    # Default
    # ------------------------------------------------------------------

    @rpc_method
    def setDefaults(self):
        """Set all the registers to their default values"""
        with open(f"{os.path.dirname(os.path.abspath(__file__))}/defaults.json") as f:
            def_reg = json.load(f)
            for add in def_reg.keys():
                self.writeRegister(int(add), def_reg[add])

    # ------------------------------------------------------------------
    # Acquistiion Evproducer
    # ------------------------------------------------------------------

    @rpc_method
    def startAcquisition(self, host: str, port: int = 5555) -> str:
        """Start acquisition"""
        command = ["/opt/mpmt-readout/build/evproducer", "--disable-rc",
                   "--host", host, "--port", str(port)]
        try:
            self.acqprocess = subprocess.Popen(command)
            return f'Process started with PID: {self.acqprocess.pid}'
        except FileNotFoundError:
            return 'Error: executable not found'
        except Exception as e:
            return f"Error during start: {e}"

    @rpc_method
    def stopAcquisition(self) -> str:
        """Stop acquisition"""
        pid = self.acqprocess.pid
        if pid is None:
            return "PID not found"
        try:
            os.kill(pid, signal.SIGTERM)
            return f"Process with PID {pid} terminated."
        except ProcessLookupError:
            return f"No process found with PID {pid}."
        except Exception as e:
            return f"Error during stop: {e}"