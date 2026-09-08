# Architecture

The package is layered so that everything except the outermost layer can be
tested without a terminal and without a vehicle.

```
obd_tui/
├── cli.py            argument parsing, process entry point
├── config.py         user settings, read from a TOML file
├── logs.py           routing log records to the interface, not the terminal
├── app.py            Textual application: tabs, key bindings, workers
├── services/         talking to the adapter and the vehicle
│   ├── detection.py    find the serial port of an adapter
│   ├── connection.py   open the link, query commands, discover capabilities
│   ├── diesel_monitoring.py  the aftertreatment in one view, derived rows
│   ├── polling.py      one sweep of the sensors into a state snapshot
│   ├── recording.py    append each sweep to a JSON Lines file
│   ├── simulation.py   a vehicle that only exists in memory
│   └── session.py      the connection lifecycle the dashboard renders
├── obd/              capabilities: what to ask, resolved per vehicle
│   ├── standard.py     SAE/ISO PIDs past the end of python-obd's table
│   ├── uds.py          proprietary identifiers, declared with provenance
│   ├── manufacturers/  one profile per make, tables per engine
│   └── registry.py     standard first, then the manufacturer
├── models/           plain data: adapter, command catalogue, vehicle state,
│                     reading history, exhaust bank, particulate filter
└── views/            turning readings into text
    ├── format.py       one reading into one string
    ├── units.py        metric or imperial display of a metric reading
    ├── gauges.py       block-character bars
    ├── panel.py        assembling the lines of a panel
    └── panels/         the seven panels and their registry
```

Dependencies point inwards: `views` and `services` both know `models`,
`services` never imports `views`, and only `app.py` knows Textual exists.

## Session: the whole model

`Session` owns the connection state machine, the adapter it is bound to,
the discovered catalogue and the latest readings. It is everything the
dashboard draws and it knows nothing about the UI, so the lifecycle -
connect, discover, poll, disconnect - is exercised in tests with a fake
connection and no terminal at all.

States are `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `NO_DEVICE`, `FAILED`
and `LOST`. Only `CONNECTED` polls. `LOST` is a disconnect that keeps the
last readings on screen, because what the vehicle was doing when it went
quiet is the interesting part.

Beside the state sits one flag, `held`: set by `disconnect`, cleared by
`connect`. The state says whether the link is up; the flag says whether
the user wants it down, which the state alone cannot tell, since
`DISCONNECTED` is also where every session starts. `wants_link` combines
the two into the one question a reconnect policy has to ask.

## Failures degrade, they do not propagate

python-obd raises freely: a port that vanished, a clone adapter that stops
replying, a protocol it fails to negotiate. `ObdConnection` turns each of
those into "no answer" - a `None` reading, an empty catalogue, a failed
open - so a flaky adapter degrades the dashboard instead of taking it down.

The same idea runs through the rendering: a missing reading is dropped
rather than shown as a placeholder, so a panel always reflects what the ECU
really answered.

## Capabilities, not commands

The poller, the state and the views ask for a capability - `EGT_BANK_1`,
what the dashboard wants to know - never for the bytes that fetch it. The
`obd` package turns one into the other, per vehicle, in a fixed order:

```
SAE/ISO PID the vehicle vouches for?
        ↓ yes                      ↓ no
  standard command       manufacturer profile has one?
                                   ↓ yes            ↓ no
                          manufacturer command   not available
