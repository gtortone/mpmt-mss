#include <mpmt_mss/mssclient.hpp>

#include <curl/curl.h>

using nlohmann::json;

namespace mpmt_mss {

JsonRpcError::JsonRpcError(int code_, std::string message_, nlohmann::json data_)
    : std::runtime_error("[" + std::to_string(code_) + "] " + message_ + " " + data_.dump()),
      code(code_),
      message(std::move(message_)),
      data(std::move(data_)) {}

JsonRpcTransportError::JsonRpcTransportError(const std::string& what) : std::runtime_error(what) {}

std::string to_string(DeviceType type) {
  switch (type) {
    case DeviceType::PMT:
      return "PMT";
    case DeviceType::LED:
      return "LED";
  }
  throw std::invalid_argument("invalid DeviceType");
}

std::string to_string(TriggerSource source) {
  switch (source) {
    case TriggerSource::MB:
      return "MB";
    case TriggerSource::MCU:
      return "MCU";
    case TriggerSource::EXT:
      return "EXT";
  }
  throw std::invalid_argument("invalid TriggerSource");
}

namespace {

size_t WriteCallback(char* ptr, size_t size, size_t nmemb, void* userdata) {
  auto* out = static_cast<std::string*>(userdata);
  out->append(ptr, size * nmemb);
  return size * nmemb;
}

}  // namespace

BaseRpcClient::BaseRpcClient(std::string url, double timeout_sec)
    : url_(std::move(url)), timeout_(timeout_sec) {
  curl_ = curl_easy_init();
  if (!curl_) {
    throw JsonRpcTransportError("failed to initialise curl handle");
  }
  // Content-Type never changes across calls, so it's set once here rather
  // than rebuilt on every post().
  headers_ = curl_slist_append(nullptr, "Content-Type: application/json");
  curl_easy_setopt(static_cast<CURL*>(curl_), CURLOPT_URL, url_.c_str());
  curl_easy_setopt(static_cast<CURL*>(curl_), CURLOPT_HTTPHEADER,
                    static_cast<curl_slist*>(headers_));
  curl_easy_setopt(static_cast<CURL*>(curl_), CURLOPT_WRITEFUNCTION, WriteCallback);
}

BaseRpcClient::~BaseRpcClient() {
  curl_slist_free_all(static_cast<curl_slist*>(headers_));
  curl_easy_cleanup(static_cast<CURL*>(curl_));
}

json BaseRpcClient::post(const json& payload, bool want_response) {
  std::lock_guard<std::mutex> lock(mutex_);

  CURL* curl = static_cast<CURL*>(curl_);

  std::string body = payload.dump();
  std::string response;

  curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
  curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, static_cast<long>(body.size()));
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, static_cast<long>(timeout_ * 1000));

  CURLcode res = curl_easy_perform(curl);

  long status_code = 0;
  curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status_code);

  if (res != CURLE_OK) {
    throw JsonRpcTransportError(curl_easy_strerror(res));
  }
  if (status_code != 0 && (status_code < 200 || status_code >= 300)) {
    throw JsonRpcTransportError("HTTP status " + std::to_string(status_code));
  }

  if (!want_response || response.empty()) {
    return nullptr;
  }

  json data;
  try {
    data = json::parse(response);
  } catch (const json::parse_error& exc) {
    throw JsonRpcTransportError(std::string("invalid JSON response: ") + exc.what());
  }

  if (data.contains("error") && !data["error"].is_null()) {
    const json& err = data["error"];
    throw JsonRpcError(err.value("code", 0), err.value("message", std::string("Unknown error")),
                        err.contains("data") ? err["data"] : nullptr);
  }

  return data.contains("result") ? data["result"] : nullptr;
}

json BaseRpcClient::call(const std::string& method, const json& params) {
  json payload = {{"jsonrpc", "2.0"}, {"method", method}, {"params", params}, {"id", next_id_++}};
  return post(payload, /*want_response=*/true);
}

void BaseRpcClient::notify(const std::string& method, const json& params) {
  json payload = {{"jsonrpc", "2.0"}, {"method", method}, {"params", params}};
  post(payload, /*want_response=*/false);
}

// ---------------------------------------------------------------------------
// febmgr
// ---------------------------------------------------------------------------

namespace {

json OptionalDeviceTypeParams(std::optional<DeviceType> channel_type) {
  if (!channel_type.has_value()) return json::array();
  return json::array({to_string(*channel_type)});
}

}  // namespace

std::vector<int> FebmgrNamespace::getDefinedChannels(std::optional<DeviceType> channel_type) {
  return client_.call("febmgr.getDefinedChannels", OptionalDeviceTypeParams(channel_type));
}

std::vector<int> FebmgrNamespace::getOnlineChannels(std::optional<DeviceType> channel_type) {
  return client_.call("febmgr.getOnlineChannels", OptionalDeviceTypeParams(channel_type));
}

