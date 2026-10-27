#include <DmxSimple.h>
#include <string.h>

const uint8_t DMX_PIN = 13;
const uint16_t START_CHANNEL = 1;
const uint8_t RGB_GROUPS = 10;
const unsigned long FADE_DURATION_MS = 500;
const uint32_t SERIAL_BAUD = 115200;

uint8_t currentRgb[3] = {0, 0, 0};
uint8_t fadeFromRgb[3] = {0, 0, 0};
uint8_t targetRgb[3] = {0, 0, 0};
unsigned long fadeStartedAt = 0;
bool fading = false;
char inputLine[32];
uint8_t inputLength = 0;
bool discardLine = false;

void writeRgbToAllGroups(const uint8_t rgb[3]) {
  for (uint8_t group = 0; group < RGB_GROUPS; ++group) {
    const uint16_t channel = START_CHANNEL + group * 3;
    DmxSimple.write(channel, rgb[0]);
    DmxSimple.write(channel + 1, rgb[1]);
    DmxSimple.write(channel + 2, rgb[2]);
  }
}

void selectColor(const uint8_t rgb[3]) {
  // Preserve the currently displayed value if a new command arrives mid-fade.
  for (uint8_t channel = 0; channel < 3; ++channel) {
    fadeFromRgb[channel] = currentRgb[channel];
    targetRgb[channel] = rgb[channel];
  }
  fadeStartedAt = millis();
  fading = true;
}

bool parseInputLine() {
  if (inputLength == 0) return false;
  inputLine[inputLength] = '\0';
  if (inputLength < 10 || strncmp(inputLine, "RGB(", 4) != 0 || inputLine[inputLength - 1] != ')') return false;
  uint8_t rgb[3];
  uint8_t position = 4;
  for (uint8_t channel = 0; channel < 3; ++channel) {
    if (position >= inputLength - 1 || inputLine[position] < '0' || inputLine[position] > '9') return false;
    uint16_t value = 0;
    while (position < inputLength - 1 && inputLine[position] >= '0' && inputLine[position] <= '9') {
      value = value * 10 + (inputLine[position++] - '0');
      if (value > 255) return false;
    }
    rgb[channel] = (uint8_t)value;
    if (channel < 2) {
      if (position >= inputLength - 1 || inputLine[position++] != ',') return false;
    }
  }
  if (position != inputLength - 1) return false;
  selectColor(rgb);
  return true;
}

void processInputLine() {
  if (inputLength == 0 && !discardLine) return;
  // "1" = the video (re)started. Nothing to do yet besides acknowledging it.
  if (!discardLine && inputLength == 1 && inputLine[0] == '1') {
    Serial.println("OK 1");
    return;
  }
  // Acknowledge every line so the host can tell the command arrived intact.
  if (!discardLine && parseInputLine()) {
    Serial.print("OK ");
    Serial.println(inputLine);
  } else {
    Serial.println("ERR");
  }
}

void readSerialLines() {
  while (Serial.available() > 0) {
    const char value = Serial.read();
    if (value == '\n') {
      processInputLine();
      inputLength = 0;
      discardLine = false;
    } else if (value == '\r') {
      continue;
    } else {
      if (inputLength < sizeof(inputLine) - 1 && !discardLine) {
        inputLine[inputLength++] = value;
      } else {
        discardLine = true;
      }
    }
  }
}

void updateFade() {
  if (!fading) return;

  const unsigned long elapsed = millis() - fadeStartedAt;
  if (elapsed >= FADE_DURATION_MS) {
    for (uint8_t channel = 0; channel < 3; ++channel) {
      currentRgb[channel] = targetRgb[channel];
    }
    fading = false;
  } else {
    for (uint8_t channel = 0; channel < 3; ++channel) {
      const int difference = (int)targetRgb[channel] - (int)fadeFromRgb[channel];
      currentRgb[channel] = fadeFromRgb[channel] +
          (int32_t)difference * (int32_t)elapsed / (int32_t)FADE_DURATION_MS;
    }
  }
  writeRgbToAllGroups(currentRgb);
}

void setup() {
  DmxSimple.usePin(DMX_PIN);
  DmxSimple.maxChannel(START_CHANNEL + RGB_GROUPS * 3 - 1);
  Serial.begin(SERIAL_BAUD);
  writeRgbToAllGroups(currentRgb);
  Serial.println("READY");
}

void loop() {
  readSerialLines();
  updateFade();
}
