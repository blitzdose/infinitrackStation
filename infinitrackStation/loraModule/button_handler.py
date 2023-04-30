import machine
import time


class ButtonHandler:

    def __init__(self, pin: machine.Pin, short_click_callback, long_click_callback, hold_callback):
        self.timer0 = machine.Timer(0)
        self.timer1 = machine.Timer(1)

        self.pin = pin
        self.short_click_callback = short_click_callback
        self.long_click_callback = long_click_callback
        self.hold_callback = hold_callback

        self.pressed_time = 0

        pin.irq(self.__debounce, machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING)

    def deinit(self):
        self.pin.irq(None)
        self.timer0.deinit()
        self.timer1.deinit()

    def __debounce(self, pin):
        self.timer0.init(mode=machine.Timer.ONE_SHOT, period=200, callback=self.__click_handler)

    def __click_handler(self, t):
        if self.pin.value() == 0:
            if self.hold_callback is not None:
                self.hold_callback(True)
            self.pressed_time = time.time_ns()
            self.timer1.init(mode=machine.Timer.ONE_SHOT, period=5000, callback=self.__long_click_handler)
        else:
            self.timer1.deinit()
            if self.hold_callback is not None:
                self.hold_callback(False)
            if self.pressed_time + 1e9 > time.time_ns():
                if self.short_click_callback is not None:
                    self.short_click_callback()

    def __long_click_handler(self, t):
        if self.long_click_callback is not None:
            self.long_click_callback()
