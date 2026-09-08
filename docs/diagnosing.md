# Diagnosing faults

The dashboard reads; the diagnosis is yours. This page is the method,
fault by fault - the exhaust gas temperature sensors, then the
particulate filter: what `obd-tui` can show about one, how to read it,
and what usually fixes it. Each section assumes the basics from
[Usage](usage.md): an adapter that connects, the PID catalogue (`p`) to
check what the vehicle answers, and `--record` to keep a drive for later.

Two habits pay off whatever the fault. Read the sensors with the engine
completely cold, ideally left overnight: every temperature should then sit
near ambient, and one that does not stands out. And record the first
drive after a repair, so the next time the code comes back there is a
healthy trace to compare against.

## Exhaust gas temperature sensors

### What the dashboard reads

The exhaust panel (`6`) reads mode 01 PIDs `0x78` and `0x79`, one per
bank, each answering the whole bank in one frame: a bitmap of the sensors
fitted, then four temperatures. `obd-tui` shows the fitted ones, up to
four per bank, upstream first: sensor 1 sits before the turbine on most
diesels, the last one past the particulate filter. Rows are named the way
a trouble code names a sensor - `B1S2` is bank 1 sensor 2.

python-obd's own table stops at PID `0x5F`, so these are declared by
`obd-tui` itself, and so is the supported-PID bitmap that covers them, PID
`0x60`. On connect the vehicle is asked for that bitmap; only a bank it
names there is ever asked for. The PID catalogue (`p`) lists `EGT_BANK_1`
and `EGT_BANK_2` as `[x]` or `[ ]` accordingly. Most four-cylinder
diesels have one bank; a V engine has two.

Both PIDs are optional in the standard. Diesels with a particulate filter
usually have the first, since the filter's regeneration is controlled
from those sensors; many petrol engines do not, and the panel then says
`No data reported by the vehicle`. A manufacturer that exposes the
temperatures some other way can fill in through its profile; the panel
reads the same either way.

A recording writes the banks as `egt_banks`, one list of four sensor
slots per bank number, `null` for a slot not fitted. The banks are read
every fifth sweep, and every sweep while the panel is open.

### The codes

The ECU raises one code per sensor and per failure, and the code names
both:

| Sensor | Circuit | Low | High |
| --- | --- | --- | --- |
| Bank 1 sensor 1 | `P0544` | `P0545` | `P0546` |
| Bank 1 sensor 2 | `P2031` | `P2032` | `P2033` |
| Bank 2 sensor 1 | `P0547` | `P0548` | `P0549` |
| Bank 2 sensor 2 | `P2034` | `P2035` | `P2036` |

*Low* and *high* describe the signal, not the exhaust: a sensor whose
circuit is shorted reads one end of the scale, and one whose circuit is
open reads the other. `P2033` - sensor circuit high, bank 1 sensor 2 - is
the ECU saying the second sensor reports a temperature it cannot believe.

### Reading the panel

1. Connect the adapter and switch the ignition on, engine off and
   completely cold.
2. Open the PID catalogue (`p`) and check that the bank the code names,
   `EGT_BANK_1` or `EGT_BANK_2`, is marked `[x]`. If it is not, the
   vehicle does not report that bank and there is nothing more to see
   here.
3. Open the exhaust panel (`6`). Cold, every sensor should read close to
   the ambient temperature shown on the engine panel:

    ```
    B1S1 °C           19.0
    B1S2 °C           18.0
    B1S3 °C           19.0
    ```

    A sensor whose circuit is open or shorted reads one end of the scale
    instead, and gets a note:

    ```
    B1S1 °C           19.0
    B1S2 °C         1000.0  ⚠ far from the other sensors
    B1S3 °C           18.0
    ```

4. Start the engine and watch the bank warm up. The sensors should climb
   together, the upstream one first and fastest; one that stays put, or
   stays pegged, is the one the code names.

The note is a hint for the eye, not a verdict. It marks a sensor sitting
more than 300 °C from the median of all the others, which under load a healthy
exhaust never does, and a failed circuit always does. With only two
sensors fitted it cannot tell which of the two is wrong - both get the
note, and the ambient temperature settles it.

### Remediation

A sensor that reads one end of the scale on a cold engine is almost
always the sensor or its wiring, not the exhaust:

- **Connector first.** Exhaust sensors live in heat and road spray; a
  corroded or loose connector is the cheapest find. Unplug, inspect, and
  reseat. Watch the panel while wiggling the harness - a reading that
  jumps is a wire.
- **Then the sensor.** Most EGT sensors are thermistors; the workshop
  manual gives a resistance at room temperature. One that reads open or
  shorted is done. They screw into the exhaust and seize; penetrating
  oil and patience beat force.
- **Then the loom.** A sensor that measures fine off the car but reads
  wrong on it points at the wiring to the ECU.

