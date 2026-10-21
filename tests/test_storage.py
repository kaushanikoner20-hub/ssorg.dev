"""Tests for app/storage.py: hashing, validation, safe filenames and safe file handling."""

import io
import os

from PIL import Image

from app import config, storage


def make_image_bytes(image_format="PNG", color="white", size=(60, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, image_format)
    return buffer.getvalue()


# ----- hashing -----
def test_hash_is_sha256_of_the_bytes():
    assert storage.hash_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_identical_bytes_have_identical_hashes_and_different_bytes_differ():
    first = make_image_bytes(color="red")
    same = bytes(first)
    other = make_image_bytes(color="blue")
    assert storage.hash_bytes(first) == storage.hash_bytes(same)
    assert storage.hash_bytes(first) != storage.hash_bytes(other)


# ----- validation -----
def test_valid_formats_are_detected_from_content():
    assert storage.validate_image_bytes(make_image_bytes("PNG")).extension == ".png"
    assert storage.validate_image_bytes(make_image_bytes("JPEG")).extension == ".jpg"
    assert storage.validate_image_bytes(make_image_bytes("JPEG")).mime_type == "image/jpeg"
    assert storage.validate_image_bytes(make_image_bytes("WEBP")).mime_type == "image/webp"


def expect_invalid(data):
    try:
        storage.validate_image_bytes(data)
    except storage.InvalidImageError as error:
        return str(error)
    return None


def test_invalid_uploads_are_rejected_with_friendly_messages():
    assert "empty" in expect_invalid(b"")
    assert "could not be read" in expect_invalid(b"this is not an image")
    assert "Only PNG" in expect_invalid(make_image_bytes("GIF"))


def test_oversized_upload_is_rejected():
    too_big = b"x" * (config.MAX_FILE_SIZE_MB * 1024 * 1024 + 1)
    assert "limit" in expect_invalid(too_big)


# ----- generated filenames -----
def test_generated_filenames_are_safe_and_unique():
    names = {storage.generate_stored_filename(".png") for _ in range(50)}
    assert len(names) == 50
    for name in names:
        assert name.endswith(".png") and len(name) == 36
        assert "/" not in name and "\\" not in name and ".." not in name


def test_generating_a_name_with_a_strange_extension_is_refused():
    try:
        storage.generate_stored_filename(".exe")
    except storage.StorageError:
        return
    raise AssertionError("an unsupported extension should be refused")


# ----- path safety -----
GOOD_NAME = "0123456789abcdef0123456789abcdef.png"


def test_good_name_resolves_inside_the_storage_folder(tmp_path):
    path = storage.resolve_stored_path(GOOD_NAME, tmp_path)
    assert path.parent == tmp_path.resolve()
    assert path.name == GOOD_NAME


def test_path_traversal_and_odd_names_are_rejected(tmp_path):
    bad_names = [
        "../evil.png",
        "..\\evil.png",
        "../../etc/passwd",
        "sub/" + GOOD_NAME,
        "sub\\" + GOOD_NAME,
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "C:/Windows/win.ini",
        GOOD_NAME + "\x00.txt",
        "evil.png",                      # not one of our generated names
        "0123456789abcdef0123456789abcdef.exe",
        "0123456789ABCDEF0123456789ABCDEF.png",  # we only generate lowercase
        "",
        " " + GOOD_NAME,
        GOOD_NAME + " ",
        None,
        123,
    ]
    for name in bad_names:
        try:
            storage.resolve_stored_path(name, tmp_path)
        except storage.UnsafePathError:
            continue
        raise AssertionError(f"{name!r} should have been rejected")


def test_symlink_pointing_outside_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.png"
    secret.write_bytes(b"do not delete")
    storage_dir = tmp_path / "shots"
    storage_dir.mkdir()
    try:
        os.symlink(secret, storage_dir / GOOD_NAME)
    except (OSError, NotImplementedError):
        return  # this computer does not allow symlinks (common on Windows without admin rights)
    try:
        storage.delete_stored_file(GOOD_NAME, storage_dir)
    except storage.UnsafePathError:
        pass
    else:
        raise AssertionError("a symlink leaving the storage folder must be rejected")
    assert secret.read_bytes() == b"do not delete"


# ----- saving, reading, deleting -----
def test_save_and_read_back(tmp_path):
    storage_dir = tmp_path / "shots"  # does not exist yet; it is created
    data = make_image_bytes()
    saved_path = storage.save_image_bytes(data, GOOD_NAME, storage_dir)
    assert saved_path.read_bytes() == data
    assert storage.read_stored_file(GOOD_NAME, storage_dir) == data


def test_saving_never_overwrites_an_existing_file(tmp_path):
    storage_dir = tmp_path / "shots"
    storage.save_image_bytes(b"original", GOOD_NAME, storage_dir)
    try:
        storage.save_image_bytes(b"replacement", GOOD_NAME, storage_dir)
    except storage.StorageError:
        pass
    else:
        raise AssertionError("overwriting must be refused")
    assert (storage_dir / GOOD_NAME).read_bytes() == b"original"


def test_reading_a_missing_or_unsafe_file_returns_none(tmp_path):
    assert storage.read_stored_file(GOOD_NAME, tmp_path) is None
    assert storage.read_stored_file("../x.png", tmp_path) is None


def test_delete_removes_only_the_named_file(tmp_path):
    other = "fedcba9876543210fedcba9876543210.png"
    storage.save_image_bytes(b"a", GOOD_NAME, tmp_path)
    storage.save_image_bytes(b"b", other, tmp_path)
    assert storage.delete_stored_file(GOOD_NAME, tmp_path) is True
    assert not (tmp_path / GOOD_NAME).exists()
    assert (tmp_path / other).exists()


def test_deleting_a_missing_file_returns_false(tmp_path):
    assert storage.delete_stored_file(GOOD_NAME, tmp_path) is False


def test_delete_refuses_unsafe_names_and_leaves_outside_files_alone(tmp_path):
    storage_dir = tmp_path / "shots"
    storage_dir.mkdir()
    decoy = tmp_path / "outside.png"
    decoy.write_bytes(b"keep me")
    for name in ("../outside.png", "..\\outside.png", str(decoy)):
        try:
            storage.delete_stored_file(name, storage_dir)
        except storage.UnsafePathError:
            continue
        raise AssertionError(f"{name!r} should have been refused")
    assert decoy.read_bytes() == b"keep me"


def test_default_storage_folder_comes_from_config(tmp_path):
    storage.save_image_bytes(b"x", GOOD_NAME)  # no folder given: uses the (temporary) config folder
    assert (config.SCREENSHOT_DIR / GOOD_NAME).is_file()