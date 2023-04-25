import _thread
import binascii
import gc
import json
import random
import struct
import time
from sys import stdin

import esp
import esp32
import machine
import os
import select
import ubluetooth
from micropython import const
import urandom

import ble_advertising
import config_lora
import cryptor
from cryptor import Cryptor
import serial_communication as serial
import sx127x

from micropyGPS import MicropyGPS

gc.collect()

controller = None
lora: sx127x.SX127x = None
lora_parameter = {
    'address': '',
    'tx_power_level': 40,
    'signal_bandwidth': 500000,
    'spreading_factor': 10,
    'coding_rate': 5,
    'key': bytes(0),
    'myaddress': ''
}

gps: MicropyGPS

initialized = False

intTime = 0
debTime = 300

timer0 = machine.Timer(0)
timer1 = machine.Timer(1)
timer2 = machine.Timer(2)
timer3 = machine.Timer(3)

pin_button: machine.Pin
pin_led_blue: machine.Pin
pin_led_green: machine.Pin
pin_led_red: machine.Pin

heartbeat_running = True
paring_mode_running = False

paring_mode_delay = 0.6

reset = False

send_timer_running = False

button_pressed_time = 0


def do_loop():
    if 'basestation' not in os.listdir():
        module()

    serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_READY_GLOBAL)

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
                ble.gap_connect(0x00, binascii.unhexlify(input_arr[1]))
        time.sleep(0.01)


def module():
    global pin_button
    pin_button = machine.Pin(33, machine.Pin.IN, machine.Pin.PULL_UP)
    pin_button.irq(debounce, machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING)

    global pin_led_blue, pin_led_green, pin_led_red
    pin_led_blue = machine.Pin(2, machine.Pin.OUT)
    pin_led_green = machine.Pin(17, machine.Pin.OUT)
    pin_led_red = machine.Pin(13, machine.Pin.OUT)

    serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_READY_GLOBAL)

    if machine.reset_cause() != machine.DEEPSLEEP_RESET:
        esp32.wake_on_ext0(pin=pin_button, level=esp32.WAKEUP_ALL_LOW)

        print("going to sleep")
        machine.deepsleep()

    timer3.init(mode=machine.Timer.PERIODIC, period=2000, callback=heartbeat)

    uart = machine.UART(1)
    uart.init(baudrate=9600, tx=16, rx=4)

    global gps, send_timer_running, reset
    gps = MicropyGPS(location_formatting="dd")

    while not reset:
        while not heartbeat_running:
            timer2.deinit()
            send_timer_running = False
            time.sleep(0.01)
        try:
            if uart.any() > 0:
                nmea_sentence = uart.readline().decode('utf-8')
                print(nmea_sentence)
                for x in nmea_sentence:
                    gps.update(x)
        except UnicodeError:
            pass

        if not send_timer_running:
            timer2.init(mode=machine.Timer.ONE_SHOT, period=2000, callback=activity_detection)
            send_timer_running = True
        time.sleep(0.01)
    reset = False
    main()


def cad(detected):
    lora.standby()
    if detected == 0:
        send_position()
        lora.sleep()
        global send_timer_running
        send_timer_running = False
    else:
        wait_time = urandom.randint(50, 100)
        timer2.init(mode=machine.Timer.ONE_SHOT, period=wait_time, callback=activity_detection)
        pass


def activity_detection(t):
    lora.standby()
    lora.cad()


def init():

    if machine.reset_cause() == machine.DEEPSLEEP_RESET:
        global pin_led_green
        pin_led_green = machine.Pin(17, machine.Pin.OUT)

        pin_led_green.on()
        time.sleep(0.2)
        pin_led_green.off()
        time.sleep(0.3)
        pin_led_green.on()
        time.sleep(0.2)
        pin_led_green.off()

    global initialized, intTime, debTime, timer0, timer1, timer2, timer3, heartbeat_running, paring_mode_running, paring_mode_delay, reset

    initialized = False

    intTime = 0
    debTime = 300

    timer0 = machine.Timer(0)
    timer1 = machine.Timer(1)
    timer2 = machine.Timer(2)
    timer3 = machine.Timer(3)

    heartbeat_running = True
    paring_mode_running = False

    paring_mode_delay = 0.6

    reset = False


