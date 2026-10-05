#!/usr/bin/env python3
"""Deterministic UCI pondering protocol validation.

Uses "go ponder nodes 1" so the search itself finishes almost immediately.
The engine must nevertheless HOLD bestmove until stop/ponderhit.
"""
from __future__ import annotations

import argparse
import os
import queue
import threading
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def engine_path(profile: str) -> Path:
    d = ROOT / "engine" / "c" / f"zchezz_{profile}"
    for name in ("zchezz.exe", "zchezz"):
        p = d / name
        if p.is_file():
            return p
    raise FileNotFoundError(d)


class Uci:
    def __init__(self, exe: Path):
        self.p = subprocess.Popen(
            [str(exe)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert self.p.stdin and self.p.stdout
        self.lines: queue.Queue[str] = queue.Queue()
        self.reader = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader.start()

    def _reader_loop(self) -> None:
        assert self.p.stdout
        for line in self.p.stdout:
            self.lines.put(line.strip())

    def send(self, line: str) -> None:
        assert self.p.stdin
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def read_for(self, seconds: float) -> list[str]:
        end = time.monotonic() + seconds
        out: list[str] = []
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            try:
                out.append(self.lines.get(timeout=min(remaining, 0.05)))
            except queue.Empty:
                pass
        return out

    def read_until(self, prefix: str, timeout: float) -> tuple[str, list[str]]:
        end = time.monotonic() + timeout
        out: list[str] = []
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            try:
                line = self.lines.get(timeout=min(remaining, 0.05))
            except queue.Empty:
                continue
            out.append(line)
            if line.startswith(prefix):
                return line, out
        raise AssertionError(f"timeout waiting for {prefix!r}; output tail={out[-20:]}")

    def close(self) -> None:
        if self.p.poll() is None:
            try:
                self.send("quit")
                self.p.wait(timeout=2)
            except Exception:
                self.p.kill()
                self.p.wait(timeout=2)


def no_bestmove(lines: list[str], where: str) -> None:
    bad = [x for x in lines if x.startswith("bestmove ")]
    if bad:
        raise AssertionError(f"premature bestmove during {where}: {bad}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, choices=("v331", "v507"))
    args = ap.parse_args()

    u = Uci(engine_path(args.profile))
    try:
        u.send("uci")
        u.read_until("uciok", 3)
        u.send("setoption name Ponder value true")
        u.send("isready")
        u.read_until("readyok", 3)

        # Case 1: the node-limited ponder search completes internally, but UCI
        # requires its bestmove to remain held until STOP.
        u.send("position startpos")
        u.send("go ponder nodes 1")
        held = u.read_for(0.35)
        no_bestmove(held, "completed ponder before stop")
        u.send("stop")
        stopped, stop_lines = u.read_until("bestmove ", 3)
        if not stopped.startswith("bestmove "):
            raise AssertionError(stopped)
        extra = u.read_for(0.20)
        no_bestmove(extra, "after stop bestmove")

        # Case 2: on PONDERHIT the held ponder result itself must be suppressed;
        # cmd_go resumes from the warm TT and only the resumed search may emit.
        u.send("position startpos")
        u.send("go ponder nodes 1")
        held2 = u.read_for(0.35)
        no_bestmove(held2, "completed ponder before ponderhit")
        t0 = time.monotonic()
        u.send("ponderhit")
        hit_move, hit_lines = u.read_until("bestmove ", 3)
        dt = time.monotonic() - t0
        if not hit_move.startswith("bestmove "):
            raise AssertionError(hit_move)
        # There must not be a second bestmove from the held ponder search.
        extra2 = u.read_for(0.25)
        no_bestmove(extra2, "after ponderhit resumed bestmove")

        print(
            f"PONDER_PROTOCOL_OK profile={args.profile} "
            f"stop={stopped.split()[1]} hit={hit_move.split()[1]} "
            f"ponderhit_to_bestmove_ms={dt*1000:.1f}"
        )
        return 0
    finally:
        u.close()


if __name__ == "__main__":
    raise SystemExit(main())
