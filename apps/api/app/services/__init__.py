"""Application services for apps.api.app -- business logic that doesn't
belong in a router (thin HTTP translation) or a repository (persistence
only). Mirrors the pattern already established by services/incident_service
and services/calibration, scoped here to apps.api-owned domains."""
