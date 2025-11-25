"""Data conversion utilities for batplot.

This module provides functions to convert X-ray diffraction data between
different representations, primarily from angle-based (2θ) to momentum
transfer (Q) space.

WHY CONVERT BETWEEN 2θ AND Q?
-----------------------------
X-ray diffraction data can be represented in two ways:

1. **2θ space (angle-based)**: Traditional representation in degrees
   - Pros: Directly matches experimental setup (detector angle)
   - Cons: Depends on X-ray wavelength (different wavelengths = different scales)
   - Example: Peak at 2θ = 20° for Cu Kα (λ=1.5406 Å)

2. **Q space (momentum transfer)**: Physical quantity independent of wavelength
   - Pros: Universal scale (same Q value regardless of wavelength)
   - Cons: Requires wavelength to convert
   - Example: Peak at Q = 2.0 Å⁻¹ (same for any wavelength)

Converting to Q-space is useful for:
- Comparing data from different X-ray sources (synchrotron vs lab)
- Pair Distribution Function (PDF) analysis (requires Q-space)
- Direct comparison with theoretical calculations (often in Q-space)
- Combining datasets from different experiments

CONVERSION FORMULA:
------------------
The conversion uses Bragg's law:
    Q = (4π sin(θ)) / λ
    
Where:
    - Q: Momentum transfer in Å⁻¹
    - θ: Half of the diffraction angle (2θ/2) in radians
    - λ: X-ray wavelength in Angstroms

Physical meaning:
    - Q represents the momentum transferred from X-ray to sample
    - Higher Q = smaller d-spacing (shorter distances in crystal)
    - Q is proportional to sin(θ), so it increases non-linearly with angle
"""

from __future__ import annotations

import os
import numpy as np


