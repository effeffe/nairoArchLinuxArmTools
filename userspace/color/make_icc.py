#!/usr/bin/env python3
"""Write an ICC v2.4 matrix/TRC display profile from chromaticities."""
import struct, sys

def xy_to_XYZ(x, y, Y=1.0):
    return [x / y * Y, Y, (1 - x - y) / y * Y]

def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

def mat_vec(a, v):
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]

def inv(m):
    a, b, c = m[0]; d, e, f = m[1]; g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]

def s15f16(v):
    return struct.pack('>i', int(round(v * 65536)))

def xyz_tag(X):
    return b'XYZ ' + b'\0' * 4 + b''.join(s15f16(v) for v in X)

def curv_gamma(g):
    return b'curv' + b'\0' * 4 + struct.pack('>I', 1) + struct.pack('>H', int(round(g * 256))) + b'\0\0'

def desc_tag(text):
    t = text.encode('ascii') + b'\0'
    return (b'desc' + b'\0' * 4 + struct.pack('>I', len(t)) + t +
            struct.pack('>II', 0, 0) + struct.pack('>HB', 0, 0) + b'\0' * 67)

def text_tag(text):
    return b'text' + b'\0' * 4 + text.encode('ascii') + b'\0'

def sf32_tag(m):
    return b'sf32' + b'\0' * 4 + b''.join(s15f16(v) for row in m for v in row)

def vcgt_tag(gains, gamma, n=256):
    """Per-channel table: scale linear light by gain, on gamma-encoded values."""
    out = b'vcgt' + b'\0' * 4 + struct.pack('>I', 0) + struct.pack('>HHH', 3, n, 2)
    for g in gains:
        k = g ** (1 / gamma)
        out += b''.join(struct.pack('>H', int(round(min(1.0, i / (n - 1) * k) * 65535))) for i in range(n))
    return out

def native_gains(prim, white, target):
    """RGB gains that turn the panel's native white into the target white."""
    W = xy_to_XYZ(*white)
    P = [xy_to_XYZ(*p) for p in prim]
    Pm = [[P[j][i] for j in range(3)] for i in range(3)]
    S = mat_vec(inv(Pm), W)
    M = [[Pm[i][j] * S[j] for j in range(3)] for i in range(3)]
    rgb = mat_vec(inv(M), xy_to_XYZ(*target))
    m = max(rgb)
    return [v / m for v in rgb]

def make(prim, white, gamma, lum, name, cprt, vcgt=None):
    D50 = [0.9642, 1.0, 0.8249]
    W = xy_to_XYZ(*white)
    P = [xy_to_XYZ(*p) for p in prim]          # columns R, G, B
    Pm = [[P[j][i] for j in range(3)] for i in range(3)]
    S = mat_vec(inv(Pm), W)
    M = [[Pm[i][j] * S[j] for j in range(3)] for i in range(3)]   # RGB -> XYZ, white Y=1
    brad = [[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]]
    cs, cd = mat_vec(brad, W), mat_vec(brad, D50)
    chad = mat_mul(inv(brad), mat_mul([[cd[0] / cs[0], 0, 0], [0, cd[1] / cs[1], 0], [0, 0, cd[2] / cs[2]]], brad))
    M50 = mat_mul(chad, M)
    cols = [[M50[i][j] for i in range(3)] for j in range(3)]
    tags = [
        (b'desc', desc_tag(name)),
        (b'cprt', text_tag(cprt)),
        (b'wtpt', xyz_tag(D50)),
        (b'rXYZ', xyz_tag(cols[0])),
        (b'gXYZ', xyz_tag(cols[1])),
        (b'bXYZ', xyz_tag(cols[2])),
        (b'rTRC', curv_gamma(gamma)),
        (b'gTRC', curv_gamma(gamma)),
        (b'bTRC', curv_gamma(gamma)),
        (b'lumi', xyz_tag([0, lum, 0])),
        (b'chad', sf32_tag(chad)),
    ]
    if vcgt:
        tags.append((b'vcgt', vcgt_tag(vcgt, gamma)))
    off = 128 + 4 + 12 * len(tags)
    table, data = b'', b''
    for sig, body in tags:
        while (off + len(data)) % 4:
            data += b'\0'
        table += sig + struct.pack('>II', off + len(data), len(body))
        data += body
    body = struct.pack('>I', len(tags)) + table + data
    size = 128 + len(body)
    hdr = (struct.pack('>I', size) + b'none' + bytes([2, 0x40, 0, 0]) + b'mntr' + b'RGB ' + b'XYZ ' +
           struct.pack('>6H', 2026, 10, 11, 0, 0, 0) + b'acsp' + b'\0' * 4 + struct.pack('>I', 0) +
           b'\0' * 4 + b'\0' * 4 + b'\0' * 8 + struct.pack('>I', 0) +
           b''.join(s15f16(v) for v in D50) + b'\0' * 4 + b'\0' * 16 + b'\0' * 28)
    assert len(hdr) == 128
    return hdr + body, M, chad

if __name__ == '__main__':
    prim = [(0.640, 0.340), (0.310, 0.600), (0.160, 0.060)]
    native, d65 = (0.290, 0.310), (0.3127, 0.3290)
    gains = native_gains(prim, native, d65)
    # The profile describes the panel after the vcgt: D65 white, same primaries
    data, M, chad = make(prim=prim, white=d65, gamma=2.2, lum=420.0 * gains[1],
                         name='Motorola moto g 5G plus (Tianma NT36672C, design values, D65)',
                         cprt='Generated from the downstream panel description; no warranty',
                         vcgt=gains)
    open(sys.argv[1], 'wb').write(data)
    print('wrote', sys.argv[1], len(data), 'bytes; RGB gains to D65: %.3f %.3f %.3f' % tuple(gains))