std::vector<int> FebmgrNamespace::getOfflineChannels(std::optional<DeviceType> channel_type) {
  return client_.call("febmgr.getOfflineChannels", OptionalDeviceTypeParams(channel_type));
}

json FebmgrNamespace::getStatus(std::optional<DeviceType> channel_type) {
  return client_.call("febmgr.getStatus", OptionalDeviceTypeParams(channel_type));
}

void FebmgrNamespace::enableChannel(int channel) {
  client_.call("febmgr.enableChannel", json::array({channel}));
}

void FebmgrNamespace::disableChannel(int channel) {
  client_.call("febmgr.disableChannel", json::array({channel}));
}

void FebmgrNamespace::enableChannels(const std::vector<int>& channels) {
  client_.call("febmgr.enableChannels", json::array({channels}));
}

void FebmgrNamespace::disableChannels(const std::vector<int>& channels) {
  client_.call("febmgr.disableChannels", json::array({channels}));
}

void FebmgrNamespace::enableChannelsByMask(uint32_t mask) {
  client_.call("febmgr.enableChannelsByMask", json::array({mask}));
}

void FebmgrNamespace::disableChannelsByMask(uint32_t mask) {
  client_.call("febmgr.disableChannelsByMask", json::array({mask}));
}

json FebmgrNamespace::getPMTStatus(int channel) {
  return client_.call("febmgr.getPMTStatus", json::array({channel}));
}

double FebmgrNamespace::getPMTVoltage(int channel) {
  return client_.call("febmgr.getPMTVoltage", json::array({channel}));
}

double FebmgrNamespace::getPMTVoltageSet(int channel) {
  return client_.call("febmgr.getPMTVoltageSet", json::array({channel}));
}

void FebmgrNamespace::setPMTVoltageSet(int channel, int value) {
  client_.call("febmgr.setPMTVoltageSet", json::array({channel, value}));
}

double FebmgrNamespace::getPMTCurrent(int channel) {
  return client_.call("febmgr.getPMTCurrent", json::array({channel}));
}

double FebmgrNamespace::getPMTTemperature(int channel) {
  return client_.call("febmgr.getPMTTemperature", json::array({channel}));
}

int FebmgrNamespace::getPMTRateRampup(int channel) {
  return client_.call("febmgr.getPMTRateRampup", json::array({channel}));
}

int FebmgrNamespace::getPMTRateRampdown(int channel) {
  return client_.call("febmgr.getPMTRateRampdown", json::array({channel}));
}

void FebmgrNamespace::setPMTRateRampup(int channel, int value) {
  client_.call("febmgr.setPMTRateRampup", json::array({channel, value}));
}

void FebmgrNamespace::setPMTRateRampdown(int channel, int value) {
  client_.call("febmgr.setPMTRateRampdown", json::array({channel, value}));
}

void FebmgrNamespace::setPMTLimitVoltage(int channel, int value) {
  client_.call("febmgr.setPMTLimitVoltage", json::array({channel, value}));
}

void FebmgrNamespace::setPMTLimitCurrent(int channel, int value) {
  client_.call("febmgr.setPMTLimitCurrent", json::array({channel, value}));
}

void FebmgrNamespace::setPMTLimitTemperature(int channel, int value) {
  client_.call("febmgr.setPMTLimitTemperature", json::array({channel, value}));
}

void FebmgrNamespace::setPMTLimitTriptime(int channel, int value) {
  client_.call("febmgr.setPMTLimitTriptime", json::array({channel, value}));
}

void FebmgrNamespace::setPMTThreshold(int channel, double value) {
  client_.call("febmgr.setPMTThreshold", json::array({channel, value}));
}

double FebmgrNamespace::getPMTThreshold(int channel) {
  return client_.call("febmgr.getPMTThreshold", json::array({channel}));
}

json FebmgrNamespace::getPMTAlarm(int channel) {
  return client_.call("febmgr.getPMTAlarm", json::array({channel}));
}

double FebmgrNamespace::getPMTVref(int channel) {
  return client_.call("febmgr.getPMTVref", json::array({channel}));
}

void FebmgrNamespace::powerPMTOn(int channel) {
  client_.call("febmgr.powerPMTOn", json::array({channel}));
}

void FebmgrNamespace::powerPMTOff(int channel) {
  client_.call("febmgr.powerPMTOff", json::array({channel}));
}

void FebmgrNamespace::resetPMT(int channel) {
  client_.call("febmgr.resetPMT", json::array({channel}));
}

json FebmgrNamespace::getPMTInfo(int channel) {
  return client_.call("febmgr.getPMTInfo", json::array({channel}));
}

void FebmgrNamespace::setPMTSerialNumber(int channel, const std::string& sn) {
  client_.call("febmgr.setPMTSerialNumber", json::array({channel, sn}));
}

