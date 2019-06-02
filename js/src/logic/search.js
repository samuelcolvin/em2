import debounce from 'debounce-async'

export default class Contacts {
  constructor (main) {
    this._main = main
    this._debounce_search = debounce(this._raw_search, 300)
    this.min_length = 4
  }

  search = async query => {
    if (query.length <= this.min_length) {
      return
    }
    const cached_search = await this._search_table().get(query)
    if (cached_search && cached_search.live) {
      return cached_search.convs
    }
    const online = await this._main.online()
    if (online) {
      try {
        return await this._debounce_search(query)
      } catch (e) {
        if (e !== 'canceled') {
          throw e
        }
      }
    }
    return null
  }

  recent_searches = async query => {
    let q = this._search_table()
    if (query) {
      q = q.where('query').startsWith(query).filter(s => s.visible)
    } else {
      q = q.where({visible: 1})
    }
    q = await q.reverse().sortBy('ts')
    return q.slice(0, 5).map(s => s.query)
  }

  mark_visible = async query => {
    await this._search_table().update(query, {visible: 1})
  }

  _raw_search = async query => {
    const r = await this._main.requests.get('ui', `/${this._main.session.id}/search/`, {query})
    const convs = r.data.conversations
    await this._search_table().put({
      query,
      visible: 0,
      live: 1,
      ts: (new Date()).getTime(),
      convs,
    })
    return convs
  }

  _search_table = () => this._main.session.db.search
}
