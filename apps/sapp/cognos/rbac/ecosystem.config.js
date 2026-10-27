// ecosystem.config.js
// PM2 configuration for RBAC 2.0
// This file is used only as a fallback or for manual PM2 management
// The docker-env-setup.sh script handles actual service startup

module.exports = {
  apps: [
    {
      name: 'RBAC-CLIENT',
      script: 'serve',
      args: 'build -l 6720',
      cwd: '/app/core/bin/rbac-client-repo',
      interpreter: 'none',
      instances: 1,
      exec_mode: 'fork',
      env: {
        NODE_ENV: 'production',
        PORT: '6720'
      },
      max_restarts: 10,
      restart_delay: 5000,
      min_uptime: '10s',
      autorestart: true,
      watch: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      error_file: '/app/core/logs/rbac-client-error.log',
      out_file: '/app/core/logs/rbac-client-out.log',
      merge_logs: true
    },
    {
      name: 'RBAC-EXE',
      script: './rbac-module',
      interpreter: 'none',
      instances: 1,
      exec_mode: 'fork',
      cwd: '/app/core/bin/rbac-service',
      env: {
        NODE_ENV: 'production',
        PORT: '6721'
      },
      max_restarts: 10,
      restart_delay: 5000,
      min_uptime: '10s',
      autorestart: true,
      watch: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      error_file: '/app/core/logs/rbac-exe-error.log',
      out_file: '/app/core/logs/rbac-exe-out.log',
      merge_logs: true
    },
    {
      name: 'licensing',
      script: './licensing',
      interpreter: 'none',
      instances: 1,
      exec_mode: 'fork',
      cwd: '/app/core/lib',
      env: {
        NODE_ENV: 'production'
      },
      max_restarts: 10,
      restart_delay: 5000,
      min_uptime: '10s',
      autorestart: true,
      watch: false,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      error_file: '/app/core/logs/licensing-error.log',
      out_file: '/app/core/logs/licensing-out.log',
      merge_logs: true
    }
  ]
};
