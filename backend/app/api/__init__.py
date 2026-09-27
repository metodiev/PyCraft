"""API layer: dependency wiring and route assembly."""

from app.api import auth, challenges, dashboard, github, runtime, submissions

__all__ = ["auth", "challenges", "dashboard", "github", "runtime", "submissions"]
