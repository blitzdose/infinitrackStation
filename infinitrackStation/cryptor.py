import binascii

import cryptolib
import ustruct
import urandom


class Cryptor:

    def __init__(self):
        self.key = self.__read_key()

        self.encryptor = cryptolib.aes(self.key, 1)
        self.decryptor = cryptolib.aes(self.key, 1)

    def set_key(self, key: bytes):
        self.key = key
        self.__write_key(key)

    def get_key(self):
        return self.key

    def generate_key(self):
        key_size = 16
        buf = bytearray(key_size)
        q, r = divmod(key_size, 4)  # 32 bits == 4 bytes
        if r:
            if r == 3:
                ustruct.pack_into('>HB', buf, 0, urandom.getrandbits(16), urandom.getrandbits(8))
            else:
                ustruct.pack_into(
                    '>H' if r == 2 else '>B', buf, 0, urandom.getrandbits(8 * r)
                )
        while q:
            ustruct.pack_into('>I', buf, 4 * (q - 1) + r, urandom.getrandbits(32))
            q -= 1
        self.__write_key(buf)
        return buf

    def encrypt(self, data: str):
        data = self.__add_padding(data)
        return self.encryptor.encrypt(data)

    def decrypt(self, data: bytes):
        decrypted = self.decryptor.decrypt(data).replace(b"\x00", bytes()).decode('utf-8')
        return decrypted

    def __add_padding(self, data):
        data = data.encode('utf-8')
        length = len(data)
        rest = (length % 16)
        if rest > 0:
            data += bytes(16 - rest)
        return data

    def __read_key(self):
        try:
            f = open("lora.key")
            return binascii.unhexlify(f.readline())
        except OSError:
            return self.generate_key()

    def __write_key(self, key):
        f = open('lora.key', 'w')
        f.write(binascii.hexlify(key).decode('utf-8'))
        f.flush()
        f.close()
