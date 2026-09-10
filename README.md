# Smart Watering System

A self-contained garden irrigation controller for a Raspberry Pi Zero 2 W, 3, 4 or better. A Python service decides when
to water based on live weather data and recent watering history, and exposes a small web dashboard on your local WiFi so
you can check status, view consumption, and manage profiles from a phone or laptop at home.

No cloud, no subscription, no port forwarding.

## Table of contents

1. [Hardware parts list](#hardware-parts-list)
2. [Wiring](#wiring)
3. [Example Hardware Configuration](#example-hardware-configuration)
4. [Safety notes](#safety-notes)
5. [Software](#software)
6. [Installation & setup](#installation--setup)
7. [Known Issues](#known-issues)

## Hardware parts list

| Part                                      | Notes                                                                    |
| ----------------------------------------- | ------------------------------------------------------------------------ |
| Raspberry Pi Zero 2 W                     | With header soldered (or use a pHAT / jumper wires).                     |
| microSD card, 8 GB+                       | Class 10 / A1.                                                           |
| 5V USB power supply + micro-USB cable     | For the Pi. Use a stable 2.5 A supply.                                   |
| 1-channel 5V relay module (opto-isolated) | Active-low or active-high; configured in software.                       |
| 12V DC solenoid valve                     | Irrigation-rated. Match port size to your tubing.                        |
| 12V DC power supply                       | Separate from the Pi. Current rating ≥ solenoid draw (often ~0.3–0.5 A). |
| 1N4007 flyback diode                      | Solder across the solenoid (cathode to +) to protect the relay contacts. |
| Jumper wires (F-F)                        | Pi → relay `IN`, `VCC`, `GND`.                                           |
| Irrigation tubing + barbed fittings       | As needed for your setup.                                                |

## Wiring

```
Raspberry Pi Zero 2 W                Relay module
┌──────────────┐                    ┌───────────────┐
│  GPIO 17  ───┼────────────────────┤ IN            │
│  5V/3,3V  ───┼────────────────────┤ VCC           │
│  GND      ───┼────────────────────┤ GND           │
└──────────────┘                    └───────────────┘
                                       │  COM / NO contacts
                                       ▼
                      ┌─────────────────────────────────┐
                      │  12V DC circuit:                │
                      │  12V PSU (+) → relay COM        │
                      │  relay NO → solenoid (+)        │
                      │  solenoid (-) → 12V PSU (-)     │
                      │  flyback diode across solenoid  │
                      └─────────────────────────────────┘
```

- The Pi drives only the relay input (3.3 V logic level); the Pi never touches the 12 V circuit. How much voltage the relay needs may depend on the exact relay.
- The relay opto-isolator keeps the Pi electrically separate from the solenoid.
- The **flyback diode** is important: solenoids are inductive and can arc the relay contacts on disconnect without one.
  Cathode (stripe) to +12 V side.
- The GPIO pin is configurable in software — the example above uses BCM 17.

## Example Hardware Configuration

### Shopping List

#### Parts

- Raspberry Pi 4 (1GB)
- Raspberry Pi 15W USB-C Power Supply
- Flyback Diode(s) 1N4007
- ZUOKENZU AC Adapter: 12V 2A Power Supply with +/- screw interface
- AZDelivery 5V Relay KF-301 "Low-Level-Trigger"
- EXLECO NC G3/4 inch Magnetventil

#### Wires and Miscellanious

- Female - Female Dupont Wires (at least 3) (Pi -> Relay)
- One thicker wire (Relay -> Valve -> 12V Power)
- Cable Lug Set & Crimping tool
- Electrical Tape
- 32GB Micro SD Card for the raspberry pi image
- (optional) Waterproof Housing for all components
- (optional) Cooling solution for the raspberry pi Chip

### Setup specific Notes

While creating the pi image, make sure to already connect wifi and enable pi connect for easy access to the system later on, especially once the system is wired up.

After creating the raspberry pi image and inserting it into the pi, clone this repository onto the pi and follow the instructions under [Software](#software) to install and start the application.

Follow the instructions under [Wiring](#wiring). For this relay, you will need to turn off the `VALVE_ACTIVE_HIGH=true` found in the `.env` file and connect the relay to the board using one of the 3.3V VCC connectors on the PI.

Think about solutions for housing the components safely close to water.
The housing for this specific setup was custom built by cutting two thin plastic bottles down the middle.
Then, putting the tape-isolated components inside one of the bottles and putting one bottle-bottom opening over the opening of the other bottle-bottom.
Cuts were made to relieve stress and let the cables run out of slim gaps between the bottles, while making sure that the housing is generally gap-less

Cooling for the pi should normally not be an issue, but if you want to avoid overheating you may add appropriate measures.

### Debugging

- To see if your setup is working, you may use the manual on and off button on the application. You should be able to hear the relay clicking with each press. The LED on the relay will show you whether is is currently opening or closing the 12V valve circuit.
- If the Relay is opening once on app startup and staying open the entire time until the app is killed and releasing the pin again, you may be passing too much voltage through the relay, try various combinations of setting the `VALVE_ACTIVE_HIGH=false` and wiring the relay to the 5V or 3.3V pin.

## Safety notes

- **Separate power rails.** The 12 V solenoid circuit must never share the Pi's 5 V rail. Use the relay's opto-isolated
  input only.
- **Flyback diode.** Always fit a 1N4007 (or similar) reverse-biased across the solenoid to absorb the inductive spike
  when the valve closes. Without it the relay contacts will eventually pit or weld.
- **No mains voltage.** This design assumes low-voltage DC only. Do not wire mains-powered pumps or valves through this
  relay without a qualified electrician and appropriate isolation.
- **Water and electricity.** House the Pi, relay, and 12 V PSU in a dry, weatherproof enclosure. Only the valve and
  tubing go outside.
- **Fail-safe.** The valve is **normally closed** — if the Pi crashes or loses power, the valve closes and watering
  simply stops (no flooding). Confirm your solenoid is NC (most irrigation ones are).
- **Power budget.** The Pi Zero 2 W's USB input should be a stable 2.5 A supply; a weak charger can brown out when WiFi
  transmits.

## Software

### Architecture at a glance

| Layer         | Choice                                               |
| ------------- | ---------------------------------------------------- |
| Language      | Python 3.10+                                         |
| Web framework | FastAPI                                              |
| Server        | Uvicorn / `fastapi` CLI                              |
| Frontend      | HTMX 2.0 + Jinja2 templates (no client JS framework) |
| Styling       | DaisyUI 5 + Tailwind CSS 4                           |
| ORM / DB      | SQLAlchemy 2.0 + SQLite (`app.db`)                   |
| Migrations    | Alembic                                              |
| HTTP client   | httpx (async) — weather & geocoding API calls        |
| Validation    | Pydantic v2 (API response models)                    |

### Project layout (under `app/`)

```
main.py                  FastAPI app entry point
database/models.py       SQLAlchemy ORM models + engine
alembic/                 Alembic env + migrations
clients/                 Async API clients (Open-Meteo forecast + geocoding)
service/                 Business logic (profiles, weather, water usage)
v1/                      HTMX/JSON API routers (weather, profiles, usage)
frontend/                Page router, Jinja2 templates, static assets
```

### Dependencies

Key runtime packages (see `app/requirements.txt` for the full pinned list):
`fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `httpx`, `jinja2`, `pydantic`,
`python-multipart`.

## Installation & setup

### Running in production (autostart on boot)

For a Raspberry Pi that's actually out watering your garden `scripts/install.sh`
automates the manual steps in [Manual & Dev Setup](#manual--dev-setup) and additionally registers the app as a
`systemd` service, so it starts automatically on every boot and restarts on its own if it ever crashes:

After cloning and entering this codebase in a terminal, run:

```sh
bash scripts/install.sh
```

This creates the virtual environment, installs the Python and GPIO dependencies, runs the database migrations, and
installs + enables a `smart-watering.service` unit running as whichever user invoked the script. It's safe to re-run
(e.g. after pulling changes that add a dependency) — it'll reuse the existing venv and just reinstall/restart the
service.

Once installed:

```sh
sudo systemctl status smart-watering     # is it running?
sudo journalctl -u smart-watering -f     # follow the logs
sudo systemctl restart smart-watering    # after editing app/.env, etc.
```

**This is for production deployments only.** For local development, follow the manual steps in
[Installation & setup](#installation--setup) instead — `install.sh` installs system packages via `apt`/`sudo` and a
systemd unit, neither of which you want on a dev machine.

---

### Manual & Dev Setup

#### Prerequisites

- Python 3.10 or newer

#### Steps

All commands are run from the `app/` directory, because imports and template paths are relative to it.

```sh
# Navigate to /app
cd app

# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
# .\venv\Scripts\Activate.ps1   # Windows PowerShell

# 2. Install dependencies
pip install -r requirements.txt

# 2.5 Raspberry Pi only: install a real GPIO backend for gpiozero.
# Without this, gpiozero falls back to its experimental NativeFactory, which
# can claim/release the pin correctly but won't reliably drive it on demand
# (the valve will look "stuck" — see the Wiring section above).
sudo apt update && sudo apt install swig liblgpio-dev -y
pip install lgpio

# 3. Create the database and apply migrations
alembic upgrade head

# 4. Configure the valve pin/polarity for your hardware
cp .env.example .env   # if app/.env doesn't already exist
# edit VALVE_GPIO_PIN and VALVE_ACTIVE_HIGH to match your wiring — see the
# "Wiring" and "Example Hardware Configuration" sections above for how to
# determine the right ACTIVE_HIGH value and debug relay behavior

# 5. Run the app
fastapi run main.py
# or: uvicorn main:app --reload
```

## Known Issues

- During development, it has been observed that the forecast api is often unstable, returning timeouts from time to time. This will result in error logs, but usually resolves itself after a few seconds.
  - Possible measures: Introduce local caching of past forecast data to use as a fallback, only updating the local forecast when a call was successful, which happens often enough.
