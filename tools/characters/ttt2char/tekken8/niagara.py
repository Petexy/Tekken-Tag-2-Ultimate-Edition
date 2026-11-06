"""Tekken 8's effects: Niagara systems (cooked Unreal Engine 5 NS_*.uasset), read for TTT2's effect files
(convert/effects8.py).

A NiagaraSystem lists its EmitterHandles {Name, bIsEnabled, VersionedInstance.Emitter}; a NiagaraEmitter's
VersionData[0] holds SimTarget (CPUSim 0, GPUComputeSim 1), bLocalSpace, FixedBounds (cm), RendererProperties (sprite,
mesh, ribbon, light renderer objects: Material, or Meshes[k].Mesh + OverrideMaterials[k].ExplicitMat, SubImageSize,
Alignment, FacingMode) and its scripts (SpawnScriptProps.Script, UpdateScriptProps.Script; a GPU emitter's particles
run in GPUComputeScript, a compute shader). A script's CachedDefaultDataInterfaces name its data interfaces by module
and input ('Emitter.ScaleSpriteSize001.Uniform Curve Sprite Scale'): curves are cooked into lookup tables (ShaderLUT,
LUTNumSamplesMinusOne + 1 samples of each channel, interleaved, over LUTMinTime .. LUTMaxTime, default 0 .. 1),
colour arrays into ColorData. A system SkeletalMesh interface's FilteredBones names the bone the system follows (Miary
Zo's staff systems: ATH_R_spear, SourceMode AttachParent).

The CPU scripts (the system's spawn and update scripts, which also run every emitter's spawn and lifecycle modules,
and a CPU emitter's particle scripts) are Niagara VM bytecode (CachedScriptVM.ByteCode) with their constants baked
in (cooked: rapid-iteration parameters folded into ScriptLiterals). Instruction format (classic VectorVM): u8 opcode,
then for math ops u8 operand kinds (bit k: input k is a constant), u16 per input (a register, or a constant's byte
offset), u16 output register; inputdata u16 data set, u16 data-set register, u16 register; outputdata u8 kinds, u16
data set, u16 index register, u16 input, u16 data-set register; acquireindex u8 kinds, u16 data set, u16 input,
u16 register; external_func_call u8 function (CalledVMExternalFunctions: its inputs and outputs), u16 per input (bit
15: a register, else a constant) and per output; enter_stat_scope u16 (a constant: the StatScopes index of the module
it opens); exit_stat_scope; exec_index u16. A script's constants: engine parameters, its parameter store, then
ScriptLiterals; the first literal is the outermost scope's index (the first enter_stat_scope's constant), which places
the literals. The stat scopes name each module ('SpawnBurst_Instantaneous001_Aura001'), so a module's literals are
the constants used inside its scope (SpawnBurst: count = the literal multiplied by the spawn-count scale, spawn time =
the literal it is compared with (0: none); SpawnRate: the rate per second; InitializeParticle (CPU particles): its
random ranges, lifetime first).

Not read: the GPU particle scripts' constants (lifetime, size, velocity, colour of a GPU emitter are compiled into its
shader); convert/effects8.py approximates them.

Written for this project from the files themselves (no third-party code).
"""
import struct

from . import uprops

FILTERED_BONES = 'FilteredBones'
CPU, GPU = 0, 1

# ------------------------------------------------------------------------------------------- VM bytecode
OPS = ('done add sub mul div mad lerp rcp rsq sqrt neg abs exp exp2 log log2 sin cos tan asin acos atan atan2 ceil '
       'floor fmod frac trunc clamp min max pow round sign step random noise cmplt cmple cmpgt cmpge cmpeq cmpneq '
       'select addi subi muli divi clampi mini maxi absi negi signi randomi cmplti cmplei cmpgti cmpgei cmpeqi cmpneqi '
       'bit_and bit_or bit_xor bit_not bit_lshift bit_rshift logic_and logic_or logic_xor logic_not f2i i2f f2b b2f '
       'i2b b2i inputdata_float inputdata_int32 inputdata_half inputdata_noadvance_float inputdata_noadvance_int32 '
       'inputdata_noadvance_half outputdata_float outputdata_int32 outputdata_half acquireindex external_func_call '
       'exec_index noise2D noise3D enter_stat_scope exit_stat_scope update_id acquire_id half_to_float fasi '
       'iasf').split()
