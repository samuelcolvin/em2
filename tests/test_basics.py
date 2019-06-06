import pytest

from em2.main import create_app
from em2.utils.web import MakeUrl


async def test_ui_index(cli, url):
    r = await cli.get(url('ui:index'))
    text = await r.text()
    assert r.status == 200, text
    assert 'em2 user interface\n' in text
    assert '  /auth/token/ - auth-token\n' in text


def test_make_url_localhost(cli):
    mu = MakeUrl(cli.server.app)
    assert str(mu.get_path('ui:online')) == '/ui/online/'
    assert mu.get_url('ui:online') == 'http://localhost:8000/ui/online/'
    assert str(mu.get_path('auth:update-session')) == '/auth/session/update/'
    assert mu.get_url('auth:update-session') == 'http://localhost:8000/auth/session/update/'


async def test_make_url_other(settings):
    settings2 = settings.copy()
    settings2.domain = 'example.com'
    app = await create_app(settings=settings)

    mu = MakeUrl(app)
    assert str(mu.get_path('ui:online')) == '/online/'
    assert mu.get_url('ui:online') == 'https://ui.example.com/online/'
    assert str(mu.get_path('auth:update-session')) == '/session/update/'
    assert mu.get_url('auth:update-session') == 'https://auth.example.com/session/update/'


async def test_make_url_errors(settings):
    settings2 = settings.copy()
    settings2.domain = 'example.com'
    app = await create_app(settings=settings)

    with pytest.raises(RuntimeError) as exc_info:
        MakeUrl(app).get_path('wrong')
    assert exc_info.value.args[0] == 'no app name, use format "<app name>:<route name>"'

    with pytest.raises(RuntimeError) as exc_info:
        MakeUrl(app).get_path('missing:online')
    assert exc_info.value.args[0] == 'app not found, options are : "ui", "protocol" and "auth"'

    with pytest.raises(RuntimeError) as exc_info:
        MakeUrl(app).get_path('ui:missing')
    assert exc_info.value.args[0].startswith('route "missing" not found')
