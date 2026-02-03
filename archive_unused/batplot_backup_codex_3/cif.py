"""CIF parsing and simple powder pattern simulation utilities."""

from __future__ import annotations

import numpy as np
import re


def _atomic_number_table():
    elements = [
        'H','He','Li','Be','B','C','N','O','F','Ne','Na','Mg','Al','Si','P','S','Cl','Ar','K','Ca','Sc','Ti','V','Cr','Mn','Fe','Co','Ni','Cu','Zn','Ga','Ge','As','Se','Br','Kr','Rb','Sr','Y','Zr','Nb','Mo','Tc','Ru','Rh','Pd','Ag','Cd','In','Sn','Sb','Te','I','Xe','Cs','Ba','La','Ce','Pr','Nd','Pm','Sm','Eu','Gd','Tb','Dy','Ho','Er','Tm','Yb','Lu','Hf','Ta','W','Re','Os','Ir','Pt','Au','Hg','Tl','Pb','Bi','Po','At','Rn'
    ]
    return {el:i+1 for i,el in enumerate(elements)}


def _parse_cif_basic(fname):
    cell = {'a':None,'b':None,'c':None,'alpha':None,'beta':None,'gamma':None,'space_group':None}
    atoms = []
    sym_ops = []
    atom_headers = []
    in_atom_loop = False
    def _clean_num(tok: str):
        t = tok.strip().strip("'\"")
        t = re.sub(r"\([0-9]+\)$", "", t)
        return t
    with open(fname,'r',encoding='utf-8',errors='ignore') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'): continue
            low = line.lower()
            if low.startswith('_space_group_name_h-m_alt') or low.startswith('_symmetry_space_group_name_h-m'):
                parts=line.split()
                if len(parts)>=2:
                    cell['space_group']=parts[1].strip("'\"")
            if low.startswith('_cell_length_a'):
                try:
                    cell['a']=float(_clean_num(line.split()[1]))
                except Exception:
                    pass
            elif low.startswith('_cell_length_b'):
                try:
                    cell['b']=float(_clean_num(line.split()[1]))
                except Exception:
                    pass
            elif low.startswith('_cell_length_c'):
                try:
                    cell['c']=float(_clean_num(line.split()[1]))
                except Exception:
                    pass
            elif low.startswith('_cell_angle_alpha'):
                try:
                    cell['alpha']=float(_clean_num(line.split()[1]))
                except Exception:
                    pass
            elif low.startswith('_cell_angle_beta'):
                try:
                    cell['beta']=float(_clean_num(line.split()[1]))
                except Exception:
                    pass
            elif low.startswith('_cell_angle_gamma'):
                try:
                    cell['gamma']=float(_clean_num(line.split()[1]))
                except Exception:
                    pass
            if line.lower().startswith('loop_'):
                in_atom_loop=False; atom_headers=[]; continue
            if line.lower().startswith('_space_group_symop_operation_xyz'): continue
            if line.lower().startswith('_atom_site_'):
                atom_headers.append(line)
                if any(h.lower().startswith('_atom_site_fract_x') for h in atom_headers) and \
                   any(h.lower().startswith('_atom_site_fract_y') for h in atom_headers) and \
                   any(h.lower().startswith('_atom_site_fract_z') for h in atom_headers):
                    in_atom_loop=True
                continue
            if (len(atom_headers)==1 and atom_headers[0].lower().startswith('_space_group_symop_operation_xyz') and not line.startswith('_') and ',' in line):
                sym_ops.append(line.strip().strip("'\"")); continue
            if in_atom_loop and not line.startswith('_'):
                toks=line.split();
                if len(toks)<4: continue
                header_map={h.lower():i for i,h in enumerate(atom_headers)}
                def gidx(prefix):
                    for h,i in header_map.items():
                        if h.startswith(prefix): return i
                    return None
                ix=gidx('_atom_site_fract_x'); iy=gidx('_atom_site_fract_y'); iz=gidx('_atom_site_fract_z')
                isym=gidx('_atom_site_type_symbol'); ilab=gidx('_atom_site_label')
                iocc=gidx('_atom_site_occupancy'); iuiso=gidx('_atom_site_u_iso') or gidx('_atom_site_u_iso_or_equiv') or gidx('_atom_site_u_equiv')
                try:
                    x=float(_clean_num(toks[ix])) if ix is not None else 0.0
                    y=float(_clean_num(toks[iy])) if iy is not None else 0.0
                    z=float(_clean_num(toks[iz])) if iz is not None else 0.0
                except: continue
                if isym is not None and isym < len(toks):
                    sym=re.sub(r'[^A-Za-z].*','',toks[isym])
                elif ilab is not None and ilab < len(toks):
                    sym=re.sub(r'[^A-Za-z].*','',toks[ilab])
                else: sym='X'
                if iocc is not None and iocc < len(toks):
                    try:
                        occ=float(_clean_num(toks[iocc]))
                    except Exception:
                        occ=1.0
                else: occ=1.0
                if iuiso is not None and iuiso < len(toks):
                    try:
                        Uiso=float(_clean_num(toks[iuiso]))
                    except Exception:
                        Uiso=None
                else: Uiso=None
                atoms.append((sym,x,y,z,occ,Uiso))
    if any(v is None for v in cell.values()):
        raise ValueError(f"Incomplete cell parameters in CIF {fname}")
    if not atoms: raise ValueError(f"No atoms parsed from CIF {fname}")
    if sym_ops:
        seen=set(); expanded=[]
        if not any(op.replace(' ','') in ('x,y,z','x,y,z,') for op in sym_ops): sym_ops.append('x, y, z')
        def eval_coord(expr,x,y,z):
            expr=expr.strip().lower().replace(' ','')
            if not re.match(r'^[xyz0-9+\-*/().,/]*$',expr): return x
            try: return eval(expr,{"__builtins__":{}},{'x':x,'y':y,'z':z})%1.0
            except: return x
        for sym,x,y,z,occ,Uiso in atoms:
            for op in sym_ops:
                parts=op.strip().strip("'\"").split(',')
                if len(parts)!=3: continue
                nx=eval_coord(parts[0],x,y,z); ny=eval_coord(parts[1],x,y,z); nz=eval_coord(parts[2],x,y,z)
                key=(round(nx,4),round(ny,4),round(nz,4),sym)
                if key in seen: continue
                seen.add(key); expanded.append((sym,nx,ny,nz,occ,Uiso))
        if expanded: atoms=expanded
    return cell, atoms


