"""
core/stats.py
=============
Fast lookup of a player's attributes on the 1-20 engine scale.

Every part of the AI used to re-read and re-clamp the same attribute many
thousands of times a match (e.g. Top Speed over a million times).  Attributes
never change during a match, so each one is worked out once per player and
remembered.  The value is exactly the same as before:
    raw value (default 10), divided by 5 if it's on the 1-100 scale, clamped to 1-20.
"""


def stat20(p, name):
    cache = p.__dict__.get("_stat20")
    if cache is None or cache[0] is not p.attributes:
        cache = (p.attributes, {})
        p.__dict__["_stat20"] = cache
    vals = cache[1]
    v = vals.get(name)
    if v is None:
        v = p.attributes.get(name, 10)
        if v > 25:
            v /= 5.0
        v = max(1.0, min(20.0, v))
        vals[name] = v
    return v
