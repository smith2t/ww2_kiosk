# Orange Pi Zero 2W Wiring Guide for WW2 Kiosk

## 🔌 GPIO Pin Mapping (Following Standard Raspberry Pi BCM Convention)

This configuration follows the standard Raspberry Pi pinout recommendations for maximum compatibility with existing documentation and projects.

### **Button Connections (Lower Pins Layout)**

| Button | BCM Pin | Orange Pi GPIO | Physical Pin | Wire Connection |
|--------|---------|----------------|--------------|-----------------|
| Button 1 | BCM 17 | GPIO 229 | Pin 11 | Connect to GND |
| Button 2 | BCM 18 | GPIO 230 | Pin 12 | Connect to GND |
| Button 3 | BCM 27 | GPIO 231 | Pin 13 | Connect to GND |
| Button 4 | BCM 22 | GPIO 232 | Pin 15 | Connect to GND |

### **LED Connections (Lower Pins Layout)**

| LED | BCM Pin | Orange Pi GPIO | Physical Pin | Wire Connection |
|-----|---------|----------------|--------------|-----------------|
| LED 1 | BCM 23 | GPIO 78  | Pin 16 | Connect to LED+ (with resistor) |
| LED 2 | BCM 24 | GPIO 226 | Pin 18 | Connect to LED+ (with resistor) |
| LED 3 | BCM 25 | GPIO 227 | Pin 22 | Connect to LED+ (with resistor) |
| LED 4 | BCM 8  | GPIO 228 | Pin 24 | Connect to LED+ (with resistor) |

## 🔧 Wiring Instructions

### **Button Wiring**
1. Connect one terminal of each button to the corresponding GPIO pin (pins 11, 12, 13, 15)
2. Connect the other terminal of each button to any GND pin (pins 6, 9, 14, 20, 25, 30, 34, 39)
3. The software uses internal pull-up resistors, so no external resistors needed
4. Button press = connecting GPIO to GND (active LOW)

### **LED Wiring**
1. Connect LED positive (longer leg) to GPIO pin through a 220Ω-330Ω current limiting resistor (pins 16, 18, 22, 24)
2. Connect LED negative (shorter leg) to GND
3. LEDs will light up when GPIO pin is HIGH (3.3V)

## 📊 Orange Pi Zero 2W 40-Pin Header Layout

```
                    Orange Pi Zero 2W GPIO Header
                         (View from top)

     3.3V  [ 1] [  2]  5V
   GPIO 2  [ 3] [  4]  5V
   GPIO 3  [ 5] [  6]  GND
   GPIO 4  [ 7] [  8]  GPIO 14
      GND  [ 9] [ 10]  GPIO 15
▶GPIO 229  [11] [ 12]  GPIO 230▶ (Button 2)
▶GPIO 231  [13] [ 14]  GND
▶GPIO 232  [15] [ 16]  GPIO 78 ◀ (LED 1)
     3.3V  [17] [ 18]  GPIO 226◀ (LED 2)
  GPIO 10  [19] [ 20]  GND
   GPIO 9  [21] [ 22]  GPIO 227◀ (LED 3)
  GPIO 11  [23] [ 24]  GPIO 228◀ (LED 4)
      GND  [25] [ 26]  GPIO 7
   GPIO 0  [27] [ 28]  GPIO 1
   GPIO 5  [29] [ 30]  GND
   GPIO ?  [31] [ 32]  GPIO ?
   GPIO ?  [33] [ 34]  GND
   GPIO ?  [35] [ 36]  GPIO ?
   GPIO ?  [37] [ 38]  GPIO ?
      GND  [39] [ 40]  GPIO ?

▶ = Button pins (11,12,13,15)   ◀ = LED pins (16,18,22,24)
```

## ⚡ Power Requirements

- **Buttons**: No external power required (use internal pull-ups)
- **LEDs**: Each LED draws ~10-20mA at 3.3V through resistor
- **Total GPIO current**: Orange Pi can safely source ~50mA total across all GPIO pins

## 🛠️ Component Requirements

### **For Buttons:**
- 4x Momentary push buttons (normally open)
- Jumper wires (male-to-male for breadboard, male-to-female for direct connection)

### **For LEDs:**
- 4x LEDs (any color, 3mm or 5mm)
- 4x Current limiting resistors (220Ω to 330Ω)
- Jumper wires

### **Optional:**
- Breadboard for prototyping
- Header pins (if not pre-soldered on Orange Pi)

## 📝 Configuration File

The pin configuration is stored in `config/config.yaml`:

```yaml
display:
  led1_pin: 78   # GPIO 78 (Physical pin 16, BCM 23 equivalent)
  led2_pin: 226  # GPIO 226 (Physical pin 18, BCM 24 equivalent)
  led3_pin: 227  # GPIO 227 (Physical pin 22, BCM 25 equivalent)
  led4_pin: 228  # GPIO 228 (Physical pin 24, BCM 8 equivalent)

input:
  button1_pin: 229  # GPIO 229 (Physical pin 11, BCM 17 equivalent)
  button2_pin: 230  # GPIO 230 (Physical pin 12, BCM 18 equivalent)
  button3_pin: 231  # GPIO 231 (Physical pin 13, BCM 27 equivalent)
  button4_pin: 232  # GPIO 232 (Physical pin 15, BCM 22 equivalent)
```

## 🧪 Testing

Test your wiring with:
```bash
python3 test_buttons.py
```

This will verify all GPIO pins are working correctly before running the full kiosk application.

## 📚 Compatibility Notes

- This mapping follows standard Raspberry Pi BCM pin recommendations
- Compatible with most Raspberry Pi GPIO documentation and tutorials
- Physical pin numbers match Raspberry Pi 40-pin header layout
- Orange Pi GPIO numbers are mapped to equivalent BCM functionality