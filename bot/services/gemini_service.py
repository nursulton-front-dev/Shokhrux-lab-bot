import asyncio
import os
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types
from bot.config import config

logger = logging.getLogger(__name__)

# Google API call timeout in milliseconds (guards against hung requests).
GEMINI_TIMEOUT_MS = 60_000


def get_gemini_client() -> Optional[genai.Client]:
    api_key = os.getenv("GEMINI_API_KEY") or config.gemini_api_key
    if not api_key:
        logger.error("GEMINI_API_KEY is not set in environment or config.")
        return None
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
    )


async def _close_gemini_client(client: genai.Client) -> None:
    """Both transports belong to the request, including the unused sync one."""
    try:
        await client.aio.aclose()
    finally:
        await asyncio.to_thread(client.close)


async def _finish_client_cleanup(client: genai.Client) -> None:
    cleanup = asyncio.create_task(_close_gemini_client(client))
    try:
        await asyncio.shield(cleanup)
    except asyncio.CancelledError:
        # Do not strand the HTTP transport when polling cancels a handler.
        await cleanup
        raise


@asynccontextmanager
async def _gemini_client() -> AsyncIterator[genai.Client]:
    # Client construction loads SSL certificates from disk synchronously.
    creation = asyncio.create_task(asyncio.to_thread(get_gemini_client))
    try:
        client = await asyncio.shield(creation)
    except asyncio.CancelledError:
        client = await creation
        if client is not None:
            await _finish_client_cleanup(client)
        raise
    if client is None:
        raise ValueError("GEMINI_API_KEY is missing")
    try:
        yield client
    finally:
        await _finish_client_cleanup(client)

# The whole 2.5 family answers 404 for API keys created after its retirement, so
# it cannot serve as a fallback. Every name below was verified callable with the
# production key. gemini-3.6-flash is the congested default and returns 503
# under load, so the chain leads with a faster sibling and degrades to a lite
# model rather than failing the user's request.
PRIMARY_MODEL = "gemini-3.7-flash"
FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite"]

async def analyze_food_image(image_bytes: bytes, mime_type: str = "image/jpeg", language: str = "ru") -> Dict[str, Any]:
    lang_code = language if language in ("uz", "ru") else "ru"
    lang_name = "Uzbek (O'zbek tili)" if lang_code == "uz" else "Russian (Русский язык)"
    
    prompt = (
        f"Analyze this food image accurately.\n"
        f"1. Identify the dish name.\n"
        f"2. Estimate total portion weight in grams.\n"
        f"3. Calculate estimated total calories (kcal), protein (g), fat (g), and carbohydrates (g).\n"
        f"4. Provide a brief, practical nutritional recommendation/tip in {lang_name}.\n\n"
        f"CRITICAL REQUIREMENTS:\n"
        f"- The 'dish' string MUST BE written 100% in {lang_name}.\n"
        f"- The 'tip' string MUST BE written 100% in {lang_name}.\n"
        f"- Return ONLY valid JSON matching this exact structure without markdown backticks or commentary:\n"
        f'{{"dish": "Name of dish", "weight_g": 300, "calories": 450, "protein": 25, "fat": 12, "carbs": 50, "tip": "Recommendation..."}}'
    )

    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    models_to_try = [PRIMARY_MODEL] + FALLBACK_MODELS
    last_exception = None

    async with _gemini_client() as client:
        for model_name in models_to_try:
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=[prompt, image_part],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                raw_text = response.text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text.replace("```json", "", 1)
                if raw_text.startswith("```"):
                    raw_text = raw_text.replace("```", "", 1)
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

                data = json.loads(raw_text)
                fallback_dish = "Noma'lum taom" if lang_code == "uz" else "Неизвестное блюдо"
                fallback_tip = "Sog'lom taomlanish va me'yorga rioya qiling." if lang_code == "uz" else "Соблюдайте баланс и норму калорий."

                return {
                    "dish": str(data.get("dish", fallback_dish)),
                    "weight_g": int(data.get("weight_g", 0)),
                    "calories": int(data.get("calories", 0)),
                    "protein": float(data.get("protein", 0.0)),
                    "fat": float(data.get("fat", 0.0)),
                    "carbs": float(data.get("carbs", 0.0)),
                    "tip": str(data.get("tip", fallback_tip))
                }
            except Exception as e:
                logger.warning(f"Gemini analyze_food_image error with model {model_name}: {e}")
                last_exception = e

        raise last_exception or Exception("Failed to analyze food image with Gemini API")


