import gc

import time
import _thread
from sys import stdin, stdout

import json

import binascii
import machine
import select
import utime as utime
from micropython import const
from machine import UART

import ble_advertising
import config_lora
import serial_communication as serial
import sx127x

import ubluetooth
from ble_advertising import generate_advertising_payload as adpl
#from micropyGPS import MicropyGPS

gc.collect()

lora: sx127x.SX127x = None

intTime = 0
debTime = 300

timer0 = machine.Timer(0)
timer1 = machine.Timer(1)

pin_button: machine.Pin
pin_led_blue: machine.Pin
pin_led_green: machine.Pin
pin_led_red: machine.Pin

heartbeat_running = True

def do_loop():
    serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_READY_GLOBAL)

    #uart = UART(1)
    #uart.init(baudrate=9600, tx=16, rx=4)
#
    #gps = MicropyGPS(location_formatting="dd")
#
    #while True:
    #    try:
    #        if uart.any() > 0:
    #            nmea_sentence = uart.readline().decode('utf-8')
    #            print(nmea_sentence)
    #            for x in nmea_sentence:
    #                gps.update(x)
#
    #            print(gps.latitude)
    #            print(gps.longitude)
    #            print(gps.coord_format)
    #    except UnicodeError:
    #        pass
#
    #    #lora.println("{\"name\": \"Test123\"}")
    #    time.sleep(0.01)

    #module()

    while True:
        poll = select.poll()
        poll.register(stdin, select.POLLIN)
        available = poll.poll(1000)
        if available:
            input_arr = stdin.readline().strip().split(":")
            input = input_arr[0]
            if input == serial.INPUT_START_SCAN:
                serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_BLE_SCAN_STARTED)
                init_ble()
            elif input == serial.INPUT_STOP_SCAN:
                disable_ble()
            elif input == serial.INPUT_GET_READY:
                serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_READY_GLOBAL)
            elif input == serial.INPUT_BLE_CONNECT:
                ble = ubluetooth.BLE()
                ble.active(True)
                serial.send_message_str("status", input_arr[1])
                ble.gap_connect(0x00, binascii.unhexlify(input_arr[1]))

        time.sleep(0.01)


