# SERVAL Examples

This directory contains examples for working with SERVAL using the HERMES acquisition system.

## Files

### `initial_serval_check.py`
A complete, production-ready example that demonstrates:
- Automatic SERVAL discovery and startup
- Camera connection timeout handling
- Health checking and status monitoring
- Graceful shutdown

This is the **recommended starting point** for new users.

### `example_config.ini` *(existing)*
Configuration file example for SERVAL settings.

## Quick Start

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

## Key Features

### 🔍 **Automatic Discovery**
- Searches common installation locations (`/opt/serval/`, `~/Programs/TPX3Cam/Serval/`, etc.)
- Supports user-provided paths
- Validates SERVAL installations and Java requirements

### ⏱️ **Camera Connection Timeout**
- Automatically shuts down SERVAL if camera doesn't connect within timeout (default: 30s)
- Prevents endless retry loops when no camera is connected
- Configurable timeout duration

### 🏥 **Health Monitoring**
- API responsiveness checks
- Camera connection status monitoring
- Response time measurement

### 🛡️ **Error Handling**
- Graceful error handling and reporting
- Automatic cleanup on failures
- Clear status messages and recommendations

## Architecture Integration

This example uses the layered HERMES architecture:

- **Models Layer**: `ServalConfig` for type-safe configuration
- **Services Layer**: `ServalProcessManager` for process lifecycle
- **Factories Layer**: `ServalFactory` for instantiation and validation

## Requirements

- Python 3.8+
- Java Runtime Environment (for running SERVAL)
- SERVAL installation (auto-discovered or user-provided path)

## Expected Output

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

The example uses default Serval 2.1.6 settings but you can modify the configuration in the script or use the provided `example_config.ini` file as a template.

### Key Configuration Options

- **httpPort**: Port for Serval HTTP interface (default: 8080)
- **spidrNet**: IP address for SPIDR network (default: 192.168.100.10)
- **httpLog**: Path for HTTP access log (default: /tmp/serval_example.log)

## Troubleshooting

1. **"Java not found"** - Install Java Runtime Environment
2. **"serv-2.1.6.jar not found"** - Ensure the JAR file is in the correct path
3. **"Port already in use"** - Change the httpPort in configuration or stop other services using port 8080
4. **Import errors** - Make sure you're running from the correct directory and the HERMES package is installed

## Next Steps

After running this basic example, you can:

1. Modify the configuration to match your hardware setup
2. Integrate Serval startup/shutdown into your data acquisition workflows
3. Use the ServalManager class directly for more advanced control
4. Add error handling and monitoring specific to your use case
