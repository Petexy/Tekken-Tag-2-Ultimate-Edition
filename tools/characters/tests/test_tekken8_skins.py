"""Tekken 8 body looks (0x83ca) as bursts at body parts (moveset.Converter.skin8_rows): made-up data."""
import collections
import types

from ttt2char.convert import moveset


class _Sampler:
    def __init__(self, spec, clip=True):
        self.spec = spec
        self.calls = []
        self.trails = types.SimpleNamespace(clip=lambda move: [0.0] * 40 if clip else None)

    def body(self, values, first, eid, look):
        self.calls.append((first, eid, look))
        return dict(burst=tuple(look), id=eid, part=99, key=('disk', eid, 99))


def _converter(spec, clip=True):
    c = types.SimpleNamespace(disk_sampler=_Sampler(spec, clip), effect_conditions={}, stats=collections.Counter(),
                              trail_rows=[], effect_ids=set())
    c.skin8_rows = types.MethodType(moveset.Converter.skin8_rows, c)
    c.assign_trails = types.MethodType(moveset.Converter.assign_trails, c)
    return c


SPEC = {'looks': {}, 'skins': {0: dict(look='hand', parts=(3, 5, 9))}}


def test_a_named_body_look_puts_its_burst_on_every_part_for_the_rows_frames():
    c = _converter(SPEC)
    rows = []
    c.skin8_rows(rows, 0x8001, 1 << 24 | 0 << 16 | 60 << 8, None, 7)
    assert [r['part'] for r in rows] == [3, 5, 9]
    assert all(r['frame'] == 0x8001 and r['id'] == moveset.EFFECT_PROP for r in rows)
    assert c.disk_sampler.calls == [(0, moveset.BODY_LOOK8, ('hand', 60))]
    ids = c.assign_trails(set())
    assert len(ids) == 1                                    # one effect for all the parts
    (i,) = ids
    assert [r['value'] for r in rows] == [3 << 8 | i, 5 << 8 | i, 9 << 8 | i]


def test_moves_with_the_same_frames_share_the_effect_and_other_frames_get_their_own():
    c = _converter(SPEC)
    a, b, d = [], [], []
    c.skin8_rows(a, 0x8001, 1 << 24 | 60 << 8, None, 1)
    c.skin8_rows(b, 0x8001, 1 << 24 | 60 << 8, None, 2)
    c.skin8_rows(d, 0x8001, 1 << 24 | 30 << 8, None, 3)
    assert len(c.assign_trails(set())) == 2
    assert a[0]['value'] == b[0]['value'] != d[0]['value']


def test_a_move_without_a_clip_has_no_rows():
    c = _converter(SPEC, clip=False)
    rows = []
    c.skin8_rows(rows, 0x8001, 1 << 24 | 60 << 8, None, 7)
    assert rows == [] and c.trail_rows == []


def test_a_share_burns_part_of_the_rows_frames():
    c = _converter({'looks': {}, 'skins': {0: dict(look='hand', parts=(3,), share=0.4)}})
    rows = []
    c.skin8_rows(rows, 0x8001, 1 << 24 | 60 << 8, None, 7)
    assert c.disk_sampler.calls == [(0, moveset.BODY_LOOK8, ('hand', 24))]


def test_a_look_with_hidden_cuts_its_moves_hides_short():
    c = _converter({'looks': {}, 'skins': {0: dict(look='hand', parts=(3,), hidden=4)}})
    look = (0x8001, moveset.BODY_LOOK8, 1 << 24 | 40 << 8, None)
    rows = [(6, moveset.HIDE8, 1, None), (30, moveset.HIDE8, 0, None), look, (0, 0, 0, None)]
    c.skin8_hidden = types.MethodType(moveset.Converter.skin8_hidden, c)
    assert c.skin8_hidden(rows) == [(6, moveset.HIDE8, 1, None), (10, moveset.HIDE8, 0, None), look, (0, 0, 0, None)]
    from_start = [(0x8001, moveset.HIDE8, 1, None), (12, moveset.HIDE8, 0, None), look]
    assert c.skin8_hidden(from_start)[1] == (5, moveset.HIDE8, 0, None)


