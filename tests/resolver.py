import re
from dataclasses import dataclass

from aiodns import DNSResolver


@dataclass
class DNSResult:
    cname: str
    type: str = 'CNAME'
    ttl: int = -1


class TestDNSResolver(DNSResolver):
    def __init__(self, dummy_server, nameservers=('1.1.1.1', '1.0.0.1'), loop=None, **kwargs):
        self._dummy_server = dummy_server
        super().__init__(nameservers, loop, **kwargs)

    async def query(self, host: str, qtype: str):
        if (host, qtype) == ('em2-platform.example.org', 'CNAME'):
            origin = re.sub('^http://', '', self._dummy_server.server_name)
            # including prt and path here are a big corruption of dns, but helpful in tests
            return DNSResult(origin)
        else:
            return await super().query(host, qtype)
