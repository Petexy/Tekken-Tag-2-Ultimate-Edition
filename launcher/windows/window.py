"""The Windows launcher's window, as the Linux launcher's (launcher/app): the header bar, the
update notice, the banner, the game and its characters on one page, Settings on another, and the
task panel below both. Windows' own parts stay: Set Up Game and the tools it gets, building and
installing from a Wii U source (the More menu), the folders (Settings) and the logs.
"""
from pathlib import Path
import datetime
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import keys
import look
import self_update
from backend import built_by, importer, installed_by
from look import (BAD, CARD_LINE, DIM, HEADER, HEADER_LINE, LIST, LOG, NOTICE, NOTICE_ICON, OK, ROW_LINE, TASK,
                  TASK_LINE, TEXT, WARN, WINDOW)

NAME = 'Ultimate Launcher'
NOTE = ('The Wii U game as a native Windows program, built on this PC from your own copy, with Tekken 7\'s and '
        'Tekken 8\'s characters added from yours.')
RESOLUTIONS = [('auto', 'Automatic'), ('1280x720', '1280 × 720'), ('1920x1080', '1920 × 1080'),
               ('2560x1440', '2560 × 1440'), ('3840x2160', '3840 × 2160'), ('5120x2880', '5120 × 2880')]
TASK_TITLES = dict(setup='Setting up the game', build='Building the game', install='Installing the game',
                   update='Updating the installed game', upgrade='Updating the game', launcher='Updating the launcher',
                   files='Updating the launcher')
FOLDERS = [('source', 'Wii U archive', 'Your European Wii U .wua with update v16', False),
           ('title', 'Extracted Wii U title', 'For development imports, instead of an installed game', True),
           ('install', 'Installation folder', 'Where Set Up Game installs the game', True),
           ('data', 'Data folder', 'Settings, logs and saves: its name ends in TTT2Ultimate', True),
           ('packs', 'Fighter packs', 'The characters added to the game', True),
           ('saves', 'Save files', 'The game\'s saves', True),
           ('tools', 'Build tools', 'The compiler and libraries Set Up Game downloads', True)]


def clear(widget):
    for child in widget.winfo_children(): child.destroy()


def opened(path):
    """A file or folder shown by Windows (or this desktop)."""
    if sys.platform == 'win32': os.startfile(path)
    else: webbrowser.open(Path(path).as_uri())


