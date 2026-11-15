# The Android package

A WebView pointed at her own laptop, and nothing else. `MainActivity` asks once for the address the
app shows at `/phone`, saves it, and hands it to `BrowserActivity`; that is the whole application.
There are no libraries to vendor: `dependencies` in [app/build.gradle](app/build.gradle) is empty on
purpose, because the entire surface is `android.webkit`, which ships with the OS.

## What is here

| File | Why it exists |
| --- | --- |
| `app/src/main/java/com/fame/strategist/MainActivity.kt` | the address box, and the one place the saved address is written |
| `app/src/main/java/com/fame/strategist/BrowserActivity.kt` | the WebView, the file chooser, the camera grant, the download listener, and the screen that says which address failed |
| `app/src/main/AndroidManifest.xml` | three permissions and two activities, each with a reason in the comment above it |
| `app/src/main/res/xml/network_security_config.xml` | plain http allowed only on 10/8, 172.16/12, 192.168/16 and `.local` |
| `app/src/main/res/mipmap-*/ic_launcher.png` | cut from `src/static/icon-512.png` by `../scripts/make_icons.py` |
| `build.gradle`, `settings.gradle`, `gradle.properties` | AGP 8.7.3 + Kotlin 2.0.21, JDK 17, `versionName 1.0` |

## Building it

Nothing in this folder has been compiled on this machine yet, and that is a fact about the machine,
not the project: there is no JDK, no Gradle and no Android SDK here today.

```powershell
powershell -ExecutionPolicy Bypass -File ..\scripts\build_apk.ps1          # signed release
powershell -ExecutionPolicy Bypass -File ..\scripts\build_apk.ps1 -Debug   # her own phone
```

The script wants a Gradle wrapper at `apk/gradlew.bat` (Android Studio writes it when the folder is
opened) or `gradle` on `PATH`, and prints the three ways to get one when neither is there. A release
needs a key first:

```powershell
powershell -ExecutionPolicy Bypass -File ..\scripts\make_keystore.ps1
```

That writes `keystore/fame.keystore` (ignored by git) and the four `fame*` properties into
`%USERPROFILE%\.gradle\gradle.properties`. Keeping the same keystore is what lets an update install
over the app already on the phone; a new key means an uninstall first, and no way to merge the two.

A successful build copies the APK to `data/packages/`, where `/store` lists it and the download link
is the installer. `/store` cannot say "ready" before that copy happens, and does not try to.

## Two rules worth knowing before changing anything

**The cleartext exception is scoped, not switched off.** `network_security_config.xml` allows plain
http on the private ranges a laptop gets from a router, plus `.local` names. Typing a public address
into the setup screen is refused there rather than failing later, because the OS would refuse it
silently and "the laptop did not answer" would be a lie. The iOS side does the same thing with
`NSAppTransportSecurity`.

**Install from Unknown sources is her tap, not the app's.** Android requires it for any APK that did
not come from Play, and no code in this folder can pre-approve it. The `.apk` is signed by her key
and self-hosted, so there is no review, no account fee and no approval queue - which is also why the
app is only ever as live as the PC behind it.
