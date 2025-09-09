#!/usr/bin/env python3
"""
RemBraille Dummy Server
A test server for RemBraille NVDA add-on development

This server simulates a braille display host and displays all messages
received from the RemBraille NVDA driver. Useful for testing and debugging.

Usage:
    python rembraille_server.py [--port PORT] [--cells CELLS] [--verbose]

Copyright (C) 2025 Stefan Lohmaier
Licensed under GNU GPL v2
"""

import socket
import struct
import threading
import time
import argparse
import sys
import signal
import os
import platform
import re
from typing import Optional, Dict, Any, List
from datetime import datetime


# Terminal control functions
def clear_screen():
    """Clear the terminal screen"""
    if platform.system() == 'Windows':
        os.system('cls')
    else:
        os.system('clear')

def move_cursor(row: int, col: int):
    """Move cursor to specific position"""
    if platform.system() != 'Windows':
        sys.stdout.write(f'\033[{row};{col}H')
    # Windows doesn't support ANSI escape codes well without special setup

# Unicode fallback for terminals that don't support UTF-8
def safe_print(text: str, end='\n'):
    """Print text with fallback for non-UTF-8 terminals"""
    try:
        print(text, end=end)
    except UnicodeEncodeError:
        # Replace Unicode characters with ASCII alternatives
        safe_text = text.replace("🚀", "[START]")
        safe_text = safe_text.replace("📡", "[LISTEN]")
        safe_text = safe_text.replace("📄", "[CELLS]")
        safe_text = safe_text.replace("🔧", "[MODE]")
        safe_text = safe_text.replace("⏰", "[TIME]")
        safe_text = safe_text.replace("🔌", "[CLIENT]")
        safe_text = safe_text.replace("❌", "[ERROR]")
        safe_text = safe_text.replace("✅", "[OK]")
        safe_text = safe_text.replace("⚠️", "[WARN]")
        safe_text = safe_text.replace("🛑", "[STOP]")
        safe_text = safe_text.replace("📨", "[MSG]")
        safe_text = safe_text.replace("🤝", "[HANDSHAKE]")
        safe_text = safe_text.replace("📏", "[SIZE]")
        safe_text = safe_text.replace("🔤", "[BRAILLE]")
        safe_text = safe_text.replace("📝", "[TEXT]")
        safe_text = safe_text.replace("🔢", "[HEX]")
        safe_text = safe_text.replace("🏓", "[PING]")
        safe_text = safe_text.replace("⌨️", "[KEY]")
        safe_text = safe_text.replace("❓", "[UNKNOWN]")
        safe_text = safe_text.replace("📊", "[STATS]")
        safe_text = safe_text.replace("⏱️", "[UPTIME]")
        safe_text = safe_text.replace("👥", "[CLIENTS]")
        safe_text = safe_text.replace("💡", "[INFO]")
        safe_text = safe_text.replace("⠀", " ")  # Braille space
        # Replace all braille Unicode characters (U+2800-U+28FF) with dots or spaces
        safe_text = re.sub(r'[\u2800-\u28FF]', '.', safe_text)
        print(safe_text, end=end)


# Protocol constants (matching the client)
REMBRAILLE_PORT = 17635
PROTOCOL_VERSION = 1
TIMEOUT = 30.0

# Message types
MSG_HANDSHAKE = 0x01
MSG_HANDSHAKE_RESP = 0x02
MSG_DISPLAY_CELLS = 0x10
MSG_KEY_EVENT = 0x20
MSG_NUM_CELLS_REQ = 0x30
MSG_NUM_CELLS_RESP = 0x31
MSG_PING = 0x40
MSG_PONG = 0x41
MSG_ERROR = 0xFF

# Key event types
KEY_DOWN = 0x01
KEY_UP = 0x02

