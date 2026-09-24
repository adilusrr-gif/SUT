import httpx
from app.core.config import settings


async def status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            r.raise_for_status()
            models = [m.get("name") for m in r.json().get("models", [])]
            return {"available": True, "model": settings.ollama_model, "installed": models}
    except Exception as e:
        return {"available": False, "model": settings.ollama_model, "error": str(e)}


async def explain(payload: dict) -> str:
    prompt = f"""Ты помощник зоотехника в продукте Süt • Рацион.
Тебе запрещено менять числа, придумывать диагнозы, лечение или новый рацион.
Ты только объясняешь уже рассчитанный детерминированным LP-оптимизатором результат простым русским языком.
Максимум 120 слов. Формат строго:
Что меняем:
1. ...
2. ...
Почему: одна короткая фраза.
Расчётная экономия: ... ₸/день на корову; ... ₸/месяц на группу.
Важно: подтвердить у зоотехника перед внедрением.

Данные расчёта:
{payload}
"""
    req = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 300},
    }
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(f"{settings.ollama_url}/api/generate", json=req)
        r.raise_for_status()
        return r.json().get("response", "").strip()
