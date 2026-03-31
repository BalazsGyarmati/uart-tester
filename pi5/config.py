# Pi 5 UART Tester Configuration

# UART settings
UART_PORT = "/dev/ttyUSB0"
BAUD_RATE = 4800

# Timing settings (milliseconds)
SEND_INTERVAL_MS = 200
TIMEOUT_MS = 500

# Protocol settings
CHECKSUM_ENABLED = True

# Logging settings
CSV_PREFIX = "uart_test"
LOG_DIR = "./logs"
