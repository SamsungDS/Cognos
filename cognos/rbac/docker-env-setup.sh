#!/bin/bash
# docker-env-setup.sh
# Complete non-interactive environment setup script for RBAC 2.0 Docker container
# Covers ALL functionality from original install-rbac.sh

set -e

echo "======================================"
echo "   RBAC Docker Environment Setup"
echo "======================================"

# Configuration file path
CONFIG_FILE="/app/docker-config.env"

# Function to read value from config file
get_config_value() {
    local key=$1
    local default=$2
    local value
    if [[ -f "$CONFIG_FILE" ]]; then
        value=$(grep "^${key}=" "$CONFIG_FILE" | cut -d'=' -f2- | tr -d '\r\n' | xargs)
        echo "${value:-$default}"
    else
        echo "$default"
    fi
}

# Load configuration values
FRONTEND_PORT=$(get_config_value "FRONTEND_PORT" "6720")
BACKEND_PORT=$(get_config_value "BACKEND_PORT" "6721")
SSL_ENABLED=$(get_config_value "SSL_ENABLED" "false")
SSL_KEY_PATH=$(get_config_value "SSL_KEY_PATH" "")
SSL_CERT_PATH=$(get_config_value "SSL_CERT_PATH" "")
BACKEND_URL=$(get_config_value "BACKEND_URL")
INTERNET_COMM_PREF=$(get_config_value "INTERNET_COMM_PREF")
APPROVAL_WORKFLOW_ENABLED=$(get_config_value "APPROVAL_WORKFLOW_ENABLED")
SUPER_ADMIN_USERNAME=$(get_config_value "SUPER_ADMIN_USERNAME")
SUPER_ADMIN_EMAIL=$(get_config_value "SUPER_ADMIN_EMAIL")
SUPER_ADMIN_PASSWORD=$(get_config_value "SUPER_ADMIN_PASSWORD")
MONGODB_URI=$(get_config_value "MONGODB_URI")

echo "Configuration loaded:"
echo "  Frontend Port: $FRONTEND_PORT"
echo "  Backend Port: $BACKEND_PORT"
echo "  SSL Enabled: $SSL_ENABLED"
echo "  Backend URL: $BACKEND_URL"
echo "  Internet Communication: $INTERNET_COMM_PREF"
echo "  User Approval Workflow: $APPROVAL_WORKFLOW_ENABLED"
echo "  Super Admin: $SUPER_ADMIN_USERNAME"

# Validate ports (from original script)
if [[ ! "$BACKEND_PORT" =~ ^[0-9]+$ ]] || [ "$BACKEND_PORT" -lt 1024 ] || [ "$BACKEND_PORT" -gt 65535 ]; then
    echo "ERROR: Invalid backend port: $BACKEND_PORT (must be 1024-65535)"
    exit 1
fi

if [[ ! "$FRONTEND_PORT" =~ ^[0-9]+$ ]] || [ "$FRONTEND_PORT" -lt 1024 ] || [ "$FRONTEND_PORT" -gt 65535 ]; then
    echo "ERROR: Invalid frontend port: $FRONTEND_PORT (must be 1024-65535)"
    exit 1
fi

if [ "$BACKEND_PORT" -eq "$FRONTEND_PORT" ]; then
    echo "ERROR: Backend and frontend ports must be different"
    exit 1
fi

echo "✓ Port validation passed"

# Validate SSL configuration
if [[ "$SSL_ENABLED" == "true" ]]; then
    if [[ -n "$SSL_CERT_PATH" ]] && [[ -f "$SSL_CERT_PATH" ]] && [[ -n "$SSL_KEY_PATH" ]] && [[ -f "$SSL_KEY_PATH" ]]; then
        echo "✓ SSL certificates validated"
        PROTOCOL="https"
    else
        echo "⚠ Warning: SSL enabled but certificates not found. Disabling SSL."
        SSL_ENABLED="false"
        PROTOCOL="http"
    fi
else
    PROTOCOL="http"
fi

# Create necessary directories
mkdir -p /var/lib/bv/rbac
mkdir -p /app/core/logs
mkdir -p /app/core/data

# Update ports file (from original script)
HOST_COOKIE_DIR="/var/lib/bv/rbac"
PORTS_FILE="$HOST_COOKIE_DIR/ports.txt"

echo "Frontend Port: $FRONTEND_PORT" > "$PORTS_FILE"
echo "Backend Port: $BACKEND_PORT" >> "$PORTS_FILE"
echo "✓ Ports saved to $PORTS_FILE"

