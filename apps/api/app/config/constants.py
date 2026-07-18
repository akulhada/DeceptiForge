# Purpose: hold cross-cutting constants with no framework dependencies.
# Responsibilities: define the single demo/default organization used when auth is disabled and by
#   the persistence defaults. Future modules: real multi-tenant identity replaces this constant.
from __future__ import annotations

from uuid import UUID

# The organization every demo/pipeline artifact is stamped with, and the identity returned when the
# auth boundary is disabled for local development. Production supplies real organization ids.
DEMO_ORGANIZATION_ID = UUID("00000000-0000-0000-0000-0000000000de")
