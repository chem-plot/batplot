# Manual figure manifest

Wavelengths: TD_R* = 0.259 Å (synchrotron); TD_S0062-64 / Operando TD_S0034 = 1.54 Å (Cu)
PNG max width: 900px (CSS also limits display size)

| PNG | Status | Description |
|-----|--------|-------------|
| `manual-batch-ec-1.png` | OK | batch B443 |
| `manual-batch-ec-2.png` | OK | batch B444 |
| `manual-batch-ec-3.png` | OK | batch B445 |
| `manual-ec-cpc-multi.png` | OK | multi CPC |
| `manual-ec-cpc.png` | OK | --cpc |
| `manual-ec-dqdv.png` | OK | --dqdv |
| `manual-ec-gc-mpt.png` | OK | TD_O2.mpt --gc |
| `manual-ec-gc-multi.png` | OK | multi GC |
| `manual-ec-gc.png` | OK | B443 --gc |
| `manual-ec-time.png` | OK | --xaxis time |
| `manual-histo.png` | OK | histogram |
| `manual-op-cif.png` | OK | operando + CIF |
| `manual-op-contour.png` | OK | operando --wl 1.54 |
| `manual-util-convert.png` | OK | converted R02.qye |
| `manual-xy-2theta.png` | OK | Cu XRD 2θ TD_S0062-64 |
| `manual-xy-cif-2theta.png` | OK | CIF in 2θ |
| `manual-xy-cif.png` | OK | stack + CIF |
| `manual-xy-deriv.png` | OK | XAS --1d |
| `manual-xy-norm.png` | OK | --norm --wl 0.259 |
| `manual-xy-overlay-mixed-wl.png` | OK | Cu+synchrotron mixed λ |
| `manual-xy-overlay-same-wl.png` | OK | TD_R02+R03 --wl 0.259 |
| `manual-xy-q-suffix.png` | OK | TD_S0062-64.xy:1.54 |
| `manual-xy-q.png` | OK | Cu XRD → Q TD_S0062-64 --wl 1.54 |
| `manual-xy-qye.png` | OK | R02.qye |
| `manual-xy-readcol-multi.png` | OK | readcol 1 2-4 |
| `manual-xy-readcol.png` | OK | readcol 1 4 |
| `manual-xy-reproj.png` | OK | TD_R02.dat:0.259:1.54 |
| `manual-xy-ry.png` | OK | dual y --ry |
| `manual-xy-stack.png` | OK | TD_R stack --wl 0.259 |
| `manual-xy-xas.png` | OK | XAS energy |

Regenerate: `MPLBACKEND=Agg python scripts/capture_manual_figures.py`
