# Smart Watering System

A self-contained garden irrigation controller for a Raspberry Pi Zero 2 W, 3, 4 or better.
A Python service runs a watering schedule, skips runs when rain is forecast,
and exposes a small web dashboard on your local WiFi so you can check status,
view history, and enable/disable the system from a phone or laptop at home.

No cloud, no subscription, no port forwarding.

---

## Table of contents

1. [Hardware parts list](#hardware-parts-list)
2. [Wiring](#wiring)
3. [Safety notes](#safety-notes)

---

## Hardware parts list

| Part                                   | Notes                                                                 |
| -------------------------------------- | --------------------------------------------------------------------- |
| Raspberry Pi Zero 2 W                  | With header soldered (or use a pHAT / jumper wires).                   |
| microSD card, 8 GB+                    | Class 10 / A1.                                                        |
| 5V USB power supply + micro-USB cable  | For the Pi. Use a stable 2.5 A supply.                                |
| 1-channel 5V relay module (opto-isolated) | Active-low or active-high; configured in software.                |
| 12V DC solenoid valve                  | Irrigation-rated. Match port size to your tubing.                     |
| 12V DC power supply                    | Separate from the Pi. Current rating ≥ solenoid draw (often ~0.3–0.5 A). |
| 1N4007 flyback diode                   | Solder across the solenoid (cathode to +) to protect the relay contacts. |
| Jumper wires (F-F)                     | Pi → relay `IN`, `VCC`, `GND`.                                        |
| Irrigation tubing + barbed fittings    | As needed for your setup.                                             |

---

## Wiring

```
Raspberry Pi Zero 2 W                Relay module
┌──────────────┐                    ┌──────────────┐
│  GPIO 17  ───┼────────────────────┤ IN            │
│  5V       ───┼────────────────────┤ VCC           │
│  GND      ───┼────────────────────┤ GND           │
└──────────────┘                    └──────────────┘
                                       │  COM / NO contacts
                                       ▼
                      ┌───────────────────────────────┐
                      │  12V DC circuit:               │
                      │  12V PSU (+) → relay COM        │
                      │  relay NO → solenoid (+)        │
                      │  solenoid (-) → 12V PSU (-)     │
                      │  flyback diode across solenoid  │
                      └───────────────────────────────┘
```

- The Pi drives only the relay input (3.3 V logic level); the Pi never touches
  the 12 V circuit.
- The relay opto-isolator keeps the Pi electrically separate from the solenoid.
- The **flyback diode** is important: solenoids are inductive and can arc the
  relay contacts on disconnect without one. Cathode (stripe) to +12 V side.
- The GPIO pin is configurable in software — the example above uses BCM 17.

---

## Safety notes

- **Separate power rails.** The 12 V solenoid circuit must never share the
  Pi's 5 V rail. Use the relay's opto-isolated input only.
- **Flyback diode.** Always fit a 1N4007 (or similar) reverse-biased across
  the solenoid to absorb the inductive spike when the valve closes. Without
  it the relay contacts will eventually pit or weld.
- **No mains voltage.** This design assumes low-voltage DC only. Do not wire
  mains-powered pumps or valves through this relay without a qualified
  electrician and appropriate isolation.
- **Water and electricity.** House the Pi, relay, and 12 V PSU in a dry,
  weatherproof enclosure. Only the valve and tubing go outside.
- **Fail-safe.** The valve is **normally closed** — if the Pi crashes or loses
  power, the valve closes and watering simply stops (no flooding). Confirm
  your solenoid is NC (most irrigation ones are).
- **Power budget.** The Pi Zero 2 W's USB input should be a stable 2.5 A
  supply; a weak charger can brown out when WiFi transmits.

---
