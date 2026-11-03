"""Costume-only packs for native fighters. No roster, moveset or save replacement."""
import json
import os
from pathlib import Path
import tempfile
import time
import uuid
from types import SimpleNamespace

from . import InputError, pack, signals

from .native_profiles import profile, presets, page_size, body_code, texture_ids

# Compatibility for the existing Paul API and packs.
PRESETS = presets()
PAGE_SIZE = page_size()
MAX_SELECTED = len(PRESETS)
TEXTURE_BASE = 0x10e00000
PREVIEW_BASE = 0x10e10000

def selection(names, fighter='pau'):
    names = list(dict.fromkeys(names))
    ordered = profile(fighter)['presets']
    if not names or set(names) - set(ordered):
        raise InputError('Choose one or more listed presets for ' + profile(fighter)['name'] + '.')
    return [name for name in ordered if name in names]

def installed(folder, fighter='pau'):
    target = Path(folder) / 'native' / profile(fighter)['code']
    try:
        data = json.loads((target / 'presets.json').read_text(encoding='utf-8'))
        return selection(data['presets'], fighter) if (target / 'native.ini').is_file() else []
    except (OSError, ValueError, KeyError, InputError):
        return []


def rename(source, target):
    """Allow a short Windows scanner/sync lock to release, without hiding other errors."""
    for attempt in range(21):
        try:
            return source.rename(target)
        except OSError as error:
            if getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == 20:
                raise
            time.sleep(.1)


def publish(temporary, target):
    """Atomic directory switch with a retained backup and rollback on failure."""
    temporary, target = Path(temporary), Path(target)
    if temporary.resolve().parent != target.resolve().parent or temporary.is_symlink() or target.is_symlink():
        raise InputError('Native costume folders must be ordinary sibling directories.')
    if target.exists() and not (target / 'native.ini').is_file():
        raise InputError('Refusing to replace an unrecognised native costume directory: ' + str(target))
    backup = target.with_name('.' + target.name + '-backup-' + uuid.uuid4().hex)
    with signals.deferred():
        if target.exists():
            rename(target, backup)
        try:
            rename(temporary, target)
        except BaseException:
            if backup.exists():
                rename(backup, target)
            raise
    return target


def remove(folder, fighter='pau'):
    target = Path(folder) / 'native' / profile(fighter)['code']
    if not target.exists():
        return
    if target.is_symlink() or not (target / 'native.ini').is_file():
        raise InputError('Refusing to remove an unrecognised native costume directory.')
    rename(target, target.with_name('.' + target.name + '-backup-' + uuid.uuid4().hex))


