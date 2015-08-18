import gevent
from gevent.server import StreamServer
from gevent.pool import Pool

from pymc.network.connection import ConnectionHandler


def handle(sock, addr):
    g = gevent.spawn(ConnectionHandler().greenlet_run, sock)
    g.join()


def start(addr, port):
    pool = Pool()

    listener = StreamServer((addr, port), handle, spawn=pool)
    try:
        listener.serve_forever()
    except KeyboardInterrupt:
        listener.stop()