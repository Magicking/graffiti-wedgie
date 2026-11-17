# Where the graffiti come from: the snapshot packed with the app, or a chain, read live.
#
# Both give the same thing: count(), get(i, buf) -> (id, color) with the 2048 bitfield bytes in buf, or
# None while a live token is on its way (poll() brings it in).
import json
import struct

BITS = 2048
HEADER = 16
META = 32
RECORD = META + BITS

SEL_TOTAL = "0x18160ddd"                    # totalSupply()
SEL_BASE = "0x62829900"                     # getGraffitiBase(uint256)
WORDS = 72                                  # its reply: tuple offset, 6 head words, length, 64 words


def _open(name):
    for p in (name, "/" + name):            # the wedgie keeps every app file in the flash's root
        try:
            return open(p, "rb")
        except OSError:
            pass
    raise OSError("no " + name)


def chains():
    """{chain id: name} for every chain with a contract, in the file's order."""
    f = _open("graffiti_chains.json")
    try:
        c = json.load(f)
    finally:
        f.close()
    return [(int(k), v["name"], v["address"]) for k, v in c.items() if v.get("address")]


class Snap:
    live = False
    name = "Snapshot"

    def __init__(self):
        self.f = _open("graffiti_snap.bin")
        h = self.f.read(HEADER)
        if h[:4] != b"GRF1":
            raise ValueError("graffiti_snap.bin: bad header")
        self.n, self.chain, self.block = struct.unpack(">HII", h[4:14])
        self.meta = bytearray(META)

    def count(self):
        return self.n

    def get(self, i, buf):
        self.f.seek(HEADER + i * RECORD)
        self.f.readinto(self.meta)
        self.f.readinto(buf)
        m = self.meta
        return (m[0] << 8) | m[1], (m[2] << 16) | (m[3] << 8) | m[4]

    def poll(self):
        return False

    def busy(self):
        return False

    def forget(self, i):
        pass

    def close(self):
        self.f.close()


class Live:
    """A chain, through net.chain (the wedgie's page on wedgie.dev carries it). Tokens it got stay in a
    small cache (SLOTS of them, the least used goes first): a wall page is 9."""
    live = True
    SLOTS = 12

    def __init__(self, chain, name, address):
        import net                          # only when a chain is picked: the snapshot needs no net
        self.net = net
        self.chain, self.name, self.address = chain, name, address
        self.data = bytearray(self.SLOTS * BITS)
        self.ids = [-1] * self.SLOTS        # token index in each slot
        self.colors = [0] * self.SLOTS
        self.used = [0] * self.SLOTS
        self.clock = 0
        self.want = []                      # indexes to ask for, in order
        self.rid = None                     # the ask under way
        self.asking = -1
        self.err = None
        self.n = 0

    def _call(self, data):
        return [{"to": self.address, "data": data}, "latest"]

    def total(self):
        """totalSupply, waiting for it (under a second through the relay; 15 s with nothing open)."""
        r = self.net.chain(self.chain, "eth_call", self._call(SEL_TOTAL))
        self.n = int(r, 16)
        return self.n

    def count(self):
        return self.n

    def _slot(self, i):
        for s in range(self.SLOTS):
            if self.ids[s] == i:
                return s
        return -1

    def get(self, i, buf):
        s = self._slot(i)
        if s < 0:
            if i != self.asking and i not in self.want:
                self.want.append(i)
            return None
        self.clock += 1
        self.used[s] = self.clock
        buf[:] = memoryview(self.data)[s * BITS:(s + 1) * BITS]
        return i, self.colors[s]

    def forget(self, i):
        s = self._slot(i)
        if s >= 0:
            self.ids[s] = -1
            self.used[s] = 0

    def drop_wants(self):
        self.want.clear()

    def busy(self):
        return self.rid is not None or bool(self.want)

    def poll(self):
        """Ask for the next wanted token, or take in the answer. True when something came in (or failed)."""
        net = self.net
        if self.rid is None:
            if not self.want:
                return False
            i = self.want.pop(0)
            if self._slot(i) >= 0:
                return False
            self.asking = i
            try:
                self.rid = net.ask({"chain": self.chain, "method": "eth_call",
                                    "params": self._call(SEL_BASE + "%064x" % i)})
            except Exception as e:
                return self._fail(e)
            return False
        try:
            a = net.answer(self.rid)
        except Exception as e:
            return self._fail(e)
        if a is None:
            return False
        self.rid = None
        try:
            self._take(self.asking, a)
        except Exception as e:
            return self._fail(e)
        self.asking = -1
        return True

    def _fail(self, e):
        self.rid, self.asking = None, -1
        self.want.clear()
        self.err = str(e)[:60] or e.__class__.__name__
        return True

    def _take(self, i, a):
        if isinstance(a, dict):             # a JSON-RPC error (a revert: no such token)
            raise ValueError(a.get("message") or "error")
        if not isinstance(a, str) or len(a) < 2 + WORDS * 64:
            raise ValueError("short answer")
        import ubinascii
        bits = ubinascii.unhexlify(a[2 + 8 * 64:2 + WORDS * 64])
        s = 0
        for k in range(1, self.SLOTS):      # the least used slot
            if self.used[k] < self.used[s]:
                s = k
        self.data[s * BITS:(s + 1) * BITS] = bits
        self.colors[s] = int(a[2 + 2 * 64:2 + 3 * 64], 16) & 0xFFFFFF
        self.ids[s] = i
        self.clock += 1
        self.used[s] = self.clock

    def close(self):
        self.want.clear()
        self.rid = None
