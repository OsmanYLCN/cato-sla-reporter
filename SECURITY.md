# Security Policy

## Supported Versions

Security patches and maintenance updates are provided for the following release branches:

| Version Line | Support Status     | Release Lifecycle |
|--------------|--------------------|-------------------|
| 1.1.x        | Active Support     | Current           |
| 1.0.x        | End of Life (EOL)  | Deprecated        |

---

## Credential & Secret Management

This system processes network telemetry and interfaces with external infrastructure APIs. The following secret handling controls are strictly enforced:

- **Zero Embedded Secrets**: API keys, authentication tokens, and server passwords must never be committed to the repository or hardcoded in source modules.
- **Environment Isolation**: Credentials must be supplied exclusively through environment variables or a secured local `.env` file.
- **Access Control & Scope**: API tokens must adhere to the principle of least privilege, with permissions restricted exclusively to read-only connectivity event logs.
- **Repository Hygiene**: Local `.env` files and runtime secret stores are ignored by `.gitignore` and must never be staged.

---

## Reporting a Vulnerability

If you identify a security vulnerability, flaw, or potential credential exposure:

1. **Do not submit public issues, pull requests, or discussions.**
2. Report the vulnerability privately to the repository administrators or utilize GitHub Private Vulnerability Reporting where enabled.
3. Provide a clear technical summary, step-by-step reproduction instructions, and an impact assessment.

### Remediation SLA
- **Initial Assessment**: Within 24-48 business hours.
- **Patch Resolution**: Confirmed security vulnerabilities are remediated via an expedited patch release.
