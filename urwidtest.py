import urwid
from urwid import *


def _handle_global_input(key):
    if key in ('q', 'Q'):
        raise urwid.ExitMainLoop()

class SmallButton(Button):
    button_left = urwid.Text("[")
    button_right = urwid.Text("]")

class Item(WidgetWrap):
    def __init__(self):
        self.edit = Edit("item: ")
        root = AttrMap(Columns([self.edit,
                                (5, SmallButton("X", self.update_caption)),
                               ]),
                       'default', 'focused')
        super().__init__(root)

    def update_caption(self, *args):
        self.edit.set_caption("foo")



items = [Item() for i in range(8)]
# walker = SimpleFocusListWalker(items)
listbox = ListBox(items)

palette = [
    ('divider', '', '', '', '#666', ''),
    ('focused', 'yellow', ''),
    ('default', '', ''),
]

frame = Frame(header=Pile([Text("foo"), AttrMap(Divider("─"), 'divider')]),
              body=Columns([listbox, listbox], dividechars=1),
              )


loop = urwid.MainLoop(frame, palette, unhandled_input=_handle_global_input)
loop.screen.set_terminal_properties(colors=256)
loop.run()
