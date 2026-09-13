#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import random
from pathlib import Path


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly 1 match, got {n}")
    return text.replace(old, new, 1)


def apply_hash_patch(root: Path) -> None:
    p = root / "engine/c/zchezz_v500/search.h"
    s = p.read_text()
    s = once(
        s,
        "    size_t   size;\n    size_t   mask;\n",
        "    size_t   size;\n    size_t   slots;\n",
        "TTable size/mask fields",
    )
    s = once(
        s,
        "void    tt_new_generation(TTable *tt);\n",
        "void    tt_new_generation(TTable *tt);\nint     tt_resize_mb(TTable **tt, int mb);\n",
        "tt_resize declaration",
    )
    p.write_text(s)

    p = root / "engine/c/zchezz_v500/search.c"
    s = p.read_text()
    old = """TTable *tt_create(size_t n_entries) {
    TTable *tt = (TTable *)calloc(1, sizeof(TTable));
    if (!tt) return NULL;
    tt->e = (TTEntry *)calloc(n_entries, sizeof(TTEntry));
    if (!tt->e) {
        tt_destroy(tt);
        return NULL;
    }
    tt->size = n_entries;
    tt->mask = (n_entries / TT_BUCKETS) - 1;
    tt->gen  = 0;
    for (size_t i = 0; i < n_entries; i++) tt->e[i].eval = TT_EVAL_NONE;
    return tt;
}
"""
    new = """static inline size_t tt_index(const TTable *tt, uint64_t hash) {
#if defined(__SIZEOF_INT128__)
    return (size_t)(((__uint128_t)hash * (__uint128_t)tt->slots) >> 64);
#else
    return (size_t)(hash % tt->slots);
#endif
}

TTable *tt_create(size_t n_entries) {
    if (n_entries < TT_BUCKETS) n_entries = TT_BUCKETS;
    n_entries -= n_entries % TT_BUCKETS;
    TTable *tt = (TTable *)calloc(1, sizeof(TTable));
    if (!tt) return NULL;
    tt->e = (TTEntry *)calloc(n_entries, sizeof(TTEntry));
    if (!tt->e) {
        tt_destroy(tt);
        return NULL;
    }
    tt->size  = n_entries;
    tt->slots = n_entries / TT_BUCKETS;
    tt->gen   = 0;
    for (size_t i = 0; i < n_entries; i++) tt->e[i].eval = TT_EVAL_NONE;
    return tt;
}

int tt_resize_mb(TTable **ptt, int mb) {
    if (!ptt) return 0;
    if (mb < 1) mb = 1;
    if (mb > 1024) mb = 1024;
    const size_t requested = (size_t)mb * 1024u * 1024u;
    size_t n_entries = requested / sizeof(TTEntry);
    n_entries -= n_entries % TT_BUCKETS;
    if (n_entries < TT_BUCKETS) n_entries = TT_BUCKETS;
    TTable *fresh = tt_create(n_entries);
    if (!fresh) return 0;
    TTable *old = *ptt;
    *ptt = fresh;
    tt_destroy(old);
    const size_t actual = fresh->size * sizeof(TTEntry);
    fprintf(stderr,
            "[TT] aos48: requested=%d MB actual=%.3f MB slots=%zu entries=%zu entry=%zuB bucket=%zuB\\n",
            mb, (double)actual / (1024.0 * 1024.0), fresh->slots,
            fresh->size, sizeof(TTEntry), sizeof(TTEntry) * (size_t)TT_BUCKETS);
    return 1;
}
"""
    s = once(s, old, new, "tt_create block")
    s = once(
        s,
        "    int slot = (int)(hash & tt->mask);\n",
        "    size_t slot = tt_index(tt, hash);\n",
        "tt_store index",
    )
    s = once(
        s,
        "    TTEntry *e = &tt->e[(size_t)(hash & tt->mask) * TT_BUCKETS];\n",
        "    TTEntry *e = &tt->e[tt_index(tt, hash) * TT_BUCKETS];\n",
        "tt_probe index",
    )
    old_prefetch = "&tt->e[((b->hash ^ ZR_side) & tt->mask) * TT_BUCKETS]"
    n = s.count(old_prefetch)
    if n < 1:
        raise RuntimeError(f"prefetch replacement: expected >=1 match, got {n}")
    s = s.replace(
        old_prefetch,
        "&tt->e[tt_index(tt, b->hash ^ ZR_side) * TT_BUCKETS]",
    )
    if "tt->mask" in s:
        raise RuntimeError("unconverted tt->mask use remains in search.c")
    s = once(
        s,
        "        g_tt = tt_create(TT_SIZE);\n",
        """#ifdef __EMSCRIPTEN__
        g_tt = tt_create(TT_SIZE);
#else
        if (!tt_resize_mb(&g_tt, 64)) {
            fprintf(stderr, "[TT] fatal: 64 MB default allocation failed (out of memory)\\n");
            exit(1);
        }
#endif
""",
        "search_init allocation line",
    )
    p.write_text(s)

    p = root / "engine/c/zchezz_v500/main.c"
    s = p.read_text()
    s = once(s, '#define ENGINE_VERSION "5.03"', '#define ENGINE_VERSION "5.04"', "engine version")
    s = once(
        s,
        "static int    g_opt_threads    = 1;       /* number of search threads */\n",
        "static int    g_opt_threads    = 1;       /* number of search threads */\n"
        "static int    g_opt_hash_mb    = 64;      /* TT size requested through UCI */\n",
        "hash option state",
    )
    s = once(
        s,
        "    if (sample > TT_SIZE) sample = TT_SIZE;\n",
        "    if (g_tt && sample > (int)g_tt->size) sample = (int)g_tt->size;\n",
        "hashfull size",
    )
    s = once(
        s,
        "    /* Hash is accepted but currently ignored (fixed TT size) */\n",
        """    else if (strcasecmp(name, "Hash") == 0) {
        int mb = atoi(value);
        if (mb < 1) mb = 1;
        if (mb > 1024) mb = 1024;
        if (g_searching) {
            g_stop_flag = 1;
            pthread_join(g_search_thread, NULL);
            g_searching = 0;
        }
        if (tt_resize_mb(&g_tt, mb)) g_opt_hash_mb = mb;
    }
""",
        "Hash handler",
    )
    p.write_text(s)


