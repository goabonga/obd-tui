# Usage

## Command line

```bash
obd-tui [--port DEVICE | --demo] [--units SYSTEM] [--poll-interval SECONDS]
        [--config FILE] [--record FILE] [--version]
```

| Option | Effect |
| --- | --- |
| `--port DEVICE` | Open `DEVICE` instead of scanning, e.g. `--port /dev/ttyUSB0`. |
| `--demo` | Run against a simulated vehicle, with no adapter. |
| `--units SYSTEM` | `metric` or `imperial`. |
| `--poll-interval SECONDS` | Seconds between two sweeps. |
| `--config FILE` | Configuration file to read. |
| `--record FILE` | Append every sweep to `FILE` as JSON Lines. |
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

## Recording a drive

```bash
obd-tui --record ~/drives/2026-08-15.jsonl
```

Every sweep appends one JSON object to the file, stamped in UTC and
carrying every reading — including the ones the vehicle did not answer,
which stay `null` so each line has the same keys and the file loads as a
table. Derived readings such as `net_boost` are written too.

```json
{"time":"2026-08-15T10:30:00+00:00","rpm":880.4,"coolant_temp":90.9,"speed":60.0,"stored_codes":[{"code":"P0401","description":"..."}],"net_boost":17.2}
```

Lines are flushed as they are written, so a session that ends with a pulled
plug keeps everything up to the last sweep. Reconnecting appends to the
same file rather than truncating it.

Reading one back:

```bash
jq -r '[.time, .rpm, .coolant_temp] | @tsv' drive.jsonl
python -c "import pandas; print(pandas.read_json('drive.jsonl', lines=True).describe())"
```

`--record` combines with `--demo`, which is a quick way to produce a sample
file without a vehicle.

## Configuration file

Settings that would otherwise be retyped on every run live in a TOML file:

```toml
# ~/.config/obd-tui/config.toml
port = "/dev/rfcomm0"
units = "imperial"
poll_interval = 0.5
```

