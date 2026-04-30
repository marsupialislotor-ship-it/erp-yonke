import json
import os
import firebase_admin
from firebase_admin import credentials, messaging

_app = None

def get_firebase_app():
    global _app
    if _app is not None:
        return _app
    creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if not creds_json:
        raise RuntimeError("FIREBASE_CREDENTIALS_JSON no configurado")
    creds_dict = json.loads(creds_json)
    cred = credentials.Certificate(creds_dict)
    _app = firebase_admin.initialize_app(cred)
    return _app


async def send_notification(
    fcm_tokens: list[str],
    title: str,
    body: str,
    data: dict | None = None,
    is_urgent: bool = False,
) -> int:
    if not fcm_tokens:
        return 0
    try:
        get_firebase_app()
    except Exception as e:
        print(f"Firebase no inicializado: {e}")
        return 0

    android_config = messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(
            sound="urgent" if is_urgent else "default",
            priority="max" if is_urgent else "default",
            channel_id="orders_urgent" if is_urgent else "orders_normal",
        ),
    )

    messages = [
        messaging.Message(
            token=token,
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            android=android_config,
        )
        for token in fcm_tokens
    ]

    try:
        batch_response = messaging.send_each(messages)
        print(f"Notificaciones: {batch_response.success_count} exitosas, {batch_response.failure_count} fallidas")
        return batch_response.success_count
    except Exception as e:
        print(f"Error enviando notificaciones FCM: {e}")
        return 0