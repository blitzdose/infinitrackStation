import binascii
import time
from sys import stdin

import select
import ubluetooth

import serial_communication as serial
from ble_communication import BLECommunication
from cryptor import Cryptor
from .lora_receiver import LoraReceiver


class BaseStation:
    def __init__(self):
        self.lora_parameter = {
            'address': bytes(0),
            'tx_power_level': 40,
            'signal_bandwidth': 500000,
            'spreading_factor': 10,
            'coding_rate': 5,
            'key': bytes(0),
            'myaddress': bytes(0)
        }
        self.lora_receiver = None
        self.ble = BLECommunication(
            ubluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E"),
            ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'),
            ubluetooth.UUID('6E400003-B5A3-F393-E0A9-E50E24DCCA9E')
        )

        self.initialize_lora()
        self.loop()

    def initialize_lora(self):
        self.initialize_lora_parameter()
        self.lora_receiver = LoraReceiver(self.lora_parameter)
        self.lora_receiver.set_receive_callback(self.on_lora_receive)

    def initialize_lora_parameter(self):
        addr = self.ble.get_mac()
        self.lora_parameter['address'] = binascii.hexlify(addr)
        self.lora_parameter['myaddress'] = binascii.hexlify(addr)
        cryptor = Cryptor()
        self.lora_parameter['key'] = binascii.hexlify(cryptor.get_key())

    def on_lora_receive(self, payload: bytes, rssi: int):
        if not len(payload) >= 16:
            return
        if not payload[:4] == b'infi':
            return

        recv_addr = payload[4:10]
        if recv_addr != binascii.unhexlify(self.lora_parameter['myaddress']):
            return

        message_dict = dict()
        message_dict['rssi'] = rssi
        message_dict['header'] = binascii.hexlify(payload[:16])
        message_dict['payload'] = binascii.hexlify(Cryptor().decrypt(payload[16:]))

        serial.send_message_json(serial.TYPE_LORA_RECV, message_dict)

    def loop(self):
        serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_READY_GLOBAL)

        while True:
            poll = select.poll()
            poll.register(stdin, select.POLLIN)
            available = poll.poll(1000)
            if available:
                self.handle_input(stdin.readline())
            time.sleep(0.01)

    def handle_input(self, line):
        input_arr = line.strip().split(":")
        if input_arr[0] == serial.INPUT_START_SCAN:
            self.ble.start_scan(self.ble_device_discovered)
            serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_BLE_SCAN_STARTED)
        elif input_arr[0] == serial.INPUT_STOP_SCAN:
            self.ble.stop_scan(self.ble_scan_done)
        elif input_arr[0] == serial.INPUT_GET_READY:
            serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_READY_GLOBAL)
        elif input_arr[0] == serial.INPUT_BLE_CONNECT:
            self.ble.connect(binascii.unhexlify(input_arr[1]), self.ble_connect_success, self.ble_connect_error)

    def ble_device_discovered(self, data):
        serial.send_message_json(serial.TYPE_BLE_SCAN_RESULT, data)

    def ble_scan_done(self):
        serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_BLE_SCAN_STOPPED)

    def ble_connect_success(self, conn_handle, value_handle):
        self.ble.write_gattc(conn_handle, value_handle,
                             binascii.unhexlify("01") + binascii.unhexlify(self.lora_parameter['address']))
        time.sleep(1)
        self.ble.write_gattc(conn_handle, value_handle,
                             binascii.unhexlify("02") + self.lora_parameter['tx_power_level'].to_bytes(1, 'big'))
        time.sleep(1)
        self.ble.write_gattc(conn_handle, value_handle,
                             binascii.unhexlify("03") + self.lora_parameter['signal_bandwidth'].to_bytes(5, 'big'))
        time.sleep(1)
        self.ble.write_gattc(conn_handle, value_handle,
                             binascii.unhexlify("04") + self.lora_parameter['spreading_factor'].to_bytes(1, 'big'))
        time.sleep(1)
        self.ble.write_gattc(conn_handle, value_handle,
                             binascii.unhexlify("05") + self.lora_parameter['coding_rate'].to_bytes(1, 'big'))
        time.sleep(1)
        self.ble.write_gattc(conn_handle, value_handle,
                             binascii.unhexlify("06") + binascii.unhexlify(self.lora_parameter['key']))
        time.sleep(1)
        self.ble.write_gattc(conn_handle, value_handle, binascii.unhexlify("FFFF"))

        serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_BLE_DATA_SEND)

    def ble_connect_error(self):
        serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_ERROR_OCCURRED)
