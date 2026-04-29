import json
import os
import firebase_admin
from firebase_admin import credentials, messaging

_app = None

def get_firebase_app():
    global _app
    if _app is not None:
        return _app
    
    # Leer credenciales desde variable de entorno
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
    """
    Envía notificación a una lista de tokens FCM.
    Devuelve el número de notificaciones enviadas exitosamente.
    """
    if not fcm_tokens:
        return 0

    try:
        get_firebase_app()
    except Exception as e:
        print(f"Firebase no inicializado: {e}")
        return 0

    # Configurar sonido según urgencia
    android_config = messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(
            sound="urgent" if is_urgent else "default",
            priority="max" if is_urgent else "default",
            channel_id="orders_urgent" if is_urgent else "orders_normal",
        ),
    )

    apns_config = messaging.APNSConfig(
        payload=messaging.APNSPayload(
            aps=messaging.Aps(
                sound="urgent.caf" if is_urgent else "default",
                badge=1,
            )
        )
    )

    messages = [
        messaging.Message(
            token=token,
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            android=android_config,
            apns=apns_config,
        )
        for token in fcm_tokens
    ]

    try:
        batch_response = messaging.send_each(messages)
        return batch_response.success_count
    except Exception as e:
        print(f"Error enviando notificaciones: {e}")
        return 0