"""Hard gates for Round-10 BC-safe residual fixes."""

from __future__ import annotations

from pathlib import Path


def test_xy_cif_submenu_validate_then_push():
    src = Path("batplot/plot_modes/xy/cif.py").read_text(encoding="utf-8")
    region = src[src.find("if any(':' in t for t in tokens):") :]
    region = region[:1800]
    assert "planned" in region
    assert region.find("planned.append") < region.find('push_state("cif-color")')
    assert region.find("if not planned") < region.find('push_state("cif-color")')


def test_ec_cycle_colors_validate_palette_before_push():
    src = Path("batplot/plot_modes/electrochem/colors.py").read_text(encoding="utf-8")
    region = src[src.find("# Palette: validate colormap before push") :]
    region = region[:1200]
    assert 'print(f"Unknown colormap' in region
    assert region.find("continue") < region.find('push_state("cycles/colors")')


def test_histo_grid_linewidth_preserves_zero():
    src = Path("batplot/plot_modes/histo/plot.py").read_text(encoding="utf-8")
    assert "grid_linewidth\", 0.6) or 0.6" not in src
    assert "0.6 if _lw is None else _lw" in src


def test_ec_wasd_chrome_uses_set_primary_axis_title():
    style = Path("batplot/plot_modes/electrochem/style.py").read_text(encoding="utf-8")
    assert "set_primary_axis_title(" in style
    apply = Path("batplot/plot_modes/electrochem/style_apply.py").read_text(
        encoding="utf-8"
    )
    assert "set_primary_axis_title(" in apply
    # Dual top remains visibility-only (SecondaryAxis keeps text).
    assert "secax.xaxis.label.set_visible(bool(top_s['title']))" in style


def test_dqdv_tick_state_empty_dict_persisted():
    src = Path("batplot/plot_modes/electrochem/dqdv_2d.py").read_text(encoding="utf-8")
    assert 'isinstance(ts, dict) and ts' not in src
    assert "if isinstance(ts, dict):" in src
    assert "set_primary_axis_title(" in src


def test_seal_ec_chrome_doc_mentions_titles():
    src = Path("batplot/plot_modes/electrochem/style.py").read_text(encoding="utf-8")
    assert "titles left alone" not in src
    assert "apply_titles=True" in src
