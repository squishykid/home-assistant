import asyncio

from datetime import timedelta
import logging

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.const import (
        TEMP_CELSIUS,
        CONF_TOKEN, CONF_ID
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)

ATTR_VOLTAGE = 'Voltage'
ATTR_CURRENT = 'Current'
ATTR_POWER = 'Power'
ATTR_TEMPERATURE = 'Temperature'
ATTR_REMAINING_CAPACITY = 'Remaining Capacity'
BATTERY_SENSORS = [
    ATTR_VOLTAGE,
    ATTR_CURRENT,
    ATTR_POWER,
    ATTR_TEMPERATURE,
    ATTR_REMAINING_CAPACITY
]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_ID): cv.string,
    vol.Required(CONF_TOKEN): cv.string,
})

SCAN_INTERVAL = timedelta(minutes=30)
REQUEST_TIMEOUT = 5

BATTERY_ENDPOINT = 'https://www.solax-portal.com/api/v1/site/BatteryList/{solax_id}?token={token}'

SOLAX_BATTERY_DATA = vol.Schema({
    vol.Required('key'): cv.string,
    vol.Required('name'): cv.string,
    vol.Required('value'): vol.Coerce(float),
    vol.Required('unit'): cv.string,
})

SOLAX_BATTERY_SCHEMA = vol.Schema({
    vol.Required('dataDict'): [SOLAX_BATTERY_DATA],
}, extra=vol.REMOVE_EXTRA)

SOLAX_DATA_SCHEMA = vol.Schema({
    vol.Required('batList'): [SOLAX_BATTERY_SCHEMA],
}, extra=vol.REMOVE_EXTRA)

BATTERY_SCHEMA = vol.Schema({
    vol.Required('data'): [SOLAX_DATA_SCHEMA],
}, extra=vol.REMOVE_EXTRA)

class SolaxRequestError(Exception):
    """Error to indicate a Solax API request has failed."""
    pass


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup the sensor platform."""
    update_interval = timedelta(seconds=30)
    endpoint = BatteryEndpoint(hass, config.get(CONF_ID), config.get(CONF_TOKEN))
    hass.async_add_job(endpoint.async_refresh)
    async_track_time_interval(hass, endpoint.async_refresh, update_interval)
    devices = []
    for x in BATTERY_SENSORS:
        devices.append(Battery(endpoint, x))
    endpoint.sensors = devices
    async_add_entities(devices)


async def async_solax_dashboard_request(hass, schema, solax_id, token, retry, wait_time=0):
    if wait_time > 0:
        _LOGGER.warn("Waiting %d to retry Solax", wait_time)
        asyncio.sleep(wait_time)
    new_wait = (wait_time*2)+5
    retry = retry - 1
    try:
        session = async_get_clientsession(hass)

        with async_timeout.timeout(REQUEST_TIMEOUT, loop=hass.loop):
            req = await session.get(BATTERY_ENDPOINT.format(solax_id=solax_id, token=token))
        
        json_response = await req.json()
        return schema(json_response)
    except (asyncio.TimeoutError):
        _LOGGER.error("Timeout connecting to Solax API endpoint")
        if retry > 0:
            _LOGGER.warn("Retrying Solax")
            return await async_solax_dashboard_request(hass, schema, solax_id, token, retry, new_wait)
    except (aiohttp.ClientError) as clientErr:
        _LOGGER.error("Could not connect to Solax API endpoint")
        _LOGGER.error(clientErr)
    except ValueError:
        _LOGGER.error("Received non-JSON data from Solax API endpoint")
    except vol.Invalid as err:
        _LOGGER.error("Received unexpected JSON from Solax"
                      " API endpoint: %s", err)
        _LOGGER.error(json_response)
    raise SolaxRequestError

def parse_solax_battery_response(json):
    dataDict = json['data'][0]['batList'][0]['dataDict']
    def extract(key):
        return next((i for i in dataDict if i['key'] == key), dict(value=None))['value']
    volts = extract('b1_1')
    current = extract('b1_2')
    power = extract('b1_3')
    temperature = extract('b1_4')
    remaining = extract('b1_5')
    return {
        ATTR_VOLTAGE: volts,
        ATTR_CURRENT: current,
        ATTR_POWER: power,
        ATTR_TEMPERATURE: temperature,
        ATTR_REMAINING_CAPACITY: remaining
    }


class BatteryEndpoint:
    """Representation of a Sensor."""

    def __init__(self, hass, solax_id, token):
        """Initialize the sensor."""
        self.hass = hass
        self.solax_id = solax_id
        self.token = token
        self.data = {}
        self.ready = asyncio.Event()
        self.sensors = []

    async def async_refresh(self, now=None):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        try:
            json = await async_solax_dashboard_request(self.hass, BATTERY_SCHEMA, self.solax_id, self.token, 3)
            _LOGGER.info("called async_update %s", json)
            self.data = parse_solax_battery_response(json)
            self.ready.set()
        except SolaxRequestError:
            if now is not None:
                self.ready.clear()
            else:
                raise PlatformNotReady
        for s in self.sensors:
            s.async_schedule_update_ha_state(force_refresh=True)


class Battery(Entity):
    def __init__(self, endpoint, key):
        self._endpoint = endpoint
        self._key = key
        self._value = None
    
    @property
    def state(self):
        _LOGGER.warn('state')
        return self._value

    @property
    def name(self):
        return self._key

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return {
            ATTR_VOLTAGE: 'V',
            ATTR_CURRENT: 'A',
            ATTR_POWER: 'W',
            ATTR_TEMPERATURE: TEMP_CELSIUS,
            ATTR_REMAINING_CAPACITY: '%'
        }[self._key]
    
    async def async_update(self):
        """Update station state."""
        _LOGGER.warn('async_update')
        if self._endpoint.ready.is_set():
            if self._key in self._endpoint.data:
                self._value = self._endpoint.data[self._key]
