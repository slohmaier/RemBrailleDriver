# A part of NonVisual Desktop Access (NVDA)
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.
# Copyright (C) 2025 Stefan Lohmaier

"""
RemBraille Global Plugin
Provides global settings and management for RemBraille connection
"""

import wx
import globalPluginHandler
import gui
from gui import guiHelper, settingsDialogs
import braille
from logHandler import log
import scriptHandler
import api


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Global plugin for RemBraille management"""
	
	def __init__(self):
		super().__init__()
		
		# Add to NVDA menu
		self._add_menu_items()
	
	def _add_menu_items(self):
		"""Add RemBraille items to NVDA menu"""
		try:
			# Add to Tools menu
			tools_menu = gui.mainFrame.sysTrayIcon.toolsMenu
			
			# RemBraille submenu
			self.rembraille_menu = wx.Menu()
			
			# Connection item
			self.connection_item = self.rembraille_menu.Append(
				wx.ID_ANY,
				_("Connection Settings..."),
				_("Configure RemBraille host connection")
			)
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self._on_connection_settings, self.connection_item)
			
			# Status item
			self.status_item = self.rembraille_menu.Append(
				wx.ID_ANY,
				_("Connection Status"),
				_("Show RemBraille connection status")
			)
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self._on_connection_status, self.status_item)
			
			# Reconnect item
			self.reconnect_item = self.rembraille_menu.Append(
				wx.ID_ANY,
				_("Reconnect"),
				_("Reconnect to RemBraille host")
			)
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self._on_reconnect, self.reconnect_item)
			
			# Add submenu to Tools
			tools_menu.AppendSubMenu(self.rembraille_menu, _("RemBraille"))
			
		except Exception as e:
			log.error(f"Failed to add RemBraille menu items: {e}")
	
	def _on_connection_settings(self, event):
		"""Show connection settings dialog"""
		try:
			# Get current braille driver
			if braille.handler.display.name == "remBraille":
				from brailleDisplayDrivers.remBraille import RemBrailleConnectionDialog
				dialog = RemBrailleConnectionDialog(gui.mainFrame, braille.handler.display)
				dialog.ShowModal()
				dialog.Destroy()
			else:
				gui.messageBox(
					_("RemBraille is not the current braille display driver. Please select RemBraille in NVDA Settings > Braille first."),
					_("RemBraille Not Active"),
					wx.OK | wx.ICON_INFORMATION
				)
		except Exception as e:
			log.error(f"Error showing connection settings: {e}")
			gui.messageBox(
				_("Failed to show connection settings: {error}").format(error=str(e)),
				_("Error"),
				wx.OK | wx.ICON_ERROR
			)
	
	def _on_connection_status(self, event):
		"""Show connection status"""
		try:
			if braille.handler.display.name == "remBraille":
				display = braille.handler.display
				if display.connected:
					message = _(
						"RemBraille Status: Connected\n"
						"Host: {host}:{port}\n"
						"Cells: {cells}"
					).format(
						host=display._hostIP,
						port=display._port,
						cells=display.numCells
					)
					title = _("RemBraille Connected")
					icon = wx.ICON_INFORMATION
				else:
					message = _("RemBraille Status: Disconnected")
					title = _("RemBraille Disconnected")
					icon = wx.ICON_WARNING
			else:
				message = _("RemBraille is not the current braille display driver.")
				title = _("RemBraille Not Active")
				icon = wx.ICON_INFORMATION
			
			gui.messageBox(message, title, wx.OK | icon)
			
		except Exception as e:
			log.error(f"Error showing connection status: {e}")
			gui.messageBox(
				_("Failed to get connection status: {error}").format(error=str(e)),
				_("Error"),
				wx.OK | wx.ICON_ERROR
			)
	
	def _on_reconnect(self, event):
		"""Reconnect to RemBraille host"""
		try:
			if braille.handler.display.name == "remBraille":
				display = braille.handler.display
				
				# Show progress dialog
				progress = gui.IndeterminateProgressDialog(
					gui.mainFrame,
					_("RemBraille Reconnect"),
					_("Reconnecting to RemBraille host...")
				)
				
				try:
					# Disconnect and reconnect
					display._disconnect_from_host()
					wx.CallAfter(lambda: display._auto_connect())
					
					progress.done()
					gui.messageBox(
						_("Reconnection initiated. Check connection status in a few seconds."),
						_("RemBraille Reconnect"),
						wx.OK | wx.ICON_INFORMATION
					)
				except Exception as e:
					progress.done()
					raise e
			else:
				gui.messageBox(
					_("RemBraille is not the current braille display driver."),
					_("RemBraille Not Active"),
					wx.OK | wx.ICON_INFORMATION
				)
		except Exception as e:
			log.error(f"Error reconnecting: {e}")
			gui.messageBox(
				_("Failed to reconnect: {error}").format(error=str(e)),
				_("Reconnect Error"),
				wx.OK | wx.ICON_ERROR
			)
	
	def terminate(self):
		"""Clean up when plugin is terminated"""
		try:
			# Remove menu items
			if hasattr(self, 'rembraille_menu'):
				tools_menu = gui.mainFrame.sysTrayIcon.toolsMenu
				# Find and remove our submenu
				for i in range(tools_menu.GetMenuItemCount()):
					item = tools_menu.FindItemByPosition(i)
					if item and item.GetItemLabel() == _("RemBraille"):
						tools_menu.Delete(item.GetId())
						break
		except Exception as e:
			log.debug(f"Error during RemBraille plugin termination: {e}")
		
		super().terminate()
	
	@scriptHandler.script(
		description=_("Show RemBraille connection status"),
		category=_("RemBraille")
	)
	def script_rembraille_status(self, gesture):
		"""Script to announce RemBraille connection status"""
		try:
			if braille.handler.display.name == "remBraille":
				display = braille.handler.display
				if display.connected:
					message = _("RemBraille connected to {host} with {cells} cells").format(
						host=display._hostIP,
						cells=display.numCells
					)
				else:
					message = _("RemBraille disconnected")
			else:
				message = _("RemBraille driver not active")
			
			api.speakText(message)
		except Exception as e:
			log.error(f"Error in RemBraille status script: {e}")
			api.speakText(_("RemBraille status unavailable"))
	
	@scriptHandler.script(
		description=_("Reconnect to RemBraille host"),
		category=_("RemBraille")
	)
	def script_rembraille_reconnect(self, gesture):
		"""Script to reconnect to RemBraille host"""
		try:
			if braille.handler.display.name == "remBraille":
				display = braille.handler.display
				
				api.speakText(_("Reconnecting to RemBraille host"))
				
				# Disconnect and reconnect
				display._disconnect_from_host()
				wx.CallAfter(display._auto_connect)
			else:
				api.speakText(_("RemBraille driver not active"))
		except Exception as e:
			log.error(f"Error in RemBraille reconnect script: {e}")
			api.speakText(_("RemBraille reconnect failed"))
	
	def getScript(self, gesture):
		"""Get script for gesture"""
		# Allow gesture passthrough for RemBraille-specific gestures
		if gesture.source == "remBraille":
			return None
		
		return super().getScript(gesture)