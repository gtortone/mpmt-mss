#pragma once

#include <cstdint>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

// C++ equivalent of client/python/mssclient.py: a JSON-RPC 2.0 client over
// HTTP for the mPMT Slow Control (mss) service, exposing the same
// febmgr/fpga/sensors namespaces and wire method names. Methods whose JSON
// result shape is not fixed (the server returns plain dicts, no schema)
// return nlohmann::json rather than a typed struct, same choice the Python
// client makes by returning dict/List[dict] as-is.

// Opaque libcurl handle - matches curl.h's own `typedef void CURL;` so this
// header doesn't need to include <curl/curl.h>.
typedef void CURL;

namespace mpmt_mss {

// Error returned by the server according to the JSON-RPC 2.0 standard.
class JsonRpcError : public std::runtime_error {
 public:
  JsonRpcError(int code, std::string message, nlohmann::json data);

  int code;
  std::string message;
  nlohmann::json data;
};

// Transport/HTTP error (connection, timeout, non-2xx status code).
class JsonRpcTransportError : public std::runtime_error {
 public:
  explicit JsonRpcTransportError(const std::string& what);
};

enum class DeviceType { PMT, LED };
std::string to_string(DeviceType type);

enum class TriggerSource { MB, MCU, EXT };
std::string to_string(TriggerSource source);

// Handles only HTTP transport and the JSON-RPC protocol.
//
// Holds one persistent curl easy handle for the lifetime of the client, so
// repeated calls reuse the underlying HTTP keep-alive connection instead of
// paying a fresh TCP handshake on every RPC (same effect as the Python
// client's reused requests.Session()). The handle is not safe for concurrent
// use, so post() serialises callers with a mutex - fine for RPC traffic,
// which is inherently one-request-at-a-time anyway.
class BaseRpcClient {
 public:
  explicit BaseRpcClient(std::string url, double timeout_sec = 10.0);
  virtual ~BaseRpcClient();

  BaseRpcClient(const BaseRpcClient&) = delete;
  BaseRpcClient& operator=(const BaseRpcClient&) = delete;

  nlohmann::json call(const std::string& method, const nlohmann::json& params);
  // Send a JSON-RPC notification (no id, no response expected).
  void notify(const std::string& method, const nlohmann::json& params);

 private:
  nlohmann::json post(const nlohmann::json& payload, bool want_response);

  std::string url_;
  double timeout_;
  long next_id_ = 1;
  CURL* curl_;
  void* headers_;  // curl_slist*, opaque here for the same reason as CURL
  std::mutex mutex_;
};

class FebmgrNamespace {
 public:
  explicit FebmgrNamespace(BaseRpcClient& client) : client_(client) {}

  std::vector<int> getDefinedChannels(std::optional<DeviceType> channel_type = std::nullopt);
  std::vector<int> getOnlineChannels(std::optional<DeviceType> channel_type = std::nullopt);
  std::vector<int> getOfflineChannels(std::optional<DeviceType> channel_type = std::nullopt);
  nlohmann::json getStatus(std::optional<DeviceType> channel_type = std::nullopt);
  void enableChannel(const std::vector<int>& channels);
  void disableChannel(const std::vector<int>& channels);
  void enableAllChannels();
  void disableAllChannels();
  void enableChannelsByMask(uint32_t mask);
  void disableChannelsByMask(uint32_t mask);

  // Acquisition enable, register 0
  void enableAcqChannel(const std::vector<int>& channels);
  void disableAcqChannel(const std::vector<int>& channels);
  void enableAcqAll();
  void disableAcqAll();

  // Channel clear/block, register 5
  void clearChannel(const std::vector<int>& channels);
  void freeChannel(const std::vector<int>& channels);
  void clearAll();
  void freeAll();

  // Trigger enable, register 58
  void enableTriggerChannel(const std::vector<int>& channels);
  void disableTriggerChannel(const std::vector<int>& channels);
  void enableAllTrigger();
  void disableAllTrigger();

  // Pulser channel enable, register 59
  void enablePulserChannel(const std::vector<int>& channels);
  void disablePulserChannel(const std::vector<int>& channels);
  void enableAllPulser();
  void disableAllPulser();

  // Time to peak, registers 28..37
  void setTimeToPeakChannel(int channel, int value);
  void setAllTimeToPeak(int value);
  nlohmann::json getTimeToPeak();

  // Per-channel delay, registers 38..42
  void setDelayChannel(int channel, int value);
  void setAllDelay(int value);

  // Ratemeter thresholds, registers 46..55
  void setRateThresholdChannel(int channel, int value);
  nlohmann::json getRateThreshold();
  void setAllRateThreshold(int value);

  // Ratemeters
  int64_t getRateChannel(int channel);
  nlohmann::json getRateAll();

  // Global FEB methods
  void powerPMTOnAll();
  void powerPMTOffAll();
  void setPMTThresholdAll(double value);
  void setPMTModbusAddressForced(int addr);

