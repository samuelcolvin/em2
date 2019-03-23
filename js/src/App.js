import React, {Component} from 'react'
import {Route, Switch, withRouter} from 'react-router-dom'
import {library as FaLibrary} from '@fortawesome/fontawesome-svg-core'
import {far} from '@fortawesome/free-regular-svg-icons'
import {fas} from '@fortawesome/free-solid-svg-icons'
import {fab} from '@fortawesome/free-brands-svg-icons'

import {statuses} from './lib'
import {GlobalContext} from './lib/context'
import {Error, NotFound} from './lib/Errors'
import Worker from './run_worker'
import Navbar from './common/Navbar'
import Notify from './common/Notify'
import Login from './auth/Login'
import Logout from './auth/Logout'
import SwitchSession from './auth/SwitchSession'
import ListConversations from './conversations/List'
import ConversationDetails from './conversations/Details'
import CreateConversation from './conversations/Create'

// TODO replace with specific icons
FaLibrary.add(far, fas, fab)

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
        <Route exact path="/" component={ListConversations}/>
        <Route exact path="/create/" component={CreateConversation}/>
        <Route exact path="/login/" component={Login}/>
        <Route exact path="/logout/" component={Logout}/>
        <Route exact path="/switch/:id(\d+)/" component={SwitchSession}/>
        <Route exact path="/:key([a-f0-9]{10,64})/" component={ConversationDetails}/>

        <Route component={NotFound}/>
      </Switch>
    )
  }
}

class App extends Component {
  state = {
    title: null,
    error: null,
    message: null,
    user: null,
    other_sessions: [],
    conn_status: null,
  }
  worker = new Worker(this)
  message_timeout1 = null
  message_timeout2 = null

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

  setMessage = async message => {
    clearInterval(this.message_timeout1)
    clearInterval(this.message_timeout2)
    this.message_timeout1 = setTimeout(() => {
      this.setState({message})
      this.message_timeout2 = setTimeout(() => this.setState({message: null}), 8000)
    }, 50)
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
    // } else if (error.status === 0) {
      // this.setState({connection_status: conn_status.not_connected})
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
      setMessage: msg => this.setMessage(msg),
      setError: error => this.setError(error),
      setTitle: title => this.setState({title}),
      user: this.state.user,
      other_sessions: this.state.other_sessions,
      worker: this.worker,
    }
    return (
      <GlobalContext.Provider value={ctx}>
        <Navbar app_state={this.state} location={this.props.location}/>
        <main className="container">
          <Main app_state={this.state}/>
        </main>
        <Notify/>
      </GlobalContext.Provider>
    )
  }
}

export default withRouter(App)
