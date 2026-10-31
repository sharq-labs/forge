"""Opt-in Linux root adversarial check: kill a worker with a live isolated child."""
import multiprocessing as mp
import os
import pathlib
import sys
import time
import subprocess

from benchmarks.genesis_lite import isolated_host as ih


def busy_arm(card, client, *, seed=0):
    subprocess.Popen([sys.executable, "-c", "import os,time; os.setsid(); time.sleep(60)"])
    client.observe(card["universe_id"], {"busy": 1})
    time.sleep(60)  # deliberately never reads stdin; EOF must not be the cleanup mechanism
    return {"answer": "no_law"}


def worker(pipe):
    host = ih.IsolatedProposerHost(ih.hidden_paths())
    class Client:
        def observe(self, *args, **kwargs):
            from benchmarks.genesis_lite.telemetry_v4 import tree_pids
            pipe.send((tree_pids(host._proc.pid), host.outside))
            return {"observation": {}}
    host.propose("tools.genesis_performance.check_deadline:busy_arm", {"universe_id": "public-busy"}, 0, Client())


def main():
    assert ih.support()[0], "requires Linux root isolation deployment"
    parent, child = mp.get_context("spawn").Pipe()
    process = mp.get_context("spawn").Process(target=worker, args=(child,))
    process.start()
    assert parent.poll(10), "worker did not verify its proposer"
    descendants, outside = parent.recv()
    assert ih.verified(outside)
    process.kill()
    process.join(5)
    end = time.monotonic() + 5
    while time.monotonic() < end:
        live = []
        for pid in descendants:
            try:
                state = pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
                if state != "Z":
                    live.append(pid)
            except FileNotFoundError:
                pass
        if not live:
            print("PASS: killed campaign left no live namespace init, busy proposer or detached child; outside verification passed")
            return
        time.sleep(0.05)
    for pid in live:
        os.kill(pid, 9)
    raise AssertionError(f"parent-death chain failed: {live}")


if __name__ == "__main__":
    main()