def simulate_cif_pattern_Q(fname, Qmax=10.0, dQ=0.002, peak_width=0.01,
                           wavelength=1.5406, space_group_hint=None):
    # Simplified import from monolithic file; unchanged logic.
    cell, atoms = _parse_cif_basic(fname)
    if space_group_hint is None:
        space_group_hint = cell.get('space_group')
    a, b, c = cell['a'], cell['b'], cell['c']
    alpha = np.deg2rad(cell['alpha']); beta = np.deg2rad(cell['beta']); gamma = np.deg2rad(cell['gamma'])
    a_vec = np.array([a, 0, 0], dtype=float)
    b_vec = np.array([b * np.cos(gamma), b * np.sin(gamma), 0], dtype=float)
    c_x = c * np.cos(beta)
    c_y = c * (np.cos(alpha) - np.cos(beta) * np.cos(gamma)) / np.sin(gamma)
    c_z = np.sqrt(max(c ** 2 - c_x ** 2 - c_y ** 2, 1e-12))
    c_vec = np.array([c_x, c_y, c_z], dtype=float)
    A = np.column_stack([a_vec, b_vec, c_vec])
    V = np.dot(a_vec, np.cross(b_vec, c_vec))
    if abs(V) < 1e-10:
        raise ValueError('Invalid cell volume')
    B = 2 * np.pi * np.linalg.inv(A).T
    b1, b2, b3 = B[:, 0], B[:, 1], B[:, 2]
    a_star = np.linalg.norm(b1); b_star = np.linalg.norm(b2); c_star = np.linalg.norm(b3)
    hmax = max(1, int(np.ceil(Qmax / a_star)))
    kmax = max(1, int(np.ceil(Qmax / b_star)))
    lmax = max(1, int(np.ceil(Qmax / c_star)))
    Zmap = _atomic_number_table()
    CM_COEFFS = {
        'C':  ([2.3100, 1.0200, 1.5886, 0.8650], [20.8439, 10.2075, 0.5687, 51.6512], 0.2156),
        'N':  ([12.2126, 3.1322, 2.0125, 1.1663], [0.0057, 9.8933, 28.9975, 0.5826], -11.5290),
        'O':  ([3.0485, 2.2868, 1.5463, 0.8670], [13.2771, 5.7011, 0.3239, 32.9089], 0.2508),
        'Si': ([6.2915, 3.0353, 1.9891, 1.5410], [2.4386, 32.3337, 0.6785, 81.6937], 1.1407),
        'Fe': ([11.7695, 7.3573, 3.5222, 2.3045], [4.7611, 0.3072, 15.3535, 76.8805], 1.0369),
        'Ni': ([12.8376, 7.2920, 4.4438, 2.3800], [3.8785, 0.2565, 13.5290, 71.1692], 1.0341),
        'Cu': ([13.3380, 7.1676, 5.6158, 1.6735], [3.5828, 0.2470, 11.3966, 64.8126], 1.1910),
        'Se': ([19.3319, 8.8752, 2.6959, 1.2199], [6.4000, 1.4838, 19.9887, 55.4486], 1.1053),
    }
    def form_factor(sym, Q):
        s2 = (Q / (4 * np.pi)) ** 2
        if sym in CM_COEFFS:
            a, b, c = CM_COEFFS[sym]
            f = c
            for ai, bi in zip(a, b):
                f += ai * np.exp(-bi * s2)
            return max(f, 0.0)
        Z = Zmap.get(sym, 10)
        return Z * np.exp(-0.002 * Q * Q)
    atom_data = []
    for sym, x, y, z, occ, Uiso in _parse_cif_basic(fname)[1]:
        sym_cap = sym.capitalize()
        Biso = 8 * np.pi ** 2 * Uiso if Uiso is not None else 0.0
        atom_data.append((sym_cap, x, y, z, occ, Biso))
    def extinct(h, k, l, sg):
        if not sg: return False
        sg0 = sg.lower()[0]
        if sg0 == 'p': return False
        if sg0 == 'i': return (h + k + l) % 2 != 0
        if sg0 == 'f':
            all_even = (h % 2 == 0) and (k % 2 == 0) and (l % 2 == 0)
            all_odd = (h % 2 != 0) and (k % 2 != 0) and (l % 2 != 0)
            return not (all_even or all_odd)
        if sg0 == 'c': return (h + k) % 2 != 0
        if sg0 == 'r': return ((-h + k + l) % 3) != 0
        return False
    refl_map = {}
    lam = wavelength if wavelength else 1.5406
    for h in range(-hmax, hmax + 1):
        for k in range(-kmax, kmax + 1):
            for l in range(-lmax, lmax + 1):
                if h == 0 and k == 0 and l == 0: continue
                if extinct(h, k, l, space_group_hint): continue
                G = h * b1 + k * b2 + l * b3
                Q = np.linalg.norm(G)
                if Q <= 0 or Q > Qmax: continue
                s = (Q * lam) / (4 * np.pi)
                if s <= 0 or s >= 1: continue
                theta = np.arcsin(s)
                s2 = (Q / (4 * np.pi)) ** 2
                phases = []
                weights = []
                for sym_cap, ax, ay, az, occ, Biso in atom_data:
                    phase = 2 * np.pi * (h * ax + k * ay + l * az)
                    f0 = form_factor(sym_cap, Q)
                    if f0 <= 1e-8: continue
                    dw = np.exp(-Biso * s2) if Biso > 0 else 1.0
                    w = f0 * occ * dw
                    if w <= 0: continue
                    phases.append(phase)
                    weights.append(w)
                if not weights: continue
                weights = np.array(weights); phases = np.array(phases)
                F = np.sum(weights * np.exp(1j * phases))
                I = (F.real ** 2 + F.imag ** 2)
                if I <= 1e-14: continue
                cos_2theta = np.cos(2 * theta)
                sin_theta_sq = np.sin(theta) ** 2
                sin_2theta = np.sin(2 * theta)
                if sin_theta_sq <= 0 or sin_2theta <= 1e-12: continue
                lp = (1 + cos_2theta ** 2) / (sin_theta_sq * sin_2theta)
                qkey = round(Q, 5)
                refl_map[qkey] = refl_map.get(qkey, 0.0) + I * lp
    if not refl_map:
        raise ValueError('No reflections in range')
    refl_items = sorted(refl_map.items())
    refl_Q = np.array([k for k, _ in refl_items])
    refl_I = np.array([v for _, v in refl_items])
    Q_grid = np.arange(0, Qmax + dQ * 0.5, dQ)
    intens = np.zeros_like(Q_grid)
    for q, I in zip(refl_Q, refl_I):
        sigma = peak_width * (0.6 + 0.4 * q / Qmax)
        intens += I * np.exp(-0.5 * ((Q_grid - q) / sigma) ** 2)
    if intens.max() > 0:
        intens /= intens.max()
    return Q_grid, intens


