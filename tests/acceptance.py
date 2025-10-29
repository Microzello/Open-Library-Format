"""Acceptance tests for Portable Library Manager MVP."""
import requests
import time
import os
from pathlib import Path
import io


BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8080")
session = requests.Session()
csrf_token = None


def print_step(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def test_health():
    """Test health endpoint."""
    print_step("Test 1: Health check")
    
    resp = session.get(f"{BASE_URL}/api/health")
    assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
    
    data = resp.json()
    assert data["status"] == "ok", "Health status not ok"
    print(f"✓ Health check passed: {data}")


def test_create_libraries():
    """Test creating three libraries (photos, docs, music)."""
    print_step("Test 2: Create libraries")
    
    global csrf_token
    
    libraries = [
        {"name": "Test Photos", "type": "photo_video", "tz": "UTC"},
        {"name": "Test Documents", "type": "documents", "tz": "UTC"},
        {"name": "Test Music", "type": "music", "tz": "UTC"},
    ]
    
    created = []
    for lib in libraries:
        resp = session.post(
            f"{BASE_URL}/api/libraries",
            json=lib,
            headers={"X-CSRF-Token": csrf_token},
        )
        assert resp.status_code == 201, f"Failed to create {lib['name']}: {resp.text}"
        
        data = resp.json()
        created.append(data)
        print(f"✓ Created library: {data['name']} ({data['id']})")
    
    return created


def test_upload_photos(library_id):
    """Test uploading photos."""
    print_step("Test 3: Upload photos")
    
    # Create a dummy image file (1x1 pixel PNG)
    png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    
    uploaded = []
    for i in range(3):
        files = {"file": (f"test_{i}.png", io.BytesIO(png_data), "image/png")}
        
        resp = session.post(
            f"{BASE_URL}/api/libraries/{library_id}/files",
            files=files,
            headers={"X-CSRF-Token": csrf_token},
        )
        assert resp.status_code == 201, f"Failed to upload photo {i}: {resp.text}"
        
        data = resp.json()
        uploaded.append(data)
        print(f"✓ Uploaded photo {i}: {data['status']} (file_id={data['file_id']})")
    
    return uploaded


def test_duplicate_upload(library_id, sha256):
    """Test uploading duplicate (should return exists)."""
    print_step("Test 4: Duplicate upload")
    
    png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    
    files = {"file": ("duplicate.png", io.BytesIO(png_data), "image/png")}
    resp = session.post(
        f"{BASE_URL}/api/libraries/{library_id}/files",
        files=files,
        headers={"X-CSRF-Token": csrf_token},
    )
    
    assert resp.status_code == 201, f"Duplicate upload failed: {resp.text}"
    data = resp.json()
    
    assert data["status"] == "exists", f"Expected 'exists', got '{data['status']}'"
    assert data["sha256"] == sha256, "SHA256 mismatch"
    print(f"✓ Duplicate detected correctly: {data}")


def test_tags(library_id, file_id):
    """Test creating tags and adding to files."""
    print_step("Test 5: Tags")
    
    # Create tags
    for tag_name in ["Favorites", "Vacation"]:
        resp = session.post(
            f"{BASE_URL}/api/libraries/{library_id}/tags",
            json={"name": tag_name},
            headers={"X-CSRF-Token": csrf_token},
        )
        # 201 if created, 409 if exists (Favorites is created by default)
        assert resp.status_code in (201, 409), f"Failed to create tag {tag_name}: {resp.text}"
        print(f"✓ Tag '{tag_name}' ready")
    
    # Get tags
    resp = session.get(f"{BASE_URL}/api/libraries/{library_id}/tags")
    assert resp.status_code == 200
    tags = resp.json()
    assert len(tags) >= 2, "Should have at least 2 tags"
    
    vacation_tag = next((t for t in tags if t["name"] == "Vacation"), None)
    assert vacation_tag is not None, "Vacation tag not found"
    
    # Add tag to file
    resp = session.post(
        f"{BASE_URL}/api/libraries/{library_id}/files/{file_id}/tags",
        json={"tag_id": vacation_tag["id"]},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 204, f"Failed to add tag: {resp.text}"
    print(f"✓ Added tag to file")
    
    # Query files by tag
    resp = session.get(f"{BASE_URL}/api/libraries/{library_id}/files?tag=Vacation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1, "Should have at least 1 file with Vacation tag"
    print(f"✓ Tag query returned {data['total']} files")


def test_trash_and_restore(library_id, file_id):
    """Test deleting to trash and restoring."""
    print_step("Test 6: Trash & Restore")
    
    # Delete file
    resp = session.delete(
        f"{BASE_URL}/api/libraries/{library_id}/files/{file_id}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 204, f"Failed to delete file: {resp.text}"
    print(f"✓ File deleted (moved to trash)")
    
    # Verify it's in trash
    resp = session.get(f"{BASE_URL}/api/libraries/{library_id}/files/{file_id}")
    assert resp.status_code == 200
    file_data = resp.json()
    assert file_data["deleted_at"] is not None, "File should have deleted_at set"
    print(f"✓ File marked as deleted")
    
    # Restore
    resp = session.post(
        f"{BASE_URL}/api/libraries/{library_id}/files/{file_id}/restore",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code == 204, f"Failed to restore file: {resp.text}"
    print(f"✓ File restored")
    
    # Verify it's back
    resp = session.get(f"{BASE_URL}/api/libraries/{library_id}/files/{file_id}")
    assert resp.status_code == 200
    file_data = resp.json()
    assert file_data["deleted_at"] is None, "File should not have deleted_at"
    print(f"✓ File back in main library")


def run_tests():
    """Run all acceptance tests."""
    global csrf_token
    
    print(f"\n{'#'*60}")
    print(f"  PORTABLE LIBRARY MANAGER - ACCEPTANCE TESTS")
    print(f"  Base URL: {BASE_URL}")
    print(f"{'#'*60}")
    
    # Assume bootstrap is already complete and we're logged in
    # For a real test, you'd need to handle login first
    
    # Try to login (or skip if already in session)
    try:
        resp = session.get(f"{BASE_URL}/api/me")
        if resp.status_code == 401:
            print("\n⚠ Not authenticated. Please login first.")
            print("Run: docker-compose up -d, visit http://localhost:8080, complete setup, then run tests.")
            return
        
        # Get CSRF token from login response or from a login call
        # For this MVP test, we'll try to extract it from a test login
        resp = session.post(
            f"{BASE_URL}/api/login",
            json={"username": "admin", "password": "admin"},  # CHANGE THIS
        )
        if resp.status_code == 200:
            csrf_token = resp.json().get("csrf_token")
        else:
            print(f"\n⚠ Login failed. You may need to manually set credentials.")
            print(f"Status: {resp.status_code}, Response: {resp.text}")
            return
    except Exception as e:
        print(f"\n⚠ Cannot connect to {BASE_URL}: {e}")
        print("Make sure the app is running: docker-compose up -d")
        return
    
    try:
        # Run tests
        test_health()
        libraries = test_create_libraries()
        
        photo_lib = next(lib for lib in libraries if lib["type"] == "photo_video")
        uploads = test_upload_photos(photo_lib["id"])
        
        first_upload = uploads[0]
        test_duplicate_upload(photo_lib["id"], first_upload["sha256"])
        
        test_tags(photo_lib["id"], first_upload["file_id"])
        test_trash_and_restore(photo_lib["id"], first_upload["file_id"])
        
        print(f"\n{'#'*60}")
        print(f"  ✅ ALL TESTS PASSED")
        print(f"{'#'*60}\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        raise
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        raise


if __name__ == "__main__":
    run_tests()

