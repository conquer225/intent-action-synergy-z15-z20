#include "PendulumLink.h"
#include "BlePendulumSession.h"
#include "PendulumBleConfig.h"
#include <BLEDevice.h>
#include <BLEClient.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <atomic>
#if defined(CONFIG_NIMBLE_ENABLED)
#include <host/ble_hs.h>
#include <host/ble_gap.h>
#endif

namespace {
QueueHandle_t outputQueue=nullptr,snapshotQueue=nullptr,receiveQueue=nullptr;
std::atomic<bool> disconnected(false),rxOverflow(false);
struct RxChunk { uint8_t data[64];size_t length;uint32_t at; };
class Callbacks:public BLEClientCallbacks {
  void onConnect(BLEClient*) override {}
  void onDisconnect(BLEClient*) override { disconnected.store(true); }
};
Callbacks callbacks;
void publish(BlePendulumSession &s,uint32_t now,uint32_t arm) {
  PendulumLink::Snapshot v;
  v.revision=s.revision();v.connected=s.linked();v.seen=s.fresh(now);
  v.statusAt=s.statusAt();v.state=s.state();v.blocked=s.blocked();v.stmLinked=s.stmLinked();
  v.armed=s.neutralReady()?arm:0;
  xQueueOverwrite(snapshotQueue,&v);
}
void worker(void*) {
  Serial.println("BLE_SETUP,init");
  if(!BLEDevice::init("GuardianLoop-Pendulum")) { vTaskDelete(nullptr);return; }
  BLEClient *client=BLEDevice::createClient();
  if(!client) { vTaskDelete(nullptr);return; }
  Serial.printf("BLE_SETUP,client,handle:%u\n",client->getConnId());
  client->setClientCallbacks(&callbacks);
  BlePendulumSession session;BlePendulumInput input;
  for(;;) {
    disconnected.store(false);rxOverflow.store(false);xQueueReset(receiveQueue);
    Serial.printf("BLE_SETUP,connect,handle:%u,connected:%d",client->getConnId(),client->isConnected());
#if defined(CONFIG_NIMBLE_ENABLED)
    Serial.printf(",synced:%d,active:%d",ble_hs_synced(),ble_gap_conn_active());
#endif
    Serial.println();
    if(!client->connect(BLEAddress(PENDULUM_BLE_ADDRESS),0,3000)) {
      Serial.println("BLE_SETUP,connect_failed");
      session.connection(false,millis());publish(session,millis(),0);
      vTaskDelay(pdMS_TO_TICKS(1500));continue;
    }
    Serial.println("BLE_SETUP,service");
    BLERemoteService *service=client->getService(PENDULUM_BLE_SERVICE);
    Serial.printf("BLE_SETUP,characteristic,service:%d\n",service!=nullptr);
    BLERemoteCharacteristic *characteristic=service?service->getCharacteristic(PENDULUM_BLE_CHARACTERISTIC):nullptr;
    if(!characteristic || !characteristic->canNotify() || !characteristic->canWrite()) {
      Serial.println("BLE_SETUP,characteristic_failed");
      client->disconnect();vTaskDelay(pdMS_TO_TICKS(1500));continue;
    }
    Serial.println("BLE_SETUP,parameters");
    client->updateConnParams(12,24,0,100);
    Serial.println("BLE_SETUP,subscribe");
    characteristic->registerForNotify([](BLERemoteCharacteristic*,uint8_t *data,size_t n,bool) {
      while(n) {
        RxChunk chunk;chunk.length=n>sizeof(chunk.data)?sizeof(chunk.data):n;chunk.at=millis();
        memcpy(chunk.data,data,chunk.length);
        if(xQueueSend(receiveQueue,&chunk,0)!=pdPASS) {rxOverflow.store(true);return;}
        data+=chunk.length;n-=chunk.length;
      }
    });
    Serial.println("BLE_SETUP,ready");
    session.connection(true,millis());publish(session,millis(),0);
    uint32_t lastSend=millis()-50;
    while(client->isConnected() && !disconnected.load() && !rxOverflow.load()) {
      RxChunk chunk;
      for(unsigned n=0;n<16 && xQueueReceive(receiveQueue,&chunk,0)==pdPASS;++n)
        session.receive(chunk.data,chunk.length,chunk.at);
      xQueuePeek(outputQueue,&input,0);
      uint32_t now=millis();
      if(uint32_t(now-lastSend)>=50) {
        ControlFrame frame=session.output(now,input);
        uint8_t bytes[CONTROL_FRAME_SIZE];Control_Encode(&frame,bytes);
        // ATT completion may block only this worker; no movement write queue.
        bool ok=characteristic->writeValue(bytes,sizeof(bytes),true);
        lastSend=millis();if(!ok)break;
      }
      publish(session,millis(),input.arm);
      vTaskDelay(pdMS_TO_TICKS(5));
    }
    session.connection(false,millis());publish(session,millis(),0);
    if(client->isConnected())client->disconnect();
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}
}
void PendulumLink::begin() {
  if(outputQueue)return;
  outputQueue=xQueueCreate(1,sizeof(BlePendulumInput));
  snapshotQueue=xQueueCreate(1,sizeof(Snapshot));receiveQueue=xQueueCreate(16,sizeof(RxChunk));
  if(!outputQueue || !snapshotQueue || !receiveQueue)return;
  BlePendulumInput input;xQueueOverwrite(outputQueue,&input);
  xTaskCreatePinnedToCore(worker,"pendulum-ble",8192,nullptr,1,nullptr,0);
}
void PendulumLink::tick(uint32_t now,const ControlFrame &desired) {
  if(!outputQueue || !snapshotQueue)return;
  const uint32_t observedRevision=snapshot_.revision;
  xQueuePeek(snapshotQueue,&snapshot_,0);
  BlePendulumInput input;input.frame=desired;input.producedAt=now;
  // Desired was calculated before polling the snapshot: never retag an old action.
  input.revision=observedRevision;input.arm=arm_;
  xQueueOverwrite(outputQueue,&input);
}
void PendulumLink::forceStop() {
  arm_=0;if(!outputQueue)return;
  BlePendulumInput input;input.producedAt=millis();input.revision=snapshot_.revision;
  xQueueOverwrite(outputQueue,&input);
}
void PendulumLink::armNeutral() {
  static uint32_t serial=0;
  arm_=++serial;if(!arm_)arm_=++serial;
  if(!outputQueue)return;
  BlePendulumInput input;input.frame.flags=CONTROL_VALID;input.producedAt=millis();
  input.revision=snapshot_.revision;input.arm=arm_;
  xQueueOverwrite(outputQueue,&input);
}
