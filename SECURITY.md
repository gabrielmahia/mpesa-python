# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Yes    |

## Reporting a Vulnerability

If you discover an error:

DO NOT open a public issue.

Email directly to:
contact@aikungfu.dev

## Security Notes

- This SDK never logs credentials, tokens, or phone numbers
- OAuth tokens are held in memory only (not written to disk)
- The `security_credential` for B2C must be encrypted by the caller per Daraja documentation
- Webhook validation: always verify requests originate from Safaricom IPs in production
