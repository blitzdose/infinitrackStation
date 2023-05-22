# InfiniTrack

<p align="center">
<img src="https://github.com/blitzdose/InfiniTrack/blob/main/src/main/resources/META-INF/resources/icons/icon.png" width="200">
</p>


Ein System zur Positionsverfolgung mit GPS und LoRa! Entstanden im Rahmen der Studienarbeit an der DHBW Karlsruhe.

Dies ist der Code für die **Mikrocontroller**. Das Webinterface ist [hier](https://github.com/blitzdose/InfiniTrack) zu finden

## Firmware auf LOLIN32 schreiben

1. Lade dir die aktuellste Firmware herunter. [Download](https://github.com/blitzdose/infinitrackStation/releases)
2. Abhängigkeiten installieren `pip install esptool`
3. Firmware auf den Mikrocontroller schreiben <br> `esptool.py --chip esp32 --port <COM-Port> write_flash infinitrack-firmware-<version>.bin`
