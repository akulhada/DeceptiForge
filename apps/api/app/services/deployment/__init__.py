"""Decoy deployment: preview, safety policy, GitHub port, jobs, and orchestration.

Repository writes only ever happen through a controlled branch + pull request; the default branch is
never written directly, monitoring activates only after a verified merge, and every decoy is inert.
"""
