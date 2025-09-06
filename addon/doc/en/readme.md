# RemBraille - Virtual Machine Braille Display Driver

RemBraille provides braille display support for NVDA running in virtual machines by connecting to the host system's braille display via TCP.

## Features

- **Automatic Host Detection**: Automatically detects the IP address of the host system when running in common VM environments (VMware, VirtualBox, Parallels, Hyper-V)
- **Manual Configuration**: Allows manual IP and port configuration through NVDA settings
- **Seamless Integration**: Works transparently with NVDA's braille system
- **Connection Management**: Automatic reconnection on connection loss
- **Multi-Platform Support**: Works with various VM platforms and host operating systems

## Supported Virtual Machine Platforms

- VMware Workstation / VMware Fusion
- VirtualBox
- Parallels Desktop
- Microsoft Hyper-V
- Other VM platforms with TCP networking

## Setup

### Host System Requirements

The host system must be running a RemBraille server application that:
1. Connects to the physical braille display
2. Listens on TCP port 17635 (default)
3. Forwards braille display data between NVDA guest and physical display

### Guest System Setup

1. Install this RemBraille add-on in NVDA
2. Go to NVDA Settings > Braille
3. Select "RemBraille (VM Host Connection)" as your braille display
4. The add-on will attempt to auto-detect the host IP
5. If auto-detection fails, manually configure the host IP address

## Configuration

### Automatic Detection

RemBraille will automatically attempt to detect the host system IP address using:
- Common VM network configurations
- Gateway detection
- ARP table analysis
- Platform-specific network patterns

### Manual Configuration

If automatic detection fails, you can manually configure:

1. **Host IP Address**: The IP address of your host system
2. **Port**: TCP port number (default: 17635)
3. **Auto-connect**: Whether to automatically connect on NVDA startup

Access these settings through:
- NVDA Settings > Braille (when RemBraille is selected as the display)
- Tools > RemBraille > Connection Settings

## Usage

Once configured and connected:

1. RemBraille appears as a regular braille display to NVDA
2. Braille output is sent to the host system's physical display
3. Key input from the physical display is forwarded to NVDA
4. Connection status is shown in the system tray menu

### Menu Options

The **Tools > RemBraille** menu provides:
- **Connection Settings**: Configure host IP and port
- **Connection Status**: View current connection state
- **Reconnect**: Manually reconnect to the host

### Keyboard Shortcuts

- **NVDA+Control+R**: Announce RemBraille connection status
- **NVDA+Control+Shift+R**: Reconnect to RemBraille host

## Troubleshooting

### Connection Issues

1. **Verify host server is running**: Ensure the RemBraille host server is active
2. **Check firewall settings**: Host firewall may block port 17635
3. **Network connectivity**: Verify guest can reach host IP
4. **VM network mode**: Ensure VM network mode allows host communication

### Common Solutions

- **Bridged networking**: Use bridged network mode for direct IP connectivity
- **Host-only networking**: Configure host-only adapter for VM-host communication
- **Port forwarding**: Set up port forwarding if using NAT networking

### Log Information

Check NVDA log (NVDA+F1) for RemBraille connection details and error messages.

## Support

For support and updates, visit: https://slohmaier.de/rembraille

## License

This add-on is released under the GNU General Public License v2.