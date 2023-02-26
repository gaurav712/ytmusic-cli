# relative path to auth headers file
AUTH_HEADERS = '../headersauth.json'

# Socket to control mpv
IPC_SERVER_PATH = "/tmp/mpvsocket"

searching = False # flag to check if UI is in search mode

# IPC Commands
play_cmd = '{ "command": ["set_property", "pause", false] }\n'
pause_cmd = '{ "command": ["set_property", "pause", true] }\n'

# Keys to be handled by the list view
HANDLED_KEYS = ['k', 'j', 'enter']
