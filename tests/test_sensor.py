"""Tests for Yahoo Finance component."""
import copy
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from homeassistant.const import CONF_SCAN_INTERVAL
import pytest

from custom_components.yahoofinance import (
    DEFAULT_SCAN_INTERVAL,
    YahooSymbolUpdateCoordinator,
)
from custom_components.yahoofinance.const import (
    ATTR_CURRENCY_SYMBOL,
    ATTR_TRENDING,
    CONF_DECIMAL_PLACES,
    CONF_SHOW_TRENDING_ICON,
    CONF_SYMBOLS,
    CONF_TARGET_CURRENCY,
    DATA_FINANCIAL_CURRENCY,
    DATA_REGULAR_MARKET_PREVIOUS_CLOSE,
    DATA_REGULAR_MARKET_PRICE,
    DATA_SHORT_NAME,
    DEFAULT_CONF_SHOW_TRENDING_ICON,
    DEFAULT_CURRENCY,
    DEFAULT_CURRENCY_SYMBOL,
    DEFAULT_DECIMAL_PLACES,
    DOMAIN,
    HASS_DATA_CONFIG,
    HASS_DATA_COORDINATOR,
    NUMERIC_DATA_KEYS,
)
from custom_components.yahoofinance.sensor import (
    YahooFinanceSensor,
    async_setup_platform,
)

DEFAULT_OPTIONAL_CONFIG = {
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_DECIMAL_PLACES: DEFAULT_DECIMAL_PLACES,
    CONF_SHOW_TRENDING_ICON: DEFAULT_CONF_SHOW_TRENDING_ICON,
}

YSUC = "custom_components.yahoofinance.YahooSymbolUpdateCoordinator"


def build_mock_symbol_data(symbol, market_price, currency="USD"):
    """Build mock data for a symbol."""
    source_data = {
        DATA_FINANCIAL_CURRENCY: currency,
        DATA_SHORT_NAME: f"Symbol {symbol}",
        DATA_REGULAR_MARKET_PRICE: market_price,
    }
    return YahooSymbolUpdateCoordinator.parse_symbol_data(source_data)


def build_mock_coordinator(hass, last_update_success, symbol, market_price):
    """Build a mock data coordinator."""
    coordinator = Mock(
        data={symbol: build_mock_symbol_data(symbol, market_price)},
        hass=hass,
        last_update_success=last_update_success,
    )

    return coordinator


def build_mock_coordinator_for_conversion(
    hass, symbol, market_price, currency, target_currency, target_market_price
):
    """Build a mock data coordinator with conversion data."""

    target_symbol = f"{currency}{target_currency}=X"
    coordinator = Mock(
        data={
            symbol: build_mock_symbol_data(symbol, market_price),
            target_symbol: build_mock_symbol_data(
                target_symbol, target_market_price, target_currency
            ),
        },
        hass=hass,
        last_update_success=True,
    )

    return coordinator


async def test_setup_platform(hass):
    """Test platform setup."""

    async_add_entities = MagicMock()
    mock_coordinator = Mock()

    config = copy.deepcopy(DEFAULT_OPTIONAL_CONFIG)
    config[CONF_SYMBOLS] = [{"symbol": "BABA"}]

    hass.data = {
        DOMAIN: {
            HASS_DATA_COORDINATOR: mock_coordinator,
            HASS_DATA_CONFIG: config,
        }
    }

    await async_setup_platform(hass, None, async_add_entities, None)
    assert async_add_entities.called


@pytest.mark.parametrize(
    "last_update_success,symbol,market_price,expected_market_price",
    [(True, "XYZ", 12, 12), (False, "^ABC", 0.1221, 0.12), (True, "BOB", 6.156, 6.16)],
)
def test_sensor_creation(
    hass, last_update_success, symbol, market_price, expected_market_price
):
    """Test sensor status based on the expected_market_price."""

    mock_coordinator = build_mock_coordinator(
        hass, last_update_success, symbol, market_price
    )

    sensor = YahooFinanceSensor(
        hass, mock_coordinator, {"symbol": symbol}, DEFAULT_OPTIONAL_CONFIG
    )

    # Accessing `available` triggers data population
    assert sensor.available is last_update_success

    # state represents the rounded market price
    assert sensor.state == expected_market_price
    assert sensor.name == f"Symbol {symbol}"

    attributes = sensor.device_state_attributes
    # Sensor would be trending up because _previous_close is 0.
    assert attributes[ATTR_TRENDING] == "up"

    # All numeric values besides DATA_REGULAR_MARKET_PRICE should be 0
    for value in NUMERIC_DATA_KEYS:
        key = value[0]
        if key != DATA_REGULAR_MARKET_PRICE:
            assert attributes[key] == 0

    # Since we did not provide any data so currency should be the default value
    assert sensor.unit_of_measurement == DEFAULT_CURRENCY
    assert attributes[ATTR_CURRENCY_SYMBOL] == DEFAULT_CURRENCY_SYMBOL

    assert sensor.should_poll is False


