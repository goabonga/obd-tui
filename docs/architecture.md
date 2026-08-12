# Architecture

The package is layered so that everything except the outermost layer can be
tested without a terminal and without a vehicle.

```
obd_tui/
├── cli.py            argument parsing, process entry point
├── app.py            Textual application: tabs, key bindings, workers
├── services/         talking to the adapter and the vehicle
│   ├── detection.py    find the serial port of an adapter
│   ├── connection.py   open the link, query commands, discover capabilities
│   ├── polling.py      one sweep of the sensors into a state snapshot
│   └── session.py      the connection lifecycle the dashboard renders
├── models/           plain data: adapter, command catalogue, vehicle state
└── views/            turning readings into text
    ├── format.py       one reading into one string
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

States are `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `NO_DEVICE` and
`FAILED`. Only `CONNECTED` polls.

## Failures degrade, they do not propagate

python-obd raises freely: a port that vanished, a clone adapter that stops
replying, a protocol it fails to negotiate. `ObdConnection` turns each of
those into "no answer" — a `None` reading, an empty catalogue, a failed
open — so a flaky adapter degrades the dashboard instead of taking it down.

The same idea runs through the rendering: a missing reading is dropped
rather than shown as a placeholder, so a panel always reflects what the ECU
really answered.

## Adapter work runs off the event loop

Connecting probes the protocol for seconds; a sweep queries dozens of PIDs.
Either would freeze a Textual application if it ran on the event loop, so
both run on exclusive worker threads — exclusive because a serial link
cannot serve a connect and a poll at once — and hand their result back to
the UI thread when done.

## Panels are a registry, not a switch

Each panel is a function of the readings and the catalogue. A single
registry holds their order, titles and shortcuts; the application builds
tabs, key bindings and content widgets from that one list, so adding a
panel is one entry rather than edits in three parallel places.

## Discovery drives polling

On connect, the vehicle is asked which commands it supports. The poller
queries only those. When discovery comes back empty — an adapter that will
not report its capabilities — it falls back to querying everything, which
is slower but still works.