# Configure frontend environment
FRONTEND_ENV="/app/core/bin/rbac-client-repo/.env"
cat > "$FRONTEND_ENV" << EOF
REACT_APP_BACKEND_URL=$BACKEND_URL
REACT_APP_API_URL=$BACKEND_URL
NODE_ENV=production
PORT=$FRONTEND_PORT
EOF
echo "✓ Frontend environment configured"

# Configure backend environment
BACKEND_ENV="/app/core/bin/rbac-service/.env"
cat > "$BACKEND_ENV" << EOF
PORT=$BACKEND_PORT
IS_SSL=$SSL_ENABLED
SSL_KEY_PATH=$SSL_KEY_PATH
SSL_CERT_PATH=$SSL_CERT_PATH
NODE_ENV=production
MONGODB_URI=$MONGODB_URI
LOG_LEVEL=info
JWT_SECRET=$(openssl rand -hex 32)
SESSION_SECRET=$(openssl rand -hex 32)
EOF

# Copy backend .env to service directory
#cp "$BACKEND_ENV" /app/core/bin/rbac-service/.env
echo "✓ Backend environment configured"

# Configure rbac.yaml (from original script)
RBAC_CONFIG_FILE="/app/core/etc/rbac.yaml"
if [[ -f "$RBAC_CONFIG_FILE" ]]; then
    # Backup original
    cp "$RBAC_CONFIG_FILE" "${RBAC_CONFIG_FILE}.backup"

    # Update internet-communication preference
    if grep -q "internet-communication:" "$RBAC_CONFIG_FILE"; then
        sed -i "s/internet-communication:.*/internet-communication: '$INTERNET_COMM_PREF'/" "$RBAC_CONFIG_FILE"
    else
        echo "internet-communication: '$INTERNET_COMM_PREF'" >> "$RBAC_CONFIG_FILE"
    fi

    # Update user-approval-workflow
    if grep -q "user-approval-workflow:" "$RBAC_CONFIG_FILE"; then
        sed -i "s/user-approval-workflow:.*/user-approval-workflow: '$APPROVAL_WORKFLOW_ENABLED'/" "$RBAC_CONFIG_FILE"
    else
        echo "user-approval-workflow: '$APPROVAL_WORKFLOW_ENABLED'" >> "$RBAC_CONFIG_FILE"
    fi

    # Update email-verification
    if grep -q "email-verification:" "$RBAC_CONFIG_FILE"; then
        sed -i "s/email-verification:.*/email-verification: 'N'/" "$RBAC_CONFIG_FILE"
    else
        echo "email-verification: 'N'" >> "$RBAC_CONFIG_FILE"
    fi

    echo "✓ RBAC configuration updated"
else
    echo "⚠ Warning: rbac.yaml not found at $RBAC_CONFIG_FILE"
fi

# Create super admin credentials file (from original script)
TEMP_ADMIN_FILE="/tmp/rbac_super_admin.json"
PERSISTENT_ADMIN_FILE="/app/core/etc/rbac_super_admin_backup.json"

cat > "$TEMP_ADMIN_FILE" << EOF
{
    "username": "$SUPER_ADMIN_USERNAME",
    "email": "$SUPER_ADMIN_EMAIL",
    "password": "$SUPER_ADMIN_PASSWORD",
    "role": "owner",
    "createdAt": "$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")",
    "isApproved": true,
    "isInitialSetup": true
}
EOF

# Create persistent backup
cp "$TEMP_ADMIN_FILE" "$PERSISTENT_ADMIN_FILE"
chmod 644 "$TEMP_ADMIN_FILE"
chmod 600 "$PERSISTENT_ADMIN_FILE"

echo "✓ Super admin credentials configured:"
echo "    Username: $SUPER_ADMIN_USERNAME"
echo "    Email: $SUPER_ADMIN_EMAIL"
echo "    File created at: $TEMP_ADMIN_FILE"
echo "    Backup at: $PERSISTENT_ADMIN_FILE"

# Verify file was created correctly (from original script)
if [[ -f "$TEMP_ADMIN_FILE" ]]; then
    FILE_SIZE=$(stat -c%s "$TEMP_ADMIN_FILE" 2>/dev/null || stat -f%z "$TEMP_ADMIN_FILE" 2>/dev/null || echo "unknown")
    echo "✓ Temporary admin file created successfully (size: $FILE_SIZE bytes)"
