#!/usr/bin/env python3
"""Benchmark e simulador de gating para a arquitetura Dual NNUE (Small Net + Big Net).

Mede:
  1. A concordância de avaliação entre v507 (Small Net) e v601 (Big Net).
  2. A taxa de ativação da Big Net em função do threshold theta (cp).
  3. O throughput efetivo estimado (NPS) do motor híbrido.
"""
from __future__ import annotations
import argparse
import math
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def extract_fens(folder: Path, max_fens: int = 200) -> list[str]:
    fens = []
    # Try epd or pgn files
    files = list(folder.glob("*.epd")) + list(folder.glob("*.pgn"))
    for f in files:
        if f.suffix == ".epd":
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split(";")
                    fen = parts[0].strip()
                    if len(fen.split()) >= 4:
                        fens.append(fen)
                        if len(fens) >= max_fens:
                            return fens
    if not fens:
        # Standard benchmark fallback positions
        fens = [
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "r1bqkbnr/pppppppp/2n5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 1 2",
            "r1bqkb1r/pppppppp/2n2n2/8/2PP4/8/PP2PPPP/RNBQKBNR w KQkq - 2 3",
            "r1bqkb1r/1ppp1ppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4",
            "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
            "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
            "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
            "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
            "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
        ] * (max_fens // 9 + 1)
        fens = fens[:max_fens]
    return fens

class UciEvalClient:
    def __init__(self, exe: Path):
        self.exe = str(exe)
        self.proc = subprocess.Popen(
            [self.exe],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(Path(self.exe).parent),
        )
        self._send("uci")
        self._wait("uciok")
        self._send("isready")
        self._wait("readyok")

    def _send(self, cmd: str):
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def _wait(self, token: str, timeout: float = 5.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self.proc.stdout.readline()
            if token in line:
                return True
        return False

    def evaluate(self, fen: str) -> int:
        self._send(f"position fen {fen}")
        self._send("eval")
        # Parse: "info string eval <X> cp (STM-relative)"
        for _ in range(50):
            line = self.proc.stdout.readline().strip()
            if "info string eval" in line:
                parts = line.split()
                if "eval" in parts:
                    idx = parts.index("eval")
                    if idx + 1 < len(parts):
                        try:
                            return int(parts[idx + 1])
                        except ValueError:
                            pass
        return 0

    def close(self):
        try:
            self._send("quit")
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.kill()

def simulate_hybrid(evals_small: list[int], evals_big: list[int], nps_small: int = 1150000, nps_big: int = 470000):
    print("\n" + "=" * 80)
    print(" SIMULAÇÃO DE GATING DUAL NNUE (Small Net = v507 | Big Net = v601)")
    print(f" NPS Base: Small Net = {nps_small:,} n/s | Big Net = {nps_big:,} n/s")
    print("=" * 80)
    print(f"{'Theta (cp)':>10} | {'Ativação Big (%)':>18} | {'NPS Efetivo Est.':>18} | {'Ganho vs v601':>16}")
    print("-" * 80)

    total = len(evals_small)
    thresholds = [40, 60, 80, 100, 120, 150, 200]

    for th in thresholds:
        # Gating condition: In main search, invoke big net if |eval_small| < th
        # In a real tree, ~85% of leaves are in QSearch (100% small net).
        # In the remaining 15% of nodes, Big Net is called if |eval_small| < th.
        active_in_sample = sum(1 for s in evals_small if abs(s) < th)
        sample_pct = active_in_sample / max(1, total)

        # Global tree activation: 15% main search * sample_pct
        global_big_pct = 0.15 * sample_pct

        # Combined cost per node:
        # Time per node = (1 / nps_small) + global_big_pct * (1 / nps_big)
        t_small = 1.0 / nps_small
        t_big = 1.0 / nps_big
        t_effective = t_small + global_big_pct * t_big
        nps_effective = int(round(1.0 / t_effective))

        speedup = ((nps_effective / nps_big) - 1.0) * 100.0

        print(f"{th:>10} cp | {sample_pct * 100:>17.1f}% | {nps_effective:>16,d} n/s | {speedup:>+15.1f}%")
    print("=" * 80 + "\n")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=100, help="Número de posições para avaliar (default: 100)")
    parser.add_argument("--show-config", action="store_true", help="Mostra a configuração e sai")
    args = parser.parse_args()

    v507_exe = ROOT / "engine" / "c" / "zchezz_v507" / "zchezz.exe"
    v601_exe = ROOT / "engine" / "c" / "zchezz_v601" / "zchezz.exe"

    if args.show_config:
        print("dual_eval_benchmark config:")
        print(f"  positions={args.positions}")
        print(f"  small_net_v507={v507_exe}")
        print(f"  big_net_v601={v601_exe}")
        return 0

    assert v507_exe.is_file(), f"Faltando v507: {v507_exe}"
    assert v601_exe.is_file(), f"Faltando v601: {v601_exe}"

    openings_dir = ROOT / "openings" / "lines"
    fens = extract_fens(openings_dir, max_fens=args.positions)
    print(f"[+] Carregadas {len(fens)} posições de teste.")

    print("[+] Conectando à Small Net (v507)...")
    c_small = UciEvalClient(v507_exe)
    print("[+] Conectando à Big Net (v601)...")
    c_big = UciEvalClient(v601_exe)

    print(f"[+] Avaliando {len(fens)} posições...")
    evals_small = []
    evals_big = []

    for i, fen in enumerate(fens):
        es = c_small.evaluate(fen)
        eb = c_big.evaluate(fen)
        evals_small.append(es)
        evals_big.append(eb)
        if (i + 1) % 25 == 0:
            print(f"  [{i+1}/{len(fens)}] processados...")

    c_small.close()
    c_big.close()

    # Correlation
    mean_s = sum(evals_small) / len(evals_small)
    mean_b = sum(evals_big) / len(evals_big)
    num = sum((s - mean_s) * (b - mean_b) for s, b in zip(evals_small, evals_big))
    den = math.sqrt(sum((s - mean_s)**2 for s in evals_small) * sum((b - mean_b)**2 for b in evals_big))
    corr = (num / den) if den > 0 else 0.0

    print(f"\n[+] Correlação de Pearson entre v507 e v601: r = {corr:.3f}")

    simulate_hybrid(evals_small, evals_big)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