@pytest.mark.parametrize(
    "market_price, decimal_places, expected_market_price",
    [
        (12.12645, 2, 12.13),
        (12.12345, 1, 12.1),
        (12.12345, 0, 12),
        (12.12345, -1, 12.12345),
    ],
)
def test_sensor_decimal_placs(
    hass, market_price, decimal_places, expected_market_price
):
    """Tests numeric value rounding."""

    symbol = "XYZ"
    mock_coordinator = build_mock_coordinator(hass, True, symbol, market_price)

    config = copy.deepcopy(DEFAULT_OPTIONAL_CONFIG)
    config[CONF_DECIMAL_PLACES] = decimal_places

    sensor = YahooFinanceSensor(hass, mock_coordinator, {"symbol": symbol}, config)

    # Accessing `available` triggers data population
    assert sensor.available is True

    # state represents the rounded market price
    assert sensor.state == expected_market_price


@pytest.mark.parametrize("last_update_success,symbol,market_price", [(True, "XYZ", 12)])
def test_sensor_data_when_coordinator_is_missing_symbol_data(
    hass, last_update_success, symbol, market_price
):
    """Test sensor status when data coordinator does not have data for that symbol."""

    mock_coordinator = build_mock_coordinator(
        hass, last_update_success, symbol, market_price
    )

    # Create a sensor for some other symbol
    symbol_to_test = "ABC"
    sensor = YahooFinanceSensor(
        hass, mock_coordinator, {"symbol": symbol_to_test}, DEFAULT_OPTIONAL_CONFIG
    )

    # Accessing `available` triggers data population
    assert sensor.available is last_update_success

    assert sensor.state is None

    # Symbol is used as name when there is no data
    assert sensor.name == symbol_to_test


def test_sensor_data_when_coordinator_returns_none(hass):
    """Test sensor status when data coordinator does not have any data."""

    symbol = "XYZ"
    mock_coordinator = Mock(
        data=None,
        hass=hass,
        last_update_success=False,
    )

    sensor = YahooFinanceSensor(
        hass, mock_coordinator, {"symbol": symbol}, DEFAULT_OPTIONAL_CONFIG
    )

    # Accessing `available` triggers data population
    assert sensor.available is False

    assert sensor.state is None
    # Since we do not have data so the name will be the symbol
    assert sensor.name == symbol


async def test_sensor_update_calls_coordinator(hass):
    """Test sensor data update."""

    symbol = "XYZ"
    mock_coordinator = build_mock_coordinator(hass, True, symbol, None)
    mock_coordinator.async_request_refresh = AsyncMock(return_value=None)
    sensor = YahooFinanceSensor(
        hass, mock_coordinator, {"symbol": symbol}, DEFAULT_OPTIONAL_CONFIG
    )

    await sensor.async_update()
    assert mock_coordinator.async_request_refresh.call_count == 1


@pytest.mark.parametrize(
    "market_price,previous_close,show_trending,expected_trend",
    [
        (12, 12, False, "neutral"),
        (12, 12.1, False, "down"),
        (12, 11, False, "up"),
        (12, 12, True, "neutral"),
        (12, 12.1, True, "down"),
        (12, 11, True, "up"),
    ],
)
def test_sensor_trend(
    hass, market_price, previous_close, show_trending, expected_trend
):
    """Test sensor trending status."""

    symbol = "XYZ"
    mock_coordinator = build_mock_coordinator(hass, True, symbol, market_price)
    mock_coordinator.data[symbol][DATA_REGULAR_MARKET_PREVIOUS_CLOSE] = previous_close

    config = copy.deepcopy(DEFAULT_OPTIONAL_CONFIG)
    config[CONF_SHOW_TRENDING_ICON] = show_trending

    sensor = YahooFinanceSensor(hass, mock_coordinator, {"symbol": symbol}, config)

    # Accessing `available` triggers data population
    assert sensor.available is True

    # ATTR_TRENDING should always reflect the trending status regarding of CONF_SHOW_TRENDING_ICON
    assert sensor.device_state_attributes[ATTR_TRENDING] == expected_trend

    if show_trending:
        assert sensor.icon == f"mdi:trending-{expected_trend}"
    else:
        currency = sensor.unit_of_measurement
        lower_currency = currency.lower()
        assert sensor.icon == f"mdi:currency-{lower_currency}"


