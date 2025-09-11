# Serval Example Scripts

This directory contains example scripts demonstrating how to use the HERMES Serval integration.

## Files

- `serval_example.py` - Main example script showing Serval lifecycle
- `example_config.ini` - Example configuration file
- `README.md` - This file

## Usage

### Basic Example

Run the basic example that starts Serval, waits 5 seconds, then stops it:

```bash
cd /Users/alexlong/Programs/HERMES/examples/scripts/Serval/
python serval_example.py
```

### Prerequisites

1. **Java Runtime Environment** - Serval 2.1.6 requires Java to run
2. **Serval JAR file** - You need the `serv-2.1.6.jar` file in the serval directory
3. **Python dependencies** - Ensure you have the required Python packages installed

### Expected Output

When you run the example, you should see output similar to:

```
2025-08-17 13:30:00,123 - __main__ - INFO - === Serval Example Script Starting ===
2025-08-17 13:30:00,124 - __main__ - INFO - Creating Serval configuration...
2025-08-17 13:30:00,125 - __main__ - INFO - Initializing TPX3 Serval interface...
2025-08-17 13:30:00,126 - __main__ - INFO - Starting Serval application...
2025-08-17 13:30:01,200 - __main__ - INFO - ✅ Serval started successfully!
2025-08-17 13:30:01,201 - __main__ - INFO - Serval status: True
2025-08-17 13:30:01,201 - __main__ - INFO - Waiting for 5 seconds...
2025-08-17 13:30:01,201 - __main__ - INFO -   5 seconds remaining...
2025-08-17 13:30:02,202 - __main__ - INFO -   4 seconds remaining...
2025-08-17 13:30:03,203 - __main__ - INFO -   3 seconds remaining...
2025-08-17 13:30:04,204 - __main__ - INFO -   2 seconds remaining...
2025-08-17 13:30:05,205 - __main__ - INFO -   1 seconds remaining...
2025-08-17 13:30:06,206 - __main__ - INFO - Wait complete!
2025-08-17 13:30:06,206 - __main__ - INFO - Stopping Serval application...
2025-08-17 13:30:06,300 - __main__ - INFO - ✅ Serval stopped successfully!
2025-08-17 13:30:06,300 - __main__ - INFO - === Serval Example Script Complete ===
```

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
