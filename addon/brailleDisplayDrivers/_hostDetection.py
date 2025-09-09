# A part of NonVisual Desktop Access (NVDA)
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.
# Copyright (C) 2025 Stefan Lohmaier

"""
Host IP Detection for RemBraille
Automatically detects the IP address of the host system when running in a VM
"""

import socket
import subprocess
import ipaddress
import re
from typing import List, Optional, Tuple
from logHandler import log


def get_vm_host_ip() -> Optional[str]:
	"""
	Detect the IP address of the host system when running in a VM
	
	Tries multiple methods to detect the host IP:
	1. Check for VMware host IP (.1 address on VM network)
	2. Check for VirtualBox host IP (usually .1 on host-only network)
	3. Check for Parallels host IP
	4. Parse VM-specific network information
	
	@return: Host IP address if detected, None otherwise
	"""
	
	# Method 1: Try common VM host IP patterns
	vm_host_candidates = _get_vm_host_candidates()
	for host_ip in vm_host_candidates:
		if _test_host_connectivity(host_ip):
			log.info(f"Detected VM host IP: {host_ip}")
			return host_ip
	
	# Method 2: Try to detect from network interfaces
	interface_host = _detect_from_network_interfaces()
	if interface_host and _test_host_connectivity(interface_host):
		log.info(f"Detected host IP from network interfaces: {interface_host}")
		return interface_host
	
	# Method 3: Try to detect from ARP table
	arp_host = _detect_from_arp_table()
	if arp_host and _test_host_connectivity(arp_host):
		log.info(f"Detected host IP from ARP table: {arp_host}")
		return arp_host
	
	log.warning("Could not detect VM host IP automatically")
	return None


def _get_vm_host_candidates() -> List[str]:
	"""Get list of candidate host IP addresses based on local network configuration"""
	candidates = []
	
	try:
		# Get local IP addresses
		local_ips = _get_local_ip_addresses()
		
		for local_ip in local_ips:
			try:
				network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
				
				# Common VM host IP patterns
				host_candidates = [
					str(network.network_address + 1),  # .1 (common for VMware, VirtualBox)
					str(network.network_address + 2),  # .2 (alternative)
					str(network.broadcast_address - 1),  # Last IP minus 1
				]
				
				# Specific VM platform IPs
				if "192.168" in str(network):
					# VMware typical ranges
					if str(network).startswith("192.168."):
						candidates.extend([
							"192.168.1.1",
							"192.168.0.1",
							"192.168.56.1",  # VirtualBox host-only
							"192.168.137.1",  # Hyper-V
						])
				
				# Filter out localhost and our own IP
				for candidate in host_candidates:
					if candidate != local_ip and not candidate.endswith(".0") and not candidate.endswith(".255"):
						candidates.append(candidate)
						
			except (ipaddress.AddressValueError, ValueError):
				continue
	
	except Exception as e:
		log.error(f"Error getting VM host candidates: {e}")
	
	# Remove duplicates while preserving order
	return list(dict.fromkeys(candidates))


def _get_local_ip_addresses() -> List[str]:
	"""Get list of local IP addresses"""
	local_ips = []
	
	try:
		# Method 1: Use socket to connect to external address
		with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
			s.connect(("8.8.8.8", 80))
			local_ip = s.getsockname()[0]
			if local_ip and local_ip != "127.0.0.1":
				local_ips.append(local_ip)
	except:
		pass
	
	try:
		# Method 2: Get all network interfaces
		hostname = socket.gethostname()
		ip_list = socket.gethostbyname_ex(hostname)[2]
		for ip in ip_list:
			if not ip.startswith("127.") and ip not in local_ips:
				local_ips.append(ip)
	except:
		pass
	
	return local_ips


def _detect_from_network_interfaces() -> Optional[str]:
	"""Try to detect host IP from network interface information"""
	try:
		# Windows: Use ipconfig to get default gateway
		if _is_windows():
			result = subprocess.run(
				["ipconfig", "/all"],
				capture_output=True,
				text=True,
				timeout=10
			)
			
			if result.returncode == 0:
				# Look for default gateway
				gateway_pattern = r"Default Gateway.*?:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)"
				matches = re.findall(gateway_pattern, result.stdout, re.IGNORECASE)
				
				for gateway in matches:
					if not gateway.startswith("0.") and not gateway.startswith("127."):
						return gateway
		
		# Linux/Unix: Use route or ip command
		else:
			# Try 'ip route' first
			try:
				result = subprocess.run(
					["ip", "route", "show", "default"],
					capture_output=True,
					text=True,
					timeout=10
				)
				
				if result.returncode == 0:
					# Parse: default via X.X.X.X dev ...
					match = re.search(r"default via ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", result.stdout)
					if match:
						return match.group(1)
			except:
				pass
			
			# Try 'route' command as fallback
			try:
				result = subprocess.run(
					["route", "-n", "get", "default"],
					capture_output=True,
					text=True,
					timeout=10
				)
				
				if result.returncode == 0:
					match = re.search(r"gateway: ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", result.stdout)
					if match:
						return match.group(1)
			except:
				pass
	
	except Exception as e:
		log.debug(f"Error detecting from network interfaces: {e}")
	
	return None


