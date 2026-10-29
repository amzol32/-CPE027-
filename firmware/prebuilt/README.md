# Prebuilt firmware (ESP32-S3)

`soil_dsp_esp32s3_merged.bin` is `firmware/soil_dsp` compiled with esp32 core 3.0.7, board *ESP32S3 Dev Module*,
default options (4 MB flash map, QIO 80 MHz, USB CDC On Boot disabled, so `Serial` is on the UART/COM port at 115200).
It works on boards with 4 MB or more of flash. It has no Wi-Fi credentials, so it starts its own network:
SSID `SoilDSP`, password `soildsp123`, dashboard at http://192.168.4.1/.

Flash the whole image at address 0x0, through the board's UART/COM USB port:

```bash
pip install esptool
esptool.py --chip esp32s3 --baud 460800 write_flash 0x0 soil_dsp_esp32s3_merged.bin
```

Or, with no install, in Chrome/Edge: https://espressif.github.io/esptool-js/ -> Connect -> address 0x0 -> choose the file -> Program.

To use your own Wi-Fi, or after any code change, build from source with the Arduino IDE instead.
Rebuild this image whenever `firmware/soil_dsp` changes (Sketch -> Export Compiled Binary, take the `.merged.bin`).

SHA-256: cc1bff1e17a11c9ae7e0ba9583cec25f31a044a3778b497049843427f7c68040
