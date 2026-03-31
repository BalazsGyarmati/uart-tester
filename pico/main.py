import time
import random
from machine import UART, Pin
import _thread
import config

try:
    from neopixel import NeoPixel
    NEOPIXEL_AVAILABLE = True
except ImportError:
    NEOPIXEL_AVAILABLE = False

# CRC-16 CCITT implementation
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

def verify_checksum(seq: str, payload: str, received_crc: str) -> bool:
    data = f"{seq}:{payload}".encode()
    calculated = crc16(data)
    try:
        received = int(received_crc, 16)
        return calculated == received
    except ValueError:
        return False

def parse_message(line: str) -> tuple:
    """Parse incoming message. Returns (valid, seq, payload, checksum_present)"""
    line = line.strip()
    if not line:
        return False, None, None, False
    
    parts = line.split(':')
    
    if len(parts) == 2:
        seq, payload = parts
        if len(seq) == 5 and seq.isdigit():
            return True, seq, payload, False
        return False, None, None, False
    
    elif len(parts) == 3:
        seq, payload, crc = parts
        if len(seq) == 5 and seq.isdigit() and len(crc) == 4:
            if config.CHECKSUM_ENABLED:
                valid = verify_checksum(seq, payload, crc)
                return valid, seq, payload, True
            else:
                return True, seq, payload, True
        return False, None, None, True
    
    return False, None, None, False

# Neopixel color format mapping
FORMAT_MAP = {
    "RGB": (0, 1, 2, -1),
    "GRB": (1, 0, 2, -1),
    "RGBW": (0, 1, 2, 3),
    "GRBW": (1, 0, 2, 3),
}

def wheel(pos):
    """Generate rainbow colors (0-255)"""
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    else:
        pos -= 170
        return (pos * 3, 0, 255 - pos * 3)

def format_color(r, g, b, fmt):
    """Convert RGB to configured format"""
    order = FORMAT_MAP.get(fmt, (0, 1, 2, -1))
    rgb = [r, g, b]
    if order[3] >= 0:  # RGBW format
        return (rgb[order[0]], rgb[order[1]], rgb[order[2]], 0)
    return (rgb[order[0]], rgb[order[1]], rgb[order[2]])

# Global state for neopixel animation
neopixel_running = True
rainbow_offset = 0

def neopixel_thread():
    """Background thread for rainbow animation"""
    global rainbow_offset, neopixel_running
    
    if not NEOPIXEL_AVAILABLE:
        return
    
    pin = Pin(config.NEOPIXEL_PIN, Pin.OUT)
    np = NeoPixel(pin, config.NEOPIXEL_COUNT)
    
    while neopixel_running:
        for i in range(config.NEOPIXEL_COUNT):
            color_pos = (i * 256 // config.NEOPIXEL_COUNT + rainbow_offset) & 255
            r, g, b = wheel(color_pos)
            np[i] = format_color(r, g, b, config.NEOPIXEL_FORMAT)
        np.write()
        rainbow_offset = (rainbow_offset + 1) & 255
        time.sleep_ms(20)

def main():
    global neopixel_running
    
    # Initialize UART
    uart = UART(
        config.UART_ID,
        baudrate=config.BAUD_RATE,
        tx=Pin(config.UART_TX_PIN),
        rx=Pin(config.UART_RX_PIN)
    )
    
    # Start neopixel animation in background thread
    if NEOPIXEL_AVAILABLE:
        _thread.start_new_thread(neopixel_thread, ())
    
    buffer = ""
    
    print(f"UART Tester started - UART{config.UART_ID} @ {config.BAUD_RATE} bps")
    print(f"Checksum: {'ON' if config.CHECKSUM_ENABLED else 'OFF'}")
    
    while True:
        # Check for incoming data
        if uart.any():
            try:
                data = uart.read()
                if data:
                    buffer += data.decode('utf-8', errors='ignore')
                    
                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        valid, seq, payload, has_checksum = parse_message(line)
                        
                        if valid:
                            uart.write(b"OK\n")
                        else:
                            uart.write(b"NOK\n")
            except Exception as e:
                uart.write(b"NOK\n")
                buffer = ""
        
        time.sleep_ms(1)

if __name__ == "__main__":
    main()
