// ecosystem.config.js
module.exports = {
    apps: [
        {
            name: 'RBAC-CLIENT',
            script: 'npm',
            args: 'start',
            cwd: '/app/rbac-client-repo',
            env: {
                NODE_ENV: 'production',
                PORT: 6720
            },
            max_restarts: 5,
            restart_delay: 5000
        },
        {
            name: 'RBAC-EXE',
            script: './rbac-module',
            args: '--config rbac.yaml',
            interpreter:null,
	    exec_mode: 'fork',
            cwd: '/app/rbac-service',
            env: {
                NODE_ENV: 'production',
                PORT: 6721
            },
            max_restarts: 5,
            restart_delay: 5000
        }
    ]
};
