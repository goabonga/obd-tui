# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""What a manufacturer profile is, and the one that knows nothing."""

from __future__ import annotations

from abc import ABC, abstractmethod

import obd

from obd_tui.models.dpf import DpfRole


class ManufacturerProfile(ABC):
    """How one manufacturer answers capabilities the standard does not.

    A profile is consulted only after the standard registry has come up
    empty, so it never shadows a SAE/ISO PID the vehicle supports. It is
    also the one place a manufacturer's name is allowed to appear: the
    polling, the state and the views ask for a capability and never for
    a make.

    Attributes:
        name: The manufacturer, as shown to the user.
    """

    name: str

    @abstractmethod
    def supports(self, vin: str) -> bool:
        """Return whether ``vin`` belongs to a vehicle this profile knows."""

    def command(self, capability: str) -> obd.OBDCommand | None:
        """Return the command answering ``capability``, or ``None``.

        The default answers nothing: a profile only overrides this for
        the capabilities its manufacturer exposes some non-standard way.
        """
        return None

    @property
    def capabilities(self) -> frozenset[str]:
        """Return the capabilities this profile has a command for."""
        return frozenset()

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
