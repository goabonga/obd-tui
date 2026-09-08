# Compatibility

What `obd-tui` reads, on which vehicles, and how far to trust it. The
standard PIDs are the same on every vehicle that supports them; the
proprietary identifiers are per manufacturer and per engine, and each is
listed with its provenance.

## Status

| Status | Meaning |
| --- | --- |
| `validated` | Read on a vehicle and checked against a workshop tool. |
| `experimental` | Decoder follows a published layout; not yet checked on a vehicle by this project. |
| `reverse-engineered` | Worked out from traffic, with the formula guessed to fit. |
| `planned` | Nothing declared yet; the capability exists, the reading does not. |

## Standard readings

Declared by `obd-tui` past the end of python-obd's table, from SAE J1979
and J1979-DA. A vehicle is asked for one only when it names the PID in
its supported-PID bitmap.

| Capability | PID | Status | Note |
| --- | --- | --- | --- |
| `EGT_BANK_1` | `0x78` | experimental | Bitmap of fitted sensors, four 16-bit temperatures. |
| `EGT_BANK_2` | `0x79` | experimental | Same layout, bank 2. |
| `DPF_DIFFERENTIAL_PRESSURE` | `0x7A` | experimental | Differential signed around -327.68 kPa; inlet and outlet unsigned. |
| `DPF_TEMP_INLET`, `DPF_TEMP_OUTLET` | `0x7C` | experimental | One frame for both; bank 1 only, bank 2 left aside. |
| `DPF_TEMP_INTERNAL` | none | planned | No standard slot. Manufacturer only. |
| `DPF_REGEN_STATUS` | `0x8B` | experimental | J1979-DA diesel aftertreatment status; bit layout to be checked on a vehicle. |
| `DPF_SOOT_LOAD` | none | planned | No standard PID. Manufacturer only. |

## Manufacturers

A manufacturer is recognised from the first three characters of the VIN.
Its profile is bound to the engine declared with `--engine`, and answers
only from a table for that engine, only for what the standard could not
answer.

| Manufacturer | Engine | Capability | Status | Source |
| --- | --- | --- | --- | --- |
| Suzuki | D16AA | `DPF_SOOT_LOAD` | planned | No identifier read on a vehicle, none in a source this project can cite. |
| Suzuki | D16AA | `DPF_REGEN_STATUS` | planned | Standard PID `0x8B` first, if the ECU names it. |
| Suzuki | D16AA | `DPF_DIFFERENTIAL_PRESSURE` | planned | Standard PID `0x7A` first, if the ECU names it. |
| Suzuki | D16AA | exhaust sensor placement | planned | Which sensor is the filter's inlet is for a wiring diagram to say. |

Suzuki is recognised under the identifiers `JS2`, `JS3`, `JSA`, `TSM` and
`MA3`. Its tables are empty on purpose: a guessed identifier decodes to
a number that looks like a reading, and that is worse than nothing.

## Declaring a proprietary reading

An entry is one `DataIdentifier` in the profile's engine table, and it
must carry:

- service and identifier - service `0x22`, the two-byte identifier;
- the expected payload length, which the decoder refuses to bend;
- the byte order, unit and formula, spelt out;
- the ECU and the engines it was seen on - it is sent to no other;
- the status above, and the source it comes from.

A reply to another identifier, a negative response or a payload of the
wrong length is read as no answer. Add the entry, its test against a
captured reply, and its line in the table above, in the same change.
