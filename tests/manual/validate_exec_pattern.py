#!/usr/bin/env python3
"""Manual validation script for exec() pattern (Phase 2.2).

This script validates exec() and copy_to() methods with real podman containers.
Run this manually to verify the exec pattern works correctly.

Usage:
    python tests/manual/validate_exec_pattern.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from koji_adjutant.container.interface import ContainerHandle, ContainerSpec, InMemoryLogSink
from koji_adjutant.container.podman_manager import PodmanManager

# Test image (should be available)
TEST_IMAGE = "docker.io/almalinux/9-minimal:latest"


def test_exec_basic():
    """Test basic exec() command execution."""
    print("=" * 60)
    print("Test 1: Basic exec() command")
    print("=" * 60)
    
    manager = PodmanManager()
    sink = InMemoryLogSink()
    
    try:
        # Ensure image is available
        print(f"Ensuring image {TEST_IMAGE} is available...")
        manager.ensure_image_available(TEST_IMAGE)
        print("✓ Image available")
        
        # Create container with sleep
        spec = ContainerSpec(
            image=TEST_IMAGE,
            command=["/bin/sleep", "infinity"],
            environment={},
            remove_after_exit=True,
        )
        
        print("Creating container...")
        handle = manager.create(spec)
        print(f"✓ Container created: {handle.container_id[:12]}")
        
        print("Starting container...")
        manager.start(handle)
        print("✓ Container started")
        
        try:
            # Execute a simple command
            print("Executing: /bin/echo hello world")
            exit_code = manager.exec(handle, ["/bin/echo", "hello", "world"], sink)
            
            print(f"Exit code: {exit_code}")
            output = sink.stdout.decode("utf-8", errors="replace")
            print(f"Output: {repr(output)}")
            
            if exit_code == 0 and ("hello world" in output or "hello" in output):
                print("✓ Test PASSED")
                return True
            else:
                print("✗ Test FAILED")
                return False
                
        finally:
            print("Cleaning up container...")
            manager.remove(handle, force=True)
            print("✓ Container removed")
            
    except Exception as e:
        print(f"✗ Test FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_copy_to():
    """Test copy_to() file copy."""
    print("\n" + "=" * 60)
    print("Test 2: copy_to() file copy")
    print("=" * 60)
    
    manager = PodmanManager()
    sink = InMemoryLogSink()
    
    # Create temporary test file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        test_content = "test content from host\n"
        f.write(test_content)
        test_file = Path(f.name)
    
    try:
        # Ensure image is available
        print(f"Ensuring image {TEST_IMAGE} is available...")
        manager.ensure_image_available(TEST_IMAGE)
        print("✓ Image available")
        
        # Create container with sleep
        spec = ContainerSpec(
            image=TEST_IMAGE,
            command=["/bin/sleep", "infinity"],
            environment={},
            remove_after_exit=True,
        )
        
        print("Creating container...")
        handle = manager.create(spec)
        print(f"✓ Container created: {handle.container_id[:12]}")
        
        print("Starting container...")
        manager.start(handle)
        print("✓ Container started")
        
        try:
            # Copy file to container
            print(f"Copying {test_file} to /tmp/test.txt...")
            manager.copy_to(handle, test_file, "/tmp/test.txt")
            print("✓ File copied")
            
            # Verify file exists by executing cat
            print("Verifying file content...")
            sink.stdout = b""  # Clear previous output
            exit_code = manager.exec(handle, ["/bin/cat", "/tmp/test.txt"], sink)
            
            print(f"Exit code: {exit_code}")
            output = sink.stdout.decode("utf-8", errors="replace")
            print(f"Output: {repr(output)}")
            
            if exit_code == 0 and test_content.strip() in output:
                print("✓ Test PASSED")
                return True
            else:
                print("✗ Test FAILED")
                return False
                
        finally:
            print("Cleaning up container...")
            manager.remove(handle, force=True)
            print("✓ Container removed")
            
    except Exception as e:
        print(f"✗ Test FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up temp file
        try:
            test_file.unlink()
        except Exception:
            pass


def test_exec_with_env():
    """Test exec() with environment variables."""
    print("\n" + "=" * 60)
    print("Test 3: exec() with environment variables")
    print("=" * 60)
    
    manager = PodmanManager()
    sink = InMemoryLogSink()
    
    try:
        # Ensure image is available
        print(f"Ensuring image {TEST_IMAGE} is available...")
        manager.ensure_image_available(TEST_IMAGE)
        print("✓ Image available")
        
        # Create container with sleep
        spec = ContainerSpec(
            image=TEST_IMAGE,
            command=["/bin/sleep", "infinity"],
            environment={"ORIGINAL_VAR": "original_value"},
            remove_after_exit=True,
        )
        
        print("Creating container...")
        handle = manager.create(spec)
        print(f"✓ Container created: {handle.container_id[:12]}")
        
        print("Starting container...")
        manager.start(handle)
        print("✓ Container started")
        
        try:
            # Execute command with custom environment
            print("Executing: /bin/sh -c 'echo $TEST_VAR' with TEST_VAR=modified_value")
            sink.stdout = b""  # Clear previous output
            exit_code = manager.exec(
                handle,
                ["/bin/sh", "-c", "echo $TEST_VAR"],
                sink,
                environment={"TEST_VAR": "modified_value"},
            )
            
            print(f"Exit code: {exit_code}")
            output = sink.stdout.decode("utf-8", errors="replace")
            print(f"Output: {repr(output)}")
            
            if exit_code == 0 and "modified_value" in output:
                print("✓ Test PASSED")
                return True
            else:
                print("✗ Test FAILED")
                return False
                
        finally:
            print("Cleaning up container...")
            manager.remove(handle, force=True)
            print("✓ Container removed")
            
    except Exception as e:
        print(f"✗ Test FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all validation tests."""
    print("Exec Pattern Validation (Phase 2.2)")
    print("=" * 60)
    print()
    
    results = []
    
    # Run tests
    results.append(("Basic exec()", test_exec_basic()))
    results.append(("copy_to()", test_copy_to()))
    results.append(("exec() with env", test_exec_with_env()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All tests PASSED")
        return 0
    else:
        print("✗ Some tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
