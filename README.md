# UART Reliability Tester

UART kommunikáció megbízhatósági tesztelése Raspberry Pi 5 és Raspberry Pi Pico között.

## Architektúra

```
┌─────────────┐     hosszú kábel     ┌─────────────┐
│   Pi 5      │◄───────────────────►│    Pico     │
│ (USB-UART)  │      UART 4800bps    │ (UART1)     │
│             │                      │ + Neopixel  │
└─────────────┘                      └─────────────┘
```

## Funkciók

- **Konfigurálható baud rate** (default: 4800 bps)
- **Konfigurálható timeout és küldési intervallum**
- **Opcionális CRC-16 checksum**
- **CSV logging** minden üzenetváltásról
- **Háttérben futó Neopixel animáció** a Pico-n (rainbow loop)
- **Systemd service** a Pi 5-ön (logout-túlélő)

## Telepítés

### Pi 5

```bash
# Másold át a fájlokat
scp -r pi5/ pi@<PI_IP>:~/uart-tester/

# SSH a Pi-re
ssh pi@<PI_IP>

# Függőségek
cd ~/uart-tester/pi5
pip3 install -r requirements.txt

# Systemd service telepítése (opcionális)
sudo cp uart-tester.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### Pico

1. Telepíts MicroPython-t a Pico-ra
2. Másold át a `pico/` mappa tartalmát a Pico-ra (Thonny vagy mpremote)
   ```bash
   mpremote cp pico/config.py :config.py
   mpremote cp pico/main.py :main.py
   ```

## Bekötés

### UART kapcsolat

| Pi 5 USB-UART | Pico |
|---------------|------|
| TX | GP5 (UART1 RX) |
| RX | GP4 (UART1 TX) |
| GND | GND |

### Neopixel (opcionális)

| Pico | Neopixel |
|------|----------|
| GP2 | DIN |
| 3.3V vagy 5V | VCC |
| GND | GND |

## Konfiguráció

### Pi 5 (`pi5/config.py`)

```python
UART_PORT = "/dev/ttyUSB0"  # USB-UART adapter port
BAUD_RATE = 4800
SEND_INTERVAL_MS = 200      # Várakozás küldések között
TIMEOUT_MS = 500            # Válasz timeout
CHECKSUM_ENABLED = True     # CRC-16 ellenőrzés
CSV_PREFIX = "uart_test"    # Log fájl prefix
LOG_DIR = "./logs"          # Log mappa
```

### Pico (`pico/config.py`)

```python
BAUD_RATE = 4800
UART_ID = 1
UART_TX_PIN = 4
UART_RX_PIN = 5
NEOPIXEL_PIN = 2
NEOPIXEL_COUNT = 8
NEOPIXEL_FORMAT = "GRB"     # RGB, GRB, RGBW, GRBW
CHECKSUM_ENABLED = True
```

## Használat

### Manuális futtatás

```bash
cd ~/uart-tester/pi5
python3 uart_tester.py
```

### Systemd service

```bash
# Indítás
sudo systemctl start uart-tester

# Leállítás
sudo systemctl stop uart-tester

# Logok megtekintése
journalctl -u uart-tester -f
```

## Protokoll

### Üzenet formátum

**Pi → Pico (checksum OFF):**
```
<seq>:<payload>\n
```

**Pi → Pico (checksum ON):**
```
<seq>:<payload>:<crc>\n
```

- `seq`: 5 számjegyű sorszám (00000-99999)
- `payload`: random alfanumerikus karakterek
- `crc`: 4 hex karakter (CRC-16 CCITT)
- Teljes hossz (newline nélkül): 18-40 karakter

**Pico → Pi:**
```
OK\n   - sikeres fogadás
NOK\n  - hibás üzenet
```

## CSV output

| Oszlop | Leírás |
|--------|--------|
| timestamp | ISO 8601 UTC |
| seq | Üzenet sorszám |
| payload_len | Üzenet hossza |
| timeout_ms | Beállított timeout |
| checksum_enabled | Checksum be/ki |
| rtt_ms | Round-trip time (ms) |
| result | OK / NOK / TIMEOUT / ERROR |
| error_detail | Hiba részlet |

## Hibaelhárítás

1. **Permission denied a serial porton:**
   ```bash
   sudo usermod -a -G dialout $USER
   # Majd logout/login
   ```

2. **Nincs válasz a Pico-tól:**
   - Ellenőrizd a bekötést (TX↔RX keresztbe!)
   - Ellenőrizd, hogy a baud rate egyezik mindkét oldalon

3. **Sok timeout:**
   - Növeld a `TIMEOUT_MS` értéket
   - Csökkentsd a `BAUD_RATE`-et
