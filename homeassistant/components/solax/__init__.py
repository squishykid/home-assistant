"""The solax component."""
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.solax.const import DOMAIN, DEFAULT_PORT
from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_IP_ADDRESS): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistantType, config: ConfigType) -> bool:
    """
    Setup Solax from YAML
    """
    if DOMAIN not in config:
        return True

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context=dict(source=SOURCE_IMPORT), data=dict(config[DOMAIN])
        )
    )
    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """
    Setup Solax from config entry
    """
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, SENSOR_DOMAIN)
    )
    return True
