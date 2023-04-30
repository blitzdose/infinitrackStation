import struct


class LoRaPayload:
    def __init__(self):
        self.timestamp = None
        self.date = None
        self.latitude = None
        self.longitude = None
        self.speed = None
        self.course = None
        self.satellites_in_use = None
        self.altitude = None
        self.pdop = None
        self.charge_level = None
        pass

    def set_timestamp(self, timestamp):
        self.timestamp = int((timestamp[0] * 3600) + (timestamp[1] * 60) + (timestamp[2])).to_bytes(3, 'big')

    def set_date(self, date):
        self.date = date[2].to_bytes(1, 'big') + date[1].to_bytes(1, 'big') + date[0].to_bytes(1, 'big')

    def set_latitude(self, latitude):
        self.latitude = struct.pack('>f', latitude[0]) + (b'\x01' if latitude[1] == 'N' else b'\x00')

    def set_longitude(self, longitude):
        self.longitude = struct.pack('>f', longitude[0]) + (b'\x01' if longitude[1] == 'E' else b'\x00')

    def set_speed(self, speed):
        self.speed = struct.pack('>f', speed)

    def set_course(self, course):
        self.course = struct.pack('>f', course)

    def set_satellites_in_use(self, satellites_in_use):
        self.satellites_in_use = satellites_in_use.to_bytes(1, 'big')

    def set_altitude(self, altitude):
        self.altitude = struct.pack('>f', altitude)

    def set_pdop(self, pdop):
        self.pdop = struct.pack('>f', pdop)

    def set_charge_level(self, charge_level):
        self.charge_level = charge_level.to_bytes(1, 'big')

    def get_bytes(self):
        return self.timestamp + \
            self.date + \
            self.latitude + \
            self.longitude + \
            self.speed + \
            self.course + \
            self.satellites_in_use + \
            self.altitude + \
            self.pdop + \
            self.charge_level
