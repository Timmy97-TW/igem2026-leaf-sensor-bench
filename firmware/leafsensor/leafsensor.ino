// leafsensor.ino — ESP32 bench logger
// RS485 leaf temperature/wetness sensor (Modbus RTU) + SHT31 or SHT40 reference.
// No extra libraries needed. Board: "ESP32 Dev Module". Serial Monitor: 115200.
//
// Output, one CSV line per sample:
//   ms,ok,r0,r1,sht_t,sht_rh
//   r0 / r1 = the two Modbus registers divided by 10 (which one is wetness and
//   which one is temperature is decided from the datasheet, see guide step 0).
//
// Wiring (see index.html, section "Assemble"):
//   GPIO17 (TX2) -> RS485 module TXD     GPIO16 (RX2) -> RS485 module RXD
//   3V3 -> RS485 module VCC, SHT VIN     GND -> all grounds (common!)
//   GPIO21 -> SHT SDA                    GPIO22 -> SHT SCL

#include <Wire.h>

// ---------- edit these after reading the sensor label ----------
#define SHT_MODEL       31      // 31 = SHT31/SHT30/SHT35, 40 = SHT40/SHT41/SHT45
#define SAMPLE_MS       2000    // 2 s during tests; 10000 for overnight run
#define MODBUS_ADDR     1       // factory default is almost always 1
#define REG_START       0x0000  // first register to read
#define REG_COUNT       2       // number of registers to read
// ----------------------------------------------------------------

HardwareSerial RS(2);
long foundBaud = 0;
uint8_t addr = MODBUS_ADDR;

uint16_t crc16(const uint8_t *b, int n) {
  uint16_t c = 0xFFFF;
  for (int i = 0; i < n; i++) {
    c ^= b[i];
    for (int k = 0; k < 8; k++) c = (c & 1) ? (c >> 1) ^ 0xA001 : c >> 1;
  }
  return c;
}

// Reads REG_COUNT holding registers into regs[]. Returns true on a valid reply.
bool modbusRead(uint8_t a, int16_t *regs) {
  uint8_t q[8] = {a, 0x03, REG_START >> 8, REG_START & 0xFF, 0, REG_COUNT};
  uint16_t c = crc16(q, 6);
  q[6] = c & 0xFF; q[7] = c >> 8;
  while (RS.available()) RS.read();
  RS.write(q, 8);
  RS.flush();
  const int n = 5 + 2 * REG_COUNT;
  uint8_t r[5 + 2 * 8];
  if (RS.readBytes(r, n) != n) return false;
  if (crc16(r, n - 2) != (r[n - 2] | (r[n - 1] << 8))) return false;
  if (r[1] != 0x03) return false;
  for (int i = 0; i < REG_COUNT; i++) regs[i] = (int16_t)((r[3 + 2 * i] << 8) | r[4 + 2 * i]);
  return true;
}

bool shtRead(float &t, float &rh) {
  Wire.beginTransmission(0x44);
#if SHT_MODEL == 40
  Wire.write(0xFD);                       // SHT4x: measure, high precision
#else
  Wire.write(0x24); Wire.write(0x00);     // SHT3x: single shot, high repeatability
#endif
  if (Wire.endTransmission() != 0) return false;
  delay(20);
  if (Wire.requestFrom(0x44, 6) != 6) return false;
  uint8_t d[6];
  for (int i = 0; i < 6; i++) d[i] = Wire.read();
  uint16_t rt = (d[0] << 8) | d[1], rr = (d[3] << 8) | d[4];
  t = -45 + 175.0 * rt / 65535.0;
#if SHT_MODEL == 40
  rh = -6 + 125.0 * rr / 65535.0;
#else
  rh = 100.0 * rr / 65535.0;
#endif
  rh = constrain(rh, 0, 100);
  return true;
}

void findSensor() {
  const long bauds[] = {4800, 9600, 2400, 19200};
  const uint8_t addrs[] = {MODBUS_ADDR, 0xFF};
  int16_t regs[8];
  for (long bd : bauds) {
    RS.begin(bd, SERIAL_8N1, 16, 17);
    RS.setTimeout(300);
    for (uint8_t a : addrs) {
      if (modbusRead(a, regs)) {
        foundBaud = bd; addr = a;
        Serial.printf("# FOUND sensor: baud=%ld addr=%d\n", bd, a);
        return;
      }
    }
    RS.end();
  }
  Serial.println("# NO REPLY. Check: power LED/voltage, common GND, swap TX/RX, swap A/B.");
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Wire.begin(21, 22);
  Serial.println("# leafsensor bench logger");
  float t, rh;
  Serial.println(shtRead(t, rh) ? "# SHT OK" : "# SHT NOT FOUND (check SDA=21, SCL=22, SHT_MODEL)");
  findSensor();
  Serial.println("ms,ok,r0,r1,sht_t,sht_rh");
}

void loop() {
  static unsigned long last = 0;
  if (millis() - last < SAMPLE_MS) return;
  last = millis();
  if (!foundBaud) { findSensor(); if (!foundBaud) { delay(3000); return; } }
  int16_t regs[8] = {0};
  bool ok = modbusRead(addr, regs);
  float t = NAN, rh = NAN;
  shtRead(t, rh);
  Serial.printf("%lu,%d,%.1f,%.1f,%.2f,%.2f\n", last, ok ? 1 : 0,
                ok ? regs[0] / 10.0 : NAN, ok ? regs[1] / 10.0 : NAN, t, rh);
}
