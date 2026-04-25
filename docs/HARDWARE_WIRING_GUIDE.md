# WW2 Kiosk Hardware Wiring Guide
## OrangePi Zero 2W GPIO Configuration

### 🎯 **Your Hardware Layout**

Based on your setup with Button 1 using:
- **Physical Pin 11** (GPIO 17) - Button input
- **Physical Pin 12** (GPIO 18) - LED output

### ⚠️ **GPIO Availability Issue**

The standard Raspberry Pi GPIO pins (17, 18, 22, 23, 27) are currently reserved by the OrangePi system. We have **two solutions**:

---

## 🔧 **Solution A: Use Available GPIO Pins (Recommended)**

### Current Working Configuration:
```yaml
# Working GPIO pins that are available
input:
  button1_pin: 65   # Available GPIO
  button2_pin: 69   # Available GPIO
  button3_pin: 70   # Available GPIO
  button4_pin: 71   # Available GPIO

display:
  led1_pin: 72      # Available GPIO
  led2_pin: 73      # Available GPIO
  led3_pin: 74      # Available GPIO
  led4_pin: 75      # Available GPIO
```

### Hardware Wiring (Solution A):
```
Button Hardware:           OrangePi Connections:
┌─────────────────┐       ┌──────────────────────┐
│  [Button 1]     │  ──→  │ GPIO 65 (Available)  │
│  [LED 1]        │  ──→  │ GPIO 72 (Available)  │
│  [Button 2]     │  ──→  │ GPIO 69 (Available)  │
│  [LED 2]        │  ──→  │ GPIO 73 (Available)  │
│  [Button 3]     │  ──→  │ GPIO 70 (Available)  │
│  [LED 3]        │  ──→  │ GPIO 74 (Available)  │
│  [Button 4]     │  ──→  │ GPIO 71 (Available)  │
│  [LED 4]        │  ──→  │ GPIO 75 (Available)  │
│  [All GND]      │  ──→  │ GND Pins             │
└─────────────────┘       └──────────────────────┘
```

**✅ Pros:** Works immediately, no system changes needed
**❌ Cons:** Requires rewiring or jumper wires from your existing setup

---

## 🔧 **Solution B: Free Up Standard GPIO Pins**

### Free the Reserved GPIO Pins:

1. **Check what's using the pins:**
```bash
sudo lsof /dev/gpiochip*
sudo systemctl list-units | grep gpio
```

2. **Disable GPIO-related services (if any):**
```bash
# Common services that might reserve GPIO pins
sudo systemctl disable gpiod
sudo systemctl stop gpiod
```

3. **Add to `/boot/armbianEnv.txt` to free pins at boot:**
```bash
echo "param_gpio_pin_17=off" | sudo tee -a /boot/armbianEnv.txt
echo "param_gpio_pin_18=off" | sudo tee -a /boot/armbianEnv.txt
echo "param_gpio_pin_22=off" | sudo tee -a /boot/armbianEnv.txt
echo "param_gpio_pin_23=off" | sudo tee -a /boot/armbianEnv.txt
echo "param_gpio_pin_27=off" | sudo tee -a /boot/armbianEnv.txt
```

4. **Reboot and test:**
```bash
sudo reboot
```

### Your Original Hardware Wiring (Solution B):
```
Physical Pin Layout:        GPIO Mapping:
┌────────────────────┐     ┌──────────────────────┐
│ Pin 11 [Button 1]  │ ──→ │ GPIO 17              │
│ Pin 12 [LED 1]     │ ──→ │ GPIO 18              │
│ Pin 13 [Button 2]  │ ──→ │ GPIO 27              │
│ Pin 15 [Button 3]  │ ──→ │ GPIO 22              │
│ Pin 16 [Button 4]  │ ──→ │ GPIO 23              │
│ Pin 18 [LED 2]     │ ──→ │ GPIO 24              │
│ Pin 22 [LED 3]     │ ──→ │ GPIO 25              │
│ Pin 24 [LED 4]     │ ──→ │ GPIO 8               │
│ Pin 6,9,14,20,25   │ ──→ │ GND                  │
│ Pin 1,17           │ ──→ │ 3.3V                 │
└────────────────────┘     └──────────────────────┘
```

**✅ Pros:** Matches your existing hardware exactly
**❌ Cons:** Requires system configuration changes

---

## 🎮 **Button + LED Circuit Design**

### Individual Button/LED Module:
```
3.3V ──┬── [10kΩ Resistor] ── Button GPIO (Pull-up)
       │
       └── [Button] ── GND

LED GPIO ── [220Ω Resistor] ── [LED +] ── [LED -] ── GND
```

### Complete 4-Button Layout:
```
OrangePi Zero 2W
         ┌─────────────────────────────────────────┐
    3.3V │ 1  ● ● 2  │ 5V                          │
GPIO65   │ 3  ● ● 4  │ 5V     [Use Available      │
GPIO69   │ 5  ● ● 6  │ GND     GPIOs for now]     │
GPIO70   │ 7  ● ● 8  │ GPIO71                     │
     GND │ 9  ● ● 10 │ GPIO72                     │
GPIO17   │ 11 ● ● 12 │ GPIO18  [Your Original     │
GPIO27   │ 13 ● ● 14 │ GND      Hardware Layout]  │
GPIO22   │ 15 ● ● 16 │ GPIO23                     │
    3.3V │ 17 ● ● 18 │ GPIO24                     │
         │ ....... 40│                             │
         └─────────────────────────────────────────┘
```

---

## 🚀 **Quick Start Instructions**

### For Immediate Testing (Solution A):
1. Update wiring to use available GPIO pins (65, 69-75)
2. Current config already set for this
3. Run: `sudo python3 test_buttons.py`

### For Original Hardware (Solution B):
1. Run the GPIO freeing commands above
2. Update config to use original pins (17, 18, 22, 23, 27)
3. Reboot and test

---

## 🔧 **Configuration Files**

### Current Working Config (`config/config.yaml`):
```yaml
input:
  button1_pin: 65  # Working available GPIO
  button2_pin: 69  # Working available GPIO
  button3_pin: 70  # Working available GPIO
  button4_pin: 71  # Working available GPIO

display:
  led1_pin: 72     # Working available GPIO
  led2_pin: 73     # Working available GPIO
  led3_pin: 74     # Working available GPIO
  led4_pin: 75     # Working available GPIO
```

### Original Hardware Config:
```yaml
input:
  button1_pin: 17  # Physical pin 11
  button2_pin: 27  # Physical pin 13
  button3_pin: 22  # Physical pin 15
  button4_pin: 23  # Physical pin 16

display:
  led1_pin: 18     # Physical pin 12
  led2_pin: 24     # Physical pin 18
  led3_pin: 25     # Physical pin 22
  led4_pin: 8      # Physical pin 24
```

---

## 🎯 **Recommendation**

**Start with Solution A** (available GPIO pins) for immediate functionality, then optionally move to Solution B if you prefer to keep your existing wiring.

Both solutions are fully supported by the WW2 Kiosk software!