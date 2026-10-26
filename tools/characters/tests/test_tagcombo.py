"""Unit tests of ttt2char.convert.tagcombo (the tag combos of the converted launchers), on made-up tables (no game
files needed).

    python3 -m pytest -q tools/characters/tests/test_tagcombo.py
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ttt2char.convert import idmaps as M  # noqa: E402
from ttt2char.convert import tagcombo as TC, tagsystem as TS  # noqa: E402
from ttt2char.movesets import TTT2  # noqa: E402

STANCE, CROUCH = 0x8001, 0x8002
EX = {'plain': 0, 'action': 1, 'own': 2, 'made': 3, 'keep': 4}       # extradata rows (values below)
VALUES = {'plain': 0x80, 'action': TC.ACTION_ONLY, 'own': 0x4bc, 'made': 0xbc, 'keep': 0x401}


class Tables:
    """Made-up TTT2 tables, built list by list."""

    def __init__(self):
        self.t = {name: [] for name in TTT2}
        self.t['cancel_extras'] = [dict(value=VALUES[k]) for k in sorted(EX, key=EX.get)]
        self.names = []
        self.aliases = [0] * 56

    def req(self, *conditions):
        return TS.write(self.t, 'requirements', [dict(condition=c, param=p) for c, p in conditions]
                        + [dict(condition=TS.TT_END, param=0)])

    def cancels(self, *rows):
        base = dict(direction=0, button=0, req=0, extradata=EX['plain'], win_start=1, win_end=32767, start_frame=1,
                    move_id=0, option=0)
        return TS.write(self.t, 'cancels', [dict(base, **r) for r in rows])

    def hits(self, *entries):
        return TS.write(self.t, 'hit_conditions', [dict(req=r, damage=d, reactions=x) for r, d, x in entries])

    def props(self, *rows):
        return TS.write(self.t, 'extra_move_properties', [dict(frame=f, id=i, value=v) for f, i, v in rows]
                        + [dict(frame=0, id=0, value=0)])

    def reaction(self, default):
        row = {f: 0 for f, _, _, _ in TTT2['reactions'][1]}
        row['default'] = default
        return TS.write(self.t, 'reactions', [row])

    def move(self, name, **fields):
        row = {f: 0 for f, _, _, _ in TTT2['moves'][1]}
        row.update(name=len(self.names), cancel=None, hit_condition=None, extraprops=None, voiceclip=None,
                   begin_props=None, end_props=None, hitbox=b'\1\2\3\4', transition=STANCE)
        row.update(fields)
        self.names.append(name)
        return TS.write(self.t, 'moves', [row])

    def end(self, start=48):
        return dict(direction=M.LIST_END, win_start=start, start_frame=start)

    def name_of(self, i):
        return self.names[i]

    def string(self, s):
        self.names.append(s)
        return len(self.names) - 1


def rows(t, i):
    return [dict(r) for r in TS.cancels(t, i)]


class Base(unittest.TestCase):
    def donor(self):
        """A donor with its stance, a 51-frame launch reaction and a 40-frame knockdown, two own-animation tag combos
        (X active 16-17 and 20-21, tag rows to 25 and 29: XChg tags out 5 and 3 frames after, the stance 4 and 6
        after that) and one into a made animation, with a hit version pressing Tag."""
        d = Tables()
        d.move('stance')
        self.launch_move = d.move('sDw_UP_01_', airborne_start=1, airborne_end=52)
        self.down_move = d.move('dw_has', airborne_start=1, airborne_end=41)
        self.r_launch, self.r_down = d.reaction(self.launch_move), d.reaction(self.down_move)
        r = self.r = dict(always=d.req((0, 0)), never=d.req(), tag=d.req((TC.TAG_HIT, 0), (TC.CAN_TAG, 0)),
                          press=d.req((TC.CAN_TAG, 0)), hub=d.req((TC.OFF_POINT, 0)),
                          out=d.req((0x824D, 1), (TC.TAG_OUT, 0xFFF5D816), (0x824E, 0)), hit=d.req((46, 0), (0x8003, 0)),
                          air=d.req((TS.AIR, 0)), bound=d.req((TS.BOUND, 0)))
        self.nohit = d.hits((r['always'], 0, 0), (r['never'], 0, 15))
        for name, fa, we, n, m_, bits in (('Ju_a', 16, 25, 30, 34, 0x20), ('Ju_b', 20, 29, 32, 38, 0x28)):
            x = len(d.t['moves'])
            d.move(name, first_active=fa, last_active=fa + 1, anim=0x4000 + x, hitlevel=0x200217, bitfield=bits,
                   voiceclip=7, hit_condition=d.hits((r['air'], 20, self.r_down), (r['never'], 20, self.r_launch)),
                   cancel=d.cancels(dict(req=r['hit'], extradata=EX['action'], move_id=STANCE),
                                    dict(req=r['tag'], extradata=EX['own'], win_end=we, move_id=x + 1), d.end(60)),
                   extraprops=d.props((0x8001, 0x82ed, 0), (5, 0x82d7, 0x290f), (40, 0x82d9, 0x10f)))
            d.move(name + 'Chg', anim=0x4000 + x, hitlevel=0x200000, bitfield=bits | 0x80000000, hitbox=bytes(4),
                   hit_condition=self.nohit,
                   cancel=d.cancels(dict(req=r['hub'], move_id=TC.HUB),
                                    dict(req=r['out'], extradata=EX['action'], win_start=n, win_end=n, start_frame=n,
                                         move_id=STANCE),
                                    dict(req=r['always'], win_start=m_, win_end=m_, start_frame=m_, move_id=STANCE),
                                    dict(direction=M.LIST_END, req=r['always'], win_start=0, win_end=0,
                                         start_frame=0)),
                   extraprops=d.props((0x8001, 0x82d7, 0x290f), (40, 0x82d9, 0x10f), (0x8001, 0x824d, 1)))
        # a made-animation tag combo (Kazuya's EWGF form) and its hit version (its own animation, a press row)
        x = len(d.t['moves'])
        d.move('Ju_c', first_active=11, last_active=12, anim=0x4100, hit_condition=d.hits((r['never'], 23, self.r_launch)),
               cancel=d.cancels(dict(req=r['tag'], extradata=EX['made'], win_end=20, move_id=x + 1),
                                dict(req=r['hit'], extradata=EX['keep'], move_id=x + 2), d.end(36)))
        d.move('Ju_cChg', anim=0x4101, hit_condition=self.nohit,
               cancel=d.cancels(dict(req=r['hub'], move_id=TC.HUB),
                                dict(req=r['out'], extradata=EX['action'], win_start=5, win_end=5, start_frame=5,
                                     move_id=STANCE), d.end(0)))
        d.move('Ju_c_H', anim=0x4100, hit_condition=self.nohit,
               cancel=d.cancels(dict(button=TS.TAG_BUTTON, req=r['press'], extradata=EX['made'], win_end=20,
                                     move_id=x + 1), d.end(36)))
        return d


class Template(Base):
    def test_learnt_from_own_animation_pairs(self):
        d = self.donor()
        tpl = TC.combo_template(d.t, d.aliases, 8)
        self.assertEqual(tpl['pairs'], 2)                                   # Ju_c's made animation is left out
        self.assertEqual(tpl['row'], (self.r['tag'], EX['own'], 0, 1, 1))
        self.assertEqual(tpl['press'], self.r['press'])
        self.assertEqual((tpl['after'], tpl['gap']), (3, 4))                # low medians of (5, 3) and (4, 6)
        self.assertEqual(tpl['hub'], ((self.r['hub'], EX['plain'], 0, 1, 32767, 1),))
        self.assertEqual(tpl['out'], ((self.r['out'], EX['action'], 0, STANCE),))
        self.assertEqual(tpl['back'], ((self.r['always'], EX['plain'], 0),))
        self.assertEqual(tpl['no hit'], self.nohit)
        self.assertEqual(tpl['adds'], ((0x8001, 0x824d, 1),))
        self.assertEqual(tpl['start ids'], {0x82d7})
        f = tpl['fields']
        self.assertEqual(f['hitlevel'], TC.HIGH)
        self.assertEqual(f['bitfield'], (TC.OR, 0x80000000))
        self.assertEqual(f['hitbox'], ('value', bytes(4)))
        self.assertEqual(f['voiceclip'], ('value', None))
        self.assertEqual(f['vuln'], TC.SAME)

    def test_no_own_animation_pair(self):
        d = self.donor()
        for k, n in enumerate(d.names):
            if n in ('Ju_aChg', 'Ju_bChg'):
                d.t['moves'][k]['anim'] = 0x4200
        with self.assertRaises(ValueError):
            TC.combo_template(d.t, d.aliases, 8)

    def test_ewgf_window(self):
        h = Tables()
        h.move('stance')
        tag = h.req((TC.TAG_HIT, 0), (TC.CAN_TAG, 0))
        h.move('He_shoryu_S', first_active=11, last_active=12,
               cancel=h.cancels(dict(req=tag, extradata=EX['made'], win_end=20, move_id=0), h.end(36)))
        self.assertEqual(TC.ewgf_window(h.t, h.name_of), 8)


class Picks(Base):
    def test_launchers(self):
        d = self.donor()
        T = d.t
        r = self.r
        first = len(T['moves'])
        launch = d.hits((r['air'], 20, self.r_down), (r['never'], 20, self.r_launch))
        d.move('Ka_up', first_active=15, last_active=16, hit_condition=launch, cancel=d.cancels(d.end(50)))
        d.move('Ka_down', first_active=15, last_active=16, cancel=d.cancels(d.end(50)),
               hit_condition=d.hits((r['never'], 20, self.r_down)))
        d.move('Ka_bound', first_active=15, last_active=16, cancel=d.cancels(d.end(50)),
               hit_condition=d.hits((r['bound'], 20, self.r_down), (r['never'], 20, self.r_launch)))
        d.move('Ka_slow', first_active=40, last_active=41, hit_condition=launch, cancel=d.cancels(d.end(70)))
        d.move('Ka_air_only', first_active=15, last_active=16, cancel=d.cancels(d.end(50)),
               hit_condition=d.hits((r['air'], 20, self.r_launch), (r['never'], 20, self.r_down)))
        own = list(range(first, len(T['moves'])))
        self.assertEqual([d.names[i] for i in TC.launchers(T, d.aliases, own)], ['Ka_up'])
        self.assertEqual(TC.air_time(T, d.aliases, T['moves'][first]), 51)

    def test_reachable(self):
        d = self.donor()
        stance = 0
        d.aliases[1] = stance
        T = d.t
        b, b_exit, a = (d.names.index(n) for n in ('Ju_b', 'Ju_bChg', 'Ju_a'))
        T['moves'][stance]['cancel'] = d.cancels(dict(button=1, move_id=b), d.end(0))
        live = TC.reachable(T, d.aliases)
        self.assertIn(b, live)
        self.assertIn(b_exit, live)                              # through its tag row
        self.assertNotIn(a, live)                                # nothing leads to it


class Make(Base):
    def converted(self, recovery=60, extra_hit_row=False):
        d = self.donor()
        tpl = TC.combo_template(d.t, d.aliases, 8)
        T = copy.deepcopy(d.t)
        names = Tables()
        names.names = list(d.names)
        r = self.r
        first = len(T['moves'])
        hl = TS.write(T, 'hit_conditions', [dict(req=r['air'], damage=21, reactions=self.r_down),
                                            dict(req=r['never'], damage=21, reactions=self.r_launch)])
        pl = TS.write(T, 'extra_move_properties', [dict(frame=0x8001, id=0x80f8, value=7),
                                                   dict(frame=6, id=0x801f, value=0x763),
                                                   dict(frame=30, id=0x82f9, value=1),
                                                   dict(frame=0x4001, id=0x822C, value=0),
                                                   dict(frame=0, id=0, value=0)])
        x = dict(T['moves'][2], name=0, first_active=11, last_active=12, anim=0x4300, hitlevel=0x2C0512,
                 bitfield=0x20, voiceclip=9, hit_condition=hl, extraprops=pl, transition=CROUCH)
        own_rows = [dict(direction=0, button=0, req=r['hit'], extradata=EX['action'], win_start=1, win_end=32767,
                         start_frame=1, move_id=STANCE, option=0)]
        if extra_hit_row:
            own_rows.append(dict(direction=0, button=0, req=r['hit'], extradata=EX['keep'], win_start=11, win_end=12,
                                 start_frame=11, move_id=first + 1, option=0))
        own_rows.append(dict(direction=M.LIST_END, button=0, req=r['always'], extradata=EX['plain'],
                             win_start=recovery, win_end=32767, start_frame=recovery, move_id=0, option=0))
        x['cancel'] = TS.write(T, 'cancels', own_rows)
        T['moves'].append(x)
        names.names.append('Zbr_shoryu_S')
        if extra_hit_row:
            h = dict(x, first_active=0, last_active=0, hit_condition=self.nohit,
                     cancel=TS.write(T, 'cancels', [dict(own_rows[-1])]))
            T['moves'].append(h)
            names.names.append('Zbr_shoryu_S_H')
        return d, tpl, T, names, first, x

    def test_row_and_exit(self):
        d, tpl, T, names, first, x = self.converted()
        old_list = x['cancel']
        old = rows(T, old_list)
        made = TC.add_tag_combos(T, tpl, [first], d.aliases, names.name_of, names.string)
        self.assertEqual(made, [(first, first + 1, [])])
        self.assertEqual(rows(T, T['moves'][first]['cancel'])[0], old[0])          # the on-hit action row first
        tag = rows(T, T['moves'][first]['cancel'])[1]
        self.assertEqual((tag['button'], tag['req'], tag['extradata'], tag['win_start'], tag['win_end'],
                          tag['start_frame'], tag['move_id']), (0, self.r['tag'], EX['own'], 1, 20, 1, first + 1))
        self.assertEqual(rows(T, old_list), old)                                     # X's old list unchanged
        e = T['moves'][first + 1]
        self.assertEqual(names.names[e['name']], 'Zbr_shoryu_SChg')
        self.assertEqual((e['anim'], e['first_active'], e['last_active'], e['hitbox'], e['voiceclip']),
                         (0x4300, 0, 0, bytes(4), None))
        self.assertEqual((e['hitlevel'], e['bitfield'], e['transition']), (0x2C0000, 0x80000020, CROUCH))
        self.assertEqual(e['hit_condition'], self.nohit)
        ex = rows(T, e['cancel'])
        self.assertEqual([(c['move_id'], c['win_start']) for c in ex],
                         [(TC.HUB, 1), (STANCE, 23), (CROUCH, 27), (0, 0)])               # out 20+3, back +4
        self.assertEqual(ex[1]['req'], self.r['out'])
        props = TS.props(T, e['extraprops'])
        self.assertEqual([(p['frame'], p['id']) for p in props], [(30, 0x82f9), (0x4001, 0x822C), (0x8001, 0x824d)])
        # X's own property rows themselves (effects are renumbered in them later)
        self.assertTrue(any(p is q for p in props for q in TS.props(T, x['extraprops'])))

    def test_short_recovery(self):
        d, tpl, T, names, first, x = self.converted(recovery=22)
        TC.add_tag_combos(T, tpl, [first], d.aliases, names.name_of, names.string)
        tag = rows(T, T['moves'][first]['cancel'])[1]
        ex = rows(T, T['moves'][first + 1]['cancel'])
        self.assertEqual((tag['win_end'], ex[1]['win_start'], ex[2]['win_start']), (20, 21, 22))

    def test_too_short_is_left_out(self):
        d, tpl, T, names, first, x = self.converted(recovery=13)       # the window would end before frame 12
        self.assertEqual(TC.add_tag_combos(T, tpl, [first], d.aliases, names.name_of, names.string), [])

    def test_hit_version_and_air(self):
        d, tpl, T, names, first, x = self.converted(extra_hit_row=True)
        e_i = len(T['moves'])
        made = TC.add_tag_combos(T, tpl, [first], d.aliases, names.name_of, names.string, air={first})
        self.assertEqual(made, [(first, e_i, [first + 1])])
        tag = rows(T, T['moves'][first]['cancel'])[1]
        self.assertEqual(TS.reqs(T, tag['req']), [(TC.TAG_HIT, 0), (TC.CAN_TAG, 0), (TS.AIR, 0)])
        press = rows(T, T['moves'][first + 1]['cancel'])[0]
        self.assertEqual((press['button'], press['move_id'], press['win_end'], press['extradata']),
                         (TS.TAG_BUTTON, e_i, 20, EX['own']))
        self.assertEqual(TS.reqs(T, press['req']), [(TC.CAN_TAG, 0), (TS.AIR, 0)])



class Tighten(unittest.TestCase):
    def test_classes_twins_and_best(self):
        d = Tables()
        names = ['Ka_up', 'Co_s_trp00', 'Ka_10comb7', 'Ka_jprk00F', 'Ka_up01', 'Ka_df2', 'Co_t_slk00B']
        anims = [1, 2, 3, 4, 1, 5, 6]
        for n, a in zip(names, anims):
            d.move(n, anim=0x4000 + a, first_active=15, last_active=16)
        picks = list(range(len(names)))
        out = TC.tighten(d.t, picks, d.name_of, donor_tagged={'Co_t_slk00B'})
        self.assertEqual([d.names[i] for i in out], ['Ka_up', 'Ka_df2', 'Co_t_slk00B'])   # Ka_up01: Ka_up's twin
        # nothing left: the best one (not a jump or 10-hit move first, then the earliest active)
        d.t['moves'][1]['first_active'] = 20
        self.assertEqual([d.names[i] for i in TC.tighten(d.t, [1, 2, 3], d.name_of)], ['Co_s_trp00'])
        self.assertEqual(TC.left_out('Co_sjprk01F'), {'generic', 'jump'})
        # a generic move whose stem TTT2's fighters' own launchers mostly have a tag combo on is kept
        out = TC.tighten(d.t, picks, d.name_of, stems={'s_trp00'})
        self.assertEqual([d.names[i] for i in out], ['Ka_up', 'Co_s_trp00', 'Ka_df2'])
        self.assertEqual(TC.left_out('Co_sjprk01F', stems={'sjprk01F'}), {'jump'})

    def test_stems(self):
        d = Tables()
        d.move('Ju_stance')
        launch = d.move('sDw_UP_01_', airborne_start=1, airborne_end=52)
        r = d.reaction(launch)
        hit = d.hits((d.req(), 20, r))
        tag, hub = d.req((TC.TAG_HIT, 0), (TC.CAN_TAG, 0)), d.req((TC.OFF_POINT, 0))
        out = d.req((TC.TAG_OUT, 0x16))
        e = len(d.t['moves']) + 1
        d.move('Ju_s_trp00', first_active=15, last_active=16, hit_condition=hit,
               cancel=d.cancels(dict(req=tag, move_id=e), d.end()))
        d.move('Ju_s_trp00Chg', cancel=d.cancels(dict(req=hub, move_id=TC.HUB), dict(req=out, move_id=STANCE),
                                                  d.end(0)))
        d.move('Ju_t_srpF', first_active=15, last_active=16, hit_condition=hit, cancel=d.cancels(d.end()))
        d.move('Co_s_trp00', first_active=15, last_active=16, hit_condition=hit, cancel=d.cancels(d.end()))

        class Set:
            tables, aliases = d.t, d.aliases

            def move_name(self, i):
                return d.names[d.t['moves'][i]['name']]
        self.assertEqual(TC.combo_stems([Set()]), {'s_trp00': (1, 1), 't_srpF': (1, 0)})


class IdleVariants(unittest.TestCase):
    def test_stance_rows_shared(self):
        d = Tables()
        always, never = d.req((0, 0)), d.req((1, 0))
        stance = d.move('Zbr_sKAM00_')
        idle1, idle2, empty = (d.move(n, transition=STANCE) for n in ('Zbr_sKAM00_1', 'Zbr_sKAM00_2', 'It_practice'))
        walk = d.move('Zbr_sWALKF')
        d.aliases[0] = stance
        own = [dict(direction=0x40, req=always, move_id=walk), dict(direction=M.GROUP, move_id=7)]
        d.t['moves'][stance]['cancel'] = d.cancels(
            dict(button=TS.TAG_BUTTON, req=always, move_id=walk),                    # (the donor's: tag out ...)
            dict(direction=M.GROUP, move_id=3), *own,
            dict(req=always, win_start=120, win_end=120, start_frame=120, move_id=idle1),
            dict(req=always, win_start=120, win_end=120, start_frame=120, move_id=idle2),
            dict(req=never, move_id=empty), d.end(0))
        for v in (idle1, idle2):
            d.t['moves'][v]['cancel'] = d.cancels(*own, d.end(0))
        d.t['moves'][empty]['cancel'] = d.cancels(d.end(0))
        self.assertEqual(TS.idle_variants(d.t, d.aliases, 1), {stance: [idle1, idle2]})
        old = d.t['moves'][stance]['cancel']
        self.assertEqual(TS.share_stance(d.t, d.aliases, 1), 2)
        rows = TS.cancels(d.t, d.t['moves'][idle1]['cancel'])
        self.assertEqual([(r['direction'], r['move_id']) for r in rows],
                         [(0, walk), (M.GROUP, 3), (0x40, walk), (M.GROUP, 7), (0, empty), (M.LIST_END, 0)])
        self.assertEqual(d.t['moves'][idle2]['cancel'], d.t['moves'][idle1]['cancel'])
        self.assertEqual(d.t['moves'][stance]['cancel'], old)                       # the stance's own list stays
        self.assertEqual(len(TS.cancels(d.t, d.t['moves'][empty]['cancel'])), 1)

if __name__ == '__main__':
    unittest.main()