def convert_to_qye(filenames, wavelength: float):
    """
    Convert 2θ-based XRD files to Q-based .qye files.
    
    HOW IT WORKS:
    ------------
    This function reads XRD data files that have 2θ (two-theta) angles as the
    x-axis and converts them to Q-space (momentum transfer). The conversion
    process:
    
    1. Read input file (2θ in degrees, intensity, optional error bars)
    2. Convert 2θ to θ (half-angle): θ = 2θ / 2
    3. Convert θ from degrees to radians: θ_rad = θ × π/180
    4. Apply conversion formula: Q = 4π sin(θ_rad) / λ
    5. Save output as .qye file (Q, intensity, [error])
    
    INPUT FORMAT:
    ------------
    Expected columns in input file:
    - Column 1: 2θ values in degrees (e.g., 10.0, 10.1, 10.2, ...)
    - Column 2: Intensity values (e.g., 100, 150, 200, ...)
    - Column 3 (optional): Error bars (e.g., 5, 7, 10, ...)
    
    OUTPUT FORMAT:
    -------------
    Saved .qye file contains:
    - Column 1: Q values in Å⁻¹ (momentum transfer)
    - Column 2: Intensity values (unchanged)
    - Column 3 (if present): Error bars (unchanged)
    - Header comment: Documents conversion parameters
    
    WAVELENGTH VALUES:
    -----------------
    Common X-ray wavelengths:
    - Cu Kα: 1.5406 Å (most common lab source)
    - Mo Kα: 0.7093 Å (higher energy, shorter wavelength)
    - Synchrotron: 0.6199 Å (or other, depends on beamline)
    - Co Kα: 1.7889 Å
    - Fe Kα: 1.9360 Å
    
    Args:
        filenames: List of file paths to convert (e.g., ['data.xy', 'pattern.xye'])
        wavelength: X-ray wavelength in Angstroms (Å)
                   Examples:
                   - 1.5406 for Cu Kα (most common)
                   - 0.7093 for Mo Kα
                   - 0.6199 for synchrotron
    
    Output:
        Creates .qye files alongside input files with same basename.
        Example: data.xy → data.qye
        
    Example:
        >>> # Convert Cu Kα data to Q-space
        >>> convert_to_qye(['pattern.xy'], wavelength=1.5406)
        Saved pattern.qye
        
        >>> # Convert multiple files from synchrotron
        >>> convert_to_qye(['scan1.xy', 'scan2.xy'], wavelength=0.6199)
        Saved scan1.qye
        Saved scan2.qye
    """
    # ====================================================================
    # PROCESS EACH FILE
    # ====================================================================
    # Loop through each input file and convert it to Q-space.
    # Each file is processed independently (errors in one don't stop others).
    # ====================================================================
    for fname in filenames:
        # STEP 1: Validate file exists
        if not os.path.isfile(fname):
            print(f"File not found: {fname}")
            continue  # Skip this file, continue with next
        
        # STEP 2: Read data from file
        # np.loadtxt() reads numeric data, skipping lines starting with '#'
        # This handles comment lines in data files
        try:
            data = np.loadtxt(fname, comments="#")
        except Exception as e:
            print(f"Error reading {fname}: {e}")
            continue  # Skip if file can't be read
        
        # STEP 3: Ensure data is 2D array (handle edge cases)
        # Some files might have only one row, which numpy reads as 1D array
        # We reshape to 2D so indexing works consistently
        if data.ndim == 1:
            data = data.reshape(1, -1)  # Reshape to (1, n_columns)
        
        # STEP 4: Validate data format
        # Need at least 2 columns: x (2θ) and y (intensity)
        if data.shape[1] < 2:
            print(f"Invalid data format in {fname}: need at least 2 columns (x, y)")
            continue
        
        # STEP 5: Extract columns
        x = data[:, 0]  # 2θ values in degrees (first column)
        y = data[:, 1]  # Intensity values (second column)
        e = data[:, 2] if data.shape[1] >= 3 else None  # Error bars (third column, optional)
        
        # ====================================================================
        # STEP 6: CONVERT 2θ TO Q
        # ====================================================================
        # This is the core conversion using Bragg's law.
        #
        # Mathematical steps:
        # 1. Get θ (half-angle): θ = 2θ / 2
        #    Example: 2θ = 20° → θ = 10°
        #
        # 2. Convert to radians: θ_rad = θ × (π/180)
        #    Example: θ = 10° → θ_rad = 0.1745 radians
        #    (NumPy's np.radians() does this conversion)
        #
        # 3. Apply conversion formula: Q = 4π sin(θ_rad) / λ
        #    Example: θ_rad = 0.1745, λ = 1.5406 Å
        #             Q = 4π sin(0.1745) / 1.5406 = 1.42 Å⁻¹
        #
        # Why sin(θ)?
        # The momentum transfer Q is proportional to sin(θ), not θ itself.
        # This is because diffraction follows a sine relationship (Bragg's law).
        # ====================================================================
        
        # Get θ (half of 2θ) and convert to radians
        # x contains 2θ values in degrees, so x/2 gives θ in degrees
        theta_rad = np.radians(x / 2)  # Convert degrees to radians
        
        # Apply conversion formula: Q = 4π sin(θ) / λ
        # This gives Q in units of Å⁻¹ (inverse Angstroms)
        q = 4 * np.pi * np.sin(theta_rad) / wavelength
        
        # STEP 7: Prepare output data
        # Combine Q, intensity, and optional error bars into output array
        if e is None:
            # No error bars: output has 2 columns (Q, intensity)
            out_data = np.column_stack((q, y))
        else:
            # With error bars: output has 3 columns (Q, intensity, error)
            out_data = np.column_stack((q, y, e))
        
        # STEP 8: Generate output filename
        # Replace input extension with .qye
        # Example: data.xy → data.qye, pattern.xye → pattern.qye
        base, _ = os.path.splitext(fname)
        out_fname = f"{base}.qye"
        
        # STEP 9: Save converted data
        # Save with:
        # - Header comment documenting the conversion (wavelength used)
        # - 6 decimal places precision (sufficient for most XRD data)
        # - Space-padded format for readability
        np.savetxt(out_fname, out_data, fmt="% .6f",
                   header=f"# Converted from {fname} using λ={wavelength} Å")
        print(f"Saved {out_fname}")


__all__ = ["convert_to_qye"]
