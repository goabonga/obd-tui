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

On the supported LTS releases - 24.04 (noble) and 26.04 (resolute) - a
packaged build is published to a PPA:

```bash
sudo add-apt-repository ppa:goabonga/obd-tui
sudo apt install obd-tui
```

The package carries its Python dependencies in a self-contained virtual
environment under `/opt/venvs/obd-tui`, because two of them are missing
from the Ubuntu archive or too old there. It touches no system Python
packages.

Other releases are out of reach for two reasons. 22.04 and earlier ship
Python 3.10, and `obd-tui` needs 3.11. Interim releases go out of support
after nine months, and Launchpad refuses uploads for a series once it
does - so an Ubuntu that is itself unsupported cannot be served. On one of
those, install from PyPI instead:

```bash
uvx obd-tui        # or: pip install --user obd-tui
```

## Without a vehicle

```bash
obd-tui --demo
```

Demo mode drives the whole dashboard from a simulated vehicle - no
adapter, no car, no serial port. See [Usage](usage.md#demo-mode).

## Requirements

- Python 3.11 or newer.
- An ELM327-compatible adapter reachable as a serial port - a USB dongle
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

The dashboard starts disconnected and its tabs are disabled - there is
nothing to show until a vehicle answers. Press `c` to connect: `obd-tui`
scans the serial ports, opens the first adapter it recognises, and asks the
ECU for its capability list. From then on the panels refresh once a second.

Ignition must be on for the ECU to answer. With the engine off, most
vehicles reply to a handful of commands and leave the rest empty; the
panels simply omit what was never reported.

## Where to go next

- [Usage](usage.md) - command line options and key bindings.
- [Panels](panels.md) - what each tab shows.
- [Architecture](architecture.md) - how the pieces fit together.
- [Stability & deprecation](stability.md) - what the version numbers promise.
