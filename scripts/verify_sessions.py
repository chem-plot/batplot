import os
import tempfile
import pickle
import math
from typing import Dict, Any

import numpy as np
import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt

from batplot.readers import read_mpt_file, read_ec_csv_dqdv_file
from batplot.session import (
    dump_ec_session, load_ec_session,
    dump_cpc_session, load_cpc_session,
    dump_operando_session, load_operando_session,
)


def _approx(a, b, tol=1e-6):
    try:
        return abs(float(a) - float(b)) <= tol
    except Exception:
        return False


def _bbox_equal(ax0, ax1, tol=1e-6):
    b0 = ax0.get_position().bounds
    b1 = ax1.get_position().bounds
    return all(_approx(x, y, tol) for x, y in zip(b0, b1))


def _tick_width_sample(ax, axis='x', which='major'):
    try:
        ticks = ax.xaxis.get_major_ticks() if axis == 'x' and which == 'major' else \
                ax.xaxis.get_minor_ticks() if axis == 'x' else \
                ax.yaxis.get_major_ticks() if which == 'major' else \
                ax.yaxis.get_minor_ticks()
        if ticks:
            return ticks[0].tick1line.get_linewidth()
    except Exception:
        pass
    return None


def verify_ec_gc(path_mpt: str = None, path_csv: str = None) -> None:
    print("[EC GC] round-trip")
    # Prefer .csv for speed if present
    if path_csv and os.path.isfile(path_csv):
        # Build simple GC-like plot: x as specific capacity, y as voltage per cycle
        # Readers for CSV GC are in read_ec_csv_file but we can fake simple cycles
        x = np.linspace(0, 100, 200)
        y1 = 3.7 - 0.5*np.exp(-x/50)
        y2 = 3.6 - 0.4*np.exp(-(x-10)/50)
        fig, ax = plt.subplots(figsize=(9, 6), dpi=100)
        ln1, = ax.plot(x, y1, label='Cycle 1', color='tab:blue', lw=2)
        ln2, = ax.plot(x, y2, label='Cycle 2', color='tab:orange', lw=2)
        cycle_lines = {1: {'charge': ln1, 'discharge': None}, 2: {'charge': ln2, 'discharge': None}}
    else:
        # No file needed; synthetic
        x = np.linspace(0, 120, 300)
        y = 3.5 - 0.3*np.sin(x/40)
        fig, ax = plt.subplots(figsize=(10, 6), dpi=110)
        ln1, = ax.plot(x, y, label='Cycle 1', color='tab:blue', lw=2)
        cycle_lines = {1: {'charge': ln1, 'discharge': None}}

    # Styles and axis setup
    ax.set_xlabel('Specific Capacity (mAh g$^{-1}$)', labelpad=8)
    ax.set_ylabel('Voltage (V)', labelpad=12)
    ax.set_xlim(5, 95)
    ax.set_ylim(2.2, 4.1)
    ax.spines['top'].set_visible(False)
    ax.tick_params(axis='x', which='major', width=1.5)
    ax.tick_params(axis='y', which='major', width=1.2)
    # Duplicate titles
    ax._top_xlabel_on = True
    ax._right_ylabel_on = True

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 'ec.pkl')
        dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
        res = load_ec_session(p)
        assert res is not None
        fig2, ax2, cycle_lines2 = res
        # Compare
        assert tuple(fig.get_size_inches()) == tuple(fig2.get_size_inches())
        assert fig.dpi == fig2.dpi
        assert ax.get_xlabel() == ax2.get_xlabel()
        assert ax.get_ylabel() == ax2.get_ylabel()
        assert np.allclose(ax.get_xlim(), ax2.get_xlim())
        assert np.allclose(ax.get_ylim(), ax2.get_ylim())
        # Label pads
        # Use Axis.labelpad; Text.get_pad is backend-specific
        assert _approx(getattr(ax.xaxis, 'labelpad', 0.0), getattr(ax2.xaxis, 'labelpad', 0.0), 1e-3)
        assert _approx(getattr(ax.yaxis, 'labelpad', 0.0), getattr(ax2.yaxis, 'labelpad', 0.0), 1e-3)
        # Duplicate titles flags
        assert bool(getattr(ax, '_top_xlabel_on', False)) == bool(getattr(ax2, '_top_xlabel_on', False))
        assert bool(getattr(ax, '_right_ylabel_on', False)) == bool(getattr(ax2, '_right_ylabel_on', False))
        # Spines visibility and linewidths
        for side in ('bottom','top','left','right'):
            s1 = ax.spines[side]; s2 = ax2.spines[side]
            assert bool(s1.get_visible()) == bool(s2.get_visible())
            assert _approx(s1.get_linewidth(), s2.get_linewidth(), 1e-3)
        # Tick widths
        for (axis, which) in (('x','major'),('x','minor'),('y','major'),('y','minor')):
            w1 = _tick_width_sample(ax, axis, which)
            w2 = _tick_width_sample(ax2, axis, which)
            if w1 is None and w2 is None:
                continue
            assert _approx(w1 or 0.0, w2 or 0.0, 1e-3)
        plt.close(fig); plt.close(fig2)
    print("  OK")


