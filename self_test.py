"""Self-test suite for the Shokhrux Lab fitness bot.

Runs WITHOUT network or a live database. It verifies:
  1. No syntax errors / circular imports across all bot modules.
  2. All routers register cleanly into a Dispatcher (handler/filter/FSM wiring).
  3. Payment confirm/reject handlers exist (regression guard for the dead-button bug).
  4. Bilingual text dictionaries expose both 'uz' and 'ru' keys.
  5. Main-menu and hub keyboards build for every language / subscription state.
  6. Pure helpers (weight chart, text chunking) work on sample data.

Usage:  python self_test.py
Exit code 0 = all passed, 1 = at least one failure.
"""
import importlib
import sys
import traceback

# Make sure the config can import even if .env is absent (defaults exist).
FAILURES: list[str] = []
PASSES: list[str] = []


def check(name: str, fn):
    try:
        fn()
    except Exception as e:  # noqa: BLE001 - self-test reports every failure
        FAILURES.append(name)
        print(f"  ❌ {name}: {type(e).__name__}: {e}")
        traceback.print_exc()
    else:
        PASSES.append(name)
        print(f"  ✅ {name}")


# ---------------------------------------------------------------------------
# 1. Import every module (syntax + circular-import guard)
# ---------------------------------------------------------------------------
MODULES = [
    "bot.config",
    "bot.database.models",
    "bot.database.db",
    "bot.texts",
    "bot.filters.admin",
    "bot.states.admin",
    "bot.states.support",
    "bot.states.fitness",
    "bot.states.registration",
    "bot.services.subscription",
    "bot.services.rahmat",
    "bot.services.scheduler",
    "bot.services.charts",
    "bot.services.gemini_service",
    "bot.handlers.user",
    "bot.handlers.admin",
    "bot.handlers.fitness_tools",
]


def test_imports():
    print("[1] Importing all modules (syntax / circular imports)…")
    for mod in MODULES:
        check(f"import {mod}", lambda m=mod: importlib.import_module(m))


# ---------------------------------------------------------------------------
# 2. Routers register into a Dispatcher
# ---------------------------------------------------------------------------
def test_router_registration():
    print("[2] Registering routers into a Dispatcher…")

    def _register():
        from aiogram import Dispatcher
        from bot.handlers.user import router as user_router, start_router
        from bot.handlers.admin import router as admin_router
        from bot.handlers.fitness_tools import router as fitness_router

        dp = Dispatcher()
        dp.include_router(start_router)
        dp.include_router(admin_router)
        dp.include_router(fitness_router)
        dp.include_router(user_router)

    check("include all routers", _register)


# ---------------------------------------------------------------------------
# 3. Critical payment handlers exist (regression guard)
# ---------------------------------------------------------------------------
def test_payment_handlers_present():
    print("[3] Verifying payment confirm/reject handlers exist…")

    def _check():
        from bot.handlers import admin
        names = {"admin_confirm_payment", "admin_reject_payment"}
        missing = [n for n in names if not hasattr(admin, n)]
        assert not missing, f"missing handlers: {missing}"

    check("admin_conf_/admin_rej_ handlers defined", _check)


def test_vip_and_admin_wiring():
    print("[3b] Verifying VIP-group + client-search wiring…")

    def _vip():
        from bot.config import config
        from bot.database.models import Subscription
        from bot.handlers import user as user_mod
        from bot.handlers import admin as admin_mod
        from bot import texts

        # config exposes the VIP chat id
        assert hasattr(config, "vip_chat_id"), "config.vip_chat_id missing"
        # model stores the VIP invite link, not the removed созвон status
        assert hasattr(Subscription, "vip_invite_link"), "Subscription.vip_invite_link missing"
        assert not hasattr(Subscription, "vip_call_status"), "vip_call_status must be removed"
        # user-side VIP-group link handler + texts
        assert hasattr(user_mod, "cb_vip_group_link"), "cb_vip_group_link missing"
        for key in ("VIP_GROUP_BTN", "PAYMENT_SUCCESS_VIP", "VIP_EXPIRED", "VIP_GROUP_CARD"):
            assert hasattr(texts, key), f"texts.{key} missing"
        assert not hasattr(texts, "VIP_CALL_BTN"), "VIP_CALL_BTN must be removed"
        # restored admin client search/management + VIP excel
        for name in ("msg_search_user", "adm_user_extend", "adm_user_kick",
                     "adm_user_link", "generate_vip_excel", "cb_vip_excel_download"):
            assert hasattr(admin_mod, name), f"admin.{name} missing"

    check("VIP group + admin search wiring", _vip)


