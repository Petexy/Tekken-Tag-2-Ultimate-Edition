"""Unversioned properties (Tekken 8's cooked Unreal Engine 5 packages), with the layouts from the program
(reflect.Schema).

An export's data starts with its properties, then (UObject) a u32 GUID flag [+ FGuid] and the class's own data.
Properties are stored by their index in the class's schema (reflect.Schema.schema: own properties first, then the
super's), a struct's the same way within it:
    FUnversionedHeader: u16 fragments {bits 0-6 properties to skip, bit 7 some of these values are zero, bit 8
        last fragment, bits 9-15 values that follow}; then, when any fragment has zeros, one bit per value of those
        fragments (u8 for up to 8 values, u16 for up to 16, else u32 words; bit set: the value is zero and not
        stored); then the stored values in order
    values: Bool, Byte, an enum: u8 (an enum property: its underlying integer); Int8..UInt64, Float, Double as
        they are; Name: u32 name map index + u32 number; Str: FString; Text: FText (u32 flags, i8 history: -1 none
        {u32 has culture-invariant string, [FString]}, 0 base {FString namespace, key, source}, 11 string table
        {FName table, FString key}); Object, Class, Interface, WeakObject: FPackageIndex (i32); LazyObject: FGuid;
        SoftObject, SoftClass: FName package, FName asset, FString sub-path; Array: i32 n + n values; Set, Map: i32
        removed (0) + i32 n + n values (a map's: key, value); Delegate: FPackageIndex + FName; FieldPath: TArray of
        FName + FPackageIndex; Struct: a struct with a serialiser of its own (vectors, colours, soft object paths,
        per-platform values, curve keys, ...: NATIVE below) as that writes it, an immutable struct (StructFlags 0x20)
        as its properties' values in schema order with no header, any other as its own unversioned properties
Python values: numbers; bool; str for names and strings; object references as object paths ('/Game/X/Y.Y',
'/Script/Engine.Texture2D', None for null; '?<hex>' parts where the store does not know a name); soft paths as
'/Game/X/Y.Y[:sub]' (None when empty); structs as dicts by property name (vectors {'X', 'Y', 'Z'}, colours
{'R', 'G', 'B', 'A'}); arrays as lists (an array of plain bytes as bytes); sets as lists; maps as dicts (a list of
(key, value) pairs when a key is a dict); texts as dicts; enum values as Enum (an int that knows its enumerator's
name). A zero-masked value comes out as its type's zero (0, False, '', None, [], a struct of zeros). A property
the data leaves out keeps the class's default, which is not stored here, so it is missing from the dict.

Written for this project from the files themselves (no third-party code).
"""
import struct

from . import reflect

STRUCT_IMMUTABLE = reflect.STRUCT_IMMUTABLE
NUMBERS = {'Int8': 'b', 'Int16': 'h', 'Int': 'i', 'Int64': 'q', 'UInt16': 'H', 'UInt32': 'I', 'UInt64': 'Q',
           'Float': 'f', 'Double': 'd', 'LargeWorldCoordinatesReal': 'd'}
REFERENCES = ('Object', 'Class', 'Interface', 'WeakObject')
TEXT_NONE, TEXT_BASE, TEXT_STRING_TABLE = -1, 0, 11
MAX_COUNT = 1 << 26                        # an array or map count beyond this is a decoding error


class Enum(int):
    """An enum value: compares as its number; .name is its enumerator ('TC_Normalmap') or None."""

    def __new__(cls, value, name=None):
        v = int.__new__(cls, value)
        v.name = name
        return v

    def __repr__(self):
        return '%s(%d)' % (self.name, int(self)) if self.name else int.__repr__(self)


