import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class SMBServer:
    def __init__(self, settings):
        self.settings = settings
        self.is_running = False
        
        self.share_name = "media"
        self.username = settings.network.smb_username
        self.password = settings.network.smb_password
        self.media_path = settings.media.base_dir
        
    async def start(self):
        """Start the SMB server"""
        logger.info("Starting SMB server")
        
        try:
            # Configure Samba
            await self._configure_samba()
            
            # Set SMB user password
            await self._set_user_password()
            
            # Start/restart Samba service
            await self._start_service()
            
            self.is_running = True
            logger.info(f"SMB server started - share: \\\\{self._get_ip()}\\{self.share_name}")
            
        except Exception as e:
            logger.error(f"Failed to start SMB server: {e}")
            raise
            
    async def _configure_samba(self):
        """Configure Samba shares"""
        config = f"""
[global]
   workgroup = WORKGROUP
   server string = WW2 Kiosk Media Server
   security = user
   map to guest = Bad User
   dns proxy = no
   
[{self.share_name}]
   comment = WW2 Kiosk Media Files
   path = {self.media_path}
   browseable = yes
   read only = no
   guest ok = no
   valid users = {self.username}
   create mask = 0755
   directory mask = 0755
"""
        
        config_file = Path("/tmp/smb.conf")
        config_file.write_text(config)
        
        # Copy to system location (requires sudo)
        try:
            cmd = "sudo cp /tmp/smb.conf /etc/samba/smb.conf"
            result = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            
        except Exception as e:
            logger.error(f"Failed to configure Samba: {e}")
            
    async def _set_user_password(self):
        """Set SMB user password"""
        try:
            # Create system user if not exists
            cmd = f"sudo useradd -M -s /sbin/nologin {self.username} 2>/dev/null || true"
            await asyncio.create_subprocess_shell(cmd)
            
            # Set SMB password
            cmd = f"echo '{self.password}\\n{self.password}' | sudo smbpasswd -a -s {self.username}"
            result = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            
            # Enable SMB user
            cmd = f"sudo smbpasswd -e {self.username}"
            await asyncio.create_subprocess_shell(cmd)
            
        except Exception as e:
            logger.error(f"Failed to set SMB user password: {e}")
            
    async def _start_service(self):
        """Start or restart Samba service"""
        try:
            cmd = "sudo systemctl restart smbd"
            result = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.communicate()
            
        except Exception as e:
            logger.error(f"Failed to start Samba service: {e}")
            
    def _get_ip(self):
        """Get the IP address for SMB access"""
        if self.settings.network.enable_ap:
            return "192.168.4.1"
        else:
            # Get system IP
            try:
                result = subprocess.run(
                    ["hostname", "-I"],
                    capture_output=True,
                    text=True
                )
                return result.stdout.strip().split()[0]
            except:
                return "localhost"
                
    async def stop(self):
        """Stop the SMB server"""
        logger.info("Stopping SMB server")
        
        try:
            cmd = "sudo systemctl stop smbd"
            await asyncio.create_subprocess_shell(cmd)
        except Exception as e:
            logger.warning(f"Error stopping SMB: {e}")
            
        self.is_running = False