```

python-obd's mode 01 table stops at PID `0x5F`, and its capability scan
stops with it. The standard registry declares the PIDs beyond in the
library's own terms, an `OBDCommand` with a decoder, and sends them
forced, since python-obd would otherwise refuse a command its scan never
found:

| Capability | PID | Reading |
| --- | --- | --- |
| `EGT_BANK_1`, `EGT_BANK_2` | `0x78`, `0x79` | Exhaust gas temperatures, four sensors per bank |
| `DPF_DIFFERENTIAL_PRESSURE` | `0x7A` | Particulate filter differential, inlet and outlet pressures |
| `DPF_TEMP_INLET`, `DPF_TEMP_OUTLET` | `0x7C` | Particulate filter inlet and outlet temperatures, one frame for both |
| `DPF_TEMP_INTERNAL` | none | Manufacturer only |
| `DPF_REGEN_STATUS` | `0x8B` | Regeneration status and normalised trigger |
| `DPF_SOOT_LOAD` | none | Manufacturer only |

Two capabilities may share one command - the filter's inlet and outlet
come in the one frame of PID `0x7C` - and a sweep asks the adapter once
for it, handing the same answer to both: the connection remembers every
answer for the length of a sweep. Each is still a capability of its own,
so that a manufacturer can answer either alone, as a bare number, and
the internal temperature only that way.

Discovery covers them the way the ECU does: it asks for the supported-PID
bitmaps of their blocks, PIDs `0x60` and `0x80`, and a standard command
only ever answers a capability whose bit is set.

The manufacturer registry is where a make is allowed to appear, and the
only place. Discovery reads the VIN and matches it against the profiles,
the generic one last since it claims everything; a profile answers the
capabilities its manufacturer exposes some non-standard way, and is asked
only after the standard has come up empty. A profile is bound to the
engine the user declared, and answers from tables keyed by engine code:
each entry is a `DataIdentifier`, a UDS service `0x22` reading declared
with the engines it was seen on, how far to trust it and where that
comes from, whose decoder refuses a negative response, another
identifier or a payload of the wrong length. An engine with no table
gets the standard and no more. Suzuki is recognised; its tables are
empty until an identifier can be cited. Nothing outside the package
tests a make.

The profile also knows what only a wiring diagram can say: which exhaust
gas sensor, if any, sits at the particulate filter's inlet or outlet.
The generic profile places none, so an exhaust sensor never passes for a
filter temperature by assumption from its number.

Discovery settles the answer for every capability once, on connect, and
the catalogue lists each under its own name whichever command serves it.
A capability neither registry can answer on this vehicle is never sent.

A bank answers several sensors at once and a vehicle may have several
banks, so the banks are one family in the state - a mapping by bank
number - rather than a field per sensor. Every bank command feeds that
one field, each adding its own member to what the sweep holds, and the
exhaust panel draws whatever is there. The decoded bank is a plain model
of its own, indexed by sensor, with no knowledge of python-obd.

## The aftertreatment in one view

After each sweep, a monitoring service completes the snapshot with what
the profile can add - exhaust sensors standing in for filter temperatures
the ECU did not report, a regeneration guessed from a hot filter at
moderate load when the ECU reports none - and builds one view from the
capabilities alone: the readings as they came, and beside them what
follows. Restriction per unit of air flow, inlet-to-outlet delta, a
descriptive state for the pressure that says `elevated` or
`inconsistent` and never `clogged`, and the time since a regeneration
was seen to end, which is why the service is an object with a clock.

Every stand-in and every guess is flagged, and the panel words it as one;
an estimate never replaces what the ECU said. The service never sends a
command and never tests a make: what a profile knows about an engine is
asked of the profile.

## Adapter work runs off the event loop

Connecting probes the protocol for seconds; a sweep queries dozens of PIDs;
clearing the codes waits on the ECU. Any of them would freeze a Textual
application if it ran on the event loop, so all three run on worker threads
in one exclusive group - exclusive because a serial link cannot serve a
connect and a poll at once - and hand their result back to the UI thread
when done.

## Panels are a registry, not a switch

Each panel is a function of the readings and the catalogue. A single
registry holds their order, titles and shortcuts; the application builds
tabs, key bindings and content widgets from that one list, so adding a
panel is one entry rather than edits in three parallel places.

## Discovery drives polling

On connect, the vehicle is asked which commands it supports. The poller
queries only those, at one of three cadences, promoting whatever the open
panel displays to every sweep. When discovery comes back empty - an adapter
that will not report its capabilities - it falls back to querying
everything, which is slower but still works.

Five supported commands going unanswered in a row is taken as a lost link
rather than dropped frames: the sweep is abandoned and the session moves to
`LINK LOST`, keeping the last readings on screen.

## Two timers, one running

The application owns a poll timer and a retry timer, and every transition -
a connect answering, a sweep ending, the user hanging up - settles them
from the session's state in one place: polling while the link is up,
retrying while it is down and wanted, neither once the user has hung up.
The retry timer is also paused for the length of a connect attempt, since
a second open landing on the serial link mid-probe helps nothing.

## A state is a snapshot, a history is a series

`VehicleState` is frozen. A sweep builds a new one from the previous one
and the session rebinds it in a single assignment, because the sweep runs
on a worker thread while the UI renders on another - one rebind is atomic,
forty field assignments are not.

The rolling history of the charted readings lives beside the state rather
than inside it, for the same reason: a state describes one sweep, a history
spans many.
