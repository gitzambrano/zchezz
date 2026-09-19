#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path


def elo(score: float) -> float:
    eps = 1e-12
    score = min(1.0 - eps, max(eps, score))
    return 400.0 * math.log10(score / (1.0 - score))


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bootstrap", type=int, default=50000)
    args = ap.parse_args()

    files = sorted(Path().glob(args.glob))
    if not files:
        raise SystemExit(f"no shard JSON files for {args.glob}")
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in files]

    wins = sum(r["wins_a"] for r in rows)
    draws = sum(r["draws"] for r in rows)
    losses = sum(r["losses_a"] for r in rows)
    games = wins + draws + losses
    pair_points = [x for r in rows for x in r["pair_points_a"]]
    pairs = len(pair_points)
    score = (wins + 0.5 * draws) / games
    point_elo = elo(score)

    rng = random.Random(3303201)
    boots: list[float] = []
    positive = 0
    for _ in range(args.bootstrap):
        pts = sum(pair_points[rng.randrange(pairs)] for __ in range(pairs))
        s = pts / (2.0 * pairs)
        e = elo(s)
        boots.append(e)
        if s > 0.5:
            positive += 1

    def merged_metric(side: str, field: str) -> float:
        return sum(float(r["metrics"][side][field]) for r in rows)

    n_a = merged_metric("a", "nodes"); t_a = merged_metric("a", "time_s")
    n_b = merged_metric("b", "nodes"); t_b = merged_metric("b", "time_s")
    d_a = merged_metric("a", "depth"); m_a = merged_metric("a", "moves")
    d_b = merged_metric("b", "depth"); m_b = merged_metric("b", "moves")
    nps_a = n_a / t_a if t_a else 0.0
    nps_b = n_b / t_b if t_b else 0.0
    depth_a = d_a / m_a if m_a else 0.0
    depth_b = d_b / m_b if m_b else 0.0

    payload = {
        "shards": len(rows), "pairs": pairs, "games": games,
        "wins_a": wins, "draws": draws, "losses_a": losses,
        "score_a": score, "elo_a": point_elo,
        "paired_bootstrap_ci95_elo": [pct(boots, 0.025), pct(boots, 0.975)],
        "paired_bootstrap_los": positive / args.bootstrap,
        "confirmed_positive": pct(boots, 0.025) > 0.0,
        "nps_a": nps_a, "nps_b": nps_b,
        "nps_ratio_a_over_b": (nps_a / nps_b) if nps_b else None,
        "avg_depth_a": depth_a, "avg_depth_b": depth_b,
        "source_files": [str(p) for p in files],
    }
    print("AGGREGATE " + json.dumps(payload, sort_keys=True))
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