def cif_reflection_positions(fname, Qmax=10.0, wavelength=1.5406, space_group_hint=None):
    cell, atoms = _parse_cif_basic(fname)
    if space_group_hint is None:
        space_group_hint = cell.get('space_group')
    a,b,c = cell['a'], cell['b'], cell['c']
    alpha = np.deg2rad(cell['alpha']); beta = np.deg2rad(cell['beta']); gamma = np.deg2rad(cell['gamma'])
    a_vec = np.array([a,0,0]); b_vec = np.array([b*np.cos(gamma), b*np.sin(gamma), 0])
    c_x = c*np.cos(beta); c_y = c*(np.cos(alpha)-np.cos(beta)*np.cos(gamma))/np.sin(gamma)
    c_z = np.sqrt(max(c**2 - c_x**2 - c_y**2, 1e-12))
    c_vec = np.array([c_x,c_y,c_z])
    A = np.column_stack([a_vec,b_vec,c_vec])
    V = np.dot(a_vec, np.cross(b_vec, c_vec))
    if abs(V) < 1e-10:
        return []
    B = 2*np.pi * np.linalg.inv(A).T
    b1,b2,b3 = B[:,0],B[:,1],B[:,2]
    a_star,b_star,c_star = np.linalg.norm(b1), np.linalg.norm(b2), np.linalg.norm(b3)
    hmax = max(1,int(np.ceil(Qmax/a_star)))
    kmax = max(1,int(np.ceil(Qmax/b_star)))
    lmax = max(1,int(np.ceil(Qmax/c_star)))
    def extinct(h,k,l,sg):
        if not sg: return False
        c0 = sg.lower()[0]
        if c0=='i': return (h+k+l)%2!=0
        if c0=='f':
            all_even=(h%2==0 and k%2==0 and l%2==0); all_odd=(h%2!=0 and k%2!=0 and l%2!=0)
            return not (all_even or all_odd)
        if c0=='c': return (h+k)%2!=0
        if c0=='r': return ((-h+k+l)%3)!=0
        return False
    lam = wavelength
    refl=set()
    for h in range(-hmax,hmax+1):
        for k in range(-kmax,kmax+1):
            for l in range(-lmax,lmax+1):
                if h==k==l==0: continue
                if extinct(h,k,l,space_group_hint): continue
                G = h*b1 + k*b2 + l*b3
                Q = np.linalg.norm(G)
                if Q<=0 or Q>Qmax: continue
                if lam is not None:
                    s = (Q*lam)/(4*np.pi)
                    if s<=0 or s>=1: continue
                q_round = round(Q,6)
                refl.add(q_round)
    return sorted(refl)