def verify_dqdv(csv_path: str) -> None:
    print("[EC dQ/dV] round-trip")
    # Build using reader
    voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_ec_csv_dqdv_file(csv_path, prefer_specific=True)
    fig, ax = plt.subplots(figsize=(10, 6), dpi=105)
    cyc_int = (np.rint(cycles)).astype(int)
    for cyc in sorted(set(cyc_int)):
        m = cyc_int == cyc
        if m.sum() >= 2:
            ln, = ax.plot(voltage[m], dqdv[m], '-', lw=1.8, alpha=0.85, label=f'Cycle {cyc}')
    ax.legend()
    cycle_lines = {int(c): {'charge': None, 'discharge': None} for c in set(cyc_int)}
    ax.set_xlabel('Voltage (V)', labelpad=9)
    ax.set_ylabel(y_label, labelpad=11)
    ax.set_xlim(np.nanmin(voltage)+0.1, np.nanmax(voltage)-0.1)
    ax.set_ylim(np.nanmin(dqdv), np.nanmax(dqdv))

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 'dqdv.pkl')
        dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
        res = load_ec_session(p)
        assert res is not None
        fig2, ax2, _ = res
        assert tuple(fig.get_size_inches()) == tuple(fig2.get_size_inches())
        assert fig.dpi == fig2.dpi
        assert ax.get_xlabel() == ax2.get_xlabel()
        assert ax.get_ylabel() == ax2.get_ylabel()
        assert np.allclose(ax.get_xlim(), ax2.get_xlim())
        assert np.allclose(ax.get_ylim(), ax2.get_ylim())
    # Label pads
    assert _approx(getattr(ax.xaxis, 'labelpad', 0.0), getattr(ax2.xaxis, 'labelpad', 0.0), 1e-3)
    assert _approx(getattr(ax.yaxis, 'labelpad', 0.0), getattr(ax2.yaxis, 'labelpad', 0.0), 1e-3)
    plt.close(fig); plt.close(fig2)
    print("  OK")


def verify_cpc() -> None:
    print("[CPC] round-trip")
    x = np.arange(1, 11)
    y_c = 100 + 3*np.random.RandomState(0).randn(10)
    y_d = 98 + 3*np.random.RandomState(1).randn(10)
    eff = 95 + 2*np.random.RandomState(2).randn(10)
    fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
    ax2 = ax.twinx()
    sc_c = ax.scatter(x, y_c, s=36, color='#1f77b4', label='Charge capacity', alpha=0.9, zorder=3)
    sc_d = ax.scatter(x, y_d, s=36, color='#ff7f0e', label='Discharge capacity', alpha=0.9, zorder=3)
    sc_e = ax2.scatter(x, eff, s=50, color='#2ca02c', label='Coulombic efficiency', alpha=0.85, marker='^', zorder=3)
    ax.set_xlabel('Cycle number', labelpad=7)
    ax.set_ylabel('Specific Capacity (mAh g⁻¹)', labelpad=10)
    ax2.set_ylabel('Efficiency (%)', labelpad=9)
    ax.set_xlim(0.5, 10.5)
    ax.set_ylim(min(y_c.min(), y_d.min())-5, max(y_c.max(), y_d.max())+5)
    ax2.set_ylim(eff.min()-3, eff.max()+3)
    # Legend at a custom position (in inches)
    fig_w, fig_h = fig.get_size_inches()
    fig._cpc_legend_xy_in = (0.0, (fig_h/2.0)-0.5)
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(handles1 + handles2, labels1 + labels2, loc='center', bbox_to_anchor=(0.5, 0.5), bbox_transform=fig.transFigure)

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 'cpc.pkl')
        dump_cpc_session(p, fig=fig, ax=ax, ax2=ax2, sc_charge=sc_c, sc_discharge=sc_d, sc_eff=sc_e, skip_confirm=True)
        res = load_cpc_session(p)
        assert res is not None
        fig2, axl, axr, scC, scD, scE = res
        assert tuple(fig.get_size_inches()) == tuple(fig2.get_size_inches())
        assert fig.dpi == fig2.dpi
        assert ax.get_xlabel() == axl.get_xlabel()
        assert ax.get_ylabel() == axl.get_ylabel()
        assert ax2.get_ylabel() == axr.get_ylabel()
        assert np.allclose(ax.get_xlim(), axl.get_xlim())
        assert np.allclose(ax.get_ylim(), axl.get_ylim())
        assert np.allclose(ax2.get_ylim(), axr.get_ylim())
        # Label pads
        assert _approx(getattr(ax.xaxis, 'labelpad', 0.0), getattr(axl.xaxis, 'labelpad', 0.0), 1e-3)
        assert _approx(getattr(ax.yaxis, 'labelpad', 0.0), getattr(axl.yaxis, 'labelpad', 0.0), 1e-3)
        assert _approx(getattr(ax2.yaxis, 'labelpad', 0.0), getattr(axr.yaxis, 'labelpad', 0.0), 1e-3)
        # Series match
        def _sc_xy(sc):
            arr = np.asarray(sc.get_offsets())
            return arr[:,0], arr[:,1]
        for (s0,s1) in ((sc_c, scC),(sc_d, scD),(sc_e, scE)):
            x0,y0 = _sc_xy(s0); x1,y1 = _sc_xy(s1)
            assert np.allclose(x0, x1)
            assert np.allclose(y0, y1)
        # Legend position inches
        assert hasattr(fig2, '_cpc_legend_xy_in')
        assert np.allclose(fig._cpc_legend_xy_in, fig2._cpc_legend_xy_in)
        plt.close(fig); plt.close(fig2)
    print("  OK")