def make_openings(all_epd: Path, out: Path, shard: int) -> None:
    lines = []
    for raw in all_epd.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 4:
            lines.append(" ".join(parts[:4]))
    rng = random.Random(504326)
    rng.shuffle(lines)
    start = 8000 + shard * 32
    chosen = lines[start : start + 32]
    if len(chosen) != 32:
        raise RuntimeError(f"expected 32 openings, got {len(chosen)}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(chosen) + "\n", encoding="utf-8")


def stats(v: list[int]) -> dict[str, float | int]:
    w, d, l = v
    n = w + d + l
    if n != 256:
        raise RuntimeError(f"expected 256 games, got {n}")
    score = (w + 0.5 * d) / n
    elo = 400 * math.log10(score / (1 - score)) if 0 < score < 1 else (9999.0 if score == 1 else -9999.0)
    second = (w + 0.25 * d) / n
    var = max(0.0, second - score * score)
    se = math.sqrt(var / n)
    deriv = 400 / math.log(10) / (score * (1 - score)) if 0 < score < 1 else 0.0
    ci = 1.96 * deriv * se
    return {"w": w, "d": d, "l": l, "n": n, "score": score, "elo": elo, "ci95_half": ci}


def aggregate(downloaded: Path, summary_json: Path, summary_md: Path, github_output: Path | None) -> None:
    totals = {"search_v502": [0, 0, 0], "final_v326": [0, 0, 0]}
    files = list(downloaded.glob("**/result.json"))
    if len(files) != 8:
        raise RuntimeError(f"expected 8 result files, got {len(files)}")
    for f in files:
        pair = json.loads(f.read_text())["pairings"][0]
        # Arena JSON is first-player perspective. Candidate is second.
        w, d, l = int(pair["l"]), int(pair["d"]), int(pair["w"])
        key = "search_v502" if "search-v502" in str(f) else "final_v326"
        totals[key][0] += w
        totals[key][1] += d
        totals[key][2] += l

    search = stats(totals["search_v502"])
    final = stats(totals["final_v326"])
    promote = final["score"] >= 0.500 and (search["score"] >= 0.515 or final["score"] >= 0.515)
    summary = {
        "search_v502": search,
        "final_v326": final,
        "promote": promote,
        "gate": "v326 score >= 50.0% and (v502 search score >= 51.5% or v326 score >= 51.5%)",
    }
    summary_json.write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# v5.04 promotion screen",
        "",
        "256 games per pairing, 200 ms/move, Threads=1, serial games, paired UHO openings, no tablebases.",
        "",
        "| Match | Candidate W-D-L | Score | Elo | approx 95% half-width |",
        "|---|---:|---:|---:|---:|",
        f"| v5.03 search vs v5.02 (both legacy fixed TT) | {search['w']}-{search['d']}-{search['l']} | {100*search['score']:.2f}% | {search['elo']:+.1f} | ±{search['ci95_half']:.1f} |",
        f"| final v5.04 vs v3.26 (both real 64 MB) | {final['w']}-{final['d']}-{final['l']} | {100*final['score']:.2f}% | {final['elo']:+.1f} | ±{final['ci95_half']:.1f} |",
        "",
        f"Promotion gate: **{'PASS' if promote else 'FAIL'}**.",
        "",
        "The CI is reported for context only; it is not the promotion criterion.",
    ]
    summary_md.write_text("\n".join(lines) + "\n")
    print(summary_md.read_text())
    if github_output is not None:
        with github_output.open("a") as fh:
            fh.write(f"promote={'true' if promote else 'false'}\n")