def test_hides_stay_without_hidden_or_without_the_look():
    rows = [(6, moveset.HIDE8, 1, None), (30, moveset.HIDE8, 0, None), (0x8001, moveset.BODY_LOOK8, 1 << 24 | 40 << 8, None)]
    c = _converter(SPEC)
    c.skin8_hidden = types.MethodType(moveset.Converter.skin8_hidden, c)
    assert c.skin8_hidden(rows) == rows
    c = _converter({'looks': {}, 'skins': {0: dict(look='hand', parts=(3,), hidden=4)}})
    c.skin8_hidden = types.MethodType(moveset.Converter.skin8_hidden, c)
    assert c.skin8_hidden(rows[:2]) == rows[:2]


def test_burn_caps_the_frames_and_with_hide_leaves_out_a_move_that_does_not_hide_him():
    c = _converter({'looks': {}, 'skins': {0: dict(look='hand', parts=(3,), burn=9, with_hide=True)}})
    rows = []
    c.skin8_rows(rows, 0x8001, 1 << 24 | 60 << 8, None, 7, hides=True)
    assert c.disk_sampler.calls == [(0, moveset.BODY_LOOK8, ('hand', 9))]
    later = []
    c.skin8_rows(later, 0x8001, 1 << 24 | 30 << 8, None, 8, hides=False)
    assert later == [] and len(c.disk_sampler.calls) == 1


class _Moves:
    """A made-up Tekken 8 moveset: moves [(extra property rows, cancels [(target, win_start, start_frame)])]."""

    def __init__(self, moves):
        self.tables = {'moves': [dict(extraprops=i, cancel=i if cancels else None) for i, (_, cancels) in enumerate(moves)]}
        self.rows = [rows for rows, _ in moves]
        self.cancels = [[dict(direction=0, move_id=t, win_start=w, win_end=w + 9, start_frame=s) for t, w, s in cancels]
                        + [dict(direction=moveset.M.LIST_END, move_id=None, win_start=0, win_end=0, start_frame=0)]
                        for _, cancels in moves]

    def iter_list(self, table, start, end_test):
        assert table == 'cancels'
        for n, c in enumerate(self.cancels[start]):
            yield n, c
            if end_test(c):
                return

    def resolve_alias(self, mid):
        return mid - 0x8000


def _carrier(skin, moves):
    c = _converter({'looks': {}, 'skins': {0: skin}})
    c.k = _Moves(moves)
    c.skin8_carry = None
    c.xp_rows = lambda i: c.k.rows[i]
    c.skin8_carried = types.MethodType(moveset.Converter.skin8_carried, c)
    return c


LOOK60 = (0x8001, moveset.BODY_LOOK8, 1 << 24 | 60 << 8, None)
HIDE = (10, moveset.HIDE8, 1, None)


def test_carry_burns_the_moves_out_of_a_look_for_its_frames_left_less_the_fade():
    skin = dict(look='hand', parts=(3, 5), burn=9, with_hide=True, carry=30)
    c = _carrier(skin, [([LOOK60, HIDE], [(1, 1, 15), (2, 1, 15), (3, 20, 20), (0x8004, 1, 1)]),   # 0: the shift
                        ([], []),                                                       # 1: a move out of it
                        ([(0x8001, moveset.BODY_LOOK8, 1 << 24 | 30 << 8, None)], []),  # 2: has its own look
                        ([], []),                                                       # 3: out of it later
                        ([], [])])                                                      # 4: his stance (an alias)
    assert c.skin8_carried(1) == [(0, 15)]                  # 60 - 15 - 30
    assert c.skin8_carried(2) == []
    assert c.skin8_carried(3) == [(0, 10)]                  # 60 - 20 - 30
    assert c.skin8_carried(4) == []                         # (never through an alias: the stance would burn)
    assert c.skin8_carried(0) == []
    rows = []
    c.skin8_rows(rows, 0x8001, 1 << 24 | 15 << 8, None, 1, carried=15)
    assert [r['part'] for r in rows] == [3, 5]              # (no hide of its own, past burn's 9: carried as it is)
    assert c.disk_sampler.calls == [(0, moveset.BODY_LOOK8, ('hand', 15))]


def test_no_carry_without_the_key_or_out_of_a_move_that_does_not_hide_under_with_hide():
    moves = [([LOOK60], [(1, 1, 15)]), ([], [])]
    assert _carrier(dict(look='hand', parts=(3,), with_hide=True, carry=30), moves).skin8_carried(1) == []
    assert _carrier(dict(look='hand', parts=(3,)), moves).skin8_carried(1) == []
    assert _carrier(dict(look='hand', parts=(3,), carry=30), moves).skin8_carried(1) == [(0, 15)]
    assert _carrier(dict(look='hand', parts=(3,), carry=50), moves).skin8_carried(1) == []    # nothing left
