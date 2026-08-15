# obd-tui

`obd-tui` turns any ELM327-compatible OBD-II adapter into a live terminal
dashboard. It finds the adapter on the serial bus, asks the vehicle which
commands it actually supports, and streams the answers into a tabbed
[Textual](https://textual.textualize.io/) interface.

![The engine panel of obd-tui](assets/dashboard-engine.svg)

## Install

```bash
pip install obd-tui
```

Or run it without installing anything permanently:

```bash
uvx obd-tui
```

## Without a vehicle

```bash
obd-tui --demo
```

Demo mode drives the whole dashboard from a simulated vehicle — no
adapter, no car, no serial port. See [Usage](usage.md#demo-mode).

## Requirements

- Python 3.11 or newer.
- An ELM327-compatible adapter reachable as a serial port — a USB dongle
  such as the vLinker family, or a Bluetooth adapter bound to an RFCOMM
  node.
- Permission to read that port. On most Linux distributions this means
  belonging to the `dialout` group:

  ```bash
  sudo usermod -aG dialout "$USER"   # log out and back in
  ```

## First run

```bash
obd-tui
```

The dashboard starts disconnected and its tabs are disabled — there is
nothing to show until a vehicle answers. Press `c` to connect: `obd-tui`
scans the serial ports, opens the first adapter it recognises, and asks the
ECU for its capability list. From then on the panels refresh once a second.

Ignition must be on for the ECU to answer. With the engine off, most
vehicles reply to a handful of commands and leave the rest empty; the
panels simply omit what was never reported.

## Where to go next

- [Usage](usage.md) — command line options and key bindings.
- [Panels](panels.md) — what each tab shows.
- [Architecture](architecture.md) — how the pieces fit together.
- [Stability & deprecation](stability.md) — what the version numbers promise.
