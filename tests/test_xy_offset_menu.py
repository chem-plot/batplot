"""Regression: XY offset submenu must receive label_text_objects."""

from __future__ import annotations

from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.xy.menu import print_xy_menu
from batplot.plot_modes.xy.offset_menu import run_offset_menu


def test_xy_stack_menu_hides_disabled_keys(capsys):
    fig = plt.figure()
    try:
        print_xy_menu(fig=fig, stack=True, is_diffraction=True, colorize_menu=lambda s: s)
        out = capsys.readouterr().out
        assert "o: offset" not in out
        assert "y: change Y" not in out
        assert "d: derivative" not in out
        assert "a: rearrange" in out
    finally:
        plt.close(fig)


def test_offset_menu_reset_updates_labels_without_nameerror():
    fig, ax = plt.subplots()
    try:
        x = np.linspace(0.0, 1.0, 20)
        y0 = np.ones_like(x)
        y1 = np.ones_like(x) * 0.5
        (ln0,) = ax.plot(x, y0 + 1.0)
        (ln1,) = ax.plot(x, y1 + 2.0)
        lines = [ln0, ln1]
        labels = ["a", "b"]
        label_text_objects = [
            ax.text(0.1, 1.0, "a"),
            ax.text(0.1, 2.0, "b"),
        ]
        args = SimpleNamespace(stack=False, autoscale=False)
        inputs = iter(["r", "q"])

        delta = run_offset_menu(
            ax=ax,
            fig=fig,
            args=args,
            labels=labels,
            orig_y=[y0, y1],
            x_data_list=[x.copy(), x.copy()],
            y_data_list=[y0 + 1.0, y1 + 2.0],
            offsets_list=[1.0, 2.0],
            delta=1.0,
            line=lambda i: lines[i],
            nlines=lambda: len(lines),
            push_state=lambda *_a, **_k: None,
            safe_input=lambda _p: next(inputs),
            colorize_menu=lambda s: s,
            label_text_objects=label_text_objects,
        )
        assert delta == 1.0
        assert np.allclose(lines[0].get_ydata(), y0)
        assert np.allclose(lines[1].get_ydata(), y1)
    finally:
        plt.close(fig)