def _detect_from_arp_table() -> Optional[str]:
	"""Try to detect host IP from ARP table"""
	try:
		if _is_windows():
			result = subprocess.run(
				["arp", "-a"],
				capture_output=True,
				text=True,
				timeout=10
			)
		else:
			result = subprocess.run(
				["arp", "-a"],
				capture_output=True,
				text=True,
				timeout=10
			)
		
		if result.returncode == 0:
			# Look for entries that might be the host
			lines = result.stdout.split('\n')
			for line in lines:
				# Look for .1 addresses (common host IPs)
				if re.search(r'\b\d+\.\d+\.\d+\.1\b', line):
					match = re.search(r'(\d+\.\d+\.\d+\.1)', line)
					if match:
						host_ip = match.group(1)
						# Exclude obvious non-host IPs
						if not host_ip.startswith(("127.", "169.254.")):
							return host_ip
	
	except Exception as e:
		log.debug(f"Error detecting from ARP table: {e}")
	
	return None


def _test_host_connectivity(host_ip: str, port: int = 17635) -> bool:
	"""
	Test if the host IP has a RemBraille server running
	
	@param host_ip: IP address to test
	@param port: Port to test (default: RemBraille port)
	@return: True if connection possible, False otherwise
	"""
	try:
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
			sock.settimeout(2.0)  # Short timeout for detection
			result = sock.connect_ex((host_ip, port))
			return result == 0
	except:
		return False


def _is_windows() -> bool:
	"""Check if running on Windows"""
	import platform
	return platform.system().lower() == "windows"


def get_vm_platform() -> Optional[str]:
	"""
	Try to detect which VM platform we're running on
	
	@return: VM platform name ("vmware", "virtualbox", "parallels", "hyper-v") or None
	"""
	try:
		# Check for VM indicators in system information
		if _is_windows():
			# Check Windows system info
			result = subprocess.run(
				["systeminfo"],
				capture_output=True,
				text=True,
				timeout=15
			)
			
			if result.returncode == 0:
				output = result.stdout.lower()
				
				if "vmware" in output:
					return "vmware"
				elif "virtualbox" in output or "vbox" in output:
					return "virtualbox"
				elif "parallels" in output:
					return "parallels"
				elif "hyper-v" in output or "microsoft" in output:
					return "hyper-v"
		
		else:
			# Check for VM indicators in Linux
			try:
				# Check DMI information
				with open("/sys/class/dmi/id/product_name", "r") as f:
					product = f.read().lower().strip()
					
				if "vmware" in product:
					return "vmware"
				elif "virtualbox" in product:
					return "virtualbox"
				elif "parallels" in product:
					return "parallels"
			except:
				pass
	
	except Exception as e:
		log.debug(f"Error detecting VM platform: {e}")
	
	return None


def suggest_host_ips() -> List[Tuple[str, str]]:
	"""
	Get a list of suggested host IPs with descriptions
	
	@return: List of (ip, description) tuples
	"""
	suggestions = []
	
	# Add localhost first for debugging
	suggestions.append(("127.0.0.1", "Localhost (for debugging/testing)"))
	
	# Add automatically detected IP if available
	auto_ip = get_vm_host_ip()
	if auto_ip:
		suggestions.append((auto_ip, "Auto-detected VM host"))
	
	# Add common VM host IPs
	platform = get_vm_platform()
	
	common_ips = [
		("192.168.1.1", "Common router/host IP"),
		("192.168.0.1", "Common router/host IP"),
		("192.168.56.1", "VirtualBox host-only adapter"),
		("192.168.137.1", "Windows Hyper-V"),
		("10.0.2.2", "VirtualBox NAT gateway"),
		("172.16.0.1", "VMware host IP"),
	]
	
	# Platform-specific suggestions
	if platform == "vmware":
		suggestions.extend([
			("192.168.142.1", "VMware Workstation host"),
			("192.168.91.1", "VMware Fusion host"),
		])
	elif platform == "virtualbox":
		suggestions.extend([
			("192.168.56.1", "VirtualBox host-only"),
			("10.0.2.2", "VirtualBox NAT gateway"),
		])
	elif platform == "parallels":
		suggestions.extend([
			("10.211.55.2", "Parallels shared networking"),
			("192.168.1.1", "Parallels bridged networking"),
		])
	
	# Add common IPs (avoiding duplicates)
	existing_ips = {ip for ip, _ in suggestions}
	for ip, desc in common_ips:
		if ip not in existing_ips:
			suggestions.append((ip, desc))
	
	return suggestions