# --- New helpers for hkl labeling ---
def list_reflections_with_hkl(fname, Qmax=10.0, wavelength=1.5406, space_group_hint=None):
    """Return a list of (Q_rounded, h, k, l) for reflections up to Qmax.

    When wavelength is None, do not apply Bragg cutoff (enumerate by Q only).
    Q values are rounded to 6 decimals to group symmetrically equivalent sets.
    """
    cell, _atoms = _parse_cif_basic(fname)
    if space_group_hint is None:
        space_group_hint = cell.get('space_group')
    a,b,c = cell['a'], cell['b'], cell['c']
    alpha = np.deg2rad(cell['alpha']); beta = np.deg2rad(cell['beta']); gamma = np.deg2rad(cell['gamma'])
    a_vec = np.array([a,0,0]); b_vec = np.array([b*np.cos(gamma), b*np.sin(gamma), 0])
    c_x = c*np.cos(beta); c_y = c*(np.cos(alpha)-np.cos(beta)*np.cos(gamma))/np.sin(gamma)
    c_z = np.sqrt(max(c**2 - c_x**2 - c_y**2, 1e-12))
    c_vec = np.array([c_x,c_y,c_z])
    A = np.column_stack([a_vec,b_vec,c_vec])
    V = np.dot(a_vec, np.cross(b_vec, c_vec))
    if abs(V) < 1e-10:
        return []
    B = 2*np.pi * np.linalg.inv(A).T
    b1,b2,b3 = B[:,0],B[:,1],B[:,2]
    a_star,b_star,c_star = np.linalg.norm(b1), np.linalg.norm(b2), np.linalg.norm(b3)
    hmax = max(1,int(np.ceil(Qmax/a_star)))
    kmax = max(1,int(np.ceil(Qmax/b_star)))
    lmax = max(1,int(np.ceil(Qmax/c_star)))
    def extinct(h,k,l,sg):
        if not sg: return False
        c0 = sg.lower()[0]
        if c0=='i': return (h+k+l)%2!=0
        if c0=='f':
            all_even=(h%2==0 and k%2==0 and l%2==0); all_odd=(h%2!=0 and k%2!=0 and l%2!=0)
            return not (all_even or all_odd)
        if c0=='c': return (h+k)%2!=0
        if c0=='r': return ((-h+k+l)%3)!=0
        return False
    lam = wavelength
    hkl_list = []
    for h in range(-hmax,hmax+1):
        for k in range(-kmax,kmax+1):
            for l in range(-lmax,lmax+1):
                if h==k==l==0: continue
                if extinct(h,k,l,space_group_hint): continue
                G = h*b1 + k*b2 + l*b3
                Q = np.linalg.norm(G)
                if Q<=0 or Q>Qmax: continue
                if lam is not None:
                    s = (Q*lam)/(4*np.pi)
                    if s<=0 or s>=1: continue
                q_round = round(Q,6)
                hkl_list.append((q_round, h, k, l))
    # de-duplicate identical entries
    seen = set(); uniq = []
    for item in hkl_list:
        if item in seen: continue
        seen.add(item); uniq.append(item)
    return uniq


def build_hkl_label_map_from_list(hkl_list):
    """Build a dict Q-> "(h k l), (h k l), ..." using canonical positive indices if present.

    This mirrors the prior UI labeling convention.
    """
    by_q = {}
    for q,h,k,l in hkl_list:
        # canonicalize sign: prefer non-negative if possible for readability
        if h<0 or (h==0 and k<0) or (h==0 and k==0 and l<0):
            h,k,l = -h,-k,-l
        by_q.setdefault(q,set()).add((h,k,l))
    label_map = {}
    for q, triples in by_q.items():
        ordered = sorted(triples)
        nonneg_all = [t for t in ordered if t[0] >= 0 and t[1] >= 0 and t[2] >= 0]
        use_list = nonneg_all if nonneg_all else ordered
        label_map[q] = ", ".join(f"({h} {k} {l})" for h,k,l in use_list)
    return label_map


def build_hkl_label_map(fname, Qmax=10.0, wavelength=1.5406, space_group_hint=None):
    """Convenience: compute label map directly from a CIF file."""
    hkl_list = list_reflections_with_hkl(fname, Qmax=Qmax, wavelength=wavelength, space_group_hint=space_group_hint)
    return build_hkl_label_map_from_list(hkl_list)
