import gc

PA_OUTPUT_RFO_PIN = 0
PA_OUTPUT_PA_BOOST_PIN = 1

# registers
REG_FIFO = 0x00
REG_OP_MODE = 0x01
REG_FRF_MSB = 0x06
REG_FRF_MID = 0x07
REG_FRF_LSB = 0x08
REG_PA_CONFIG = 0x09
REG_LNA = 0x0c
REG_FIFO_ADDR_PTR = 0x0d

REG_FIFO_TX_BASE_ADDR = 0x0e
FifoTxBaseAddr = 0x00
# FifoTxBaseAddr = 0x80

REG_FIFO_RX_BASE_ADDR = 0x0f
FifoRxBaseAddr = 0x00
REG_FIFO_RX_CURRENT_ADDR = 0x10
REG_IRQ_FLAGS_MASK = 0x11
REG_IRQ_FLAGS = 0x12
REG_RX_NB_BYTES = 0x13
REG_PKT_RSSI_VALUE = 0x1a
REG_PKT_SNR_VALUE = 0x1b
REG_MODEM_CONFIG_1 = 0x1d
REG_MODEM_CONFIG_2 = 0x1e
REG_PREAMBLE_MSB = 0x20
REG_PREAMBLE_LSB = 0x21
REG_PAYLOAD_LENGTH = 0x22
REG_FIFO_RX_BYTE_ADDR = 0x25
REG_MODEM_CONFIG_3 = 0x26
REG_RSSI_WIDEBAND = 0x2c
REG_DETECTION_OPTIMIZE = 0x31
REG_DETECTION_THRESHOLD = 0x37
REG_SYNC_WORD = 0x39
REG_DIO_MAPPING_1 = 0x40
REG_VERSION = 0x42

# modes
MODE_LONG_RANGE_MODE = 0x80  # bit 7: 1 => LoRa mode
MODE_SLEEP = 0x00
MODE_STDBY = 0x01
MODE_TX = 0x03
MODE_RX_CONTINUOUS = 0x05
MODE_RX_SINGLE = 0x06

# PA config
PA_BOOST = 0x80

# IRQ masks
IRQ_TX_DONE_MASK = 0x08
IRQ_PAYLOAD_CRC_ERROR_MASK = 0x20
IRQ_RX_DONE_MASK = 0x40
IRQ_RX_TIME_OUT_MASK = 0x80

# Buffer size
MAX_PKT_LENGTH = 255


