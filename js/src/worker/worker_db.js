import Dexie from 'dexie'

const db = new Dexie('em2')
db.version(1).stores({
  sessions: '&session_id, email',
  conversations: '&key, new_key, created_ts, updated_ts, publish_ts',
  actions: '[conv+id], [conv+act], conv, ts',
})

export default db

class Session {
  constructor () {
    this.current = null
    this.id = null
  }

  _set = session => {
    this.current = session
    this.id = this.current ? this.current.session_id : null
  }

  update = async session_id => {
    if (session_id) {
      const session = await db.sessions.get(session_id)
      if (session) {
        this._set(session)
        return
      }
    }
    this._set(await db.sessions.toCollection().first())
  }

  add = async session => {
    await db.sessions.add(session)
    this._set(session)
  }

  delete = async () => {
    await db.sessions.where({session_id: this.id}).delete()
    await this.update()
  }

  others = () => db.sessions.where('session_id').notEqual(this.id).toArray()
}
export const session = new Session()
