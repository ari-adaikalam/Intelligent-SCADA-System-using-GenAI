"""
Alert System Configuration
==========================
Store all alert settings and credentials here.

SECURITY: Never commit this file to Git!
Add to .gitignore: alert_config.py
"""

# ============================================================================
# EMAIL CONFIGURATION (Gmail)
# ============================================================================

EMAIL_CONFIG = {
    'enabled': False,  # Set to False to disable email alerts

    # Gmail SMTP settings
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,

    # Your Gmail account
    'sender_email': '',  # CHANGE THIS
    'sender_password': '',  # CHANGE THIS (16-char app password)

    # Who receives alerts
    'recipient_emails': [
        'ariadaikalam1234@gmail.com',
    ]
}

# ============================================================================
# SMS CONFIGURATION (Twilio)
# ============================================================================

SMS_CONFIG = {
    'enabled': False,  # Set to False to disable SMS alerts

    # Twilio credentials (from https://console.twilio.com)
    'twilio_account_sid': '',  # CHANGE THIS
    'twilio_auth_token': '',  # CHANGE THIS
    'twilio_phone_number': '',  # CHANGE THIS

    # Who receives SMS (must be verified on free tier)
    'recipient_phones': [
        '',  # CHANGE THIS
    ]
}

# ============================================================================
# PHONE CALL CONFIGURATION (Twilio)
# ============================================================================

CALL_CONFIG = {
    'enabled': False,  # Set to False to disable phone calls

    # Twilio credentials (same as SMS)
    'twilio_account_sid': SMS_CONFIG['twilio_account_sid'],
    'twilio_auth_token': SMS_CONFIG['twilio_auth_token'],
    'twilio_phone_number': SMS_CONFIG['twilio_phone_number'],

    # Who receives calls (emergency contact only)
    'recipient_phones': [
        '+916382043877',  # CHANGE THIS
    ],

    # Only call if confidence is this high
    'confidence_threshold': 0.90  # 90%
}

# ============================================================================
# ALERT BEHAVIOR
# ============================================================================

ALERT_BEHAVIOR = {
    # Cooldown period (seconds) - prevents alert spam
    # If alert sent at 10:00:00, next alert won't send until 10:05:00
    'cooldown_seconds': 180,  # 5 minutes
    'degrading_persist_seconds': 30,
    'faulted_persist_seconds': 15,

    # Send alerts for these states
    'alert_on_degrading': True,  # Email only
    'alert_on_faulted': True,  # Email + SMS + Call (if high confidence)

    # Test mode: Print instead of actually sending
    'test_mode': False,  # Set to False for production
}

# ============================================================================
# ALERT TEMPLATES
# ============================================================================

EMAIL_TEMPLATES = {
    'subject': "⚠️ SWAT Alert: {component} - {state}",

    'body_html': """
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .header {{ background: {color}; color: white; padding: 20px; border-radius: 8px; }}
            .content {{ padding: 20px; }}
            .metric {{ margin: 10px 0; }}
            .label {{ font-weight: bold; }}
            .footer {{ margin-top: 30px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>{icon} {alert_title}</h2>
        </div>
        <div class="content">
            <div class="metric">
                <span class="label">Component:</span> {component}
            </div>
            <div class="metric">
                <span class="label">State:</span> {state}
            </div>
            <div class="metric">
                <span class="label">Confidence:</span> {confidence}%
            </div>
            <div class="metric">
                <span class="label">Timestamp:</span> {timestamp}
            </div>

            <h3>Top 3 Suspect Components:</h3>
            <ul>
                {top3_list}
            </ul>

            <h3>Recommended Actions:</h3>
            <ol>
                {actions_list}
            </ol>
        </div>
        <div class="footer">
            <em>This is an automated alert from SWAT Predictive Maintenance System</em>
        </div>
    </body>
    </html>
    """
}

SMS_TEMPLATE = """
🚨 SWAT CRITICAL FAULT 🚨

Component: {component}
State: {state}
Confidence: {confidence}%
Time: {time}

IMMEDIATE ACTION REQUIRED
Check dashboard for details.
"""

CALL_SCRIPT = """
<Response>
    <Say voice="alice">
        Critical fault detected in SWAT system.
        Component {component} has failed.
        Confidence level: {confidence} percent.
        Immediate maintenance required.
        Please check the dashboard for details.
    </Say>
    <Pause length="2"/>
    <Say voice="alice">
        Repeating: Critical fault in component {component}.
        Check the dashboard immediately.
    </Say>
</Response>
"""

# ============================================================================
# SECURITY NOTE
# ============================================================================
# Add this file to .gitignore:
# echo "alert_config.py" >> .gitignore