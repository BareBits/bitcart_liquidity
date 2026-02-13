from typing import List,Dict,Set,Optional,Iterable,Literal
import smtplib,traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import ssl
import logging
logger = logging.getLogger(__name__)
class NotificationProvider:
    """
    Base class for a Notification Provider
    """

    def __init__(self, name: str):
        """
        Initialize the Notification Provider
        """
        self.name = name
    async def notify(self, body:str,subject:Optional[str]) -> bool:
        """
        Send a notification, return True if successful, false otherwise
        """
        return False
class EmailNotificationProvider(NotificationProvider):
    def __init__(self,name:str,from_name:str,from_email:str,username:str,password:str,smtp_server:str,smtp_port:int,ssl_enabled:bool,tls_enabled:bool,to_email:str):
        self.name=name
        self.from_name=from_name
        self.from_email=from_email
        self.username=username
        self.password=password
        self.smtp_server=smtp_server
        self.smtp_port=smtp_port
        self.ssl_enabled=ssl_enabled
        self.tls_enabled=tls_enabled
        self.to_email=to_email
    def test_connection(self)->bool:
        smtp_host=self.smtp_server
        smtp_port=self.smtp_port
        timeout=30
        if self.ssl_enabled == 'ssl':
            # Use SMTP_SSL for implicit SSL/TLS
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout, context=context)
        else:
            # Use regular SMTP for no security or STARTTLS
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=timeout)

            if self.tls_enabled:
                # Upgrade connection to TLS
                context = ssl.create_default_context()
                server.starttls(context=context)

        # Authenticate if credentials provided
        if self.username and self.password:
            server.login(self.username, self.password)
        return True

    def send_email(
            self,
            subject: str,
            body: str,
            dest_email: Optional[str]=None,
            from_email: Optional[str]=None,
            from_name: Optional[str]=None,
            smtp_host: Optional[str]=None,
            smtp_port: Optional[int]=None,
            username: Optional[str] = None,
            password: Optional[str] = None,
            security: Optional[Literal['none', 'ssl', 'starttls']] = 'starttls',
            timeout: int = 30,
            body_type: Literal['plain', 'html'] = 'plain'
    ) -> bool:
        """
        Send an email via SMTP.

        Args:
            dest_email: Recipient email address
            from_email: Sender email address
            subject: Email subject line
            body: Email body content
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            username: SMTP authentication username (optional)
            password: SMTP authentication password (optional)
            security: Security protocol - 'none', 'ssl', or 'starttls'
            timeout: Connection timeout in seconds
            body_type: Email body format - 'plain' or 'html'

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not from_email:
            from_email=self.from_email
        if not from_name:
            from_name=self.from_name
        if not dest_email:
            dest_email=self.to_email
        if not smtp_host:
            smtp_host=self.smtp_server
        if not smtp_port:
            smtp_port=self.smtp_port
        if not username:
            username=self.username
        if not password:
            password=self.password
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = f"{from_name} <{from_email}>"
            msg['To'] = dest_email
            msg['Subject'] = subject

            # Attach body
            msg.attach(MIMEText(body, body_type))

            # Initialize SMTP connection based on security type
            if security == 'ssl':
                # Use SMTP_SSL for implicit SSL/TLS
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout, context=context)
            else:
                # Use regular SMTP for no security or STARTTLS
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=timeout)

                if security == 'starttls':
                    # Upgrade connection to TLS
                    context = ssl.create_default_context()
                    server.starttls(context=context)

            # Authenticate if credentials provided
            if username and password:
                server.login(username, password)

            # Send email
            server.send_message(msg)
            server.quit()

            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"Authentication failed: {e}")
            return False

        except smtplib.SMTPConnectError as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            return False

        except smtplib.SMTPServerDisconnected as e:
            logger.error(f"Server disconnected unexpectedly: {e}")
            return False

        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"Recipient address refused: {e}")
            return False

        except smtplib.SMTPSenderRefused as e:
            logger.error(f"Sender address refused: {e}")
            return False

        except smtplib.SMTPDataError as e:
            logger.error(f"SMTP data error: {e}")
            return False

        except smtplib.SMTPHeloError as e:
            logger.error(f"SMTP HELO error: {e}")
            return False

        except smtplib.SMTPNotSupportedError as e:
            logger.error(f"SMTP command not supported: {e}")
            return False

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error occurred: {e}")
            return False

        except ssl.SSLError as e:
            logger.error(f"SSL/TLS error: {e}")
            return False

        except TimeoutError as e:
            logger.error(f"Connection timed out: {e}")
            return False

        except OSError as e:
            logger.error(f"Network error: {e}")
            return False

        except Exception as e:
            logger.error(f"Unexpected error: {e} ")
            traceback.print_exc()
            return False
    def notify(self,
               subject: str,
               body: str,
               ):
        self.send_email(subject=subject,body=body)