import Dexie from 'dexie'

const db = new Dexie('em2')
db.version(1).stores({
  sessions: '&session_id, email',
  conversations: '&key, new_key, created_ts, updated_ts, publish_ts',
  actions: '[conv+id], [conv+act], conv, ts',
})

export async function get_session (session_id) {
  if (session_id) {
    const session = await db.sessions.get(session_id)
    if (session) {
      return session
    }
  }
  return await db.sessions.toCollection().first()
}

export function other_sessions (session_id) {
  return db.sessions.where('session_id').notEqual(session_id).toArray()
}
export default db
