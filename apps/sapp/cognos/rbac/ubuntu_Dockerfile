FROM node:18-slim

# Install PM2 globally and other utilities
# sonar.issue.ignore.block
RUN npm install -g pm2 serve --ignore-scripts && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl procps && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
# sonar.issue.ignore.unblock

# Set working directory
WORKDIR /app

# Create necessary directories
RUN mkdir -p /app/core/bin \
             /app/core/etc \
             /app/core/lib \
             /app/core/logs \
             /app/core/data \
             /var/lib/bv/rbac

# Copy the entire core directory structure
COPY core/ /app/core/

# Set executable permissions for binaries
RUN chmod +x /app/core/bin/rbac-service/rbac-module 2>/dev/null || true && \
    chmod +x /app/core/lib/licensing 2>/dev/null || true

# Copy PM2 ecosystem file (for reference/manual management)
COPY ecosystem.config.js /app/

# Copy environment configuration script
COPY docker-env-setup.sh /app/
RUN chmod +x /app/docker-env-setup.sh

# Expose necessary ports (default values, can be overridden)
EXPOSE 6720 6721

# Set working directory back to /app
WORKDIR /app

# Run environment setup script which will:
# 1. Configure all settings from docker-config.env
# 2. Build frontend
# 3. Start all PM2 services (RBAC-CLIENT, RBAC-EXE, licensing)
# 4. Keep container running with PM2 in foreground
CMD ["/bin/bash", "-c", "/app/docker-env-setup.sh && exec pm2 logs"]
