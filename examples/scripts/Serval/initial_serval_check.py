#!/usr/bin/env python3
"""
Simple SERVAL Startup and Health Check Example

This script demonstrates how to:
1. Discover and start SERVAL with automatic camera timeout
2. Check SERVAL health and camera connection status
3. Properly shutdown SERVAL

This is a minimal example for production use.
"""

import asyncio
import argparse
from pathlib import Path
import sys

# Add the hermes package to the path (adjust path as needed)
hermes_root = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(hermes_root))

from hermes.acquisition.factories.serval_factory import ServalFactory


async def start_and_check_serval(
    serval_path: str = None,
    camera_timeout: float = 30.0,
    require_camera: bool = True,
    port: int = 8080
):
    """
    Start SERVAL and perform health checks.
    
    Args:
        serval_path: Path to SERVAL installation (auto-discovered if None)
        camera_timeout: Time to wait for camera connection (seconds)
        require_camera: Whether to require camera connection
        port: SERVAL HTTP port
        
    Returns:
        True if SERVAL started successfully, False otherwise
    """
    print("  Starting SERVAL...")
    print(f"   Camera timeout: {camera_timeout}s")
    print(f"   Camera required: {'Yes' if require_camera else 'No'}")
    print(f"   Port: {port}")
    
    try:
        # Quick start with camera timeout
        manager = await ServalFactory.quick_start(
            host="localhost",
            port=port,
            path_to_serval=serval_path,
            require_camera=require_camera,
            camera_timeout=camera_timeout
        )
        
        print("SERVAL started successfully!")
        
        # Perform health check
        print("\nChecking SERVAL health...")
        health = await manager.health_check()
        
        print(f"   Status: {'Healthy' if health.is_healthy else 'Unhealthy'}")
        print(f"   API URL: {manager.get_api_base_url()}")
        print(f"   Response Time: {health.response_time_ms:.1f}ms" if health.response_time_ms else "N/A")
        
        # Check camera connection
        print(f"   Camera Connected: {'Yes' if manager.camera_connected else 'No'}")
        
        if manager.shutdown_due_to_camera_timeout:
            print("WARNING: SERVAL was shut down due to camera timeout")
            return False
        
        # Show some additional info if available
        if health.additional_info:
            print(f"   Additional Info: {health.additional_info}")
        
        return manager
        
    except Exception as e:
        print(f"ERROR: Failed to start SERVAL: {e}")
        return False


async def stop_serval(manager):
    """Stop SERVAL gracefully."""
    if manager:
        print("\nStopping SERVAL...")
        try:
            await manager.disconnect()
            print("SERVAL stopped successfully")
        except Exception as e:
            print(f"WARNING: Error stopping SERVAL: {e}")


async def main():
    """Main function with command line arguments."""
    parser = argparse.ArgumentParser(
        description='Simple SERVAL startup and health check example',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start SERVAL with auto-discovery and 30s camera timeout
  python initial_serval_check.py
  
  # Start with specific SERVAL path
  python initial_serval_check.py --serval-path /path/to/serval
  
  # Start without requiring camera connection
  python initial_serval_check.py --no-camera
  
  # Start with custom timeout and port
  python initial_serval_check.py --timeout 60 --port 8081
        """
    )
    
    parser.add_argument(
        '--serval-path', 
        help='Path to SERVAL installation (auto-discovered if not provided)'
    )
    parser.add_argument(
        '--timeout', 
        type=float, 
        default=30.0,
        help='Camera connection timeout in seconds (default: 30)'
    )
    parser.add_argument(
        '--no-camera', 
        action='store_true',
        help='Do not require camera connection'
    )
    parser.add_argument(
        '--port', 
        type=int, 
        default=8080,
        help='SERVAL HTTP port (default: 8080)'
    )
    parser.add_argument(
        '--check-only', 
        action='store_true',
        help='Only check if SERVAL can be discovered, do not start'
    )
    
    args = parser.parse_args()
    
    print("HERMES SERVAL Example")
    print("=" * 40)
    
    if args.check_only:
        # Only perform discovery check
        print("Checking SERVAL discovery...")
        factory = ServalFactory()
        validation = await factory.validate_prerequisites()
        
        print(f"Java available: {'YES' if validation['java_available'] else 'NO'}")
        print(f"SERVAL installations: {len(validation['serval_installations'])}")
        
        if validation['serval_installations']:
            for i, inst in enumerate(validation['serval_installations'], 1):
                print(f"  {i}. {inst['path']} (version: {inst.get('version', 'unknown')})")
        
        if validation['validation_errors']:
            print("\nIssues found:")
            for error in validation['validation_errors']:
                print(f"  - {error}")
        
        if validation['recommendations']:
            print("\nRecommendations:")
            for rec in validation['recommendations']:
                print(f"  - {rec}")
        
        return
    
    # Start SERVAL
    manager = await start_and_check_serval(
        serval_path=args.serval_path,
        camera_timeout=args.timeout,
        require_camera=not args.no_camera,
        port=args.port
    )
    
    if not manager:
        print("\nERROR: SERVAL startup failed")
        return
    
    # Keep SERVAL running for a moment
    print(f"\nSERVAL is running. Waiting 10 seconds...")
    print("   (In a real application, you would perform your acquisition tasks here)")
    
    try:
        await asyncio.sleep(10)
        
        # Optional: Perform another health check
        print("\nFinal health check...")
        health = await manager.health_check()
        print(f"   Final status: {'Healthy' if health.is_healthy else 'Unhealthy'}")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    # Cleanup
    await stop_serval(manager)
    
    print("\nExample completed successfully!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nERROR: Unexpected error: {e}")
        sys.exit(1)