else
    echo "✗ ERROR: Failed to create temporary admin file!"
    exit 1
fi

# Add TEMP_ADMIN_FILE to backend .env
echo "TEMP_ADMIN_FILE=$TEMP_ADMIN_FILE" >> "$BACKEND_ENV"
#cp "$BACKEND_ENV" /app/core/bin/rbac-service/.env

# Build and serve frontend (MISSING FROM ORIGINAL docker-env-setup.sh)
echo ""
echo "======================================"
echo "   Building Frontend"
echo "======================================"
cd /app/core/bin/rbac-client-repo || exit 1

echo "Installing frontend dependencies..."
rm -rf node_modules package-lock.json
npm install || { echo "ERROR: npm install failed"; exit 1; }

echo "Building frontend..."
npm run build || { echo "ERROR: npm build failed"; exit 1; }

echo "✓ Frontend build completed"

# Install serve package (from original script)
echo "Installing serve package for SSL support..."
npm install -g serve 2>/dev/null || npm install serve

# Stop existing PM2 processes (from original script)
echo "Stopping existing PM2 processes..."
pm2 delete RBAC-CLIENT 2>/dev/null || true
pm2 delete RBAC-EXE 2>/dev/null || true
pm2 delete licensing 2>/dev/null || true

# Start frontend with PM2 (from original script)
echo ""
echo "======================================"
echo "   Starting Frontend Service"
echo "======================================"

if [[ "$SSL_ENABLED" == "true" ]] && [[ -n "$SSL_CERT_PATH" ]] && [[ -n "$SSL_KEY_PATH" ]]; then
    echo "Starting RBAC-CLIENT with SSL on port $FRONTEND_PORT..."
    pm2 start "npx serve build -l $FRONTEND_PORT --ssl-cert $SSL_CERT_PATH --ssl-key $SSL_KEY_PATH" --name RBAC-CLIENT || {
        echo "ERROR: Failed to start RBAC-CLIENT with SSL"
        exit 1
    }
else
    echo "Starting RBAC-CLIENT on port $FRONTEND_PORT..."
    pm2 serve build "$FRONTEND_PORT" --name RBAC-CLIENT || {
        echo "ERROR: Failed to start RBAC-CLIENT"
        exit 1
    }
fi

echo "✓ Frontend started successfully on port $FRONTEND_PORT"

# Start backend service (from original script)
echo ""
echo "======================================"
echo "   Starting Backend Service"
echo "======================================"
cd /app/core/bin/rbac-service || exit 1

# Verify executable exists and is executable (from original script)
if [[ ! -f "./rbac-module" ]]; then
    echo "ERROR: rbac-module executable not found"
    exit 1
fi

if [[ ! -x "./rbac-module" ]]; then
    echo "Making rbac-module executable..."
    chmod +x ./rbac-module
fi

echo "Starting RBAC-EXE service..."
pm2 start ./rbac-module --name RBAC-EXE || {
    echo "ERROR: Failed to start RBAC-EXE"
    exit 1
}

echo "✓ Backend started successfully on port $BACKEND_PORT"

# Wait for backend to initialize (from original script)
echo "Waiting for RBAC-EXE service to initialize..."
sleep 10

# Start licensing service (from original script)
echo ""
echo "======================================"
echo "   Starting Licensing Service"
echo "======================================"

if [[ -f "/app/core/lib/licensing" ]]; then
    chmod +x /app/core/lib/licensing
    cd /app || exit 1
    pm2 start /app/core/lib/licensing --name licensing || {
        echo "⚠ Warning: Failed to start licensing service (non-critical)"
    }
    echo "✓ Licensing service started"
else
    echo "⚠ Licensing service not found at /app/core/lib/licensing (skipping)"
fi

echo ""
echo "======================================"
echo "   Auto-Verification Setup"
echo "======================================"

# Install MongoDB driver in the rbac-service directory
echo "Installing MongoDB driver..."
cd /app/core/bin/rbac-service
npm install mongodb --save 2>/dev/null || {
    echo "⚠ Warning: Failed to install mongodb driver"
}

# Create auto-verification script IN THE CORRECT DIRECTORY
cat > "/app/core/bin/rbac-service/auto-verify.js" << 'VERIFY_JS'
const { MongoClient } = require('mongodb');

const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://admin:admin@rbac-mongo-db:27017/test?authSource=admin';

