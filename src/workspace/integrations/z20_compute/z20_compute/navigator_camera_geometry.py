"""Centered sensor window for square-pixel 640x720 stereo half frames."""
from math import gcd


def crop_plan(*, output=(640, 720)):
    """Crop the vendor 2624x1944 window rather than squeeze its full field.

    Bounds are exclusive. OV5640 end registers use inclusive coordinates.
    The old per-mode calibration is invalid after this window change.
    """
    if (len(output) != 2 or any(type(v) is not int or v <= 0 for v in output)):
        raise ValueError('output must have two positive integer dimensions')
    width, height = output
    divisor = gcd(width, height)
    rw, rh = width//divisor, height//divisor
    factor = min(2624//rw, 1944//rh)
    # Even crop dimensions and starts retain the Bayer/binning phase.
    factor -= factor % 2
    crop_width, crop_height = rw*factor, rh*factor
    if not factor or crop_width < width or crop_height < height:
        raise ValueError('output is too large for an aspect-preserving sensor crop')
    x0 = ((2624-crop_width)//2)//2*2
    y0 = 4+((1944-crop_height)//2)//2*2
    x1, y1 = x0+crop_width, y0+crop_height
    registers = []
    for address, value in ((0x3800,x0),(0x3802,y0),(0x3804,x1-1),(0x3806,y1-1)):
        registers.extend(((address,value>>8),(address+1,value&255)))
    return dict(mode='navigator-centered-portrait-{}x{}-v1'.format(width,height),
                output=list(output),window=[x0,y0,x1,y1],registers=registers,
                calibration_reusable=False)
