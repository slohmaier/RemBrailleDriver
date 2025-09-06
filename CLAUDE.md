# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **RemBraille NVDA add-on project** that creates a braille driver for NVDA running on Windows guest systems (Parallels, VMware Fusion, VMware Workstation, VirtualBox). The add-on connects to a TCP server on the host PC to provide braille display interface between the guest system's NVDA and the host system's braille display.

## Architecture

This project uses the **NVDA Add-on Template** structure:

- **Build System**: SCons-based build system (`sconstruct`) with build variables defined in `buildVars.py`
- **Configuration**: Build customization via `buildVars.py` - modify addon metadata, version, sources, and exclusions here
- **Addon Structure**: The actual addon code should be placed in an `addon/` directory (not yet created)
- **NVDA Integration**: Requires NVDA source at `../nvda/` relative to this directory for development
- **Localization**: Uses gettext with `.po` files in `addon/locale/<lang>/LC_MESSAGES/`
- **Documentation**: Markdown files in `addon/doc/<lang>/` converted to HTML during build

## Development Commands

### Environment Setup
```bash
# Install development dependencies
pip install pre-commit scons markdown ruff pyright

# Install gettext tools (Windows)
# Download from https://gnuwin32.sourceforge.net/downlinks/gettext.php

# Setup pre-commit hooks
pre-commit install
```

### Build Commands
```bash
# Build addon package
scons

# Build with custom version
scons version=1.0.0

# Build development version (uses current date)
scons dev=1

# Generate translation template
scons pot

# Clean build artifacts
scons -c
```

### Code Quality
```bash
# Run all pre-commit checks
pre-commit run --all

# Run specific checks
ruff check .          # Linting
ruff format .         # Code formatting  
pyright              # Type checking
```

### Testing
```bash
# Run GitHub Actions locally (if act installed)
act

# Manual testing requires:
# 1. Install built .nvda-addon file in NVDA
# 2. Test in VM environment with host TCP server
```

## Key Configuration Files

- **`buildVars.py`**: Main configuration - update addon metadata, version, python sources, and i18n sources
- **`pyproject.toml`**: Ruff and Pyright configuration with strict type checking enabled
- **`sconstruct`**: SCons build script (rarely needs modification)
- **`manifest.ini.tpl`**: Template for addon manifest (auto-generated from buildVars.py)

## Development Notes

- **NVDA Dependency**: VS Code expects NVDA source code at `../nvda/` for IntelliSense
- **Python Version**: Uses Python 3.11+ (3.13.7 currently available)
- **Code Style**: Uses tabs for indentation, enforced by Ruff
- **Type Checking**: Strict Pyright configuration enabled
- **Addon Directory**: ✅ **IMPLEMENTED** - Complete addon structure created:
  - `addon/brailleDisplayDrivers/` - RemBraille display drivers
  - `addon/globalPlugins/` - Settings management plugin
  - `addon/locale/` - Translation support (structure ready)
  - `addon/doc/` - User documentation

## RemBraille Implementation Status

✅ **COMPLETED** - Full implementation includes:

1. **RemBrailleCom class**: Complete TCP communication protocol in `remBrailleCom.py`
2. **Host IP Detection**: Automatic VM host detection in `hostDetection.py` 
3. **Connection Management**: Auto-reconnect and connection handling
4. **Settings Panel**: NVDA settings integration and connection dialogs
5. **Error Handling**: Comprehensive error handling with user dialogs
6. **Braille Driver**: Full driver implementation in `remBraille.py`
7. **Global Plugin**: Settings management in `remBrailleSettings.py`
8. **Test Server**: Development server in `rembraille_server.py`

### Implementation Details

**Core Files:**
- `addon/brailleDisplayDrivers/remBraille.py` - Main NVDA braille driver
- `addon/brailleDisplayDrivers/remBrailleCom.py` - TCP protocol implementation  
- `addon/brailleDisplayDrivers/hostDetection.py` - VM host IP detection
- `addon/globalPlugins/remBrailleSettings.py` - Settings UI and management
- `rembraille_server.py` - Dummy server for testing

**Protocol:**
- Port 17635, custom message format with version/type/length/data
- Handshake, cell display, key events, ping/pong, error messages
- Thread-safe with background receive/ping loops

**VM Detection:**
- Supports VMware, VirtualBox, Parallels, Hyper-V
- Gateway analysis, ARP table parsing, network interface scanning
- Platform-specific IP detection patterns

## GitHub Actions

- **Automatic builds** on pull requests and tags
- **Release creation** when tags are pushed (format: `git tag v1.0 && git push --tag`)
- **Artifact upload** for manual builds via workflow dispatch