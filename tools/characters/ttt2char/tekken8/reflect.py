"""The class and struct layouts of Tekken 8's program, read statically from Polaris-Win64-Shipping.exe.

Cooked Unreal Engine 5 packages store properties "unversioned": by their index in the class's property list, with
no names or types (uprops.py). Those lists are in the program: Unreal's code generator (UHT) emits a constant
description of every class, struct and enum, which the engine turns into its reflection data at start-up. They are
found here by their layout in .rdata/.data (UE 5.1/5.2, x64; every pointer an absolute address):
    FClassParams (80 bytes): +0 ClassNoRegisterFunc (X::StaticClass: its code passes the class's name and package
        as UTF-16 strings, 'Texture2D' and '/Script/Engine'; a leading jmp is followed), +8 config name, +16 C++
        class info, +24 DependencySingletonFuncArray (the first: Z_Construct_UClass_<Super>, whose code refers to
        the super's FClassParams), +32 functions, +40 PropertyArray, +48 interfaces, +56 i32 dependency count,
        +60 i32 function count, +64 i32 NumProperties, +68 i32 interface count, +72 u32 ClassFlags
    FStructParams: +0 OuterFunc, +8 SuperFunc (Z_Construct_UScriptStruct_<Super> or 0), +16 StructOpsFunc,
        +24 NameUTF8, +32 SizeOf, +40 AlignOf, +48 PropertyArray, +56 i32 NumProperties, +60 ObjectFlags,
        +64 StructFlags (0x20 Immutable: serialised as its properties' raw values, in order, e.g. Guid); the
        StructOpsFunc allocates a UScriptStruct::TCppStructOps<T>: its vtable's second function (GetCapabilities)
        writes the struct's capabilities, `mov word [rdx+8], bits` with bit 3 HasSerializer and bit 4
        HasStructuredSerializer: such a struct is serialised by its own code, not as properties
    FPropertyParams: +0 NameUTF8, +8 RepNotify, +16 u64 PropertyFlags, +24 u8 EPropertyGenFlags (low 6 bits the
        type: 0 Byte, 1 Int8, 2 Int16, 3 Int, 4 Int64, 5 UInt16, 6 UInt32, 7 UInt64, 0xA Float, 0xB Double, 0xC Bool,
        0xD SoftClass, 0xE WeakObject, 0xF LazyObject, 0x10 SoftObject, 0x11 Class, 0x12 Object, 0x13 Interface,
        0x14 Name, 0x15 Str, 0x16 Array, 0x17 Map, 0x18 Set, 0x19 Struct, 0x1A Delegate, 0x1B/0x1C multicast
        delegates, 0x1D Text, 0x1E Enum, 0x1F FieldPath, 0x20 LargeWorldCoordinatesReal (a double)), +28 ObjectFlags,
        +32 i32 ArrayDim, +40 setter, +48 getter, +56 i32 Offset, +64 the type's own: ScriptStructFunc (struct),
        ClassFunc (object), EnumFunc (byte, enum)
    FEnumParams: +0 OuterFunc, +8 DisplayNameFunc, +16 NameUTF8, +24 CppTypeUTF8, +32 FEnumeratorParam[] {char*
        name, i64 value}, +40 i32 count
In a PropertyArray a container's inner properties come right before it: an array's or set's element, an enum
property's underlying integer, a map's value then key ('<Name>_Key'); the engine walks the array backwards and
each container takes the entries before it, so the list keeps the array's order. The unversioned property order of
a class or struct is its own properties first, then its super's, and so on (each property ArrayDim times).

The scan takes a few seconds; its result is cached as JSON in $XDG_CACHE_HOME/ttt2/tekken8/ (~/.cache), named
after the program's size and modification time, so later runs load it in a fraction of a second.

Written for this project from the program itself (no third-party code).
"""
import bisect
import json
import os
import re
import struct
import tempfile

import numpy as np