After the repair, clear the codes from the faults panel (`x`), let the
engine cool, and read the bank cold again: every sensor near ambient, no
note. Then drive it and watch the sensors climb together. A particulate
filter whose regeneration was blocked by the bad reading may need a few
drives, or a forced regeneration from a workshop tool, before its own
codes clear.

## Particulate filter

### What the dashboard reads

The DPF panel (`7`) gathers everything the vehicle says about its
particulate filter and, beside it, what the dashboard works out from that.
Three standard mode 01 PIDs feed it, each optional and each asked for
only when the vehicle names it in its supported-PID bitmap:

| PID | Capability | Reading |
| --- | --- | --- |
| `0x7A` | `DPF_DIFFERENTIAL_PRESSURE` | The restriction across the filter, with the inlet and outlet pressures when reported. |
| `0x7C` | `DPF_TEMP_INLET`, `DPF_TEMP_OUTLET` | The filter's inlet and outlet temperatures, one frame for both. |
| `0x8B` | `DPF_REGEN_STATUS` | Whether a regeneration is running, and how close the ECU is to starting one. |

A temperature inside the filter, `DPF_TEMP_INTERNAL`, has no standard
slot either, and comes only from a manufacturer.

The soot load has no standard PID. It comes from the manufacturer's own
identifiers, which differ from one engine's ECU to the next, so it is
read only when the [engine is declared](usage.md#declaring-the-engine)
and a profile has a cited table for it. [Compatibility](compatibility.md)
says what is declared today.

Two rows are guesses when the vehicle gives nothing better, and say so.
A filter temperature marked `(exhaust sensor)` is an exhaust gas sensor
the manufacturer profile placed at the filter, not the filter's own. A
regeneration reading `probable` with `estimated` on the source row was
inferred from a hot filter at moderate load, not reported. Neither ever
replaces what the ECU said when it said something.

Rows marked `(derived)` were worked out by the dashboard: the restriction
per gram per second of air, the inlet-to-outlet temperature delta, and
the time since a regeneration the dashboard saw end.

### The codes

| Code | Meaning |
| --- | --- |
| `P2002` | Filter efficiency below threshold, bank 1: the ECU sees too little restriction for the soot it expects, or too much. |
| `P242F` | Filter restriction from ash: what a regeneration cannot burn off has built up. |
| `P2463` | Soot accumulation: the load rose past what regeneration should have handled. |
| `P2452` to `P2455` | Differential pressure sensor circuit, range, low or high. |

The pressure sensor codes are the ones to rule out first: a filter reads
as blocked, or as empty, through a sensor that has failed.

### Reading the panel

The restriction rises with the flow through the filter, so a number on
its own means little; the panel puts the engine speed and air flow beside
it, and works out the restriction per unit of flow so two moments compare.

1. At idle, warm, note the differential pressure and the `ΔP / MAF` row.
   A clean filter puts a few kPa in the way.
2. Hold a steady 2500 rpm and note both again. The differential rises
   with the flow; the per-flow figure should not rise much.
3. Compare the `DPF ΔT` row across the two: a filter doing nothing runs
   the outlet a little cooler than the inlet. During a regeneration the
   outlet runs hotter, and the exhaust sensors climb past 550 °C.

A differential marked `(elevated)` sits past 20 kPa, a wide bound that a
healthy filter under load rarely reaches. It is a reason to look, not a
diagnosis: the per-flow figure, the soot load when the vehicle gives one,
and a recorded drive to compare against are what turn it into one. A
differential marked `(inconsistent)` reads more pressure after the filter
than before, which is a sensor or a hose, not a filter.

Watch a regeneration through: `SINCE LAST` restarts when it ends, and the
differential should drop afterwards. One that does not drop after a
completed regeneration is ash, not soot, and `P242F` will say so in time.

### Remediation

- **A pressure that does not move with the flow** is a blocked hose or a
  failed sensor. The two hoses to the differential pressure sensor clog
  with soot; clearing them is a five-minute job, and the sensor's own
  codes point at it.
- **A load that keeps climbing between regenerations** on a car driven
  short distances is the driving, not the filter. A regeneration needs
  the exhaust hot for a quarter of an hour; a longer drive lets it finish.
  A workshop tool can force one.
- **A restriction that survives a completed regeneration** is ash. Ash is
  not burnt off; the filter is cleaned or replaced.
- **An estimated regeneration that never reads `probable`** on a vehicle
  that should regenerate every few hundred kilometres is worth a look at
  the exhaust temperatures: a sensor reading low keeps the ECU from ever
  seeing the filter hot enough.

After a repair, clear the codes from the faults panel (`x`), record the
next drive with `--record`, and compare its `dpf_pressure` and `diesel`
columns against the one before.
