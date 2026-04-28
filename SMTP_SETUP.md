# SMTP Configuration for Email Sending

To enable email functionality for sending trip itineraries, configure these environment variables:

TripBreeze currently sends mail with `smtplib.SMTP` and optional `STARTTLS`. In practice that means port `587` with `SMTP_USE_TLS=true` is the supported path. Implicit SSL on port `465` is not currently supported by the app.

## Configuration Variables

```bash
# SMTP Server Settings
SMTP_HOST=smtp.gmail.com          # Your SMTP server hostname
SMTP_PORT=587                     # SMTP port (usually 587 for TLS, 465 for SSL)
SMTP_SENDER_EMAIL=your-email@gmail.com   # Email address to send from
SMTP_SENDER_PASSWORD=your-app-password   # Email password or app-specific password
SMTP_USE_TLS=true                 # Use TLS for connection (true/false)
```

## Common SMTP Providers

### Gmail
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SENDER_EMAIL=your-email@gmail.com
SMTP_SENDER_PASSWORD=<app-specific-password>
SMTP_USE_TLS=true
```
**Note:** Use [Google App Passwords](https://support.google.com/accounts/answer/185833) instead of your main password.

### Outlook/Office 365
```
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_SENDER_EMAIL=your-email@outlook.com
SMTP_SENDER_PASSWORD=your-password
SMTP_USE_TLS=true
```

### SendGrid (using their SMTP relay)
```
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_SENDER_EMAIL=apikey
SMTP_SENDER_PASSWORD=<your-sendgrid-api-key>
SMTP_USE_TLS=true
```

### Custom Company SMTP Server
```
SMTP_HOST=mail.yourcompany.com
SMTP_PORT=587
SMTP_SENDER_EMAIL=noreply@yourcompany.com
SMTP_SENDER_PASSWORD=your-password
SMTP_USE_TLS=true
```

## Adding to .env File

Add these variables to your `.env` file in the project root:

```
# Email Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SENDER_EMAIL=your-email@gmail.com
SMTP_SENDER_PASSWORD=your-app-password
SMTP_USE_TLS=true
```

## Troubleshooting

- **Authentication Failed**: Double-check your email and password. For Gmail, ensure you're using an [app-specific password](https://support.google.com/accounts/answer/185833).
- **Connection Refused**: Verify the SMTP host and port are correct.
- **TLS Issues**: Prefer port `587` with `SMTP_USE_TLS=true`. Port `465` uses implicit SSL and does not match the app's current SMTP client setup.
- **Gmail App Password Formatting**: If Google shows the app password with spaces, paste it into `.env` without spaces.
- **Check Logs**: Enable `LOG_LEVEL=DEBUG` to see detailed SMTP connection logs.
