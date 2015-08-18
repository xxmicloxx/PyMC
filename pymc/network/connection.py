import json
import random
import uuid
import fastmc.auth
import fastmc.proto
import pprint
import cProfile
import time
from threading import Timer, Lock
import time
import pstats
from pymc import world
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


class ConnectionHandler(object):
    def __init__(self):
        self.sock = None
        self.reader = self.writer = None
        self.token = fastmc.auth.generate_challenge_token()
        self.server_id = fastmc.auth.generate_server_id()
        self.key = fastmc.auth.generate_key_pair()
        self.player_ign = None
        self.uuid = None
        self.alive = True
        self.sock_mutex = Lock()

    def handle_pkt(self, pkt):
        # print pkt
        # print

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
                self.sock_send(out_buf)
            elif pkt.id == 0x01:
                out_buf = fastmc.proto.WriteBuffer()
                self.writer.write(out_buf, 0x01, time=pkt.time)
                self.sock_send(out_buf)
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

                self.sock_send(out_buf)
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
                    self.sock_send(out_buf)
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

                self.sock_send(out_buf)
                print "%s logged in" % self.player_ign

                # send join game packet, just for fun
                out_buf.reset()

                # join game packet
                self.writer.write(out_buf, 0x01,
                                  eid=1,
                                  game_mode=0,
                                  dimension=0,
                                  difficulty=0,
                                  max_players=60,
                                  level_type="default",
                                  reduced_debug=False)

                # player spawn location (not where the player spawns, but where the compass points to)
                self.writer.write(out_buf, 0x05,
                                  location=fastmc.proto.Position(x=0, y=0, z=0))

                # player abilities
                self.writer.write(out_buf, 0x39,
                                  flags=5,
                                  flying_speed=0.1,
                                  walking_speed=0.1)

                # player list item, for skin and player list
                player_actions = fastmc.proto.PlayerListActionAdd(
                    uuid=self.uuid.int,
                    name=self.player_ign,
                    properties=[fastmc.proto.PlayerListActionAddProperty(**check['properties'][0])],
                    game_mode=0,
                    ping=0,
                    display_name=None
                )

                list_actions = fastmc.proto.PlayerListActions(action=fastmc.proto.LIST_ACTION_ADD_PLAYER, players=[player_actions])

                self.writer.write(out_buf, 0x38,
                                  list_actions=list_actions)

                self.sock_send(out_buf)
                out_buf.reset()

                #cProfile.runctx("self.write_world()", locals(), globals(), 'restats')
                #p = pstats.Stats('restats')
                #p.strip_dirs().sort_stats('time').print_stats()
                self.write_world()

                # time update - freezes time at noon
                self.writer.write(out_buf, 0x03,
                                      world_age=0,
                                      time_of_day=-6000)

                # chat message - welcome
                self.writer.write(out_buf, 0x02,
                                  chat={"text": "Welcome to PyMC! Testing done here!"},
                                  position=1)

                # player position and look - this will make the player leave the "Loading terrain..." screen
                self.writer.write(out_buf, 0x08,
                                  x=0.0, y=100.0, z=0.0,
                                  yaw=0.0, pitch=0.0,
                                  flag=0)

                self.sock_send(out_buf)

                # start ping timer

                def timeout():
                    if not self.alive:
                        return

                    buf = fastmc.proto.WriteBuffer()

                    if not hasattr(self, "test"):
                        self.test = True

                        # set initial health
                        self.writer.write(buf, 0x06,
                                          health=20.0,
                                          food=20,
                                          food_saturation=500)

                        # play damage animation
                        self.writer.write(buf, 0x0B,
                                          eid=1,
                                          animation=1)

                        # actually set health
                        self.writer.write(buf, 0x06,
                                          health=10.0,
                                          food=20,
                                          food_saturation=500)

                        # chat message - welcome
                        self.writer.write(buf, 0x02,
                                  chat={"text": "Ouch!", "color": "dark_red", "bold": True},
                                  position=1)


                    self.writer.write(buf, 0x00,
                                      keepalive_id=random.randint(0, 99999))

                    self.sock_send(buf)

                    thread = Timer(1, timeout)
                    thread.setDaemon(True)
                    thread.start()

                timeout()

            elif self.reader.state == fastmc.proto.PLAY:
                # ready to receive packets
                pass

    def write_world(self):
        out_buf = fastmc.proto.WriteBuffer()

        start = time.clock()
        my_world = world.World()
        chunk_coords = []
        for x in range(-5, 5):
            for z in range(-5, 5):
                chunk = world.Chunk(my_world, x=x, z=z)
                my_world.set_chunk(chunk)
                for xb in range(16):
                    for yb in range(64, 80):
                        for zb in range(16):
                            chunk.set_block_id_and_metadata(xb, yb, zb, 2, 0)

                chunk_coords.append(world.ChunkCoordinate(x=x, z=z))
        print "Time for chunk generation: %f" % (time.clock() - start)
        start = time.clock()
        fake_data, properties = my_world.encode_bulk(chunk_coords)
        file = open("/home/ml/test.hex", "wb")
        file.write(fake_data)
        file.flush()
        file.close()

        start_encode = time.clock()
        chunk_info_list = []
        for coord in chunk_coords:
            property = properties[coord]
            chunk_info = fastmc.proto.Chunk14w28a(coord.x, coord.z, property.bitmask, property.offset)
            chunk_info_list.append(chunk_info)
        bulk = fastmc.proto.ChunkBulk14w28a(
            sky_light_sent=True,
            data=fake_data,
            chunks=chunk_info_list
        )
        self.writer.write(out_buf, 0x26, bulk=bulk)
        current_clock = time.clock()
        print "Time for chunk encoding: %f" % (start_encode - start)
        print "Total time for chunking: %f" % (current_clock - start)

        self.sock_send(out_buf)

    def sock_send(self, buf):
        with self.sock_mutex:
            self.sock.send(buf)

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
        self.alive = False
        sock.close()
