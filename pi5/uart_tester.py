#!/usr/bin/env python3
"""
UART Reliability Tester - Pi 5 Host
Sends test messages to Pico and logs results to CSV.
"""

import serial
import time
import random
import string
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import config

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

class UARTTester:
    # Message length constraints (without newline)
    MIN_MSG_LEN = 18
    MAX_MSG_LEN = 40
    
    def __init__(self):
        self.running = False
        self.seq = 0
        self.csv_file = None
        self.csv_path = None
        
        # Statistics
        self.stats = {
            'total': 0,
            'ok': 0,
            'nok': 0,
            'timeout': 0,
            'error': 0,
            'rtt_sum': 0.0,
            'rtt_count': 0,
        }
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        print("\nShutting down...")
        self.running = False
    
    def _generate_payload(self) -> str:
        """Generate random payload with correct total message length (18-40 chars)"""
        # Format: seq:payload or seq:payload:crc
        # seq = 5 chars, colon = 1 char
        # crc = 4 chars + colon = 5 chars (if enabled)
        
        base_len = 6  # "00000:"
        if config.CHECKSUM_ENABLED:
            base_len += 5  # ":XXXX"
        
        # Calculate payload length range
        min_payload = self.MIN_MSG_LEN - base_len
        max_payload = self.MAX_MSG_LEN - base_len
        
        # Random length between 50-100% of max
        target_len = random.randint(
            max(min_payload, max_payload // 2),
            max_payload
        )
        
        return ''.join(random.choices(string.ascii_letters + string.digits, k=target_len))
    
    def _build_message(self, payload: str) -> str:
        """Build complete message with optional checksum"""
        seq_str = f"{self.seq:05d}"
        
        if config.CHECKSUM_ENABLED:
            data = f"{seq_str}:{payload}".encode()
            crc = crc16(data)
            return f"{seq_str}:{payload}:{crc:04X}"
        else:
            return f"{seq_str}:{payload}"
    
    def _init_csv(self):
        """Initialize CSV file with headers"""
        log_dir = Path(config.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{config.CSV_PREFIX}_{timestamp}.csv"
        self.csv_path = log_dir / filename
        
        self.csv_file = open(self.csv_path, 'w', buffering=1)  # Line buffered
        headers = [
            'timestamp',
            'seq',
            'payload_len',
            'timeout_ms',
            'checksum_enabled',
            'rtt_ms',
            'result',
            'error_detail'
        ]
        self.csv_file.write(','.join(headers) + '\n')
        print(f"Logging to: {self.csv_path}")
    
    def _log_result(self, seq: int, payload_len: int, rtt_ms: float | None, 
                    result: str, error_detail: str = ""):
        """Write result to CSV"""
        timestamp = datetime.now(timezone.utc).isoformat()
        rtt_str = f"{rtt_ms:.2f}" if rtt_ms is not None else ""
        checksum_str = "true" if config.CHECKSUM_ENABLED else "false"
        
        # Escape error detail if it contains commas
        if ',' in error_detail or '"' in error_detail:
            error_detail = f'"{error_detail.replace(chr(34), chr(34)+chr(34))}"'
        
        row = [
            timestamp,
            str(seq),
            str(payload_len),
            str(config.TIMEOUT_MS),
            checksum_str,
            rtt_str,
            result,
            error_detail
        ]
        self.csv_file.write(','.join(row) + '\n')
    
    def _update_stats(self, result: str, rtt_ms: float | None):
        """Update running statistics"""
        self.stats['total'] += 1
        
        if result == 'OK':
            self.stats['ok'] += 1
            if rtt_ms is not None:
                self.stats['rtt_sum'] += rtt_ms
                self.stats['rtt_count'] += 1
        elif result == 'NOK':
            self.stats['nok'] += 1
        elif result == 'TIMEOUT':
            self.stats['timeout'] += 1
        else:
            self.stats['error'] += 1
    
    def _print_stats(self):
        """Print current statistics"""
        s = self.stats
        avg_rtt = s['rtt_sum'] / s['rtt_count'] if s['rtt_count'] > 0 else 0
        
        print(f"\n--- Statistics ---")
        print(f"Total: {s['total']} | OK: {s['ok']} | NOK: {s['nok']} | "
              f"Timeout: {s['timeout']} | Error: {s['error']}")
        if s['rtt_count'] > 0:
            print(f"Avg RTT: {avg_rtt:.2f} ms")
        print(f"Success rate: {s['ok']/s['total']*100:.1f}%" if s['total'] > 0 else "")
    
    def run(self):
        """Main test loop"""
        print(f"UART Tester starting...")
        print(f"Port: {config.UART_PORT} @ {config.BAUD_RATE} bps")
        print(f"Timeout: {config.TIMEOUT_MS} ms | Interval: {config.SEND_INTERVAL_MS} ms")
        print(f"Checksum: {'ON' if config.CHECKSUM_ENABLED else 'OFF'}")
        print("Press Ctrl+C to stop\n")
        
        try:
            ser = serial.Serial(
                port=config.UART_PORT,
                baudrate=config.BAUD_RATE,
                timeout=config.TIMEOUT_MS / 1000.0
            )
        except serial.SerialException as e:
            print(f"Failed to open serial port: {e}")
            sys.exit(1)
        
        self._init_csv()
        self.running = True
        
        try:
            while self.running:
                # Generate and send message
                payload = self._generate_payload()
                message = self._build_message(payload)
                payload_len = len(message)
                
                start_time = time.perf_counter()
                
                try:
                    ser.write((message + '\n').encode())
                    ser.flush()
                    
                    # Wait for response
                    response = ser.readline()
                    end_time = time.perf_counter()
                    
                    rtt_ms = (end_time - start_time) * 1000
                    
                    if response:
                        response_str = response.decode('utf-8', errors='ignore').strip()
                        
                        if response_str == 'OK':
                            result = 'OK'
                            error_detail = ""
                        elif response_str == 'NOK':
                            result = 'NOK'
                            error_detail = ""
                        else:
                            result = 'ERROR'
                            error_detail = f"Unexpected response: {response_str}"
                            rtt_ms = None
                    else:
                        result = 'TIMEOUT'
                        error_detail = ""
                        rtt_ms = None
                        
                except serial.SerialException as e:
                    result = 'ERROR'
                    error_detail = str(e)
                    rtt_ms = None
                
                # Log and update stats
                self._log_result(self.seq, payload_len, rtt_ms, result, error_detail)
                self._update_stats(result, rtt_ms)
                
                # Print progress
                rtt_display = f"{rtt_ms:.1f}ms" if rtt_ms else "---"
                print(f"[{self.seq:05d}] {result:7s} RTT: {rtt_display:>8s} | "
                      f"OK: {self.stats['ok']} NOK: {self.stats['nok']} "
                      f"TO: {self.stats['timeout']}", end='\r')
                
                # Increment sequence
                self.seq = (self.seq + 1) % 100000
                
                # Wait interval before next message
                time.sleep(config.SEND_INTERVAL_MS / 1000.0)
                
        finally:
            self._print_stats()
            if self.csv_file:
                self.csv_file.close()
                print(f"\nLog saved to: {self.csv_path}")
            ser.close()

def main():
    tester = UARTTester()
    tester.run()

if __name__ == "__main__":
    main()
