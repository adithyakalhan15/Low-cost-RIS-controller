#include <Arduino.h>
#include <LD2450.hpp>
#include <math.h>

using namespace esphome::ld245x;

// ================= UART PINS =================
// LD2450 TX -> ESP32 RX
// LD2450 RX -> ESP32 TX

#define RX_PIN_A 11
#define TX_PIN_A 10

#define RX_PIN_B 5
#define TX_PIN_B 4

// ================= SENSOR GEOMETRY =================
// Same physical mounting point.
// Surface normals separated by 90 degrees total.
// A looks +45 degrees, B looks -45 degrees.

const float ANGLE_SENSOR_A = 45.0;
const float ANGLE_SENSOR_B = -45.0;

const float OFFSET_X_A = 0.0;
const float OFFSET_Y_A = 0.0;

const float OFFSET_X_B = 0.0;
const float OFFSET_Y_B = 0.0;

// Fusion threshold in mm.
// If A and B transformed points are within this distance, treat as same target.
const float MERGE_DISTANCE_MM = 400.0;

// Remove stale fused targets after this time.
const uint32_t TARGET_TIMEOUT_MS = 1200;

// Ignore fake/zero targets closer than this distance.
const float MIN_VALID_DISTANCE_M = 0.15;

// Keep both false for Raspberry Pi serial input.
const bool DEBUG_UART = false;
const bool PRINT_MEAS_JSON = false;

HardwareSerial ld2450Serial_A(1);
HardwareSerial ld2450Serial_B(2);

enum SensorID {
  SENSOR_A,
  SENSOR_B
};

struct RadarPacket {
  SensorID sensor;
  int id;
  int16_t x;
  int16_t y;
  int16_t speed;
  uint16_t resolution;
};

struct RadarTaskParams {
  HardwareSerial* serial;
  SensorID sensor;
  const char* name;
};

struct FusedTarget {
  bool active;
  int id;
  float x;
  float y;
  float speed;
  uint32_t lastSeen;
};

QueueHandle_t radarQueue;
FusedTarget fusedTargets[6];

RadarTaskParams radarAParams = { .serial = &ld2450Serial_A, .sensor = SENSOR_A, .name = "A" };
RadarTaskParams radarBParams = { .serial = &ld2450Serial_B, .sensor = SENSOR_B, .name = "B" };

float toRadians(float degrees) { return degrees * (PI / 180.0); }
float distanceM(float x_m, float y_m) { return sqrt((x_m * x_m) + (y_m * y_m)); }

bool isValidTargetMeters(float x_m, float y_m) {
  return distanceM(x_m, y_m) >= MIN_VALID_DISTANCE_M;
}

bool isValidTargetMm(float x_mm, float y_mm) {
  return isValidTargetMeters(x_mm / 1000.0, y_mm / 1000.0);
}

void localToGlobal(SensorID sensor, float localX, float localY, float &globalX, float &globalY) {
  float angle = 0.0;
  float offsetX = 0.0;
  float offsetY = 0.0;

  if (sensor == SENSOR_A) {
    angle = toRadians(ANGLE_SENSOR_A);
    offsetX = OFFSET_X_A;
    offsetY = OFFSET_Y_A;
  } else {
    angle = toRadians(ANGLE_SENSOR_B);
    offsetX = OFFSET_X_B;
    offsetY = OFFSET_Y_B;
  }

  float c = cos(angle);
  float s = sin(angle);

  globalX = (localX * c) - (localY * s) + offsetX;
  globalY = (localX * s) + (localY * c) + offsetY;
}

void cleanupStaleTargets() {
  uint32_t now = millis();
  for (int i = 0; i < 6; i++) {
    if (fusedTargets[i].active && (now - fusedTargets[i].lastSeen > TARGET_TIMEOUT_MS)) {
      fusedTargets[i].active = false;
    }
  }
}

int countActiveTargets() {
  int count = 0;
  for (int i = 0; i < 6; i++) {
    if (!fusedTargets[i].active) continue;
    if (isValidTargetMm(fusedTargets[i].x, fusedTargets[i].y)) count++;
  }
  return count;
}

int updateFusedTarget(float globalX, float globalY, float speed) {
  uint32_t now = millis();

  if (!isValidTargetMm(globalX, globalY)) {
    return -1;
  }

  int bestIndex = -1;
  float bestDistance = 999999.0;

  for (int i = 0; i < 6; i++) {
    if (!fusedTargets[i].active) continue;

    float dx = fusedTargets[i].x - globalX;
    float dy = fusedTargets[i].y - globalY;
    float distance = sqrt((dx * dx) + (dy * dy));

    if (distance < MERGE_DISTANCE_MM && distance < bestDistance) {
      bestDistance = distance;
      bestIndex = i;
    }
  }

  if (bestIndex >= 0) {
    fusedTargets[bestIndex].x = (0.65 * fusedTargets[bestIndex].x) + (0.35 * globalX);
    fusedTargets[bestIndex].y = (0.65 * fusedTargets[bestIndex].y) + (0.35 * globalY);
    fusedTargets[bestIndex].speed = (0.65 * fusedTargets[bestIndex].speed) + (0.35 * speed);
    fusedTargets[bestIndex].lastSeen = now;
    return bestIndex;
  }

  for (int i = 0; i < 6; i++) {
    if (!fusedTargets[i].active) {
      fusedTargets[i].active = true;
      fusedTargets[i].id = i;
      fusedTargets[i].x = globalX;
      fusedTargets[i].y = globalY;
      fusedTargets[i].speed = speed;
      fusedTargets[i].lastSeen = now;
      return i;
    }
  }

  return -1;
}

