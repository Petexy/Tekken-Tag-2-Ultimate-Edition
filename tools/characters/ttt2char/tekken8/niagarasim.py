"""Runs a Tekken 8 CPU Niagara emitter's own particle scripts (VM bytecode: tekken8/niagara.py) to measure what they do:
each particle's lifetime, colour, size, place and turn over its life.

The VM: 32-bit registers (a float or an int, by the operation), constants by byte offset in one table, attributes read
from and written to a data set by component (floats and ints numbered apart, in the order of the script's Attributes:
a position 3 floats, a colour 4, a quaternion 4, ...). The table: the engine's values, then the script's parameter
store, then its literals:

    0 global (32 bytes: +4 the frame's time), 32 system (64), 96 owner (512: six matrices, 64 each, rows, of which +256
    is local to world without scale, as in the scripts' `mad` of a row by a local coordinate), 608 emitter (32: +12 the
    emitter's age), 640 the parameters; a script that interpolates its spawning has a second such set (the previous
    frame's) after them; then the literals.

Curves sampled by a script are its data interfaces' lookup tables (niagara.Emitter.curves). The owner is left at the
origin, unturned, so that places and speeds come out in the emitter's own frame.

Written for this project from the files themselves (no third-party code).
"""
import numpy as np

from . import niagara

GLOBAL_DT = 4                     # byte offsets of the engine's values in the table
EMITTER_AGE = 620
ENGINE_SET = 640                  # the engine's values take this many bytes (each copy of the set)
NO_PAUSE_PARAM = 'IsNotPaused'
FRAME = 1.0 / 60.0
PARTICLES = 96                    # particles simulated per spawn
MAX_FRAMES = 240

BOOL_TRUE = -1


