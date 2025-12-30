# GCP Credentials - Embedded JSON Method

This method allows you to embed GCP credentials directly as an environment variable, avoiding file path issues.

## Quick Setup

### Option 1: Use the PowerShell Script (Easiest)

```powershell
.\set_gcp_credentials_embedded.ps1
```

This script will:
1. Read your `dhaya123-335710-039eabaad669.json` file
2. Set the `GCP_CREDENTIALS_JSON` environment variable with the full JSON content
3. Set `GCP_PROJECT_ID` environment variable

### Option 2: Manual Setup

**PowerShell:**
```powershell
$jsonContent = Get-Content dhaya123-335710-039eabaad669.json -Raw
$env:GCP_CREDENTIALS_JSON = $jsonContent
$env:GCP_PROJECT_ID = "dhaya123-335710"
```

**Linux/Mac:**
```bash
export GCP_CREDENTIALS_JSON="$(cat dhaya123-335710-039eabaad669.json)"
export GCP_PROJECT_ID="dhaya123-335710"
```

### Option 3: In docker-compose.airflow.yml

Add the JSON content directly (replace `{...}` with your actual JSON):

```yaml
environment:
  GCP_CREDENTIALS_JSON: '{"type":"service_account","project_id":"dhaya123-335710",...}'
  GCP_PROJECT_ID: dhaya123-335710
```

**Note:** Make sure to properly escape quotes in YAML. You can use single quotes around the JSON string.

## How It Works

1. **Priority 1:** If `GCP_CREDENTIALS_JSON` is set, GCSManager uses it directly (no file needed)
2. **Priority 2:** If not set, falls back to file-based approach using `GOOGLE_APPLICATION_CREDENTIALS` or `GCP_CREDENTIALS_PATH`

## Advantages

✅ **No file path issues** - Works regardless of working directory  
✅ **No relative path problems** - Absolute paths not required  
✅ **Docker-friendly** - No need to mount credential files  
✅ **Simpler deployment** - Just set environment variable  

## Security Note

⚠️ **Important:** While this avoids file path issues, be careful:
- Don't commit credentials to version control
- Use secrets management in production (e.g., Docker secrets, Kubernetes secrets)
- Rotate credentials regularly

## Verification

After setting the environment variable, test it:

```python
import os
print("GCP_CREDENTIALS_JSON is set:", bool(os.getenv("GCP_CREDENTIALS_JSON")))
```

The GCSManager will automatically detect and use embedded credentials when available.