def test_sensor_trending_state_is_not_populate_if_previous_closing_missing(hass):
    """The trending state is None if _previous_close is None for some reason."""

    symbol = "XYZ"
    mock_coordinator = build_mock_coordinator(hass, True, symbol, 12)

    # Force update _previous_close to None
    mock_coordinator.data[symbol][DATA_REGULAR_MARKET_PREVIOUS_CLOSE] = None

    config = copy.deepcopy(DEFAULT_OPTIONAL_CONFIG)
    config[CONF_SHOW_TRENDING_ICON] = True

    sensor = YahooFinanceSensor(hass, mock_coordinator, {"symbol": symbol}, config)

    # Accessing `available` triggers data population
    assert sensor.available is True

    # ATTR_TRENDING should always reflect the trending status regarding of CONF_SHOW_TRENDING_ICON
    assert (ATTR_TRENDING in sensor.device_state_attributes) is False

    # icon is based on the currency
    currency = sensor.unit_of_measurement
    lower_currency = currency.lower()
    assert sensor.icon == f"mdi:currency-{lower_currency}"


async def test_data_from_json(hass, mock_json):
    """Tests data update all the way from from json."""
    symbol = "BABA"
    coordinator = YahooSymbolUpdateCoordinator([symbol], hass, DEFAULT_SCAN_INTERVAL)
    coordinator.get_json = AsyncMock(return_value=mock_json)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    sensor = YahooFinanceSensor(
        hass, coordinator, {"symbol": symbol}, DEFAULT_OPTIONAL_CONFIG
    )

    # Accessing `available` triggers data population
    assert sensor.available is True

    attributes = sensor.device_state_attributes

    assert sensor.state == 232.73
    assert attributes["regularMarketChange"] == -5.66
    assert attributes["twoHundredDayAverageChangePercent"] == -0.13


@pytest.mark.parametrize(
    "value,conversion,expected",
    [(123.5, 1, 123.5), (None, 1, None), (123.5, None, 123.5)],
)
def test_safe_convert(hass, value, conversion, expected):
    """Test value conversion."""
    assert YahooFinanceSensor.safe_convert(value, conversion) == expected


def test_conversion(hass):
    """Numeric values get multiplied based on conversion currency."""

    symbol = "XYZ"
    mock_coordinator = build_mock_coordinator_for_conversion(
        hass, symbol, 12, "USD", "CHF", 1.5
    )

    # Force update _previous_close to None
    mock_coordinator.data[symbol][DATA_REGULAR_MARKET_PREVIOUS_CLOSE] = None

    sensor = YahooFinanceSensor(
        hass,
        mock_coordinator,
        {"symbol": symbol, CONF_TARGET_CURRENCY: "CHF"},
        DEFAULT_OPTIONAL_CONFIG,
    )

    # Accessing `available` triggers data population
    assert sensor.available is True
    assert sensor.state == (12 * 1.5)


def test_conversion_requests_additional_data_from_coordinator(hass):
    """Numeric values get multiplied based on conversion currency."""

    symbol = "XYZ"
    mock_coordinator = build_mock_coordinator(hass, True, symbol, 12)

    # Force update _previous_close to None
    mock_coordinator.data[symbol][DATA_REGULAR_MARKET_PREVIOUS_CLOSE] = None

    sensor = YahooFinanceSensor(
        hass,
        mock_coordinator,
        {"symbol": symbol, CONF_TARGET_CURRENCY: "EUR"},
        DEFAULT_OPTIONAL_CONFIG,
    )

    with patch.object(mock_coordinator, "add_symbol") as mock_add_symbol:
        # Accessing `available` triggers data population
        assert sensor.available is True

        assert mock_add_symbol.call_count == 1


async def test_setup_listener_registration(hass):
    """Test entity listener registration."""
    symbol = "XYZ"
    mock_coordinator = build_mock_coordinator(hass, True, symbol, 12)

    sensor = YahooFinanceSensor(
        hass, mock_coordinator, {"symbol": symbol}, DEFAULT_OPTIONAL_CONFIG
    )

    await sensor.async_added_to_hass()
    assert mock_coordinator.async_add_listener.call_count == 1


async def test_setup_listener_unregistration(hass):
    """Test entity listener unregistration."""
    symbol = "XYZ"
    mock_coordinator = build_mock_coordinator(hass, True, symbol, 12)

    sensor = YahooFinanceSensor(
        hass, mock_coordinator, {"symbol": symbol}, DEFAULT_OPTIONAL_CONFIG
    )

    await sensor.async_will_remove_from_hass()
    assert mock_coordinator.async_remove_listener.call_count == 1
