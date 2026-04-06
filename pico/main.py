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

def apply_brightness(color, brightness):
    """Apply brightness (0.0-1.0) to color tuple"""
    return tuple(int(c * brightness) for c in color)

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
    if config.NEOPIXEL_FORMAT in ("RGBW", "GRBW"):
        np = NeoPixel(pin, config.NEOPIXEL_COUNT, bpp=4)
    else:
        np = NeoPixel(pin, config.NEOPIXEL_COUNT)
    brightness = getattr(config, 'NEOPIXEL_BRIGHTNESS', 1.0)
    
    while neopixel_running:
        for i in range(config.NEOPIXEL_COUNT):
            color_pos = (i * 256 // config.NEOPIXEL_COUNT + rainbow_offset) & 255
            r, g, b = wheel(color_pos)
            r, g, b = apply_brightness((r, g, b), brightness)
            np[i] = format_color(r, g, b, config.NEOPIXEL_FORMAT)
        np.write()
        rainbow_offset = (rainbow_offset + 1) & 255
        time.sleep_ms(20)

def main():
    global neopixel_running
    
    # Initialize UART (UART1 uses GP4=TX, GP5=RX by default)
    uart = UART(config.UART_ID, config.BAUD_RATE)
    
    # Start neopixel animation in background thread
    if NEOPIXEL_AVAILABLE:
        _thread.start_new_thread(neopixel_thread, ())
    
    buffer = ""
    heartbeat_interval_ms = 5000
    last_heartbeat = time.ticks_ms()
    msg_count = 0
    
    print(f"UART Tester started - UART{config.UART_ID} @ {config.BAUD_RATE} bps")
    print(f"Checksum: {'ON' if config.CHECKSUM_ENABLED else 'OFF'}")
    print(f"Neopixel: {config.NEOPIXEL_COUNT} LEDs on GP{config.NEOPIXEL_PIN}")
    print("Waiting for UART messages...")
    
    while True:
        now = time.ticks_ms()
        
        # Heartbeat
        if time.ticks_diff(now, last_heartbeat) >= heartbeat_interval_ms:
            print(f"[HEARTBEAT] uptime: {now // 1000}s, msgs: {msg_count}")
            last_heartbeat = now
        
        # Check for incoming data
        if uart.any():
            try:
                data = uart.read(uart.any())
                if data:
                    buffer += data.decode('utf-8', 'ignore')
                    
                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        print(f"[DEBUG] raw line: {repr(line)}")
                        valid, seq, payload, has_checksum = parse_message(line)
                        print(f"[DEBUG] parsed: valid={valid}, seq={seq}, has_crc={has_checksum}")
                        msg_count += 1
                        
                        if valid:
                            uart.write(b"OK\n")
                            print(f"[RX] #{seq} len={len(line)} -> OK")
                        else:
                            uart.write(b"NOK\n")
                            print(f"[RX] invalid: {line[:50]} -> NOK")
            except Exception as e:
                uart.write(b"NOK\n")
                print(f"[ERR] {e}")
                buffer = ""
        
        time.sleep_ms(1)

if __name__ == "__main__":
    main()
