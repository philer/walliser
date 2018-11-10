# -*- coding: utf-8 -*-

import logging

import urwid
from urwid import *   # TODO

from .util import CallbackLogHandler

__all__ = ('Ui')

log = logging.getLogger(__name__)

palette = [
    ('divider', '', '', '', '#666', ''),
    ('focused screen', 'bold', ''),
    ('path', 'underline,brown', ''),
    ('focused path', 'underline,bold,yellow', '')
]

# this is dumb: 'shift 1', 'shift 2', ...
_shift_number_keys = dict((key, number) for number, key
                          in enumerate('!"§$%&/()='))

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

    _info_template = ("{collection_size:>4g}"
                      " [ {rating} | {purity} ]"
                      " {format} {width:d}×{height:d} {scale:.0%}")

    def __init__(self, screen):
        self._screen = screen
        screen.subscribe(self)
        self._left_border = Text(" ")
        # self._playpause = Text("⏸")
        self._info = Text(self._info_template)
        self._transformations = Text("")
        info = Columns([
            (1, self._left_border),
            # (2, self._playpause),
            ('pack', self._info),
            ('pack', self._transformations),
        ])
        self._path = PathWidget()
        self._root = AttrMap(Pile([
            info,
            Columns([(1, self._left_border), self._path]),
        ]), None, 'focused screen')
        super().__init__(self._root)
        self.notify()

    def render(self, size, focus=False):
        # maybe this is better:
        # https://groups.google.com/a/excess.org/forum/#!topic/urwid/3Si0ZRKkFaw
        self._left_border.set_text("│" if focus else " ")
        return self._root.render(size, focus)

    def selectable(self):
        return True

    def notify(self, *_):
        wp = self._screen.wallpaper
        self._info.set_text(self._info_template.format(
            collection_size=len(self._screen.wallpapers),
            rating=("☆" if wp.rating == 0 else "★·" + str(wp.rating)),
            purity=("♡" if wp.purity == 0 else "♥·" + str(wp.purity)),
            format=wp.format,
            width=wp.width,
            height=wp.height,
            scale=self._screen.wallpaper_scale,
        ))
        parts = []
        if wp.x_offset or wp.y_offset:
            parts.append("{:+},{:+}".format(wp.x_offset, wp.y_offset))
        if wp.zoom != 1:
            parts.append("{:.0%}".format(wp.zoom))
        if wp.transformations[2]:
            parts.append(str(wp.transformations[2]) + "°")
        if wp.transformations[0]:
            parts.append("↔")
        if wp.transformations[1]:
            parts.append("↕")
        if parts:
            self._transformations.set_text(" (" + ",".join(parts) + ")")
        else:
            self._transformations.set_text("")
        self._path.set_text(wp.path)

    def keypress(self, size, key):
        wp = self._screen.wallpaper
        if key == 'delete': self._screen.remove_current_wallpaper()
        elif key == 'o': wp.open()
        elif key == 'a': self._screen.next_wallpaper()
        elif key == 'q': self._screen.prev_wallpaper()
        elif key == 's': wp.rating -= 1
        elif key == 'w': wp.rating += 1
        elif key == 'd': wp.purity += 1
        elif key == 'e': wp.purity -= 1
        elif key == 'z': wp.zoom += .05
        elif key == 'Z': wp.zoom += .2
        elif key == 'u': wp.zoom -= .05
        elif key == 'U': wp.zoom -= .2
        elif key == 'r': wp.rotate(+90)
        elif key == 'R': wp.rotate(-90)
        elif key == 'f': wp.flip_vertical()
        elif key == 'F': wp.flip_horizontal()
        elif key == 'h' or key == 'left':
            wp.x_offset += 10
        elif key == 'H' or key == 'shift left':
            wp.x_offset += 100
        elif key == 'l' or key == 'right':
            wp.x_offset -= 10
        elif key == 'L' or key == 'shift right':
            wp.x_offset -= 100
        elif key == 'k' or key == 'up':
            wp.y_offset += 10
        elif key == 'K' or key == 'shift up':
            wp.y_offset += 100
        elif key == 'j' or key == 'down':
            wp.y_offset -= 10
        elif key == 'J' or key == 'shift down':
            wp.y_offset -= 100
        elif key == '1':
            wp.zoom = 1 / max(self._screen.width / wp.width,
                              self._screen.height / wp.height)
        elif key == '0':
            wp = self._screen.wallpaper
            del wp.zoom
            del wp.x_offset
            del wp.y_offset
            del wp.transformations
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
        self._loop = urwid.MainLoop(widget=self._root,
                                    palette=palette,
                                    unhandled_input=self._handle_global_input)
        self._loop.screen.set_terminal_properties(
            colors=256, bright_is_bold=False, has_underline=True)

        # make special key combinations available, see
        # https://github.com/urwid/urwid/issues/140
        self._loop.screen.tty_signal_keys(stop='undefined')


    def _layout(self):
        self._wallpaper_count = Text(str(len(self._wpctrl.wallpapers)))
        self._info = Text("", wrap='clip')
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
        elif key in _shift_number_keys:
            current_screen_idx = self._root.focus.focus._screen.idx
            key_number = _shift_number_keys[key]
            self._scrctrl.move_wallpaper(current_screen_idx, key_number)
        else:
            log.info("unhandled key: '%s'", key)
