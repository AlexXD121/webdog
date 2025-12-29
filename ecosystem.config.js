module.exports = {
    apps: [{
        name: "webdog-pro",
        script: "./webdog_bot/main.py",
        interpreter: "python3",
        watch: false,
        autorestart: true,
        restart_delay: 5000,
        env: {
            PYTHONUNBUFFERED: "1"
        }
    }]
}