# Message type names for display
MSG_NAMES = {
    MSG_HANDSHAKE: "HANDSHAKE",
    MSG_HANDSHAKE_RESP: "HANDSHAKE_RESP",
    MSG_DISPLAY_CELLS: "DISPLAY_CELLS",
    MSG_KEY_EVENT: "KEY_EVENT",
    MSG_NUM_CELLS_REQ: "NUM_CELLS_REQ",
    MSG_NUM_CELLS_RESP: "NUM_CELLS_RESP",
    MSG_PING: "PING",
    MSG_PONG: "PONG",
    MSG_ERROR: "ERROR",
}


class RemBrailleMessage:
    """Represents a RemBraille protocol message"""
    
    def __init__(self, msg_type: int, data: bytes = b""):
        self.msg_type = msg_type
        self.data = data
        self.length = len(data)
    
    def serialize(self) -> bytes:
        """Serialize message to bytes for transmission"""
        header = struct.pack("!BBH", PROTOCOL_VERSION, self.msg_type, self.length)
        return header + self.data
    
    @classmethod
    def deserialize(cls, data: bytes) -> Optional["RemBrailleMessage"]:
        """Deserialize bytes to RemBrailleMessage"""
        if len(data) < 4:
            return None
        
        version, msg_type, length = struct.unpack("!BBH", data[:4])
        if version != PROTOCOL_VERSION:
            safe_print(f"❌ Unsupported protocol version: {version}")
            return None
        
        if len(data) < 4 + length:
            return None
        
        msg_data = data[4:4 + length]
        return cls(msg_type, msg_data)


