# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in PRAHARI, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please contact the maintainer directly:

- **Author:** Sumit Nawale
- **LinkedIn:** https://www.linkedin.com/in/sumit-nawale-25274638b
- **Repository:** https://github.com/itzlucifa/PRAHARI-

## Security Considerations for Surveillance Systems

PRAHARI handles sensitive surveillance data. When deploying:

1. **Network Security**
   - Use TLS/WSS for all API and WebSocket connections
   - Isolate MQTT broker from public internet
   - Use VPN for remote access to dashboard

2. **Access Control**
   - Enable JWT authentication in production
   - Implement role-based access control (RBAC)
   - Audit all access to camera feeds and case files

3. **Data Protection**
   - Enable privacy blur by default
   - Log all unblur operations with officer ID and case number
   - Encrypt stored evidence files at rest

4. **Infrastructure**
   - Run services in Docker with minimal privileges
   - Keep model weights and credentials out of version control
   - Use Docker secrets for sensitive configuration

## Known Limitations

- Current implementation uses in-memory stores (not suitable for production without persistence)
- Default MQTT broker has no authentication
- No built-in rate limiting on API endpoints
- Test credentials and demo data should not be used in production

## Security Updates

Security updates will be released as patch versions. Follow the repository to stay informed.