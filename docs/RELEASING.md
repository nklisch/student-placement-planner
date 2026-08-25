# Building and publishing desktop releases

GitHub Actions builds the application on native Windows x64 and Apple-Silicon macOS runners. Each artifact contains Python, Qt, OR-Tools, the offline Valhalla engine and local region-building tools; users do not install those separately.

## Try a build without publishing

Run **Actions → Build desktop release → Run workflow** and enter a version such as `0.1.0-preview`. The workflow runs the full tests and uploads:

- `Student-Placement-Planner-<version>-Windows-x64-Setup.exe`
- `Student-Placement-Planner-<version>-macOS-Apple-Silicon.dmg`
- checksums and a small file describing the signing method used

Manual runs do not create a GitHub Release.

## Publish a prerelease

1. Update `pyproject.toml` to the intended version.
2. Run the complete local test and formatting gate.
3. Push the commit and tag it, for example `v0.1.0b1`.
4. The release workflow builds both platforms, creates GitHub build-provenance attestations, writes combined SHA-256 checksums, and creates a GitHub prerelease.
5. Test both downloads on clean machines before promoting a release.

## Preview signing and operating-system warnings

The workflow always signs the generated artifacts, but a signature is not automatically trusted by Windows or Apple.

When no signing secrets are configured:

- Windows creates an ephemeral self-signed Authenticode certificate. The file is signed, but another computer does not trust that certificate and Microsoft Defender SmartScreen may show an unknown-publisher warning.
- macOS applies an ad-hoc signature. Gatekeeper may require the user to right-click the app and choose **Open** once.

These fallbacks are suitable for development previews, not a friction-free public release. GitHub checksums and build attestations provide independent evidence that a binary came from this repository, but they do not remove operating-system warnings.

## Trusted Windows signing

Set these repository secrets:

- `WINDOWS_CERTIFICATE_BASE64` — base64-encoded trusted code-signing `.pfx`
- `WINDOWS_CERTIFICATE_PASSWORD` — its password

A certificate chained to a Windows-trusted root is required to avoid an untrusted-publisher prompt. SmartScreen reputation can still take time to develop. Microsoft Store distribution can be considered after the direct installer is stable.

## Trusted macOS signing and notarization

Set:

- `MACOS_CERTIFICATE_BASE64` — base64-encoded Developer ID Application `.p12`
- `MACOS_CERTIFICATE_PASSWORD`
- `APPLE_ID`
- `APPLE_TEAM_ID`
- `APPLE_APP_PASSWORD` — an app-specific password

With all values present, the workflow signs nested native libraries inside-out, signs the app and disk image, submits the disk image to Apple notarization, and staples the ticket. This requires an Apple Developer Program membership.

## Platform scope

The first macOS build targets Apple Silicon because pyvalhalla currently publishes macOS wheels for arm64 but not Intel. Manual and Google workflows can be packaged separately for Intel later, but an Intel build cannot promise offline routing until a compatible native wheel is available.

## Local packaging smoke test

Linux can validate the shared PyInstaller graph even though Linux is not a release target:

```bash
python -m pip install '.[offline-maps,build]'
pyinstaller --clean --noconfirm packaging/student-placement-planner.spec
'dist/Student Placement Planner/Student Placement Planner' --self-test-offline-builder
QT_QPA_PLATFORM=offscreen 'dist/Student Placement Planner/Student Placement Planner'
```

Windows uses `packaging/windows/installer.iss`. macOS uses the scripts under `packaging/macos/` to create the icon, sign the app, and build the disk image.
