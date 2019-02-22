import Dexie from 'dexie'

const db = new Dexie('em2')
db.version(1).stores({
  sessions: '&session_id, email',
  conversations: '&key, new_key, created_ts, updated_ts, publish_ts',
  actions: '[conv+id], [conv+act], conv, ts',
})

export const get_session = () => db.sessions.toCollection().first()
export default db