async def ask_nutritionist_ai(history: List[Dict[str, str]], user_message: str, language: str = "ru", profile: Optional[Dict[str, Any]] = None) -> str:
    lang_code = language if language in ("uz", "ru") else "ru"

    goal_labels = {
        "weight_loss": {"uz": "Ozish (kaloriya defitsiti)", "ru": "Похудение (дефицит калорий)"},
        "keep_fit": {"uz": "Formani saqlash (balans)", "ru": "Поддержание формы (баланс)"},
        "muscle_gain": {"uz": "Mushak massasini oshirish (profitsit)", "ru": "Набор мышечной массы (профицит)"}
    }

    profile_context = ""
    if profile:
        g_code = profile.get('goal', 'keep_fit')
        g_text = goal_labels.get(g_code, {}).get(lang_code, g_code)
        profile_context = (
            f"\n\n📋 FOYDALANUVCHI PARAMETRLARI:\n"
            f"• Bo'yi: {profile.get('height_cm')} sm\n"
            f"• Vazni: {profile.get('weight_kg')} kg\n"
            f"• Maqsadi: {g_text}"
            if lang_code == "uz" else
            f"\n\n📋 ПАРАМЕТРЫ ПОЛЬЗОВАТЕЛЯ:\n"
            f"• Рост: {profile.get('height_cm')} см\n"
            f"• Вес: {profile.get('weight_kg')} кг\n"
            f"• Цель: {g_text}"
        )

    if lang_code == "uz":
        system_instruction = (
            "Siz Shokhrux Lab yopiq fitnes-klubining bosh murabbiyi va professional nutritsiologisiz.\n"
            "Siz mijozlarga mashg'ulotlar, to'g'ri ovqatlanish (PP), kaloriya defitsiti, vazn yo'qotish va mushak massasi yig'ish bo'yicha maslahat berasiz.\n\n"
            "QAT'IY QOIDALAR:\n"
            "1. Har doim javobingizni 100% O'ZBEK TILIDA (Lotin alifbosida), samimiy, tushunarli, ilmiy va motivatsiya beruvchi tarzda bering.\n"
            "2. Javobingizni strukturaviy, chiroyli va Telegram HTML teglaridan (<b>, <i>, <code>) o'rinli foydalanib yozing.\n"
            "3. Noto'g'ri yoki xavfli parhezlarni (masalan, och qolish) tavsiya etmang.\n"
            + profile_context
        )
    else:
        system_instruction = (
            "Вы — главный тренер и квалифицированный нутрициолог закрытого фитнес-клуба Shokhrux Lab.\n"
            "Вы консультируете участников клуба по тренировкам, ПП-рациону, дефициту калорий, снижению веса и набору массы.\n\n"
            "СТРОГИЕ ПРАВИЛА:\n"
            "1. Отвечайте ВСЕГДА строго на РУССКОМ ЯЗЫКЕ, профессионально, дружелюбно, структурированно и мотивирующе.\n"
            "2. Используйте Telegram HTML теги (<b>, <i>, <code>) для красивого форматирования текста.\n"
            "3. Никогда не рекомендуйте экстремальные голодовки или опасные диеты.\n"
            + profile_context
        )

    contents = []
    for msg in history:
        contents.append(types.Content(
            role=msg["role"],
            parts=[types.Part.from_text(text=msg["content"])]
        ))
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)]
    ))

    models_to_try = [PRIMARY_MODEL] + FALLBACK_MODELS
    last_exception = None

    async with _gemini_client() as client:
        for model_name in models_to_try:
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.7
                    )
                )
                return response.text.strip()
            except Exception as e:
                logger.warning(f"Gemini ask_nutritionist_ai error with model {model_name}: {e}")
                last_exception = e

        raise last_exception or Exception("Failed to generate response from Gemini API")


