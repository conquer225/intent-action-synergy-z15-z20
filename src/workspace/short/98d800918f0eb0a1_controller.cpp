#include <Arduino.h>
#include <atomic>
#include <WiFi.h>
#include <WheelchairGuard.h>
#include <driver/gpio.h>
#include <esp_http_server.h>
#include <esp_random.h>
#include <esp_timer.h>
#include <inttypes.h>
#include "config.h"
#if WC_ENABLE_MOTOR_GPIO
#include "motor_gpio.h"
#endif

#if !CONFIG_IDF_TARGET_ESP32S3
#error "This isolated bench firmware targets ESP32-S3 only."
#endif

enum class Operation : uint8_t { Status, Ticket, Command, LocalArm, LocalClear, ManualArm };
struct Request {
  Operation operation;
  uint64_t id, issuedMs, stopGeneration;
  wc_wire_command command;
};
struct Reply {
  uint64_t id;
  bool ok, armed, estop, driverFault, manual;
  wc_direction direction;
  wc_ticket ticket;
  uint32_t gpioRequested, gpioInputs;
};
#if !WC_ENABLE_MOTOR_GPIO
static void printBenchReply(const Reply &reply);
#endif

static QueueHandle_t requests, replies;
static wc_guard guard;
static portMUX_TYPE flagMux = portMUX_INITIALIZER_UNLOCKED;
static bool stopPending, estopPending;
static uint64_t stopGeneration;
static std::atomic<bool> networkReady{false};
static bool stationMode, driverFault;
static uint32_t appliedMask;
static httpd_handle_t server;
static uint64_t nextRequestId;
static const char *const directionWords[] = {"stop", "forward", "backward", "left", "right"};
#if WC_ENABLE_MOTOR_GPIO
static const char product[] = "guardianloop-wheelchair-remote-0.1.0";
static const char operatingMode[] = "remote_control";
#else
static const char product[] = "guardianloop-wheelchair-bench-0.1.0";
static const char operatingMode[] = "bench_only";
#endif

static uint64_t nowMs() { return static_cast<uint64_t>(esp_timer_get_time()) / 1000; }

static void requestStop(bool estop = false) {
  portENTER_CRITICAL(&flagMux);
  stopPending = true;
  estopPending = estopPending || estop;
  if (stopGeneration != UINT64_MAX) ++stopGeneration;
  else estopPending = true;
  portEXIT_CRITICAL(&flagMux);
}

static uint64_t generation() {
  portENTER_CRITICAL(&flagMux);
  uint64_t value = stopGeneration;
  portEXIT_CRITICAL(&flagMux);
  return value;
}

static bool linkReady() {
  return networkReady && (stationMode ? WiFi.status() == WL_CONNECTED : WiFi.softAPgetStationNum() > 0);
}

static void motorOutput(void *, wc_direction direction) {
  uint32_t mask = wc_backup_gpio_mask(direction);
  // A renewal must not toggle mechanical relays off and on again.
  if (mask == appliedMask) return;
#if WC_ENABLE_MOTOR_GPIO
  bool ok = applyMotorPins(mask);
  if (!ok) {
    clearMotorPins();
    mask = 0;
    driverFault = true;
    requestStop(true);
  }
#endif
  appliedMask = mask;
}

static void motionOwner(void *) {
  uint64_t bootId;
  esp_fill_random(&bootId, sizeof(bootId));
  wc_init(&guard, motorOutput, nullptr, bootId, nowMs());
  TickType_t wake = xTaskGetTickCount();
  for (;;) {
    bool stop, estop;
    portENTER_CRITICAL(&flagMux);
    stop = stopPending; estop = estopPending;
    stopPending = false; estopPending = false;
    portEXIT_CRITICAL(&flagMux);
    wc_tick(&guard, nowMs());
    if (estop || driverFault) wc_estop(&guard);
    else if (stop || !linkReady()) wc_disarm(&guard);
    Request request;
    if (xQueueReceive(requests, &request, 0) == pdTRUE) {
      Reply reply = {};
      reply.id = request.id;
      uint64_t now = nowMs();
      bool timely = now >= request.issuedMs && now - request.issuedMs < 100;
      bool uncancelled = request.stopGeneration == generation();
      if (request.operation == Operation::Status) reply.ok = true;
      else if (!timely || !uncancelled || !linkReady()) wc_disarm(&guard);
      else switch (request.operation) {
        case Operation::Ticket: reply.ok = wc_issue_ticket(&guard, now, &reply.ticket); break;
        case Operation::Command:
          reply.ok = wc_command(&guard, request.command.boot_id, request.command.sequence,
                                request.command.direction, now);
          break;
        case Operation::LocalArm: reply.ok = wc_local_arm(&guard, now); break;
        case Operation::ManualArm:
#if WC_ENABLE_MOTOR_GPIO
          reply.ok = wc_manual_arm(&guard, now);
#endif
          break;
        case Operation::LocalClear:
          if (!driverFault) { wc_local_clear_estop(&guard); reply.ok = true; }
          break;
        default: break;
      }
      if (driverFault) { wc_estop(&guard); reply.ok = false; }
      reply.armed = guard.armed;
      reply.estop = guard.estop_latched;
      reply.driverFault = driverFault;
      reply.direction = guard.direction;
      reply.manual = guard.manual_mode;
      reply.gpioRequested = appliedMask;
#if WC_ENABLE_MOTOR_GPIO
      reply.gpioInputs = readMotorPins();
#endif
      if (reply.ticket.boot_id == 0) reply.ticket.boot_id = guard.boot_id;
      // Local operations have no HTTP waiter.
      if (request.id != 0 && xQueueSend(replies, &reply, 0) != pdTRUE) requestStop();
#if !WC_ENABLE_MOTOR_GPIO
      if (request.id == 0) printBenchReply(reply);
#endif
    }
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(10) > 0 ? pdMS_TO_TICKS(10) : 1);
  }
}

