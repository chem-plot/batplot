"""Stack rearrange must not change offsets or wipe custom minor tick locators."""

from __future__ import annotations

import types

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.ticker import AutoMinorLocator, MultipleLocator, NullLocator

from batplot.plot_modes.common.spines import apply_flat_tick_params
from batplot.plot_modes.xy.arrange import run_rearrange_menu
from batplot.plot_modes.xy.full_data import install_master_full
from batplot.ui import apply_wasd_minor_ticks, update_tick_visibility


def _stack_setup():
    fig, ax = plt.subplots()
    x = np.linspace(0.0, 10.0, 21)
    y0 = np.sin(x)
    y1 = np.cos(x)
    y2 = np.sin(x) * 0.5
    offsets = [0.0, -1.5, -3.0]
    lines = []
    for y, off in zip((y0, y1, y2), offsets):
        (ln,) = ax.plot(x, y + off)
        lines.append(ln)
    ax.set_xlim(0.0, 10.0)
    ax.set_ylim(-4.0, 1.5)
    ax.xaxis.set_major_locator(MultipleLocator(2.0))
    ax.xaxis.set_minor_locator(AutoMinorLocator(5))  # 4 minors / major
    ax.yaxis.set_major_locator(MultipleLocator(1.0))
    ax.yaxis.set_minor_locator(MultipleLocator(0.25))
    labels = ["a", "b", "c"]
    label_txt = [ax.text(0, 0, f"{i+1}") for i in range(3)]
    x_data = [x.copy(), x.copy(), x.copy()]
    orig = [y0.copy(), y1.copy(), y2.copy()]
    y_data = [y0 + offsets[0], y1 + offsets[1], y2 + offsets[2]]
    x_full = [x.copy(), x.copy(), x.copy()]
    y_full = [y0.copy(), y1.copy(), y2.copy()]
    install_master_full(fig, x_full, y_full, force=True)
    args = types.SimpleNamespace(stack=True, autoscale=False)
    return (
        fig,
        ax,
        args,
        labels,
        label_txt,
        x_data,
        y_data,
        orig,
        list(offsets),
        x_full,
        y_full,
        lines,
    )


def test_stack_rearrange_keeps_offsets_and_minor_locators():
    (
        fig,
        ax,
        args,
        labels,
        label_txt,
        x_data,
        y_data,
        orig,
        offsets,
        x_full,
        y_full,
        lines,
    ) = _stack_setup()
    xlim0, ylim0 = ax.get_xlim(), ax.get_ylim()
    x_ndivs = int(ax.xaxis.get_minor_locator().ndivs)
    y_step = float(ax.yaxis.get_minor_locator()._edge.step)

    answers = iter(["3 1 2", "q"])
    run_rearrange_menu(
        args=args,
        ax=ax,
        fig=fig,
        labels=labels,
        label_text_objects=label_txt,
        x_data_list=x_data,
        y_data_list=y_data,
        orig_y=orig,
        offsets_list=offsets,
        x_full_list=x_full,
        raw_y_full_list=y_full,
        delta=1.5,  # must not restack from this
        push_state=lambda *_a, **_k: None,
        _safe_input=lambda *_a, **_k: next(answers, "q"),
        _line=lambda i: lines[i],
        _lines_by_curve=lines,
    )

    # Order-only: offsets follow curves (c, a, b) → (-3, 0, -1.5)
    assert offsets == pytest.approx([-3.0, 0.0, -1.5])
    assert labels == ["c", "a", "b"]
    # Must not recompute equal gaps from delta (that would be 0, -1.5, -3 again
    # but attached to wrong curve heights / change visual spacing under ticks).
    assert ax.get_xlim() == pytest.approx(xlim0)
    assert ax.get_ylim() == pytest.approx(ylim0)
    assert isinstance(ax.xaxis.get_minor_locator(), AutoMinorLocator)
    assert int(ax.xaxis.get_minor_locator().ndivs) == x_ndivs
    assert isinstance(ax.yaxis.get_minor_locator(), MultipleLocator)
    assert float(ax.yaxis.get_minor_locator()._edge.step) == pytest.approx(y_step)
    plt.close(fig)