CACHE = os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'ttt2', 'tekken8')
SCHEMA_VERSION = 3                          # bump when the scan's output changes (old caches are then ignored)
TYPES = {0x00: 'Byte', 0x01: 'Int8', 0x02: 'Int16', 0x03: 'Int', 0x04: 'Int64', 0x05: 'UInt16', 0x06: 'UInt32',
         0x07: 'UInt64', 0x0A: 'Float', 0x0B: 'Double', 0x0C: 'Bool', 0x0D: 'SoftClass', 0x0E: 'WeakObject',
         0x0F: 'LazyObject', 0x10: 'SoftObject', 0x11: 'Class', 0x12: 'Object', 0x13: 'Interface', 0x14: 'Name',
         0x15: 'Str', 0x16: 'Array', 0x17: 'Map', 0x18: 'Set', 0x19: 'Struct', 0x1A: 'Delegate',
         0x1B: 'InlineMulticastDelegate', 0x1C: 'SparseMulticastDelegate', 0x1D: 'Text', 0x1E: 'Enum',
         0x1F: 'FieldPath', 0x20: 'LargeWorldCoordinatesReal'}
OBJECT_TYPES = ('Object', 'Class', 'SoftObject', 'SoftClass', 'WeakObject', 'LazyObject', 'Interface')
STRUCT_IMMUTABLE = 0x20
CAPABILITY_SERIALIZERS = 0x18               # FCapabilities bits HasSerializer | HasStructuredSerializer
CAPABILITIES_STORE = b'\x66\xc7\x42\x08'      # mov word [rdx+8], imm16 (in GetCapabilities)
MAX_COUNT = 4096                            # properties, enumerators, dependencies: sanity bounds of the scan
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


