from libraries import config_lora, sx127x


class LoraReceiver:
    def __init__(self, lora_parameter):
        self.controller = config_lora.Controller()
        self.callback = None

        self.lora = self.controller.add_transceiver(sx127x.SX127x(
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

        self.lora.on_receive(self.__lora_receive_handler)
        self.lora.receive()

    def set_receive_callback(self, callback):
        self.callback = callback

    def __lora_receive_handler(self, lora: sx127x.SX127x, payload):
        if self.callback is not None:
            self.callback(payload, lora.packet_rssi())