def init_params():
    try:
        with open('lora.config') as f:
            global lora_parameter
            lora_parameter = json.load(f)
        global initialized
        initialized = True
        return
    except (OSError, ValueError):
        pass
    ble = ubluetooth.BLE()
    ble.active(True)
    addr = ble.config('mac')[1]
    lora_parameter['address'] = binascii.hexlify(addr)
    lora_parameter['myaddress'] = binascii.hexlify(addr)
    cryptor = Cryptor()
    lora_parameter['key'] = binascii.hexlify(cryptor.get_key())
    ble.active(False)
    if 'basestation' in os.listdir():
        initialized = True


def main():
    init()
    init_params()
    init_lora()
    do_loop()


def init_ble():
    ble = ubluetooth.BLE()
    ble.active(True)
    ble.irq(ble_handler)
    ble.gap_scan(30000, 300000, 11250, True)


def disable_ble():
    ble = ubluetooth.BLE()
    if ble.active():
        ble.gap_scan(None)
        ble.active(False)


def ble_handler(event, data):
    serial.send_message_str(serial.TYPE_STATUS, f'event: {event}')
    if event == const(1):
        global paring_mode_delay
        paring_mode_delay = 0.1
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
        ble.gattc_discover_characteristics(conn_handle, start_handle, end_handle,
                                           ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'))
    elif event == const(10):
        conn_handle, status = data
        if status != 0:
            serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_ERROR_OCCURRED)
    elif event == const(11):
        conn_handle, def_handle, value_handle, properties, uuid = data
        if uuid == ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'):
            ble = ubluetooth.BLE()
            ble.gattc_write(conn_handle, value_handle,
                            binascii.unhexlify("01") + binascii.unhexlify(lora_parameter['address']))
            time.sleep(1)
            ble.gattc_write(conn_handle, value_handle,
                            binascii.unhexlify("02") + lora_parameter['tx_power_level'].to_bytes(2, 'big'))
            time.sleep(1)
            ble.gattc_write(conn_handle, value_handle,
                            binascii.unhexlify("03") + lora_parameter['signal_bandwidth'].to_bytes(5, 'big'))
            time.sleep(1)
            ble.gattc_write(conn_handle, value_handle,
                            binascii.unhexlify("04") + lora_parameter['spreading_factor'].to_bytes(2, 'big'))
            time.sleep(1)
            ble.gattc_write(conn_handle, value_handle,
                            binascii.unhexlify("05") + lora_parameter['coding_rate'].to_bytes(1, 'big'))
            time.sleep(1)
            ble.gattc_write(conn_handle, value_handle,
                            binascii.unhexlify("06") + binascii.unhexlify(lora_parameter['key']))
            time.sleep(1)
            ble.gattc_write(conn_handle, value_handle, binascii.unhexlify("FFFF"))
            serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_BLE_DATA_SEND)
    elif event == const(12):
        conn_handle, status = data
        if status != 0:
            serial.send_message_str(serial.TYPE_STATUS, serial.STATUS_ERROR_OCCURRED)
    elif event == const(3):
        conn_handle, attr_handle = data
        ble = ubluetooth.BLE()
        value = ble.gatts_read(attr_handle)
        print(binascii.hexlify(value))
        value_array = bytearray(value)

        type = value_array[:1]
        data = value_array[1:]

        if type == b'\x01':
            lora_parameter['address'] = binascii.hexlify(bytes(data))
        elif type == b'\x02':
            lora_parameter['tx_power_level'] = int.from_bytes(data, 'big')
        elif type == b'\x03':
            lora_parameter['signal_bandwidth'] = int.from_bytes(data, 'big')
        elif type == b'\x04':
            lora_parameter['spreading_factor'] = int.from_bytes(data, 'big')
        elif type == b'\x05':
            lora_parameter['coding_rate'] = int.from_bytes(data, 'big')
        elif type == b'\x06':
            lora_parameter['key'] = binascii.hexlify(bytes(data))
        elif type == b'\xFF':
            with open('lora.config', 'w') as f:
                json.dump(lora_parameter, f)
                Cryptor().set_key(binascii.unhexlify(lora_parameter['key']))

            global reset, heartbeat_running
            reset = True
            heartbeat_running = True