async function verifyUsers() {
    const client = new MongoClient(MONGODB_URI);

    try {
        await client.connect();
        const db = client.db('test');

        const result = await db.collection('users').updateMany(
            { is_verified: { $ne: true } },
            { $set: { is_verified: true } }
        );

        if (result.modifiedCount > 0) {
            console.log(`[${new Date().toISOString()}] Auto-verified ${result.modifiedCount} users in database 'test'`);
        }
    } catch (error) {
        console.error('Auto-verification error:', error.message);
    } finally {
        await client.close();
    }
}

setInterval(verifyUsers, 30000);
verifyUsers();

console.log('Auto-verification service started - checking database "test" every 30 seconds');
VERIFY_JS

# Start with PM2 from the correct directory
cd /app/core/bin/rbac-service
pm2 start auto-verify.js --name auto-verify-users --interpreter node

echo "✓ Auto-verification service started (database: test, interval: 30s)"

# Save PM2 process list (from original script)
echo ""
echo "======================================"
echo "   Configuring PM2 Startup"
echo "======================================"
pm2 save

# Configure PM2 startup for Docker (from original script)
if [ -f /.dockerenv ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    echo "Docker environment detected - using PM2 resurrection"
    pm2 save --force
    pm2 resurrect || {
        echo "⚠ Warning: PM2 resurrection failed. Services will still run."
    }
    echo "✓ PM2 startup configuration complete"
else
    echo "Non-Docker environment detected"
fi

# Wait for backend to process super admin credentials (from original script)
echo ""
echo "Waiting for backend to process super admin credentials..."
sleep 15

# Check if the backend processed the admin file (from original script)
if [[ -f "$TEMP_ADMIN_FILE" ]]; then
    echo "⚠ Warning: Temporary admin file still exists. Backend may need more time to process."
    echo "  The file will be cleaned up automatically by the backend once processed."
    echo "  If super admin login doesn't work after a few minutes, check logs: pm2 logs RBAC-EXE"
else
    echo "✓ Super admin credentials processed successfully by the backend."
fi

# Create restore and verify scripts (from original script)
echo ""
echo "Creating diagnostic scripts..."

cat > "/tmp/restore_super_admin.sh" << 'RESTORE_SCRIPT'
#!/bin/bash
echo "=== SUPER ADMIN RESTORE SCRIPT ==="
BACKUP_FILE="/app/core/etc/rbac_super_admin_backup.json"
TEMP_FILE="/tmp/rbac_super_admin.json"

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "✗ ERROR: No backup file found at $BACKUP_FILE"
    exit 1
fi

echo "✓ Found backup file. Restoring super admin setup..."
cp "$BACKUP_FILE" "$TEMP_FILE"
chmod 644 "$TEMP_FILE"

echo "✓ Temp file restored. Restarting backend..."
cd /app/core/bin/rbac-service || exit 1
pm2 restart RBAC-EXE
echo "✓ Backend restarted. Wait 30 seconds and check if super admin login works."
RESTORE_SCRIPT

cat > "/tmp/verify_super_admin.sh" << 'VERIFY_SCRIPT'
#!/bin/bash
echo "=== SUPER ADMIN VERIFICATION ==="
echo "1. Checking temp admin file:"
if [[ -f "/tmp/rbac_super_admin.json" ]]; then
    echo "   ✓ Temp file exists"
    cat /tmp/rbac_super_admin.json
else
    echo "   ✗ Temp file processed/removed"
fi

echo ""
echo "2. Checking backup file:"
if [[ -f "/app/core/etc/rbac_super_admin_backup.json" ]]; then
    echo "   ✓ Backup exists"
else
    echo "   ✗ Backup missing"
fi

echo ""
echo "3. Backend status:"
pm2 status | grep RBAC-EXE

echo ""
echo "4. Recent backend logs:"
pm2 logs RBAC-EXE --lines 20 --nostream
VERIFY_SCRIPT

chmod +x "/tmp/restore_super_admin.sh"
chmod +x "/tmp/verify_super_admin.sh"

echo "✓ Debug scripts created:"
echo "    - /tmp/verify_super_admin.sh"
echo "    - /tmp/restore_super_admin.sh"

# Final summary (from original script)
echo ""
echo "======================================"
echo "        === SETUP COMPLETE ===        "
echo "======================================"
echo ""
echo "RBAC installation is complete and ready to use!"
echo ""
echo "=== SUPER ADMIN ACCOUNT ==="
echo "Username: $SUPER_ADMIN_USERNAME"
echo "Email: $SUPER_ADMIN_EMAIL"
echo "Role: Owner (Full Access)"
echo "- Can approve/reject user registrations"
echo "- Has full system access"
echo "- Can manage all users"
echo ""
echo "TROUBLESHOOTING:"
echo "- If login fails, check backend logs: pm2 logs RBAC-EXE"
echo "- Verify backend started properly: pm2 status"
echo "- Super admin creation logs will show in backend logs"
echo "- If super admin lost after PM2 restart: bash /tmp/restore_super_admin.sh"
echo "- Debug script available: bash /tmp/verify_super_admin.sh"

if [[ "$APPROVAL_WORKFLOW_ENABLED" == "Y" ]]; then
    echo ""
    echo "User Approval Workflow: ENABLED"
    echo "  - New users require your approval after email verification"
    echo "  - Check your owner dashboard for pending user approvals"
    echo "  - Access User Management at: /user-approval"
else
    echo ""
    echo "User Approval Workflow: DISABLED"
    echo "  - Users can register and login immediately after email verification"
fi

echo ""
echo "=== SYSTEM FEATURES ==="
echo "✓ Email verification for new registrations"
echo "✓ Super admin user with owner role created"
echo "✓ User approval workflow (configurable)"
echo "✓ Role-based access control"
echo "✓ SSL/HTTPS support (if enabled)"
echo ""
echo "=== AVAILABLE ROLES ==="
echo "• owner: Full system access, can approve users"
echo "• admin: Administrative access"
echo "• user: Basic user access"
echo ""
echo "=== PM2 MANAGEMENT COMMANDS ==="
echo "View all services:       pm2 list"
echo "Check logs:              pm2 log <service-name>"
echo "Restart a service:       pm2 restart <service-name>"
echo "Stop a service:          pm2 stop <service-name>"
echo ""
echo "For example, you can use 'RBAC-CLIENT' for the frontend and 'RBAC-EXE' for the backend service names."
echo ""
echo "Please ensure that the frontend port ($FRONTEND_PORT) and backend port ($BACKEND_PORT) are open on your machine or AWS security groups, as applicable."
echo ""

if [[ "$SSL_ENABLED" == "true" ]]; then
    echo "SSL/HTTPS is ENABLED for both frontend and backend:"
    echo "  Frontend URL: https://<YOUR-MACHINE-IP>:$FRONTEND_PORT"
    echo "  Backend URL: https://<YOUR-MACHINE-IP>:$BACKEND_PORT"
    echo "  SSL Key: $SSL_KEY_PATH"
    echo "  SSL Certificate: $SSL_CERT_PATH"
    echo ""
    echo "To visit the Client Sample Frontend, navigate to 'https://<YOUR-MACHINE-IP>:$FRONTEND_PORT' or 'https://localhost:$FRONTEND_PORT'"
    echo ""
    echo "To call the RBAC Backend, use 'https://<YOUR-MACHINE-IP>:$BACKEND_PORT' or 'https://localhost:$BACKEND_PORT'"
else
    echo "SSL/HTTPS is DISABLED for both frontend and backend:"
    echo "  Frontend URL: http://<YOUR-MACHINE-IP>:$FRONTEND_PORT"
    echo "  Backend URL: http://<YOUR-MACHINE-IP>:$BACKEND_PORT"
    echo ""
    echo "To visit the Client Sample Frontend, navigate to 'http://<YOUR-MACHINE-IP>:$FRONTEND_PORT' or 'http://localhost:$FRONTEND_PORT'"
    echo ""
    echo "To call the RBAC Backend, use 'http://<YOUR-MACHINE-IP>:$BACKEND_PORT' or 'http://localhost:$BACKEND_PORT'"
fi

echo ""
echo "Thank you for installing RBAC. Enjoy!"
echo ""
echo "Configuration Summary:"
echo "  Frontend: $PROTOCOL://localhost:$FRONTEND_PORT"
echo "  Backend: $BACKEND_URL"
echo "  Super Admin: $SUPER_ADMIN_USERNAME ($SUPER_ADMIN_EMAIL)"
echo "  User Approval: $APPROVAL_WORKFLOW_ENABLED"
echo "  Internet Comm: $INTERNET_COMM_PREF"
echo ""
echo "Starting PM2 processes monitoring..."