The exact location follows the platform's convention — `~/.config/obd-tui/`
on Linux, `~/Library/Application Support/obd-tui/` on macOS,
`%LOCALAPPDATA%\obd-tui\` on Windows. `obd-tui --help` prints the one in
use, and `--config FILE` reads another.

Precedence is command line, then file, then defaults: `--units metric`
overrides a file asking for imperial, and settings the command line does
not mention keep their configured value.

Nothing here can stop the dashboard from starting. A missing file is the
normal case; a malformed one, an unknown key or a value of the wrong type
is reported to the log and then ignored.

## Units

Readings are shown in metric by default and in US customary units with
`--units imperial`: °F, mph, psi, miles and gallons per hour.

Only the display changes. A vehicle reports metric by standard, so that is
what is stored, charted and written to a recording — a file recorded in
imperial mode holds the same numbers as one recorded in metric. Gauges are
drawn from those source values too, so a bar reads the same either way.

## Adapter detection

Without `--port`, every serial port the system reports is examined and the
first one that looks like an OBD-II adapter is used. A port matches when
either:

- its USB vendor/product pair is a known adapter — currently the FTDI
  `0403:6015` pair used by the vLinker family, which otherwise advertises a
  generic serial-bridge descriptor; or
- its product, manufacturer or description string contains `obd`, `elm327`,
  `obdlink`, `stn11`, `vlinker` or `vgate`, case-insensitively.

If no USB port matches, bound Bluetooth RFCOMM nodes are tried next. Such a
node carries neither USB ids nor descriptor strings, so there is nothing to
recognise it by — but binding one is a deliberate act, so it is taken at
face value. The lowest-numbered node wins.

`--port` always wins over both passes. When the scan happens to recognise
that same port, its USB ids are kept for the status bar.

Only Bluetooth Classic adapters (Serial Port Profile) reach the system this
way. A Bluetooth Low Energy dongle — most of the cheap ones sold as "OBD2
BLE 4.0" — exposes no serial profile, creates no node, and cannot be used.

### Binding a Bluetooth adapter

```bash
bluetoothctl scan on                    # note the adapter's MAC address
bluetoothctl pair 00:11:22:33:44:55     # PIN is usually 1234 or 0000
bluetoothctl trust 00:11:22:33:44:55    # reconnect without an agent
sudo rfcomm bind 0 00:11:22:33:44:55    # creates /dev/rfcomm0
```

`bind` only creates the node; the radio link is established when something
opens it, so binding an adapter that is powered off costs nothing. The flip
side is that a bound node whose adapter is absent still looks like an
adapter to the scan: `obd-tui` will pick it and report `FAILED` rather than
`NO DEVICE`.

### Keeping the binding across reboots

`rfcomm bind` does not survive a restart. A one-shot unit re-runs it at
boot, once the Bluetooth stack is up:

```ini
# /etc/systemd/system/rfcomm-obd.service
[Unit]
Description=Bind the OBD-II adapter to /dev/rfcomm0
Requires=bluetooth.service
After=bluetooth.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/rfcomm bind 0 00:11:22:33:44:55
ExecStop=/usr/bin/rfcomm release 0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now rfcomm-obd.service
```

`Type=oneshot` with `RemainAfterExit=yes` because `rfcomm bind` returns as
soon as the node exists; without it systemd would treat the service as dead
and never run `ExecStop`. The adapter has to be trusted, not merely paired,
or the connection will ask for an agent that a boot-time service does not
have.

The `rfcomm` tool is deprecated in BlueZ. It still ships with it (5.79 at
the time of writing), but some distributions move it to a separate
"deprecated tools" package.

### Permissions

Check who may open the node:

```bash
ls -l /dev/rfcomm0
```

If its group is one you belong to — `dialout` on most distributions — there
is nothing to do. If not, a udev rule settles it for every RFCOMM node
rather than for one device path:

```
# /etc/udev/rules.d/99-rfcomm.rules
KERNEL=="rfcomm[0-9]*", SUBSYSTEM=="tty", GROUP="dialout", MODE="0660"
```

```bash
sudo udevadm control --reload-rules
sudo usermod -aG dialout "$USER"   # log out and back in
```

## Publishing to the PPA

Each release uploads a source package per series to
`ppa:goabonga/obd-tui`, and Launchpad builds the binaries. The same upload
can be run on demand from the Actions tab — *ci* → *Run workflow* → tick
*Upload the current version to the PPA* — which is what a first
publication, a newly added series or a rejected upload needs.

Only a release that bumps the version publishes on its own: multicz judges
a commit by the files it touches, so a change to the packaging or the
pipeline itself never triggers one. That is what the manual run is for.

Re-running for a version whose first series already went through needs
*Leave the upstream tarball out* ticked as well — the archive keeps one
copy per upstream version and refuses a second. Launchpad also refuses a
series it already holds at that version, so a re-run publishes the series
that failed and rejects the rest by mail, which is harmless.

Locally, the same packages are produced by:

```bash
scripts/build-deb.sh                       # every configured series
scripts/build-deb.sh noble                 # just one
dput ppa:goabonga/obd-tui ../build-area/obd-tui_*_source.changes
```

All the series go up in one `dput` run on purpose: Launchpad's anonymous
FTP endpoint has accepted the first upload of a session and refused the
next one with a `550` every time they were sent separately. If that ever
stops working, the authenticated alternative is sftp — register an SSH key
on the Launchpad account and point dput at
`method = sftp`, `login = <launchpad-user>`.

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
| `x` | Clear the stored trouble codes (faults panel only). |
| `q` | Quit. |
| `↑` `↓` | Scroll the open panel a line at a time. |
| `PgUp` `PgDn` | Scroll it a screen at a time. |
| `Home` `End` | Jump to the top or the bottom of it. |

Panel shortcuts do nothing while disconnected, and the tabs themselves are
disabled, so there is no way to land on a panel that has nothing to show.

## Small terminals

A panel taller than the window scrolls, with a scrollbar on its right and
the mouse wheel, the arrow keys, `PgUp`/`PgDn` and `Home`/`End` all moving
it. The scrollbar appears only when there is something to scroll to. The
header, the status bar and the key hints stay put, so the readings never
disappear behind them.

The PID catalogue is a few hundred lines on most vehicles and scrolls at
any window size.

## Clearing the trouble codes

On the faults panel, `x` sends mode 04 after a confirmation dialog. It is
offered only while connected and only on that panel; elsewhere the key is
greyed out in the footer.

Clearing does more than empty the list on screen. Mode 04 also erases the
freeze frame data and resets the readiness monitors, which the vehicle then
has to re-run over several drive cycles — a car cleared just before an
emissions test will fail it for "monitors not ready". A fault that is still
present comes straight back: the codes are re-read immediately after the
clear, so the panel shows what the vehicle actually kept.

## Status bar

The line above the key hints reads:

```
CONNECTED  |  /dev/ttyUSB0  |  0403:6015
```

— the connection state, the port in use, and the adapter's USB
vendor:product ids (`-:-` for an adapter that exposes none). The state is
one of `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `NO DEVICE` (no adapter
was found), `FAILED` (the port refused to open) or `LINK LOST`.

`LINK LOST` means the vehicle stopped answering commands it had declared
supported — five in a row, which is a cable rather than a dropped frame.
Polling stops and the last readings stay on screen, since they are what the
vehicle was doing when it went quiet. Press `c` to reconnect.

## How often each reading is taken

An adapter answers a few dozen commands a second at best, so a sweep does
not ask for everything every time:

| Cadence | Readings |
| --- | --- |
| Every sweep | Engine speed, vehicle speed, load, throttle, MAF, manifold pressure, pedal. |
| Every 5th sweep | Temperatures, pressures, fuel trims and the rest. |
| Every 60th sweep | Trouble codes, status word, mode 09 vehicle info, counters. |

Whatever the open panel shows is promoted to every sweep: sit on the
diagnostics panel and its counters update every second; leave it and they
fall back to once a minute. The first sweep after connecting reads
everything, so the dashboard fills at once.

## Reading the panels

Only what the vehicle answered is displayed. A command the ECU does not
support never appears — no empty row, no placeholder — and a section whose
readings are all missing does not print its heading either. A panel with
nothing at all to show says so.

When a sweep drops an answer, the previous value stays on screen rather
than blanking: adapters lose the occasional frame, and a flickering
dashboard is harder to read than a slightly stale one.
