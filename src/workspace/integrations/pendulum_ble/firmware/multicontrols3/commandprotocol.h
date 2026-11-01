#pragma once
#include <ArduinoJson.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

enum class CommandSource : uint8_t { NONE, PC, EYE, BRAIN };
enum class CommandDevice : uint8_t { ALL, HAND, PENDULUM };
enum class CommandAction : uint8_t {
  HELLO, HEARTBEAT, STATUS, MODE, ENABLE, DISABLE, ESTOP,
  OPEN, CLOSE, POSE, START, STOP, LEFT, RIGHT, SET_INPUT, ZERO
};
enum class CommandMode : uint8_t { NONE, NETWORK, EMG, GLOVE, TILT_TEST };
struct NetworkRequest {
  CommandSource source = CommandSource::NONE;
  CommandDevice device = CommandDevice::ALL;
  CommandAction action = CommandAction::STATUS;
  CommandMode mode = CommandMode::NONE;
  uint32_t sequence = 0;
  int16_t angles[6] = {};
  bool contactInput = false;
};
constexpr size_t NETWORK_LINE_LIMIT = 1023;
constexpr uint32_t SOURCE_TIMEOUT_MS = 500;
inline const char *sourceName(CommandSource source) {
  switch (source) {
    case CommandSource::PC: return "pc";
    case CommandSource::EYE: return "eye";
    case CommandSource::BRAIN: return "brain";
    default: return "none";
  }
}
inline bool forwardSequence(uint32_t current, uint32_t previous) {
  uint32_t delta = current - previous;
  return delta != 0 && delta < 0x80000000UL;
}
inline bool singleJsonObject(const char *line,size_t size,size_t &fields) {
  bool quoted=false,escaped=false,started=false,finished=false;
  unsigned depth=0; fields=0;
  for(size_t i=0;i<size;++i) {
    char c=line[i]; if (!c) return false;
    if (quoted) {
      if(escaped) escaped=false;
      else if(c=='\\') escaped=true;
      else if(c=='"') quoted=false;
      continue;
    }
    if(c==' ' || c=='\t' || c=='\r' || c=='\n') continue;
    if(finished) return false;
    if(!started) { if(c!='{') return false; started=true; }
    if(c=='"') quoted=true;
    else if(c=='{' || c=='[') ++depth;
    else if(c=='}' || c==']') { if(!depth) return false; if(!--depth) finished=true; }
    else if(c==':' && depth==1) ++fields;
  }
  return started && finished && !quoted && !depth;
}
inline bool parseNetworkRequest(const char *line, size_t size,
                               NetworkRequest &out, const char *&error) {
  error = "bad_request";
  if (!size || size > NETWORK_LINE_LIMIT) { error = "line_too_long"; return false; }
  size_t fields=0;
  if(!singleJsonObject(line,size,fields)) { error="bad_json"; return false; }
  // Read-only input keeps strings inside the document. Bound nesting and bytes.
  JsonDocument document;
  if (deserializeJson(document, line, size, DeserializationOption::NestingLimit(3))) {
    error = "bad_json"; return false;
  }
  JsonObjectConst obj = document.as<JsonObjectConst>();
  if (obj.isNull() || fields!=obj.size() || obj.size() < 5 || obj.size() > 7 ||
      !obj["v"].is<unsigned>() || obj["v"].as<unsigned>() != 1 ||
      !obj["seq"].is<uint32_t>() || !obj["source"].is<const char *>() ||
      !obj["device"].is<const char *>() || !obj["action"].is<const char *>()) return false;
  for (JsonPairConst field : obj) {
    const char *key = field.key().c_str();
    if (field.key().size()!=strlen(key)) return false;
    if (field.value().is<const char *>()) {
      JsonString text=field.value().as<JsonString>();
      if(text.size()!=strlen(text.c_str())) return false;
    }
    if (strcmp(key,"v") && strcmp(key,"seq") && strcmp(key,"source") &&
        strcmp(key,"device") && strcmp(key,"action") && strcmp(key,"mode") &&
        strcmp(key,"angles") && strcmp(key,"input")) { error = "unknown_field"; return false; }
  }
  NetworkRequest value;
  value.sequence = obj["seq"].as<uint32_t>();
  const char *source = obj["source"], *device = obj["device"], *action = obj["action"];
  if (!strcmp(source,"pc")) value.source = CommandSource::PC;
  else if (!strcmp(source,"eye")) value.source = CommandSource::EYE;
  else if (!strcmp(source,"brain")) value.source = CommandSource::BRAIN;
  else { error = "bad_source"; return false; }
  if (!strcmp(device,"hand")) value.device = CommandDevice::HAND;
  else if (!strcmp(device,"pendulum")) value.device = CommandDevice::PENDULUM;
  else if (strcmp(device,"all")) { error = "bad_device"; return false; }
  const char *actions[] = {"hello","heartbeat","status","mode","enable","disable","estop",
                          "open","close","pose","start","stop","left","right","input","zero"};
  size_t actionIndex = 0;
  while (actionIndex < sizeof(actions)/sizeof(actions[0]) && strcmp(action,actions[actionIndex])) ++actionIndex;
  if (actionIndex == sizeof(actions)/sizeof(actions[0])) { error = "bad_action"; return false; }
  value.action = static_cast<CommandAction>(actionIndex);
  if(obj.size()!=size_t(5+(value.action==CommandAction::MODE)+(value.action==CommandAction::POSE)+(value.action==CommandAction::SET_INPUT))) {
    error="unexpected_field"; return false;
  }
  if ((value.action == CommandAction::HELLO || value.action == CommandAction::HEARTBEAT) &&
       value.device != CommandDevice::ALL) { error = "all_required"; return false; }
  if (value.device == CommandDevice::ALL && value.action != CommandAction::HELLO &&
      value.action != CommandAction::HEARTBEAT && value.action != CommandAction::STATUS &&
      value.action != CommandAction::DISABLE && value.action != CommandAction::ESTOP) {
    error = "single_device_required"; return false;
  }
  if (value.action == CommandAction::MODE) {
    if (!obj["mode"].is<const char *>()) { error = "bad_mode"; return false; }
    const char *mode = obj["mode"];
    if (!strcmp(mode,"network")) value.mode = CommandMode::NETWORK;
    else if (!strcmp(mode,"emg")) value.mode = CommandMode::EMG;
    else if (!strcmp(mode,"glove") && value.device == CommandDevice::HAND) value.mode = CommandMode::GLOVE;
    else if (!strcmp(mode,"tilt_test") && value.device == CommandDevice::PENDULUM) value.mode = CommandMode::TILT_TEST;
    else { error = "bad_mode"; return false; }
  } else if (!obj["mode"].isNull()) { error = "unexpected_mode"; return false; }
  if (value.action == CommandAction::POSE) {
    JsonArrayConst angles = obj["angles"].as<JsonArrayConst>();
    if (value.device != CommandDevice::HAND || angles.size() != 6) { error = "bad_angles"; return false; }
    for (uint8_t i=0;i<6;++i) {
      if (!angles[i].is<int>() || angles[i].as<int>() < 0 || angles[i].as<int>() > 180) {
        error = "bad_angles"; return false;
      }
      value.angles[i] = angles[i].as<int16_t>();
    }
  } else if (!obj["angles"].isNull()) { error = "unexpected_angles"; return false; }
  if (value.action==CommandAction::SET_INPUT) {
    if (value.device!=CommandDevice::HAND || !obj["input"].is<const char *>()) { error="bad_input"; return false; }
    const char *input=obj["input"];
    if (strcmp(input,"contact") && strcmp(input,"rms")) { error="bad_input"; return false; }
    value.contactInput=!strcmp(input,"contact");
  } else if (!obj["input"].isNull()) { error="unexpected_input"; return false; }
  if ((value.action == CommandAction::OPEN || value.action == CommandAction::CLOSE) &&
       value.device != CommandDevice::HAND) { error = "hand_required"; return false; }
  if ((value.action == CommandAction::START || value.action == CommandAction::STOP ||
       value.action == CommandAction::LEFT || value.action == CommandAction::RIGHT || value.action==CommandAction::ZERO) &&
       value.device != CommandDevice::PENDULUM) { error = "pendulum_required"; return false; }
  out = value; error = nullptr; return true;
}

// This policy is shared by the actual TCP service and host regression tests.
struct SourceSession {
  bool active = false;
  CommandSource source = CommandSource::NONE;
  uint32_t lastSequence = 0, lastFreshMs = 0;
  bool expired(uint32_t now) const { return active && uint32_t(now-lastFreshMs) > SOURCE_TIMEOUT_MS; }
  void clear() { *this = SourceSession{}; }
  bool accepts(const NetworkRequest &request, uint32_t now, const char *&error) const {
    if (!active) {
      if (request.action != CommandAction::HELLO) { error="hello_required"; return false; }
      return true;
    }
    if (expired(now)) { error="session_expired"; return false; }
    if (request.source != source) { error="source_mismatch"; return false; }
    if (request.action == CommandAction::HELLO) { error="already_connected"; return false; }
    if (!forwardSequence(request.sequence,lastSequence)) { error="old_sequence"; return false; }
    return true;
  }
  void consume(const NetworkRequest &request, uint32_t now, bool accepted) {
    lastSequence=request.sequence;
    if (!accepted) return;
    active=true; source=request.source; lastFreshMs=now;
  }
};
