"""Capture backend selection + bbox conversion. We don't take a real screenshot here
(non-deterministic, needs a display) — we test the pure (x,y,w,h)->(l,t,r,b) mapping
and that capture_region dispatches to the right backend per platform / override."""
from __future__ import annotations

import sys

import pytest

from vision import capture


def test_ltrb_conversion():
    assert capture._ltrb(None) is None
    assert capture._ltrb((10, 20, 100, 50)) == (10, 20, 110, 70)   # x,y,w,h -> l,t,r,b


def test_unknown_backend_raises():
    with pytest.raises(ValueError) as exc:
        capture.capture_region(None, backend="mss")
    assert "mss" in str(exc.value)


def test_auto_dispatches_by_platform(monkeypatch):
    calls = []
    monkeypatch.setattr(capture, "_grab_screencapture", lambda b: calls.append(("sc", b)))
    monkeypatch.setattr(capture, "_grab_imagegrab", lambda b: calls.append(("ig", b)))
    capture.capture_region((0, 0, 10, 10), backend="auto")
    expected = "sc" if sys.platform == "darwin" else "ig"
    assert calls == [(expected, (0, 0, 10, 10))]


def test_explicit_backends_route(monkeypatch):
    calls = []
    monkeypatch.setattr(capture, "_grab_screencapture", lambda b: calls.append("sc"))
    monkeypatch.setattr(capture, "_grab_imagegrab", lambda b: calls.append("ig"))
    capture.capture_region(None, "screencapture")
    capture.capture_region(None, "imagegrab")
    assert calls == ["sc", "ig"]