def test_apply_wasd_and_visibility_preserve_custom_minors():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.xaxis.set_minor_locator(AutoMinorLocator(5))
    ax.yaxis.set_minor_locator(MultipleLocator(0.1))
    wasd = {
        "top": {"minor": False},
        "bottom": {"minor": True},
        "left": {"minor": True},
        "right": {"minor": False},
    }
    apply_wasd_minor_ticks(ax, wasd)
    assert isinstance(ax.xaxis.get_minor_locator(), AutoMinorLocator)
    assert int(ax.xaxis.get_minor_locator().ndivs) == 5
    assert isinstance(ax.yaxis.get_minor_locator(), MultipleLocator)
    assert float(ax.yaxis.get_minor_locator()._edge.step) == pytest.approx(0.1)

    tick_state = {
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": False,
        "mbx": True,
        "mtx": False,
        "mly": True,
        "mry": False,
    }
    update_tick_visibility(ax, tick_state)
    assert int(ax.xaxis.get_minor_locator().ndivs) == 5
    assert float(ax.yaxis.get_minor_locator()._edge.step) == pytest.approx(0.1)

    flat_state = {
        "b_ticks": True,
        "b_labels": True,
        "t_ticks": False,
        "t_labels": False,
        "l_ticks": True,
        "l_labels": True,
        "r_ticks": False,
        "r_labels": False,
        "mbx": True,
        "mtx": False,
        "mly": True,
        "mry": False,
    }
    apply_flat_tick_params(ax, flat_state)
    assert int(ax.xaxis.get_minor_locator().ndivs) == 5
    assert float(ax.yaxis.get_minor_locator()._edge.step) == pytest.approx(0.1)
    plt.close(fig)


def test_capture_restore_preserves_autominor_ndivs():
    """Matplotlib 3.8+ uses public ``ndivs``; capture must not lose it."""
    from batplot.ui import capture_axes_tick_locators, restore_axes_tick_locators

    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.xaxis.set_minor_locator(AutoMinorLocator(5))
    ax.yaxis.set_minor_locator(MultipleLocator(0.2))
    cap = capture_axes_tick_locators(ax, ("x", "y"))
    assert cap.get("x_minor_ndivs") == 5
    assert cap.get("x_minor_off") is False
    assert cap.get("y_minor_step") == pytest.approx(0.2)

    ax.xaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_minor_locator(NullLocator())
    restore_axes_tick_locators(ax, cap, ("x", "y"))
    assert isinstance(ax.xaxis.get_minor_locator(), AutoMinorLocator)
    assert int(getattr(ax.xaxis.get_minor_locator(), "ndivs",
                        getattr(ax.xaxis.get_minor_locator(), "_ndivs", 0))) == 5
    assert isinstance(ax.yaxis.get_minor_locator(), MultipleLocator)
    assert float(ax.yaxis.get_minor_locator()._edge.step) == pytest.approx(0.2)
    plt.close(fig)


def test_restore_legacy_missing_ndivs_keeps_autominor_when_not_off():
    """Snapshots with minor_off=False but no ndivs must not force NullLocator."""
    from batplot.ui import restore_axes_tick_locators
    from matplotlib.ticker import NullLocator

    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    restore_axes_tick_locators(
        ax,
        {
            "x_major_step": None,
            "x_minor_step": None,
            "x_minor_ndivs": None,
            "x_minor_off": False,
            "y_major_step": None,
            "y_minor_step": None,
            "y_minor_ndivs": None,
            "y_minor_off": False,
        },
        ("x", "y"),
    )
    assert isinstance(ax.xaxis.get_minor_locator(), AutoMinorLocator)
    assert not isinstance(ax.xaxis.get_minor_locator(), NullLocator)
    plt.close(fig)


def test_apply_wasd_installs_default_when_null():
    """Old sessions / NullLocator still get a usable AutoMinorLocator (BC)."""
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.xaxis.set_minor_locator(NullLocator())
    apply_wasd_minor_ticks(
        ax,
        {
            "top": {"minor": False},
            "bottom": {"minor": True},
            "left": {"minor": False},
            "right": {"minor": False},
        },
    )
    assert isinstance(ax.xaxis.get_minor_locator(), AutoMinorLocator)
    plt.close(fig)
