"""Pari verified training data pipeline.

This package turns candidate coding/reasoning examples into verified,
deduplicated, scored, split, training-ready JSONL. Executable coding
candidates are always verified inside the existing Pari Docker sandbox;
nothing is ever executed on the host.
"""

__version__ = "1.0.0"