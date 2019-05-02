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
    ('path', 'underline,dark cyan', '', '', 'underline,#6dd', ''),
    ('focused path', 'underline,bold,light cyan', '', '', 'underline,bold,#0ff', ''),
    ('warning', 'bold,light red', '', '', 'bold,#f60', '')
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
            self._root.focus_position = 1
        else:
            self._content = Text(self._content.get_edit_text())
            self._update()

    def __init__(self, text):
        self._editable = False
        self._content = Text(text)
        self._root = Columns(())
        self._content_options = self._root.options('pack')
        self._left = Text("("), self._root.options('given', 1)
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

    _info_template = ("{collection_size:>2g}"
                      " [ {rating} | {purity} ]"
                      " {format} {width:d}×{height:d}")

    def __init__(self, screen, screen_controller):
        self._screen = screen
        self._scrctrl = screen_controller
        self._left_border = Text(" ")
        # self._playpause = Text("⏸")
        self._info = Text(self._info_template)
        self._scale = Text("")
        self._transformations = Parenthesis("")
        self._tags = Parenthesis("")
        self._top = Columns([
            (1, self._left_border),
            # (2, self._playpause),
            ('pack', self._info),
            ('pack', self._scale),
            ('pack', self._transformations),
            ('pack', self._tags),
        ], dividechars=1)
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
        ))
        self._scale.set_text((
            'warning' if self._screen.wallpaper_scale > 1 else None,
            f"{self._screen.wallpaper_scale:.0%}",
        ))
        trafo = wp.transformation
        trafo_strings = []
        if trafo.x_offset or trafo.y_offset:
            trafo_strings.append("{:+},{:+}".format(trafo.x_offset, trafo.y_offset))
        if trafo.zoom != 1:
            trafo_strings.append("{:.0%}".format(trafo.zoom))
        if trafo.rotate:
            trafo_strings.append(str(trafo.rotate) + "°")
        if trafo.horizontal:
            trafo_strings.append("↔")
        if trafo.vertical:
            trafo_strings.append("↕")
        self._transformations.set_text(",".join(trafo_strings))
        self._tags.set_text(",".join(sorted(wp.tags)))
        self._path.set_text(wp.path)

    def keypress(self, size, key):
        log.debug("processing keypress '%s'", key)
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
        elif key == 'z': wp.zoom_by(.05)
        elif key == 'Z': wp.zoom_by(.2)
        elif key == 'u': wp.zoom_by(-.05)
        elif key == 'U': wp.zoom_by(-.2)
        elif key == 'r': wp.rotate_by(+90)
        elif key == 'R': wp.rotate_by(-90)
        elif key == 'f': wp.flip_horizontal()
        elif key == 'F': wp.flip_vertical()
        elif key == 'h' or key == 'left':
            wp.shift(x=10)
        elif key == 'H' or key == 'shift left':
            wp.shift(x=100)
        elif key == 'l' or key == 'right':
            wp.shift(x=-10)
        elif key == 'L' or key == 'shift right':
            wp.shift(x=-100)
        elif key == 'k' or key == 'up':
            wp.shift(y=10)
        elif key == 'K' or key == 'shift up':
            wp.shift(y=100)
        elif key == 'j' or key == 'down':
            wp.shift(y=-10)
        elif key == 'J' or key == 'shift down':
            wp.shift(y=-100)
        elif key == '1':
            # 100% zoom
            wp.zoom_to(min(wp.width / self._screen.width,
                           wp.height / self._screen.height))
        elif key == '!':
            # zoom to fit
            w_rel = self._screen.width / wp.transformed_width
            h_rel = self._screen.height / wp.transformed_height
            wp.zoom_to(min(w_rel, h_rel) / max(w_rel, h_rel))
        elif key == '0':
            # zoom to fill (default)
            wp.clear_transformation()
        elif key == 't':
            if wp.tags:
                self._tags.text += ","
            self._tags.editable = True
            # make sure to adjust when changing the layout:
            self._top.focus_position = 4
            return
        elif key == 'enter' and self._tags.editable:
            self._tags.editable = False
            wp.set_tags(self._tags.text)
        elif key == 'esc' and self._tags.editable:
            self._tags.editable = False
            self._tags.text = ",".join(wp.tags)
        else:
            return key
        self.update()
        self._scrctrl.display_wallpapers()

    def mouse_event(self, size, event, button, *_):
        if event == 'mouse release':
            self._screen.wallpaper.open()
        elif event == 'mouse press' and button == 4:
            self._screen.wallpapers.prev()
            self.update()
            self._scrctrl.display_wallpapers()
        elif event == 'mouse press' and button == 5:
            self._screen.wallpapers.next()
            self.update()
            self._scrctrl.display_wallpapers()



class Ui:

    def __init__(self, screen_controller, wallpaper_controller):
        self._scrctrl = screen_controller
        self._wpctrl = wallpaper_controller
        self._layout()

        self._reading_command = False

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
        self._head = Columns([('pack', self._wallpaper_count),
                              (10, Text("Wallpapers")),
                              self._info],
                             dividechars=1)
        header = Pile([self._head, AttrMap(Divider("─"), 'divider')])

        self._screens = [ScreenWidget(screen, self._scrctrl)
                         for screen in self._scrctrl.screens]
        body = ListBoxWithTabSupport(self._screens)

        self._root = Frame(header=header, body=body)


    def run_loop(self):
        self._log_handler = CallbackLogHandler(self.info)
        logging.getLogger(__package__).addHandler(self._log_handler)
        self._loop.run()
        logging.getLogger(__package__).removeHandler(self._log_handler)


    def info(self, message):
        self._info.set_text("⋮ " + str(message))

    def _start_reading_command(self):
        self._reading_command = True
        self._info = Edit(caption="_⟩ ", wrap='clip')
        self._head.contents[2] = (self._info, self._head.options('pack'))
        self._root.set_focus_path(("header", 0, 2))

    def _finish_reading_command(self):
        command = self._info.get_edit_text()
        self._info = Text("", wrap='clip')
        self._head.contents[2] = (self._info, self._head.options('pack'))
        self._root.focus_position = "body"
        self._reading_command = False
        return command

    def _handle_global_input(self, key):
        if self._reading_command:
            if key == 'esc':
                self._finish_reading_command()
            elif key == 'enter':
                command = self._finish_reading_command()
                log.info(f"Commands ({command}) are not implemented yet.")
            return

        if key == 'esc':
            raise ExitMainLoop()
        elif key == ':' or key == '-':
            self._start_reading_command()
        elif key == 'ctrl s':
            self._wpctrl.save_updates()
        elif key == 'x':
            self._scrctrl.cycle_collections()
        elif key in _shift_number_keys:
            current_screen_idx = self._root.focus.focus._screen.idx
            key_number = _shift_number_keys[key]
            self._scrctrl.move_wallpaper(current_screen_idx, key_number)
        else:
            log.debug("unhandled key: '%s'", key)
            return
        for screen_widget in self._screens:
            screen_widget.update()
        return True
