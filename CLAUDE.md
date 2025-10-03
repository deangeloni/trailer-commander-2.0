# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a MicroPython IoT application for Moovalot trailer tracking and security. The system runs on Digi XBee Cellular modules and manages:
- Real-time GPS tracking with dynamic reporting intervals
- Remote lock/unlock control via MQTT
- Security alarms triggered by toolbox opening, movement, or corral exit
- I2C sensor monitoring (voltage, current, power, temperature)
- Maintenance mode and rental status management
- Cellular connectivity with automatic reconnection

## Architecture

### Core Components

**main.py** - Main application entry and event loop
- Initializes cellular connection and MQTT client
- Runs Main_Routine() which contains the primary event loop
- Handles GPIO state changes (lock, plug, toolbox)
- Dynamic reporting frequency based on speed/state
- Manages alarm logic with timeout and deactivation
- Publishes telemetry to MQTT broker at `mqtt.moovalot.com:8883`

**boot.py** - Boot initialization
- Enables Digi cloud console for remote debugging

**lib/mqtt.py** - Custom MQTT client (modified micropython-lib)
- TLS/SSL support configurable
- Publishes device telemetry to topic: `moovalot/trailer/{phone_number}`
- Subscribes to command topic for remote control
- Connection resilience with reconnection logic

**lib/gps.py** - GPS data acquisition via UART
- Parses NMEA sentences (GNRMC, GNGGA)
- Calculates distance traveled and speed
- Validates GPS fix quality using HDOP and satellite count
- Converts coordinates and computes distances for geofencing

**lib/i2c.py** - I2C sensor interface
- Reads INA219 power monitor (voltage, current, power)
- Reads MCP9808 temperature sensor
- Located at I2C addresses 0x40 and 0x18

### State Management

The application maintains several global state variables:
- `LOCK_STATUS`: Current hitch lock state (LOCKED/UNLOCKED)
- `RENT_STATUS`: Whether trailer is rented (disables alarms)
- `ALARM_STATUS`: Alarm active state
- `MAINTENANCE_MODE`: Disables alarms for service work
- `CORAL_*`: Geofence location data (lat, lon, radius, name)
- `GONOW`: Forces immediate telemetry transmission

### MQTT Command Protocol

Commands arrive on topic `moovalot/trailer/{phone_number}` with format `TCMD:{command}:{data}`

Key commands:
- `TCMD:LOCK` / `TCMD:UNLOCK` - Control hitch lock
- `TCMD:MTC:1` / `TCMD:MTC:0` - Enable/disable maintenance mode
- `TCMD:RENTED` / `TCMD:NOTRENTED` - Set rental status
- `TCMD:CORAL:{name}|{lat}|{lon}|{radius}|{address}` - Update geofence
- `TCMD:ALARM` - Manual alarm trigger
- `TCMD:REBOOT` / `TCMD:SHUTDOWN` - Device control
- `TCMD:UPDATE` / `TCMD:STATUS` - Force status update

### Alarm Logic

Alarms activate when:
1. Toolbox opened (90s duration)
2. Plugged into vehicle while not rented (30s duration)
3. Trailer moves while not rented
4. Trailer exits corral (geofence) while not rented (90s duration)

Alarms are suppressed during:
- `MAINTENANCE_MODE = True`
- `RENT_STATUS = True`
- Startup routine (first 45 seconds)

### GPIO Pin Assignments

- D0: Toolbox trigger (input, pull-up)
- D2: Lock notice (input, pull-up)
- D3: Lock relay (output)
- D5: Plugged hot wire detect (input, pull-down)
- D7: Unlock relay (output)
- D9: Siren (output)
- D10: Cooling fan (output)

## Development Commands

This is an embedded MicroPython project for Digi XBee Cellular modules. There is no standard build system.

**Compile to bytecode:**
```bash
python -m mpy_cross main.py
python -m mpy_cross boot.py
python -m mpy_cross lib/mqtt.py
python -m mpy_cross lib/gps.py
python -m mpy_cross lib/i2c.py
```

**Deploy to device:**
Files must be uploaded to the XBee module via:
- Digi XBee MicroPython PyCharm plugin
- XCTU utility
- Direct file transfer over USB/serial

## Key Design Patterns

**Dynamic Reporting**: Telemetry frequency adjusts based on speed:
- >65 mph: 15s interval
- 35-65 mph: 20s interval
- 15-35 mph: 20s interval
- 5-15 mph: 30s interval
- <5 mph: 90s interval
- Plugged in: Maximum frequency (100 mph equivalent)

**GPS Quality Validation**: Uses HDOP and satellite count thresholds:
- STRONG: HDOP < 1.0, sats > 10
- FAIR: HDOP < 2, sats > 6
- Moderate: HDOP < 8, sats > 3

**Memory Management**: Explicit `gc.collect()` calls throughout to manage limited RAM on embedded device.

**Connection Resilience**: `check_connection()` function attempts MQTT reconnection up to 12 times with exponential backoff.

## Important Constraints

- MicroPython subset of Python 3.4
- Limited to ~64KB RAM
- No standard library - uses micropython-lib modules
- Blocking operations must be minimized
- UART GPS reads timeout after 10 seconds
- Main loop runs every 1 second checking for events

## TODO List

### Lock Mechanism Improvements
- [ ] Verify LOCK_NOTICE state after lock/unlock commands
- [ ] Implement retry logic if lock fails to engage (2-3 attempts)
- [ ] Send alert/alarm if lock fails after retries
- [ ] Return actual success/failure status from lock_trailer() function

### Data Cleanup
- [ ] Remove dead "motion" field (hardcoded to "0")
- [ ] Remove redundant "online" field (always 1)
- [ ] Remove or update "error_last_msg" field (never updated during runtime)
- [ ] Fix typo: "memory_pct " → "memory_pct" (trailing space)
- [ ] Evaluate if "command": "status" is needed in telemetry payloads