class SX127x:

    # The controller can be ESP8266, ESP32, Raspberry Pi, or a PC.
    # The controller needs to provide an interface consisted of:
    # 1. a SPI, with transfer function.
    # 2. a reset pin, with low(), high() functions.
    # 3. IRQ pinS , to be triggered by RFM96W's DIO0~5 pins. These pins each has two functions:
    #   3.1 set_handler_for_irq_on_rising_edge() 
    #   3.2 detach_irq()
    # 4. a function to blink on-board LED. 

    def __init__(self,
                 name='SX127x',
                 parameters=None,
                 on_receive=None):

        if parameters is None:
            parameters = {'frequency': 433E6, 'tx_power_level': 20, 'signal_bandwidth': 125E3,
                          'spreading_factor': 8, 'coding_rate': 5, 'preamble_length': 8,
                          'implicitHeader': False, 'sync_word': 0x12, 'enable_CRC': False}
        self.name = name
        self.parameters = parameters
        self._onReceive = on_receive
        self._lock = False
        self._implicitHeaderMode = None
        self._frequency = None

    def init(self, parameters=None):
        if parameters:
            self.parameters = parameters

        # check version
        version = self.read_register(REG_VERSION)
        print(f'Version: {version}')
        if version != 0x12:
            raise Exception(f'Invalid version: {version}')

        # put in LoRa and sleep mode
        self.sleep()

        # config
        self.set_frequency(self.parameters['frequency'])
        self.set_signal_bandwidth(self.parameters['signal_bandwidth'])

        # set LNA boost
        self.write_register(REG_LNA, self.read_register(REG_LNA) | 0x03)

        # set auto AGC
        self.write_register(REG_MODEM_CONFIG_3, 0x04)

        self.set_tx_power(self.parameters['tx_power_level'])
        self._implicitHeaderMode = None
        self.implicit_header_mode(self.parameters['implicitHeader'])
        self.set_spreading_factor(self.parameters['spreading_factor'])
        self.set_coding_rate(self.parameters['coding_rate'])
        self.set_preamble_length(self.parameters['preamble_length'])
        self.set_sync_word(self.parameters['sync_word'])
        self.enable_crc(self.parameters['enable_CRC'])

        # set LowDataRateOptimize flag if symbol time > 16ms (default disable on reset)
        if 1000 / (self.parameters['signal_bandwidth'] / 2 ** self.parameters['spreading_factor']) > 16:
            self.write_register(REG_MODEM_CONFIG_3, self.read_register(REG_MODEM_CONFIG_3) | 0x08)

        # set base addresses
        self.write_register(REG_FIFO_TX_BASE_ADDR, FifoTxBaseAddr)
        self.write_register(REG_FIFO_RX_BASE_ADDR, FifoRxBaseAddr)

        self.standby()

    def begin_packet(self, implicit_header_mode=False):
        self.standby()
        self.implicit_header_mode(implicit_header_mode)

        # reset FIFO address and paload length 
        self.write_register(REG_FIFO_ADDR_PTR, FifoTxBaseAddr)
        self.write_register(REG_PAYLOAD_LENGTH, 0)

    def end_packet(self):
        # put in TX mode
        self.write_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_TX)

        # wait for TX done, standby automatically on TX_DONE
        while (self.read_register(REG_IRQ_FLAGS) & IRQ_TX_DONE_MASK) == 0:
            pass

            # clear IRQ's
        self.write_register(REG_IRQ_FLAGS, IRQ_TX_DONE_MASK)

        self.collect_garbage()

    def write(self, buffer):
        current_length = self.read_register(REG_PAYLOAD_LENGTH)
        size = len(buffer)

        # check size
        size = min(size, (MAX_PKT_LENGTH - FifoTxBaseAddr - current_length))

        # write data
        for i in range(size):
            self.write_register(REG_FIFO, buffer[i])

        # update length        
        self.write_register(REG_PAYLOAD_LENGTH, current_length + size)
        return size

    def aquire_lock(self, lock=False):
        pass

    def println(self, string, implict_header=False):
        self.aquire_lock(True)  # wait until RX_Done, lock and begin writing.

        self.begin_packet(implict_header)
        self.write(string.encode())
        self.end_packet()

        self.aquire_lock(False)  # unlock when done writing

    def get_irq_flags(self):
        irq_flags = self.read_register(REG_IRQ_FLAGS)
        self.write_register(REG_IRQ_FLAGS, irq_flags)
        return irq_flags

    def packet_rssi(self):
        return self.read_register(REG_PKT_RSSI_VALUE) - (164 if self._frequency < 868E6 else 157)

    def packet_snr(self):
        return (self.read_register(REG_PKT_SNR_VALUE)) * 0.25

    def standby(self):
        self.write_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY)

    def sleep(self):
        self.write_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_SLEEP)

    def set_tx_power(self, level, output_pin=PA_OUTPUT_PA_BOOST_PIN):
        if output_pin == PA_OUTPUT_RFO_PIN:
            # RFO
            level = min(max(level, 0), 14)
            self.write_register(REG_PA_CONFIG, 0x70 | level)

        else:
            # PA BOOST                
            level = min(max(level, 2), 17)
            self.write_register(REG_PA_CONFIG, PA_BOOST | (level - 2))

    def set_frequency(self, frequency):
        self._frequency = frequency

        frfs = {169E6: (42, 64, 0),
                433E6: (108, 64, 0),
                434E6: (108, 128, 0),
                866E6: (216, 128, 0),
                868E6: (217, 0, 0),
                915E6: (228, 192, 0)}

        self.write_register(REG_FRF_MSB, frfs[frequency][0])
        self.write_register(REG_FRF_MID, frfs[frequency][1])
        self.write_register(REG_FRF_LSB, frfs[frequency][2])

    def set_spreading_factor(self, sf):
        sf = min(max(sf, 6), 12)
        self.write_register(REG_DETECTION_OPTIMIZE, 0xc5 if sf == 6 else 0xc3)
        self.write_register(REG_DETECTION_THRESHOLD, 0x0c if sf == 6 else 0x0a)
        self.write_register(REG_MODEM_CONFIG_2, (self.read_register(REG_MODEM_CONFIG_2) & 0x0f) | ((sf << 4) & 0xf0))

    def set_signal_bandwidth(self, sbw):
        bins = (7.8E3, 10.4E3, 15.6E3, 20.8E3, 31.25E3, 41.7E3, 62.5E3, 125E3, 250E3)

        bw = 9
        for i in range(len(bins)):
            if sbw <= bins[i]:
                bw = i
                break

        # bw = bins.index(sbw)

        self.write_register(REG_MODEM_CONFIG_1, (self.read_register(REG_MODEM_CONFIG_1) & 0x0f) | (bw << 4))

    def set_coding_rate(self, denominator):
        denominator = min(max(denominator, 5), 8)
        cr = denominator - 4
        self.write_register(REG_MODEM_CONFIG_1, (self.read_register(REG_MODEM_CONFIG_1) & 0xf1) | (cr << 1))

    def set_preamble_length(self, length):
        self.write_register(REG_PREAMBLE_MSB, (length >> 8) & 0xff)
        self.write_register(REG_PREAMBLE_LSB, (length >> 0) & 0xff)

    def enable_crc(self, enable_crc=False):
        modem_config_2 = self.read_register(REG_MODEM_CONFIG_2)
        config = modem_config_2 | 0x04 if enable_crc else modem_config_2 & 0xfb
        self.write_register(REG_MODEM_CONFIG_2, config)

    def set_sync_word(self, sw):
        self.write_register(REG_SYNC_WORD, sw)

    def implicit_header_mode(self, implicit_header_mode=False):
        if self._implicitHeaderMode != implicit_header_mode:  # set value only if different.
            self._implicitHeaderMode = implicit_header_mode
            modem_config_1 = self.read_register(REG_MODEM_CONFIG_1)
            config = modem_config_1 | 0x01 if implicit_header_mode else modem_config_1 & 0xfe
            self.write_register(REG_MODEM_CONFIG_1, config)

    def on_receive(self, callback):
        self._onReceive = callback

        if self.pin_RxDone:
            if callback:
                self.write_register(REG_DIO_MAPPING_1, 0x00)
                self.pin_RxDone.set_handler_for_irq_on_rising_edge(handler=self.handle_on_receive)
            else:
                self.pin_RxDone.detach_irq()

    def receive(self, size=0):
        self.implicit_header_mode(size > 0)
        if size > 0:
            self.write_register(REG_PAYLOAD_LENGTH, size & 0xff)

        # The last packet always starts at FIFO_RX_CURRENT_ADDR
        # no need to reset FIFO_ADDR_PTR
        self.write_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_RX_CONTINUOUS)

        # on RPi, interrupt callback is threaded and racing with main thread,

    # Needs a lock for accessing FIFO.
    # https://sourceforge.net/p/raspberry-gpio-python/wiki/Inputs/
    # http://raspi.tv/2013/how-to-use-interrupts-with-python-on-the-raspberry-pi-and-rpi-gpio-part-2
    def handle_on_receive(self, event_source):
        self.aquire_lock(True)  # lock until TX_Done

        # irqFlags = self.getIrqFlags() should be 0x50
        if (self.get_irq_flags() & IRQ_PAYLOAD_CRC_ERROR_MASK) == 0:
            if self._onReceive:
                payload = self.read_payload()
                self.aquire_lock(False)  # unlock when done reading

                self._onReceive(self, payload)

        self.aquire_lock(False)  # unlock in any case.

    def received_packet(self, size=0):
        irq_flags = self.get_irq_flags()

        self.implicit_header_mode(size > 0)
        if size > 0:
            self.write_register(REG_PAYLOAD_LENGTH, size & 0xff)

        # if (irqFlags & IRQ_RX_DONE_MASK) and \
        # (irqFlags & IRQ_RX_TIME_OUT_MASK == 0) and \
        # (irqFlags & IRQ_PAYLOAD_CRC_ERROR_MASK == 0):

        if irq_flags == IRQ_RX_DONE_MASK:  # RX_DONE only, irqFlags should be 0x40
            # automatically standby when RX_DONE
            return True

        elif self.read_register(REG_OP_MODE) != (MODE_LONG_RANGE_MODE | MODE_RX_SINGLE):
            # no packet received.            
            # reset FIFO address / # enter single RX mode
            self.write_register(REG_FIFO_ADDR_PTR, FifoRxBaseAddr)
            self.write_register(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_RX_SINGLE)

    def read_payload(self):
        # set FIFO address to current RX address
        # fifo_rx_current_addr = self.readRegister(REG_FIFO_RX_CURRENT_ADDR)
        self.write_register(REG_FIFO_ADDR_PTR, self.read_register(REG_FIFO_RX_CURRENT_ADDR))

        # read packet length
        packet_length = self.read_register(REG_PAYLOAD_LENGTH) if self._implicitHeaderMode else \
            self.read_register(REG_RX_NB_BYTES)

        payload = bytearray()
        for i in range(packet_length):
            payload.append(self.read_register(REG_FIFO))

        self.collect_garbage()
        return bytes(payload)

    def read_register(self, address, byteorder='big', signed=False):
        response = self.transfer(self.pin_ss, address & 0x7f)
        return int.from_bytes(response, byteorder)

    def write_register(self, address, value):
        self.transfer(self.pin_ss, address | 0x80, value)

    def collect_garbage(self):
        gc.collect()
        print('[Memory - free: {}   allocated: {}]'.format(gc.mem_free(), gc.mem_alloc()))
