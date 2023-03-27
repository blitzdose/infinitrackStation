import struct

import binascii
from micropython import const

_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID16_COMPLETE = const(0x3)
_ADV_TYPE_UUID32_COMPLETE = const(0x5)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_UUID16_MORE = const(0x2)
_ADV_TYPE_UUID32_MORE = const(0x4)
_ADV_TYPE_UUID128_MORE = const(0x6)
_ADV_TYPE_APPEARANCE = const(0x19)
_ADV_TYPE_CUSTOMDATA = const(0xff)


# Generate a payload to be passed to gap_advertise(adv_data=...).
def generate_advertising_payload(limited_disc=False, br_edr=False, name=None, services=None, custom_data=None, appearance=0):
    payload = bytearray()

    def _append(adv_type, value):
        nonlocal payload
        payload += struct.pack('BB', len(value) + 1, adv_type) + value

    _append(_ADV_TYPE_FLAGS, struct.pack('B', (0x01 if limited_disc else 0x02) + (0x00 if br_edr else 0x04)))

    if name:
        _append(_ADV_TYPE_NAME, name)

    if services:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 2:
                _append(_ADV_TYPE_UUID16_COMPLETE, b)
            elif len(b) == 4:
                _append(_ADV_TYPE_UUID32_COMPLETE, b)
            elif len(b) == 16:
                _append(_ADV_TYPE_UUID128_COMPLETE, b)

    if custom_data:
        _append(_ADV_TYPE_CUSTOMDATA, custom_data)

        _append(_ADV_TYPE_APPEARANCE, struct.pack('<h', appearance))

    return payload


def parse_advertising_payload(addr, rssi, payload):
    parsed_payload = dict()
    while len(payload) > 0:
        size = payload[0]
        if size == 0:
            continue
        type = payload[1]
        data = binascii.hexlify(payload[2:size+1]).decode("utf-8")
        parsed_payload[type] = data
        payload = payload[size+1:]
    parsed_data = dict()
    parsed_data['addr'] = binascii.hexlify(addr).decode('utf-8')
    parsed_data['rssi'] = rssi
    parsed_data['payload'] = parsed_payload

    return parsed_data
