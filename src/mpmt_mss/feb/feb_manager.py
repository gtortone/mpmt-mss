import inspect
import logging
import os
import subprocess
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

log = logging.getLogger(__name__)

FEB_RPC_METHODS: list[str] = [

    # PMT
    # getPMTStatus is not routed generically: FEBManager defines its own
    # version to keep REG_HV_STATUS in sync as soon as a channel's status is read
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
    "getPMTLimitVoltage",
    "setPMTLimitCurrent",
    "getPMTLimitCurrent",
    "setPMTLimitTemperature",
    "getPMTLimitTemperature",
    "setPMTLimitTriptime",
    "getPMTLimitTriptime",
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
    "getLEDErrorRegisters",
    "getLEDBurstConfig",
    "setLEDBurstConfig",
    "setLEDBurstConfigIn",
    "getLEDBurstKey",
    "setLEDBurstKey",
    "startLEDBurst",
    "getLEDBurstStatus",
    "clearLEDBurstStatus",
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
    # PMTChannel.STATUS_MAP values where HV is above 0V (UP, RUP, RDN, TUP, TDN)
    PMT_HV_ON_STATUS_VALUES = {0, 2, 3, 4, 5}

    def __init__(self, cfg: ModbusConfig, config_from_fpga=True):
        self.modbus = ModbusManager(cfg)
        self.fpga = FPGA('/dev/uio0')
        self.all_channels_mask = 0x7FFFF
        self.UINT32_MASK = 0xFFFFFFFF

        # channels are labeled from J1 to J19 (1...19)
        self._channels = [ FEBChannel(i) for i in range(20) ]
        self._led_rank = 0
        self._overcurrentLatch = 0

        self._rpc_methods: list[str] = []
        self._generate_routed_methods()        

        if config_from_fpga:
            self._configureFromFpga()

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
        self.pause_probe()

    def pause_probe(self):
        """Stops the background probe thread. Unlike close(), this is meant
        to be resumed later with resume_probe() - used by flashFirmware() to
        keep probe_task from fighting stm32flash for the shared UART.
        """
        if not self._stop_event.is_set():
            self._stop_event.set()

            if self._thread.is_alive():
                self._thread.join(timeout=5)

    def resume_probe(self):
        """Restarts the background probe thread after pause_probe(). A
        Thread object can't be restarted once stopped, so this creates a
        fresh one.
        """
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.probe_task)
        self._thread.start()

    def probe_task(self):
        while True:
            for ch in self.getDefinedChannels():
                try:
                    self.channel(ch).device.probe()
                except Exception:
                    # unhandled here silently kills this thread for good - see clear()
                    log.exception("probe_task: channel %s probe failed, skipping", ch)
                if self._stop_event.is_set():
                    return
                time.sleep(0.250)

    def channel(self, i: int) -> FEBChannel: 
        if i <= 0 or i>len(self._channels)-1:
            raise IndexError(f"Invalid channel index {i}")

        return self._channels[i]

    def clear(self):
        # no lock against probe_task - it can catch a channel mid-detach
        for i in range(1, 20):
            self.channel(i).detach()
        self._led_rank = 0

    # register 103 bit (x) is '1' for PMT channel, '0' for LED channel
    def _configureFromFpga(self):
        pmtmask = self.fpga.readRegister(103)
        for ch in range(19):       # 0...18
            if pmtmask & 1<<ch:
                self.configure(DeviceType.PMT, ch+1, ch+1)
            else:
                self.configure(DeviceType.LED, ch+1, ch+21)

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
            device = LEDChannel(self.modbus, channel, address, self._led_rank)
            self._led_rank += 1
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

    def _updateHVStatusBit(self, channel: int, statusValue: int):
        if statusValue in self.PMT_HV_ON_STATUS_VALUES:
            self._setRegisterBits(self.fpga.REG_HV_STATUS, self._channelMask(channel))
        else:
            self._clearRegisterBits(self.fpga.REG_HV_STATUS, self._channelMask(channel))


    @rpc_method
    def call(self, channel: int, method: str, params: dict):
        dev = self.channel(channel).device

        mth = getattr(dev, method)

        sig = inspect.signature(mth)
        bound = sig.bind(**params)

        return mth(*bound.args, **bound.kwargs)

    @rpc_method
    def getPMTStatus(self, channel: int) -> dict:
        status = self.channel(channel).device.getPMTStatus()
        self._updateHVStatusBit(channel, status["value"])
        return status

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
            "Time to peak": self.getTimeToPeak()[str(channel)],
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
                    self._updateHVStatusBit(ch, PMTreport["status"]["value"])
                elif self.channel(ch).device.DEVICE_TYPE == "LED":
                    report[str(ch)] = {
                        "type": self.channel(ch).device.DEVICE_TYPE,
                        **self.channel(ch).device.readLEDMonRegisters()
                    }
            except Exception as e:
                raise Exception(f"Error reading channel {ch}: {e}")
        return report

    # ------------------------------------------------------------------
    # Overcurrent latch, register 2 (main power rail, not HV)
    # bits clear on hardware read, so we OR them into a software latch
    # ------------------------------------------------------------------
    @rpc_method
    def getOvercurrentChannels(self) -> list[int]:
        """Channels forcibly powered off by an overcurrent on their main power rail."""
        self._overcurrentLatch |= self.fpga.readRegister(2)
        return [ch for ch in range(1, 20) if self._overcurrentLatch & self._channelMask(ch)]

    @rpc_method
    def clearOvercurrentLatch(self):
        """Acknowledge and clear the software-side overcurrent latch."""
        self._overcurrentLatch = 0

    # ------------------------------------------------------------------
    # Modbus address alignment: power one board at a time and force it onto
    # the address dictated by its FPGA wiring (register 103), so this
    # doesn't have to be scripted externally.
    # ------------------------------------------------------------------
    def _alignChannel(self, channel: int, dtype: DeviceType, target: int,
                       timeout: float, poll_interval: float):
        """Power just this channel, retry the forced-address broadcast until
        a readback at the target address succeeds or timeout elapses."""
        self.enableChannel([channel])
        deadline = time.time() + timeout
        last_err = None
        try:
            while time.time() < deadline:
                try:
                    if dtype == DeviceType.PMT:
                        self.setPMTModbusAddressForced(target)
                        self.modbus.read_holding_registers(address=6, count=1, slave=target)
                    else:
                        self.setLEDModbusAddressForced(target)
                        self.modbus.read_input_registers(address=30001, count=1, slave=target)
                    return True, None
                except Exception as e:
                    last_err = e
                    time.sleep(poll_interval)
            return False, str(last_err)
        finally:
            self.disableChannel([channel])

    @rpc_method
    def alignModbusAddresses(self, channels: list[int] = None, timeout: float = 5.0,
                              poll_interval: float = 0.25, reconfigure: bool = True) -> dict:
        """Assign Modbus addresses without external scripting: for each
        channel, power only that board, broadcast its target address (PMT:
        channel, LED: channel+20, from the register 103 wiring), and confirm
        it by reading back at that address before moving on to the next
        channel - retrying on the broadcast+readback until timeout if the
        board isn't up yet.

        All other channels are powered off for the duration (their online
        status will drop and recover on its own via probe_task). Channels
        that fail are reported in "failed" and left untouched; if at least
        one channel succeeded, "reconfigure" (default True) re-attaches the
        whole board from register 103 (not just the channels just aligned),
        so it's usable immediately without waiting for a restart.
        """
        pmtmask = self.fpga.readRegister(103)
        if channels is None:
            channels = list(range(1, 20))

        self.disableAllChannels()
        ok, failed = [], {}

        log.info("alignModbusAddresses: starting on %d channel(s): %s", len(channels), channels)
        for ch in channels:
            dtype = DeviceType.PMT if (pmtmask & self._channelMask(ch)) else DeviceType.LED
            target = ch if dtype == DeviceType.PMT else ch + 20
            log.info("alignModbusAddresses: channel %s (%s) -> address %s...", ch, dtype, target)
            success, err = self._alignChannel(ch, dtype, target, timeout, poll_interval)
            if success:
                log.info("alignModbusAddresses: channel %s -> OK (address %s)", ch, target)
                ok.append({"channel": ch, "type": dtype, "address": target})
            else:
                log.warning("alignModbusAddresses: channel %s -> FAILED: %s", ch, err)
                failed[str(ch)] = err
        log.info(
            "alignModbusAddresses: done - %d ok, %d failed%s",
            len(ok), len(failed), f": {list(failed.keys())}" if failed else "",
        )

        if reconfigure and ok:
            self.reconfigureFromFpga()

        return {"ok": ok, "failed": failed}

    @rpc_method
    def reconfigureFromFpga(self):
        """Re-attaches every channel (1-19) from register 103's PMT/LED
        wiring mask - pure software, no Modbus/hardware I/O. Separate from
        alignModbusAddresses so it can be called once after aligning
        channels individually, since _led_rank must be recomputed for the
        whole board.
        """
        self.clear()
        self._configureFromFpga()

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

    @rpc_method
    def setLEDModbusAddressForced(self, addr: int):
        """Force modbus address to all LED channels turned on"""
        self._validateRange(addr, 21, 39, "address")
        self.modbus.write_register(address=40006, value=addr, slave=0, no_response_expected=True)
        time.sleep(0.05) # critical since there is no response

    # ------------------------------------------------------------------
    # Turn on/off channels, register 1
    # ------------------------------------------------------------------
    
    @rpc_method
    def enableChannel(self, channels: list[int]):
        """Turn on channels using a list"""
        for ch in channels:
            self._setRegisterBits(1, self._channelMask(ch))

    #for safety we also disable the acquisition to prevent boot mode at startup.
    @rpc_method
    def disableChannel(self, channels: list[int]):
        """Turn off channels using a list"""
        for ch in channels:
            self._clearRegisterBits(1, self._channelMask(ch))
            self._clearRegisterBits(0, self._channelMask(ch))

    @rpc_method
    def enableAllChannels(self):
        """Turn on all channels"""
        self.fpga.writeRegister(1, self.all_channels_mask)

    @rpc_method
    def disableAllChannels(self):
        """Turn off all channels"""
        self.fpga.writeRegister(1, 0)
        self.fpga.writeRegister(0, 0)

    @rpc_method
    def enableChannelsByMask(self, mask: int):
        """Turn on multiple channels using a bitmask"""
        for ch in range(19):
            if mask & (1 << ch):
                self.enableChannel([ch+1])

    @rpc_method
    def disableChannelsByMask(self, mask: int):
        """Turn off multiple channels using a bitmask"""
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
        """Get all channels time-to-peak, in setTimeToPeakChannel()'s units.

        setTimeToPeakChannel divides by 3.7 to fit its 0..0xFFF input into
        the register's 12 bit field; this used to return the raw encoded
        value with no inverse conversion, so set(42) read back as 11.
        """
        ttps = {}
        for ch in range(19):
            register = 28 + ch // 2
            value = self.fpga.readRegister(register)
            if ch % 2 == 1:
                encoded = value & 0xFFF
            else:
                encoded = (value >> 12) & 0xFFF
            ttps[str(ch+1)] = round(encoded * 3.7)
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

    # ------------------------------------------------------------------
    # Run preparation
    # ------------------------------------------------------------------
    def _waitOnline(self, channels: list[int], timeout: float) -> list[int]:
        deadline = time.time() + timeout
        while True:
            online = [ch for ch in channels if self.channel(ch).device.online]
            if len(online) == len(channels) or time.time() >= deadline:
                return online
            time.sleep(0.25)

    @rpc_method
    def prepareForRun(self, timeout: float = 10.0, channels: list[int] = None) -> dict:
        """Enable the given PMT channels (all defined PMT channels if none
        given), wait for them to probe online, then enable acquisition and
        trigger on the ones that made it."""
        if channels is None:
            channels = self.getDefinedChannels(DeviceType.PMT)

        self.fpga.setFifoReset(True)
        self.enableChannel(channels)

        online = self._waitOnline(channels, timeout)
        offline = [ch for ch in channels if ch not in online]

        self.enableAcqChannel(online)
        self.enableTriggerChannel(online)
        self.fpga.setPulserFrequency(1)
        self.enablePulserChannel(online)

        for ch in online:
            self.powerPMTOn(ch)

        self.fpga.setFifoReset(False)

        return {"enabled": channels, "online": online, "offline": offline, "hvStarted": online}

    @rpc_method
    def getHVReadyChannels(self, channels: list[int] = None) -> dict:
        """Split PMT channels by HV ramp completion (status UP vs still ramping/down/tripped)."""
        if channels is None:
            channels = self.getOnlineChannels(DeviceType.PMT)

        ready, notReady = [], []
        for ch in channels:
            status = self.channel(ch).device.getPMTStatus()["value"]
            (ready if status == 0 else notReady).append(ch)

        return {"ready": ready, "notReady": notReady}

    # ------------------------------------------------------------------
    # Firmware update
    #
    # The STM32L0 behind each channel is flashed over the same UART used
    # for Modbus - there's no separate programming interface. So this has
    # to: pause probe_task (it also uses that UART in the background),
    # release the modbus connection, isolate+power only the target channel
    # (same register 0/1 sequence mpmt-board-cli's reprogram_FEBs.py used),
    # run stm32flash, then undo all of that - regardless of whether
    # stm32flash succeeded. If the modbus connection isn't reopened and
    # probe_task isn't resumed here, mss loses its hardware link entirely
    # until the service is restarted, so the cleanup runs in `finally`.
    # ------------------------------------------------------------------

    @rpc_method
    def flashFirmware(self, channel: int, firmware_path: str) -> str:
        """Flash firmware onto one channel's STM32L0 via stm32flash.

        Only one channel at a time: all 19 channels share the same UART, so
        there's no way to flash two channels concurrently even in
        principle. Every other channel is powered off for the duration.
        """
        self._validateChannel(channel)
        if not os.path.isfile(firmware_path):
            raise FileNotFoundError(f"firmware file not found: {firmware_path}")

        serial_port = self.modbus.param.port

        self.pause_probe()
        try:
            self.modbus.close()

            self.disableAcqAll()
            self.disableAllChannels()
            time.sleep(2)
            self.enableAcqChannel([channel])
            time.sleep(1)
            self.enableChannel([channel])
            time.sleep(3)

            try:
                result = subprocess.run(
                    ["stm32flash", "-b", "115200", "-w", firmware_path,
                     "-e", "255", "-v", serial_port],
                    capture_output=True, text=True, timeout=120,
                )
                output = result.stdout + result.stderr
                if result.returncode != 0:
                    return f"FAILED (exit {result.returncode}):\n{output}"
                return f"OK:\n{output}"
            except subprocess.TimeoutExpired as e:
                return f"FAILED: stm32flash timed out after 120s:\n{(e.stdout or '') + (e.stderr or '')}"
            except FileNotFoundError:
                return "FAILED: stm32flash executable not found on PATH"
        finally:
            self.disableAcqAll()
            self.disableAllChannels()
            self.modbus.connect()
            self.resume_probe()
