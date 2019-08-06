from .conftest import Factory


async def test_signing_verification(cli, factory: Factory):
    obj = await cli.get_json(factory.url('protocol:signing-verification'))
    assert obj == [{'key': 'd04ab232742bb4ab3a1368bd4615e4e6d0224ab71a016baf8520a332c9778737', 'ttl': 86400}]