TERNARY = {'mad', 'lerp', 'clamp', 'select', 'clampi'}
UNARY = {'rcp', 'rsq', 'sqrt', 'neg', 'abs', 'exp', 'exp2', 'log', 'log2', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan',
         'ceil', 'floor', 'frac', 'trunc', 'round', 'sign', 'random', 'absi', 'negi', 'signi', 'randomi', 'bit_not',
         'logic_not', 'f2i', 'i2f', 'f2b', 'b2f', 'i2b', 'b2i', 'half_to_float', 'fasi', 'iasf'}
EXT_REGISTER = 0x8000
MIN_SECONDS = 1e-6                 # literals below this are ints' words read as floats (EmitterState's enums)


class Instruction:
    """op, kinds (operand kinds: bit k = input k is a constant), inputs [u16], outputs [u16] (registers)."""
    __slots__ = ('op', 'kinds', 'inputs', 'outputs', 'args')

    def __init__(self, op, kinds=0, inputs=(), outputs=(), args=()):
        self.op, self.kinds, self.inputs, self.outputs, self.args = op, kinds, list(inputs), list(outputs), args

    def constant_inputs(self):
        """The byte offsets of the inputs that are constants."""
        if self.op == 'external_func_call':
            return [v for v in self.inputs if v != 0xFFFF and not v & EXT_REGISTER]
        return [v for k, v in enumerate(self.inputs) if self.kinds >> k & 1]

    def __repr__(self):
        return '%s(%s -> %s)' % (self.op, self.inputs, self.outputs)


def disassemble(code, externals=()):
    """VM bytecode -> [Instruction] (externals: [(inputs, outputs)] of the script's external functions). Raises
    ValueError on an opcode it does not know (the format is the classic VectorVM's)."""
    out, p, n = [], 0, len(code)

    def u16s(k):
        nonlocal p
        if p + 2 * k > n:
            raise ValueError('bytecode ends inside an instruction at %d' % p)
        v = struct.unpack_from('<%dH' % k, code, p)
        p += 2 * k
        return list(v)
    while p < n:
        o = code[p]
        p += 1
        if o >= len(OPS):
            raise ValueError('unknown VM opcode %d at %d' % (o, p - 1))
        op = OPS[o]
        if op == 'done':
            out.append(Instruction(op))
            break
        if op == 'enter_stat_scope':
            out.append(Instruction(op, 1, u16s(1)))
        elif op == 'exit_stat_scope':
            out.append(Instruction(op))
        elif op.startswith('inputdata'):
            a = u16s(3)
            out.append(Instruction(op, 0, [], [a[2]], (a[0], a[1])))
        elif op.startswith('outputdata'):
            kinds = code[p]
            p += 1
            a = u16s(4)
            out.append(Instruction(op, kinds & 1, [a[2]], [], (a[0], a[1], a[3])))
        elif op == 'acquireindex':
            kinds = code[p]
            p += 1
            a = u16s(3)
            out.append(Instruction(op, kinds & 1, [a[1]], [a[2]], (a[0],)))
        elif op == 'external_func_call':
            f = code[p]
            p += 1
            if f >= len(externals):
                raise ValueError('external function %d of %d' % (f, len(externals)))
            nin, nout = externals[f]
            a = u16s(nin + nout)
            out.append(Instruction(op, 0, a[:nin], a[nin:], (f,)))
        elif op == 'exec_index':
            out.append(Instruction(op, 0, [], u16s(1)))
        elif op in ('update_id', 'acquire_id'):
            out.append(Instruction(op, 0, [], [], tuple(u16s(3))))
        elif op in ('noise2D', 'noise3D'):
            raise ValueError('VM noise op at %d (not read)' % (p - 1))
        else:
            k = 3 if op in TERNARY else 1 if op in UNARY else 2
            kinds = code[p]
            p += 1
            a = u16s(k + 1)
            out.append(Instruction(op, kinds, a[:k], a[k:]))
    return out


