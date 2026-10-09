#include <DmxSimple.h>

const uint8_t DMX_PIN = 13;
const uint16_t START_CHANNEL = 1;
const uint8_t RGB_GROUPS = 10;
const uint32_t SERIAL_BAUD = 115200;

char inputLine[16];
uint8_t inputLength = 0;
bool discardLine = false;

void writeRgbToAllGroups(uint8_t r, uint8_t g, uint8_t b) {
  for (uint8_t group = 0; group < RGB_GROUPS; ++group) {
    const uint16_t channel = START_CHANNEL + group * 3;
    DmxSimple.write(channel,     r);
    DmxSimple.write(channel + 1, g);
    DmxSimple.write(channel + 2, b);
  }
}

// Parse "R,G,B" — retorna true em sucesso
bool parseRgb(const char* line, uint8_t len, uint8_t& r, uint8_t& g, uint8_t& b) {
  uint16_t values[3] = {0, 0, 0};
  uint8_t field = 0;

  for (uint8_t i = 0; i < len; ++i) {
    const char c = line[i];
    if (c == ',') {
      if (field >= 2) return false;
      ++field;
    } else if (c >= '0' && c <= '9') {
      values[field] = values[field] * 10 + (c - '0');
      if (values[field] > 255) return false;
    } else {
      return false;
    }
  }

  if (field != 2) return false;
  r = (uint8_t)values[0];
  g = (uint8_t)values[1];
  b = (uint8_t)values[2];
  return true;
}

void processInputLine() {
  if (discardLine || inputLength == 0) return;

  uint8_t r, g, b;
  if (!parseRgb(inputLine, inputLength, r, g, b)) {
    Serial.println("ERR formato: R,G,B  ex: 255,0,0");
    return;
  }

  writeRgbToAllGroups(r, g, b);
  Serial.print("OK ");
  Serial.print(r); Serial.print(',');
  Serial.print(g); Serial.print(',');
  Serial.println(b);
}

void readSerialLines() {
  while (Serial.available() > 0) {
    const char value = Serial.read();
    if (value == '\n') {
      processInputLine();
      inputLength = 0;
      discardLine = false;
    } else if (value != '\r') {
      if (inputLength < sizeof(inputLine) - 1 && !discardLine) {
        inputLine[inputLength++] = value;
      } else {
        discardLine = true;
      }
    }
  }
}

void setup() {
  DmxSimple.usePin(DMX_PIN);
  DmxSimple.maxChannel(START_CHANNEL + RGB_GROUPS * 3 - 1);
  Serial.begin(SERIAL_BAUD);
  writeRgbToAllGroups(0, 0, 0);
  Serial.println("rgb_test pronto. Envie: R,G,B");
}

void loop() {
  readSerialLines();
}
