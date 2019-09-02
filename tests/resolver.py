import logging
import re
from dataclasses import dataclass

from aiodns import DNSResolver
from atoolbox.test_utils import DummyServer

logger = logging.getLogger('resolver')


@dataclass
class DNSResult:
    cname: str
    type: str = 'CNAME'
    ttl: int = -1


class TestDNSResolver(DNSResolver):
    def __init__(self, dummy_server: DummyServer, nameservers=('1.1.1.1', '1.0.0.1'), loop=None, **kwargs):
        self._dummy_server = dummy_server
        self.main_server = None
        self.alt_server = None
        super().__init__(nameservers, loop, **kwargs)

    async def query(self, host: str, qtype: str):
        if (host, qtype) == ('em2-platform.em2-ext.example.com', 'CNAME'):
            # including port is a big corruption of dns, but helpful in tests
            domain = re.sub('^http://', '', self._dummy_server.server_name)
        elif (host, qtype) == ('em2-platform.local.example.com', 'CNAME'):
            if not self.main_server:
                raise RuntimeError('server not set on TestDNSResolver with request to em2-platform.local.example.com')
            domain = f'localhost:{self.main_server.port}/auth'
        elif (host, qtype) == ('em2-platform.alt.example.com', 'CNAME'):
            if not self.alt_server:
                raise RuntimeError('alt_server not set on TestDNSResolver with request to em2-platform.alt.example.com')
            domain = f'localhost:{self.alt_server.port}/auth'
        elif (host, qtype) == ('em2-platform.error.com', 'CNAME'):
            domain = 'localhost:4999'
        else:
            r = await super().query(host, qtype)
            logger.info('query %r %s -> %s', host, qtype, r)
            return r

        logger.info('query %s %r -> %s', qtype, host, domain)
        return DNSResult(domain)
