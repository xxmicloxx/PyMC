import gevent
from gevent.server import StreamServer

from pymc.network.connection import ClientHandler


def handle(sock, addr):
    g = gevent.spawn(ClientHandler().greenlet_run, sock)
    g.join()


def start(addr, port):
    listener = StreamServer((addr, port), handle)
    listener.start()
    listener.serve_forever()
