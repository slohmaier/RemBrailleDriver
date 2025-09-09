# A part of NonVisual Desktop Access (NVDA)
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.
# Copyright (C) 2025 Stefan Lohmaier

"""
RemBraille Driver for NVDA
Provides braille display support for NVDA running in virtual machines
"""

import threading
import time
import wx
from typing import List, Optional

import braille
import inputCore
from logHandler import log
import config
import gui
from gui import guiHelper
from autoSettingsUtils.driverSetting import BooleanDriverSetting, NumericDriverSetting
import speech

# Import our RemBraille components
from ._remBrailleCom import RemBrailleCom, REMBRAILLE_PORT
from ._hostDetection import get_vm_host_ip, suggest_host_ips


class RemBrailleDriverSetting:
	"""Custom driver settings for RemBraille"""
	
	class HostIPSetting:
		"""Host IP address setting"""
		id = "hostIP"
		displayName = _("Host IP Address")
		
		def __init__(self, driver):
			self.driver = driver
		
		@property
		def value(self):
			return getattr(self.driver, '_hostIP', '')
		
		@value.setter
		def value(self, val):
			self.driver._hostIP = val
			# Reconnect if IP changed
			if self.driver.connected and val != self.driver.com.host_ip:
				wx.CallAfter(self.driver._reconnect_with_new_ip, val)
	
	class PortSetting:
		"""Port number setting"""
		id = "port"
		displayName = _("Port Number")
		
		def __init__(self, driver):
			self.driver = driver
		
		@property
		def value(self):
			return getattr(self.driver, '_port', REMBRAILLE_PORT)
		
		@value.setter
		def value(self, val):
			try:
				port = int(val)
				if 1 <= port <= 65535:
					self.driver._port = port
					# Reconnect if port changed
					if self.driver.connected and port != self.driver.com.port:
						wx.CallAfter(self.driver._reconnect_with_new_port, port)
			except (ValueError, TypeError):
				pass
	
	# Remove the custom setting classes - use direct instantiation


