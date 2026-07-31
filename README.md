# Instagram Telegram Bot

## Deploy
1. Push to GitHub.
2. Create a Render Web Service.
3. Add BOT_TOKEN and WEBHOOK_SECRET environment variables.
4. Deploy.
5. Set webhook:
https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://YOUR-RENDER-URL/webhook/WEBHOOK_SECRET
