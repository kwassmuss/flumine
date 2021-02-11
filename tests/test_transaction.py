import unittest
from unittest import mock
from unittest.mock import call

from flumine.execution.transaction import Transaction, OrderPackageType, ControlError


class TransactionTest(unittest.TestCase):
    def setUp(self) -> None:
        mock_blotter = {}
        self.mock_market = mock.Mock(blotter=mock_blotter)
        self.transaction = Transaction(self.mock_market)

    def test_init(self):
        self.assertEqual(self.transaction.market, self.mock_market)
        self.assertEqual(self.transaction._pending_place, [])
        self.assertEqual(self.transaction._pending_cancel, [])
        self.assertEqual(self.transaction._pending_update, [])
        self.assertEqual(self.transaction._pending_replace, [])

    @mock.patch(
        "flumine.execution.transaction.Transaction._validate_controls",
        return_value=True,
    )
    @mock.patch("flumine.execution.transaction.events")
    def test_place_order(self, mock_events, mock__validate_controls):
        mock_order = mock.Mock(id="123")
        mock_order.trade.market_notes = None
        self.assertTrue(self.transaction.place_order(mock_order))
        mock_order.place.assert_called_with(
            self.transaction.market.market_book.publish_time
        )
        self.transaction.market.flumine.log_control.assert_called_with(
            mock_events.TradeEvent()
        )
        mock_order.trade.update_market_notes.assert_called_with(self.mock_market)
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.PLACE)
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.PLACE)
        self.transaction._pending_place = [(mock_order, None)]

    @mock.patch(
        "flumine.execution.transaction.Transaction._validate_controls",
        return_value=True,
    )
    @mock.patch("flumine.execution.transaction.events")
    def test_place_order_not_executed(self, mock_events, mock__validate_controls):
        mock_order = mock.Mock(id="123")
        self.assertTrue(self.transaction.place_order(mock_order, execute=False))
        mock_order.place.assert_called_with(
            self.transaction.market.market_book.publish_time
        )
        self.transaction.market.flumine.log_control.assert_called_with(
            mock_events.TradeEvent()
        )
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.PLACE)
        self.transaction._pending_place = []

    @mock.patch(
        "flumine.execution.transaction.Transaction._validate_controls",
        return_value=True,
    )
    def test_place_order_retry(self, mock__validate_controls):
        mock_order = mock.Mock()
        self.transaction.market.blotter = {mock_order.id: mock_order}
        self.assertTrue(self.transaction.place_order(mock_order))
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.PLACE)
        self.transaction._pending_place = []

    @mock.patch(
        "flumine.execution.transaction.Transaction._validate_controls",
        return_value=False,
    )
    def test_place_order_violation(self, mock__validate_controls):
        mock_order = mock.Mock()
        self.assertFalse(self.transaction.place_order(mock_order))
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.PLACE)
        self.transaction._pending_place = []

    @mock.patch(
        "flumine.execution.transaction.Transaction._validate_controls",
        return_value=True,
    )
    def test_cancel_order(self, mock__validate_controls):
        mock_order = mock.Mock()
        self.assertTrue(self.transaction.cancel_order(mock_order, 0.01))
        mock_order.cancel.assert_called_with(0.01)
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.CANCEL)
        self.transaction._pending_cancel = [(mock_order,)]

    @mock.patch(
        "flumine.execution.transaction.Transaction._validate_controls",
        return_value=False,
    )
    def test_cancel_order_violation(self, mock__validate_controls):
        mock_order = mock.Mock()
        self.assertFalse(self.transaction.cancel_order(mock_order))
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.CANCEL)
        self.transaction._pending_cancel = []

    @mock.patch(
        "flumine.execution.transaction.Transaction._validate_controls",
        return_value=True,
    )
    def test_update_order(self, mock__validate_controls):
        mock_order = mock.Mock()
        self.assertTrue(self.transaction.update_order(mock_order, "PERSIST"))
        mock_order.update.assert_called_with("PERSIST")
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.UPDATE)
        self.transaction._pending_update = [(mock_order,)]

    @mock.patch(
        "flumine.execution.transaction.Transaction._validate_controls",
        return_value=False,
    )
    def test_update_order_violation(self, mock__validate_controls):
        mock_order = mock.Mock()
        self.assertFalse(self.transaction.update_order(mock_order, "test"))
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.UPDATE)
        self.transaction._pending_update = []

    @mock.patch(
        "flumine.execution.transaction.Transaction._validate_controls",
        return_value=True,
    )
    def test_replace_order(self, mock__validate_controls):
        mock_order = mock.Mock()
        self.assertTrue(self.transaction.replace_order(mock_order, 1.01, 321))
        mock_order.replace.assert_called_with(1.01)
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.REPLACE)
        self.transaction._pending_replace = [(mock_order,)]

    @mock.patch(
        "flumine.execution.transaction.Transaction._validate_controls",
        return_value=False,
    )
    def test_replace_order_violation(self, mock__validate_controls):
        mock_order = mock.Mock()
        self.assertFalse(self.transaction.replace_order(mock_order, 2.02))
        mock__validate_controls.assert_called_with(mock_order, OrderPackageType.REPLACE)
        self.transaction._pending_replace = []

    @mock.patch("flumine.execution.transaction.Transaction._create_order_package")
    def test_execute(self, mock__create_order_package):
        self.assertEqual(self.transaction.execute(), 0)
        mock_order = mock.Mock()
        self.transaction._pending_place = [(mock_order, 1234)]
        self.transaction._pending_cancel = [(mock_order,)]
        self.transaction._pending_update = [(mock_order,)]
        self.transaction._pending_replace = [(mock_order, 1234)]
        self.assertEqual(self.transaction.execute(), 4)
        mock__create_order_package.assert_has_calls(
            [
                call([], OrderPackageType.PLACE),
                call([], OrderPackageType.CANCEL),
                call([], OrderPackageType.UPDATE),
                call([], OrderPackageType.REPLACE),
            ]
        )
        self.transaction.market.flumine.process_order_package.assert_has_calls(
            [
                call(mock__create_order_package()),
                call(mock__create_order_package()),
                call(mock__create_order_package()),
                call(mock__create_order_package()),
            ]
        )

    def test__validate_controls(self):
        mock_trading_control = mock.Mock()
        mock_client_control = mock.Mock()
        self.transaction.market.flumine.trading_controls = [mock_trading_control]
        self.transaction.market.flumine.client.trading_controls = [mock_client_control]
        mock_order = mock.Mock()
        mock_package_type = mock.Mock()
        self.assertTrue(
            self.transaction._validate_controls(mock_order, mock_package_type)
        )
        mock_trading_control.assert_called_with(mock_order, mock_package_type)
        mock_client_control.assert_called_with(mock_order, mock_package_type)

    def test__validate_controls_violation(self):
        mock_trading_control = mock.Mock()
        mock_trading_control.side_effect = ControlError("test")
        mock_client_control = mock.Mock()
        self.transaction.market.flumine.trading_controls = [mock_trading_control]
        self.transaction.market.flumine.client.trading_controls = [mock_client_control]
        mock_order = mock.Mock()
        mock_package_type = mock.Mock()
        self.assertFalse(
            self.transaction._validate_controls(mock_order, mock_package_type)
        )
        mock_trading_control.assert_called_with(mock_order, mock_package_type)
        mock_client_control.assert_not_called()

    @mock.patch("flumine.execution.transaction.BetfairOrderPackage")
    def test__create_order_package(self, mock_betfair_order_package):
        package = self.transaction._create_order_package(
            [(1,), (2,)], OrderPackageType.PLACE, 123
        )
        mock_betfair_order_package.assert_called_with(
            client=self.transaction.market.flumine.client,
            market_id=self.transaction.market.market_id,
            orders=[1, 2],
            package_type=OrderPackageType.PLACE,
            bet_delay=self.transaction.market.market_book.bet_delay,
            market_version=123,
        )
        self.assertEqual(package, mock_betfair_order_package())

    @mock.patch("flumine.execution.transaction.Transaction.execute")
    def test_enter_exit(self, mock_execute):
        with self.transaction as t:
            self.assertEqual(self.transaction, t)
        mock_execute.assert_called()