  nlohmann::json getPMTStatus(int channel);
  double getPMTVoltage(int channel);
  double getPMTVoltageSet(int channel);
  void setPMTVoltageSet(int channel, int value);
  double getPMTCurrent(int channel);
  double getPMTTemperature(int channel);
  int getPMTRateRampup(int channel);
  int getPMTRateRampdown(int channel);
  void setPMTRateRampup(int channel, int value);
  void setPMTRateRampdown(int channel, int value);
  void setPMTLimitVoltage(int channel, int value);
  void setPMTLimitCurrent(int channel, int value);
  void setPMTLimitTemperature(int channel, int value);
  void setPMTLimitTriptime(int channel, int value);
  void setPMTThreshold(int channel, double value);
  double getPMTThreshold(int channel);
  nlohmann::json getPMTAlarm(int channel);
  double getPMTVref(int channel);
  void powerPMTOn(int channel);
  void powerPMTOff(int channel);
  void resetPMT(int channel);
  nlohmann::json getPMTInfo(int channel);
  void setPMTSerialNumber(int channel, const std::string& sn);
  void setPMTHVSerialNumber(int channel, const std::string& sn);
  void setPMTFEBSerialNumber(int channel, const std::string& sn);
  nlohmann::json readPMTMonRegisters(int channel);
  nlohmann::json readPMTCalibRegisters(int channel);
  void writePMTCalibSlope(int channel, double value);
  void writePMTCalibOffset(int channel, double value);
  void writePMTCalibDiscr(int channel, double value);

  nlohmann::json getLEDStatus(int channel);
  nlohmann::json getLEDInfo(int channel);
  nlohmann::json getLEDTriggerStatus(int channel);
  nlohmann::json getLEDBiasStatus(int channel);
  double getLEDBiasVoltage(int channel);
  double readLEDBiasVoltage(int channel);
  nlohmann::json getLEDTriggerSource(int channel);
  double getLEDCurrent(int channel);
  std::vector<int> getLEDChannels(int channel);
  nlohmann::json readLEDMonRegisters(int channel);
  void powerLEDOn(int channel);
  void powerLEDOff(int channel);
  void setLEDTrigger(int channel, bool value);
  void setLEDTriggerSource(int channel, TriggerSource source);
  void setLEDBias(int channel, bool value);
  void setLEDBiasVoltage(int channel, double value);
  void setLEDChannels(int channel, const std::vector<int>& channels,
                       std::optional<bool> append = std::nullopt);

 private:
  BaseRpcClient& client_;
};

class FpgaNamespace {
 public:
  explicit FpgaNamespace(BaseRpcClient& client) : client_(client) {}

  int64_t readRegister(int64_t address);
  void writeRegister(int64_t address, int64_t value);

  // Pulser configuration, registers 7 and 60
  void setPulserFrequency(int frequencyHz);
  nlohmann::json getPulserFrequency();
  void setPulserSubhits(int subhits);
  int getPulserSubhits();

  // Clock configuration and status, registers 3 and 4
  void setClockSource(const std::string& source);
  void setClockCable(int cable);
  nlohmann::json getClockStatus();
  nlohmann::json getTr32Status();

  // Tr32 and TagT
  void enableTr32Channel();
  void disableTr32Channel();

  // ADC calibration
  void requestAdcCalibration();

  // SPI clock
  void setSpiClock(int selection);
  double getSpiClock();

  // FIFO reset
  std::string setFifoReset(bool reset);

  // Data-shifter timeout, REG_CONTROL bits 0..8
  void setDataShifterTimeout(int ticks);
  int getDataShifterTimeout();

  // External trigger window, register 44
  void setTriggerWindow(int64_t ticks);
  int64_t getTriggerWindow();

  // Monitoring methods
  nlohmann::json getDeadtime();
  nlohmann::json getHousekeeping();
  nlohmann::json getFifoStatus();

  // Firmware/bitstream information
  nlohmann::json getFirmwareInfo();

  // Default
  void setDefaults();

  // Acquisition evproducer
  std::string startAcquisition(const std::string& host, int port = 5555);
  std::string stopAcquisition();

 private:
  BaseRpcClient& client_;
};

class SensorsNamespace {
 public:
  explicit SensorsNamespace(BaseRpcClient& client) : client_(client) {}

  nlohmann::json read();

 private:
  BaseRpcClient& client_;
};

// client.febmgr.getStatus(...)   -> wire method "febmgr.getStatus"
// client.fpga.readRegister(...)  -> wire method "fpga.readRegister"
// client.sensors.read()          -> wire method "sensors.read"
class MSSClient : public BaseRpcClient {
 public:
  explicit MSSClient(const std::string& url, double timeout_sec = 10.0);

  FebmgrNamespace febmgr;
  FpgaNamespace fpga;
  SensorsNamespace sensors;
};

}  // namespace mpmt_mss
