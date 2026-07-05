"""Юнит-тесты чистого ядра складского учёта (allocate_fifo + валидации).

Без I/O и БД: только Decimal-математика FIFO-аллокации, округление сумм
(ROUND_HALF_UP до 0.01) и входные валидации.
"""

from decimal import Decimal

import pytest

from uk_management_bot.services.material_service import (
    Allocation,
    BatchView,
    InsufficientStockError,
    MaterialValidationError,
    allocate_fifo,
    money,
    parse_price,
    parse_qty,
    validate_unit,
)


def _batch(id_: int, remaining: str, price: str) -> BatchView:
    return BatchView(id=id_, qty_remaining=Decimal(remaining), unit_price=Decimal(price))


class TestAllocateFifo:
    def test_single_batch_partial(self):
        allocs = allocate_fifo([_batch(1, "10", "100.00")], Decimal("4"))
        assert allocs == [
            Allocation(receipt_id=1, qty=Decimal("4"),
                       unit_price=Decimal("100.00"), amount=Decimal("400.00"))
        ]

    def test_multiple_batches_fifo_order(self):
        """Первая партия съедается целиком, вторая — частично."""
        allocs = allocate_fifo(
            [_batch(1, "3", "100.00"), _batch(2, "10", "150.00")], Decimal("5")
        )
        assert [(a.receipt_id, a.qty, a.amount) for a in allocs] == [
            (1, Decimal("3"), Decimal("300.00")),
            (2, Decimal("2"), Decimal("300.00")),
        ]

    def test_exactly_to_zero(self):
        allocs = allocate_fifo(
            [_batch(1, "2", "50.00"), _batch(2, "3", "60.00")], Decimal("5")
        )
        assert sum(a.qty for a in allocs) == Decimal("5")
        assert [a.qty for a in allocs] == [Decimal("2"), Decimal("3")]

    def test_insufficient_raises_with_available(self):
        with pytest.raises(InsufficientStockError) as exc:
            allocate_fifo(
                [_batch(1, "2", "50.00"), _batch(2, "1.5", "60.00")], Decimal("5")
            )
        assert exc.value.available == Decimal("3.5")

    def test_empty_batches_insufficient(self):
        with pytest.raises(InsufficientStockError) as exc:
            allocate_fifo([], Decimal("1"))
        assert exc.value.available == Decimal("0")

    def test_zero_remaining_batches_skipped(self):
        allocs = allocate_fifo(
            [_batch(1, "0", "10.00"), _batch(2, "5", "20.00")], Decimal("2")
        )
        assert [a.receipt_id for a in allocs] == [2]

    def test_rounding_half_up_per_line(self):
        # 0.25 * 10.50 = 2.625 → HALF_UP → 2.63
        allocs = allocate_fifo([_batch(1, "1", "10.50")], Decimal("0.25"))
        assert allocs[0].amount == Decimal("2.63")

    def test_fractional_qty_across_batches(self):
        allocs = allocate_fifo(
            [_batch(1, "0.4", "33.33"), _batch(2, "1", "33.34")], Decimal("0.7")
        )
        assert [(a.qty, a.amount) for a in allocs] == [
            (Decimal("0.4"), Decimal("13.33")),   # 0.4*33.33=13.332 → 13.33
            (Decimal("0.3"), Decimal("10.00")),   # 0.3*33.34=10.002 → 10.00
        ]


class TestMoney:
    def test_half_up(self):
        assert money(Decimal("2.625")) == Decimal("2.63")
        assert money(Decimal("2.624")) == Decimal("2.62")

    def test_already_rounded(self):
        assert money(Decimal("5")) == Decimal("5.00")


class TestValidations:
    def test_parse_qty_ok(self):
        assert parse_qty("1.5") == Decimal("1.5")
        assert parse_qty(3) == Decimal("3")

    @pytest.mark.parametrize("bad", ["0", "-1", "abc", None, "1.2345"])
    def test_parse_qty_rejects(self, bad):
        with pytest.raises(MaterialValidationError):
            parse_qty(bad)

    def test_parse_price_ok(self):
        assert parse_price("10.5") == Decimal("10.50")
        assert parse_price(0) == Decimal("0.00")

    @pytest.mark.parametrize("bad", ["-0.01", "xx", None])
    def test_parse_price_rejects(self, bad):
        with pytest.raises(MaterialValidationError):
            parse_price(bad)

    def test_validate_unit(self):
        assert validate_unit("pcs") == "pcs"
        with pytest.raises(MaterialValidationError):
            validate_unit("шт")