static bool transact(Operation operation, const wc_wire_command *command, Reply &reply) {
  if (nextRequestId == UINT64_MAX) { requestStop(true); return false; }
  Request request = {};
  request.id = ++nextRequestId;
  request.operation = operation;
  request.issuedMs = nowMs();
  request.stopGeneration = generation();
  if (command) request.command = *command;
  if (xQueueSend(requests, &request, 0) != pdTRUE) { requestStop(); return false; }
  uint64_t started = nowMs();
  while (nowMs() - started < 100) {
    if (xQueueReceive(replies, &reply, pdMS_TO_TICKS(10)) == pdTRUE && reply.id == request.id) return true;
  }
  requestStop();
  return false;
}

static esp_err_t sendError(httpd_req_t *request, const char *status, const char *reason) {
  httpd_resp_set_status(request, status);
  httpd_resp_set_type(request, "text/plain");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  return httpd_resp_sendstr(request, reason);
}

static bool authorized(httpd_req_t *request) {
  const size_t required = strlen(WC_AUTH_TOKEN);
  char token[65];
  if (required != 64 || httpd_req_get_hdr_value_len(request, "X-WC-Key") != required ||
      httpd_req_get_hdr_value_str(request, "X-WC-Key", token, sizeof(token)) != ESP_OK) {
    requestStop(); return false;
  }
  unsigned difference = 0;
  for (size_t i = 0; i < required; ++i) difference |= static_cast<unsigned char>(token[i] ^ WC_AUTH_TOKEN[i]);
  if (difference) requestStop();
  return difference == 0;
}

static void formatReply(char *json, size_t capacity, const Reply &reply) {
  char requested[5] = {}, inputs[5] = {};
  for (unsigned i = 0; i < 4; ++i) {
    requested[i] = '0' + ((reply.gpioRequested >> (10 + i)) & 1);
    inputs[i] = '0' + ((reply.gpioInputs >> (10 + i)) & 1);
  }
  snprintf(json, capacity,
    "{\"firmware\":\"%s\",\"ok\":%s,\"armed\":%s,\"software_estop_latched\":%s,\"driver_fault\":%s,"
    "\"requested_direction\":\"%s\",\"motor_gpio_enabled\":%s,\"current_motor_state\":\"not_observed\","
    "\"mode\":\"%s\",\"lease_ms\":300,\"max_burst_ms\":1000,"
    "\"manual_lease_ms\":500,\"manual_active\":%s,"
    "\"gpio_profile\":\"input_output_v1\",\"gpio_pin_order\":[10,11,12,13],"
    "\"gpio_requested_bits\":\"%s\",\"gpio_input_bits\":\"%s\",\"gpio_readback_available\":%s,"
    "\"boot_id\":\"%016" PRIx64 "\",\"sequence\":\"%016" PRIx64 "\",\"expires_ms\":\"%" PRIu64 "\"}",
    product, reply.ok ? "true" : "false", reply.armed ? "true" : "false", reply.estop ? "true" : "false",
    reply.driverFault ? "true" : "false", directionWords[reply.direction],
    WC_ENABLE_MOTOR_GPIO ? "true" : "false", operatingMode, reply.manual ? "true" : "false",
    requested, inputs, WC_ENABLE_MOTOR_GPIO ? "true" : "false",
    reply.ticket.boot_id, reply.ticket.sequence, reply.ticket.expires_ms);
}

#if !WC_ENABLE_MOTOR_GPIO
static void printBenchReply(const Reply &reply) {
  char json[768];
  formatReply(json, sizeof(json), reply);
  Serial.printf("BENCH {\"link_ready\":%s,\"state\":%s}\n", linkReady() ? "true" : "false", json);
}
#endif

