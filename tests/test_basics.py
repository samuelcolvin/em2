async def test_ui_index(cli, url):
    r = await cli.get(url('ui:index'))
    text = await r.text()
    assert r.status == 200, text
    assert 'em2 user interface\n' in text
    assert '  /auth-token/ - auth-token\n' in text
