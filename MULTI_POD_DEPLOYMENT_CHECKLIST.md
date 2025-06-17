# Multi-Pod Deployment Session Persistence Checklist

## ✅ Already Configured Correctly

1. **Database Sessions**: Using `SESSION_ENGINE = "django.contrib.sessions.backends.db"` - sessions are stored in the shared PostgreSQL database
2. **Secret Key**: Production environment correctly uses `DJANGO_SECRET_KEY` environment variable
3. **Shared Database**: All pods connect to the same PostgreSQL database via `DATABASE_URL`
4. **Authentication Backends**: Using django-allauth and sesame which work well with database sessions

## ✅ Recently Added/Fixed

1. **Session Cookie Settings**: 
   - `SESSION_COOKIE_SECURE = True` for HTTPS-only cookies
   - `SESSION_COOKIE_HTTPONLY = True` for XSS protection
   - `SESSION_COOKIE_SAMESITE = 'Lax'` for CSRF protection
   - `SESSION_COOKIE_AGE = 86400 * 30` (30 days)

2. **CSRF Protection**:
   - `CSRF_COOKIE_SECURE = True`
   - `CSRF_COOKIE_HTTPONLY = True` 
   - `CSRF_COOKIE_SAMESITE = 'Lax'`

3. **Cache Configuration**: Database-backed cache for shared state across pods

4. **Security Headers**: HSTS, XSS filter, content type nosniff

## 🔧 Next Steps Required

### 1. Environment Variables
Ensure these environment variables are set in your DigitalOcean App Platform:

```bash
DJANGO_SECRET_KEY=your-super-secret-key-here-make-it-long-and-random
DATABASE_URL=postgresql://... (should already be set)
```

### 2. Run Migration Command
After deployment, run this to create the cache table:
```bash
python manage.py createcachetable
```
(This is automatically included in the updated `post_deploy.py` command)

### 3. Test Session Persistence
To verify sessions work across pods:

1. Log in to your application
2. Check browser dev tools → Application → Cookies to see the session cookie
3. Make multiple requests - they may hit different pods
4. Verify you stay logged in
5. Check that session data persists

## 🚨 Critical Security Notes

1. **Secret Key**: Must be the same across all pods. If each pod has a different SECRET_KEY, sessions won't work between them.

2. **Session Cookie Domain**: Your current setup should work, but if you have issues, you might need to set:
   ```python
   SESSION_COOKIE_DOMAIN = '.overslotbaseball.com'  # Note the leading dot
   ```

3. **Load Balancer**: Ensure your load balancer forwards the correct headers (already configured with `SECURE_PROXY_SSL_HEADER`)

## 🔍 How Sessions Work in Multi-Pod Setup

1. User logs in → Django creates session in database
2. Django sends session cookie to browser
3. Subsequent requests include session cookie
4. Any pod can look up session in shared database using session key
5. User remains authenticated across all pods

## 🛠️ Alternative Improvements (Future)

For higher traffic, consider:

1. **Redis Sessions**: 
   ```python
   SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
   SESSION_CACHE_ALIAS = 'default'
   ```
   With Redis cache backend for better performance

2. **Separate Session Cache**: Use Redis specifically for sessions while keeping database cache for other data

## 📊 Monitoring Session Health

Monitor these metrics:
- Session table size (`django_session` table)
- Average session duration
- Session-related errors in logs
- Authentication failure rates

## 🔧 Troubleshooting

If users report being logged out unexpectedly:

1. Check if all pods have the same SECRET_KEY
2. Verify database connectivity from all pods
3. Check session cookie settings in browser dev tools
4. Look for session-related errors in application logs
5. Verify CSRF token issues aren't being mistaken for session issues

The configuration is now properly set up for multi-pod deployment with persistent sessions! 