class BrailleDisplayDriver(braille.BrailleDisplayDriver):
	"""RemBraille display driver for NVDA"""
	
	name = "remBrailleDriver"
	# Translators: Description of the RemBraille display driver
	description = _("RemBraille (VM Host Connection)")
	isThreadSafe = True
	supportsAutomaticDetection = False  # We use manual connection
	receivesAckPackets = False
	
	# Driver settings
	supportedSettings = [
		BooleanDriverSetting(
			"autoConnect",
			_("&Auto-connect on startup"),
			defaultVal=True,
			useConfig=True,
		),
		NumericDriverSetting(
			"reconnectInterval",
			_("Reconnection &interval (minutes)"),
			defaultVal=1,
			minVal=1,
			maxVal=60,
			minStep=1,
			normalStep=1,
			useConfig=True,
		),
	]
	
	@classmethod
	def check(cls):
		"""Check if RemBraille driver is available.
		Always returns True since this is a network-based driver that can be configured.
		"""
		return True
	
	def __init__(self, port: str = "auto"):
		"""Initialize RemBraille driver"""
		super().__init__()
		
		# Connection state
		self.connected = False
		self.numCells = 0
		
		# Settings
		self._hostIP = ""
		self._port = REMBRAILLE_PORT
		self.autoConnect = True
		self.reconnectInterval = 1  # minutes
		
		# Communication
		self.com: Optional[RemBrailleCom] = None
		self._connection_lock = threading.Lock()
		
		# Reconnection timer
		self._reconnect_timer: Optional[threading.Timer] = None
		
		# Load settings from config
		self._load_settings()
		
		# Initialize communication
		self.com = RemBrailleCom(on_key_event=self._on_key_event)
		
		# Auto-connect if enabled
		if self.autoConnect:
			wx.CallAfter(self._auto_connect)
	
	def _load_settings(self):
		"""Load settings from NVDA configuration"""
		try:
			section = config.conf["braille"]["remBrailleDriver"]
			self._hostIP = section.get("hostIP", "")
			self._port = section.get("port", REMBRAILLE_PORT)
			self.autoConnect = section.get("autoConnect", True)
			self.reconnectInterval = section.get("reconnectInterval", 1)
		except KeyError:
			# Create default config section
			if "remBrailleDriver" not in config.conf["braille"]:
				config.conf["braille"]["remBrailleDriver"] = {}
	
	def _save_settings(self):
		"""Save settings to NVDA configuration"""
		try:
			section = config.conf["braille"]["remBrailleDriver"]
			section["hostIP"] = self._hostIP
			section["port"] = int(self._port)
			section["autoConnect"] = self.autoConnect
			section["reconnectInterval"] = self.reconnectInterval
			config.conf.save()
		except Exception as e:
			log.error(f"Failed to save RemBraille settings: {e}")
	
	def _auto_connect(self):
		"""Attempt automatic connection in background thread"""
		def _auto_connect_thread():
			try:
				if self._hostIP:
					# Use configured host IP
					self._connect_to_host(self._hostIP, self._port)
				else:
					# Try localhost first (for debugging)
					log.info("Attempting to connect to localhost for debugging")
					if self._connect_to_host("127.0.0.1", self._port):
						self._hostIP = "127.0.0.1"
						self._save_settings()
						return
					
					# Try to auto-detect host IP
					host_ip = get_vm_host_ip()
					if host_ip:
						self._hostIP = host_ip
						self._save_settings()
						self._connect_to_host(host_ip, self._port)
					else:
						# Show connection dialog
						wx.CallAfter(self._show_connection_dialog, auto_connect=True)
			except Exception as e:
				log.error(f"Error in auto-connect thread: {e}")
		
		# Run auto-connect in background thread to avoid blocking NVDA
		auto_connect_thread = threading.Thread(target=_auto_connect_thread, daemon=True)
		auto_connect_thread.start()
	
	def _connect_to_host(self, host_ip: str, port: int = REMBRAILLE_PORT) -> bool:
		"""Connect to RemBraille host"""
		with self._connection_lock:
			if self.connected:
				return True
			
			if not self.com:
				return False
			
			log.info(f"Connecting to RemBraille host at {host_ip}:{port}")
			
			if self.com.connect(host_ip, port):
				self.connected = True
				self.numCells = self.com.get_num_cells()
				self._hostIP = host_ip
				self._port = port
				self._save_settings()
				
				# Announce connection success (use CallAfter for thread safety)
				def announce_success():
					speech.speakMessage(_("RemBraille connected to {ip}:{port} with {cells} cells.").format(
						ip=host_ip, port=port, cells=self.numCells
					))
				wx.CallAfter(announce_success)
				
				return True
			else:
				log.error(f"Failed to connect to RemBraille host at {host_ip}:{port}")
				# Start reconnection timer
				self._schedule_reconnection(host_ip, port, "Connection failed")
				return False
	
	def _disconnect_from_host(self):
		"""Disconnect from RemBraille host"""
		with self._connection_lock:
			# Cancel reconnection timer if running
			self._cancel_reconnection_timer()
			
			if self.com:
				self.com.disconnect()
			self.connected = False
			self.numCells = 0
	
	def _reconnect_with_new_ip(self, new_ip: str):
		"""Reconnect with new IP address"""
		self._disconnect_from_host()
		time.sleep(1.0)  # Brief delay
		self._connect_to_host(new_ip, self._port)
	
	def _reconnect_with_new_port(self, new_port: int):
		"""Reconnect with new port"""
		self._disconnect_from_host()
		time.sleep(1.0)  # Brief delay
		self._connect_to_host(self._hostIP, new_port)
	
	def _on_key_event(self, key_id: int, is_pressed: bool):
		"""Handle key events from braille display"""
		try:
			if is_pressed:
				# Map RemBraille key IDs to NVDA input gestures
				gesture_name = self._map_key_to_gesture(key_id)
				if gesture_name:
					inputCore.manager.emulateGesture(RemBrailleInputGesture(gesture_name))
		except Exception as e:
			log.error(f"Error handling key event {key_id}: {e}")
	
	def _schedule_reconnection(self, host_ip: str, port: int, reason: str):
		"""Schedule automatic reconnection after configured interval"""
		# Cancel existing timer
		self._cancel_reconnection_timer()
		
		# Announce connection loss and retry schedule
		speech.speakMessage(_("RemBraille {reason}. Will retry in {minutes} minutes.").format(
			reason=reason.lower(), minutes=self.reconnectInterval
		))
		
		# Schedule reconnection
		delay_seconds = self.reconnectInterval * 60
		self._reconnect_timer = threading.Timer(delay_seconds, self._attempt_reconnection, [host_ip, port])
		self._reconnect_timer.start()
		
		log.info(f"Scheduled RemBraille reconnection to {host_ip}:{port} in {self.reconnectInterval} minutes")
	
	def _cancel_reconnection_timer(self):
		"""Cancel the reconnection timer if it's running"""
		if self._reconnect_timer:
			self._reconnect_timer.cancel()
			self._reconnect_timer = None
	
	def _attempt_reconnection(self, host_ip: str, port: int):
		"""Attempt to reconnect to the host"""
		log.info(f"Attempting RemBraille reconnection to {host_ip}:{port}")
		speech.speakMessage(_("RemBraille attempting reconnection."))
		
		success = self._connect_to_host(host_ip, port)
		if not success:
			# If connection failed, schedule another retry
			self._schedule_reconnection(host_ip, port, "Reconnection failed")
	
	def _handle_connection_lost(self):
		"""Handle when connection is lost during operation"""
		if self.connected:
			self.connected = False
			self.numCells = 0
			
			speech.speakMessage(_("RemBraille connection lost."))
			log.warning("RemBraille connection lost")
			
			# Schedule reconnection if we have connection details
			if self._hostIP and self._port:
				self._schedule_reconnection(self._hostIP, self._port, "Connection lost")

	def _map_key_to_gesture(self, key_id: int) -> Optional[str]:
		"""Map RemBraille key ID to NVDA gesture name"""
		# Basic routing keys (cell selectors)
		if 1 <= key_id <= 80:  # Assuming max 80 cells
			return f"routing{key_id}"
		
		# Navigation keys (these would be defined based on the host braille display)
		key_map = {
			100: "leftArrow",
			101: "rightArrow", 
			102: "upArrow",
			103: "downArrow",
			110: "space",
			120: "scrollLeft",
			121: "scrollRight",
		}
		
		return key_map.get(key_id)
	
	def _show_connection_dialog(self, auto_connect: bool = False):
		"""Show connection configuration dialog"""
		try:
			dialog = RemBrailleConnectionDialog(None, self, auto_connect)
			dialog.ShowModal()
			dialog.Destroy()
		except Exception as e:
			log.error(f"Error showing connection dialog: {e}")
			# Fallback: announce failure
			if auto_connect:
				speech.speakMessage(_("Could not auto-detect RemBraille host. Please configure the connection manually in NVDA Settings."))
	
	def display(self, cells: List[int]):
		"""Display braille cells"""
		if not self.connected or not self.com:
			return
		
		try:
			# Ensure we don't send more cells than the display supports
			if len(cells) > self.numCells:
				cells = cells[:self.numCells]
			elif len(cells) < self.numCells:
				# Pad with spaces
				cells = cells + [0] * (self.numCells - len(cells))
			
			success = self.com.display_cells(cells)
			if not success:
				# Connection may have been lost
				self._handle_connection_lost()
		except Exception as e:
			log.error(f"Error displaying braille cells: {e}")
			# Assume connection loss
			self._handle_connection_lost()
	
	def terminate(self):
		"""Clean up and disconnect"""
		self._disconnect_from_host()
		super().terminate()
	
	@classmethod
	def getManualPorts(cls):
		"""Return manual connection options"""
		return ["manual"]


