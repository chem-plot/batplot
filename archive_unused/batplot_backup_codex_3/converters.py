"""Data conversion utilities for batplot.

This module provides functions to convert X-ray diffraction data between
different representations, primarily from angle-based (2θ) to momentum
transfer (Q) space.

Conversion formulas:
    Q = (4π sin(θ)) / λ
    where θ = 2θ/2 (half the diffraction angle)
          λ = X-ray wavelength in Angstroms
"""

from __future__ import annotations

import os
import numpy as np


def convert_to_qye(filenames, wavelength: float):
    """Convert 2θ-based XRD files to Q-based .qye files.
    
    Reads files with columns: 2θ (degrees), intensity, [optional: error]
    Converts 2θ to Q using Bragg's law with given wavelength.
    Saves output alongside input with .qye extension.
    
    This is useful for:
    - Comparing data from different wavelengths
    - Pair Distribution Function (PDF) analysis
    - Direct comparison with simulation data in Q-space
    
    Args:
        filenames: List of file paths to convert
        wavelength: X-ray wavelength in Angstroms (e.g., 0.6199 for synchrotron,
                   1.5406 for Cu Kα, 0.7093 for Mo Kα)
    
    Output format:
        Q (Å⁻¹)  Intensity  [Error]
        Header includes wavelength used for conversion
        
    Example:
        >>> convert_to_qye(['data.xy'], wavelength=1.5406)
        Saved data.qye
    """
    for fname in filenames:
        # Check if input file exists
        if not os.path.isfile(fname):
            print(f"File not found: {fname}")
            continue
        
        # Read data (skip lines starting with #)
        try:
            data = np.loadtxt(fname, comments="#")
        except Exception as e:
            print(f"Error reading {fname}: {e}")
            continue
        
        # Ensure data is 2D array (handle single-row files)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        
        # Validate data format: need at least 2 columns (x, y)
        if data.shape[1] < 2:
            print(f"Invalid data format in {fname}")
            continue
        
        # Extract columns
        x, y = data[:, 0], data[:, 1]  # 2θ (degrees), intensity
        e = data[:, 2] if data.shape[1] >= 3 else None  # Optional: error bars
        
        # Convert 2θ to Q
        # Step 1: Get θ (half of 2θ) and convert to radians
        theta_rad = np.radians(x / 2)
        
        # Step 2: Apply formula Q = 4π sin(θ) / λ
        q = 4 * np.pi * np.sin(theta_rad) / wavelength
        
        # Prepare output data (Q, intensity, [error])
        if e is None:
            out_data = np.column_stack((q, y))
        else:
            out_data = np.column_stack((q, y, e))
        
        # Generate output filename (same basename, .qye extension)
        base, _ = os.path.splitext(fname)
        out_fname = f"{base}.qye"
        
        # Save with header documenting the conversion
        np.savetxt(out_fname, out_data, fmt="% .6f",
                   header=f"# Converted from {fname} using λ={wavelength} Å")
        print(f"Saved {out_fname}")


__all__ = ["convert_to_qye"]
