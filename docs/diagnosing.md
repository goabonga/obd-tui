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

The exhaust panel (`6`) reads mode 01 PID `0x78`, which answers the whole
of bank 1 in one frame: a bitmap of the sensors fitted, then four
temperatures. `obd-tui` shows the fitted ones, up to four, upstream first:
sensor 1 sits before the turbine on most diesels, the last one past the
particulate filter.

python-obd's own table stops at PID `0x5F`, so this one is declared by
`obd-tui` itself, and so is the supported-PID bitmap that covers it, PID
`0x60`. On connect the vehicle is asked for that bitmap; only a vehicle
that names `0x78` in it is ever asked for the temperatures. The PID
catalogue (`p`) lists `EGT_BANK_1` as `[x]` or `[ ]` accordingly.

PID `0x78` is optional in the standard. Diesels with a particulate filter
usually have it, since the filter's regeneration is controlled from those
sensors; many petrol engines do not, and the panel then says `No data
reported by the vehicle`.

Each sensor is a reading of its own, `egt_bank_1_sensor_1` to
`egt_bank_1_sensor_4`, in the state, in a recording and in imperial
display. The bank is read every fifth sweep, and every sweep while the
panel is open.

### The codes

The ECU raises one code per sensor and per failure, and the code names
both. For bank 1:

| Sensor | Circuit | Low | High |
| --- | --- | --- | --- |
| Sensor 1 | `P0544` | `P0545` | `P0546` |
| Sensor 2 | `P2031` | `P2032` | `P2033` |

*Low* and *high* describe the signal, not the exhaust: a sensor whose
circuit is shorted reads one end of the scale, and one whose circuit is
open reads the other. `P2033` - sensor circuit high, bank 1 sensor 2 - is
the ECU saying the second sensor reports a temperature it cannot believe.

### Reading the panel

1. Connect the adapter and switch the ignition on, engine off and
   completely cold.
2. Open the PID catalogue (`p`) and check that `EGT_BANK_1` is marked
   `[x]`. If it is not, the vehicle does not report the bank and there is
   nothing more to see here.
3. Open the exhaust panel (`6`). Cold, every sensor should read close to
   the ambient temperature shown on the engine panel:

    ```
    EGT B1 S1 °C      19.0
    EGT B1 S2 °C      18.0
    EGT B1 S3 °C      19.0
    ```

    A sensor whose circuit is open or shorted reads one end of the scale
    instead, and gets a note:

    ```
    EGT B1 S1 °C      19.0
    EGT B1 S2 °C    1000.0  ⚠ far from the other sensors
    EGT B1 S3 °C      18.0
    ```

4. Start the engine and watch the bank warm up. The sensors should climb
   together, the upstream one first and fastest; one that stays put, or
   stays pegged, is the one the code names.

The note is a hint for the eye, not a verdict. It marks a sensor sitting
more than 300 °C from the median of its bank, which under load a healthy
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
