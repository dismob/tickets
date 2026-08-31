# Copyright (c) 2025 Benoît Pelletier
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Shared fixtures for the `tickets` plugin's tests.

This plugin is a standalone Git submodule (dismob/tickets repo), so its
tests live here rather than in the main bot repo, so they travel with the
plugin regardless of which bot it's used in.

This file is intentionally minimal for now: no fixture is defined until the
first tests for this plugin are actually written.

Reminder: this plugin depends on the shared `dismob` framework, which lives
in the main bot repo (DungeonBot), not in this submodule. For these tests
to run, `dismob` must be importable:
- From the main repo (DungeonBot), the project root is already on
  sys.path via `pythonpath = .` in the root `pytest.ini`, so simply running
  `pytest` from the DungeonBot repo root works (it also collects the tests
  under `plugins/*/tests/`).
- To test this submodule in complete isolation (outside the DungeonBot
  repo), `dismob` would need to be made importable some other way (e.g. a
  PYTHONPATH environment variable pointing at a DungeonBot checkout, or
  publishing `dismob` as an installable package). Not set up yet.
"""
