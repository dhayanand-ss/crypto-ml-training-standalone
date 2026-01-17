# PowerShell script to reset Grafana admin password
# This script resets the Grafana admin password using Grafana CLI

param(
    [string]$NewPassword = "admin123"
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Resetting Grafana Admin Password" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Get Grafana pod name
Write-Host "Finding Grafana pod..." -ForegroundColor Yellow
$GRAFANA_POD = kubectl get pods -n prometheus -l app.kubernetes.io/name=grafana -o jsonpath="{.items[0].metadata.name}" 2>$null

if (-not $GRAFANA_POD) {
    Write-Host "[ERROR] Grafana pod not found!" -ForegroundColor Red
    Write-Host "Make sure Grafana is running in the prometheus namespace." -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Found Grafana pod: $GRAFANA_POD" -ForegroundColor Green
Write-Host ""

# Method 1: Reset password using Grafana CLI
Write-Host "Resetting admin password to: $NewPassword" -ForegroundColor Yellow
Write-Host ""

# Execute grafana-cli admin reset-admin-password command
Write-Host "Executing password reset..." -ForegroundColor Yellow
$RESULT = kubectl exec -n prometheus $GRAFANA_POD -c grafana -- grafana-cli admin reset-admin-password $NewPassword 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Password reset successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "New Credentials:" -ForegroundColor Cyan
    Write-Host "  Username: admin" -ForegroundColor White
    Write-Host "  Password: $NewPassword" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "[WARNING] CLI reset failed. Trying alternative method..." -ForegroundColor Yellow
    Write-Host ""
    
    # Method 2: Use SQLite database directly (if using SQLite)
    Write-Host "Attempting to reset via database..." -ForegroundColor Yellow
    
    # Check if using SQLite
    $DB_TYPE = kubectl exec -n prometheus $GRAFANA_POD -c grafana -- env | Select-String "GF_DATABASE_TYPE"
    
    if ($DB_TYPE -match "sqlite") {
        Write-Host "Using SQLite database reset method..." -ForegroundColor Yellow
        
        # Generate password hash (bcrypt)
        # For simplicity, we'll use a known hash for "admin123"
        # In production, you'd want to generate this properly
        
        Write-Host "[INFO] To reset via database, you may need to:" -ForegroundColor Yellow
        Write-Host "  1. Access the Grafana pod shell" -ForegroundColor White
        Write-Host "  2. Navigate to /var/lib/grafana/grafana.db" -ForegroundColor White
        Write-Host "  3. Update the user table" -ForegroundColor White
        Write-Host ""
        Write-Host "Alternatively, delete the persistent volume to start fresh:" -ForegroundColor Yellow
        Write-Host "  kubectl delete pvc -n prometheus -l app.kubernetes.io/name=grafana" -ForegroundColor White
        Write-Host "  kubectl rollout restart deployment prometheus-grafana -n prometheus" -ForegroundColor White
        Write-Host ""
    }
    
    # Method 3: Update secret and delete PVC
    Write-Host "Recommended: Reset by updating secret and restarting..." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Option A - Update secret with new password:" -ForegroundColor Yellow
    Write-Host "  kubectl create secret generic prometheus-grafana `" -ForegroundColor White
    Write-Host "    --from-literal=admin-password=`"$NewPassword`" `" -ForegroundColor White
    Write-Host "    -n prometheus `" -ForegroundColor White
    Write-Host "    --dry-run=client -o yaml | kubectl apply -f -" -ForegroundColor White
    Write-Host ""
    Write-Host "Option B - Delete PVC to start fresh (WARNING: Loses all dashboards/data):" -ForegroundColor Yellow
    Write-Host "  kubectl delete pvc -n prometheus -l app.kubernetes.io/name=grafana" -ForegroundColor White
    Write-Host "  kubectl rollout restart deployment prometheus-grafana -n prometheus" -ForegroundColor White
    Write-Host ""
}

Write-Host "============================================================" -ForegroundColor Green
Write-Host "Next Steps:" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "1. Port forward Grafana:" -ForegroundColor Yellow
Write-Host "   kubectl port-forward svc/prometheus-grafana -n prometheus 3000:80" -ForegroundColor White
Write-Host ""
Write-Host "2. Open browser: http://localhost:3000" -ForegroundColor White
Write-Host ""
Write-Host "3. Login with:" -ForegroundColor Yellow
Write-Host "   Username: admin" -ForegroundColor White
Write-Host "   Password: $NewPassword" -ForegroundColor White
Write-Host ""










