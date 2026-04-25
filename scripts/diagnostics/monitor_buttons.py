#!/usr/bin/env python3
"""Simple button monitor - shows which GPIO is pressed"""

import time
import os

# Button GPIOs and their physical pins
BUTTONS = {
    229: "Pin 11",
    230: "Pin 12",
    231: "Pin 13",
    232: "Pin 15"
}

def setup_button(gpio):
    try:
        if not os.path.exists(f"/sys/class/gpio/gpio{gpio}"):
            with open(f"/sys/class/gpio/export", "w") as f:
                f.write(str(gpio))
            time.sleep(0.1)
        with open(f"/sys/class/gpio/gpio{gpio}/direction", "w") as f:
            f.write("in")
        return True
    except:
        return False

def read_button(gpio):
    try:
        with open(f"/sys/class/gpio/gpio{gpio}/value", "r") as f:
            return int(f.read().strip())
    except:
        return 1

print("BUTTON MONITOR - Press buttons to see which GPIO triggers")
print("="*60)
print("You said RED button is on pins 9,11,12")
print("Pin 9 is GND, so RED is on Pin 11 or 12\n")

# Setup buttons
for gpio in BUTTONS:
    if setup_button(gpio):
        print(f"✅ GPIO {gpio} ({BUTTONS[gpio]}) ready")

print("\nPress your buttons! (Ctrl+C to exit)\n")

# Monitor buttons
states = {gpio: 1 for gpio in BUTTONS}
button_colors = {}

try:
    while True:
        for gpio, pin_name in BUTTONS.items():
            current = read_button(gpio)

            # Button pressed (0 = pressed)
            if current == 0 and states[gpio] == 1:
                print(f"🔴 PRESSED: {pin_name} (GPIO {gpio})")

                # Ask for color first time
                if gpio not in button_colors:
                    print(f"   ➡️  What color is this button?")

            # Button released
            elif current == 1 and states[gpio] == 0:
                print(f"   Released: {pin_name}")

            states[gpio] = current

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\n\nExiting...")