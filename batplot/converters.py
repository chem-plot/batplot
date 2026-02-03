"""Data conversion utilities for batplot.

This module provides functions to convert X-ray diffraction data between
different representations, primarily from angle-based (2θ) to momentum
transfer (Q) space, and between different wavelengths.

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

CONVERSION FORMULAS:
-------------------
The conversion uses Bragg's law:
    Q = (4π sin(θ)) / λ
    
Where:
    - Q: Momentum transfer in Å⁻¹
    - θ: Half of the diffraction angle (2θ/2) in radians
    - λ: X-ray wavelength in Angstroms

To convert from Q back to 2θ:
    2θ = 2 × arcsin(Q × λ / (4π)) × (180/π)
    
Physical meaning:
    - Q represents the momentum transferred from X-ray to sample
    - Higher Q = smaller d-spacing (shorter distances in crystal)
    - Q is proportional to sin(θ), so it increases non-linearly with angle
"""

from __future__ import annotations

import os
import numpy as np


def convert_xrd_data(filenames, from_param: str, to_param: str):
    """
    Convert XRD data files between different representations.
    
    This function handles three conversion modes:
    1. Wavelength-to-wavelength: Convert 2θ values from one wavelength to another
    2. Wavelength-to-Q: Convert 2θ (with given wavelength) to Q space
    3. Q-to-wavelength: Convert Q space to 2θ (with given wavelength)
    
    HOW IT WORKS:
    ------------
    The function reads input files, determines the conversion type based on
    the from/to parameters, applies the appropriate conversion formula, and
    saves the converted data to a new 'converted' subfolder.
    
    CONVERSION MODES:
    ----------------
    1. Wavelength-to-wavelength (e.g., --convert 1.54 0.25):
       - Input: 2θ values measured with wavelength1
       - Process: Convert 2θ → Q using wavelength1, then Q → 2θ using wavelength2
       - Output: 2θ values for wavelength2
       
    2. Wavelength-to-Q (e.g., --convert 1.54 q):
       - Input: 2θ values measured with given wavelength
       - Process: Convert 2θ → Q using the wavelength
       - Output: Q values (Å⁻¹)
       
    3. Q-to-wavelength (e.g., --convert q 1.54):
       - Input: Q values (Å⁻¹)
       - Process: Convert Q → 2θ using the given wavelength
       - Output: 2θ values for the given wavelength
    
    Args:
        filenames: List of file paths to convert (e.g., ['data.xy', 'pattern.xye'])
        from_param: Source parameter - either a wavelength (float as string) or 'q'
        to_param: Target parameter - either a wavelength (float as string) or 'q'
    
    Output:
        Creates converted files in a 'converted' subfolder within the directory
        containing the input files. Files keep their original names but may have
        different extensions (.qye for Q-space, original extension for 2θ).
        
    Example:
        >>> # Convert 2θ from Cu Kα (1.54 Å) to Mo Kα (0.709 Å)
        >>> convert_xrd_data(['pattern.xy'], '1.54', '0.709')
        Saved converted/pattern.xy
        
        >>> # Convert 2θ to Q space
        >>> convert_xrd_data(['pattern.xy'], '1.54', 'q')
        Saved converted/pattern.qye
        
        >>> # Convert Q to 2θ
        >>> convert_xrd_data(['pattern.qye'], 'q', '1.54')
        Saved converted/pattern.xy
    """
    # Parse parameters
    try:
        from_is_q = (from_param.lower() == 'q')
        to_is_q = (to_param.lower() == 'q')
        
        if from_is_q:
            from_wl = None
        else:
            from_wl = float(from_param)
            
        if to_is_q:
            to_wl = None
        else:
            to_wl = float(to_param)
    except ValueError:
        print(f"Error: Invalid conversion parameters. Expected wavelengths (numbers) or 'q', got '{from_param}' and '{to_param}'")
        return
    
    # Determine conversion type
    if not from_is_q and not to_is_q:
        # Wavelength-to-wavelength conversion
        conversion_type = "wavelength_to_wavelength"
    elif not from_is_q and to_is_q:
        # Wavelength-to-Q conversion
        conversion_type = "wavelength_to_q"
    elif from_is_q and not to_is_q:
        # Q-to-wavelength conversion
        conversion_type = "q_to_wavelength"
    else:
        print("Error: Cannot convert Q to Q (no conversion needed)")
        return
    
    # Process each file
    for fname in filenames:
        # Validate file exists
        if not os.path.isfile(fname):
            print(f"File not found: {fname}")
            continue
        
        # Read data from file
        try:
            data = np.loadtxt(fname, comments="#")
        except Exception as e:
            print(f"Error reading {fname}: {e}")
            continue
        
        # Ensure data is 2D array
        if data.ndim == 1:
            data = data.reshape(1, -1)
        
        # Validate data format
        if data.shape[1] < 2:
            print(f"Invalid data format in {fname}: need at least 2 columns (x, y)")
            continue
        
        # Extract columns
        x = data[:, 0]  # X values (2θ or Q)
        y = data[:, 1]  # Intensity values
        e = data[:, 2] if data.shape[1] >= 3 else None  # Error bars (optional)
        
        # Perform conversion based on type
        if conversion_type == "wavelength_to_wavelength":
            # Step 1: Convert 2θ (from_wl) → Q
            theta_rad = np.radians(x / 2)  # Convert 2θ to θ in radians
            q = 4 * np.pi * np.sin(theta_rad) / from_wl
            
            # Step 2: Convert Q → 2θ (to_wl)
            # Q = 4π sin(θ) / λ, so sin(θ) = Q × λ / (4π)
            # θ = arcsin(Q × λ / (4π))
            # 2θ = 2 × θ × (180/π)
            sin_theta = q * to_wl / (4 * np.pi)
            # Clamp sin_theta to valid range [-1, 1] to avoid domain errors
            sin_theta = np.clip(sin_theta, -1.0, 1.0)
            theta_rad_new = np.arcsin(sin_theta)
            x_new = 2 * np.degrees(theta_rad_new)  # Convert to 2θ in degrees
            output_ext = os.path.splitext(fname)[1]  # Keep original extension
            
        elif conversion_type == "wavelength_to_q":
            # Convert 2θ → Q
            theta_rad = np.radians(x / 2)  # Convert 2θ to θ in radians
            x_new = 4 * np.pi * np.sin(theta_rad) / from_wl
            output_ext = ".qye"
            
        elif conversion_type == "q_to_wavelength":
            # Convert Q → 2θ
            # Q = 4π sin(θ) / λ, so sin(θ) = Q × λ / (4π)
            sin_theta = x * to_wl / (4 * np.pi)
            # Clamp sin_theta to valid range [-1, 1] to avoid domain errors
            sin_theta = np.clip(sin_theta, -1.0, 1.0)
            theta_rad = np.arcsin(sin_theta)
            x_new = 2 * np.degrees(theta_rad)  # Convert to 2θ in degrees
            output_ext = ".xy"
        
        # Prepare output data
        if e is None:
            out_data = np.column_stack((x_new, y))
        else:
            out_data = np.column_stack((x_new, y, e))
        
        # Create output directory (converted subfolder)
        input_dir = os.path.dirname(os.path.abspath(fname))
        if not input_dir:
            input_dir = os.getcwd()
        output_dir = os.path.join(input_dir, "converted")
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate output filename
        base = os.path.basename(os.path.splitext(fname)[0])
        output_fname = os.path.join(output_dir, f"{base}{output_ext}")
        
        # Create header comment
        if conversion_type == "wavelength_to_wavelength":
            header = f"# Converted from {os.path.basename(fname)}: 2θ (λ={from_wl} Å) → Q → 2θ (λ={to_wl} Å)"
        elif conversion_type == "wavelength_to_q":
            header = f"# Converted from {os.path.basename(fname)}: 2θ (λ={from_wl} Å) → Q"
        else:  # q_to_wavelength
            header = f"# Converted from {os.path.basename(fname)}: Q → 2θ (λ={to_wl} Å)"
        
        # Save converted data
        try:
            # Use UTF-8 encoding to support Greek letters (θ) in headers on all platforms
            np.savetxt(output_fname, out_data, fmt="% .6f", header=header, encoding='utf-8')
            print(f"Saved {output_fname}")
        except Exception as e:
            print(f"Error saving {output_fname}: {e}")


def convert_to_qye(filenames, wavelength: float):
    """
    Convert 2θ-based XRD files to Q-based .qye files.
    
    This is a legacy function maintained for backward compatibility.
    For new code, use convert_xrd_data() instead.
    
    Args:
        filenames: List of file paths to convert (e.g., ['data.xy', 'pattern.xye'])
        wavelength: X-ray wavelength in Angstroms (Å)
    
    Output:
        Creates .qye files alongside input files with same basename.
        Example: data.xy → data.qye
    """
    # Convert to new format: wavelength to Q
    convert_xrd_data(filenames, str(wavelength), 'q')


__all__ = ["convert_xrd_data", "convert_to_qye"]