def debounce(pin):
    global timer0
    timer0.init(mode=machine.Timer.ONE_SHOT, period=200, callback=button_handler)


def button_handler(t):
    global pin_button, pin_led_blue, heartbeat_running, button_pressed_time
    if pin_button.value() == 0:
        pin_led_blue.on()
        print('pressed')
        button_pressed_time = time.time_ns()
        timer1.init(mode=machine.Timer.ONE_SHOT, period=5000, callback=paring_mode)
        heartbeat_running = False
        timer3.deinit()
    else:
        pin_led_blue.off()
        print('unpressed')
        print(time.time_ns() - button_pressed_time)
        timer1.deinit()
        heartbeat_running = True
        timer3.init(mode=machine.Timer.PERIODIC, period=2000, callback=heartbeat)


def paring_mode(t):
    global timer0, pin_button, pin_led_blue, paring_mode_running
    timer0.deinit()
    pin_button.irq(None)
    pin_led_blue.on()
    paring_mode_running = True
    _thread.start_new_thread(blink, ())
    print("PARING MODE")

    ble = ubluetooth.BLE()
    ble.active(True)
    ble.irq(ble_handler)
    payload = ble_advertising.generate_advertising_payload(name="Infinitrack Module")
    payload2 = ble_advertising.generate_advertising_payload(
        custom_data=binascii.unhexlify("4954496e66696e69747261636b4d6f64"))

    UART_UUID = ubluetooth.UUID('6E400001-B5A3-F393-E0A9-E50E24DCCA9E')
    UART_TX = (ubluetooth.UUID('6E400003-B5A3-F393-E0A9-E50E24DCCA9E'), ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY,)
    UART_RX = (ubluetooth.UUID('6E400002-B5A3-F393-E0A9-E50E24DCCA9E'), ubluetooth.FLAG_WRITE,)
    UART_SERVICE = (UART_UUID, (UART_TX, UART_RX,),)
    SERVICES = (UART_SERVICE,)
    ble.gatts_register_services(SERVICES)

    ble.gap_advertise(150000, payload, resp_data=payload2, connectable=True)


def blink():
    global pin_led_blue
    while paring_mode_running:
        pin_led_blue.on()
        time.sleep(0.05)
        pin_led_blue.off()
        time.sleep(paring_mode_delay)


def heartbeat(t):
    global pin_led_green, pin_led_red, heartbeat_running
    if initialized:
        pin_led = pin_led_green
    else:
        pin_led = pin_led_red
    pin_led.on()
    time.sleep(0.1)
    pin_led.off()