class Window:
    def __init__(self, args, settings):
        look.dpi_aware()
        self.args, self.settings = args, settings
        self.root = tk.Tk(className='UltimateLauncher')
        self.root.title(NAME)
        self.root.withdraw()
        self.look = L = look.Look(self.root)
        px = L.px
        height = min(px(860), self.root.winfo_screenheight() - px(80))
        self.root.geometry('%dx%d' % (px(880), height))
        self.root.minsize(px(520), min(px(480), height))
        self.exe = self_update.running_exe()
        if self.exe:
            try: self.root.iconbitmap(default=str(self.exe))
            except tk.TclError: pass
        self.version = self_update.version()
        # What a game built from these files is from (the version; a test build's commit too).
        self.files_id = self_update.files_id()
        self.events = queue.Queue()
        self.task = None            # the task running, or ended and shown
        self.game = None            # the game, when started from here
        self.status, self.status_error, self.status_loading, self.status_time = None, '', False, 0.0
        self.owned, self.owned_state = None, 'unknown'
        self.outfits = {}           # the outfit boxes clicked: {fighter: whether to make their outfits}
        self.release = dict(newer=None, checking=False, time=time.monotonic())
        # What main has beyond this build (launcher.py main), when its commit is known: a test build's
        # own branch instead, whose newer commits update these files (Update, self_update.update_files).
        self.commit, self.main_news, self.main_checking = self_update.build_commit(), None, False
        self.branch = self_update.test_branch() if self.exe else None
        self.news_branch = self.branch or 'main'
        self.dlc_open, self.picking, self.page = False, None, 'main'
        self.root.report_callback_exception = self.callback_failed
        self.build_header()
        self.build_task_panel()
        self.body = tk.Frame(self.root, bg=WINDOW)
        self.body.pack(fill='both', expand=True)
        self.main = look.Page(self.body, L)
        self.settings_page = look.Page(self.body, L)
        self.build_main()
        self.build_settings()
        self.main.pack(fill='both', expand=True)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        # Back in the launcher (after starting Steam, say): look again (GitHub after hours).
        self.root.bind('<FocusIn>', self.focused, add='+')
        self.root.deiconify()
        look.dark_title_bar(self.root)
        self.refresh()
        self.pump()
        if self.exe and not args.ui_smoke_test: self.root.after(1000, self.check_release)
        if self.commit and not args.ui_smoke_test: self.root.after(1500, self.check_main)
        if args.ui_smoke_test: self.root.after(500, self.smoke_test)

    def run(self):
        self.root.mainloop()
        return getattr(self, 'smoke_error', None)

    def callback_failed(self, kind, value, trace):
        text = ''.join(traceback.format_exception(kind, value, trace))
        print(text, flush=True)
        if self.args.ui_smoke_test: self.smoke_error = value
        messagebox.showerror(NAME, '%s\n\nDetails are in the launcher\'s log.' % value, parent=self.root)

    # ---------------------------------------------------------------- the header bar

    def build_header(self):
        L, px = self.look, self.look.px
        bar = L.frame(self.root, 'header')
        bar.configure(height=px(46))
        bar.pack_propagate(False)
        bar.pack(fill='x')
        tk.Frame(self.root, bg=HEADER_LINE, height=1).pack(fill='x')
        self.back_button = L.button(bar, icon='back', kind='flat', command=self.close_settings, tip='Back')
        self.title = tk.Label(bar, text=NAME, bg=HEADER, fg=TEXT, font=L.fonts['header'])
        self.title.place(relx=0.5, rely=0.5, anchor='center')
        self.refresh_button = L.button(bar, icon='refresh', kind='flat', command=self.check_again, tip='Check again')
        self.refresh_button.pack(side='right', padx=(0, px(8)))
        self.update_button = L.button(bar, icon='update', kind='flat', command=self.update_launcher,
                                      tip=self.update_tip())
        if self.exe: self.update_button.pack(side='right', padx=(0, px(2)))

    # ---------------------------------------------------------------- the main page

    def build_main(self):
        L, px = self.look, self.look.px
        column = self.main.column
        # A newer version of the launcher, when GitHub has one (show_notice).
        self.notice = L.box(column, 'Notice')
        self.notice.configure(padding=(px(18), px(14), px(16), px(14)))
        tk.Label(self.notice, image=L.icon('update', 20, NOTICE_ICON), bg=NOTICE).pack(side='left', padx=(0, px(14)))
        texts = L.frame(self.notice)
        texts.pack(side='left', fill='x', expand=True)
        self.notice_title = L.label(texts, kind='notice')
        self.notice_title.pack(fill='x')
        self.notice_detail = L.label(texts, kind='small', wrap=True)
        self.notice_detail.pack(fill='x', pady=(px(3), 0))
        self.notice_update = L.button(self.notice, 'Update', self.update_launcher, 'suggested')
        self.notice_update.pack(side='right')
        self.notice_page = L.button(self.notice, 'What\'s New', self.open_release_page)
        self.notice_page.pack(side='right', padx=(0, px(8)))
        self.banner = look.Banner(column, L, NOTE)
        self.banner.pack(fill='x')
        self.game_title = L.label(column, 'Game', 'section')
        self.game_title.pack(fill='x', padx=px(4), pady=(px(26), px(10)))
        self.game_card = L.box(column, 'Card')
        self.game_card.configure(padding=(px(20), px(18)))
        self.game_card.pack(fill='x')
        L.label(column, 'Characters', 'section').pack(fill='x', padx=px(4), pady=(px(26), px(10)))
        self.characters_card = L.box(column, 'Card')
        self.characters_card.configure(padding=(px(20), px(18)))
        self.characters_card.pack(fill='x')

    def show_all(self):
        self.show_game()
        self.show_characters()
        self.show_notice()

    def show_banner_icon(self):
        folder = self.settings.installed()
        icon = folder / 'icon.png' if folder else None
        image = None
        if icon and icon.is_file():
            try:
                image = tk.PhotoImage(file=str(icon))
                size = self.look.px(72)
                factor = max(1, round(image.width() / size))
                if factor > 1: image = image.subsample(factor)
            except tk.TclError:
                image = None
        self.banner_icon = image
        self.banner.set_icon(image)

    def note(self, parent, icon, text, colour=DIM, button=None):
        """A line of a card with an icon and a note (and a button after it), as the Linux launcher's."""
        L, px = self.look, self.look.px
        line = L.frame(parent)
        line.pack(fill='x', pady=(px(10), 0))
        tk.Label(line, image=L.icon(icon, 16, colour), bg=look.surface_of(parent)).pack(side='left', anchor='n',
                                                                                         padx=(0, px(10)), pady=px(2))
        if button:
            button.pack(in_=line, side='right', padx=(px(12), 0))
            button.lift()
        L.label(line, text, wrap=True).pack(side='left', fill='x', expand=True)
        return line

    def show_game(self):
        L, px = self.look, self.look.px
        card = self.game_card
        clear(card)
        installed = self.settings.installed()
        busy = self.task is not None and self.task.get('running')
        running = self.game is not None and self.game.poll() is None
        top = L.frame(card)
        top.pack(fill='x')
        L.label(top, 'Tekken Tag Tournament 2', 'card').pack(side='left')
        state = ('Running', 'ok') if running else ('Installed', 'ok') if installed else ('Not installed', 'neutral')
        L.pill(top, *state).pack(side='right')
        if installed:
            L.label(card, str(installed), 'path').pack(fill='x', pady=(px(4), 0))
        else:
            self.note(card, 'info', 'Set Up Game asks for your own European Wii U archive (.wua) with update v16 and '
                      'a folder. It downloads what it needs, builds the game on this PC from your copy and installs it: '
                      'about 30 GB, and a while. Your archive is kept.')
        game_files = installed_by(self.settings)
        update = bool(installed and game_files and game_files != self.files_id)
        if update:
            self.note(card, 'warning', 'An update of the game is ready (Ultimate Launcher %s; the game is from %s). '
                      'Update builds it again on this PC from your game: a few minutes.'
                      % (self_update.shown_id(self.files_id), self_update.shown_id(game_files)), WARN)
        buttons = L.frame(card)
        buttons.pack(fill='x', pady=(px(16), 0))
        if installed:
            play = L.button(buttons, 'Play', self.play, 'suggested', icon='play')
            play.configure(state='disabled' if busy or running else 'normal')
            play.pack(side='left')
            self.play_button = play
        else:
            setup = L.button(buttons, 'Set Up Game…', self.first_setup, 'suggested')
            setup.configure(state='disabled' if busy else 'normal')
            setup.pack(side='left')
        L.button(buttons, icon='settings', command=self.open_settings, tip='Settings').pack(side='left', padx=(px(8), 0))
        if update:
            b = L.button(buttons, 'Update', lambda: self.start('upgrade'))
            b.configure(state='disabled' if busy or running else 'normal')
            b.pack(side='left', padx=(px(8), 0))
        more = L.button(buttons, 'More', tip='Build, install and the logs')
        more.configure(command=lambda: self.more_menu(more), state='disabled' if busy else 'normal')
        more.pack(side='right')
        if installed:
            L.button(buttons, icon='folder', command=lambda: opened(installed),
                     tip='Open the game\'s folder').pack(side='right', padx=(0, px(8)))

    def more_menu(self, button):
        """Windows' own: building and installing from a Wii U source, and the logs."""
        menu = tk.Menu(self.root, tearoff=0, bg='#2b2b2d', fg=TEXT, activebackground=look.ACCENT,
                       activeforeground=TEXT, bd=0, relief='flat', font=self.look.fonts['normal'])
        installed = self.settings.installed()
        menu.add_command(label='Build / Rebuild', command=lambda: self.start('build'))
        menu.add_command(label='Install from Wii U Source', command=lambda: self.start('install'))
        menu.add_command(label='Update Installed Game', command=lambda: self.start('update'),
                         state='normal' if installed else 'disabled')
        if installed: menu.add_command(label='Set Up Again…', command=self.first_setup)
        menu.add_separator()
        menu.add_command(label='Open Logs Folder', command=self.open_logs)
        menu.add_command(label='Open Latest Log', command=self.open_latest_log)
        try:
            menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        finally:
            menu.grab_release()

    def first_setup(self):
        if self.busy(): return
        source = filedialog.askopenfilename(parent=self.root, title='Choose your European Wii U TTT2 archive (update v16)',
                                            filetypes=[('Wii U game archive', '*.wua')])
        if not source: return
        folder = filedialog.askdirectory(parent=self.root, title='Choose where to install Tekken Tag Tournament 2')
        if not folder: return
        if not messagebox.askokcancel('Set Up Game', 'The launcher will download missing tools, build the game from '
                                      'your archive, and install it. This first setup needs internet, at least 30 GB '
                                      'of free space and may take a while. Your original archive is kept. Continue?',
                                      parent=self.root):
            return
        self.settings.values.update(source=source, install=folder)
        self.folder_vars['source'].set(source); self.folder_vars['install'].set(folder)
        self.start('setup')

    def play(self):
        try:
            if self.game and self.game.poll() is None: raise ValueError('The game is already running.')
            command = self.settings.game_command()
            logs = Path(self.settings.values['data']) / 'logs'
            logs.mkdir(parents=True, exist_ok=True)
            with (logs / 'game-latest.log').open('w', encoding='utf-8') as log:
                self.game = subprocess.Popen(command, cwd=Path(command[0]).parent, env=self.settings.environment(),
                                             stdout=log, stderr=subprocess.STDOUT,
                                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.show_game()
            self.watch_game()
        except Exception as error:
            self.error(error)

    def watch_game(self):
        if self.game and self.game.poll() is None: self.root.after(1000, self.watch_game)
        else: self.show_game()

    # ---------------------------------------------------------------- the characters

    def busy(self):
        return bool(self.task and self.task.get('running'))

    def added(self, f):
        return f['installed'] and not f['outdated'] and not f['newer']

    def owns(self, f):
        if not f['dlc']: return True
        if self.owned is None: return None
        return self.owned.get(f['name'])

    def can_import(self):
        """None, or why no character can be added now."""
        s = self.status
        if not self.settings.installed(): return 'Set up the game first: characters are made from it.'
        if not s: return 'The importer cannot tell what this PC has: %s' % (self.status_error or 'still looking')
        if s.get('game', {}).get('error'): return 'The importer cannot read the installed game: ' + s['game']['error']
        return None

    def readable(self, game):
        s = self.status
        return bool(s and (s['tekken8']['found'] if game == 'tekken8' else s['tekken7']['readable']))

    def game_why(self, game):
        """None, or why `game`'s characters cannot be added now."""
        why = self.can_import()
        if why: return why
        s, name = self.status, 'Tekken 8' if game == 'tekken8' else 'Tekken 7'
        found = s[game]
        if not found['found'] or (game == 'tekken7' and found['error']):
            return found['error'] or '%s is not installed.' % name
        other = 'tekken7' if game == 'tekken8' else 'tekken8'
        if not self.readable(other) and any(self.of(f, other) and self.added(f) for f in s['fighters']):
            other_name = 'Tekken 8' if other == 'tekken8' else 'Tekken 7'
            return ('The %s characters added need %s whenever a character is added: what all of them share is made '
                    'again from each one\'s own game. Install %s again, or remove them first.'
                    % (other_name, other_name, other_name))
        return None

    def of(self, f, game):
        return f.get('game', 'tekken7') == game

    def addable(self, f):
        s = self.status
        if not s or (self.added(f) and not f['update'] and not self.outfits_changed(f)) or f['newer'] or \
                self.owns(f) is False: return False
        steam = s['steam']['running']
        if f['dlc']:
            # (Which DLC is owned not known: Steam is asked when adding, which says so then.)
            return steam and (self.owns(f) is True or self.owned_state == 'failed')
        if self.of(f, 'tekken8'): return f['moveset_saved'] or steam
        return steam or (f['moveset_saved'] and s['movesets']['heihachi'])

    def not_addable_why(self, f):
        if f['dlc']: return 'Start Steam: it checks that you own their DLC'
        if self.of(f, 'tekken8'): return 'Start Steam: Tekken 8 needs it to save their moves'
        return 'Start Steam: Tekken 7 needs it to save their moves'

    def wants_outfits(self, f):
        """Whether adding `f` makes their outfits: as their box was clicked, else as their pack in the game has them."""
        if not f.get('outfits'): return False
        return self.outfits.get(f['name'], f.get('outfits_added', False))

    def outfits_choosable(self, f):
        """Outfits to make, and a pack this importer may make (not a newer version's, nor a DLC's not owned)."""
        return bool(f.get('outfits')) and self.owns(f) is not False and not f['newer']

    def outfit_choices(self):
        return [f for f in self.status['fighters'] if self.outfits_choosable(f)] if self.status else []

    def outfits_changed(self, f):
        """In the game, and their box no longer says what their pack has: updating them adds or removes their outfits.
        (One to update anyway is updated with their box as it is.)"""
        return (self.added(f) and not f['update'] and self.outfits_choosable(f)
                and self.wants_outfits(f) != f.get('outfits_added', False))

    def outfits_to_change(self):
        return [f['name'] for f in self.outfit_choices() if self.outfits_changed(f) and self.addable(f)
                and not self.game_why(f.get('game', 'tekken7'))]

    def set_outfits(self, names, on):
        for name in names: self.outfits[name] = on
        self.show_characters()

    def outfits_line(self, card):
        """One box for every character's outfits (their own boxes are in their rows), and what choosing them costs."""
        L, px = self.look, self.look.px
        choices = self.outfit_choices()
        if not choices: return
        wanted = sum(1 for f in choices if self.wants_outfits(f))
        # (Ticked where an import makes them: not a pack in the game that has them already, with nothing to update.)
        making = sum(1 for f in choices if self.wants_outfits(f) and (not self.added(f) or f['update']
                                                                     or not f.get('outfits_added')))
        changed = [f for f in choices if self.outfits_changed(f)]
        var = tk.BooleanVar(value=wanted == len(choices))
        # (Some or none chosen: all; all: none.)
        every = ttk.Checkbutton(card, text='Import outfits for every character', variable=var, takefocus=True,
                                style='Check.Card.TCheckbutton',
                                command=lambda: self.set_outfits([f['name'] for f in self.outfit_choices()],
                                                                 not all(self.wants_outfits(f) for f in self.outfit_choices())))
        every.var = var
        if 0 < wanted < len(choices): every.state(['alternate'])
        if self.busy(): every.state(['disabled'])
        look.Tooltip(every, 'Outfits are complete bodies for the in-game costume chooser. Without them, a character '
                     'has their default costume.', L)
        every.pack(fill='x', pady=(px(14), 0))
        if making:
            self.note(card, 'warning', 'Importing outfits can drastically prolong adding and updating characters: each '
                      'outfit is a complete extra body made from your Tekken 7\'s files.', WARN)
        # Characters in the game whose box was changed: updating them all at once.
        if not changed: return
        names = self.outfits_to_change()
        b = L.button(card, 'Update All' if len(changed) > 1 else 'Update',
                     lambda: self.start('import', self.outfits_to_change()))
        b.configure(state='normal' if names and not self.busy() else 'disabled')
        if not names and not self.can_import() and not self.busy(): look.Tooltip(b, self.not_addable_why(changed[0]), L)
        one = changed[0]
        self.note(card, 'update', '%d characters\' outfits change when they are updated.' % len(changed)
                  if len(changed) > 1 else '%s\'s outfits are %s when they are updated.'
                  % (one['display'], 'removed' if one.get('outfits_added') else 'added'), WARN, b)

    def removable(self, f):
        """None, or why `f` cannot be removed alone now."""
        s = self.status
        for o in s['fighters'] if s else ():
            if o['name'] != f['name'] and self.added(o) and not self.readable(o.get('game', 'tekken7')):
                name = 'Tekken 8' if self.of(o, 'tekken8') else 'Tekken 7'
                return '%s is needed for the %s characters that stay: what they share is made again from it.' % (name, name)
        return None

    def show_characters(self):
        L, px = self.look, self.look.px
        card = self.characters_card
        clear(card)
        s = self.status
        if not s:
            if self.status_error:
                self.note(card, 'warning', 'The importer cannot tell what this PC has: ' + self.status_error, BAD)
            else:
                L.label(card, 'Looking for Tekken 7, Tekken 8 and Steam…', 'dim').pack(fill='x')
            return
        facts = L.frame(card)
        facts.pack(fill='x')
        facts.columnconfigure(1, weight=1)
        rows = [('Tekken 7', s['tekken7']), ('Tekken 8', s['tekken8'])]
        for row, (name, found) in enumerate(rows):
            L.label(facts, name, 'dim').grid(row=row, column=0, sticky='nw', padx=(0, px(18)), pady=px(3))
            if found['found'] and not (name == 'Tekken 7' and found['error']):
                L.label(facts, found['path'], 'path').grid(row=row, column=1, sticky='ew', pady=px(3))
            else:
                L.label(facts, found['error'] or 'Not installed', 'warn', wrap=True).grid(row=row, column=1, sticky='ew',
                                                                                         pady=px(3))
        L.label(facts, 'Steam', 'dim').grid(row=2, column=0, sticky='nw', padx=(0, px(18)), pady=px(3))
        steam = L.frame(facts)
        steam.grid(row=2, column=1, sticky='ew', pady=px(3))
        if not s['steam']['installed']:
            L.label(steam, 'Not installed', 'warn').pack(fill='x')
        elif s['steam']['running']:
            L.label(steam, 'Running', 'ok').pack(fill='x')
        else:
            L.label(steam, 'Not running', 'warn').pack(fill='x')
            L.label(steam, 'Start Steam to add characters: Tekken 7 needs it the first time, and it tells which DLC you '
                    'own.', 'small', wrap=True).pack(fill='x', pady=(px(2), 0))
        why = self.can_import()
        if why: self.note(card, 'warning', why, WARN)
        fresh = [n['display'] for n in self.main_news['new']] if self.main_news else []
        if fresh:
            names = fresh[0] if len(fresh) == 1 else ', '.join(fresh[:-1]) + ' and ' + fresh[-1]
            self.note(card, 'info', ('%s adds %s: Update the launcher to get them.' % (self.branch, names)) if self.branch
                      else 'Main adds %s: they come with the next release.' % names)
        self.outfits_line(card)
        for game in ('tekken7', 'tekken8'):
            tk.Frame(card, bg=CARD_LINE, height=1).pack(fill='x', pady=(px(18), px(16)))
            self.show_game_characters(card, game)

    def show_game_characters(self, card, game):
        L, px = self.look, self.look.px
        s, busy = self.status, self.busy()
        name = 'Tekken 8' if game == 'tekken8' else 'Tekken 7'
        fighters = [f for f in s['fighters'] if self.of(f, game)]
        base = [f for f in fighters if not f['dlc']]
        dlc = [f for f in fighters if f['dlc']]
        why = self.game_why(game)
        head = L.frame(card)
        head.pack(fill='x')
        to_add = [f['name'] for f in base if not self.added(f) and self.addable(f)] if not why else []
        add_all = L.button(head, 'Add All', lambda: self.start('import', to_add))
        add_all.configure(state='normal' if to_add and not busy else 'disabled')
        add_all.pack(side='right', anchor='n', padx=(px(16), 0))
        texts = L.frame(head)
        texts.pack(side='left', fill='x', expand=True)
        L.label(texts, "%s's characters" % name, 'card').pack(fill='x')
        L.label(texts, 'They join the roster beside the game\'s own fighters. Each takes a few minutes; the first time, '
                '%s runs hidden in the background to save their moves.' % name, 'small', wrap=True).pack(fill='x',
                                                                                                        pady=(px(2), 0))
        if why and why != self.can_import():
            self.note(card, 'warning', why, WARN)
        update = [f['name'] for f in base if f['update'] and self.addable(f)] if not why else []
        if update:
            b = L.button(card, 'Update All' if len(update) > 1 else 'Update', lambda: self.start('import', update))
            b.configure(state='disabled' if busy else 'normal')
            who = '%d characters were' % len(update) if len(update) > 1 else self.display(update[0]) + ' was'
            self.note(card, 'update', '%s made by an older version: update %s to get what this one adds.'
                      % (who, 'them all' if len(update) > 1 else 'them'), WARN, b)
        self.fighter_list(card, base, why)
        if not dlc: return
        head = L.frame(card)
        head.pack(fill='x', pady=(px(18), 0))
        toggle = L.button(head, 'DLC characters', self.toggle_dlc, 'flat', surface='card',
                          icon='expanded' if self.dlc_open else 'collapsed')
        toggle.pack(side='left')
        if self.owned_state == 'checking': L.pill(head, 'Checking ownership…').pack(side='left', padx=(px(6), 0))
        elif self.owned is not None:
            owned = sum(1 for f in dlc if self.owned.get(f['name']))
            L.pill(head, '%d of %d owned' % (owned, len(dlc))).pack(side='left', padx=(px(6), 0))
        later = sum(1 for f in dlc if f['update'])
        if later: L.pill(head, '%d to update' % later, 'warn').pack(side='left', padx=(px(6), 0))
        owned_to_add = [f['name'] for f in dlc if not self.added(f) and self.addable(f)] if not why else []
        add_owned = L.button(head, 'Add All Owned', lambda: self.start('import', owned_to_add))
        add_owned.configure(state='normal' if owned_to_add and not busy else 'disabled')
        add_owned.pack(side='right')
        if not self.dlc_open: return
        if self.owned is not None:
            text = 'Your Steam account owns %d of them.' % sum(1 for f in dlc if self.owned.get(f['name']))
        elif self.owned_state == 'failed':
            text = 'Steam could not tell which you own: adding one asks it again.'
        else:
            text = 'Start Steam to add them: it tells which of them you own.'
        L.label(card, text, 'small', wrap=True).pack(fill='x', pady=(px(6), 0))
        self.fighter_list(card, dlc, why)

    def toggle_dlc(self):
        self.dlc_open = not self.dlc_open
        self.show_characters()

    def display(self, name):
        return next((f['display'] for f in self.status['fighters'] if f['name'] == name), name) if self.status else name

    def fighter_list(self, card, fighters, why):
        L, px = self.look, self.look.px
        box = L.box(card, 'List')
        box.configure(padding=px(4))
        box.pack(fill='x', pady=(px(12), 0))
        installed = self.settings.installed()
        for i, f in enumerate(fighters):
            if i: tk.Frame(box, bg=ROW_LINE, height=1).pack(fill='x')
            row = L.frame(box)
            row.pack(fill='x')
            line = L.frame(row)
            line.pack(fill='x', padx=(px(10), px(4)), pady=px(5))
            L.label(line, f['display'], width=18).pack(side='left')   # (the outfits' boxes in a column after it)
            owned = self.owns(f)
            # Their outfits: whether adding them makes theirs, or (in the game with nothing to add) whether their
            # pack has them.
            choosable = self.outfits_choosable(f)
            if choosable or (f.get('outfits') and self.added(f)):
                var = tk.BooleanVar(value=self.wants_outfits(f) if choosable else f.get('outfits_added', False))
                outfit_box = ttk.Checkbutton(line, text='Outfits', variable=var, takefocus=True, style='Check.List.TCheckbutton',
                                      command=lambda n=f['name'], v=var: self.set_outfits([n], v.get()))
                outfit_box.var = var
                if not choosable or self.busy(): outfit_box.state(['disabled'])
                count, has = f['outfits'], f.get('outfits_added')
                tip = ('Also make their %d outfits for the costume chooser: adding them takes much longer' % count
                       if not self.added(f) or f['update'] else
                       ('Their pack has their outfits' if has else 'Their pack has no outfits') if not choosable else
                       'Their pack has their outfits: untick, then Update, to remove them' if has else
                       'Tick, then Update, to add their %d outfits (it takes much longer)' % count)
                look.Tooltip(outfit_box, tip, L)
                outfit_box.pack(side='left', padx=(px(12), 0))
            buttons = []
            if f['outdated'] or f['update'] or self.added(f):
                remove = L.button(line, 'Remove', lambda n=f['name']: self.start('remove', [n]), 'flat', width=-8)
                not_now = self.removable(f)
                remove.configure(state='normal' if installed and not self.busy() and not not_now else 'disabled')
                if not_now: look.Tooltip(remove, not_now, L)
                buttons.append(remove)
            if not self.added(f) or f['update'] or self.outfits_changed(f):
                text = 'Add Again' if f['outdated'] else 'Add' if not self.added(f) else 'Update'
                add = L.button(line, text, lambda n=f['name']: self.start('import', [n]), width=-8)
                can = not why and not self.busy() and self.addable(f)
                add.configure(state='normal' if can else 'disabled')
                tip = '' if why or can else ('Start Steam: it tells which DLC you own' if owned is None and f['dlc']
                                             else 'Your Steam account does not own their DLC' if owned is False
                                             else self.not_addable_why(f))
                if tip and not self.busy(): look.Tooltip(add, tip, L)
                buttons.append(add)
            for b in reversed(buttons): b.pack(side='right', padx=(px(8), 0))
            state = self.fighter_state(f, owned)
            if state:
                text, kind, tip = state
                widget = L.pill(line, text, kind, tip) if kind else L.label(line, text, 'small')
                widget.pack(side='right', padx=(px(8), px(4)))

    def fighter_state(self, f, owned):
        if f['outdated']:
            return 'Older version', 'warn', 'Made by an older version: the game leaves them out until they are added again.'
        if f['newer']:
            return ('Newer version', 'warn', 'Made by a newer version of Ultimate Launcher: the game leaves them out until '
                    'it is updated.')
        if f['update']:
            return ('Update ready', 'warn', 'They fight with Heihachi\'s moves: updating them gives them their own.'
                    if f.get('stand_in') else 'Made by an older version: they are in the game, and updating them gives '
                    'them what this version adds.')
        if self.outfits_changed(f):
            return (('Outfits to remove', 'warn', 'Update them to remove their outfits.') if f.get('outfits_added') else
                    ('Outfits to add', 'warn', 'Update them to add their outfits.'))
        if f.get('stand_in'):
            return 'Heihachi\'s moves', 'neutral', 'They fight with Heihachi\'s moves until their own can be saved.'
        if self.main_news and f['name'] in self.main_news['fighters'] and self.added(f):
            return 'Newer on ' + self.news_branch, 'neutral', (
                '%s has an update for them: Update the launcher, then them.' % self.branch if self.branch else
                'Main has an update for them: it comes with the next release.')
        if f['installed']: return 'Added', 'ok', None
        if f['dlc'] and owned is not None: return ('Owned' if owned else 'Not owned'), None, None
        return None

    def load_status(self):
        if self.status_loading: return
        self.status_loading = True
        def ask():
            try:
                answer = importer(self.settings, 'status', timeout=120)
            except Exception as error:
                answer = error
            self.events.put(('status', answer))
        threading.Thread(target=ask, daemon=True).start()

    def status_known(self, answer):
        self.status_loading = False
        self.status_time = time.monotonic()
        if isinstance(answer, Exception):
            self.status, self.status_error = None, str(answer) or type(answer).__name__
        else:
            self.status, self.status_error = answer, ''
            # Steam closed: asked again once it runs again (as another account, maybe).
            if not answer['steam']['running'] and self.owned_state != 'checking': self.owned_state = 'unknown'
        self.show_characters()
        self.check_ownership()

    def check_ownership(self):
        """Which DLC the Steam account owns, asked once Steam runs (as the Linux launcher asks)."""
        s = self.status
        if (not s or self.owned_state != 'unknown' or not s['steam']['running'] or not s['tekken7']['found']
                or not any(f['dlc'] for f in s['fighters'])):
            return
        self.owned_state = 'checking'
        def ask():
            try:
                answer = importer(self.settings, 'owned', timeout=300)
            except Exception as error:
                answer = {'error': str(error)}
            self.events.put(('owned', answer))
        threading.Thread(target=ask, daemon=True).start()
        self.show_characters()

    def owned_known(self, answer):
        if 'owned' in answer:
            self.owned, self.owned_state = answer['owned'], 'known'
        else:
            print('Ultimate Launcher: Steam could not tell which DLC is owned:', answer.get('error'), flush=True)
            self.owned_state = 'failed'
        self.show_characters()

    # ---------------------------------------------------------------- refreshing

    def refresh(self):
        self.show_banner_icon()
        self.show_all()
        self.load_status()

    def check_again(self):
        if self.owned_state == 'failed': self.owned_state = 'unknown'
        self.refresh()

    def focused(self, event):
        if event.widget is not self.root: return
        if time.monotonic() - self.release['time'] >= self_update.CHECK_SECONDS:
            self.check_release()
            self.check_main()
        if not self.busy() and not self.status_loading and time.monotonic() - self.status_time > 5:
            self.refresh()

    # ---------------------------------------------------------------- the launcher's own update

    def show_notice(self):
        newer, news = self.release['newer'], self.main_news
        L = self.look
        offered = bool(self.exe and newer) or bool(self.branch and news and news['ahead'])
        if (self.exe and newer) or (news and news['ahead']):
            if self.exe and newer:
                self.notice_title.configure(text='Version %s of the launcher is out' % newer.version)
                self.notice_detail.configure(text='You have %s. Update replaces this launcher with it and opens it.'
                                             % ('a test build of it' if newer.version == self.version else self.version))
                self.notice_link = newer.page
                show_page = newer.page.startswith('https://') or (self_update.custom_releases() and newer.page)
                self.notice_update.configure(state='disabled' if self.busy() else 'normal')
            else:
                # Newer changes on main, before a release has them (as the Linux launcher says); a test
                # build's on its branch, which Update gets.
                count = news['ahead']
                self.notice_title.configure(text='Newer changes are on ' + self.news_branch)
                newest = (', the newest: \u201c%s\u201d' % news['changes'][0]) if news['changes'] else ''
                self.notice_detail.configure(text='%d change%s since this %s (%s, %s)%s. %s' % (
                    count, '' if count == 1 else 's', 'test build' if self.branch else 'version', self.version,
                    self.commit[:7], newest, 'Update gets them without a new .exe.' if self.branch else
                    'They come with the next release.'))
                self.notice_link = news['page']
                show_page = news['page'].startswith('https://') or bool(os.environ.get('TTT2_LAUNCHER_GITHUB'))
                self.notice_update.configure(state='disabled' if self.busy() else 'normal')
            self.notice_update.pack_forget()
            self.notice_page.pack_forget()
            if offered: self.notice_update.pack(side='right')
            if show_page: self.notice_page.pack(side='right', padx=(0, L.px(8)))
            if not self.notice.winfo_ismapped(): self.notice.pack(fill='x', pady=(0, L.px(14)), before=self.banner)
        else:
            self.notice.pack_forget()
        self.update_button.configure(image=L.icon('update', 16, NOTICE_ICON if offered else TEXT))
        self.update_button.tooltip.text = self.update_tip()

    def update_tip(self):
        newer = self.release['newer'] if self.exe else None
        if newer: return 'Update the launcher to version %s (this is version %s)' % (newer.version, self.version)
        if self.branch: return 'Update the launcher from %s (this is %s, %s)' % (self.branch, self.version,
                                                                                  (self.commit or '')[:7])
        return 'Update the launcher (this is version %s)' % self.version

    def check_release(self):
        if not self.exe or self.release['checking']: return
        self.release.update(checking=True, time=time.monotonic())
        def ask():
            # (Quietly: no notice when GitHub cannot be asked now.)
            try:
                answer = self_update.ask()
                if answer.error: print('Ultimate Launcher:', answer.error, flush=True)
            except Exception as error:
                print('Ultimate Launcher: GitHub cannot be asked for a newer version:', self_update.reason(error),
                      flush=True)
                answer = None
            self.events.put(('release', answer))
        threading.Thread(target=ask, daemon=True).start()

    def release_known(self, answer):
        self.release['checking'] = False
        if not answer: return
        # (A newer release without its .exe yet is not offered.)
        if answer.none: self.release['newer'] = None
        elif answer.release:
            self.release['newer'] = answer.release if self_update.newer_release(answer.release.version) else None
        self.show_notice()

    def open_release_page(self):
        if getattr(self, 'notice_link', ''): webbrowser.open(self.notice_link)

    def check_main(self):
        if not self.commit or self.main_checking: return
        self.main_checking = True
        def ask():
            try:
                answer = importer(self.settings, 'main', '--commit', self.commit,
                                  *(('--branch', self.branch) if self.branch else ()), timeout=120)
            except Exception as error:
                answer = {'error': str(error)}
            self.events.put(('main', answer))
        threading.Thread(target=ask, daemon=True).start()

    def main_known(self, answer):
        self.main_checking = False
        # (Quietly: no notice when GitHub cannot be asked now, or does not know this build.)
        if 'error' in answer: return print('Ultimate Launcher: %s:' % self.news_branch, answer['error'], flush=True)
        self.main_news = answer
        self.show_notice()
        self.show_characters()

    def update_launcher(self):
        if not self.exe: return
        why = self_update.cannot_replace(self.exe)
        if why:
            return self.error('The launcher cannot update itself: its folder, %s, cannot be written to (%s). Move it to '
                              'a folder of yours, then update it.' % (self.exe.parent, why))
        # (A newer release first; else a test build's newer files on its branch.)
        self.start('files' if self.branch and not self.release['newer'] else 'launcher')

    # ---------------------------------------------------------------- tasks

    def build_task_panel(self):
        L, px = self.look, self.look.px
        self.task_panel = L.frame(self.root, 'task')
        tk.Frame(self.task_panel, bg=TASK_LINE, height=1).pack(fill='x')
        inner = L.frame(self.task_panel)
        inner.pack(fill='x', padx=px(24), pady=(px(14), px(16)))
        top = L.frame(inner)
        top.pack(fill='x')
        self.task_button = L.button(top, 'Cancel', self.task_clicked, width=-9)
        self.task_button.pack(side='right', padx=(px(12), 0))
        self.task_log_button = L.button(top, 'Open Log', self.open_task_log, 'flat')
        self.task_log_button.pack(side='right')
        texts = L.frame(top)
        texts.pack(side='left', fill='x', expand=True)
        self.task_title = L.label(texts, kind='task')
        self.task_title.pack(fill='x')
        self.task_detail = L.label(texts, kind='small', wrap=True)
        self.task_detail.pack(fill='x', pady=(px(3), 0))
        self.task_progress = ttk.Progressbar(inner, mode='indeterminate')
        self.task_progress.pack(fill='x', pady=(px(10), 0))
        self.details_button = L.button(inner, 'Details', self.toggle_details, 'flat', icon='collapsed')
        self.details_button.pack(anchor='w', pady=(px(6), 0))
        self.log_frame = tk.Frame(inner, bg=CARD_LINE, bd=0)
        self.log_view = tk.Text(self.log_frame, height=10, wrap='word', bg=LOG, fg='#d8d8d8', bd=0, relief='flat',
                                font=L.fonts['log'], padx=px(10), pady=px(8), insertbackground=TEXT,
                                highlightthickness=0, state='disabled')
        bar = ttk.Scrollbar(self.log_frame, orient='vertical', command=self.log_view.yview)
        self.log_view.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.log_view.pack(fill='both', expand=True, padx=1, pady=1)

    def toggle_details(self):
        if self.log_frame.winfo_ismapped():
            self.log_frame.pack_forget()
            self.details_button.configure(image=self.look.icon('collapsed'))
        else:
            self.log_frame.pack(fill='x', pady=(self.look.px(8), 0))
            self.details_button.configure(image=self.look.icon('expanded'))

    def log(self, text):
        self.log_view.configure(state='normal')
        self.log_view.insert('end', text if text.endswith('\n') else text + '\n')
        self.log_view.see('end')
        self.log_view.configure(state='disabled')

    def start(self, action, names=()):
        try:
            if self.busy(): raise ValueError('Another task is running: wait for it to end.')
            if action not in ('launcher', 'files', 'import', 'remove') and self.game and self.game.poll() is None:
                raise ValueError('Close the game before building or installing it.')
            if action == 'setup':
                from setup_game import validate_setup_paths
                validate_setup_paths(self.settings)
            if action in ('import', 'remove'):
                if self.game and self.game.poll() is None: raise ValueError('Close the game before changing its characters.')
                self.settings.import_command(names, action == 'remove')
            if action in ('install', 'update'): self.settings.installer_command(action == 'update')
            self.settings.save()
            logs = Path(self.settings.values['data']) / 'logs'
            logs.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            logfile, cancel = logs / (action + '-' + stamp + '.log'), logs / (action + '-' + stamp + '.cancel')
            # (Their outfits as their boxes say.)
            outfits = ','.join(f['name'] for f in self.status['fighters'] if f['name'] in names and
                               self.wants_outfits(f)) if action == 'import' and self.status else ''
            command = [sys.executable, '-u', str(Path(__file__).with_name('main.py')), '--build-dir',
                       str(self.settings.build), '--config', str(self.settings.file), '--worker', action,
                       '--cancel-file', str(cancel), '--outfits', outfits or 'none', *names]
            process = subprocess.Popen(command, cwd=self.settings.root, env=self.settings.environment(),
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8',
                                       errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception as error:
            return self.error(error)
        shown = ', '.join(self.display(n) for n in names) if len(names) < 3 else '%d characters' % len(names)
        updating = action == 'import' and self.status and all(
            f['update'] or self.outfits_changed(f) for f in self.status['fighters'] if f['name'] in names)
        title = (('Updating ' if updating else 'Adding ') + shown if action == 'import' else
                 'Removing ' + shown if action == 'remove' else TASK_TITLES[action])
        if action == 'launcher' and self.release['newer']: title += ' to ' + self.release['newer'].version
        self.task = dict(action=action, names=list(names), title=title, process=process, log=logfile, cancel=cancel,
                         running=True, error='', updated='', step='', serial=time.monotonic(), updating=updating)
        self.log_view.configure(state='normal')
        self.log_view.delete('1.0', 'end')
        self.log_view.configure(state='disabled')
        self.task_title.configure(text=title, fg=TEXT)
        self.task_detail.configure(text='Starting…')
        self.task_detail.pack(fill='x', pady=(self.look.px(3), 0))
        self.task_progress.configure(mode='indeterminate')
        self.task_progress.pack(fill='x', pady=(self.look.px(10), 0), before=self.details_button)
        self.task_progress.start(12)
        self.task_button.configure(text='Cancel', state='normal' if action in ('import', 'remove', 'launcher', 'files')
                                   else 'disabled')
        if not self.task_panel.winfo_ismapped(): self.task_panel.pack(side='bottom', fill='x', before=self.body)
        self.show_all()
        def collect():
            with logfile.open('w', encoding='utf-8') as log:
                for line in process.stdout:
                    log.write(line); log.flush(); self.events.put(('line', line))
            self.events.put(('done', process.wait()))
        threading.Thread(target=collect, daemon=True).start()

    def task_line(self, line):
        task = self.task
        text = line.rstrip('\n')
        word, _, rest = text.partition(' ')
        if word == '@step':
            task['step'] = rest.partition(' ')[2] or rest
            self.task_detail.configure(text=task['step'])
        elif word == '@progress':
            try:
                done, total = (int(n) for n in rest.split()[:2])
                if total:
                    self.task_progress.stop()
                    self.task_progress.configure(mode='determinate', maximum=total, value=done)
            except ValueError:
                pass
        elif word == '@error':
            task['error'] = rest.strip()
            self.log(task['error'])
        elif word == '@launcher-updated':
            task['updated'] = rest.strip()
        elif word.startswith('@') and word[1:].isalpha():
            pass                    # (@added, @removed, @done ...: the end says it)
        else:
            self.log(text)

    def task_done(self, code):
        task = self.task
        task['running'] = False
        self.task_progress.stop()
        self.task_progress.pack_forget()
        ok = code == 0
        action, names = task['action'], task['names']
        shown = ', '.join(self.display(n) for n in names) if len(names) < 3 else '%d characters' % len(names)
        mine = action in ('launcher', 'files')     # (the launcher's own update)
        if mine and ok and task['updated'] and 'opened' not in task:
            # The new launcher opened (it waits for this one to end), from a thread: a virus scanner can hold the
            # start of a program it has not seen before, and this window says what it waits for meanwhile, instead
            # of hanging. (Then this again, with what came of it.)
            task.update(running=True, opening=True)
            self.task_title.configure(text='Updated to ' + task['updated'])
            self.task_detail.configure(text='Opening it…')
            self.task_button.configure(state='disabled')
            def open_it():
                try:
                    self_update.open_updated(self.exe); task['opened'] = None
                except OSError as error:
                    task['opened'] = error
                self.events.put(('done', code))
            threading.Thread(target=open_it, daemon=True).start()
            return
        if mine and ok and task['updated'] and not task['opened']:
            self.root.destroy()
            return
        if mine and ok and task['updated']:
            title, detail, ok = ('Updated to %s, but it cannot be opened' % task['updated'],
                                 self_update.reason(task['opened']) + '. Start the launcher again.', False)
        elif code == 130:
            title, detail = ('Update cancelled' if mine else 'Cancelled'), (
                'The launcher is as it was.' if mine else 'Completed extraction data is kept.')
        elif ok:
            title = {'import': ('Updated ' if task['updating'] else 'Added ') + shown, 'remove': 'Removed ' + shown,
                     'setup': 'The game is set up', 'build': 'The game is built', 'install': 'The game is installed',
                     'update': 'The installed game is updated', 'upgrade': 'The game is updated',
                     'launcher': 'The launcher is up to date', 'files': 'The launcher is up to date'}[action]
            detail = task['step'] if mine else 'Click Play to start it.' if action in (
                'setup', 'update', 'upgrade', 'install') else ''
        else:
            title = {'import': 'Could not add ' + shown, 'remove': 'Could not remove ' + shown,
                     'launcher': 'Update failed', 'files': 'Update failed'}.get(action, TASK_TITLES[action] + ' failed')
            detail = task['error'] or 'See Details, or Open Log to send it for help.'
        self.task_title.configure(text=title, fg=TEXT if ok or code == 130 else BAD)
        self.task_detail.configure(text=detail)
        if not detail: self.task_detail.pack_forget()
        self.task_button.configure(text='Close', state='normal')
        self.log('Done.' if ok else title + (': ' + detail if detail else ''))
        # The installer may choose a child folder of a folder that was not empty.
        try:
            self.settings.values.update(json.loads(self.settings.file.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            pass
        for key, var in self.folder_vars.items(): var.set(self.settings.values.get(key, ''))
        if action == 'launcher':
            self.release['newer'] = None if ok else self.release['newer']
        if action == 'files' and ok: self.check_main()
        self.refresh()
        # A success says so for a while; a failure stays until closed.
        if ok:
            serial = task['serial']
            self.root.after(12000, lambda: self.task is task and task['serial'] == serial and not
                            self.log_frame.winfo_ismapped() and self.close_task_panel())

    def task_clicked(self):
        if self.busy():
            self.task['cancel'].touch()
            self.task_detail.configure(text='Stopping…')
            self.task_button.configure(state='disabled')
        else:
            self.close_task_panel()

    def close_task_panel(self):
        if self.busy(): return
        self.task = None
        self.task_panel.pack_forget()

    def open_task_log(self):
        if self.task: opened(self.task['log'])

    def open_logs(self):
        folder = Path(self.settings.values['data']) / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        opened(folder)

    def open_latest_log(self):
        folder = Path(self.settings.values['data']) / 'logs'
        logs = list(folder.glob('*.log')) if folder.is_dir() else []
        if not logs: return self.error('No task logs yet. Set up the game or add a character first.')
        opened(max(logs, key=lambda path: path.stat().st_mtime))

    def pump(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == 'line': self.task_line(payload)
                elif kind == 'done':
                    self.task_done(payload)
                    if not self.root.winfo_exists(): return
                elif kind == 'status': self.status_known(payload)
                elif kind == 'owned': self.owned_known(payload)
                elif kind == 'release': self.release_known(payload)
                elif kind == 'main': self.main_known(payload)
        except queue.Empty:
            pass
        except Exception:
            try:
                if not self.root.winfo_exists(): return
            except tk.TclError:
                return              # (the window is gone: an update opened the new launcher)
            # (Said, and the events after it still shown: a task's end among them, else its panel waits for good.)
            self.callback_failed(*sys.exc_info())
        self.root.after(100, self.pump)

    def error(self, error):
        messagebox.showerror(NAME, str(error), parent=self.root)

    def close(self):
        if self.busy() and not self.task.get('opening'):    # (the new launcher is opening: this one can go)
            messagebox.showinfo('Task running', 'Wait for this task to finish, or cancel it first. The launcher stays '
                                'open so that cleaning up and logging can finish.', parent=self.root)
        else:
            self.root.destroy()

    # ---------------------------------------------------------------- Settings

    def open_settings(self):
        self.stop_picking()
        self.load_display()
        self.load_keys()
        self.main.pack_forget()
        self.settings_page.pack(fill='both', expand=True)
        self.title.configure(text='Settings')
        self.back_button.pack(side='left', padx=(self.look.px(8), 0))
        self.refresh_button.pack_forget()
        self.update_button.pack_forget()
        self.page = 'settings'

    def close_settings(self):
        self.stop_picking()
        self.settings_page.pack_forget()
        self.main.pack(fill='both', expand=True)
        self.title.configure(text=NAME)
        self.back_button.pack_forget()
        self.refresh_button.pack(side='right', padx=(0, self.look.px(8)))
        if self.exe: self.update_button.pack(side='right', padx=(0, self.look.px(2)))
        self.page = 'main'

    def build_settings(self):
        L, px = self.look, self.look.px
        column = self.settings_page.column
        def section(title, text, top=0):
            L.label(column, title, 'section').pack(fill='x', padx=px(4), pady=(top, px(4)))
            L.label(column, text, 'dim', wrap=True).pack(fill='x', padx=px(4), pady=(0, px(12)))
            card = L.box(column, 'Card')
            card.configure(padding=px(18))
            card.pack(fill='x')
            return card
        card = section('Game', 'The game uses these when it starts.')
        rows = L.box(card, 'List')
        rows.configure(padding=px(4))
        rows.pack(fill='x')
        self.display_vars = {key: tk.BooleanVar(value=default) for key, default in
                             (('fullscreen', True), ('interpolation', True), ('input_delay', False))}
        self.resolution = tk.StringVar(value=RESOLUTIONS[0][1])
        def row(title, text, control, first=False):
            if not first: tk.Frame(rows, bg=look.ROW_LINE, height=1).pack(fill='x')
            line = L.frame(rows)
            line.pack(fill='x', padx=(px(12), px(10)), pady=px(10))
            widget = control(line)
            widget.pack(side='right', padx=(px(16), 0))
            texts = L.frame(line)
            texts.pack(side='left', fill='x', expand=True)
            L.label(texts, title).pack(fill='x')
            L.label(texts, text, 'small', wrap=True).pack(fill='x', pady=(px(2), 0))
            return widget
        switch = lambda key: lambda parent: ttk.Checkbutton(parent, style='Switch.TCheckbutton', takefocus=True,
                                                            variable=self.display_vars[key], command=self.save_display)
        row('Fullscreen', 'Start the game fullscreen. F11 switches it in the game.', switch('fullscreen'), True)
        self.resolution_text = row('Resolution', 'The size the game draws at; the picture is scaled to the window or the '
                                   'screen.', lambda parent: self.resolution_box(parent))
        row('120 fps', 'A frame between each two of the game\'s 60 every second: smoother motion on displays of 100 Hz '
            'and more.', switch('interpolation'))
        row('Input delay', 'Two frames between a button press and the game acting on it, as on the Wii U. Practice\'s '
            'own Input Delay works either way.', switch('input_delay'))
        row('Performance', '1280 × 720 without 120 fps: for a slower graphics card.',
            lambda parent: L.button(parent, 'Use', self.performance_preset))
        self.display_note = L.label(card, '', 'small', wrap=True)
        card = section('Keyboard', 'Keys by position on the keyboard; the game uses them as the Wii U GamePad\'s buttons. '
                       'Changes apply at once, also while the game runs.', px(28))
        self.build_keys(card)
        card = section('Folders', 'Where the launcher finds your game and keeps its tools, characters and saves '
                       '(Windows).', px(28))
        self.build_folders(card)

    def resolution_box(self, parent):
        box = ttk.Combobox(parent, state='readonly', values=[label for _, label in RESOLUTIONS],
                           textvariable=self.resolution, width=12, font=self.look.fonts['normal'])
        box.bind('<<ComboboxSelected>>', lambda e: (box.selection_clear(), self.save_display()))
        return box

    def display_file(self):
        data = Path(self.settings.values['data'])
        if data.name != 'TTT2Ultimate':
            raise ValueError('The data folder must end in TTT2Ultimate so the game and launcher share settings.')
        return data / 'config' / 'display.ini'

    def load_display(self):
        try:
            file = self.display_file()
            if file.exists():
                for line in file.read_text(encoding='utf-8-sig').splitlines():
                    key, separator, value = line.split('#', 1)[0].partition('=')
                    key, value = key.strip(), value.strip()
                    if separator and key in self.display_vars: self.display_vars[key].set(value in ('yes', 'true', '1'))
                    if separator and key == 'resolution':
                        self.resolution.set(dict(RESOLUTIONS).get(value, RESOLUTIONS[0][1]))
        except (OSError, ValueError) as error:
            self.display_note.configure(text=str(error), fg=BAD)
            self.display_note.pack(fill='x', pady=(self.look.px(10), 0))

    def save_display(self):
        try:
            file = self.display_file()
            file.parent.mkdir(parents=True, exist_ok=True)
            value = next((v for v, label in RESOLUTIONS if label == self.resolution.get()), 'auto')
            text = '# Written by Ultimate Launcher for Windows\n' + ''.join(
                key + ' = ' + ('yes' if var.get() else 'no') + '\n' for key, var in self.display_vars.items())
            part = file.with_name('display.ini.part')
            part.write_text(text + 'resolution = ' + value + '\n', encoding='utf-8')
            part.replace(file)
            self.display_note.pack_forget()
        except (OSError, ValueError) as error:
            self.display_note.configure(text='Cannot save: %s' % error, fg=BAD)
            self.display_note.pack(fill='x', pady=(self.look.px(10), 0))

    def performance_preset(self):
        self.resolution.set('1280 × 720')
        self.display_vars['interpolation'].set(False)
        self.save_display()

    # -- the keyboard

    def keyboard_file(self):
        return self.display_file().with_name('keyboard.ini')

    def build_keys(self, card):
        L, px = self.look, self.look.px
        grid = L.frame(card)
        grid.pack(fill='x')
        grid.columnconfigure(0, weight=1, uniform='keys')
        grid.columnconfigure(1, weight=1, uniform='keys')
        self.keycaps = []
        groups = []
        for index, (id_, group, name, full, _) in enumerate(keys.inputs()):
            if not groups or groups[-1][0] != group: groups.append((group, []))
            groups[-1][1].append((index, id_, name))
        for n, (group, members) in enumerate(groups):
            cell = L.frame(grid)
            cell.grid(row=n // 2, column=n % 2, sticky='new', padx=(0 if n % 2 == 0 else px(8), px(8) if n % 2 == 0 else 0),
                      pady=(0, px(14)))
            L.label(cell, group, 'small_bold', fg=DIM).pack(fill='x', padx=px(4), pady=(0, px(6)))
            rows = L.box(cell, 'List')
            rows.configure(padding=px(3))
            rows.pack(fill='x')
            for i, (index, id_, name) in enumerate(members):
                if i: tk.Frame(rows, bg=look.ROW_LINE, height=1).pack(fill='x')
                line = L.frame(rows)
                line.pack(fill='x', padx=(px(8), px(5)), pady=px(5))
                shoulder = id_ in ('l', 'r', 'zl', 'zr')
                tk.Label(line, image=L.input_icon(id_), bg=LIST, text=id_.upper() if shoulder else '', compound='center',
                         fg='#202020', font=L.fonts['small_bold' if len(id_) < 2 else 'small_bold']).pack(side='left')
                L.label(line, name).pack(side='left', padx=(px(10), 0))
                cap = ttk.Button(line, style='Keycap.TButton', takefocus=True,
                                 command=lambda i=index: self.pick_key(i))
                cap.pack(side='right')
                cap.bind('<KeyPress>', lambda e, i=index: self.key_pressed(e, i))
                cap.bind('<FocusOut>', lambda e, i=index: self.stop_picking() if self.picking == i else None)
                self.keycaps.append(cap)
        buttons = L.frame(card)
        buttons.pack(fill='x')
        L.button(buttons, 'Restore Defaults', self.reset_keys).pack(side='left')
        L.button(buttons, 'Open keyboard.ini', self.edit_keyboard_file, 'flat').pack(side='left', padx=(px(8), 0))
        self.key_note = L.label(card, '', 'small', wrap=True)

    def load_keys(self):
        try:
            self.keymap, notes = keys.Keymap.load(self.keyboard_file())
        except ValueError as error:
            self.keymap, notes = keys.Keymap(), [str(error)]
        self.show_keys()
        self.say_keys('keyboard.ini: ' + '; '.join(notes) if notes else '')

    def show_keys(self):
        for index, cap in enumerate(self.keycaps):
            if index == self.picking:
                cap.configure(text='Press a key…')
                cap.state(['selected'])
            else:
                cap.configure(text=keys.label(self.keymap.keys[index]))
                cap.state(['!selected'])

    def say_keys(self, text, colour=DIM):
        if text:
            self.key_note.configure(text=text, fg=colour)
            self.key_note.pack(fill='x', pady=(self.look.px(10), 0))
        else:
            self.key_note.pack_forget()

    def pick_key(self, index):
        self.picking = None if self.picking == index else index
        self.show_keys()
        if self.picking is not None:
            self.keycaps[index].focus_set()
            self.say_keys('Press the key for %s, or Esc to keep %s.' % (keys.inputs()[index][3],
                                                                         keys.label(self.keymap.keys[index])))

    def stop_picking(self):
        if self.picking is None: return
        self.picking = None
        self.show_keys()
        self.say_keys('')

    def key_pressed(self, event, index):
        if self.picking != index: return None
        usage = keys.usage_of(event)
        if usage == keys.ESCAPE:
            self.stop_picking()
            return 'break'
        if not usage:
            self.say_keys('That key cannot be given to a button.', WARN)
            return 'break'
        ok, swapped, why = self.keymap.bind(index, usage)
        if not ok:
            self.say_keys(why + ': choose another key.', WARN)
            return 'break'
        try:
            self.keymap.save(self.keyboard_file())
        except (OSError, ValueError) as error:
            self.picking = None
            self.show_keys()
            self.say_keys('Cannot save the keys: %s' % error, BAD)
            return 'break'
        self.picking = None
        self.show_keys()
        name = keys.inputs()[index][3]
        if swapped >= 0:
            self.say_keys('%s is %s\'s now; %s has %s instead.' % (keys.label(usage), name, keys.inputs()[swapped][3],
                                                                    keys.label(self.keymap.keys[swapped])), NOTICE_ICON)
        else:
            self.say_keys('')
        return 'break'

    def reset_keys(self):
        self.stop_picking()
        self.keymap = keys.Keymap()
        try:
            self.keymap.save(self.keyboard_file())
        except (OSError, ValueError) as error:
            return self.say_keys('Cannot save the keys: %s' % error, BAD)
        self.show_keys()
        self.say_keys('')

    def edit_keyboard_file(self):
        try:
            file = self.keyboard_file()
            if not file.exists(): self.keymap.save(file)
            opened(file)
        except (OSError, ValueError) as error:
            self.error(error)

    # -- the folders (Windows)

    def build_folders(self, card):
        L, px = self.look, self.look.px
        self.folder_vars = {}
        rows = L.box(card, 'List')
        rows.configure(padding=px(4))
        rows.pack(fill='x')
        for i, (key, title, text, folder) in enumerate(FOLDERS):
            if i: tk.Frame(rows, bg=look.ROW_LINE, height=1).pack(fill='x')
            line = L.frame(rows)
            line.pack(fill='x', padx=(px(12), px(10)), pady=px(9))
            L.label(line, title).pack(fill='x')
            L.label(line, text, 'small', wrap=True).pack(fill='x', pady=(px(1), px(6)))
            field = L.frame(line)
            field.pack(fill='x')
            var = self.folder_vars[key] = tk.StringVar(value=self.settings.values.get(key, ''))
            def browse(var=var, folder=folder):
                value = filedialog.askdirectory(parent=self.root) if folder else filedialog.askopenfilename(
                    parent=self.root, filetypes=[('Wii U archive', '*.wua'), ('All files', '*.*')])
                if value: var.set(value)
            L.button(field, 'Browse…', browse).pack(side='right', padx=(px(8), 0))
            ttk.Entry(field, textvariable=var, font=L.fonts['mono']).pack(side='left', fill='x', expand=True)
        buttons = L.frame(card)
        buttons.pack(fill='x', pady=(px(14), 0))
        L.button(buttons, 'Save Folders', self.save_folders, 'suggested').pack(side='left')
        self.folders_note = L.label(buttons, '', 'small')
        self.folders_note.pack(side='left', padx=(px(12), 0))

    def save_folders(self):
        try:
            if self.busy(): raise ValueError('Wait for the task to end before changing folders.')
            self.settings.values.update({k: v.get().strip() for k, v in self.folder_vars.items()})
            self.settings.save()
            self.folders_note.configure(text='Saved.', fg=OK)
            self.root.after(4000, lambda: self.folders_note.configure(text=''))
            self.refresh()
        except Exception as error:
            self.error(error)

    # ---------------------------------------------------------------- tests

    def smoke_test(self, tries=0):
        """--ui-smoke-test FILE: the window's parts as the user sees them, written to FILE (CI)."""
        if self.status is None and not self.status_error and tries < 120:
            return self.root.after(500, lambda: self.smoke_test(tries + 1))
        try:
            assert self.status is not None, 'no importer status: ' + self.status_error
            self.dlc_open = True
            self.show_characters()
            self.root.update()
            rows = sum(1 for w in walk(self.characters_card) if isinstance(w, tk.Label) and w.cget('text') in
                       {f['display'] for f in (self.status or {}).get('fighters', [])})
            self.open_settings()
            self.root.update()
            switches = sum(1 for w in walk(self.settings_page.column) if isinstance(w, ttk.Checkbutton))
            caps = [c.cget('text') for c in self.keycaps]
            self.close_settings()
            assert rows == len(self.status['fighters']) > 0, (rows, len(self.status['fighters']))
            assert switches == 3 and len(caps) == 19 and all(caps), (switches, caps)
            self.args.ui_smoke_test.write_text(json.dumps(dict(
                window=self.root.title(), fighters=rows, pages=2, keys=caps, paths=self.settings.values,
                ), indent=2), encoding='utf-8')
        except Exception as error:
            self.smoke_error = error
        finally:
            self.root.destroy()


def walk(widget):
    yield widget
    for child in widget.winfo_children(): yield from walk(child)
