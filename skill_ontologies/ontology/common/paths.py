"""Locations of the project's ontology files."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIVERSAL_DIR = ROOT / "universal"
SKILLS_DIR = ROOT / "skills"
VOCABULARY = UNIVERSAL_DIR / "vocabulary.ttl"
SHAPES = UNIVERSAL_DIR / "shapes.ttl"
MANIFEST = ROOT / "manifest.json"
OBSERVATIONS_DIR = ROOT / "observations"
