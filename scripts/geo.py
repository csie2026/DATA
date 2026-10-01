"""Shared paths and projections (moved out of archive/build_mountains.py)."""
import math, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)

# Transverse Mercator on GRS80 (Snyder series). pyproj's DLL is blocked by Windows app control here.
# GRS80 vs WGS84 differ < 1 mm, so lon/lat output is treated as WGS84.
A_ = 6378137.0
F_ = 1 / 298.257222101
E2 = 2 * F_ - F_ ** 2
EP2 = E2 / (1 - E2)
TM = {5179: (127.5, 38.0, 0.9996, 1_000_000.0, 2_000_000.0),  # UTM-K
      5186: (127.0, 38.0, 1.0, 200_000.0, 600_000.0)}         # 중부원점 (GRS80)


def _m(phi):
    e4, e6 = E2 ** 2, E2 ** 3
    return A_ * ((1 - E2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                 - (3 * E2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
                 + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
                 - (35 * e6 / 3072) * math.sin(6 * phi))


def tm_forward(epsg, lon, lat):
    lon0, lat0, k0, fe, fn = TM[epsg]
    phi, lam = math.radians(lat), math.radians(lon - lon0)
    n = A_ / math.sqrt(1 - E2 * math.sin(phi) ** 2)
    t, c, a = math.tan(phi) ** 2, EP2 * math.cos(phi) ** 2, lam * math.cos(phi)
    x = fe + k0 * n * (a + (1 - t + c) * a ** 3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * EP2) * a ** 5 / 120)
    y = fn + k0 * (_m(phi) - _m(math.radians(lat0)) + n * math.tan(phi) * (
        a * a / 2 + (5 - t + 9 * c + 4 * c * c) * a ** 4 / 24 + (61 - 58 * t + t * t + 600 * c - 330 * EP2) * a ** 6 / 720))
    return x, y


def tm_inverse(epsg, x, y):
    lon0, lat0, k0, fe, fn = TM[epsg]
    mu = (_m(math.radians(lat0)) + (y - fn) / k0) / (A_ * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    c1, t1 = EP2 * math.cos(p1) ** 2, math.tan(p1) ** 2
    n1 = A_ / math.sqrt(1 - E2 * math.sin(p1) ** 2)
    r1 = A_ * (1 - E2) / (1 - E2 * math.sin(p1) ** 2) ** 1.5
    d = (x - fe) / (n1 * k0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * EP2) * d ** 4 / 24
                                           + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * EP2 - 3 * c1 * c1) * d ** 6 / 720)
    lon = (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * EP2 + 24 * t1 * t1) * d ** 5 / 120) / math.cos(p1)
    return lon0 + math.degrees(lon), math.degrees(lat)


to_wgs_5179 = lambda x, y: tm_inverse(5179, x, y)
to_5179_from_wgs = lambda lon, lat: tm_forward(5179, lon, lat)
to_5179_from_5186 = lambda x, y: tm_forward(5179, *tm_inverse(5186, x, y))


def check():
    assert all(abs(v - w) < 1e-6 for v, w in zip(tm_forward(5179, 127.5, 38.0), (1_000_000, 2_000_000)))
    for epsg in TM:
        for lon, lat in [(126.78, 37.49), (127.4, 37.9), (126.5, 37.0)]:
            lo, la = tm_inverse(epsg, *tm_forward(epsg, lon, lat))
            assert abs(lo - lon) < 1e-8 and abs(la - lat) < 1e-8, (epsg, lon, lat, lo, la)


if __name__ == "__main__":
    check()
    print("ok")
