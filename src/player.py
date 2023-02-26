import socket
import subprocess
from time import sleep
from ytmusicapi import YTMusic
from threading import Thread

from globals import AUTH_HEADERS, IPC_SERVER_PATH, pause_cmd, play_cmd

class PlayerThread(Thread):

    def run(self):
        subprocess.Popen('notify-send ' + self.url, shell=True) #feedback

        # Start the player
        self.process = subprocess.Popen('mpv '+ self.url + ' --no-video --cache=no --input-ipc-server=' + IPC_SERVER_PATH, shell=True, stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Create a socket object
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        try:
            # Connect to the socket
            sleep(2)
            self.sock.connect(IPC_SERVER_PATH)
        except:
            print('Some error occured while connecting to IPC Socket!')

    def __init__(self, url):
        self.url = url
        super().__init__()

    def terminate(self):
        self.sock.close()
        self.process.terminate()

    def send_command(self, ipc_command_json):
        # Send the JSON IPC command to the socket
        self.sock.sendall(ipc_command_json.encode())

        # Receive a response from the socket
        return self.sock.recv(1024)

    def play(self):
        self.send_command(play_cmd)

    def pause(self):
        self.send_command(pause_cmd)

class Player:
    def __init__(self):

        self.playing = False

        # Initialise connection
        self.player = YTMusic(AUTH_HEADERS)

    def search(self, query, callback) -> None:
        if(query == ''):
            callback([])
            return

        results = self.player.search(query=query, filter='songs')
        callback(results)

    def start(self, url: str) -> None:
        # self.playback = Thread(target=self.play, args=url)
        self.playback = PlayerThread(url)
        self.playback.start()
        self.playing = True

    def stop(self) -> None:
        try:
            self.playback.terminate()
            self.playing = False
        except:
            pass

    def play(self):
        try:
            self.playback.play()
            self.playing = True
        except:
            pass

    def pause(self):
        try:
            self.playback.pause()
            self.playing = False
        except:
            pass

    def __del__(self):
        try:
            self.playback.terminate()
        except:
            pass

