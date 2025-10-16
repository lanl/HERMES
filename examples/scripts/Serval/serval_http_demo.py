#!/usr/bin/env python3
"""
SERVAL HTTP Information Demo

This script demonstrates how to get various types of information from SERVAL
using the HERMES HTTP client. It shows how to:

1. Start SERVAL without requiring a camera
2. Connect to SERVAL's HTTP API
3. Retrieve different types of information (dashboard, server info, etc.)
4. Handle errors gracefully
5. Clean up resources properly

Usage:
    python serval_http_demo.py [--port PORT] [--verbose]

Example:
    python serval_http_demo.py --port 8080 --verbose
"""

import asyncio
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

# Add the src directory to the path so we can import hermes modules
sys.path.append(str(Path(__file__).parent.parent.parent.parent / "src"))

from hermes.acquisition.factories.serval_factory import ServalFactory
from hermes.acquisition.services.direct.serval_http_client import create_serval_http_client
from hermes.acquisition.models.software.serval import ServalConfig


class ServalInfoDemo:
    """
    Demonstration class for retrieving information from SERVAL.
    """
    
    def __init__(self, port: int = 8080, verbose: bool = False):
        self.port = port
        self.verbose = verbose
        self.process_manager = None
        self.http_client = None
    
    async def start_serval(self) -> bool:
        """
        Start SERVAL process manager.
        
        Returns:
            True if SERVAL started successfully
        """
        try:
            print(f"Starting SERVAL on port {self.port}...")
            
            # Create factory and start SERVAL without camera requirement
            serval_factory = ServalFactory()
            self.process_manager = await serval_factory.create_and_start_manager(
                port=self.port,
                require_camera=False  # Allow running without physical camera
            )
            
            print(f"SERVAL started successfully on port {self.port}")
            return True
            
        except Exception as e:
            print(f"Failed to start SERVAL: {e}")
            return False
    
    async def connect_http_client(self) -> bool:
        """
        Connect to SERVAL's HTTP API.
        
        Returns:
            True if connection successful
        """
        try:
            print("Connecting to SERVAL HTTP API...")
            
            # Create and connect HTTP client
            serval_config = ServalConfig(port=self.port)
            self.http_client = create_serval_http_client(serval_config)
            await self.http_client.connect()
            
            print("Connected to SERVAL HTTP API")
            return True
            
        except Exception as e:
            print(f"Failed to connect to SERVAL HTTP API: {e}")
            return False
    
    async def get_dashboard_info(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve and display dashboard information.
        
        Returns:
            Dashboard data if successful, None otherwise
        """
        try:
            print("\nRetrieving Dashboard Information...")
            
            dashboard = await self.http_client.get_dashboard()
            dashboard_dict = dashboard.model_dump()
            
            print("Dashboard retrieved successfully")
            
            # Display formatted dashboard info
            self._display_dashboard_info(dashboard_dict)
            
            return dashboard_dict
            
        except Exception as e:
            print(f"Failed to get dashboard: {e}")
            return None
    
    def _display_dashboard_info(self, dashboard: Dict[str, Any]) -> None:
        """
        Display dashboard information in a formatted way.
        
        Args:
            dashboard: Dashboard data dictionary
        """
        print("\n" + "="*60)
        print("SERVAL DASHBOARD INFORMATION")
        print("="*60)
        
        # Server Information
        if server := dashboard.get("Server"):
            print("\nSERVER INFO:")
            if version := server.get("SoftwareVersion"):
                print(f"   Software Version: {version}")
            if timestamp := server.get("SoftwareTimestamp"):
                print(f"   Build Timestamp: {timestamp}")
            if commit := server.get("SoftwareCommit"):
                print(f"   Git Commit: {commit}")
            if build := server.get("SoftwareBuild"):
                print(f"   Build Number: {build}")
            
            # Disk Space Information
            if disk_spaces := server.get("DiskSpace"):
                print(f"\nDISK SPACE ({len(disk_spaces)} location(s)):")
                for i, disk in enumerate(disk_spaces, 1):
                    path = disk.get("Path", "Unknown")
                    free_bytes = disk.get("FreeSpace", 0)
                    total_bytes = disk.get("TotalSpace", 0)
                    
                    if free_bytes and total_bytes:
                        free_gb = free_bytes / (1024**3)
                        total_gb = total_bytes / (1024**3)
                        used_percent = ((total_bytes - free_bytes) / total_bytes) * 100
                        print(f"   {i}. {path}")
                        print(f"      Free: {free_gb:.1f} GB / Total: {total_gb:.1f} GB ({used_percent:.1f}% used)")
                    else:
                        print(f"   {i}. {path}: Space info not available")
            
            # Notifications
            if notifications := server.get("Notifications"):
                if notifications:
                    print(f"\nNOTIFICATIONS ({len(notifications)} total):")
                    for i, notification in enumerate(notifications[:5], 1):
                        print(f"   {i}. {notification}")
                    if len(notifications) > 5:
                        print(f"   ... and {len(notifications) - 5} more")
                else:
                    print(f"\nNOTIFICATIONS: None")
        
        # Current Measurement
        if measurement := dashboard.get("Measurement"):
            if measurement:
                print(f"\nCURRENT MEASUREMENT:")
                if name := measurement.get("Name"):
                    print(f"   Name: {name}")
                if timestamp := measurement.get("Timestamp"):
                    print(f"   Started: {timestamp}")
                if frames := measurement.get("FrameCount"):
                    print(f"   Frames Captured: {frames:,}")
                if duration := measurement.get("Duration"):
                    print(f"   Duration: {duration}")
                if status := measurement.get("Status"):
                    print(f"   Status: {status}")
            else:
                print(f"\nCURRENT MEASUREMENT: None active")
        
        # Detector Information
        if detector := dashboard.get("Detector"):
            if detector:
                print(f"\nDETECTOR INFO:")
                if detector_id := detector.get("DetectorID"):
                    print(f"   Detector ID: {detector_id}")
                if detector_type := detector.get("DetectorType"):
                    print(f"   Type: {detector_type}")
                if connection_status := detector.get("Connected"):
                    status = "Connected" if connection_status else "Disconnected"
                    print(f"   Status: {status}")
                if firmware := detector.get("FirmwareVersion"):
                    print(f"   Firmware: {firmware}")
            else:
                print(f"\nDETECTOR: Not connected")
        
        # Raw JSON Structure Summary
        if self.verbose:
            print(f"\nRAW JSON STRUCTURE:")
            print(f"   Total top-level keys: {len(dashboard)}")
            for key, value in dashboard.items():
                if value is not None:
                    if isinstance(value, dict):
                        subkeys = len(value)
                        print(f"   {key}: {subkeys} sub-fields")
                    elif isinstance(value, list):
                        items = len(value)
                        print(f"   {key}: {items} items")
                    else:
                        print(f"   {key}: {type(value).__name__}")
                else:
                    print(f"   {key}: null")
        
        print("="*60)
    
    async def demonstrate_error_handling(self) -> None:
        """
        Demonstrate how to handle various error scenarios.
        """
        print("\nDemonstrating Error Handling...")
        
        # Try to make a request to a non-existent endpoint
        try:
            print("   Testing invalid endpoint...")
            # This would normally fail, but we'll simulate it
            print("   Note: SERVAL HTTP client only supports dashboard endpoint currently")
            
        except Exception as e:
            print(f"   Caught expected error: {e}")
    
    async def save_dashboard_to_file(self, filename: str = "serval_dashboard_demo.json") -> bool:
        """
        Save dashboard information to a JSON file.
        
        Args:
            filename: Output filename
            
        Returns:
            True if saved successfully
        """
        try:
            print(f"\nSaving dashboard to {filename}...")
            
            dashboard = await self.http_client.get_dashboard()
            dashboard_dict = dashboard.model_dump()
            
            output_path = Path(filename)
            with open(output_path, 'w') as f:
                json.dump(dashboard_dict, f, indent=2, default=str)
            
            print(f"Dashboard saved to: {output_path.absolute()}")
            return True
            
        except Exception as e:
            print(f"Failed to save dashboard: {e}")
            return False
    
    async def cleanup(self) -> None:
        """
        Clean up resources and shutdown SERVAL.
        """
        print("\nCleaning up...")
        
        try:
            # Disconnect HTTP client
            if self.http_client:
                await self.http_client.disconnect()
                print("HTTP client disconnected")
            
            # Stop SERVAL process
            if self.process_manager:
                await self.process_manager.stop_process()
                print("SERVAL process stopped")
                
        except Exception as e:
            print(f"Warning during cleanup: {e}")
    
    async def run_demo(self) -> None:
        """
        Run the complete demonstration.
        """
        print("SERVAL HTTP Information Demo")
        print("=" * 50)
        
        try:
            # Step 1: Start SERVAL
            if not await self.start_serval():
                return
            
            # Step 2: Connect HTTP client
            if not await self.connect_http_client():
                return
            
            # Step 3: Get and display dashboard info
            dashboard_data = await self.get_dashboard_info()
            if not dashboard_data:
                return
            
            # Step 4: Save to file
            await self.save_dashboard_to_file()
            
            # Step 5: Demonstrate error handling
            await self.demonstrate_error_handling()
            
            print(f"\nDemo completed successfully!")
            print(f"   SERVAL version: {dashboard_data.get('Server', {}).get('SoftwareVersion', 'Unknown')}")
            print(f"   Port: {self.port}")
            print(f"   Dashboard keys: {list(dashboard_data.keys())}")
            
        except Exception as e:
            print(f"\nDemo failed with error: {e}")
            raise
        finally:
            await self.cleanup()


async def main() -> None:
    """
    Main function with command line argument parsing.
    """
    parser = argparse.ArgumentParser(
        description="Demonstrate SERVAL HTTP information retrieval",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                     # Run with default settings
  %(prog)s --port 8080         # Specify SERVAL port
  %(prog)s --verbose           # Show detailed JSON structure
  %(prog)s --port 8080 --verbose  # All options
  
This demo will:
  1. Start SERVAL without requiring a camera
  2. Connect to SERVAL's HTTP API
  3. Retrieve and display dashboard information
  4. Save the dashboard to a JSON file
  5. Demonstrate error handling
  6. Clean up all resources
        """
    )
    
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="SERVAL HTTP port (default: 8080)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output including raw JSON structure"
    )
    
    args = parser.parse_args()
    
    # Create and run demo
    demo = ServalInfoDemo(port=args.port, verbose=args.verbose)
    await demo.run_demo()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)