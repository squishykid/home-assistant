"""Config flow for the Solax"""
from homeassistant import config_entries
from homeassistant.components.solax.const import DOMAIN
from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT


@callback
def solax_entries(hass: HomeAssistant):
    """Return the site_ids for the domain."""
    return set(
        (entry.data[CONF_IP_ADDRESS], entry.data[CONF_PORT])
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


class SolaxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Solax Config Flow Handler"""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self) -> None:
        """config flow init"""
        self._errors = {}

    def _inverter_exists_already(self, ip_address, port) -> bool:
        """Does the inverter already exist in the config"""
        return (ip_address, port) in solax_entries(self.hass)

    def _check_inverter(self, ip_address, port) -> bool:
        """Is the inverter reachable with expected API"""
        pass
        # TODO implement

    async def async_step_user(self, user_input=None):
