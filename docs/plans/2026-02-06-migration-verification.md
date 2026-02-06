# Migration Verification Checklist

Date: 2026-02-06
Status: In Progress

## Success Metrics

- [ ] Site updates within 20 minutes of Pi data push
  - Test: Push dummy data to gardener-site, time until live
  - Result: ___ minutes

- [ ] GitHub Actions build completes in <5 minutes
  - Check: Recent workflow runs in gardener-site repo
  - Result: ___ minutes average

- [ ] CloudFront cache invalidates successfully
  - Check: Workflow logs show invalidation success
  - Result: Pass/Fail

- [ ] No AWS credential errors in logs
  - Check: OIDC authentication works
  - Result: Pass/Fail

- [ ] Pi logs cleaned up automatically (21-day retention)
  - Check: After first successful push
  - Result: Pass/Fail

- [ ] Site accessible at https://plants.cynexia.com
  - Test: curl -I https://plants.cynexia.com
  - Result: Pass/Fail

- [ ] All historical data preserved in gardener-site repo
  - Check: gardener-site repo has data/, photos/, workspace/, logs/
  - Result: Pass/Fail

## Workflow Location Verification

- [ ] Workflow is in gardener-site repo (NOT claude-code-the-gardener)
  - Location: gardener-site/.github/workflows/deploy.yml
  - Verified: Yes/No

- [ ] Secrets are in gardener-site repo
  - Check: gh secret list -R mnbf9rca/gardener-site
  - Verified: Yes/No

- [ ] Workflow triggers on push to gardener-site/main
  - Check: workflow YAML on: push: branches: [main]
  - Verified: Yes/No

## Testing Notes

### Local Testing
- Data generator works: ___
- Astro builds successfully: ___
- JSON files are valid: ___

### CI Testing
- Both repos checkout correctly: ___
- Python dependencies install: ___
- Node dependencies install: ___
- Build artifacts correct: ___

### Pi Testing
- SSH key added to GitHub: ___
- First push successful: ___
- Timer runs on schedule: ___
- Logs are cleaned: ___

## Issues Found

(Document any issues encountered and how they were resolved)

## Sign-off

- [ ] Human Meatbag approves migration
- [ ] Site is live and functional
- [ ] Old system can be decommissioned