def init_lora():
    global controller, lora

    if controller is None:
        controller = config_lora.Controller()

    if lora is not None:
        controller.reset_pin(controller.pin_reset)
        controller.transceivers['LoRa'].init(parameters={
            'frequency': 433E6,
            'tx_power_level': lora_parameter['tx_power_level'],
            'signal_bandwidth': lora_parameter['signal_bandwidth'],
            'spreading_factor': lora_parameter['spreading_factor'],
            'coding_rate': lora_parameter['coding_rate'],
            'preamble_length': 8,
            'implicitHeader': False,
            'sync_word': 0x12,
            'enable_CRC': True
        })
    else:
        lora = controller.add_transceiver(sx127x.SX127x(
            name='LoRa',
            parameters={
                'frequency': 433E6,
                'tx_power_level': lora_parameter['tx_power_level'],
                'signal_bandwidth': lora_parameter['signal_bandwidth'],
                'spreading_factor': lora_parameter['spreading_factor'],
                'coding_rate': lora_parameter['coding_rate'],
                'preamble_length': 8,
                'implicitHeader': False,
                'sync_word': 0x12,
                'enable_CRC': True
            }),
            pin_id_ss=config_lora.Controller.PIN_ID_FOR_LORA_SS,
            pin_id_RxDone=config_lora.Controller.PIN_ID_FOR_LORA_DIO0)

    lora.on_receive(on_lora_receive)
    lora.on_cad(cad)
    lora.sleep()
    if initialized:
        if 'basestation' in os.listdir():
            lora.receive()


def on_lora_receive(lora: sx127x.SX127x, payload):
    global send_timer_running
    send_timer_running = False
    print("data recv")
    if not len(payload) >= 16:
        print(f'too short: {len(payload)}')
        return
    if not payload[:4] == b'infi':
        print(f"recv incorrect: {binascii.hexlify(payload)}")
        return

    recv_addr = payload[4:10]
    if recv_addr != binascii.unhexlify(lora_parameter['myaddress']):
        print(f'recv-addr incorrect: {binascii.hexlify(recv_addr)}, {lora_parameter["myaddress"]}')
        return

    send_addr = payload[10:16]

    if 'basestation' in os.listdir():
        rssi = lora.packet_rssi()

        message_dict = dict()
        message_dict['rssi'] = rssi
        message_dict['header'] = binascii.hexlify(payload[:16])
        message_dict['payload'] = binascii.hexlify(Cryptor().decrypt(payload[16:]))

        serial.send_message_json(serial.TYPE_LORA_RECV, message_dict)


def send_position():
    global gps
    if gps.satellite_data_updated():
        print("position fixed")

        timestamp = int((gps.timestamp[0] * 3600) + (gps.timestamp[1] * 60) + (gps.timestamp[2])).to_bytes(3, 'big')  # in seconds
        date = gps.date[2].to_bytes(1, 'big') + gps.date[1].to_bytes(1, 'big') + gps.date[0].to_bytes(1, 'big')  # yyymdd
        latitude = struct.pack('>f', gps.latitude[0]) + (b'\x01' if gps.latitude[1] == 'N' else b'\x00')  # 4 bytes lat float, 1 byte is N?
        longitude = struct.pack('>f', gps.longitude[0]) + (b'\x01' if gps.longitude[1] == 'E' else b'\x00')  # 4 bytes long float, 1 byte is E?
        speed = struct.pack('>f', gps.speed[2]) # 4 bytes speed float
        course = struct.pack('>f', gps.course) # 4 bytes course float
        satellites_in_use = gps.satellites_in_use.to_bytes(1, 'big')  # 2 bytes for satellites in use
        altitude = struct.pack('>f', gps.altitude)  # 4 bytes altitude float
        pdop = struct.pack('>f', gps.pdop)  # 4 bytes pdop float

        payload_bytes = timestamp + date + latitude + longitude + speed + course + satellites_in_use + altitude + pdop  # 02 = response-type, 01 = position
        header_bytes = b'infi' + bytes(binascii.unhexlify(lora_parameter['address'])) + bytes(binascii.unhexlify(lora_parameter['myaddress']))

        payload_bytes_encrypted = Cryptor().encrypt(payload_bytes)

        response = header_bytes + payload_bytes_encrypted

        lora.printbuff(response)

    else:
        print("position N/A")
        lora.printbuff(b'infi' + bytes(binascii.unhexlify(lora_parameter['address'])) + bytes(binascii.unhexlify(lora_parameter['myaddress'])) + Cryptor().encrypt(b'\xFF\xFF'))


if __name__ == "__main__":
    main()
