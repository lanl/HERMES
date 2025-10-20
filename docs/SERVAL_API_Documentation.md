# SERVAL API Documentation

## Overview

SERVAL (Timepix3 Server Software) is a Java-based acquisition server that provides complete control over TPX3 neutron imaging detectors. It runs as a standalone HTTP server and communicates with the detector hardware over TCP/IP, offering a comprehensive REST API for detector control, measurement configuration, and data acquisition.

**Key Features:**
- HTTP REST API for all operations
- Real-time detector control and monitoring
- Flexible data output (files, TCP streams, HTTP endpoints)
- Live preview and histogram generation
- Complete detector configuration management
- Multi-chip detector support

---

## Table of Contents

1. [Installation and Setup](#installation-and-setup)
2. [Network Configuration](#network-configuration)
3. [Starting SERVAL](#starting-serval)
4. [API Overview](#api-overview)
5. [API Reference](#api-reference)
   - [Server Management](#server-management)
   - [Detector Control](#detector-control)
   - [Measurement Control](#measurement-control)
   - [Configuration Management](#configuration-management)
   - [Dashboard](#dashboard)
6. [Data Models](#data-models)
7. [Usage Examples](#usage-examples)
8. [Troubleshooting](#troubleshooting)

---

## Installation and Setup

### System Requirements

**Operating System:**
- Ubuntu 22.04 LTS (recommended)
- Other Linux distributions supported

**Java Environment:**
- Java 11 or later required
- Java 21 recommended for optimal performance

**Verification:**
```bash
java --version
javac --version
```

### Hardware Requirements
- Network interface for detector communication (10 Gb/s or 1 Gb/s Ethernet)
- Sufficient disk space for data acquisition
- RAM: 8GB minimum, 16GB+ recommended for high-speed acquisition

---

## Network Configuration

### Required Network Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 8080 | TCP | SERVAL HTTP API server |
| 50000 | TCP | Detector control connection |
| 8192-8195 | UDP | Detector data channels (events/images) |

### Firewall Configuration (Ubuntu UFW)

```bash
# Allow SERVAL communication ports
sudo ufw allow 8080/tcp
sudo ufw allow 50000/tcp
sudo ufw allow 8192:8195/udp

# Verify configuration
sudo ufw status numbered
```

### Network Interface Setup

Configure static IP addresses based on connection speed:

**For 10 Gb/s connection:**
- Workstation: `192.168.100.1`
- Detector: `192.168.100.10`

**For 1 Gb/s connection:**
- Workstation: `192.168.1.1`
- Detector: `192.168.1.10`

#### Example Netplan Configuration

```yaml
# /etc/netplan/01-detector-config.yaml
network:
  version: 2
  ethernets:
    enp4s0:  # Replace with your interface name
      dhcp4: false
      addresses:
        - 192.168.100.1/24  # For 10 Gb/s
      mtu: 9000
```

Apply configuration:
```bash
sudo netplan apply
```

### MTU and Jumbo Frame Settings

**For high-speed acquisition (recommended):**
```bash
# Set MTU to 9000 for jumbo frames
sudo ip link set dev enp4s0 mtu 9000

# Verify setting
ip link show enp4s0
```

### Connection Verification

```bash
# 1. Verify detector connectivity
ping 192.168.100.10

# 2. Check network interface
ip addr show enp4s0

# 3. Test firewall rules
sudo ufw status
```

---

## Starting SERVAL

### Basic Usage

```bash
# Start SERVAL (replace with actual version)
java -jar serval-3.3.0.jar

# View available options
java -jar serval-3.3.0.jar --help
```

### Startup Process

1. **Detector Discovery**: SERVAL automatically scans for connected cameras
2. **Network Interface Check**: Verifies available network interfaces
3. **HTTP Server Launch**: Starts webserver on port 8080
4. **Ready State**: Server becomes available for client connections

### Verification

**Local connection test:**
```bash
curl http://127.0.0.1:8080/
# Expected: "Welcome to SERVAL – Timepix3 Server Software"
```

**Remote connection test:**
```bash
curl http://192.168.100.1:8080/
# Expected: HTTP 200 OK with welcome message
```

---

## API Overview

### Communication Protocol

SERVAL uses standard HTTP request-response communication:

- **GET**: Retrieve information or trigger actions
- **PUT**: Upload configuration data (JSON objects)
- **Content-Type**: `application/json` for structured data
- **Response Format**: JSON objects, plain text, or binary data

### URL Structure

```
<method> <server>/<namespace>/<command>[?<parameter>=<value>&...]
```

**Example:**
```
GET http://192.168.100.1:8080/detector/config
PUT http://192.168.100.1:8080/server/destination
```

### HTTP Response Codes

| Code | Status | Description |
|------|--------|-------------|
| 200 | OK | Request successful |
| 204 | No Content | Request fulfilled, no response data |
| 302 | Moved Temporarily | Server redirect |
| 400 | Bad Request | Invalid syntax or parameters |
| 401 | Unauthorized | Authentication required |
| 404 | Not Found | Endpoint not found |
| 409 | Conflict | Resource conflict |
| 500 | Internal Error | Server error |
| 503 | Service Unavailable | Temporary overload |

### API Namespaces

| Namespace | Purpose |
|-----------|---------|
| `/` | Welcome message |
| `/*` | Complete JSON hierarchy |
| `/server` | Server configuration and control |
| `/detector` | Detector hardware control |
| `/measurement` | Acquisition and data control |
| `/config` | File-based configuration management |
| `/dashboard` | System status overview |

---

## API Reference

### Server Management (`/server`)

#### Server Information and Control

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/server` | JSON object | Complete server information |
| GET | `/server/shutdown` | Text | Terminate SERVAL process |

#### Destination Configuration

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/server/destination` | JSON object | Current data output configuration |
| PUT | `/server/destination` | Success message | Upload destination configuration |

**Destination Configuration Structure:**
```json
{
  "Raw": [
    {
      "Base": "file:///data/raw/",
      "FilePattern": "run_%Y%m%d_%H%M%S_",
      "SplitStrategy": "single_file",
      "QueueSize": 16384
    }
  ],
  "Image": [
    {
      "Base": "file:///data/images/",
      "FilePattern": "img_%05d.tiff",
      "Format": "tiff",
      "Mode": "tot",
      "QueueSize": 1024
    }
  ],
  "Preview": {
    "Period": 0.1,
    "SamplingMode": "skipOnPeriod",
    "ImageChannels": [
      {
        "Base": "http://localhost:8080",
        "Format": "pgm",
        "Mode": "tot"
      }
    ]
  }
}
```

### Detector Control (`/detector`)

#### Connection Management

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/detector/list` | JSON array | Available detectors |
| GET | `/detector/connect` | Text | Connect to first detector |
| GET | `/detector/disconnect` | Text | Disconnect current detector |

#### Detector Information

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/detector` | JSON object | Complete detector settings |
| GET | `/detector/info` | JSON object | Static detector metadata |
| GET | `/detector/health` | JSON object | Environmental telemetry |
| GET | `/detector/layout` | JSON object | Chip layout and orientation |
| GET | `/detector/config` | JSON object | Runtime configuration |

#### Chip-Level Control

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/detector/chips` | JSON array | All chip configurations |
| GET | `/detector/chips/{chip}` | JSON object | Single chip configuration |
| GET | `/detector/chips/{chip}/dacs` | JSON object | DAC values for chip |
| GET | `/detector/chips/{chip}/pixelconfig` | JSON/Binary | Per-pixel configuration |
| PUT | `/detector/chips/{chip}/dacs` | Success message | Update DAC values |
| PUT | `/detector/chips/{chip}/pixelconfig` | Success message | Update pixel configuration |

#### Layout Control

| Method | Endpoint | Parameters | Description |
|--------|----------|------------|-------------|
| GET | `/detector/layout/rotate` | `direction=left\|right\|180` | Rotate detector image |
| GET | `/detector/layout/rotate` | `flip=horizontal\|vertical` | Flip detector image |
| GET | `/detector/layout/rotate` | `reset` | Reset to default orientation |

### Measurement Control (`/measurement`)

#### Acquisition Control

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/measurement/start` | Text | Start data acquisition |
| GET | `/measurement/stop` | Text | Stop current acquisition |
| GET | `/measurement/preview` | Text | Start preview mode only |

#### Data Retrieval

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/measurement` | JSON object | Complete measurement status |
| GET | `/measurement/config` | JSON object | Measurement configuration |
| GET | `/measurement/image` | Binary | Live preview image |
| GET | `/measurement/histogram` | JSON/Binary | Histogram data |

#### Configuration Upload

| Method | Endpoint | Data Type | Description |
|--------|----------|-----------|-------------|
| PUT | `/measurement/config` | JSON object | Measurement parameters |
| PUT | `/measurement/config/corrections` | JSON object | Correction settings |
| PUT | `/measurement/config/timeofflight` | JSON object | Time-of-flight parameters |

### Configuration Management (`/config`)

#### File Operations

| Method | Endpoint | Parameters | Description |
|--------|----------|------------|-------------|
| GET | `/config/load` | `format=dacs&file=path` | Load DAC configuration |
| GET | `/config/load` | `format=pixelconfig&file=path` | Load pixel configuration |
| GET | `/config/load` | `format=serval&file=path` | Load complete SERVAL state |
| GET | `/config/store` | `format=serval&file=path` | Save complete SERVAL state |

**Supported Formats:**
- `serval`: Complete SERVAL configuration (JSON)
- `pixelconfig`: Per-pixel configuration (binary .bpc)
- `dacs`: DAC configuration (JSON or .dacs)

### Dashboard (`/dashboard`)

#### System Status

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/dashboard` | JSON object | Consolidated system status |

**Dashboard Response Structure:**
```json
{
  "server": {
    "status": "running",
    "uptime": 3600,
    "version": "3.3.0"
  },
  "detector": {
    "connected": true,
    "temperature": 25.5,
    "bias_enabled": true,
    "bias_voltage": 100.0
  },
  "measurement": {
    "active": true,
    "frame_count": 1500,
    "elapsed_time": 150.0,
    "acquisition_rate": 10.0
  }
}
```

---

## Data Models

### Detector Configuration Object

```json
{
  "LogLevel": 2,
  "Fan1PWM": 50,
  "Fan2PWM": 50,
  "BiasVoltage": 100.0,
  "BiasEnabled": true,
  "Polarity": "Positive",
  "PeriphClk80": false,
  "ChainMode": "NONE",
  "TriggerIn": 1,
  "TriggerOut": 1,
  "TriggerPeriod": 0.1,
  "ExposureTime": 0.05,
  "TriggerDelay": 0.0,
  "TriggerMode": "EXTERNAL",
  "nTriggers": 1000,
  "GlobalTimestampInterval": 0.0,
  "ExternalReferenceClock": false
}
```

### Detector Health Object

```json
{
  "LocalTemperature": 25.5,
  "FPGATemperature": 35.2,
  "ChipTemperatures": [28.1, 28.3, 27.9, 28.0],
  "Fan1Speed": 2500,
  "Fan2Speed": 2500,
  "AVDD": [3.3, 1.2, 3.96],
  "VDD": [1.8, 2.1, 3.78],
  "BiasVoltage": 100.0,
  "Humidity": 45
}
```

### DAC Configuration Object

```json
{
  "Ibias_Preamp_ON": 128,
  "Ibias_Preamp_OFF": 8,
  "VPreamp_NCAS": 128,
  "Ibias_Ikrum": 16,
  "Vfbk": 164,
  "Vthreshold_fine": 256,
  "Vthreshold_coarse": 8,
  "Ibias_DiscS1_ON": 128,
  "Ibias_DiscS1_OFF": 8,
  "Ibias_DiscS2_ON": 128,
  "Ibias_DiscS2_OFF": 8,
  "Ibias_PixelDAC": 128,
  "Ibias_TPbufferIn": 128,
  "Ibias_TPbufferOut": 128,
  "VTP_coarse": 128,
  "VTP_fine": 256,
  "Ibias_CP_PLL": 128,
  "PLL_Vcntrl": 128
}
```

---

## Usage Examples

### Complete Acquisition Workflow

```python
import requests
import json
from pathlib import Path

class ServalClient:
    def __init__(self, host="192.168.100.1", port=8080):
        self.base_url = f"http://{host}:{port}"
    
    def connect_detector(self):
        """Connect to the first available detector"""
        response = requests.get(f"{self.base_url}/detector/connect")
        return response.status_code == 200
    
    def load_calibration(self, bpc_file, dacs_file):
        """Load calibration files"""
        # Load pixel configuration
        response = requests.get(
            f"{self.base_url}/config/load",
            params={"format": "pixelconfig", "file": bpc_file}
        )
        if response.status_code != 200:
            raise RuntimeError(f"Failed to load BPC file: {response.text}")
        
        # Load DAC configuration
        response = requests.get(
            f"{self.base_url}/config/load",
            params={"format": "dacs", "file": dacs_file}
        )
        if response.status_code != 200:
            raise RuntimeError(f"Failed to load DACs file: {response.text}")
    
    def configure_detector(self, config):
        """Upload detector configuration"""
        response = requests.put(
            f"{self.base_url}/detector/config",
            json=config
        )
        return response.status_code == 200
    
    def setup_destination(self, output_dir):
        """Configure data output destination"""
        destination = {
            "Raw": [{
                "Base": f"file://{output_dir}/raw/",
                "FilePattern": "run_%Y%m%d_%H%M%S.tpx3",
                "SplitStrategy": "single_file"
            }],
            "Image": [{
                "Base": f"file://{output_dir}/images/",
                "FilePattern": "img_%05d.tiff",
                "Format": "tiff",
                "Mode": "tot"
            }],
            "Preview": {
                "Period": 0.1,
                "SamplingMode": "skipOnPeriod",
                "ImageChannels": [{
                    "Base": "http://localhost:8080",
                    "Format": "pgm",
                    "Mode": "tot"
                }]
            }
        }
        
        response = requests.put(
            f"{self.base_url}/server/destination",
            json=destination
        )
        return response.status_code == 200
    
    def start_measurement(self):
        """Start data acquisition"""
        response = requests.get(f"{self.base_url}/measurement/start")
        return response.status_code == 200
    
    def stop_measurement(self):
        """Stop data acquisition"""
        response = requests.get(f"{self.base_url}/measurement/stop")
        return response.status_code == 200
    
    def get_status(self):
        """Get current system status"""
        response = requests.get(f"{self.base_url}/dashboard")
        return response.json() if response.status_code == 200 else None

# Example usage
def run_acquisition():
    client = ServalClient()
    
    # Connect to detector
    if not client.connect_detector():
        raise RuntimeError("Failed to connect to detector")
    
    # Load calibration files
    client.load_calibration("detector_config.bpc", "detector_dacs.dacs")
    
    # Configure detector settings
    detector_config = {
        "BiasVoltage": 100.0,
        "BiasEnabled": True,
        "TriggerPeriod": 0.1,
        "ExposureTime": 0.05,
        "nTriggers": 1000,
        "TriggerMode": "EXTERNAL"
    }
    client.configure_detector(detector_config)
    
    # Setup data output
    client.setup_destination("/data/experiments/run_001")
    
    # Start acquisition
    client.start_measurement()
    
    # Monitor progress
    import time
    while True:
        status = client.get_status()
        if status and status['measurement']['active']:
            print(f"Frame: {status['measurement']['frame_count']}")
            time.sleep(1)
        else:
            break
    
    print("Acquisition completed")

if __name__ == "__main__":
    run_acquisition()
```

### Live Image Monitoring

```python
import requests
import numpy as np
from PIL import Image
import io

def monitor_live_images(host="192.168.100.1", port=8080):
    """Monitor live preview images from SERVAL"""
    base_url = f"http://{host}:{port}"
    
    while True:
        try:
            # Get live image
            response = requests.get(f"{base_url}/measurement/image")
            if response.status_code == 200:
                # Convert binary data to image
                image_data = io.BytesIO(response.content)
                img = Image.open(image_data)
                
                # Process image (display, analyze, etc.)
                print(f"Received image: {img.size}")
                
                # Optional: save image
                img.save(f"preview_{int(time.time())}.png")
                
        except Exception as e:
            print(f"Error getting image: {e}")
            time.sleep(0.1)
```

---

## Troubleshooting

### Common Issues

#### Detector Not Detected

**Symptoms:**
- `/detector/list` returns empty array
- Connection attempts fail

**Solutions:**
1. Check physical Ethernet connection
2. Verify network configuration:
   ```bash
   ping 192.168.100.10
   ```
3. Check firewall settings:
   ```bash
   sudo ufw status
   ```
4. Verify detector power and LED status

#### Connection Drops Under Load

**Symptoms:**
- Acquisition stops unexpectedly
- Network timeouts during high-speed acquisition

**Solutions:**
1. Check MTU settings:
   ```bash
   ip link show | grep mtu
   ```
2. Verify jumbo frame support:
   ```bash
   ping -M do -s 8972 192.168.100.10
   ```
3. Monitor network interface errors:
   ```bash
   watch -n 1 'cat /proc/net/dev'
   ```

#### HTTP API Errors

**Common Error Responses:**

| Error | Cause | Solution |
|-------|-------|----------|
| 404 Not Found | Invalid endpoint | Check API documentation |
| 400 Bad Request | Invalid JSON or parameters | Validate request data |
| 409 Conflict | Detector busy/disconnected | Check detector status |
| 500 Internal Error | SERVAL internal error | Check SERVAL logs |

#### Performance Issues

**Symptoms:**
- Slow image acquisition
- High CPU usage
- Memory consumption

**Optimization:**
1. Adjust queue sizes in destination configuration
2. Use appropriate image formats (PGM vs TIFF)
3. Optimize preview refresh rates
4. Monitor disk I/O performance

### Diagnostic Commands

```bash
# Check SERVAL process
ps aux | grep serval

# Monitor network traffic
sudo netstat -tuln | grep :8080

# Check system resources
htop
iotop

# Test HTTP connectivity
curl -v http://192.168.100.1:8080/

# Monitor detector communication
sudo tcpdump -i enp4s0 port 50000
```

### Log Analysis

SERVAL logs contain valuable diagnostic information:

```bash
# Start SERVAL with verbose logging
java -jar serval-3.3.0.jar --verbose

# Monitor system logs
journalctl -f -u serval

# Check network interface logs
dmesg | grep enp4s0
```

---

## Additional Resources

### SERVAL Configuration Files

- **Pixel Configuration (`.bpc`)**: Binary per-pixel settings
- **DAC Configuration (`.dacs`)**: Analog bias and threshold settings  
- **SERVAL State (`.json`)**: Complete system configuration

### Network Performance Tuning

For high-speed acquisition, consider additional network optimizations:

```bash
# Increase network buffer sizes
echo 'net.core.rmem_max = 134217728' >> /etc/sysctl.conf
echo 'net.core.wmem_max = 134217728' >> /etc/sysctl.conf

# Apply changes
sysctl -p
```

### Integration with HERMES

This SERVAL API documentation directly supports the HERMES acquisition system's services layer implementation, providing the foundation for:

- Direct SERVAL HTTP client services
- Type-safe API request/response validation
- Complete detector control workflows
- Real-time data acquisition monitoring

---

**Version:** SERVAL 3.3.0  
**Last Updated:** October 2025  
**Compatibility:** Ubuntu 22.04 LTS, Java 11+