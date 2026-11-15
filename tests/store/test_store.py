"""The store may only repeat what the disk already says.

Half of these tests are about the one failure mode that matters here: a listing that describes a
package nobody built, or a permission string the wrapper does not actually carry. Both would look
like success on screen and fail on the phone, so they are checked against bytes and files instead
of against the page.
"""

import hashlib
import json
import os
import plistlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.app import create_app
from src.config import Config
from src.store import altsource, inventory

ROOT = Path(__file__).resolve().parent.parent.parent
IOS_DIR = ROOT / "ios" / "FameStrategist"
APK_APP = ROOT / "apk" / "app"
sys.path.insert(0, str(ROOT / "scripts"))
from make_icons import ANDROID_SIZES       # noqa: E402  the same table the icons were cut from

LAPTOP = ("127.0.0.1", 53211)
PHONE = ("192.168.1.50", 53212)


@pytest.fixture
def shelf(tmp_path):
    """One machine, one store, no packages yet - the state a fresh clone is really in."""
    app = create_app(Config(api_key=None, engine_name="offline", model=""),
                     tmp_path / "a.sqlite3")
    return {"root": tmp_path,
            "packages": tmp_path / "packages",
            "laptop": TestClient(app, client=LAPTOP),
            "phone": TestClient(app, client=PHONE)}


def drop(packages, name, payload=b"x" * 2048, mtime=None):
    packages.mkdir(parents=True, exist_ok=True)
    path = packages / name
    path.write_bytes(payload)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# ---- what the folder actually holds -----------------------------------------


def test_an_empty_folder_answers_empty(shelf):
    assert inventory.scan(shelf["root"]) == []


def test_a_note_beside_the_packages_is_not_a_package(shelf):
    drop(shelf["packages"], "readme.txt", b"build me later")
    drop(shelf["packages"], "store.json", b'{"name": "x"}')
    assert inventory.scan(shelf["root"]) == []


def test_a_real_package_is_measured_not_described(shelf):
    payload = bytes(range(256)) * 7
    drop(shelf["packages"], "fame-1.0.apk", payload)
    item = inventory.scan(shelf["root"])[0]
    assert (item.kind, item.name, item.size) == ("android", "fame-1.0.apk", len(payload))
    assert item.sha256 == hashlib.sha256(payload).hexdigest()
    assert item.url == "/store/dl/fame-1.0.apk"
    assert item.megabytes.endswith(" MB")


def test_the_newest_build_leads_the_list(shelf):
    drop(shelf["packages"], "old.apk", mtime=1_600_000_000)
    drop(shelf["packages"], "new.apk", mtime=1_700_000_000)
    assert [a.name for a in inventory.scan(shelf["root"])] == ["new.apk", "old.apk"]


# ---- the one door to the bytes ----------------------------------------------


def test_a_bare_name_reaches_the_folder(shelf):
    built = drop(shelf["packages"], "fame.apk")
    assert inventory.resolve(shelf["root"], "fame.apk") == built.resolve()


@pytest.mark.parametrize("name", [
    "",
    "fame.apk/",
    "../a.sqlite3",
    "sub/fame.apk",
    "sub\\fame.apk",
    "a.sqlite3",
    "notes.txt",
    "missing.apk",
    "fame\x00.apk",
])
def test_every_way_out_of_the_folder_is_refused(shelf, name):
    drop(shelf["packages"], "fame.apk")
    assert inventory.resolve(shelf["root"], name) is None


def test_a_folder_named_like_a_package_is_not_one(shelf):
    (shelf["packages"] / "fake.apk").mkdir(parents=True)
    assert inventory.resolve(shelf["root"], "fake.apk") is None


def test_a_symlink_pointing_outside_is_refused(shelf):
    outside = drop(shelf["root"], "elsewhere.apk")
    try:
        os.symlink(outside, shelf["packages"] / "trap.apk")
    except (OSError, NotImplementedError):
        pytest.skip("this machine will not let a test make a symlink")
    assert inventory.resolve(shelf["root"], "trap.apk") is None


# ---- the listing file --------------------------------------------------------


def test_no_ipa_no_app_entry(shelf):
    body = altsource.source([], shelf["root"], "http://192.168.1.20:8756")
    assert body["apps"] == []
    assert body["news"] == []
    assert body["nsfw"] is False
    assert "featuredApps" not in body            # nothing to feature


def test_an_ipa_is_described_only_by_its_own_bytes(shelf):
    payload = b"\x50\x4b" + b"ipa contents" * 40
    drop(shelf["packages"], "Fame.ipa", payload)
    body = altsource.source(inventory.scan(shelf["root"]), shelf["root"],
                            "http://192.168.1.20:8756")
    version = body["apps"][0]["versions"][0]
    assert len(body["apps"]) == 1
    assert version["size"] == len(payload)
    assert version["downloadURL"] == "http://192.168.1.20:8756/store/dl/Fame.ipa"
    assert version["version"] == altsource.VERSION
    assert version["minOSVersion"] == altsource.MIN_OS
    assert body["apps"][0]["appPermissions"]["privacy"] == altsource.PRIVACY
    assert body["apps"][0]["appPermissions"]["entitlements"] == []
    assert body["featuredApps"] == [altsource.BUNDLE_ID]


def test_versions_go_newest_first_because_altstore_reads_them_that_way(shelf):
    drop(shelf["packages"], "older.ipa", mtime=1_600_000_000)
    drop(shelf["packages"], "newer.ipa", mtime=1_700_000_000)
    versions = altsource.source(inventory.scan(shelf["root"]), shelf["root"],
                                "http://10.0.0.5:8756")["apps"][0]["versions"]
    assert [v["downloadURL"].rsplit("/", 1)[1] for v in versions] == ["newer.ipa", "older.ipa"]


