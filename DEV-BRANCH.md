# Dev Branch - Continuous Testing & Deployment

## Overview

The `dev` branch is used for continuous testing and deployment of new features before they reach production (`main` branch).

## Branch Structure

```
main (production)
  ↑
  │ merge when stable
  │
dev (testing/staging)
  ↑
  │ merge features
  │
feature/optimize-image-loading
feature/other-features
```

## Current State

**Branch:** `dev`
**Based on:** `feature/optimize-image-loading` (64b8803)
**Includes:**
- ✅ Device-side thumbnail generation
- ✅ Server-side thumbnail storage
- ✅ WebSocket real-time notifications
- ✅ Thumbnail serving endpoint
- 🚧 Dashboard updates (Phase 3 - TODO)

## Workflow

### 1. Developing New Features

```bash
# Start from dev branch
git checkout dev
git pull origin dev

# Create feature branch
git checkout -b feature/my-new-feature

# Make changes, commit
git add .
git commit -m "Add new feature"

# Push feature branch
git push -u origin feature/my-new-feature
```

### 2. Merging to Dev for Testing

```bash
# Switch to dev
git checkout dev

# Merge feature branch
git merge feature/my-new-feature

# Push to trigger deployment
git push origin dev
```

### 3. Testing on Dev Deployment

- Deploy `dev` branch to staging environment
- Test all features thoroughly
- Monitor logs and performance
- Fix any issues found

### 4. Promoting to Production

Once dev branch is stable and tested:

```bash
# Switch to main
git checkout main
git pull origin main

# Merge dev branch
git merge dev

# Push to production
git push origin main
```

## Deployment Targets

### Dev Branch
- **Server:** Railway (dev environment) or test server
- **Device:** Test Raspberry Pi devices
- **Purpose:** Testing new features, breaking changes OK
- **Auto-deploy:** Yes (on push to dev)

### Main Branch
- **Server:** Railway (production environment)
- **Device:** Production Raspberry Pi devices
- **Purpose:** Stable, customer-facing deployments
- **Auto-deploy:** Yes (on push to main)

## Testing Checklist for Dev

Before merging dev → main, ensure:

### Backend Tests
- [ ] All API endpoints respond correctly
- [ ] WebSocket connections work
- [ ] Thumbnail generation and serving work
- [ ] Database migrations complete successfully
- [ ] No errors in server logs

### Device Tests
- [ ] Devices can capture and upload
- [ ] Thumbnails are generated correctly
- [ ] Classification works as expected
- [ ] Auto-updates work from dev branch

### Dashboard Tests
- [ ] All pages load correctly
- [ ] Real-time updates work (WebSocket)
- [ ] Images load (thumbnails and full)
- [ ] No JavaScript errors in console
- [ ] Responsive design works on mobile

### Performance Tests
- [ ] Page load time acceptable
- [ ] Network bandwidth reduced (thumbnails)
- [ ] No memory leaks (WebSocket)
- [ ] Server CPU/RAM usage normal

## Current Dev Features

### Image Loading Optimization (Active)

**Status:** Server-side complete, dashboard pending

**What's Working:**
1. ✅ Device generates thumbnails (~90% size reduction)
2. ✅ Server stores thumbnails separately
3. ✅ WebSocket endpoint for real-time notifications
4. ✅ Thumbnail serving endpoint with caching

**What's Pending:**
1. 🚧 Dashboard WebSocket client
2. 🚧 Client-side thumbnail caching
3. 🚧 Lazy loading full images

**Testing:**
```bash
# Test thumbnail endpoint
curl http://dev-server/v1/captures/{record_id}/thumbnail

# Test WebSocket
wscat -c 'ws://dev-server/ws/captures?device_id=all'
```

See [OPTIMIZATION.md](OPTIMIZATION.md) for full details.

## Rollback Procedure

If dev branch has critical issues:

```bash
# Revert to last known good commit
git checkout dev
git reset --hard <good-commit-hash>
git push --force origin dev

# Or revert specific commit
git revert <bad-commit-hash>
git push origin dev
```

## Branch Protection Rules (Recommended)

### For `main` branch:
- Require pull request reviews
- Require status checks to pass
- No force pushes
- No deletions

### For `dev` branch:
- Allow force pushes (for testing)
- Allow direct commits
- Automatic deployment on push

## Monitoring Dev Deployment

### Server Logs
```bash
# Railway CLI
railway logs --environment dev

# Or check Railway dashboard
https://railway.app/project/{project-id}/environment/dev
```

### Device Logs
```bash
# SSH to test device
ssh mok@okmonitor.local

# Check service logs
sudo journalctl -u okmonitor-device -f
```

### Dashboard Health
```bash
# Check health endpoint
curl http://dev-server/health

# Response should be:
# {"status": "ok"}
```

## Communication

### When to Update Team

1. **Breaking changes merged to dev** → Notify team before pushing
2. **Dev deployment issues** → Report in team chat immediately
3. **Ready to merge dev → main** → Request code review
4. **Production deployment** → Announce to all stakeholders

## Feature Flags (Future Enhancement)

Consider adding feature flags to control features in dev:

```python
# .env.device or server config
ENABLE_WEBSOCKET=true
ENABLE_THUMBNAILS=true
ENABLE_CACHING=true
```

This allows testing features in dev without affecting production.

## FAQ

**Q: How often should we merge dev → main?**
A: When dev has been stable for at least 1 week and all tests pass.

**Q: Can we have multiple features in dev at once?**
A: Yes! That's the point of dev - test multiple features together.

**Q: What if a feature in dev breaks?**
A: Fix it in dev, or revert the merge. Don't merge to main until stable.

**Q: Should devices auto-update from dev branch?**
A: Only test devices. Production devices should track main branch.

**Q: How do we handle database migrations in dev?**
A: Test migrations thoroughly in dev before running on production.

---

## Current Dev Status

✅ **Branch Created:** 2025-01-22
✅ **Pushed to Remote:** origin/dev
✅ **Tracking:** origin/dev
✅ **Latest Commit:** 64b8803 (Add optimization feature documentation)

**Next Steps:**
1. Configure Railway to deploy from `dev` branch
2. Point test devices to dev server
3. Complete dashboard WebSocket implementation
4. Test optimization features end-to-end
5. Merge to main when stable

---

**Branch:** `dev`
**Purpose:** Continuous testing and deployment
**Status:** Active, includes image optimization features
