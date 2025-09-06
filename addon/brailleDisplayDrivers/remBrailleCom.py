# A part of NonVisual Desktop Access (NVDA)
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.
# Copyright (C) 2025 Stefan Lohmaier

"""
RemBraille Communication Protocol
Handles TCP socket communication between NVDA guest and host braille display
"""

import socket
import struct
import threading
import time
from typing import Optional, Callable, List, Tuple, Union
from logHandler import log
import queue

# Protocol constants
REMBRAILLE_PORT = 17635  # Unique port for RemBraille
PROTOCOL_VERSION = 1
TIMEOUT = 5.0
RECONNECT_DELAY = 3.0

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


class RemBrailleMessage:
	"""Represents a RemBraille protocol message"""
	
	def __init__(self, msg_type: int, data: bytes = b""):
		self.msg_type = msg_type
		self.data = data
		self.length = len(data)
	
	def serialize(self) -> bytes:
		"""Serialize message to bytes for transmission"""
		# Header: [version:1][type:1][length:2][data:n]
		header = struct.pack("!BBH", PROTOCOL_VERSION, self.msg_type, self.length)
		return header + self.data
	
	@classmethod
	def deserialize(cls, data: bytes) -> Optional["RemBrailleMessage"]:
		"""Deserialize bytes to RemBrailleMessage"""
		if len(data) < 4:
			return None
		
		version, msg_type, length = struct.unpack("!BBH", data[:4])
		if version != PROTOCOL_VERSION:
			log.error(f"Unsupported protocol version: {version}")
			return None
		
		if len(data) < 4 + length:
			return None
		
		msg_data = data[4:4 + length]
		return cls(msg_type, msg_data)


