"""Run from this directory. Relative paths are shared with the RTL testbench."""
from pathlib import Path
import sys
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import welch

OUT = Path("out")
OUT.mkdir(exist_ok=True)
N, CP, FS = 512, 32, 7.68e6
BINS = np.r_[-48:0, 1:49]
STRIDE = N + CP


def transmit(seed, count=64):
    rng = np.random.default_rng(seed)
    grid = np.zeros((count, N), complex)
    levels = [-3, -1, 1, 3]
    shape = (count, len(BINS))
    grid[:, BINS] = rng.choice(levels, shape) + 1j * rng.choice(levels, shape)
    td = np.fft.ifft(grid, axis=1)
    scale = 0.25 / np.sqrt(np.mean(abs(td)**2))
    x = np.column_stack((td[:, -CP:], td)).ravel() * scale
    return x, grid[:, BINS] * scale


def receive(y):
    useful = y.reshape(-1, STRIDE)[:, CP:]
    return np.fft.fft(useful, axis=1)[:, BINS]


def pa(u, compression):
    prev = np.r_[0j, u[:-1]]
    return u / (1 + compression * abs(u)**2) + (0.04+0.02j)*prev*abs(prev)**2


def basis(s):
    prev = np.r_[0j, s[:-1]]
    return np.column_stack([z*abs(z)**p for z in (s, prev) for p in (0, 2, 4)])


def fit(u, y):
    return np.linalg.lstsq(basis(y)[1:], u[1:], rcond=None)[0]


def spectrum(y):
    f, power = welch(y, fs=FS, nperseg=2048, return_onesided=False)
    return np.fft.fftshift(f), np.fft.fftshift(power)


def metrics(y, ref):
    recovered = receive(y)
    evm = 100 * np.linalg.norm(recovered-ref) / np.linalg.norm(ref)
    f, psd = spectrum(y)
    def band(center):
        return psd[abs(f-center) <= 0.75e6].sum()
    leakage = [10*np.log10(band(0)/band(c)) for c in (-1.5e6, 1.5e6)]
    return evm, *leakage, np.mean(abs(y)**2)


def quant(z, frac):
    iq = np.column_stack((z.real, z.imag))
    raw = np.rint(iq * (1 << frac))
    if np.any((raw < -32768) | (raw > 32767)):
        raise ValueError("Input or coefficient outside its signed 16-bit format")
    return raw.astype(np.int64)


def fixed(iq, coeff):
    prev = np.vstack(([0, 0], iq[:-1]))
    acc_i = np.zeros(len(iq), np.int64)
    acc_q = np.zeros_like(acc_i)
    for tap, data in enumerate((iq, prev)):
        i, q = data.T
        r = (i*i + q*q) >> 14
        for order in range(3):
            cr, ci = coeff[tap*3 + order]
            acc_i += i*cr - q*ci
            acc_q += i*ci + q*cr
            if order < 2:
                i, q = (i*r) >> 14, (q*r) >> 14
    raw = np.column_stack((acc_i, acc_q)) >> 12
    return np.clip(raw, -32768, 32767), np.count_nonzero((raw < -32768)|(raw > 32767))


def complex_iq(iq):
    return (iq[:, 0] + 1j*iq[:, 1]) / 16384


def write_hex(name, iq):
    words = ((iq[:, 1] & 65535) << 16) | (iq[:, 0] & 65535)
    (OUT/name).write_text("".join(f"{int(word):08x}\n" for word in words))


def main():
    train, _ = transmit(1)
    coeff = fit(train, pa(train, 0.60))
    x, ref = transmit(2)
    assert np.allclose(receive(x), ref)
    iq, cq = quant(x, 14), quant(coeff, 12)
    expected, clips = fixed(iq, cq)
    u = complex_iq(expected)
    plots = [("desired", x), ("bypass", pa(x, 0.60)),
             ("float", pa(basis(x) @ coeff, 0.60)), ("fixed", pa(u, 0.60))]
    print("Case         EVM %    ACLR L    ACLR R    output power (relative linear)")
    for name, signal in plots:
        print(f"{name:10s}", " ".join(f"{v:9.4f}" for v in metrics(signal, ref)))
    print("Clipped output components:", clips)
    print("Coefficient pairs, Re and Im:", cq.tolist())
    write_hex("input.hex", iq)
    write_hex("coeff.hex", cq)
    write_hex("expected.hex", expected)
    fig, ax = plt.subplots(1, 3, figsize=(14, 4), layout="constrained")
    for name, signal in plots:
        f, psd = spectrum(signal)
        ax[0].plot(f/1e6, 10*np.log10(np.maximum(psd, 1e-30)), label=name)
    ax[0].set(xlabel="Frequency (MHz)", ylabel="PSD (dB per Hz, relative)", title="Output spectrum")
    ax[0].legend()
    for name, signal in (plots[1], plots[3]):
        ax[1].scatter(abs(x[::16]), abs(signal[::16]), s=2, alpha=.4, label=name)
        symbols = receive(signal)[:6].ravel()
        ax[2].scatter(symbols.real, symbols.imag, s=3, alpha=.4, label=name)
    ax[1].set(xlabel="Desired amplitude", ylabel="PA output amplitude", title="Gain compression")
    ax[2].set(xlabel="I", ylabel="Q", title="Recovered 16-QAM", aspect="equal")
    for a in ax[1:]:
        a.legend()
    fig.savefig(OUT/"signal_plots.png", dpi=150)
    # Independent training and probe captures. Each capture starts with zero history.
    # Refitting the active PA requires its actual predistorted drive as the target.
    capture, _ = transmit(3)
    capture_words, _ = fixed(quant(capture, 14), cq)
    drive = complex_iq(capture_words)
    new_coeff = fit(drive, pa(drive, 0.90))
    probe, probe_ref = transmit(4)
    for label, compression, c in [("A trained", .60, coeff), ("B frozen", .90, coeff),
                                  ("B updated", .90, new_coeff)]:
        out, _ = fixed(quant(probe, 14), quant(c, 12))
        print(label, metrics(pa(complex_iq(out), compression), probe_ref))
    if "--rtl" in sys.argv:
        words = np.array([int(v, 16) for v in (OUT/"rtl.hex").read_text().splitlines()])
        actual = np.column_stack((words & 65535, words >> 16)).astype(np.int16)
        np.testing.assert_array_equal(actual, expected)
        print("RTL through PA:", metrics(pa(complex_iq(actual), .60), ref))


if __name__ == "__main__":
    main()
