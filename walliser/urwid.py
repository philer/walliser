# -*- coding: utf-8 -*-

import logging

import urwid
from urwid import (MainLoop, ExitMainLoop, WidgetWrap,
                   Frame, Pile, Columns, ListBox, Text, Edit, Divider, AttrMap)

from .util import CallbackLogHandler

__all__ = ('Ui')

log = logging.getLogger(__name__)

palette = [
    ('divider', '', '', '', '#666', ''),
    ('focused screen', 'bold', ''),
    ('path', 'underline,brown', ''),
    ('focused path', 'underline,bold,yellow', ''),
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

class Parenthesis(WidgetWrap):

    def get_text(self):
        if self._editable:
            return self._content.get_edit_text()
        return self._content.get_text()[0]

    def set_text(self, text):
        try:
            self._content.set_text(text)
        except urwid.widget.EditError:
            self._content.set_edit_text(text)
        self._update()

    text = property(get_text, set_text)

    @property
    def editable(self):
        return self._editable

    @editable.setter
    def editable(self, yes):
        if self._editable == yes:
            return
        self._editable = yes
        if yes:
            self._content = Edit(caption="tags:", edit_text=self._content.get_text()[0])
            self._update()
            # self._content.set_edit_pos(1000000)
            self._root.focus_position = 1
        else:
            self._content = Text(self._content.get_edit_text())
            self._update()

    def __init__(self, text):
        self._editable = False
        self._content = Text(text)
        self._root = Columns(())
        self._content_options = self._root.options('pack')
        self._left = Text(" ("), self._root.options('given', 2)
        self._right = Text(")"), self._root.options('given', 1)
        self._update()
        super().__init__(self._root)

    def selectable(self):
        return self._editable

    def pack(self, size=None, focus=False):
        width, _ = self._content.pack()
        return (2 + width + 1, 1)

    def keypress(self, size, key):
        if self._editable:
            if key == 'enter' or key == 'esc':
                return key
            else:
                # make sure unhandled navigation doesn't leak
                self._content.keypress(size, key)
                return
        return key

    def _visible(self):
        return self._editable or bool(self.text)

    def _update(self):
        if self._visible():
            self._root.contents = [self._left,
                                   (self._content, self._content_options),
                                   self._right]
        else:
            self._root.contents.clear()


class ScreenWidget(WidgetWrap):

    _info_template = ("{collection_size:>4g}"
                      " [ {rating} | {purity} ]"
                      " {format} {width:d}×{height:d} {scale:.0%}")

    def __init__(self, screen, screen_controller):
        self._screen = screen
        self._scrctrl = screen_controller
        self._left_border = Text(" ")
        # self._playpause = Text("⏸")
        self._info = Text(self._info_template)
        self._transformations = Parenthesis("")
        self._tags = Parenthesis("")
        self._top = Columns([
            (1, self._left_border),
            # (2, self._playpause),
            ('pack', self._info),
            ('pack', self._transformations),
            ('pack', self._tags),
        ])
        self._path = PathWidget()
        self._root = AttrMap(Pile([
            self._top,
            Columns([(1, self._left_border), self._path]),
        ]), None, 'focused screen')
        super().__init__(self._root)
        self.update()

    def selectable(self):
        return True

    def render(self, size, focus=False):
        # maybe this is better:
        # https://groups.google.com/a/excess.org/forum/#!topic/urwid/3Si0ZRKkFaw
        self._left_border.set_text("│" if focus else " ")
        return self._root.render(size, focus)

    def update(self, *_):
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
        trafos = []
        if wp.x_offset or wp.y_offset:
            trafos.append("{:+},{:+}".format(wp.x_offset, wp.y_offset))
        if wp.zoom != 1:
            trafos.append("{:.0%}".format(wp.zoom))
        if wp.transformations[2]:
            trafos.append(str(wp.transformations[2]) + "°")
        if wp.transformations[0]:
            trafos.append("↔")
        if wp.transformations[1]:
            trafos.append("↕")
        self._transformations.set_text(",".join(trafos))
        self._tags.set_text(",".join(wp.tags))
        self._path.set_text(wp.path)

    def keypress(self, size, key):
        if self._top.focus.selectable():
            child_result = self._top.keypress(size, key)
            if child_result is None:
                return

        wp = self._screen.wallpaper
        if key == 'delete': self._screen.wallpapers.remove_current()
        elif key == 'o': wp.open()
        elif key == 'a': self._screen.wallpapers.next()
        elif key == 'q': self._screen.wallpapers.prev()
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
        elif key == 'f': wp.flip_horizontal()
        elif key == 'F': wp.flip_vertical()
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
            del wp.zoom
            del wp.x_offset
            del wp.y_offset
            del wp.transformations
        elif key == 't':
            if wp.tags:
                self._tags.text += ","
            self._tags.editable = True
            self._top.focus_position = 3
            return
        elif key == 'enter' and self._tags.editable:
            self._tags.editable = False
            wp.tags = self._tags.text
        elif key == 'esc' and self._tags.editable:
            self._tags.editable = False
            self._tags.text = ",".join(wp.tags)
        else:
            return key
        self.update()
        self._scrctrl.display_wallpapers()

    def mouse_event(self, size, event, *_):
        if event == 'mouse release':
            self._screen.wallpaper.open()


class Ui:

    def __init__(self, screen_controller, wallpaper_controller):
        self._scrctrl = screen_controller
        self._wpctrl = wallpaper_controller
        self._layout()
        self._loop = MainLoop(widget=self._root,
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
        self._screens = [ScreenWidget(screen, self._scrctrl)
                         for screen in self._scrctrl.screens]
        header = Pile([Columns([('pack', self._wallpaper_count),
                                ('pack', Text(" Wallpapers ⋮ ")),
                                self._info]),
                       AttrMap(Divider("─"), 'divider')])
        self._root = Frame(header=header,
                           body=ListBoxWithTabSupport(self._screens))


    def run_loop(self):
        self._log_handler = CallbackLogHandler(self.info)
        logging.getLogger(__package__).addHandler(self._log_handler)
        self._loop.run()
        logging.getLogger(__package__).removeHandler(self._log_handler)


    def info(self, message):
        self._info.set_text(message)


    def _handle_global_input(self, key):
        if key == 'esc':
            raise ExitMainLoop()
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
            return
        for screen_widget in self._screens:
            screen_widget.update()