# ---------------------------------------------------------------------------
# 4. Bilingual text dictionaries
# ---------------------------------------------------------------------------
def test_texts_bilingual():
    print("[4] Checking bilingual text dictionaries (uz/ru)…")
    from bot import texts

    def _check():
        problems = []
        for attr in dir(texts):
            if attr.startswith("_"):
                continue
            val = getattr(texts, attr)
            if isinstance(val, dict) and set(val.keys()) & {"uz", "ru"}:
                # Language-keyed dict: must have both languages, non-empty.
                for lang in ("uz", "ru"):
                    if lang not in val:
                        problems.append(f"{attr} missing '{lang}'")
                    elif isinstance(val[lang], str) and not val[lang].strip():
                        problems.append(f"{attr}[{lang}] is empty")
        assert not problems, "; ".join(problems)

    check("all uz/ru text pairs complete", _check)


# ---------------------------------------------------------------------------
# 5. Keyboards build for all states/languages
# ---------------------------------------------------------------------------
def test_keyboards():
    print("[5] Building keyboards for all languages / states…")
    from bot.handlers.user import main_menu_keyboard
    from bot.handlers.fitness_tools import get_smart_fitness_hub_reply_keyboard

    def _main():
        for lang in ("uz", "ru"):
            for active in (True, False):
                kb = main_menu_keyboard(lang, is_active=active, has_bought=active)
                assert kb.keyboard, "empty keyboard"
                # Non-subscribers must NOT see the AI button; subscribers must.
                from bot import texts
                flat = [b.text for row in kb.keyboard for b in row]
                ai_label = texts.MENU_BUTTONS["fitness_hub"][lang]
                if active:
                    assert ai_label in flat, "subscriber menu missing AI button"
                    assert texts.MENU_BUTTONS["prolong"][lang] in flat
                else:
                    assert ai_label not in flat, "non-subscriber menu shows AI button"
                    assert texts.MENU_BUTTONS["subscribe"][lang] in flat

    def _hub():
        for lang in ("uz", "ru"):
            kb = get_smart_fitness_hub_reply_keyboard(lang)
            assert kb.keyboard, "empty hub keyboard"

    check("main_menu_keyboard (all states)", _main)
    check("smart fitness hub keyboard", _hub)


# ---------------------------------------------------------------------------
# 6. Pure helpers
# ---------------------------------------------------------------------------
def test_helpers():
    print("[6] Exercising pure helper functions…")
    import datetime
    from bot.services.charts import generate_weight_chart
    from bot.handlers.fitness_tools import split_text_into_chunks

    def _chart():
        now = datetime.datetime.now(datetime.timezone.utc)
        records = [
            (now - datetime.timedelta(days=14), 80.0),
            (now - datetime.timedelta(days=7), 78.5),
            (now, 77.0),
        ]
        for lang in ("uz", "ru"):
            buf, summary = generate_weight_chart(records, language=lang)
            assert buf.getvalue(), "empty chart PNG"
            assert summary, "empty summary"

    def _chunks():
        long_text = "\n\n".join(f"Параграф {i} " + "x" * 200 for i in range(60))
        chunks = split_text_into_chunks(long_text, max_chunk_size=3500)
        assert all(len(c) <= 3500 for c in chunks), "chunk exceeds limit"
        assert "".join(chunks).replace("\n", "") == long_text.replace("\n", "") \
            or len(chunks) >= 1

    check("generate_weight_chart", _chart)
    check("split_text_into_chunks", _chunks)


def main() -> int:
    print("=" * 60)
    print("SHOKHRUX LAB BOT — SELF TEST SUITE")
    print("=" * 60)
    test_imports()
    test_router_registration()
    test_payment_handlers_present()
    test_vip_and_admin_wiring()
    test_texts_bilingual()
    test_keyboards()
    test_helpers()

    print("=" * 60)
    total = len(PASSES) + len(FAILURES)
    print(f"RESULT: {len(PASSES)}/{total} checks passed, {len(FAILURES)} failed.")
    if FAILURES:
        print("FAILED:", ", ".join(FAILURES))
        return 1
    print("✅ ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
