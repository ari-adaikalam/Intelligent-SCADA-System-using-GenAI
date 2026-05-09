"""
Alert System Implementation
===========================
Handles email, SMS, and phone call alerts.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import time

# Import configuration
from alert_config import (
    EMAIL_CONFIG, SMS_CONFIG, CALL_CONFIG,
    ALERT_BEHAVIOR, EMAIL_TEMPLATES, SMS_TEMPLATE, CALL_SCRIPT
)

# Try to import Twilio
try:
    from twilio.rest import Client

    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    print("⚠️  Twilio not installed. SMS/Calls disabled. Install: pip install twilio")

# ============================================================================
# COOLDOWN TRACKING
# ============================================================================

_last_alert_time = {}  # Track last alert time per component
_state_started_at = {}  # key: f"{component}_{state}" -> epoch seconds

def state_persisted_long_enough(component, state):
    """
    Returns True only if the current state has been continuous long enough.
    Resets other state timers for that component automatically.
    """
    if not component or state in (None, "NORMAL", "UNKNOWN", "ERROR"):
        return False

    now = time.time()

    # Reset timers for this component for other states (prevents stale timers)
    for key in list(_state_started_at.keys()):
        if key.startswith(component + "_") and key != f"{component}_{state}":
            _state_started_at.pop(key, None)

    k = f"{component}_{state}"
    if k not in _state_started_at:
        _state_started_at[k] = now
        #print(f"🧪 {state} started: {component}")
        return False

    elapsed = now - _state_started_at[k]

    if state == "DEGRADING":
        required = ALERT_BEHAVIOR.get("degrading_persist_seconds", 60)
    elif state == "FAULTED":
        required = ALERT_BEHAVIOR.get("faulted_persist_seconds", 0)
    else:
        required = 0

    if elapsed < required:
        #print(f"🧪 Waiting persistence: {component} {state} {int(elapsed)}/{required}s")
        return False

    return True

def reset_component_timers(component):
    if not component:
        return
    for key in list(_state_started_at.keys()):
        if key.startswith(component + "_"):
            _state_started_at.pop(key, None)

def check_cooldown(component, alert_type, state):
    key = f"{component}_{state}_{alert_type}"
    current_time = time.time()

    if key in _last_alert_time:
        elapsed = current_time - _last_alert_time[key]
        if elapsed < ALERT_BEHAVIOR['cooldown_seconds']:
            #print(f"⏳ Cooldown: {component} {state} ({alert_type}) - {int(elapsed)}s ago")
            return False

    _last_alert_time[key] = current_time
    return True


# ============================================================================
# EMAIL ALERTS
# ============================================================================

def send_email_alert(prediction):
    """
    Send email alert for DEGRADING or FAULTED state.

    Args:
        prediction (dict): ML prediction result

    Returns:
        bool: True if sent successfully
    """
    if not EMAIL_CONFIG['enabled']:
        #print("📧 Email alerts disabled in config")
        return False

    state = prediction['stage2']['state']
    component = prediction['stage3']['component']
    confidence = prediction['stage3']['confidence']

    if not component:
        return False

    # Check cooldown
    if not check_cooldown(component, 'EMAIL', state):
        return False

    # Test mode: Just print
    if ALERT_BEHAVIOR['test_mode']:
        print(f"📧 [TEST MODE] Would send email: {component} - {state} ({confidence * 100:.0f}%)")
        return True

    try:
        # Create message
        msg = MIMEMultipart('alternative')

        # Subject
        subject = EMAIL_TEMPLATES['subject'].format(
            component=component,
            state=state
        )
        msg['Subject'] = subject
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = ', '.join(EMAIL_CONFIG['recipient_emails'])

        # Determine color and icon
        if state == "FAULTED":
            color = "#dc3545"
            icon = "🔴"
            alert_title = "CRITICAL FAULT DETECTED"
        else:
            color = "#ffc107"
            icon = "🟡"
            alert_title = "DEGRADATION WARNING"

        # Build top 3 list
        top3 = prediction['stage3'].get('top3', [])
        top3_html = ''.join([
            f"<li>{comp}: {conf * 100:.1f}%</li>"
            for comp, conf in top3
        ])

        # Build actions list
        actions = prediction.get('actions', [])[:5]  # Top 5 actions
        actions_html = ''.join([
            f"<li>{action}</li>"
            for action in actions
        ])

        # Format HTML body
        html = EMAIL_TEMPLATES['body_html'].format(
            color=color,
            icon=icon,
            alert_title=alert_title,
            component=component,
            state=state,
            confidence=confidence * 100,
            timestamp=prediction['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            top3_list=top3_html,
            actions_list=actions_html
        )

        msg.attach(MIMEText(html, 'html'))

        # Send email
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
            server.send_message(msg)

        print(f"✅ Email sent: {component} - {state}")
        return True

    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False


# ============================================================================
# SMS ALERTS
# ============================================================================

def send_sms_alert(prediction):
    """
    Send SMS alert for FAULTED state.

    Args:
        prediction (dict): ML prediction result

    Returns:
        bool: True if sent successfully
    """
    if not SMS_CONFIG['enabled']:
        #print("📱 SMS alerts disabled in config")
        return False

    if not TWILIO_AVAILABLE:
        print("❌ SMS failed: Twilio not installed")
        return False

    state = prediction['stage2']['state']

    if state != 'FAULTED':
        return False  # Only SMS for faults

    component = prediction['stage3']['component']
    confidence = prediction['stage3']['confidence']

    if not component:
        return False

    # Check cooldown
    if not check_cooldown(component, 'SMS', state):
        return False

    # Test mode: Just print
    if ALERT_BEHAVIOR['test_mode']:
        print(f"📱 [TEST MODE] Would send SMS: {component} - FAULTED ({confidence * 100:.0f}%)")
        return True

    try:
        client = Client(
            SMS_CONFIG['twilio_account_sid'],
            SMS_CONFIG['twilio_auth_token']
        )

        message_body = SMS_TEMPLATE.format(
            component=component,
            state=state,
            confidence=confidence * 100,
            time=prediction['timestamp'].strftime('%H:%M:%S')
        )

        for phone in SMS_CONFIG['recipient_phones']:
            message = client.messages.create(
                body=message_body,
                from_=SMS_CONFIG['twilio_phone_number'],
                to=phone
            )
            print(f"✅ SMS sent to {phone}: {message.sid}")

        return True

    except Exception as e:
        print(f"❌ SMS failed: {e}")
        return False


# ============================================================================
# PHONE CALL ALERTS
# ============================================================================

def send_phone_alert(prediction):
    """
    Send phone call for FAULTED state with high confidence.

    Args:
        prediction (dict): ML prediction result

    Returns:
        bool: True if sent successfully
    """
    if not CALL_CONFIG['enabled']:
        #print("☎️  Phone alerts disabled in config")
        return False

    if not TWILIO_AVAILABLE:
        print("❌ Call failed: Twilio not installed")
        return False

    state = prediction['stage2']['state']
    confidence = prediction['stage3']['confidence']

    if state != 'FAULTED' or confidence < CALL_CONFIG['confidence_threshold']:
        return False

    component = prediction['stage3']['component']

    if not component:
        return False

    # Check cooldown
    if not check_cooldown(component, 'CALL', state):
        return False

    # Test mode: Just print
    if ALERT_BEHAVIOR['test_mode']:
        print(f"☎️  [TEST MODE] Would call: {component} - FAULTED ({confidence * 100:.0f}%)")
        return True

    try:
        client = Client(
            CALL_CONFIG['twilio_account_sid'],
            CALL_CONFIG['twilio_auth_token']
        )

        twiml = CALL_SCRIPT.format(
            component=component,
            confidence=int(confidence * 100)
        )

        for phone in CALL_CONFIG['recipient_phones']:
            call = client.calls.create(
                twiml=twiml,
                from_=CALL_CONFIG['twilio_phone_number'],
                to=phone
            )
            print(f"✅ Call initiated to {phone}: {call.sid}")

        return True

    except Exception as e:
        print(f"❌ Call failed: {e}")
        return False


# ============================================================================
# TRIGGER ALERTS
# ============================================================================

def trigger_alerts(prediction):
    state = prediction['stage2']['state']
    component = prediction['stage3'].get('component')

    # If normal, reset timers and exit
    if state in ('NORMAL', 'UNKNOWN', 'ERROR'):
        if not component:
            _state_started_at.clear()
            # optionally also clear _last_alert_time for state keys if desired
        else:
            reset_component_timers(component)

        return {'email': False, 'sms': False, 'call': False}

    results = {'email': False, 'sms': False, 'call': False}

    # ✅ Persistence gates for both DEGRADING and FAULTED
    if state in ("DEGRADING", "FAULTED"):
        if not state_persisted_long_enough(component, state):
            return results  # don't alert yet

    # Email for DEGRADING or FAULTED
    if state in ['DEGRADING', 'FAULTED']:
        if ALERT_BEHAVIOR['alert_on_degrading'] or state == 'FAULTED':
            results['email'] = send_email_alert(prediction)

    # SMS for FAULTED only (after persistence gate)
    if state == 'FAULTED' and ALERT_BEHAVIOR['alert_on_faulted']:
        results['sms'] = send_sms_alert(prediction)

    # Phone call for FAULTED only (after persistence gate + your confidence threshold)
    if state == 'FAULTED' and ALERT_BEHAVIOR['alert_on_faulted']:
        results['call'] = send_phone_alert(prediction)

    return results


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("ALERT SYSTEM TEST")
    print("=" * 60)

    # Mock prediction
    test_prediction = {
        'timestamp': datetime.now(),
        'stage2': {
            'state': 'FAULTED',
            'confidence': 0.95
        },
        'stage3': {
            'component': 'P302',
            'confidence': 0.93,
            'top3': [
                ('P302', 0.93),
                ('P402', 0.04),
                ('P501', 0.02)
            ]
        },
        'actions': [
            '🔧 Inspect UF feed pump P302',
            '📋 Check UF membrane differential pressure',
            '💧 Consider membrane backwash or cleaning'
        ]
    }

    print("\n📧 Testing Email Alert...")
    email_result = send_email_alert(test_prediction)

    print("\n📱 Testing SMS Alert...")
    sms_result = send_sms_alert(test_prediction)

    print("\n☎️  Testing Phone Alert...")
    call_result = send_phone_alert(test_prediction)

    print("\n" + "=" * 60)
    print("RESULTS:")
    print("=" * 60)
    print(f"Email: {'✅ Sent' if email_result else '❌ Failed'}")
    print(f"SMS:   {'✅ Sent' if sms_result else '❌ Failed'}")
    print(f"Call:  {'✅ Sent' if call_result else '❌ Failed'}")