class RemBrailleServer:
    """Dummy RemBraille server for testing"""
    
    def __init__(self, port: int = REMBRAILLE_PORT, num_cells: int = 40, verbose: bool = False):
        self.port = port
        self.num_cells = num_cells
        self.verbose = verbose
        self.running = False
        self.clients: Dict[str, Any] = {}
        self.server_socket: Optional[socket.socket] = None
        
        # Current braille display content
        self.current_braille_cells: List[int] = []
        self.current_braille_text = ""
        self.current_ascii_text = ""
        self.display_lock = threading.Lock()
        
        # Message log for scrolling display
        self.message_log: List[str] = []
        self.max_log_lines = 10
        
        # Statistics
        self.stats = {
            'connections': 0,
            'messages_received': 0,
            'cells_displayed': 0,
            'start_time': None
        }
    
    def _add_message_to_log(self, message: str):
        """Add a message to the scrolling log"""
        with self.display_lock:
            self.message_log.append(message)
            if len(self.message_log) > self.max_log_lines:
                self.message_log.pop(0)
    
    def _update_display(self):
        """Update the static display with current stats and braille content"""
        if not self.running:
            return
            
        # Clear screen for fresh display
        clear_screen()
        
        # Show title
        safe_print("+" + "=" * 72 + "+")
        safe_print("|              RemBraille Test Server - Live Monitor                  |")
        safe_print("+" + "=" * 72 + "+")
        safe_print("")
        
        # Show message log
        safe_print("Recent Messages:")
        safe_print("-" * 72)
        for msg in self.message_log[-self.max_log_lines:]:
            safe_print(msg[:72])  # Truncate long lines
        
        # Pad empty lines
        for _ in range(self.max_log_lines - len(self.message_log)):
            safe_print("")
        
        safe_print("-" * 72)
        safe_print("")
        
        # Show stats box
        uptime = datetime.now() - self.stats['start_time'] if self.stats['start_time'] else None
        uptime_str = str(uptime).split('.')[0] if uptime else "00:00:00"
        
        safe_print("+" + "=" * 30 + " STATISTICS " + "=" * 30 + "+")
        safe_print(f"| Port: {self.port:<6} | Cells: {self.num_cells:<3} | Uptime: {uptime_str:<8} | Clients: {len(self.clients):<3}    |")
        safe_print(f"| Connections: {self.stats['connections']:<4} | Messages: {self.stats['messages_received']:<6} | Cells Displayed: {self.stats['cells_displayed']:<8} |")
        safe_print("+" + "-" * 72 + "+")
        safe_print("|                        CURRENT BRAILLE DISPLAY                       |")
        safe_print("+" + "-" * 72 + "+")
        
        # Show current braille content
        with self.display_lock:
            if self.current_braille_text:
                # Braille line
                braille_line = f"| Braille: {self.current_braille_text[:60]:<60} |"
                safe_print(braille_line)
                # ASCII line
                ascii_line = f"| ASCII:   {self.current_ascii_text[:60]:<60} |"
                safe_print(ascii_line)
                # Hex line if verbose
                if self.verbose and self.current_braille_cells:
                    hex_vals = ' '.join(f'{c:02X}' for c in self.current_braille_cells[:20])
                    hex_line = f"| Hex:     {hex_vals[:60]:<60} |"
                    safe_print(hex_line)
            else:
                safe_print("|                         (No content displayed)                       |")
                if self.verbose:
                    safe_print("|                                                                      |")
        
        safe_print("+" + "=" * 72 + "+")
        safe_print("")
        safe_print("Commands: [s]tats [k]ey test [q]uit [h]elp")
    
    def start(self):
        """Start the RemBraille server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Handle potential binding issues on macOS/Unix
            try:
                self.server_socket.bind(('0.0.0.0', self.port))
            except OSError as e:
                if e.errno == 48:  # Address already in use (macOS)
                    safe_print(f"❌ Port {self.port} is already in use. Please try a different port or kill the existing process.")
                    sys.exit(1)
                elif e.errno == 13:  # Permission denied
                    safe_print(f"❌ Permission denied to bind to port {self.port}. Try using a port > 1024 or run with sudo.")
                    sys.exit(1)
                else:
                    raise
            
            self.server_socket.listen(5)
            
            self.running = True
            self.stats['start_time'] = datetime.now()
            
            # Initial display
            self._update_display()
            
            # Start display update thread
            display_thread = threading.Thread(target=self._display_update_loop, daemon=True)
            display_thread.start()
            
            self._add_message_to_log(f"[{datetime.now().strftime('%H:%M:%S')}] Server started on port {self.port}")
            
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except OSError:
                    if self.running:  # Only log if not shutting down
                        safe_print("❌ Error accepting connections")
                        break
        
        except Exception as e:
            print(f"[ERROR] Failed to start server: {e}")
            sys.exit(1)
    
    def _display_update_loop(self):
        """Background thread to update the display periodically"""
        while self.running:
            time.sleep(1)  # Update every second
            self._update_display()
    
    def stop(self):
        """Stop the RemBraille server"""
        self.running = False
        
        # Close all client connections
        for client_id, client_info in list(self.clients.items()):
            try:
                client_info['socket'].close()
            except:
                pass
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        # Clear screen and show final message
        clear_screen()
        safe_print("✅ Server stopped successfully")
    
    def _handle_client(self, client_socket: socket.socket, address: tuple):
        """Handle a client connection"""
        client_id = f"{address[0]}:{address[1]}"
        
        self._add_message_to_log(f"[{datetime.now().strftime('%H:%M:%S')}] Client connected: {client_id}")
        self.stats['connections'] += 1
        
        self.clients[client_id] = {
            'socket': client_socket,
            'address': address,
            'connected_at': datetime.now(),
            'last_activity': datetime.now()
        }
        
        try:
            client_socket.settimeout(TIMEOUT)
            
            while self.running:
                # Receive message
                message = self._receive_message(client_socket)
                if not message:
                    break
                
                self.clients[client_id]['last_activity'] = datetime.now()
                self.stats['messages_received'] += 1
                
                # Handle message
                self._handle_message(client_socket, client_id, message)
        
        except Exception as e:
            if self.verbose:
                safe_print(f"⚠️  Client {client_id} error: {e}")
        
        finally:
            # Clean up
            try:
                client_socket.close()
            except:
                pass
            
            if client_id in self.clients:
                duration = (datetime.now() - self.clients[client_id]['connected_at']).total_seconds()
                self._add_message_to_log(f"[{datetime.now().strftime('%H:%M:%S')}] Client disconnected: {client_id} ({duration:.1f}s)")
                del self.clients[client_id]
    
    def _receive_message(self, client_socket: socket.socket) -> Optional[RemBrailleMessage]:
        """Receive a message from client"""
        try:
            # Read header
            header_data = self._receive_exact(client_socket, 4)
            if not header_data:
                return None
            
            version, msg_type, length = struct.unpack("!BBH", header_data)
            
            # Read data
            data = b""
            if length > 0:
                data = self._receive_exact(client_socket, length)
                if not data:
                    return None
            
            return RemBrailleMessage(msg_type, data)
        
        except Exception as e:
            if self.verbose:
                safe_print(f"❌ Error receiving message: {e}")
            return None
    
    def _receive_exact(self, client_socket: socket.socket, length: int) -> Optional[bytes]:
        """Receive exactly the specified number of bytes"""
        data = b""
        while len(data) < length:
            try:
                chunk = client_socket.recv(length - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                if self.verbose:
                    safe_print("⏱️  Receive timeout")
                return None
            except Exception:
                return None
        return data
    
    def _handle_message(self, client_socket: socket.socket, client_id: str, message: RemBrailleMessage):
        """Handle received message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        msg_name = MSG_NAMES.get(message.msg_type, f"UNKNOWN({message.msg_type})")
        
        self._add_message_to_log(f"[{timestamp}] {client_id} -> {msg_name}")
        
        if message.msg_type == MSG_HANDSHAKE:
            client_info = message.data.decode('utf-8', errors='ignore')
            self._add_message_to_log(f"  Handshake: {client_info}")
            
            # Send handshake response
            response = RemBrailleMessage(MSG_HANDSHAKE_RESP, b"RemBraille_Dummy_Server_OK")
            self._send_message(client_socket, response)
        
        elif message.msg_type == MSG_NUM_CELLS_REQ:
            # Send number of cells
            cells_data = struct.pack("!H", self.num_cells)
            response = RemBrailleMessage(MSG_NUM_CELLS_RESP, cells_data)
            self._send_message(client_socket, response)
            self._add_message_to_log(f"  Sent cell count: {self.num_cells}")
        
        elif message.msg_type == MSG_DISPLAY_CELLS:
            cells = list(message.data)
            self.stats['cells_displayed'] += len(cells)
            
            # Update current display content
            with self.display_lock:
                self.current_braille_cells = cells
                self.current_braille_text = self._cells_to_braille(cells)
                self.current_ascii_text = self._cells_to_ascii(cells)
            
            self._add_message_to_log(f"  Display: {len(cells)} cells")
        
        elif message.msg_type == MSG_PING:
            # Send pong response
            pong = RemBrailleMessage(MSG_PONG)
            self._send_message(client_socket, pong)
            if self.verbose:
                self._add_message_to_log(f"  Ping/Pong")
        
        elif message.msg_type == MSG_KEY_EVENT:
            if len(message.data) >= 3:
                key_id, event_type = struct.unpack("!HB", message.data[:3])
                event_name = "PRESS" if event_type == KEY_DOWN else "RELEASE"
                self._add_message_to_log(f"  Key: {key_id} {event_name}")
        
        else:
            self._add_message_to_log(f"  Unknown message type: {message.msg_type}")
    
    def _send_message(self, client_socket: socket.socket, message: RemBrailleMessage) -> bool:
        """Send message to client"""
        try:
            data = message.serialize()
            client_socket.sendall(data)
            return True
        except Exception as e:
            if self.verbose:
                safe_print(f"❌ Error sending message: {e}")
            return False
    
    def _cells_to_braille(self, cells: list) -> str:
        """Convert braille cell values to Unicode braille characters"""
        braille_text = ""
        for cell in cells:
            try:
                if cell == 0:
                    braille_text += " "  # Blank braille cell (ASCII space)
                else:
                    # Convert to Unicode braille (U+2800 + cell value)
                    braille_char = chr(0x2800 + cell)
                    braille_text += braille_char
            except (ValueError, OverflowError):
                # Fallback for invalid cell values
                braille_text += "?"
        return braille_text
    
    def _cells_to_ascii(self, cells: list) -> str:
        """Convert braille cells to approximated ASCII representation"""
        ascii_text = ""
        for cell in cells:
            if cell == 0:
                ascii_text += " "
            else:
                # Simple mapping for common characters
                # This is a very basic approximation
                if cell in range(32, 127):  # Printable ASCII range
                    try:
                        ascii_text += chr(cell)
                    except:
                        ascii_text += "?"
                else:
                    ascii_text += "?"
        return ascii_text
    
    def send_test_key_event(self, key_id: int = 100, is_press: bool = True):
        """Send a test key event to all connected clients"""
        if not self.clients:
            self._add_message_to_log("No connected clients to send key event")
            return
        
        event_type = KEY_DOWN if is_press else KEY_UP
        event_name = "PRESS" if is_press else "RELEASE"
        key_data = struct.pack("!HB", key_id, event_type)
        message = RemBrailleMessage(MSG_KEY_EVENT, key_data)
        
        self._add_message_to_log(f"Sending test key: {key_id} {event_name}")
        
        sent_count = 0
        for client_id, client_info in self.clients.items():
            if self._send_message(client_info['socket'], message):
                sent_count += 1
        
        self._add_message_to_log(f"  Sent to {sent_count}/{len(self.clients)} clients")


