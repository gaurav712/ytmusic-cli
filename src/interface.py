import urwid

from threading import Thread
from player import Player
from custom_list_box import CustomListBox
from globals import searching

# to render the main UI
class Interface:
    def item_chosen(self, _, choice) -> None:
        self.now_playing.set_text(choice['title'])
        self.player.stop()
        self.player.start('https://music.youtube.com/watch?v=' + choice['videoId'])

    def handle_keypress(self, key) -> None:
        global searching

        # trim the last char if it's backspace
        if key == 'backspace':
            self.status_text = self.status_text[:-1]
            self.status.set_text(self.status_text)
        elif searching:
            if key == 'enter':
                self.handle_search()
                return
            self.status_text += key
            self.status.set_text(self.status_text)
        elif key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        elif key == '/':
            searching = True
            self.status_text = '/'
            self.status.set_text(self.status_text)
        elif key == ' ':
            self.play_pause_toggle()

    # To serve 'searching' state to the 'custom_list_box'
    def is_searching(self):
        global searching
        return searching

    def play_pause_toggle(self):
        if self.player.playing:
            self.player.pause()
        else:
            self.player.play()

    def handle_search(self) -> None:
        self.status.set_text('Searching for: ' + self.status_text[1:])

        # search async
        search_thread = Thread(target=self.player.search, args=(self.status_text[1:], self.search_thread_callback))
        search_thread.start()

    def search_thread_callback(self, search_results):
        global searching
        # print(search_results[0]['title'])

        self.listbox._set_body(urwid.SimpleFocusListWalker([urwid.Button(s['title'] + ' - ' + s['artists'][0]['name'], on_press=self.item_chosen, user_data=s) for s in search_results]))
        self.mainloop.draw_screen()
        searching = False

    def __init__(self) -> None:
        # Initialise the UI
        self.status_text = u''

        self.header = urwid.Text(u'Nothing to show')
        self.now_playing = urwid.Text([u'Not Playing'])
        self.status = urwid.Text(u'')
        self.footer = urwid.Pile([self.now_playing, self.status])
        self.listbox = CustomListBox(self.handle_keypress, self.is_searching, [])
        self.frame = urwid.Frame(header=self.header, body=self.listbox, footer=self.footer)
        top = urwid.Padding(self.frame, left=2, right=2)

        # Initialise the player
        self.player = Player()

        self.mainloop = urwid.MainLoop(top, unhandled_input=self.handle_keypress)
        self.mainloop.run()

