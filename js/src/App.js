import React from 'react'
import {Route, Switch, withRouter} from 'react-router-dom'
import {GlobalContext, Error, NotFound, Notify} from 'reactstrap-toolbox'

import {statuses} from './utils/network'
import Worker from './run_worker'
import Navbar from './common/Navbar'
import WithMenu from './common/LeftMenu'
import Login from './auth/Login'
import Logout from './auth/Logout'
import SwitchSession from './auth/SwitchSession'
import ListConversations from './conversations/List'
import ConversationDetails from './conversations/Details'
import CreateConversation from './conversations/Create'
import './fa'


const Main = ({app_state}) => {
  if (app_state.error) {
    return <Error error={app_state.error}/>
  } else if (!app_state.conn_status) {
    // this should happen very briefly, don't show loading to avoid FOUC
    return null
  } else if (app_state.conn_status === statuses.offline && !app_state.user) {
    return (
      <div className="text-center">
        No internet connection and no local data, so sadly nothing much to show you. :-(
      </div>
    )
  } else {
    return (
      <Switch>
        <Route exact path="/" render={WithMenu(ListConversations, 'all')}/>
        <Route exact path="/create/" render={WithMenu(CreateConversation, 'create')}/>
        <Route exact path="/login/" component={Login}/>
        <Route exact path="/logout/" component={Logout}/>
        <Route exact path="/switch/:id(\d+)/" component={SwitchSession}/>
        <Route path="/:key([a-f0-9]{10,64})/" render={WithMenu(ConversationDetails, 'all')}/>
        <Route component={NotFound}/>
      </Switch>
    )
  }
}

class App extends React.Component {
  state = {
    title: null,
    error: null,
    user: null,
    other_sessions: [],
    conn_status: null,
  }

  constructor (props) {
    super(props)
    this.worker = new Worker(this)
    this.notify = new Notify(this.props.history)
    this.worker.add_listener('notify', this.notify.notify)
    this.worker.add_listener('notify-request', this.notify.request)
  }

  componentDidMount () {
    this.worker.add_listener('setState', s => this.setState(s))
    this.worker.add_listener('setUser', u => this.setUser(u))
    this.worker.call('start', JSON.parse(sessionStorage['session_id'] || 'null'))
  }

  componentDidUpdate (prevProps) {
    document.title = this.state.title ? this.state.title : 'em2'
    if (this.props.location !== prevProps.location) {
      this.state.error && this.setState({error: null})
    }
    if (!this.state.user && this.state.conn_status && this.props.location.pathname !== '/login/') {
      this.props.history.push('/login/')
    }
  }

  setUser = user => {
    this.setState({user})
    sessionStorage['session_id'] = JSON.stringify(user ? user.session_id : null)
  }

  componentDidCatch (error, info) {
    // Raven.captureException(error, {extra: info})
    this.setState({error: error.toString()})
  }

  setError = error => {
    if (error.status === 401 && this.props.location.pathname !== '/login/') {
      this.props.history.push('/login/')
    } else {
      console.warn('setting error:', error)
      // Raven.captureMessage(`caught error: ${error.message || error.toString()}`, {
      //   stacktrace: true, level: 'warning', extra: error
      // })
      this.setState({error})
    }
  }

  render () {
    const ctx = {
      setError: error => this.setError(error),
      setTitle: title => this.setState({title}),
      user: this.state.user,
      worker: this.worker,
    }
    return (
      <GlobalContext.Provider value={ctx}>
        <Navbar app_state={this.state} location={this.props.location}/>
        <main className="container" id="main">
          <Main app_state={this.state}/>
        </main>
      </GlobalContext.Provider>
    )
  }
}

export default withRouter(App)