def build(game, tekken7, folder, names, log=print, cached=None, fighter='pau'):
    from . import importer
    from .characters import claudio
    from .convert import art, chains, effects, face, itemdb, model, outfits, tiger
    from .source import Tekken7Source
    from .tekken7.pak import Paks
    from .ttt2 import bone, nud, nut
    from .ttt2.archive import key_of
    p = profile(fighter)
    code_name = p['code']
    original_count = p['originals']
    size_per_page = page_size(fighter)
    choices = presets(fighter)
    names = selection(names, fighter)
    folder = Path(pack.output_folder(str(folder)))
    target = folder / 'native' / code_name
    target.parent.mkdir(parents=True, exist_ok=True)
    paks = Paks(importer.tekken7_paks(str(tekken7)))
    archives = importer._archives(importer.ttt2_folder(str(game)))
    temporary = None
    try:
        source = Tekken7Source(paks)
        rpx = importer._rpx(importer.ttt2_folder(str(game)))
        native_count = rpx.u32(0x103B4B88 + 8 * p['id'])
        target_code = rpx.read(rpx.u32(0x107c57f4 + 4 * p['id']), 8).split(b'\0')[0].decode()
        if native_count != original_count or target_code != code_name or size_per_page < 1:
            raise InputError('The native costume table does not match the supported EU v16 ' + p['name'] + ' profile.')
        preview_key = rpx.u32(0x10161590 + 4 * p['id'])
        previews = nut.read(archives.read(preview_key))['textures']
        if len(previews) < native_count:
            raise InputError('Native costume previews are incomplete.')
        previews = previews[:native_count]
        donor_bon = archives.read_name(code_name + '.bon')
        donor_xml = archives.read_name(code_name + '.xml')
        xml = itemdb.body_only(donor_xml)
        effect_files, _, _ = effects.copy_files(archives, code_name, itemdb.effect_names(donor_xml), {}, log=log)
        base = SimpleNamespace(CODE=code_name, DONOR=code_name, NAME=p['name'], SEX=p['sex'], TEKKEN7_CODE=p['source'],
                               TEKKEN7={'costume': '', 'parts': [], 'merge_order': ['fac', 'bdl', 'bdu', 'har', 'fah']},
                               MESHES={}, MATERIALS={}, NATIVE_BUDGET=True, TEMPLATES=claudio.TEMPLATES,
                               TEMPLATE_TEXTURES=claudio.TEMPLATE_TEXTURES)
        files = {}
        preview_fallbacks = []
        labels = dict(choices)
        for index, preset in enumerate(names):
            log('@step fighter %s - preset %d of %d' % (p['name'], index + 1, len(names)))
            log(p['name'] + ' preset: ' + labels[preset])
            source_code = p['source'].upper()
            costume = '/Game/Character/Item/Sets/%s/CS_%s_%s' % (source_code, source_code, preset)
            definition = outfits.definition(paks, base, costume)
            cache = folder / '.native-costume-cache' / 'v2' / code_name / preset
            path = Path(cached) / ('CS_PAU_' + preset) if cached and fighter == 'pau' else cache
            using_cache = all((path / (code_name + ext)).is_file() for ext in ('.nud', '.nut', '.bon', '.mop'))
            if using_cache:
                mesh, textures, skeleton = [(path / (code_name + ext)).read_bytes() for ext in ('.nud', '.nut', '.bon')]
                spring_path = path / (code_name + '.mop')
                mop = spring_path.read_bytes() if spring_path.is_file() else importer.spring_file(archives, definition, skeleton, None)
                using_cache = sum(len(poly['verts']) for part in nud.read(mesh)['meshes'] for poly in part['polys']) <= model.VERTEX_BUDGET
            if not using_cache:
                mesh, textures, skeleton, _, springs = model.convert(source, archives, definition, 128 + index, log=log)
                mop = importer.spring_file(archives, definition, skeleton, springs)
            if mop is None:
                mop = archives.read_name(code_name + '.mop') if archives.has(key_of(code_name + '.mop')) else chains.empty_spring_file(
                    archives.read_name(tiger.SPRING_TEMPLATE[0] + '.mop'))
            if sum(len(poly['verts']) for part in nud.read(mesh)['meshes'] for poly in part['polys']) > model.VERTEX_BUDGET:
                raise InputError('Native preset still exceeds the safe skinned-vertex budget after reduction: ' + preset)
            if mop is not None and (not using_cache or not all((cache / (code_name + ext)).is_file() for ext in ('.nud', '.nut', '.bon', '.mop'))):
                cache.mkdir(parents=True, exist_ok=True)
                for ext, data in zip(('.nud', '.nut', '.bon', '.mop'), (mesh, textures, skeleton, mop)):
                    (cache / (code_name + ext)).write_bytes(data)
            skeleton = face.same_joints(skeleton, donor_bon)
            if bone.read(skeleton)['names'][:len(bone.read(donor_bon)['names'])] != bone.read(donor_bon)['names']:
                raise InputError('Native skeleton layout changed during conversion.')
            body_texture, preview_texture = texture_ids(preset, fighter)
            if len(nut.read(textures)['textures']) > (0x1000 if fighter == 'pau' else 0x400):
                raise InputError('Costume exceeds its reserved texture namespace.')
            mesh, textures = outfits.relocate(mesh, textures, body_texture)
            # Read back the output before the old pack can be replaced.
            nud.read(mesh)
            nut.read(textures)
            code = body_code(preset, fighter)
            files.update({code + '.nud': mesh, code + '.nut': textures, code + '.bon': skeleton, code + '.xml': xml})
            if mop is None:
                mop = archives.read_name(code_name + '.mop') if archives.has(key_of(code_name + '.mop')) else chains.empty_spring_file(
                    archives.read_name(tiger.SPRING_TEMPLATE[0] + '.mop'))
            files[code + '.mop'] = mop
            if archives.has(key_of(code_name + '.havok.xml')):
                files[code + '.havok.xml'] = archives.read_name(code_name + '.havok.xml')
            for name, data in effect_files.items():
                files[code + '/' + name] = data
            suffix = {'DefaultCos1P': '01', 'DefaultCos2P': '02'}.get(preset, preset.upper())
            definition.ART = {'costume': '/Game/UI_common/Texture2D/ReplaceImages/CS_CH_SLOT/CS_CH_SLOT_' + source_code + '_' + suffix}
            # Two source sets have no supplied thumbnail. Use an explicitly labelled
            # placeholder so their convertible models remain available without a false preview.
            picture_cache = cache / 'preview.nut'
            if picture_cache.is_file():
                preview = picture_cache.read_bytes()
            elif paks.find(definition.ART['costume']):
                preview = art.costume_previews(source, archives, rpx, definition, 128 + index)
                if preview:
                    cache.mkdir(parents=True, exist_ok=True)
                    picture_cache.write_bytes(preview)
            else:
                preview = None
            if preview:
                texture = nut.read(preview)['textures'][0]
            else:
                from PIL import Image, ImageDraw, ImageFont
                import textwrap
                like = previews[0]
                image = Image.new('RGBA', (like['w'], like['h']), (22, 28, 38, 255))
                draw = ImageDraw.Draw(image)
                font = ImageFont.load_default(size=max(10, image.width // 12))
                caption = 'TEKKEN 7\n\n' + labels[preset] + '\n\nNo source preview'
                lines = '\n'.join('\n'.join(textwrap.wrap(line, max(10, image.width // 8))) for line in caption.split('\n'))
                draw.multiline_text((8, 25), lines, font=font, fill='white', spacing=5)
                texture = nut.make_texture(image, preview_texture, fmt=2, mips=1)
                preview_fallbacks.append(preset)
                log('No source thumbnail for ' + preset + '; using a labelled placeholder.')
            texture['gidx'] = preview_texture
            texture.pop('ext', None)
            # A visible source/page badge also explains paging inside the chooser.
            if len(names) > size_per_page:
                from PIL import Image, ImageDraw, ImageFont
                image = Image.fromarray(nut.decode(texture))
                draw = ImageDraw.Draw(image)
                size = max(10, image.width // 22)
                font = ImageFont.load_default(size=size)
                caption = 'T7  %d/%d  UP / DOWN' % (index // size_per_page + 1, (len(names) + size_per_page - 1) // size_per_page)
                height = size + 10
                draw.rectangle((0, image.height - height, image.width, image.height), fill=(12, 16, 24, 245))
                draw.text((5, image.height - height + 4), caption, font=font, fill=(255, 255, 255, 255))
                texture = nut.make_texture(image, texture['gidx'], fmt=2, mips=1)
            previews.append(texture)
        files['art/costumes.nut'] = nut.write(previews)
        codes = [body_code(name, fighter) for name in names]
        files['native.ini'] = ('format = 1\ntarget = ' + code_name + '\noutfits = ' + ','.join(codes) + '\n').encode()
        files['presets.json'] = (json.dumps({'format': 1, 'source': 'tekken7', 'presets': names, 'preview_fallbacks': preview_fallbacks}, indent=2) + '\n').encode()
        temporary = Path(tempfile.mkdtemp(prefix='.' + code_name + '-import-', dir=target.parent))
        for name, data in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        destination = publish(temporary, target)
        log(p['name'] + ' presets installed: ' + str(destination))
        log('@done')
        return destination
    finally:
        archives.close()
        paks.close()
        if temporary is not None and temporary.exists():
            # A failed unpublished import is retained for diagnosis, never loaded.
            log('Unpublished temporary assets retained: ' + str(temporary))