def write_release(summary_path: Path, out: Path) -> None:
    x = json.loads(summary_path.read_text())
    a, b = x["search_v502"], x["final_v326"]
    text = f"""# Zchezz v5.04

v5.04 promotes the v3.26-proven search-selectivity port onto the v5 NNU4 line and fixes UCI `Hash` so the v500 profile now honors the requested transposition-table size.

## Search changes

Relative to v5.02, the promoted search removes the blanket `depth++` at in-check alpha-beta nodes, uses quiet history pruning at `-64 * depth`, and retunes LMR history feedback to `-512 / -1024 / +512`. The NNUE weights remain exactly the v5.02 weights.

## Hash compliance

The previous v5 UCI advertised `Hash` but ignored it and always allocated its fixed table. v5.04 resizes the existing two-entry AoS table to the requested memory budget and uses unbiased indexing for non-power-of-two slot counts. Default UCI Hash is 64 MB.

## Promotion evidence

All games used 200 ms/move, Threads=1, serial execution, paired UHO openings with reversed colors, maximum 400 plies, and tablebases disabled. Confidence intervals are reported for context only; the maintainer chose a pragmatic point-estimate promotion rule rather than requiring the 95% interval to exclude zero.

- Search-only v5.03 vs v5.02 under the same legacy fixed-TT behavior: **{a['w']}-{a['d']}-{a['l']}**, score **{100*a['score']:.2f}%**, estimated **{a['elo']:+.1f} Elo** (approx. 95% half-width {a['ci95_half']:.1f}).
- Final v5.04 vs v3.26 with both engines actually using 64 MB Hash: **{b['w']}-{b['d']}-{b['l']}**, score **{100*b['score']:.2f}%**, estimated **{b['elo']:+.1f} Elo** (approx. 95% half-width {b['ci95_half']:.1f}).

The promotion gate required the final v5.04 point estimate to be at least 50.0% against v3.26, plus at least one of the two comparisons to reach 51.5%. The gate passed.

v5.04 becomes the promoted **v5-family baseline** in `main`. The repository's bare-build default remains `v326`; changing the default profile is a separate decision.
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("patch")
    p.add_argument("--root", type=Path, default=Path("."))

    p = sub.add_parser("openings")
    p.add_argument("--all", dest="all_epd", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--shard", type=int, required=True)

    p = sub.add_parser("aggregate")
    p.add_argument("--downloaded", type=Path, required=True)
    p.add_argument("--summary-json", type=Path, default=Path("summary.json"))
    p.add_argument("--summary-md", type=Path, default=Path("summary.md"))
    p.add_argument("--github-output", type=Path)

    p = sub.add_parser("release")
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)

    args = ap.parse_args()
    if args.cmd == "patch":
        apply_hash_patch(args.root)
    elif args.cmd == "openings":
        make_openings(args.all_epd, args.out, args.shard)
    elif args.cmd == "aggregate":
        aggregate(args.downloaded, args.summary_json, args.summary_md, args.github_output)
    elif args.cmd == "release":
        write_release(args.summary, args.out)


if __name__ == "__main__":
    main()
