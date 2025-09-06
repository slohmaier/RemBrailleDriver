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
from typing import Optional, Dict, Any
from datetime import datetime


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
            print(f"❌ Unsupported protocol version: {version}")
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
        
        # Statistics
        self.stats = {
            'connections': 0,
            'messages_received': 0,
            'cells_displayed': 0,
            'start_time': None
        }
    
    def start(self):
        """Start the RemBraille server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(5)
            
            self.running = True
            self.stats['start_time'] = datetime.now()
            
            print(f"🚀 RemBraille Dummy Server Started")
            print(f"📡 Listening on port {self.port}")
            print(f"📄 Simulating {self.num_cells} braille cells")
            print(f"🔧 Verbose mode: {'ON' if self.verbose else 'OFF'}")
            print(f"⏰ Started at: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
            
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
                        print("❌ Error accepting connections")
                        break
        
        except Exception as e:
            print(f"❌ Failed to start server: {e}")
            sys.exit(1)
    
    def stop(self):
        """Stop the RemBraille server"""
        print("\n🛑 Shutting down RemBraille server...")
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
        
        self._print_statistics()
        print("✅ Server stopped successfully")
    
    def _handle_client(self, client_socket: socket.socket, address: tuple):
        """Handle a client connection"""
        client_id = f"{address[0]}:{address[1]}"
        
        print(f"🔌 New client connected: {client_id}")
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
                print(f"⚠️  Client {client_id} error: {e}")
        
        finally:
            # Clean up
            try:
                client_socket.close()
            except:
                pass
            
            if client_id in self.clients:
                duration = (datetime.now() - self.clients[client_id]['connected_at']).total_seconds()
                print(f"🔌 Client disconnected: {client_id} (connected for {duration:.1f}s)")
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
                print(f"❌ Error receiving message: {e}")
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
                    print("⏱️  Receive timeout")
                return None
            except Exception:
                return None
        return data
    
    def _handle_message(self, client_socket: socket.socket, client_id: str, message: RemBrailleMessage):
        """Handle received message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        msg_name = MSG_NAMES.get(message.msg_type, f"UNKNOWN({message.msg_type})")
        
        print(f"📨 [{timestamp}] {client_id} -> {msg_name}")
        
        if message.msg_type == MSG_HANDSHAKE:
            client_info = message.data.decode('utf-8', errors='ignore')
            print(f"   🤝 Handshake from: {client_info}")
            
            # Send handshake response
            response = RemBrailleMessage(MSG_HANDSHAKE_RESP, b"RemBraille_Dummy_Server_OK")
            self._send_message(client_socket, response)
            print(f"   ✅ Handshake response sent")
        
        elif message.msg_type == MSG_NUM_CELLS_REQ:
            print(f"   📏 Client requesting number of cells")
            
            # Send number of cells
            cells_data = struct.pack("!H", self.num_cells)
            response = RemBrailleMessage(MSG_NUM_CELLS_RESP, cells_data)
            self._send_message(client_socket, response)
            print(f"   📏 Responded with {self.num_cells} cells")
        
        elif message.msg_type == MSG_DISPLAY_CELLS:
            cells = list(message.data)
            self.stats['cells_displayed'] += len(cells)
            
            print(f"   🔤 Displaying {len(cells)} braille cells:")
            
            # Convert cells to readable braille characters
            braille_text = self._cells_to_braille(cells)
            ascii_text = self._cells_to_ascii(cells)
            
            print(f"   📝 Braille: {braille_text}")
            print(f"   📝 ASCII:   {ascii_text}")
            
            if self.verbose:
                print(f"   🔢 Raw:     {' '.join(f'{c:02X}' for c in cells)}")
        
        elif message.msg_type == MSG_PING:
            print(f"   🏓 Ping received")
            # Send pong response
            pong = RemBrailleMessage(MSG_PONG)
            self._send_message(client_socket, pong)
            if self.verbose:
                print(f"   🏓 Pong sent")
        
        elif message.msg_type == MSG_KEY_EVENT:
            if len(message.data) >= 3:
                key_id, event_type = struct.unpack("!HB", message.data[:3])
                event_name = "PRESS" if event_type == KEY_DOWN else "RELEASE"
                print(f"   ⌨️  Key event: Key {key_id} {event_name}")
        
        else:
            print(f"   ❓ Unknown message type: {message.msg_type}")
            if self.verbose and message.data:
                print(f"   📊 Data: {message.data[:50]}{'...' if len(message.data) > 50 else ''}")
    
    def _send_message(self, client_socket: socket.socket, message: RemBrailleMessage) -> bool:
        """Send message to client"""
        try:
            data = message.serialize()
            client_socket.sendall(data)
            return True
        except Exception as e:
            if self.verbose:
                print(f"❌ Error sending message: {e}")
            return False
    
    def _cells_to_braille(self, cells: list) -> str:
        """Convert braille cell values to Unicode braille characters"""
        braille_text = ""
        for cell in cells:
            if cell == 0:
                braille_text += "⠀"  # Blank braille cell
            else:
                # Convert to Unicode braille (U+2800 + cell value)
                braille_char = chr(0x2800 + cell)
                braille_text += braille_char
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
    
    def _print_statistics(self):
        """Print server statistics"""
        if not self.stats['start_time']:
            return
        
        uptime = datetime.now() - self.stats['start_time']
        uptime_str = str(uptime).split('.')[0]  # Remove microseconds
        
        print("\n" + "=" * 60)
        print("📊 RemBraille Server Statistics")
        print("=" * 60)
        print(f"⏱️  Uptime: {uptime_str}")
        print(f"🔌 Total connections: {self.stats['connections']}")
        print(f"📨 Messages received: {self.stats['messages_received']}")
        print(f"🔤 Braille cells displayed: {self.stats['cells_displayed']}")
        print(f"👥 Active clients: {len(self.clients)}")
        print("=" * 60)
    
    def send_test_key_event(self, key_id: int = 100, is_press: bool = True):
        """Send a test key event to all connected clients"""
        if not self.clients:
            print("⚠️  No connected clients to send key event")
            return
        
        event_type = KEY_DOWN if is_press else KEY_UP
        event_name = "PRESS" if is_press else "RELEASE"
        key_data = struct.pack("!HB", key_id, event_type)
        message = RemBrailleMessage(MSG_KEY_EVENT, key_data)
        
        print(f"⌨️  Sending test key event: Key {key_id} {event_name}")
        
        for client_id, client_info in self.clients.items():
            if self._send_message(client_info['socket'], message):
                print(f"   ✅ Sent to {client_id}")
            else:
                print(f"   ❌ Failed to send to {client_id}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="RemBraille Dummy Server - Test server for RemBraille NVDA add-on",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python rembraille_server.py                    # Start with defaults
  python rembraille_server.py --port 12345       # Custom port
  python rembraille_server.py --cells 80 -v      # 80 cells, verbose mode
  
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
    
    try:
        # Start server in background thread
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        
        # Interactive command loop
        print("\n💡 Interactive commands:")
        print("   's' + Enter: Show statistics")
        print("   'k' + Enter: Send test key event")  
        print("   'q' + Enter: Quit server")
        print("   'h' + Enter: Show this help")
        print("\n")
        
        while server.running:
            try:
                command = input().strip().lower()
                
                if command == 'q':
                    break
                elif command == 's':
                    server._print_statistics()
                elif command == 'k':
                    server.send_test_key_event()
                elif command == 'h':
                    print("\n💡 Available commands:")
                    print("   's': Show server statistics")
                    print("   'k': Send test key event to all clients")
                    print("   'q': Quit server")
                    print("   'h': Show this help")
                    print()
                elif command == '':
                    continue  # Ignore empty input
                else:
                    print(f"❓ Unknown command: '{command}'. Type 'h' for help.")
                    
            except (EOFError, KeyboardInterrupt):
                break
    
    finally:
        server.stop()


if __name__ == "__main__":
    main()