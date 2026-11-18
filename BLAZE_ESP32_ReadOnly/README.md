# BLAZE ESP32 Read-only Monitor

This is an incremental upgrade from the simulation-only Streamlit dashboard.
It can receive **actual MAX6675 temperature measurements** from an ESP32 during
a supervised, low-voltage, ambient-temperature bench test.

## Safety boundary

This project is read-only. The new firmware has no servo, valve, relay, heater,
burner, or kiln-control code. Do not combine this software with the previous
servo/valve firmware.

For the first actual sensor test:
- Use a low-voltage ESP32 + MAX6675 bench setup only.
- Keep the thermocouple probe at room/ambient temperature.
- Keep all burner, LPG, heater, flame, reactor, and kiln equipment disconnected.
- Do not use the app or ESP32 as a safety system or to conduct a pyrolysis run.
- Have a knowledgeable adult supervise the wiring and bench test.

The 300–500 °C band is a research display reference only, not an operating
instruction, control threshold, or safety limit.

## 1. Files

```text
BLAZE_ESP32_ReadOnly/
├── app.py
├── api.py
├── database.py
├── requirements.txt
├── README.md
├── data/
└── esp32/
    └── blaze_monitor.ino
```

## 2. Install and run in VS Code (Windows)

Open this folder in VS Code, then Terminal > New Terminal:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Generate a random API token:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output. In the same terminal, set it:

```powershell
$env:BLAZE_DEVICE_TOKEN="PASTE_GENERATED_TOKEN"
```

Start the API in Terminal 1:

```powershell
uvicorn api:app --host 0.0.0.0 --port 8000
```

Start Streamlit in Terminal 2 (activate the same .venv first):

```powershell
.venv\Scripts\Activate.ps1
streamlit run app.py
```

Open `http://localhost:8501`.

## 3. Configure the ESP32 sketch

Open `esp32/blaze_monitor.ino` in Arduino IDE.

Install a compatible MAX6675 library. Select your ESP32 board and port.

Edit:
- `WIFI_SSID`
- `WIFI_PASSWORD`
- `API_URL`: replace `192.168.1.100` with your computer's private IPv4 address
- `DEVICE_TOKEN`: paste the same token used in the API terminal

Find the computer's private IPv4 address with:

```powershell
ipconfig
```

Use the IPv4 address of the active Wi-Fi adapter, for example
`http://192.168.1.100:8000/telemetry`.

Keep the ESP32 and computer on the same trusted private Wi-Fi network.
Allow Python through Windows Firewall only on a private network if prompted.
Do not use router port forwarding and do not expose port 8000 publicly.

## 4. Safe bench test sequence

1. Keep the thermocouple at room temperature and all high-temperature/gas equipment disconnected.
2. Connect the MAX6675 module to the ESP32 according to the module and board documentation. Confirm voltage compatibility before powering it.
3. Start the API and Streamlit dashboard.
4. Upload `blaze_monitor.ino` to the ESP32.
5. Open Arduino Serial Monitor at 115200 baud.
6. Look for a temperature reading and a successful HTTP response (2xx).
7. In the Streamlit Dashboard, confirm that the latest value and chart update.
8. If the probe is not detected, the app should show a sensor fault / invalid reading.

The common MAX6675 SPI signal mapping in this sketch is SCK=18, CS=23, SO=19.
Power and ground must follow the exact MAX6675 breakout-board and ESP32 specifications.
Do not connect any servo or valve to this project.

## 5. Troubleshooting

- API 401: the token in the sketch does not match `BLAZE_DEVICE_TOKEN`.
- API 503: the API terminal does not have the token environment variable set.
- API 422: payload is malformed or temperature is outside the accepted sensor range.
- HTTP -1 / connection failure: check PC IP, same Wi-Fi, API terminal, and private firewall rule.
- Dashboard says stale: check Serial Monitor and API responses.
- Sensor fault at ambient: check the MAX6675 module, thermocouple connection, signal pins, and voltage compatibility with adult supervision.

## 6. Network/security notes

The example uses plain HTTP on a private LAN for a local demonstration. It is not
suitable for public hosting. The device token is visible in the firmware source,
so treat it as a demo credential. Do not commit Wi-Fi passwords or tokens to a
public GitHub repository.