class Script:
    """A NiagaraScript's compiled VM code: instructions, its constants (value(offset)), its modules' scopes."""

    def __init__(self, props):
        vm = props.get('CachedScriptVM') or {}
        self.usage = props.get('Usage')
        self.code = bytes(((vm.get('ByteCode') or {}).get('Data')) or b'')
        self.literals = bytes(vm.get('ScriptLiterals') or b'')
        self.scope_names = [s.get('FriendlyName') for s in vm.get('StatScopes') or []]
        ext = vm.get('CalledVMExternalFunctions') or []
        self.externals = [(len(x.get('InputParamLocations') or []), int(x.get('NumOutputs') or 0)) for x in ext]
        self.external_names = [x.get('Name') for x in ext]
        self.attributes = [a.get('Name') for a in vm.get('Attributes') or []]
        self.data_interfaces = [(d.get('Name'), d.get('DataInterface'))
                                for d in props.get('CachedDefaultDataInterfaces') or []]
        self.instructions = disassemble(self.code, self.externals) if self.code else []
        first = next((i for i in self.instructions if i.op == 'enter_stat_scope'), None)
        self.base = first.inputs[0] if first is not None else None

    def word(self, offset):
        """The literal at a constant's byte offset -> (u32, f32), or None (an engine or parameter-store value)."""
        if self.base is None or offset < self.base:
            return None
        k = offset - self.base
        if k % 4 or k + 4 > len(self.literals):
            return None
        return struct.unpack_from('<I', self.literals, k)[0], struct.unpack_from('<f', self.literals, k)[0]

    def scoped(self):
        """[(scope names, open at the instruction (outermost first), Instruction)] of the code, the scope
        instructions left out."""
        out, stack = [], []
        for ins in self.instructions:
            if ins.op == 'enter_stat_scope':
                w = self.word(ins.inputs[0])
                stack.append(self.scope_names[w[0]] if w and w[0] < len(self.scope_names) else '?')
            elif ins.op == 'exit_stat_scope':
                if stack:
                    stack.pop()
            else:
                out.append((tuple(stack), ins))
        return out

    def module(self, name):
        """[Instruction] in the innermost scope `name` (a module of one emitter, e.g. 'SpawnRate_Aura001')."""
        return [ins for scopes, ins in self.scoped() if scopes and scopes[-1] == name]

    def floats(self, instructions, ops=None):
        """[(op, f32)] of the literal constants the instructions use (ops: only those operations')."""
        out = []
        for ins in instructions:
            if ops is not None and ins.op not in ops:
                continue
            for o in ins.constant_inputs():
                w = self.word(o)
                if w is not None:
                    out.append((ins.op, w[1]))
        return out


# ------------------------------------------------------------------------------------------- the system
class Renderer:
    """kind ('sprite', 'mesh', 'ribbon', 'light', ...), material (object path), meshes [(mesh, material)], sub_images
    (columns, rows), alignment / facing (enum names), enabled."""

    def __init__(self, cls, props):
        self.kind = cls.replace('Niagara', '').replace('RendererProperties', '').lower()
        self.props = props
        self.enabled = props.get('bIsEnabled', True) is not False
        self.material = props.get('Material')
        overrides = [m.get('ExplicitMat') for m in props.get('OverrideMaterials') or []] \
            if props.get('bOverrideMaterials') else []
        self.meshes = [(m.get('Mesh'), overrides[k] if k < len(overrides) else None)
                       for k, m in enumerate(props.get('Meshes') or [])]
        sub = props.get('SubImageSize') or {}
        self.sub_images = (max(1, int(round(sub.get('X', 1.0) or 1.0))), max(1, int(round(sub.get('Y', 1.0) or 1.0))))
        self.alignment = getattr(props.get('Alignment'), 'name', None)
        self.facing = getattr(props.get('FacingMode'), 'name', None)


