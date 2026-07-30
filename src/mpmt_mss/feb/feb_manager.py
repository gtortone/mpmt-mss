import inspect
import threading
import time
import math
from mpmt_mss.feb.feb_channel import FEBChannel
from mpmt_mss.feb.modbus_manager import ModbusManager, ModbusConfig
from mpmt_mss.feb.devices import DeviceType, DeviceConfig
from mpmt_mss.feb.pmtchannel import PMTChannel
from mpmt_mss.feb.ledchannel import LEDChannel
from mpmt_mss.runcontrol.fpga import FPGA
from mpmt_mss.rpc import rpc_service, rpc_method

FEB_RPC_METHODS: list[str] = [

    # PMT
    "getPMTStatus",
    "getPMTVoltage",
    "getPMTVoltageSet",
    "setPMTVoltageSet",
    "getPMTCurrent",
    "getPMTTemperature",
    "getPMTRateRampup",
    "getPMTRateRampdown",
    "setPMTRateRampup",
    "setPMTRateRampdown",
    "setPMTLimitVoltage",
    "setPMTLimitCurrent",
    "setPMTLimitTemperature",
    "setPMTLimitTriptime",
    "setPMTThreshold",
    "getPMTThreshold",
    "getPMTAlarm",
    "getPMTVref",
    "powerPMTOn",
    "powerPMTOff",
    "resetPMT",
    "getPMTInfo",
    "setPMTSerialNumber",
    "setPMTHVSerialNumber",
    "setPMTFEBSerialNumber",
    "setPMTModbusAddress",
    "readPMTMonRegisters",
    "readPMTCalibRegisters",
    "writePMTCalibSlope",
    "writePMTCalibOffset",
    "writePMTCalibDiscr",

    # LED
    "getLEDStatus",
    "powerLEDOn",    
    "powerLEDOff",    
    "getLEDInfo",
    "setLEDTrigger",
    "getLEDTriggerStatus",
    "setLEDBias",
    "getLEDBiasStatus",
    "setLEDBiasVoltage",
    "getLEDBiasVoltage",
    "readLEDBiasVoltage",
    "getLEDChannels",
    "setLEDChannels",
    "setLEDTriggerSource",
    "getLEDTriggerSource",
    "getLEDCurrent",
    "readLEDMonRegisters",
    "setLEDModbusAddress",
]

