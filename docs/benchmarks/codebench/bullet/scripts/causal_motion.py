"""Per-body motion in the causal variant: first frame a body leaves its start by >2 mm, z history, tilt."""
import sys
import numpy as np

ROOT = "C:/Users/kuock/source/repos/4DVisWorld-Infra/docs/benchmarks/codebench/"


def tilt(q):
    w, x, y, z = q
    return np.degrees(np.arccos(np.clip(1 - 2 * (x * x + y * y), -1, 1)))


for lab in sys.argv[1:] or ["bullet", "bullet_orig"]:
    for case in ["B_01", "B_03"]:
        try:
            d = np.load(f"{ROOT}{lab}/{case}_poses.npz")
        except FileNotFoundError:
            continue
        keys = sorted(k for k in d.files if k.startswith("causal/"))
        print(f"== {lab} {case} causal")
        rows = []
        for k in keys:
            p = d[k].astype(float)
            dis = np.linalg.norm(p[:, :3] - p[0, :3], axis=1)
            if dis.max() < 1e-6:
                continue
            first = int(np.argmax(dis > 0.002)) if (dis > 0.002).any() else -1
            rows.append((k[7:], first, dis[1], dis.max(), p[1, 2] - p[0, 2], tilt(p[-1, 3:])))
        rows.sort(key=lambda r: (r[1] if r[1] >= 0 else 999))
        for r in rows[:14]:
            print("  %-8s first>2mm=%4d  d(f1)=%.4f  max=%.3f  dz(f1)=%+.4f  tilt_end=%.1f" % r)