class Reader:
    def __init__(self, pkg, schema, start, end):
        self.pkg, self.s = pkg, schema
        self.b, self.p, self.end = pkg.data, start, end

    # ------------------------------------------------------------------------------------------- primitives
    def take(self, fmt, size):
        if self.p + size > self.end:
            raise ValueError('read of %d bytes at %#x past the end %#x' % (size, self.p, self.end))
        v = struct.unpack_from(fmt, self.b, self.p)
        self.p += size
        return v

    def one(self, fmt, size):
        return self.take('<' + fmt, size)[0]

    def i32(self):
        return self.one('i', 4)

    def fname(self):
        i, n = self.take('<II', 8)
        return self.pkg.mapped_name(i, n)

    def fstring(self):
        n = self.i32()
        if n == 0:
            return ''
        if n < 0:
            raw = self.take('<%ds' % (-2 * n), -2 * n)[0]
            return raw.decode('utf-16-le').rstrip('\0')
        return self.take('<%ds' % n, n)[0].decode('utf-8', 'replace').rstrip('\0')

    def reference(self):
        return self.pkg.reference(self.i32())

    def soft_path(self):
        package, asset, sub = self.fname(), self.fname(), self.fstring()
        if package == 'None':
            return None
        path = package + ('.' + asset if asset != 'None' else '')
        return path + (':' + sub if sub else '')

    def count(self):
        n = self.i32()
        if not 0 <= n < MAX_COUNT:
            raise ValueError('bad count %d at %#x' % (n, self.p - 4))
        return n

    # ------------------------------------------------------------------------------------------- values
    def value(self, p):
        t = p.type
        fmt = NUMBERS.get(t)
        if fmt:
            return self.one(fmt, struct.calcsize(fmt))
        if t == 'Bool':
            return bool(self.one('B', 1))
        if t == 'Byte':
            v = self.one('B', 1)
            return Enum(v, self.s.enum_name(p.ref, v)) if p.ref else v
        if t == 'Enum':
            v = self.value(p.inner)
            return Enum(v, self.s.enum_name(p.ref, v)) if p.ref else v
        if t == 'Name':
            return self.fname()
        if t == 'Str':
            return self.fstring()
        if t in REFERENCES:
            return self.reference()
        if t in ('SoftObject', 'SoftClass'):
            return self.soft_path()
        if t == 'LazyObject':
            return '%08x%08x%08x%08x' % self.take('<4I', 16)
        if t == 'Struct':
            return self.struct(p.ref)
        if t == 'Array':
            return self.array(p.inner, self.count())
        if t == 'Set':
            if self.i32() != 0:
                raise ValueError('a set with removed elements')
            return self.array(p.inner, self.count())
        if t == 'Map':
            if self.i32() != 0:
                raise ValueError('a map with removed keys')
            items = [(self.value(p.inner), self.value(p.value)) for _ in range(self.count())]
            try:
                return dict(items)
            except TypeError:
                return items
        if t == 'Text':
            return self.text()
        if t == 'Delegate':
            return {'object': self.reference(), 'function': self.fname()}
        if t in ('InlineMulticastDelegate', 'SparseMulticastDelegate'):
            return [{'object': self.reference(), 'function': self.fname()} for _ in range(self.count())]
        if t == 'FieldPath':
            path = [self.fname() for _ in range(self.count())]
            return {'path': path, 'owner': self.reference()}
        raise NotImplementedError('property type %s (%s)' % (t, p.name))

    def array(self, inner, n):
        fmt = NUMBERS.get(inner.type)
        if fmt:
            size = struct.calcsize(fmt)
            return list(self.take('<%d%s' % (n, fmt), size * n))
        if inner.type == 'Byte' and not inner.ref:
            return self.take('<%ds' % n, n)[0]
        return [self.value(inner) for _ in range(n)]

    def text(self):
        flags = self.one('I', 4)
        history = self.one('b', 1)
        if history == TEXT_NONE:
            return {'flags': flags, 'invariant': self.fstring()} if self.one('I', 4) else None
        if history == TEXT_BASE:
            return {'flags': flags, 'namespace': self.fstring(), 'key': self.fstring(), 'source': self.fstring()}
        if history == TEXT_STRING_TABLE:
            return {'flags': flags, 'table': self.fname(), 'key': self.fstring()}
        raise NotImplementedError('FText history type %d' % history)

    def struct(self, name):
        fn = NATIVE.get(name.split('@', 1)[0] if name else name)
        if fn is not None:
            return fn(self)
        if name is None or name not in self.s.structs:
            raise NotImplementedError('struct %s has no layout' % name)
        if self.s.struct_serializer(name) and name not in AS_PROPERTIES:
            raise NotImplementedError('struct %s is serialised by its own code (not read yet)' % name)
        if self.s.struct_flags(name) & STRUCT_IMMUTABLE:
            return {_key(p, i): self.value(p) for p, i in self.s.schema(name, True)}
        return self.properties(self.s.schema(name, True), name)

    # ------------------------------------------------------------------------------------------- unversioned
    def properties(self, schema, what):
        frags = []
        while True:
            v = self.one('H', 2)
            frags.append((v & 0x7F, bool(v & 0x80), v >> 9))
            if v & 0x100:
                break
        zeros = sum(n for _, z, n in frags if z)
        mask = 0
        if zeros:
            if zeros <= 8:
                mask = self.one('B', 1)
            elif zeros <= 16:
                mask = self.one('H', 2)
            else:
                for k in range((zeros + 31) // 32):
                    mask |= self.one('I', 4) << (32 * k)
        out, at, bit = {}, 0, 0
        for skip, has_zeros, n in frags:
            at += skip
            for _ in range(n):
                if at >= len(schema):
                    raise ValueError('%s: property %d beyond its %d properties' % (what, at, len(schema)))
                p, i = schema[at]
                zero = False
                if has_zeros:
                    zero = bool((mask >> bit) & 1)
                    bit += 1
                out[_key(p, i)] = self.zero(p) if zero else self.value(p)
                at += 1
        return out

    def zero(self, p, depth=0):
        """The value a zero-masked property has."""
        t = p.type
        if t in NUMBERS:
            return 0.0 if t in ('Float', 'Double', 'LargeWorldCoordinatesReal') else 0
        if t == 'Bool':
            return False
        if t in ('Byte', 'Enum'):
            return Enum(0, self.s.enum_name(p.ref, 0)) if p.ref else 0
        if t in ('Name', 'Str'):
            return 'None' if t == 'Name' else ''
        if t in ('Array', 'Set', 'InlineMulticastDelegate', 'SparseMulticastDelegate'):
            return []
        if t == 'Map':
            return {}
        if t == 'Struct' and depth < 8:
            z = NATIVE_ZERO.get(p.ref)
            if z is not None:
                return dict(z) if isinstance(z, dict) else z
            if p.ref in self.s.structs:
                return {_key(q, i): self.zero(q, depth + 1) for q, i in self.s.schema(p.ref, True)}
        return None


def _key(p, i):
    return p.name if p.dim == 1 else '%s[%d]' % (p.name, i)


# ---------------------------------------------------------------------------------------------------- native structs
def _fields(fmt, names):
    size = struct.calcsize(fmt)

    def read(r):
        return dict(zip(names, r.take(fmt, size)))
    return read


def _box(n, axes):
    size = struct.calcsize('<%ddB' % (2 * n))

    def read(r):
        v = r.take('<%ddB' % (2 * n), size)
        return {'Min': dict(zip(axes, v[:n])), 'Max': dict(zip(axes, v[n:2 * n])), 'IsValid': v[-1]}
    return read


def _per_platform(value):
    """FPerPlatform<T>: u32 bCooked, T Default, [not cooked: TMap<FName, T> (i32 n + pairs)]."""
    def read(r):
        cooked = r.one('I', 4)
        out = {'Default': value(r)}
        if not cooked:
            out['PerPlatform'] = {r.fname(): value(r) for _ in range(r.count())}
        return out
    return read


def _per_quality(value):
    """FPerQualityLevel<T>: u32 bCooked, T Default, TMap<int32, T> (i32 n + pairs)."""
    def read(r):
        r.one('I', 4)
        default = value(r)
        return {'Default': default, 'PerQuality': {r.i32(): value(r) for _ in range(r.count())}}
    return read


def _float(r):
    return r.one('f', 4)


def _int(r):
    return r.i32()


def _frame_rate(r):
    return dict(zip(('Numerator', 'Denominator'), r.take('<2i', 8)))


_FLOAT = reflect.Prop({'n': 'Float', 't': 'Float'})
_INT = reflect.Prop({'n': 'Int', 't': 'Int'})


def _weighted_sampler(r):
    """FWeightedRandomSampler (a skeletal mesh's area-weighted triangle sampler): TArray<float> Prob,
    TArray<int32> Alias, float TotalWeight."""
    prob = r.array(_FLOAT, r.count())
    alias = r.array(_INT, r.count())
    return {'Prob': prob, 'Alias': alias, 'TotalWeight': r.one('f', 4)}


def _rich_curve_key(r):
    v = r.take('<3B6f', 27)
    return dict(zip(('InterpMode', 'TangentMode', 'TangentWeightMode', 'Time', 'Value', 'ArriveTangent',
                     'ArriveTangentWeight', 'LeaveTangent', 'LeaveTangentWeight'), v))


XYZ, XYZW, RGBA, BGRA = ('X', 'Y', 'Z'), ('X', 'Y', 'Z', 'W'), ('R', 'G', 'B', 'A'), ('B', 'G', 'R', 'A')
NATIVE = {   # structs with a serialiser of their own (TStructOpsTypeTraits WithSerializer) or a fixed binary layout
    'Vector': _fields('<3d', XYZ), 'Vector3d': _fields('<3d', XYZ), 'Vector3f': _fields('<3f', XYZ),
    'Vector2D': _fields('<2d', XYZ[:2]), 'Vector2f': _fields('<2f', XYZ[:2]),
    'Vector4': _fields('<4d', XYZW), 'Vector4d': _fields('<4d', XYZW), 'Vector4f': _fields('<4f', XYZW),
    'Plane': _fields('<4d', XYZW), 'Plane4f': _fields('<4f', XYZW), 'Quat': _fields('<4d', XYZW),
    'Quat4f': _fields('<4f', XYZW), 'Rotator': _fields('<3d', ('Pitch', 'Yaw', 'Roll')),
    'Rotator3f': _fields('<3f', ('Pitch', 'Yaw', 'Roll')),
    'IntPoint': _fields('<2i', XYZ[:2]), 'IntVector': _fields('<3i', XYZ), 'IntVector4': _fields('<4i', XYZW),
    'UintVector2': _fields('<2I', XYZ[:2]),
    'Box': _box(3, XYZ), 'Box3f': _box(3, XYZ), 'Box2D': _box(2, XYZ[:2]),
    'Sphere': lambda r: dict(zip(('Center', 'W'), (dict(zip(XYZ, r.take('<3d', 24))), r.one('d', 8)))),
    'Matrix': lambda r: {'M': list(r.take('<16d', 128))},
    'LinearColor': _fields('<4f', RGBA), 'Color': _fields('<4B', BGRA),
    'Guid': _fields('<4I', ('A', 'B', 'C', 'D')),
    'DateTime': _fields('<q', ('Ticks',)), 'Timespan': _fields('<q', ('Ticks',)),
    'FrameNumber': _fields('<i', ('Value',)),
    'SoftObjectPath': lambda r: r.soft_path(), 'SoftClassPath': lambda r: r.soft_path(),
    'TopLevelAssetPath': lambda r: (lambda pk, an: None if pk == 'None' else pk + ('.' + an if an != 'None' else ''))(
        r.fname(), r.fname()),
    'PerPlatformFloat': _per_platform(_float), 'PerPlatformInt': _per_platform(_int),
    'PerPlatformBool': _per_platform(lambda r: bool(r.one('I', 4))), 'PerPlatformFrameRate': _per_platform(_frame_rate),
    'PerQualityLevelInt': _per_quality(_int), 'PerQualityLevelFloat': _per_quality(_float),
    'RichCurveKey': _rich_curve_key, 'SimpleCurveKey': _fields('<2f', ('Time', 'Value')),
    'SkeletalMeshSamplingLODBuiltData': lambda r: {'AreaWeightedTriangleSampler': _weighted_sampler(r)},
}
AS_PROPERTIES = {   # structs whose serialiser only notes a version and leaves the rest to the properties
    'ConstraintInstance',
}
NATIVE_ZERO = {'Vector': dict.fromkeys(XYZ, 0.0), 'Vector3f': dict.fromkeys(XYZ, 0.0),
               'Vector2D': dict.fromkeys(XYZ[:2], 0.0), 'Vector4': dict.fromkeys(XYZW, 0.0),
               'Quat': dict.fromkeys(XYZW, 0.0), 'Rotator': dict.fromkeys(('Pitch', 'Yaw', 'Roll'), 0.0),
               'LinearColor': dict.fromkeys(RGBA, 0.0), 'Color': dict.fromkeys(BGRA, 0),
               'Guid': dict.fromkeys('ABCD', 0), 'IntPoint': dict.fromkeys(XYZ[:2], 0),
               'SoftObjectPath': '', 'SoftClassPath': '', 'TopLevelAssetPath': ''}


# ---------------------------------------------------------------------------------------------------- API
def read(pkg, export, schema=None, class_name=None):
    """An export's properties -> (dict, offset in the export where they end: the u32 GUID flag and the class's
    own data follow). schema: reflect.Schema (default: the package's store's); class_name: the class whose
    layout to use (default: the export's class)."""
    if schema is None:
        if pkg.store is None:
            raise ValueError('%s: no schema (pass one or open the package through a store)' % pkg.name)
        schema = pkg.store.schema
    cls = class_name or export.class_path
    try:
        layout = schema.schema(cls)
    except KeyError:
        raise KeyError('%s: no layout for class %s (only the program\'s own classes have one)' % (export.path, cls))
    end = export.offset + export.size
    if end > len(pkg.data):
        raise ValueError('%s: export %s lies past the data read' % (pkg.name, export.name))
    r = Reader(pkg, schema, export.offset, end)
    props = r.properties(layout, cls)
    return props, r.p - export.offset


def read_object(pkg, export, schema=None, class_name=None):
    """An export's properties and the offset of the class's own data in it (after the u32 GUID flag and its FGuid,
    as tekken7.uasset.read_object returns)."""
    props, end = read(pkg, export, schema, class_name)
    if end + 4 > export.size:
        raise ValueError('%s: no object GUID flag after the properties' % export.path)
    flag, = struct.unpack_from('<I', pkg.data, export.offset + end)
    if flag not in (0, 1):
        raise ValueError('%s: bad object GUID flag %d after the properties' % (export.path, flag))
    return props, end + 4 + 16 * flag


def read_struct(pkg, schema, struct_name, start, end=None):
    """A struct's value at pkg.data[start:] (e.g. one a class serialises after its properties) -> (value, end)."""
    r = Reader(pkg, schema, start, len(pkg.data) if end is None else end)
    v = r.struct(struct_name)
    return v, r.p
