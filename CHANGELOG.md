# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/) and this project
adheres to [Semantic Versioning](https://semver.org/). New entries are
generated from [Conventional Commits](https://www.conventionalcommits.org/)
by [multicz](https://github.com/goabonga/multicz).

## [0.5.1] - 2026-09-10

### Fixed

- **app**: pause polling while the codes are cleared (`566709a`)

## [0.5.0] - 2026-09-08

### Added

- **models**: decode a bank of exhaust gas temperatures (`99b7c7f`)
- **services**: declare the EGT bank 1 command for python-obd (`deae898`)
- **services**: query the custom commands through the connection (`46f97af`)
- **services**: discover the custom commands through PID 0x60 (`7d11f49`)
- **models**: hold the four EGT sensors of bank 1 in the state (`cb8f589`)
- read and show the exhaust gas temperatures of bank 1 (`632add1`)
- **views**: point out an EGT sensor far from the rest of its bank (`294bb67`)
- **simulation**: answer the EGT bank and vouch for it (`39e90ae`)
- **obd**: resolve a capability through standard then manufacturer registries (`f408e7d`)
- **services**: resolve each capability for the connected vehicle (`690a65d`)
- **models**: hold the exhaust banks in the state by number (`cdef893`)
- read and show every exhaust bank as one family (`3ffad14`)
- **obd**: read exhaust bank 2 through PID 0x79 (`5a7a479`)
- **models**: decode the particulate filter pressures of PID 0x7A (`9515054`)
- read and show the particulate filter pressure (`b31734b`)
- **models**: decode the particulate filter temperatures of PID 0x7C (`a3e2536`)
- read and show the particulate filter temperatures (`bef73aa`)
- **models**: hold the particulate filter's soot load (`3496f84`)
- read and show the soot load a manufacturer exposes (`a708fb4`)
- **obd**: vouch for PIDs 0x81 to 0xA0 through the second bitmap (`aa49a42`)
- **models**: decode the regeneration status of PID 0x8B (`0973688`)
- read and show the particulate filter regeneration (`727f947`)
- sum the diesel aftertreatment up in one view (`fbf92ef`)
- **obd**: declare proprietary data identifiers with their provenance (`a4fd253`)
- **obd**: bind a manufacturer profile to the engine it serves (`0dcd886`)
- **config**: declare the vehicle's engine for its manufacturer profile (`e5d9a3e`)
- **session**: switch the engine on a live link (`91c78a1`)
- **obd**: let a profile list the engines it has a table for (`dde584e`)
- **app**: choose the engine from the dashboard (`009ef47`)
- **session**: remember the VIN discovery read (`fd75aae`)
- build a dated report of the whole session (`0d5d8f3`)
- **config**: choose where reports are saved (`d27a185`)
- **app**: save a dated report with r (`5ee071a`)

### Fixed

- **app**: a retry landing after a disconnect no longer lifts the hold (`1f1106e`)

## [0.4.0] - 2026-09-02

### Added

- **cli**: connect on start when a port is given (`f1cc5bf`)
- **session**: hold the link down after a deliberate disconnect (`e919640`)
- **app**: retry a down link every few seconds (`5873be4`)
- **config**: make the reconnect interval a setting (`7ffe987`)

## [0.3.8] - 2026-09-01

### Fixed

- **views**: show log messages as notifications, not over the screen (`5a3ace1`)

## [0.3.7] - 2026-09-01

### Fixed

- stop treating a silent vehicle as a broken link (`f22b27c`)
- serialise every conversation with the adapter (`8396def`)

## [0.3.6] - 2026-08-16

### Fixed

- bind the package to the interpreter its venv was built with (`a719acf`)

## [0.3.5] - 2026-08-16

### Fixed

- **build**: make the package architecture independent (`1ad5838`)

## [0.3.4] - 2026-08-16

### Fixed

- build the virtualenv with python3 -m venv (`5bb54ca`)

## [0.3.3] - 2026-08-16

### Fixed

- **ci**: stop lintian judging the target series (`8866005`)

## [0.3.2] - 2026-08-16

### Fixed

- **ci**: publish for the supported LTS releases (`2472c22`)

## [0.3.1] - 2026-08-15

### Fixed

- **ci**: ship the upstream tarball with every series (`860a997`)
- **ci**: build a reproducible upstream tarball (`fa1a376`)

## [0.3.0] - 2026-08-15

### Added

- **views**: show the version in the header (`6f83255`)

## [0.2.2] - 2026-08-15

### Fixed

- **deps**: lower the platformdirs floor to what the code needs (`f162d31`)

## [0.2.1] - 2026-08-15

### Fixed

- **views**: scroll panels that do not fit the window (`3456ae9`)

## [0.2.0] - 2026-08-15

### Added

- **services**: add simulated connection backend (`fac79ec`)
- **cli**: add --demo flag (`a8e9ad4`)
- **models**: add bounded reading history (`5c6c0e1`)
- **views**: render sparklines in engine panel (`ce014d6`)
- **cli**: add --record session logging (`8aa23f3`)
- **services**: tiered polling frequencies (`623c5f9`)
- **services**: prioritize active panel fields (`5f4236f`)
- **services**: abort sweep and drop session on link loss (`6f5338a`)
- **services**: support clearing stored DTCs (`a70e995`)
- **views**: confirm-and-clear action on faults panel (`2cbdcf4`)
- **config**: load user configuration file (`660a087`)
- **views**: imperial unit support (`2797f91`)
- **services**: detect rfcomm bluetooth nodes (`64429dd`)

### Performance

- **services**: cache connection liveness per sweep (`d2e7d1f`)

## [0.1.0] - 2026-08-13

### Added

- add adapter, command catalog and vehicle state models (`eeb7e59`)
- detect the serial port of an OBD-II adapter (`fdefcd1`)
- add the vehicle connection and capability discovery service (`cff195c`)
- poll the vehicle sensors into a state snapshot (`8435a28`)
- orchestrate the connection lifecycle in a session (`43d2896`)
- add the panel text building blocks (`56624bc`)
- add the six dashboard panels (`3de5e5f`)
- add the Textual dashboard and its command line entry point (`7ad6031`)