@rpc_service()
class FEBManager:
    def __init__(self, cfg: ModbusConfig, config_from_fpga=True):
        self.modbus = ModbusManager(cfg)
        self.fpga = FPGA('/dev/uio0')
        self.all_channels_mask = 0x7FFFF
        self.UINT32_MASK = 0xFFFFFFFF

        # channels are labeled from J1 to J19 (1...19)
        self._channels = [ FEBChannel(i) for i in range(20) ]

        self._rpc_methods: list[str] = []
        self._generate_routed_methods()        

        # register 103 bit (x) is '1' for PMT channel, '0' for LED channel
        if config_from_fpga:
            pmtmask = self.fpga.readRegister(103)
            for ch in range(19):       # 0...18
                if pmtmask & 1<<ch:
                    self.configure(DeviceType.PMT, ch+1, ch+1)
                else:
                    self.configure(DeviceType.LED, ch+1, ch+21)

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self.probe_task)
        self._thread.start()

    def _generate_routed_methods(self) -> None:
        for name in FEB_RPC_METHODS:

            def _make_routed(method_name: str):
                def _routed(self, channel: int, *args, **kwargs):
                    ch = self._channels[channel].device
                    method = getattr(ch, method_name, None)
                    if method is None or not callable(method):
                        raise AttributeError(
                            f"Channel {channel} ({type(ch).__name__}) "
                            f"has no '{method_name}'"
                        )
                    return method(*args, **kwargs)

                _routed.__name__ = method_name

                return rpc_method(_routed)

            setattr(FEBManager, name, _make_routed(name))
            self._rpc_methods.append(name)

    def get_rpc_interface(self) -> dict[str, inspect.Signature | None]:
        result = {}
        for name in self._rpc_methods:
            method = getattr(self, name)
            try:
                result[name] = inspect.signature(method)
            except (ValueError, TypeError):
                result[name] = None
        return result

    def close(self):
        if not self._stop_event.is_set():
            self._stop_event.set()

            if self._thread.is_alive():
                self._thread.join(timeout=5)

    def probe_task(self):
        while True:
            for ch in self.getDefinedChannels():
                self.channel(ch).device.probe()
                if self._stop_event.is_set():
                    return
                time.sleep(0.250) 

    def channel(self, i: int) -> FEBChannel: 
        if i <= 0 or i>len(self._channels)-1:
            raise IndexError(f"Invalid channel index {i}")

        return self._channels[i]

    def clear(self):
        for i in range(20):
            self.channel(i).detach()

    def setup(self, cfg: list[DeviceConfig]):
        self.clear()
        for dev in cfg:
            self.configure(dev.device_type, dev.channel, dev.address)

    # parameters to attach a device on a FEB channel
    # channel: FEB channel number (1...19)
    # address: device Modbus address

    def configure(self, dtype: DeviceType, channel: int, address: int):
        if dtype == DeviceType.PMT:
            device = PMTChannel(self.modbus, channel, address)
        elif dtype == DeviceType.LED:
            device = LEDChannel(self.modbus, channel, address)
        else:
            raise ValueError(f"Invalid channel type: {dtype}")
        self.channel(channel).attach(device)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _validateChannel(channel: int) -> None:
        if isinstance(channel, bool) or not isinstance(channel, int):
            raise TypeError("channel must be an integer")
        if channel < 1 or channel > 19:
            raise IndexError(f"Invalid channel index {channel}; expected 1..19")

    @staticmethod
    def _validateRange(value: int | float, minimum: int, maximum: int, name: str) -> None:
        if isinstance(value, bool):
            raise TypeError(f"{name} must be an number")
        if value < minimum or value > maximum:
            raise ValueError(f"Invalid {name} {value}; expected {minimum}..{maximum}")

    def _channelMask(self, channel: int) -> int:
        self._validateChannel(channel)
        return 1 << (channel - 1)

    def _setRegisterBits(self, register: int, mask: int):
        value = self.fpga.readRegister(register)
        value = (value | mask) & self.UINT32_MASK
        self.fpga.writeRegister(register, value)

    def _clearRegisterBits(self, register: int, mask: int):
        value = self.fpga.readRegister(register)
        value = value & ~mask & self.UINT32_MASK
        self.fpga.writeRegister(register, value)

    def _updateRegisterField(self, register: int, mask: int, fieldValue: int):
        value = self.fpga.readRegister(register)
        value = (value & ~mask) | (fieldValue & mask)
        value &= self.UINT32_MASK
        self.fpga.writeRegister(register, value)


    @rpc_method
    def call(self, channel: int, method: str, params: dict):
        dev = self.channel(channel).device

        mth = getattr(dev, method)

        sig = inspect.signature(mth)
        bound = sig.bind(**params)

        return mth(*bound.args, **bound.kwargs)

    @rpc_method
    def getDefinedChannels(self, dtype: DeviceType = None):
        """Get board channel numbers filtered by DeviceType or all."""
        if dtype is None:
            return [ch.channel for ch in self._channels if ch.is_configured()]
        else:
            return [ch.channel for ch in self._channels 
                if ch.is_configured() and ch.device.DEVICE_TYPE == dtype]

    @rpc_method
    def getOnlineChannels(self, dtype: DeviceType = None):
        """Get online board channel numbers filtered by DeviceType or all."""
        online_channels = []
        for ch in self.getDefinedChannels():
            if self.channel(ch).device.online:
                online_channels.append(self.channel(ch).device.channel) 
        if dtype is None:
            return online_channels
        else:
            return list(set(online_channels) & set(self.getDefinedChannels(dtype)))

    @rpc_method
    def getOfflineChannels(self, dtype: DeviceType = None):
        """Get offline board channel numbers filtered by DeviceType or all."""
        offline_channels = []
        for ch in self.getDefinedChannels():
            if not self.channel(ch).device.online:
                offline_channels.append(self.channel(ch).device.channel) 
        if dtype is None:
            return offline_channels
        else:
            return list(set(offline_channels) & set(self.getDefinedChannels(dtype)))

    def getChannelStatus(self, channel: int) -> dict:
        status = {
            "Acquisition": "enabled" if self.fpga.readRegister(0) & self._channelMask(channel) else "disabled",
            "Trigger": "enabled" if self.fpga.readRegister(58) & self._channelMask(channel) else "disabled",
            "Pulser": "enabled" if self.fpga.readRegister(59) & self._channelMask(channel) else "disabled",
            "Block": "blocked" if self.fpga.readRegister(5) & self._channelMask(channel) else "free",
            "Rate": self.fpga.readRegister(8 + channel - 1),
            "Rate threshold": self.getRateThreshold()[str(channel)],
            "Time to peak": self.getTimeToPeak()[str(channel)]*3.7,
        }
        return status

    @rpc_method
    def getStatus(self, dtype: DeviceType = None):
        """Return overall status for online channels"""
        report = {}
        for ch in self.getOnlineChannels(dtype):
            try:
                if self.channel(ch).device.DEVICE_TYPE == "PMT":
                    PMTreport = self.channel(ch).device.readPMTMonRegisters()
                    report[str(ch)] = {
                        "Type": self.channel(ch).device.DEVICE_TYPE,
                        **self.getChannelStatus(ch),
                        "V": PMTreport["V"],
                        "Vset": PMTreport["Vset"],
                        "I": PMTreport["I"],
                        "T": PMTreport["T"],
                        "Status": PMTreport["status"],
                        "Threshold": PMTreport["threshold"],
                        "Alarm": PMTreport["alarm"]
                    }
                elif self.channel(ch).device.DEVICE_TYPE == "LED":
                    report[str(ch)] = {
                        "type": self.channel(ch).device.DEVICE_TYPE,
                        **self.channel(ch).device.readLEDMonRegisters()
                    }
            except Exception as e:
                raise Exception(f"Error reading channel {ch}: {e}")
        return report

    # ------------------------------------------------------------------
    # Global FEB methods
    # ------------------------------------------------------------------

    @rpc_method
    def powerPMTOnAll(self):
        """Power on all channels."""
        self.modbus.write_coil(address=1, value=True, slave=0, no_response_expected=True)

    @rpc_method
    def powerPMTOffAll(self):
        """Power on all channels."""
        self.modbus.write_coil(address=1, value=False, slave=0, no_response_expected=True)

    @rpc_method
    def setPMTVoltageSetAll(self, value: int):
        """Set threshold of all channels."""
        self._validateRange(value, 0, 1450, "voltage")
        self.modbus.write_register(address=0x26, value=value, slave=0, no_response_expected=True)
        time.sleep(0.05) # critical since there is no response

    @rpc_method
    def setPMTThresholdAll(self, value: float):
        """Set threshold of all channels."""
        self._validateRange(value, 0, 2500, "threshold")
        self.modbus.write_register(address=0x2D, value=math.floor(value), slave=0, no_response_expected=True)
        time.sleep(0.05) # critical since there is no response
        self.modbus.write_register(address=0x35, value=(int(value * 10) % 10), slave=0, no_response_expected=True)

    @rpc_method
    def setPMTModbusAddressForced(self, addr: int):
        """Force modbus addres to all channels turned on"""
        self._validateRange(addr, 1, 19, "channel")
        self.modbus.write_register(address=0x00, value=addr, slave=0, no_response_expected=True)
        time.sleep(0.05) # critical since there is no response

    # ------------------------------------------------------------------
    # Turn on/off channels, register 1
    # ------------------------------------------------------------------
    
    @rpc_method
    def enableChannel(self, channels: list[int]):
        """Turn on channels using a list"""
        for ch in channels:
            self._setRegisterBits(1, self._channelMask(ch))

    @rpc_method
    def disableChannel(self, channels: list[int]):
        """Turn off channels using a list"""
        for ch in channels:
            self._clearRegisterBits(1, self._channelMask(ch))

    @rpc_method
    def enableAllChannels(self):
        """Turn on all channels"""
        self.fpga.writeRegister(1, self.all_channels_mask)

    @rpc_method
    def disableAllChannels(self):
        """Turn off all channels"""
        self.fpga.writeRegister(1, 0)

    @rpc_method
    def enableChannelsByMask(self, mask: int):
        """Turn off multiple channels using a bitmask"""
        for ch in range(19):
            if mask & (1 << ch):
                self.enableChannel([ch+1])

    @rpc_method
    def disableChannelsByMask(self, mask: int):
        """Turn on multiple channels using a bitmask"""
        for ch in range(19):
            if mask & (1 << ch):
                self.disableChannel([ch+1])


    # ------------------------------------------------------------------
    # Acquisition enable, register 0
    # ------------------------------------------------------------------
    @rpc_method
    def enableAcqChannel(self, channels: list[int]):
        """Turn on multiple channels using a list"""
        for ch in channels:
            self._setRegisterBits(0, self._channelMask(ch))

    @rpc_method
    def disableAcqChannel(self, channels: list[int]):
        """Turn off multiple channels using a list"""
        for ch in channels:
            self._clearRegisterBits(0, self._channelMask(ch))

    @rpc_method
    def enableAcqAll(self):
        """Enable data acquisition for all channels."""
        self.fpga.writeRegister(0, self.all_channels_mask)

    @rpc_method
    def disableAcqAll(self):
        """Disable data acquisition for all channels."""
        self.fpga.writeRegister(0, 0)

    # ------------------------------------------------------------------
    # Channel clear, register 5
    # ------------------------------------------------------------------
    @rpc_method
    def clearChannel(self, channels: list[int]):
        """Clear and block a channel."""
        for ch in channels:
            self._setRegisterBits(5, self._channelMask(ch))

    @rpc_method
    def freeChannel(self, channels: list[int]):
        """Free a channel."""
        for ch in channels:
            self._clearRegisterBits(5, self._channelMask(ch))

    @rpc_method
    def clearAll(self):
        """Clear and block every channel."""
        self.fpga.writeRegister(5, self.all_channels_mask)

    @rpc_method
    def freeAll(self):
        """Free every channel."""
        self.fpga.writeRegister(5, 0)

    # ------------------------------------------------------------------
    # Trigger enable, register 58
    # ------------------------------------------------------------------
    @rpc_method
    def enableTriggerChannel(self, channels: list[int]):
        """Enable trigger for a channel."""
        for ch in channels:
            self._setRegisterBits(58, self._channelMask(ch))

    @rpc_method
    def disableTriggerChannel(self, channels: list[int]):
        """Enable trigger for all channels."""
        for ch in channels:
            self._clearRegisterBits(58, self._channelMask(ch))

    @rpc_method
    def enableAllTrigger(self):
        """Disable trigger for a channel."""
        self.fpga.writeRegister(58, self.all_channels_mask)

    @rpc_method
    def disableAllTrigger(self):
        """Disable trigger for all channels."""
        self.fpga.writeRegister(58, 0)

    # ------------------------------------------------------------------
    # Pulser channel enable, register 59
    # ------------------------------------------------------------------
    @rpc_method
    def enablePulserChannel(self, channels: list[int]):
        """Enable pulser for a channel."""
        for ch in channels:
            self._setRegisterBits(59, self._channelMask(ch))

    @rpc_method
    def disablePulserChannel(self, channels: list[int]):
        """Disable pulser for a channel."""
        for ch in channels:
            self._clearRegisterBits(59,self._channelMask(ch))

    @rpc_method
    def enableAllPulser(self):
        """Enable pulser for all channels."""
        self.fpga.writeRegister(59, self.all_channels_mask)

    @rpc_method
    def disableAllPulser(self):
        """Disable pulser for all channels."""
        self.fpga.writeRegister(59, 0)

    # ------------------------------------------------------------------
    # Time to peak, registers 28..37
    # ------------------------------------------------------------------
    @rpc_method
    def setTimeToPeakChannel(self, channel: int, value: int):
        """Set channel time-to-peak."""
        self._validateChannel(channel)
        self._validateRange(value, 0, 0xFFF, "value")
        value = int(value/3.7)

        register = 28 + (channel - 1) // 2
        original = self.fpga.readRegister(register)

        if (channel-1) % 2 == 1:
            mask = 0xFFF
            updated = (original & ~mask) | (value & 0xFFF)
        else:
            mask = 0xFFF << 12
            updated = (original & ~mask) | ((value & 0xFFF) << 12)

        updated &= self.UINT32_MASK
        self.fpga.writeRegister(register, updated)

    @rpc_method
    def setAllTimeToPeak(self, value: int):
        """Set all channels time-to-peak."""
        self._validateRange(value, 0, 0xFFF, "value")
        value = int(value/3.7)
        packed = ((value & 0xFFF) << 12) | (value & 0xFFF)
        registerCount = 20 // 2
        for offset in range(registerCount):
            self.fpga.writeRegister(28 + offset, packed)

    @rpc_method
    def getTimeToPeak(self) -> dict[str, int]:
        """Get all channels time-to-peak."""
        ttps = {}
        for ch in range(19):
            register = 28 + ch // 2
            value = self.fpga.readRegister(register)
            if ch % 2 == 1:
                ttps[str(ch+1)] = value & 0xFFF
            else:
                ttps[str(ch+1)] = (value >> 12) & 0xFFF
        return ttps


    # ------------------------------------------------------------------
    # Per-channel delay, registers 38..42
    # ------------------------------------------------------------------
    @rpc_method
    def setDelayChannel(self, channel: int, value: int):
        """Set one channel delay in 8 ns ticks."""
        self._validateChannel(channel)
        self._validateRange(value, 0, 0xFF, "value")

        value = int(value/8)
        register = 38 + (channel - 1) // 4
        bytePosition = 3 - ((channel - 1) % 4)
        shift = bytePosition * 8
        mask = 0xFF << shift

        original = self.fpga.readRegister(register)
        updated = (original & ~mask) | ((value & 0xFF) << shift)
        updated &= self.UINT32_MASK
        self.fpga.writeRegister(register, updated)

    @rpc_method
    def setAllDelay(self, value: int):
        """Set all channels delay in 8 ns ticks."""
        self._validateRange(value, 0, 0xFF, "value")
        value = int(value/8)
        packed = ((value << 24) | (value << 16) | (value << 8) | value)
        registerCount = 22 // 4
        for offset in range(registerCount):
            self.fpga.writeRegister(38 + offset,packed)

    def getDelay(self) -> dict[str, int]:
        """Get all channels delay in 8 ns ticks."""
        delays = {}
        for ch in range(19):
            register = 38 + ch // 4
            bytePosition = 3 - (ch % 4)
            shift = bytePosition * 8
            packed = self.fpga.readRegister(register)
            value = (packed >> shift) & 0xFF
            delays[str(ch+1)] = value
        return delays

    # ------------------------------------------------------------------
    # Ratemeter thresholds, registers 46..55
    # ------------------------------------------------------------------
    @rpc_method
    def setRateThresholdChannel(self, channel: int, value: int):
        """Set one channel rate threshold in Hz."""
        self._validateChannel(channel)
        self._validateRange(value, 0, 0xFFFF, "value")
        register = 46 + (channel - 1) // 2
        original = self.fpga.readRegister(register)
        if channel % 2 == 1:
            mask = 0x0000FFFF
            updated = (original & ~mask) | value
        else:
            mask = 0xFFFF0000
            updated = (original & ~mask) | (value << 16)
        updated &= self.UINT32_MASK
        self.fpga.writeRegister(register, updated)

    @rpc_method
    def setAllRateThreshold(self, value: int):
        """Set all channels rate threshold in Hz."""
        self._validateRange(value, 0, 0xFFFF, "value")
        value = (value << 16) | value
        for add in range(46, 56):
            self.fpga.writeRegister(add, value)

    @rpc_method
    def getRateThreshold(self) -> dict[str, int]:
        """Get all channels rate threshold in Hz."""
        thresholds = {}
        for ch in range(19):
            register = 46 + ch // 2
            packed = self.fpga.readRegister(register)
            if ch % 2 == 0:
                thresholds[str(ch+1)] = packed & 0xFFFF
            else:
                thresholds[str(ch + 1)] = (packed >> 16) & 0xFFFF
        return thresholds


    # ------------------------------------------------------------------
    # Ratemeters: no RPC methods only for status
    # ------------------------------------------------------------------
    @rpc_method
    def getRateChannel(self, channel: int) -> int:
        """Get channel ratemeter in Hz."""
        self._validateChannel(channel)
        return self.fpga.readRegister(8 + channel - 1)

    @rpc_method
    def getRateAll(self) -> dict[str, int]:
        """Get all channels ratemeters in Hz."""
        rates = {}
        for ch in range(19):
            register = 8 + ch
            rates[str(ch+1)] = self.fpga.readRegister(register)
        return rates
