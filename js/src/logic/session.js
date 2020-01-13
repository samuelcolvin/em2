import Dexie from 'dexie'

const session_db = new Dexie('em2_session')
session_db.version(1).stores({
  sessions: [
    '&session_id',
    'email',
    'user_id',
  ].join(','),
})

export default class Session {
  constructor (main) {
    this._main = main
    this.current = null
    this.id = null
    this.db = null
  }

  init = async () => {
    let session_id = JSON.parse(sessionStorage['session_id'] || 'null')
    if (!session_id) {
      const s = await session_db.sessions.toCollection().first()
      session_id = s && s.session_id
    }
    if (session_id) {
      await this._set(session_id)
    }
  }

  new = async session => {
    await session_db.sessions.add(session)
    await this._set(session.session_id)
  }

  finish = async (delete_db = true) => {
    const id = this.id
    this.current = null
    this.id = null
    sessionStorage.removeItem('session_id')

    await session_db.sessions.where({session_id: id}).delete()
    this._main.fire('setState', {other_sessions: await this._other_sessions(), user: null})
    if (delete_db) {
      await this.db.delete()
    }
    this.db = null
  }

  expired = async () => {
    await this.finish(false)
    this._main.notify.notify({
      title: 'Session Expired',
      message: 'Session expired, please log in again.',
    })
  }

  active = async () => {
    if (!this.current) {
      return false
    } else if (await Dexie.exists(this._db_name())) {
      return true
    } else {
      // db has been closed and deleted, finish session
      this.current = null
      this.id = null
      this.db = null
      this._main.fire('setState', {other_sessions: await this._other_sessions(), user: null})
      return false
    }
  }

  update = async changes => {
    this.current = {...this.current, ...changes}
    await session_db.sessions.update(this.id, changes)
    if ('cache' in changes) {
      await this.db.search.toCollection().modify({live: 0})
    }
  }

  update_cache = async cache_key => {
    this.current.cache.add(cache_key)
    await this.update({cache: this.current.cache})
  }

  all_emails = () => session_db.sessions.orderBy('email').keys()

  switch = async session_id => {
    await this._set(session_id)
    return {email: this.current.email, name: this.current.name}
  }

  _other_sessions = () => session_db.sessions.where('session_id').notEqual(this.id || -1).sortBy('session_id')
  _db_name = () => 'em2-' + this.current.email

  _set = async session_id => {
    this.current = await session_db.sessions.get(session_id)
    if (!this.current) {
      this.current = null
      return
    }
    this.id = this.current.session_id
    this.db = new Dexie(this._db_name())
    this.db.version(1).stores({
      conversations: [
        '&key',
        'new_key',
        'created_ts',
        'updated_ts',
        'publish_ts',
        'seen',
        'inbox',
        'draft',
        'sent',
        'archive',
        'all',
        'deleted',
        'spam',
        'labels',
      ].join(','),
      contacts: [
        '&email',
        'last_updated',
      ].join(','),
      actions: [
        '[conv+id]',
        '[conv+act]',
        'id',
        'conv',
        'ts',
      ].join(','),
      labels: [
        'id',
        'ordering',
      ].join(','),
      search: [
        '&query',
        'visible',
        'live',
        'ts',
      ].join(','),
    })
    await this.db.open()
    sessionStorage['session_id'] = JSON.stringify(this.id)

    this._main.fire('setState', {other_sessions: await this._other_sessions(), user: this.current})
    await this._main.realtime.connect()
  }
}
