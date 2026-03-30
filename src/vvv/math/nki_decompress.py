import numpy as np
from numba import njit

@njit
def nki_private_decompress(src, org_size, nki_mode):
    """
    JIT-compiled NKI decompression algorithm.
    Runs at native C++ speeds.
    """
    dest = np.empty(org_size, dtype=np.int16)
    src_idx = 0
    dest_idx = 0

    # 1. Skip Header
    if nki_mode == 1 or nki_mode == 3:
        src_idx += 8
    elif nki_mode == 2 or nki_mode == 4:
        src_idx += 20
    else:
        return dest

        # 2. Read first pixel (Little-endian 16-bit)
    val = np.int16(src[src_idx] | (src[src_idx+1] << 8))
    dest[dest_idx] = val
    dest_idx += 1
    src_idx += 2

    npixels = org_size - 1

    # 3. Main Decompression Loop
    while npixels > 0 and src_idx < len(src):
        val_u8 = src[src_idx]
        val_i8 = np.int8(val_u8)
        val_int = int(val_i8) # Sign-extend to match C++ 'int' cast

        if -64 <= val_int <= 63:
            # Mode 1: 7-bit diff
            dest[dest_idx] = dest[dest_idx-1] + val_int
            dest_idx += 1
            src_idx += 1
            npixels -= 1

        elif val_u8 == 0x7f:
            # Mode 3: 16-bit absolute (Big Endian)
            v1 = int(src[src_idx+1])
            v2 = int(src[src_idx+2])
            dest[dest_idx] = np.int16((v1 << 8) + v2)
            dest_idx += 1
            src_idx += 3
            npixels -= 1

        elif val_u8 == 0x80:
            # Mode 2: Run length encoding (Zeros)
            run = int(src[src_idx+1])
            src_idx += 2
            npixels -= run
            for _ in range(run):
                dest[dest_idx] = dest[dest_idx-1]
                dest_idx += 1

        elif (nki_mode == 3 or nki_mode == 4) and val_u8 == 0xc0:
            # Mode 2: 4-bit encoding
            run = int(src[src_idx+1])
            src_idx += 2
            npixels -= run

            half_run = run // 2
            for _ in range(half_run):
                v_i8 = np.int8(src[src_idx])
                src_idx += 1
                v_int2 = int(v_i8)

                # First 4 bits
                dest[dest_idx] = dest[dest_idx-1] + (v_int2 >> 4)
                dest_idx += 1

                # Second 4 bits
                if v_int2 & 8:
                    v_int2 |= -16  # Bitwise equivalent of C++ 0xfffffff0
                else:
                    v_int2 &= 0x0f

                dest[dest_idx] = dest[dest_idx-1] + v_int2
                dest_idx += 1

        else:
            # Mode 2: 15-bit diff
            diff = np.int16(((val_int ^ 0x40) << 8) + int(src[src_idx+1]))
            dest[dest_idx] = dest[dest_idx-1] + diff
            dest_idx += 1
            src_idx += 2
            npixels -= 1

    return dest