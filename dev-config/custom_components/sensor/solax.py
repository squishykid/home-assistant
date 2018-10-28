import asyncio

from datetime import timedelta
import logging

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.const import TEMP_CELSIUS
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA

_LOGGER = logging.getLogger(__name__)

ATTR_VOLTAGE = 'voltage'
ATTR_CURRENT = 'current'
ATTR_POWER = 'power'
ATTR_TEMPERATURE = 'temperature'
ATTR_REMAINING_CAPACITY = 'remaining_capacity'

CONF_ID = 'solax_id'
CONF_TOKEN = 'token'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_ID): cv.string,
    vol.Required(CONF_TOKEN): cv.string,
})

SCAN_INTERVAL = timedelta(seconds=30)
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
    async_add_entities([Battery(hass, config.get(CONF_ID), config.get(CONF_TOKEN))])


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


class Battery(Entity):
    """Representation of a Sensor."""

    def __init__(self, hass, solax_id, token):
        """Initialize the sensor."""
        self.hass = hass
        self.solax_id = solax_id
        self.token = token
        self._state = {}


    @property
    def name(self):
        """Return the name of the sensor."""
        return 'Example Temperature'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state.get(ATTR_REMAINING_CAPACITY, None)
    
    @property
    def device_state_attributes(self):
        return {
            ATTR_VOLTAGE: self._state.get(ATTR_VOLTAGE, None),
            ATTR_CURRENT: self._state.get(ATTR_CURRENT, None),
            ATTR_POWER: self._state.get(ATTR_POWER, None),
            ATTR_TEMPERATURE: self._state.get(ATTR_TEMPERATURE, None),
        }

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return '%'

    async def async_update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        json = await async_solax_dashboard_request(self.hass, BATTERY_SCHEMA, self.solax_id, self.token, 3)
        _LOGGER.info("called async_update %s", json)
        self._state = parse_solax_battery_response(json)