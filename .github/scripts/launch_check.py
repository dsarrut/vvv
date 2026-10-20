"""Start the installed `vvv` command on a small image and check it keeps running.

Usage: python launch_check.py [seconds]
Fails (exit 1) if vvv exits early or prints a traceback.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
import SimpleITK as sitk

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
exe = shutil.which("vvv")
if exe is None:
    sys.exit("vvv command not found on PATH")

work = tempfile.mkdtemp()
img_path = os.path.join(work, "small.nii.gz")
arr = np.random.default_rng(0).integers(-100, 100, (40, 64, 64)).astype(np.int16)
img = sitk.GetImageFromArray(arr)
img.SetSpacing((1.0, 1.0, 2.0))
sitk.WriteImage(img, img_path)

env = dict(os.environ, HOME=work, USERPROFILE=work)  # fresh settings / history
p = subprocess.Popen([exe, img_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True)
t0 = time.time()
while time.time() - t0 < seconds and p.poll() is None:
    time.sleep(0.2)
alive = p.poll() is None
if alive:
    p.terminate()
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        p.kill()
out = p.stdout.read()
print(out)
if not alive:
    sys.exit(f"vvv exited after {time.time() - t0:.1f} s with code {p.returncode}")
if "Traceback" in out:
    sys.exit("vvv printed a traceback")
print(f"OK: vvv ran for {seconds:.0f} s without error")
