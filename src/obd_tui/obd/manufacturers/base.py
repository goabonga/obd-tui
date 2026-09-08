# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""What a manufacturer profile is, and the one that knows nothing."""

from __future__ import annotations

from abc import ABC, abstractmethod

import obd

from obd_tui.models.dpf import DpfRole
from obd_tui.obd.uds import DataIdentifier


class ManufacturerProfile(ABC):
    """How one manufacturer answers capabilities the standard does not.

    A profile is consulted only after the standard registry has come up
    empty, so it never shadows a SAE/ISO PID the vehicle supports. It is
    also the one place a manufacturer's name is allowed to appear: the
    polling, the state and the views ask for a capability and never for
    a make.

    A profile is bound to an engine, when one is known: proprietary
    readings differ from one engine's ECU to the next, and an engine the
    profile does not know is answered nothing rather than something that
    might be wrong for it.

    Attributes:
        name: The manufacturer, as shown to the user.
        engine: The engine code the vehicle was declared with, if any.
    """

    name: str

    def __init__(self, engine: str | None = None) -> None:
        self.engine = engine

    @abstractmethod
    def supports(self, vin: str) -> bool:
        """Return whether ``vin`` belongs to a vehicle this profile knows."""

    @classmethod
    def known_engines(cls) -> frozenset[str]:
        """Return the engine codes this profile has anything to say about.

        Empty by default. What is offered to the user as a choice, so it
        never names an engine the profile would answer nothing for.
        """
        return frozenset()

    @property
    def identifiers(self) -> tuple[DataIdentifier, ...]:
        """Return the proprietary readings this profile has for its engine.

        Empty by default, and for any engine the profile does not know.
        """
        return ()

    def command(self, capability: str) -> obd.OBDCommand | None:
        """Return the command answering ``capability``, or ``None``.

        The first identifier declared for the capability on this engine
        answers; a capability none is declared for is not available.
        """
        for identifier in self.identifiers:
            if identifier.capability == capability:
                return identifier.command()
        return None

    @property
    def capabilities(self) -> frozenset[str]:
        """Return the capabilities this profile has a command for."""
        return frozenset(identifier.capability for identifier in self.identifiers)

    def exhaust_sensor_role(self, bank: int, sensor: int) -> DpfRole | None:
        """Return where an exhaust gas sensor sits relative to the filter.

        ``None`` for a sensor the profile cannot place, which is the
        default for every sensor: an exhaust gas sensor is the filter's
        inlet only when someone who knows the engine says so, never by
        assumption from its number.
        """
        return None


class GenericProfile(ManufacturerProfile):
    """The profile of a vehicle nobody recognised: the standard, and no more."""

    name = "generic"

    def supports(self, vin: str) -> bool:
        """Claim every vehicle, which is why it is consulted last."""
        return True
