import machine

import urandom

from libraries import config_lora, sx127x


class LoraSender:
    def __init__(self, lora_parameter, ready_callback):
        self.timer3 = machine.Timer(3)
        self.ready_callback = ready_callback

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

        self.lora.on_cad(self.__cad)
        self.sleep()

    def __cad(self, detected):
        self.lora.standby()
        if detected == 0:
            self.ready_callback()
            self.sleep()
        else:
            self.sleep()
            wait_time = urandom.randint(50, 100)
            self.timer3.init(mode=machine.Timer.ONE_SHOT, period=wait_time, callback=self.activity_detection)

    def activity_detection(self, t):
        self.lora.standby()
        self.lora.cad()

    def send_data(self, data):
        self.lora.printbuff(data)
        self.sleep()

    def sleep(self):
        self.lora.sleep()

    def stop_sending(self):
        self.lora.on_cad(None)
        self.timer3.deinit()
