"""Rust SAB/ASM active-table parsing; unsupported schemas retain raw bytes."""
from . import _native
from .model import AcisModel


def parse_sab_model(data: bytes, *, source_id: str = "sab-input") -> AcisModel:
    """Decode an admitted binary profile directly into the shared model.

    History is retained as an opaque source attachment. Model diagnostics and
    raw entities describe semantic limitations; framing errors raise ValueError.
    """
    return _native.parse_sab_model(data, source_id).to_model()
