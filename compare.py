"""Floating-point screening experiment. Sets the same average PA output power."""
from itertools import combinations
import numpy as np
from experiment import transmit, basis, pa, metrics

def cross_basis(z, subset):
    prev = np.r_[0j, z[:-1]]
    candidates = [z*abs(prev)**2, z*abs(prev)**4,
                  prev*abs(z)**2, prev*abs(z)**4]
    return np.column_stack([basis(z)] + [candidates[i] for i in subset])

def amplifier(z):
    prev = np.r_[0j, z[:-1]]
    return pa(z, 0.60) + (0.12+0.09j)*z*abs(prev)**2

def evaluate(x, ref, c, subset):
    target = np.mean(abs(amplifier(x))**2)
    def output(scale):
        desired = x*scale
        return amplifier(cross_basis(desired, subset) @ c)
    lo, hi = 0.6, 1.4
    assert np.mean(abs(output(lo))**2) < target < np.mean(abs(output(hi))**2)
    for _ in range(24):
        scale = (lo+hi)/2
        y = output(scale)
        if np.mean(abs(y)**2) < target:
            lo = scale
        else:
            hi = scale
    # Remove one constant complex gain for this matched-power experiment.
    gain = np.vdot(x,y)/np.vdot(x,x)
    evm, left, right, _ = metrics(y/gain, ref)
    return evm, left, right, np.mean(abs(y)**2)

if __name__ == "__main__":
    train, _ = transmit(10, 20)
    val, val_ref = transmit(11, 20)
    test, test_ref = transmit(12, 20)
    observed = amplifier(train)
    def learn(subset):
        return np.linalg.lstsq(cross_basis(observed,subset)[1:],train[1:],rcond=None)[0]
    pairs = list(combinations(range(4),2))
    # Selection criterion declared in advance: lowest validation EVM.
    best = min(pairs,key=lambda group: evaluate(val,val_ref,learn(group),group)[0])
    print("Test: model, selected terms, EVM %, ACLR L/R dB, output mean power")
    y = amplifier(test)
    gain = np.vdot(test,y)/np.vdot(test,test)
    print("Bypass", *metrics(y/gain, test_ref)[:3], np.mean(abs(y)**2))
    for name, subset in [("MP",()), ("four cross terms",(0,1,2,3)), ("selected pair",best)]:
        print(name, subset, *evaluate(test,test_ref,learn(subset),subset))
