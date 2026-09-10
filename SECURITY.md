# 🔐 Security Policy

> We take the security of Visora, its HTTP bridge, and the Unity Editor execution environment seriously. Responsible vulnerability reports are appreciated and promptly addressed.

---

## 🛡️ Supported Versions

We provide security updates and patches for the following versions:

| Version | Supported | Status |
| :--- | :---: | :--- |
| `0.1.x` (Current) | ✅ | Actively supported with security fixes |
| `< 0.1.0` | ❌ | End of life — please upgrade to the latest release |

---

## 📬 Reporting a Vulnerability

> [!WARNING]
> **Do NOT file public GitHub issues for security vulnerabilities.**

Please submit security concerns privately via [GitHub's Private Vulnerability Reporting](https://github.com/AmaLS367/Visora/security/advisories/new).

Please include as much detail as possible:
- 🎯 **Vulnerability Type**: Path traversal, SSRF, command injection, authorization bypass, etc.
- 📦 **Affected Components**: Python MCP server, native Unity package (`com.visora.editor`), or bridge client.
- ⚙️ **Reproduction Steps**: Detailed instructions or a minimal proof-of-concept.
- 💡 **Suggested Fix**: Remediation suggestions or patches (if available).

> [!CAUTION]
> Never include real secrets, API credentials, or proprietary Unity assets in vulnerability reports.

### ⏱️ Response Timeline

- **Initial Triage**: We aim to acknowledge reports within 48 hours.
- **Coordination**: We will validate the issue and coordinate a patch privately.
- **Disclosure**: A CVE/Advisory and release will be published simultaneously once users have a clear update path.