class RemBrailleCom:
	"""
	RemBraille Communication Class
	
	Handles TCP socket communication with the host system's braille display.
	Provides methods for:
	- Connecting to host braille server
	- Sending braille cell data for display
	- Receiving key events from braille display
	- Managing connection state and reconnection
	"""
	
	def __init__(self, on_key_event: Optional[Callable[[int, bool], None]] = None):
		"""
		Initialize RemBraille communication
		
		@param on_key_event: Callback function for key events (key_id, is_pressed)
		"""
		self.on_key_event = on_key_event
		self.socket: Optional[socket.socket] = None
		self.connected = False
		self.host_ip: Optional[str] = None
		self.port = REMBRAILLE_PORT
		self.num_cells = 0
		
		# Threading
		self._stop_event = threading.Event()
		self._receive_thread: Optional[threading.Thread] = None
		self._ping_thread: Optional[threading.Thread] = None
		self._message_queue = queue.Queue()
		
		# Connection management
		self._reconnect_timer: Optional[threading.Timer] = None
		self._last_ping_time = 0.0
		
	def connect(self, host_ip: str, port: int = REMBRAILLE_PORT) -> bool:
		"""
		Connect to RemBraille host server
		
		@param host_ip: IP address of the host system
		@param port: Port number (default: REMBRAILLE_PORT)
		@return: True if connection successful, False otherwise
		"""
		self.host_ip = host_ip
		self.port = port
		
		try:
			# Create socket
			self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.socket.settimeout(TIMEOUT)
			
			# Connect to host
			log.info(f"Connecting to RemBraille host at {host_ip}:{port}")
			self.socket.connect((host_ip, port))
			
			# Send handshake
			handshake = RemBrailleMessage(MSG_HANDSHAKE, b"NVDA_RemBraille_Client")
			self._send_message(handshake)
			
			# Wait for handshake response
			response = self._receive_message()
			if not response or response.msg_type != MSG_HANDSHAKE_RESP:
				log.error("Handshake failed")
				self.disconnect()
				return False
			
			# Request number of cells
			cells_req = RemBrailleMessage(MSG_NUM_CELLS_REQ)
			self._send_message(cells_req)
			
			# Wait for cells response
			cells_resp = self._receive_message()
			if not cells_resp or cells_resp.msg_type != MSG_NUM_CELLS_RESP:
				log.error("Failed to get number of cells")
				self.disconnect()
				return False
			
			self.num_cells = struct.unpack("!H", cells_resp.data)[0]
			log.info(f"Connected to RemBraille host with {self.num_cells} cells")
			
			self.connected = True
			
			# Start background threads
			self._start_threads()
			
			return True
			
		except Exception as e:
			log.error(f"Failed to connect to RemBraille host: {e}")
			self.disconnect()
			return False
	
	def disconnect(self):
		"""Disconnect from RemBraille host"""
		self.connected = False
		self._stop_threads()
		
		if self.socket:
			try:
				self.socket.close()
			except:
				pass
			self.socket = None
		
		if self._reconnect_timer:
			self._reconnect_timer.cancel()
			self._reconnect_timer = None
		
		log.info("Disconnected from RemBraille host")
	
	def display_cells(self, cells: List[int]) -> bool:
		"""
		Send braille cells to display
		
		@param cells: List of braille cell values (0-255)
		@return: True if sent successfully, False otherwise
		"""
		if not self.connected or not self.socket:
			return False
		
		try:
			# Pack cells as bytes
			cell_data = bytes(cells)
			message = RemBrailleMessage(MSG_DISPLAY_CELLS, cell_data)
			return self._send_message(message)
		except Exception as e:
			log.error(f"Failed to send braille cells: {e}")
			self._handle_connection_error()
			return False
	
	def _send_message(self, message: RemBrailleMessage) -> bool:
		"""Send a message to the host"""
		if not self.socket:
			return False
		
		try:
			data = message.serialize()
			self.socket.sendall(data)
			return True
		except Exception as e:
			log.error(f"Failed to send message: {e}")
			self._handle_connection_error()
			return False
	
	def _receive_message(self) -> Optional[RemBrailleMessage]:
		"""Receive a message from the host"""
		if not self.socket:
			return None
		
		try:
			# Read header
			header_data = self._receive_exact(4)
			if not header_data:
				return None
			
			version, msg_type, length = struct.unpack("!BBH", header_data)
			if version != PROTOCOL_VERSION:
				log.error(f"Unsupported protocol version: {version}")
				return None
			
			# Read data
			data = b""
			if length > 0:
				data = self._receive_exact(length)
				if not data:
					return None
			
			return RemBrailleMessage(msg_type, data)
			
		except Exception as e:
			log.error(f"Failed to receive message: {e}")
			self._handle_connection_error()
			return None
	
	def _receive_exact(self, length: int) -> Optional[bytes]:
		"""Receive exactly the specified number of bytes"""
		if not self.socket:
			return None
		
		data = b""
		while len(data) < length:
			try:
				chunk = self.socket.recv(length - len(data))
				if not chunk:
					return None  # Connection closed
				data += chunk
			except socket.timeout:
				continue
			except Exception:
				return None
		
		return data
	
	def _start_threads(self):
		"""Start background threads for communication"""
		self._stop_event.clear()
		
		# Start receive thread
		self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
		self._receive_thread.start()
		
		# Start ping thread
		self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
		self._ping_thread.start()
	
	def _stop_threads(self):
		"""Stop background threads"""
		self._stop_event.set()
		
		if self._receive_thread and self._receive_thread.is_alive():
			self._receive_thread.join(timeout=1.0)
		
		if self._ping_thread and self._ping_thread.is_alive():
			self._ping_thread.join(timeout=1.0)
	
	def _receive_loop(self):
		"""Background thread for receiving messages"""
		while not self._stop_event.is_set() and self.connected:
			try:
				message = self._receive_message()
				if not message:
					continue
				
				self._handle_message(message)
				
			except Exception as e:
				if self.connected:
					log.error(f"Error in receive loop: {e}")
					self._handle_connection_error()
				break
	
	def _ping_loop(self):
		"""Background thread for sending keep-alive pings"""
		while not self._stop_event.is_set() and self.connected:
			try:
				time.sleep(10.0)  # Ping every 10 seconds
				
				if self.connected:
					ping_msg = RemBrailleMessage(MSG_PING)
					self._send_message(ping_msg)
					self._last_ping_time = time.time()
				
			except Exception as e:
				if self.connected:
					log.error(f"Error in ping loop: {e}")
				break
	
	def _handle_message(self, message: RemBrailleMessage):
		"""Handle received message"""
		if message.msg_type == MSG_KEY_EVENT:
			# Key event: [key_id:2][event_type:1]
			if len(message.data) >= 3:
				key_id, event_type = struct.unpack("!HB", message.data[:3])
				is_pressed = (event_type == KEY_DOWN)
				
				if self.on_key_event:
					self.on_key_event(key_id, is_pressed)
		
		elif message.msg_type == MSG_PONG:
			# Pong response - connection is alive
			pass
		
		elif message.msg_type == MSG_ERROR:
			error_msg = message.data.decode('utf-8', errors='ignore')
			log.error(f"RemBraille host error: {error_msg}")
		
		else:
			log.warning(f"Unknown message type: {message.msg_type}")
	
	def _handle_connection_error(self):
		"""Handle connection error by scheduling reconnection"""
		if not self.connected:
			return
		
		self.connected = False
		log.warning("RemBraille connection lost, scheduling reconnection...")
		
		# Schedule reconnection
		if self._reconnect_timer:
			self._reconnect_timer.cancel()
		
		self._reconnect_timer = threading.Timer(RECONNECT_DELAY, self._attempt_reconnect)
		self._reconnect_timer.start()
	
	def _attempt_reconnect(self):
		"""Attempt to reconnect to the host"""
		if self.host_ip:
			log.info("Attempting to reconnect to RemBraille host...")
			if not self.connect(self.host_ip, self.port):
				# Schedule another reconnection attempt
				self._reconnect_timer = threading.Timer(RECONNECT_DELAY, self._attempt_reconnect)
				self._reconnect_timer.start()
	
	def is_connected(self) -> bool:
		"""Check if connected to host"""
		return self.connected and self.socket is not None
	
	def get_num_cells(self) -> int:
		"""Get number of braille cells"""
		return self.num_cells