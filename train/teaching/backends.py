"""Long-lived UCI teacher backends used by the teaching pipeline."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MATE_CP = 30000


@dataclass
class SearchLine:
    move: str
    cp_white: int
    multipv: int = 1


class UciBackend:
    """Raw UCI client optimized for many positions per process.

    Stockfish's non-standard ``eval`` command is supported, as is Zchezz's
    compact ``info string eval <cp> cp`` response.  ``static_eval`` always
    returns a WHITE-relative score regardless of the engine's native eval
    convention. If an engine exposes neither form, it falls back to a tiny
    fixed-node search. Search/MultiPV remains available for refinement.
    """

    def __init__(self, path: str | Path, hash_mb: int = 16, threads: int = 1,
                 static_fallback_nodes: int = 1):
        self.path = str(path)
        self.static_fallback_nodes = max(1, int(static_fallback_nodes))
        self.p = subprocess.Popen(
            [self.path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            encoding="utf-8", errors="replace")
        self._send("uci")
        self._drain_until("uciok")
        self._send(f"setoption name Threads value {max(1, int(threads))}")
        self._send(f"setoption name Hash value {max(1, int(hash_mb))}")
        self._send("setoption name UCI_ShowWDL value false")
        self._ready()
        self._static_supported: bool | None = None
        self._static_style: str | None = None

    def _send(self, line: str) -> None:
        if self.p.poll() is not None:
            raise RuntimeError(f"engine exited with code {self.p.returncode}: {self.path}")
        assert self.p.stdin is not None
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def _readline(self) -> str:
        assert self.p.stdout is not None
        line = self.p.stdout.readline()
        if line == "" and self.p.poll() is not None:
            raise RuntimeError(f"engine exited while waiting for output: {self.path}")
        return line.rstrip("\r\n")

    def _drain_until(self, token: str) -> list[str]:
        lines = []
        while True:
            line = self._readline()
            lines.append(line)
            if token in line:
                return lines

    def _ready(self) -> None:
        self._send("isready")
        self._drain_until("readyok")

    @staticmethod
    def _mate_to_cp(mate: int) -> int:
        if mate == 0:
            return 0
        return (1 if mate > 0 else -1) * max(25000, MATE_CP - abs(mate) * 10)

    def static_eval(self, fen: str, white_to_move: bool) -> int:
        if self._static_supported is False:
            lines = self.search(fen, white_to_move,
                                nodes=self.static_fallback_nodes, multipv=1)
            return lines[0].cp_white if lines else 0

        self._send(f"position fen {fen}")
        self._send("eval")
        value = None
        unknown = False
        style = None
        # Stockfish prints a verbose table ending in "Final evaluation".
        # Zchezz prints one compact STM-relative line:
        #     info string eval <signed_cp> cp
        # Recognize both before synchronizing with isready.
        for _ in range(512):
            line = self._readline()
            if "Unknown command" in line and "eval" in line:
                unknown = True
                break
            z = re.search(r"(?:^|\s)info\s+string\s+eval\s+([+-]?\d+)\s+cp(?:\s|$)", line)
            if z:
                raw_stm = int(z.group(1))
                value = raw_stm if white_to_move else -raw_stm
                style = "zchezz_stm_cp"
                break
            if "Final evaluation" in line:
                tail = line.split("Final evaluation", 1)[1]
                m = re.search(r"([+-]?\d+(?:\.\d+)?)", tail)
                if m:
                    # Stockfish's Final evaluation is White-relative.
                    value = int(round(float(m.group(1)) * 100.0))
                    style = "stockfish_white_cp"
                break
        self._ready()
        if unknown or value is None:
            self._static_supported = False
            lines = self.search(fen, white_to_move,
                                nodes=self.static_fallback_nodes, multipv=1)
            return lines[0].cp_white if lines else 0
        self._static_supported = True
        self._static_style = style
        return max(-32000, min(32000, value))

    def search(self, fen: str, white_to_move: bool, *, nodes: int = 0,
               depth: int = 0, movetime_ms: int = 0,
               multipv: int = 1) -> list[SearchLine]:
        multipv = max(1, int(multipv))
        self._send(f"setoption name MultiPV value {multipv}")
        self._send(f"position fen {fen}")
        if nodes > 0:
            go = f"go nodes {int(nodes)}"
        elif depth > 0:
            go = f"go depth {int(depth)}"
        elif movetime_ms > 0:
            go = f"go movetime {int(movetime_ms)}"
        else:
            go = "go nodes 1"
        self._send(go)

        latest: dict[int, SearchLine] = {}
        while True:
            line = self._readline()
            if line.startswith("bestmove"):
                break
            if not line.startswith("info ") or " score " not in line or " pv " not in line:
                continue
            toks = line.split()
            try:
                pv_i = toks.index("multipv")
                idx = int(toks[pv_i + 1])
            except (ValueError, IndexError):
                idx = 1
            try:
                score_i = toks.index("score")
                kind, raw = toks[score_i + 1], int(toks[score_i + 2])
                if kind == "cp":
                    cp_stm = raw
                elif kind == "mate":
                    cp_stm = self._mate_to_cp(raw)
                else:
                    continue
                pv = toks[toks.index("pv") + 1]
            except (ValueError, IndexError):
                continue
            cp_white = cp_stm if white_to_move else -cp_stm
            latest[idx] = SearchLine(
                pv, max(-32000, min(32000, cp_white)), idx)
        return [latest[k] for k in sorted(latest)]

    def close(self) -> None:
        if self.p.poll() is None:
            try:
                self._send("quit")
            except Exception:
                pass
            try:
                self.p.wait(timeout=2)
            except Exception:
                self.p.kill()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