static esp_err_t sendReply(httpd_req_t *request, const Reply &reply) {
  char json[768];
  formatReply(json, sizeof(json), reply);
  httpd_resp_set_type(request, "application/json");
  httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  return httpd_resp_sendstr(request, json);
}

static esp_err_t statusHandler(httpd_req_t *request) {
  Reply reply;
  if (!transact(Operation::Status, nullptr, reply)) return sendError(request, "503 Service Unavailable", "owner unavailable");
  return sendReply(request, reply);
}

static esp_err_t ticketHandler(httpd_req_t *request) {
  if (!authorized(request)) return sendError(request, "401 Unauthorized", "key required");
  if (request->content_len != 0) { requestStop(); return sendError(request, "400 Bad Request", "empty body required"); }
  Reply reply;
  if (!transact(Operation::Ticket, nullptr, reply)) return sendError(request, "503 Service Unavailable", "owner unavailable");
  if (!reply.ok) httpd_resp_set_status(request, "409 Conflict");
  return sendReply(request, reply);
}

static esp_err_t commandHandler(httpd_req_t *request) {
  if (!authorized(request)) return sendError(request, "401 Unauthorized", "key required");
  if (request->content_len < 38 || request->content_len > 42) {
    requestStop(); return sendError(request, "400 Bad Request", "invalid body length");
  }
  char body[42];
  size_t received = 0;
  while (received < request->content_len) {
    int count = httpd_req_recv(request, body + received, request->content_len - received);
    if (count <= 0) { requestStop(); return sendError(request, "400 Bad Request", "incomplete body"); }
    received += static_cast<size_t>(count);
  }
  wc_wire_command command;
  if (!wc_decode_command(body, received, &command)) {
    requestStop(); return sendError(request, "400 Bad Request", "invalid command");
  }
  Reply reply;
  if (!transact(Operation::Command, &command, reply)) return sendError(request, "503 Service Unavailable", "owner unavailable");
  if (!reply.ok) httpd_resp_set_status(request, "409 Conflict");
  return sendReply(request, reply);
}

static esp_err_t manualArmHandler(httpd_req_t *request) {
  if (!authorized(request)) return sendError(request, "401 Unauthorized", "key required");
  if (request->content_len != 0) { requestStop(); return sendError(request, "400 Bad Request", "empty body required"); }
  Reply reply;
  if (!transact(Operation::ManualArm, nullptr, reply)) return sendError(request, "503 Service Unavailable", "owner unavailable");
  if (!reply.ok) httpd_resp_set_status(request, "409 Conflict");
  return sendReply(request, reply);
}

static esp_err_t stopHandler(httpd_req_t *request) {
  requestStop(); // A local-network STOP is deliberately allowed without a motion key.
  return sendError(request, "202 Accepted", "stop requested; physical stop not observed");
}

static esp_err_t legacyHandler(httpd_req_t *request) {
  requestStop();
  return sendError(request, "410 Gone", "legacy direction routes disabled; use bounded ticket protocol");
}

static esp_err_t pageHandler(httpd_req_t *request) {
  static const char page[] = R"HTML(<!doctype html><meta charset="utf-8"><title>GuardianLoop 轮椅台架</title>
<h1>轮椅接收端状态／停止</h1><p>请通过 Z15 手机控制台选择方向。电机 GPIO 是否启用请查看下方 motor_gpio_enabled 状态。</p>
<button id="stop">请求停止</button><pre id="state">读取状态…</pre>
<p>网页停止不是独立物理急停；未观察车轮或刹车状态。不用于载人行驶。</p>
<script>const state=document.getElementById('state');document.getElementById('stop').onclick=async()=>{try{state.textContent=await(await fetch('/api/stop',{method:'POST'})).text()}catch(e){state.textContent='停止请求未送达，请使用独立物理急停'}};
setInterval(async()=>{try{state.textContent=JSON.stringify(await(await fetch('/api/status',{cache:'no-store'})).json(),null,2)}catch(e){state.textContent='接收端不可达；不能据此确认轮椅已停'}},1000);</script>)HTML";
  httpd_resp_set_type(request, "text/html; charset=utf-8");
  return httpd_resp_sendstr(request, page);
}

static bool addRoute(const char *uri, httpd_method_t method, esp_err_t (*handler)(httpd_req_t *)) {
  httpd_uri_t route = {};
  route.uri = uri; route.method = method; route.handler = handler;
  return httpd_register_uri_handler(server, &route) == ESP_OK;
}