def module():
    global pin_button
    pin_button = machine.Pin(33, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_button.irq(debounce, machine.Pin.IRQ_RISING)

    global pin_led_blue, pin_led_green, pin_led_red
    pin_led_blue = machine.Pin(2, machine.Pin.OUT)
    pin_led_green = machine.Pin(17, machine.Pin.OUT)
    pin_led_red = machine.Pin(13, machine.Pin.OUT)

    _thread.start_new_thread(heartbeat, ())

    while True:
        time.sleep(0.01)


def main():
    init_lora()
    do_loop()


def init_ble():
    ble = ubluetooth.BLE()
    ble.active(True)
    ble.irq(ble_handler)
    ble.gap_scan(30000, 1280000, 11250, True)


def disable_ble():
    ble = ubluetooth.BLE()
    if ble.active():
        ble.gap_scan(None)
        ble.active(False)


def ble_handler(event, data):
    if event == const(5):
        addr_type, addr, adv_type, rssi, adv_data = data
        data = ble_advertising.parse_advertising_payload(bytes(addr), rssi, bytes(adv_data))
        serial.send_message_json(serial.TYPE_BLE_SCAN_RESULT, data)
    elif event == const(6):
        serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_BLE_SCAN_STOPPED)
    elif event == const(7):
        conn_handle, addr_type, addr = data
        ble = ubluetooth.BLE()
        ble.gattc_discover_services(conn_handle, ubluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E"))
    elif event == const(9):
        conn_handle, start_handle, end_handle, uuid = data
        ble = ubluetooth.BLE()
        ble.gattc_discover_characteristics(conn_handle, start_handle, end_handle, ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'))
    elif event == const(11):
        conn_handle, def_handle, value_handle, properties, uuid = data
        if uuid == ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'):
            serial.send_message_str("status", "123123123")
            ble = ubluetooth.BLE()
            ble.gattc_write(conn_handle, value_handle, binascii.unhexlify("FFFFFFFF"))
            time.sleep(1)
            ble.gattc_write(conn_handle, value_handle, binascii.unhexlify("AAAAAA"))
            time.sleep(1)
            ble.gattc_write(conn_handle, value_handle, binascii.unhexlify("6666666666"))

    elif event == const(12):
        pass
        # serial.send_message_str("status", "4")
    elif event == const(3):
        conn_handle, attr_handle = data
        ble = ubluetooth.BLE()
        value = ble.gatts_read(attr_handle)
        print(value)
        # TODO: Daten empfangen und speichern, verbindung aufbauen


def debounce(pin):
    global timer0
    timer0.init(mode=machine.Timer.ONE_SHOT, period=200, callback=button_handler)


def button_handler(t):
    global pin_button, pin_led_blue, heartbeat_running
    if pin_button.value() == 0:
        pin_led_blue.on()
        print('pressed')
        timer1.init(mode=machine.Timer.ONE_SHOT, period=5000, callback=paring_mode)
        heartbeat_running = False
    else:
        pin_led_blue.off()
        print('unpressed')
        timer1.deinit()
        heartbeat_running = True
        _thread.start_new_thread(heartbeat, ())


def paring_mode(t):
    global timer0, pin_button, pin_led_blue
    timer0.deinit()
    pin_button.irq(None)
    pin_led_blue.on()
    _thread.start_new_thread(blink, ())
    print("PARING MODE")

    ble = ubluetooth.BLE()
    ble.active(True)
    ble.irq(ble_handler)
    payload = ble_advertising.generate_advertising_payload(name="Infinitrack Module")
    payload2 = ble_advertising.generate_advertising_payload(custom_data=binascii.unhexlify("4954496e66696e69747261636b4d6f64"))

    UART_UUID = ubluetooth.UUID('6E400001-B5A3-F393-E0A9-E50E24DCCA9E')
    UART_TX = (ubluetooth.UUID('6E400003-B5A3-F393-E0A9-E50E24DCCA9E'), ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY,)
    UART_RX = (ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'), ubluetooth.FLAG_WRITE,)
    UART_SERVICE = (UART_UUID, (UART_TX, UART_RX,),)
    SERVICES = (UART_SERVICE,)
    ble.gatts_register_services(SERVICES)

    ble.gap_advertise(150000, payload, resp_data=payload2, connectable=True)


def blink():
    global pin_led_blue
    while True:
        pin_led_blue.on()
        time.sleep(0.05)
        pin_led_blue.off()
        time.sleep(0.6)


def heartbeat():
    global pin_led_green, heartbeat_running
    while heartbeat_running:
        pin_led_green.on()
        time.sleep(0.1)
        pin_led_green.off()
        time.sleep(2)


def init_lora():
    controller = config_lora.Controller()
    global lora
    lora = controller.add_transceiver(sx127x.SX127x(
        name='LoRa',
        parameters={
            'frequency': 433E6,
            'tx_power_level': 40,
            'signal_bandwidth': 125E3,
            'spreading_factor': 10,
            'coding_rate': 5,
            'preamble_length': 8,
            'implicitHeader': False,
            'sync_word': 0x12,
            'enable_CRC': False
        }),
        pin_id_ss=config_lora.Controller.PIN_ID_FOR_LORA_SS,
        pin_id_RxDone=config_lora.Controller.PIN_ID_FOR_LORA_DIO0)

    lora.on_receive(on_lora_receive)
    lora.receive()


def on_lora_receive(lora, payload):
    payload_string = payload.decode()
    payload_dict = json.loads(payload_string)

    rssi = lora.packet_rssi()

    message_dict = dict()
    message_dict['rssi'] = rssi
    message_dict['payload'] = payload_dict

    serial.send_message_json(serial.TYPE_LORA_RECV, message_dict)


if __name__ == "__main__":
    main()