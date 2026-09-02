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
│   ├── polling.py      one sweep of the sensors into a state snapshot
│   ├── recording.py    append each sweep to a JSON Lines file
│   ├── simulation.py   a vehicle that only exists in memory
│   └── session.py      the connection lifecycle the dashboard renders
├── models/           plain data: adapter, command catalogue, vehicle state,
│                     reading history
└── views/            turning readings into text
    ├── format.py       one reading into one string
    ├── units.py        metric or imperial display of a metric reading
    ├── gauges.py       block-character bars
    ├── panel.py        assembling the lines of a panel
    └── panels/         the six panels and their registry
```

Dependencies point inwards: `views` and `services` both know `models`,
`services` never imports `views`, and only `app.py` knows Textual exists.

## Session: the whole model

`Session` owns the connection state machine, the adapter it is bound to,
the discovered catalogue and the latest readings. It is everything the
dashboard draws and it knows nothing about the UI, so the lifecycle —
connect, discover, poll, disconnect — is exercised in tests with a fake
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
those into "no answer" — a `None` reading, an empty catalogue, a failed
open — so a flaky adapter degrades the dashboard instead of taking it down.

The same idea runs through the rendering: a missing reading is dropped
rather than shown as a placeholder, so a panel always reflects what the ECU
really answered.

## Adapter work runs off the event loop

Connecting probes the protocol for seconds; a sweep queries dozens of PIDs;
clearing the codes waits on the ECU. Any of them would freeze a Textual
application if it ran on the event loop, so all three run on worker threads
in one exclusive group — exclusive because a serial link cannot serve a
connect and a poll at once — and hand their result back to the UI thread
when done.

## Panels are a registry, not a switch

Each panel is a function of the readings and the catalogue. A single
registry holds their order, titles and shortcuts; the application builds
tabs, key bindings and content widgets from that one list, so adding a
panel is one entry rather than edits in three parallel places.

## Discovery drives polling

On connect, the vehicle is asked which commands it supports. The poller
queries only those, at one of three cadences, promoting whatever the open
panel displays to every sweep. When discovery comes back empty — an adapter
that will not report its capabilities — it falls back to querying
everything, which is slower but still works.

Five supported commands going unanswered in a row is taken as a lost link
rather than dropped frames: the sweep is abandoned and the session moves to
`LINK LOST`, keeping the last readings on screen.

## A state is a snapshot, a history is a series

`VehicleState` is frozen. A sweep builds a new one from the previous one
and the session rebinds it in a single assignment, because the sweep runs
on a worker thread while the UI renders on another — one rebind is atomic,
forty field assignments are not.

The rolling history of the charted readings lives beside the state rather
than inside it, for the same reason: a state describes one sweep, a history
spans many.
