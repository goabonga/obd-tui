# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/) and this project
adheres to [Semantic Versioning](https://semver.org/). New entries are
generated from [Conventional Commits](https://www.conventionalcommits.org/)
by [multicz](https://github.com/goabonga/multicz).

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
