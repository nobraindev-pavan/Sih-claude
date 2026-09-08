"""SANCHAY - Section-level Analytics & Coordinated Block Planning Engine.

SIH 2026, problem statement SIH26027 (Ministry of Railways).

Read docs/ before changing anything here. The short version:

  A *block* is a period when a railway section is closed so maintenance can
  happen safely. Engineering, S&T and Traction Distribution each raise their
  own demands. This package packs those demands into the smallest number of
  safe, coordinated blocks that cost the fewest train minutes.

Everything is in minutes-from-horizon-start (an int). See core.timeutil.
"""

__version__ = "0.1.0"