class Script:
    """A script's code and constants, ready to run."""

    def __init__(self, props, curves, label='', arrays=None, user=None):
        self.vm = props.get('CachedScriptVM') or {}
        self.script = niagara.Script(props)
        self.curves = curves
        self.arrays = arrays or {}
        self.label = label
        self.attributes = self._layout(self.vm.get('Attributes') or [])
        store = props.get('ScriptExecutionParamStore') or {}
        self.params = {q.get('Name'): q.get('Offset') for q in store.get('SortedParameterOffsets') or []
                       if 'DataInterface' not in str((q.get('Type') or {}).get('ClassStructOrEnum'))}
        data = bytes(store.get('ParameterData') or b'')
        size = int(store.get('ParameterSize') or 0)
        base = self.script.base if self.script.base is not None else ENGINE_SET + size
        # the table: engine values, parameters; a script with a previous-frame copy has both twice, then the literals
        self.sets = [0] if base <= ENGINE_SET + size else [0, ENGINE_SET + size]
        self.table = np.zeros(base // 4 + len(self.script.literals) // 4 + 8, np.uint32)
        words = np.frombuffer(data[:len(data) // 4 * 4], '<u4')
        for k, start in enumerate(self.sets):
            first = start + ENGINE_SET
            part = words[k * size // 4:(k + 1) * size // 4]
            self.table[first // 4:first // 4 + len(part)] = part
        if self.script.literals:
            lit = np.frombuffer(self.script.literals[:len(self.script.literals) // 4 * 4], '<u4')
            self.table[base // 4:base // 4 + len(lit)] = lit
        for k, offset in self.params.items():              # (the game's own switch: not paused)
            if NO_PAUSE_PARAM in k:
                where = offset % size if size else 0
                for start in self.sets:
                    self.table[(start + ENGINE_SET + where) // 4] = 1
        for name, values in (user or {}).items():          # (the system's exposed parameters, at their defaults)
            for k, prefix in enumerate(('', 'PREV_')):
                offset = self.params.get(prefix + name)
                if offset is None:
                    continue
                offset = offset % size if size else 0
                for start in self.sets[k:k + 1] or self.sets[:1]:
                    first = (start + ENGINE_SET + offset) // 4
                    self.table[first:first + len(values)] = np.frombuffer(np.float32(values).tobytes(), '<u4')
        self.externals = [(x.get('Name'), (x.get('OwnerName') or '')) for x in self.vm.get('CalledVMExternalFunctions')
                          or []]
        self.warned = set()

    @staticmethod
    def _layout(attrs):
        """[(name, 'f' or 'i', first component, components)]."""
        sizes = {'LinearColor': 4, 'Quat4f': 4, 'Quat': 4, 'Vector3f': 3, 'Vector': 3, 'NiagaraPosition': 3,
                 'Vector2f': 2, 'Vector2D': 2, 'Vector4f': 4, 'Vector4': 4, 'NiagaraFloat': 1, 'NiagaraMatrix': 16}
        out, nf, ni = [], 0, 0
        for a in attrs:
            cls = str((a.get('Type') or {}).get('ClassStructOrEnum')).rsplit('.', 1)[-1]
            if cls in sizes:
                out.append((a.get('Name'), 'f', nf, sizes[cls]))
                nf += sizes[cls]
            elif cls == 'NiagaraID':
                out.append((a.get('Name'), 'i', ni, 2))
                ni += 2
            else:                                          # NiagaraInt32, NiagaraBool, enums
                out.append((a.get('Name'), 'i', ni, 1))
                ni += 1
        return out

    def counts(self):
        nf = sum(n for _, kind, _, n in self.attributes if kind == 'f')
        ni = sum(n for _, kind, _, n in self.attributes if kind == 'i')
        return nf, ni

    def run(self, n, floats, ints, age=0.0, dt=FRAME, rng=None):
        """Runs the script for n particles from data set columns floats, ints (arrays of n) -> their new columns."""
        rng = rng or np.random.default_rng(1)
        table = self.table.copy()
        for start in self.sets:
            table[(start + GLOBAL_DT) // 4] = np.frombuffer(np.float32(dt).tobytes(), '<u4')[0]
            table[(start + EMITTER_AGE) // 4] = np.frombuffer(np.float32(age).tobytes(), '<u4')[0]
            for row in range(4):                           # identity matrices (six of them; rows of 16 bytes)
                for m in range(6):
                    table[(start + 96 + 64 * m + 16 * row + 4 * row) // 4] = 0x3F800000
        regs = {}
        nfo, nio = self.counts()
        out_f = [np.zeros(n, np.float32) for _ in range(max(nfo, len(floats)))]
        out_i = [np.zeros(n, np.int32) for _ in range(max(nio, len(ints)))]
        mf = lambda v: v.view(np.float32)
        full = lambda v: np.full(n, v, np.uint32)

        def val(ins, k):
            x = ins.inputs[k]
            if ins.kinds >> k & 1:
                return full(table[x // 4] if x // 4 < len(table) else 0)
            return regs.get(x, np.zeros(n, np.uint32))

        def F(ins, k):
            return val(ins, k).view(np.float32)

        def I(ins, k):
            return val(ins, k).view(np.int32)

        def setf(r, v):
            regs[r] = np.asarray(v, np.float32).view(np.uint32)

        def seti(r, v):
            regs[r] = np.asarray(v, np.int32).view(np.uint32)

        for ins in self.script.instructions:
            op = ins.op
            if op in ('enter_stat_scope', 'exit_stat_scope', 'done', 'update_id', 'acquire_id'):
                continue
            if op == 'inputdata_float' or op == 'inputdata_noadvance_float':
                c = ins.args[1]
                regs[ins.outputs[0]] = (floats[c] if c < len(floats) else np.zeros(n, np.float32)).view(np.uint32)
            elif op == 'inputdata_int32' or op == 'inputdata_noadvance_int32':
                c = ins.args[1]
                regs[ins.outputs[0]] = (ints[c] if c < len(ints) else np.zeros(n, np.int32)).view(np.uint32)
            elif op == 'outputdata_float':
                c = ins.args[2]
                if c < len(out_f):
                    out_f[c] = val(ins, 0).view(np.float32).copy()
            elif op == 'outputdata_int32':
                c = ins.args[2]
                if c < len(out_i):
                    out_i[c] = val(ins, 0).view(np.int32).copy()
            elif op == 'acquireindex':
                seti(ins.outputs[0], np.arange(n))         # (no particle is removed here: run() reads their ages)
            elif op == 'exec_index':
                seti(ins.outputs[0], np.arange(n))
            elif op == 'external_func_call':
                self._external(ins, regs, table, n, setf, seti)
            elif op == 'add':
                setf(ins.outputs[0], F(ins, 0) + F(ins, 1))
            elif op == 'sub':
                setf(ins.outputs[0], F(ins, 0) - F(ins, 1))
            elif op == 'mul':
                setf(ins.outputs[0], F(ins, 0) * F(ins, 1))
            elif op == 'div':
                b = F(ins, 1)
                setf(ins.outputs[0], np.where(np.abs(b) > 1e-8, F(ins, 0) / np.where(b == 0, 1, b), 0.0))
            elif op == 'mad':
                setf(ins.outputs[0], F(ins, 0) * F(ins, 1) + F(ins, 2))
            elif op == 'lerp':
                a, b, t = F(ins, 0), F(ins, 1), F(ins, 2)
                setf(ins.outputs[0], a + t * (b - a))
            elif op == 'rcp':
                b = F(ins, 0)
                setf(ins.outputs[0], np.where(np.abs(b) > 1e-8, 1.0 / np.where(b == 0, 1, b), 0.0))
            elif op == 'rsq':
                b = F(ins, 0)
                setf(ins.outputs[0], np.where(b > 1e-8, 1.0 / np.sqrt(np.maximum(b, 1e-8)), 0.0))
            elif op == 'sqrt':
                setf(ins.outputs[0], np.sqrt(np.maximum(F(ins, 0), 0.0)))
            elif op == 'neg':
                setf(ins.outputs[0], -F(ins, 0))
            elif op == 'abs':
                setf(ins.outputs[0], np.abs(F(ins, 0)))
            elif op == 'exp':
                setf(ins.outputs[0], np.exp(F(ins, 0)))
            elif op == 'exp2':
                setf(ins.outputs[0], np.exp2(F(ins, 0)))
            elif op == 'log':
                setf(ins.outputs[0], np.log(np.maximum(F(ins, 0), 1e-30)))
            elif op == 'log2':
                setf(ins.outputs[0], np.log2(np.maximum(F(ins, 0), 1e-30)))
            elif op == 'sin':
                setf(ins.outputs[0], np.sin(F(ins, 0)))
            elif op == 'cos':
                setf(ins.outputs[0], np.cos(F(ins, 0)))
            elif op == 'tan':
                setf(ins.outputs[0], np.tan(F(ins, 0)))
            elif op == 'asin':
                setf(ins.outputs[0], np.arcsin(np.clip(F(ins, 0), -1, 1)))
            elif op == 'acos':
                setf(ins.outputs[0], np.arccos(np.clip(F(ins, 0), -1, 1)))
            elif op == 'atan':
                setf(ins.outputs[0], np.arctan(F(ins, 0)))
            elif op == 'atan2':
                setf(ins.outputs[0], np.arctan2(F(ins, 0), F(ins, 1)))
            elif op == 'ceil':
                setf(ins.outputs[0], np.ceil(F(ins, 0)))
            elif op == 'floor':
                setf(ins.outputs[0], np.floor(F(ins, 0)))
            elif op == 'fmod':
                b = F(ins, 1)
                setf(ins.outputs[0], np.where(b != 0, np.fmod(F(ins, 0), np.where(b == 0, 1, b)), 0.0))
            elif op == 'frac':
                a = F(ins, 0)
                setf(ins.outputs[0], a - np.trunc(a))
            elif op == 'trunc':
                setf(ins.outputs[0], np.trunc(F(ins, 0)))
            elif op == 'clamp':
                setf(ins.outputs[0], np.minimum(np.maximum(F(ins, 0), F(ins, 1)), F(ins, 2)))
            elif op == 'min':
                setf(ins.outputs[0], np.minimum(F(ins, 0), F(ins, 1)))
            elif op == 'max':
                setf(ins.outputs[0], np.maximum(F(ins, 0), F(ins, 1)))
            elif op == 'pow':
                setf(ins.outputs[0], np.power(np.maximum(F(ins, 0), 1e-30), F(ins, 1)))
            elif op == 'round':
                setf(ins.outputs[0], np.round(F(ins, 0)))
            elif op == 'sign':
                setf(ins.outputs[0], np.sign(F(ins, 0)))
            elif op == 'step':
                setf(ins.outputs[0], (F(ins, 1) >= F(ins, 0)).astype(np.float32))
            elif op == 'random':
                setf(ins.outputs[0], rng.random(n).astype(np.float32) * F(ins, 0))
            elif op == 'noise':
                setf(ins.outputs[0], np.zeros(n))
            elif op in ('cmplt', 'cmple', 'cmpgt', 'cmpge', 'cmpeq', 'cmpneq'):
                a, b = F(ins, 0), F(ins, 1)
                r = {'cmplt': a < b, 'cmple': a <= b, 'cmpgt': a > b, 'cmpge': a >= b, 'cmpeq': a == b,
                     'cmpneq': a != b}[op]
                seti(ins.outputs[0], np.where(r, BOOL_TRUE, 0))
            elif op == 'select':
                regs[ins.outputs[0]] = np.where(val(ins, 0) != 0, val(ins, 1), val(ins, 2)).astype(np.uint32)
            elif op == 'addi':
                seti(ins.outputs[0], I(ins, 0) + I(ins, 1))
            elif op == 'subi':
                seti(ins.outputs[0], I(ins, 0) - I(ins, 1))
            elif op == 'muli':
                seti(ins.outputs[0], I(ins, 0) * I(ins, 1))
            elif op == 'divi':
                b = I(ins, 1)
                seti(ins.outputs[0], np.where(b != 0, I(ins, 0) // np.where(b == 0, 1, b), 0))
            elif op == 'clampi':
                seti(ins.outputs[0], np.minimum(np.maximum(I(ins, 0), I(ins, 1)), I(ins, 2)))
            elif op == 'mini':
                seti(ins.outputs[0], np.minimum(I(ins, 0), I(ins, 1)))
            elif op == 'maxi':
                seti(ins.outputs[0], np.maximum(I(ins, 0), I(ins, 1)))
            elif op == 'absi':
                seti(ins.outputs[0], np.abs(I(ins, 0)))
            elif op == 'negi':
                seti(ins.outputs[0], -I(ins, 0))
            elif op == 'signi':
                seti(ins.outputs[0], np.sign(I(ins, 0)))
            elif op == 'randomi':
                seti(ins.outputs[0], rng.integers(0, np.maximum(I(ins, 0), 1)))
            elif op in ('cmplti', 'cmplei', 'cmpgti', 'cmpgei', 'cmpeqi', 'cmpneqi'):
                a, b = I(ins, 0), I(ins, 1)
                r = {'cmplti': a < b, 'cmplei': a <= b, 'cmpgti': a > b, 'cmpgei': a >= b, 'cmpeqi': a == b,
                     'cmpneqi': a != b}[op]
                seti(ins.outputs[0], np.where(r, BOOL_TRUE, 0))
            elif op == 'bit_and' or op == 'logic_and':
                regs[ins.outputs[0]] = val(ins, 0) & val(ins, 1)
            elif op == 'bit_or' or op == 'logic_or':
                regs[ins.outputs[0]] = val(ins, 0) | val(ins, 1)
            elif op == 'bit_xor' or op == 'logic_xor':
                regs[ins.outputs[0]] = val(ins, 0) ^ val(ins, 1)
            elif op == 'bit_not' or op == 'logic_not':
                regs[ins.outputs[0]] = ~val(ins, 0)
            elif op == 'bit_lshift':
                regs[ins.outputs[0]] = val(ins, 0) << (val(ins, 1) & 31)
            elif op == 'bit_rshift':
                seti(ins.outputs[0], I(ins, 0) >> (I(ins, 1) & 31))
            elif op == 'f2i':
                seti(ins.outputs[0], np.nan_to_num(F(ins, 0)).astype(np.int64).astype(np.int32))
            elif op == 'i2f':
                setf(ins.outputs[0], I(ins, 0).astype(np.float32))
            elif op == 'f2b':
                seti(ins.outputs[0], np.where(F(ins, 0) > 0.0, BOOL_TRUE, 0))
            elif op == 'b2f':
                setf(ins.outputs[0], np.where(val(ins, 0) != 0, 1.0, 0.0))
            elif op == 'i2b':
                seti(ins.outputs[0], np.where(I(ins, 0) > 0, BOOL_TRUE, 0))
            elif op == 'b2i':
                seti(ins.outputs[0], np.where(val(ins, 0) != 0, 1, 0))
            elif op in ('fasi', 'iasf'):
                regs[ins.outputs[0]] = val(ins, 0).copy()
            elif op == 'half_to_float':
                regs[ins.outputs[0]] = val(ins, 0).copy()
            else:
                raise NotImplementedError('VM operation %s' % op)
        return out_f, out_i

    def _external(self, ins, regs, table, n, setf, seti):
        name, owner = self.externals[ins.args[0]]
        key = owner.split('.', 1)[1] if owner.startswith('Emitter.') else owner
        curve = self.curves.get(key)
        array = self.arrays.get(key)

        def arg(k):
            v = ins.inputs[k]
            if v & niagara.EXT_REGISTER:
                return regs.get(v & 0x7FFF, np.zeros(n, np.uint32)).view(np.float32)
            return np.full(n, table[v // 4] if v // 4 < len(table) else 0, np.uint32).view(np.float32)

        if array is not None and name == 'Length':
            seti(ins.outputs[0], np.full(n, len(array)))
            return
        if array is not None and name == 'Get':
            index = arg(len(ins.inputs) - 1).view(np.int32)
            rows = np.asarray(array, np.float64).reshape(len(array), -1)
            picked = rows[np.clip(index, 0, len(rows) - 1)]
            whole = isinstance(array[0][0], int)
            for k, r in enumerate(ins.outputs):
                if r != 0xFFFF:
                    (seti if whole else setf)(r, picked[:, k])
            return
        if name in ('SampleCurve', 'SampleVectorCurve', 'SampleColorCurve') and curve is not None:
            ch, samples, (t0, t1) = curve
            x = arg(0)
            arr = np.asarray(samples, np.float64)
            pos = np.clip((x - t0) / max(1e-9, t1 - t0), 0.0, 1.0) * (len(samples) - 1)
            lo = np.clip(np.floor(pos).astype(int), 0, len(samples) - 1)
            hi = np.minimum(lo + 1, len(samples) - 1)
            f = (pos - lo)[..., None]
            v = arr[lo] * (1 - f) + arr[hi] * f
            for k, r in enumerate(ins.outputs):
                if r != 0xFFFF:
                    setf(r, v[:, min(k, v.shape[1] - 1)])
        else:
            self.warned.add(name + ':' + owner)
            for r in ins.outputs:
                if r != 0xFFFF:
                    setf(r, np.zeros(n))


class Run:
    """The measured particles: `frames` samples each of attribute name -> array (samples, particles, components);
    ages in seconds; lifetime per particle."""

    def __init__(self, names, history, lifetime, warned):
        self.names, self.history, self.lifetime, self.warned = names, history, lifetime, warned

    def attr(self, name):
        return self.history.get(name)


def simulate(spawn_props, update_props, curves, arrays=None, age=0.0, particles=PARTICLES, frames=MAX_FRAMES, seed=1,
             user=None):
    """Spawns `particles` at emitter age `age`, runs them `frames` frames (the emitter's age going on) -> Run. user: the
    system's exposed parameters {'User.Scale': [2.0, 2.0, 2.0]} (niagara.System.user), left at 0 without it."""
    rng = np.random.default_rng(seed)
    spawn = Script(spawn_props, curves, 'spawn', arrays, user)
    update = Script(update_props, curves, 'update', arrays, user)
    nf, ni = spawn.counts()
    floats = [np.zeros(particles, np.float32) for _ in range(nf)]
    ints = [np.zeros(particles, np.int32) for _ in range(ni)]
    floats, ints = spawn.run(particles, floats, ints, age, FRAME, rng)
    history = {}
    layout = {n: (kind, a, c) for n, kind, a, c in update.attributes}
    t = 0

    def record(fl, il):
        for name, (kind, a, c) in layout.items():
            src = fl if kind == 'f' else il
            history.setdefault(name, []).append(np.stack([src[a + k] for k in range(c)], axis=-1).astype(np.float64))

    lay_spawn = {n: (kind, a, c) for n, kind, a, c in spawn.attributes}
    remap_f = [np.zeros(particles, np.float32) for _ in range(update.counts()[0])]
    remap_i = [np.zeros(particles, np.int32) for _ in range(update.counts()[1])]
    for name, (kind, a, c) in layout.items():              # (the two scripts' attribute lists may differ)
        if name in lay_spawn and lay_spawn[name][0] == kind:
            s = lay_spawn[name][1]
            for k in range(c):
                (remap_f if kind == 'f' else remap_i)[a + k] = (floats if kind == 'f' else ints)[s + k]
    floats, ints = remap_f, remap_i
    record(floats, ints)
    for t in range(1, frames):
        floats, ints = update.run(particles, floats, ints, age + t * FRAME, FRAME, rng)
        record(floats, ints)
    history = {k: np.stack(v, axis=0) for k, v in history.items()}
    life = history['Lifetime'][0, :, 0] if 'Lifetime' in history else None
    return Run(list(layout), history, life, spawn.warned | update.warned)
