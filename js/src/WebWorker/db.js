import Dexie from 'dexie'

const db = new Dexie('em2')
db.version(1).stores({
  sessions: '&session_id, email',
})

export default db