void printFusedTargetJson(int fusedID) {
  if (fusedID < 0) return;
  if (!fusedTargets[fusedID].active) return;

  float x_m = fusedTargets[fusedID].x / 1000.0;
  float y_m = fusedTargets[fusedID].y / 1000.0;
  float distance_m = distanceM(x_m, y_m);

  if (distance_m < MIN_VALID_DISTANCE_M) return;

  float angle_deg = atan2(y_m, x_m) * 180.0 / PI;
  float speed_value = fusedTargets[fusedID].speed;
  int activeTargets = countActiveTargets();

  Serial.printf(
    "{\"x\":%.3f,\"y\":%.3f,\"angle\":%.2f,\"distance\":%.3f,\"speed\":%.2f,\"targets\":%d}\n",
    x_m, y_m, angle_deg, distance_m, speed_value, activeTargets
  );
}

void printMeasurementJson(const char* sensorName, int rawID, float localX, float localY, float globalX, float globalY, float speed) {
  float local_x_m = localX / 1000.0;
  float local_y_m = localY / 1000.0;
  float global_x_m = globalX / 1000.0;
  float global_y_m = globalY / 1000.0;

  if (!isValidTargetMeters(global_x_m, global_y_m)) return;

  Serial.printf(
    "{\"type\":\"meas\",\"sensor\":\"%s\",\"raw_id\":%d,\"local_x\":%.3f,\"local_y\":%.3f,\"global_x\":%.3f,\"global_y\":%.3f,\"speed\":%.2f}\n",
    sensorName, rawID, local_x_m, local_y_m, global_x_m, global_y_m, speed
  );
}

void vRadarTask(void *pvParameters) {
  RadarTaskParams* params = (RadarTaskParams*)pvParameters;

  HardwareSerial* radarSerial = params->serial;
  SensorID sensorID = params->sensor;
  const char* sensorName = params->name;

  if (DEBUG_UART) Serial.printf("Radar task started: %s\n", sensorName);

  LD2450 detector;
  radarSerial->setTimeout(1000);
  detector.begin(*radarSerial);

  delay(500);
  detector.beginConfigurationSession();
  detector.setMultiTargetTracking();
  detector.endConfigurationSession();

  RadarPacket packet;
  packet.sensor = sensorID;
  uint32_t lastDebug = millis();

  for (;;) {
    if (detector.update()) {
      int validTargets = detector.getNrValidTargets();

      while (validTargets > 0) {
        validTargets--;
        auto target = detector.getTarget(validTargets);

        packet.id = target.id;
        packet.x = target.x;
        packet.y = target.y;
        packet.speed = target.v;
        packet.resolution = target.res;

        xQueueSend(radarQueue, &packet, pdMS_TO_TICKS(5));
      }
    }

    if (DEBUG_UART && millis() - lastDebug > 2000) {
      Serial.printf("DEBUG | Sensor: %s | UART available: %d\n", sensorName, radarSerial->available());
      lastDebug = millis();
    }

    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

void vBrainTask(void *pvParameters) {
  RadarPacket receivedTarget;

  if (DEBUG_UART) Serial.println("SYSTEM | Dual LD2450 tracking started");

  for (;;) {
    if (xQueueReceive(radarQueue, &receivedTarget, portMAX_DELAY) == pdTRUE) {
      float localX = receivedTarget.x;
      float localY = receivedTarget.y;
      float globalX = 0.0;
      float globalY = 0.0;

      localToGlobal(receivedTarget.sensor, localX, localY, globalX, globalY);

      if (!isValidTargetMm(globalX, globalY)) {
        cleanupStaleTargets();
        continue;
      }

      int fusedID = updateFusedTarget(globalX, globalY, receivedTarget.speed);
      const char* sensorName = receivedTarget.sensor == SENSOR_A ? "A" : "B";

      if (PRINT_MEAS_JSON) {
        printMeasurementJson(sensorName, receivedTarget.id, localX, localY, globalX, globalY, receivedTarget.speed);
      }

      cleanupStaleTargets();

      if (fusedID >= 0 && fusedTargets[fusedID].active) {
        printFusedTargetJson(fusedID);
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(2000);

  if (DEBUG_UART) {
    Serial.println();
    Serial.println("SYSTEM | Starting dual LD2450 test");
  }

  ld2450Serial_A.begin(256000, SERIAL_8N1, RX_PIN_A, TX_PIN_A);
  ld2450Serial_B.begin(256000, SERIAL_8N1, RX_PIN_B, TX_PIN_B);

  radarQueue = xQueueCreate(30, sizeof(RadarPacket));

  if (radarQueue == NULL) {
    if (DEBUG_UART) Serial.println("ERROR | Failed to create radarQueue");
    return;
  }

  xTaskCreatePinnedToCore(vRadarTask, "Radar_A_Task", 8192, &radarAParams, 2, NULL, 1);
  xTaskCreatePinnedToCore(vRadarTask, "Radar_B_Task", 8192, &radarBParams, 2, NULL, 1);
  xTaskCreatePinnedToCore(vBrainTask, "Brain_Task", 8192, NULL, 1, NULL, 1);
}

void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000));
}