class RemBrailleInputGesture(inputCore.InputGesture):
	"""Input gesture for RemBraille"""
	
	def __init__(self, gesture_name: str):
		super().__init__()
		self.id = f"remBrailleDriver:{gesture_name}"
	
	@property
	def source(self):
		return "remBrailleDriver"


class RemBrailleConnectionDialog(wx.Dialog):
	"""Connection configuration dialog for RemBraille"""
	
	def __init__(self, parent, driver: BrailleDisplayDriver, auto_connect: bool = False):
		self.driver = driver
		self.auto_connect = auto_connect
		
		title = _("RemBraille Connection") if not auto_connect else _("RemBraille Auto-Connect Failed")
		super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		
		self._setup_ui()
		self._populate_suggestions()
		
		if auto_connect:
			self.messageText.SetLabel(
				_("Could not automatically connect to RemBraille host. Please select or enter the host IP address manually:")
			)
	
	def _setup_ui(self):
		"""Setup dialog UI"""
		main_sizer = wx.BoxSizer(wx.VERTICAL)
		
		# Message
		if not self.auto_connect:
			message = _("Configure connection to RemBraille host:")
		else:
			message = _("Auto-connect failed. Please configure manually:")
		
		self.messageText = wx.StaticText(self, label=message)
		main_sizer.Add(self.messageText, flag=wx.ALL, border=10)
		
		# Settings panel
		settings_panel = wx.Panel(self)
		settings_sizer = wx.FlexGridSizer(3, 2, 10, 10)
		settings_sizer.AddGrowableCol(1)
		
		# Host IP
		ip_label = wx.StaticText(settings_panel, label=_("Host IP Address:"))
		self.ip_combo = wx.ComboBox(settings_panel, style=wx.CB_DROPDOWN)
		self.ip_combo.SetValue(self.driver._hostIP)
		
		settings_sizer.Add(ip_label, flag=wx.ALIGN_CENTER_VERTICAL)
		settings_sizer.Add(self.ip_combo, flag=wx.EXPAND)
		
		# Port
		port_label = wx.StaticText(settings_panel, label=_("Port:"))
		self.port_ctrl = wx.SpinCtrl(settings_panel, value=str(self.driver._port), min=1, max=65535)
		
		settings_sizer.Add(port_label, flag=wx.ALIGN_CENTER_VERTICAL)
		settings_sizer.Add(self.port_ctrl, flag=wx.EXPAND)
		
		# Auto-connect
		self.auto_connect_cb = wx.CheckBox(settings_panel, label=_("Automatically connect on startup"))
		self.auto_connect_cb.SetValue(self.driver.autoConnect)
		
		settings_sizer.Add(wx.StaticText(settings_panel, label=""))  # Empty cell
		settings_sizer.Add(self.auto_connect_cb)
		
		settings_panel.SetSizer(settings_sizer)
		main_sizer.Add(settings_panel, flag=wx.ALL | wx.EXPAND, border=10)
		
		# Buttons
		button_sizer = wx.BoxSizer(wx.HORIZONTAL)
		
		self.test_btn = wx.Button(self, label=_("Test Connection"))
		self.connect_btn = wx.Button(self, label=_("Connect"))
		cancel_btn = wx.Button(self, wx.ID_CANCEL, label=_("Cancel"))
		
		button_sizer.Add(self.test_btn, flag=wx.RIGHT, border=5)
		button_sizer.Add(self.connect_btn, flag=wx.RIGHT, border=5)
		button_sizer.Add(cancel_btn)
		
		main_sizer.Add(button_sizer, flag=wx.ALL | wx.ALIGN_RIGHT, border=10)
		
		# Bind events
		self.test_btn.Bind(wx.EVT_BUTTON, self._on_test)
		self.connect_btn.Bind(wx.EVT_BUTTON, self._on_connect)
		
		self.SetSizer(main_sizer)
		self.Fit()
		self.Center()
	
	def _populate_suggestions(self):
		"""Populate IP address suggestions"""
		suggestions = suggest_host_ips()
		
		for ip, description in suggestions:
			self.ip_combo.Append(f"{ip} ({description})", ip)
		
		# Set default if empty
		if not self.ip_combo.GetValue() and suggestions:
			self.ip_combo.SetSelection(0)
	
	def _on_test(self, event):
		"""Test connection without connecting permanently"""
		ip = self._get_selected_ip()
		port = self.port_ctrl.GetValue()
		
		if not ip:
			gui.messageBox(_("Please enter a host IP address."), _("Error"), wx.OK | wx.ICON_ERROR)
			return
		
		# Show testing message
		progress = gui.IndeterminateProgressDialog(
			self,
			_("RemBraille Connection Test"),
			_("Testing connection to {ip}:{port}...").format(ip=ip, port=port)
		)
		
		try:
			# Test connection in background thread
			test_com = RemBrailleCom()
			success = test_com.connect(ip, port)
			
			if success:
				cells = test_com.get_num_cells()
				test_com.disconnect()
				progress.done()
				
				gui.messageBox(
					_("Connection successful! Found {cells} braille cells.").format(cells=cells),
					_("Test Successful"),
					wx.OK | wx.ICON_INFORMATION
				)
			else:
				progress.done()
				gui.messageBox(
					_("Connection failed. Please check the IP address and ensure the RemBraille host server is running."),
					_("Test Failed"),
					wx.OK | wx.ICON_ERROR
				)
		except Exception as e:
			progress.done()
			log.error(f"Connection test error: {e}")
			gui.messageBox(
				_("Connection test failed: {error}").format(error=str(e)),
				_("Test Error"),
				wx.OK | wx.ICON_ERROR
			)
	
	def _on_connect(self, event):
		"""Connect to the selected host"""
		ip = self._get_selected_ip()
		port = self.port_ctrl.GetValue()
		auto_connect = self.auto_connect_cb.GetValue()
		
		if not ip:
			gui.messageBox(_("Please enter a host IP address."), _("Error"), wx.OK | wx.ICON_ERROR)
			return
		
		# Update driver settings
		self.driver._hostIP = ip
		self.driver._port = port
		self.driver.autoConnect = auto_connect
		self.driver._save_settings()
		
		# Show connecting message
		progress = gui.IndeterminateProgressDialog(
			self,
			_("RemBraille Connection"),
			_("Connecting to {ip}:{port}...").format(ip=ip, port=port)
		)
		
		try:
			# Connect
			success = self.driver._connect_to_host(ip, port)
			progress.done()
			
			if success:
				self.EndModal(wx.ID_OK)
			else:
				gui.messageBox(
					_("Connection failed. Please check the settings and ensure the RemBraille host server is running."),
					_("Connection Failed"),
					wx.OK | wx.ICON_ERROR
				)
		except Exception as e:
			progress.done()
			log.error(f"Connection error: {e}")
			gui.messageBox(
				_("Connection failed: {error}").format(error=str(e)),
				_("Connection Error"),
				wx.OK | wx.ICON_ERROR
			)
	
	def _get_selected_ip(self) -> str:
		"""Get the selected or entered IP address"""
		value = self.ip_combo.GetValue().strip()
		
		# If it's a suggestion with description, extract just the IP
		if " (" in value:
			return value.split(" (")[0]
		
		return value