async def generate_weekly_meal_plan(
    height_cm: float,
    weight_kg: float,
    goal: str,
    language: str = "ru",
    gender: str = "M"
) -> str:
    lang_code = language if language in ("uz", "ru") else "ru"
    lang_name = "Uzbek (O'zbek tili)" if lang_code == "uz" else "Russian (Русский язык)"

    goal_map = {
        "weight_loss": "Ozish (kaloriya defitsiti) / Сброс веса (дефицит калорий)",
        "muscle_gain": "Mushak massasini oshirish / Набор массы (профицит калорий)",
        "keep_fit": "Formada qolish / Поддержание формы"
    }
    goal_str = goal_map.get(goal, goal)
    gender_str = "Male (Erkak)" if gender == "M" else "Female (Ayol)"

    if lang_code == "uz":
        prompt = (
            f"You are a top fitness nutritionist in Uzbekistan.\n"
            f"Generate a personal 7-day meal plan and weekly shopping list for a client with parameters:\n"
            f"- Jinsi: {gender_str}\n"
            f"- Bo'yi: {height_cm} cm\n"
            f"- Vazni: {weight_kg} kg\n"
            f"- Maqsadi: {goal_str}\n\n"
            f"CRITICAL INSTRUCTIONS:\n"
            f"1. Language: MUST BE 100% in Uzbek (O'zbek tili, Lotin alifbosida).\n"
            f"2. Product Choice: Use healthy, affordable local ingredients in Uzbekistan (tovuq ko'kragi, mol go'shti, baliq, tuxum, tvorog, grechka, guruch, suli, bodring, pomidor, ko'katlar, zaytun yog'i, va h.k.).\n"
            f"3. Structure:\n"
            f"   - Write for days 1 to 7 (1-kun, 2-kun... 7-kun):\n"
            f"     • 🌅 <b>Nonushta:</b> ...\n"
            f"     • ☀️ <b>Tushlik:</b> ...\n"
            f"     • 🍎 <b>Perekus (Tamaddi):</b> ...\n"
            f"     • 🌙 <b>Kechki ovqat:</b> ...\n"
            f"   - Ending section:\n"
            f"     🛒 <b>Bozorlik ro'yxati (1 hafta uchun)</b>\n"
            f"     List all products with exact required quantities in grams/kg/pieces.\n"
            f"4. Format ONLY with valid Telegram HTML tags (<b>, <i>, <code>). NEVER use markdown symbols (#, **)."
        )
    else:
        prompt = (
            f"You are a top fitness nutritionist in Uzbekistan.\n"
            f"Generate a personal 7-day meal plan and weekly shopping list for a client with parameters:\n"
            f"- Пол: {gender_str}\n"
            f"- Рост: {height_cm} см\n"
            f"- Вес: {weight_kg} кг\n"
            f"- Цель: {goal_str}\n\n"
            f"CRITICAL INSTRUCTIONS:\n"
            f"1. Language: MUST BE 100% in Russian (Русский язык).\n"
            f"2. Product Choice: Use healthy, affordable local ingredients available in Uzbekistan (куриное филе, говядина, рыба, яйца, творог, гречка, рис, овсянка, овощи, зелень, оливковое масло и т.д.).\n"
            f"3. Structure:\n"
            f"   - Write for days 1 to 7 (День 1, День 2... День 7):\n"
            f"     • 🌅 <b>Завтрак:</b> ...\n"
            f"     • ☀️ <b>Обед:</b> ...\n"
            f"     • 🍎 <b>Перекус:</b> ...\n"
            f"     • 🌙 <b>Ужин:</b> ...\n"
            f"   - Ending section:\n"
            f"     🛒 <b>Список покупок на неделю</b>\n"
            f"     List all products with exact required quantities in grams/kg/pieces.\n"
            f"4. Format ONLY with valid Telegram HTML tags (<b>, <i>, <code>). NEVER use markdown symbols (#, **)."
        )

    models_to_try = [PRIMARY_MODEL] + FALLBACK_MODELS
    last_exception = None

    async with _gemini_client() as client:
        for model_name in models_to_try:
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.7
                    )
                )
                return response.text.strip()
            except Exception as e:
                logger.warning(f"Gemini generate_weekly_meal_plan error with model {model_name}: {e}")
                last_exception = e

        raise last_exception or Exception("Failed to generate meal plan with Gemini API")
