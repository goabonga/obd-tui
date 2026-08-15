# Usage

## Command line

```bash
obd-tui [--port DEVICE] [--version]
```

| Option | Effect |
| --- | --- |
| `--port DEVICE` | Open `DEVICE` instead of scanning, e.g. `--port /dev/ttyUSB0`. |
| `--demo` | Run against a simulated vehicle, with no adapter. |
| `--version` | Print the version and exit. |
| `--help` | Print the usage summary and exit. |

The module form works too, which is handy from a checkout:

```bash
python -m obd_tui
```

`--port` and `--demo` are mutually exclusive: demo mode opens no port at
all.

## Demo mode

```bash
obd-tui --demo
```

The dashboard connects to a vehicle that exists only in memory. Its
readings move the way a real one's would — RPM oscillating around idle,
coolant and oil warming up, throttle and pedal sweeping together — and it
reports a MIL, two stored trouble codes and one pending code, so every
panel has something to show.

Nothing is opened, written or scanned. Use it to try the interface, to
demonstrate it, or to regenerate the screenshots in this documentation:

```bash
uv run python scripts/screenshots.py
```

## Adapter detection

Without `--port`, every serial port the system reports is examined and the
first one that looks like an OBD-II adapter is used. A port matches when
either:

- its USB vendor/product pair is a known adapter — currently the FTDI
  `0403:6015` pair used by the vLinker family, which otherwise advertises a
  generic serial-bridge descriptor; or
- its product, manufacturer or description string contains `obd`, `elm327`,
  `obdlink`, `stn11`, `vlinker` or `vgate`, case-insensitively.

A Bluetooth adapter bound to `/dev/rfcomm0` usually exposes no USB ids and
no descriptor, so pass it explicitly:

```bash
obd-tui --port /dev/rfcomm0
```

`--port` always wins. When the scan happens to recognise that same port,
its USB ids are kept for the status bar.

## Key bindings

| Key | Action |
| --- | --- |
| `c` | Connect: scan, open the adapter, discover the supported commands. |
| `d` | Disconnect: stop polling and forget the readings. |
| `1` | Engine panel. |
| `2` | Air panel. |
| `3` | EGR panel. |
| `4` | Diagnostics panel. |
| `5` | Faults panel. |
| `p` | Supported PID catalogue. |
| `q` | Quit. |

Panel shortcuts do nothing while disconnected, and the tabs themselves are
disabled, so there is no way to land on a panel that has nothing to show.

## Status bar

The line above the key hints reads:

```
CONNECTED  |  /dev/ttyUSB0  |  0403:6015
```

— the connection state, the port in use, and the adapter's USB
vendor:product ids (`-:-` for an adapter that exposes none). The state is
one of `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `NO DEVICE` (no adapter
was found) or `FAILED` (the port refused to open).

## Reading the panels

Only what the vehicle answered is displayed. A command the ECU does not
support never appears — no empty row, no placeholder — and a section whose
readings are all missing does not print its heading either. A panel with
nothing at all to show says so.

When a sweep drops an answer, the previous value stays on screen rather
than blanking: adapters lose the occasional frame, and a flickering
dashboard is harder to read than a slightly stale one.
