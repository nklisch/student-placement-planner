# Install Student Placement Planner

Download the self-contained app for **Windows x64** or **Apple-Silicon Mac**. You do not need Python or a terminal. There is no Intel Mac installer.

## Before opening a download

1. Start at the [official project website](https://nklisch.github.io/student-placement-planner/) or [GitHub releases](https://github.com/nklisch/student-placement-planner/releases). Check that the repository is `nklisch/student-placement-planner`, not a similarly named download site.
2. Choose the installer for your computer. On a Mac, **Apple menu → About This Mac** should show an Apple chip, such as M1 or M2, rather than Intel. On Windows, **Settings → System → About → System type** identifies an x64-based processor.
3. Read that release's notes and signing information. Preview builds may have signatures that Windows or Apple does not trust. A signature alone does not mean the publisher has been verified.

The release includes SHA-256 checksums and GitHub build attestations. School IT can compare the downloaded file with this evidence before approving it. Matching a checksum confirms the file matches the release; it is not a malware assessment.

On a school-managed computer, ask IT whether this beta is approved **before installing**. Send them the release link and the exact warning if installation is blocked. Do not disable antivirus, SmartScreen, Gatekeeper, or school policy to install it.

## Windows

1. Open the downloaded `Student-Placement-Planner-…-Windows-x64-Setup.exe`.
2. Follow the setup window. If Windows asks permission to make changes, check that this is the installer you deliberately opened. Cancel if the file or publisher information is unexpected.
3. After setup finishes, open **Student Placement Planner** from Start.

### If Windows warns about an unrecognized app

A preview certificate may appear as an unknown or unverified publisher. SmartScreen can also warn about a newly signed app that has not built a reputation. This warning is not the same as a specific malware detection.

If you have checked the official release and your school's policy permits it, **More info** on the “Windows protected your PC” screen may offer **Run anyway**. Review the app and publisher there before deciding. This is a decision about that file, not an instruction to turn off protection.

If **Run anyway** is absent, Windows reports a malware detection, or an administrator blocks the app, stop and contact IT. Smart App Control and managed policies can prevent exceptions; there is no universal confirmation sequence. See [Microsoft's SmartScreen guidance](https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen/).

## macOS

1. Open the downloaded `Student-Placement-Planner-…-macOS-Apple-Silicon.dmg`.
2. Drag **Student Placement Planner** to **Applications** in Finder.
3. Open the app from Applications. If macOS simply asks whether to open an app downloaded from the internet, check its name and choose **Open** if you intended to launch it.
4. Eject the disk image after copying the app.

### If Apple cannot verify the developer or check the app

Preview builds may use an ad-hoc signature rather than an Apple-verified developer signature and notarization. macOS cannot use that preview signature to establish the developer's identity or that Apple checked the app.

Only if you have verified the official source and your school's policy permits the app:

1. Try opening the app once, then close the warning.
2. Open **System Settings → Privacy & Security**.
3. Scroll to the security message for this app. If **Open Anyway** is offered, select it and follow the confirmation prompts.

This makes an exception for this app. It is not a promise that every warning can be overridden. On managed Macs the setting may be unavailable. If macOS says the app **will damage your computer**, contains malware, or is damaged, do not use this exception procedure. Stop, check the release, and contact IT or [report the problem](https://github.com/nklisch/student-placement-planner/issues) without attaching student data.

These steps follow [Apple's “Safely open apps on your Mac” guidance](https://support.apple.com/en-us/102445) (published May 27, 2026). Warning wording varies by macOS version; a right-click shortcut is not a universal workaround.

## First launch

Choose **File → Load sample data**, then **Find placements**. The sample uses manual driving times and needs no internet or account. Continue with the [user guide](USER_GUIDE.md) to enter your own data and save a reusable project.

The instructions above are based on the app's packaging and OS vendor guidance. They do not claim a fresh hands-on installation check of every supported Windows/macOS version.
