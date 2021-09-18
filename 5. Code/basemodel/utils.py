import sys

BITMAP_SIZ = 1 << 16  # 64k bitmap
# BUFFER_SIZ_LEN = 32
ENDIAN = sys.byteorder
INPUT_SIZ_LEN = 4  # length of the current input



def dprint(obj):
    """ debug print """
    print(obj)