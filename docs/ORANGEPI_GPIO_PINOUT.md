# OrangePi Zero 2W GPIO Pinout Reference

This document provides the GPIO pinout mapping for the OrangePi Zero 2W 40-pin header used in the WW2 Kiosk project.

## Physical Pin Layout (40-pin header)

```
     3.3V  (1) ◯ ◯ (2)  5V
GPIO65_SDA1  (3) ◯ ◯ (4)  5V
GPIO69_SCL1  (5) ◯ ◯ (6)  GND
   GPIO70    (7) ◯ ◯ (8)  GPIO71_UART0_TX
     GND     (9) ◯ ◯ (10) GPIO72_UART0_RX
   GPIO17   (11) ◯ ◯ (12) GPIO18
   GPIO27   (13) ◯ ◯ (14) GND
   GPIO22   (15) ◯ ◯ (16) GPIO23
     3.3V   (17) ◯ ◯ (18) GPIO24
GPIO19_MOSI (19) ◯ ◯ (20) GND
GPIO21_MISO (21) ◯ ◯ (22) GPIO25
GPIO11_SCLK (23) ◯ ◯ (24) GPIO8_CE0
     GND    (25) ◯ ◯ (26) GPIO7_CE1
   ID_SDA   (27) ◯ ◯ (28) ID_SCL
   GPIO5    (29) ◯ ◯ (30) GND
   GPIO6    (31) ◯ ◯ (32) GPIO12
   GPIO13   (33) ◯ ◯ (34) GND
   GPIO19   (35) ◯ ◯ (36) GPIO16
   GPIO26   (37) ◯ ◯ (38) GPIO20
     GND    (39) ◯ ◯ (40) GPIO21
```

## WW2 Kiosk GPIO Assignment

### Current Working Configuration (Tested Available GPIOs)

#### Button Inputs:
- **Button 1**: GPIO 65 (Physical Pin 3) - I2C1_SDA - *Available for GPIO*
- **Button 2**: GPIO 69 (Physical Pin 5) - I2C1_SCL - *Available for GPIO*
- **Button 3**: GPIO 70 (Physical Pin 7) - *Available for GPIO*
- **Button 4**: GPIO 71 (Physical Pin 8) - UART0_TX - *Available if UART not used*

#### LED Outputs:
- **LED 1**: GPIO 72 (Physical Pin 10) - UART0_RX - *Available if UART not used*
- **LED 2**: GPIO 73 - *If available*
- **LED 3**: GPIO 74 - *If available*
- **LED 4**: GPIO 75 - *If available*

### Physical Pin References (Standard Raspberry Pi Compatible)

If you have buttons connected to specific physical pins, here's the mapping:

- **Physical Pin 11** = GPIO 17 (Currently busy/reserved)
- **Physical Pin 12** = GPIO 18 (Currently busy/reserved)
- **Physical Pin 13** = GPIO 27 (Currently busy/reserved)
- **Physical Pin 15** = GPIO 22 (Currently busy/reserved)
- **Physical Pin 16** = GPIO 23 (Currently busy/reserved)

## Important Notes

1. **GPIO Availability**: GPIOs 17, 18, 22, 23, 27 appear to be reserved/busy on this OrangePi system
2. **I2C Pins**: GPIO 65 (SDA) and GPIO 69 (SCL) can be used as regular GPIO if I2C is not needed
3. **UART Pins**: GPIO 71 (TX) and GPIO 72 (RX) can be used as GPIO if serial console is not needed
4. **Allwinner Mapping**: OrangePi uses Allwinner H618 GPIO numbering, not BCM numbering

## Hardware Wiring Guide

### Button Connections (Pull-up configuration):
```
[Button] ──┐
           │
[GPIO Pin] ┼─── [10kΩ Resistor] ─── 3.3V
           │
         [GND]
```

### LED Connections:
```
[GPIO Pin] ─── [220Ω Resistor] ─── [LED Anode]
                                       │
                                   [LED Cathode] ─── GND
```

## Testing GPIO Availability

To test which GPIO pins are available on your system:

```bash
sudo python3 -c "
for pin in [65, 69, 70, 71, 72, 73, 74, 75]:
    try:
        with open('/sys/class/gpio/export', 'w') as f:
            f.write(str(pin))
        print(f'GPIO {pin}: Available')
        with open('/sys/class/gpio/unexport', 'w') as f:
            f.write(str(pin))
    except Exception as e:
        print(f'GPIO {pin}: {e}')
"
```

## Troubleshooting

### If GPIO pins show as "busy":
1. Check if they're being used by other services (UART, I2C, etc.)
2. Try different GPIO numbers from the available list
3. Update the configuration in `src/config/settings.py`

### Alternative GPIO pins to try:
- GPIO 5, 6, 12, 13, 16, 19, 20, 21, 26 (if not used by other functions)

## References

- OrangePi Zero 2W Official Documentation
- Allwinner H618 GPIO mapping
- Linux sysfs GPIO interface (/sys/class/gpio/)