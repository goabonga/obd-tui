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
PROFILES: tuple[ManufacturerProfile, ...] = (SuzukiProfile(), GenericProfile())


def detect(vin: str | None) -> ManufacturerProfile:
    """Return the profile of the vehicle ``vin`` belongs to.

    A vehicle that did not report a VIN is generic: there is nothing to
    recognise it by.
    """
    if not vin:
        return GenericProfile()
    # The generic profile closes the list and claims everything, so the
    # search always finds one.
    return next(profile for profile in PROFILES if profile.supports(vin))


__all__ = ["PROFILES", "GenericProfile", "ManufacturerProfile", "SuzukiProfile", "detect"]