void FebmgrNamespace::setPMTHVSerialNumber(int channel, const std::string& sn) {
  client_.call("febmgr.setPMTHVSerialNumber", json::array({channel, sn}));
}

void FebmgrNamespace::setPMTFEBSerialNumber(int channel, const std::string& sn) {
  client_.call("febmgr.setPMTFEBSerialNumber", json::array({channel, sn}));
}

json FebmgrNamespace::readPMTMonRegisters(int channel) {
  return client_.call("febmgr.readPMTMonRegisters", json::array({channel}));
}

json FebmgrNamespace::readPMTCalibRegisters(int channel) {
  return client_.call("febmgr.readPMTCalibRegisters", json::array({channel}));
}

void FebmgrNamespace::writePMTCalibSlope(int channel, double value) {
  client_.call("febmgr.writePMTCalibSlope", json::array({channel, value}));
}

void FebmgrNamespace::writePMTCalibOffset(int channel, double value) {
  client_.call("febmgr.writePMTCalibOffset", json::array({channel, value}));
}

void FebmgrNamespace::writePMTCalibDiscr(int channel, double value) {
  client_.call("febmgr.writePMTCalibDiscr", json::array({channel, value}));
}

json FebmgrNamespace::getLEDStatus(int channel) {
  return client_.call("febmgr.getLEDStatus", json::array({channel}));
}

json FebmgrNamespace::getLEDInfo(int channel) {
  return client_.call("febmgr.getLEDInfo", json::array({channel}));
}

json FebmgrNamespace::getLEDTriggerStatus(int channel) {
  return client_.call("febmgr.getLEDTriggerStatus", json::array({channel}));
}

json FebmgrNamespace::getLEDBiasStatus(int channel) {
  return client_.call("febmgr.getLEDBiasStatus", json::array({channel}));
}

double FebmgrNamespace::getLEDBiasVoltage(int channel) {
  return client_.call("febmgr.getLEDBiasVoltage", json::array({channel}));
}

double FebmgrNamespace::readLEDBiasVoltage(int channel) {
  return client_.call("febmgr.readLEDBiasVoltage", json::array({channel}));
}

json FebmgrNamespace::getLEDTriggerSource(int channel) {
  return client_.call("febmgr.getLEDTriggerSource", json::array({channel}));
}

double FebmgrNamespace::getLEDCurrent(int channel) {
  return client_.call("febmgr.getLEDCurrent", json::array({channel}));
}

std::vector<int> FebmgrNamespace::getLEDChannels(int channel) {
  return client_.call("febmgr.getLEDChannels", json::array({channel}));
}

json FebmgrNamespace::readLEDMonRegisters(int channel) {
  return client_.call("febmgr.readLEDMonRegisters", json::array({channel}));
}

void FebmgrNamespace::powerLEDOn(int channel) {
  client_.call("febmgr.powerLEDOn", json::array({channel}));
}

void FebmgrNamespace::powerLEDOff(int channel) {
  client_.call("febmgr.powerLEDOff", json::array({channel}));
}

void FebmgrNamespace::setLEDTrigger(int channel, bool value) {
  client_.call("febmgr.setLEDTrigger", json::array({channel, value}));
}

void FebmgrNamespace::setLEDTriggerSource(int channel, TriggerSource source) {
  client_.call("febmgr.setLEDTriggerSource", json::array({channel, to_string(source)}));
}

void FebmgrNamespace::setLEDBias(int channel, bool value) {
  client_.call("febmgr.setLEDBias", json::array({channel, value}));
}

void FebmgrNamespace::setLEDBiasVoltage(int channel, double value) {
  client_.call("febmgr.setLEDBiasVoltage", json::array({channel, value}));
}

void FebmgrNamespace::setLEDChannels(int channel, const std::vector<int>& channels,
                                      std::optional<bool> append) {
  json params = json::array({channel, channels});
  if (append.has_value()) params.push_back(*append);
  client_.call("febmgr.setLEDChannels", params);
}

// ---------------------------------------------------------------------------
// fpga
// ---------------------------------------------------------------------------

int64_t FpgaNamespace::readRegister(int64_t address) {
  return client_.call("fpga.readRegister", json::array({address}));
}

int64_t FpgaNamespace::writeRegister(int64_t address, int64_t value) {
  return client_.call("fpga.writeRegister", json::array({address, value}));
}

// ---------------------------------------------------------------------------
// sensors
// ---------------------------------------------------------------------------

json SensorsNamespace::read() { return client_.call("sensors.read", json::array()); }

// ---------------------------------------------------------------------------
// MSSClient
// ---------------------------------------------------------------------------

MSSClient::MSSClient(const std::string& url, double timeout_sec)
    : BaseRpcClient(url, timeout_sec), febmgr(*this), fpga(*this), sensors(*this) {}

}  // namespace mpmt_mss
