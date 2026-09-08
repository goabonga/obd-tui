# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The OBD-II commands the dashboard declares beyond python-obd's table.

A capability - ``EGT_BANK_1``, say - names what the dashboard wants to
know, not which bytes fetch it. The standard registry answers it with the
SAE/ISO PID when one exists; the manufacturer registry answers for the
vehicles that expose it some other way. The rest of the dashboard only
ever asks for the capability.
"""
