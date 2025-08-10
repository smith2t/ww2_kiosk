import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class AccessPointManager:
    def __init__(self, settings):
        self.settings = settings
        self.is_running = False
        
        self.ssid = settings.network.ap_ssid
        self.password = settings.network.ap_password
        self.interface = settings.network.ap_interface
        
    async def start(self):
        """Start the WiFi access point"""
        logger.info(f"Starting WiFi AP: {self.ssid}")
        
        try:
            # Configure hostapd
            await self._configure_hostapd()
            
            # Configure dnsmasq
            await self._configure_dnsmasq()
            
            # Start services
            await self._start_services()
            
            self.is_running = True
            logger.info("WiFi access point started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start access point: {e}")
            raise
            
    async def _configure_hostapd(self):
        """Configure hostapd for WiFi AP"""
        config = f"""
interface={self.interface}
driver=nl80211
ssid={self.ssid}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={self.password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
        
        config_file = Path("/tmp/hostapd.conf")
        config_file.write_text(config)
        
        logger.debug(f"Hostapd configuration written to {config_file}")
        
    async def _configure_dnsmasq(self):
        """Configure dnsmasq for DHCP"""
        config = f"""
interface={self.interface}
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
"""
        
        config_file = Path("/tmp/dnsmasq.conf")
        config_file.write_text(config)
        
        logger.debug(f"Dnsmasq configuration written to {config_file}")
        
    async def _start_services(self):
        """Start hostapd and dnsmasq services"""
        # Configure network interface
        commands = [
            f"sudo ip link set {self.interface} up",
            f"sudo ip addr add 192.168.4.1/24 dev {self.interface}",
            "sudo systemctl stop hostapd",
            "sudo systemctl stop dnsmasq",
            "sudo hostapd /tmp/hostapd.conf -B",
            "sudo dnsmasq -C /tmp/dnsmasq.conf"
        ]
        
        for cmd in commands:
            try:
                result = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await result.communicate()
                
                if result.returncode != 0:
                    logger.warning(f"Command '{cmd}' failed: {stderr.decode()}")
                    
            except Exception as e:
                logger.error(f"Failed to execute '{cmd}': {e}")
                
    async def stop(self):
        """Stop the WiFi access point"""
        logger.info("Stopping WiFi access point")
        
        commands = [
            "sudo pkill hostapd",
            "sudo pkill dnsmasq",
            f"sudo ip addr del 192.168.4.1/24 dev {self.interface}",
            f"sudo ip link set {self.interface} down"
        ]
        
        for cmd in commands:
            try:
                await asyncio.create_subprocess_shell(cmd)
            except Exception as e:
                logger.warning(f"Error stopping AP: {e}")
                
        self.is_running = False