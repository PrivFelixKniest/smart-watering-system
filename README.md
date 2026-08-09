# Smart Watering System

A self-contained garden irrigation controller for a Raspberry Pi Zero 2 W.
A Python service runs a watering schedule, skips runs when rain is forecast,
logs all activity to SQLite, and exposes a small web dashboard on your local
WiFi so you can check status, view history, and enable/disable the system
from a phone or laptop at home.

No cloud, no subscription, no port forwarding. The only outbound internet
dependency is the free Open-Meteo weather API (no API key required).

---

## Table of contents

1. [Overview](#1-overview)
2. [Hardware parts list](#2-hardware-parts-list)
3. [Wiring](#3-wiring)
4. [Headless Pi OS setup](#4-headless-pi-os-setup)
5. [Software install](#5-software-install)
6. [Configuration reference](#6-configuration-reference)
7. [Running via systemd](#7-running-via-systemd)
8. [Web UI access](#8-web-ui-access)
9. [Watering logic](#9-watering-logic)
10. [Development on Windows (mock hardware)](#10-development-on-windows-mock-hardware)
11. [Database](#11-database)
12. [Safety notes](#12-safety-notes)

---

## 1. Overview

| Component         | Choice                                             |
| ----------------- | -------------------------------------------------- |
| Controller        | Raspberry Pi Zero 2 W                              |
| OS                | Raspberry Pi OS Lite (64-bit, Bookworm)            |
| Language          | Python 3.11                                        |
| Web framework     | FastAPI + Uvicorn                                  |
| Scheduling        | APScheduler (AsyncIOScheduler)                     |
| Weather data      | Open-Meteo (free, no API key)                      |
| Storage            | SQLite (file-based, via stdlib `sqlite3`)          |
| GPIO library      | gpiozero                                           |
| Deployment         | Python venv + systemd service (no Docker)         |
| Network access    | Local WiFi only via mDNS (`smart-watering.local`)  |

The system is **multi-zone capable** but typically starts with a single valve.
Adding a zone means wiring another relay channel and adding an entry to
`config.yaml` — no code changes required.

---

## 2. Hardware parts list

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

## 3. Wiring

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
                          │  12V DC circuit:              │
                          │  12V PSU (+) → relay COM       │
                          │  relay NO → solenoid (+)       │
                          │  solenoid (-) → 12V PSU (-)    │
                          │  flyback diode across solenoid │
                          └───────────────────────────────┘
```

- The Pi drives only the relay input (3.3 V logic level); the Pi never touches
  the 12 V circuit.
- The relay opto-isolator keeps the Pi electrically separate from the solenoid.
- The **flyback diode** is important: solenoids are inductive and can arc the
  relay contacts on disconnect without one. Cathode (stripe) to +12 V side.
- The GPIO pin is configurable in `config.yaml` — the example above uses BCM 17.

---

## 4. Headless Pi OS setup

You do not need a keyboard or monitor on the Pi.

1. **Flash the OS**
   - Download **Raspberry Pi Imager** (<https://www.raspberrypi.com/software/>).
   - Choose **Raspberry Pi OS Lite (64-bit)** (Bookworm).
   - Select your microSD card and click the **gear icon** before writing to
     preconfigure:
     - **Hostname:** `smart-watering`
     - **Enable SSH:** *use password authentication*
     - **Set username and password:** e.g. `pi` / a strong password
     - **Configure wireless LAN:** enter your home WiFi SSID + password and
       pick the correct country code
   - Write the card.

2. **Boot the Pi**
   - Insert the microSD, power on. After ~1–2 minutes it should join your WiFi.
   - From a computer on the same network, test connectivity:
     ```sh
     ssh pi@smart-watering.local
     ```
   - If mDNS does not resolve, find the Pi's IP in your router's DHCP list and
     `ssh pi@<ip>`.

3. **Update the system**
   ```sh
   sudo apt update && sudo apt full-upgrade -y
   ```

4. **Optionally set a static IP** in your router's DHCP reservations for the
   Pi's MAC address so the address is stable.

---

## 5. Software install

Run these on the Pi over SSH. Assumes Debian/Bookworm (Pi OS Lite).

1. **Install system packages**
   ```sh
   sudo apt install -y python3 python3-venv python3-pip git
   ```

2. **Clone the repository** (or copy the code over via `scp`)
   ```sh
   cd ~
   git clone https://github.com/<you>/smart-watering-system.git
   cd smart-watering-system
   ```

3. **Create a virtualenv and install the app**
   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -e .
   ```

4. **Create your config file**
   ```sh
   cp config.example.yaml config.yaml
   nano config.yaml
   ```
   Edit at least `location.lat`, `location.lon`, and your `zones`. See the
   [configuration reference](#6-configuration-reference) below.

5. **Allow binding port 80 as a non-root user** (preferred over running the
   service as root):
   ```sh
   sudo setcap 'cap_net_bind_service=+ep' $(readlink -f $(which python3))
   ```
   Or, if you prefer, leave Uvicorn on a high port (e.g. 8080) and skip this.

---

## 6. Configuration reference

All runtime settings live in `config.yaml` (copied from `config.example.yaml`).
The file is intentionally simple — flat YAML, no templating.

```yaml
# Coordinates for the Open-Meteo API. Use decimal degrees.
location:
  lat: 52.5200
  lon: 13.4050

# Skip a scheduled run if forecast precipitation in the next 12 hours
# exceeds this value (in millimeters). Set to 0 to disable rain skipping.
rain_threshold_mm: 2.0

# Master port for the web server.
web_port: 80

# Timezone for schedule interpretation (IANA name).
timezone: "Europe/Berlin"

# One entry per valve/zone. Add more by duplicating the block.
zones:
  - name: "Garden bed"
    gpio_pin: 17          # BCM pin number (gpiozero convention)
    active_high: true      # true = relay energizes on HIGH; false for active-low boards
    schedule_time: "06:00" # 24h local time, daily
    duration_seconds: 300  # how long the valve opens each scheduled run
  # - name: "Greenhouse"
  #   gpio_pin: 18
  #   active_high: true
  #   schedule_time: "07:00"
  #   duration_seconds: 180
```

### Field reference

| Field              | Scope | Description                                                            |
| ------------------ | ----- | --------------------------------------------------------------------- |
| `location.lat`     | global | Latitude for weather lookup.                                          |
| `location.lon`     | global | Longitude for weather lookup.                                         |
| `rain_threshold_mm` | global | Forecast precipitation over the next 12h that triggers a skip. 0 = off. |
| `web_port`         | global | TCP port for Uvicorn. Defaults to 80.                                 |
| `timezone`         | global | IANA timezone name for schedule interpretation.                       |
| `zones[].name`     | per zone | Human-readable label shown in the UI.                              |
| `zones[].gpio_pin` | per zone | BCM GPIO pin driving the relay input.                              |
| `zones[].active_high` | per zone | `true` if relay energizes on HIGH. Most 5V relay modules: `true`. |
| `zones[].schedule_time` | per zone | Local time `HH:MM`, daily.                                       |
| `zones[].duration_seconds` | per zone | Valve open duration per scheduled run.                           |

---

## 7. Running via systemd

A systemd unit runs the app as the `pi` user, restarts on crash, and starts on
boot.

1. **Install the service file**
   ```sh
   sudo cp systemd/smart-watering.service /etc/systemd/system/
   sudo systemctl daemon-reload
   ```

2. **Edit the file** if your install path differs from
   `/home/pi/smart-watering-system`. Adjust the `WorkingDirectory=` and
   `ExecStart=` paths accordingly.

3. **Enable and start**
   ```sh
   sudo systemctl enable --now smart-watering
   ```

4. **Check status and logs**
   ```sh
   systemctl status smart-watering
   journalctl -u smart-watering -f   # live follow
   ```

5. **Restart after config edits**
   ```sh
   sudo systemctl restart smart-watering
   ```

The service expects the virtualenv at `./.venv` inside the project directory.
If you named it differently, update `ExecStart=` in the unit file.

---

## 8. Web UI access

Once the service is running, open from any device on the same WiFi:

```
http://smart-watering.local
```

If mDNS doesn't resolve, use the Pi's IP directly, e.g. `http://192.168.1.42`.

### Endpoints

| Method | Path                       | Purpose                                             |
| ------ | -------------------------- | --------------------------------------------------- |
| GET    | `/`                        | HTML dashboard (status, history, controls).          |
| GET    | `/api/state`               | JSON: enabled flag, per-zone status, next runs.      |
| GET    | `/api/events?limit=100`    | JSON event history (most recent first).               |
| POST   | `/api/enable`              | Master switch on — resumes scheduled watering.       |
| POST   | `/api/disable`             | Master switch off — pauses all scheduled watering.   |
| POST   | `/api/zone/{id}/water`     | Manually water a zone now (logs `MANUAL` event).      |

All POST endpoints accept a regular browser form post, so the dashboard works
without JavaScript. JSON bodies are also accepted.

### Dashboard features

- Master on/off switch with current state.
- Per-zone card: next scheduled run, last event, **Water now** button.
- Last 20 events table (auto-refreshes via `<meta http-equiv="refresh">`).
- No external CSS/JS — small inline stylesheet, fast on the Zero's CPU.

---

## 9. Watering logic

For each zone, an APScheduler job fires daily at `schedule_time` (local time
per `timezone`). The run proceeds as follows:

1. If the master switch is **disabled**, do nothing (no log entry).
2. Query Open-Meteo for the next 12 hours of forecast precipitation at
   `location`.
3. If forecast rain ≥ `rain_threshold_mm`:
   - Skip the run.
   - Log `SKIPPED_RAIN` event with the forecast amount.
4. Otherwise:
   - Open the valve (energize the relay) for `duration_seconds`.
   - Log `WATERED` event with the duration and trigger `SCHEDULE`.
5. A nightly `HEARTBEAT` job at 00:05 logs a row so you can tell the service
   is alive even on dry days.

Manual triggers via the web UI open the valve immediately for the configured
`duration_seconds` and log a `MANUAL` event. They are allowed even when the
master switch is disabled (you're overriding yourself).

The Open-Meteo endpoint used:
```
https://api.open-meteo.com/v1/forecast
  ?latitude=<lat>
  &longitude=<lon>
  &hourly=precipitation
  &forecast_days=2
```
No API key is required. The service caches the forecast for 10 minutes to
avoid redundant calls.

---

## 10. Development on Windows (mock hardware)

You can develop and test the web UI, scheduler logic, and weather client on a
Windows machine without any Pi hardware. A mock `ValveController` is used when
the `MOCK_HARDWARE` environment variable is set.

```powershell
# from the repo root, in PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .

$env:MOCK_HARDWARE = "1"
uvicorn app.main:app --reload --port 8080
```

Open <http://localhost:8080>. The dashboard works exactly as on the Pi; valve
operations are logged to the console instead of actuating a relay. The SQLite
database is created at `./data/events.db` (or a path you set with the
`DB_PATH` env var).

To simulate a scheduled run without waiting until 06:00, either temporarily
set a zone's `schedule_time` to a few minutes in the future, or use the
**Water now** button on the dashboard.

---

## 11. Database

Storage is SQLite, file-based (default `./data/events.db`). Schema:

```sql
CREATE TABLE events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,  -- ISO-8601 UTC
    zone              TEXT,               -- zone name, NULL for system-wide
    event_type        TEXT    NOT NULL,  -- see below
    duration_seconds  INTEGER,           -- valve open duration, if applicable
    trigger           TEXT,               -- SCHEDULE | MANUAL | SYSTEM
    details           TEXT                -- JSON blob with extra context
);

CREATE INDEX idx_events_timestamp ON events(timestamp);
CREATE INDEX idx_events_zone ON events(zone);
```

### Event types

| event_type      | When it's logged                                            |
| --------------- | ------------------------------------------------------------ |
| `WATERED`       | A scheduled (or manual) watering completed normally.        |
| `SKIPPED_RAIN`  | A scheduled run was skipped due to forecast rain.          |
| `MANUAL`        | The **Water now** button was used.                          |
| `ENABLED`       | Master switch turned on.                                    |
| `DISABLED`      | Master switch turned off.                                   |
| `HEARTBEAT`     | Nightly 00:05 health check (system alive).                  |
| `ERROR`         | Something failed during a run (valve fault, API error…).   |

You can inspect the database directly:

```sh
sqlite3 data/events.db "SELECT timestamp, zone, event_type, duration_seconds FROM events ORDER BY id DESC LIMIT 20;"
```

---

## 12. Safety notes

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
- **WiFi credentials.** Stored in `wpa_supplicant.conf` on the Pi only; never
  committed to this repo. Likewise keep `config.yaml` (it may contain your
  lat/lon) out of version control — `.gitignore` excludes it.

---

## License

TBD — choose an OSI-approved license before distributing.