def verify_operando() -> None:
    print("[Operando+EC] round-trip")
    # Synthetic image + EC panel
    img = np.linspace(0, 1, 100*40).reshape(40, 100)
    fig = plt.figure(figsize=(11, 6), dpi=120)
    # Place axes similar to loader logic (will recenter on load)
    ax = fig.add_axes([0.25, 0.2, 0.5, 0.6])
    im = ax.imshow(img, aspect='auto', origin='upper', extent=(0, 10, 0, 5), cmap='plasma', interpolation='nearest')
    cbar_ax = fig.add_axes([0.2, 0.2, 0.03, 0.6])
    cbar = plt.colorbar(im, cax=cbar_ax)
    cbar.set_label('Intensity (a.u.)')
    ax.set_xlabel('2θ (deg)', labelpad=6)
    ax.set_ylabel('Scan index', labelpad=8)
    ax.set_xlim(1.0, 9.0)
    ax.set_ylim(0.5, 4.5)
    # EC panel
    ec_ax = fig.add_axes([0.78, 0.2, 0.17, 0.6])
    t = np.linspace(0, 5, 100)
    v = 3.0 + 0.1*np.sin(2*np.pi*t/5)
    ln, = ec_ax.plot(v, t, lw=1.5, color='tab:blue')
    setattr(ec_ax, '_ec_line', ln)
    ec_ax.set_xlabel('Voltage (V)')
    ec_ax.set_ylabel('Time (h)')
    setattr(ec_ax, '_ec_time_h', t)
    setattr(ec_ax, '_ec_voltage_v', v)
    setattr(ec_ax, '_ec_current_mA', np.zeros_like(t))
    setattr(ec_ax, '_ec_y_mode', 'time')
    ec_ax.set_xlim(2.8, 3.2)
    ec_ax.set_ylim(0.0, 5.0)

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 'op.pkl')
        dump_operando_session(p, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True)
        res = load_operando_session(p)
        assert res is not None
        fig2, ax2, im2, cbar2, ec2 = res
        # Basic comparisons
        assert tuple(fig.get_size_inches()) == tuple(fig2.get_size_inches())
        assert fig.dpi == fig2.dpi
        # Labels and pads
        assert ax.get_xlabel() == ax2.get_xlabel()
        assert ax.get_ylabel() == ax2.get_ylabel()
        assert _approx(getattr(ax.xaxis, 'labelpad', 0.0), getattr(ax2.xaxis, 'labelpad', 0.0), 1e-3)
        assert _approx(getattr(ax.yaxis, 'labelpad', 0.0), getattr(ax2.yaxis, 'labelpad', 0.0), 1e-3)
        # Limits
        assert np.allclose(ax.get_xlim(), ax2.get_xlim())
        assert np.allclose(ax.get_ylim(), ax2.get_ylim())
        # Image state
        assert im.get_cmap().name == im2.get_cmap().name
        assert np.allclose(np.array(im.get_clim()), np.array(im2.get_clim()))
        assert cbar.ax.get_ylabel() == cbar2.ax.get_ylabel()
        # EC pane basics
        assert ec2 is not None
        assert ec_ax.get_xlabel() == ec2.get_xlabel()
        # Y label is mode-dependent; in 'time' should match
        assert ec_ax.yaxis.label.get_text() == ec2.yaxis.label.get_text()
        assert np.allclose(ec_ax.get_xlim(), ec2.get_xlim())
        assert np.allclose(ec_ax.get_ylim(), ec2.get_ylim())
        plt.close(fig); plt.close(fig2)
    print("  OK")


def main():
    # Paths available in workspace for CSV
    csv_dqdv = os.path.join(os.getcwd(), 'RA_B076.csv')
    if not os.path.isfile(csv_dqdv):
        print("Warning: RA_B076.csv not found; skipping dQ/dV.")
    verify_ec_gc()
    if os.path.isfile(csv_dqdv):
        verify_dqdv(csv_dqdv)
    verify_cpc()
    verify_operando()
    print("All round-trip checks passed.")


if __name__ == '__main__':
    main()