static bool startServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.max_uri_handlers = 11;
  config.recv_wait_timeout = 1;
  config.send_wait_timeout = 1;
  if (httpd_start(&server, &config) != ESP_OK) return false;
  bool ok = addRoute("/", HTTP_GET, pageHandler) && addRoute("/api/status", HTTP_GET, statusHandler) &&
    addRoute("/api/ticket", HTTP_POST, ticketHandler) && addRoute("/api/command", HTTP_POST, commandHandler) &&
    addRoute("/api/stop", HTTP_POST, stopHandler) && addRoute("/stop", HTTP_POST, stopHandler);
  ok = addRoute("/api/manual-arm", HTTP_POST, manualArmHandler) && ok;
  for (const char *uri : {"/start", "/turn_back", "/turn_left", "/turn_right"}) ok = addRoute(uri, HTTP_POST, legacyHandler) && ok;
  if (!ok) { httpd_stop(server); server = nullptr; }
  return ok;
}

static bool configureNetwork() {
  if (strlen(WC_AUTH_TOKEN) != 64) return false;
  for (const char *p = WC_AUTH_TOKEN; *p; ++p) {
    if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f'))) return false;
  }
  stationMode = strlen(WC_STA_SSID) != 0;
  if (stationMode && strlen(WC_STA_PASSWORD) < 12) return false;
  if (!stationMode && (strlen(WC_AP_PASSWORD) < 12 || strlen(WC_AP_PASSWORD) > 63)) return false;
  WiFi.onEvent([](arduino_event_id_t event, arduino_event_info_t) {
    if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED || event == ARDUINO_EVENT_WIFI_AP_STADISCONNECTED) requestStop();
  });
  if (stationMode) { WiFi.mode(WIFI_STA); WiFi.begin(WC_STA_SSID, WC_STA_PASSWORD); return true; }
  WiFi.mode(WIFI_AP);
  return WiFi.softAP(WC_AP_SSID, WC_AP_PASSWORD);
}

void setup() {
  Serial.begin(115200);
  Serial.println(product);
  requests = xQueueCreate(8, sizeof(Request));
  replies = xQueueCreate(8, sizeof(Reply));
  if (!requests || !replies) { Serial.println("Queue allocation failed; keep motor power disconnected."); return; }
#if WC_ENABLE_MOTOR_GPIO
  if (!initializeMotorPins()) { Serial.println("GPIO init failed; use independent physical stop."); return; }
#endif
  networkReady = configureNetwork();
  if (xTaskCreatePinnedToCore(motionOwner, "wheelchair_owner", 4096, nullptr, 6, nullptr, 0) != pdPASS) {
    Serial.println("Owner creation failed; keep motor power disconnected."); networkReady = false; return;
  }
  if (networkReady && !startServer()) { requestStop(true); networkReady = false; }
  Serial.println("Unoccupied validation required. Manual control renews a 500ms lease; loss/STOP disarms. Serial ARM retains the one-second bench limit. ESTOP latches; CLEAR does not arm.");
  Serial.println(WC_ENABLE_MOTOR_GPIO ? "Motor GPIO build opted in; physical safety NOT certified." : "Motor GPIO disabled. No output pin initialization/writes in this build.");
  if (!networkReady) Serial.println("Network closed: configure private credentials for an isolated, disconnected-motor bench test.");
}

void loop() {
#if WC_ENABLE_MOTOR_GPIO
  static char line[9];
#else
  static char line[48];
#endif
  static size_t used;
  static bool discardLine;
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c != '\n') {
      if (!discardLine && used < sizeof(line) - 1) line[used++] = c;
      else { discardLine = true; requestStop(); }
      continue;
    }
    if (discardLine) { used = 0; discardLine = false; continue; }
    line[used] = '\0'; used = 0;
    if (!strcmp(line, "STOP")) { requestStop(); continue; }
    if (!strcmp(line, "ESTOP")) { requestStop(true); continue; }
    Request request = {};
#if !WC_ENABLE_MOTOR_GPIO
    if (!strcmp(line, "STATUS")) request.operation = Operation::Status;
    else if (!strcmp(line, "TICKET")) request.operation = Operation::Ticket;
    else if (!strncmp(line, "CMD ", 4)) {
      request.operation = Operation::Command;
      if (!wc_decode_command(line + 4, strlen(line + 4), &request.command)) {
        requestStop(); Serial.println("BENCH invalid wire command"); continue;
      }
    }
    else
#endif
    if (!strcmp(line, "ARM")) request.operation = Operation::LocalArm;
    else if (!strcmp(line, "CLEAR")) request.operation = Operation::LocalClear;
    else { requestStop(); Serial.println("Only ARM, STOP, ESTOP, CLEAR are accepted locally."); continue; }
    request.issuedMs = nowMs(); request.stopGeneration = generation();
    if (!requests || xQueueSend(requests, &request, 0) != pdTRUE) requestStop();
  }
  delay(10);
}
