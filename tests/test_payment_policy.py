"""The tariff invariant shared by the bot, Click and Payme."""
import pytest

from bot.services.payment_policy import (
    TARIFF_PRICES,
    PaymentValidationError,
    assert_order_matches_tariff,
)


@pytest.mark.parametrize("months,price", TARIFF_PRICES.items())
def test_full_price_gateway_order_matches_its_tariff(months, price):
    assert_order_matches_tariff(amount=price, cashback_applied=0, tariff_months=months,
                                payment_method="click")


def test_cashback_plus_amount_must_add_up_to_the_price():
    assert_order_matches_tariff(amount=400_000, cashback_applied=100_000, tariff_months=1,
                                payment_method="payme")
    assert_order_matches_tariff(amount=0, cashback_applied=500_000, tariff_months=1,
                                payment_method="cashback")
    with pytest.raises(PaymentValidationError):
        assert_order_matches_tariff(amount=400_000, cashback_applied=50_000, tariff_months=1,
                                    payment_method="payme")


@pytest.mark.parametrize("amount", [1_000, 5_000, 50_000_000, 499_999, 500_001, -500_000])
def test_amount_in_the_wrong_unit_or_edited_by_hand_is_rejected(amount):
    # 50_000_000 is the tariff in tiyin: the order table is whole UZS only.
    with pytest.raises(PaymentValidationError):
        assert_order_matches_tariff(amount=amount, cashback_applied=0, tariff_months=1,
                                    payment_method="click")


def test_unknown_tariff_and_null_cashback_are_handled():
    assert_order_matches_tariff(amount=500_000, cashback_applied=None, tariff_months=1,
                                payment_method="click")
    with pytest.raises(PaymentValidationError):
        assert_order_matches_tariff(amount=500_000, cashback_applied=0, tariff_months=2,
                                    payment_method="click")


def test_balance_only_method_cannot_carry_an_invoice():
    with pytest.raises(PaymentValidationError):
        assert_order_matches_tariff(amount=500_000, cashback_applied=0, tariff_months=1,
                                    payment_method="cashback")
