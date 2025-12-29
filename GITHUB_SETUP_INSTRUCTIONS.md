# GitHub Repository Setup Instructions

## Quick Setup Steps

### Step 1: Create Repository on GitHub

1. Go to: **https://github.com/new**
2. Repository name: `crypto-ml-training-standalone`
3. Description (optional): "Crypto ML Training Standalone - Vast AI Training Pipeline"
4. Visibility: Choose **Public** (or Private if you prefer)
5. **IMPORTANT:** Do NOT check any of these boxes:
   - ❌ Add a README file
   - ❌ Add .gitignore
   - ❌ Choose a license
6. Click **"Create repository"**

### Step 2: Push Your Code

After creating the repository, run this command:

```powershell
git push -u origin main
```

If you get authentication errors, you may need to:
- Use a Personal Access Token instead of password
- Or authenticate with GitHub CLI: `gh auth login`

### Step 3: Verify Configuration

The `.env` file should already have:
```
VASTAI_GITHUB_REPO=https://github.com/dhayanand-ss/crypto-ml-training-standalone.git
```

### Step 4: Restart Airflow

```powershell
docker-compose -f docker-compose.airflow.yml restart
```

## Alternative: Use GitHub CLI (if authenticated)

If you're already logged into GitHub CLI:

```powershell
gh auth login
gh repo create crypto-ml-training-standalone --public --source=. --remote=origin --push
```

## Troubleshooting

### Authentication Issues

If `git push` fails with authentication errors:

1. **Create a Personal Access Token:**
   - Go to: https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scopes: `repo` (full control)
   - Copy the token

2. **Use token as password:**
   ```powershell
   git push -u origin main
   # Username: dhayanand-ss
   # Password: <paste your token here>
   ```

### Repository Already Exists

If the repository already exists, just update the remote:

```powershell
git remote set-url origin https://github.com/dhayanand-ss/crypto-ml-training-standalone.git
git push -u origin main
```

