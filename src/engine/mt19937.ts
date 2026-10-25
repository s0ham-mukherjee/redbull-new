/**
 * MT19937 — bit-exact port of CPython's `random.Random` core.
 *
 * Why this exists: the sakura-abm engine's paired-seed design requires the
 * TypeScript runtime to consume the SAME random stream the Python engine
 * consumes for a given seed. CPython's `random()` is genrand_res53 (two
 * 32-bit draws per value) and `randrange(n)` is `_randbelow_with_getrandbits`
 * (rejection sampling at `bit_length(n)` bits) — both reproduced here exactly,
 * including `init_by_array` seeding of integer seeds.
 *
 * Reference: CPython Lib/random.py + Modules/_randommodule.c.
 */

const N = 624;
const M = 397;
const MATRIX_A = 0x9908b0df;
const UPPER_MASK = 0x80000000;
const LOWER_MASK = 0x7fffffff;

export class MT19937 {
  private mt = new Uint32Array(N);
  private mti = N + 1; // mti == N+1 means mt[] is not initialised

  constructor(seed: number | number[] = 42) {
    this.seed(seed);
  }

  /** CPython random.Random.seed(int, version=2): abs int → little-endian 32-bit words → init_by_array */
  seed(value: number | number[]): void {
    if (Array.isArray(value)) {
      this.initByArray(value);
      return;
    }
    let n = Math.abs(Math.trunc(value));
    if (!Number.isFinite(n)) {
      // CPython falls back to hashing for unhashable/absent seeds — not our case.
      n = 0;
    }
    const words: number[] = [];
    if (n === 0) words.push(0);
    while (n > 0) {
      words.push(n % 0x100000000);
      n = Math.floor(n / 0x100000000);
    }
    this.initByArray(words);
  }

  private initGenrand(s: number): void {
    this.mt[0] = s >>> 0;
    for (let i = 1; i < N; i++) {
      const prev = this.mt[i - 1];
      this.mt[i] = (Math.imul(1812433253, prev ^ (prev >>> 30)) + i) >>> 0;
    }
    this.mti = N;
  }

  private initByArray(key: number[]): void {
    this.initGenrand(19650218);
    let i = 1;
    let j = 0;
    let k = Math.max(N, key.length);
    for (; k; k--) {
      const prev = this.mt[i - 1];
      this.mt[i] =
        ((this.mt[i] ^ (Math.imul(prev ^ (prev >>> 30), 1664525) >>> 0)) + (key[j] >>> 0) + j) >>> 0;
      i++;
      j++;
      if (i >= N) {
        this.mt[0] = this.mt[N - 1];
        i = 1;
      }
      if (j >= key.length) j = 0;
    }
    for (let kk = N - 1; kk; kk--) {
      const prev = this.mt[i - 1];
      this.mt[i] =
        ((this.mt[i] ^ (Math.imul(prev ^ (prev >>> 30), 1566083941) >>> 0)) - i) >>> 0;
      i++;
      if (i >= N) {
        this.mt[0] = this.mt[N - 1];
        i = 1;
      }
    }
    this.mt[0] = 0x80000000;
  }

  genrandInt32(): number {
    let y: number;
    if (this.mti >= N) {
      if (this.mti === N + 1) this.initGenrand(5489);
      for (let kk = 0; kk < N - M; kk++) {
        y = (this.mt[kk] & UPPER_MASK) | (this.mt[kk + 1] & LOWER_MASK);
        this.mt[kk] = this.mt[kk + M] ^ (y >>> 1) ^ (y & 1 ? MATRIX_A : 0);
      }
      for (let kk = N - M; kk < N - 1; kk++) {
        y = (this.mt[kk] & UPPER_MASK) | (this.mt[kk + 1] & LOWER_MASK);
        this.mt[kk] = this.mt[kk + (M - N)] ^ (y >>> 1) ^ (y & 1 ? MATRIX_A : 0);
      }
      y = (this.mt[N - 1] & UPPER_MASK) | (this.mt[0] & LOWER_MASK);
      this.mt[N - 1] = this.mt[M - 1] ^ (y >>> 1) ^ (y & 1 ? MATRIX_A : 0);
      this.mti = 0;
    }
    y = this.mt[this.mti++];
    y ^= y >>> 11;
    y ^= (y << 7) & 0x9d2c5680;
    y = (y ^ ((y << 15) & 0xefc60000)) >>> 0;
    y ^= y >>> 18;
    return y >>> 0;
  }

  /** CPython random.random() — genrand_res53: exactly two int32 draws. */
  random(): number {
    const a = this.genrandInt32() >>> 5; // 27 bits
    const b = this.genrandInt32() >>> 6; // 26 bits
    return (a * 67108864.0 + b) / 9007199254740992.0;
  }

  /** CPython random.getrandbits(k) for 0 < k <= 32 (single draw). */
  getrandbits(k: number): number {
    if (k <= 0) return 0;
    if (k > 32) {
      // multi-word path (unused by the engine; kept for completeness)
      let words = Math.ceil(k / 32);
      let result = 0n;
      let shift = 0n;
      while (words-- > 0) {
        const w = BigInt(this.genrandInt32());
        result |= w << shift;
        shift += 32n;
      }
      result &= (1n << BigInt(k)) - 1n;
      return Number(result);
    }
    return this.genrandInt32() >>> (32 - k);
  }

  /** CPython random._randbelow_with_getrandbits — rejection sampling. */
  private randbelow(n: number): number {
    if (n <= 0) throw new RangeError("_randbelow_with_getrandbits: n <= 0");
    const k = 32 - Math.clz32(n); // bit_length(n)
    let r = this.getrandbits(k);
    while (r >= n) r = this.getrandbits(k);
    return r;
  }

  /** CPython random.randrange(n) — single-arg form → _randbelow(n). */
  randrange(n: number): number {
    return this.randbelow(n);
  }
}
