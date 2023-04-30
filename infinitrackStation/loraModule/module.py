import _thread
import binascii
import json
import time

import machine
import esp32
import ubluetooth

from ble_communication import BLECommunication
from .button_handler import ButtonHandler
from cryptor import Cryptor
from libraries.micropyGPS import MicropyGPS
from .lora_payload import LoRaPayload
from .lora_sender import LoraSender

charge_levels = [
    4.20,
    4.15,
    4.11,
    4.08,
    4.02,
    3.98,
    3.95,
    3.91,
    3.87,
    3.85,
    3.84,
    3.82,
    3.80,
    3.79,
    3.77,
    3.75,
    3.73,
    3.71,
    3.69,
    3.61,
    3.27
]


class Module:
    def __init__(self):
        self.pin_button: machine.Pin
        self.pin_led_red: machine.Pin
        self.pin_led_green: machine.Pin
        self.pin_led_blue: machine.Pin
        self.pin_adc_lipo: machine.Pin

        self.button_handler = None

        self.init_pins()

        self.blink(self.pin_led_green, 0.2, 0.3, 2)

        self.timer2 = machine.Timer(2)

        self.ble = BLECommunication(
            ubluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E"),
            ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'),
            ubluetooth.UUID('6E400003-B5A3-F393-E0A9-E50E24DCCA9E')
        )

        self.paring_mode_blink_delay = 0.6

        self.lora_sender = None
        self.lora_parameter = {
            'address': bytes(0),
            'tx_power_level': 40,
            'signal_bandwidth': 500000,
            'spreading_factor': 10,
            'coding_rate': 5,
            'key': bytes(0),
            'myaddress': bytes(0)
        }

        self.gps = MicropyGPS(location_formatting="dd")

        self.initialized = False

        self.initialize_lora()

        if machine.reset_cause() == machine.PWRON_RESET:
            self.sleep()

        self.loop()

    def init_pins(self):
        self.pin_button = machine.Pin(33, machine.Pin.IN, machine.Pin.PULL_UP)
        self.pin_led_red = machine.Pin(13, machine.Pin.OUT)
        self.pin_led_green = machine.Pin(17, machine.Pin.OUT)
        self.pin_led_blue = machine.Pin(2, machine.Pin.OUT)

        self.pin_adc_lipo = machine.ADC(machine.Pin(32))
        self.pin_adc_lipo.atten(machine.ADC.ATTN_11DB)

        self.button_handler = ButtonHandler(
            self.pin_button,
            self.button_short_click,
            self.button_long_click,
            self.button_hold
        )

    def button_short_click(self):
        self.sleep()
        pass

    def button_long_click(self):
        self.button_handler.deinit()
        self.button_handler = ButtonHandler(self.pin_button, self.button_short_click, None, None)
        self.pin_led_blue.off()
        self.ble.pairing_mode(self.ble_connected, self.ble_data_write)

        _thread.start_new_thread(self.blink_paring_mode, ())

    def button_hold(self, pressed):
        if pressed:
            self.pin_led_blue.on()
            self.timer2.deinit()
        else:
            self.pin_led_blue.off()
            if self.initialized:
                self.timer2.init(mode=machine.Timer.ONE_SHOT, period=2000, callback=self.lora_sender.activity_detection)
            else:
                self.timer2.init(mode=machine.Timer.PERIODIC, period=2000, callback=self.heartbeat)

    def blink_paring_mode(self):
        while True:
            self.blink(self.pin_led_blue, 0.05, self.paring_mode_blink_delay, 1)

    def ble_connected(self):
        self.paring_mode_blink_delay = 0.1

    def ble_data_write(self, type: bytearray, data: bytearray):
        if type == b'\x01':
            self.lora_parameter['address'] = binascii.hexlify(bytes(data))
        elif type == b'\x02':
            self.lora_parameter['tx_power_level'] = int.from_bytes(data, 'big')
        elif type == b'\x03':
            self.lora_parameter['signal_bandwidth'] = int.from_bytes(data, 'big')
        elif type == b'\x04':
            self.lora_parameter['spreading_factor'] = int.from_bytes(data, 'big')
        elif type == b'\x05':
            self.lora_parameter['coding_rate'] = int.from_bytes(data, 'big')
        elif type == b'\x06':
            self.lora_parameter['key'] = binascii.hexlify(bytes(data))
        elif type == b'\xFF':
            self.lora_parameter['myaddress'] = binascii.hexlify(self.ble.get_mac())
            with open('lora.config', 'w') as f:
                json.dump(self.lora_parameter, f)
                Cryptor().set_key(binascii.unhexlify(self.lora_parameter['key']))

            machine.reset()

    def initialize_lora(self):
        self.initialize_lora_parameter()
        self.lora_sender = LoraSender(self.lora_parameter, self.send_lora_payload)
        if self.initialized:
            self.timer2.init(mode=machine.Timer.ONE_SHOT, period=2000, callback=self.lora_sender.activity_detection)
        else:
            self.timer2.init(mode=machine.Timer.PERIODIC, period=2000, callback=self.heartbeat)

    def initialize_lora_parameter(self):
        try:
            with open('lora.config') as f:
                self.lora_parameter = json.load(f)
            self.initialized = True
            return
        except (OSError, ValueError):
            pass

    def send_lora_payload(self):
        if self.gps.satellite_data_updated():
            payload = LoRaPayload()
            payload.set_timestamp(self.gps.timestamp)
            payload.set_date(self.gps.date)
            payload.set_latitude(self.gps.latitude)
            payload.set_longitude(self.gps.longitude)
            payload.set_speed(self.gps.speed[2])
            payload.set_course(self.gps.course)
            payload.set_satellites_in_use(self.gps.satellites_in_use)
            payload.set_altitude(self.gps.altitude)
            payload.set_pdop(self.gps.pdop)
            payload.set_charge_level(self.get_charge_level()[0])

            payload_bytes = payload.get_bytes()
            header_bytes = b'infi' + \
                           bytes(binascii.unhexlify(self.lora_parameter['address'])) + \
                           bytes(binascii.unhexlify(self.lora_parameter['myaddress']))
            payload_bytes_encrypted = Cryptor().encrypt(payload_bytes)
            data = header_bytes + payload_bytes_encrypted

            self.lora_sender.send_data(data)
        else:
            data = b'infi' + \
                   bytes(binascii.unhexlify(self.lora_parameter['address'])) + \
                   bytes(binascii.unhexlify(self.lora_parameter['myaddress'])) + \
                   Cryptor().encrypt(b'\xFF\xFF')
            self.lora_sender.send_data(data)

        self.heartbeat(None)

        self.timer2.init(mode=machine.Timer.ONE_SHOT, period=2000, callback=self.lora_sender.activity_detection)

    def get_charge_level(self):
        val = self.pin_adc_lipo.read()
        voltage_level = val * 1.7 / 1000
        charge = 100
        if voltage_level > 4.2:
            charge = 100
        elif voltage_level < 3.27:
            charge = 0
        else:
            idx = 0
            for level in charge_levels:
                if level < voltage_level:
                    level_before = charge_levels[idx-1]
                    change = level_before - level

                    linear_regression = ((voltage_level - level) * (5 / change))
                    charge = ((20 - idx) * 5) + linear_regression
                    break
                idx = idx + 1

        return round(charge), voltage_level

    def sleep(self):
        self.blink(self.pin_led_red, 0.2, 0.3, 2)
        esp32.wake_on_ext0(pin=self.pin_button, level=esp32.WAKEUP_ALL_LOW)
        print("Going to sleep. Good night! :)")
        machine.deepsleep()

    def heartbeat(self, t):
        pin = self.pin_led_green
        if not self.initialized:
            pin = self.pin_led_red
        self.blink(pin, 0.2, 0, 1)

    def blink(self, pin, on_time, off_time, count):
        for i in range(count):
            pin.on()
            time.sleep(on_time)
            pin.off()
            time.sleep(off_time)

    def loop(self):
        uart = machine.UART(1)
        uart.init(baudrate=9600, tx=16, rx=4)

        while True:
            try:
                if uart.any() > 0:
                    nmea_sentence = uart.readline().decode('utf-8')
                    for x in nmea_sentence:
                        self.gps.update(x)
            except UnicodeError:
                pass
            time.sleep(0.01)
