"""Host-controlled burst adaptation with the compiled RTL simulator in the loop."""
from pathlib import Path
import subprocess
import numpy as np
from experiment import (OUT, transmit, fit, pa, metrics, quant, fixed,
                        write_hex, complex_iq)

def run_burst(x, coeff):
    iq, cq = quant(x, 14), quant(coeff, 12)
    expected, clips = fixed(iq, cq)
    print("Clipped output components in this burst:", clips)
    write_hex("input.hex", iq)
    write_hex("coeff.hex", cq)
    write_hex("expected.hex", expected)
    subprocess.run([str(Path("obj_dir/Vtb").resolve())], check=True,
                   stdout=subprocess.DEVNULL)
    words = np.loadtxt(OUT/"rtl.hex", dtype=str)
    raw = np.array([int(word, 16) for word in words])
    iq_out = np.column_stack((raw & 65535, raw >> 16)).astype(np.int16)
    np.testing.assert_array_equal(iq_out, expected)
    return complex_iq(iq_out)

if __name__ == "__main__":
    train, _ = transmit(1)
    c_a = fit(train, pa(train, .60))
    capture, _ = transmit(3)
    u_capture = run_burst(capture, c_a)
    y_capture = pa(u_capture, .90)
    c_b = fit(u_capture, y_capture)
    probe, ref = transmit(4)
    for name, c, k in [("A trained", c_a, .60), ("B frozen", c_a, .90),
                       ("B updated", c_b, .90)]:
        y = pa(run_burst(probe,c), k)
        print(name, "EVM %, ACLR L/R dB, relative power:", *metrics(y,ref))
