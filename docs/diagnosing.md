# Diagnosing faults

The dashboard reads; the diagnosis is yours. This page is the method,
fault by fault: what `obd-tui` can show about one, how to read it, and
what usually fixes it. Each section assumes the basics from
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