def main():
    """Main entry point"""
    # Set up signal handlers for graceful shutdown
    server_instance = None
    
    def signal_handler(signum, frame):
        safe_print(f"\n🛑 Received signal {signum}, shutting down...")
        if server_instance:
            server_instance.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Handle Unicode output issues on some terminals
    try:
        # Test if we can output Unicode characters
        test_chars = "🚀📡⚠️"
        sys.stdout.write("")  # Test encoding
        unicode_support = True
    except (UnicodeEncodeError, UnicodeDecodeError):
        unicode_support = False
        safe_print("Warning: Your terminal may not display Unicode characters properly.")
        safe_print("Consider setting LANG=en_US.UTF-8 or similar in your environment.")
        safe_print("")
    
    parser = argparse.ArgumentParser(
        description="RemBraille Dummy Server - Test server for RemBraille NVDA add-on",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 rembraille_server.py                   # Start with defaults  
  python3 rembraille_server.py --port 12345      # Custom port
  python3 rembraille_server.py --cells 80 -v     # 80 cells, verbose mode
  
Interactive commands while running:
  's' + Enter: Show statistics
  'k' + Enter: Send test key event
  'q' + Enter: Quit server
        """
    )
    
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=REMBRAILLE_PORT,
        help=f'Port to listen on (default: {REMBRAILLE_PORT})'
    )
    
    parser.add_argument(
        '--cells', '-c',
        type=int,
        default=40,
        help='Number of braille cells to simulate (default: 40)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Create and start server
    server = RemBrailleServer(args.port, args.cells, args.verbose)
    server_instance = server  # For signal handler
    
    try:
        # Start server in background thread
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        
        # Wait a moment for the server to start
        time.sleep(0.5)
        
        if not server.running:
            safe_print("❌ Failed to start server")
            return 1
        
        # Interactive command loop (input handled silently in the background)
        while server.running:
            try:
                command = input().strip().lower()
                
                if command == 'q':
                    break
                elif command == 's':
                    # Force display refresh
                    server._update_display()
                elif command == 'k':
                    server.send_test_key_event()
                elif command == 'h':
                    server._add_message_to_log("Commands: [s]tats refresh [k]ey test [q]uit")
                elif command == '':
                    continue  # Ignore empty input
                else:
                    server._add_message_to_log(f"Unknown command: '{command}'.")
                    
            except (EOFError, KeyboardInterrupt):
                safe_print("\n")
                break
    
    except Exception as e:
        safe_print(f"❌ Unexpected error: {e}")
        return 1
        
    finally:
        if server:
            server.stop()
        return 0


if __name__ == "__main__":
    sys.exit(main())