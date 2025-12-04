def run(params):
    """
    Сообщить об ошибке/невозможности выполнить запрос.

    Вход:
      { "reason": str }

    Выход:
      {
        "status": "error",
        "reason": str
      }
    """
    reason = str(params.get("reason", "unknown")).strip() or "unknown"
    return {
        "status": "error",
        "reason": reason,
    }
