# Security Policy

## Supported versions

Security fixes are applied only to the latest released version on the
`main` branch (and the matching release of `obd-tui`).

| Version | Supported |
| --- | --- |
| latest release | ✅ |
| older releases | ❌ |

## Reporting a vulnerability

**Please do not open a public issue.** GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
is the preferred channel:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the issue with reproduction steps and a suggested mitigation.

If you cannot use GitHub's form, email **goabonga@pm.me** with the same
information. PGP encryption is available on request.

You can expect an acknowledgement within **3 business days**, a triage
assessment within **10 business days**, and a fix or written mitigation
plan before any public disclosure.

## Scope

`obd-tui` is a local terminal application. It opens no network socket and
starts no subprocess. Its untrusted input is what a vehicle and its adapter
send back over the serial link: ECU responses, descriptor strings and
trouble codes, all of which reach the screen. Reports about that path —
crafted adapter responses, the serial port it decides to open, or anything
that turns a reading into code execution — are in scope.

Vulnerabilities in third-party dependencies (python-obd, pyserial, Textual)
should be reported upstream, but please let us know so the ranges can be
bumped here.

Thanks for helping keep the project and its users safe.
