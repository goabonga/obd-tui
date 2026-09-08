# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Recognise the manufacturer of a vehicle from its VIN.

The only place that turns a make into a profile. Every profile is asked
in turn whether it knows the VIN, and the generic one, which claims
everything, closes the list - so an unrecognised vehicle gets the
standard and nothing else, rather than an error.
"""

from __future__ import annotations

from obd_tui.obd.manufacturers.base import GenericProfile, ManufacturerProfile
from obd_tui.obd.manufacturers.suzuki import SuzukiProfile

# In the order they are asked. The generic profile goes last because it
# says yes to everything.
PROFILES: tuple[type[ManufacturerProfile], ...] = (SuzukiProfile, GenericProfile)


def detect(vin: str | None, engine: str | None = None) -> ManufacturerProfile:
    """Return the profile of the vehicle ``vin`` belongs to, bound to ``engine``.

    A vehicle that did not report a VIN is generic: there is nothing to
    recognise it by. The engine is what the user declared, since no
    standard reading names it reliably; a profile answers proprietary
    readings only for an engine it was told.
    """
    if not vin:
        return GenericProfile(engine)
    # The generic profile closes the list and claims everything, so the
    # search always finds one.
    return next(profile for profile in (cls(engine) for cls in PROFILES) if profile.supports(vin))


__all__ = ["PROFILES", "GenericProfile", "ManufacturerProfile", "SuzukiProfile", "detect"]
