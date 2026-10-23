# Apple Silicon macOS build

The native app supports macOS 12 or newer on M1 and later Apple Silicon Macs. Intel Macs are not a build target. The app bundles the Rust cartridge backend, Espressif esptool 4.12.0, openFPGALoader 1.1.1 and libusb 1.0.27. End users do not need Homebrew, Python or Rosetta. The existing ChroMagic USB protocol is used without firmware source changes.

## Build from source

Install full Xcode, open it once to complete setup, and select its developer directory. Install Flutter 3.44.6 (Dart 3.12.2), Rust, Python 3.12 or newer, CMake and pkg-config. Run these commands from `flutter/`:

```sh
flutter pub get --enforce-lockfile
flutter analyze
flutter test --concurrency=2 test/macos_app_update_test.dart test/app_update_test.dart test/windows_app_update_test.dart test/update_helper_test.dart test/update_ui_test.dart test/firmware_test.dart test/firmware_setup_test.dart test/firmware_dialog_test.dart test/backend_test.dart test/auto_read_test.dart test/controller_test.dart test/build_desktop_test.dart test/releases_test.dart
cargo test --workspace --locked --manifest-path ../Cargo.toml
dart run tool/build_desktop.dart
python3 tool/package_macos_app.py \
  build/macos/Build/Products/Release/chromatic_pc_backup.app \
  build/macos-package
```

Tool downloads are SHA-256 pinned. Native USB dependencies are built from the same pinned source revisions as the existing desktop releases. The packager checks architectures, rejects external non-system dylib paths, signs the nested executables/frameworks and app, verifies the signature, and emits a `.tar.gz`, SHA-256 file and `macos-build-info.json`. A tool-source archive is generated under `.dart_tool/`. Build metadata records the source commit and whether the checkout contains changes; it is a build record, not an independently signed attestation.

The `.app` above is directly installable. The release archive expands to `ChroMagician.app`; drag it to Applications or another writable folder. Keep all files inside the app together. Close MRUpdater and other serial-port applications before using ChroMagician. No Windows USB-driver setup is needed on macOS. Use a USB cable with data support. Firmware flashing and cartridge operations still require a physical console for final validation.

## Signing and distribution

Local builds use an ad-hoc signature (`--identity -`). This provides bundle-integrity checks, not an Apple-verified publisher identity or notarization. A downloaded ad-hoc build can be blocked by Gatekeeper. For public releases, use `--identity 'Developer ID Application: …'`, notarize the archive with an authorized Apple Developer account, and staple the ticket to the `.app` before producing the final release archive. Do not strip quarantine or disable Gatekeeper as part of installation.

The manually triggered `macos-arm64.yml` workflow builds on an Apple Silicon GitHub runner and retains artifacts for 90 days. It does not publish a release or raise a PR. Upload tested archives and their hashes to a GitHub release rather than committing compiled binaries into Git history.

The CI test selection above covers this port and existing backend/update regressions. A full test run also exercises SD/workspace UI tests with failures reproduced on the unmodified upstream source. Those existing failures are not hidden by changing production UI behavior in this port.

## Updates and validation

The Mac updater expects `ChroMagician-VERSION-macos-arm64.tar.gz` containing a top-level `ChroMagician.app`. It verifies the download hash, bounds extraction, rejects traversal and writes through symlinks, checks native ARM64 executables and code signatures, and uses the existing staged replacement/startup acknowledgement/rollback mechanism. Future release updates require upstream to publish the Mac asset under that filename.

To validate a packaged archive without touching hardware:

```sh
CHROMAGIC_TEST_MACOS_ARCHIVE="$PWD/build/macos-package/ChroMagician-1.0.3-macos-arm64.tar.gz" \
  flutter test test/macos_app_update_test.dart
```

Hardware acceptance should separately cover device discovery, backing up a known cartridge and save, SD file operations, firmware preflight, and explicitly authorized writes to a backed-up cartridge. Passing software tests does not establish those hardware results.
