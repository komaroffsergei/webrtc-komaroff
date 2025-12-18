import uuid
from datetime import datetime, timezone

def now():
    return datetime.now(tz=timezone.utc).isoformat()

def new_uuid():
    return str(uuid.uuid4())


def db_insert(table: str, record: dict):
    DB_STORE[table].append(record)


def create_session(user_id: str):
    session_id = new_uuid()
    db_insert("sessions", {
        "session_id": session_id,
        "user_id": user_id,
        "status": "RUNNING",
        "created_at": now(),
        "updated_at": now(),
    })
    return session_id


def finish_session(session_id: str, status: str):
    for s in DB_STORE["sessions"]:
        if s["session_id"] == session_id:
            s["status"] = status
            s["updated_at"] = now()
            return


def create_intent(session_id: str, user_id: str, intent_type: str):
    intent_id = new_uuid()
    db_insert("intents", {
        "intent_id": intent_id,
        "session_id": session_id,
        "intent_type": intent_type,
        "user_id": user_id,
        "status": "RUNNING",
        "created_at": now(),
    })
    return intent_id


def finish_intent(intent_id: str, status: str):
    for i in DB_STORE["intents"]:
        if i["intent_id"] == intent_id:
            i["status"] = status
            return


def log_event(
    session_id: str,
    intent_id: str,
    seq: int,
    role: str,
    event_type: str,
    name: str | None,
    input_data,
    output_data,
):
    db_insert("events", {
        "event_id": len(DB_STORE["events"]) + 1,
        "session_id": session_id,
        "intent_id": intent_id,
        "seq": seq,
        "role": role,
        "event_type": event_type,
        "name": name,
        "input": input_data,
        "output": output_data,
        "created_at": now(),
    })

def log_artifact(
    session_id: str,
    intent_id: str,
    artifact_type: str,
    name: str,
    data,
):
    db_insert("artifacts", {
        "artifact_id": new_uuid(),
        "session_id": session_id,
        "intent_id": intent_id,
        "type": artifact_type,
        "name": name,
        "data": data,
        "created_at": now(),
    })


DB_STORE = {
    "sessions": [],
    "intents": [],
    "artifacts": [],
    "events": [],
}