# ---------------------------------------------------------------------------------------------------- the exe
class _Exe:
    def __init__(self, path):
        with open(path, 'rb') as f:
            self.d = d = f.read()
        if d[:2] != b'MZ':
            raise ValueError('%s is not a Windows program' % path)
        pe, = struct.unpack_from('<I', d, 0x3C)
        nsec, = struct.unpack_from('<H', d, pe + 6)
        opt = pe + 24
        self.base, = struct.unpack_from('<Q', d, opt + 24)
        osz, = struct.unpack_from('<H', d, pe + 20)
        self.sections = {}
        spans = []
        for i in range(nsec):
            o = opt + osz + 40 * i
            name = d[o:o + 8].rstrip(b'\0').decode('latin-1')
            vsize, va, rsize, raw = struct.unpack_from('<IIII', d, o + 8)
            self.sections[name] = (self.base + va, vsize, raw, rsize)
            spans.append((self.base + va, self.base + va + min(vsize, rsize), raw))
        spans.sort()
        self._starts = [s[0] for s in spans]
        self._spans = spans
        pv, pn, praw, _ = self.sections['.pdata']
        pd = np.frombuffer(d, '<u4', (pn // 12) * 3, praw).reshape(-1, 3)
        pd = pd[pd[:, 0] != 0]
        order = np.argsort(pd[:, 0])
        self.fbegin = pd[order, 0].astype(np.int64) + self.base
        self.fend = pd[order, 1].astype(np.int64) + self.base
        tv, tn, _, _ = self.sections['.text']
        self.text = (tv, tv + tn)
        self.data = [(v, v + min(n, r)) for v, n, _, r in (self.sections['.rdata'], self.sections['.data'])]
        self._leas = {}

    def offset(self, va):
        i = bisect.bisect_right(self._starts, va) - 1
        if i >= 0:
            lo, hi, raw = self._spans[i]
            if va < hi:
                return raw + va - lo
        return None

    def q(self, va):
        o = self.offset(va)
        return struct.unpack_from('<Q', self.d, o)[0] if o is not None else 0

    def i32(self, va):
        o = self.offset(va)
        return struct.unpack_from('<i', self.d, o)[0] if o is not None else 0

    def in_text(self, va):
        return self.text[0] <= va < self.text[1]

    def in_data(self, va):
        return any(lo <= va < hi for lo, hi in self.data)

    def cstr(self, va):
        """An ASCII (identifier-like, '::' allowed) C string in a data section, or None."""
        if not va or not self.in_data(va):
            return None
        o = self.offset(va)
        e = self.d.find(b'\0', o, o + 256)
        if e <= o:
            return None
        s = self.d[o:e]
        if not all(32 < c < 127 for c in s):
            return None
        return s.decode()

    def wstr(self, va):
        """An ASCII UTF-16 string in a data section, or None."""
        if not va or not self.in_data(va):
            return None
        o = self.offset(va)
        out = []
        while len(out) < 128:
            c, = struct.unpack_from('<H', self.d, o + 2 * len(out))
            if c == 0:
                break
            if not 32 <= c < 127:
                return None
            out.append(chr(c))
        return ''.join(out) or None

    def function(self, va):
        i = int(np.searchsorted(self.fbegin, va, side='right')) - 1
        if i >= 0 and self.fbegin[i] <= va < self.fend[i]:
            return int(self.fbegin[i]), int(self.fend[i])
        return None

    def leas(self, fva, depth=0):
        """Targets of the rip-relative lea instructions of the function at fva (one that starts with a jmp: its
        target's)."""
        if fva in self._leas:
            return self._leas[fva]
        out = []
        if self.in_text(fva):
            o = self.offset(fva)
            if self.d[o] == 0xE9 and depth < 3:
                out = self.leas(fva + 5 + struct.unpack_from('<i', self.d, o + 1)[0], depth + 1)
            else:
                f = self.function(fva)
                if f is not None:
                    lo, hi = self.offset(f[0]), self.offset(f[0]) + (f[1] - f[0])
                    code = self.d
                    i = code.find(b'\x8d', lo + 1, hi)
                    while i >= 0:
                        if code[i - 1] in (0x48, 0x4C) and code[i + 1] & 0xC7 == 0x05 and i + 6 <= hi:
                            disp, = struct.unpack_from('<i', code, i + 2)
                            out.append(f[0] + (i - lo) + 6 + disp)
                        i = code.find(b'\x8d', i + 1, hi)
        self._leas[fva] = out
        return out


# ---------------------------------------------------------------------------------------------------- scanning
def _candidates(x):
    """VAs of the data that look like FClassParams (in .rdata) and FStructParams (in .data, where MSVC puts them)."""
    classes, structs = [], []
    tv0, tv1 = np.uint64(x.text[0]), np.uint64(x.text[1])
    lo, hi = np.uint64(x.base), np.uint64(x.base + 0x10000000)
    m32 = np.uint64(0xFFFFFFFF)
    for name in ('.rdata', '.data'):
        v, vs, raw, rs = x.sections[name]
        n = min(vs, rs) // 8
        a = np.concatenate([np.frombuffer(x.d, np.uint64, n, raw), np.zeros(10, np.uint64)])  # (to the very end)
        ptr = (a >= lo) & (a < hi)
        code = (a >= tv0) & (a < tv1)
        i = np.arange(n)
        c = code[i] & ((a[i + 1] == 0) | ptr[i + 1]) & ((a[i + 3] == 0) | ptr[i + 3]) & ((a[i + 5] == 0) | ptr[i + 5])
        deps, funcs = a[i + 7] & m32, a[i + 7] >> np.uint64(32)
        props, ifaces = a[i + 8] & m32, a[i + 8] >> np.uint64(32)
        c &= (deps >= 1) & (deps < 64) & (funcs < MAX_COUNT) & (props < MAX_COUNT) & (ifaces < 64)
        c &= ~ptr[i + 7] & ~ptr[i + 8]
        if name == '.rdata':                # UHT's class parameters are constant (look-alikes in .data are not)
            classes += (v + 8 * np.nonzero(c)[0]).tolist()
        s = ptr[i + 3] & ((a[i + 6] == 0) | ptr[i + 6]) & ((a[i] == 0) | code[i]) & ((a[i + 1] == 0) | code[i + 1])
        s &= (a[i + 2] == 0) | code[i + 2]
        count, oflags = a[i + 7] & m32, a[i + 7] >> np.uint64(32)
        s &= (count < MAX_COUNT) & ((oflags & np.uint64(0xFFFF)) != 0) & (oflags < np.uint64(0x10000))
        s &= (a[i + 4] > 0) & (a[i + 4] < (1 << 24)) & (a[i + 5] > 0) & (a[i + 5] <= 64)
        structs += (v + 8 * np.nonzero(s)[0]).tolist()
    return classes, structs


class _Scan:
    def __init__(self, exe_path):
        self.x = x = _Exe(exe_path)
        class_vas, struct_vas = _candidates(x)
        self.class_params = {}                  # va -> dict
        for va in class_vas:
            name = package = None
            for t in x.leas(x.q(va)):
                w = x.wstr(t)
                if not w:
                    continue
                if w.startswith('/Script/') and package is None:
                    package = w
                elif name is None and IDENT.match(w):
                    name = w
            if name is None:
                continue
            n, arr = x.i32(va + 64), x.q(va + 40)
            if n and not x.in_data(arr):
                continue
            self.class_params[va] = dict(name=name, package=package, props_va=arr, nprops=n, deps=x.q(va + 24),
                                         ndeps=x.i32(va + 56), flags=x.i32(va + 72) & 0xFFFFFFFF)
        self.struct_params = {}
        for va in struct_vas:
            name = x.cstr(x.q(va + 24))
            if not name or not IDENT.match(name):
                continue
            n, arr = x.i32(va + 56), x.q(va + 48)
            if n and not x.in_data(arr):
                continue
            self.struct_params[va] = dict(name=name, props_va=arr, nprops=n, super_func=x.q(va + 8),
                                          size=x.q(va + 32), flags=x.i32(va + 64) & 0xFFFFFFFF,
                                          serializer=self._serializer(x.q(va + 16)))
        # unique keys: a class by its path ('/Script/Engine.Texture2D'), a struct by its name (a repeated name
        # gets '@<address>')
        self.class_key, self.struct_key, taken = {}, {}, set()
        for va in sorted(self.class_params):
            c = self.class_params[va]
            key = '%s.%s' % (c['package'], c['name']) if c['package'] else c['name']
            self.class_key[va] = key + '@%x' % va if key in taken else key
            taken.add(key)
        taken = set()
        for va in sorted(self.struct_params):
            key = self.struct_params[va]['name']
            self.struct_key[va] = key + '@%x' % va if key in taken else key
            taken.add(key)
        self.enums = {}
        self._enum_of = {}
        self._class_of = {}

    def _serializer(self, ops_func):
        """Whether a struct has a serialiser of its own (None: not known, e.g. no StructOpsFunc)."""
        x = self.x
        if not ops_func or not x.in_text(ops_func):
            return None
        for vt in x.leas(ops_func):
            caps = x.q(vt + 8) if x.in_data(vt) else 0
            if not x.in_text(caps):
                continue
            o = x.offset(caps)
            i = x.d.find(CAPABILITIES_STORE, o, o + 48)
            if i >= 0:
                bits, = struct.unpack_from('<H', x.d, i + 4)
                return bool(bits & CAPABILITY_SERIALIZERS)
        return None

    def _target(self, func, table):
        if not func or not self.x.in_text(func):
            return None
        for t in self.x.leas(func):
            if t in table:
                return t
        return None

    def _enum(self, func):
        """The enum an EnumFunc constructs -> its name (its enumerators go to self.enums), or None."""
        if func in self._enum_of:
            return self._enum_of[func]
        x, name = self.x, None
        if func and x.in_text(func):
            for t in x.leas(func):
                if not x.in_data(t):
                    continue
                nm, arr, n = x.cstr(x.q(t + 16)), x.q(t + 32), x.i32(t + 40)
                if not nm or not (0 < n < MAX_COUNT) or not x.in_data(arr):
                    continue
                values = {}
                for k in range(n):
                    en = x.cstr(x.q(arr + 16 * k))
                    if en is None:
                        values = None
                        break
                    v = struct.unpack('<q', struct.pack('<Q', x.q(arr + 16 * k + 8)))[0]
                    values[str(v)] = en.rsplit('::', 1)[-1]
                if values:
                    name = nm
                    self.enums.setdefault(nm, values)
                    break
        self._enum_of[func] = name
        return name

    def _class_ref(self, func):
        if func in self._class_of:
            return self._class_of[func]
        x, out = self.x, None
        if func and x.in_text(func):
            t = self._target(func, self.class_params)
            if t is not None:
                out = self.class_key[t]
            else:
                for t in x.leas(func):
                    w = x.wstr(t)
                    if w and IDENT.match(w):
                        out = w
                        break
        self._class_of[func] = out
        return out

    def _prop(self, va):
        x = self.x
        name = x.cstr(x.q(va))
        o = x.offset(va)
        if name is None or o is None:
            raise ValueError('no property parameters at %#x' % va)
        flags, = struct.unpack_from('<Q', x.d, o + 16)
        gen = x.d[o + 24]
        t = TYPES.get(gen & 0x3F)
        if t is None:
            raise ValueError('property %s at %#x has type %#x' % (name, va, gen))
        dim, = struct.unpack_from('<i', x.d, o + 32)
        p = {'n': name, 't': t}
        if dim != 1:
            p['d'] = dim
        if flags:
            p['f'] = flags
        func = x.q(va + 64)
        if t == 'Struct':
            s = self._target(func, self.struct_params)
            p['r'] = self.struct_key[s] if s is not None else None
        elif t in OBJECT_TYPES:
            p['r'] = self._class_ref(func)
        elif t in ('Byte', 'Enum'):
            e = self._enum(func) if func and x.in_text(func) else None
            if e:
                p['r'] = e
        return p

    def props(self, arr, n):
        x = self.x
        ptrs = [x.q(arr + 8 * k) for k in range(n)]
        out = []
        k = n

        def take():
            nonlocal k
            k -= 1
            if k < 0:
                raise ValueError('a container at %#x has no inner property' % arr)
            p = self._prop(ptrs[k])
            if p['t'] in ('Array', 'Set', 'Enum'):
                p['i'] = take()
            elif p['t'] == 'Map':
                p['i'] = take()             # the key ('<Name>_Key'), then the value
                p['v'] = take()
            return p
        while k > 0:
            out.append(take())
        return out[::-1]

    def result(self):
        classes, structs = {}, {}
        for va, c in self.class_params.items():
            sup = None
            if c['ndeps'] >= 1 and c['deps'] and self.x.in_data(c['deps']):
                t = self._target(self.x.q(c['deps']), self.class_params)
                sup = self.class_key[t] if t is not None and t != va else None
            try:
                props = self.props(c['props_va'], c['nprops']) if c['nprops'] else []
            except ValueError:
                continue
            classes[self.class_key[va]] = {'name': c['name'], 'super': sup, 'flags': c['flags'], 'props': props}
        for va, s in self.struct_params.items():
            t = self._target(s['super_func'], self.struct_params)
            try:
                props = self.props(s['props_va'], s['nprops']) if s['nprops'] else []
            except ValueError:
                continue
            structs[self.struct_key[va]] = {'name': s['name'], 'super': self.struct_key[t] if t is not None else None,
                                            'flags': s['flags'], 'size': s['size'], 'serializer': s['serializer'],
                                            'props': props}
        return {'version': SCHEMA_VERSION, 'classes': classes, 'structs': structs, 'enums': self.enums}


def scan(exe):
    """The schemas of a program as a JSON-able dict {'classes', 'structs', 'enums'}."""
    return _Scan(exe).result()


# ---------------------------------------------------------------------------------------------------- schemas
class Prop:
    __slots__ = ('name', 'type', 'dim', 'flags', 'ref', 'inner', 'value')

    def __init__(self, d):
        self.name, self.type = d['n'], d['t']
        self.dim, self.flags, self.ref = d.get('d', 1), d.get('f', 0), d.get('r')
        self.inner = Prop(d['i']) if 'i' in d else None
        self.value = Prop(d['v']) if 'v' in d else None

    def __repr__(self):
        t = self.type
        if self.ref:
            t += '<%s>' % self.ref
        if self.inner is not None:
            t += '[%r%s]' % (self.inner, ', %r' % self.value if self.value is not None else '')
        return '%s:%s%s' % (self.name, t, '*%d' % self.dim if self.dim != 1 else '')


class Schema:
    """Class, struct and enum layouts (from scan(), usually through load())."""

    def __init__(self, data):
        self.classes, self.structs, self.enums = data['classes'], data['structs'], data.get('enums', {})
        self._short = {}
        for key, c in self.classes.items():
            if '@' not in key:
                self._short.setdefault(c['name'], []).append(key)
        self._schemas = {}

    @classmethod
    def load(cls, exe, cache=None):
        """The schemas of `exe`, from the cache when it has them (else scanned and cached)."""
        folder = cache or CACHE
        st = os.stat(exe)
        name = 'schema-v%d-%d-%d.json' % (SCHEMA_VERSION, st.st_size, int(st.st_mtime))
        path = os.path.join(folder, name)
        try:
            with open(path) as f:
                return cls(json.load(f))
        except (OSError, ValueError, KeyError):
            pass
        data = scan(exe)
        try:
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix='.schema.', dir=folder)
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, separators=(',', ':'))
            os.replace(tmp, path)
            for old in os.listdir(folder):              # an older program's schemas
                if old.startswith('schema-') and old.endswith('.json') and old != name:
                    os.unlink(os.path.join(folder, old))
        except OSError:
            pass
        return cls(data)

    def class_key(self, name):
        """A class's key from its path ('/Script/Engine.Texture2D') or name ('Texture2D'), or None."""
        if name in self.classes:
            return name
        keys = self._short.get(name.rsplit('.', 1)[-1] if name.startswith('/Script/') else name, [])
        return keys[0] if len(keys) == 1 else None

    def class_super(self, name):
        key = self.class_key(name)
        return self.classes[key]['super'] if key else None

    def struct_super(self, name):
        s = self.structs.get(name)
        return s['super'] if s else None

    def struct_flags(self, name):
        s = self.structs.get(name)
        return s['flags'] if s else 0

    def struct_serializer(self, name):
        """Whether a struct is serialised by its own code (True), as properties (False), or not known (None)."""
        s = self.structs.get(name)
        return s.get('serializer') if s else None

    def properties(self, name, struct=False):
        """A class's or struct's own properties (Prop) in their order."""
        table = self.structs if struct else self.classes
        key = name if struct else self.class_key(name)
        if key not in table:
            raise KeyError(name)
        return [Prop(p) for p in table[key]['props']]

    def schema(self, name, struct=False):
        """[(Prop, element index)] in unversioned order: own properties first, then the super's, ..."""
        k = (name, struct)
        if k not in self._schemas:
            out, cur, seen = [], name if struct else self.class_key(name), set()
            if cur is None or cur not in (self.structs if struct else self.classes):
                raise KeyError(name)
            while cur and cur not in seen:
                seen.add(cur)
                for p in self.properties(cur, struct):
                    for i in range(max(1, p.dim)):
                        out.append((p, i))
                cur = (self.structs if struct else self.classes).get(cur, {}).get('super')
            self._schemas[k] = out
        return self._schemas[k]

    def enum_name(self, enum, value):
        """The enumerator name of a value ('TC_Normalmap'), or None."""
        e = self.enums.get(enum)
        return e.get(str(value)) if e else None
