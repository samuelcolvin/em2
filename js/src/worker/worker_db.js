import Dexie from 'dexie'

const session_db = new Dexie('em2_session')
session_db.version(1).stores({
  sessions: '&session_id, email',
})

class Session {
  constructor () {
    this.current = null
    this.id = null
    this.db = null
  }

  _set_session = session => {
    this.current = session
    if (this.current) {
      this.id = this.current.session_id
      this.db = new Dexie('em2-' + this.current.email)
      this.db.version(1).stores({
        conversations: '&key, new_key, created_ts, updated_ts, publish_ts',
        actions: '[conv+id], [conv+act], conv, ts',
      })
    } else {
      this.id = null
      this.db = null
    }
  }

  set = async session_id => {
    if (session_id) {
      const session = await session_db.sessions.get(session_id)
      if (session) {
        this._set_session(session)
        return
      }
    }
    this._set_session(await session_db.sessions.toCollection().first())
  }

  add = async session => {
    await session_db.sessions.add(session)
    this._set_session(session)
  }

  delete = async () => {
    await session_db.sessions.where({session_id: this.id}).delete()
    await this.db.delete()
    await this.set()
  }

  update = async changes => {
    Object.assign(this.current, changes)
    await session_db.sessions.update(this.id, changes)
  }

  other_sessions = () => session_db.sessions.where('session_id').notEqual(this.id || -1).toArray()
  all_emails = () => session_db.sessions.orderBy('email').keys()
}
export const session = new Session()
