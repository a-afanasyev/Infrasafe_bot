# Bot Gateway Service - Security Guide
**UK Management Bot - Sprint 19-22**

Comprehensive security implementation guide for Bot Gateway Service.

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Security Features](#security-features)
3. [Rate Limiting](#rate-limiting)
4. [Input Validation](#input-validation)
5. [Service Authentication](#service-authentication)
6. [Security Headers](#security-headers)
7. [CORS Configuration](#cors-configuration)
8. [Secrets Management](#secrets-management)
9. [Security Audit Checklist](#security-audit-checklist)
10. [Incident Response](#incident-response)

---

## 🛡 Overview

Bot Gateway Service implements multiple layers of security to protect against common attacks and unauthorized access.

### Security Principles

- **Defense in Depth**: Multiple security layers
- **Least Privilege**: Minimal permissions by default
- **Fail Secure**: Deny access on errors
- **Zero Trust**: Verify all requests
- **Audit Everything**: Comprehensive logging

---

## 🔒 Security Features

### 1. Advanced Rate Limiting

**Implementation**: Redis-based sliding window algorithm

**Features**:
- Per-user rate limits
- Distributed across bot instances
- Atomic operations (Lua scripts)
- Burst allowance support
- Automatic metrics tracking

**Configuration**:
```python
# app/core/rate_limiter.py
RATE_LIMITS = {
    "messages_per_minute": RateLimitConfig(
        max_requests=20,
        window_seconds=60,
        burst_size=25  # Allow 5 extra for bursts
    ),
    "messages_per_hour": RateLimitConfig(
        max_requests=100,
        window_seconds=3600
    ),
    "commands_per_minute": RateLimitConfig(
        max_requests=5,
        window_seconds=60,
        burst_size=7
    )
}
```

**Environment Variables**:
```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MESSAGES_PER_MINUTE=20
RATE_LIMIT_MESSAGES_PER_HOUR=100
RATE_LIMIT_COMMANDS_PER_MINUTE=5
```

---

### 2. Input Validation

**Implementation**: Comprehensive validation framework

**Protection Against**:
- SQL injection
- XSS attacks
- Command injection
- Path traversal
- Buffer overflow
- Invalid data types

**Usage Example**:
```python
from app.core.validators import InputValidator, ValidationError

try:
    # Validate telegram ID
    user_id = InputValidator.validate_telegram_id(telegram_id)

    # Validate request number
    req_num = InputValidator.validate_request_number("251007-001")

    # Validate text input
    text = InputValidator.validate_text(
        user_input,
        max_length=1000,
        allow_empty=False,
        field_name="description"
    )

    # Validate pagination
    limit, offset = InputValidator.validate_pagination(
        limit=request.query.get("limit"),
        offset=request.query.get("offset")
    )

except ValidationError as e:
    logger.warning(f"Validation failed: {e}")
    # Return error to user
```

**Validated Fields**:
- Telegram IDs
- Request numbers (YYMMDD-NNN)
- UUIDs
- Phone numbers
- Email addresses
- Dates and times
- Addresses
- Specializations
- File paths

---

### 3. Service-to-Service Authentication

**Implementation**: HMAC-SHA256 request signing

**Features**:
- Per-service secret keys
- Timestamp validation (prevents replay attacks)
- Request integrity verification
- Atomic signature generation

**Signing Requests** (Outgoing):
```python
from app.core.request_signing import service_authenticator

# Sign request to another service
headers = service_authenticator.sign_outgoing_request(
    service_name="user-service",
    method="POST",
    path="/api/v1/users",
    body=json.dumps(payload)
)

# Headers added:
# X-Service-Signature: <hmac_signature>
# X-Service-Timestamp: <unix_timestamp>
# X-Service-Name: bot-gateway

response = await httpx.post(
    url,
    json=payload,
    headers=headers
)
```

**Verifying Requests** (Incoming):
```python
from app.core.request_signing import service_authenticator

result = service_authenticator.verify_incoming_request(
    from_service=request.headers["X-Service-Name"],
    method=request.method,
    path=request.path,
    signature=request.headers["X-Service-Signature"],
    timestamp=request.headers["X-Service-Timestamp"],
    body=await request.text()
)

if not result.valid:
    logger.warning(f"Invalid signature: {result.error}")
    return web.Response(status=401, text="Unauthorized")
```

**Configuration**:
```bash
# .env
ENABLE_REQUEST_SIGNING=true

# Per-service keys (generate unique keys for each service)
AUTH_SERVICE_KEY=your-secret-key-here-32-chars-min
USER_SERVICE_KEY=your-secret-key-here-32-chars-min
REQUEST_SERVICE_KEY=your-secret-key-here-32-chars-min
```

**Generating Keys**:
```bash
# Generate secure random keys
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

### 4. Security Headers

**Implementation**: Middleware adding security headers to all responses

**Headers Added**:

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Content-Type-Options` | `nosniff` | Prevent MIME sniffing |
| `X-Frame-Options` | `DENY` | Prevent clickjacking |
| `X-XSS-Protection` | `1; mode=block` | Enable XSS filtering |
| `Strict-Transport-Security` | `max-age=31536000` | Force HTTPS |
| `Content-Security-Policy` | See below | Restrict resources |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Control referrer |
| `Permissions-Policy` | See below | Restrict features |

**Content Security Policy**:
```
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' data: https:;
font-src 'self';
connect-src 'self';
frame-ancestors 'none';
base-uri 'self';
form-action 'self'
```

**Permissions Policy**:
```
geolocation=(), microphone=(), camera=(),
payment=(), usb=(), magnetometer=(),
accelerometer=(), gyroscope=()
```

**Configuration**:
```bash
ENABLE_SECURITY_HEADERS=true
```

---

### 5. CORS Configuration

**Implementation**: Middleware with configurable origins

**Configuration**:
```bash
# Allow specific origins (comma-separated)
ALLOWED_ORIGINS=http://localhost:3000,https://grafana.example.com

# Or allow all (NOT recommended for production)
ALLOWED_ORIGINS=*
```

**Response Headers**:
- `Access-Control-Allow-Origin`
- `Access-Control-Allow-Credentials`
- `Access-Control-Allow-Methods`
- `Access-Control-Allow-Headers`
- `Access-Control-Max-Age`

---

## 🔐 Secrets Management

### Development

**Using .env file**:
```bash
# .env (never commit to git!)
TELEGRAM_BOT_TOKEN=your_token_here
JWT_SECRET_KEY=your_jwt_secret_32_chars_minimum
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db
REDIS_URL=redis://localhost:6379/0
```

### Production

**Recommended approaches**:

1. **Environment Variables** (Docker/Kubernetes):
   ```yaml
   # docker-compose.yml
   environment:
     - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
     - JWT_SECRET_KEY=${JWT_SECRET_KEY}
   ```

2. **Secrets Manager** (AWS Secrets Manager, HashiCorp Vault):
   ```python
   import boto3

   def get_secret(secret_name):
       client = boto3.client('secretsmanager')
       response = client.get_secret_value(SecretId=secret_name)
       return response['SecretString']
   ```

3. **Kubernetes Secrets**:
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: bot-gateway-secrets
   type: Opaque
   data:
     telegram-token: <base64-encoded>
     jwt-secret: <base64-encoded>
   ```

### Best Practices

✅ **DO**:
- Use strong, random secrets (32+ characters)
- Rotate secrets regularly
- Use different secrets for each environment
- Store secrets in secure vaults
- Use read-only access where possible

❌ **DON'T**:
- Commit secrets to git
- Share secrets via email/chat
- Reuse secrets across services
- Use default/example secrets
- Log secrets in application logs

---

## ✅ Security Audit Checklist

### Pre-Deployment

- [ ] All secrets are stored securely (not in code)
- [ ] Rate limiting is enabled and configured
- [ ] Input validation is enabled for all endpoints
- [ ] Security headers are enabled
- [ ] CORS is properly configured
- [ ] Request signing is enabled for production
- [ ] HTTPS is enforced (if production)
- [ ] Database credentials are secure
- [ ] Redis is password-protected
- [ ] Monitoring is configured
- [ ] Alerts are set up
- [ ] Logs don't contain sensitive data

### Post-Deployment

- [ ] Monitor for unusual traffic patterns
- [ ] Check error rates in metrics
- [ ] Review security logs regularly
- [ ] Test rate limiting is working
- [ ] Verify HTTPS is working
- [ ] Check for security updates
- [ ] Review access logs
- [ ] Test disaster recovery

### Regular Audits (Monthly)

- [ ] Review and rotate secrets
- [ ] Check for security updates
- [ ] Review access logs for anomalies
- [ ] Test backup and recovery
- [ ] Update dependencies
- [ ] Review alert configurations
- [ ] Penetration testing (quarterly)

---

## 🚨 Incident Response

### Attack Detection

**Signs of attack**:
- Sudden spike in error rates
- High rate limit blocks
- Failed authentication attempts
- Unusual traffic patterns
- Memory/CPU spikes

**Monitoring**:
```bash
# Check Grafana alerts
http://localhost:3000

# Check rate limit blocks
curl http://localhost:9090/api/v1/query?query=rate(bot_gateway_rate_limit_blocks_total[5m])

# Check error rates
curl http://localhost:9090/api/v1/query?query=rate(bot_gateway_errors_total[5m])
```

### Response Steps

1. **Identify**: Confirm attack is occurring
   ```bash
   # Check logs
   docker-compose logs bot-gateway | tail -100

   # Check metrics
   curl http://localhost:8000/metrics | grep error
   ```

2. **Contain**: Block attacking user/IP
   ```python
   # Using rate limiter
   from app.core.rate_limiter import rate_limiter

   # Reset specific user's limit (temporary ban)
   await rate_limiter.reset_limit(user_id, namespace="ban")
   ```

3. **Eradicate**: Fix vulnerability
   - Update code
   - Deploy patch
   - Update security rules

4. **Recover**: Return to normal operation
   - Monitor for continued attacks
   - Clear any corrupted data
   - Verify services are healthy

5. **Post-Incident**: Document and improve
   - Write incident report
   - Update security measures
   - Train team on new procedures

### Emergency Contacts

```yaml
# Define in your organization
Security Team: security@example.com
On-Call Engineer: +1-xxx-xxx-xxxx
DevOps Lead: devops@example.com
```

---

## 🔍 Penetration Testing

### Testing Areas

1. **Rate Limiting**:
   ```bash
   # Test message flood
   for i in {1..100}; do
     curl -X POST http://localhost:8000/webhook \
       -H "Content-Type: application/json" \
       -d '{"message":{"text":"test"}}'
   done
   ```

2. **Input Validation**:
   ```bash
   # Test SQL injection
   curl -X POST http://localhost:8000/api/test \
     -d "input=' OR '1'='1"

   # Test XSS
   curl -X POST http://localhost:8000/api/test \
     -d "input=<script>alert('xss')</script>"
   ```

3. **Authentication**:
   ```bash
   # Test without token
   curl http://localhost:8000/api/protected

   # Test with invalid token
   curl -H "Authorization: Bearer invalid" \
     http://localhost:8000/api/protected
   ```

### Tools

- **OWASP ZAP**: Web application security scanner
- **Burp Suite**: Web vulnerability scanner
- **Nikto**: Web server scanner
- **SQLMap**: SQL injection testing
- **Artillery**: Load testing

---

## 📚 Additional Resources

### Security Standards
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)

### Tools & Libraries
- [Safety](https://pypi.org/project/safety/) - Dependency vulnerability scanner
- [Bandit](https://pypi.org/project/bandit/) - Python security linter
- [Trivy](https://github.com/aquasecurity/trivy) - Container security scanner

### Best Practices
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/)
- [Python Security Best Practices](https://python.plainenglish.io/python-security-best-practices-cheat-sheet-3f8f4e5f7a0f)

---

**Last Updated:** 2025-10-07
**Version:** 1.0.0
**Sprint:** 19-22 Week 4
