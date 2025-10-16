# SERVAL Examples

This directory contains examples for working with SERVAL using the HERMES acquisition system.

## Overview

The examples demonstrate different aspects of SERVAL integration:
- **Process lifecycle management** (startup, monitoring, shutdown)
- **HTTP API integration** (dashboard retrieval, data export)
- **Error handling and resource cleanup**
- **Production-ready patterns and best practices**

---

## Example 1: `initial_serval_check.py`

### Purpose
A complete, production-ready example that demonstrates SERVAL process lifecycle management with automatic discovery, camera timeout handling, and health monitoring. This is the **recommended starting point** for new users.

### Basic Usage
```bash
# Start SERVAL with auto-discovery and default settings
python initial_serval_check.py

# Check if SERVAL can be discovered without starting
python initial_serval_check.py --check-only
```

### Advanced Usage
```bash
# Start with specific SERVAL path
python initial_serval_check.py --serval-path /path/to/serval

# Start without requiring camera connection
python initial_serval_check.py --no-camera

# Start with custom timeout and port
python initial_serval_check.py --timeout 60 --port 8081
```

### Key Features
- **Automatic Discovery**: Searches common installation locations and validates SERVAL installations
- **Camera Connection Timeout**: Automatically shuts down SERVAL if camera doesn't connect within timeout (default: 30s)
- **Health Monitoring**: API responsiveness checks, camera connection status monitoring, response time measurement
- **Error Handling**: Graceful error handling and reporting with automatic cleanup on failures

### What You Learn
- How to implement SERVAL discovery and validation
- Process lifecycle management patterns
- Camera timeout handling for production environments
- Health checking and monitoring techniques
- Resource cleanup and graceful shutdown

---

## Example 2: `serval_http_demo.py`

### Purpose
A comprehensive demonstration of SERVAL HTTP API integration that showcases dashboard data retrieval, JSON export, and complete workflow management. This example is **ideal for understanding HTTP API capabilities** and data retrieval patterns.

### Basic Usage
```bash
# Run HTTP API demo with dashboard information
python serval_http_demo.py

# Run HTTP demo with verbose JSON structure output
python serval_http_demo.py --verbose
```

### Advanced Usage
```bash
# HTTP demo with custom port and verbose output
python serval_http_demo.py --port 8081 --verbose

# Save dashboard to custom filename
# (modify script to change default filename)
```

### Key Features
- **Complete Lifecycle Management**: Startup → connection → data retrieval → shutdown
- **Dashboard Information Retrieval**: Server info, detector status, measurement data, disk space, notifications
- **JSON Data Export**: Save dashboard data to files for persistence and analysis
- **Formatted Output**: Human-readable display with detailed server, detector, and measurement information
- **Resource Cleanup**: Proper session management and graceful shutdown

### What You Learn
- HTTP API integration patterns with SERVAL
- Dashboard data parsing and presentation
- JSON export and data persistence techniques
- Session management and resource cleanup
- Error handling for HTTP operations
- Structured data display and formatting

---

## Supporting Files

### `example_config.ini` *(existing)*
Configuration file example for SERVAL settings.

---

## Architecture Integration

These examples use the layered HERMES architecture:

- **Models Layer**: `ServalConfig` for type-safe configuration
- **Services Layer**: `ServalProcessManager` for process lifecycle
- **Factories Layer**: `ServalFactory` for instantiation and validation

## Requirements

- Python 3.8+
- Java Runtime Environment (for running SERVAL)
- SERVAL installation (auto-discovered or user-provided path)

## Expected Output Examples

### `initial_serval_check.py` Output
```
🔬 HERMES SERVAL Example
========================================
🚀 Starting SERVAL...
   Camera timeout: 30.0s
   Camera required: Yes
   Port: 8080
✅ SERVAL started successfully!

🔍 Checking SERVAL health...
   Status: ✅ Healthy
   API URL: http://localhost:8080
   Response Time: 25.3ms
   Camera Connected: ❌ No

⏳ SERVAL is running. Waiting 10 seconds...
   (In a real application, you would perform your acquisition tasks here)

🔄 Final health check...
   Final status: ✅ Healthy

🛑 Stopping SERVAL...
✅ SERVAL stopped successfully

✨ Example completed successfully!
```

### `serval_http_demo.py` Output
```
SERVAL HTTP Information Demo
==================================================
Starting SERVAL on port 8080...
SERVAL started successfully on port 8080
Connecting to SERVAL HTTP API...
Connected to SERVAL HTTP API

Retrieving Dashboard Information...
Dashboard retrieved successfully

============================================================
SERVAL DASHBOARD INFORMATION
============================================================

SERVER INFO:
   Software Version: 2.1.6
   Build Timestamp: 2021/05/21 07:55

DISK SPACE (4 location(s)):
   1. /
      Free: 245.2 GB / Total: 494.4 GB (50.4% used)
   2. /System/Volumes/Data
      Free: 245.2 GB / Total: 494.4 GB (50.4% used)

CURRENT MEASUREMENT: None active
DETECTOR: Not connected
============================================================

Saving dashboard to serval_dashboard_demo.json...
Dashboard saved to: /Users/alexlong/Programs/HERMES/serval_dashboard_demo.json

Demo completed successfully!
   SERVAL version: 2.1.6
   Port: 8080
   Dashboard keys: ['Server', 'Measurement', 'Detector']

Cleaning up...
HTTP client disconnected
SERVAL process stopped
```

## Troubleshooting

### Common Issues

1. **"No valid SERVAL installations found"**
   - Install SERVAL in `/opt/serval/` or use `--serval-path`
   - Check that JAR files exist in the SERVAL directory

2. **"Java not found or not working"**
   - Install Java JRE/JDK
   - Ensure `java` command is in your PATH

3. **"Camera connection timeout"**
   - This is expected behavior when no camera is connected
   - Use `--no-camera` flag if you don't need camera connection

4. **"Port already in use"**
   - Another SERVAL instance may be running
   - Use `--port` to specify a different port
   - Check for existing processes: `lsof -i :8080`

### Getting Help

- Use `--help` flag for command line options
- Check the HERMES documentation for detailed architecture information
- Review the factory and service layer code for advanced customization

## Configuration

The examples use default SERVAL 2.1.6 settings but you can modify the configuration in the scripts or use the provided `example_config.ini` file as a template.

### Key Configuration Options

- **httpPort**: Port for SERVAL HTTP interface (default: 8080)
- **spidrNet**: IP address for SPIDR network (default: 192.168.100.10)
- **httpLog**: Path for HTTP access log (default: /tmp/serval_example.log)

## Next Steps

After running these examples, you can:

1. **Modify configurations** to match your hardware setup
2. **Integrate lifecycle management** into your data acquisition workflows
3. **Use the factory classes directly** for more advanced control
4. **Add custom error handling** and monitoring specific to your use case
5. **Extend the HTTP client** to support additional SERVAL endpoints
6. **Combine both patterns** for comprehensive SERVAL integration