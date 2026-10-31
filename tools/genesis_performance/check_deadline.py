"""Opt-in Linux root adversarial check: kill a worker with a live isolated child."""
import multiprocessing as mp
import os
import pathlib
import sys
import time

from benchmarks.genesis_lite import isolated_host as ih


def worker(pipe):
    host = ih.IsolatedProposerHost(ih.hidden_paths())
    pipe.send((host._proc.pid, ih._leaf(host._proc.pid), host.outside))
    time.sleep(60)


def main():
    assert ih.support()[0], "requires Linux root isolation deployment"
    parent, child = mp.get_context("spawn").Pipe()
    process = mp.get_context("spawn").Process(target=worker, args=(child,))
    process.start()
    assert parent.poll(10), "worker did not verify its proposer"
    launcher, leaf, outside = parent.recv()
    assert ih.verified(outside)
    process.kill()
    process.join(5)
    end = time.monotonic() + 5
    while time.monotonic() < end:
        live = []
        for pid in (launcher, leaf):
            try:
                state = pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
                if state != "Z":
                    live.append(pid)
            except FileNotFoundError:
                pass
        if not live:
            print("PASS: killed campaign left no live launcher/proposer; outside verification passed")
            return
        time.sleep(0.05)
    for pid in live:
        os.kill(pid, 9)
    raise AssertionError(f"parent-death chain failed: {live}")


if __name__ == "__main__":
    main()
