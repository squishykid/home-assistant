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

ATTR_PV1_CURRENT = 'PV1 Current'
ATTR_PV2_CURRENT = 'PV2 Current'
ATTR_PV1_VOLTAGE = 'PV1 Voltage'
ATTR_PV2_VOLTAGE = 'PV2 Voltage'
ATTR_PV1_POWER = 'PV1 Input Power'
ATTR_PV1_POWER = 'PV1 Input Power'
ATTR_OUTPUT_CURRENT = 'Output Current'
ATTR_NETWORK_VOLTAGE = 'Network Voltage'
ATTR_POWER_NOW = 'Power Now'
ATTR_EXPORTED_POWER = 'Exported Power'
ATTR_EXPORTED_ENERGY = 'Exported energy'
ATTR_GRID_CONSUMPTION = 'Grid Consumption'
ATTR_FREQ_AC = 'FAC1'
ATTR_TODAY_ENERGY = 'Today\'s Energy'
ATTR_TOTAL_ENERGY = 'Total Energy'
ATTR_EPS_VOLTAGE = 'EPS Voltage'
ATTR_EPS_CURRENT = 'EPS Current'
ATTR_EPS_POWER = 'EPS Power'
ATTR_EPS_FREQUENCY = 'EPS Frequency'
ATTR_BMS_LOST = 'BMS Lost'

INVERTER_SENSORS = {
    ATTR_PV1_CURRENT: 'A',
    ATTR_PV2_CURRENT: 'A',
    ATTR_PV1_VOLTAGE: 'V',
    ATTR_PV2_VOLTAGE: 'V',
    ATTR_PV1_POWER: 'W',
    ATTR_PV1_POWER: 'W',
    ATTR_OUTPUT_CURRENT: 'A',
    ATTR_NETWORK_VOLTAGE: 'V',
    ATTR_POWER_NOW: 'W',
    ATTR_EXPORTED_POWER: 'W',
    ATTR_EXPORTED_ENERGY: 'kWh',
    ATTR_GRID_CONSUMPTION: 'kWh',
    ATTR_FREQ_AC: 'Hz',
    ATTR_TODAY_ENERGY: 'kWh',
    ATTR_TOTAL_ENERGY: 'kWh',
    ATTR_EPS_VOLTAGE: 'V',
    ATTR_EPS_CURRENT: 'A',
    ATTR_EPS_POWER: 'W',
    ATTR_EPS_FREQUENCY: 'Hz',
    ATTR_BMS_LOST: None,
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_ID): cv.string,
    vol.Required(CONF_TOKEN): cv.string,
})

SCAN_INTERVAL = timedelta(seconds=30)
REQUEST_TIMEOUT = 5

INVERTER_ENDPOINT = 'https://www.solax-portal.com/api/v1/site/InverterList/{solax_id}?token={token}'

SOLAX_BATTERY_DATA = vol.Schema({
    vol.Required('key'): cv.string,
    vol.Required('name'): cv.string,
    vol.Required('value'): vol.Coerce(float),
    vol.Required('unit'): cv.string,
})

SOLAX_BATTERY_SCHEMA = vol.Schema({
    vol.Required('dataDict'): [SOLAX_BATTERY_DATA],
}, extra=vol.REMOVE_EXTRA)

INVERTER_SCHEMA = vol.Schema({
    vol.Required('data'): [SOLAX_BATTERY_SCHEMA],
}, extra=vol.REMOVE_EXTRA)

class SolaxRequestError(Exception):
    """Error to indicate a Solax API request has failed."""
    pass


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup the sensor platform."""
    endpoint = BatteryEndpoint(hass, config.get(CONF_ID), config.get(CONF_TOKEN))
    hass.async_add_job(endpoint.async_refresh)
    async_track_time_interval(hass, endpoint.async_refresh, SCAN_INTERVAL)
    devices = []
    for x in INVERTER_SENSORS:
        devices.append(Inverter(x))
    endpoint.sensors = devices
    async_add_entities(devices)


async def async_solax_dashboard_request(hass, schema, solax_id, token, retry, wait_time=0):
    if wait_time > 0:
        _LOGGER.warn("Timeout connecting to Solax, waiting %d to retry.", wait_time)
        asyncio.sleep(wait_time)
    new_wait = (wait_time*2)+5
    retry = retry - 1
    try:
        session = async_get_clientsession(hass)

        with async_timeout.timeout(REQUEST_TIMEOUT, loop=hass.loop):
            req = await session.get(INVERTER_ENDPOINT.format(solax_id=solax_id, token=token))
        
        json_response = await req.json()
        return schema(json_response)
    except (asyncio.TimeoutError):
        if retry > 0:
            return await async_solax_dashboard_request(hass, schema, solax_id, token, retry, new_wait)
        _LOGGER.error("Too many timeouts connecting to Solax.")
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
    dataDict = json['data'][0]['dataDict']
    result = {}
    for e in dataDict:
        test = INVERTER_SENSORS.get(e['name'], 1)
        if test == 1:
            continue
        result[e['name']] = e['value']
    return result


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
            json = await async_solax_dashboard_request(self.hass, INVERTER_SCHEMA, self.solax_id, self.token, 3)
            self.data = parse_solax_battery_response(json)
            self.ready.set()
        except SolaxRequestError:
            if now is not None:
                self.ready.clear()
            else:
                raise PlatformNotReady
        for s in self.sensors:
            if s._key in self.data:
                s._value = self.data[s._key]
            s.async_schedule_update_ha_state()


class Inverter(Entity):
    def __init__(self, key):
        self._key = key
        self._value = None
    
    @property
    def state(self):
        return self._value

    @property
    def name(self):
        return self._key

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return INVERTER_SENSORS[self._key]
    
    @property
    def should_poll(self):
        """No polling needed."""
        return False