class Emitter:
    """name, enabled, gpu, local (bLocalSpace), bounds ((min, max) cm or None), renderers, curves {module.input:
    (channels, [[values per sample]] over 0..1 of its time range, (min time, max time))}, colours {module.input:
    [(r, g, b, a)]}, bursts [(time s, count)], rate (per second) or 0, per_unit (spawn by distance: True), loop
    (seconds or None), modules (the module names its scripts have), literals {module: [(op, f32)]} (CPU emitters'
    particle modules)."""

    def __init__(self, name):
        self.name = name
        self.enabled, self.gpu, self.local, self.bounds = True, True, False, None
        self.renderers, self.curves, self.colours = [], {}, {}
        self.bursts, self.rate, self.per_unit, self.loop = [], 0.0, False, None
        self.modules, self.literals = [], {}

    def __repr__(self):
        return '<Emitter %s %s %s bursts %s rate %g>' % (self.name, 'GPU' if self.gpu else 'CPU',
                                                         [r.kind for r in self.renderers], self.bursts, self.rate)


class System:
    """A Niagara system: name, path, bones (the bones its skeletal-mesh interfaces follow), bounds, emitters."""

    def __init__(self, store, path):
        self.path = path.split('.')[0]
        self.pkg = pkg = store.package(self.path)
        self.objects = {ex.path.lower(): ex for ex in pkg.exports}
        main = next((ex for ex in pkg.exports if ex.class_name == 'NiagaraSystem'), None)
        if main is None:
            raise KeyError('%s has no Niagara system' % path)
        self.name = main.name
        props = self._props(main)
        b = props.get('FixedBounds') or {}
        self.bounds = _bounds(b) if props.get('bFixedBounds') else None
        self.scripts = {}
        for key in ('SystemSpawnScript', 'SystemUpdateScript'):
            s = self._script(props.get(key))
            if s is not None:
                self.scripts[key] = s
        self.bones = []
        for s in self.scripts.values():
            for _, ref in s.data_interfaces:
                ex = self._export(ref)
                if ex is not None and 'SkeletalMesh' in ex.class_name:
                    for bone in self._props(ex).get(FILTERED_BONES) or []:
                        if bone not in self.bones:
                            self.bones.append(bone)
        self.emitters = []
        for h in props.get('EmitterHandles') or []:
            ref = (h.get('VersionedInstance') or {}).get('Emitter')
            ex = self._export(ref)
            if ex is None:
                continue
            e = self._emitter(ex)
            e.enabled = h.get('bIsEnabled', True) is not False
            self.emitters.append(e)
        update = self.scripts.get('SystemUpdateScript')
        if update is not None:
            for e in self.emitters:
                _spawn_modules(update, e)

    # --------------------------------------------------------------------------------------- pieces
    def _export(self, ref):
        return self.objects.get(ref.lower()) if isinstance(ref, str) else None

    def _props(self, ex):
        return uprops.read(self.pkg, ex)[0]

    def _script(self, ref):
        ex = self._export(ref)
        if ex is None:
            return None
        try:
            return Script(self._props(ex))
        except (ValueError, KeyError, NotImplementedError):
            return None

    def _emitter(self, ex):
        props = self._props(ex)
        e = Emitter(props.get('UniqueEmitterName') or ex.name)
        v = (props.get('VersionData') or [{}])[0]
        e.gpu = int(v.get('SimTarget') or 0) == GPU
        e.local = bool(v.get('bLocalSpace'))
        if v.get('FixedBounds'):
            e.bounds = _bounds(v['FixedBounds'])
        for ref in v.get('RendererProperties') or []:
            rex = self._export(ref)
            if rex is None:
                continue
            try:
                e.renderers.append(Renderer(rex.class_name, self._props(rex)))
            except (ValueError, KeyError, NotImplementedError):
                continue
        for key in ('SpawnScriptProps', 'UpdateScriptProps'):
            s = self._script((v.get(key) or {}).get('Script'))
            if s is None:
                continue
            for name, ref in s.data_interfaces:
                self._data_interface(e, name, self._export(ref))
            for a in s.attributes:
                parts = (a or '').split('.')
                if len(parts) >= 3 and parts[0] in ('Particles', e.name) and parts[1] not in e.modules:
                    e.modules.append(parts[1])
            if not e.gpu and s.code:
                for scopes, ins in s.scoped():
                    if len(scopes) >= 2 and scopes[-1].endswith('_Emitter'):
                        e.literals.setdefault(scopes[-1][:-len('_Emitter')], []).extend(s.floats([ins]))
        return e

    def _data_interface(self, e, name, ex):
        if ex is None or not name:
            return
        key = name.split('.', 1)[1] if name.startswith(('Emitter.', e.name + '.')) else name
        try:
            p = self._props(ex)
        except (ValueError, KeyError, NotImplementedError):
            return
        if 'ShaderLUT' in p:
            lut = [float(x) for x in p.get('ShaderLUT') or []]
            n = int(round(float(p.get('LUTNumSamplesMinusOne') or 0.0))) + 1
            if lut and n > 0 and len(lut) % n == 0:
                ch = len(lut) // n
                e.curves[key] = (ch, [lut[i * ch:(i + 1) * ch] for i in range(n)],
                                 (float(p.get('LUTMinTime') or 0.0), float(p.get('LUTMaxTime', 1.0) or 1.0)))
        elif 'ColorData' in p:
            e.colours[key] = [(c.get('R', 0.0), c.get('G', 0.0), c.get('B', 0.0), c.get('A', 1.0))
                              for c in p.get('ColorData') or []]


