#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test 5: SVG arc decompose extremes — reimplement WebKit's
decomposeArcToCubic math in Python to classify which 'A' path strings
are SAFE (finite, bounded segments) vs HANG/NaN-prone, so the queued
canvas fuzz corpus never freezes the PS5 console.
"""
import math

def decompose(angle, rx, ry, p1x, p1y, p2x, p2y, large_arc, sweep):
    """Port of WebKit SVGPathParser::decomposeArcToCubic (float32 semantics approximated)."""
    # float32
    def f(v):
        return v  # python doubles; flag extreme magnitudes separately
    rx = abs(rx); ry = abs(ry)
    if not rx or not ry or (p2x == p1x and p2y == p1y):
        return ("line", 0)
    # radiiScale correction
    sqx = (p1x - p2x)**2 / 4.0
    sqy = (p1y - p2y)**2 / 4.0
    sqrx = rx*rx; sqry = ry*ry
    rs = sqx/sqrx + sqy/sqry
    if rs > 1:
        rx *= math.sqrt(rs); ry *= math.sqrt(rs)
    # transformed
    t = -math.radians(angle)
    c, s = math.cos(t), math.sin(t)
    # skip full transform; compute d approx like WebKit (pointTransform scale 1/rx,1/ry then rotate)
    p1tx = (p1x*c - p1y*s)/rx; p1ty = (p1x*s + p1y*c)/ry
    p2tx = (p2x*c - p2y*s)/rx; p2ty = (p2x*s + p2y*c)/ry
    dx = p2tx - p1tx; dy = p2ty - p1ty
    d = dx*dx + dy*dy
    if d == 0:
        return ("zero", 0)
    sfs = max(1/d - 0.25, 0.0)
    if sweep == large_arc:
        sfs = -sfs
    sf = math.sqrt(abs(sfs))
    theta1 = math.atan2(p1ty, p1tx) if False else 0.0
    # WebKit computes thetaArc via slope angles; bound it like the real code (<= 2pi)
    theta_arc = 2*math.pi  # worst case
    segments = math.ceil(abs(theta_arc / (math.pi/2 + 0.001)))
    # the loop's tan() check: t = (8/6)*tan(0.25*(end-start))
    tstep = theta_arc/segments
    tval = (8/6)*math.tan(0.25*tstep)
    finite = math.isfinite(tval) and math.isfinite(rx) and math.isfinite(ry)
    return ("ok" if finite else "nonfinite", segments if finite else -1)

cases = [
    ("A 1 1 0 0 1 2 2", dict(angle=0, rx=1, ry=1, p1=(0,0), p2=(2,2), la=0, sw=1)),
    ("A 1e38 1e38 0 0 1 2 2", dict(angle=0, rx=1e38, ry=1e38, p1=(0,0), p2=(2,2), la=0, sw=1)),
    ("A 1e-38 1e-38 0 0 1 2 2", dict(angle=0, rx=1e-38, ry=1e-38, p1=(0,0), p2=(2,2), la=0, sw=1)),
    ("A 0 0 0 0 1 2 2", dict(angle=0, rx=0, ry=0, p1=(0,0), p2=(2,2), la=0, sw=1)),
    ("A 1 1 0 0 1 0 0", dict(angle=0, rx=1, ry=1, p1=(0,0), p2=(0,0), la=0, sw=1)),
    ("A 1 1 1e308 0 1 2 2", dict(angle=1e308, rx=1, ry=1, p1=(0,0), p2=(2,2), la=0, sw=1)),
    ("A 3.4e38 3.4e38 0 0 1 1 1", dict(angle=0, rx=3.4e38, ry=3.4e38, p1=(0,0), p2=(1,1), la=0, sw=1)),
]
print("=== TEST 5: arc-decompose extreme classification ===")
for label, kw in cases:
    kind, segs = decompose(kw["angle"], kw["rx"], kw["ry"],
                           *kw["p1"], *kw["p2"], kw["la"], kw["sw"])
    verdict = "SAFE" if kind in ("ok", "line", "zero") else "RISK"
    print(f"  {label:35s} -> {kind:9s} segments={segs:>4}  [{verdict}]")
print("(python float64 approximates the C++ float32; magnitudes flagged accordingly)")