def test_the_copy_file_changes_the_words_not_the_identity(shelf):
    drop(shelf["packages"], "store.json", json.dumps({
        "name": "Fame Lab", "developer": "her own name",
        "bundle_id": "com.somebody.else", "version": "9.9"}).encode())
    listing = altsource.listing_for(shelf["root"])
    assert (listing.name, listing.developer) == ("Fame Lab", "her own name")
    assert listing.subtitle == altsource.Listing().subtitle      # untouched, still true
    assert listing.bundle_id == altsource.BUNDLE_ID
    assert listing.version == altsource.VERSION


def test_a_broken_copy_file_leaves_the_defaults(shelf):
    drop(shelf["packages"], "store.json", b"{ not json at all")
    assert altsource.listing_for(shelf["root"]) == altsource.Listing()


# ---- the wrapper and the listing must never drift ----------------------------


def test_the_permission_strings_are_the_ones_the_wrapper_carries():
    plist = plistlib.load((IOS_DIR / "Info.plist").open("rb"))
    for key, text in altsource.PRIVACY.items():
        assert plist[key] == text, f"{key} drifted from the published listing"


def test_the_version_pair_matches_the_plist_and_the_xcode_manifest():
    plist = plistlib.load((IOS_DIR / "Info.plist").open("rb"))
    assert plist["CFBundleShortVersionString"] == altsource.VERSION
    assert plist["CFBundleVersion"] == altsource.BUILD
    manifest = (IOS_DIR.parent / "project.yml").read_text(encoding="utf-8")
    assert f"PRODUCT_BUNDLE_IDENTIFIER: {altsource.BUNDLE_ID}" in manifest
    assert f'"{altsource.MIN_OS}"' in manifest


def test_the_wrapper_asks_for_no_entitlements_and_the_listing_agrees():
    entitlements = plistlib.load((IOS_DIR / "Fame.entitlements").open("rb"))
    assert entitlements == {}
    assert list(altsource.ENTITLEMENTS) == []


def test_the_android_build_claims_the_same_version_as_the_ios_wrapper():
    gradle = (APK_APP / "build.gradle").read_text(encoding="utf-8")
    assert f"versionName '{altsource.VERSION}'" in gradle
    assert f"versionCode {altsource.BUILD}" in gradle
    assert f"namespace '{altsource.BUNDLE_ID}'" in gradle


# ---- the launcher art the build files point at ------------------------------


def test_the_ios_catalog_lists_only_icons_that_exist():
    catalog = IOS_DIR / "Assets.xcassets" / "AppIcon.appiconset"
    images = json.loads((catalog / "Contents.json").read_text(encoding="utf-8"))["images"]
    assert images, "an empty catalog is an app with no icon"
    for entry in images:
        png = catalog / entry["filename"]
        assert png.is_file(), entry["filename"]
        points = int(entry["size"].split("x")[0])
        scale = int(entry["scale"].rstrip("x"))
        assert png.stem == f"AppIcon-{points * scale}", f"{entry} does not match its own name"
        with Image.open(png) as icon:
            assert icon.size == (points * scale, points * scale)


def test_the_android_mipmaps_are_the_sizes_android_asks_for():
    for density, px in ANDROID_SIZES.items():
        png = APK_APP / "src" / "main" / "res" / f"mipmap-{density}" / "ic_launcher.png"
        assert png.is_file(), density
        with Image.open(png) as icon:
            assert icon.size == (px, px)


# ---- the three routes -------------------------------------------------------


def test_the_store_page_is_a_laptop_page(shelf):
    assert shelf["laptop"].get("/store").status_code == 200
    assert shelf["phone"].get("/store").status_code == 401


def test_an_installer_reaches_the_listing_without_the_pin(shelf):
    """An installer app fetches a URL on its own and cannot carry her cookie, so the listing has
    to answer a stranger on the wifi - that is the documented exception, not an oversight."""
    got = shelf["phone"].get("/store/apps.json")
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("application/json")
    assert json.loads(got.text)["apps"] == []


def test_an_installer_reaches_the_bytes_without_the_pin(shelf):
    payload = drop(shelf["packages"], "fame.apk", b"apk bytes here").read_bytes()
    got = shelf["phone"].get("/store/dl/fame.apk")
    assert got.status_code == 200
    assert got.content == payload
    assert "attachment" in got.headers["content-disposition"]


def test_the_listing_urls_are_absolute_and_point_at_this_machine(shelf):
    drop(shelf["packages"], "Fame.ipa")
    body = json.loads(shelf["laptop"].get("/store/apps.json").text)
    url = body["apps"][0]["versions"][0]["downloadURL"]
    assert url.startswith("http")
    assert url.endswith("/store/dl/Fame.ipa")


def test_a_name_that_is_not_a_package_is_a_plain_404(shelf):
    for name in ["fame.apk", "nope.ipa", "a.sqlite3"]:
        got = shelf["laptop"].get(f"/store/dl/{name}")
        assert got.status_code == 404, name
        assert "no package by that name" in got.json()["detail"]


def test_the_page_names_the_file_it_can_really_offer(shelf):
    drop(shelf["packages"], "fame-1.0.apk", b"y" * (2 * 1024 * 1024))
    text = shelf["laptop"].get("/store").text
    assert "fame-1.0.apk" in text
    assert "2.0 MB" in text
    assert "Nothing here yet" not in text


def test_the_page_offers_no_download_link_for_nothing(shelf):
    text = shelf["laptop"].get("/store").text
    assert "Nothing here yet" in text
    assert "/store/dl/" not in text