def _bounds(b):
    lo, hi = b.get('Min') or {}, b.get('Max') or {}
    return ([float(lo.get(k, 0.0)) for k in 'XYZ'], [float(hi.get(k, 0.0)) for k in 'XYZ'])


def _spawn_modules(script, e):
    """An emitter's bursts, rate, spawn by distance and loop length from the system update script's modules."""
    suffix = '_' + e.name
    seen = []
    for scopes, ins in script.scoped():
        if scopes and scopes[-1].endswith(suffix) and scopes[-1] not in seen:
            seen.append(scopes[-1])
    for scope in seen:
        module = scope[:-len(suffix)]
        ins = script.module(scope)
        lits = script.floats(ins)
        if module.startswith('SpawnBurst_Instantaneous'):
            count = next((v for op, v in lits if op in ('mul', 'max') and v >= 1.0), 1.0)
            time = next((v for op, v in lits if op == 'sub' and v > 0.0), 0.0)
            e.bursts.append((float(time), max(1, int(count))))
        elif module.startswith('SpawnRate'):
            e.rate += next((v for op, v in lits if op == 'mul' and v > 0.0), 0.0)
        elif module.startswith('SpawnPerUnit'):
            e.per_unit = True
        elif module.startswith('EmitterState'):
            e.loop = next((v for op, v in lits if op == 'select' and v > MIN_SECONDS), None)   # (an int's word:
                                                                                   # a denormal, not a time)
        elif module.startswith('PolarisSpawnRate'):          # Tekken 8's own spawn module (its rate is an input)
            e.per_unit = e.per_unit or not e.bursts


def read(store, path):
    """The Niagara system at `path` (an object or package path) -> System."""
    return System(store, path)


# ------------------------------------------------------------------------------------------- effect table
def effect_table(store, code):
    """A fighter's Tekken 8 effect table DA_CharacterEffect_<CODE> -> {effect id: {'system': NS object path, 'attached':
    isAttachedCharacter, ...the entry's other flags}} (empty when the fighter has none)."""
    path = '/Game/Effect/Polaris%swork/Character/%s/DA_CharacterEffect_%s' % (code.upper(), code, code.upper())
    try:
        pkg = store.package(path)
    except (KeyError, OSError, ValueError):
        return {}
    props = uprops.read(pkg, pkg.main_export())[0]
    out = {}
    for k, e in (props.get('CharacterEffect') or {}).items():
        if not isinstance(e, dict) or not e.get('ParticleAsset'):
            continue
        out[int(k)] = {'system': e.get('ParticleAsset'), 'attached': bool(e.get('isAttachedCharacter')),
                       'rotation': bool(e.get('isSelfRotation')), 'opponent': bool(e.get('isGetAitePosition'))}
    return out
