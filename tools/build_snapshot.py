#!/usr/bin/env python3
"""Pack Graffiti NFT tokens into graffiti/graffiti_snap.bin for the wedgie app.

Default source: the Blast snapshot saved by the migration (graffiti-nft/script/migration/plan-8453.json).
Its ids are the Blast ids, which are also the Sepolia ids (the Sepolia migration kept them).

  python3 -I tools/build_snapshot.py
  python3 -I tools/build_snapshot.py --from-chain 11155111 --rpc https://1rpc.io/sepolia

--from-chain reads every token live with `cast call getGraffitiBase(uint256)` (Foundry). The contract
address comes from graffiti/graffiti_chains.json unless --address is given.

File layout (all big-endian):
  header 16 bytes: b"GRF1", count u16, chain id u32, source block u32, 2 bytes zero
  per token 2080 bytes:
    32-byte meta: id u16, color 3 bytes (RRGGBB), creator 20 bytes, 7 bytes zero
    2048 bytes:   the 64 uint256 words of the bitfield as stored on chain
                  (128 rows x 16 bytes, MSB = leftmost pixel: MONO_HLSB)
"""
import argparse
import json
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_PLAN = os.path.join(ROOT, "..", "graffiti-nft", "script", "migration", "plan-8453.json")
OUT = os.path.join(ROOT, "graffiti", "graffiti_snap.bin")
CHAINS = os.path.join(ROOT, "graffiti", "graffiti_chains.json")

MAGIC = b"GRF1"
HEADER = 16
META = 32
BITS = 2048
RECORD = META + BITS
LIMIT = 256 * 1024 - 32 * 1024     # the app's 256 KB, with room left for the code


def word_bytes(h):
    h = h[2:] if h.startswith("0x") else h
    if len(h) > 64:
        raise ValueError("word longer than 32 bytes: %s" % h)
    return bytes.fromhex(h.rjust(64, "0"))


def record(tid, color, creator, words):
    if len(words) != 64:
        raise ValueError("token %d: %d words, want 64" % (tid, len(words)))
    meta = struct.pack(">H", tid) + color.to_bytes(3, "big") + bytes.fromhex(creator[2:].rjust(40, "0"))
    meta += bytes(META - len(meta))
    bits = b"".join(word_bytes(w) for w in words)
    assert len(meta) == META and len(bits) == BITS
    return meta + bits


def from_plan(path):
    with open(path) as f:
        plan = json.load(f)
    out = []
    for t in plan["tokens"]:
        # the Blast data: original id, original color (not proposedColor, which is Base's substitute)
        out.append(record(int(t["sourceId"]), int(t["color"], 16), t["creator"], t["sig"]))
    return out, int(plan.get("sourceChain") or 81457), int(plan.get("blockNumber") or 0)


def cast(*args, tries=6):
    """cast, again after a pause when it fails: public RPCs answer "too many requests" often."""
    for k in range(tries):
        r = subprocess.run(["cast", *args], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
        time.sleep(2 ** k)
    sys.exit("cast %s failed:\n%s" % (" ".join(args), r.stderr.strip()[-500:]))


def from_chain(chain, rpc, address):
    n = int(cast("call", "--rpc-url", rpc, address, "totalSupply()(uint256)").split()[0])
    block = int(cast("block-number", "--rpc-url", rpc))
    out = []
    for i in range(n):
        h = cast("call", "--rpc-url", rpc, "--block", str(block), address, "getGraffitiBase(uint256)", str(i))
        h = h[2:]
        w = [h[k:k + 64] for k in range(0, len(h), 64)]
        # tuple offset, id, color, creator, owner, colorOwner, array offset, length, 64 words
        if len(w) != 72 or int(w[7], 16) != 64:
            raise ValueError("token %d: unexpected reply (%d words)" % (i, len(w)))
        out.append(record(int(w[1], 16), int(w[2], 16) & 0xFFFFFF, "0x" + w[3][24:], w[8:]))
        print("  %d/%d" % (i + 1, n), end="\r", file=sys.stderr)
    print(file=sys.stderr)
    return out, chain, block


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", default=DEFAULT_PLAN, help="migration plan JSON (default: plan-8453.json)")
    ap.add_argument("--from-chain", type=int, help="read live from this chain id instead of the plan")
    ap.add_argument("--rpc", help="RPC URL for --from-chain (default: $RPC_URL_<chain>)")
    ap.add_argument("--address", help="contract address for --from-chain (default: graffiti_chains.json)")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    if a.from_chain:
        rpc = a.rpc or os.environ.get("RPC_URL_%d" % a.from_chain)
        address = a.address
        if not address:
            with open(CHAINS) as f:
                address = json.load(f).get(str(a.from_chain), {}).get("address")
        if not rpc or not address:
            sys.exit("need --rpc and an address for chain %d" % a.from_chain)
        recs, chain, block = from_chain(a.from_chain, rpc, address)
    else:
        recs, chain, block = from_plan(a.plan)

    data = MAGIC + struct.pack(">HII", len(recs), chain, block) + bytes(2)
    assert len(data) == HEADER
    data += b"".join(recs)
    if len(data) > LIMIT:
        sys.exit("snapshot is %d bytes, over the %d left for it in a 256 KB app" % (len(data), LIMIT))
    with open(a.out, "wb") as f:
        f.write(data)
    print("%s: %d tokens, chain %d, block %d, %d bytes" % (os.path.relpath(a.out), len(recs), chain, block, len(data)))


if __name__ == "__main__":
    main()
