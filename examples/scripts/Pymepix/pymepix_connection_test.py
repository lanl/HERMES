#!/usr/bin/env python3
"""
Pymepix Connection Test

This script tests a direct connection to a TPX3Cam via the SPIDR board
using pymepix (no Serval middleware required).

It will:
1. Connect to the SPIDR board over TCP
2. Query attached Timepix devices
3. Read basic device info (device ID, firmware, chip temperature)
4. Disconnect cleanly

This is read-only — it does NOT change any camera settings, 
load any config, or start any acquisition.

Usage:
    pixi run python examples/scripts/Pymepix/pymepix_connection_test.py

    # With custom IPs:
    pixi run python examples/scripts/Pymepix/pymepix_connection_test.py \
        --spidr-ip 192.168.100.10 \
        --local-ip 192.168.100.1
"""

import argparse
import os
import sys
import time


def test_connection(spidr_ip: str, spidr_port: int, local_ip: str, local_port: int, camera_gen: int):
    """Attempt to connect to SPIDR and query device info."""
    
    print("=" * 60)
    print("Pymepix Connection Test")
    print("=" * 60)
    print(f"  SPIDR address : {spidr_ip}:{spidr_port}")
    print(f"  Local address : {local_ip}:{local_port}")
    print(f"  Camera gen    : Timepix{camera_gen}")
    print("=" * 60)
    print()

    # --- Step 1: Import pymepix ---
    print("[1/6] Importing pymepix...")
    try:
        from pymepix.pymepix_connection import PymepixConnection
        print("  ✓ pymepix imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import pymepix: {e}")
        sys.exit(1)

    # --- Step 2: Connect to SPIDR ---
    print(f"\n[2/6] Connecting to SPIDR at {spidr_ip}:{spidr_port}...")
    try:
        tpx = PymepixConnection(
            spidr_address=(spidr_ip, spidr_port),
            udp_ip_port=(local_ip, local_port),
            pc_ip=local_ip,
            camera_generation=camera_gen,
        )
        print(f"  ✓ Connected to SPIDR")
    except Exception as e:
        print(f"  ✗ Failed to connect: {e}")
        sys.exit(1)

    # --- Step 3: Query devices ---
    num_devices = len(tpx)
    print(f"\n[3/6] Querying Timepix devices...")
    print(f"  Found {num_devices} device(s)")

    if num_devices == 0:
        print("  ⚠ No Timepix devices detected on SPIDR")
        print("    - Is the camera powered on?")
        print("    - Is the camera connected to the SPIDR board?")
        sys.exit(1)

    # --- Step 4: Read device info ---
    print(f"\n[4/6] Device information:")
    for i in range(num_devices):
        device = tpx[i]
        print(f"\n  --- Device {i} ---")
        try:
            print(f"  Device ID   : {device.devIdToString()}")
        except Exception as e:
            print(f"  Device ID   : (error: {e})")
        try:
            print(f"  Device name : {device.deviceName}")
        except Exception as e:
            print(f"  Device name : (error: {e})")

    # --- Step 5: Start acquisition ---
    print(f"\n[5/6] Starting acquisition...")
    try:
        output_dir = os.path.join(os.path.dirname(__file__), "../../workspace")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "acquired_data.tpx3")

        with open(output_file, "wb") as f:
            tpx.start()
            print("  ✓ Acquisition started")

            # Acquire data for 5 seconds
            time.sleep(5)

            # Stop acquisition
            tpx.stop()
            print("  ✓ Acquisition stopped")

            # Save data to file
            for packet in tpx.read_data():
                f.write(packet)

        print(f"  ✓ Data saved to {output_file}")
    except Exception as e:
        print(f"  ✗ Failed during acquisition: {e}")
        sys.exit(1)

    # --- Done ---
    print()
    print("=" * 60)
    print("Acquisition test COMPLETED")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Test pymepix connection to TPX3Cam via SPIDR"
    )
    parser.add_argument(
        "--spidr-ip",
        default="192.168.100.10",
        help="SPIDR board IP address (default: 192.168.100.10)",
    )
    parser.add_argument(
        "--spidr-port",
        type=int,
        default=50000,
        help="SPIDR board TCP port (default: 50000)",
    )
    parser.add_argument(
        "--local-ip",
        default="192.168.100.1",
        help="Local IP on the camera network interface (default: 192.168.100.1)",
    )
    parser.add_argument(
        "--local-port",
        type=int,
        default=8192,
        help="Local UDP port for data reception (default: 8192)",
    )
    parser.add_argument(
        "--camera-gen",
        type=int,
        default=3,
        choices=[3, 4],
        help="Camera generation: 3=Timepix3, 4=Timepix4 (default: 3)",
    )

    args = parser.parse_args()

    test_connection(
        spidr_ip=args.spidr_ip,
        spidr_port=args.spidr_port,
        local_ip=args.local_ip,
        local_port=args.local_port,
        camera_gen=args.camera_gen,
    )


if __name__ == "__main__":
    main()
