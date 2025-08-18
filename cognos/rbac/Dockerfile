# Dockerfile
FROM node:18-slim

# Install PM2 globally
RUN npm install -g pm2

# Set working directory
WORKDIR /app

# Install dependencies
COPY rbac-client-repo/package*.json ./rbac-client-repo/
RUN cd rbac-client-repo && npm install

# Copy application code
COPY rbac-client-repo ./rbac-client-repo/
COPY rbac-service ./rbac-service/

RUN chmod +x /app/rbac-service/rbac-module
# Copy PM2 ecosystem file
COPY ecosystem.config.js .

# Build client
RUN cd rbac-client-repo && npm run build

# Expose necessary ports
EXPOSE 6720 6721

# Start PM2 and keep container running
CMD ["sh", "-c", "pm2 start ecosystem.config.js && pm2 save && pm2 logs"]