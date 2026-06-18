"""ARCH-012: route modules extracted from the monolithic `api/main.py`.

Each module exposes an ``APIRouter`` that `main.py` includes. Endpoints keep
their original absolute paths, so the public HTTP surface is unchanged.
"""
