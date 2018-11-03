# -*- coding: utf-8 -*-

import logging

import urwid
from urwid import *   # TODO

from .util import CallbackLogHandler

log = logging.getLogger(__name__)


palette = [
    ('divider', '', '', '', '#666', ''),
    ('focused screen', 'bold', ''),
    ('path', 'underline,brown', ''),
    ('focused path', 'underline,bold,yellow', '')
]


class ListBoxWithTabSupport(ListBox):
    """urwid *still* doesn't support tab key for cycling focus"""

    def keypress(self, size, key):
        if key == 'tab':
            try:
                self.set_focus(self.focus_position + 1, coming_from='above')
            except IndexError:
                self.set_focus(0, coming_from='below')
        else:
            return super().keypress(size, key)


class PathWidget(Text):

    def __init__(self):
        super().__init__("", wrap='clip')

    def selectable(self):
        return True

    def keypress(self, size, key):
        return key

    def render(self, size, focus=False):
        self.set_text(('focused path' if focus else 'path', self.text))
        return super().render(size, focus)


class ScreenWidget(WidgetWrap):

    _info_template = "[ {rating} | {purity} ] {format} {width:d}×{height:d}"

    def __init__(self, screen):
        self._screen = screen
        screen.subscribe(self)
        self._left_border = Text(" ")
        self._playpause = Text("⏸")
        self._info = Text(self._info_template)
        self._offsets = Text("")
        info = Columns([
            (1, self._left_border),
            (2, self._playpause),
            ('pack', self._info),
            ('pack', self._offsets),
        ])
        self._path = PathWidget()
        self._root = AttrMap(Pile([
            info,
            Columns([(1, self._left_border), self._path]),
        ]), None, 'focused screen')
        super().__init__(self._root)
        self.notify()

    def render(self, size, focus=False):
        self._left_border.set_text("│" if focus else " ")
        return self._root.render(size, focus)

    def selectable(self):
        return True

    def notify(self, *_):
        wp = self._screen.wallpaper
        self._info.set_text(self._info_template.format(
            rating=("☆" if wp.rating == 0 else "★·" + str(wp.rating)),
            purity=("♡" if wp.purity == 0 else "♥·" + str(wp.purity)),
            format=wp.format,
            width=wp.width,
            height=wp.height,
        ))
        if wp.x_offset or wp.y_offset or wp.scale != 1:
            self._offsets.set_text(" ({:+},{:+},{:.0%})".format(
                wp.x_offset, wp.y_offset, self._screen.wallpaper_scale
            ))
        else:
            self._offsets.set_text("")
        self._path.set_text(wp.path)

    def keypress(self, size, key):
        if key == 'a':
            self._screen.next_wallpaper()
        elif key == 'q':
            self._screen.prev_wallpaper()
        elif key == 's':
            self._screen.wallpaper.rating -= 1
        elif key == 'w':
            self._screen.wallpaper.rating += 1
        elif key == 'd':
            self._screen.wallpaper.purity -= 1
        elif key == 'e':
            self._screen.wallpaper.purity += 1
        elif key == 'k':
            self._screen.wallpaper.y_offset += 10
        elif key == 'j':
            self._screen.wallpaper.y_offset -= 10
        elif key == 'h':
            self._screen.wallpaper.x_offset += 10
        elif key == 'l':
            self._screen.wallpaper.x_offset -= 10
        elif key == 'z':
            self._screen.wallpaper.scale += .05
        elif key == 'u':
            self._screen.wallpaper.scale -= .05
        elif key == '1':
            wp = self._screen.wallpaper
            wp.scale = 1 / max(self._screen.width / wp.width,
                               self._screen.height / wp.height)
        elif key == '0':
            wp = self._screen.wallpaper
            wp.scale = 1
            wp.x_offset = 0
            wp.y_offset = 0
        else:
            return super().keypress(size, key)

    def mouse_event(self, size, event, *_):
        if event == 'mouse release':
            self._screen.wallpaper.open()


class Ui:

    def __init__(self, screen_controller, wallpaper_controller):
        self._scrctrl = screen_controller
        self._wpctrl = wallpaper_controller
        self._layout()
        self._loop = urwid.MainLoop(self._root,
                                    palette=palette,
                                    unhandled_input=self._handle_global_input)
        self._loop.screen.set_terminal_properties(
            colors=256, bright_is_bold=False, has_underline=True)

        # make special key combinations available, see
        # https://github.com/urwid/urwid/issues/140
        self._loop.screen.tty_signal_keys(stop='undefined')


    def _layout(self):
        self._wallpaper_count = Text(str(len(self._wpctrl.wallpapers)))
        self._info = Text("")
        header = Pile([Columns([('pack', self._wallpaper_count),
                                ('pack', Text(" Wallpapers ⋮ ")),
                                self._info]),
                       AttrMap(Divider("─"), 'divider')])
        body = ListBoxWithTabSupport([ScreenWidget(screen)
                                      for screen in self._scrctrl.screens])
        self._root = Frame(header=header, body=body)


    def run_loop(self):
        self.log_handler = CallbackLogHandler(self.info)
        logging.getLogger(__package__).addHandler(self.log_handler)
        self._loop.run()
        logging.getLogger(__package__).removeHandler(self.log_handler)


    def info(self, message):
        self._info.set_text(message)


    def _handle_global_input(self, key):
        if key == 'esc':
            raise urwid.ExitMainLoop()
        elif key == 'ctrl s':
            self._wpctrl.save_updates()
        elif key == 'x':
            self._scrctrl.cycle_collections()
        else:
            log.info("unhandled key: '%s'", key)
