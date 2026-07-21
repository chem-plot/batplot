"""Flexible parsing for canvas/frame size prompts (shared across modes)."""

from __future__ import annotations


def parse_size_spec(
    spec: str,
    cur_w: float,
    cur_h: float,
) -> tuple[float, float] | None:
    """Parse a resize spec (same rules as ``ui.resize_plot_frame``).

    Accepts ``6 4``, ``6x4``, ``w=6 h=4``, ``scale=1.2``, or a single width
    (height scaled to preserve aspect).
    """
    raw = (spec or "").strip().lower()
    if not raw or raw == "q":
        return None
    new_w, new_h = cur_w, cur_h
    if "scale=" in raw:
        try:
            factor = float(raw.split("scale=", 1)[1].strip())
            new_w = cur_w * factor
            new_h = cur_h * factor
        except Exception:
            print("Invalid scale factor.")
            return None
    else:
        parts = raw.replace("x", " ").split()
        kv: dict[str, str] = {}
        numbers: list[str] = []
        for part in parts:
            if "=" in part:
                key, val = part.split("=", 1)
                kv[key.strip()] = val.strip()
            else:
                numbers.append(part)
        if kv:
            if "w" in kv:
                new_w = float(kv["w"])
            if "h" in kv:
                new_h = float(kv["h"])
        elif len(numbers) == 2:
            new_w, new_h = float(numbers[0]), float(numbers[1])
        elif len(numbers) == 1:
            new_w = float(numbers[0])
            aspect = cur_h / cur_w if cur_w else 1.0
            new_h = new_w * aspect
        else:
            print("Could not parse specification.")
            return None
    min_in = 0.01
    return max(min_in, new_w), max(min_in, new_h)


def parse_positive_float(spec: str, *, label: str = "value") -> float | None:
    """Parse one positive inch value; return None on cancel/invalid."""
    raw = (spec or "").strip().lower()
    if not raw or raw == "q":
        return None
    try:
        val = float(raw)
    except ValueError:
        print(f"Invalid {label}.")
        return None
    if val <= 0:
        print(f"{label.title()} must be positive.")
        return None
    return val


__all__ = ["parse_positive_float", "parse_size_spec"]
