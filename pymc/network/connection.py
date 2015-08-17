import json
import uuid
import fastmc.auth
import fastmc.proto
import pprint
from pymc.util import event

ping_event = event.Event()

pre_connect_event = event.Event()

connect_event = event.Event()


class PreConnectEventData(event.Cancelable):
    def __init__(self, player_name):
        super(PreConnectEventData, self).__init__()
        self.player_name = player_name
        self.cancel_reason = None


class ConnectEventData(event.Cancelable):
    def __init__(self, player_name, player_uuid):
        super(ConnectEventData, self).__init__()
        self.player_name = player_name
        self.player_uuid = player_uuid
        self.cancel_reason = None


class PingEventData(object):
    def __init__(self):
        self.max_players = 1
        self.online_players = 0
        self.description = {"text": "A Minecraft Server"}


class ClientHandler(object):
    def __init__(self):
        self.sock = None
        self.reader = self.writer = None
        self.token = fastmc.auth.generate_challenge_token()
        self.server_id = fastmc.auth.generate_server_id()
        self.key = fastmc.auth.generate_key_pair()
        self.player_ign = None
        self.uuid = None

    def handle_pkt(self, pkt):
        print pkt
        print

        if self.reader.state == fastmc.proto.HANDSHAKE:
            if pkt.id == 0x00:
                self.reader.switch_state(pkt.state)
                self.writer.switch_state(pkt.state)
        elif self.reader.state == fastmc.proto.STATUS:
            if pkt.id == 0x00:
                data = PingEventData()
                ping_event(data)

                out_buf = fastmc.proto.WriteBuffer()
                self.writer.write(out_buf, 0x00, response={
                    "version": {
                        "name": self.reader.protocol.name,
                        "protocol": self.reader.protocol.version
                    },
                    "players": {
                        "max": data.max_players,
                        "online": data.online_players
                    },
                    "description": data.description
                })
                self.sock.send(out_buf)
            elif pkt.id == 0x01:
                out_buf = fastmc.proto.WriteBuffer()
                self.writer.write(out_buf, 0x01, time=pkt.time)
                self.sock.send(out_buf)
        elif self.reader.state == fastmc.proto.LOGIN:
            if pkt.id == 0x00:
                out_buf = fastmc.proto.WriteBuffer()

                self.player_ign = pkt.name

                event_data = PreConnectEventData(self.player_ign)
                pre_connect_event(event_data)

                if event_data.cancelled:
                    self.writer.write(out_buf, 0x00, reason=event_data.cancel_reason or {"text": "Event cancelled. "
                                                                                                 "Please supply a "
                                                                                                 "reason in the "
                                                                                                 "cancel_reason "
                                                                                                 "field."})
                else:
                    self.writer.write(out_buf, 0x01,
                                      server_id=self.server_id,
                                      public_key=fastmc.auth.encode_public_key(self.key),
                                      challenge_token=self.token)

                self.sock.send(out_buf)
            elif pkt.id == 0x01:
                decrypted_token = fastmc.auth.decrypt_with_private_key(pkt.response_token, self.key)

                if decrypted_token != self.token:
                    raise Exception("Token verification failed")

                shared_secret = fastmc.auth.decrypt_with_private_key(pkt.shared_secret, self.key)

                self.sock.set_cipher(fastmc.auth.generated_cipher(shared_secret),
                                     fastmc.auth.generated_cipher(shared_secret))

                server_hash = fastmc.auth.make_server_hash(
                    server_id=self.server_id,
                    shared_secret=shared_secret,
                    key=self.key
                )

                check = fastmc.auth.check_player(self.player_ign, server_hash)
                if not check:
                    raise Exception("Cannot verify your username. Sorry.")

                print
                print "Player information from Mojang"
                print "---------------------------------------"
                pprint.pprint(check)

                print
                print "Decoded Property Values"
                print "---------------------------------------"
                pprint.pprint(json.loads(check['properties'][0]['value'].decode('base64')))

                out_buf = fastmc.proto.WriteBuffer()

                event_data = ConnectEventData(self.player_ign, self.uuid)
                connect_event(event_data)
                if event_data.cancelled:
                    self.writer.write(out_buf, 0x00, reason=event_data.cancel_reason or {"text": "Event cancelled. "
                                                                                                 "Please supply a "
                                                                                                 "reason in the "
                                                                                                 "cancel_reason "
                                                                                                 "field."})
                    self.sock.send(out_buf)
                    return

                # set compression
                threshold = 256
                self.writer.write(out_buf, 0x03,
                                  threshold=threshold)

                self.reader.set_compression_threshold(threshold)
                self.writer.set_compression_threshold(threshold)

                self.uuid = uuid.UUID(check['id'])
                self.writer.write(out_buf, 0x02,
                                  uuid=str(self.uuid),
                                  username=self.player_ign)

                self.reader.switch_state(fastmc.proto.PLAY)
                self.writer.switch_state(fastmc.proto.PLAY)

                self.sock.send(out_buf)
                print "%s logged in" % self.player_ign

                # send join game packet, just for fun
                out_buf.reset()

                self.writer.write(out_buf, 0x01,
                                  eid=1,
                                  game_mode=1,
                                  dimension=1,
                                  difficulty=0,
                                  max_players=60,
                                  level_type="default",
                                  reduced_debug=False)

                self.writer.write(out_buf, 0x05,
                                  location=fastmc.proto.Position(x=0, y=0, z=0))

                self.writer.write(out_buf, 0x39,
                                  flags=1,
                                  flying_speed=1,
                                  walking_speed=1)

                self.writer.write(out_buf, 0x08,
                                  x=0.0, y=75.0, z=0.0,
                                  yaw=0.0, pitch=0.0,
                                  flag=0)

                self.sock.send(out_buf)

            elif self.reader.state == fastmc.proto.PLAY:
                # ready to receive packets
                pass

    def greenlet_run(self, sock):
        protocol_version = 47
        self.sock = fastmc.proto.MinecraftSocket(sock)
        self.reader, self.writer = fastmc.proto.Endpoint.server_pair(protocol_version)

        in_buf = fastmc.proto.ReadBuffer()
        while 1:
            data = self.sock.recv()
            if not data:
                break
            in_buf.append(data)
            while 1:
                pkt, pkt_raw = self.reader.read(in_buf)
                if pkt is None:
                    break
                self.handle_pkt(pkt)

        print "Client disconnected"
        sock.close()
