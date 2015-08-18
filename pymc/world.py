from collections import namedtuple
import itertools
import array

ChunkCoordinate = namedtuple("ChunkCoordinate", "x z")

EncodedChunkProperty = namedtuple("EncodedChunkProperty", "offset bitmask")

class World(object):
    def __init__(self, dimension=0):
        self.dimension = dimension
        self.skylight = dimension == 0
        self.chunks = {} # TODO add loading and unloading from disk

    def set_chunk(self, chunk):
        chunk_x_dict = self.chunks.setdefault(chunk.x, {})
        chunk_x_dict[chunk.z] = chunk

    def get_chunk(self, coord):
        chunk_x_dict = self.chunks.get(coord.x, {})
        val = chunk_x_dict.get(coord.z)
        if val is None:
            # TODO try loading, or try generating
            pass

        return val

    def encode_bulk(self, chunks):
        data = bytearray()
        properties = {}
        for coord in chunks:
            chunk = self.get_chunk(coord)
            data, properties[coord] = chunk.encode(data)

        return data, properties


class Chunk(object):
    def __init__(self, world, x=0, z=0):
        # height in 16*16*16 cubes
        self.world = world
        self.height = 16
        self.chunk_splits = dict()
        self.x = x
        self.z = z

    @property
    def bitmask(self):
        bitmask_var = 0
        for i in range(self.height):
            if self.chunk_splits.has_key(i):
                bitmask_var |= 1 << i

        return bitmask_var

    def encode(self, data):
        offset = len(data)

        for i in range(self.height):
            if self.chunk_splits.has_key(i):
                data = self.chunk_splits[i].encode(data)

        # biome
        for z in range(16):
            for x in range(16):
                # TODO send real biome
                data.append(1)

        return data, EncodedChunkProperty(offset=offset, bitmask=self.bitmask)

    def initialize_split(self, y):
        split = ChunkSplit(self, y)
        self.chunk_splits[y] = split
        return split

    def get_split(self, y):
        if not self.chunk_splits.has_key(y):
            return self.initialize_split(y)
        return self.chunk_splits[y]

    def set_block_id_and_metadata(self, x, y, z, id, metadata):
        split = self.get_split(y >> 4)
        split.set_block_id_and_metadata(x, y % 16, z, id, metadata)


class ChunkSplit(object):
    def __init__(self, chunk, y):
        self.chunk = chunk
        self.y = y
        self.ids = bytearray(8192)
        self.light = bytearray()
        self.light.extend([255]*2048)
        self.skylight = None

        if self.chunk.world.skylight:
            self.skylight = bytearray()
            self.light.extend([255]*2048)


    def set_block_id_and_metadata(self, x, y, z, id, metadata):
        short = id << 4 | metadata
        i = y << 9 | z << 5 | x << 1
        self.ids[i] = short & 0xff
        self.ids[i | 1] = short >> 8
        # TODO mark dirty

    def encode(self, data):
        data.extend(self.ids)

        # send light levels
        data.extend(self.light)

        if self.skylight is not None:
            data.extend(self.skylight)

        return data