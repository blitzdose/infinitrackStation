import binascii

import ubluetooth
from micropython import const

import ble_advertising

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_GATTS_WRITE = const(3)
_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_IRQ_PERIPHERAL_CONNECT = const(7)
_IRQ_GATTC_SERVICE_RESULT = const(9)
_IRQ_GATTC_SERVICE_DONE = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE = const(12)

ble_advertising_data = binascii.unhexlify("4954496e66696e69747261636b4d6f64")

class BLECommunication:
    def __init__(self, service_uuid, characteristics_rx_uuid, characteristics_tx_uuid):
        self.ble = ubluetooth.BLE()
        self.callback_discovery = None
        self.callback_scan_done = None
        self.callback_characteristic = None
        self.callback_error = None

        self.callback_connected = None
        self.callback_data_write = None

        self.service_uuid = service_uuid
        self.characteristics_rx_uuid = characteristics_rx_uuid
        self.characteristics_tx_uuid = characteristics_tx_uuid
        self.ble.irq(self.irq_handler)

    def get_mac(self):
        self.ble.active(True)
        mac = self.ble.config('mac')[1]
        self.ble.active(False)
        return mac

    def start_scan(self, callback_discovery=None):
        self.callback_discovery = callback_discovery
        self.ble.active(True)
        self.ble.gap_scan(30000, 300000, 11250, True)

    def stop_scan(self, callback_scan_done=None):
        self.callback_scan_done = callback_scan_done
        if self.ble.active():
            self.ble.gap_scan(None)
            self.ble.active(False)

    def connect(self, addr: bytes, callback_characteristic=None, callback_error=None):
        self.callback_characteristic = callback_characteristic
        self.callback_error = callback_error
        self.ble.active(True)
        self.ble.gap_connect(0x00, addr)

    def write_gattc(self, conn_handle, value_handle, data):
        self.ble.gattc_write(conn_handle, value_handle, data)

    def irq_handler(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            if self.callback_connected is not None:
                self.callback_connected()
        elif event == _IRQ_SCAN_RESULT:
            addr_type, addr, adv_type, rssi, adv_data = data
            data = ble_advertising.parse_advertising_payload(bytes(addr), rssi, bytes(adv_data))
            if self.callback_discovery is not None:
                self.callback_discovery(data)
        elif event == _IRQ_SCAN_DONE:
            if self.callback_scan_done:
                self.callback_scan_done()
        elif event == _IRQ_PERIPHERAL_CONNECT:
            conn_handle, addr_type, addr = data
            self.ble.gattc_discover_services(conn_handle, self.service_uuid)
        elif event == _IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start_handle, end_handle, uuid = data
            self.ble.gattc_discover_characteristics(conn_handle, start_handle, end_handle, self.characteristics_rx_uuid)
        elif event == _IRQ_GATTC_SERVICE_DONE:
            conn_handle, status = data
            if status != 0:
                if self.callback_error is not None:
                    self.callback_error()
        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            conn_handle, def_handle, value_handle, properties, uuid = data
            if uuid == self.characteristics_rx_uuid:
                if self.callback_characteristic is not None:
                    self.callback_characteristic(conn_handle, value_handle)
        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            conn_handle, status = data
            if status != 0:
                if self.callback_error is not None:
                    self.callback_error()
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data
            value = self.ble.gatts_read(attr_handle)
            value_array = bytearray(value)

            type = value_array[:1]
            data = value_array[1:]

            if self.callback_data_write is not None:
                self.callback_data_write(type, data)

    def pairing_mode(self, callback_connected, callback_data_write):
        self.callback_connected = callback_connected
        self.callback_data_write = callback_data_write

        self.ble.active(True)
        payload = ble_advertising.generate_advertising_payload(name="Infinitrack Module")
        payload2 = ble_advertising.generate_advertising_payload(custom_data=ble_advertising_data)

        uart_tx = (self.characteristics_tx_uuid, ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY,)
        uart_rx = (self.characteristics_rx_uuid, ubluetooth.FLAG_WRITE,)
        uart_service = (self.service_uuid, (uart_tx, uart_rx,),)
        services = (uart_service,)
        self.ble.gatts_register_services(services)

        self.ble.gap_advertise(150000, payload, resp_data=payload2, connectable=True)
